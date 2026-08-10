#!/usr/bin/env python3
"""
scripts/report_e11_24_other_attribution.py   (E11.24 — the `other`-bucket STATEMENT cut)

Read-only. Runs on **MONITOR_WH** (`get_monitoring_connection`) so the audit is never a line in
its own results. Companion to `report_e11_24_wake_census.py`, which classifies waits into
FAMILIES; this script opens the largest family — `other` — down to individual STATEMENTS, and
answers the three questions the family cut cannot:

  1. WHICH STATEMENT wakes the warehouse, and who owns it?
  2. Is it a bursty WAKER (shows in resumes), a 24/7 POLLER (shows in awake-minutes), or an
     overnight ZOMBIE (fires in the 00-07 zero-game band = the literal-zero blocker)?
  3. Would a table->view flip actually remove the wake? (Table 5 measures it directly.)

Run on the LAPTOP (that is where the Snowflake key lives):

    uv run python scripts/report_e11_24_other_attribution.py
    uv run python scripts/report_e11_24_other_attribution.py --days 9

────────────────────────────────────────────────────────────────────────────────────────────
⚠️ FOUR MEASUREMENT LANDMINES THIS SCRIPT EXISTS TO NOT STEP IN. Each cost a prior session,
and the first two were stepped in *again* while building this one.

⭐ (1) `warehouse_size IS NULL` = THE QUERY NEVER OCCUPIED THE WAREHOUSE.
A row in `query_history` carrying `warehouse_name='COMPUTE_WH'` has NOT necessarily used the
warehouse: cloud-services-only statements (`SHOW OBJECTS`, `ALTER SESSION SET QUERY_TAG`,
`ALTER EXTERNAL TABLE ... REFRESH`, `CALL SYSTEM$...`, and every `create or replace view`) are
billed to cloud services and can neither RESUME the warehouse nor keep it awake. They are
distinguished by `warehouse_size IS NULL` (and 0 bytes scanned).
  · Measured 2026-08-08: they are **40–138% of the census's ACTIVE-MINUTES figure** (Table 2).
  · Ignoring this invents phantom pollers. The first cut of this script ranked
    `CALL SYSTEM$GET_RECENT_IN_APP_NOTIFICATIONS()` as the single largest awake-time consumer
    in the account (74 "exclusive" minutes) — it is a Snowsight browser tab's notification poll
    that never touched the warehouse. A fix session would have been sent at nothing.
  · WAITS are immune (a metadata query cannot queue on provisioning), which is why the
    provisioning-wait instrument stayed sound while the awake-time one did not.
⇒ every awake-time cut here filters `warehouse_size is not null`. Waits are reported both ways
  only in Table 1, to prove the filter changes no wait total.

⭐ (2) READ PER-DAY, NEVER THE AGGREGATE, WHEN THE WINDOW STRADDLES A FLIP.
Target 6 deployed 2026-08-06. A 6-day aggregate put `feature_pregame_umpire_features` at 23
waits — top of the board — when the per-day cut shows it went `12/0` `8/0` `9/0` as a VIEW from
08-06 (executions HOLD, waits -> 0, DDL kind flips = the gate fired; the waits are pre-flip
residue). Table 6 is the per-day cut and is the only one that may be quoted for a verdict.

⭐ (3) CLASSIFY OVER THE SAME 400-CHAR WINDOW `FAMILY_CASE` USES.
`FAMILY_CASE` is imported from the census rather than restated, so the two scripts cannot drift.
Truncating shorter before classifying dumps real families into `other` and invents a phantom
waker (the 2026-08-03 110-char bug). Table 0 cross-checks the classified total against an
unclassified one; they must agree exactly or the classification is wrong, not interesting.

⭐ (4) A SHAPE AT ZERO IS ALSO WHAT A DEAD JOB LOOKS LIKE.
Every per-day cell is `executions/waits`. executions HOLD + waits->0 = a lever fired; BOTH
collapsing = the caller stopped (do not take credit); both holding = a live waker.

⚠️ `warehouse_events_history.timestamp` / `query_history.start_time` are TIMESTAMP_LTZ — a
`>= 'YYYY-MM-DD'` string boundary prunes in the session tz and cuts ~7h off the range's FIRST
day. Defences: the session is pinned to UTC, every filter is a `dateadd` on a timestamp (never a
date string), and the window is deliberately read WIDER than the days quoted.
"""
from __future__ import annotations

