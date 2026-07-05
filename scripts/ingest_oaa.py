"""
ingest_oaa.py
-------------
Fetches team-level Outs Above Average (OAA) from the Baseball Savant
"Fielding Team" leaderboard and loads it to Snowflake.

Source change (2026-06-02): previously sourced from the FanGraphs fielding
leaderboard, but FanGraphs is now behind a Cloudflare managed JavaScript
challenge (`cf-mitigated: challenge`) that curl_cffi cannot solve. OAA is a
Statcast metric whose canonical home is Baseball Savant anyway, and Savant's
CSV leaderboard is not challenge-gated. See the FanGraphs-block diagnosis in
the conversation/runbook for the broader (still-open) FanGraphs client issue.

Target table: baseball_data.external.oaa_team_season_raw
  team_abbrev     VARCHAR  -- project team abbreviation (e.g. SF, CWS)
  game_year       INTEGER
  oaa             FLOAT    -- Outs Above Average (Statcast-era, 2016+)
  drs             FLOAT    -- NULL going forward: DRS is an SIS metric only
                           --   exposed by FanGraphs; not available from Savant.
                           --   Nothing downstream consumes it (mart passes it
                           --   through as team_drs_prior_season but no feature
                           --   reads it). Pre-2026 rows keep their FanGraphs DRS.
  n_opportunities INTEGER  -- NULL going forward: not in the Savant team CSV.
  defense         FLOAT    -- NULL going forward: FanGraphs composite only.

Only `oaa` flows into features (team_oaa_prior_season / team_oaa_blended via
mart_team_fielding_oaa), and only the PRIOR season's value is used (leakage
guard), so the daily current-season fetch is for monitoring freshness.

Load is append-only; mart_team_fielding_oaa dedupes per team×year by latest
loaded_at, so re-runs are safe.

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
import csv
import io
import logging
import os
import sys
import time
from datetime import date, datetime, timezone
from typing import Any

import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from curl_cffi import requests as cffi_requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

_KEY_PATH = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH") or os.path.expanduser(
    "~/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem"
)

TABLE_FQN = "baseball_data.external.oaa_team_season_raw"

# E11.1-W11 (FINISH wave): gated Snowflake→S3 flip. The typed records (no raw_json) are mirrored to
# lakehouse_raw/oaa_team_season_raw/ when LAKEHOUSE_RAW_WRITE_MODE is 'both'/'s3' (default
# 'snowflake' → unchanged). ⚠️ mart_team_fielding_oaa dedups by latest `loaded_at` (the SF DDL
# DEFAULT), which the record dict lacks — so the mirror STAMPS loaded_at, else the downstream dedup
# column would be absent. Bespoke per-record INSERT → leg-gated, not the dispatcher.
from utils.lakehouse_raw_writer import lakehouse_write_legs, w11_write_mode, write_raw_rows_s3  # noqa: E402

_LAKEHOUSE_SOURCE = "oaa_team_season_raw"

# Baseball Savant team OAA leaderboard (CSV). team_id is the MLB StatsAPI id.
SAVANT_URL = "https://baseballsavant.mlb.com/leaderboard/outs_above_average"
REQUEST_DELAY = 1.5  # seconds between season requests

# MLB StatsAPI team_id → project canonical team abbreviation (see ref_teams.csv).
# NOTE: ref_teams.csv's own team_id column is an internal scheme, NOT the MLB
# id, so it cannot be joined to Savant directly — hence this explicit map.
_MLB_ID_TO_ABBREV: dict[int, str] = {
    108: "LAA", 109: "AZ",  110: "BAL", 111: "BOS", 112: "CHC", 113: "CIN",
    114: "CLE", 115: "COL", 116: "DET", 117: "HOU", 118: "KC",  119: "LAD",
    120: "WSH", 121: "NYM", 133: "ATH", 134: "PIT", 135: "SD",  136: "SEA",
    137: "SF",  138: "STL", 139: "TB",  140: "TEX", 141: "TOR", 142: "MIN",
    143: "PHI", 144: "ATL", 145: "CWS", 146: "MIA", 147: "NYY", 158: "MIL",
}

_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 4, 8]
_session: cffi_requests.Session | None = None

_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_FQN} (
    team_abbrev     VARCHAR(10)  NOT NULL,
    game_year       INTEGER      NOT NULL,
    oaa             FLOAT,
    drs             FLOAT,
    n_opportunities INTEGER,
    defense         FLOAT,
    loaded_at       TIMESTAMP_NTZ
)
"""

