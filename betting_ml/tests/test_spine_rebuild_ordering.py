"""Regression — the daily lakehouse build must rebuild mart_game_spine (W5 Group A) BEFORE the
--w8a/--w8b feature build reads it.

Root cause (2026-07-02): the W8b cutover made mart_game_spine serving-critical (the --w8a/--w8b
feature build reads it as a precursor view, and the served feature_pregame_game_features is only as
fresh as the spine's scheduled-game universe). But --w5 wasn't in the daily build, so the spine froze
and the pregame feature store lost the current slate → predict_today silently degraded to the
intraday-assembly fallback. The fix wired a spine (W5 Group A) rebuild BEFORE --w8a/--w8b.

E11.20 UPDATE: run_w1_lakehouse_op was DECOMPOSED into per-wave ops, so the protected ordering now
lives in TWO places this test locks: (a) the daily job graph wires lakehouse_spine_odds_bridge_op →
lakehouse_w8a_feature_layer_op → lakehouse_w8b_aggregator_op in that order, and (b) inside the ops,
the spine op carries the --w5-only --w5-group-a-only rebuild and the W8b op runs --w5b-only BEFORE
--w8b-only (W5b reads the eb_bullpen_team_posteriors parquet --w8a writes; the aggregator reads W5b).

AST/source inspection only — must NOT import the `pipeline` package (pulls the dbt manifest +
Snowflake resource init, absent in the fast CI job).
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


def _lakehouse_calls(fn: ast.FunctionDef) -> list[tuple[int, str]]:
    """(lineno, joined-string-args) for every run_w1_lakehouse.py subprocess call in the op,
    in source order."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        consts = [a.value for a in node.args if isinstance(a, ast.Constant)]
        list_consts = [e.value for a in node.args if isinstance(a, ast.List)
                       for e in a.elts if isinstance(e, ast.Constant)]
        blob = " ".join(str(x) for x in consts + list_consts)
        if "run_w1_lakehouse.py" in blob:
            out.append((node.lineno, blob))
    return sorted(out, key=lambda x: x[0])


def test_spine_group_a_rebuild_is_present():
    calls = _lakehouse_calls(_op_fn("lakehouse_spine_odds_bridge_op"))
    spine = [c for c in calls if "--w5-group-a-only" in c[1]]
    assert spine, "lakehouse_spine_odds_bridge_op must rebuild the spine (--w5-only --w5-group-a-only)"
    # the group-A modifier only takes effect alongside --w5-only
    assert all("--w5-only" in blob for _, blob in spine), "--w5-group-a-only requires --w5-only"


def test_spine_rebuild_precedes_the_w8a_and_w8b_feature_builds():
    # The ordering is now a JOB GRAPH invariant: spine op wired before the W8a op, which is
    # wired before the W8b op, inside daily_ingestion_job().
    body = _JOB.read_text()
    body = body[body.index("def daily_ingestion_job"):]
    i_spine = body.index("lakehouse_spine_odds_bridge_op(")
    i_w8a = body.index("lakehouse_w8a_feature_layer_op(")
    i_w8b = body.index("lakehouse_w8b_aggregator_op(")
    assert i_spine < i_w8a < i_w8b, (
        "daily job must wire spine → W8a → W8b (a frozen spine silently degrades "
        "predict_today to the intraday fallback)"
    )


def test_w5b_rebuild_runs_after_w8a_and_before_the_w8b_aggregator():
    # W5b reads the eb_bullpen_team_posteriors parquet --w8a writes, and the --w8b aggregator
    # reads W5b's park/defense/bullpen-effectiveness marts → --w5b-only lives INSIDE the W8b op
    # (which the job wires after the W8a op — asserted above), BEFORE its --w8b-only call.
    calls = _lakehouse_calls(_op_fn("lakehouse_w8b_aggregator_op"))
    w5b = [ln for ln, blob in calls if "--w5b-only" in blob]
    w8b = [ln for ln, blob in calls if "--w8b-only" in blob]
    assert w5b and w8b, "lakehouse_w8b_aggregator_op must run both --w5b-only and --w8b-only"
    assert min(w5b) < min(w8b), "--w5b-only must run BEFORE --w8b-only"
    # and the W8a build itself must NOT have moved into some later op
    assert any("--w8a-only" in blob
               for _, blob in _lakehouse_calls(_op_fn("lakehouse_w8a_feature_layer_op"))), \
        "lakehouse_w8a_feature_layer_op must run --w8a-only"
