#!/usr/bin/env python3
"""
export_w11_raw_to_s3.py   (E11.1-W11 — the ingestion-decommission FINISH wave)
------------------------------------------------------------------------------
One-time historical + recurring-bridge export of the W11 Tier-A raw feeds from
Snowflake → S3 raw parquet (lakehouse_raw/<source>/), so each source's stg/mart duckdb
branch can read it AFTER the read-side cutover (the repoint from lakehouse_loc → lakehouse_raw_loc).

WHY THIS EXISTS alongside the migrated writers (the W7b mirror→validate→cutover discipline):
  • Historical backfill — the live writers only flip GOING FORWARD (gated by
    LAKEHOUSE_RAW_WRITE_MODE, default 'snowflake'). Everything already in Snowflake must be
    exported once so the flatten/stg sees full history.
  • Parity bridge — runs BEFORE the read-side cutover so scripts/parity_check_w11.py can compare
    the S3 mirror against the live Snowflake raw, proving they match before any reader repoints.
  • Recurring bridge — re-exports each lakehouse cycle until the source's live writer is flipped
    to mode 's3' (Snowflake leg retired).

Layout: routes through the shared keystone (scripts/utils/lakehouse_raw_writer.write_raw_rows_s3),
identical to export_odds_raw_to_s3.py — VARIANT cols (raw_json / request_params) land as JSON-string
VARCHAR (matching TO_JSON), timestamps as ISO VARCHAR, dt= partitions — so live-writer rows and
exported rows are byte-compatible for the duckdb branch (no union_by_name schema drift).

IDEMPOTENT: mode='overwrite_partition' (deletes each dt= partition before writing) so re-running a
date range can't leave a stale double-counting part file (the W2 dupe class).

⚠️ >1 min on full history → operator runs it. Reads Snowflake via the connector (snowflake_loader);
writes S3 via the boto3 credential chain (instance-role-safe on the box).

Usage:
  uv run python scripts/export_w11_raw_to_s3.py                          # all W11 sources, full history
  uv run python scripts/export_w11_raw_to_s3.py --source fg_stuff_plus_raw
  uv run python scripts/export_w11_raw_to_s3.py --since 2026-06-01       # only ingestion dates >= since
  uv run python scripts/export_w11_raw_to_s3.py --dry-run               # per-source row counts, no S3 write
"""

import argparse

# scripts/ is on sys.path under the runtime; import the shared utils as top-level packages.
from utils.lakehouse_raw_writer import write_raw_rows_s3
from utils.snowflake_loader import get_snowflake_connection

# W11 Tier-A source → (fully-qualified Snowflake raw table, timestamp column to alias to
# `ingestion_ts` for the dt= partition + the staging qualify dedup). The timestamp column varies
# by table (the FanGraphs/JSON feeds use `ingestion_ts`; the typed savant feeds use their own
# stamp); aliasing it to `ingestion_ts` keeps every source's parquet layout uniform so
# write_raw_rows_s3 partitions correctly and the duckdb branch's `order by ingestion_ts` dedup
# matches Snowflake. `None` ts_col → the writer stamps the export run-time (today's partition),
# which is harmless: every W11 stg/mart dedups by a NATURAL key (player×season, game_pk, …), so
# the dt= partition is a physical layout detail, never a semantic one.
SOURCES = {
    # JSON-VARIANT (raw_json blob) feeds — flattened by the stg duckdb branch
    "fg_stuff_plus_raw":          ("baseball_data.fangraphs.fg_stuff_plus_raw",          "ingestion_ts"),
    "fg_hitting_leaderboard_raw": ("baseball_data.fangraphs.fg_hitting_leaderboard_raw", "ingestion_ts"),
    "catcher_framing_raw":        ("baseball_data.savant.catcher_framing_raw",           None),
    "player_transactions":        ("baseball_data.statsapi.player_transactions",         None),
    # Typed (columnar) feeds — read column-wise by the stg/mart duckdb branch (no raw_json)
    "sprint_speed_raw":           ("baseball_data.savant.sprint_speed_raw",              "ingestion_timestamp"),
    "oaa_team_season_raw":        ("baseball_data.external.oaa_team_season_raw",         "loaded_at"),
    "savant_park_factors_raw":    ("baseball_data.fangraphs.savant_park_factors_raw",    None),
    # E11.1-W11 Tier-B — the shared umpire feed (4 writers → one table). loaded_at is the stg
    # dedup tiebreaker (order by loaded_at desc); alias it to ingestion_ts for the dt= partition.
    "umpire_game_log":            ("baseball_data.statsapi.umpire_game_log",             "loaded_at"),
    # E11.1-W11 Tier-C — the shared weather feed (ingest_weather + backfill_observed_weather → one
    # table). loaded_at is the stg dedup tiebreaker (order by loaded_at desc); alias it to ingestion_ts
    # for the dt= partition. (The hourly weather_intraday_series is S3-ONLY new data — no SF to export.)
    "weather_raw":                ("baseball_data.statsapi.weather_raw",                 "loaded_at"),
    # E11.1-W11 Tier-D — the ActionNetwork public-betting feed. ingestion_timestamp is the stg dedup
    # key (order by ingestion_timestamp desc) + the SCD-2 loaded_at; alias it to ingestion_ts for the
    # dt= partition. public_betting_raw is append-only (no INC-20 retention) — a full re-export is
    # idempotent per dt= via overwrite_partition. (The hourly public_betting_intraday_series is S3-ONLY
    # new data — no SF to export.)
    "public_betting_raw":         ("baseball_data.actionnetwork.public_betting_raw",     "ingestion_timestamp"),
}


