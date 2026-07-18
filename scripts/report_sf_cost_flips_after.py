#!/usr/bin/env python3
"""
scripts/report_sf_cost_flips_after.py   (E11.20-COST — the AFTER measurement instrument)

One-command BEFORE→AFTER verdict on the 2026-07-16 wake-kill flip package
(docs/e11_20_cost_flips.md): daily metered credits, warehouse awake-hours, and the
per-waker-family 30-min-bucket footprint, each compared against the hardcoded BEFORE
baselines measured over 2026-07-06→07-12 (game days, pre-flip).

Read-only against snowflake.account_usage. Run WHERE the ACCOUNTADMIN key lives — the
LAPTOP (delegates to betting_ml.utils.data_loader.get_snowflake_connection):

  uv run python scripts/report_sf_cost_flips_after.py                # AFTER window starts 2026-07-17
  uv run python scripts/report_sf_cost_flips_after.py --after-start 2026-07-17 --dollars-per-credit 2.0

⏱️ account_usage latency: metering ~2h, query_history ~45min, query_attribution up to
~6h — a Sunday-late-night run reports 7/17+7/18 complete and most of 7/19; re-running
Monday morning firms up the last partial day. Both are fine for the go/no-go.

The flips this measures (deployed 2026-07-16 evening):
  F1 host-cron schedule-capture disabled (double-fire kill)  → capture_dbt buckets ≈ halve
  F2 lineup-monitor 8h horizon gate                          → monitor buckets → game-window only
  F3 write_book_odds --s3 (W7B+W6 gated)                     → intraday serving SF reads → ~0
  F4 W7B_LAKEHOUSE_S3=1 (daily predict/serving reads → S3)   → daily serving SF reads shrink
Target: game-day metered ~4.2–5.1 → ~2.5–3.0 credits/day (≈1.5–2.0 banked ≈ $90–120/mo).
"""
from __future__ import annotations

import argparse
from datetime import date

# ── BEFORE baselines (measured 2026-07-16 over the 7/06–7/12 pre-flip game days) ──
BEFORE = {
    "metered_credits_per_gameday": (4.23, 5.10),
    "metered_credits_per_breakday": (2.44, 2.71),   # 7/13–15, the All-Star break
    "awake_hours_per_day": 24,
    "attributed_compute_per_day": 0.79,             # ~5.5 credits/wk
    # 30-min buckets touched per WEEK (of 336) by each waker family:
    "buckets_capture_dbt": 288,
    "buckets_lineup_monitor": 273,
    "buckets_book_odds_sf": 78,                     # midpoint of 72–85
    "ext_refresh_per_week": 17005,
}

FAMILY_CASE = """
      case
        when query_text ilike '%stg_statsapi_probable_pitchers%'
          or query_text ilike '%stg_statsapi_lineups_wide%' then 'capture_dbt_tick'
        when query_text ilike '%lineup_monitor_state%'
          or query_text ilike '%pipeline_run_log%'          then 'lineup_monitor_tick'
        when query_text ilike 'alter external table%'        then 'ext_table_refresh'
        else 'other'
      end
"""


