"""MLB Edge-E7.3 — MiLB→MLB translation MLE (the modeling crux) guards.

Fast-gate only: pure numpy/pandas/sklearn over a SYNTHETIC graduated-player universe, no DuckDB, no S3,
no `pipeline` import (the fast gate has no dbt manifest — CLAUDE.md's fast-gate rule).

What these tests are for (model-quality gates are BEHAVIORAL — CI mocks all IO and cannot see this class):
  * the metric math (wOBA / K% / BB% / ISO from box counts) is correct — one formula home;
  * a row is labelled only with BOTH a thick pre-debut minor line AND a realized MLB line at the PA
    floor; a prospect / thin line stays UNKNOWN, never 0;
  * the bake-off recovers a planted minor→MLB translation signal, the winner beats the level-mean NULL
    FLOOR, and the identity / archetype benchmarks are REPORTED but never selected;
  * the partial-pool candidate SHRINKS a thin level cell toward the global line and no variance
    component collapses to 0 (the P1.2 bug, one rung down);
  * ⭐ the leakage contract holds by DEBUT COHORT: a future cohort cannot move an earlier cohort's
    projection, and it is verified to FAIL on a tampered PRIOR cohort (so green means something);
  * the ORACLE-FLOOR sanity holds (no candidate beats a target-seeing model — the E2.1-r tell);
  * prospects (no MLB label) are emitted (flagged), never a fabricated 0; projections are clipped to the
    physically-plausible range.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle import milb_mle as mle

_LEVELS = ["Triple-A", "Double-A", "High-A", "Single-A"]
_LEAGUES = {"Triple-A": "International", "Double-A": "Texas", "High-A": "Midwest", "Single-A": "Carolina"}
# planted per-level translation: MLB_woba = slope·minor_woba + level_offset + noise. Lower levels
# discount harder (a Single-A .350 is worth less MLB wOBA than a AAA .350) → real LEVEL factors, so a
# translation must beat the level-mean null AND the raw-identity benchmark.
_SLOPE = 0.55
_LEVEL_OFFSET = {"Triple-A": 0.075, "Double-A": 0.055, "High-A": 0.035, "Single-A": 0.020}


def _simulate(cohorts=(2015, 2016, 2017, 2018, 2019, 2020, 2021), seed=7, per_cohort=14,
              noise=0.020, include_prospects=True, levels=None):
    """A synthetic E7.3 pairs frame: graduated players (a pre-debut minor line + a realized MLB line
    driven by a planted per-level translation) across debut cohorts, plus active prospects (no MLB
    label). Grain is one row per (player, level)."""
    rng = np.random.default_rng(seed)
    levels = levels or _LEVELS
    rows = []
    pid = 0
    for cohort in cohorts:
        for _ in range(per_cohort):
            pid += 1
            level = levels[rng.integers(0, len(levels))]
            minor_woba = float(np.clip(rng.normal(0.340, 0.030), 0.250, 0.440))
            minor_k = float(np.clip(rng.normal(0.22, 0.04), 0.05, 0.40))
            minor_bb = float(np.clip(rng.normal(0.09, 0.03), 0.02, 0.20))
            minor_iso = float(np.clip(rng.normal(0.170, 0.050), 0.03, 0.35))
            minor_pa = int(rng.integers(200, 600))
            mlb_woba = _SLOPE * minor_woba + _LEVEL_OFFSET[level] + float(rng.normal(0, noise))
            mlb_k = 0.6 * minor_k + 0.10 + float(rng.normal(0, noise))
            mlb_bb = 0.5 * minor_bb + 0.03 + float(rng.normal(0, noise))
            mlb_iso = 0.5 * minor_iso + 0.05 + float(rng.normal(0, noise))
            rows.append({
                "player_id": f"{pid}", "player_name": f"P{pid}", "level": level,
                "league": _LEAGUES[level], "age": float(rng.normal(23, 1.5)), "minor_pa": minor_pa,
                "minor_woba": minor_woba, "minor_k_pct": minor_k, "minor_bb_pct": minor_bb,
                "minor_iso": minor_iso, "debut_cohort": cohort, "mlb_pa": int(rng.integers(200, 700)),
                "mlb_woba": mlb_woba, "mlb_k_pct": mlb_k, "mlb_bb_pct": mlb_bb, "mlb_iso": mlb_iso,
                "sc_xwoba": (minor_woba + rng.normal(0, 0.01)) if level == "Triple-A" else np.nan,
                "sc_barrels_per_pa_percent": np.nan, "sc_hardhit_percent": np.nan,
                "sc_avg_exit_velocity_mph": np.nan, "sc_avg_bat_speed_mph": np.nan,
            })
    if include_prospects:
        for _ in range(20):
            pid += 1
            level = levels[rng.integers(0, len(levels))]
            rows.append({
                "player_id": f"{pid}", "player_name": f"Prospect{pid}", "level": level,
                "league": _LEAGUES[level], "age": float(rng.normal(21, 1.0)),
                "minor_pa": int(rng.integers(200, 500)),
                "minor_woba": float(np.clip(rng.normal(0.350, 0.030), 0.25, 0.45)),
                "minor_k_pct": 0.22, "minor_bb_pct": 0.09, "minor_iso": 0.18,
                "debut_cohort": np.nan, "mlb_pa": np.nan, "mlb_woba": np.nan, "mlb_k_pct": np.nan,
                "mlb_bb_pct": np.nan, "mlb_iso": np.nan, "sc_xwoba": np.nan,
                "sc_barrels_per_pa_percent": np.nan, "sc_hardhit_percent": np.nan,
                "sc_avg_exit_velocity_mph": np.nan, "sc_avg_bat_speed_mph": np.nan,
            })
    return pd.DataFrame(rows)


_FAST = mle.MleConfig(pool_prior_scales=(2.0,), gbm_grid=((60, 2, 0.08),))


# ── 1. metric math ──────────────────────────────────────────────────────────────────────

def test_woba_and_rate_math_from_counts():
    # a hand-checkable line: 100 PA, 90 AB, 27 H (18×1B, 5×2B, 3×3B, 1×HR), 8 BB (1 IBB), 2 HBP, 0 SF.
    df = pd.DataFrame([{
        "bat_plate_appearances": 100, "bat_at_bats": 90, "bat_hits": 27, "bat_doubles": 5,
        "bat_triples": 3, "bat_home_runs": 1, "bat_walks": 8, "bat_intentional_walks": 1,
        "bat_hit_by_pitch": 2, "bat_sac_flies": 0, "bat_strike_outs": 20,
        "bat_total_bases": 18 + 2 * 5 + 3 * 3 + 4 * 1,  # 41
    }])
    out = mle.compute_rate_metrics_from_counts(df)
    b1 = 27 - 5 - 3 - 1
    num = 0.69 * (8 - 1) + 0.72 * 2 + 0.89 * b1 + 1.27 * 5 + 1.62 * 3 + 2.10 * 1
    den = 90 + (8 - 1) + 0 + 2
    assert out["minor_woba"].iloc[0] == pytest.approx(num / den, rel=1e-9)
    assert out["minor_k_pct"].iloc[0] == pytest.approx(20 / 100)
    assert out["minor_bb_pct"].iloc[0] == pytest.approx(8 / 100)
    assert out["minor_iso"].iloc[0] == pytest.approx((41 - 27) / 90)


# ── 2. target / label construction ──────────────────────────────────────────────────────

def test_labelled_needs_both_a_thick_minor_line_and_an_mlb_label():
    sim = _simulate()
    d = mle.build_target(sim, _FAST)
    # graduated rows with both sides are labelled; prospects are not
    assert d.loc[d["player_name"].str.startswith("P") & ~d["player_name"].str.startswith("Prospect"),
                 "has_target"].any()
    assert not d.loc[d["is_prospect"], "has_target"].any()


def test_thin_minor_line_and_prospect_stay_unknown_not_zero():
    sim = _simulate(include_prospects=True)
    sim.loc[sim.index[:5], "minor_pa"] = 10  # below the min_minor_pa floor
    d = mle.build_target(sim, mle.MleConfig(min_minor_pa=150))
    assert not d.loc[d.index[:5], "has_minor_line"].any()
    # a prospect carries a projection-eligible minor line but NO target (unknown, not 0)
    prospects = d[d["is_prospect"]]
    assert len(prospects) > 0
    assert prospects["target"].isna().all()


# ── 3. partial-pool shrink + no variance collapse ───────────────────────────────────────

def test_partial_pool_keeps_variance_components_alive_on_thin_data():
    d = mle.build_target(_simulate(cohorts=(2015, 2016)), _FAST)
    lab = d[d["has_target"]]
    pool = mle.PartialPoolProjector(prior_scale=2.0).fit(lab)
    for name in ("level_intercept", "level_slope"):
        tau = float(np.sqrt(pool.post_.variances[name]))
        assert tau > 1e-3, f"variance component {name} collapsed (tau={tau})"


def test_partial_pool_shrinks_a_thin_level_cell_toward_the_global_line():
    d = mle.build_target(_simulate(seed=3), _FAST)
    lab = d[d["has_target"]].copy()
    thin_level = "Single-A"
    thin = pd.concat([lab[lab["level"] != thin_level],
                      lab[lab["level"] == thin_level].head(3)], ignore_index=True)
    pool = mle.PartialPoolProjector(prior_scale=2.0).fit(thin)
    probe = thin[thin["level"] != thin_level].head(2).copy()
    probe["level"] = thin_level
    probe.iloc[0, probe.columns.get_loc("minor_woba")] = 0.28
    probe.iloc[1, probe.columns.get_loc("minor_woba")] = 0.44
    probe["feat"] = probe["minor_woba"]
    pm, _ = pool.predict(probe)
    swing_pool = abs(pm[1] - pm[0])
    cell = lab[lab["level"] == thin_level].head(3)
    x = pool.feat_scaler_.transform(cell)[0]
    y = cell["target"].to_numpy(float)
    if np.std(x) > 0:
        b = np.polyfit(x, y, 1)[0]
        xp = pool.feat_scaler_.transform(probe)[0]
        swing_raw = abs(b * (xp[1] - xp[0]))
        assert swing_pool < swing_raw + 1e-9, "the thin level cell was not shrunk relative to its raw fit"


# ── 4. bake-off recovers signal, beats the null, respects the non-selectable benchmarks ──

def test_bakeoff_winner_beats_the_level_mean_null():
    bake = mle.run_bakeoff(_simulate(), _FAST)
    lb = bake.leaderboard
    null_mae = float(lb.loc[lb["config"] == "level_mean", "oos_mae"].iloc[0])
    win_mae = float(lb[lb["selectable"]]["oos_mae"].min())
    assert win_mae < null_mae, f"winner {win_mae:.4f} did not beat the null {null_mae:.4f}"
    assert bake.winner_name not in mle._NON_SELECTABLE


def test_benchmarks_are_never_selected_as_winner():
    bake = mle.run_bakeoff(_simulate(), _FAST)
    lb = bake.leaderboard
    for ref in ("level_mean", "identity_no_translation", "archetype_prior"):
        assert not lb.loc[lb["config"] == ref, "selectable"].iloc[0]
    assert bake.winner_name not in mle._NON_SELECTABLE


def test_oracle_floor_holds():
    bake = mle.run_bakeoff(_simulate(), _FAST)
    assert bake.oracle_floor_ok
    assert float(bake.leaderboard["oos_mae"].min()) >= -1e-9


def test_pbo_and_dsr_are_computed():
    bake = mle.run_bakeoff(_simulate(), _FAST)
    assert bake.pbo is not None
    assert 0.0 <= bake.pbo.pbo <= 1.0


# ── 5. leakage contract — by DEBUT COHORT ───────────────────────────────────────────────

def test_a_future_cohort_cannot_change_an_earlier_cohorts_projection():
    sim = _simulate()
    factory = lambda: mle.PartialPoolProjector(prior_scale=2.0)
    base = mle.emit_projections(sim, factory, _FAST)

    tampered = sim.copy()
    late = int(tampered["debut_cohort"].dropna().max())
    m = tampered["debut_cohort"] == late
    tampered.loc[m, "mlb_woba"] = 0.500
    after = mle.emit_projections(tampered, factory, _FAST)

    early = base[base["debut_cohort"] < late].merge(
        after[after["debut_cohort"] < late], on=["player_id", "level"], suffixes=("_a", "_b"))
    assert len(early) > 0
    assert np.allclose(early["mle_woba_a"], early["mle_woba_b"]), (
        "a future debut cohort's MLB line moved an earlier cohort's projection — the window leaks")


def test_tampering_a_prior_cohort_does_change_a_later_projection():
    sim = _simulate()
    factory = lambda: mle.PartialPoolProjector(prior_scale=2.0)
    base = mle.emit_projections(sim, factory, _FAST)

    tampered = sim.copy()
    early_year = sorted(sim["debut_cohort"].dropna().unique())[1]
    tampered.loc[tampered["debut_cohort"] == early_year, "mlb_woba"] += 0.10
    after = mle.emit_projections(tampered, factory, _FAST)

    latest = int(sim["debut_cohort"].dropna().max())
    b = base[base["debut_cohort"] == latest]
    a = after[after["debut_cohort"] == latest]
    merged = b.merge(a, on=["player_id", "level"], suffixes=("_a", "_b"))
    assert len(merged) > 0
    assert not np.allclose(merged["mle_woba_a"], merged["mle_woba_b"]), (
        "tampering a TRAINING cohort did not move the downstream projection — the leakage guard is blind")


def test_seed_cohort_is_never_emitted():
    proj = mle.emit_projections(_simulate(), lambda: mle.PartialPoolProjector(2.0), _FAST)
    graduated = proj[~proj["is_prospect"]]
    assert int(graduated["debut_cohort"].min()) > int(_simulate()["debut_cohort"].dropna().min())
    assert (proj["n_prior_cohorts"] >= 1).all()


# ── 6. output contract + prospects + plausibility ───────────────────────────────────────

def test_end_to_end_grain_columns_and_prospects_emitted():
    run = mle.run_milb_mle(_simulate(), _FAST)
    p = run.projections
    assert not p.duplicated(subset=["player_id", "level"]).any(), "grain must be unique"
    for c in ("sport", "player_id", "level", "metric", "mle_woba", "mle_woba_sd", "is_prospect",
              "debut_cohort", "n_prior_cohorts", "model_version"):
        assert c in p.columns, f"missing column {c}"
    assert (p["mle_woba_sd"] > 0).all()
    assert np.isfinite(p["mle_woba"]).all()
    # prospects are still emitted, flagged
    assert p["is_prospect"].any()
    assert p.loc[p["is_prospect"], "mle_woba"].notna().all()


def test_projection_is_clipped_to_the_plausible_range():
    run = mle.run_milb_mle(_simulate(), _FAST)
    lo, hi = mle.PLAUSIBLE_RANGE["woba"]
    assert run.projections["mle_woba"].between(lo, hi).all()


def test_projection_tracks_realized_mlb_line_out_of_sample():
    run = mle.run_milb_mle(_simulate(noise=0.012), _FAST)
    tgt = mle.build_target(_simulate(noise=0.012), _FAST)[["player_id", "level", "target", "has_target"]]
    merged = run.projections.merge(tgt, on=["player_id", "level"])
    merged = merged[merged["has_target"]]
    rho = float(np.corrcoef(merged["mle_woba"], merged["target"])[0, 1])
    assert rho > 0.2, f"projection↔realized correlation only {rho:.2f} — no signal recovered"


# ── 7. metric switch + validation ───────────────────────────────────────────────────────

def test_metric_switch_changes_the_label():
    sim = _simulate()
    d_woba = mle.build_target(sim, mle.MleConfig(metric="woba"))
    d_k = mle.build_target(sim, mle.MleConfig(metric="k_pct"))
    assert not np.allclose(d_woba.loc[d_woba["has_target"], "target"].to_numpy(),
                           d_k.loc[d_k["has_target"], "target"].to_numpy())


def test_invalid_metric_rejected():
    with pytest.raises(ValueError):
        mle.MleConfig(metric="ops")
