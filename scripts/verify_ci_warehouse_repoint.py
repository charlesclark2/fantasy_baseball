#!/usr/bin/env python
"""E11.24 — prove the dbt-Build CI repoint onto `CI_WH` under REAL LOAD.

WHY THIS EXISTS (the defect it closes)
--------------------------------------
The 2026-08-10 repoint was recorded as "CI_WH IS LIVE AND PROVEN — traffic moved", on the
strength of 8 statements under `CI_WH` and 0 under `COMPUTE_WH`. Re-measured 2026-08-14:

    CI_WH, all time:  12 statements, ALL `warehouse_size IS NULL`, 0 bytes scanned, 0 waits.

Every one was cloud-services-only (`DROP` x8, `SELECT` x3, `GRANT` x1 — the `drop_ci_schemas`
teardowns). `dbtf build --select state:modified+` had selected NOTHING, because that PR changed
`profiles.yml` and the workflow, neither of which is a model. So the warehouse was never resumed
and never did any work.

⇒ **A CI run that builds nothing puts zero statements on `COMPUTE_WH` whether or not the repoint
works.** Healthy and broken produce the identical observation. That session's own doc states the
standard that rules its proof out — "a green CI run that selects zero models proves the env var is
read, never that the warehouse is usable or that traffic moved" — and the run it cited met exactly
that description.

So the assertion here is deliberately TWO-SIDED and insists on OCCUPATION, not mere attribution:

    (1) CI_WH carried at least one BILLABLE statement   (`warehouse_size IS NOT NULL`)
    (2) NO CI statement ran on COMPUTE_WH               (`schema_name = 'CI_BETTING'` there)

(1) alone is the part the prior proof lacked. (2) alone is satisfiable by an empty run.

⚠️ (2) IS SCOPED TO THE `CI_BETTING` SCHEMA, DELIBERATELY. The naive form — "DBT_RW ran nothing on
COMPUTE_WH" — is unusable: measured 2026-08-14, the box pipeline puts `DBT_RW` on `COMPUTE_WH` in
**19 of 24 hours**, so that clause would report NOT PROVEN on a perfectly working repoint in almost
any window. `ci_betting` is the schema the CI target builds into, it is what the pre-repoint CI
bursts carried (08-06/07/10 on COMPUTE_WH), and the box pipeline never writes it — 0 `ci_betting`
executions on COMPUTE_WH across all 19 of those hours. So this clause is BOTH discriminating and
confound-free, where the broad one is neither. The broad count is still reported, as context.

HOW TO USE
----------
    gh workflow run dbt_build_ci.yml --ref main          # builds the `ref_teams` seed on --target ci
    uv run python scripts/verify_ci_warehouse_repoint.py --since-minutes 90

Reads `snowflake.account_usage.query_history` on **MONITOR_WH** (`get_monitoring_connection`), so
the measurement never wakes the warehouse being measured. Never touches COMPUTE_WH.

⚠️ `account_usage.query_history` lags ~10-45 min. If the run just finished, wait — an empty result
is reported as UNVERIFIED, never as a pass (NF1.7 (a): a check that did not run is not a pass).

⚠️ TIMEZONE. `start_time` is `TIMESTAMP_LTZ`, so `hour()`, `to_date()` and `::timestamp_ntz` are
all evaluated in the SESSION timezone. Measured 2026-08-14: `hour(start_time)` disagreed with the
UTC hour on 10,331 of 10,331 statements. Worse, `convert_timezone('UTC', start_time) BETWEEN
'<literal>'` coerces the LITERAL back to session-local, silently re-introducing the same shift —
that cost this session a query that read 07:20-08:30 UTC while claiming 00:20-01:30. Both sides of
every comparison below are cast to `TIMESTAMP_NTZ` in UTC.
"""

from __future__ import annotations

import argparse
import os
import sys

# UTC-naive on BOTH sides of every comparison — see the timezone note above.
_UTC = "convert_timezone('UTC', start_time)::timestamp_ntz"

_WINDOW = f"{_UTC} >= dateadd(minute, -%(mins)s, convert_timezone('UTC', current_timestamp())::timestamp_ntz)"

# A coarse LTZ prefilter so the scan is pruned; deliberately WIDER than the reported window (a
# boundary day must never be a reported day — the LTZ boundary-truncation lesson).
_PREFILTER = "start_time >= dateadd(minute, -%(mins)s - 1440, current_timestamp())"


