"""Guards the intraday odds SERVING refresh (2026-07-03).

Two fixes for the "served odds froze at ~7:30 AM" incident, both in pipeline/ops/intraday_ops.py:
  1. `write_book_odds_op` must run write_serving_store.py with BOTH --book-odds AND --game-detail —
     the "Line Movement Over Time" chart (`line_movement_series`) is produced ONLY by the game-detail
     write, so without --game-detail the served chart froze at the once/day morning serve.
  2. `_w6_lakehouse_intraday` must export the RAW S3 odds mirror UNGATED (before the
     W6_LAKEHOUSE_INTRADAY gate) so a flaky 30-min host-cron `exec` can't leave it stale, while the
     cutover-sensitive S3 MART rebuild stays gated.

Import-free AST/source check (mirrors test_e11_7_failure_contract's strategy) — importing the ops
module would trigger pipeline/__init__ → a hard SNOWFLAKE_ACCOUNT env dependency.
"""
import ast
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[2] / "pipeline" / "ops" / "intraday_ops.py").read_text()
_TREE = ast.parse(_SRC)


def _func_src(name: str) -> str:
    for node in ast.walk(_TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            seg = ast.get_source_segment(_SRC, node)
            assert seg is not None
            return seg
    raise AssertionError(f"function {name} not found in intraday_ops.py")


def test_book_odds_op_refreshes_game_detail():
    """The intraday odds rebuild must re-write the game-detail blob (where line_movement_series lives)."""
    src = _func_src("write_book_odds_op")
    assert "write_serving_store.py" in src
    assert "--book-odds" in src
    assert "--game-detail" in src, (
        "write_book_odds_op must pass --game-detail so line_movement_series refreshes intraday "
        "instead of freezing at the morning daily serve"
    )


def test_raw_odds_mirror_export_runs_ungated():
    """The raw S3 odds mirror must export BEFORE the W6 gate so a flaky host cron can't stale it."""
    src = _func_src("_w6_lakehouse_intraday")
    export_pos = src.find("export_odds_raw_to_s3.py")
    gate_pos = src.find("if not _W6_INTRADAY_ENABLED")
    assert export_pos != -1, "the raw mirror export must still be present"
    assert gate_pos != -1, "the W6 gate must still be present"
    assert export_pos < gate_pos, (
        "export_odds_raw_to_s3 (raw mirror) must run UNGATED, before the W6_LAKEHOUSE_INTRADAY gate"
    )


def test_mart_rebuild_stays_gated():
    """The cutover-sensitive S3 mart rebuild must remain behind W6_LAKEHOUSE_INTRADAY."""
    src = _func_src("_w6_lakehouse_intraday")
    gate_pos = src.find("if not _W6_INTRADAY_ENABLED")
    # Match the actual _run_script CALL (bracketed arg), not the docstring mention which precedes the gate.
    mart_pos = src.find('["--w6-odds-current"]')
    assert gate_pos != -1 and mart_pos != -1
    assert mart_pos > gate_pos, (
        "run_w1_lakehouse --w6-odds-current (rewrites the served mart parquet) must stay gated"
    )


def test_raw_mirror_export_not_duplicated_in_clv_branch():
    """The raw export was hoisted out of both scope branches — it must appear exactly once now."""
    src = _func_src("_w6_lakehouse_intraday")
    assert src.count("export_odds_raw_to_s3.py") == 1, (
        "the raw mirror export should be hoisted to a single ungated call, not repeated per scope"
    )
