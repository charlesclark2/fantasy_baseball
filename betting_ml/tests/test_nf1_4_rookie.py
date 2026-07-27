"""NF1.4 — rookie-prior refinement: pure-logic fast-gate tests.

Covers the three things NF1.4 actually ships and the guards that make its NULL trustworthy:
  1. the pre-registered candidate set + feature blocks behave as specified (shrinkage, the
     anti-extrapolation property of the EB form, the leakage-safe fold-local features);
  2. the SELECTION METRIC is not silently inverted (oracle floor, the degenerate-median tell in the
     field, the fixed incumbent-anchored tier, the do-no-harm constraint);
  3. ⭐ the one SHIPPED change — the calibrated rookie 80% band — widens the interval WITHOUT
     moving the point projection by a single fantasy point.

Import-safe (no `pipeline`, no IO) per the fast-gate rule; every fixture is synthetic.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import nf1_4_rookie as M14
from quant_sports_intel_models.football.nfl.fantasy import season_projection as sp

RNG = np.random.default_rng(7)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Fixtures — a synthetic drafted-rookie population with the real structure: draft slot drives
# production, ~15% of drafted rookies (more at QB) never play, and combine coverage is partial.
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _rookie_pool(n_per_pos: int = 60, classes=(2016, 2017, 2018, 2019, 2020)) -> pd.DataFrame:
    rows = []
    base = {"QB": 240.0, "RB": 170.0, "WR": 150.0, "TE": 90.0}
    zero_rate = {"QB": 0.35, "RB": 0.12, "WR": 0.11, "TE": 0.13}
    for pos, b in base.items():
        for i in range(n_per_pos):
            cls = classes[i % len(classes)]
            overall = int(RNG.integers(1, 255))
            scale = max(0.05, (260 - overall) / 260.0)
            played = RNG.random() > zero_rate[pos] * (1.4 - scale)
            fp = max(0.0, b * scale * RNG.uniform(0.5, 1.5)) if played else 0.0
            has_combine = RNG.random() > 0.3
            rows.append({
                "gsis_id": f"{pos}{cls}{i}", "player_name": f"{pos} {i}", "position_group": pos,
                "nfl_position": pos, "draft_year": cls, "draft_overall": float(overall),
                "draft_round": float(min(7, overall // 32 + 1)),
                "log_overall": float(np.log(max(1, overall))),
                "is_top10": float(overall <= 10), "is_day1": float(overall <= 32),
                "projected_nfl_z": float(RNG.normal(0.6 * scale, 1.0)),
                "forty": float(RNG.normal(4.55, 0.12)) if has_combine else np.nan,
                "vertical": float(RNG.normal(34, 3)) if has_combine else np.nan,
                "broad_jump": float(RNG.normal(120, 6)) if has_combine else np.nan,
                "cone": float(RNG.normal(7.0, 0.25)) if has_combine else np.nan,
                "shuttle": float(RNG.normal(4.3, 0.15)) if has_combine else np.nan,
                "combine_wt": float(RNG.normal(215, 25)) if has_combine else np.nan,
                "combine_ht_in": float(RNG.normal(73, 2)) if has_combine else np.nan,
                "recruit_composite_rating": float(RNG.uniform(0.8, 1.0)),
                "recruit_stars_f": float(RNG.integers(2, 6)),
                "n_college_seasons": float(RNG.integers(3, 5)),
                "breakout_season_index": float(RNG.integers(0, 3)),
                "breakout_class_year": float(RNG.integers(1, 5)),
                "career_index_at_draft": float(RNG.integers(3, 5)),
                "early_breakout": float(RNG.random() > 0.6), "has_breakout": 1.0,
                "rookie_games": float(RNG.integers(4, 17)) if played else 0.0,
                "rookie_fp_ppr": fp,
            })
    d = pd.DataFrame(rows)
    d["p1a_slot_residual"] = M14.p1a_slot_residual(d)
    return pd.concat([d, M14.athletic_features(d, ref=d)], axis=1)


@pytest.fixture(scope="module")
def pool() -> pd.DataFrame:
    return _rookie_pool()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Feature blocks + fold-local (leakage-safe) features
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_slot_block_is_always_on():
    """Draft capital is the backbone — P1A's own verdict is that slot beats college production, so
    a candidate without it was never pre-registered and must not be constructible by omission."""
    for blocks in (("p1a",), ("athletic",), ("breakout", "recruit"), ("slot",)):
        feats = M14.block_features(blocks)
        assert set(M14.FEATURE_BLOCKS["slot"]).issubset(feats)
    assert len(set(M14.block_features(("slot", "slot", "p1a")))) == len(M14.block_features(("slot", "p1a")))


def test_athletic_features_standardise_against_the_REFERENCE_frame_only(pool):
    """Leakage: scoring a held-out class must standardise on the TRAINING classes. Passing a test
    frame with a shifted combine distribution must move its z-scores — if the function silently
    normalised the test frame against itself, the z's would be invariant to the shift."""
    train = pool[pool["draft_year"] < 2020]
    test = pool[pool["draft_year"] == 2020].copy()
    z_ref = M14.athletic_features(test, ref=train)["forty_z"]
    shifted = test.assign(forty=test["forty"] - 0.20)     # everyone runs 0.2s faster
    z_shift = M14.athletic_features(shifted, ref=train)["forty_z"]
    m = z_ref.notna() & z_shift.notna()
    assert m.sum() > 5
    # forty is sign -1 (lower is better) ⇒ a faster class must score HIGHER, not identical
    assert (z_shift[m] > z_ref[m]).all()
    # self-normalising would leave the mean at ~0 for both; it must not
    assert abs(float(z_shift[m].mean()) - float(z_ref[m].mean())) > 0.5


