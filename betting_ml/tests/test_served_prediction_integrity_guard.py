"""Tests for scripts/check_served_prediction_integrity.py — the E11.22 served-prediction
integrity gate (the permanent INPUT-integrity monitor).

Guards the migration failure classes that row-count parity misses and the 30-day model-health
sensor only surfaces weeks later:
  - INC-22    predictions dated beyond the served date (UTC/clock roll)
  - INC-25    the slate fell to intraday_fallback (data_source != feature_store)
  - INC-17-P2 post_lineup feature_coverage_score collapsed (a lineup block went null)
  - INC-24    a target's output went FLAT (near-constant / all-null)

The pure classifier (evaluate_tier) must fire on each degradation and stay silent on a healthy
tier; main() must ALERT-but-exit-0 by default and HALT (exit 1) under --strict.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _PROJECT_ROOT / "scripts" / "check_served_prediction_integrity.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_served_prediction_integrity", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve cls.__module__ in sys.modules (it fails
    # with AttributeError otherwise under a bare importlib load).
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


spi = _load_module()


def _healthy(tier: str = "post_lineup", n: int = 15) -> "spi.TierStat":
    """A tier that passes every check: full feature-store serve, high coverage, varied output."""
    return spi.TierStat(
        tier=tier, n=n,
        feature_store_frac=1.0,
        avg_coverage=0.95,
        spread_win_prob=0.05,     # > MIN_SPREAD_PROB (0.025)
        spread_total_runs=1.20,   # > MIN_SPREAD_TOTALS (0.50)
        spread_run_diff=1.10,     # > MIN_SPREAD_RUNDIFF (0.50)
    )


class TestEvaluateTier:
    def test_healthy_tier_has_no_problems(self):
        assert spi.evaluate_tier(_healthy()) == []

    def test_too_small_slate_is_not_assessed(self):
        s = _healthy(n=3)  # < MIN_GAMES_FOR_CHECK
        s.spread_total_runs = 0.0  # would be FLAT, but n too small → skipped
        assert spi.evaluate_tier(s) == []

    def test_intraday_fallback_is_flagged(self):
        s = _healthy()
        s.feature_store_frac = 0.10   # slate fell to intraday assembly
        probs = spi.evaluate_tier(s)
        assert any("intraday_fallback" in p for p in probs)

    def test_post_lineup_coverage_collapse_is_flagged(self):
        s = _healthy(tier="post_lineup")
        s.avg_coverage = 0.40   # lineup block went null
        probs = spi.evaluate_tier(s)
        assert any("feature_coverage_score" in p and "INC-17-P2" in p for p in probs)

    def test_morning_tier_does_not_assert_coverage_floor(self):
        # Pre-lineup coverage is legitimately lower (lineup/odds not posted) — no coverage alarm.
        s = _healthy(tier="morning")
        s.avg_coverage = 0.40
        probs = spi.evaluate_tier(s)
        assert not any("feature_coverage_score" in p for p in probs)

    def test_flat_total_runs_is_the_inc24_signature(self):
        s = _healthy(n=15)   # ≥ MIN_GAMES_FOR_SPREAD
        s.spread_total_runs = 0.20   # < MIN_SPREAD_TOTALS → near-constant (INC-24)
        probs = spi.evaluate_tier(s)
        assert any("total_runs" in p and "FLAT" in p for p in probs)

    def test_flat_spread_not_asserted_on_a_light_slate(self):
        # The 2026-07-06 case: an 8-game slate served 100% from the feature store, but with a
        # naturally lower total_runs spread. Below MIN_GAMES_FOR_SPREAD the flat verdict is NOT
        # asserted (small-sample), so a healthy light day does not false-fire.
        s = _healthy(n=8)
        s.spread_total_runs = 0.44   # below the 0.50 floor but only 8 games
        assert spi.evaluate_tier(s) == []

    def test_flat_home_win_is_flagged(self):
        s = _healthy()
        s.spread_win_prob = 0.005   # < MIN_SPREAD_PROB → flat classifier output
        probs = spi.evaluate_tier(s)
        assert any("home_win" in p and "FLAT" in p for p in probs)

    def test_all_null_target_on_serving_tier_is_flagged(self):
        # A tier that serves win_prob + run_diff but total_runs materialized 100% NULL.
        s = _healthy()
        s.spread_total_runs = None
        probs = spi.evaluate_tier(s)
        assert any("total_runs" in p and "ALL-NULL" in p for p in probs)

    def test_all_targets_null_does_not_spam(self):
        # A tier that emits none of the three targets is not asserted against (not a corruption
        # of a serving tier — tier_is_serving is False).
        s = _healthy()
        s.spread_win_prob = s.spread_total_runs = s.spread_run_diff = None
        assert spi.evaluate_tier(s) == []


def _run_main(tier_rows, future_rows, argv, capsys, *, served_date="2026-07-06"):
    """Run main() with a mocked cursor. `tier_rows` is a list of 7-tuples matching the SELECT
    column order (prediction_type, n, feature_store_frac, avg_coverage, spread_win_prob,
    spread_total_runs, spread_run_diff). Returns (return_code, stdout_text)."""
    cur = mock.MagicMock()
    # First execute → group-by tier rows; second execute → the future-rows scalar.
    cur.fetchall.return_value = tier_rows
    cur.fetchone.return_value = (future_rows,)
    conn = mock.MagicMock()
    conn.cursor.return_value = cur
    with mock.patch.object(spi, "get_snowflake_connection", return_value=conn), \
         mock.patch.object(sys, "argv",
                           ["check_served_prediction_integrity.py", "--date", served_date, *argv]):
        rc = spi.main()
    return rc, capsys.readouterr().out


_HEALTHY_ROW = ("post_lineup", 15, 1.0, 0.95, 0.05, 1.20, 1.10)


class TestMain:
    def test_all_healthy_passes(self, capsys):
        rc, out = _run_main([_HEALTHY_ROW], 0, ["--env", "prod", "--strict"], capsys)
        assert rc == 0
        assert "served_integrity_problem_count=0" in out

    def test_flat_slate_non_strict_alerts_but_exits_zero(self, capsys, caplog):
        flat = ("post_lineup", 15, 1.0, 0.95, 0.05, 0.20, 1.10)  # total_runs flat
        with caplog.at_level("WARNING"):
            rc, out = _run_main([flat], 0, ["--env", "prod"], capsys)
        assert rc == 0
        assert "ALERT" in caplog.text and "FLAT" in caplog.text
        assert "served_integrity_problem_count=1" in out

    def test_flat_slate_strict_halts(self, capsys, caplog):
        flat = ("post_lineup", 15, 1.0, 0.95, 0.05, 0.20, 1.10)
        with caplog.at_level("ERROR"):
            rc, out = _run_main([flat], 0, ["--env", "prod", "--strict"], capsys)
        assert rc == 1
        assert "HALT" in caplog.text

    def test_future_dated_rows_flag_inc22(self, capsys, caplog):
        with caplog.at_level("ERROR"):
            rc, out = _run_main([_HEALTHY_ROW], 12, ["--env", "prod", "--strict"], capsys)
        assert rc == 1
        assert "INC-22" in caplog.text

    def test_empty_slate_is_benign(self, capsys):
        # No predictions for today (off-day / not-yet-run) → benign, never a HALT.
        rc, out = _run_main([], 0, ["--env", "prod", "--strict"], capsys)
        assert rc == 0
        assert "served_integrity_problem_count=0" in out
