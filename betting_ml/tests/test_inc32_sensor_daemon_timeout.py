"""INC-32 — the sensor-daemon-block guard (fast-gate, source-inspection only).

7/17: sensor EVALUATIONS stopped ~21:30Z mid-slate → 7 of 15 games never got post_lineup. Root
cause: ``_evaluate_lineup_monitor`` ran ``lineup_monitor.py`` via ``subprocess.run`` with NO
timeout, so a wedged monitor (its state read is still Snowflake) blocked the Dagster sensor-daemon
worker thread forever → ALL sensor evals stopped. The op-side helpers got a hard timeout on
2026-06-15; this locks in the SAME guard on the sensor-eval path.

Source-inspection (AST) only — must NOT import the ``pipeline`` package (pulls in the dbt manifest,
absent in the fast gate), like the other fast-gate op/sensor guards.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).parents[2]
_SENSOR = _REPO / "pipeline" / "sensors" / "lineup_monitor_sensor.py"


def _func(path: Path, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"{name} not found in {path.name}")


def test_evaluate_passes_subprocess_timeout():
    """The lineup_monitor.py subprocess.run must set a finite timeout (a wedge can NEVER block
    the daemon thread indefinitely)."""
    fn = _func(_SENSOR, "_evaluate_lineup_monitor")
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    run_calls = [
        c for c in calls
        if isinstance(c.func, ast.Attribute) and c.func.attr == "run"
    ]
    assert run_calls, "expected a subprocess.run call in _evaluate_lineup_monitor"
    assert any(
        any(kw.arg == "timeout" for kw in c.keywords) for c in run_calls
    ), "INC-32: the lineup_monitor.py subprocess.run must pass timeout= (daemon-block guard)"


def test_evaluate_handles_timeout_expired():
    """A TimeoutExpired must be caught and turned into a SkipReason — never propagate as a hang."""
    fn = _func(_SENSOR, "_evaluate_lineup_monitor")
    body = ast.unparse(fn)
    assert "TimeoutExpired" in body, "must explicitly handle subprocess.TimeoutExpired"
    handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
    to_handler = [
        h for h in handlers
        if h.type is not None and "TimeoutExpired" in ast.unparse(h.type)
    ]
    assert to_handler, "must have an except that names TimeoutExpired"
    hbody = ast.unparse(to_handler[0])
    assert "SkipReason" in hbody, "the timeout handler must return a SkipReason (skip, not hang)"
    assert not any(isinstance(n, ast.Raise) for n in ast.walk(to_handler[0])), (
        "the timeout handler must NOT re-raise — the daemon must keep evaluating"
    )
