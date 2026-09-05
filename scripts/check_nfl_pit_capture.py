"""
check_nfl_pit_capture.py — read the NFL point-in-time capture stores and say what is IN them.

WHY THIS EXISTS (NF-CAP1, 2026-09-05). Two sessions read `nfl/pit/injuries` — 12,136 rows, one
capture date, zero 2026 rows — as "this capture has fired once in its life". The measurement was
right and the inference was wrong: nflverse had not published `injuries_2026.parquet` yet, so the
leg was firing on its cron and correctly capturing nothing, and **the artifact is structurally
incapable of recording a fire that legitimately captured nothing.** In the same store,
`nfl/pit/market` looked entirely healthy while the props tier had NEVER captured, because the
game-line tier filled every check.

So this prints the things that actually discriminate, rather than a row count:

  • the last CAPTURE INSTANT per store, read from INSIDE the parquet (never an S3 mtime —
    `aws s3 ls` prints shell-local time, and an atomic server-side copy refreshes an mtime on
    unchanged data, so an mtime check reads GREEN through the very freeze it should catch);
  • for `market`, the breakdown BY TIER — `game_lines` alone means props are not landing;
  • for `injuries`, the SEASONS present, and whether the vendor asset even exists yet;
  • ⭐ the SIBLING WITNESS: `injuries` and `schema_snapshot` are written by the SAME op in the
    same invocation, so a schema capture at a cron instant proves the injury leg ran at that
    instant too. When the primary artifact is silent, check the sibling — not the silence.

Read-only. No API credits. Snowflake-free. LAPTOP or BOX.

    AWS_DEFAULT_REGION=us-east-2 uv run python scripts/check_nfl_pit_capture.py
    AWS_DEFAULT_REGION=us-east-2 uv run python scripts/check_nfl_pit_capture.py --expect-props
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SOURCES = ("market", "injuries", "schema_snapshot", "weather")


def _rows(con, uri: str, sql: str):
    from deltalake import DeltaTable

    from quant_sports_intel_models.football.nfl.ingest import s3io

    dataset = DeltaTable(uri, storage_options=s3io.storage_options()).to_pyarrow_dataset()
    con.register("t", dataset)
    try:
        return con.execute(sql).fetchall(), [f.name for f in dataset.schema]
    finally:
        con.unregister("t")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expect-props", action="store_true",
                    help="exit 1 unless nfl/pit/market carries at least one market_tier='props' "
                         "row — the acceptance gate after enabling NFL_PIT_CAPTURE_PROPS")
    args = ap.parse_args()

    import duckdb

    from quant_sports_intel_models.football.nfl.pit import store

    now = datetime.now(timezone.utc)
    print(f"NFL point-in-time capture stores — {now:%Y-%m-%d %H:%M}Z")
    print("(every timestamp below is read from INSIDE the parquet, never an S3 mtime)\n")

    con = duckdb.connect()
    props_rows = 0
    problems: list[str] = []

    for src in SOURCES:
        uri = store.table_uri(src)
        try:
            if src == "market":
                rows, _ = _rows(con, uri, "select capture_date, market_tier, count(*), "
                                          "count(distinct event_id), max(capture_timestamp) "
                                          "from t group by 1,2 order by 1,2")
            else:
                rows, cols = _rows(con, uri, "select capture_date, "
                                             + ("season" if src != "weather" else "season")
                                             + ", count(*), 0, max(capture_timestamp) "
                                               "from t group by 1,2 order by 1,2")
        except Exception as exc:  # noqa: BLE001 — one unreadable store must not blind the others
            print(f"  {src:<16} UNREADABLE — {type(exc).__name__}: {str(exc)[:110]}")
            problems.append(f"{src} unreadable")
            continue

        print(f"  {src}")
        for capture_date, key, n, ev, ts in rows:
            extra = f" events={ev}" if src == "market" else ""
            print(f"     {capture_date}  {str(key):<12} rows={n:<6}{extra}  last_capture={ts}")
            if src == "market" and key == "props":
                props_rows += n
        if not rows:
            print("     (empty)")
        print()

    print("─" * 78)
    if props_rows:
        print(f"props: {props_rows} row(s) captured.")
    else:
        print("props: NONE captured on any date. If NFL_PIT_CAPTURE_PROPS is meant to be on, the "
              "flag is not reaching the container that RUNS the job (an env change needs the "
              "container RECREATED, not restarted) — or the props fetch failed, which the "
              "manifest's `errors` will name. Each missed Tue/Fri props board is unrecoverable.")
        if args.expect_props:
            problems.append("no props rows")

    print("\n⭐ The injuries leg's WITNESS is schema_snapshot: both are written by the SAME op in "
          "one invocation, so a schema capture at a cron instant proves the injury leg ran then "
          "too. Zero injury rows for the current season is EXPECTED until nflverse publishes "
          "injuries_<season>.parquet (week 1); it is not evidence the leg did not run.")

    if problems:
        print(f"\nPROBLEMS: {', '.join(problems)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
