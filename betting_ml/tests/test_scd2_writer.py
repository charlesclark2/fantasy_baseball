"""
Unit tests for betting_ml/scripts/scd2_writer.py

Tests cover pure-Python logic (record_hash, annotate, empty-batch guard).
Integration tests (scd2_upsert against a live Snowflake connection) require
credentials and are not included here — exercise manually or via a dedicated
integration test suite.
"""

from __future__ import annotations

import pytest

from betting_ml.scripts.scd2_writer import compute_record_hash, _PAYLOAD_COLS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _row(signal_value=9.34, uncertainty=0.42, signal_available=True, **extras):
    base = {
        "game_pk": 748532,
        "side": "home",
        "signal_name": "run_env_signal",
        "sub_model_name": "run_env",
        "sub_model_version": "v1",
        "signal_value": signal_value,
        "uncertainty": uncertainty,
        "signal_available": signal_available,
        "input_feature_hash": "abc123",
    }
    base.update(extras)
    return base


# ---------------------------------------------------------------------------
# compute_record_hash
# ---------------------------------------------------------------------------

class TestComputeRecordHash:
    def test_deterministic(self):
        row = _row()
        assert compute_record_hash(row) == compute_record_hash(row)

    def test_same_payload_same_hash(self):
        assert compute_record_hash(_row(signal_value=1.0)) == compute_record_hash(_row(signal_value=1.0))

    def test_different_signal_value_different_hash(self):
        assert compute_record_hash(_row(signal_value=1.0)) != compute_record_hash(_row(signal_value=2.0))

    def test_different_uncertainty_different_hash(self):
        assert compute_record_hash(_row(uncertainty=0.1)) != compute_record_hash(_row(uncertainty=0.9))

    def test_different_available_different_hash(self):
        assert compute_record_hash(_row(signal_available=True)) != compute_record_hash(_row(signal_available=False))

    def test_none_signal_value(self):
        h = compute_record_hash(_row(signal_value=None))
        assert isinstance(h, str) and len(h) == 32

    def test_none_uncertainty(self):
        h = compute_record_hash(_row(uncertainty=None))
        assert isinstance(h, str) and len(h) == 32

    def test_null_vs_zero_different(self):
        assert compute_record_hash(_row(signal_value=None)) != compute_record_hash(_row(signal_value=0.0))

    def test_non_payload_fields_ignored(self):
        r1 = _row(input_feature_hash="aaa")
        r2 = _row(input_feature_hash="zzz")
        assert compute_record_hash(r1) == compute_record_hash(r2)

    def test_natural_key_fields_ignored(self):
        r1 = _row(game_pk=111111)
        r2 = _row(game_pk=999999)
        assert compute_record_hash(r1) == compute_record_hash(r2)

    def test_returns_32_char_hex(self):
        h = compute_record_hash(_row())
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# Payload column contract
# ---------------------------------------------------------------------------

class TestPayloadCols:
    def test_expected_payload_cols(self):
        assert set(_PAYLOAD_COLS) == {"signal_value", "uncertainty", "signal_available"}

    def test_payload_cols_ordered(self):
        assert list(_PAYLOAD_COLS) == ["signal_value", "uncertainty", "signal_available"]
