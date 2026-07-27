"""build_player_xref.py — MLB Edge-E7.4 runner: build `dim_player_xref` off the S3 lake.

SF-FREE, DuckDB over the S3 Delta lake (instance-role auth). Reads:
    baseball/milb/the_board              (E7.7 — FanGraphs THE BOARD; FV/ETA/rank/level/org)
    baseball/milb/fg_leaderboards        (E7.7 — the fg_minor_id ↔ xMLBAMID BRIDGE)
    baseball/milb/player_game_logs       (E7.1 — MLBAM ids + level/org for every minor leaguer)
    baseball/lakehouse/stg_statsapi_player_profiles   (the existing MLB player master)
    baseball/lakehouse_raw/fg_{hitting_leaderboard,stuff_plus}_raw   (fg_mlb_id ↔ xMLBAMID)

Writes `<out>/dim_player_xref.parquet` (+ `--s3` lands the Delta table at
`baseball/milb/derived/dim_player_xref`, beside E7.3's MLE outputs) and prints the per-hop
match-rate report the E7.4 AC requires. `--report-json` also persists that report.

⚠️ OPERATOR-RUN (>2 min: it scans the MLB FanGraphs raw feeds, ~230k JSON rows). `--dry-run`
reports without writing; `--no-enforce` reports a degraded bridge instead of failing.

    # LAPTOP (or box) — full build + land to S3:
    uv run python betting_ml/scripts/milb_xref/build_player_xref.py --s3

    # report only, no write:
    uv run python betting_ml/scripts/milb_xref/build_player_xref.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.milb_xref.player_xref import (  # noqa: E402
    MILB,
    XREF_TABLE,
    XrefValidationError,
    build_xref,
    format_report,
    register_board,
    s3_sources,
)

log = logging.getLogger("e7_4.build")


def _connect():
    """DuckDB with the S3 credential chain + the Delta extension (the MiLB tables are Delta; the
    MLB profile/FanGraphs-raw tables glob parquet). Mirrors E7.3's `build_graduated_pairs`."""
    from scripts.utils.lakehouse_read import duck_connect

    conn = duck_connect()
    conn.execute("INSTALL delta; LOAD delta")   # LOUD on failure — a silent fallback is INC-31
    return conn


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="E7.4 — build dim_player_xref (prospect identity spine)")
    p.add_argument("--out-dir", default="quant_sports_intel_models/baseball/edge_program/"
                                        "ablation_results/e7_4_artifacts")
    p.add_argument("--season-floor", type=int, default=None,
                   help="only MiLB game-log seasons >= this (default: all, 2005+)")
    p.add_argument("--s3", action="store_true",
                   help=f"also land the dimension at baseball/milb/derived/{XREF_TABLE} (Delta)")
    p.add_argument("--dry-run", action="store_true",
                   help="report only; write nothing. Tripwires stay ARMED — a dry run must tell "
                        "you whether the real run would pass, not just print numbers")
    p.add_argument("--no-enforce", action="store_true",
                   help="report a degraded bridge instead of raising (diagnosis only)")
    p.add_argument("--report-json", default=None, help="also write the match-rate report here")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")

    conn = _connect()
    src = s3_sources()
    register_board(conn)   # landmine 1/2: the ONLY sanctioned board reader

    try:
        res = build_xref(conn, src, season_floor=args.season_floor, enforce=not args.no_enforce)
    except XrefValidationError as e:
        log.error("XREF BUILD FAILED — %s", e)
        return 1

    print(format_report(res.report))

    if args.report_json:
        Path(args.report_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_json).write_text(json.dumps(res.report, indent=2, default=str))
        log.info("wrote report %s", args.report_json)

    if args.dry_run:
        log.info("--dry-run: nothing written (%d rows built)", len(res.dim))
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{XREF_TABLE}.parquet"
    res.dim.to_parquet(dest, index=False)
    log.info("wrote %s (%d rows)", dest, len(res.dim))

    if args.s3:
        from deltalake import write_deltalake

        from scripts.utils.delta_lake import storage_options

        # Un-partitioned full overwrite: the dimension is small (~45k rows) and is a CURRENT-STATE
        # snapshot, so a partition scheme would buy nothing and a stale partition would be a
        # silent-mixed-vintage hazard. Point-in-time prospect history lives in the_board's as_of
        # snapshots (E7.8 reads those), not here.
        write_deltalake(f"{MILB}/derived/{XREF_TABLE}", res.dim, mode="overwrite",
                        schema_mode="overwrite", storage_options=storage_options())
        log.info("landed %s at %s/derived/%s", XREF_TABLE, MILB, XREF_TABLE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
