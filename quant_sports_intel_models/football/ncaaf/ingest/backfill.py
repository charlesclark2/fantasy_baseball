"""backfill.py  (NCAAF-P0.2 — the off-Lambda full-history runner)
==================================================================
The one-time full-history pull, run OFF the weekly path (no 15-min Lambda cap; the box or a
laptop). Same registry + same `run_ingest` as `handler.py` — the ONLY difference is scope:
all sources × the 2014–2025 window (ncaaf_data_inventory.md §2.7 — player-advanced floor is
2014; team/box/PBP could extend to 2004 but the modelled window is 2014+).

⚠️ COST GATE (ncaaf_data_inventory.md §6): the full backfill is ~15,800 CFBD calls (the
per-game `/plays/stats` pull dominates at ~960/season). The FREE tier is 1,000 calls/mo —
it CANNOT do this (~16 months). BUY Patreon **Tier 3 ($10/mo, 75k calls)** → the whole
backfill completes in one month with ~5× headroom. This runner watches
`_cfbd_calls_remaining` and stops early if the budget is exhausted.

  # LAPTOP or BOX, repo root (>1 min — hand to the operator):
  uv run python -m quant_sports_intel_models.football.ncaaf.ingest.backfill \
      --seasons 2014-2025 --sources games,game_team_stats,plays

Idempotent: each season is a Delta partition overwrite, so a re-run (or a resumed backfill)
is value-identical. Start narrow (a couple of cheap sources / a 2-season window) to prove
the path before committing the ~15.8k-call full pull.
"""
from __future__ import annotations

import argparse
import logging

from . import s3io
from .handler import _parse_seasons, load_env, run_ingest
from .sources import build_ctx

log = logging.getLogger(__name__)

# The modelled backfill window (ncaaf_data_inventory.md §2.7 / §8).
DEFAULT_BACKFILL = "2014-2025"


def main() -> None:
    p = argparse.ArgumentParser(description="NCAAF full-history backfill (off-Lambda).")
    p.add_argument("--seasons", default=DEFAULT_BACKFILL, help=f"default {DEFAULT_BACKFILL}")
    p.add_argument("--sources", help="comma list (default: all 24). Start narrow to prove the path.")
    p.add_argument("--weeks", help="scope week-grained/per-game pulls (default: whole season)")
    p.add_argument("--local-root", help="write Delta to a local dir instead of S3 (dry backfill)")
    p.add_argument("--bucket", default=s3io.DEFAULT_BUCKET)
    p.add_argument("--min-calls", type=int, default=200,
                   help="stop before a season if CFBD calls-remaining drops below this")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_env()  # pick up CFBD_API_KEY / ODDS_API_KEY from .env for standalone laptop runs
    seasons = _parse_seasons(args.seasons)
    sources = args.sources.split(",") if args.sources else None
    weeks = [int(w) for w in args.weeks.split(",")] if args.weeks else None

    log.info("Backfill NCAAF seasons=%s sources=%s → %s",
             seasons, sources or "ALL(24)", args.local_root or f"s3://{args.bucket}/ncaaf/raw")
    # ONE ctx/client for the whole backfill so the CFBD adaptive throttle (self-tunes up on
    # 429) persists across seasons instead of resetting to the fast default each season.
    ctx = build_ctx()
    # Run season-by-season so a budget stop-out leaves completed seasons durably landed.
    total = {}
    for season in seasons:
        manifest = run_ingest([season], sources=sources, weeks=weeks,
                              local_root=args.local_root, bucket=args.bucket, ctx=ctx)
        rem = manifest.get("_cfbd_calls_remaining")
        total.update({k: v for k, v in manifest.items() if not k.startswith("_")})
        log.info("  season %s done; CFBD calls remaining: %s", season, rem)
        if rem is not None and rem < args.min_calls:
            log.warning("ALERT CFBD budget below --min-calls=%s after season %s — STOPPING "
                        "(buy Tier 3 / wait for the monthly reset; completed seasons are landed).",
                        args.min_calls, season)
            break

    ok = sum(1 for v in total.values() if isinstance(v, int))
    errs = [k for k, v in total.items() if isinstance(v, str)]
    log.info("Backfill complete: %d (source,season) landed, %d errors%s",
             ok, len(errs), (": " + ", ".join(errs)) if errs else "")


if __name__ == "__main__":
    main()
