"""E9.26 — canonical performance-metric semantics + honest-framing guard.

Locks the ONE definition of "correct" / record / win-rate so every surface means
the same thing:
  * model & market pick = the side the probability favors (>= 0.5 → home/over)
  * per market_type, NEVER combined (the E9.40 doubled-tally bug class)
  * pushes excluded from the rate denominator
  * small-sample flag below SMALL_SAMPLE_N decisive calls
and extends the honest-framing (`best_alpha = 0`) banned-language scan to the new
metric surfaces + copy.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.backend.models.picks import GameScorecard, MarketScorecard
from app.backend.services import metric_semantics as ms
from app.backend.services.scorecard import build_scorecard_from_detail, build_scorecard_summary


# ── the pick rule ────────────────────────────────────────────────────────────

def test_pick_side_ge_half_is_home_over():
    assert ms.pick_side("h2h", 0.5) == "home"
    assert ms.pick_side("h2h", 0.49) == "away"
    assert ms.pick_side("totals", 0.5) == "over"
    assert ms.pick_side("totals", 0.4999) == "under"


def test_pick_side_none_prob_is_none():
    # abstain / missing prob never silently counts as a pick
    assert ms.pick_side("h2h", None) is None
    assert ms.pick_side("spread", 0.9) is None


def test_oriented_prob_flips_for_away_under():
    assert ms.oriented_prob(0.6, "home") == pytest.approx(0.6)
    assert ms.oriented_prob(0.6, "away") == pytest.approx(0.4)
    assert ms.oriented_prob(None, "home") is None


# ── grading + record ─────────────────────────────────────────────────────────

def test_grade_and_landed():
    assert ms.grade_h2h("home", 5, 3) == "win"
    assert ms.grade_h2h("away", 5, 3) == "loss"
    assert ms.totals_landed(9, 8.5) == "over"
    assert ms.totals_landed(8, 8.0) == "push"
    assert ms.grade_totals("over", "push") == "push"


def test_record_excludes_pushes_from_denominator():
    rec = ms.record_from_tally({"wins": 6, "losses": 4, "pushes": 3})
    assert rec["decisive"] == 10  # pushes NOT in denominator
    assert rec["win_rate"] == pytest.approx(0.6)
    assert rec["pushes"] == 3


def test_record_none_rate_when_no_decisive():
    rec = ms.record_from_tally({"wins": 0, "losses": 0, "pushes": 5})
    assert rec["win_rate"] is None
    assert rec["low_sample"] is True


def test_low_sample_flag_at_threshold():
    below = ms.record_from_tally({"wins": ms.SMALL_SAMPLE_N - 1, "losses": 0, "pushes": 0})
    at = ms.record_from_tally({"wins": ms.SMALL_SAMPLE_N, "losses": 0, "pushes": 0})
    assert below["low_sample"] is True
    assert at["low_sample"] is False


# ── aggregation: per market, never combined ──────────────────────────────────

def _sc(markets):
    return GameScorecard(status="Final", markets=markets)


def test_aggregate_never_combines_markets():
    # 2 games, each with an h2h + totals call. A combined tally would read 4/4 in one
    # bucket (the E9.40 doubled bug); the canonical output keeps them separate.
    games = [
        _sc([
            MarketScorecard(market_type="h2h", model_result="win", market_result="win"),
            MarketScorecard(market_type="totals", model_result="loss", market_result="win"),
        ]),
        _sc([
            MarketScorecard(market_type="h2h", model_result="loss", market_result="loss"),
            MarketScorecard(market_type="totals", model_result="win", market_result="push"),
        ]),
    ]
    agg = ms.aggregate_scorecard_records(games)
    assert set(agg.keys()) == {"h2h", "totals"}
    assert agg["h2h"]["model"]["wins"] == 1 and agg["h2h"]["model"]["losses"] == 1
    assert agg["h2h"]["model"]["decisive"] == 2
    # totals: model 1W-1L; market win/push → 1 decisive win, 1 push excluded
    assert agg["totals"]["model"]["decisive"] == 2
    assert agg["totals"]["market"]["decisive"] == 1
    assert agg["totals"]["market"]["pushes"] == 1
    # h2h listed before totals
    assert list(agg.keys()) == ["h2h", "totals"]


def test_summary_parity_with_client_tally_semantics():
    # build_scorecard_summary must match a hand tally: per market, pushes excluded.
    games = [
        _sc([MarketScorecard(market_type="h2h", model_result="win", market_result="loss")]),
        _sc([MarketScorecard(market_type="h2h", model_result="push", market_result="win")]),
        _sc([MarketScorecard(market_type="h2h", model_result="loss", market_result="win")]),
    ]
    summary = build_scorecard_summary(games)
    h2h = next(m for m in summary.markets if m.market_type == "h2h")
    assert h2h.model.wins == 1 and h2h.model.losses == 1 and h2h.model.pushes == 1
    assert h2h.model.decisive == 2                     # push excluded
    assert h2h.market.wins == 2 and h2h.market.decisive == 3
    assert summary.n_games == 3
    assert summary.small_sample_n == ms.SMALL_SAMPLE_N


def test_summary_matches_scorecard_grading_end_to_end():
    # Same convention as scorecard.build_scorecard_from_detail — grade then aggregate.
    detail = {
        "game_score": {"status": "Final", "home_score": 6, "away_score": 2},
        "picks": [
            {"market_type": "h2h", "model_prob": 0.62, "bovada_devig_prob": 0.55},
            {"market_type": "totals", "model_prob": 0.40, "bovada_devig_prob": 0.5,
             "market_total_line": 7.5},
        ],
    }
    sc = build_scorecard_from_detail(detail)
    summary = build_scorecard_summary([sc])
    h2h = next(m for m in summary.markets if m.market_type == "h2h")
    assert h2h.model.wins == 1                          # model called home, home won 6-2
    totals = next(m for m in summary.markets if m.market_type == "totals")
    assert totals.model.losses == 1                     # model leaned under, total 8 > 7.5


# ── HONEST-FRAMING GUARD across the new metric surfaces ──────────────────────

_BANNED = [
    r"\+ev\b", r"value play", r"value bet", r"bet this", r"\bedge\b",
    r"\bprofit\b", r"profitable", r"\bcash(able)?\b", r"\block\b",
    r"smash", r"hammer", r"guaranteed", r"sure thing", r"lay the", r"take the over",
    r"beat the book", r"can't lose", r"free money",
]
_BANNED_RE = re.compile("|".join(_BANNED), re.IGNORECASE)

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The canonical record/win-rate/ROI metric-definition surfaces authored for E9.26.
# (The bet-log page is intentionally NOT scanned whole: it carries legitimate
# pre-existing per-pick "Edge" model-output labels unrelated to the record copy.
# Its E9.26 tile copy — "excl. pushes", "realized, net of vig" — is asserted below.)
_METRIC_SURFACES = [
    "app/backend/services/metric_semantics.py",
    "frontend/lib/metrics.ts",
    "frontend/components/game-scorecard.tsx",
    "quant_sports_intel_models/baseball/ablation_results/calibration_e9_26.md",
    "scripts/compute_calibration_artifact_e9_26.py",
]


@pytest.mark.parametrize("rel", _METRIC_SURFACES)
def test_metric_surface_has_no_bet_rec_language(rel):
    path = _REPO_ROOT / rel
    if not path.exists():
        pytest.skip(f"{rel} not present in this checkout")
    src = path.read_text(encoding="utf-8")
    hits = sorted({m.group(0) for m in _BANNED_RE.finditer(src)})
    assert not hits, f"banned profitability language in {rel}: {hits}"


def test_bet_log_summary_tiles_honest_framing():
    """The bet-log summary tiles must carry the honest sample-size / vig framing."""
    path = _REPO_ROOT / "frontend" / "app" / "bet-log" / "page.tsx"
    if not path.exists():
        pytest.skip("bet-log/page.tsx not present")
    src = path.read_text(encoding="utf-8")
    assert "excl. pushes" in src          # win rate excludes pushes (canonical)
    assert "realized, net of vig" in src  # ROI framed as realized settlement
    assert "Small sample" in src          # small-N caveat present
