"""NF-INFRA1 follow-up — coverage for the on-demand heartbeat runner.

The original version trusted the ambient console log stream to show the op's verdict. On the box
that stream silently dropped everything between RESOURCE_INIT_SUCCESS and the job-level "finished
steps" event — the op's own STEP_START/STEP_SUCCESS and its "Monitor health OK"/"[ALERT] ..."
message never echoed, even though the run reported `success: True`. This reproduces this repo's
own documented §10 hygiene rule #3 (BOX_OPERATIONS.md): an exec-based console read of a Dagster run
is NOT restart-proof evidence — only the Postgres event log is. `_print_durable_event_log` reads
that log back explicitly instead of trusting stdout, so these tests drive it directly against a
fake instance/event-log rather than a real Dagster run (keeps this fast-gate safe — no pipeline /
dbt-manifest import needed to test the log-reading logic itself).

`DagsterInstance.get()` needs `DAGSTER_HOME` — running the REAL op end-to-end is only meaningful ON
THE BOX (see the module docstring). Off-box (CI, the laptop) `main()` must fail with a clear
message, not a raw traceback or a silent success that would mislead an operator into thinking the
real state was checked.
"""
from __future__ import annotations

from types import SimpleNamespace

from pathlib import Path

import pytest

import check_monitors_healthy_locally as target

_MANIFEST = Path(__file__).resolve().parents[2] / "dbt" / "target" / "manifest.json"


def _record(event_type=None, step_key=None, msg="", level=10):
    event = None
    if event_type is not None:
        event = SimpleNamespace(event_type_value=event_type, step_key=step_key)
    return SimpleNamespace(dagster_event=event, user_message=msg, level=level)


class _FakeInstance:
    def __init__(self, records):
        self._records = records

    def all_logs(self, run_id):  # noqa: ARG002
        return self._records


def test_off_box_without_dagster_home_fails_clearly(monkeypatch, capsys):
    monkeypatch.delenv("DAGSTER_HOME", raising=False)
    rc = target.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "DAGSTER_HOME is not set" in out
    assert "docker compose" in out and "dagster-codeloc" in out


# ── the durable-event-log reader: the fix for the box's dropped console output ─────────────────
def test_step_started_and_succeeded_detected_from_a_healthy_run(capsys):
    records = [
        _record("PIPELINE_START", msg="Started execution of run"),
        _record("STEP_START", step_key=target._OP_NAME, msg="Started execution of step"),
        _record(msg="Monitor health OK: no critical sensor/schedule STOPPED.", level=20),
        _record("STEP_SUCCESS", step_key=target._OP_NAME, msg="Finished execution of step"),
        _record("PIPELINE_SUCCESS", msg="Finished execution of run"),
    ]
    started, succeeded = target._print_durable_event_log(_FakeInstance(records), "run-1")
    assert started is True
    assert succeeded is True
    out = capsys.readouterr().out
    assert "Monitor health OK" in out


def test_step_that_never_started_is_detected():
    """The exact box symptom: a run reporting success with NO evidence the op's step ever ran.
    Reproduced here directly (no real Dagster execution needed) — the fix must catch it."""
    records = [
        _record("PIPELINE_START", msg="Started execution of run"),
        _record("ENGINE_EVENT", msg="Executing steps in process"),
        _record("RESOURCE_INIT_STARTED", step_key=target._OP_NAME, msg="Starting init"),
        _record("RESOURCE_INIT_SUCCESS", step_key=target._OP_NAME, msg="Finished init"),
        # ⬅ no STEP_START, no op log message, no STEP_SUCCESS — exactly what the box showed
        _record("ENGINE_EVENT", msg="Finished steps in process"),
        _record("PIPELINE_SUCCESS", msg="Finished execution of run"),
    ]
    started, succeeded = target._print_durable_event_log(_FakeInstance(records), "run-2")
    assert started is False
    assert succeeded is False


def test_step_started_but_not_succeeded_is_distinguished():
    records = [
        _record("STEP_START", step_key=target._OP_NAME, msg="Started execution of step"),
        _record("STEP_FAILURE", step_key=target._OP_NAME, msg="Step failed"),
    ]
    started, succeeded = target._print_durable_event_log(_FakeInstance(records), "run-3")
    assert started is True
    assert succeeded is False


def test_a_step_start_for_a_DIFFERENT_step_does_not_count():
    """Only `check_monitors_healthy_op`'s own STEP_START/STEP_SUCCESS should count — a real job
    could carry other steps, and crediting the wrong one would be the exact false-positive this
    fix exists to prevent."""
    records = [
        _record("STEP_START", step_key="some_other_op", msg="Started execution of step"),
        _record("STEP_SUCCESS", step_key="some_other_op", msg="Finished execution of step"),
    ]
    started, succeeded = target._print_durable_event_log(_FakeInstance(records), "run-4")
    assert started is False
    assert succeeded is False


@pytest.mark.skipif(
    not _MANIFEST.exists(),
    reason="pipeline import requires dbt/target/manifest.json (absent in the fast gate); "
           "runs locally / on the box after a dbt compile.",
)
def test_the_wrapping_job_contains_the_real_op():
    """Not a stand-in — the same op object the daily job runs."""
    from pipeline.ops.daily_ingestion_ops import check_monitors_healthy_op

    standalone_job = target._build_standalone_job()
    node_names = {node.name for node in standalone_job.nodes}
    assert check_monitors_healthy_op.name in node_names
