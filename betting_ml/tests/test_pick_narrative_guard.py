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


# ---------------------------------------------------------------------------
# E11.20 phase-2b — the totals paragraph must not hinge on `totals_edge`
#
# `totals_edge` is the alpha-aware ACTIONABLE edge and is NULL by design while
# best_alpha = 0. The Nova prompt decides paragraph count deterministically from
# `totals_ev_str`, so gating that string on `totals_edge` silently dropped the
# totals paragraph from EVERY narrative on the first Nova slate (2026-07-27:
# 0/85 two-paragraph, though 80/85 carried the line + both probabilities).
# ---------------------------------------------------------------------------

def _totals_row(tot_edge=None, tot_model=0.556, tot_mkt=0.512, tot_line=8.5):
    row = _prompt_row()
    row.update({
        "totals_edge": tot_edge,
        "totals_model_prob": tot_model,
        "over_prob_consensus": tot_mkt,
        "total_line_consensus": tot_line,
    })
    return row


def test_totals_paragraph_survives_null_totals_edge():
    """The regression that shipped: probs + line present, totals_edge NULL."""
    prompt = _build_prompt(_totals_row(tot_edge=None), {})
    assert "TWO paragraphs" in prompt, (
        "a NULL totals_edge must not suppress the totals paragraph — totals_edge is "
        "unpopulated by design while best_alpha=0, so the paragraph would never render."
    )
    assert "Total line: 8.5" in prompt
    assert "Model P(over): 55.6%" in prompt and "Market P(over): 51.2%" in prompt


def test_divergence_is_derived_when_totals_edge_is_null():
    """Derived divergence must equal |model − market| — the same number
    write_serving_store's `ABS(totals_model_prob - over_prob_consensus)` serves."""
    prompt = _build_prompt(_totals_row(tot_edge=None, tot_model=0.556, tot_mkt=0.512), {})
    assert "Model-vs-market divergence (edge): +4.4%" in prompt


def test_populated_totals_edge_is_still_used():
    prompt = _build_prompt(_totals_row(tot_edge=0.031), {})
    assert "Model-vs-market divergence (edge): +3.1%" in prompt


def test_one_paragraph_when_totals_market_absent():
    """No totals market ⇒ ONE paragraph and an explicit no-totals instruction —
    the model must never invent a total line."""
    prompt = _build_prompt(_totals_row(tot_model=None, tot_mkt=None, tot_line=None), {})
    assert "ONE paragraph" in prompt
    assert "no totals data is available" in prompt


def test_missing_total_line_falls_back_to_one_paragraph():
    """Probabilities without a line can't answer 'give the total line' — don't ask
    for a paragraph the data can't fill."""
    prompt = _build_prompt(_totals_row(tot_line=None), {})
    assert "ONE paragraph" in prompt


# ---------------------------------------------------------------------------
# 2026-07-27 — the divergence clause must name the EDGE side, not the outright pick
#
# The two disagree on ~2 of every 3 served rows (391/597 over 7/20–7/27). The clause
# sits inside the "Model-vs-market divergence (edge)" sentence, so naming the outright
# pick there made the LLM attribute the edge to the wrong team on most picks.
# Live case 824570: model P(CWS) 47.4% vs market 42.2% ⇒ divergence favours CWS, while
# the model's outright pick is NYY.
# ---------------------------------------------------------------------------

def test_divergence_names_the_edge_side_not_the_outright_pick():
    """Model picks the AWAY team outright (cal_win 0.474 < 0.5) but sits ABOVE the
    market on HOME (0.474 > 0.422) — the divergence favours HOME."""
    prompt = _build_prompt(_prompt_row(cal_win=0.4745, mkt_win=0.4218, home="CWS", away="NYY"), {})
    assert "higher than the market on Chicago White Sox" in prompt, (
        "the divergence clause must name the side the model is ABOVE the market on "
        "(CWS here) — naming the outright pick (NYY) mis-attributes the edge."
    )
    assert "higher than the market on New York Yankees" not in prompt


def test_divergence_side_when_pick_and_edge_agree():
    """Model picks HOME outright AND sits above the market on HOME — same side."""
    prompt = _build_prompt(_prompt_row(cal_win=0.62, mkt_win=0.55, home="CWS", away="NYY"), {})
    assert "higher than the market on Chicago White Sox" in prompt


def test_divergence_side_flips_with_the_market_not_with_one_half():
    """Same model probability, market moved past it ⇒ the named side must flip. This is
    the property a `cal_win >= 0.5` label structurally cannot have."""
    below = _build_prompt(_prompt_row(cal_win=0.62, mkt_win=0.55, home="CWS", away="NYY"), {})
    above = _build_prompt(_prompt_row(cal_win=0.62, mkt_win=0.70, home="CWS", away="NYY"), {})
    assert "higher than the market on Chicago White Sox" in below
    assert "higher than the market on New York Yankees" in above, (
        "with the market ABOVE the model on home, the model is higher on away — the "
        "divergence side must follow the market, not the 0.5 threshold."
    )


def test_divergence_magnitude_is_unchanged():
    """The edge NUMBER still matches the pick chip: abs(P_home_model − P_home_market)."""
    prompt = _build_prompt(_prompt_row(cal_win=0.4745, mkt_win=0.4218), {})
    assert "divergence (edge): 5.3%" in prompt
