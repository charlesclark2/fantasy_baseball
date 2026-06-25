"""test_prop_edge.py — Edge Program E5.3 pure de-vig / model-vs-market machinery.

Covers the AC-critical pieces: two-way de-vig correctness (additive, hold), the half-line vs
integer-line PUSH convention, push-excluded conditional probs, per-$1 EV (push = refund), the edge
definition, and the name→id bridge normalisation (accents / punctuation / Jr.–Sr.).
"""

from __future__ import annotations

import numpy as np
import pytest

from betting_ml.utils.prop_edge import (
    american_to_profit,
    compute_edge_row,
    conditional_no_push,
    devig_two_way,
    ev_per_dollar,
    last_initial_key,
    line_probabilities,
    normalize_name,
    ref_display_name,
)


# ── name normalisation (the bridge join key) ────────────────────────────────

def test_normalize_basic_first_last():
    assert normalize_name("Aaron Nola") == "aaron nola"


def test_normalize_strips_accents():
    assert normalize_name("José Ramírez") == "jose ramirez"
    assert normalize_name("Jesús Luzardo") == "jesus luzardo"


def test_normalize_strips_generational_suffix():
    assert normalize_name("Nestor Cortes Jr.") == "nestor cortes"
    assert normalize_name("Lance McCullers Jr.") == "lance mccullers"
    assert normalize_name("Ken Griffey III") == "ken griffey"


def test_normalize_punctuation_and_hyphen():
    assert normalize_name("AJ Smith-Shawver") == "aj smith shawver"
    assert normalize_name("Ryan O'Brien") == "ryan o brien"


def test_normalize_none_and_blank():
    assert normalize_name(None) == ""
    assert normalize_name("   ") == ""


def test_ref_display_name_reassembles_first_last():
    # ref_players stores "Last, First"; we feed first/last columns → "First Last".
    assert normalize_name(ref_display_name("Shohei", "Ohtani")) == "shohei ohtani"


def test_bridge_matches_across_formats():
    # S3 "First Last" with accent+suffix ↔ ref first/last columns → same key.
    s3 = normalize_name("José Ureña Jr.")
    ref = normalize_name(ref_display_name("José", "Ureña Jr."))
    assert s3 == ref == "jose urena"


def test_normalize_strips_team_parenthetical():
    assert normalize_name("Logan Allen (CLE)") == "logan allen"


def test_last_initial_fallback_key():
    # Feed full legal name vs ref common name fold to the same (last, initial) key.
    assert last_initial_key(normalize_name("Matthew Boyd")) == ("boyd", "m")
    assert last_initial_key(normalize_name("Matt Boyd")) == ("boyd", "m")
    assert last_initial_key(normalize_name("John Patrick Sears")) == ("sears", "j")
    assert last_initial_key(normalize_name("JP Sears")) == ("sears", "j")
    assert last_initial_key("madeup") is None   # single token → no key


# ── two-way de-vig + hold ───────────────────────────────────────────────────

def test_devig_symmetric_pair_is_half():
    dv = devig_two_way(-110, -110)
    assert dv["valid"]
    assert dv["devig_over"] == pytest.approx(0.5, abs=1e-9)
    assert dv["devig_under"] == pytest.approx(0.5, abs=1e-9)
    # -110/-110 implied 0.5238 each → hold ≈ 0.0476.
    assert dv["hold"] == pytest.approx(0.04762, abs=1e-4)


def test_devig_normalizes_to_one():
    dv = devig_two_way(+120, -140)
    assert dv["devig_over"] + dv["devig_under"] == pytest.approx(1.0, abs=1e-9)
    assert dv["devig_over"] < dv["devig_under"]   # +120 underdog over → lower fair prob


def test_devig_one_sided_invalid():
    dv = devig_two_way(-110, None)
    assert not dv["valid"]
    assert np.isnan(dv["devig_over"]) and np.isnan(dv["devig_under"])
    assert dv["implied_over"] == pytest.approx(110 / 210, abs=1e-6)   # one side still reported


def test_american_to_profit():
    assert american_to_profit(+150) == pytest.approx(1.5)
    assert american_to_profit(-200) == pytest.approx(0.5)
    assert american_to_profit(+100) == pytest.approx(1.0)


# ── half-line vs integer-line PUSH ──────────────────────────────────────────

def _samples_from_counts(counts):
    """Build a deterministic sample array with exact integer multiplicities."""
    return np.array([c for c, n in counts for _ in range(n)], dtype=np.int64)


