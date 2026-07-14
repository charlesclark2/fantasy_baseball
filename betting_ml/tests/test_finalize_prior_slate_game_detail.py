"""Guard: the once-daily "finalize yesterday's game-detail" op stays correct.

THE BUG THIS CLOSES (found 2026-07-15): the model-vs-market "who called it" scorecards need
each game's cached game-detail blob to be status='Final' with box scores — but NOTHING re-wrote
a slate's game-detail blobs after its games ended. `write_book_odds_op` runs on the odds sensor,
whose window CLOSES at the last first pitch, so the last intraday game-detail write catches games
mid-'Live'; the daily `write_serving_store_op` only writes TODAY. So completed slates froze at
'Live'/'Preview', `build_scorecard_from_detail` returned None, and whole dates showed 0 scorecards
(24 dates were only ever healed by manual backfills).

`finalize_prior_slate_game_detail_op` makes that backfill a daily, post-game step. This test locks
in the properties that make it correct + safe, by AST-inspecting the source (NOT importing
`pipeline`, which needs Snowflake creds + the dbt manifest and would crash the fast gate):

  1. It exists and is wired into the daily job graph.
  2. It targets YESTERDAY (`_one_day_ago`), never today's in-progress slate.
  3. It runs `write_serving_store.py --game-detail --date <d>` and does NOT pass `--picks`
     (would needlessly re-write picks/today+ev) — game-detail alone re-resolves the slate.
  4. It honours the `--s3` cutover gate (`_w7b_s3_args`) like write_serving_store_op.
  5. WARN-tier: its body catches the exception and calls `context.log.warning` (a failure
     finalizing historical scorecards must never HALT the daily serving path).
"""
import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).parents[2]
_OPS = _REPO / "pipeline" / "ops" / "daily_ingestion_ops.py"
_JOB = _REPO / "pipeline" / "jobs" / "daily_ingestion_job.py"
_OP_NAME = "finalize_prior_slate_game_detail_op"


def _func(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"{name} not found in {path.name}")


@pytest.fixture(scope="module")
def op_fn() -> ast.FunctionDef:
    return _func(_OPS, _OP_NAME)


def _code_src(fn: ast.FunctionDef) -> str:
    """Source of the function body WITHOUT its docstring (so prose can't satisfy a match)."""
    body = list(fn.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(getattr(body[0], "value", None), ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return "\n".join(ast.unparse(n) for n in body)


def _run_script_call(fn: ast.FunctionDef) -> ast.Call:
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_run_script"):
            return node
    pytest.fail("no _run_script(...) call in the op")


@pytest.fixture(scope="module")
def op_src(op_fn) -> str:
    return _code_src(op_fn)


def test_op_exists_and_is_an_op(op_fn):
    deco = {ast.unparse(d).split("(")[0] for d in op_fn.decorator_list}
    assert "op" in deco, "must be a Dagster @op"


def test_targets_yesterday_not_today(op_src):
    assert "_one_day_ago" in op_src, "must finalize the PRIOR slate, not today's in-progress one"
    assert "_today()" not in op_src, "must not target today's in-progress slate"


def test_runs_game_detail_without_picks(op_fn, op_src):
    call = _run_script_call(op_fn)
    # _run_script(context, "<script>", [args...]) — script name is the 2nd positional.
    assert isinstance(call.args[1], ast.Constant) and call.args[1].value == "write_serving_store.py"
    call_src = ast.unparse(call)
    assert "--game-detail" in call_src
    assert "--date" in call_src
    # --picks / --book-odds would needlessly re-write picks/today+ev / dead book odds.
    assert "--picks" not in call_src, "game-detail alone re-resolves the slate; do not pass --picks"
    assert "--book-odds" not in call_src, "book odds are moot for a completed game"


def test_honours_s3_cutover_gate(op_src):
    assert "_w7b_s3_args" in op_src, "must use the same --s3 gate as write_serving_store_op"


def test_is_warn_tier(op_fn):
    """Body must catch and log.warning — WARN-but-continue, never HALT the daily path."""
    handlers = [n for n in ast.walk(op_fn) if isinstance(n, ast.ExceptHandler)]
    assert handlers, "must wrap the run in try/except (WARN-tier)"
    body_src = " ".join(ast.unparse(h) for h in handlers)
    assert "log.warning" in body_src, "except block must call context.log.warning (loud, non-fatal)"
    # And it must NOT re-raise (that would make it HALT-tier).
    assert not any(isinstance(n, ast.Raise) for h in handlers for n in ast.walk(h)), \
        "must not re-raise — a finalize failure cannot block the daily serving job"


def test_wired_into_daily_job(op_src):
    job_src = _JOB.read_text()
    assert _OP_NAME in job_src, "op must be invoked in daily_ingestion_job"
    # Imported too (dagster resolves the node def from the import).
    tree = ast.parse(job_src)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert _OP_NAME in imported, "op must be imported into the job module"
