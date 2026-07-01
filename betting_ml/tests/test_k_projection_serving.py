"""test_k_projection_serving.py — Edge Program E5.5 K-PROJECTION transparency serving payload.

Covers: distribution summary packaging, the per-book model-vs-market COMPARISON row (de-vig + neutral
deltas, with NO edge/EV field), the sample→comparison convenience path, the full payload assembly +
primary-line pick, JSON-serialisability, and — the crux of E5.5 — the HONEST-FRAMING guard: NO
"+EV" / "edge" / "value play" / win-rate language anywhere on this surface (the pure module OR the
shipped frontend component), and the no-bet-rec posture (best_alpha=0, is_bet_recommendation=False)
travelling with every payload.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

from betting_ml.utils import k_projection_serving as kps
from betting_ml.utils.k_projection_serving import (
    CAPTION,
    DISCLAIMER,
    book_comparison_row,
    build_index_payload,
    build_k_projection_payload,
    comparison_from_samples,
    index_row,
    summarize_distribution,
)

_QUANTILES = tuple(round(q, 2) for q in np.arange(0.05, 0.96, 0.05))  # P05..P95, 19 pts (E5.2 grid)


# ── distribution summary ────────────────────────────────────────────────────

def test_summarize_distribution_basic():
    grid = list(range(2, 21))  # 19 ascending values to match the 19 quantile levels
    out = summarize_distribution(_QUANTILES, grid, mean=6.2, std=2.1)
    assert out["quantile_levels"] == [round(q, 4) for q in _QUANTILES]
    assert out["k_quantile_grid"] == grid
    assert out["mean"] == 6.2
    assert out["std"] == 2.1
    assert out["p05"] == grid[0]
    assert out["p95"] == grid[-1]


def test_summarize_distribution_median_from_grid():
    # 0.50 is the 10th of 19 levels (index 9) → its grid value is the median.
    grid = list(range(0, 19))
    out = summarize_distribution(_QUANTILES, grid, mean=None, std=None)
    assert out["median"] == float(grid[9])
    assert out["mean"] is None and out["std"] is None


def test_summarize_distribution_nan_safe():
    out = summarize_distribution(_QUANTILES, list(range(19)), mean=float("nan"), std=float("inf"))
    assert out["mean"] is None and out["std"] is None


# ── per-book comparison row (NO edge/EV) ────────────────────────────────────

def test_book_comparison_row_devig_and_delta():
    # Symmetric −110/−110 → de-vigged P(over) = 0.5 exactly.
    row = book_comparison_row(
        book="bovada", line=5.5, over_american=-110, under_american=-110,
        model_p_over=0.61, model_p_under=0.39, model_p_push=0.0, model_mean=6.2,
    )
    assert row["book"] == "bovada"
    assert row["line"] == 5.5
    assert row["is_integer_line"] is False
    assert row["over_odds"] == -110 and row["under_odds"] == -110
    assert row["book_implied_p_over"] == pytest.approx(0.5, abs=1e-6)
    assert row["model_p_over"] == 0.61
    # transparency delta = model − book no-vig implied
    assert row["model_vs_book_p_over"] == pytest.approx(0.11, abs=1e-6)
    assert row["model_mean_minus_line"] == pytest.approx(0.7, abs=1e-9)


def test_book_comparison_row_has_no_edge_or_ev_fields():
    """Honest framing: the SERVING row must not carry edge / EV / win-prob-style keys."""
    row = book_comparison_row(
        book="fanduel", line=6.0, over_american=120, under_american=-140,
        model_p_over=0.4, model_p_under=0.5, model_p_push=0.1, model_mean=5.8,
    )
    forbidden_keys = {"edge_over", "edge_under", "best_edge", "best_ev",
                      "ev_over", "ev_under", "best_side", "alpha", "win_rate", "roi"}
    assert forbidden_keys.isdisjoint(row.keys())
    assert row["is_integer_line"] is True  # 6.0 integer line


def test_book_comparison_row_missing_price_is_nan_safe():
    row = book_comparison_row(
        book="dk", line=5.5, over_american=None, under_american=-110,
        model_p_over=0.6, model_p_under=0.4, model_p_push=0.0, model_mean=None,
    )
    assert row["book_implied_p_over"] is None
    assert row["model_vs_book_p_over"] is None
    assert row["model_mean_minus_line"] is None
    assert row["over_odds"] is None and row["under_odds"] == -110


def test_comparison_from_samples():
    rng = np.random.default_rng(0)
    samples = rng.poisson(6.0, size=20000)
    book_lines = [
        {"book": "bovada", "line": 5.5, "over_odds": -110, "under_odds": -110},
        {"book": "fanduel", "line": 6.5, "over_odds": 100, "under_odds": -120},
    ]
    rows = comparison_from_samples(samples, book_lines, model_mean=6.0)
    assert len(rows) == 2
    assert rows[0]["book"] == "bovada" and rows[0]["line"] == 5.5
    # P(over 5.5) for a Poisson(6) is clearly > P(over 6.5)
    assert rows[0]["model_p_over"] > rows[1]["model_p_over"]
    for r in rows:
        assert 0.0 <= r["model_p_over"] <= 1.0


# ── full payload ────────────────────────────────────────────────────────────

def _sample_payload():
    grid = list(range(2, 21))
    comps = [
        book_comparison_row("bovada", 5.5, -110, -110, 0.61, 0.39, 0.0, 6.2),
        book_comparison_row("fanduel", 5.5, -115, -105, 0.61, 0.39, 0.0, 6.2),
        book_comparison_row("dk", 6.5, 100, -120, 0.44, 0.56, 0.0, 6.2),
    ]
    return build_k_projection_payload(
        pitcher_id=543037, full_name="Gerrit Cole", team="NYY", game_pk=778899,
        game_date="2026-06-30", opponent="BOS",
        quantile_levels=_QUANTILES, k_quantile_grid=grid, mean=6.2, std=2.1, calib_80=0.8104,
        book_comparisons=comps, generated_at="2026-06-30T13:00:00Z",
    )


def test_build_payload_shape_and_primary_line():
    p = _sample_payload()
    assert p["pitcher_id"] == 543037
    assert p["model_version"] == "strikeout_glm_v1"
    assert p["calib_80"] == 0.81
    assert p["distribution"]["k_quantile_grid"][0] == 2
    assert len(p["book_comparisons"]) == 3
    assert p["primary_line"] == 5.5  # 2× 5.5 vs 1× 6.5 → 5.5 wins
    assert p["best_alpha"] == 0
    assert p["is_bet_recommendation"] is False
    assert p["caption"] == CAPTION and p["disclaimer"] == DISCLAIMER


def test_build_payload_is_json_serialisable():
    p = _sample_payload()
    s = json.dumps(p)  # must not raise (no numpy scalars / NaN-as-object leaks)
    assert "strikeout_glm_v1" in s


def test_primary_line_none_when_no_books():
    p = build_k_projection_payload(
        pitcher_id=1, full_name="x", team=None, game_pk=None, game_date=None, opponent=None,
        quantile_levels=_QUANTILES, k_quantile_grid=list(range(19)), mean=5.0, std=2.0,
        calib_80=0.8, book_comparisons=[],
    )
    assert p["primary_line"] is None
    assert p["book_comparisons"] == []


# ── daily index (list page) ─────────────────────────────────────────────────

def test_index_row_extracts_summary():
    p = _sample_payload()  # primary line 5.5, bovada+fanduel at 5.5 (model_p_over 0.61)
    row = index_row(p)
    assert row["pitcher_id"] == 543037
    assert row["full_name"] == "Gerrit Cole"
    assert row["primary_line"] == 5.5
    assert row["mean"] == 6.2
    assert row["p10"] == 3 and row["p90"] == 19   # grid=range(2,21): level idx 1→3, 17→19
    assert row["model_p_over"] == 0.61            # pulled from the 5.5 comparison row
    assert row["book_count"] == 3
    # index row must not leak edge/EV keys either
    assert {"edge_over", "ev_over", "best_ev"}.isdisjoint(row.keys())


def test_index_row_no_books():
    p = build_k_projection_payload(
        pitcher_id=1, full_name="x", team=None, game_pk=None, game_date="2026-06-30", opponent=None,
        quantile_levels=_QUANTILES, k_quantile_grid=list(range(19)), mean=5.0, std=2.0,
        calib_80=0.8, book_comparisons=[],
    )
    row = index_row(p)
    assert row["primary_line"] is None
    assert row["model_p_over"] is None
    assert row["book_count"] == 0


def test_build_index_payload_sorts_by_mean_desc_and_is_honest():
    rows = [
        index_row(build_k_projection_payload(
            pitcher_id=i, full_name=f"P{i}", team=None, game_pk=None, game_date="2026-06-30",
            opponent=None, quantile_levels=_QUANTILES, k_quantile_grid=list(range(19)),
            mean=m, std=2.0, calib_80=0.8, book_comparisons=[]))
        for i, m in [(1, 4.0), (2, 8.0), (3, 6.0)]
    ]
    idx = build_index_payload(rows, game_date="2026-06-30", generated_at="2026-06-30T00:00:00Z")
    assert idx["count"] == 3
    assert [r["mean"] for r in idx["pitchers"]] == [8.0, 6.0, 4.0]  # desc
    assert idx["best_alpha"] == 0 and idx["is_bet_recommendation"] is False
    assert idx["disclaimer"] == DISCLAIMER
    json.dumps(idx)  # serialisable


# ── HONEST-FRAMING GUARD (the crux of E5.5) ─────────────────────────────────

# Words/phrases that would imply a profitability / bet recommendation. Banned from the user-facing
# K-projection surface (the pure module's prose AND the shipped frontend component). E5.4 proved no
# cashable edge → any of these on this surface is a trust violation, so the build fails on them.
_BANNED = [
    r"\+ev\b", r"\bev\b", r"value play", r"value bet", r"bet this", r"\bedge\b",
    r"win[\s\-]?rate", r"\bprofit\b", r"profitable", r"\bcash(able)?\b", r"\block\b",
    r"smash", r"hammer", r"guaranteed", r"sure thing", r"lay the", r"take the over",
]
_BANNED_RE = re.compile("|".join(_BANNED), re.IGNORECASE)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_SURFACES = [
    _REPO_ROOT / "frontend" / "components" / "pitcher-k-projection.tsx",
    _REPO_ROOT / "frontend" / "app" / "projections" / "page.tsx",
]


def test_caption_and_disclaimer_are_honest():
    text = f"{CAPTION}\n{DISCLAIMER}"
    hit = _BANNED_RE.search(text)
    assert hit is None, f"banned profitability language in caption/disclaimer: {hit!r}"
    # The disclaimer must affirmatively disclaim betting advice + profitability.
    low = DISCLAIMER.lower()
    assert "not betting advice" in low
    assert "no profitability claim" in low


@pytest.mark.parametrize("surface", _FRONTEND_SURFACES, ids=lambda p: p.name)
def test_frontend_surface_has_no_bet_rec_language(surface):
    """Every shipped K-projection surface must carry no +EV / edge / win-rate / bet-rec wording,
    and must surface the projection-not-advice disclaimer copy."""
    if not surface.exists():
        pytest.skip(f"{surface.name} not present in this checkout")
    src = surface.read_text(encoding="utf-8")
    hits = sorted({m.group(0) for m in _BANNED_RE.finditer(src)})
    assert not hits, f"banned profitability language in {surface.name}: {hits}"
    assert "not betting advice" in src.lower()