def test_half_line_no_push():
    # 60% at 7 (>5.5 over), 40% at 4 (<5.5 under). Half-line → no push.
    s = _samples_from_counts([(7, 600), (4, 400)])
    p = line_probabilities(s, 5.5)
    assert p["p_over"] == pytest.approx(0.6)
    assert p["p_under"] == pytest.approx(0.4)
    assert p["p_push"] == 0.0


def test_integer_line_push_mass():
    # line = 6: over = P(K>6)=P(K>=7), push = P(K=6), under = P(K<=5).
    s = _samples_from_counts([(8, 300), (6, 200), (3, 500)])
    p = line_probabilities(s, 6)
    assert p["p_over"] == pytest.approx(0.3)
    assert p["p_push"] == pytest.approx(0.2)
    assert p["p_under"] == pytest.approx(0.5)
    assert p["p_over"] + p["p_under"] + p["p_push"] == pytest.approx(1.0)


def test_probs_sum_to_one_random():
    rng = np.random.default_rng(0)
    s = rng.poisson(5.0, size=20000)
    for ln in (4.5, 5, 5.5, 6):
        p = line_probabilities(s, ln)
        assert p["p_over"] + p["p_under"] + p["p_push"] == pytest.approx(1.0, abs=1e-9)


def test_conditional_no_push_excludes_push():
    # raw over 0.3 / push 0.2 / under 0.5 → conditional over = 0.3/0.8 = 0.375.
    co, cu = conditional_no_push(0.3, 0.5)
    assert co == pytest.approx(0.375)
    assert cu == pytest.approx(0.625)
    assert co + cu == pytest.approx(1.0)


def test_conditional_half_line_identity():
    co, cu = conditional_no_push(0.6, 0.4)
    assert co == pytest.approx(0.6) and cu == pytest.approx(0.4)


# ── EV (push is a stake refund) ─────────────────────────────────────────────

def test_ev_half_line_breakeven():
    # p_over = 0.5238 at -110 is exactly breakeven (EV ≈ 0).
    ev = ev_per_dollar(110 / 210, 1 - 110 / 210, -110)
    assert ev == pytest.approx(0.0, abs=1e-6)


def test_ev_positive_when_model_beats_price():
    # model 60% over at -110 → clearly +EV.
    ev = ev_per_dollar(0.60, 0.40, -110)
    assert ev > 0
    assert ev == pytest.approx(0.60 * (100 / 110) - 0.40, abs=1e-9)


def test_ev_push_is_refund_not_loss():
    # integer line: over 0.3, under 0.5, push 0.2. EV_over uses raw masses (push refunded → 0 PnL).
    ev = ev_per_dollar(0.3, 0.5, +100)   # profit b=1
    assert ev == pytest.approx(0.3 * 1.0 - 0.5)   # = -0.2, push 0.2 contributes nothing


# ── full edge row ───────────────────────────────────────────────────────────

def test_compute_edge_row_half_line():
    s = _samples_from_counts([(7, 600), (4, 400)])   # model over 0.6 at 5.5
    row = compute_edge_row(s, 5.5, -110, -110)       # book fair over 0.5
    assert row["model_p_over"] == pytest.approx(0.6)
    assert row["book_devig_over"] == pytest.approx(0.5, abs=1e-9)
    assert row["edge_over"] == pytest.approx(0.1, abs=1e-9)
    assert row["edge_under"] == pytest.approx(-0.1, abs=1e-9)
    assert row["best_side"] == "over"
    assert row["best_edge"] == pytest.approx(0.1, abs=1e-9)
    assert not row["is_integer_line"]


def test_compute_edge_row_integer_uses_conditional_for_edge():
    s = _samples_from_counts([(8, 300), (6, 200), (3, 500)])   # over .3 push .2 under .5
    row = compute_edge_row(s, 6, -110, -110)
    assert row["is_integer_line"]
    assert row["model_p_push"] == pytest.approx(0.2)
    # edge compares push-excluded model (over .375) to push-excluded de-vig (.5).
    assert row["model_p_over_cond"] == pytest.approx(0.375)
    assert row["edge_over"] == pytest.approx(0.375 - 0.5, abs=1e-9)


def test_compute_edge_row_one_sided_no_devig():
    s = _samples_from_counts([(7, 600), (4, 400)])
    row = compute_edge_row(s, 5.5, -110, None)
    assert not row["devig_valid"]
    assert np.isnan(row["edge_over"]) and np.isnan(row["edge_under"])
    assert np.isnan(row["ev_under"])              # under price missing
    assert np.isfinite(row["ev_over"])            # over price present → over EV still computable
