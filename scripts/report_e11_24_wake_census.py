#!/usr/bin/env python3
"""
scripts/report_e11_24_wake_census.py   (E11.24 — the per-BAND wake instrument)

The measurement E11.24 runs before and after every lever flip. Read-only against
`snowflake.account_usage`, on **MONITOR_WH** so the audit is never a line in its own
results (the self-inflicted-wake cure, target 3).

Run on the LAPTOP (that is where the Snowflake key lives):

    uv run python scripts/report_e11_24_wake_census.py
    uv run python scripts/report_e11_24_wake_census.py --days 12

⭐ WHY PER BAND, NOT PER DAY (docs/e11_24_literal_zero_snowflake.md "ATTRIBUTION CORRECTION"):
lever **1b** (the statcast catch-up no-op gate, flipped 2026-07-31 ~19:45 UTC) and lever
**6a** (the per-slate umpire idempotency gate) both reduce umpire-chain waits, but in
DISJOINT UTC hour bands — 1b owns 08-13 (the catch-up re-fire window), 6a owns 14-23 (the
10-min lineup-monitor tick). Crediting a whole-day delta to either double-counts the other.
So every table here is cut by band.

📐 THREE INSTRUMENTS, and the reason each is here (E11.20-COST + the 7/31 re-census):
  1. RESUMES        — `warehouse_events_history`. The bursty-lever signal. 6a is bursty ⇒
                      expect it HERE.
  2. ACTIVE MINUTES — distinct minutes containing ≥1 query. The 24/7-POLLER signal: a lever
                      that deletes an evenly-spread poller (weather) deletes awake-TIME while
                      resumes stay flat. Report both or you under-credit exactly the levers
                      this story is built on.
  3. PROVISIONING WAITS — `query_history.queued_provisioning_time > 0`. The ATTRIBUTION
                      instrument: a query only queues on provisioning if it waited for the
                      warehouse to start, so it names the waker directly (3.7% unclassified
                      vs 53% for the "first query at/after the resume" heuristic the earlier
                      censuses used).
  ⛔ NOT sum-of-elapsed-seconds — it moved the WRONG way across a real 16% awake-time cut.

⚠️ A SHAPE GOING TO ZERO IS ALSO WHAT A DEAD JOB LOOKS LIKE. Every per-shape table below
reports TOTAL EXECUTIONS beside the waits, so "the lever fired" is separable from "the
caller stopped".

⚠️ BASELINE HYGIENE: 2026-07-29 and 2026-07-31 are CONTAMINATED (the census's own audit
queries + two `--reset` backfills, run as `DBT_RW` so they cannot be filtered by user).
Use 7/28 and 7/30 as pre-flip references. `account_usage` lags ~45 min (query_history) to
~2-3 h (events), so today's last band is always partial — the footer prints the lag.
"""
from __future__ import annotations

import argparse

# UTC hour bands. 1b (statcast catch-up re-fire) and 6a (lineup-monitor tick) are separable
# because they live in disjoint bands; see the attribution correction in the E11.24 doc.
BAND_CASE = """
      case when hour(start_time) between 8 and 13 then '08-13 (1b catchup)'
           when hour(start_time) between 14 and 23 then '14-23 (6a tick)'
           else '00-07 (overnight)' end
"""

