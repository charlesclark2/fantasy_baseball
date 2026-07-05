"""
ingest_transactions.py
----------------------
Fetches MLB player roster transaction events from the Stats API and upserts
them into baseball_data.statsapi.player_transactions.

The transactions endpoint captures IL placements (10-Day IL, 60-Day IL, 7-Day IL),
activations, reinstatements, and other roster moves. This data feeds
stg_statsapi_player_injury_status, which powers injury-adjusted lineup features.

A 7-day lookback window is used in the daily Snowflake task DAG so that
retroactive IL placements (transactions that post-date game day) are captured.

Usage:
    # Dry-run — print fetched records, skip all writes
    uv run python scripts/ingest_transactions.py --start-date 2026-04-01 --end-date 2026-04-07 --dry-run

    # Production ingest for a date range
    uv run python scripts/ingest_transactions.py --start-date 2026-04-01 --end-date 2026-04-07

    # Daily 7-day lookback (used by GitHub Actions daily_ingestion workflow)
    uv run python scripts/ingest_transactions.py \\
        --start-date $(date -v-7d +%Y-%m-%d) \\
        --end-date $(date +%Y-%m-%d)

Authentication — private key (preferred) or password fallback:
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH  (optional passphrase: SNOWFLAKE_PRIVATE_KEY_PASSPHRASE)
    -- or --
    SNOWFLAKE_PASSWORD
    SNOWFLAKE_ROLE  (optional)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

TABLE_FQN = "baseball_data.statsapi.player_transactions"
TRANSACTIONS_URL = "https://statsapi.mlb.com/api/v1/transactions"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 1

# E11.1-W11 (FINISH wave): gated Snowflake→S3 flip. The `records` list[dict] (incl. raw_json as a
# JSON string) is mirrored to lakehouse_raw/player_transactions/ when LAKEHOUSE_RAW_WRITE_MODE is
# 'both'/'s3' (default 'snowflake' → unchanged). Bespoke temp-table upsert below → leg-gated, not
# the append_raw_rows_lakehouse dispatcher. scripts/ on sys.path under both runtime + pytest.
from utils.lakehouse_raw_writer import lakehouse_write_legs, w11_write_mode, write_raw_rows_s3  # noqa: E402

_LAKEHOUSE_SOURCE = "player_transactions"


# ---------------------------------------------------------------------------
# Snowflake connection (mirrors pattern from other ingest scripts)
# ---------------------------------------------------------------------------

def _get_snowflake_connection():
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — the old
    # file-path→password resolver KeyError'd on the box. Delegate to the shared
    # PATH-if-exists→inline→password resolver. Queries are fully-qualified, so the default
    # schema is immaterial. See CLAUDE.md INC-22 landmine.
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="statsapi")


# ---------------------------------------------------------------------------
# Stats API fetch
# ---------------------------------------------------------------------------

def _fetch_transactions(start_date: str, end_date: str) -> list[dict]:
    session = requests.Session()
    session.headers["User-Agent"] = "baseball-ingest/1.0"

    params = {"sportId": 1, "startDate": start_date, "endDate": end_date}

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(TRANSACTIONS_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json().get("transactions", [])
        except requests.HTTPError as exc:
            if attempt < MAX_RETRIES and 500 <= exc.response.status_code < 600:
                log.warning("HTTP %s — retrying in 5 s", exc.response.status_code)
                time.sleep(5)
                continue
            raise

    return []


def _parse_record(t: dict) -> dict:
    return {
        "transaction_id":   str(t.get("id", "")),
        "player_id":        int((t.get("person") or {}).get("id") or 0),
        "player_name":      (t.get("person") or {}).get("fullName"),
        "team_id":          int((t.get("toTeam") or {}).get("id") or 0) or None,
        "team_name":        (t.get("toTeam") or {}).get("name"),
        "transaction_date": t.get("date"),
        "effective_date":   t.get("effectiveDate"),
        "resolution_date":  t.get("resolutionDate"),
        "type_code":        t.get("typeCode") or "",
        "type_description": t.get("typeDesc"),
        "description":      t.get("description"),
        "raw_json":         json.dumps(t),
    }


# ---------------------------------------------------------------------------
# Snowflake upsert — bulk temp table + single INSERT ... SELECT
# ---------------------------------------------------------------------------
# Pattern:
#   1. executemany plain strings into a VARCHAR temp table (fast, no PARSE_JSON)
#   2. DELETE existing rows from target by matching on temp table (handles re-runs)
#   3. Single INSERT INTO target SELECT ..., PARSE_JSON(raw_json_str) FROM tmp
#      (PARSE_JSON valid in SELECT, not in VALUES)

BATCH_SIZE = 500

_INSERT_TEMP_SQL = """
INSERT INTO tmp_player_transactions (
    transaction_id, player_id, player_name, team_id, team_name,
    transaction_date, effective_date, resolution_date,
    type_code, type_description, description, raw_json_str
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_INSERT_FROM_TEMP_SQL = f"""
INSERT INTO {TABLE_FQN} (
    transaction_id, player_id, player_name, team_id, team_name,
    transaction_date, effective_date, resolution_date,
    type_code, type_description, description, raw_json
)
SELECT
    transaction_id, player_id, player_name, team_id, team_name,
    transaction_date, effective_date, resolution_date,
    type_code, type_description, description,
    PARSE_JSON(raw_json_str)
FROM tmp_player_transactions
"""


def _upsert_records(conn, records: list[dict]) -> int:
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TEMPORARY TABLE tmp_player_transactions (
            transaction_id   VARCHAR(30),
            player_id        INTEGER,
            player_name      VARCHAR(120),
            team_id          INTEGER,
            team_name        VARCHAR(100),
            transaction_date DATE,
            effective_date   DATE,
            resolution_date  DATE,
            type_code        VARCHAR(60),
            type_description VARCHAR(255),
            description      VARCHAR(2000),
            raw_json_str     VARCHAR(16777216)
        )
    """)

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        cursor.executemany(
            _INSERT_TEMP_SQL,
            [
                (
                    r["transaction_id"], r["player_id"], r["player_name"],
                    r["team_id"], r["team_name"], r["transaction_date"],
                    r["effective_date"], r["resolution_date"],
                    r["type_code"], r["type_description"], r["description"],
                    r["raw_json"],
                )
                for r in batch
            ],
        )

    # Remove any existing rows for this batch so re-runs are idempotent
    cursor.execute(
        f"DELETE FROM {TABLE_FQN} WHERE transaction_id IN "
        f"(SELECT transaction_id FROM tmp_player_transactions)"
    )

    cursor.execute(_INSERT_FROM_TEMP_SQL)

    cursor.close()
    return len(records)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest MLB player transactions into Snowflake.")
    parser.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD (inclusive)")
    parser.add_argument("--end-date",   required=True, help="End date YYYY-MM-DD (inclusive)")
    parser.add_argument("--dry-run", action="store_true", help="Print fetched records without writing")
    args = parser.parse_args()

    log.info("Fetching transactions %s → %s", args.start_date, args.end_date)
    raw = _fetch_transactions(args.start_date, args.end_date)
    log.info("Fetched %d raw transaction records", len(raw))

    # Print unique type_code / type_description values so operators can confirm IL-specific codes.
    type_summary: dict[str, set[str]] = {}
    for t in raw:
        code = t.get("typeCode") or ""
        desc = t.get("typeDesc") or ""
        type_summary.setdefault(code, set()).add(desc)
    for code in sorted(type_summary):
        descs = sorted(type_summary[code])
        log.info("  type_code=%r  descriptions=%s", code, descs[:5])

    records = []
    skipped = 0
    for t in raw:
        rec = _parse_record(t)
        if not rec["transaction_id"] or not rec["player_id"]:
            skipped += 1
            continue
        records.append(rec)

    log.info("Parsed %d valid records (%d skipped — missing id or player_id)", len(records), skipped)

    if args.dry_run:
        # Show only records that have a non-empty type_code (IL placements, activations, etc.)
        typed = [r for r in records if r.get("type_code")]
        log.info("Records with non-empty type_code: %d / %d total", len(typed), len(records))
        for rec in typed[:10]:
            print(json.dumps({k: v for k, v in rec.items() if k != "raw_json"}, indent=2))
        if len(typed) > 10:
            log.info("  ... and %d more typed records", len(typed) - 10)
        log.info("dry-run: skipped all writes")
        return

    if not records:
        log.info("No records to upsert — done")
        return

    # E11.1-W11: leg-gated dual-write (W11_RAW_WRITE_MODE). SF upsert on 'snowflake'/'both'; S3 on 's3'/'both'.
    do_sf, do_s3 = lakehouse_write_legs(w11_write_mode())
    written = 0
    if do_sf:
        conn = _get_snowflake_connection()
        try:
            written = _upsert_records(conn, records)
            conn.commit()
        finally:
            conn.close()
    if do_s3:
        n_s3 = write_raw_rows_s3(_LAKEHOUSE_SOURCE, records, mode="append")
        log.info("mirrored %d transaction row(s) → S3 lakehouse_raw/%s/", n_s3, _LAKEHOUSE_SOURCE)
        written = written or len(records)

    log.info(
        "Done. fetched=%d  written=%d  skipped=%d",
        len(raw), written, skipped,
    )


if __name__ == "__main__":
    main()
