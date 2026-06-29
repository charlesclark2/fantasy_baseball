#!/usr/bin/env python3
"""
export_odds_raw_to_s3.py   (E11.1-W3pre lakehouse decommission)
---------------------------------------------------------------
One-time historical + recurring-bridge export of the odds/staging RAW VARIANT tables
from Snowflake → S3 raw parquet, so the W3pre staging models' duckdb branch can flatten
them. Uses the shared keystone (scripts/utils/lakehouse_raw_writer.write_raw_rows_s3).

WHY THIS EXISTS alongside the migrated writers:
  • Historical backfill — the live writers only flip GOING FORWARD; everything already in
    Snowflake (102k odds rows, etc.) must be exported once so the flatten sees full history.
  • Recurring bridge — monthly_schedule's writer (ingest_statsapi.py) is NOT flipped this
    session, so this script re-exports it each lakehouse cycle until that writer flips.
  Output layout matches the keystone exactly (raw_json/json_field as JSON-string VARCHAR,
  timestamps as ISO VARCHAR, dt= partitions) so live-writer rows and exported rows are
  byte-compatible for the flatten.

IDEMPOTENT: writes mode='overwrite_partition' (deletes each dt= partition before writing)
so re-running a date range can't leave a stale double-counting part file (the W2 dupe class
the parity pre-flight guards against).

NOT covered here (W3-MAIN follow-up): oddsapi.odds_snapshots_historical — it is read
DIRECTLY by mart_closing_line_value / mart_odds_line_movement (not via a staging model),
so it belongs to the odds/CLV MART wave, not this staging precursor.

⚠️ >1 min on the full history → operator runs it. Reads Snowflake via the MCP-equivalent
connector (snowflake_loader). Writes S3 via the boto3 credential chain.

Usage:
  uv run python scripts/export_odds_raw_to_s3.py                       # all 4 sources, full history
  uv run python scripts/export_odds_raw_to_s3.py --source mlb_odds_raw # one source
  uv run python scripts/export_odds_raw_to_s3.py --since 2026-06-01    # only ingestion dates >= since
  uv run python scripts/export_odds_raw_to_s3.py --dry-run             # per-day row counts, no S3 write
"""

import argparse

# scripts/ is on sys.path under the runtime; import the shared utils as top-level packages.
from utils.lakehouse_raw_writer import prune_partitions, write_raw_rows_s3
from utils.snowflake_loader import get_snowflake_connection


def latest_dt_per_month(dates: list) -> list:
    """Reduce ingestion dates to the LATEST per calendar (year, month) — the monthly_schedule
    retention rule (E11.1-W6 / INC-20). The daily run re-fetches only the CURRENT month, so a
    month's games live in that month's ingestion partitions and the flatten keeps the latest
    ingestion per game_pk — so only the latest ingestion date per calendar month affects the
    output; the rest are redundant snapshots whose accumulation OOM'd the W6 flatten. Pure +
    unit-tested."""
    latest: dict = {}
    for d in dates:
        key = (d.year, d.month)
        if key not in latest or d > latest[key]:
            latest[key] = d
    return sorted(latest.values())

# source → (fully-qualified raw table, SELECT column SQL). VARIANT cols are TO_JSON'd to a
# string; timestamps cast ::varchar (ISO) so the raw parquet is uniform VARCHAR for the
# flatten's ::timestamp casts. The selected columns are exactly what the stg model reads.
SOURCES = {
    "mlb_events_raw": (
        "baseball_data.oddsapi.mlb_events_raw",
        "ingestion_ts::varchar as ingestion_ts, load_id, x_requests_used, "
        "x_requests_remaining, to_json(raw_json) as raw_json",
    ),
    "mlb_odds_raw": (
        "baseball_data.oddsapi.mlb_odds_raw",
        "ingestion_ts::varchar as ingestion_ts, load_id, to_json(request_params) as request_params, "
        "x_requests_used, x_requests_remaining, to_json(raw_json) as raw_json",
    ),
    "derivative_odds_raw": (
        "baseball_data.oddsapi.derivative_odds_raw",
        "ingestion_ts::varchar as ingestion_ts, load_id, event_id, "
        "requested_snapshot_ts::varchar as requested_snapshot_ts, "
        "actual_snapshot_ts::varchar as actual_snapshot_ts, "
        "previous_snapshot_ts::varchar as previous_snapshot_ts, "
        "next_snapshot_ts::varchar as next_snapshot_ts, "
        "markets_requested, regions_requested, x_requests_remaining, x_requests_last, "
        "to_json(raw_json) as raw_json",
    ),
    "monthly_schedule": (
        "baseball_data.statsapi.monthly_schedule",
        "ingestion_ts::varchar as ingestion_ts, to_json(json_field) as json_field",
    ),
}


