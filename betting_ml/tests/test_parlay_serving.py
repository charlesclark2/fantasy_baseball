"""test_parlay_serving.py — Edge Program E10.1 parlay decision-support CALCULATOR (honest MVP).

Covers the pure parlay math (odds conversions, TRUE combined probability with same-game Gaussian-copula
correlation adjustment, book-implied + expected value from the parlay price, the factual verdict), the
backend leg-resolution logic (serving-cache-sourced, graceful on a leg with no model prob), and — the
crux of E10.1 — the HONEST-FRAMING guard: NO "+EV" / "value play" / "edge" / win-rate / bet-rec
language on the surface (the pure module's prose + generated verdicts AND the shipped frontend page),
with best_alpha=0 / is_bet_recommendation=False travelling with every payload.

Neutral vocabulary note: "expected value" and "−EV" ARE the honest, factual language of THIS
calculation (the story's own verdict example uses them), so — unlike the K-projection surface — the
bare tokens `ev` / `value` are NOT banned here; the promotional framings ("+EV" as a sell, "value
play/bet", "edge", "lock", "smash", win-rate, "profitable") are.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.backend.services import parlay_calc as pm
from app.backend.services.parlay_calc import (
    CAPTION,
    DISCLAIMER,
    american_to_decimal,
    american_to_implied_prob,
    build_verdict,
    combined_decimal_odds,
    combined_true_probability,
    copula_joint_probability,
    decimal_to_implied,
    evaluate_parlay,
    expected_value_per_dollar,
    oriented_hit_prob,
    resolve_parlay_price,
)


# ── odds conversions ─────────────────────────────────────────────────────────

def test_american_to_decimal():
    assert american_to_decimal(150) == pytest.approx(2.5)
    assert american_to_decimal(-120) == pytest.approx(1.833333, abs=1e-5)
    assert american_to_decimal(100) == pytest.approx(2.0)
    assert american_to_decimal(None) is None


def test_decimal_and_implied_roundtrip():
    assert decimal_to_implied(2.0) == pytest.approx(0.5)
    assert american_to_implied_prob(-110) == pytest.approx(0.5238, abs=1e-3)
    assert american_to_implied_prob(None) is None


def test_combined_decimal_cross_game():
    # −110 × −110 ≈ 1.909 × 1.909 ≈ 3.645
    assert combined_decimal_odds([-110, -110]) == pytest.approx(3.6446, abs=1e-3)
    assert combined_decimal_odds([-110, None]) is None  # a missing leg price → no computed price


# ── true combined probability: independence vs same-game copula ───────────────

def test_cross_game_is_independent_product():
    legs = [
        {"game_pk": 1, "market_type": "h2h", "side": "home", "hit_prob": 0.6},
        {"game_pk": 2, "market_type": "totals", "side": "over", "hit_prob": 0.5},
    ]
    out = combined_true_probability(legs)
    assert out["combined_prob"] == pytest.approx(0.30, abs=1e-6)
    assert out["naive_product"] == pytest.approx(0.30, abs=1e-6)
    assert out["has_same_game"] is False
    assert all(g["correlation_source"] == "independent" for g in out["groups"])


def test_same_game_is_correlation_adjusted_below_naive():
    """The crux: a same-game parlay's true prob is NEVER the naive product, and the conservative
    prior keeps it at/below independence — never overstated in the user's favour."""
    legs = [
        {"game_pk": 7, "market_type": "h2h", "side": "home", "hit_prob": 0.60},
        {"game_pk": 7, "market_type": "totals", "side": "over", "hit_prob": 0.50},
    ]
    out = combined_true_probability(legs)
    grp = out["groups"][0]
    assert grp["is_same_game"] is True
    assert grp["correlation_source"] == "conservative_prior"
    assert grp["is_correlation_estimated"] is True
    # correlation-adjusted joint strictly below the naive independent product
    assert out["combined_prob"] < out["naive_product"]
    assert grp["naive_product"] == pytest.approx(0.30, abs=1e-6)
    assert out["has_same_game"] is True


