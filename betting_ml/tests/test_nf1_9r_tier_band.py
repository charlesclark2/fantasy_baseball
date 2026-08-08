"""NF1.9-R — guards for the DRAFTABLE-TIER re-selection of the veteran band (recorded NULL).

WHAT THIS PROTECTS. NF1.9-R re-measured the served veteran band on the draftable tier and found the
motivating defect MIS-ATTRIBUTED: the "~0.50 tier coverage" belongs to the pre-NF1.9 NORMAL band (the
panel's `served_p10`/`served_p90` columns, which NF-RECAL1's C3 read as "the incumbent band"); the
band actually on the wire covers 0.845 there and a 21-arm re-selection field TIED it. The recorded
outcome is a NULL, the tier-overlay machinery ships DARK, and the served board is byte-identical.

The things that can silently break:
  1. **The dark machinery must stay dark.** `_VET_TIER_RECAL` is False AND no form is selected — and
     a flag flip WITHOUT a selection must activate nothing (the documented-but-never-set flag class
     cannot be allowed a mirror image: a set-but-selectionless flag that changes the board).
  2. **The code must agree with the RECORD.** The constants in `season_projection` are pinned to the
     recorded outcome in `ablation_results/nf1_9r_veteran_tier_band.json` (selection-as-data — the
     NF1.5 pattern): a session that wires a winner without re-running the gate goes red here.
  3. **The tier anchor must stay the INCUMBENT's own point.** NF-RECAL1 measured what a realized
     anchor manufactures (−12.85 → −64.80 on the same rows). `_tier_row_mask` is the single owner.
  4. **The overlay must touch ONLY the tier.** Non-tier rows keep the base band byte-identical; the
     overlay's own output must still honour the shared coherence contract (non-negative, brackets
     the point).
  5. **Each eligibility AND-clause needs its own isolating fixture** (the NF-D17 lesson: a guard on
     an AND-composed rule is vacuous unless its fixture satisfies every OTHER clause). One fixture
     per clause, each satisfying all the others.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import season_projection as sp
from quant_sports_intel_models.football.nfl.fantasy import run_season_projection as rsp
from quant_sports_intel_models.football.nfl.fantasy.run_nf1_9r_veteran_tier_band import (
    _COVERAGE_FLOOR,
    eligibility_misses,
    tier_floor_misses,
    universe_floor_misses,
)

_RECORD = (Path(__file__).resolve().parents[2]
           / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
           / "nf1_9r_veteran_tier_band.json")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _panel(n: int = 3000, seed: int = 11, seasons: tuple = (2019, 2020, 2021)) -> pd.DataFrame:
    """A synthetic veteran panel with the tier's defining feature: outcomes far more dispersed at
    the top of the board than the base band prices, and a zero atom in the bulk."""
    rng = np.random.default_rng(seed)
    per = n // len(seasons)
    season = np.repeat(list(seasons), per)
    n = len(season)
    pos = rng.choice(["QB", "RB", "WR", "TE"], size=n, p=[0.2, 0.25, 0.4, 0.15])
    point = rng.gamma(2.0, 40.0, size=n)
    real = np.clip(point * rng.lognormal(0, 0.7, size=n) - 15, 0, None)
    real[rng.random(n) < 0.28] = 0.0
    return pd.DataFrame({
        "target_season": season, "position": pos, "point": point,
        "season_sd": rng.gamma(2.0, 15.0, size=n),
        "proj_games": rng.uniform(4, 17, n), "base_games": rng.integers(1, 18, n).astype(float),
        "snap_share": rng.uniform(0, 1, n),
        "seasons_missed": (rng.random(n) < 0.1).astype(float),
        "real_fp_ppr": real,
    })


def _frame(panel: pd.DataFrame) -> pd.DataFrame:
    return sp.veteran_band_inputs(panel["position"], panel["point"], panel["season_sd"],
                                  panel["proj_games"], panel["base_games"], panel["snap_share"],
                                  panel["seasons_missed"])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The dark machinery stays dark
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_serving_flip_is_off_and_no_form_is_selected():
    """The recorded outcome is a NULL: the flip flag is False AND no overlay form is selected. A
    session wiring a winner must flip BOTH — and must first have a record whose gate shipped
    (see the selection-as-data pin below)."""
    assert sp._VET_TIER_RECAL is False
    assert sp._VET_TIER_FORM == ""
    assert sp._VET_TIER_K == 0


def test_a_flag_flip_without_a_selection_activates_nothing(monkeypatch):
    """The mirror image of the documented-but-never-set flag class: a set-but-SELECTIONLESS flag
    must not change the board. With `_VET_TIER_RECAL=True` and the recorded empty form, the fitted
    band model carries NO overlay and bands identically to the un-flagged fit."""
    monkeypatch.setattr(sp, "_VET_TIER_RECAL", True)
    panel = _panel()
    m_flagged = sp.fit_veteran_band_model(panel, form="knn_norm", k=300,
                                          tier_form=sp._VET_TIER_FORM,
                                          tier_k=sp._VET_TIER_K,
                                          tier_n=0 if not sp._VET_TIER_FORM else 156)
    m_plain = sp.fit_veteran_band_model(panel, form="knn_norm", k=300)
    assert m_flagged.tier_n == 0 and m_flagged.tier_form == ""
    f = _frame(panel)
    lo_a, hi_a = m_flagged.band_many(f)
    lo_b, hi_b = m_plain.band_many(f)
    assert np.array_equal(lo_a, lo_b) and np.array_equal(hi_a, hi_b)


def test_the_serving_fitter_passes_no_tier_kwargs_while_the_flag_is_off():
    """`fit_veteran_band_from_panel` must gate the tier kwargs on the flag — the served path with
    the flag OFF fits a model with no overlay state at all."""
    panel = _panel()
    model = rsp.fit_veteran_band_from_panel(panel.assign(target_season=2019), 2026)
    assert model is not None
    assert model.tier_n == 0 and model.tier_form == ""


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The code agrees with the RECORD (selection-as-data)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_recorded_outcome_pins_the_constants():
    """The ablation JSON is the record; the code constants must agree with it. The recorded gate
    did NOT ship ⇒ no form may be selected in code. A future session that re-runs the bake-off and
    wires a winner updates BOTH sides together, and this pin makes a one-sided edit red."""
    rec = json.loads(_RECORD.read_text())
    assert rec["gate"]["ship"] is False, (
        "the record says the gate shipped — wire the winner and update this test's expectation")
    assert sp._VET_TIER_FORM == "", (
        "code selects a tier form the RECORD does not ship — the E2.1-r laundering shape")
    assert rec["null_state"]["state"] == "TIE"
    # the premise correction is load-bearing enough to pin: the motivating figure's true owner
    assert rec["reproduction"]["nf_recal1_recorded_incumbent_cov"] == 0.5046
    assert abs(rec["reproduction"]["normal_band_tier_cov_2019_2025"] - 0.5046) <= 0.01
    assert rec["reproduction"]["served_knn_band_tier_cov_2019_2025"] >= _COVERAGE_FLOOR


def test_the_tier_size_has_one_owner():
    """`veteran_tier_size()` delegates to `level_recalibration.draftable_tier_size()` — the tier is
    DERIVED from the shipped league preset, never typed (a tier that could be tuned would be)."""
    from quant_sports_intel_models.football.nfl.fantasy import level_recalibration as LR

    assert sp.veteran_tier_size() == LR.draftable_tier_size() == 156


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The tier anchor is the incumbent's own point — never the outcome
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_tier_mask_selects_on_the_point_not_the_outcome():
    """A row with a huge REALIZED season and a small point must NOT enter the tier; a row with a
    big point and a zero outcome must. (NF-RECAL1 §0: the realized anchor manufactures the bias.)"""
    point = np.array([300.0, 250.0, 10.0, 5.0])
    mask = sp._tier_row_mask(point, None, 2)
    assert mask.tolist() == [True, True, False, False]
    # per-season: the top-n is taken WITHIN each season
    season = np.array([1, 2, 1, 2])
    mask2 = sp._tier_row_mask(point, season, 1)
    assert mask2.tolist() == [True, True, False, False]
    mask3 = sp._tier_row_mask(np.array([1.0, 2.0, 3.0, 4.0]), season, 1)
    assert mask3.tolist() == [False, False, True, True]


def test_the_overlay_fitter_tiers_per_training_season():
    """At FIT time the tier is per TARGET SEASON (top-n of each season), so one big season cannot
    crowd out another's tier rows."""
    panel = _panel(seasons=(2019, 2020))
    m = sp.fit_veteran_band_model(panel, form="knn_norm", k=300,
                                  tier_form="knn_tier", tier_k=50, tier_n=100)
    # the pooled tier training set holds rows from BOTH seasons' tiers
    assert m.tier_pool_pred is not None
    assert len(m.tier_pool_pred) >= 150   # ~2 × 100 minus thin-position scale refusals


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The overlay touches only the tier, and honours the coherence contract
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("tier_form,kw", [
    ("knn_tier", {"tier_k": 50}),
    ("knn_pos_tier", {"tier_k": 25}),
    ("qreg_tier", {}),
    ("cqr_tier", {"tier_cqr_mode": "pos"}),
    ("scale_tier", {}),
])
def test_non_tier_rows_are_byte_identical_to_the_base_band(tier_form, kw):
    panel = _panel()
    frame = _frame(panel)
    m = sp.fit_veteran_band_model(panel, form="knn_norm", k=300,
                                  tier_form=tier_form, tier_n=156, **kw)
    base = sp.fit_veteran_band_model(panel, form="knn_norm", k=300)
    info: dict = {}
    lo, hi = m.band_many(frame, tier_info=info)
    blo, bhi = base.band_many(frame)
    out = ~info["in_tier"]
    # ⚠️ the emptiness assertion is load-bearing: a broken tier mask that swallows the whole board
    # would make the byte-identity below VACUOUSLY true on an empty selection (caught by this
    # test's own red-proof — the NF1.7 (a) class inside the guard itself).
    assert out.sum() > 0 and info["in_tier"].sum() > 0
    assert np.array_equal(lo[out], blo[out]) and np.array_equal(hi[out], bhi[out])
    pt = frame["point"].to_numpy()
    assert np.all(lo >= 0) and np.all(lo <= pt + 1e-9) and np.all(hi >= pt - 1e-9)