def test_athletic_features_keep_a_missing_drill_null_and_flag_it(pool):
    a = M14.athletic_features(pool, ref=pool)
    no_combine = pool["forty"].isna() & pool["vertical"].isna()
    assert no_combine.any()
    assert a.loc[no_combine, "forty_z"].isna().all()
    assert (a.loc[no_combine, "has_combine"] == 0.0).all()
    assert (a.loc[~no_combine, "has_combine"] == 1.0).all()


def test_p1a_residual_is_computed_within_class_and_position(pool):
    """The residual is the disagreement with the draft board INSIDE a class — so it must be
    invariant to a constant shift applied to a whole class's z (a class-wide rescale of P1A's
    output is not information about any individual)."""
    r0 = M14.p1a_slot_residual(pool)
    shifted = pool.assign(projected_nfl_z=pool["projected_nfl_z"] + 3.0)
    r1 = M14.p1a_slot_residual(shifted)
    assert np.allclose(r0.to_numpy(), r1.to_numpy(), atol=1e-8)
    assert float(np.abs(r0).max()) <= 3.0 + 1e-9      # clipped


def test_p1a_residual_returns_zero_for_a_group_too_thin_to_regress():
    thin = pd.DataFrame({"draft_year": [2020] * 3, "position_group": ["QB"] * 3,
                         "draft_overall": [1.0, 20.0, 90.0], "projected_nfl_z": [2.0, 0.0, -1.0]})
    assert (M14.p1a_slot_residual(thin) == 0.0).all()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The candidate learners
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("name", sorted(M14.ROOKIE_LEARNER_REGISTRY))
def test_every_learner_fits_predicts_and_never_returns_a_negative_projection(pool, name):
    train, test = pool[pool["draft_year"] < 2020], pool[pool["draft_year"] == 2020]
    learner = M14.make_rookie_learner(name, feats=M14.block_features(("slot", "p1a")))
    learner.fit(train, train["rookie_fp_ppr"].to_numpy())
    pred = learner.predict(test)
    assert len(pred) == len(test)
    assert np.isfinite(pred).all()
    assert (pred >= 0).all()


def test_full_shrink_collapses_a_learner_to_the_position_mean(pool):
    """λ = 1 is the degenerate end of the shrinkage knob; it must reproduce `pos_mean` exactly, so
    the knob is genuinely "how much of a rookie's own information do we trust"."""
    train, test = pool[pool["draft_year"] < 2020], pool[pool["draft_year"] == 2020]
    y = train["rookie_fp_ppr"].to_numpy()
    shrunk = M14.make_rookie_learner("slot_eb", feats=(), shrink=1.0).fit(train, y).predict(test)
    mean = M14.make_rookie_learner("pos_mean", feats=()).fit(train, y).predict(test)
    assert np.allclose(shrunk, mean)