def test_copula_joint_bounds_and_monotonicity():
    # joint ≤ min(p_i), ≥ 0
    j = copula_joint_probability([0.6, 0.5])
    assert 0.0 <= j <= 0.5
    # positive prior → joint above independence; negative → below
    pos = copula_joint_probability([0.6, 0.5], rho=0.4)
    neg = copula_joint_probability([0.6, 0.5], rho=-0.4)
    assert neg < 0.30 < pos
    # single leg → itself
    assert copula_joint_probability([0.42]) == pytest.approx(0.42)


def test_three_leg_same_game_positive_definite():
    # rho below −1/(n−1) must be clamped so the matrix stays PD (no crash, valid prob)
    j = copula_joint_probability([0.5, 0.5, 0.5], rho=-0.9)
    assert 0.0 <= j <= 0.5


# ── expected value + price resolution ─────────────────────────────────────────

def test_expected_value_formula():
    # true 0.30 at decimal 3.0 → 0.30×3 − 1 = −0.10
    assert expected_value_per_dollar(0.30, 3.0) == pytest.approx(-0.10, abs=1e-9)
    assert expected_value_per_dollar(0.40, 3.0) == pytest.approx(0.20, abs=1e-9)
    assert expected_value_per_dollar(None, 3.0) is None
    assert expected_value_per_dollar(0.3, None) is None


def test_price_resolution_paths():
    # cross-game, no user price → computed from leg odds
    p = resolve_parlay_price([-110, -110], has_same_game=False, user_parlay_american=None)
    assert p["source"] == "computed_cross_game" and p["decimal"] is not None
    # same-game, no user price → unavailable (SGP priced by the book)
    p2 = resolve_parlay_price([-110, -110], has_same_game=True, user_parlay_american=None)
    assert p2["source"] == "unavailable_same_game" and p2["decimal"] is None and p2["note"]
    # user-entered price always wins
    p3 = resolve_parlay_price([-110, -110], has_same_game=True, user_parlay_american=265)
    assert p3["source"] == "user_entered" and p3["decimal"] == pytest.approx(3.65, abs=1e-2)
    # cross-game but a leg price missing → unavailable
    p4 = resolve_parlay_price([-110, None], has_same_game=False, user_parlay_american=None)
    assert p4["source"] == "unavailable_missing_leg_odds"


def test_oriented_hit_prob():
    assert oriented_hit_prob("h2h", "home", 0.55) == pytest.approx(0.55)
    assert oriented_hit_prob("h2h", "away", 0.55) == pytest.approx(0.45)
    assert oriented_hit_prob("totals", "under", 0.52) == pytest.approx(0.48)
    assert oriented_hit_prob("strikeouts", "over", 0.61) == pytest.approx(0.61)
    assert oriented_hit_prob("h2h", "home", None) is None
    assert oriented_hit_prob("h2h", "bogus", 0.5) is None


# ── full evaluate payload ─────────────────────────────────────────────────────

def test_evaluate_cross_game_full():
    legs = [
        {"game_pk": 1, "market_type": "h2h", "side": "home", "hit_prob": 0.55, "book_odds_american": -120, "label": "A"},
        {"game_pk": 2, "market_type": "totals", "side": "over", "hit_prob": 0.52, "book_odds_american": -105, "label": "B"},
    ]
    r = evaluate_parlay(legs)
    assert r["combined_true_prob"] == pytest.approx(0.286, abs=1e-3)
    assert r["parlay_price_source"] == "computed_cross_game"
    assert r["book_implied_prob"] is not None
    assert r["expected_value_per_dollar"] is not None
    assert r["best_alpha"] == 0 and r["is_bet_recommendation"] is False
    assert r["has_same_game"] is False
    json.dumps(r)  # serialisable