def test_an_overlay_that_declines_a_row_is_visible_not_silent():
    """`knn_pos_tier` refuses positions under `_VET_TIER_MIN_POS_TRAIN` tier rows — those tier rows
    keep the base band AND are reported via `tier_info` (the NF1.9 fallback-mask lesson pointed at
    the incumbent: an overlay quietly reverting tier rows to the band it re-prices flatters it)."""
    panel = _panel(n=1200)   # small panel → thin per-position tiers
    frame = _frame(panel)
    m = sp.fit_veteran_band_model(panel, form="knn_norm", k=300,
                                  tier_form="knn_pos_tier", tier_k=25, tier_n=156)
    info: dict = {}
    m.band_many(frame, tier_info=info)
    declined = info["in_tier"] & ~info["overlay_applied"]
    assert declined.sum() > 0, "expected at least one thin-position decline on this panel"


def test_cqr_tier_widens_when_the_base_band_undercovers_the_tier():
    """A structurally-NARROW base band (the normal approximation with its small `season_sd`) genuinely
    under-covers the dispersed tier outcomes, so the out-of-fold conformity quantile must come out
    positive and the applied band must be WIDER on tier rows. This is the mechanism the universe
    pinned at exactly 0 (the zero atom) — the tier is where it can act, and this proves the
    implementation lets it. (The symmetric case — a base that over-covers → the layer narrows — is
    standard CQR semantics and deliberately not forbidden.)"""
    panel = _panel()
    frame = _frame(panel)
    m = sp.fit_veteran_band_model(panel, form="normal",
                                  tier_form="cqr_tier", tier_n=156, tier_cqr_mode="pos")
    base = sp.fit_veteran_band_model(panel, form="normal")
    info: dict = {}
    lo, hi = m.band_many(frame, tier_info=info)
    blo, bhi = base.band_many(frame)
    it = info["in_tier"]
    assert np.mean((hi - lo)[it]) > np.mean((bhi - blo)[it]) + 1.0
    # both scalings came out of ONE cross-conformal pass
    assert set(m.tier_conformal) == {"add", "width"}
    # ...and the scale is selected at band time without a re-fit
    m2 = dataclasses.replace(m, tier_cqr_scale="width")
    lo2, hi2 = m2.band_many(frame)
    assert not np.array_equal(hi2, hi)