def _rows(cur, sql: str, mins: int) -> list[tuple]:
    cur.execute(sql % {"mins": mins})
    return cur.fetchall()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since-minutes", type=int, default=90, help="look-back window in minutes (default 90)")
    ap.add_argument("--ci-warehouse", default="CI_WH")
    ap.add_argument("--prod-warehouse", default="COMPUTE_WH")
    args = ap.parse_args()

    sys.path.insert(0, os.getcwd())
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    from betting_ml.utils.data_loader import get_monitoring_connection

    conn = get_monitoring_connection()
    cur = conn.cursor()
    mins = args.since_minutes

    try:
        ci = _rows(
            cur,
            f"""
            select iff(warehouse_size is null, 'metadata_only', 'BILLABLE') as kind,
                   count(*) as execs,
                   sum(iff(queued_provisioning_time > 0, 1, 0)) as waits,
                   sum(coalesce(bytes_scanned, 0)) as bytes_scanned,
                   to_char(min({_UTC}), 'YYYY-MM-DD HH24:MI') as first_utc,
                   to_char(max({_UTC}), 'YYYY-MM-DD HH24:MI') as last_utc
            from snowflake.account_usage.query_history
            where {_PREFILTER} and {_WINDOW}
              and warehouse_name = '{args.ci_warehouse}'
            group by 1 order by 1
            """,
            mins,
        )
        prod = _rows(
            cur,
            f"""
            select iff(schema_name = 'CI_BETTING', 'CI (ci_betting) — DISQUALIFYING',
                       'box pipeline (other schema) — context only') as who,
                   iff(warehouse_size is null, 'metadata_only', 'BILLABLE') as kind,
                   count(*) as execs,
                   sum(iff(queued_provisioning_time > 0, 1, 0)) as waits,
                   to_char(min({_UTC}), 'YYYY-MM-DD HH24:MI') as first_utc
            from snowflake.account_usage.query_history
            where {_PREFILTER} and {_WINDOW}
              and warehouse_name = '{args.prod_warehouse}'
              and user_name = 'DBT_RW'
            group by 1, 2 order by 1, 2
            """,
            mins,
        )
        lag = _rows(
            cur,
            f"""
            select datediff('minute', max(start_time), current_timestamp()) as lag_min
            from snowflake.account_usage.query_history
            where start_time >= dateadd(hour, -6, current_timestamp())
            """,
            mins,
        )
    finally:
        cur.close()
        conn.close()

    lag_min = lag[0][0] if lag and lag[0][0] is not None else None
    print(f"\nwindow: last {mins} min (UTC)   account_usage lag: {lag_min} min\n")

    def show(title, rows):
        print(f"  {title}")
        if not rows:
            print("    (no statements)")
        for r in rows:
            print("    " + " | ".join("" if v is None else str(v) for v in r))

    show(f"{args.ci_warehouse}:", ci)
    show(f"{args.prod_warehouse} (DBT_RW):", prod)

    ci_billable = sum(r[1] for r in ci if r[0] == "BILLABLE")
    ci_any = sum(r[1] for r in ci)
    # Only ci_betting rows disqualify — the box pipeline's own COMPUTE_WH traffic is expected
    # (19 of 24 hours) and must not be read as a failed repoint.
    prod_ci = sum(r[2] for r in prod if r[0].startswith("CI "))
    prod_box = sum(r[2] for r in prod if not r[0].startswith("CI "))

    print()
    if ci_any == 0:
        print(f"⚠️  UNVERIFIED — no statements on {args.ci_warehouse} in the window.")
        print(f"    account_usage lags ~10-45 min (currently {lag_min}); if the run just finished, wait and re-run.")
        print("    An absent measurement is NOT a pass.")
        return 2

    ok = True
    if ci_billable > 0:
        print(f"✅ (1) {args.ci_warehouse} carried {ci_billable} BILLABLE statement(s) — the warehouse was OCCUPIED.")
    else:
        ok = False
        print(f"❌ (1) {args.ci_warehouse} carried {ci_any} statement(s) but ALL metadata-only (0 billable).")
        print("       This is the 2026-08-10 non-proof: the build selected nothing, so the run")
        print("       cannot distinguish a working repoint from a broken one. Re-dispatch with a")
        print("       selector that materializes something (default `ref_teams` issues an INSERT).")

    if prod_ci == 0:
        print(f"✅ (2) No CI (`ci_betting`) statement ran on {args.prod_warehouse}.")
        if prod_box:
            print(f"       ({prod_box} box-pipeline statement(s) there — EXPECTED, not a failure: the box")
            print("        uses COMPUTE_WH in 19 of 24 hours. Only ci_betting disqualifies.)")
    else:
        ok = False
        print(f"❌ (2) {prod_ci} CI (`ci_betting`) statement(s) ran on {args.prod_warehouse} — the repoint")
        print("       did NOT hold. Most likely the SNOWFLAKE_CI_WAREHOUSE secret is EMPTY (not unset):")
        print("       an empty value makes the `warehouse` key vanish and Snowflake falls back to")
        print("       DBT_RW's default warehouse, silently, with dbt debug green.")

    print("\n" + ("VERDICT: CI_WH REPOINT PROVEN UNDER LOAD" if ok else "VERDICT: NOT PROVEN"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