def test_evaluate_same_game_needs_user_price():
    legs = [
        {"game_pk": 7, "market_type": "h2h", "side": "home", "hit_prob": 0.60, "book_odds_american": -140, "label": "H"},
        {"game_pk": 7, "market_type": "totals", "side": "over", "hit_prob": 0.50, "book_odds_american": -110, "label": "O"},
    ]
    r = evaluate_parlay(legs)  # no user price → EV can't be computed
    assert r["has_same_game"] is True
    assert r["parlay_decimal_odds"] is None
    assert r["expected_value_per_dollar"] is None
    assert any("same-game" in f.lower() for f in r["flags"])
    # with the user-entered book parlay price → EV computes
    r2 = evaluate_parlay(legs, user_parlay_american=260)
    assert r2["parlay_price_source"] == "user_entered"
    assert r2["expected_value_per_dollar"] is not None
    assert r2["combined_true_prob"] < r2["naive_independent_prob"]  # correlation-adjusted


def test_evaluate_unresolved_leg_is_excluded_gracefully():
    legs = [
        {"game_pk": 1, "market_type": "h2h", "side": "home", "hit_prob": 0.55, "book_odds_american": -120, "label": "A"},
        {"game_pk": 2, "market_type": "totals", "side": "over", "hit_prob": None, "book_odds_american": -110, "label": "no-prob"},
    ]
    r = evaluate_parlay(legs)
    assert r["resolved_leg_count"] == 1
    assert r["combined_true_prob"] == pytest.approx(0.55, abs=1e-6)  # only the resolved leg counts
    assert any("no served model probability" in f for f in r["flags"])
    # the unresolved leg still appears, flagged not-resolved
    assert any(l["resolved"] is False for l in r["legs"])


# ── HONEST-FRAMING GUARD (the crux of E10.1) ─────────────────────────────────

# Promotional / bet-recommendation framings banned from the parlay surface. NOTE (deliberate): bare
# "ev" and "value" are NOT here — "expected value" / "−EV" are the neutral, factual vocabulary of the
# calculation (the story's verdict example uses them). E10.3 (+EV recommender) is hard-gated behind a
# proven edge we do NOT have, so any of these on this surface is a trust violation → the build fails.
_BANNED = [
    r"\+ev\b", r"value play", r"value bet", r"bet this", r"\bedge\b",
    r"win[\s\-]?rate", r"\bprofit\b", r"profitable", r"\bcash(able)?\b", r"\block\b",
    r"smash", r"hammer", r"guaranteed", r"sure thing", r"lay the", r"take the over",
    r"best bet", r"good bet", r"can't lose", r"free money",
]
_BANNED_RE = re.compile("|".join(_BANNED), re.IGNORECASE)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_SURFACES = [
    _REPO_ROOT / "frontend" / "app" / "parlay" / "page.tsx",
]


def test_caption_and_disclaimer_are_honest():
    text = f"{CAPTION}\n{DISCLAIMER}"
    hit = _BANNED_RE.search(text)
    assert hit is None, f"banned profitability language in caption/disclaimer: {hit!r}"
    low = DISCLAIMER.lower()
    assert "not betting advice" in low
    assert "no profitability claim" in low
    assert "most parlays are negative expected value" in low


def test_generated_verdicts_are_honest():
    """Every branch of the plain-language verdict must be free of promotional / bet-rec framing."""
    cases = [
        build_verdict(None, None, None),
        build_verdict(0.30, None, None),                 # price not entered yet
        build_verdict(0.30, 0.279, -0.10),               # −EV
        build_verdict(0.40, 0.30, 0.20),                 # ≥0 EV, reported factually
        build_verdict(0.333, 0.333, 0.0),                # break-even
    ]
    for v in cases:
        hit = _BANNED_RE.search(v)
        assert hit is None, f"banned language in verdict {v!r}: {hit!r}"
    # even the positive-EV verdict must NOT recommend
    pos = build_verdict(0.40, 0.30, 0.20)
    assert "not a recommendation" in pos.lower()
    # the honest tail is always present
    for v in cases[1:]:
        assert "most parlays are negative expected value" in v.lower()


