"""run_projection_benchmark_ingest.py — NF-D3: land the Sleeper + ESPN benchmark assets to the lake.

The third/fourth competitor benchmarks (after ADP `run_adp_ingest.py` + ECR `run_ecr_ingest.py`):
  • sleeper — Sleeper (Rotowire) full-season projections, leakage-safe (verified frozen-preseason),
    a real POINT projection (`proj_pts_ppr` + `proj_games`). Lands `nfl/fantasy/benchmarks/sleeper_benchmark`.
  • espn    — ESPN PPR draft rank (unofficial read API; a preseason ranking). Lands
    `nfl/fantasy/benchmarks/espn_benchmark`.

⭐ RUN ON THE LAPTOP (SF-free sports lake; pulls cache to artifacts/{sleeper,espn}_cache). Landing needs
`SPORTS_LAKE_REGION=us-east-2`.

    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_projection_benchmark_ingest \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --systems sleeper,espn \
      --from 2019 --to 2026 --s3
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

from quant_sports_intel_models.football.nfl.fantasy import espn_source as E  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import sleeper_source as S  # noqa: E402

log = logging.getLogger("nfl.fantasy.proj_benchmark_ingest")

# system -> (loader, asset-source-name, ordered asset columns)
_SYSTEMS = {
    "sleeper": (S.load_sleeper_for_season, S.coverage, "sleeper_benchmark",
                ["season", "source", "provider", "player_id", "player_name", "position", "team",
                 "proj_pts_ppr", "proj_pts_half", "proj_pts_std", "proj_games", "sleeper_id"]),
    "espn": (E.load_espn_for_season, E.coverage, "espn_benchmark",
             ["season", "source", "player_id", "player_name", "position", "espn_id", "ppr_draft_rank"]),
}


def main(argv=None):
    ap = argparse.ArgumentParser(description="NF-D3 — land Sleeper/ESPN projection benchmark assets")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default="main_nfl_marts")
    ap.add_argument("--systems", default="sleeper,espn", help="comma list: sleeper,espn")
    ap.add_argument("--from", dest="from_season", type=int, default=2019)
    ap.add_argument("--to", dest="to_season", type=int, default=2026)
    ap.add_argument("--refresh", action="store_true", help="re-fetch even if a cache file exists")
    ap.add_argument("--s3", action="store_true", help="land to the S3 sports lake")
    ap.add_argument("--lake-root", default=None, help="land to a LOCAL-FS Delta tree instead of S3")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if args.s3 and args.lake_root:
        ap.error("--s3 and --lake-root are mutually exclusive")
    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb} — build the NFL marts first")
    systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    for s in systems:
        if s not in _SYSTEMS:
            ap.error(f"unknown system '{s}' — choose from {list(_SYSTEMS)}")

    import duckdb

    if args.s3 or args.lake_root:
        from quant_sports_intel_models.football.nfl.ingest import s3io

    con = duckdb.connect(args.duckdb, read_only=True)
    summary = {}
    try:
        for sysname in systems:
            loader, cov_fn, source, cols = _SYSTEMS[sysname]
            summary[sysname] = {}
            for y in range(args.from_season, args.to_season + 1):
                try:
                    df = loader(con, y, refresh=args.refresh, schema=args.schema)
                except Exception as e:  # noqa: BLE001 — a fetch failure NULLs that season, never the run
                    log.warning("  %s %d: fetch failed (%s) — skip", sysname, y, e)
                    summary[sysname][y] = {"status": "error"}
                    continue
                if df.empty:
                    log.warning("  %s %d: no data — skip", sysname, y)
                    summary[sysname][y] = {"status": "no_data"}
                    continue
                cov = cov_fn(df)
                log.info("  %s %d: %d rows (%d skill, %.0f%% gsis-matched)", sysname, y, cov["n_rows"],
                         cov["n_skill"], cov["pct_matched"])
                summary[sysname][y] = {"status": "ok", **cov}
                if args.s3 or args.lake_root:
                    asset = df.reindex(columns=cols).assign(season=int(y))
                    n = s3io.write_dataframe(asset, sport="nfl", source=source, season=int(y),
                                             tier="fantasy/benchmarks", local_root=args.lake_root)
                    log.info("    landed %d rows → nfl/fantasy/benchmarks/%s season=%d", n, source, y)
    finally:
        con.close()

    dest = f"local lake {args.lake_root}" if args.lake_root else ("the S3 sports lake" if args.s3 else "(local only — no --s3)")
    log.info("done. systems=%s; landed to %s", systems, dest)
    print(json.dumps({"systems": summary, "dest": dest}, indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
