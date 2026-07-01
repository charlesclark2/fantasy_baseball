"""INC-25 regression — lock the sub-model-signal DAG ordering in daily_ingestion_job.

The P0 (2026-07-01): after the W8a cutover the Snowflake consumer
`feature_pregame_sub_model_signals` reads an S3 parquet built from the W9 signal
stores. That parquet MUST be (re)built AFTER the day's generators write the stores
and AFTER export_w9_signals_to_s3_op mirrors them to S3 — otherwise the consumer
serves a slate-stale pivot and signal_freshness_check HALTs the whole daily job.

The required chain:
    all 8 generators
        → export_w9_signals_to_s3_op        (fan-in; SF stores → S3 parquet)
        → rebuild_sub_model_signals_consumer_op  (consumer parquet from fresh stores)
        → dbt_sub_model_signals_rebuild     (SF materialize)
        → signal_freshness_check            (HALT gate)

AST/source inspection only — like the other fast-gate op guards
(test_lineup_intraday_s3_rebuild.py, test_e11_7_failure_contract.py), it must NOT import
the `pipeline` package: that pulls in pipeline.assets → the dbt manifest, absent in the
fast CI job.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).parents[2]
_JOB = _REPO / "pipeline" / "jobs" / "daily_ingestion_job.py"

_GENERATORS = {
    "generate_run_env_signals_op",
    "generate_offense_signals_op",
    "generate_starter_signals_op",
    "generate_starter_ip_signals_op",
    "generate_bullpen_signals_op",
    "generate_matchup_signals_op",
    "generate_env_state_signals_op",
    "generate_defense_quality_signals_op",
}


def _job_fn() -> ast.FunctionDef:
    for node in ast.walk(ast.parse(_JOB.read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == "daily_ingestion_job":
            return node
    pytest.fail("daily_ingestion_job not found")


def _wiring() -> dict[str, dict]:
    """Map each `var = OpName(kw=argvar, ...)` assignment in the job body to
    {var: {"op": OpName, "args": {kw_or_index: source_var_name}}}. Positional/keyword
    args that are plain Names are recorded by their source variable; non-Name args are
    ignored (irrelevant to the dependency chain)."""
    out: dict[str, dict] = {}
    for stmt in _job_fn().body:
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Name)):
            continue
        call = stmt.value
        args: dict = {}
        for kw in call.keywords:
            if isinstance(kw.value, ast.Name):
                args[kw.arg] = kw.value.id
        for i, a in enumerate(call.args):
            if isinstance(a, ast.Name):
                args[i] = a.id
        out[stmt.targets[0].id] = {"op": call.func.id, "args": args}
    return out


def _var_for(wiring: dict, op_name: str) -> str:
    hits = [v for v, meta in wiring.items() if meta["op"] == op_name]
    assert len(hits) == 1, f"expected exactly one {op_name} assignment, got {hits}"
    return hits[0]


def test_export_w9_is_the_fan_in_of_all_eight_generators():
    w = _wiring()
    gen_vars = {v for v, meta in w.items() if meta["op"] in _GENERATORS}
    assert {w[v]["op"] for v in gen_vars} == _GENERATORS, "all 8 generators must be wired"
    export_args = set(w[_var_for(w, "export_w9_signals_to_s3_op")]["args"].values())
    assert export_args == gen_vars, "export_w9_signals_to_s3_op must fan in all 8 generator results"


def test_consumer_rebuild_runs_between_export_and_pivot_materialize():
    w = _wiring()
    export_var = _var_for(w, "export_w9_signals_to_s3_op")
    consumer_var = _var_for(w, "rebuild_sub_model_signals_consumer_op")
    rebuild_var = _var_for(w, "dbt_sub_model_signals_rebuild")
    # consumer parquet rebuild depends on the store export (fresh stores first)
    assert w[consumer_var]["args"].get("start") == export_var
    # the SF materialize depends on the fresh consumer parquet
    assert w[rebuild_var]["args"].get("start") == consumer_var


def test_freshness_gate_runs_after_the_materialize():
    w = _wiring()
    rebuild_var = _var_for(w, "dbt_sub_model_signals_rebuild")
    fresh_var = _var_for(w, "signal_freshness_check")
    assert w[fresh_var]["args"].get("start") == rebuild_var