@pytest.mark.parametrize("surface", _FRONTEND_SURFACES, ids=lambda p: p.name)
def test_frontend_surface_has_no_bet_rec_language(surface):
    if not surface.exists():
        pytest.skip(f"{surface.name} not present in this checkout")
    src = surface.read_text(encoding="utf-8")
    hits = sorted({m.group(0) for m in _BANNED_RE.finditer(src)})
    assert not hits, f"banned profitability language in {surface.name}: {hits}"
    assert "not betting advice" in src.lower()
    assert "not a bet recommendation" in src.lower()


# ── backend leg-resolution (serving-cache-sourced, book-aware, graceful) ─────

# A representative picks/book-odds blob: Bovada + FanDuel (US) + Pinnacle (sharp ref). FanDuel posts
# the total at a different line (9.0) than Bovada/consensus (8.5), so its model P(over) differs.
_BOOK_BLOB = {
    "h2h": [
        {"book_key": "bovada", "book_name": "Bovada", "home_american": -140, "away_american": 120,
         "market_bet_pct_home": 0.585, "model_prob_home": 0.62},
        {"book_key": "pinnacle", "book_name": "Pinnacle", "is_sharp_reference": True,
         "home_american": -150, "away_american": 130, "market_bet_pct_home": 0.60, "model_prob_home": 0.62},
    ],
    "totals": [
        {"book_key": "bovada", "book_name": "Bovada", "line": 8.5, "over_american": -110,
         "under_american": -110, "market_bet_pct_over": 0.50, "model_prob_over": 0.48, "model_prob_under": 0.52},
        {"book_key": "fanduel", "book_name": "FanDuel", "line": 9.0, "over_american": 105,
         "under_american": -125, "market_bet_pct_over": 0.46, "model_prob_over": 0.41, "model_prob_under": 0.59},
    ],
}

# A pitcher K detail blob: two books at the primary line (5.5) + one at a different line (6.5) that
# must NOT auto-fill at the primary line.
_K_DETAIL = {"book_comparisons": [
    {"book": "bovada", "line": 5.5, "over_odds": -115, "under_odds": -105,
     "book_implied_p_over": 0.53, "model_p_over": 0.61, "model_p_under": 0.39},
    {"book": "draftkings", "line": 5.5, "over_odds": -110, "under_odds": -110,
     "book_implied_p_over": 0.50, "model_p_over": 0.61, "model_p_under": 0.39},
    {"book": "fanduel", "line": 6.5, "over_odds": 120, "under_odds": -140,
     "book_implied_p_over": 0.44, "model_p_over": 0.47, "model_p_under": 0.53},
]}


def test_router_resolves_legs_from_serving_cache(monkeypatch):
    """The /parlay/evaluate resolution re-derives each leg's model prob from the cached blobs and
    orients it to the chosen side; a leg absent from the cache resolves gracefully (excluded)."""
    from app.backend.routers import parlay as pr
    from app.backend.models.parlay import ParlayEvaluateRequest, ParlayLegInput

    picks = [
        {"game_pk": 1, "market_type": "h2h", "model_prob": 0.62, "home_team": "NYY", "away_team": "BOS"},
        {"game_pk": 1, "market_type": "totals", "model_prob": 0.48, "market_total_line": 8.5},
    ]
    kidx = [{"pitcher_id": 543, "game_pk": 1, "primary_line": 5.5, "model_p_over": 0.61, "full_name": "Ace"}]
    monkeypatch.setattr(pr, "_picks_blob", lambda date: picks)
    monkeypatch.setattr(pr, "_k_index", lambda date: kidx)
    monkeypatch.setattr(pr, "_book_odds_blob", lambda gp: _BOOK_BLOB)
    monkeypatch.setattr(pr, "_k_detail_blob", lambda pid, d: _K_DETAIL)

    req = ParlayEvaluateRequest(
        date="2026-07-10",
        parlay_odds_american=None,
        legs=[
            # h2h away, no odds sent → backend fills from the selected book (bovada away +120)
            ParlayLegInput(game_pk=1, market_type="h2h", side="away", book_key="bovada", book_odds_american=None),
            ParlayLegInput(game_pk=1, market_type="strikeouts", side="over", pitcher_id=543, line=5.5, book_odds_american=-115),
            ParlayLegInput(game_pk=99, market_type="h2h", side="home", book_odds_american=-110),  # not in cache
        ],
    )
    r = pr.evaluate_parlay(req, _="user")
    by = {(l["market_type"], l["side"]): l for l in r["legs"]}
    assert by[("h2h", "away")]["hit_prob"] == pytest.approx(0.38, abs=1e-6)   # 1 − 0.62
    assert by[("h2h", "away")]["book_odds_american"] == 120                   # auto-filled from bovada
    assert by[("strikeouts", "over")]["hit_prob"] == pytest.approx(0.61, abs=1e-6)
    assert by[("h2h", "home")]["resolved"] is False                          # game 99 absent → graceful
    assert r["has_same_game"] is True                                        # legs share game_pk 1
    assert r["best_alpha"] == 0 and r["is_bet_recommendation"] is False


