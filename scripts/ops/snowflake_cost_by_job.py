"""snowflake_cost_by_job.py — E11.3 cost-attribution report.

Queries SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY (45 min – 3 h lag) and estimates
warehouse compute credits per QUERY_TAG, then prints a ranked breakdown.

Usage:
    uv run python scripts/ops/snowflake_cost_by_job.py [--days N] [--raw]

Options:
    --days N   Lookback window in days (default 7).
    --raw      Dump the full per-tag table as CSV instead of the summary.

Credit estimation:
    Snowflake bills per warehouse-second — execution_time (ms) / 3_600_000 ×
    credits/hour for the warehouse size.  Warehouse sizes map to:
        X-Small → 1 cr/h, Small → 2, Medium → 4, Large → 8, X-Large → 16.
    ACCOUNT_USAGE also records per-query CREDITS_USED_CLOUD_SERVICES (usually
    tiny — < 1 % of compute) which we add separately.

This report feeds the 2026-06-22 Snowflake cost audit (E11.3 AC).
"""

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils"))
from snowflake_loader import get_snowflake_connection  # noqa: E402


_CREDITS_PER_HOUR = {
    "X-Small": 1,
    "Small":   2,
    "Medium":  4,
    "Large":   8,
    "X-Large": 16,
    "2X-Large": 32,
    "3X-Large": 64,
    "4X-Large": 128,
}

# ACCOUNT_USAGE.QUERY_HISTORY has a 45 min – 3 h lag and must be read from the
# SNOWFLAKE shared database, which is accessible to ACCOUNTADMIN. We use a
# fully-qualified reference; no USE statements (project convention).
_COST_SQL = """
SELECT
    COALESCE(NULLIF(QUERY_TAG, ''), '(untagged)') AS query_tag,
    WAREHOUSE_NAME,
    WAREHOUSE_SIZE,
    COUNT(*)                                            AS query_count,
    SUM(EXECUTION_TIME)                                AS total_exec_ms,
    ROUND(SUM(EXECUTION_TIME) / 3600000.0 *
        CASE WAREHOUSE_SIZE
            WHEN 'X-Small'  THEN 1
            WHEN 'Small'    THEN 2
            WHEN 'Medium'   THEN 4
            WHEN 'Large'    THEN 8
            WHEN 'X-Large'  THEN 16
            WHEN '2X-Large' THEN 32
            WHEN '3X-Large' THEN 64
            WHEN '4X-Large' THEN 128
            ELSE 1
        END, 4)                                         AS est_compute_credits,
    ROUND(SUM(CREDITS_USED_CLOUD_SERVICES), 6)         AS cloud_svc_credits,
    ROUND(SUM(EXECUTION_TIME) / 3600000.0 *
        CASE WAREHOUSE_SIZE
            WHEN 'X-Small'  THEN 1
            WHEN 'Small'    THEN 2
            WHEN 'Medium'   THEN 4
            WHEN 'Large'    THEN 8
            WHEN 'X-Large'  THEN 16
            WHEN '2X-Large' THEN 32
            WHEN '3X-Large' THEN 64
            WHEN '4X-Large' THEN 128
            ELSE 1
        END + SUM(CREDITS_USED_CLOUD_SERVICES), 4)     AS est_total_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD(day, %(days)s * -1, CURRENT_TIMESTAMP())
  AND EXECUTION_STATUS = 'SUCCESS'
  AND WAREHOUSE_NAME IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY est_total_credits DESC
"""


def _fmt_credits(v: float) -> str:
    return f"{v:.4f}"


def main():
    ap = argparse.ArgumentParser(description="Snowflake cost-by-job report (E11.3)")
    ap.add_argument("--days", type=int, default=7, help="Lookback window in days (default 7)")
    ap.add_argument("--raw", action="store_true", help="Print CSV instead of summary table")
    args = ap.parse_args()

    print(f"Querying ACCOUNT_USAGE.QUERY_HISTORY for the last {args.days} day(s) …", flush=True)

    # Connect using the shared helper — DAGSTER_JOB_NAME will tag this session too.
    os.environ.setdefault("DAGSTER_JOB_NAME", "snowflake_cost_by_job_report")
    conn = get_snowflake_connection(database="SNOWFLAKE", schema="ACCOUNT_USAGE")

    try:
        cur = conn.cursor()
        cur.execute(_COST_SQL, {"days": args.days})
        rows = cur.fetchall()
        cols = [d[0].lower() for d in cur.description]
        cur.close()
    finally:
        conn.close()

    if not rows:
        print("No rows returned — QUERY_TAG data may not yet be in ACCOUNT_USAGE (45 min – 3 h lag).")
        return

    data = [dict(zip(cols, r)) for r in rows]

    if args.raw:
        print(",".join(cols))
        for row in data:
            print(",".join(str(row[c]) for c in cols))
        return

    # Summary: aggregate across warehouse sizes per tag
    from collections import defaultdict
    agg: dict[str, dict] = defaultdict(lambda: {"query_count": 0, "est_total_credits": 0.0, "total_exec_ms": 0})
    for row in data:
        tag = row["query_tag"]
        agg[tag]["query_count"] += row["query_count"]
        agg[tag]["est_total_credits"] += row["est_total_credits"]
        agg[tag]["total_exec_ms"] += row["total_exec_ms"]

    ranked = sorted(agg.items(), key=lambda x: x[1]["est_total_credits"], reverse=True)
    total_credits = sum(v["est_total_credits"] for _, v in ranked)

    print(f"\n{'='*72}")
    print(f"  Snowflake cost by QUERY_TAG — last {args.days} day(s)")
    print(f"  Total estimated credits: {_fmt_credits(total_credits)}")
    print(f"{'='*72}")
    print(f"{'Rank':<5} {'QUERY_TAG':<40} {'Credits':>10} {'%':>7} {'Queries':>8}")
    print(f"{'-'*5} {'-'*40} {'-'*10} {'-'*7} {'-'*8}")
    for rank, (tag, vals) in enumerate(ranked, 1):
        pct = vals["est_total_credits"] / total_credits * 100 if total_credits else 0
        print(f"{rank:<5} {tag[:40]:<40} {_fmt_credits(vals['est_total_credits']):>10} {pct:>6.1f}% {vals['query_count']:>8}")

    print(f"\nNote: compute credit estimate = execution_time_ms / 3_600_000 × credits/hr")
    print("      for the warehouse size. ACCOUNT_USAGE has a 45 min – 3 h lag.")
    print(f"      Run with --raw for per-warehouse-size CSV output.")


if __name__ == "__main__":
    main()
