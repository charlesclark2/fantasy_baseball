"""MLB Edge-E7.3p — PITCHER MiLB→MLB translation MLE guards (the E7.3 batter harness, reused).

Fast-gate only: pure numpy/pandas/sklearn over a SYNTHETIC graduated-pitcher universe, no DuckDB, no
S3, no `pipeline` import (the fast gate has no dbt manifest — CLAUDE.md's fast-gate rule).

What these tests are for (model-quality gates are BEHAVIORAL — CI mocks all IO and cannot see this):
  * the pitcher metric math (K%/BB%/HR-rate/GB-out-share/start-share from `pit_*` box counts, per-TBF)
    is correct — one formula home; `minor_pa` = TBF so the shared harness floors read exposure right;
  * the plausibility/uncertainty gate tables COVER every pre-registered pitcher metric (a missing key
    would KeyError the runner mid-bake-off on the operator's machine, not in CI);
  * the BATTER defaults are UNCHANGED (E7.3 is DONE and serving through E7.5 — this story must not
    perturb it): MleConfig() still emits batter/`milb_mle_v1` and the GBM still reads STATCAST_COLS;
  * the bake-off recovers a planted pitcher minor→MLB translation, the winner beats the level-mean
    NULL FLOOR, and the oracle floor holds (the E2.1-r inverted-metric tell);
  * the GBM actually reads the pitcher aux channel (AAA stuff/velo/spin + start-share role feature,
    impute-flagged) and clone_projector preserves it across expanding-window refits;
  * the partial-pool keeps its variance components alive on thin pitcher data (the P1.2 collapse bug
    — the Gamma(2,·) + multi-start cure must hold on this response too);
  * the leakage contract holds by DEBUT COHORT under the pitcher config (future cohort cannot move an
    earlier projection);
  * emission stamps `player_type='pitcher'` / `milb_mle_pitcher_v1`, clips to the plausible range,
    never emits the seed cohort, and flags prospects;
  * a data-thin metric (xwoba_against's AAA-2022+-only feature) raises the ValueError the runner
    catches as an HONEST skip — never a forced fit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle import milb_mle as mle

_LEVELS = ["Triple-A", "Double-A", "High-A", "Single-A"]
_LEAGUES = {"Triple-A": "International", "Double-A": "Texas", "High-A": "Midwest", "Single-A": "Carolina"}
# planted per-level K% translation: MLB_k = slope·minor_k + level_offset + noise. Lower levels
# discount harder (a Single-A 30% K rate is worth less MLB K% than a AAA 30%) → real LEVEL factors,
# so a translation must beat the level-mean null AND the raw-identity benchmark.
_K_SLOPE = 0.70
_K_OFFSET = {"Triple-A": 0.045, "Double-A": 0.025, "High-A": 0.010, "Single-A": -0.005}

_SC_COLS = [c for c in mle.PITCHER_STATCAST_COLS if c != "sc_xwoba_against"]


def _simulate(cohorts=(2015, 2016, 2017, 2018, 2019, 2020, 2021), seed=11, per_cohort=14,
              noise=0.020, include_prospects=True, levels=None):
    """A synthetic E7.3p pairs frame: graduated pitchers (a pre-debut minor line + a realized MLB
    line driven by a planted per-level translation) across debut cohorts, plus active prospects (no
    MLB label). Grain is one row per (player, level)."""
    rng = np.random.default_rng(seed)
    levels = levels or _LEVELS
    rows = []
    pid = 0
    for cohort in cohorts:
        for _ in range(per_cohort):
            pid += 1
            level = levels[rng.integers(0, len(levels))]
            minor_k = float(np.clip(rng.normal(0.24, 0.05), 0.08, 0.42))
            minor_bb = float(np.clip(rng.normal(0.09, 0.03), 0.02, 0.20))
            minor_hr = float(np.clip(rng.normal(0.022, 0.008), 0.002, 0.06))
            minor_gb = float(np.clip(rng.normal(0.50, 0.08), 0.25, 0.75))
            aaa = level == "Triple-A"
            sc_xw = float(np.clip(rng.normal(0.310, 0.025), 0.22, 0.42)) if aaa else np.nan
            rows.append({
                "player_id": f"{pid}", "player_name": f"P{pid}", "level": level,
                "league": _LEAGUES[level], "age": float(rng.normal(24, 1.5)),
                "minor_pa": int(rng.integers(200, 700)),
                "minor_k_pct": minor_k, "minor_bb_pct": minor_bb, "minor_hr_rate": minor_hr,
                "minor_gb_pct": minor_gb, "minor_xwoba_against": sc_xw,
                "minor_start_share": float(rng.uniform(0.0, 1.0)),
                "sc_xwoba_against": sc_xw,
                **{c: np.nan for c in _SC_COLS},
                "debut_cohort": cohort, "mlb_pa": int(rng.integers(200, 900)),
                "mlb_k_pct": _K_SLOPE * minor_k + _K_OFFSET[level] + float(rng.normal(0, noise)),
                "mlb_bb_pct": 0.6 * minor_bb + 0.025 + float(rng.normal(0, noise)),
                "mlb_hr_rate": 0.8 * minor_hr + 0.006 + float(rng.normal(0, 0.004)),
                "mlb_gb_pct": 0.85 * minor_gb + 0.045 + float(rng.normal(0, noise)),
                "mlb_xwoba_against": (0.6 * sc_xw + 0.130 + float(rng.normal(0, 0.010)))
                                     if aaa else np.nan,
            })
    if include_prospects:
        for _ in range(20):
            pid += 1
            level = levels[rng.integers(0, len(levels))]
            rows.append({
                "player_id": f"{pid}", "player_name": f"Prospect{pid}", "level": level,
                "league": _LEAGUES[level], "age": float(rng.normal(21.5, 1.0)),
                "minor_pa": int(rng.integers(200, 500)),
                "minor_k_pct": float(np.clip(rng.normal(0.26, 0.05), 0.08, 0.42)),
                "minor_bb_pct": 0.09, "minor_hr_rate": 0.02, "minor_gb_pct": 0.5,
                "minor_xwoba_against": np.nan, "minor_start_share": 0.8,
                "sc_xwoba_against": np.nan, **{c: np.nan for c in _SC_COLS},
                "debut_cohort": np.nan, "mlb_pa": np.nan, "mlb_k_pct": np.nan, "mlb_bb_pct": np.nan,
                "mlb_hr_rate": np.nan, "mlb_gb_pct": np.nan, "mlb_xwoba_against": np.nan,
            })
    return pd.DataFrame(rows)


def _fast(metric: str = "k_pct") -> mle.MleConfig:
    return mle.MleConfig(metric=metric, pool_prior_scales=(2.0,), gbm_grid=((60, 2, 0.08),),
                         aux_cols=mle.PITCHER_AUX_COLS, player_type="pitcher",
                         model_version=mle.PITCHER_MODEL_VERSION)


# ── 1. pitcher metric math ──────────────────────────────────────────────────────────────

def test_pitcher_rate_math_from_counts():
    # a hand-checkable line: 400 TBF, 110 K, 35 BB, 9 HR, 120 GO, 80 AO, 25 G (20 GS).
    df = pd.DataFrame([{
        "pit_batters_faced": 400, "pit_strike_outs": 110, "pit_walks": 35, "pit_home_runs": 9,
        "pit_ground_outs": 120, "pit_air_outs": 80, "pit_games_played": 25, "pit_games_started": 20,
        "sc_xwoba_against": 0.301,
    }])
    out = mle.compute_pitcher_rate_metrics_from_counts(df)
    assert out["minor_pa"].iloc[0] == pytest.approx(400)          # minor_pa IS batters faced
    assert out["minor_k_pct"].iloc[0] == pytest.approx(110 / 400)
    assert out["minor_bb_pct"].iloc[0] == pytest.approx(35 / 400)
    assert out["minor_hr_rate"].iloc[0] == pytest.approx(9 / 400)
    assert out["minor_gb_pct"].iloc[0] == pytest.approx(120 / 200)
    assert out["minor_start_share"].iloc[0] == pytest.approx(20 / 25)
    # xwoba_against's minor feature is the AAA-Statcast summary, aliased
    assert out["minor_xwoba_against"].iloc[0] == pytest.approx(0.301)


def test_pitcher_rate_math_zero_denominators_stay_nan_not_zero():
    df = pd.DataFrame([{
        "pit_batters_faced": 0, "pit_strike_outs": 0, "pit_walks": 0, "pit_home_runs": 0,
        "pit_ground_outs": 0, "pit_air_outs": 0, "pit_games_played": 0, "pit_games_started": 0,
    }])
    out = mle.compute_pitcher_rate_metrics_from_counts(df)
    for c in ("minor_k_pct", "minor_bb_pct", "minor_hr_rate", "minor_gb_pct", "minor_start_share"):
        assert np.isnan(out[c].iloc[0]), f"{c} fabricated a value from a zero denominator"


# ── 2. pre-registration completeness + batter-regression guards ─────────────────────────

def test_gate_tables_cover_every_pitcher_metric():
    for m in mle.PITCHER_METRICS:
        assert m in mle.VALID_METRICS
        assert m in mle.PLAUSIBLE_RANGE, f"PLAUSIBLE_RANGE missing {m} — the runner would KeyError"
        assert m in mle.MAX_PLAUSIBLE_SD, f"MAX_PLAUSIBLE_SD missing {m} — the runner would KeyError"
        lo, hi = mle.PLAUSIBLE_RANGE[m]
        assert lo < hi and mle.MAX_PLAUSIBLE_SD[m] > 0


def test_batter_defaults_are_unchanged_by_the_pitcher_extension():
    # E7.3 is DONE and serving (E7.5) — the pitcher story must not perturb the batter path.
    cfg = mle.MleConfig()
    assert cfg.player_type == "batter"
    assert cfg.model_version == mle.MODEL_VERSION == "milb_mle_v1"
    assert cfg.aux_cols == mle.STATCAST_COLS
    gbm = mle.GBMProjector()
    assert gbm.aux_cols == mle.STATCAST_COLS


# ── 3. bake-off recovers the planted pitcher translation ────────────────────────────────

def test_pitcher_bakeoff_winner_beats_the_level_mean_null():
    bake = mle.run_bakeoff(_simulate(), _fast("k_pct"))
    lb = bake.leaderboard
    null_mae = float(lb.loc[lb["config"] == "level_mean", "oos_mae"].iloc[0])
    win_mae = float(lb[lb["selectable"]]["oos_mae"].min())
    assert win_mae < null_mae, f"winner {win_mae:.4f} did not beat the null {null_mae:.4f}"
    assert bake.winner_name not in mle._NON_SELECTABLE
    assert bake.oracle_floor_ok


def test_pitcher_hr_rate_bakeoff_runs_and_respects_oracle_floor():
    bake = mle.run_bakeoff(_simulate(), _fast("hr_rate"))
    assert bake.oracle_floor_ok
    assert float(bake.leaderboard["oos_mae"].min()) >= -1e-9


# ── 4. the GBM aux channel (stuff + start-share) is real and clone-stable ───────────────

def test_gbm_reads_the_pitcher_aux_cols_and_clone_preserves_them():
    d = mle.build_target(_simulate(), _fast("k_pct"))
    lab = d[d["has_target"]]
    gbm = mle.GBMProjector(60, 2, 0.08, use_statcast=True, aux_cols=mle.PITCHER_AUX_COLS).fit(lab)
    fitted_aux = [s.col for s in gbm.statcast_scalers_]
    assert fitted_aux == list(mle.PITCHER_AUX_COLS)
    assert "minor_start_share" in fitted_aux          # the role feature rides the aux channel
    clone = mle.clone_projector(gbm)
    assert clone.aux_cols == gbm.aux_cols, "clone dropped aux_cols — refits would silently lose the add"
    # and the feature matrix actually widens vs the batter default (2 cols per aux: value + flag)
    base = mle.GBMProjector(60, 2, 0.08, use_statcast=False).fit(lab)
    assert gbm._features(lab).shape[1] == base._features(lab).shape[1] + 2 * len(mle.PITCHER_AUX_COLS)


# ── 5. partial-pool variance components stay alive on pitcher data (the P1.2 bug) ───────

def test_partial_pool_keeps_variance_components_alive_on_thin_pitcher_data():
    d = mle.build_target(_simulate(cohorts=(2015, 2016)), _fast("k_pct"))
    lab = d[d["has_target"]]
    pool = mle.PartialPoolProjector(prior_scale=2.0).fit(lab)
    for name in ("level_intercept", "level_slope"):
        tau = float(np.sqrt(pool.post_.variances[name]))
        assert tau > 1e-3, f"variance component {name} collapsed (tau={tau})"


# ── 6. leakage contract under the pitcher config ────────────────────────────────────────

def test_a_future_cohort_cannot_change_an_earlier_pitcher_projection():
    sim = _simulate()
    factory = lambda: mle.PartialPoolProjector(prior_scale=2.0)
    cfg = _fast("k_pct")
    base = mle.emit_projections(sim, factory, cfg)

    tampered = sim.copy()
    late = int(tampered["debut_cohort"].dropna().max())
    tampered.loc[tampered["debut_cohort"] == late, "mlb_k_pct"] = 0.55
    after = mle.emit_projections(tampered, factory, cfg)

    early = base[base["debut_cohort"] < late].merge(
        after[after["debut_cohort"] < late], on=["player_id", "level"], suffixes=("_a", "_b"))
    assert len(early) > 0
    assert np.allclose(early["mle_k_pct_a"], early["mle_k_pct_b"]), (
        "a future debut cohort's MLB line moved an earlier cohort's projection — the window leaks")


# ── 7. emission semantics ───────────────────────────────────────────────────────────────

def test_emission_stamps_pitcher_type_version_clips_and_flags_prospects():
    cfg = _fast("k_pct")
    proj = mle.emit_projections(_simulate(), lambda: mle.PartialPoolProjector(2.0), cfg)
    assert (proj["player_type"] == "pitcher").all()
    assert (proj["model_version"] == "milb_mle_pitcher_v1").all()
    lo, hi = mle.PLAUSIBLE_RANGE["k_pct"]
    assert proj["mle_k_pct"].between(lo, hi).all()
    assert proj["is_prospect"].any(), "prospects (the E8.0 board deliverable) were not emitted"
    # seed cohort never emitted; every emission fit on a strictly-prior window
    graduated = proj[~proj["is_prospect"]]
    assert int(graduated["debut_cohort"].min()) > 2015
    assert (proj["n_prior_cohorts"] >= 1).all()


# ── 8. a data-thin metric is an honest skip, not a forced fit ───────────────────────────

def test_data_thin_xwoba_against_raises_the_value_error_the_runner_skips_on():
    # only ONE cohort carries the AAA-Statcast feature → <2 evaluable debut cohorts for the metric
    sim = _simulate(cohorts=(2018, 2019, 2020))
    thin = sim.copy()
    mask = thin["debut_cohort"] != 2020
    thin.loc[mask, "minor_xwoba_against"] = np.nan
    thin.loc[mask, "sc_xwoba_against"] = np.nan
    thin.loc[mask, "mlb_xwoba_against"] = np.nan
    with pytest.raises(ValueError, match="cohort"):
        mle.run_bakeoff(thin, _fast("xwoba_against"))
