"""run_ecr_ingest.py — NF-D3: land the FantasyPros ECR competitor-benchmark asset to the sports lake.

The sibling of `run_adp_ingest.py`: pulls FantasyPros Expert Consensus Rankings (via
`fantasypros_source`), crosswalks to our gsis `player_id`, and lands it as a season-partitioned Delta
asset under `nfl/fantasy/benchmarks/ecr` — the NF-D3 `nfl/fantasy/benchmarks/` competitor-benchmark
asset (system #2, after ADP). Reproducible + leakage-safe (each year's ECR is FantasyPros' archived
final PRESEASON consensus, `last_updated` in early September of that year). Coverage 2019–2026 —
including 2025, the season FFC ADP is missing.

⭐ RUN ON THE LAPTOP (SF-free sports lake; the FP pull caches to artifacts/ecr_cache). Landing needs
`SPORTS_LAKE_REGION=us-east-2`.

    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_ecr_ingest \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --from 2019 --to 2026 --s3

The emitted asset (one row per player-season with an ECR): `season, source, scoring, player_id,
player_name, position, team, rank_ecr, rank_ave, rank_std, rank_min, rank_max, pos_rank, tier,
total_experts, last_updated`. Consumers: the NF-D3 benchmark scorecard (`benchmark_scorecard.py`).
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

from quant_sports_intel_models.football.nfl.fantasy import fantasypros_source as F  # noqa: E402

log = logging.getLogger("nfl.fantasy.ecr_ingest")

_ASSET_COLS = ["season", "source", "scoring", "player_id", "player_name", "position", "team",
               "rank_ecr", "rank_ave", "rank_std", "rank_min", "rank_max", "pos_rank",
               "tier", "total_experts", "last_updated"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="NF-D3 — land the FantasyPros ECR benchmark asset")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default="main_nfl_marts")
    ap.add_argument("--from", dest="from_season", type=int, default=2019)
    ap.add_argument("--to", dest="to_season", type=int, default=2026)
    ap.add_argument("--scoring", default="PPR", choices=("PPR", "HALF", "STD"))
    ap.add_argument("--refresh", action="store_true", help="re-fetch FP even if a cache file exists")
    ap.add_argument("--s3", action="store_true", help="land the benchmark asset to the S3 sports lake")
    ap.add_argument("--lake-root", default=None, help="land to a LOCAL-FS Delta tree instead of S3")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if args.s3 and args.lake_root:
        ap.error("--s3 and --lake-root are mutually exclusive")
    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb} — build the NFL marts first")

    import duckdb

    if args.s3 or args.lake_root:
        from quant_sports_intel_models.football.nfl.ingest import s3io

    con = duckdb.connect(args.duckdb, read_only=True)
    summary = {}
    try:
        for y in range(args.from_season, args.to_season + 1):
            ecr = F.load_ecr_for_season(con, y, scoring=args.scoring, refresh=args.refresh,
                                        schema=args.schema)
            if ecr.empty:
                log.warning("  season %d: no FantasyPros ECR — skip", y)
                summary[y] = {"status": "no_data"}
                continue
            asset = ecr.reindex(columns=_ASSET_COLS)
            cov = F.coverage(ecr)
            log.info("  season %d: %d rows (%d skill, %.0f%% gsis-matched)", y, cov["n_rows"],
                     cov["n_skill"], cov["pct_matched"])
            summary[y] = {"status": "ok", **cov}
            if args.s3 or args.lake_root:
                n = s3io.write_dataframe(asset.assign(season=int(y)), sport="nfl",
                                         source="ecr_benchmark", season=int(y),
                                         tier="fantasy/benchmarks", local_root=args.lake_root)
                log.info("    landed %d rows → nfl/fantasy/benchmarks/ecr_benchmark season=%d", n, y)
    finally:
        con.close()

    dest = f"local lake {args.lake_root}" if args.lake_root else ("the S3 sports lake" if args.s3 else "(local only — no --s3)")
    log.info("done. %d seasons; landed to %s", len(summary), dest)
    print(json.dumps({"seasons": summary, "dest": dest}, indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