import argparse

# Imported, never restated — see landmine (3). If the census's classifier changes, this script
# changes with it, and a `other` total computed here always means the same thing as there.
from scripts.report_e11_24_wake_census import FAMILY_CASE, run, run_pivot

# Cloud-services-only statements never occupy the warehouse — landmine (1). Applied to every
# awake-time cut; deliberately NOT applied to wait counts, which are immune.
OCCUPIES_WAREHOUSE = "warehouse_size is not null"


def base_cte(wh: str, days: int, occupying_only: bool = True) -> str:
    """The shared scan. One CTE, family computed ONCE.

    A doubly-evaluated FAMILY_CASE over an unfiltered `query_history` scan timed out at 300s on
    2026-08-03 — hence the single computation and the finite STATEMENT_TIMEOUT set in main().
    """
    occ = f"and {OCCUPIES_WAREHOUSE}" if occupying_only else ""
    return f"""
    with h as (
      select to_char(start_time::timestamp_ntz,'YYYY-MM-DD') as utc_day,
             hour(start_time) as hr,
             iff(queued_provisioning_time > 0, 1, 0) as is_wait,
             query_parameterized_hash as shape,
             user_name, role_name,
             date_trunc('minute', start_time) as mn,
             left(regexp_replace(query_text, '\\\\s+', ' '), 400) as q
      from snowflake.account_usage.query_history
      where warehouse_name = '{wh}'
        and start_time >= dateadd(day, -{days}, current_timestamp())
        {occ}
    ),
    f as (select h.*, {FAMILY_CASE} as family from h)
    """


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=6, help="lookback window (default 6)")
    ap.add_argument("--warehouse", default="COMPUTE_WH", help="warehouse under measurement")
    args = ap.parse_args()
    d, wh = args.days, args.warehouse

    from betting_ml.utils.data_loader import get_monitoring_connection

    conn = get_monitoring_connection()
    cur = conn.cursor()
    cur.execute("alter session set timezone='UTC'")
    # INC-32 — a finite bound on every statement on a shared/serialized path.
    cur.execute("alter session set STATEMENT_TIMEOUT_IN_SECONDS=600")

    # ── 0. RECONCILIATION ────────────────────────────────────────────────────────────────
    run(cur, "0. RECONCILIATION — classified vs unclassified totals (MUST agree exactly)", f"""
        {base_cte(wh, d, occupying_only=False)}
        select 'via FAMILY_CASE' as source, count(*) as execs, sum(is_wait) as waits from f
        union all
        select 'raw (no CASE)', count(*), sum(iff(queued_provisioning_time > 0, 1, 0))
        from snowflake.account_usage.query_history
        where warehouse_name = '{wh}'
          and start_time >= dateadd(day, -{d}, current_timestamp())""",
        note="A family bucket that does not reconcile is a MIS-CLASSIFICATION, not a finding "
             "(the 2026-08-03 110-char truncation bug). If these two rows differ, STOP.")

    # ── 1. THE INSTRUMENT CORRECTION ─────────────────────────────────────────────────────
    run(cur, "1. METADATA-ONLY POLLUTION — how much of 'active minutes' never used the warehouse", f"""
        select to_char(start_time::timestamp_ntz,'YYYY-MM-DD') as utc_day,
               count(distinct date_trunc('minute', start_time)) as active_min_as_counted,
               count(distinct iff({OCCUPIES_WAREHOUSE},
                                  date_trunc('minute', start_time), null)) as active_min_real,
               count(*) as execs,
               sum(iff(warehouse_size is null, 1, 0)) as metadata_only_execs,
               sum(iff(queued_provisioning_time > 0, 1, 0)) as waits,
               sum(iff(queued_provisioning_time > 0 and {OCCUPIES_WAREHOUSE}, 1, 0)) as waits_real
        from snowflake.account_usage.query_history
        where warehouse_name = '{wh}'
          and start_time >= dateadd(day, -{d}, current_timestamp())
        group by 1 order by 1""",
        note="`active_min_as_counted` is what report_e11_24_wake_census.py Table 2 reports; "
             "`active_min_real` excludes cloud-services-only statements (landmine 1).\n"
             "  ⭐ waits == waits_real on every row is the PROOF the filter costs no wait "
             "signal — a metadata query cannot queue on provisioning.\n"
             "  ⛔ Do NOT retro-fit this filter into the census mid-soak: it would break "
             "comparability with that soak's own T+0/T+1 readings. Fix it after the soak closes.")

    # ── 2. THE HEADLINE ──────────────────────────────────────────────────────────────────
    run_pivot(cur, "2. 'other' STATEMENT-LEVEL — who is left, per day (execs/waits)", f"""
        {base_cte(wh, d)}
        select left(regexp_replace(min(q), '\\\\s+', ' '), 58) as statement,
               utc_day, count(*) as execs, sum(is_wait) as waits
        from f
        where family = 'other'
          -- Shape-level, NOT (shape, day)-level: a shape is included on EVERY day it ran, so
          -- long as it woke the warehouse on SOME day. Filtering per (shape, day) would print
          -- `·` for a day the statement ran without waiting — making "did not run" and "ran but
          -- did not wake" look identical, which is landmine (4) reintroduced by the renderer.
          and shape in (select shape from f where family = 'other'
                        group by shape having sum(is_wait) > 0)
        group by shape, utc_day
        order by 1, 2""",
        note="Keyed on `query_parameterized_hash` — statement identity, so no text-truncation\n"
             "  risk (landmine 3). A shape appears on every day it RAN (execs/waits), provided it\n"
             "  woke the warehouse on at least one day — so `execs/0` means 'ran, did not wake'\n"
             "  and `·` means 'did not run at all'. Those are different findings; see landmine (4).",
        label_width=60)

    # ── 3. THE LITERAL-ZERO BLOCKER ──────────────────────────────────────────────────────
    run(cur, "3. OVERNIGHT 00-07 (zero-game band) by IDENTITY — the literal-zero blocker", f"""
        {base_cte(wh, d)}
        select user_name, role_name, family,
               count(*) as execs, sum(is_wait) as waits,
               count(distinct mn) as awake_min,
               count(distinct utc_day) as days_active
        from f where hr between 0 and 7
        group by 1, 2, 3 having sum(is_wait) > 0
        order by waits desc""",
        note="The band with no games. Anything here is what stops the warehouse sleeping "
             "through the night — the exit criterion for literal-zero.")

    # ── 4. POLLER vs WAKER ───────────────────────────────────────────────────────────────
    run(cur, "4. WAKER vs POLLER — resumes and awake-minutes side by side ('other' only)", f"""
        {base_cte(wh, d)}
        select left(regexp_replace(min(q), '\\\\s+', ' '), 62) as statement,
               min(user_name) as usr,
               sum(is_wait) as waits, count(*) as execs,
               count(distinct mn) as awake_min,
               round(100.0 * sum(is_wait) / nullif(count(*), 0), 0) as wake_pct
        from f where family = 'other'
        group by shape
        having sum(is_wait) > 0 or count(distinct mn) >= 20
        order by waits desc, awake_min desc limit 25""",
        note="A bursty WAKER shows in `waits`; a 24/7 POLLER shows in `awake_min` with few "
             "waits.\n  `wake_pct` = share of executions that resumed the warehouse: at ~100% "
             "almost every\n  run is a resume, which is the highest-value thing to remove.")

    # ── 5. WOULD A VIEW FLIP ACTUALLY PAY? ───────────────────────────────────────────────
    run(cur, "5. VIEW-FLIP PAYOFF — which rebuild statements wake, and the `view` control", f"""
        select lower(regexp_substr(regexp_replace(query_text,'\\\\s+',' '),
                 'create or replace (transient table|temporary table|table|view)',
                 1, 1, 'i', 1)) as ddl_kind,
               regexp_substr(regexp_replace(query_text,'\\\\s+',' '),
                 'create or replace (transient table|temporary table|table|view) ([a-zA-Z0-9_\\\\.]+)',
                 1, 1, 'i', 2) as object_name,
               count(*) as execs,
               sum(iff(queued_provisioning_time > 0, 1, 0)) as waits,
               sum(iff(warehouse_size is null, 1, 0)) as metadata_only
        from snowflake.account_usage.query_history
        where warehouse_name = '{wh}'
          and start_time >= dateadd(day, -{d}, current_timestamp())
          and regexp_replace(query_text,'\\\\s+',' ') ilike 'create or replace %'
        group by 1, 2
        having sum(iff(queued_provisioning_time > 0, 1, 0)) > 0
            or lower(regexp_substr(regexp_replace(query_text,'\\\\s+',' '),
                 'create or replace (transient table|temporary table|table|view)',
                 1, 1, 'i', 1)) = 'view'
        order by waits desc, execs desc limit 30""",
        note="⭐ THE CONTROL IS THE POINT: every `create or replace view` row must show "
             "waits=0 and metadata_only=execs.\n  That is the direct proof a table->view flip "
             "removes the wake rather than relocating it —\n  measured 2026-08-08 at 837 execs "
             "/ 0 waits / 837 metadata-only. Any `view` row with a\n  wait would falsify the "
             "whole view-flip thesis, so this table is where it would show up.")

    # ── 6. FLIP VERIFICATION ─────────────────────────────────────────────────────────────
    run_pivot(cur, "6. PER-DAY REBUILD CUT — the ONLY table that may be quoted for a verdict", f"""
        with h as (
          select to_char(start_time::timestamp_ntz,'YYYY-MM-DD') as utc_day,
            regexp_substr(regexp_replace(query_text,'\\\\s+',' '),
              'create or replace (transient table|temporary table|table|view) ([a-zA-Z0-9_\\\\.]+)',
              1, 1, 'i', 2) as obj,
            lower(regexp_substr(regexp_replace(query_text,'\\\\s+',' '),
              'create or replace (transient table|temporary table|table|view)',
              1, 1, 'i', 1)) as kind,
            iff(queued_provisioning_time > 0, 1, 0) as is_wait
          from snowflake.account_usage.query_history
          where warehouse_name = '{wh}'
            and start_time >= dateadd(day, -{d}, current_timestamp())
            and regexp_replace(query_text,'\\\\s+',' ') ilike 'create or replace %'
        )
        select split_part(obj, '.', 3) || iff(kind = 'view', ' [VIEW]', '') as object_name,
               utc_day, count(*) as execs, sum(is_wait) as waits
        from h where obj is not null
        group by 1, 2 having sum(is_wait) > 0 or max(kind) = 'view'
        order by 1, 2""",
        note="Each cell is EXECUTIONS/WAITS. A model appears on BOTH a `[VIEW]` row and a bare\n"
             "  row when the window straddles its flip — that split IS the verdict:\n"
             "     · executions HOLD across the split, waits -> 0 on the [VIEW] row = FLIP LANDED.\n"
             "     · a bare row still carrying waits on the LATEST days            = NOT flipped.\n"
             "     · executions AND waits both collapse                            = dead caller.\n"
             "  ⚠️ Target 6 deployed 2026-08-06. Reading the 6-day AGGREGATE instead of this cut\n"
             "  put an already-flipped model at the TOP of the board on 2026-08-08.",
        label_width=52)

    run(cur, "7. account_usage LATENCY (how partial is today?)", """
        select 'query_history' as view_name,
               to_char(max(start_time)::timestamp_ntz, 'YYYY-MM-DD HH24:MI') as latest_utc,
               datediff('minute', max(start_time), current_timestamp()) as lag_min
        from snowflake.account_usage.query_history
        where start_time >= dateadd(day, -2, current_timestamp())""")

    print(f"\n{'=' * 100}\nREAD IT LIKE THIS\n{'=' * 100}")
    print("  · Table 0 must reconcile exactly, or nothing below it means anything.")
    print("  · Quote Table 6 for any verdict; the aggregates are orientation only.")
    print("  · awake-minutes are only meaningful with the warehouse_size filter (Table 1).")
    print("  · A shape at zero is a lever ONLY if executions held; else the caller died.")
    print("  · Wake down does NOT imply credit down — only sustained suspension moves the bill.")
    conn.close()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
