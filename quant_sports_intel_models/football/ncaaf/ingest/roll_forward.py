"""roll_forward.py  (NCAAF-P0.7 — the annual PRE-SEASON season roll-forward ingest)
===================================================================================
Stand the UPCOMING season's pre-season data up in the lake so the P1.5 futures board + the live
P1.4 game-model board can RUN before kickoff. This is the recurring PRE-SEASON refresh of exactly
two things — the SCHEDULE and the pre-season COVARIATE priors P1.2 fits week-1 strength on (the
`ROLL_FORWARD_SOURCES` set in `sources.py`) — for `current_season()` (clock-derived, never pinned).

WHY IT RECURS (not a one-time pull), both verified live 2026-07-24:
  1. Pre-season schedules are DYNAMIC — games are added / moved / cancelled all summer.
  2. Covariates publish on a ROLLING basis — `games`/`transfer_portal`/`recruiting_players`/`teams`
     were already published for 2026, but `returning_production`/`talent`/`coaches`/`roster` still
     returned 0 rows and fill in through fall camp. A weekly refresh keeps catching them.

This is the FIRST INSTANCE of an ANNUAL cadence — `current_season()` auto-advances, so the exact
same job re-runnable next August lands 2027 with no code change. The recurring orchestration is the
Dagster pre-season schedule (`pipeline/schedules/sports_rollforward_schedules.py`); this module is
the pure driver it (and a manual laptop/box run) calls.

Same registry + same `run_ingest` as `handler.py`/`backfill.py` — the only thing sport/story-specific
is the source SET (`ROLL_FORWARD_SOURCES`) and the clock-derived season. Idempotent: each (source,
season) is a Delta partition overwrite, so re-running mid-summer just refreshes the partition.

Scope boundary (stated so nobody expects more): this lands the pre-season SCHEDULE + COVARIATES only.
It does NOT pull the per-game modelling data (plays / play_stats / box_advanced) or odds — those are
the expensive in-season / P0.6b concerns on their own budgets. After this lands, the sports dbt marts
must rebuild (the Dagster job chains that) and P1.2 must be re-fit for the season (the operator step)
before `run_season_simulation --season <YYYY>` can render a board.

  # LAPTOP or BOX, repo root (cheap — ~8 CFBD calls; still >1s so hand to the operator):
  uv run python -m quant_sports_intel_models.football.ncaaf.ingest.roll_forward
  # (defaults to current_season(); --dry-run lists what would pull without any CFBD call)
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from . import s3io
from .handler import load_env, run_ingest
from .sources import ROLL_FORWARD_SOURCES, build_ctx, current_season

log = logging.getLogger(__name__)


def run_roll_forward(
    season: int | None = None,
    *,
    sources: list[str] | None = None,
    bucket: str = s3io.DEFAULT_BUCKET,
    local_root: str | None = None,
    ctx=None,
) -> dict[str, Any]:
    """Ingest the pre-season roll-forward feeds for `season` (default `current_season()`).

    Thin wrapper over `run_ingest` that pins the season to the clock-derived roll-forward target
    and the source set to `ROLL_FORWARD_SOURCES`. Returns the `run_ingest` manifest
    ({source/season: rows|"ERROR: …"}). Per-source failures are ALERT-loud-but-continue inside
    `run_ingest` (peripheral ingestion tier) — one un-published covariate never sinks the batch.

    Emits a per-source coverage summary and WARNs on any source that landed 0 rows: a not-yet-
    published pre-season covariate (the expected mid-summer state) — the signal to re-run the
    cadence closer to kickoff before the final P1.2 re-fit + board.
    """
    season = int(season) if season is not None else current_season()
    sources = list(sources) if sources else list(ROLL_FORWARD_SOURCES)
    if ctx is None:
        ctx = build_ctx()
    log.info("NCAAF roll-forward: season=%s sources=%s → %s", season, sources,
             local_root or f"s3://{bucket}/ncaaf/raw")
    manifest = run_ingest([season], sources=sources, bucket=bucket, local_root=local_root, ctx=ctx)

    # Coverage summary — distinguish landed / not-yet-published (0 rows) / errored so the operator
    # can see at a glance which covariates CFBD hasn't posted for the upcoming season yet.
    landed, empty, errored = [], [], []
    for name in sources:
        v = manifest.get(f"{name}/{season}")
        if isinstance(v, int):
            (landed if v > 0 else empty).append(name)
        else:
            errored.append(name)
    for name in landed:
        log.info("  ✅ %-22s %s rows", name, manifest.get(f"{name}/{season}"))
    if empty:
        log.warning("ALERT roll-forward: %d source(s) returned 0 rows for %s — not yet published "
                    "by CFBD (expected pre-season; re-run the cadence closer to kickoff): %s",
                    len(empty), season, ", ".join(empty))
    if errored:
        log.warning("ALERT roll-forward: %d source(s) ERRORED for %s: %s",
                    len(errored), season, ", ".join(errored))
    log.info("roll-forward %s: %d landed, %d not-yet-published, %d errored",
             season, len(landed), len(empty), len(errored))
    return manifest


def _cli() -> None:
    p = argparse.ArgumentParser(description="NCAAF pre-season roll-forward ingest (P0.7).")
    p.add_argument("--season", type=int, default=None,
                   help="season to roll forward (default: current_season() — clock-derived, "
                        "the upcoming/in-progress season)")
    p.add_argument("--sources", help="comma list (default: the ROLL_FORWARD_SOURCES set — "
                                      "schedule + pre-season covariates)")
    p.add_argument("--local-root", help="write Delta to a local dir instead of S3 (offline dry run)")
    p.add_argument("--bucket", default=s3io.DEFAULT_BUCKET)
    p.add_argument("--dry-run", action="store_true",
                   help="print the resolved season + source set and exit — ZERO CFBD calls")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_env()  # pick up CFBD_API_KEY from .env for standalone laptop runs
    season = args.season if args.season is not None else current_season()
    sources = args.sources.split(",") if args.sources else list(ROLL_FORWARD_SOURCES)

    if args.dry_run:
        log.info("[dry-run] roll-forward season=%s (clock-derived: %s) sources=%s — no CFBD calls",
                 season, current_season(), sources)
        return

    manifest = run_roll_forward(season, sources=sources, bucket=args.bucket,
                                local_root=args.local_root)
    for k, v in manifest.items():
        if not k.startswith("_"):
            print(f"  {k}: {v}")


if __name__ == "__main__":
    _cli()
