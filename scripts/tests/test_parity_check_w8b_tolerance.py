"""test_parity_check_w8b_tolerance.py — E11.1-W9-tail PARITY RIDER guard.

Locks the posterior-drift tolerance added to scripts/parity_check_w8b.py so the benign
FALSE-RED class (native vs S3 build snapshots read different EB/sequential/archetype
posterior generations) stays tolerated WITHOUT loosening the gate's ability to catch a
real migration defect. No Snowflake/S3 IO — exercises the pure comparison logic only.
"""
from __future__ import annotations

from scripts.parity_check_w8b import (
    _is_posterior_col,
    _compare,
    _POSTERIOR_RTOL,
    _POSTERIOR_ABS,
)

_N = 26_000  # ~ aggregator row count at a full 2015→2026 build


def test_predicate_flags_posterior_columns_only():
    # posterior-derived → tolerated
    assert _is_posterior_col("away_avg_eb_woba")
    assert _is_posterior_col("home_team_sequential_woba")
    assert _is_posterior_col("home_lineup_woba_vs_starter_archetype")
    assert _is_posterior_col("home_lineup_avg_xwoba_vs_cluster")
    assert _is_posterior_col("home_bp_matchup_xwoba")
    # deterministic → NOT tolerated (must keep the tight tolerance)
    assert not _is_posterior_col("away_avg_woba_30d")
    assert not _is_posterior_col("home_win_rate_trailing_3yr")
    assert not _is_posterior_col("temp_f")
    assert not _is_posterior_col("eb_park_run_factor".replace("eb_", "park_"))  # sanity


def test_benign_posterior_drift_passes():
    # eb col summing ~7800 drifting ~104 (≈0.004/row) → within posterior tolerance → PASS
    sf = {"n_rows": _N, "c__away_avg_eb_woba": _N, "s__away_avg_eb_woba": 7800.0}
    s3 = {"n_rows": _N, "c__away_avg_eb_woba": _N, "s__away_avg_eb_woba": 7800.0 + 104.0}
    assert _compare("benign_posterior", sf, s3, None) is True


def test_real_scale_bug_on_posterior_col_still_fails():
    # a 2× scale error on a posterior col is ≫ tolerance → must FAIL
    sf = {"n_rows": _N, "c__away_avg_eb_woba": _N, "s__away_avg_eb_woba": 7800.0}
    s3 = {"n_rows": _N, "c__away_avg_eb_woba": _N, "s__away_avg_eb_woba": 15600.0}
    assert _compare("broken_posterior", sf, s3, None) is False


def test_deterministic_col_drift_still_fails():
    # the SAME magnitude of drift on a DETERMINISTIC column keeps the tight 1e-6 → FAIL
    sf = {"n_rows": _N, "c__away_avg_woba_30d": _N, "s__away_avg_woba_30d": 7800.0}
    s3 = {"n_rows": _N, "c__away_avg_woba_30d": _N, "s__away_avg_woba_30d": 7800.0 + 104.0}
    assert _compare("det_drift", sf, s3, None) is False


def test_posterior_count_change_still_fails():
    # non-null COUNT stays EXACT for posterior cols too — a coverage/null regression FAILs
    sf = {"n_rows": _N, "c__away_avg_eb_woba": _N, "s__away_avg_eb_woba": 7800.0}
    s3 = {"n_rows": _N, "c__away_avg_eb_woba": _N - 50, "s__away_avg_eb_woba": 7800.0}
    assert _compare("count_mismatch", sf, s3, None) is False


def test_tolerance_constants_are_sane():
    # loose enough for ~1% posterior drift, tight enough that a 2× error never slips through.
    assert 1e-3 <= _POSTERIOR_RTOL <= 5e-2
    assert 1e-4 <= _POSTERIOR_ABS <= 1e-2
