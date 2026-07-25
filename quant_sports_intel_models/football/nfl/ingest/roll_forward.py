"""roll_forward.py  (NF-D1 — the annual NFL season roll-forward ingest)
=========================================================================
Stand the UPCOMING season's rosters/schedule/injuries/rookie-class data up in the lake so
MVP-1's fantasy board (`mart_nfl_fantasy_season_projection`) can sharpen off REAL current-season
data instead of falling back to the prior season's carryover. This is the recurring refresh of
exactly the cheap, unauthenticated `ROLL_FORWARD_SOURCES` set in `sources.py`, for
`current_season()` (clock-derived, never pinned) — the NFL analog of NCAAF-P0.7
(`ncaaf/ingest/roll_forward.py`), same shape, same rationale.

WHY IT RECURS (not a one-time pull):
  1. Rosters/schedules move all summer — free agency, the draft, OTAs/camp cuts, preseason slate
     changes. A pull in March looks nothing like the pull in August.
  2. `depth_charts` (the 2025+ daily ESPN role snapshots `stg_nfl_depth_charts` ASOF-maps to a
     week) has NOTHING to map to until `schedules` carries the season — so depth-chart coverage
     is 0-mapped until the schedule lands, then fills in as camp battles resolve through the
     summer. A weekly refresh keeps catching both.

This is the FIRST INSTANCE of the NFL annual cadence — `current_season()` auto-advances, so the
exact same job re-runnable next spring lands 2027 with no code change.

Same registry + same `run_ingest` as `handler.py`/`backfill.py` — the only thing story-specific is
the source SET (`ROLL_FORWARD_SOURCES`) and the clock-derived season. Idempotent: each (source,
season) is a Delta partition overwrite, so re-running mid-summer just refreshes the partition.

⚠️ UNLIKE NCAAF's P0.7 (which calls the paid/keyed CFBD API), every roll-forward source here is a
FREE, unauthenticated nflverse release-Parquet read (`ODDS_API_KEY` is never touched) — there is
no external key to provision before this can run.

Scope boundary (stated so nobody expects more): this lands rosters + schedule + depth charts +
injuries + the rookie draft/combine class ONLY. It does NOT pull the realized-game stack
(pbp / stats_player_* / snap_counts / NGS / PFR / QBR) — those don't exist for an unplayed season
and are the in-season NF-D2/NF1 concern on their own cadence. After this lands, the sports dbt
NFL marts must rebuild (`stg_nfl_schedules`/`stg_nfl_depth_charts`/`stg_nfl_weekly_rosters`/…) —
the Dagster job chains that — before MVP-1's projection re-run picks up the sharper role.

  # LAPTOP or BOX, repo root (cheap — 7 unauthenticated nflverse release reads; still >1s so hand
  # to the operator unless verifying live during a session):
  uv run python -m quant_sports_intel_models.football.nfl.ingest.roll_forward
  # (defaults to current_season(); --dry-run lists what would pull without any network call)
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
    """Ingest the season roll-forward feeds for `season` (default `current_season()`).

    Thin wrapper over `run_ingest` that pins the season to the clock-derived roll-forward target
    and the source set to `ROLL_FORWARD_SOURCES`. Returns the `run_ingest` manifest
    ({source/season: rows|"ERROR: …"}). Per-source failures are ALERT-loud-but-continue inside
    `run_ingest` (peripheral ingestion tier) — one not-yet-published feed never sinks the batch.

    Emits a per-source coverage summary and WARNs on any source that landed 0 rows: a
    not-yet-published feed for the upcoming season (nflverse 404s clean-skip to an empty
    DataFrame — see `sources._nflverse_seasonal`/`_nflverse_single`) — the signal to re-run the
    cadence closer to kickoff before MVP-1's re-run.
    """
    season = int(season) if season is not None else current_season()
    sources = list(sources) if sources else list(ROLL_FORWARD_SOURCES)
    if ctx is None:
        ctx = build_ctx()
    log.info("NFL roll-forward: season=%s sources=%s → %s", season, sources,
             local_root or f"s3://{bucket}/nfl/raw")
    manifest = run_ingest([season], sources=sources, bucket=bucket, local_root=local_root, ctx=ctx)

    # Coverage summary — distinguish landed / not-yet-published (0 rows) / errored so the operator
    # can see at a glance which feeds nflverse hasn't posted for the upcoming season yet.
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
                    "by nflverse (expected pre-season; re-run the cadence closer to kickoff): %s",
                    len(empty), season, ", ".join(empty))
    if errored:
        log.warning("ALERT roll-forward: %d source(s) ERRORED for %s: %s",
                    len(errored), season, ", ".join(errored))
    log.info("roll-forward %s: %d landed, %d not-yet-published, %d errored",
             season, len(landed), len(empty), len(errored))
    return manifest


def _cli() -> None:
    p = argparse.ArgumentParser(description="NFL season roll-forward ingest (NF-D1).")
    p.add_argument("--season", type=int, default=None,
                   help="season to roll forward (default: current_season() — clock-derived, "
                        "the upcoming/in-progress season)")
    p.add_argument("--sources", help="comma list (default: the ROLL_FORWARD_SOURCES set — "
                                      "rosters/schedule/depth_charts/injuries/draft/combine)")
    p.add_argument("--local-root", help="write Delta to a local dir instead of S3 (offline dry run)")
    p.add_argument("--bucket", default=s3io.DEFAULT_BUCKET)
    p.add_argument("--dry-run", action="store_true",
                   help="print the resolved season + source set and exit — ZERO network calls")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_env()  # no-op for nflverse (unauthenticated); kept for parity / a future odds knob
    season = args.season if args.season is not None else current_season()
    sources = args.sources.split(",") if args.sources else list(ROLL_FORWARD_SOURCES)

    if args.dry_run:
        log.info("[dry-run] roll-forward season=%s (clock-derived: %s) sources=%s — no network calls",
                 season, current_season(), sources)
        return

    manifest = run_roll_forward(season, sources=sources, bucket=args.bucket,
                                local_root=args.local_root)
    for k, v in manifest.items():
        if not k.startswith("_"):
            print(f"  {k}: {v}")


if __name__ == "__main__":
    _cli()
