"""E11.24 target 6 — guards for the per-slate umpire rebuild idempotency gate.

The gate removes the largest remaining COMPUTE_WH waker, so the tests that matter are the ones
that prove it cannot remove WORK: every failure mode must fail OPEN, and a newer assignment must
always win. The "skip" path gets one test; the "must not skip" paths get most of them.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from betting_ml.monitoring.umpire_rebuild_gate import (
    UMPIRE_GATE_ENV,
    UMPIRE_MODELS,
    assignment_watermark,
    read_rebuild_marker,
    umpire_gate_on,
    umpire_rebuild_decision,
)

DAY = date(2026, 7, 31)
T0 = datetime(2026, 7, 31, 23, 9, 0, tzinfo=timezone.utc)


class _Conn:
    """Minimal DuckDB stand-in: returns a canned MAX(loaded_at) or raises."""

    def __init__(self, value=None, exc: Exception | None = None):
        self._value, self._exc = value, exc
        self.closed = False

    def execute(self, sql, params=None):
        if self._exc is not None:
            raise self._exc
        return self

    def fetchone(self):
        return (self._value,)

    def close(self):
        self.closed = True


class _S3:
    def __init__(self, payload=None, exc: Exception | None = None):
        self._payload, self._exc = payload, exc
        self.written: list[dict] = []

    def get_object(self, Bucket, Key):  # noqa: N803 — boto3 kwarg casing
        if self._exc is not None:
            raise self._exc

        class _B:
            @staticmethod
            def read():
                return json.dumps(self_payload).encode()

        self_payload = self._payload
        return {"Body": _B}

    def put_object(self, **kw):
        self.written.append(kw)


def _decide(*, current, marker, s3_exc=None, conn_exc=None):
    s3 = _S3(payload=marker, exc=s3_exc)
    return umpire_rebuild_decision(
        DAY, conn_factory=lambda: _Conn(current, conn_exc), s3=s3
    )


# ── the flag ──────────────────────────────────────────────────────────────────────────────

def test_gate_is_default_off(monkeypatch):
    monkeypatch.delenv(UMPIRE_GATE_ENV, raising=False)
    assert umpire_gate_on() is False


def test_gate_on_only_for_exactly_1(monkeypatch):
    for value, expected in (("1", True), ("0", False), ("true", False), ("", False)):
        monkeypatch.setenv(UMPIRE_GATE_ENV, value)
        assert umpire_gate_on() is expected


# ── the ONE skip path ─────────────────────────────────────────────────────────────────────

def test_skips_when_the_assignment_is_unchanged():
    should, wm, reason = _decide(
        current=T0,
        marker={"game_date": DAY.isoformat(), "assignment_watermark": T0.isoformat()},
    )
    assert should is False
    assert "unchanged" in reason


# ── everything else must REBUILD ──────────────────────────────────────────────────────────

def test_rebuilds_when_the_assignment_is_newer_than_the_marker():
    """The core requirement: a LATE-landing assignment (the ~23:10 UTC defect) must still trigger
    exactly one rebuild. This is why the key is a watermark and not 'already rebuilt today'."""
    should, wm, reason = _decide(
        current=T0 + timedelta(minutes=5),
        marker={"game_date": DAY.isoformat(), "assignment_watermark": T0.isoformat()},
    )
    assert should is True
    assert wm == T0 + timedelta(minutes=5)


def test_a_marker_from_a_DIFFERENT_slate_never_suppresses_this_one():
    should, _, _ = _decide(
        current=T0,
        marker={"game_date": "2026-07-30", "assignment_watermark": T0.isoformat()},
    )
    assert should is True


def test_no_marker_at_all_rebuilds():
    should, wm, _ = _decide(current=T0, marker=None, s3_exc=FileNotFoundError("no such key"))
    assert should is True
    # the watermark is still returned so the first successful rebuild can record it
    assert wm == T0


def test_a_lakehouse_read_error_fails_OPEN_and_records_nothing():
    should, wm, reason = _decide(current=None, marker=None, conn_exc=RuntimeError("s3 blip"))
    assert should is True
    assert wm is None, "must not persist a watermark it could not establish"
    assert "OPEN" in reason


def test_a_connect_failure_fails_OPEN():
    def _boom():
        raise RuntimeError("duckdb down")

    should, wm, reason = umpire_rebuild_decision(DAY, conn_factory=_boom, s3=_S3())
    assert (should, wm) == (True, None)
    assert "OPEN" in reason


def test_no_umpire_row_yet_fails_OPEN_and_records_nothing():
    """An empty slate must not be latched — this block has an incident history (INC-31/F2) of
    silently zeroing, so 'nothing there yet' can never become 'never rebuild'."""
    should, wm, reason = _decide(current=None, marker=None)
    assert (should, wm) == (True, None)
    assert "OPEN" in reason


def test_a_missing_glob_is_absence_not_an_error():
    exc = Exception("No files found that match the pattern foo")
    assert assignment_watermark(_Conn(exc=exc), DAY) is None


def test_a_genuine_read_error_propagates_from_the_raw_reader():
    with pytest.raises(RuntimeError):
        assignment_watermark(_Conn(exc=RuntimeError("AccessDenied")), DAY)


# ── tz handling (the LTZ/NTZ landmine) ────────────────────────────────────────────────────

def test_a_naive_loaded_at_is_read_as_UTC_not_local():
    """The SF-bridged rows try_cast to NAIVE timestamps storing UTC; the live-writer rows are
    aware UTC ISO. Both must land on the same instant, or the comparison acquires a silent offset
    (the four-times-repeated LTZ/NTZ bug class)."""
    naive = assignment_watermark(_Conn(datetime(2026, 7, 31, 23, 9, 0)), DAY)
    aware = assignment_watermark(_Conn(T0), DAY)
    assert naive == aware


def test_an_iso_string_marker_is_parsed_not_string_compared():
    """Lexicographic ISO comparison breaks across offset formats, so the marker must be parsed."""
    got = read_rebuild_marker(
        DAY, s3=_S3({"game_date": DAY.isoformat(), "assignment_watermark": "2026-07-31T23:09:00+00:00"})
    )
    assert got == T0


# ── the selector contract ─────────────────────────────────────────────────────────────────

def test_only_the_two_umpire_models_are_gateable():
    """A regression here would silently stop rebuilding a model that DOES change with a confirmed
    lineup — the opposite of the gate's intent."""
    assert set(UMPIRE_MODELS) == {"stg_statsapi_umpire_game_log", "feature_pregame_umpire_features"}


