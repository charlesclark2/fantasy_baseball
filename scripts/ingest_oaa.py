"""
ingest_oaa.py
-------------
Fetches team-level Outs Above Average (OAA) and Defensive Runs Saved (DRS)
from the FanGraphs major-league fielding leaderboard (team aggregate view)
and loads them to Snowflake.

Target table: baseball_data.external.oaa_team_season_raw
  team_abbrev     VARCHAR  -- project team abbreviation (e.g. SF, CWS)
  game_year       INTEGER
  oaa             FLOAT    -- Outs Above Average (Statcast-era, NULL before ~2016)
  drs             FLOAT    -- Defensive Runs Saved (broader era coverage)
  n_opportunities INTEGER  -- total defensive plays (FanGraphs 'Plays' column)
  defense         FLOAT    -- FanGraphs composite Defense metric

Load is idempotent: existing rows for the same team × year are updated via MERGE.

Usage:
    # Backfill 2016–2025
    uv run python scripts/ingest_oaa.py --start-season 2016 --end-season 2025

    # Update current season
    uv run python scripts/ingest_oaa.py --season 2026

    # Dry-run (print without writing)
    uv run python scripts/ingest_oaa.py --season 2024 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date
from typing import Any

import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils"))
from fangraphs_client import _get_with_retry  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

_KEY_PATH = os.path.expanduser(
    "~/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem"
)

TABLE_FQN = "baseball_data.external.oaa_team_season_raw"

# FanGraphs team abbreviation → project team abbreviation
_FG_TO_PROJECT: dict[str, str] = {
    "ARI": "AZ",
    "CHW": "CWS",
    "KCR": "KC",
    "SDP": "SD",
    "SFG": "SF",
    "TBR": "TB",
    "WSN": "WSH",
    # The A's became ATH in 2025 in our data; FanGraphs may still say OAK
    # Keep OAK→OAK for 2024 and earlier (handled by year-aware mapping below)
}

FANGRAPHS_URL = "https://www.fangraphs.com/api/leaders/major-league/data"
REQUEST_DELAY = 1.5  # seconds between season requests

_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_FQN} (
    team_abbrev     VARCHAR(10)  NOT NULL,
    game_year       INTEGER      NOT NULL,
    oaa             FLOAT,
    drs             FLOAT,
    n_opportunities INTEGER,
    defense         FLOAT,
    PRIMARY KEY (team_abbrev, game_year)
)
"""

_MERGE_SQL = f"""
MERGE INTO {TABLE_FQN} AS tgt
USING (
    SELECT
        v.team_abbrev   AS team_abbrev,
        v.game_year     AS game_year,
        v.oaa           AS oaa,
        v.drs           AS drs,
        v.n_opps        AS n_opportunities,
        v.defense       AS defense
    FROM (VALUES {{placeholders}}) AS v(team_abbrev, game_year, oaa, drs, n_opps, defense)
) AS src
ON tgt.team_abbrev = src.team_abbrev AND tgt.game_year = src.game_year
WHEN MATCHED THEN UPDATE SET
    oaa             = src.oaa,
    drs             = src.drs,
    n_opportunities = src.n_opportunities,
    defense         = src.defense
WHEN NOT MATCHED THEN INSERT (team_abbrev, game_year, oaa, drs, n_opportunities, defense)
VALUES (src.team_abbrev, src.game_year, src.oaa, src.drs, src.n_opportunities, src.defense)
"""


def _connect() -> snowflake.connector.SnowflakeConnection:
    with open(_KEY_PATH, "rb") as f:
        p_key = serialization.load_pem_private_key(
            f.read(), password=None, backend=default_backend()
        )
    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return snowflake.connector.connect(
        account="IHUPICS-DP59975",
        user="dbt_rw",
        private_key=pkb,
        warehouse="COMPUTE_WH",
        database="baseball_data",
    )