def export_source(conn, source: str, since: str | None, dry_run: bool) -> int:
    fqn, cols = SOURCES[source]
    cur = conn.cursor()

    where = f"WHERE ingestion_ts::date >= '{since}'" if since else ""
    cur.execute(f"SELECT DISTINCT ingestion_ts::date AS dt FROM {fqn} {where} ORDER BY dt")
    raw_dates = [r[0] for r in cur.fetchall()]
    # Snowflake DISTINCT includes a NULL group (sorted last by ORDER BY) for rows whose
    # ingestion_ts is NULL — monthly_schedule's historical backfill carries ~134 such rows
    # (the bulk of the pre-2026 schedule: 25k+ game_pks found in NO dated row). They have no
    # date, so the per-date loop below would both fail (WHERE ... = 'None') and DROP them.
    has_null_ts = None in raw_dates
    dates = [d for d in raw_dates if d is not None]
    # E11.1-W6 / INC-20 — monthly_schedule retention: collapse the accumulating daily month
    # snapshots to the latest ingestion per calendar month (value-identical under the flatten's
    # latest-ingestion-per-game_pk dedup). Without this, ~50 redundant full-month snapshots
    # (~470 MiB) pile up and the W6 DuckDB flatten OOMs (SIGKILL) on the ~750k pre-dedup
    # fat-JSON game-rows. Stale same-month partitions are pruned from S3 after the write below.
    retained = len(dates)
    if source == "monthly_schedule":
        dates = latest_dt_per_month(dates)
        retained = len(dates)
    print(f"\n{source}: {retained} ingestion date(s) to export"
          + (" + NULL-ts partition" if has_null_ts else "")
          + (f" (since {since})" if since else "")
          + (" [latest-per-month retention]" if source == "monthly_schedule" else ""))

    total = 0
    for dt in dates:
        cur.execute(f"SELECT {cols} FROM {fqn} WHERE ingestion_ts::date = '{dt}'")
        names = [d[0].lower() for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]
        if dry_run:
            print(f"  {dt}: {len(rows):,} rows  (dry-run — no S3 write)")
        else:
            n = write_raw_rows_s3(source, rows, mode="overwrite_partition")
            print(f"  {dt}: {n:,} rows → lakehouse_raw/{source}/dt={dt}/")
        total += len(rows)

    # NULL-ts historical rows: export explicitly into the writer's '__nullts__' sentinel
    # partition with ingestion_ts PRESERVED as NULL (the SELECT returns it as None → the writer
    # keeps the explicit None rather than stamping now(), so the flatten's qualify dedup and the
    # parity check both see NULL, matching the live Snowflake staging). They have no date, so a
    # --since run can't (and shouldn't) target them — only a full backfill exports them, and
    # overwrite_partition keeps the sentinel partition idempotent across re-runs.
    if has_null_ts:
        cur.execute(f"SELECT {cols} FROM {fqn} WHERE ingestion_ts IS NULL")
        names = [d[0].lower() for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]
        if dry_run:
            print(f"  NULL-ts: {len(rows):,} rows  (dry-run — no S3 write)")
        else:
            n = write_raw_rows_s3(source, rows, mode="overwrite_partition")
            print(f"  NULL-ts: {n:,} rows → lakehouse_raw/{source}/dt=__nullts__/")
        total += len(rows)

    # E11.1-W6 / INC-20 — prune stale monthly_schedule partitions so the W6 flatten reads only the
    # latest-per-month snapshots (+ __nullts__). Only on a FULL export: a --since run sees only
    # recent dates, so pruning to that reduced keep-set would wrongly delete older months. The keep
    # set is the latest-per-month `dates` just written; prune_partitions always keeps __nullts__.
    if source == "monthly_schedule" and not dry_run and since is None:
        deleted = prune_partitions(source, [str(d) for d in dates])
        if deleted:
            print(f"  pruned {len(deleted)} stale monthly_schedule partition(s) "
                  f"(latest-per-month retention): {deleted}")

    cur.close()
    return total


def main():
    ap = argparse.ArgumentParser(description="E11.1-W3pre: export odds/staging raw VARIANT → S3")
    ap.add_argument("--source", choices=sorted(SOURCES), help="One source (default: all 4)")
    ap.add_argument("--since", help="Only ingestion dates >= this (YYYY-MM-DD)")
    ap.add_argument("--dry-run", action="store_true", help="Per-day row counts, no S3 write")
    args = ap.parse_args()

    sources = [args.source] if args.source else list(SOURCES)
    print(f"E11.1-W3pre raw export → S3  | sources: {sources}"
          + ("  | DRY-RUN" if args.dry_run else ""))

    conn = get_snowflake_connection(database="baseball_data", schema="oddsapi")
    try:
        grand = {s: export_source(conn, s, args.since, args.dry_run) for s in sources}
    finally:
        conn.close()

    print("\n── Export summary ──")
    for s, n in grand.items():
        print(f"  {s}: {n:,} rows")
    if not args.dry_run:
        print("\nNext: uv run python scripts/run_w1_lakehouse.py --w3pre-only   "
              "# flatten → lakehouse/stg_*/data.parquet")
        print("Then: uv run python scripts/parity_check_w3pre.py")


if __name__ == "__main__":
    main()
