"""test_tb_projection_serving.py — Edge Program E5.9 batter TOTAL-BASES projection payload.

Covers: the exact pmf reads (quantile grid, moments, P(TB ≥ k)), the EXPLICIT half-vs-integer
push convention at book lines (the E5.9 AC — the Phase-2 research grading excluded integer
lines; serving must price them three-way), the per-book model-vs-market comparison row (de-vig
+ neutral deltas, NO edge/EV field), the payload/index assembly with the version stamp
(PROD-STATE-1 Class A) and the regular-season posture, and — the crux — the HONEST-FRAMING
guard over the pure module's prose AND every shipped frontend surface (best_alpha=0).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

from betting_ml.utils import tb_projection_serving as tbs
from betting_ml.utils.tb_projection_serving import (
    CALIBRATION_NOTE,
    CAPTION,
    DISCLAIMER,
    MODEL_VERSION,
    book_comparison_row,
    build_index_payload,
    build_tb_projection_payload,
    comparisons_from_pmf,
    index_row,
    pmf_line_probabilities,
    pmf_mean_std,
    pmf_p_ge,
    pmf_quantile_grid,
    summarize_distribution,
)

_QUANTILES = tuple(round(q, 2) for q in np.arange(0.05, 0.96, 0.05))


def _toy_pmf(K: int = 6) -> np.ndarray:
    """A small, exactly-normalized discrete predictive on 0..K."""
    p = np.array([0.35, 0.30, 0.18, 0.10, 0.04, 0.02, 0.01], float)[: K + 1]
    return p / p.sum()


# ── pmf reads ───────────────────────────────────────────────────────────────

def test_pmf_refuses_non_normalized():
    with pytest.raises(ValueError, match="sum to 1"):
        pmf_line_probabilities(np.array([0.5, 0.3]), 1.5)  # sums to 0.8


def test_pmf_mean_std_exact():
    p = np.array([0.5, 0.5])
    mean, std = pmf_mean_std(p)
    assert mean == pytest.approx(0.5)
    assert std == pytest.approx(0.5)


def test_pmf_quantile_grid_monotone_and_correct():
    p = _toy_pmf()
    grid = pmf_quantile_grid(p, [0.05, 0.5, 0.95])
    assert grid == sorted(grid)
    cdf = np.cumsum(p)
    assert cdf[grid[1]] >= 0.5 and (grid[1] == 0 or cdf[grid[1] - 1] < 0.5)


def test_pmf_p_ge():
    p = _toy_pmf()
    assert pmf_p_ge(p, 0) == 1.0
    assert pmf_p_ge(p, 1) == pytest.approx(1.0 - p[0])
    assert pmf_p_ge(p, 2) == pytest.approx(1.0 - p[0] - p[1])
    assert pmf_p_ge(p, 99) == 0.0


# ── the push convention (the AC) ────────────────────────────────────────────

def test_half_line_probabilities_no_push():
    p = _toy_pmf()
    cdf = np.cumsum(p)
    out = pmf_line_probabilities(p, 1.5)
    assert out["p_push"] == 0.0
    assert out["p_over"] == pytest.approx(1.0 - cdf[1])
    assert out["p_under"] == pytest.approx(cdf[1])
    assert out["p_over"] + out["p_under"] + out["p_push"] == pytest.approx(1.0)


def test_integer_line_probabilities_explicit_push():
    p = _toy_pmf()
    cdf = np.cumsum(p)
    out = pmf_line_probabilities(p, 2.0)
    assert out["p_push"] == pytest.approx(p[2])
    assert out["p_over"] == pytest.approx(1.0 - cdf[2])
    assert out["p_under"] == pytest.approx(cdf[1])
    assert out["p_over"] + out["p_under"] + out["p_push"] == pytest.approx(1.0)


def test_integer_line_zero_has_no_under():
    out = pmf_line_probabilities(_toy_pmf(), 0.0)
    assert out["p_under"] == 0.0
    assert out["p_push"] == pytest.approx(_toy_pmf()[0])


def test_line_beyond_cap_clamps():
    p = _toy_pmf()
    out = pmf_line_probabilities(p, 99.5)
    assert out["p_over"] == pytest.approx(0.0, abs=1e-12)
    assert out["p_under"] == pytest.approx(1.0)


# ── comparison rows (no edge/EV — honest framing) ───────────────────────────

def test_book_comparison_row_devig_and_delta():
    p = _toy_pmf()
    row = book_comparison_row("draftkings", 1.5, -120, +100, p, model_mean=1.3)
    assert row["is_integer_line"] is False
    assert 0.0 < row["book_implied_p_over"] < 1.0
    assert row["model_vs_book_p_over"] == pytest.approx(
        row["model_p_over"] - row["book_implied_p_over"], abs=1e-3)
    assert row["model_mean_minus_line"] == pytest.approx(1.3 - 1.5, abs=1e-9)


def test_book_comparison_row_has_no_edge_or_ev_fields():
    row = book_comparison_row("fanduel", 2.0, -110, -110, _toy_pmf(), model_mean=1.4)
    forbidden_keys = {"edge_over", "edge_under", "best_edge", "best_ev",
                      "ev_over", "ev_under", "edge", "ev", "kelly", "stake"}
    assert forbidden_keys.isdisjoint(row.keys())


def test_book_comparison_row_one_sided_quote_is_nan_safe():
    row = book_comparison_row("caesars", 1.5, -115, None, _toy_pmf(), model_mean=None)
    assert row["book_implied_p_over"] is None  # one-sided → cannot de-vig, never 50/50
    assert row["model_vs_book_p_over"] is None
    assert row["model_p_over"] is not None
    json.dumps(row)


def test_comparisons_from_pmf():
    rows = comparisons_from_pmf(_toy_pmf(), [
        {"book": "a", "line": 1.5, "over_odds": -110, "under_odds": -110},
        {"book": "b", "line": 2.0, "over_odds": +105, "under_odds": -125},
    ], model_mean=1.4)
    assert [r["book"] for r in rows] == ["a", "b"]
    assert rows[1]["is_integer_line"] is True
    assert rows[1]["model_p_push"] > 0


# ── payload + index ─────────────────────────────────────────────────────────

def _payload(**over):
    kw = dict(
        batter_id=660271, full_name="Shohei Ohtani", team="Los Angeles Dodgers",
        opponent="San Diego Padres", game_pk=812345, game_date="2026-08-14",
        quantile_levels=_QUANTILES, pmf=np.append(_toy_pmf(), np.zeros(18)) / 1.0,
        book_comparisons=comparisons_from_pmf(
            np.append(_toy_pmf(), np.zeros(18)),
            [{"book": "dk", "line": 1.5, "over_odds": -120, "under_odds": +100}],
            model_mean=1.3),
        batting_slot=1, game_datetime="2026-08-15T02:10:00Z",
        model_fit_date="2026-08-14", generated_at="2026-08-14T00:00:00Z",
    )
    kw.update(over)
    return build_tb_projection_payload(**kw)


def test_payload_version_stamp_and_posture():
    p = _payload()
    # PROD-STATE-1 Class A: the version stamp travels with EVERY payload.
    assert p["model_version"] == MODEL_VERSION == "batter_tb_glm_nb_v1"
    assert p["model_fit_date"] == "2026-08-14"
    assert p["best_alpha"] == 0
    assert p["is_bet_recommendation"] is False
    assert p["regular_season_only"] is True
    assert p["caption"] == CAPTION and p["disclaimer"] == DISCLAIMER
    assert p["primary_line"] == 1.5
    json.dumps(p)  # serialisable


def test_payload_distribution_shape():
    d = _payload()["distribution"]
    assert len(d["quantile_levels"]) == len(d["tb_quantile_grid"]) == 19
    assert set(d["p_ge"].keys()) == {"1", "2", "3", "4"}
    assert d["p05"] == d["tb_quantile_grid"][0]
    assert d["p95"] == d["tb_quantile_grid"][-1]
    assert d["median"] is not None


def test_index_row_and_payload():
    p = _payload()
    r = index_row(p)
    assert r["batter_id"] == 660271
    assert r["primary_line"] == 1.5
    assert r["p_ge_2"] == p["distribution"]["p_ge"]["2"]
    assert r["book_count"] == 1
    idx = build_index_payload([r], game_date="2026-08-14", model_fit_date="2026-08-14")
    assert idx["count"] == 1 and idx["batters"][0] is r
    assert idx["best_alpha"] == 0 and idx["is_bet_recommendation"] is False
    assert idx["regular_season_only"] is True
    assert idx["model_version"] == MODEL_VERSION
    json.dumps(idx)


def test_index_sorts_by_mean_desc():
    rows = [{"mean": 1.0}, {"mean": 2.5}, {"mean": None}, {"mean": 1.7}]
    idx = build_index_payload(rows, game_date=None)
    means = [r["mean"] for r in idx["batters"]]
    assert means == [2.5, 1.7, 1.0, None]


# ── HONEST-FRAMING GUARD (the crux of E5.9) ─────────────────────────────────

# Same banned list as the E5.5 K surface: any of these on a best_alpha=0 surface is a trust
# violation. The calibration claim is the ONLY allowed strong claim, and it must stay a
# calibration statement (no beat-the-market / edge / pick language).
_BANNED = [
    r"\+ev\b", r"\bev\b", r"value play", r"value bet", r"bet this", r"\bedge\b",
    r"win[\s\-]?rate", r"\bprofit\b", r"profitable", r"\bcash(able)?\b", r"\block\b",
    r"smash", r"hammer", r"guaranteed", r"sure thing", r"lay the", r"take the over",
    r"beat the market", r"best bets?", r"systematically off",
]
_BANNED_RE = re.compile("|".join(_BANNED), re.IGNORECASE)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_SURFACES = [
    _REPO_ROOT / "frontend" / "components" / "batter-tb-projection.tsx",
    _REPO_ROOT / "frontend" / "app" / "props" / "batter" / "[batterId]" / "page.tsx",
    _REPO_ROOT / "frontend" / "app" / "props" / "page.tsx",
]


def test_prose_constants_are_honest():
    text = f"{CAPTION}\n{DISCLAIMER}\n{CALIBRATION_NOTE}"
    hit = _BANNED_RE.search(text)
    assert hit is None, f"banned profitability language in surface prose: {hit!r}"
    low = DISCLAIMER.lower()
    assert "not betting advice" in low
    assert "no profitability claim" in low
    # regular-season boundary must be disclosed on the surface prose
    assert "regular-season" in low or "regular season" in low
    # the calibration note stays a calibration statement, not an edge claim
    assert "calibration" in CALIBRATION_NOTE.lower()
    assert "not betting advice" in CALIBRATION_NOTE.lower()


@pytest.mark.parametrize("surface", _FRONTEND_SURFACES, ids=lambda p: p.name)
def test_frontend_surface_has_no_bet_rec_language(surface):
    """Every shipped TB-projection surface must carry no +EV / edge / win-rate / bet-rec
    wording; the component must surface the projection-not-advice disclaimer copy."""
    if not surface.exists():
        pytest.skip(f"{surface} not present in this checkout")
    src = surface.read_text(encoding="utf-8")
    hits = sorted({m.group(0) for m in _BANNED_RE.finditer(src)})
    assert not hits, f"banned profitability language in {surface.name}: {hits}"
    if surface.name == "batter-tb-projection.tsx":
        assert "not betting advice" in src.lower()
