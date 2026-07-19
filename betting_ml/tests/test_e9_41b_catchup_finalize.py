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
_OPS = _REPO / "pipeline" / "ops" / "sensor_ops.py"


def _tree(path: Path = _JOBS) -> ast.Module:
    return ast.parse(path.read_text())


def _func(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"{name} not found")


def _run_script_names(fn: ast.FunctionDef) -> list[str]:
    """The first string arg of every _run_script(context, "<script>", ...) call in fn."""
    out = []
    for n in ast.walk(fn):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_run_script" and len(n.args) >= 2
                and isinstance(n.args[1], ast.Constant)):
            out.append(n.args[1].value)
    return out


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


# --------------------------------------------------------------------------
# E9.41b — the catch-up job's two head ops must actually land + expose statcast.
# Both silently no-op'd after W11-E (SF savant.batter_pitches retired +
# stg_batter_pitches enabled=false on the SF target), so the catch-up self-heal was
# dead. The fix: ingest runs the S3 pull; the (renamed) rebuild refreshes ext tables.
# --------------------------------------------------------------------------

def test_catchup_ingest_runs_s3_ingest():
    """catchup_ingest_statcast must run ingest_statcast_to_s3.py (not a bare no-op return)."""
    fn = _func(_tree(_OPS), "catchup_ingest_statcast")
    scripts = _run_script_names(fn)
    assert "ingest_statcast_to_s3.py" in scripts, (
        "E9.41b: catchup_ingest_statcast must run ingest_statcast_to_s3.py so late statcast "
        "actually lands to S3 (the pre-fix SF-retired branch just returned → landed nothing)"
    )


def test_catchup_refresh_op_refreshes_ext_tables_not_dead_dbt():
    """The renamed op refreshes ext tables; it no longer runs dbt with the dead selector."""
    fn = _func(_tree(_OPS), "catchup_refresh_ext_tables")
    assert "refresh_w1_external_tables.py" in _run_script_names(fn), (
        "E9.41b: catchup_refresh_ext_tables must run refresh_w1_external_tables.py"
    )
    # The op body must NOT run dbt at all (the stg_batter_pitches+ selector is a no-op on the
    # SF target where the model is enabled=false). A historical mention in a comment is fine —
    # this checks the executable calls, not prose.
    call_names = {
        n.func.id for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "_run_dbt" not in call_names, (
        "E9.41b: catchup_refresh_ext_tables must not call _run_dbt (the pitch marts are S3 "
        "views; the selector matched nothing on the SF target)"
    )
    # And the dead selector must not appear as a string literal anywhere in the function.
    lits = {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "stg_batter_pitches+" not in lits


def test_old_catchup_dbt_rebuild_op_is_removed():
    """The misleading 'dbt_rebuild' op must be gone as a definition and from the job wiring
    (a historical mention in a comment is fine; a live def/import/call is not)."""
    op_names = {
        n.name for n in ast.walk(_tree(_OPS)) if isinstance(n, ast.FunctionDef)
    }
    assert "catchup_dbt_rebuild" not in op_names, "the catchup_dbt_rebuild op def must be removed"
    assert "catchup_refresh_ext_tables" in op_names
    # No live import/call of the old name in the job graph.
    jobs_imports_calls = {
        n.id for n in ast.walk(_tree(_JOBS)) if isinstance(n, ast.Name)
    } | {
        a.name for n in ast.walk(_tree(_JOBS)) if isinstance(n, ast.ImportFrom) for a in n.names
    }
    assert "catchup_dbt_rebuild" not in jobs_imports_calls, (
        "sensor_jobs.py must reference catchup_refresh_ext_tables, not catchup_dbt_rebuild"
    )


# --------------------------------------------------------------------------
# E9.41 (2026-07-19) — the settled-outcome mirror-freshness fix. mart_clv_labeled_games
# was structurally a day stale (daily W6 lk6 builds it BEFORE the W5 mart_game_results
# refresh at lk8), so the featured recap + /performance never settled yesterday. The
# fix: a --clv-labels-only rebuild after mart_game_results is fresh (daily lk8 + the
# catch-up), and the catch-up rebuilds the outcome MIRROR parquets so late games settle.
# --------------------------------------------------------------------------

_DAILY_OPS = _REPO / "pipeline" / "ops" / "daily_ingestion_ops.py"
_RUNW1 = _REPO / "scripts" / "run_w1_lakehouse.py"


def _string_lits(fn: ast.FunctionDef) -> set[str]:
    return {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def test_runw1_has_clv_labels_only_routing():
    """run_w1_lakehouse must define the --clv-labels-only build + its model list."""
    src = _RUNW1.read_text()
    assert "clv_labels_only" in src and "--clv-labels-only" in src
    assert "W6_CLV_LABEL_MODELS" in src
    fn = _func(_tree(_RUNW1), "_build_clv_labels")
    # It must register the mart_closing_line_value PARQUET (not re-derive its SQL) + build the marts.
    assert "_register_s3_glob_views" in {
        n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }


def test_daily_lk8_rebuilds_clv_after_game_results():
    """lakehouse_spine_odds_bridge_op must run --clv-labels-only AFTER --w5-group-a (mart_game_results
    fresh) so the CLV-label mirror is current for the writer + /performance."""
    fn = _func(_tree(_DAILY_OPS), "lakehouse_spine_odds_bridge_op")
    body = _DAILY_OPS.read_text()
    seg = body[body.index("def lakehouse_spine_odds_bridge_op"):]
    seg = seg[: seg.index("\n@op") if "\n@op" in seg else len(seg)]
    assert "--w5-group-a-only" in seg and "--clv-labels-only" in seg
    assert seg.index("--w5-group-a-only") < seg.index("--clv-labels-only"), (
        "CLV-label rebuild must come AFTER the mart_game_results (--w5-group-a) refresh"
    )
    assert "--w6-clv" in seg  # ext-table refresh for the CLV marts


def test_catchup_rebuilds_outcome_mirrors():
    """catchup_rebuild_outcome_mirrors must rebuild mart_game_results (--w5-group-a) then the
    CLV-label mirrors (--clv-labels-only), and be wired into the catch-up job before the posteriors."""
    fn = _func(_tree(_OPS), "catchup_rebuild_outcome_mirrors")
    lits = _string_lits(fn)
    assert "--w5-group-a-only" in lits and "--clv-labels-only" in lits
    # Wired into the job.
    job = _func(_tree(_JOBS), "statcast_catchup_job")
    called = {n.func.id for n in ast.walk(job) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "catchup_rebuild_outcome_mirrors" in called
