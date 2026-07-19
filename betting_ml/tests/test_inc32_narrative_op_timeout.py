"""INC-32 run-stall (2026-07-19) — the predict→serve tail must not be held hostage by an
un-timed Cortex narrative call.

generate_pick_narratives_op is the ONLY op on the daily job's predict→serve dependency edge
(write_serving_store_op / write_api_cache_op wait on predict_done=this). It loops calling
Snowflake Cortex COMPLETE sequentially with no client-side timeout; on 7/19 a slow/hung Cortex
call stalled the serve ~2h20m. This guard locks in a finite subprocess wall-clock cap so the
soft-fail except turns an unbounded stall into a bounded degrade (the app renders SHAP drivers
when pick_narrative is NULL).

Source-inspection (AST) only — must NOT import the ``pipeline`` package (pulls in the dbt
manifest, absent in the fast gate), like the other fast-gate op/sensor guards.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).parents[2]
_OPS = _REPO / "pipeline" / "ops" / "daily_ingestion_ops.py"


def _func(path: Path, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"{name} not found in {path.name}")


def test_narrative_op_passes_finite_run_script_timeout():
    """generate_pick_narratives_op must call _run_script with a finite timeout= so a hung Cortex
    call can never stall the serve on the predict→serve edge (INC-32 run-stall)."""
    fn = _func(_OPS, "generate_pick_narratives_op")
    run_script_calls = [
        c for c in ast.walk(fn)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "_run_script"
    ]
    assert run_script_calls, "expected a _run_script call in generate_pick_narratives_op"
    for c in run_script_calls:
        tkw = next((kw for kw in c.keywords if kw.arg == "timeout"), None)
        assert tkw is not None, (
            "INC-32: generate_pick_narratives_op must pass timeout= to _run_script "
            "(un-timed Cortex loop stalled the predict→serve tail ~2h on 7/19)"
        )
        assert isinstance(tkw.value, ast.Constant) and isinstance(tkw.value.value, int), (
            "timeout must be a finite integer literal, not None"
        )


def test_narrative_op_is_soft_fail():
    """The op must swallow the exception (soft-fail) so a timeout kill degrades gracefully rather
    than failing the daily job — narrative text is cosmetic."""
    fn = _func(_OPS, "generate_pick_narratives_op")
    handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
    assert handlers, "generate_pick_narratives_op must wrap _run_script in try/except (soft-fail)"
    assert not any(
        isinstance(n, ast.Raise) for h in handlers for n in ast.walk(h)
    ), "the narrative op's except must NOT re-raise (serve must proceed on a Cortex timeout)"