def test_the_mag_conditioning_uses_the_infold_cut_never_the_frame():
    """`"mag"` groups split on the FITTED tier median (`tier_mag_cut`), not a quantity re-derived
    from the frame being banded — a frame-derived cut would make the group assignment depend on the
    board being scored."""
    panel = _panel()
    m = sp.fit_veteran_band_model(panel, form="knn_norm", k=300,
                                  tier_form="cqr_tier", tier_n=156, tier_cqr_mode="mag")
    assert np.isfinite(m.tier_mag_cut)
    grp = m._tier_cqr_groups(np.array(["QB", "RB"], dtype=object),
                             np.array([m.tier_mag_cut + 1, m.tier_mag_cut - 1]))
    assert grp.tolist() == ["mag_hi", "mag_lo"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The eligibility AND-gate — one isolating fixture per clause (NF-D17 (c))
# ══════════════════════════════════════════════════════════════════════════════════════════════
_TIER_FLOORS = {"QB": 0.80, "RB": 0.80, "WR": 0.80}
_UNI_FLOORS = {"QB": 0.80, "RB": 0.80, "TE": 0.80, "WR": 0.80}


def _rec(**over) -> dict:
    """A record that SATISFIES every clause; each test breaks exactly one, so a deleted clause in
    the source flips exactly that test (the fixture-per-clause cure for vacuous AND-gate guards)."""
    rec = {"coverage_80": 0.85, "u_coverage_80": 0.88}
    for p in ("QB", "RB", "TE", "WR"):
        rec[f"cov_{p}"] = 0.85
        rec[f"u_cov_{p}"] = 0.88
    rec.update(over)
    return rec


def test_the_fully_passing_fixture_passes():
    assert eligibility_misses(_rec(), _TIER_FLOORS, _UNI_FLOORS) == []


def test_clause_tier_pooled_floor_isolated():
    misses = eligibility_misses(_rec(coverage_80=0.79), _TIER_FLOORS, _UNI_FLOORS)
    assert misses == ["tier pooled 0.79<0.80"]


def test_clause_tier_per_position_floor_isolated():
    misses = eligibility_misses(_rec(cov_RB=0.79), _TIER_FLOORS, _UNI_FLOORS)
    assert misses == ["tier RB 0.79<0.800"]


def test_clause_universe_pooled_floor_isolated():
    misses = eligibility_misses(_rec(u_coverage_80=0.79), _TIER_FLOORS, _UNI_FLOORS)
    assert misses == ["universe pooled 0.79<0.80"]


def test_clause_universe_per_position_floor_isolated():
    misses = eligibility_misses(_rec(u_cov_TE=0.79), _TIER_FLOORS, _UNI_FLOORS)
    assert misses == ["universe TE 0.79<0.800"]


def test_an_unconstrained_position_is_not_gated():
    """TE is CARRIED, not gated, on the tier (n=251 < 400): a TE tier coverage below nominal must
    NOT make an arm ineligible — deriving a floor for it is NF-D22's job, not a side effect here."""
    misses = eligibility_misses(_rec(cov_TE=0.70), _TIER_FLOORS, _UNI_FLOORS)
    assert misses == []


def test_a_missing_coverage_reading_is_a_miss_never_a_pass():
    """NF1.7 (a): an absent reading must fail the clause, not vacuously pass it."""
    rec = _rec()
    del rec["cov_QB"]
    assert any(m.startswith("tier QB") for m in tier_floor_misses(rec, _TIER_FLOORS))
    rec2 = _rec()
    del rec2["u_cov_QB"]
    assert any(m.startswith("universe QB") for m in universe_floor_misses(rec2, _UNI_FLOORS))
