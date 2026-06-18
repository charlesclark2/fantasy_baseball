"""E9.20 — regression tests for the pick↔narrative side-attribution guard.

Tests _validate_pick_consistency (model data integrity check) and
_build_prompt (correct per-team labelling so the LLM can't flip home↔away).
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from betting_ml.scripts.generate_pick_narratives import (
    _validate_pick_consistency,
    _build_prompt,
)


# ---------------------------------------------------------------------------
# _validate_pick_consistency
# ---------------------------------------------------------------------------

def _row(pick_side, cal_win, game_pk=823125, home="SEA", away="BAL"):
    return {
        "game_pk": game_pk,
        "home_team": home,
        "away_team": away,
        "layer4_h2h_decision": pick_side,
        "calibrated_win_prob": cal_win,
    }


def test_away_pick_home_low_prob_valid():
    # pick_side='away', cal_win=0.21 (home has 21%) → away favored → OK
    ok, reason = _validate_pick_consistency(_row("away", 0.21))
    assert ok, reason


def test_home_pick_home_high_prob_valid():
    # pick_side='home', cal_win=0.80 → home favored → OK
    ok, reason = _validate_pick_consistency(_row("home", 0.80))
    assert ok, reason


def test_away_pick_home_high_prob_invalid():
    # pick_side='away' but cal_win=0.80 (home favored) → INCONSISTENT
    ok, reason = _validate_pick_consistency(_row("away", 0.80))
    assert not ok
    assert "away" in reason and "0.800" in reason


def test_home_pick_home_low_prob_invalid():
    # pick_side='home' but cal_win=0.20 (away favored) → INCONSISTENT
    ok, reason = _validate_pick_consistency(_row("home", 0.20))
    assert not ok
    assert "home" in reason and "0.200" in reason


def test_missing_pick_side_passes():
    row = _row(None, 0.40)
    ok, _ = _validate_pick_consistency(row)
    assert ok


def test_missing_cal_win_passes():
    row = _row("away", None)
    ok, _ = _validate_pick_consistency(row)
    assert ok


def test_borderline_exactly_half():
    # cal_win = 0.5 is edge case — pick_side='home' should pass (not < 0.5)
    ok, _ = _validate_pick_consistency(_row("home", 0.5))
    assert ok


# ---------------------------------------------------------------------------
# _build_prompt — team-labelled probabilities (E9.20)
# ---------------------------------------------------------------------------

def _prompt_row(pick_side="away", cal_win=0.208, mkt_win=0.520, home="SEA", away="BAL"):
    return {
        "home_team": home,
        "away_team": away,
        "pick": "AWAY (79%)" if pick_side == "away" else "HOME (80%)",
        "score_date": "2026-06-18",
        "layer4_h2h_decision": pick_side,
        "calibrated_win_prob": cal_win,
        "h2h_market_implied_prob": mkt_win,
        "totals_edge": None,
        "totals_model_prob": None,
        "over_prob_consensus": None,
        "total_line_consensus": None,
        "game_conviction_score": None,
        "qualified_bet": None,
        "sigma_tier": None,
    }


def test_prompt_labels_home_team_probability():
    prompt = _build_prompt(_prompt_row(), {})
    # Home team SEA expands to "Seattle Mariners"; probability must be explicitly named
    assert "Model P(Seattle Mariners wins): 20.8%" in prompt


def test_prompt_labels_away_team_probability():
    prompt = _build_prompt(_prompt_row(), {})
    # Away team BAL expands to "Baltimore Orioles"; probability must be explicitly named
    assert "Model P(Baltimore Orioles wins): 79.2%" in prompt


def test_prompt_no_ambiguous_win_probability():
    prompt = _build_prompt(_prompt_row(), {})
    # Old ambiguous pattern must not appear
    assert "Model win probability:" not in prompt


def test_prompt_identifies_backed_team_away():
    prompt = _build_prompt(_prompt_row(pick_side="away"), {})
    # BAL expands to "Baltimore Orioles"
    assert "The model backs Baltimore Orioles to win" in prompt


def test_prompt_identifies_backed_team_home():
    prompt = _build_prompt(_prompt_row(pick_side="home", cal_win=0.80, mkt_win=0.52), {})
    # SEA expands to "Seattle Mariners"
    assert "The model backs Seattle Mariners to win" in prompt


def test_prompt_labels_home_team_in_game_line():
    prompt = _build_prompt(_prompt_row(), {})
    # Abbreviations expanded to full names
    assert "Home team: Seattle Mariners" in prompt
    assert "Away team: Baltimore Orioles" in prompt


def test_prompt_edge_matches_chip_formula():
    # Edge displayed must equal abs(cal_win - mkt_win) = abs(0.208 - 0.520) = 0.312
    prompt = _build_prompt(_prompt_row(cal_win=0.208, mkt_win=0.520), {})
    assert "31.2%" in prompt
