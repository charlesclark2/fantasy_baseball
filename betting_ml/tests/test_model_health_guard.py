"""INC-17-P3 — unit tests for the model health guard additions.

Two ACs:
  1. A post_lineup slate with null matchup block (low feature_coverage_score) triggers
     the check_post_lineup_matchup_coverage alert.
  2. A healthy v6 calibrated model (calibrated_spread=0.0299) does NOT false-fail the
     spread gate now that MIN_SPREAD_PROB=0.025.

All Snowflake is mocked — no network.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import numpy as np
import pytest

from betting_ml.monitoring import model_health_metrics as mh


# ---------------------------------------------------------------------------
# Task 1: post_lineup matchup coverage check
# ---------------------------------------------------------------------------

def _make_conn(n_games: int, avg_coverage: float | None) -> MagicMock:
    """Mock Snowflake connection returning (n_games, avg_coverage) from the coverage query."""
    row = (n_games, avg_coverage)
    cursor = MagicMock()
    cursor.fetchone.return_value = row
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def test_post_lineup_null_matchup_fires_alert():
    """INC-17 class: a slate where lineup block is null (avg coverage 0.833) triggers alert."""
    # 0.833 = 5/6: lineup block (avg_eb_woba) null across all games, other blocks fine.
    conn = _make_conn(n_games=15, avg_coverage=5 / 6)
    result = mh.check_post_lineup_matchup_coverage(conn, "betting_ml", date(2026, 6, 27))

    assert result["alert_fired"] is True, "Expected alert when avg_coverage < threshold"
    assert result["n_games"] == 15
    assert result["avg_coverage"] == pytest.approx(5 / 6, abs=1e-6)
    assert "INC-17 class" in result["fail_reason"]
    assert "avg_eb_woba" in result["fail_reason"]


def test_post_lineup_healthy_coverage_passes():
    """Healthy slate with full coverage (avg=1.0) does not fire."""
    conn = _make_conn(n_games=15, avg_coverage=1.0)
    result = mh.check_post_lineup_matchup_coverage(conn, "betting_ml", date(2026, 6, 27))

    assert result["alert_fired"] is False
    assert result["fail_reason"] == ""


def test_post_lineup_odds_missing_only_does_not_alert():
    """A few games lacking the odds block (avg=0.944) should not fire the alert.

    With 2/15 games lacking only the odds block:
      avg = (13*1.0 + 2*(5/6)) / 15 ≈ 0.978   → above 0.85, no alert.
    With 5/15 games lacking only the odds block:
      avg = (10*1.0 + 5*(5/6)) / 15 ≈ 0.944   → still above 0.85, no alert.
    """
    avg_with_some_odds_missing = (10 * 1.0 + 5 * (5 / 6)) / 15
    conn = _make_conn(n_games=15, avg_coverage=avg_with_some_odds_missing)
    result = mh.check_post_lineup_matchup_coverage(conn, "betting_ml", date(2026, 6, 27))

    assert result["alert_fired"] is False, (
        f"Expected no alert: only odds block missing, avg={avg_with_some_odds_missing:.3f}"
    )


def test_post_lineup_too_few_games_skipped():
    """Fewer than POST_LINEUP_MIN_GAMES_FOR_CHECK rows → skip (no false alert on off-days)."""
    conn = _make_conn(n_games=2, avg_coverage=0.5)
    result = mh.check_post_lineup_matchup_coverage(conn, "betting_ml", date(2026, 6, 27))

    assert result["alert_fired"] is False
    assert "insufficient" in result["fail_reason"]


def test_post_lineup_empty_slate_skipped():
    """Zero rows → skip, no alert."""
    conn = _make_conn(n_games=0, avg_coverage=None)
    result = mh.check_post_lineup_matchup_coverage(conn, "betting_ml", date(2026, 6, 27))

    assert result["alert_fired"] is False


# ---------------------------------------------------------------------------
# Task 2: spread threshold — v6 calibrated model must PASS, real collapse must FAIL
# ---------------------------------------------------------------------------

def _make_hw_df(n: int, calibrated_spread: float, corr: float = 0.08) -> "pd.DataFrame":
    """Build a minimal home_win DataFrame with the requested calibrated spread."""
    import pandas as pd

    rng = np.random.default_rng(42)
    base = 0.50
    calibrated = rng.normal(base, calibrated_spread, n).clip(0.01, 0.99)
    # Force the exact std so the test is deterministic.
    calibrated = calibrated - calibrated.mean() + base
    calibrated = calibrated / calibrated.std() * calibrated_spread + base

    # Build a correlated outcome so corr gate passes (corr ≈ 0.08 > MIN_CORR_CLASS=0.05).
    outcome = (calibrated + rng.normal(0, 0.45, n) > base).astype(float)

    return pd.DataFrame({
        "calibrated_win_prob":     calibrated,
        "consensus_win_prob":      calibrated,
        "h2h_market_implied_prob": np.full(n, base),
        "home_final_score":        np.where(outcome == 1, 5.0, 3.0),
        "away_final_score":        np.where(outcome == 0, 5.0, 3.0),
    })


def test_spread_v6_calibrated_passes_gate():
    """v6's calibrated_spread=0.0299 must PASS with MIN_SPREAD_PROB=0.025 (INC-17-P3 fix).

    Before this fix the gate used 0.030, so 0.0299 < 0.030 → false FAIL (cry-wolf).
    """
    import pandas as pd
    df = _make_hw_df(n=60, calibrated_spread=0.0299)
    metrics = mh._eval_home_win(df, min_games=30)

    spread_reason = [r for r in (metrics.get("fail_reasons") or "").split("; ") if "spread" in r]
    assert not spread_reason, (
        f"v6 calibrated model (spread=0.0299) should NOT fail the spread gate "
        f"(MIN_SPREAD_PROB={mh.MIN_SPREAD_PROB}). Got: {metrics.get('fail_reasons')}"
    )


def test_spread_real_collapse_fails_gate():
    """A genuine flat-output collapse (spread=0.016) must still FAIL the spread gate."""
    df = _make_hw_df(n=60, calibrated_spread=0.016)
    metrics = mh._eval_home_win(df, min_games=30)

    spread_reason = [r for r in (metrics.get("fail_reasons") or "").split("; ") if "spread" in r]
    assert spread_reason, (
        f"Flat-output model (spread=0.016) should FAIL the spread gate "
        f"(MIN_SPREAD_PROB={mh.MIN_SPREAD_PROB}). Got: {metrics.get('fail_reasons')}"
    )


# ---------------------------------------------------------------------------
# INC-24 / E13.8 calibration: de-leaked home_win at the market ceiling must PASS.
# corr ≈ 0 and Brier ≈ no-skill are the HONEST limit of an efficient H2H market, not a
# regression — only the flat-output (spread) leg gates home_win now.
# ---------------------------------------------------------------------------

def test_home_win_at_market_ceiling_passes_not_fails():
    """A de-leaked classifier with healthy spread but corr≈0 / Brier≈no-skill must PASS,
    with the corr/Brier misses recorded as advisory_flags, never as fail_reasons (INC-24)."""
    import pandas as pd
    rng = np.random.default_rng(7)
    n, base = 80, 0.50
    calibrated = rng.normal(base, 0.04, n).clip(0.01, 0.99)  # healthy spread ~0.04 (> 0.025)
    outcome = rng.integers(0, 2, n).astype(float)            # independent → corr≈0, Brier≈no-skill
    df = pd.DataFrame({
        "calibrated_win_prob":     calibrated,
        "consensus_win_prob":      calibrated,
        "h2h_market_implied_prob": np.full(n, base),
        "home_final_score":        np.where(outcome == 1, 5.0, 3.0),
        "away_final_score":        np.where(outcome == 0, 5.0, 3.0),
    })
    metrics = mh._eval_home_win(df, min_games=30)
    assert metrics["calibrated_spread"] >= mh.MIN_SPREAD_PROB   # spread is healthy
    assert metrics["verdict"] == "PASS", (
        f"de-leaked home_win at the market ceiling must PASS, not FAIL. "
        f"fail_reasons={metrics.get('fail_reasons')}"
    )
    fr = metrics.get("fail_reasons") or ""
    assert "corr" not in fr and "Brier" not in fr, (
        f"corr/Brier must not gate home_win post-calibration; found in fail_reasons: {fr}"
    )


def test_home_win_flat_still_fails_even_at_ceiling():
    """Calibration must NOT swallow real corruption: a flat classifier (spread below floor)
    still FAILs even when corr/Brier are also missing (the INC-24 market-blind signature)."""
    df = _make_hw_df(n=60, calibrated_spread=0.010)
    metrics = mh._eval_home_win(df, min_games=30)
    assert metrics["verdict"] == "FAIL"
    assert "spread" in (metrics.get("fail_reasons") or "")


# ---------------------------------------------------------------------------
# Regression targets: run_differential is spread-only (near-efficient margin market, E13.8);
# total_runs KEEPS its corr gate (less-efficient O/U market, stable measurable corr).
# ---------------------------------------------------------------------------

def _make_reg_df(n: int, target: str, pred_spread: float, corr_target: float) -> "pd.DataFrame":
    """Build a regression DataFrame with a chosen pred spread and pred↔actual correlation."""
    import pandas as pd
    rng = np.random.default_rng(11)
    pred_base = 9.0 if target == "total_runs" else 0.0
    pred = rng.normal(pred_base, 1.0, n)
    pred = (pred - pred.mean()) / pred.std() * pred_spread + pred_base  # force the spread
    noise = rng.normal(0, 1.0, n)
    actual = corr_target * (pred - pred_base) + np.sqrt(max(1 - corr_target**2, 0.0)) * noise
    cols = {"home_final_score": np.zeros(n), "away_final_score": np.zeros(n)}
    if target == "total_runs":
        cols["home_final_score"] = actual + pred_base            # home+away = actual+base
        cols["pred_total_runs"] = pred
        cols["total_line_consensus"] = np.full(n, np.nan)
        cols["totals_p_over"] = np.full(n, np.nan)
        cols["over_prob_consensus"] = np.full(n, np.nan)
    else:
        cols["run_differential"] = actual
        cols["pred_run_diff_loc"] = pred
    import pandas as pd
    return pd.DataFrame(cols)


def test_run_differential_low_corr_passes_when_spread_healthy():
    """run_differential at the margin-market ceiling (corr < 0.05) but with a healthy spread must
    PASS — corr is advisory for this spread-only target (INC-24: the live corr 0.030 FAIL was a
    serving-window artifact; the rescore proved skill)."""
    df = _make_reg_df(n=80, target="run_differential", pred_spread=1.30, corr_target=0.02)
    m = mh._eval_regression(df, "run_differential", min_games=30)
    assert m["pred_spread"] >= mh.MIN_SPREAD_RUNDIFF
    assert m["verdict"] == "PASS", m.get("fail_reasons")
    assert "corr" not in (m.get("fail_reasons") or "")
    assert "corr" in (m.get("advisory_flags") or "")   # recorded, not fatal


def test_run_differential_flat_still_fails():
    """A near-constant run_differential (spread below floor) still FAILs — spread is the corruption
    gate even for a spread-only target."""
    df = _make_reg_df(n=80, target="run_differential", pred_spread=0.10, corr_target=0.30)
    m = mh._eval_regression(df, "run_differential", min_games=30)
    assert m["verdict"] == "FAIL"
    assert "spread" in (m.get("fail_reasons") or "")


def test_total_runs_keeps_its_corr_gate():
    """total_runs is NOT spread-only: a healthy spread but low corr must still FAIL (the O/U market
    is less efficient; the model retains measurable totals corr, so corr stays a gate)."""
    df = _make_reg_df(n=80, target="total_runs", pred_spread=1.20, corr_target=0.01)
    m = mh._eval_regression(df, "total_runs", min_games=30)
    assert m["pred_spread"] >= mh.MIN_SPREAD_TOTALS
    assert m["verdict"] == "FAIL"
    assert "corr" in (m.get("fail_reasons") or "")
