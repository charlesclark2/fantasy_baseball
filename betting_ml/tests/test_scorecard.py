"""test_scorecard.py — E9.40 "who called it" scorecard win-semantics.

Locks the model/market settle rules so they stay consistent with the performance
page (E9.26): the pick = the side the probability favors (>= 0.5 → home/over),
one per market; h2h also grades the closing favorite; totals reports the line
result factually (no market win/loss on a ~50/50 total). Only Final games score.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.backend.services.scorecard import build_scorecard_from_detail


def _detail(status="Final", home_score=5, away_score=3, picks=None, **top):
    d = {
        "game_score": {"status": status, "home_score": home_score, "away_score": away_score},
        "picks": picks if picks is not None else [],
        "home_team_name": "Home Team",
        "away_team_name": "Away Team",
    }
    d.update(top)
    return d


def _h2h(model_prob, market_prob, home="HOM", away="AWY", game_pk=1):
    return {
        "game_pk": game_pk, "game_date": "2026-07-01", "market_type": "h2h",
        "model_prob": model_prob, "bovada_devig_prob": market_prob,
        "home_team": home, "away_team": away,
    }


def _totals(model_prob, market_prob, line, game_pk=1):
    return {
        "game_pk": game_pk, "game_date": "2026-07-01", "market_type": "totals",
        "model_prob": model_prob, "bovada_devig_prob": market_prob,
        "market_total_line": line,
    }


# ── gating ──────────────────────────────────────────────────────────────────

def test_non_final_returns_none():
    assert build_scorecard_from_detail(_detail(status="Live", picks=[_h2h(0.6, 0.55)])) is None
    assert build_scorecard_from_detail(_detail(status="Preview", picks=[_h2h(0.6, 0.55)])) is None


def test_missing_score_returns_none():
    assert build_scorecard_from_detail(_detail(home_score=None, picks=[_h2h(0.6, 0.55)])) is None


def test_no_gradable_markets_returns_none():
    assert build_scorecard_from_detail(_detail(picks=[])) is None
    assert build_scorecard_from_detail(_detail(picks=[{"market_type": "spread"}])) is None


# ── h2h model + market grading ──────────────────────────────────────────────

def test_h2h_model_and_market_both_call_home_and_home_wins():
    # home won 5-3; model favors home (0.62 >= 0.5); market favors home (0.58)
    sc = build_scorecard_from_detail(_detail(home_score=5, away_score=3, picks=[_h2h(0.62, 0.58)]))
    assert sc is not None and sc.status == "Final"
    assert sc.home_score == 5 and sc.away_score == 3
    m = sc.markets[0]
    assert m.market_type == "h2h"
    assert m.model_side == "home" and m.model_result == "win"
    assert m.market_side == "home" and m.market_result == "win"
    # oriented probs = confidence in the picked side
    assert abs(m.model_prob - 0.62) < 1e-9
    assert abs(m.market_prob - 0.58) < 1e-9


def test_h2h_model_calls_away_market_favors_home_home_wins():
    # model favors away (0.40 < 0.5 → away, loses); market favors home (0.55 → wins)
    sc = build_scorecard_from_detail(_detail(home_score=6, away_score=2, picks=[_h2h(0.40, 0.55)]))
    m = sc.markets[0]
    assert m.model_side == "away" and m.model_result == "loss"
    assert m.market_side == "home" and m.market_result == "win"
    # away-oriented model prob = 1 - 0.40
    assert abs(m.model_prob - 0.60) < 1e-9


def test_h2h_underdog_upset_model_right_market_wrong():
    # away wins 4-1; model favored away (0.53 → away wins); market favored home (0.60 → loses)
    sc = build_scorecard_from_detail(_detail(home_score=1, away_score=4, picks=[_h2h(0.47, 0.60)]))
    m = sc.markets[0]
    assert m.model_side == "away" and m.model_result == "win"
    assert m.market_side == "home" and m.market_result == "loss"


# ── totals grading (model call + factual line result, no market win/loss) ────

def test_totals_over_model_right_landed_over():
    # total 9 vs line 8.5 → over; model favors over (0.55)
    sc = build_scorecard_from_detail(_detail(home_score=5, away_score=4, picks=[_totals(0.55, 0.50, 8.5)]))
    m = sc.markets[0]
    assert m.market_type == "totals"
    assert m.model_side == "over" and m.model_result == "win"
    assert m.final_total == 9 and m.total_line == 8.5 and m.landed == "over"
    # totals carries NO market win/loss (books balance ~50/50)
    assert m.market_side is None and m.market_result is None


def test_totals_under_model_wrong_landed_over():
    sc = build_scorecard_from_detail(_detail(home_score=6, away_score=5, picks=[_totals(0.30, 0.50, 8.5)]))
    m = sc.markets[0]
    assert m.model_side == "under" and m.model_result == "loss"
    assert m.landed == "over" and m.final_total == 11


def test_totals_push_on_integer_line():
    # total 8 exactly equals line 8 → push both for landed and model_result
    sc = build_scorecard_from_detail(_detail(home_score=5, away_score=3, picks=[_totals(0.55, 0.50, 8.0)]))
    m = sc.markets[0]
    assert m.landed == "push" and m.model_result == "push"


def test_totals_missing_line_leaves_result_none():
    sc = build_scorecard_from_detail(_detail(picks=[_totals(0.55, 0.50, None)]))
    m = sc.markets[0]
    assert m.landed is None and m.model_result is None and m.final_total == 8


# ── multi-market shape ──────────────────────────────────────────────────────

def test_both_markets_present_h2h_first():
    sc = build_scorecard_from_detail(_detail(
        home_score=5, away_score=3,
        picks=[_totals(0.55, 0.50, 8.5), _h2h(0.62, 0.58)],
    ))
    assert [m.market_type for m in sc.markets] == ["h2h", "totals"]
    assert sc.home_team == "HOM" and sc.away_team == "AWY"
    assert sc.home_team_name == "Home Team" and sc.away_team_name == "Away Team"
    assert sc.game_pk == 1 and sc.game_date == "2026-07-01"


def test_duplicate_market_rows_graded_once():
    # a stray duplicate h2h row must not double-grade
    sc = build_scorecard_from_detail(_detail(picks=[_h2h(0.62, 0.58), _h2h(0.10, 0.10)]))
    assert len([m for m in sc.markets if m.market_type == "h2h"]) == 1


def test_missing_model_prob_yields_none_result_not_crash():
    sc = build_scorecard_from_detail(_detail(picks=[_h2h(None, 0.58)]))
    m = sc.markets[0]
    assert m.model_side is None and m.model_result is None
    # market side still graded
    assert m.market_side == "home"


# ── HONEST-FRAMING GUARD (mirrors the E5.5 / E9.42 scan) ────────────────────

# Language that implies profitability / a bet recommendation. The scorecard is a
# factual "who called it" surface — E5.4 proved no cashable edge, so any of these
# on this surface is a trust violation and fails the build. (Parallel to the
# K-projection scan in test_k_projection_serving.py; the scorecard carries its own
# factual disclaimer copy rather than the K-projection wording.)
_BANNED = [
    r"\+ev\b", r"\bev\b", r"value play", r"value bet", r"bet this", r"\bedge\b",
    r"win[\s\-]?rate", r"\bprofit\b", r"profitable", r"\bcash(able)?\b", r"\block\b",
    r"smash", r"hammer", r"guaranteed", r"sure thing", r"lay the", r"take the over",
]
_BANNED_RE = re.compile("|".join(_BANNED), re.IGNORECASE)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCORECARD_COMPONENT = _REPO_ROOT / "frontend" / "components" / "game-scorecard.tsx"


def test_scorecard_component_has_no_bet_rec_language():
    if not _SCORECARD_COMPONENT.exists():
        pytest.skip("game-scorecard.tsx not present in this checkout")
    src = _SCORECARD_COMPONENT.read_text(encoding="utf-8")
    hits = sorted({m.group(0) for m in _BANNED_RE.finditer(src)})
    assert not hits, f"banned profitability language in game-scorecard.tsx: {hits}"
    # Must affirmatively disclaim betting advice (a factual results surface).
    assert "not betting advice" in src.lower()
