"""
scripts/backfill_weather_s3_gap.py
E11.22 — reconcile the small SF-only weather_raw gap into the S3 lakehouse mirror (path A).

WHY THIS EXISTS
  After the both→s3 cutover the weather_raw SF raw is FROZEN, and a parity no-loss check
  (parity_check_w11.py --source weather_raw) found ~23 keys present in Snowflake but MISSING
  from the S3 mirror (all `forecast_intraday` / `forecast_pregame`). These are historical
  orphans: `ingest_weather.py` inserts to SF per-row inside the loop but flushes S3 ONCE at the
  end gated on `do_s3`, so any run that fired while W11_RAW_WRITE_MODE was unset/'snowflake'
  (before the weather_capture image got the S3 env) wrote those rows SF-only, and the one-time
  overwrite_partition backfill export never picked up the stragglers. It is a STATIC gap (SF is
  frozen; the active intraday path now writes S3), not a live writer bug.

WHAT IT DOES (idempotent, no clobber)
  1. Read every weather_raw row from Snowflake (the frozen source of truth).
  2. Read the DISTINCT retention keys already in the S3 mirror via DuckDB.
  3. Anti-join on WEATHER_RAW_RETENTION_KEY (game_pk, venue_id, obs_type, hours_to_first_pitch)
     → the SF rows whose key is NOT yet in S3.
  4. APPEND only those rows to lakehouse_raw/weather_raw/ (mode='append' → a new part file; it
     does NOT overwrite/prune, so the ~100 live S3-only rows are untouched). The stg dedup +
     INC-20 retention key are identical to this key, so a re-run appends nothing.

After a successful --apply run, re-check parity (expect no-loss missing-from-parquet=0), then
weather_raw is safe to DROP like the rest of the A/B/C/D batch.

RUN ON THE BOX (needs Snowflake inline-key auth + S3 instance-role + DuckDB region):
  docker compose -f services/dagster/aws/docker-compose.yml exec -T -e AWS_DEFAULT_REGION=us-east-2 \
    dagster-codeloc python scripts/backfill_weather_s3_gap.py            # dry-run (default)
  docker compose -f services/dagster/aws/docker-compose.yml exec -T -e AWS_DEFAULT_REGION=us-east-2 \
    dagster-codeloc python scripts/backfill_weather_s3_gap.py --apply    # append the missing rows
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

import duckdb  # noqa: E402

from betting_ml.utils.data_loader import get_snowflake_connection  # noqa: E402
from utils.lakehouse_raw_writer import (  # noqa: E402
    WEATHER_RAW_COLS,
    WEATHER_RAW_RETENTION_KEY,
    raw_lakehouse_loc,
    weather_mirror_rows,
    write_raw_rows_s3,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_SOURCE = "weather_raw"
_SF_TABLE = "baseball_data.statsapi.weather_raw"


def _key(row: dict) -> tuple:
    """Normalize a row to its WEATHER_RAW_RETENTION_KEY tuple (NULL-safe, type-stable), so a SF row
    and an S3 row for the same checkpoint compare EQUAL regardless of int/Decimal/None representation."""
    out = []
    for c in WEATHER_RAW_RETENTION_KEY:
        v = row.get(c)
        if v is None:
            out.append(None)
        elif c == "weather_observation_type":
            out.append(str(v).lower())
        else:
            out.append(int(v))  # game_pk / venue_id / hours_to_first_pitch
    return tuple(out)


def _read_sf_rows() -> list[dict]:
    conn = get_snowflake_connection(schema="statsapi")
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT {', '.join(WEATHER_RAW_COLS)} FROM {_SF_TABLE}")
        names = [d[0].lower() for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]
        cur.close()
    finally:
        conn.close()
    log.info("Snowflake %s: %d row(s)", _SF_TABLE, len(rows))
    return rows


def _read_s3_keys() -> set[tuple]:
    glob = raw_lakehouse_loc(_SOURCE) + "**/*.parquet"
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("CREATE OR REPLACE SECRET s3sec (TYPE s3, PROVIDER credential_chain, REGION 'us-east-2');")
    key_cols = ", ".join(WEATHER_RAW_RETENTION_KEY)
    rows = con.execute(
        f"SELECT DISTINCT {key_cols} FROM read_parquet('{glob}', union_by_name=true)"
    ).fetchall()
    con.close()
    keys = {_key(dict(zip(WEATHER_RAW_RETENTION_KEY, r))) for r in rows}
    log.info("S3 mirror lakehouse_raw/%s/: %d distinct retention key(s)", _SOURCE, len(keys))
    return keys


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill SF-only weather_raw rows into the S3 mirror.")
    ap.add_argument("--apply", action="store_true", help="Append the missing rows (default: dry-run).")
    ap.add_argument("--limit-preview", type=int, default=10, help="How many missing keys to print.")
    args = ap.parse_args()

    sf_rows = _read_sf_rows()
    s3_keys = _read_s3_keys()

    missing = [r for r in sf_rows if _key(r) not in s3_keys]
    log.info("SF rows missing from the S3 mirror: %d", len(missing))
    for r in missing[: args.limit_preview]:
        log.info("    %s", "|".join("NA" if v is None else str(v) for v in _key(r)))

    if not missing:
        log.info("Nothing to backfill — the S3 mirror already contains every SF key. "
                 "weather_raw is safe to drop (re-confirm with parity_check_w11.py --source weather_raw).")
        return 0

    if not args.apply:
        log.info("─" * 70)
        log.info("DRY-RUN. Re-run with --apply to APPEND these %d row(s) to lakehouse_raw/%s/.", len(missing), _SOURCE)
        return 0

    mirror = weather_mirror_rows(missing)
    n = write_raw_rows_s3(_SOURCE, mirror, mode="append")
    log.info("Appended %d row(s) → lakehouse_raw/%s/ (mode=append; no partition overwrite).", n, _SOURCE)
    log.info("Re-run parity_check_w11.py --source weather_raw — expect no-loss missing-from-parquet=0, "
             "then weather_raw is safe to DROP.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
