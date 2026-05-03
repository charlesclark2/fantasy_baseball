"""
ingest_fangraphs_zips_csv.py
-----------------------------
Loads pre-season ZiPS projection CSVs (manually downloaded from FanGraphs)
into baseball_data.fangraphs.fg_zips_hitting_raw and fg_zips_pitching_raw.

The FanGraphs API only returns ~11 rows for historical seasons, so the full
pre-season projections must be sourced from manually downloaded CSVs.

Expected filenames (in scripts/raw_files/fangraphs/):
  batting_preseason_zips/fg_batting_zips_pre_YYYY.csv
  pitching_preseason_zips/fg_pitching_zips_pre_YYYY.csv

Season is extracted from the filename. All columns are stored as-is in
raw_json VARIANT; only batter_name / pitcher_name and fg_*_id are promoted
to top-level columns.

Usage:
    # Dry-run (shows row counts per file, no DB writes)
    uv run python scripts/ingest_fangraphs_zips_csv.py --dry-run

    # Load all CSVs (both hitting and pitching, all years)
    uv run python scripts/ingest_fangraphs_zips_csv.py

    # Load a single year
    uv run python scripts/ingest_fangraphs_zips_csv.py --season 2026

    # Load hitting only
    uv run python scripts/ingest_fangraphs_zips_csv.py --type hitting

    # Truncate tables before loading (use when replacing bad API data)
    uv run python scripts/ingest_fangraphs_zips_csv.py --truncate
"""

import argparse
import csv
import logging
import os
import re
import sys
import uuid
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils"))
from snowflake_loader import get_snowflake_connection, append_raw_rows  # noqa: E402

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

RAW_FILES_DIR = Path(__file__).parent / "raw_files" / "fangraphs"
BATTING_DIR = RAW_FILES_DIR / "batting_preseason_zips"
PITCHING_DIR = RAW_FILES_DIR / "pitching_preseason_zips"

HITTING_TABLE = "baseball_data.fangraphs.fg_zips_hitting_raw"
PITCHING_TABLE = "baseball_data.fangraphs.fg_zips_pitching_raw"

PROJECTION_TYPE = "zips"
SOURCE_LABEL = "csv_manual_download"


def _season_from_path(path: Path) -> int:
    m = re.search(r"(\d{4})", path.stem)
    if not m:
        raise ValueError(f"Cannot extract season year from filename: {path.name}")
    return int(m.group(1))


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def ingest_file(
    path: Path,
    table_fqn: str,
    stat_type: str,  # "hitting" or "pitching"
    dry_run: bool,
    conn,
) -> int:
    season = _season_from_path(path)
    rows_raw = _read_csv(path)
    log.info("%s  season=%d  %d rows", path.name, season, len(rows_raw))

    if dry_run:
        return len(rows_raw)

    load_id = str(uuid.uuid4())
    rows = []
    for player in rows_raw:
        # Coerce empty strings to None for cleaner VARIANT storage
        cleaned = {k: (v if v != "" else None) for k, v in player.items()}
        if stat_type == "hitting":
            rows.append({
                "season":           season,
                "batter_name":      player.get("Name"),
                "fg_batter_id":     player.get("PlayerId"),
                "projection_type":  PROJECTION_TYPE,
                "load_id":          load_id,
                "source_endpoint":  SOURCE_LABEL,
                "request_params":   {"file": path.name},
                "http_status_code": None,
                "raw_json":         cleaned,
            })
        else:
            rows.append({
                "season":           season,
                "pitcher_name":     player.get("Name"),
                "fg_pitcher_id":    player.get("PlayerId"),
                "projection_type":  PROJECTION_TYPE,
                "load_id":          load_id,
                "source_endpoint":  SOURCE_LABEL,
                "request_params":   {"file": path.name},
                "http_status_code": None,
                "raw_json":         cleaned,
            })

    inserted = append_raw_rows(table_fqn, rows, conn)
    log.info("Loaded %d rows → %s (season=%d)", inserted, table_fqn, season)
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load pre-season ZiPS CSVs into Snowflake"
    )
    parser.add_argument("--season", type=int, default=None, help="Load only this season year")
    parser.add_argument(
        "--type",
        choices=["hitting", "pitching", "both"],
        default="both",
        dest="stat_type",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate target tables before loading (removes the bad 11-row API data)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    jobs: list[tuple[Path, str, str]] = []  # (path, table_fqn, stat_type)

    if args.stat_type in ("hitting", "both"):
        for path in sorted(BATTING_DIR.glob("fg_batting_zips_pre_*.csv")):
            if args.season and _season_from_path(path) != args.season:
                continue
            jobs.append((path, HITTING_TABLE, "hitting"))

    if args.stat_type in ("pitching", "both"):
        for path in sorted(PITCHING_DIR.glob("fg_pitching_zips_pre_*.csv")):
            if args.season and _season_from_path(path) != args.season:
                continue
            jobs.append((path, PITCHING_TABLE, "pitching"))

    if not jobs:
        log.warning("No matching CSV files found.")
        return

    log.info("%d file(s) to load", len(jobs))

    if dry_run := args.dry_run:
        total = 0
        for path, table_fqn, stat_type in jobs:
            total += ingest_file(path, table_fqn, stat_type, dry_run=True, conn=None)
        log.info("[DRY RUN] %d total rows across %d file(s)", total, len(jobs))
        return

    conn = get_snowflake_connection()
    try:
        if args.truncate:
            tables_to_truncate = set(t for _, t, _ in jobs)
            with conn.cursor() as cur:
                for table in sorted(tables_to_truncate):
                    cur.execute(f"TRUNCATE TABLE {table}")
                    log.info("Truncated %s", table)

        total = 0
        for path, table_fqn, stat_type in jobs:
            total += ingest_file(path, table_fqn, stat_type, dry_run=False, conn=conn)
        log.info("Done. %d total rows across %d file(s).", total, len(jobs))
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("CSV ingestion failed")
        sys.exit(1)