# Classify a waker by the table it READS, never by the job it belongs to (the 7/29 lesson:
# compute_elo's waker is its READ of mart_game_results, and the weather slate query never
# contains the string "weather" — it joins ref_venues).
FAMILY_CASE = """
      case
        when q ilike '%umpire%'                              then '6a umpire chain'
        when q ilike '%int_bullpen_ali%'                     then '1b int_bullpen_ali'
        when q ilike '%mart_game_results%'                   then '1b/1 compute_elo read'
        when q ilike '%feature_pregame_lineup_features%'
          or q ilike '%feature_pregame_starter_features%'    then '6 lineup/starter CTAS'
        when q ilike '%stg_statsapi_lineups_wide%'
          or q ilike '%stg_statsapi_probable_pitchers%'      then '6 tick CTAS (dead 7/25)'
        when q ilike '%player_sequential_posteriors%'        then '4 player posteriors'
        when q ilike '%team_sequential_posteriors%'          then '4 team posteriors'
        when q ilike '%matchup_cell_sequential_posteriors%'  then '4 matchup posteriors'
        when q ilike '%mart_sub_model_signals%'
          or q ilike '%tmp_scd2_incoming%'                   then '4b scd2 signal writers'
        when q ilike '%feature_pregame_sub_model_signals%'   then '4b signals consumer'
        when q ilike '%pipeline_run_log%'                    then 'lineup_monitor audit INSERT'
        when q ilike '%ref_venues%'                          then '2 weather slate'
        when q ilike '%metering%' or q ilike '%account_usage%' then '3 metering/audit'
        else 'other'
      end
"""


