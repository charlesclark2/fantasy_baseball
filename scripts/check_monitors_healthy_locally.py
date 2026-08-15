"""NF-INFRA1 follow-up — run `check_monitors_healthy_op` on demand, against the REAL box instance.

Normally this op only runs inside a `daily_ingestion_job` fire. This lets an operator run it
standalone, ON THE BOX, without waiting for (or triggering) a full daily run.

`DagsterInstance.get()` resolves via the container's `DAGSTER_HOME=/app/services/dagster` to the
REAL production Postgres-backed instance — the SAME storage the daemon/webserver use — so
`context.instance.all_instigator_state(...)` reads the schedules' TRUE current on/off state, not a
synthetic stand-in. This is how you confirm `sports_nfl_board_publish_schedule` /
`sports_nfl_sleeper_injuries_schedule` (and everything else in `CRITICAL_SCHEDULES`) currently read
RUNNING and the required intraday flags are all set.

⚠️ THIS RUNS THE REAL OP, NOT A SMOKE (see scripts/smoke_test_monitor_health_alert.py for that
narrower, synthetic-only check). If it finds a REAL problem it sends a REAL (non-smoke) CRITICAL
page via `send_alert`, exactly as a live daily-job run would — that is the correct, intended
behavior here, not something to work around. Off the box (no Postgres schedule storage reachable)
`context.instance.all_instigator_state()` raises and the op logs "introspection unavailable" but
still succeeds (ALERT-tier: never HALTs) — so this is only meaningful ON the box.

Usage (on the box):
    docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \\
      python scripts/check_monitors_healthy_locally.py

Reads Dagster's own log output (printed directly by the run) for the verdict line — either
"Monitor health OK: ..." or a "[ALERT] SILENTLY-NOT-RUNNING ALERT (E11.23): ..." naming the
specific problems. Exit code mirrors the op's own success (ALERT-tier ops always succeed; a
non-zero exit here would mean something OUTSIDE the op's own contract broke).
"""
from __future__ import annotations

from dagster import DagsterInstance, in_process_executor, job
from dagster._core.errors import DagsterHomeNotSetError


def _build_standalone_job():
    """Imported LAZILY (not at module scope): `pipeline.ops.daily_ingestion_ops` pulls in
    `pipeline/__init__.py`, which reads the compiled dbt manifest — absent in the fast-test gate
    (E11.23). Deferring it here keeps this MODULE import-safe, so a fast-gate test can import this
    file without needing the manifest; only actually RUNNING the check (main(), on the box) does."""
    from pipeline.ops.daily_ingestion_ops import check_monitors_healthy_op

    @job(executor_def=in_process_executor)
    def _check_monitors_healthy_standalone_job():
        check_monitors_healthy_op()

    return _check_monitors_healthy_standalone_job


def main() -> int:
    try:
        instance = DagsterInstance.get()
    except DagsterHomeNotSetError:
        print("DAGSTER_HOME is not set — this script is only meaningful ON THE BOX (it needs the "
              "real production Postgres-backed instance to read the schedules' TRUE state). Run "
              "it via:\n  docker compose -f services/dagster/aws/docker-compose.yml exec -T "
              "dagster-codeloc python scripts/check_monitors_healthy_locally.py")
        return 1
    standalone_job = _build_standalone_job()
    result = standalone_job.execute_in_process(instance=instance)
    print(f"\nrun success: {result.success}  (see the log lines above for the verdict)")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
