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

⛔ DOES NOT PRINT THE VERDICT VIA THE AMBIENT CONSOLE LOG STREAM — on purpose. A first version did,
and on the box it silently dropped the op's own log lines (STEP_START/STEP_SUCCESS and the
"Monitor health OK" / "[ALERT] ..." message never echoed, though the job-level bookkeeping events
did) — reproducing this repo's own documented §10 hygiene rule #3: an exec-based console read of a
Dagster run is NOT restart-proof evidence; the only evidence that survives is the Postgres EVENT
LOG. So this reads the run's event log back from the instance (`instance.all_logs(run_id)`)
explicitly and prints from THAT, and asserts the op's step actually STARTED before trusting
anything about it — a run that reports `success` without its step ever starting would otherwise be
indistinguishable from a healthy check, which is the exact "everything looks fine" failure shape
this whole story exists to close (INC-16 / E11.23).

Usage (on the box):
    docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \\
      python scripts/check_monitors_healthy_locally.py

Exit 0 only if the op's step actually started AND ran to success. Exit 1 on anything else
(including a step that never started — see above) with a clear reason printed.
"""
from __future__ import annotations

from dagster import DagsterInstance, in_process_executor, job
from dagster._core.errors import DagsterHomeNotSetError

_OP_NAME = "check_monitors_healthy_op"


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


def _print_durable_event_log(instance, run_id: str) -> tuple[bool, bool]:
    """Reads the run's event log back from the instance (never the ambient console stream) and
    prints every message-bearing entry. Returns (step_started, step_succeeded) for the op — the
    caller uses these to decide whether the run is trustworthy evidence at all."""
    step_started = False
    step_succeeded = False
    print(f"\n--- durable event log for run {run_id} (read from the instance, not the console) ---")
    for record in instance.all_logs(run_id):
        event = record.dagster_event
        event_type = event.event_type_value if event is not None else None
        step_key = getattr(event, "step_key", None) if event is not None else None
        if step_key == _OP_NAME and event_type == "STEP_START":
            step_started = True
        if step_key == _OP_NAME and event_type == "STEP_SUCCESS":
            step_succeeded = True
        msg = record.user_message
        if msg:
            label = event_type or f"LOG(level={record.level})"
            print(f"[{label}] {msg}")
    return step_started, step_succeeded


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
    step_started, step_succeeded = _print_durable_event_log(instance, result.run_id)

    print(f"\nop step started: {step_started}   op step succeeded: {step_succeeded}   "
          f"run.success: {result.success}")

    if not step_started:
        print(f"FAIL: the {_OP_NAME} step never STARTED — `run.success` alone is meaningless "
              "here (the run can succeed vacuously with zero steps executed). This is NOT the "
              "same as the op running and reporting healthy; something upstream prevented it "
              "from executing at all.")
        return 1
    if not step_succeeded:
        print(f"FAIL: the {_OP_NAME} step started but did not reach STEP_SUCCESS — see the "
              "event log above for what happened.")
        return 1
    print("PASS: the op actually ran — read the verdict line above "
          '("Monitor health OK: ..." or "[ALERT] SILENTLY-NOT-RUNNING ALERT ...").')
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