def _rebuild_op_source() -> str:
    """The lineup_dbt_feature_rebuild body, read from DISK — the fast gate may not import
    `pipeline` (it reads the dbt manifest at import, absent in CI). Source inspection only."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "pipeline" / "ops" / "sensor_ops.py").read_text()
    start = src.index("def lineup_dbt_feature_rebuild")
    end = src.index("\n@op(", start)
    return src[start:end]


def test_the_op_drops_exactly_those_models_and_nothing_else():
    src = _rebuild_op_source()
    # the gated models are spliced in via *umpire_models, never hardcoded in the selector
    assert "*umpire_models" in src
    for keep in ("eb_starter_posteriors", "eb_batter_posteriors_raw",
                 "feature_pregame_starter_features", "feature_pregame_lineup_features",
                 "feature_pregame_game_features_raw", "feature_pregame_game_features"):
        assert f'"{keep}"' in src, f"{keep} must remain unconditionally in the selector"
    for gated in UMPIRE_MODELS:
        assert f'"{gated}"' not in src, f"{gated} must NOT be hardcoded in the selector"


def test_the_marker_is_only_written_after_a_successful_rebuild():
    src = _rebuild_op_source()
    assert src.index("_run_dbt(context") < src.index("write_rebuild_marker("), (
        "the marker must advance AFTER the dbt run, else a failed rebuild would latch the gate"
    )