def test_router_evaluate_totals_uses_selected_book_line(monkeypatch):
    """A totals leg's model prob is resolved at the SELECTED BOOK's line, not the consensus line."""
    from app.backend.routers import parlay as pr
    from app.backend.models.parlay import ParlayEvaluateRequest, ParlayLegInput

    picks = [{"game_pk": 1, "market_type": "totals", "model_prob": 0.48, "market_total_line": 8.5}]
    monkeypatch.setattr(pr, "_picks_blob", lambda date: picks)
    monkeypatch.setattr(pr, "_k_index", lambda date: [])
    monkeypatch.setattr(pr, "_book_odds_blob", lambda gp: _BOOK_BLOB)

    # FanDuel posts the total at 9.0 with model P(over)=0.41 — distinct from the 8.5 consensus (0.48).
    req = ParlayEvaluateRequest(date="2026-07-10", legs=[
        ParlayLegInput(game_pk=1, market_type="totals", side="over", book_key="fanduel", book_odds_american=None),
    ])
    r = pr.evaluate_parlay(req, _="user")
    leg = r["legs"][0]
    assert leg["hit_prob"] == pytest.approx(0.41, abs=1e-6)   # fanduel line, NOT the 0.48 consensus
    assert leg["line"] == 9.0
    assert leg["book_odds_american"] == 105                   # auto-filled from fanduel over price


def test_router_leg_universe_shape_and_books(monkeypatch):
    from app.backend.routers import parlay as pr

    picks = [
        {"game_pk": 1, "market_type": "h2h", "model_prob": 0.62, "home_team": "NYY", "away_team": "BOS", "game_start_utc": "2026-07-10T23:00:00Z"},
        {"game_pk": 1, "market_type": "totals", "model_prob": 0.48, "market_total_line": 8.5},
    ]
    kidx = [{"pitcher_id": 543, "game_pk": 1, "primary_line": 5.5, "model_p_over": 0.61, "full_name": "Ace"}]
    monkeypatch.setattr(pr, "_picks_blob", lambda date: picks)
    monkeypatch.setattr(pr, "_k_index", lambda date: kidx)
    monkeypatch.setattr(pr, "_book_odds_blob", lambda gp: _BOOK_BLOB)
    monkeypatch.setattr(pr, "_k_detail_blob", lambda pid, d: _K_DETAIL)

    out = pr.get_parlay_legs(date="2026-07-10", _="user")
    assert out["best_alpha"] == 0 and out["is_bet_recommendation"] is False
    # book selector: US books first (bovada default), Pinnacle sharp-ref last; draftkings (K-only) present
    assert out["default_book_key"] == "bovada"
    assert [b["book_key"] for b in out["books"]] == ["bovada", "fanduel", "draftkings", "pinnacle"]
    assert out["books"][-1]["is_sharp_reference"] is True
    game = out["games"][0]
    mkts = {m["market_type"] for m in game["markets"]}
    assert mkts == {"h2h", "totals", "strikeouts"}
    # h2h home side carries per-book odds (bovada -140) + model prob + no-vig book prob
    h2h_home = next(m for m in game["markets"] if m["market_type"] == "h2h")["sides"][0]
    assert h2h_home["books"]["bovada"]["american"] == -140
    assert h2h_home["books"]["bovada"]["book_devig_prob"] == pytest.approx(0.585)
    # totals over carries each book's own line (fanduel 9.0) + model prob at that line
    over = next(m for m in game["markets"] if m["market_type"] == "totals")["sides"][0]
    assert over["books"]["fanduel"]["line"] == 9.0
    assert over["books"]["fanduel"]["model_prob"] == pytest.approx(0.41)
    # strikeouts over carries per-book K odds at the primary line (5.5); the 6.5 book is excluded
    k_over = next(m for m in game["markets"] if m["market_type"] == "strikeouts")["sides"][0]
    assert set(k_over["books"]) == {"bovada", "draftkings"}     # fanduel posts 6.5, not the 5.5 primary
    assert k_over["books"]["bovada"]["american"] == -115
    assert k_over["books"]["bovada"]["line"] == 5.5
    json.dumps(out)  # serialisable


