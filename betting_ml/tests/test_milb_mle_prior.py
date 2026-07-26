"""MLB Edge-E7.5 — MiLB MLE → recalibrated rookie prior (wired into eb_batter_posteriors_raw) guards.

Fast-gate only: pure numpy/pandas over a SYNTHETIC graduated-player universe, no DuckDB, no S3, no
`pipeline` import (the fast gate has no dbt manifest — CLAUDE.md's fast-gate rule).

Model-quality gates are BEHAVIORAL (CI mocks all IO and cannot see this class). What these pin:
  * the prior-strength math κ = m(1−m)/σ_resid² − 1 (clipped) and the served Beta-Binomial / Normal-Normal
    posterior means MIRROR the served eb_batter_posteriors_raw DuckDB SQL — PA=0 ⇒ the MLE mean, PA→∞ ⇒
    the observed line (the PA-accrual blend);
  * recalibration REPLACES the too-tight parameter sd with the held-out predictive spread, and the
    has_mlb_label floor is required (thin-sample cameos would blow up σ_resid);
  * the calibration ablation is leakage-safe (generic baseline uses only strictly-prior cohorts) and MLE
    beats the generic prior when the minor line genuinely translates;
  * the calibrated prior table is one row per player at the HIGHEST reached level;
  * wOBA is NOT a wired metric (E7.3: no translatable signal).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle import mle_prior as mp


# ══════════════════════════════════════════════════════════════════════════════════════
# prior-strength math (must mirror the served DuckDB SQL exactly)
# ══════════════════════════════════════════════════════════════════════════════════════


def test_kappa_matches_prior_variance_identity():
    # a Beta(m·κ, (1−m)·κ) has prior sd sqrt(m(1−m)/(κ+1)); κ from σ_resid must invert that.
    m, sd = 0.25, 0.05
    k = mp.kappa_from_resid_sd(m, sd, floor=1.0, cap=1e6)
    implied_sd = np.sqrt(m * (1 - m) / (k + 1))
    assert abs(implied_sd - sd) < 1e-9


def test_kappa_clipped_and_degenerate_safe():
    assert mp.kappa_from_resid_sd(0.25, 1e-9, floor=20, cap=400) == 400          # tiny σ → cap
    assert mp.kappa_from_resid_sd(0.25, 10.0, floor=20, cap=400) == 20           # huge σ → floor
    assert mp.kappa_from_resid_sd(0.0, 0.05) == mp.KAPPA_FLOOR                    # degenerate mean → floor
    assert np.isfinite(mp.kappa_from_resid_sd(1.0, 0.05))                         # never NaN/Inf


def test_beta_posterior_is_mle_mean_at_zero_pa_and_observed_at_high_pa():
    mean, kappa = 0.30, 90.0
    assert abs(mp.beta_posterior_mean(mean, kappa, pa=0, obs_rate=0.10) - mean) < 1e-12
    assert abs(mp.beta_posterior_mean(mean, kappa, pa=0, obs_rate=None) - mean) < 1e-12
    # 100 PA of observed 0.10 → (0.30·90 + 0.10·100)/(90+100) = 37/190 (MLE-anchored, between prior & obs)
    assert abs(mp.beta_posterior_mean(mean, kappa, pa=100, obs_rate=0.10) - 37.0 / 190.0) < 1e-12
    # PA→∞ converges to observed
    assert abs(mp.beta_posterior_mean(mean, kappa, pa=1e7, obs_rate=0.12) - 0.12) < 1e-4


def test_normal_posterior_is_prior_mean_at_zero_pa():
    assert mp.normal_posterior_mean(0.170, 0.0475, pa=0, obs_iso=0.10) == 0.170
    # some PA pulls toward observed but stays between prior and obs
    v = mp.normal_posterior_mean(0.170, 0.0475, pa=50, obs_iso=0.10)
    assert 0.10 < v < 0.170


def test_woba_is_not_a_wired_metric():
    assert "woba" not in mp.PRIOR_METRICS
    assert set(mp.PRIOR_METRICS) == {"k_pct", "bb_pct", "iso"}


# ══════════════════════════════════════════════════════════════════════════════════════
# synthetic graduated-player universe
# ══════════════════════════════════════════════════════════════════════════════════════


def _synth(seed=3, cohorts=(2016, 2017, 2018, 2019, 2020), per=40, noise=0.03,
           translate=True, thin_cameos=True):
    """A wide projections-like frame: per (player, level) rows with an emitted MLE and a realized MLB
    line. When `translate`, mlb ≈ 0.6·mle + offset + noise (a real minor→major signal); else mlb is pure
    noise (MLE carries nothing). `thin_cameos` sprinkles has_mlb_label=False rows with extreme mlb rates
    (a 1-PA K% of 1.0) that the label floor must exclude."""
    rng = np.random.default_rng(seed)
    levels = ["Triple-A", "Double-A", "High-A"]
    rows = []
    pid = 0
    for coh in cohorts:
        for _ in range(per):
            pid += 1
            for lv in levels[: rng.integers(1, 4)]:  # each player reaches 1–3 levels
                mle_k = float(np.clip(rng.normal(0.24, 0.05), 0.08, 0.42))
                mle_bb = float(np.clip(rng.normal(0.085, 0.02), 0.03, 0.16))
                mle_iso = float(np.clip(rng.normal(0.150, 0.04), 0.03, 0.33))
                if translate:
                    mlb_k = 0.6 * mle_k + 0.09 + float(rng.normal(0, noise))
                    mlb_bb = 0.6 * mle_bb + 0.03 + float(rng.normal(0, noise * 0.5))
                    mlb_iso = 0.6 * mle_iso + 0.05 + float(rng.normal(0, noise))
                else:
                    mlb_k = 0.24 + float(rng.normal(0, noise))
                    mlb_bb = 0.085 + float(rng.normal(0, noise * 0.5))
                    mlb_iso = 0.150 + float(rng.normal(0, noise))
                rows.append(dict(
                    player_id=str(pid), level=lv, debut_cohort=coh, is_prospect=False,
                    mle_k_pct=mle_k, mlb_k_pct=mlb_k, mle_k_pct_sd=0.006,
                    mle_bb_pct=mle_bb, mlb_bb_pct=mlb_bb, mle_bb_pct_sd=0.004,
                    mle_iso=mle_iso, mlb_iso=mlb_iso, mle_iso_sd=0.007,
                    mlb_pa=int(rng.integers(200, 700)), has_mlb_label=True,
                ))
    df = pd.DataFrame(rows)
    if thin_cameos:
        cameo = df.head(30).copy()
        cameo["player_id"] = ["cameo_%d" % i for i in range(len(cameo))]
        cameo["mlb_k_pct"] = 1.0            # a 1-PA strikeout — extreme, must be excluded
        cameo["mlb_pa"] = 1
        cameo["has_mlb_label"] = False
        df = pd.concat([df, cameo], ignore_index=True)
    return df


def test_recalibration_replaces_tight_param_sd_and_excludes_thin_cameos():
    df = _synth()
    calib = mp.recalibrate(df)
    for m in mp.PRIOR_METRICS:
        c = calib[m]
        # σ_resid is the honest predictive spread — much WIDER than the tiny parameter sd (E7.3 was tight)
        assert c.resid_sd > c.param_sd_median
        # the thin-cameo K%=1.0 rows (has_mlb_label=False) are excluded → σ_resid stays sane (< 0.15)
        assert c.resid_sd < 0.15, f"{m} σ_resid={c.resid_sd} — thin cameos leaked past the label floor"
        # coverage of ±σ_resid is roughly honest (~0.68), not the ~1.0 an over-tight sd would give
        assert 0.5 < c.coverage_68 < 0.85


def test_recalibration_without_label_floor_is_inflated_by_cameos():
    df = _synth(thin_cameos=True).drop(columns=["has_mlb_label"])   # no floor → cameos pollute σ_resid
    c = mp.recalibrate_metric(df, "k_pct")
    assert c.resid_sd > 0.15   # the K%=1.0 cameos blow it up — proves the floor matters


def test_calibrated_prior_table_one_row_per_player_highest_level():
    df = _synth()
    calib = mp.recalibrate(df)
    tbl = mp.build_calibrated_prior_table(df, calib)
    assert tbl["batter_id"].is_unique
    # every batter's chosen level is their highest reached (Triple-A preferred)
    hi = mp.highest_level_rows(df)[["player_id", "level"]].set_index("player_id")["level"].to_dict()
    for _, row in tbl.iterrows():
        assert row["mle_level"] == hi[row["batter_id"]]
    # κ columns present, positive, within clip
    for col in ("k_pct_prior_kappa", "bb_pct_prior_kappa"):
        v = tbl[col].dropna()
        assert (v >= mp.KAPPA_FLOOR - 1e-6).all() and (v <= mp.KAPPA_CAP + 1e-6).all()
    assert (tbl["iso_prior_sd"].dropna() == calib["iso"].resid_sd).all()


def test_highest_level_selection_prefers_nearest_to_mlb():
    df = pd.DataFrame([
        dict(player_id="1", level="Double-A", mle_k_pct=0.20),
        dict(player_id="1", level="Triple-A", mle_k_pct=0.25),
        dict(player_id="1", level="High-A", mle_k_pct=0.30),
    ])
    hi = mp.highest_level_rows(df)
    assert len(hi) == 1 and hi.iloc[0]["level"] == "Triple-A"


def test_ablation_mle_beats_generic_when_signal_translates():
    df = _synth(translate=True)
    abl = mp.ablate(df)
    for m in mp.PRIOR_METRICS:
        r = abl[m]
        assert r.mle_mae < r.generic_mae, f"{m}: MLE MAE {r.mle_mae} !< generic {r.generic_mae}"
        assert r.mle_nll < r.generic_nll, f"{m}: MLE NLL {r.mle_nll} !< generic {r.generic_nll}"
        assert r.mle_wins


def test_ablation_mle_does_not_win_when_minor_line_carries_no_signal():
    # when mlb is pure noise (no translation), the MLE mean should NOT beat the population mean
    df = _synth(translate=False)
    abl = mp.ablate_metric(df, "k_pct")
    assert not abl.mle_wins


def test_ablation_is_purged_by_cohort():
    # the earliest cohort is a seed (no strictly-prior cohort) → it is never scored; only later cohorts are
    df = _synth(cohorts=(2016, 2017, 2018), per=30)
    r = mp.ablate_metric(df, "k_pct")
    assert r.n_cohorts == 2   # 2017, 2018 (2016 is the seed)