def run(cur, title, sql):
    print(f"\n{'=' * 96}\n{title}\n{'=' * 96}")
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) if rows else len(str(c))
              for i, c in enumerate(cols)]
    print("  ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print("  ".join(str(v).ljust(w) for v, w in zip(r, widths)))
    if not rows:
        print("(no rows)")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--after-start", default="2026-07-17",
                    help="first clean post-flip day (flips deployed 2026-07-16 evening)")
    ap.add_argument("--dollars-per-credit", type=float, default=2.0,
                    help="account $/credit for the banked-$ line (default 2.0)")
    args = ap.parse_args()

    from betting_ml.utils.data_loader import get_snowflake_connection
    conn = get_snowflake_connection()
    cur = conn.cursor()
    cur.execute("alter session set timezone='UTC'")

    # 1. Daily metered credits — the headline number.
    rows = run(cur, "1. metered credits/day (WAREHOUSE_METERING; BEFORE game days = "
                    f"{BEFORE['metered_credits_per_gameday'][0]}–{BEFORE['metered_credits_per_gameday'][1]})", f"""
        select to_date(start_time) as day,
               round(sum(credits_used), 2) as credits,
               round(sum(credits_used_compute), 2) as compute
        from snowflake.account_usage.warehouse_metering_history
        where start_time >= dateadd('day', -14, current_timestamp)
          and warehouse_name = 'COMPUTE_WH'
        group by 1 order by 1 desc""")
    after_days = {str(r[0]): float(r[1]) for r in rows if str(r[0]) >= args.after_start}

    # 2. Awake-hours/day — the idle-burn signal (BEFORE: 24/24 every day incl. break).
    run(cur, "2. awake hours/day (hours with any compute credits; BEFORE = 24)", f"""
        select to_date(start_time) as day,
               count(distinct date_trunc('hour', start_time)) as awake_hours
        from snowflake.account_usage.warehouse_metering_history
        where start_time >= dateadd('day', -14, current_timestamp)
          and warehouse_name = 'COMPUTE_WH' and credits_used_compute > 0
        group by 1 order by 1 desc""")

    # 3. Waker families: 30-min buckets touched per day since the AFTER start.
    #    BEFORE (per week/336): capture 288 · monitor 273 · ext refresh 17,005 queries.
    run(cur, "3. waker families by day since AFTER start (buckets30 of 48/day; "
             "BEFORE/wk: capture 288/336, monitor 273/336)", f"""
        with q as (
          select to_date(start_time) as day,
                 floor(datediff('minute', '2026-01-01', start_time) / 30) as b30,
                 {FAMILY_CASE} as fam
          from snowflake.account_usage.query_history
          where start_time >= '{args.after_start}'
            and warehouse_name = 'COMPUTE_WH'
        )
        select day, fam, count(*) as queries, count(distinct b30) as buckets30
        from q where fam != 'other'
        group by 1, 2 order by 1 desc, 4 desc""")

    # 4. Serving reads on SF (F3/F4): write_serving_store-class SELECTs through game hours.
    run(cur, "4. serving-path SF reads since AFTER start (F3/F4 — expect ~0 outside the "
             "daily window; write_api_cache is the known exception)", f"""
        select to_date(start_time) as day, count(*) as q,
               min(left(regexp_replace(query_text, '\\\\s+', ' '), 80)) as example_q
        from snowflake.account_usage.query_history
        where start_time >= '{args.after_start}'
          and warehouse_name = 'COMPUTE_WH'
          and query_tag ilike 'write_serving_store%'
          and regexp_like(query_text, '^\\\\s*(select|with)', 'is')
        group by 1 order by 1 desc""")

    # 5. Attributed vs metered — the wake/idle share (BEFORE: ~80% idle).
    run(cur, "5. attributed compute/day since AFTER start (BEFORE ~0.79; the metered-minus-"
             "attributed gap is the wake/idle burn)", f"""
        select to_date(qa.start_time) as day,
               round(sum(qa.credits_attributed_compute), 2) as attributed_compute
        from snowflake.account_usage.query_attribution_history qa
        where qa.start_time >= '{args.after_start}'
        group by 1 order by 1 desc""")

    # ── Verdict ──
    print(f"\n{'=' * 96}\nVERDICT (AFTER days ≥ {args.after_start}; today's partial day excluded)\n{'=' * 96}")
    full_days = {d: c for d, c in after_days.items() if d < date.today().isoformat()}
    if not full_days:
        print("No complete AFTER days in metering yet — re-run later (latency ~2h).")
    else:
        avg_after = sum(full_days.values()) / len(full_days)
        lo, hi = BEFORE["metered_credits_per_gameday"]
        avg_before = (lo + hi) / 2
        banked = avg_before - avg_after
        print(f"  AFTER complete days: {sorted(full_days)} → {[full_days[d] for d in sorted(full_days)]}")
        print(f"  avg AFTER  : {avg_after:.2f} credits/day")
        print(f"  avg BEFORE : {avg_before:.2f} credits/day (game-day baseline {lo}–{hi})")
        print(f"  BANKED     : {banked:.2f} credits/day ≈ ${banked * args.dollars_per_credit:.2f}/day "
              f"≈ ${banked * args.dollars_per_credit * 30:.0f}/mo at ${args.dollars_per_credit}/credit")
        print(f"  target was : 1.5–2.0 credits/day (~$90–120/mo)")
        print("  Checks: awake_hours < 24 on game days · capture_dbt buckets ≈ half of 288/wk pace ·")
        print("          monitor buckets ≈ game-window-only · serving-path SF reads ≈ daily-window only.")
    conn.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