def test_router_strikeout_only_game_recovers_team_names(monkeypatch):
    """A strikeout-only game (no h2h/totals pick) must not render as 'Away @ Home' — team names are
    recovered from the book-odds blob (oriented), else a 'team vs opponent' matchup from the K row."""
    from app.backend.routers import parlay as pr

    monkeypatch.setattr(pr, "_picks_blob", lambda date: [])  # no h2h/totals for either game
    monkeypatch.setattr(pr, "_k_index", lambda date: [
        {"pitcher_id": 11, "game_pk": 1, "primary_line": 5.5, "model_p_over": 0.60,
         "full_name": "Nola", "team": "PHI", "opponent": "ATL", "game_datetime": "2026-07-10T23:00:00Z"},
        {"pitcher_id": 22, "game_pk": 2, "primary_line": 4.5, "model_p_over": 0.66,
         "full_name": "Weathers", "team": "MIA", "opponent": "WSH", "game_datetime": "2026-07-10T23:05:00Z"},
    ])
    monkeypatch.setattr(pr, "_k_detail_blob", lambda pid, d: {})
    # Game 1 has an odds blob (oriented home/away); game 2 has none.
    monkeypatch.setattr(pr, "_book_odds_blob",
                        lambda gp: {"home_team": "ATL", "away_team": "PHI"} if gp == 1 else {})

    out = pr.get_parlay_legs(date="2026-07-10", _="user")
    by_pk = {g["game_pk"]: g for g in out["games"]}
    assert by_pk[1]["home_team"] == "ATL" and by_pk[1]["away_team"] == "PHI"  # oriented from odds blob
    assert by_pk[2]["home_team"] is None and by_pk[2]["matchup"] == "MIA vs WSH"  # K-row fallback


def test_router_evaluate_strikeouts_uses_book_odds(monkeypatch):
    """A strikeouts leg auto-fills the selected book's K price + model P at that book's posted line."""
    from app.backend.routers import parlay as pr
    from app.backend.models.parlay import ParlayEvaluateRequest, ParlayLegInput

    monkeypatch.setattr(pr, "_picks_blob", lambda date: [])
    monkeypatch.setattr(pr, "_k_index", lambda date: [
        {"pitcher_id": 543, "game_pk": 1, "primary_line": 5.5, "model_p_over": 0.61, "full_name": "Ace"}])
    monkeypatch.setattr(pr, "_k_detail_blob", lambda pid, d: _K_DETAIL)

    req = ParlayEvaluateRequest(date="2026-07-11", legs=[
        ParlayLegInput(game_pk=1, market_type="strikeouts", side="over", pitcher_id=543,
                       line=5.5, book_key="draftkings", book_odds_american=None)])
    r = pr.evaluate_parlay(req, _="user")
    leg = r["legs"][0]
    assert leg["book_odds_american"] == -110      # draftkings over at 5.5, auto-filled
    assert leg["hit_prob"] == pytest.approx(0.61, abs=1e-6)
    assert leg["line"] == 5.5
