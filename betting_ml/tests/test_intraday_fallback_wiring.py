"""E11.27 — wiring guard for check_intraday_fallback_op.

Asserts (source/AST inspection only — must NOT import the `pipeline` package, which pulls the
dbt manifest + Snowflake resource init, absent in the fast CI job — see
test_spine_rebuild_ordering.py for the same convention):
  1. `check_intraday_fallback_op` is defined and runs scripts/check_intraday_fallback.py.
  2. It is wired into daily_ingestion_job.py, fanned out from predict_today_morning (s19),
     beside check_served_prediction_integrity_op — the story's "wire into the daily job beside
     the other check ops" requirement.
  3. It is ALERT-tier, ALWAYS: the `except` around the subprocess call never re-raises (a
     transient read failure must not HALT the daily job — E11.7 tier-map requirement).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).parents[2]
_OPS = _REPO / "pipeline" / "ops" / "daily_ingestion_ops.py"
_JOB = _REPO / "pipeline" / "jobs" / "daily_ingestion_job.py"


def _op_fn(name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(_OPS.read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"{name} not found in daily_ingestion_ops.py")


def test_op_runs_the_check_script():
    fn = _op_fn("check_intraday_fallback_op")
    src = ast.unparse(fn)
    assert "check_intraday_fallback.py" in src


def test_op_except_block_never_reraises():
    """ALERT-tier, ALWAYS: a transient S3/DuckDB read failure must not propagate and HALT the
    daily job. Every `except` handler in the op body must not contain a bare `raise`."""
    fn = _op_fn("check_intraday_fallback_op")
    for node in ast.walk(fn):
        if isinstance(node, ast.ExceptHandler):
            for stmt in ast.walk(node):
                assert not isinstance(stmt, ast.Raise), (
                    "check_intraday_fallback_op must never re-raise — it is ALERT-tier, ALWAYS "
                    "(no --strict escalation exists, per the E11.7 tier map)"
                )


def test_op_has_no_strict_env_escalation():
    """Unlike check_served_prediction_integrity_op (which supports SERVED_INTEGRITY_STRICT),
    this monitor has NO strict/HALT escalation path at all — it must stay advisory forever."""
    fn = _op_fn("check_intraday_fallback_op")
    src = ast.unparse(fn)
    assert "STRICT" not in src
    assert "raise" not in src


def test_wired_into_daily_job_beside_the_integrity_check():
    job_src = _JOB.read_text()
    assert "check_intraday_fallback_op(start=s19)" in job_src
    # Must run alongside (fanned out from the same predict step as) the sibling integrity gate.
    integrity_idx = job_src.index("check_served_prediction_integrity_op(start=s19)")
    fallback_idx = job_src.index("check_intraday_fallback_op(start=s19)")
    assert fallback_idx > integrity_idx, (
        "check_intraday_fallback_op should be wired as a sibling immediately after "
        "check_served_prediction_integrity_op, per the story's 'add as a sibling' instruction"
    )


def test_op_is_imported_in_the_job_module():
    job_src = _JOB.read_text()
    assert "check_intraday_fallback_op," in job_src or "check_intraday_fallback_op\n" in job_src
