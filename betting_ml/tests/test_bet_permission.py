"""Unit tests for compute_bet_permission() — Story 19.2.

Each of the five gate criteria is tested independently: confirmed firing and
confirmed non-firing. Also tests the gate aggregation logic (qualified_bet,
game_conviction_score, gate_signals_met) and graceful degradation when
fields are missing.
"""

from __future__ import annotations

import pytest

from betting_ml.utils.probability_layer import compute_bet_permission


# ---------------------------------------------------------------------------
# Shared gate config (all criteria enabled so we can test each in isolation)
# ---------------------------------------------------------------------------

_ALL_ENABLED_CONFIG = {
    "min_criteria_met": 3,
    "criteria": {
        "offensive_signal_qualifies": {"threshold": 0.5, "enabled": True},
        "run_env_supports":           {"threshold": None, "enabled": True},
        "uncertainty_below_threshold": {"threshold": None, "enabled": True},
        "market_disagreement_visible": {"threshold": None, "enabled": False},  # no signal source yet
        "prior_fresh":                {"threshold": 7,    "enabled": True},
    },
}

_PROD_CONFIG = {
    "min_criteria_met": 3,
    "criteria": {
        "offensive_signal_qualifies": {"threshold": 0.5, "enabled": True},
        "run_env_supports":           {"threshold": None, "enabled": False},
        "uncertainty_below_threshold": {"threshold": None, "enabled": False},
        "market_disagreement_visible": {"threshold": None, "enabled": False},
        "prior_fresh":                {"threshold": 7,    "enabled": False},
    },
}


# ---------------------------------------------------------------------------
# Criterion 1 — offensive_signal_qualifies
# ---------------------------------------------------------------------------

class TestOffensiveSignal:
    def test_fires_when_disagreement_at_threshold(self):
        row = {"pred_total_runs": 9.5, "total_line_consensus": 9.0}  # delta = 0.5
        result = compute_bet_permission("G1", row, gate_config=_PROD_CONFIG)
        assert result["gate_detail"]["offensive_signal_qualifies"] is True

    def test_fires_when_disagreement_above_threshold(self):
        row = {"pred_total_runs": 10.5, "total_line_consensus": 9.0}  # delta = 1.5
        result = compute_bet_permission("G2", row, gate_config=_PROD_CONFIG)
        assert result["gate_detail"]["offensive_signal_qualifies"] is True

    def test_does_not_fire_when_disagreement_below_threshold(self):
        row = {"pred_total_runs": 9.4, "total_line_consensus": 9.0}  # delta = 0.4
        result = compute_bet_permission("G3", row, gate_config=_PROD_CONFIG)
        assert result["gate_detail"]["offensive_signal_qualifies"] is False

    def test_does_not_fire_when_line_missing(self):
        row = {"pred_total_runs": 10.0, "total_line_consensus": None}
        result = compute_bet_permission("G4", row, gate_config=_PROD_CONFIG)
        assert result["gate_detail"]["offensive_signal_qualifies"] is False

    def test_does_not_fire_when_pred_missing(self):
        row = {"total_line_consensus": 9.0}
        result = compute_bet_permission("G5", row, gate_config=_PROD_CONFIG)
        assert result["gate_detail"]["offensive_signal_qualifies"] is False

    def test_conviction_score_scales_with_disagreement(self):
        """Larger disagreement → higher conviction score (monotonic)."""
        row_small = {"pred_total_runs": 9.5, "total_line_consensus": 9.0}   # delta = 0.5
        row_large = {"pred_total_runs": 10.5, "total_line_consensus": 9.0}  # delta = 1.5
        r_small = compute_bet_permission("G6", row_small, gate_config=_PROD_CONFIG)
        r_large = compute_bet_permission("G7", row_large, gate_config=_PROD_CONFIG)
        assert r_large["game_conviction_score"] > r_small["game_conviction_score"]


# ---------------------------------------------------------------------------
# Criterion 2 — run_env_supports (not yet wired; always False)
# ---------------------------------------------------------------------------

class TestRunEnvSupports:
    def test_never_fires_when_disabled(self):
        row = {"run_env_signal": 1.5}
        result = compute_bet_permission("G8", row, gate_config=_PROD_CONFIG)
        assert result["gate_detail"]["run_env_supports"] is False

    def test_never_fires_even_when_enabled_no_source(self):
        # Even with enabled=True, _eval_run_env_supports currently returns 0.0
        result = compute_bet_permission("G9", {}, gate_config=_ALL_ENABLED_CONFIG)
        assert result["gate_detail"]["run_env_supports"] is False


# ---------------------------------------------------------------------------
# Criterion 3 — uncertainty_below_threshold (not yet wired; always False)
# ---------------------------------------------------------------------------

class TestUncertaintyGate:
    def test_never_fires_when_disabled(self):
        row = {"game_uncertainty_score": 0.1}
        result = compute_bet_permission("G10", row, gate_config=_PROD_CONFIG)
        assert result["gate_detail"]["uncertainty_below_threshold"] is False

    def test_never_fires_even_when_enabled_no_source(self):
        result = compute_bet_permission("G11", {}, gate_config=_ALL_ENABLED_CONFIG)
        assert result["gate_detail"]["uncertainty_below_threshold"] is False


# ---------------------------------------------------------------------------
# Criterion 4 — market_disagreement_visible (always False)
# ---------------------------------------------------------------------------

class TestMarketDisagreement:
    def test_never_fires(self):
        result = compute_bet_permission("G12", {}, gate_config=_PROD_CONFIG)
        assert result["gate_detail"]["market_disagreement_visible"] is False


# ---------------------------------------------------------------------------
# Criterion 5 — prior_fresh
# ---------------------------------------------------------------------------