def _fg_abbrev_to_project(fg_abbrev: str, game_year: int) -> str:
    """Map FanGraphs team abbreviation to project abbreviation."""
    if fg_abbrev == "OAK" and game_year >= 2025:
        return "ATH"
    return _FG_TO_PROJECT.get(fg_abbrev, fg_abbrev)


def _nullable(val: Any) -> str:
    if val is None:
        return "NULL"
    return str(val)


def fetch_season(season: int) -> list[dict[str, Any]]:
    """Fetch team-level OAA/DRS for a single season from FanGraphs."""
    resp = _get_with_retry(
        FANGRAPHS_URL,
        {
            "age": "", "pos": "all", "stats": "fld", "lg": "all", "qual": "y",
            "season": season, "season1": season,
            "startdate": "", "enddate": "",
            "month": 0, "hand": "", "team": "0,ts",
            "pageitems": 100, "pagenum": 1,
            "ind": 0, "rost": 0, "players": "", "type": 1, "postseason": "",
            "sortdir": "default", "sortstat": "Defense",
        },
        extra_headers={
            "Accept": "application/json",
            "Referer": "https://www.fangraphs.com/leaders/major-league",
        },
    )
    payload = resp.json()
    rows = payload.get("data", []) if isinstance(payload, dict) else payload

    records = []
    for row in rows:
        fg_abbrev = row.get("TeamNameAbb", "")
        if not fg_abbrev or fg_abbrev in ("2 Tms", "3 Tms", "4 Tms", "5 Tms"):
            continue
        team_abbrev = _fg_abbrev_to_project(fg_abbrev, season)
        records.append({
            "team_abbrev": team_abbrev,
            "game_year": season,
            "oaa": row.get("OAA"),
            "drs": row.get("DRS"),
            "n_opportunities": int(row["Plays"]) if row.get("Plays") is not None else None,
            "defense": row.get("Defense"),
        })

    log.info("  Season %d: %d team rows fetched", season, len(records))
    return records


def write_to_snowflake(
    conn: snowflake.connector.SnowflakeConnection,
    records: list[dict[str, Any]],
) -> int:
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS baseball_data.external")
    cur.execute(_DDL)

    def _fmt(r: dict) -> str:
        oaa = _nullable(r["oaa"])
        drs = _nullable(r["drs"])
        n   = _nullable(r["n_opportunities"])
        def_ = _nullable(r["defense"])
        return f"('{r['team_abbrev']}', {r['game_year']}, {oaa}, {drs}, {n}, {def_})"

    placeholders = ", ".join(_fmt(r) for r in records)
    cur.execute(_MERGE_SQL.format(placeholders=placeholders))
    cur.close()
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest FanGraphs team OAA/DRS to Snowflake")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--season", type=int, help="Single season to ingest")
    group.add_argument("--start-season", type=int, default=2016,
                       help="Start of range (default 2016, first OAA-available season)")
    parser.add_argument("--end-season", type=int, default=date.today().year,
                        help="End of range (default current year)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print rows without writing to Snowflake")
    args = parser.parse_args()

    if args.season:
        seasons = [args.season]
    else:
        seasons = list(range(args.start_season, args.end_season + 1))

    log.info("Fetching team OAA/DRS for seasons: %s", seasons)

    all_records: list[dict] = []
    for i, season in enumerate(seasons):
        records = fetch_season(season)
        all_records.extend(records)
        if i < len(seasons) - 1:
            time.sleep(REQUEST_DELAY)

    log.info("Total: %d team-season rows fetched", len(all_records))

    if args.dry_run:
        for r in all_records:
            print(f"  {r['game_year']}  {r['team_abbrev']:<4}  "
                  f"OAA={r['oaa']}  DRS={r['drs']}  Plays={r['n_opportunities']}")
        return

    log.info("Connecting to Snowflake...")
    conn = _connect()
    try:
        written = write_to_snowflake(conn, all_records)
        log.info("Done. %d rows written to %s", written, TABLE_FQN)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