def test_slot_eb_cannot_extrapolate_past_what_its_bin_actually_did(pool):
    """⭐ The reason a slot BIN replaces MVP-1's log-log power law as a candidate: a power law fitted
    mostly on late picks EXTRAPOLATES at pick #1 (that is how the #1-overall QB acquires a fringe-QB1
    projection), whereas a bin mean is bounded by its bin's realized outcomes by construction."""
    train = pool[pool["draft_year"] < 2020]
    learner = M14.make_rookie_learner("slot_eb", feats=(), shrink=0.0, eb_k=0.0).fit(
        train, train["rookie_fp_ppr"].to_numpy())
    top = pd.DataFrame([{"position_group": "QB", "draft_overall": 1.0}])
    bin0 = train[(train["position_group"] == "QB")
                 & (train["draft_overall"].map(M14.slot_bin) == M14.slot_bin(1.0))]
    assert float(learner.predict(top)[0]) <= float(bin0["rookie_fp_ppr"].max()) + 1e-6


def test_slot_bin_is_monotone_in_draft_capital():
    bins = [M14.slot_bin(o) for o in (1, 5, 15, 25, 40, 60, 90, 130, 200, 260)]
    assert bins == sorted(bins)
    assert M14.slot_bin(float("nan")) == len(M14.SLOT_BINS) - 2   # unknown slot → the last bin


def test_the_grid_carries_the_degenerate_median_and_every_pre_registered_block():
    grid = M14.candidate_grid()
    learners = {c["learner"] for c in grid}
    assert "pos_median" in learners, "the MAE-collapse tell must be scored, not omitted"
    assert {"pos_mean", "slot_eb", "slot_ridge", "slot_gbm"} <= learners
    blocks = {tuple(c["blocks"]) for c in grid}
    for b in M14.OPTIONAL_BLOCKS:
        assert ("slot", b) in blocks, f"pre-registered block {b} was never evaluated"
    assert M14.candidate_grid(smoke=True) and len(M14.candidate_grid(smoke=True)) < len(grid)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Selection-metric hygiene (CLAUDE.md §0.5 — a pre-registered metric can be SILENTLY INVERTED)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _scored(pool: pd.DataFrame) -> pd.DataFrame:
    """A held-out class with an incumbent anchor + two candidate columns."""
    d = pool[pool["draft_year"] == 2020].copy()
    d["_inc"] = d["rookie_fp_ppr"] * 0.8 + 12.0
    d["_good"] = d["rookie_fp_ppr"] * 0.95 + 3.0
    d["_flat"] = 40.0
    return d


def test_oracle_is_the_scoring_floor(pool):
    """⭐ The E2.1-r guard: the realized-outcome oracle scores MAE 0 and NOTHING may beat it. A
    candidate scoring below the oracle is mathematically impossible = the metric is inverted."""
    d = _scored(pool)
    scale = M14.position_scale(pool)
    assert M14.cohort_metrics(d.assign(_o=d["rookie_fp_ppr"]), "_o", scale=scale)["tier_mae"] == 0.0
    assert M14.oracle_is_the_scoring_floor(d, ["_inc", "_good", "_flat"], scale=scale)


def test_the_selection_metric_is_MONOTONE_in_accuracy(pool):
    """The substantive hygiene check. For an MAE-type metric the oracle floor is a DIRECTION check
    (the oracle trivially scores 0, so nothing can go below it); what a silent inversion would
    actually look like is the metric REWARDING a worse predictor. Assert the ordering directly:
    strictly-closer predictions must score strictly lower."""
    d = _scored(pool)
    scale = M14.position_scale(pool)
    real = d["rookie_fp_ppr"]
    scores = [M14.cohort_metrics(d.assign(_p=real + err), "_p", scale=scale)["tier_mae"]
              for err in (5.0, 25.0, 80.0)]
    assert scores == sorted(scores), scores
    assert scores[0] < scores[-1]


def test_the_degenerate_median_does_not_win_the_TIER_metric(pool):
    """The MAE-collapse trap, checked on the real metric: rookie fp is zero-inflated and right-
    skewed, so raw MAE over the full universe can be minimised by predicting ~the position median.
    Restricting to the DRAFTABLE tier is what stops that — a flat median must lose there to a
    predictor that actually tracks the outcome."""
    d = _scored(pool)
    scale = M14.position_scale(pool)
    good = M14.cohort_metrics(d, "_good", scale=scale)["tier_mae"]
    flat = M14.cohort_metrics(d, "_flat", scale=scale)["tier_mae"]
    assert good < flat, (good, flat)


def test_the_draftable_tier_is_FIXED_by_the_incumbent_anchor(pool):
    """Every candidate must grade on the identical subset — a candidate that could re-rank its own
    tier would be graded on a friendlier population than the incumbent."""
    d = _scored(pool)
    t_inc = set(M14.draftable_tier(d, "_inc").index)
    t_good = set(M14.draftable_tier(d.assign(_inc=d["_inc"]), "_inc").index)
    assert t_inc == t_good
    for p, k in M14.TIER_K.items():
        assert (M14.draftable_tier(d, "_inc")["position_group"] == p).sum() <= k


