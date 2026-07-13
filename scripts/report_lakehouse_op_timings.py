#!/usr/bin/env python3
"""
scripts/report_lakehouse_op_timings.py   (E11.20 — the AC-B measurement instrument)

Read-only: pulls per-op step durations for recent `daily_ingestion_job` runs straight
from the Dagster run storage (the box's dedicated Postgres, via DagsterInstance.get()),
so the AC-B BEFORE→AFTER table is one copy-paste per day instead of hand-reading Dagit.

The E11.20 decomposition exists precisely so these per-op durations ARE the timing
attribution (the absorbed E11.21 perf audit): under mirror the `lakehouse_w1_pitch_marts_op`
row is the full-history rebuild (BEFORE); under cutover it should collapse to
O(current-season) (AFTER). Run it on a few mirror days and again after the flip.

Run WHERE the Dagster storage env lives — the BOX codeloc container:
  docker compose -f ~/app/services/dagster/aws/docker-compose.yml exec -T \
    dagster-codeloc python -u scripts/report_lakehouse_op_timings.py [--runs 14] [--all-ops]

Output: one table per run (newest first) with the lakehouse_* ops (+ total job duration),
then a paste-ready markdown summary table (runs × ops) for docs/e11_20_delta_rollout.md.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

JOB_NAME = "daily_ingestion_job"
# Anchor (non-lakehouse) ops worth a row for context in the AC-B narrative.
CONTEXT_OPS = ("ingest_statcast_to_s3_op", "dbt_daily_build", "predict_today_morning")


def _fmt_secs(s: float | None) -> str:
    if s is None:
        return "—"
    if s < 60:
        return f"{s:.0f}s"
    return f"{int(s // 60)}m{int(s % 60):02d}s"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=14, help="how many recent runs to report")
    ap.add_argument("--all-ops", action="store_true",
                    help="every op, not just lakehouse_* + context anchors")
    args = ap.parse_args()

    from dagster import DagsterInstance
    from dagster._core.storage.dagster_run import RunsFilter

    instance = DagsterInstance.get()
    records = instance.get_run_records(
        filters=RunsFilter(job_name=JOB_NAME), limit=args.runs)
    if not records:
        print(f"No runs found for job {JOB_NAME!r} — wrong container/env?", file=sys.stderr)
        return 1

    per_run: list[dict] = []  # newest first, as returned
    op_order: list[str] = []
    for rec in records:
        run = rec.dagster_run
        started = rec.start_time
        day = (datetime.fromtimestamp(started, tz=timezone.utc).date().isoformat()
               if started else "?")
        total = (rec.end_time - rec.start_time
                 if rec.start_time and rec.end_time else None)
        steps: dict[str, float | None] = {}
        for st in instance.get_run_step_stats(run.run_id):
            key = st.step_key
            keep = (args.all_ops or key.startswith("lakehouse_") or key in CONTEXT_OPS)
            if not keep:
                continue
            dur = (st.end_time - st.start_time
                   if st.start_time and st.end_time else None)
            steps[key] = dur
            if key not in op_order:
                op_order.append(key)
        per_run.append({"day": day, "run_id": run.run_id[:8],
                        "status": run.status.value, "total": total, "steps": steps})

        print(f"\n═ {day}  run {run.run_id[:8]}  {run.status.value}"
              f"  total={_fmt_secs(total)}")
        for key in sorted(steps, key=lambda k: -(steps[k] or 0)):
            print(f"  {_fmt_secs(steps[key]):>8}  {key}")

    # Paste-ready markdown: ops as rows, runs as columns (newest LAST so time reads L→R)
    cols = list(reversed(per_run))
    print("\n\n── AC-B markdown (paste into docs/e11_20_delta_rollout.md) ──\n")
    print("| op | " + " | ".join(f"{r['day']} ({r['status'][:4]})" for r in cols) + " |")
    print("|---|" + "---|" * len(cols))
    for key in sorted(op_order):
        cells = " | ".join(_fmt_secs(r["steps"].get(key)) for r in cols)
        print(f"| `{key}` | {cells} |")
    print("| **total job** | " + " | ".join(_fmt_secs(r["total"]) for r in cols) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
