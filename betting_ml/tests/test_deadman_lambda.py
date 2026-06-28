"""INC-16-P6 — unit tests for the daily-output dead-man Lambda handler.

boto3 mocked; "today" pinned via _today_local. Covers the four outcomes:
missing heartbeat, stale heartbeat, healthy, and ran-with-errors.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_HANDLER_PATH = (
    Path(__file__).resolve().parents[2]
    / "services" / "observability" / "deadman_lambda" / "handler.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("deadman_handler", _HANDLER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _with_heartbeat(monkeypatch, mod, value: dict | None):
    """Wire boto3.resource(...).Table(...).get_item to return the given heartbeat value."""
    item = None if value is None else {"Item": {"value": json.dumps(value)}}
    table = MagicMock()
    table.get_item.return_value = item or {}
    resource = MagicMock()
    resource.Table.return_value = table
    monkeypatch.setattr("boto3.resource", lambda *a, **k: resource)
    monkeypatch.setattr("boto3.client", lambda *a, **k: MagicMock())  # sns publish no-op
    monkeypatch.setattr(mod, "_TOPIC", "arn:aws:sns:us-east-1:1:t")


def test_missing_heartbeat_alerts(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "_today_local", lambda: "2026-06-27")
    _with_heartbeat(monkeypatch, mod, None)
    out = mod.lambda_handler({}, None)
    assert out["status"] == "ALERT"
    assert out["reason"] == "missing_or_stale_heartbeat"


def test_stale_heartbeat_alerts(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "_today_local", lambda: "2026-06-27")
    _with_heartbeat(monkeypatch, mod, {"date": "2026-06-26", "n_picks": 12, "errors": 0})
    out = mod.lambda_handler({}, None)
    assert out["status"] == "ALERT"
    assert out["last"] == "2026-06-26"


def test_healthy_today_ok(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "_today_local", lambda: "2026-06-27")
    _with_heartbeat(monkeypatch, mod, {"date": "2026-06-27", "n_picks": 12, "errors": 0})
    out = mod.lambda_handler({}, None)
    assert out["status"] == "OK"
    assert out["n_picks"] == 12


def test_ran_with_errors_warns(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "_today_local", lambda: "2026-06-27")
    monkeypatch.setattr(mod, "_WARN_ON_ERRORS", True)
    _with_heartbeat(monkeypatch, mod, {"date": "2026-06-27", "n_picks": 5, "errors": 3})
    out = mod.lambda_handler({}, None)
    assert out["status"] == "WARN"
    assert out["errors"] == 3
