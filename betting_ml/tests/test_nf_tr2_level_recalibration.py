"""NF-TR2 / NF-TR2b guards — the season-projection LEVEL recalibration (draft-board credibility).

Every clause here is RED-provable by `betting_ml/tests/nf_tr2_red_proof.py` (in-process source
mutation, `BaseException` caught, mutation asserted to have LANDED before pytest runs).

Fast gate: imports `quant_sports_intel_models.football.nfl.fantasy.*` only (never `pipeline`, never
the real `duck()`); the served band model used below is fitted on a SYNTHETIC panel.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX
from quant_sports_intel_models.football.nfl.fantasy import season_level_recalibration as SLR
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP
from quant_sports_intel_models.football.nfl.fantasy import veteran_level_policy as VLP
from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import OUTPUT_COLS

_ROOT = Path(__file__).resolve().parents[2]
_REC = _ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 0. The pre-registration is pinned (a field that grows or a window that moves fails here)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_declared_field_is_three_trials_from_the_brief():
    assert SLR.FORMS == ("pos_const", "pos_affine")
    assert SLR.DECLARED_FIELD_SIZE == 3
    assert "no-op foil" in SLR.DECLARED_FIELD_SOURCE and "affine" in SLR.DECLARED_FIELD_SOURCE
    reg = SLR.registration()
    assert reg["declared_field_size"] == 3 and reg["lambda"] == 1.0
    assert reg["band_treatment"] == "fixed"
    assert SLR.SELECTION_METRIC == "crps" and "mae" in SLR.FORBIDDEN_SELECTION_METRICS


def test_window_is_derived_from_the_thinnest_tier_position_not_tuned():
    # 156-row tier, 13 seasons: TE ≈ 19.3 rows/season ⇒ ceil(90 / 19.3) = 5 (the pinned value)
    rows = {"QB": 35.77, "RB": 37.69, "TE": 19.31, "WR": 63.23}
    assert SLR.window_seasons_for(rows) == SLR.WINDOW_SEASONS == 5
    assert SLR.window_seasons_for({"X": 90.0}) == 1
    assert SLR.window_seasons_for({"X": 10.0}) == 9
    # the mask reads strictly-before AND within the window
    m = SLR.window_mask([2018, 2019, 2020, 2021, 2022, 2023], 2023, 3)
    assert m.tolist() == [False, False, True, True, True, False]
    assert SLR.window_mask([2018, 2023], 2023, None).tolist() == [True, False]


def test_policy_reads_the_registration_it_cannot_drift_from():
    assert VLP.FORM in SLR.FORMS
    assert VLP.WINDOW_SEASONS == SLR.WINDOW_SEASONS
    assert VLP.MODEL_VERSION == SLR.TR2B_MODEL_VERSION
    assert VLP.SOURCE_MODEL == SLR.TR2B_STORY and VLP.PREDECESSOR == SLR.STORY
    assert VLP.RECALIBRATED_POSITIONS == SLR.RECALIBRATED_POSITIONS


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The estimator targets the REALIZED level (L3 no-inflation, unit)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _synthetic(n=400, seed=1):
    rng = np.random.default_rng(seed)
    pos = rng.choice(["QB", "RB", "WR", "TE"], size=n)
    p = rng.uniform(20, 300, size=n)
    lift = {"QB": 0.95, "RB": 1.20, "WR": 1.10, "TE": 1.05}
    y = np.array([lift[q] for q in pos]) * p + rng.normal(0, 30, size=n)
    y = np.clip(y, 0, None)
    g = rng.uniform(8, 17, size=n)
    return p, y, pos, g


def test_estimator_targets_realized_mean_exactly_in_fold():
    p, y, pos, g = _synthetic()
    k = SLR.fit_pos_const(p, y, pos)
    for q in SLR.RECALIBRATED_POSITIONS:
        s = pos == q
        assert abs(k[q] * p[s].sum() - y[s].sum()) < 1e-9 * max(1.0, y[s].sum())
    newp = SLR.predict_level("pos_const", k, p, pos, g)
    assert abs(newp.mean() - y.mean()) < 1e-9 * max(1.0, y.mean())


def test_estimator_is_the_ratio_of_sums_not_the_mean_of_ratios():
    # a mean-of-ratios (NF-RECAL1's estimator) is NOT mean-matching on a skewed target
    p = np.array([10.0, 100.0, 200.0, 300.0]); y = np.array([30.0, 100.0, 200.0, 300.0])
    pos = np.array(["RB"] * 4)
    k = SLR.fit_pos_const(p, y, pos, min_rows=1)["RB"]
    assert abs(k - y.sum() / p.sum()) < 1e-12
    assert abs(k - np.mean(y / p)) > 0.1        # the two estimators genuinely differ here


def test_thin_position_is_left_alone_never_zeroed():
    p, y, pos, g = _synthetic(n=60)
    k = SLR.fit_pos_const(p, y, pos, min_rows=1000)
    assert all(v == 1.0 for v in k.values())
    assert np.allclose(SLR.predict_level("pos_const", k, p, pos, g), p)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Rank preservation + the incumbent-equivalent inversion (L5 / the fixed band)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_pos_const_preserves_within_position_order_exactly_and_inverts():
    p, y, pos, g = _synthetic()
    k = SLR.fit_pos_const(p, y, pos)
    newp = SLR.predict_level("pos_const", k, p, pos, g)
    for q in SLR.RECALIBRATED_POSITIONS:
        s = pos == q
        assert np.array_equal(np.argsort(-p[s], kind="stable"), np.argsort(-newp[s], kind="stable"))
    back = SLR.invert_level("pos_const", k, newp, pos, g)
    assert np.allclose(back, p, atol=1e-9)
    ri = SLR.rank_identity(p, newp, y, pos)
    assert all(v["order_identical"] and v["delta_rho_identical"] for v in ri.values())


def test_affine_inverts_only_with_a_positive_slope():
    p, y, pos, g = _synthetic()
    a = SLR.fit_pos_affine(p, y, pos, g)
    newp = SLR.predict_level("pos_affine", a, p, pos, g)
    back = SLR.invert_level("pos_affine", a, newp, pos, g)
    assert np.allclose(back, p, atol=1e-6)
    bad = {q: (0.0, -1.0) for q in SLR.RECALIBRATED_POSITIONS}
    assert np.allclose(SLR.invert_level("pos_affine", bad, newp, pos, g), newp)   # refuses to invert


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Availability preserved + the whole line moves consistently (L4, serving apply)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _projected_frame(n=40, seed=3):
    rng = np.random.default_rng(seed)
    pos = rng.choice(["QB", "RB", "WR", "TE", "FB"], size=n)
    df = pd.DataFrame({
        "position": pos, "proj_games": rng.uniform(8, 17, size=n),
        "proj_pass_att": np.where(pos == "QB", 500.0, 0.0), "proj_pass_cmp": np.where(pos == "QB", 320.0, 0.0),
        "proj_pass_yds": np.where(pos == "QB", 4000.0, 0.0), "proj_pass_td": np.where(pos == "QB", 25.0, 0.0),
        "proj_pass_int": np.where(pos == "QB", 10.0, 0.0),
        "proj_rush_att": rng.uniform(0, 250, size=n), "proj_rush_yds": rng.uniform(0, 1200, size=n),
        "proj_rush_td": rng.uniform(0, 12, size=n), "proj_targets": rng.uniform(0, 150, size=n),
        "proj_rec": rng.uniform(0, 100, size=n), "proj_rec_yds": rng.uniform(0, 1400, size=n),
        "proj_rec_td": rng.uniform(0, 10, size=n), "proj_two_pt": np.nan,
    })
    df["proj_rec"] = np.minimum(df["proj_rec"], df["proj_targets"])
    df["proj_fumbles_lost"] = np.round((df["proj_rush_att"] + df["proj_rec"]) * 0.006, 2)
    return SP.score_line(df, prefix="proj_")


def test_recalibrate_projected_frame_scales_the_line_and_leaves_games_untouched():
    df = _projected_frame()
    k = {"QB": 0.93, "RB": 1.25, "WR": 1.10, "TE": 1.11}
    out = SLR.recalibrate_projected_frame(df, "pos_const", k, score_line=SP.score_line)
    assert np.array_equal(out["proj_games"].to_numpy(), df["proj_games"].to_numpy())
    kk = df["position"].map(k).fillna(1.0).to_numpy()
    for col in ("proj_fp_ppr", "proj_fp_std", "proj_fp_half"):
        assert np.allclose(out[col].to_numpy(), df[col].to_numpy() * kk, rtol=1e-6, atol=0.05)
    fb = (df["position"] == "FB").to_numpy()
    if fb.any():
        assert np.allclose(out.loc[fb, "proj_fp_ppr"], df.loc[fb, "proj_fp_ppr"])
    # the line re-scores to the point (no stale proj_fp_ppr): re-scoring reproduces the column
    assert np.allclose(SP.score_line(out, prefix="proj_")["proj_fp_ppr"], out["proj_fp_ppr"])
    assert SLR.SCALE_COL in out.columns and np.allclose(out[SLR.SCALE_COL], kk)
    # per-game RATE moved by exactly k; games did not
    rate_before = df["proj_fp_ppr"] / df["proj_games"]
    rate_after = out["proj_fp_ppr"] / out["proj_games"]
    assert np.allclose(rate_after, rate_before * kk, rtol=1e-6, atol=0.01)


def test_recalibrate_projected_frame_raises_if_games_move():
    df = _projected_frame()

    def _bad_score(frame, prefix="proj_"):
        frame = frame.copy(); frame["proj_games"] = frame["proj_games"] + 1.0
        return SP.score_line(frame, prefix=prefix)

    with pytest.raises(AssertionError, match="L4"):
        SLR.recalibrate_projected_frame(df, "pos_const", {"RB": 1.2}, score_line=_bad_score)


def test_identity_when_serving_is_off():
    df = _projected_frame()
    assert SLR.recalibrate_projected_frame(df, "", {}, score_line=SP.score_line) is df
    assert SLR.recalibrate_projected_frame(df, "pos_const", {}, score_line=SP.score_line) is df


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The decomposition identity (Step 1)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_decomposition_identity_and_zero_game_rows_carry_no_rate_term():
    p = np.array([100.0, 200.0, 150.0]); y = np.array([0.0, 220.0, 120.0])
    gh = np.array([15.0, 16.0, 14.0]); gr = np.array([0.0, 17.0, 10.0])
    d = SLR.decompose_bias(p, y, gh, gr, ["RB", "RB", "WR"])
    assert d["identity_holds"]
    pooled = d["pooled"]
    assert abs(pooled["availability_part"] + pooled["rate_part"] - pooled["bias"]) < 1e-9
    # row 0 (zero games): whole bias is availability
    d0 = SLR.decompose_bias(p[:1], y[:1], gh[:1], gr[:1], ["RB"])["pooled"]
    assert abs(d0["rate_part"]) < 1e-12 and abs(d0["availability_part"] - 100.0) < 1e-9


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The level gates — one ISOLATING fixture per clause (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════
_SE = {"QB": 4.0, "RB": 4.0, "WR": 3.0, "TE": 4.0, "pooled": 2.0}
_INC = {"QB": -0.5, "RB": -21.0, "WR": -15.0, "TE": -9.0, "pooled": -12.0}


def _gate(win, over=True, games=True):
    return SLR.level_gate(bias_inc=_INC, bias_win=win, se=_SE, over_scale_loses=over,
                          games_untouched=games)


def test_level_gate_passes_a_calibrated_correction():
    g = _gate({"QB": 1.0, "RB": -5.0, "WR": 1.5, "TE": 3.0, "pooled": 1.4})
    assert g["pass"] and g["L1_pooled_reduced"] and g["L2_all"] and g["L3_no_inflation"]


def test_L1_fails_alone_when_the_pooled_miss_is_not_halved():
    # every position within its allowance, not hot, games fine — pooled reduction only 40%
    g = _gate({"QB": 1.0, "RB": -8.0, "WR": -7.0, "TE": -4.0, "pooled": -7.2})
    assert not g["L1_pooled_reduced"] and g["L2_all"] and g["L3_no_inflation"] and not g["pass"]


def test_L2_fails_alone_on_one_position_outside_its_allowance():
    # pooled halved and not hot; RB still at −12 (> 0.5·21 = 10.5 and > 2·SE = 8)
    g = _gate({"QB": 1.0, "RB": -12.0, "WR": 1.0, "TE": 1.0, "pooled": -1.5})
    assert g["L1_pooled_reduced"] and g["L3_no_inflation"] and not g["L2_per_position"]["RB"]
    assert g["L2_per_position"]["QB"] and not g["pass"]


def test_L3_fails_alone_when_the_winner_is_significantly_hot():
    # halved (|+5.5| < 6) and every position within allowance, but pooled +5.5 > 2·SE = 4
    g = _gate({"QB": 5.0, "RB": 4.0, "WR": 5.0, "TE": 6.0, "pooled": 5.5})
    assert g["L1_pooled_reduced"] and g["L2_all"] and not g["L3_no_inflation"] and not g["pass"]


def test_L3_fails_alone_when_over_scale_wins():
    g = _gate({"QB": 1.0, "RB": -5.0, "WR": 1.5, "TE": 3.0, "pooled": 1.4}, over=False)
    assert g["L1_pooled_reduced"] and g["L2_all"] and not g["L3_no_inflation"] and not g["pass"]


def test_L4_fails_alone_when_games_moved():
    g = _gate({"QB": 1.0, "RB": -5.0, "WR": 1.5, "TE": 3.0, "pooled": 1.4}, games=False)
    assert g["L1_pooled_reduced"] and g["L2_all"] and g["L3_no_inflation"] and not g["pass"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. SERVING — the band stays byte-identical under the level shift (the FIXED treatment)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _band_model():
    rng = np.random.default_rng(7)
    n = 900
    pos = rng.choice(["QB", "RB", "WR", "TE"], size=n)
    point = rng.uniform(20, 300, size=n)
    real = np.clip(point * 1.1 + rng.normal(0, 40, size=n), 0, None)
    panel = pd.DataFrame({"position": pos, "point": point, "season_sd": rng.uniform(20, 60, size=n),
                          "proj_games": rng.uniform(8, 17, size=n), "base_games": 15.0,
                          "snap_share": 0.5, "seasons_missed": 0.0, "real_fp_ppr": real,
                          "target_season": rng.choice([2020, 2021, 2022], size=n)})
    m = SP.fit_veteran_band_model(panel, form="knn_norm", k=50)
    assert m is not None
    return m


def _vet_frame(n=60, seed=11):
    rng = np.random.default_rng(seed)
    pos = rng.choice(["QB", "RB", "WR", "TE"], size=n)
    df = pd.DataFrame({"position": pos, "proj_games": rng.uniform(8, 17, size=n),
                       "proj_fp_ppr": rng.uniform(30, 280, size=n),
                       "fp_ppr_sd": rng.uniform(4, 9, size=n),
                       "depth_chart_position_rank": rng.integers(1, 4, size=n),
                       "games_played": 15, "snap_share": 0.5})
    return df


def test_band_is_byte_identical_under_the_level_shift_when_queried_at_the_incumbent_equivalent():
    m = _band_model()
    base = _vet_frame()
    inc = SP.attach_season_interval(base, band_model=m)
    k = {"QB": 0.93, "RB": 1.25, "WR": 1.10, "TE": 1.11}
    kk = base["position"].map(k).to_numpy()
    shifted = base.copy()
    shifted["proj_fp_ppr"] = base["proj_fp_ppr"] * kk
    shifted["veteran_level_form"] = "pos_const"
    shifted["veteran_level_params"] = SLR.params_to_json(k)
    out = SP.attach_season_interval(shifted, band_model=m)
    assert (out["uncertainty_type"] == "calibrated_per_player").all()
    # the band edges equal the incumbent's, except where the served point brackets them outward
    inc_lo, inc_hi = inc["fp_ppr_p10"].to_numpy(), inc["fp_ppr_p90"].to_numpy()
    new_lo, new_hi = out["fp_ppr_p10"].to_numpy(), out["fp_ppr_p90"].to_numpy()
    pt = out["proj_fp_ppr"].to_numpy()
    assert np.allclose(new_lo, np.minimum(inc_lo, np.floor(pt * 10) / 10), atol=0.1001)
    assert np.allclose(new_hi, np.maximum(inc_hi, pt), atol=0.1001)
    assert (new_lo <= pt + 1e-9).all() and (new_hi >= pt - 1e-9).all()
    # ⛔ the naive path — the SAME shifted point WITHOUT the stamp — re-derives a DIFFERENT band
    naive = SP.attach_season_interval(shifted.drop(columns=["veteran_level_form",
                                                             "veteran_level_params"]),
                                      band_model=m)
    assert not np.allclose(naive["fp_ppr_p90"].to_numpy(), inc_hi, atol=0.5)


def test_rookie_rows_are_never_inverted_by_a_board_wide_stamp():
    m = _band_model()
    base = _vet_frame()
    base["is_rookie"] = False
    base.loc[base.index[:10], "is_rookie"] = True
    stamped = base.copy()
    stamped["veteran_level_form"] = "pos_const"
    stamped["veteran_level_params"] = SLR.params_to_json({"QB": 2.0, "RB": 2.0, "WR": 2.0, "TE": 2.0})
    plain = SP.attach_season_interval(base, band_model=m)
    out = SP.attach_season_interval(stamped, band_model=m)
    rk = base["is_rookie"].to_numpy()
    assert np.allclose(out.loc[rk, "fp_ppr_p90"], plain.loc[rk, "fp_ppr_p90"])
    assert not np.allclose(out.loc[~rk, "fp_ppr_p90"], plain.loc[~rk, "fp_ppr_p90"])


def test_project_veterans_applies_the_level_before_the_band_and_stamps_the_frame():
    # a minimal base-season frame through the SERVED path, level on vs off
    rng = np.random.default_rng(5)
    n = 40
    pos = rng.choice(["QB", "RB", "WR", "TE"], size=n)
    base = pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)], "player_name": "x", "position": pos, "team_id": "T",
        "games_played": rng.integers(10, 17, size=n), "depth_chart_position_rank": 1,
        "fp_ppr_sd": rng.uniform(4, 9, size=n),
        **{f"{s}_pg": rng.uniform(0, 5, size=n) for s in SP._VET_PERGAME_STATS},
    })
    priors = SP.positional_pergame_priors(base)
    off = SP.project_veterans(base, priors, 2026, usage_role_blend=0.0, mover_opportunity_blend=0.0,
                              env_tilt_blend=0.0, injury_override_blend=0.0, absence_prior_blend=0.0)
    k = {"QB": 0.9, "RB": 1.3, "WR": 1.1, "TE": 1.2}
    on = SP.project_veterans(base, priors, 2026, usage_role_blend=0.0, mover_opportunity_blend=0.0,
                             env_tilt_blend=0.0, injury_override_blend=0.0, absence_prior_blend=0.0,
                             level_recal=("pos_const", k))
    kk = off["position"].map(k).to_numpy()
    assert np.allclose(on["proj_fp_ppr"], off["proj_fp_ppr"] * kk, rtol=1e-6, atol=0.05)
    assert np.array_equal(on["proj_games"].to_numpy(), off["proj_games"].to_numpy())
    assert (on["veteran_level_form"] == "pos_const").all()
    assert json.loads(on["veteran_level_params"].iloc[0]) == pytest.approx(k)
    # off ⇒ no stamp columns at all (the identity path is the pre-NF-TR2 path, not a stamped no-op)
    assert "veteran_level_form" not in off.columns
    # the interval brackets the served point on every row
    assert (on["fp_ppr_p10"] <= on["proj_fp_ppr"] + 1e-9).all()
    assert (on["fp_ppr_p90"] >= on["proj_fp_ppr"] - 1e-9).all()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. Policy + stamps + exporter
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_policy_flip_is_one_read_and_coherent(monkeypatch):
    assert VLP.serving_form() == (VLP.FORM if VLP.SERVING_ENABLED else "")
    monkeypatch.setattr(VLP, "SERVING_ENABLED", False)
    assert VLP.serving_form() == ""
    st = VLP.stamp()
    assert st["veteran_level_status"] == "incumbent" and st["level_model_version"] == "nfl_fantasy_fastpath_v1"
    monkeypatch.setattr(VLP, "SERVING_ENABLED", True)
    monkeypatch.setattr(VLP, "DISPOSITION", "CONSTRAINT_REFUSED")
    with pytest.raises(RuntimeError, match="INCOHERENT"):
        VLP.assert_coherent()


def test_output_cols_carry_the_veteran_level_stamp():
    for c in ("veteran_level_status", "veteran_level_form", "veteran_level_params",
              "veteran_level_window", "veteran_level_source_model", "level_model_version"):
        assert c in OUTPUT_COLS


def test_exporter_reads_the_stamp_off_the_board_and_decodes_params():
    pdf = pd.DataFrame({"veteran_level_status": ["recalibrated"] * 3,
                        "veteran_level_form": ["pos_const"] * 3,
                        "veteran_level_params": [SLR.params_to_json({"RB": 1.25})] * 3,
                        "veteran_level_window": [5] * 3,
                        "level_model_version": [SLR.TR2B_MODEL_VERSION] * 3})
    st = EX.veteran_level_stamp(pdf)
    assert st["form"] == "pos_const" and st["params"] == {"RB": 1.25} and st["window_seasons"] == 5
    assert st["level_model_version"] == SLR.TR2B_MODEL_VERSION
    assert EX.veteran_level_stamp(pd.DataFrame({"x": [1]})) is None
    two = pdf.copy(); two.loc[0, "veteran_level_form"] = "pos_affine"
    with pytest.raises(ValueError, match="distinct"):
        EX.veteran_level_stamp(two)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The recorded runs are pinned (the record cannot be quietly rewritten)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _rec(name):
    p = _REC / name
    if not p.exists():
        pytest.skip(f"{name} not present")
    return json.loads(p.read_text())


def test_recorded_tr2_is_refused_by_its_own_level_gate_and_tr2b_ships():
    a = _rec("nf_tr2_level_recalibration.json")
    b = _rec("nf_tr2_level_recalibration_b.json")
    assert a["story"] == "NF-TR2" and a["window"] is None
    assert a["gate_table"]["ship"] is True                  # every inherited gate passed …
    assert a["level_gate"]["pass"] is False                 # … and the level gate refused it
    assert a["verdict"]["ship"] is False and a["null"]["state"] == "CONSTRAINT_REFUSED"
    assert b["story"] == "NF-TR2b" and b["window"] == SLR.WINDOW_SEASONS
    assert b["verdict"]["ship"] is True and b["level_gate"]["pass"] is True
    assert b["selection"]["winner"]["form"] == VLP.FORM
    assert b["preregistration"]["declared_field_size"] == 3
    assert b["window_derivation"]["derived_window"] == b["window_derivation"]["pinned_window"] == 5
    # both DSR readings are on the page (the narrower family cannot launder the result)
    dd = b["deflation_disclosure"]
    assert dd["dsr_declared_field"] is not None and dd["dsr_under_b3_field"] is not None
    # rank identity per fold, availability untouched, over_scale lost, premise + rate-miss confirmed
    assert all(v["order_identical"] and v["delta_rho_identical"] for v in b["rank_identity"].values())
    assert b["level_gate"]["L4_availability_preserved"] and b["verdict"]["over_scale_loses"]
    assert b["decomposition"]["tier"]["miss_is_rate"] and b["premise"]["premise_confirmed"]
    # the board diff: within-position order identical, rookies untouched
    for dfx in b["serving"]["diffs"]:
        assert dfx["rookies_untouched"] and all(r["order_identical"] for r in dfx["per_position"])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. Governance readback reconciles the level stamp (a stamp nobody reads is décor)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_live_readback_reconciles_level_model_version(tmp_path):
    from betting_ml.governance import publish as GP
    from betting_ml.governance import registry as GR
    reg = tmp_path / "reg.yaml"
    entry = {"served_version": "v1", "level_model_version": "nfl_fantasy_fastpath_v1",
             "rookie_selection_status": "incumbent", "rookie_shrink_lambda": 0.0,
             "rookie_statistically_selected": False, "promotion_status": "champion",
             "model_family": "nfl_fantasy", "target": "season_projection"}
    GR.write_registry({GR.entry_key("nfl_fantasy", "season_projection", "v1"): entry}, reg) \
        if hasattr(GR, "write_registry") else reg.write_text(
            __import__("yaml").safe_dump({GR.entry_key("nfl_fantasy", "season_projection", "v1"): entry}))
    base = {"model_version": "v1", "rookie_policy": {"selection_status": "incumbent",
                                                       "shrink_lambda": 0.0,
                                                       "statistically_selected": False}}
    absent = GP.live_readback(model_family="nfl_fantasy", target="season_projection",
                              served_version="v1", live_payload=base, registry_path=reg)
    lvl = [c for c in absent["checks"] if c["check"] == "level_model_version"][0]
    assert lvl["status"] == "PASS" and lvl["got"] is None            # honest absence
    bad = dict(base, veteran_level_policy={"level_model_version": SLR.TR2B_MODEL_VERSION})
    disagree = GP.live_readback(model_family="nfl_fantasy", target="season_projection",
                                served_version="v1", live_payload=bad, registry_path=reg)
    lvl = [c for c in disagree["checks"] if c["check"] == "level_model_version"][0]
    assert lvl["status"] == "FAIL" and disagree["pass"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 12. The BUILD-time fit is actually INVOKED (wired ≠ invoked, NF-C0e). The first cut inlined the
#     fit in `build_projection` and no test executed it — a NameError shipped and only the operator's
#     real rebuild found it. This runs `fit_serving_level` with the policy ON on a panel shaped like
#     the real one and demands a fitted constant for every recalibrated position.
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_build_time_level_fit_is_invoked_and_returns_a_constant_per_position(monkeypatch, caplog):
    import logging
    from quant_sports_intel_models.football.nfl.fantasy import run_season_projection as RSP
    from quant_sports_intel_models.football.nfl.fantasy import veteran_level_policy as VLP

    monkeypatch.setattr(VLP, "SERVING_ENABLED", True)
    rng = np.random.default_rng(7)
    rows = []
    for season in range(2018, 2026):
        for pos, k in (("QB", 0.95), ("RB", 1.20), ("WR", 1.10), ("TE", 1.05)):
            n = 60
            p = rng.uniform(40, 320, size=n)
            y = np.clip(k * p + rng.normal(0, 25, size=n), 0, None)
            for i in range(n):
                rows.append({"target_season": season, "position": pos, "point": p[i],
                             "real_fp_ppr": y[i], "proj_games": rng.uniform(10, 17)})
    panel = pd.DataFrame(rows)
    with caplog.at_level(logging.INFO):
        form, params = RSP.fit_serving_level(panel, 2026)
    assert form == VLP.FORM == "pos_const"
    assert set(params) == set(VLP.RECALIBRATED_POSITIONS), params
    assert all(0.8 < v < 1.4 for v in params.values()), params
    # the mean-match direction on the synthetic lifts: RB above QB
    assert params["RB"] > params["QB"]
    assert any("veteran LEVEL recalibration ON" in r.getMessage() for r in caplog.records)
    # and OFF is the identity, loudly
    monkeypatch.setattr(VLP, "SERVING_ENABLED", False)
    with caplog.at_level(logging.WARNING):
        assert RSP.fit_serving_level(panel, 2026) == ("", {})
    assert any("rollback state" in r.getMessage() for r in caplog.records)