def test_a_constant_prediction_scores_zero_ordering_skill_not_a_skip(pool):
    """`degenerate_zero` semantics inherited from NF1.1: a flat projection over a scoreable position
    must score ρ = 0.0, NOT be skipped — otherwise a degenerate config buys a smaller, friendlier
    cohort denominator than the incumbent."""
    d = _scored(pool)
    per, pooled = M14.pooled_position_rho(d, "_flat")
    assert per and all(v == 0.0 for v in per.values())
    assert pooled == 0.0


def test_tier_bias_sign_reads_hot_positive_and_cold_negative(pool):
    d = _scored(pool)
    scale = M14.position_scale(pool)
    hot = M14.cohort_metrics(d.assign(_h=d["rookie_fp_ppr"] + 60.0), "_h", scale=scale)
    cold = M14.cohort_metrics(d.assign(_c=d["rookie_fp_ppr"] * 0.4), "_c", scale=scale)
    assert hot["tier_bias"] > 0 and hot["bias"] > 0
    assert cold["tier_bias"] < 0 and cold["bias"] < 0


def test_the_verdict_needs_every_gate_and_bars_the_non_shippable_form():
    ok = dict(beats_incumbent=True, ordering_ok=True, pbo=0.1, dsr=0.5, fdr_pass=True,
              shippable=True)
    assert M14.rookie_verdict(**ok)["repoint"]
    for override in ({"beats_incumbent": False}, {"ordering_ok": False}, {"shippable": False},
                     {"pbo": 0.9}, {"pbo": None}, {"dsr": -0.1}, {"dsr": None}, {"fdr_pass": False}):
        assert not M14.rookie_verdict(**{**ok, **override})["repoint"], override
    assert "pos_median" in M14.NON_SHIPPABLE


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Face validity + the empirical interval
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_face_validity_flags_a_rookie_at_the_top_of_the_board(pool):
    hist = pool[["position_group", "rookie_fp_ppr"]]
    board = pd.DataFrame([
        {"player_name": "Rookie QB", "position": "QB", "is_rookie": True, "proj_fp_ppr": 500.0},
        *[{"player_name": f"Vet {i}", "position": "QB", "is_rookie": False,
           "proj_fp_ppr": 300.0 - i} for i in range(20)],
    ])
    fv = M14.face_validity(board, hist)
    assert fv["top1_is_rookie"] and fv["n_rookies_in_top10"] == 1 and not fv["pass"]
    assert any(o["position"] == "QB" for o in fv["positions_over_cap"])


def test_the_rookie_band_covers_its_nominal_rate_on_a_known_population():
    """The band's statistical claim, on a population where the answer is known. `_fit_rookie_bands`
    takes the empirical q10/q90 of realized outcomes within a prediction tercile, so on a sample
    with a known noise level its coverage must land near the nominal 80%."""
    n = 600
    overall = RNG.uniform(1, 250, n)
    truth = np.clip(220.0 * (1.0 - overall / 260.0), 0, None)
    real = np.clip(truth + RNG.normal(0, 45, n), 0, None)
    hist = pd.DataFrame({"position_group": "WR", "draft_overall": overall, "games": 10.0,
                         "rookie_fp_ppr": real})
    for c in sp._ROOKIE_RAW_STATS:
        hist[c] = real * 0.5
    curve = sp.fit_rookie_slot_curves(hist, band_hist=hist)
    hit = 0
    for o, y in zip(overall, real):
        lo, hi = curve.band("WR", curve.predict_fp("WR", o))
        hit += int(lo <= y <= hi)
    assert 0.70 <= hit / n <= 0.92, hit / n


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. ⭐ THE SHIPPED CHANGE — the calibrated rookie band in `season_projection`
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _curve_inputs(pool: pd.DataFrame):
    """`fit_rookie_slot_curves` reads the rookie-year games as `games`. The POINT history keeps
    MVP-1's survivor filter; the BAND history is the full drafted population."""
    hist = pool[pool["rookie_games"] > 0].assign(games=lambda d: d["rookie_games"])
    band = pool.assign(games=lambda d: d["rookie_games"])
    for c in sp._ROOKIE_RAW_STATS:
        hist[c] = hist["rookie_fp_ppr"] * 0.5
        band[c] = band["rookie_fp_ppr"] * 0.5
    return hist, band