def export_source(conn, source: str, since: str | None, dry_run: bool) -> int:
    fqn, ts_col = SOURCES[source]
    cur = conn.cursor()

    # SELECT * (PRESERVE every column name — the downstream duckdb branch reads the source's own
    # columns, incl. its dedup timestamp e.g. snapshot_date / loaded_at — renaming would break it).
    # VARIANT cols (raw_json) come back as JSON text (str) from the connector; the keystone passes
    # a str through unchanged (matching TO_JSON). --since filters on the source's own timestamp col.
    where = f"WHERE {ts_col}::date >= '{since}'" if (since and ts_col) else ""
    if since and not ts_col:
        print(f"  ⚠️  {source}: --since ignored (no known timestamp column to filter on)")
    cur.execute(f"SELECT * FROM {fqn} {where}")
    names = [d[0].lower() for d in cur.description]
    rows = [dict(zip(names, r)) for r in cur.fetchall()]
    cur.close()

    # Provide an `ingestion_ts` for the dt= partition WITHOUT removing the source's own stamp.
    # rows_to_arrow_table also adds ingestion_ts to the LIVE writer's output (stamps now() when
    # absent), so both legs carry the column — the stg/mart dedup keys on the source's own column,
    # never on ingestion_ts, so this is partition-layout only (parity is on the data columns).
    if ts_col and ts_col != "ingestion_ts":
        for r in rows:
            if r.get("ingestion_ts") is None and r.get(ts_col) is not None:
                r["ingestion_ts"] = str(r[ts_col])

    if dry_run:
        print(f"  {source}: {len(rows):,} rows  (dry-run — no S3 write)"
              + (f"  [since {since}]" if since else ""))
        return len(rows)

    n = write_raw_rows_s3(source, rows, mode="overwrite_partition")
    print(f"  {source}: {n:,} rows → lakehouse_raw/{source}/")
    return n


def main():
    ap = argparse.ArgumentParser(description="E11.1-W11: export Tier-A raw feeds Snowflake → S3 lakehouse_raw/")
    ap.add_argument("--source", choices=sorted(SOURCES), help="One source (default: all)")
    ap.add_argument("--since", help="Only ingestion dates >= this (YYYY-MM-DD)")
    ap.add_argument("--dry-run", action="store_true", help="Per-source row counts, no S3 write")
    args = ap.parse_args()

    sources = [args.source] if args.source else list(SOURCES)
    print(f"E11.1-W11 raw export → S3  | sources: {sources}"
          + ("  | DRY-RUN" if args.dry_run else ""))

    # FQNs in every SELECT span fangraphs/savant/statsapi/external — the default schema is irrelevant.
    conn = get_snowflake_connection()
    try:
        grand = {s: export_source(conn, s, args.since, args.dry_run) for s in sources}
    finally:
        conn.close()

    print("\n── Export summary ──")
    for s, n in grand.items():
        print(f"  {s}: {n:,} rows")
    if not args.dry_run:
        print("\nNext: uv run python scripts/parity_check_w11.py   # S3 mirror vs Snowflake raw")
        print("Then (per source, after parity GREEN): repoint the stg/mart duckdb branch "
              "lakehouse_loc → lakehouse_raw_loc, rebuild --w4/--w5, validate, flip writer to s3.")


if __name__ == "__main__":
    main()