_INSERT_SQL = f"""
INSERT INTO {TABLE_FQN}
    (team_abbrev, game_year, oaa, drs, n_opportunities, defense, loaded_at)
SELECT
    %(team_abbrev)s::VARCHAR,
    %(game_year)s::INTEGER,
    %(oaa)s::FLOAT,
    %(drs)s::FLOAT,
    %(n_opportunities)s::INTEGER,
    %(defense)s::FLOAT,
    CURRENT_TIMESTAMP
"""


def _connect() -> snowflake.connector.SnowflakeConnection:
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE — the ~/... default _KEY_PATH doesn't exist there.
    # Delegate to the shared PATH-if-exists→inline→password resolver. All SQL here is
    # fully-qualified, so the default schema is immaterial. See CLAUDE.md INC-22 landmine.
    import sys as _sys
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in _sys.path:
        _sys.path.insert(0, _root)
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection()


def _get_session() -> cffi_requests.Session:
    global _session
    if _session is None:
        # Savant is not behind the Cloudflare JS challenge, but we keep the
        # Chrome TLS fingerprint for parity with the rest of the project.
        _session = cffi_requests.Session(impersonate="chrome124")
    return _session


def _savant_get(url: str, params: dict) -> cffi_requests.Response:
    sess = _get_session()
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = sess.get(url, params=params, timeout=60)
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            log.warning("Attempt %d/%d failed for %s: %s", attempt, _MAX_RETRIES, url, exc)
            last_exc = exc
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAYS[attempt - 1])
    raise RuntimeError(f"All {_MAX_RETRIES} attempts failed for {url}") from last_exc


def _mlb_id_to_project(team_id: int, game_year: int) -> str | None:
    """Map MLB StatsAPI team_id to project abbreviation (year-aware for the A's)."""
    if team_id == 133:  # Athletics franchise: OAK through 2024, ATH from 2025
        return "ATH" if game_year >= 2025 else "OAK"
    return _MLB_ID_TO_ABBREV.get(team_id)


def fetch_season(season: int) -> list[dict[str, Any]]:
    """Fetch team-level OAA for a single season from Baseball Savant."""
    resp = _savant_get(
        SAVANT_URL,
        {
            "type": "Fielding_Team",
            "startYear": season,
            "endYear": season,
            "split": "no",
            "team": "",
            "range": "year",
            "min": "q",
            "pos": "",
            "roles": "",
            "viz": "show",
            "csv": "true",
        },
    )
    # utf-8-sig strips the BOM Savant prepends to the header row.
    rows = list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig"))))

    records = []
    for row in rows:
        raw_id = row.get("team_id")
        try:
            team_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        team_abbrev = _mlb_id_to_project(team_id, season)
        if not team_abbrev:
            log.warning("  Unmapped MLB team_id %s (%s) — skipping",
                        team_id, row.get("team_name"))
            continue
        oaa_val = row.get("outs_above_average")
        records.append({
            "team_abbrev": team_abbrev,
            "game_year": season,
            "oaa": float(oaa_val) if oaa_val not in (None, "") else None,
            # Not available from Savant — see module docstring. Unused downstream.
            "drs": None,
            "n_opportunities": None,
            "defense": None,
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
    for record in records:
        cur.execute(_INSERT_SQL, record)
    cur.close()
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Baseball Savant team OAA to Snowflake")
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

    log.info("Fetching team OAA for seasons: %s", seasons)

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

    # E11.1-W11: leg-gated dual-write (W11_RAW_WRITE_MODE). SF insert on 'snowflake'/'both'; S3 on 's3'/'both'.
    do_sf, do_s3 = lakehouse_write_legs(w11_write_mode())
    written = 0
    if do_sf:
        log.info("Connecting to Snowflake...")
        conn = _connect()
        try:
            written = write_to_snowflake(conn, all_records)
            log.info("Done. %d rows written to %s", written, TABLE_FQN)
        finally:
            conn.close()
    if do_s3:
        # Stamp loaded_at (the mart's dedup tiebreaker) — the record dict relies on the SF DDL
        # DEFAULT, so the S3 mirror must supply it explicitly or the downstream ORDER BY breaks.
        _now = datetime.now(timezone.utc).isoformat()
        mirror_rows = [{**r, "loaded_at": _now} for r in all_records]
        n_s3 = write_raw_rows_s3(_LAKEHOUSE_SOURCE, mirror_rows, mode="append")
        log.info("mirrored %d row(s) → S3 lakehouse_raw/%s/", n_s3, _LAKEHOUSE_SOURCE)
        written = written or len(all_records)


if __name__ == "__main__":
    main()
