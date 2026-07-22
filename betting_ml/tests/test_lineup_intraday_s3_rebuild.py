"""test_lineup_intraday_s3_rebuild.py — guards lineup_intraday_s3_feature_rebuild,
the fix for the 824819 post-lineup restart loop.

Post-W8b-cutover the served lineup/matchup/aggregator features are a COPY of a
daily-frozen S3 parquet; lineup_dbt_feature_rebuild only re-copies the ext table, so an
intraday lineup confirmation never reached the post_lineup re-score and the game looped
forever. The new op regenerates the S3 chain (SCD-2 write → precursor mirror → --w8b
build → ext refresh) before the copy. These tests lock its contracts:
  1. GATED default-OFF — an early `if not _intraday_s3_rebuild_on(): return`, and the
     helper reads the dedicated LINEUP_INTRADAY_S3_REBUILD env var.
  2. Correct chain + args when enabled — the daily mirror order, scoped to the lineup
     precursor, and it actually regenerates the parquet (--w8b-only) + refreshes the ext.
  3. MIRROR-tier ALERT-continue — the chain is wrapped in try/except that logs a WARNING
     and does NOT re-raise (a build failure must never block the whole slate's re-score).
  4. WIRED between the staging rebuild and the feature copy in lineup_monitor_job.

AST/source inspection only — like the other fast-gate op guards (test_e11_11_op_diet.py,
test_e11_7_failure_contract.py), it must NOT import the `pipeline` package: that pulls in
pipeline.assets → the dbt manifest, which is absent in the fast CI job.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).parents[2]
_SENSOR_OPS = _REPO / "pipeline" / "ops" / "sensor_ops.py"
_SENSOR_JOBS = _REPO / "pipeline" / "jobs" / "sensor_jobs.py"

_OP = "lineup_intraday_s3_feature_rebuild"


def _func(path: Path, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"{name} not found in {path.name}")


def _steps(fn: ast.FunctionDef) -> list[tuple[str, list[str]]]:
    """Extract the `steps` list-of-(script, args) from the op. args entries that are not
    string literals (e.g. the _today() call) are rendered as '<expr>' so the order/shape
    can be asserted without evaluating."""
    for node in ast.walk(fn):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name, value = node.target.id, node.value
        elif isinstance(node, ast.Assign) and node.targets and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
        else:
            continue
        if name != "steps" or not isinstance(value, ast.List):
            continue
        out: list[tuple[str, list[str]]] = []
        for elt in value.elts:  # each elt is (script_literal, [args...])
            script = elt.elts[0].value
            args = [a.value if isinstance(a, ast.Constant) else "<expr>" for a in elt.elts[1].elts]
            out.append((script, args))
        return out
    pytest.fail("no `steps` list found in the op body")


def test_gated_default_off():
    body = ast.unparse(_func(_SENSOR_OPS, _OP))
    # the op must guard on the flag helper and return early when it is off
    assert "if not _intraday_s3_rebuild_on():" in body, "op must early-return when the flag is off"
    # the helper must read the DEDICATED flag (not, e.g., the always-on W9_LAKEHOUSE_S3 mirror flag)
    helper = ast.unparse(_func(_SENSOR_OPS, "_intraday_s3_rebuild_on"))
    assert "LINEUP_INTRADAY_S3_REBUILD" in helper


def test_regenerates_s3_chain_in_daily_order():
    fn = _func(_SENSOR_OPS, _OP)
    steps = _steps(fn)
    assert [s[0] for s in steps] == [
        "backfill_lineup_state_scd2.py",     # SCD-2 ← fresh staging (else intraday change is invisible)
        "export_w8b_precursors_to_s3.py",    # mirror the SCD-2 lineup state → S3
        "run_w1_lakehouse.py",               # (2026-07-22) --game-spine-only: pick up a same-day reschedule
        "run_w1_lakehouse.py",               # (2026-07-22) --eb-batter-only: fresh lineup-block EB posteriors
        "run_w1_lakehouse.py",               # rebuild the W8b feature/matchup/aggregator parquet
        "refresh_w1_external_tables.py",     # point lakehouse_ext at the new parquet
    ], "the S3-regeneration chain must run in the daily mirror order, before the feature copy"

    # Three run_w1_lakehouse.py steps now: the cheap precursor refreshes (--game-spine-only,
    # --eb-batter-only) MUST both precede --w8b-only, which reads the spine + eb as precursors.
    rw_args = [args for script, args in steps if script == "run_w1_lakehouse.py"]
    assert rw_args == [["--game-spine-only"], ["--eb-batter-only"], ["--w8b-only"]], (
        "spine + eb-batter refreshes must run before the --w8b-only aggregator rebuild"
    )
    by = dict(steps)
    assert by["refresh_w1_external_tables.py"] == ["--w8b"]      # and refresh the ext table
    # intraday-light: only the lineup_state precursor is re-mirrored (the rest are reused)
    assert by["export_w8b_precursors_to_s3.py"] == ["--table", "feature_pregame_lineup_state"]
    # SCD-2 write is date-scoped (not a full-history backfill on every sensor tick)
    assert by["backfill_lineup_state_scd2.py"][0] == "--since"

    # the op must actually iterate the steps through _run_script
    body = ast.unparse(fn)
    assert "for script, args in steps" in body and "_run_script(" in body


def test_mirror_tier_swallows_failure_and_never_raises():
    fn = _func(_SENSOR_OPS, _OP)
    handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
    assert handlers, "op must wrap the chain in try/except (mirror-tier ALERT-continue)"
    for h in handlers:
        assert "log.warning" in ast.unparse(h), "except must log a WARNING (failure contract)"
        assert not any(isinstance(n, ast.Raise) for n in ast.walk(h)), (
            "except must NOT re-raise — a rebuild failure must never block the whole slate's "
            "post_lineup re-score (predict runs on the last-good S3 features; next tick retries)"
        )


def test_mirror_tier_failure_pages_via_send_alert():
    """INC-32: 'works manually but fails silently in organic runs' — the mirror-tier except must
    now PAGE (SNS send_alert) in addition to the WARNING, so an organic-run failure is visible
    instead of dying in op logs while post_lineup coverage silently degrades (7/17: 0.833)."""
    fn = _func(_SENSOR_OPS, _OP)
    handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
    # the OUTER mirror-tier handler (wrapping the steps loop) must call send_alert
    outer = max(handlers, key=lambda h: len(ast.unparse(h)))
    body = ast.unparse(outer)
    assert "send_alert(" in body, "mirror-tier except must page via send_alert (INC-32)"
    assert "CRITICAL" in body, "the page must be severity=CRITICAL"
    # and it must record WHICH step failed so the organic-vs-manual difference is diagnosable
    assert "failed_step" in ast.unparse(fn), "must capture the failing step for the alert"


def test_wired_between_staging_and_feature_copy():
    src = _SENSOR_JOBS.read_text()
    # consumes the staging rebuild (s2) and feeds the feature copy (s2b) — order is the invariant
    assert f"{_OP}(start=s2)" in src, "new op must run AFTER lineup_dbt_staging_rebuild (needs fresh staging)"
    assert "lineup_dbt_feature_rebuild(start=s2b)" in src, "feature copy must run AFTER the S3 regen"