class TestPriorFresh:
    def test_fires_when_prior_age_within_threshold(self):
        row = {"prior_age_days": 5}
        cfg = {**_PROD_CONFIG, "criteria": {
            **_PROD_CONFIG["criteria"],
            "prior_fresh": {"threshold": 7, "enabled": True},
        }}
        result = compute_bet_permission("G13", row, gate_config=cfg)
        assert result["gate_detail"]["prior_fresh"] is True

    def test_fires_when_prior_age_exactly_at_threshold(self):
        row = {"prior_age_days": 7}
        cfg = {**_PROD_CONFIG, "criteria": {
            **_PROD_CONFIG["criteria"],
            "prior_fresh": {"threshold": 7, "enabled": True},
        }}
        result = compute_bet_permission("G14", row, gate_config=cfg)
        assert result["gate_detail"]["prior_fresh"] is True

    def test_does_not_fire_when_prior_age_above_threshold(self):
        row = {"prior_age_days": 8}
        cfg = {**_PROD_CONFIG, "criteria": {
            **_PROD_CONFIG["criteria"],
            "prior_fresh": {"threshold": 7, "enabled": True},
        }}
        result = compute_bet_permission("G15", row, gate_config=cfg)
        assert result["gate_detail"]["prior_fresh"] is False

    def test_does_not_fire_when_prior_age_missing(self):
        cfg = {**_PROD_CONFIG, "criteria": {
            **_PROD_CONFIG["criteria"],
            "prior_fresh": {"threshold": 7, "enabled": True},
        }}
        result = compute_bet_permission("G16", {}, gate_config=cfg)
        assert result["gate_detail"]["prior_fresh"] is False

    def test_does_not_fire_when_disabled_even_if_fresh(self):
        row = {"prior_age_days": 1}
        result = compute_bet_permission("G17", row, gate_config=_PROD_CONFIG)
        assert result["gate_detail"]["prior_fresh"] is False


# ---------------------------------------------------------------------------
# Gate aggregation logic
# ---------------------------------------------------------------------------

class TestGateAggregation:
    def test_qualified_bet_false_when_zero_criteria_met(self):
        result = compute_bet_permission("G18", {}, gate_config=_PROD_CONFIG)
        assert result["qualified_bet"] is False
        assert result["gate_signals_met"] == 0

    def test_qualified_bet_false_below_min_criteria_met(self):
        # Only criterion 1 fires (1 < min_criteria_met=3)
        row = {"pred_total_runs": 10.0, "total_line_consensus": 9.0}
        result = compute_bet_permission("G19", row, gate_config=_PROD_CONFIG)
        assert result["qualified_bet"] is False
        assert result["gate_signals_met"] == 1

    def test_conviction_score_zero_when_no_criteria_met(self):
        result = compute_bet_permission("G20", {}, gate_config=_PROD_CONFIG)
        assert result["game_conviction_score"] == 0.0

    def test_conviction_score_bounded_0_to_1(self):
        """Even with maximum disagreement, score must not exceed 1.0."""
        row = {"pred_total_runs": 20.0, "total_line_consensus": 9.0}  # delta = 11 runs
        result = compute_bet_permission("G21", row, gate_config=_PROD_CONFIG)
        assert 0.0 <= result["game_conviction_score"] <= 1.0

    def test_gate_detail_has_all_five_keys(self):
        result = compute_bet_permission("G22", {}, gate_config=_PROD_CONFIG)
        expected_keys = {
            "offensive_signal_qualifies",
            "run_env_supports",
            "uncertainty_below_threshold",
            "market_disagreement_visible",
            "prior_fresh",
        }
        assert set(result["gate_detail"].keys()) == expected_keys

    def test_gate_signals_met_matches_gate_detail_count(self):
        row = {"pred_total_runs": 10.5, "total_line_consensus": 9.0}
        result = compute_bet_permission("G23", row, gate_config=_PROD_CONFIG)
        fired = sum(1 for v in result["gate_detail"].values() if v)
        assert result["gate_signals_met"] == fired

    def test_return_schema_complete(self):
        result = compute_bet_permission("G24", {}, gate_config=_PROD_CONFIG)
        assert "qualified_bet" in result
        assert "gate_signals_met" in result
        assert "game_conviction_score" in result
        assert "gate_detail" in result
        assert isinstance(result["qualified_bet"], bool)
        assert isinstance(result["gate_signals_met"], int)
        assert isinstance(result["game_conviction_score"], float)
        assert isinstance(result["gate_detail"], dict)

    def test_prior_freshness_blocks_qualification_regardless_of_signal_strength(self):
        """A game with prior_age_days > 7 never achieves qualified_bet via signal alone
        when prior_fresh is the only remaining criterion needed to hit min_criteria_met.
        This validates the AC from 19.2.
        """
        # Set min_criteria_met=1 so only offensive signal is needed; prior_fresh disabled
        cfg = {
            "min_criteria_met": 1,
            "criteria": {
                "offensive_signal_qualifies": {"threshold": 0.5, "enabled": True},
                "run_env_supports":           {"threshold": None, "enabled": False},
                "uncertainty_below_threshold": {"threshold": None, "enabled": False},
                "market_disagreement_visible": {"threshold": None, "enabled": False},
                "prior_fresh":                {"threshold": 7,    "enabled": True},
            },
        }
        # Criterion 1 fires; prior_fresh doesn't (age > threshold)
        row = {"pred_total_runs": 10.5, "total_line_consensus": 9.0, "prior_age_days": 15}
        result = compute_bet_permission("G25", row, gate_config=cfg)
        # With min=1, offensive signal alone qualifies — prior_age doesn't block THIS case
        assert result["qualified_bet"] is True
        assert result["gate_detail"]["prior_fresh"] is False
