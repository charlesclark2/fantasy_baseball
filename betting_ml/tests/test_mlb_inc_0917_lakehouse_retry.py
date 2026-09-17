"""MLB-INC-0917 — the HALT-tier lakehouse ops carry ONE bounded retry, loudly.

On 2026-09-16 a transient S3 403 (RequestTimeTooSkewed) in `lakehouse_w3_marts_op` skipped the whole
rest of `daily_ingestion_job` — the only writer of stg_oddsapi_odds and the 09-16 morning serving
tier with it. See betting_ml/monitoring/lakehouse_retry.py.

Fast-gate safe: the op module is inspected by AST (never imported — `pipeline` reads the dbt
manifest at import, E11.23); the behavioural half imports only `dagster` and `betting_ml`.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from betting_ml.monitoring import lakehouse_retry as lr

REPO = Path(__file__).resolve().parents[2]
OPS_FILE = REPO / "pipeline" / "ops" / "daily_ingestion_ops.py"
DAGSTER_YAML = REPO / "services" / "dagster" / "dagster.yaml"


def _tree() -> ast.Module:
    return ast.parse(OPS_FILE.read_text())


def _op_decorator(fn: ast.FunctionDef) -> ast.Call | None:
    for d in fn.decorator_list:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "op":
            return d
    return None


def _lakehouse_ops() -> dict[str, ast.FunctionDef]:
    out = {}
    for node in _tree().body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("lakehouse_") and _op_decorator(node):
            out[node.name] = node
    return out


def _kw(call: ast.Call, name: str):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


# ── the registry is exhaustive ───────────────────────────────────────────────────────────────
def test_every_lakehouse_op_is_classified_exactly_once():
    ops = set(_lakehouse_ops())
    retried, not_retried = set(lr.RETRIED_OPS), set(lr.NOT_RETRIED_OPS)
    assert len(ops) >= 12, f"found only {len(ops)} lakehouse ops — the AST scan is not seeing the file"
    assert not (retried & not_retried), retried & not_retried
    assert ops == retried | not_retried, (
        f"unclassified: {sorted(ops - retried - not_retried)}; "
        f"stale registry entries: {sorted((retried | not_retried) - ops)}"
    )
    assert len(lr.RETRIED_OPS) == len(retried), "duplicate in RETRIED_OPS"


def test_every_exclusion_states_its_reason():
    for name, why in lr.NOT_RETRIED_OPS.items():
        assert len(why.strip()) > 20, f"{name} is excluded without a stated reason"


# ── the decorators match the registry ────────────────────────────────────────────────────────
@pytest.mark.parametrize("name", lr.RETRIED_OPS)
def test_retried_op_carries_the_shared_policy(name):
    kw = _kw(_op_decorator(_lakehouse_ops()[name]), "retry_policy")
    assert isinstance(kw, ast.Name) and kw.id == "_LAKEHOUSE_RETRY", (
        f"{name} must be decorated with retry_policy=_LAKEHOUSE_RETRY"
    )


@pytest.mark.parametrize("name", sorted(lr.NOT_RETRIED_OPS))
def test_excluded_op_carries_no_policy(name):
    assert _kw(_op_decorator(_lakehouse_ops()[name]), "retry_policy") is None


def test_the_shared_policy_is_built_from_the_registered_constants():
    for node in _tree().body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_LAKEHOUSE_RETRY" for t in node.targets
        ):
            call = node.value
            assert isinstance(call, ast.Call) and getattr(call.func, "id", None) == "RetryPolicy"
            got = {k.arg: ast.unparse(k.value) for k in call.keywords}
            assert got == {
                "max_retries": "lakehouse_retry.MAX_RETRIES",
                "delay": "lakehouse_retry.DELAY_SECONDS",
            }, got
            return
    pytest.fail("_LAKEHOUSE_RETRY is not assigned in daily_ingestion_ops.py")


@pytest.mark.parametrize("name", lr.RETRIED_OPS)
def test_retried_op_notes_the_attempt_first_under_its_own_name(name):
    first = _lakehouse_ops()[name].body[0]
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call), (
        f"{name}: the first statement must be the note_retry_attempt call"
    )
    call = first.value
    assert ast.unparse(call.func) == "lakehouse_retry.note_retry_attempt", ast.unparse(call.func)
    assert len(call.args) == 2 and isinstance(call.args[1], ast.Constant)
    # A copy-pasted name would page the wrong op on every retry.
    assert call.args[1].value == name, f"{name} notes itself as {call.args[1].value!r}"


# ── the bound ────────────────────────────────────────────────────────────────────────────────
def test_policy_is_bounded():
    assert lr.MAX_RETRIES == 1, "one extra attempt; more only lengthens a run that will fail anyway"
    assert 30 <= lr.DELAY_SECONDS <= 300


def _run_monitoring_cap() -> int:
    m = re.search(r"run_monitoring:\s*\n(?:\s+.*\n)*?\s+max_runtime_seconds:\s*(\d+)", DAGSTER_YAML.read_text())
    assert m, "run_monitoring.max_runtime_seconds not found in dagster.yaml"
    return int(m.group(1))


def _script_caps(fn: ast.FunctionDef) -> list[int]:
    caps = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_run_script":
            t = _kw(node, "timeout")
            if isinstance(t, ast.Constant):
                caps.append(int(t.value))
    return caps


def test_a_single_retried_op_cannot_outlive_the_run_cap():
    cap = _run_monitoring_cap()
    ops = _lakehouse_ops()
    capped = {n: _script_caps(ops[n]) for n in lr.RETRIED_OPS}
    capped = {n: c for n, c in capped.items() if c}
    # Non-vacuity: the W1/W2/W3/W3pre/W6 ops all carry a wall-clock cap today.
    assert len(capped) >= 5, capped
    for name, caps in capped.items():
        worst = sum(caps) * (1 + lr.MAX_RETRIES) + lr.DELAY_SECONDS * lr.MAX_RETRIES
        assert worst < cap, f"{name}: worst case {worst}s ≥ run_monitoring cap {cap}s"


# ── the retry is loud ────────────────────────────────────────────────────────────────────────
class _Log:
    def __init__(self):
        self.warnings: list[str] = []

    def warning(self, msg):
        self.warnings.append(msg)


class _Ctx:
    def __init__(self, retry_number):
        self.retry_number = retry_number
        self.run_id = "run-abc"
        self.log = _Log()


def test_first_attempt_is_silent():
    sent = []
    ctx = _Ctx(0)
    assert lr.note_retry_attempt(ctx, "lakehouse_w3_marts_op", sender=lambda *a, **k: sent.append(k)) is False
    assert sent == [] and ctx.log.warnings == []


def test_a_retry_logs_a_metric_and_pages_warn_under_its_own_key():
    sent = []
    ctx = _Ctx(1)
    assert lr.note_retry_attempt(
        ctx, "lakehouse_w3_marts_op", sender=lambda *a, **k: sent.append((a, k))
    ) is True
    assert any("[METRIC] lakehouse_op_retry=lakehouse_w3_marts_op attempt=1" in w for w in ctx.log.warnings)
    assert len(sent) == 1
    args, kwargs = sent[0]
    assert kwargs["severity"] == "WARN"
    assert kwargs["dedup_key"] == "lakehouse_op_retry:lakehouse_w3_marts_op"
    assert "lakehouse_w3_marts_op" in args[0] and "run-abc" in args[1]


def test_a_failed_page_never_fails_the_rebuild():
    def boom(*a, **k):
        raise RuntimeError("SNS down")

    ctx = _Ctx(1)
    assert lr.note_retry_attempt(ctx, "lakehouse_w6_odds_marts_op", sender=boom) is True
    assert any("retry page failed" in w for w in ctx.log.warnings)


# ── the executor the daily job uses actually honours the policy ──────────────────────────────
def _run_toy(fail_times: int):
    from dagster import (
        HookContext, In, Nothing, Out, RetryPolicy, failure_hook, in_process_executor, job, op,
    )

    state = {"calls": 0, "hook": 0, "downstream": 0}

    @failure_hook
    def on_fail(_: HookContext):
        state["hook"] += 1

    @op(out=Out(Nothing), retry_policy=RetryPolicy(max_retries=lr.MAX_RETRIES, delay=0))
    def lakehouse_like(context):
        state["calls"] += 1
        if state["calls"] <= fail_times:
            raise Exception("HTTP 403 RequestTimeTooSkewed")

    @op(ins={"start": In(Nothing)})
    def downstream(_):
        state["downstream"] += 1

    # Same executor + hook arrangement as daily_ingestion_job.
    @job(executor_def=in_process_executor, hooks={on_fail})
    def toy():
        downstream(start=lakehouse_like())

    result = toy.execute_in_process(raise_on_error=False)
    events = [e.event_type_value for e in result.all_events if e.step_key == "lakehouse_like"]
    return result.success, state, events


def test_a_transient_failure_recovers_the_rest_of_the_job_without_a_failure_event():
    ok, state, events = _run_toy(fail_times=1)
    assert ok
    assert state == {"calls": 2, "hook": 0, "downstream": 1}
    assert "STEP_UP_FOR_RETRY" in events and "STEP_FAILURE" not in events


def test_a_persistent_failure_still_fails_after_exactly_one_retry():
    ok, state, events = _run_toy(fail_times=99)
    assert not ok
    assert state["calls"] == 1 + lr.MAX_RETRIES
    assert state["downstream"] == 0 and state["hook"] == 1
    assert events.count("STEP_FAILURE") == 1