def test_calibrated_band_does_NOT_move_the_point_projection(pool):
    """⭐ THE REGRESSION GUARD FOR NF1.4'S ONLY SHIPPED CHANGE. The model verdict was a NULL, so the
    rookie POINT projection must be byte-identical with and without the band; a future edit that
    lets `band_hist` leak into the curve fit would silently ship an unselected model."""
    hist, band = _curve_inputs(pool)
    incoming = pool[pool["draft_year"] == 2020].head(20)
    old = sp.project_rookies(incoming, sp.fit_rookie_slot_curves(hist), 2021)
    new = sp.project_rookies(incoming, sp.fit_rookie_slot_curves(hist, band_hist=band), 2021)
    assert not old.empty
    for col in ("proj_fp_ppr", "proj_games", *sp.RAW_STAT_COLS):
        if col in old.columns:
            assert np.allclose(old[col].to_numpy(dtype=float), new[col].to_numpy(dtype=float),
                               equal_nan=True), col


def test_calibrated_band_is_labelled_brackets_the_point_and_is_non_negative(pool):
    hist, band = _curve_inputs(pool)
    incoming = pool[pool["draft_year"] == 2020].head(30)
    new = sp.project_rookies(incoming, sp.fit_rookie_slot_curves(hist, band_hist=band), 2021)
    assert (new["uncertainty_type"] == "calibrated").all()
    assert (new["fp_ppr_p10"] >= 0).all()
    assert (new["fp_ppr_p10"] <= new["proj_fp_ppr"] + 1e-6).all()
    assert (new["fp_ppr_p90"] >= new["proj_fp_ppr"] - 1e-6).all()
    assert (new["fp_ppr_sd"] >= 0).all()


def test_a_curve_without_band_history_keeps_the_legacy_parameter_band(pool):
    """Back-compat: an un-migrated caller must still get *a* band, and must still be honestly
    LABELLED as the parameter-uncertainty one (its measured coverage is 0.68, not 0.80)."""
    hist, _ = _curve_inputs(pool)
    incoming = pool[pool["draft_year"] == 2020].head(10)
    out = sp.project_rookies(incoming, sp.fit_rookie_slot_curves(hist), 2021)
    assert (out["uncertainty_type"] == "parameter").all()
    assert not sp.fit_rookie_slot_curves(hist).fp_bands


def test_the_band_history_prices_the_never_played_rookie(pool):
    """The whole point of the full drafted population: a late-round rookie's p10 must be able to
    reach 0. The survivor-filtered `fp × cv` band cannot express that — it scales with the point
    projection, so the rookies who most often bust get the NARROWEST interval."""
    hist, band = _curve_inputs(pool)
    curve = sp.fit_rookie_slot_curves(hist, band_hist=band)
    late = pd.DataFrame([{"gsis_id": "L1", "player_name": "Late WR", "position_group": "WR",
                          "nfl_position": "WR", "draft_overall": 230.0, "projected_nfl_z": -0.5}])
    out = sp.project_rookies(late, curve, 2021)
    assert float(out["fp_ppr_p10"].iloc[0]) == 0.0


def test_rookie_board_face_validity_passes_a_sane_board_and_trips_an_over_placed_rookie(pool):
    hist = pool[["position_group", "rookie_fp_ppr"]]
    vets = [{"player_name": f"Vet {i}", "position": "RB", "is_rookie": False,
             "proj_fp_ppr": 320.0 - 5 * i} for i in range(30)]
    sane = pd.DataFrame([*vets, {"player_name": "Rook", "position": "RB", "is_rookie": True,
                                 "proj_fp_ppr": 60.0}])
    assert sp.rookie_board_face_validity(sane, hist)["pass"]

    hot = pd.DataFrame([*vets, {"player_name": "Rook", "position": "RB", "is_rookie": True,
                                "proj_fp_ppr": 900.0}])
    res = sp.rookie_board_face_validity(hot, hist)
    assert not res["pass"]
    assert res["placement"]["top1_is_rookie"]
    assert res["placement"]["best_rookie"] == "Rook"
    assert res["level"]["positions_over_cap"]


def test_face_validity_is_empty_board_safe():
    empty = pd.DataFrame(columns=["player_name", "position", "is_rookie", "proj_fp_ppr"])
    assert sp.rookie_board_face_validity(empty, pd.DataFrame(
        {"position_group": [], "rookie_fp_ppr": []}))["pass"]
