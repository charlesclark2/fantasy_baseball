"""Regression — the daily lakehouse build must rebuild mart_game_spine (W5 Group A) BEFORE the
--w8a/--w8b feature build reads it.

Root cause (2026-07-02): the W8b cutover made mart_game_spine serving-critical (the --w8a/--w8b
feature build reads it as a precursor view, and the served feature_pregame_game_features is only as
fresh as the spine's scheduled-game universe). But --w5 wasn't in the daily build, so the spine froze
and the pregame feature store lost the current slate → predict_today silently degraded to the
intraday-assembly fallback. The fix wires a spine (W5 Group A) rebuild into run_w1_lakehouse_op BEFORE
--w8a/--w8b. This test locks that ordering so a future edit (the file is shared with the W11 sessions)
can't reintroduce the freeze.

AST/source inspection only — must NOT import the `pipeline` package (pulls the dbt manifest +
Snowflake resource init, absent in the fast CI job).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).parents[2]
_OPS = _REPO / "pipeline" / "ops" / "daily_ingestion_ops.py"


def _run_w1_lakehouse_op() -> ast.FunctionDef:
    for node in ast.walk(ast.parse(_OPS.read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == "run_w1_lakehouse_op":
            return node
    pytest.fail("run_w1_lakehouse_op not found")


def _run_w1_lakehouse_calls() -> list[tuple[int, str]]:
    """(lineno, joined-string-args) for every run_w1_lakehouse.py subprocess call in the op,
    in source order."""
    fn = _run_w1_lakehouse_op()
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
    calls = _run_w1_lakehouse_calls()
    spine = [c for c in calls if "--w5-group-a-only" in c[1]]
    assert spine, "run_w1_lakehouse_op must rebuild the spine (--w5-only --w5-group-a-only) daily"
    # the group-A modifier only takes effect alongside --w5-only
    assert all("--w5-only" in blob for _, blob in spine), "--w5-group-a-only requires --w5-only"


def test_spine_rebuild_precedes_the_w8a_and_w8b_feature_builds():
    calls = _run_w1_lakehouse_calls()
    def first_line(token: str) -> int:
        hits = [ln for ln, blob in calls if token in blob]
        assert hits, f"no run_w1_lakehouse.py call with {token}"
        return min(hits)
    spine_ln = first_line("--w5-group-a-only")
    assert spine_ln < first_line("--w8a-only"), "spine rebuild must precede --w8a-only"
    assert spine_ln < first_line("--w8b-only"), "spine rebuild must precede --w8b-only"
