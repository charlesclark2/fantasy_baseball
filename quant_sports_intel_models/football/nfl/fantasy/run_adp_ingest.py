"""run_adp_ingest.py — NF-D3: land the ADP market-consensus BENCHMARK asset to the sports lake.

Pulls Fantasy Football Calculator real-draft ADP (via `adp_source`), crosswalks it to our gsis
`player_id`, and lands it as a Delta asset under `nfl/fantasy/benchmarks/adp` (season-partitioned) —
the NF-D3 `nfl/fantasy/benchmarks/` competitor-benchmark asset. Reproducible + leakage-safe (FFC ADP
is snapshotted the week before Week 1). Historical coverage 2018–2024 (2025 absent from FFC) + the
current board year.

⭐ RUN ON THE LAPTOP (SF-free sports lake; the FFC pull caches to artifacts/adp_cache). Landing needs
`SPORTS_LAKE_REGION=us-east-2`.

    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_adp_ingest \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --from 2018 --to 2026 --s3

The emitted asset (one row per player-season with ADP): `season, source, adp_format, player_id,
player_name, position, team, adp, adp_stdev, adp_high, adp_low, times_drafted`. Consumers: the NF-D3
benchmark scorer (model-vs-market grade) and the OPTIONAL QB/RB ADP prior (`blend_adp_prior`).
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

from quant_sports_intel_models.football.nfl.fantasy import adp_source as A  # noqa: E402

log = logging.getLogger("nfl.fantasy.adp_ingest")

_ASSET_COLS = ["season", "source", "adp_format", "player_id", "player_name", "position", "team",
               "adp", "adp_stdev", "adp_high", "adp_low", "times_drafted"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="NF-D3 — land the FFC ADP benchmark asset")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default="main_nfl_marts")
    ap.add_argument("--from", dest="from_season", type=int, default=2018)
    ap.add_argument("--to", dest="to_season", type=int, default=2026)
    ap.add_argument("--fmt", default="ppr", choices=("ppr", "half-ppr", "standard"))
    ap.add_argument("--teams", type=int, default=12)
    ap.add_argument("--refresh", action="store_true", help="re-fetch FFC even if a cache file exists")
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
            adp = A.load_adp_for_season(con, y, fmt=args.fmt, teams=args.teams,
                                        refresh=args.refresh, schema=args.schema)
            if adp.empty:
                log.warning("  season %d: no FFC ADP — skip", y)
                summary[y] = {"status": "no_data"}
                continue
            asset = adp.reindex(columns=_ASSET_COLS)
            cov = A.coverage(adp)
            log.info("  season %d: %d rows (%d skill, %.0f%% gsis-matched)", y, cov["n_rows"],
                     cov["n_skill"], cov["pct_matched"])
            summary[y] = {"status": "ok", **cov}
            if args.s3 or args.lake_root:
                n = s3io.write_dataframe(asset.assign(season=int(y)), sport="nfl",
                                         source="adp_benchmark", season=int(y),
                                         tier="fantasy/benchmarks", local_root=args.lake_root)
                log.info("    landed %d rows → nfl/fantasy/benchmarks/adp_benchmark season=%d", n, y)
    finally:
        con.close()

    dest = f"local lake {args.lake_root}" if args.lake_root else ("the S3 sports lake" if args.s3 else "(local only — no --s3)")
    log.info("done. %d seasons; landed to %s", len(summary), dest)
    print(json.dumps({"seasons": summary, "dest": dest}, indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
