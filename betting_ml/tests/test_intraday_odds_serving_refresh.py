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


def test_raw_odds_mirror_export_is_retired():
    """E11.20 phase-2b (2026-07-27) — INVERTED from "must run ungated" to "must be gone".

    The old invariant existed because `lakehouse_raw/mlb_odds_raw` was mirrored FROM Snowflake and
    a flaky 30-min host cron could stale it. That premise died on 2026-07-05 when odds capture went
    S3-NATIVE and the Snowflake write was dropped: `oddsapi.mlb_odds_raw` has been FROZEN at
    ingestion_ts 2026-07-05T23:00:14 since, so `--since <today>` selected ZERO rows and the export
    wrote nothing. It was a pure COMPUTE_WH wake, ~10-14 per game-day, and one of the wakes that
    SURVIVED the W6 flip (W6 retired the two mart legs, not this bridge). The host cron was retired
    at the same time (capture.crontab line 35 commented out); this op call was simply missed.
    """
    src = _func_src("_w6_lakehouse_intraday")
    live = [ln for ln in src.splitlines()
            if "_run_script(" in ln and "export_odds_raw_to_s3.py" in ln]
    assert not live, (
        "the mlb_odds_raw export bridge must stay RETIRED — its Snowflake source is frozen, so it "
        "writes nothing and only wakes the warehouse. Found: %r" % live
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


def test_clv_branch_keeps_its_own_predictions_mirror():
    """The CLV branch's daily_model_predictions mirror is a DIFFERENT export (export_w6_raw_to_s3)
    and must survive the mlb_odds_raw retirement — only the frozen-source odds bridge goes."""
    src = _func_src("_w6_lakehouse_intraday")
    assert "export_w6_raw_to_s3.py" in src, (
        "the CLV branch still needs its daily_model_predictions mirror; the phase-2b retirement "
        "targets only the frozen mlb_odds_raw bridge"
    )
