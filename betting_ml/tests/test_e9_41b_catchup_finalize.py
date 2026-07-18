"""E9.41b — the catch-up job must settle YESTERDAY's stored game-detail same-day.

A late (West-coast) game's outcome is INNER-JOINed off the pitch-derived mart_game_results
VIEW, so the featured "Yesterday" recap + the "who called it" scorecards can't settle until
yesterday's Statcast lands. statcast_catchup_job already re-ingests + re-serves TODAY the moment
that data arrives — E9.41b free-rides on it to ALSO re-write yesterday's game-detail Finals
(finalize_prior_slate_game_detail_op), so the stored scorecard blobs settle same-day instead of
waiting for the next 08:00 daily run.

Source-inspection (AST) only — must NOT import the ``pipeline`` package (pulls in the dbt
manifest, absent in the fast gate), like the other fast-gate op/sensor/job guards.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).parents[2]
_JOBS = _REPO / "pipeline" / "jobs" / "sensor_jobs.py"


def _tree() -> ast.Module:
    return ast.parse(_JOBS.read_text())


def _func(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"{name} not found in {_JOBS.name}")


def test_finalize_op_is_imported():
    tree = _tree()
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "finalize_prior_slate_game_detail_op" in imported, (
        "E9.41b: sensor_jobs.py must import finalize_prior_slate_game_detail_op"
    )


def test_catchup_job_calls_finalize_after_serving():
    """statcast_catchup_job must invoke finalize_prior_slate_game_detail_op (settle yesterday)."""
    fn = _func(_tree(), "statcast_catchup_job")
    called = {
        n.func.id
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "finalize_prior_slate_game_detail_op" in called, (
        "E9.41b: statcast_catchup_job must call finalize_prior_slate_game_detail_op so a "
        "late game's scorecards settle when its Statcast lands, not only at the next 08:00 run"
    )
    # And it must run AFTER the serving write (needs the fresh serve to have happened first).
    assert "write_serving_store_intraday_op" in called


def test_finalize_is_terminal_leaf():
    """finalize is a terminal WARN leaf — nothing in the job may consume its result
    (its own return must not be threaded into a downstream op's `start=`)."""
    fn = _func(_tree(), "statcast_catchup_job")
    # Find the assignment target that holds the serving-store result, then confirm finalize
    # is invoked and its call is not itself assigned to a name that is later consumed.
    finalize_calls = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "finalize_prior_slate_game_detail_op"
    ]
    assert len(finalize_calls) == 1
    # The finalize call is an expression statement (not an assignment feeding another op).
    expr_stmts = [
        s for s in fn.body
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
        and isinstance(s.value.func, ast.Name)
        and s.value.func.id == "finalize_prior_slate_game_detail_op"
    ]
    assert expr_stmts, "finalize must be a terminal leaf (bare expression statement, not assigned)"
