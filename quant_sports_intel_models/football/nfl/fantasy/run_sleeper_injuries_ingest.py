"""run_sleeper_injuries_ingest.py — NF-D5: land the Sleeper forward-availability feed to the lake.

Pulls Sleeper's `v1/players/nfl` snapshot (via `sleeper_injuries_source`), resolves `player_id`
(native gsis_id + the deterministic name/position crosswalk fallback), and lands it as a Delta asset
under `nfl/raw/sleeper_injuries` (season-partitioned, overwritten on each capture) — the RAW tier
`load_forward_roster_status` (run_season_projection.py) reads via the `stg_nfl_sleeper_injuries`
staging model, COALESCING it OVER nflverse's roster status (Sleeper preferred — fresher, offseason-
covering; nflverse the fallback).

⭐ RUN ON THE LAPTOP (SF-free sports lake; the pull caches to artifacts/sleeper_injuries_cache).
Landing needs `SPORTS_LAKE_REGION=us-east-2`. WARN-tier / non-serving — a failed run never blocks
the projection (nflverse-only fallback holds).

    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_sleeper_injuries_ingest \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --s3

⏱️ RECURRING (mirrors the NF-D1 roll-forward cadence): re-run daily through camp so offseason
surgery/PUP/IR cases surface on the board as Sleeper reports them, not once. See
`pipeline/jobs/sports_nfl_sleeper_injuries_job.py` for the (operator-gated STOPPED) Dagster schedule.

After landing, rebuild just this staging model so `load_forward_roster_status` sees the fresh
snapshot (from `quant_sports_intel_models/sports_dbt`, dbt-core not dbtf — see run_season_projection.py
header):
    export SPORTS_LAKE_REGION=us-east-2
    python -m dbt.cli.main run --select stg_nfl_sleeper_injuries --threads 1
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import sleeper_injuries_source as SI  # noqa: E402

log = logging.getLogger("nfl.fantasy.sleeper_injuries_ingest")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-D5 — land the Sleeper forward-availability feed")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default="main_nfl_marts")
    ap.add_argument("--season", type=int, default=None,
                     help="default: current_season() (clock-derived NFL roll-forward season)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch Sleeper even if today's cache exists")
    ap.add_argument("--s3", action="store_true", help="land the feed to the S3 sports lake")
    ap.add_argument("--lake-root", default=None, help="land to a LOCAL-FS Delta tree instead of S3")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if args.s3 and args.lake_root:
        ap.error("--s3 and --lake-root are mutually exclusive")
    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb} — build the NFL marts first")

    from quant_sports_intel_models.football.nfl.ingest.sources import current_season

    season = args.season if args.season is not None else current_season()

    import duckdb

    if args.s3 or args.lake_root:
        from quant_sports_intel_models.football.nfl.ingest import s3io

    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        df = SI.load_sleeper_injuries(con, season, refresh=args.refresh, schema=args.schema)
    finally:
        con.close()

    cov = SI.coverage(df)
    log.info("Sleeper forward-availability feed: season=%s %d rows, %d gsis-matched, %d flagged (%s)",
             season, cov["n_rows"], cov["n_matched"], cov["n_flagged"], cov.get("by_injury_status"))

    dest = "(local only — no --s3)"
    if args.s3 or args.lake_root:
        n = s3io.write_dataframe(df, sport="nfl", source="sleeper_injuries", season=int(season),
                                 tier="raw", local_root=args.lake_root)
        dest = f"local lake {args.lake_root}" if args.lake_root else "the S3 sports lake"
        log.info("landed %d rows → nfl/raw/sleeper_injuries season=%d (%s)", n, season, dest)

    print(json.dumps({"season": season, **cov, "dest": dest}, indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