def run(cur, title, sql, note=None):
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")
    if note:
        print(f"  {note}\n")
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    widths = [
        max(len(str(c)), *(len(str(r[i])) for r in rows)) if rows else len(str(c))
        for i, c in enumerate(cols)
    ]
    print("  ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print("  ".join(str(v).ljust(w) for v, w in zip(r, widths)))
    if not rows:
        print("(no rows)")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=10, help="lookback window (default 10)")
    ap.add_argument("--warehouse", default="COMPUTE_WH", help="warehouse under measurement")
    args = ap.parse_args()
    d, wh = args.days, args.warehouse

    from betting_ml.utils.data_loader import get_monitoring_connection

    conn = get_monitoring_connection()
    cur = conn.cursor()
    # Everything below is reported in UTC. ⚠️ `warehouse_events_history.timestamp` is
    # TIMESTAMP_LTZ: a `>= 'YYYY-MM-DD'` string boundary would prune in the SESSION tz and
    # cut ~7h off the first day (the LTZ boundary-day landmine). Two defences: the session is
    # pinned to UTC, and every filter is a `dateadd` on a timestamp, never a date string.
    cur.execute("alter session set timezone='UTC'")

    run(cur, f"1. RESUMES/day — {wh} (the BURSTY-lever signal; 6a should land here)", f"""
        select to_char(timestamp::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
               count(*) as resumes
        from snowflake.account_usage.warehouse_events_history
        where event_name = 'RESUME_WAREHOUSE' and event_state = 'STARTED'
          and warehouse_name = '{wh}'
          and timestamp >= dateadd(day, -{d}, current_timestamp())
        group by 1 order by 1""",
        note="event_state='STARTED' is REQUIRED — RESUME_WAREHOUSE and RESUME_CLUSTER are "
             "separate rows and an unfiltered count roughly doubles.")

    run(cur, f"2. ACTIVE MINUTES/day — {wh} (the 24/7-POLLER signal; ref 7/28=167, 7/30=141)", f"""
        select to_char(start_time::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
               count(distinct date_trunc('minute', start_time)) as active_min,
               count(*) as executions
        from snowflake.account_usage.query_history
        where warehouse_name = '{wh}'
          and start_time >= dateadd(day, -{d}, current_timestamp())
        group by 1 order by 1""",
        note="`executions` is the DEAD-JOB cross-check: active-min falling while executions "
             "hold = a lever; both collapsing = the caller stopped.")

    run(cur, f"3. PROVISIONING WAITS by day × BAND — {wh}  ⬅ THE HEADLINE", f"""
        select to_char(start_time::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
               {BAND_CASE} as band,
               count(*) as waits,
               round(avg(queued_provisioning_time)/1000, 1) as avg_wait_s
        from snowflake.account_usage.query_history
        where warehouse_name = '{wh}' and queued_provisioning_time > 0
          and start_time >= dateadd(day, -{d}, current_timestamp())
        group by 1, 2 order by 1, 2""",
        note="1b owns 08-13, 6a owns 14-23. A whole-day delta double-counts; read the band.")

    run(cur, f"4. PROVISIONING WAITS by BAND × FAMILY — {wh} (who is left, and where)", f"""
        with h as (
          select {BAND_CASE} as band,
                 left(regexp_replace(query_text, '\\\\s+', ' '), 400) as q
          from snowflake.account_usage.query_history
          where warehouse_name = '{wh}' and queued_provisioning_time > 0
            and start_time >= dateadd(day, -{d}, current_timestamp())
        )
        select band, {FAMILY_CASE} as family, count(*) as waits
        from h group by 1, 2 having count(*) > 0 order by 1, 3 desc""",
        note="Classified by the table READ, not the owning job.")

    run(cur, "5. LEVER 1b VERIFICATION — the two 08-13 shapes, waits AND executions", f"""
        select to_char(start_time::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
               case when regexp_replace(query_text,'\\\\s+',' ') ilike '%int_bullpen_ali%'
                      then 'int_bullpen_ali'
                    when regexp_replace(query_text,'\\\\s+',' ') ilike '%mart_game_results%'
                      then 'compute_elo read'
                    else 'umpire (catchup chain)' end as shape,
               count(*) as executions,
               sum(iff(queued_provisioning_time > 0, 1, 0)) as waits
        from snowflake.account_usage.query_history
        where warehouse_name = '{wh}'
          and start_time >= dateadd(day, -{d}, current_timestamp())
          and hour(start_time) between 8 and 13
          and (regexp_replace(query_text,'\\\\s+',' ') ilike '%int_bullpen_ali%'
            or regexp_replace(query_text,'\\\\s+',' ') ilike '%mart_game_results%'
            or regexp_replace(query_text,'\\\\s+',' ') ilike '%umpire%')
        group by 1, 2 order by 1, 2""",
        note="Pre-flip 1b: int_bullpen_ali ran ~10x/hr through 08-13. EXECUTIONS going to ~0 "
             "with the daily job still running = the gate fired; the waits column is the credit.")

    run(cur, "6. LEVER 6a PRE-FLIP REFERENCE — umpire chain by day × band, waits AND executions", f"""
        select to_char(start_time::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
               {BAND_CASE} as band,
               count(*) as executions,
               sum(iff(queued_provisioning_time > 0, 1, 0)) as waits
        from snowflake.account_usage.query_history
        where warehouse_name = '{wh}'
          and start_time >= dateadd(day, -{d}, current_timestamp())
          and regexp_replace(query_text, '\\\\s+', ' ') ilike '%umpire%'
        group by 1, 2 order by 1, 2""",
        note="6a gates ONLY the 14-23 band (the intraday tick). The 08-13 slice belongs to 1b "
             "and the once-daily UNGATED rebuild — it must NOT go to zero.")

    rows = run(cur, "7. account_usage LATENCY (how partial is today?)", f"""
        select 'query_history' as view,
               to_char(max(start_time)::timestamp_ntz, 'YYYY-MM-DD HH24:MI') as latest_utc,
               datediff('minute', max(start_time), current_timestamp()) as lag_min
        from snowflake.account_usage.query_history
        where start_time >= dateadd(day, -2, current_timestamp())
        union all
        select 'warehouse_events_history',
               to_char(max(timestamp)::timestamp_ntz, 'YYYY-MM-DD HH24:MI'),
               datediff('minute', max(timestamp), current_timestamp())
        from snowflake.account_usage.warehouse_events_history
        where timestamp >= dateadd(day, -2, current_timestamp())""")

    print(f"\n{'=' * 100}\nREAD IT LIKE THIS\n{'=' * 100}")
    print("  · Compare BANDS across days, never whole days (1b and 6a both cut umpire waits).")
    print("  · 7/29 and 7/31 are CONTAMINATED baselines (own audit queries + --reset backfills).")
    print("  · A shape at zero is only a lever if EXECUTIONS held up elsewhere; else it's a dead job.")
    print("  · Wake↓ does NOT imply credit↓ — the credit line only moves once the warehouse")
    print("    actually stays suspended for long stretches (the E11.20-COST lesson).")
    print(f"  · Today's trailing band is partial by the lag printed above ({rows and 'see table 7'}).")
    conn.close()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
