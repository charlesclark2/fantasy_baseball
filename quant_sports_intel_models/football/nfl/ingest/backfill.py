"""backfill.py  (NFL-N0.2 — the off-Lambda full-history runner)
================================================================
The one-time fresh nflverse re-pull, run OFF the weekly path (no 15-min Lambda cap; the box or
a laptop). Same registry + same `run_ingest` as `handler.py` — the ONLY difference is scope:
all sources × the backfill window.

WINDOW (`nfl_data_inventory.md` §7/§8): the **advanced stack (NGS + pbp_participation floor =
2016; PFR = 2018; FTN = 2022) → default 2016–2025.** Team/box/PBP/roster/schedule extend to
1999 and draft/combine/players are all-time — pass a wider `--seasons` for those (a below-floor
season for an advanced feed 404s → a clean empty skip, so a wide window is safe, just sparse at
the edges). This is a **FRESH re-pull** — the stale Snowflake `FOOTBALL_DATA` rows are NOT
migrated (brownfield §0).

COST: nflverse is FREE + public (no API budget to watch, unlike NCAAF's CFBD Tier-3 gate) —
the only cost is DuckDB compute + the S3 PUTs. ⚠️ the big feeds (`pbp` 372 cols × ~50k
rows/season, `pbp_participation`, `ftn_charting`) are the wall-clock cost → run ON THE BOX
(in-region multipart PUTs, instance-role write; the laptop's IAM is read-only + out-of-region).

  # BOX (>1 min — hand to the operator), all sources 2016–2025:
  docker compose -f services/dagster/aws/docker-compose.yml exec -T \
    -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \
    python -m quant_sports_intel_models.football.nfl.ingest.backfill --seasons 2016-2025

Idempotent: each season is a Delta partition overwrite, so a re-run (or a `--skip-existing`
resume) is value-identical. Start narrow (a couple cheap sources / a 2-season window) to prove
the path before the full pull.
"""
from __future__ import annotations

import argparse
import logging

from . import s3io
from .handler import _parse_seasons, load_env, run_ingest
from .sources import DEFAULT_SOURCES, SOURCES, build_ctx

log = logging.getLogger(__name__)

# The advanced-stack backfill window (`nfl_data_inventory.md` §7). Widen --seasons to 1999 for
# the box/team/roster/schedule feeds; all-time for draft/combine/players.
DEFAULT_BACKFILL = "2016-2025"


def main() -> None:
    p = argparse.ArgumentParser(description="NFL fresh nflverse backfill (off-Lambda).")
    p.add_argument("--seasons", default=DEFAULT_BACKFILL, help=f"default {DEFAULT_BACKFILL}")
    p.add_argument("--sources", help="comma list (default: all). Start narrow to prove the path.")
    p.add_argument("--exclude", help="comma list of sources to drop (e.g. pbp — the heaviest feed)")
    p.add_argument("--weeks", help="(reserved) week scope; nflverse reads whole seasons")
    p.add_argument("--local-root", help="write Delta to a local dir instead of S3 (dry backfill)")
    p.add_argument("--bucket", default=s3io.DEFAULT_BUCKET)
    p.add_argument("--skip-existing", action="store_true",
                   help="skip (source, season) partitions already landed — a pure S3/metadata "
                        "check (ZERO fetches); use to RESUME without re-pulling landed seasons")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_env()  # pick up ODDS_API_KEY from .env for standalone laptop runs
    seasons = _parse_seasons(args.seasons)
    sources = args.sources.split(",") if args.sources else None
    if args.exclude:
        excl = set(args.exclude.split(","))
        # default base = DEFAULT_SOURCES (excludes the on_demand paid odds feeds — N0.4)
        sources = [s for s in (sources or DEFAULT_SOURCES) if s not in excl]
    weeks = [int(w) for w in args.weeks.split(",")] if args.weeks else None

    log.info("Backfill NFL seasons=%s sources=%s → %s",
             seasons, sources or f"DEFAULT({len(DEFAULT_SOURCES)}; excl. paid on_demand odds)",
             args.local_root or f"s3://{args.bucket}/nfl/raw")
    # ONE ctx for the whole backfill so the DuckDB httpfs connection persists across seasons.
    ctx = build_ctx()
    # Run season-by-season so an interruption leaves completed seasons durably landed.
    total = {}
    for season in seasons:
        manifest = run_ingest([season], sources=sources, weeks=weeks,
                              local_root=args.local_root, bucket=args.bucket, ctx=ctx,
                              skip_existing=args.skip_existing)
        total.update(manifest)
        landed_yr = sum(1 for v in manifest.values() if isinstance(v, int) and v > 0)
        log.info("  season %s done (%d sources landed)", season, landed_yr)

    # Distinguish the THREE outcomes — a "skipped (already ingested)" and an empty-slice 0 are
    # NOT errors (an advanced feed below its coverage floor legitimately writes 0 rows).
    landed = [k for k, v in total.items() if isinstance(v, int) and v > 0]
    empty = [k for k, v in total.items() if isinstance(v, int) and v == 0]
    skipped = [k for k, v in total.items() if isinstance(v, str) and v.startswith("skipped")]
    errs = [k for k, v in total.items() if isinstance(v, str) and v.startswith("ERROR")]
    log.info("Backfill complete: %d landed, %d empty (below-floor/no-data), %d skipped, %d ERRORS%s",
             len(landed), len(empty), len(skipped), len(errs),
             (": " + ", ".join(errs)) if errs else "")


if __name__ == "__main__":
    main()
