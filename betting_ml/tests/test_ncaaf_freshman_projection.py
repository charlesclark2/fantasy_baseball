"""NCAAF-P1.2b — recruit→freshman-production MLE guards.

Fast-gate only: pure numpy/pandas/sklearn over SYNTHETIC recruit↔production pairs, no DuckDB,
no S3, no `pipeline` import (the fast gate has no dbt manifest — CLAUDE.md's fast-gate rule).

What these tests are actually for (the P1.2 lesson: model-quality gates are BEHAVIORAL, not
green-checkmark — CI mocks all IO and cannot see this class):
  * the target is standardized WITHIN (group, class) and a NULL production stays UNKNOWN, not 0;
  * the bake-off recovers a planted recruit-rating → production signal (else every prior is
    decoration) and the winner beats the position-mean NULL FLOOR;
  * the partial-pooling candidate demonstrably SHRINKS a thin position cell toward the global
    rating→production line — the whole reason candidate (a) exists;
  * ⭐ the leakage contract holds by CLASS: a FUTURE class's production cannot move an earlier
    class's prior, and it is verified to FAIL on a tampered PRIOR class (so green means something);
  * the ORACLE-FLOOR sanity holds (no candidate beats a target-seeing model — the E2.1-r
    inverted-metric tell);
  * OL / special teams get a rating-only prior, flagged, never a fabricated production 0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.ncaaf.models import freshman_projection as fp


# ══════════════════════════════════════════════════════════════════════════════════════
# Synthetic recruit↔production universe
# ══════════════════════════════════════════════════════════════════════════════════════

_OFFENSE = ["QB", "RB", "WR", "TE"]
_DEFENSE = ["DL", "LB", "DB"]
_STAT_GROUPS = _OFFENSE + _DEFENSE
_TEAMS = [f"Team-{i}" for i in range(12)]

# planted rating→production slope per group (points of raw production per unit rating). Genuinely
# positive so the signal is there to find, but with heavy noise so the null is not trivially beaten.
_SLOPE = {"QB": 4000, "RB": 1500, "WR": 1200, "TE": 800, "DL": 120, "LB": 140, "DB": 90}


def _simulate(seasons=(2014, 2015, 2016, 2017, 2018, 2019), seed=7, per_team_pos=2,
              include_ol=True, noise=1.0):
    rng = np.random.default_rng(seed)
    rows = []
    pid = 0
    for season in seasons:
        for team in _TEAMS:
            groups = list(_STAT_GROUPS) + (["OL", "ST"] if include_ol else [])
            for grp in groups:
                for _ in range(per_team_pos):
                    pid += 1
                    rating = float(np.clip(rng.normal(0.85, 0.06), 0.6, 1.0))
                    stars = int(np.clip(round(1 + (rating - 0.6) / 0.1), 1, 5))
                    has_prod = grp in _STAT_GROUPS and rng.random() > 0.15
                    scrim = defn = 0.0
                    if grp in _OFFENSE and has_prod:
                        scrim = max(0.0, _SLOPE[grp] * rating + rng.normal(0, _SLOPE[grp] * 0.5 * noise))
                    elif grp in _DEFENSE and has_prod:
                        defn = max(0.0, _SLOPE[grp] * rating + rng.normal(0, _SLOPE[grp] * 0.5 * noise))
                    rows.append({
                        "sport": "ncaaf", "player_id": str(pid), "recruit_name": f"R{pid}",
                        "arrival_season": season, "arrival_team": team, "class_year": season,
                        "recruit_type": "HighSchool", "recruit_position": grp, "position_group": grp,
                        "stars": stars, "composite_rating": rating,
                        "national_ranking": int(rng.integers(1, 3000)),
                        "games_played": int(rng.integers(0, 13)) if has_prod else 0,
                        "scrimmage_prod": scrim, "scrimmage_tds": float(scrim > 0) * rng.integers(0, 20),
                        "defense_prod": defn, "has_production": has_prod,
                    })
    return pd.DataFrame(rows)


_FAST = fp.FreshmanConfig(pool_prior_scales=(2.0,), gbm_grid=((40, 2, 0.1),))


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. Target construction
# ══════════════════════════════════════════════════════════════════════════════════════


def test_target_is_standardized_within_group_and_season():
    d = fp.build_target(_simulate())
    lab = d[d["has_target"]]
    # each (group, season) cell of the standardized target has ~mean 0, ~sd 1
    g = lab.groupby(["position_group", "arrival_season"])["production_z"]
    assert g.mean().abs().max() < 1e-6
    sds = g.std(ddof=0)
    assert ((sds - 1.0).abs() < 1e-6).all()


def test_null_production_stays_unknown_not_zero():
    d = fp.build_target(_simulate())
    # a redshirt (has_production False) must carry NaN target, never a fabricated 0
    redshirt = d[(~d["has_production"]) & d["position_group"].isin(_STAT_GROUPS)]
    assert len(redshirt) > 0
    assert redshirt["production_z"].isna().all()


def test_ol_and_st_have_no_box_production_but_still_get_a_row():
    d = fp.build_target(_simulate())
    ol = d[d["position_group"] == "OL"]
    assert len(ol) > 0
    assert (~ol["box_production_available"]).all()
    assert ol["production_z"].isna().all(), "OL must have NO production label (box-invisible)"


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. Partial pooling — the reason candidate (a) exists
# ══════════════════════════════════════════════════════════════════════════════════════


def test_partial_pool_shrinks_a_thin_position_cell_toward_the_global_line():
    """A position group with only a couple of freshmen must be pulled toward the global
    rating→production line, not fit to its own 2 points."""
    d = fp.build_target(_simulate(seasons=(2014, 2015), seed=3))
    lab = d[d["has_target"]].copy()
    # make DB thin: keep only 3 DB pairs, leave the rest intact
    db = lab[lab["position_group"] == "DB"]
    thin = pd.concat([lab[lab["position_group"] != "DB"], db.head(3)], ignore_index=True)

    pool = fp.PartialPoolProjector(prior_scale=2.0).fit(thin)
    ols = fp.StratifiedOLSProjector(min_support=15).fit(thin)
    # the stratified OLS falls back to the global line for the thin DB cell (min_support unmet);
    # the pool must produce a DB slope BETWEEN a naive 3-point fit and the global line — i.e. its
    # DB prediction cannot swing as wildly as an unpooled 3-point regression.
    probe = pd.DataFrame({"position_group": ["DB", "DB"], "composite_rating": [0.70, 1.00]})
    pm, _ = pool.predict(probe)
    swing_pool = abs(pm[1] - pm[0])
    # a raw 3-point OLS swing (unpooled) — fit DB alone
    x = fp._rating_features(db.head(3), pool.rating_mu_, pool.rating_sd_)
    y = db.head(3)["production_z"].to_numpy(float)
    b = np.polyfit(x, y, 1)[0]
    swing_raw = abs(b * (fp._rating_features(probe, pool.rating_mu_, pool.rating_sd_)[1]
                         - fp._rating_features(probe, pool.rating_mu_, pool.rating_sd_)[0]))
    assert swing_pool < swing_raw + 1e-9, "the thin DB cell was not shrunk relative to its raw fit"


def test_partial_pool_keeps_a_variance_component_alive_on_thin_data():
    """The boundary-avoiding prior (inherited from hierarchical.py) must stop tau collapsing to 0
    on a thin fit — otherwise every position equals the global line and the group level is dead."""
    d = fp.build_target(_simulate(seasons=(2014,), seed=5))
    lab = d[d["has_target"]]
    pool = fp.PartialPoolProjector(prior_scale=2.0).fit(lab)
    tau_gi = float(np.sqrt(pool.post_.variances["group_intercept"]))
    tau_gs = float(np.sqrt(pool.post_.variances["group_slope"]))
    assert tau_gi > 1e-3 and tau_gs > 1e-3, f"a variance component collapsed (gi={tau_gi}, gs={tau_gs})"


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. The bake-off recovers signal and beats the null
# ══════════════════════════════════════════════════════════════════════════════════════


def test_bakeoff_winner_beats_the_position_mean_null():
    bake = fp.run_bakeoff(_simulate(noise=0.6), _FAST)
    lb = bake.leaderboard
    null_mae = float(lb.loc[lb["config"] == "position_mean", "oos_mae"].iloc[0])
    win_mae = float(lb["oos_mae"].min())
    assert win_mae < null_mae, f"winner {win_mae:.3f} did not beat the null {null_mae:.3f}"
    assert bake.winner_name != "position_mean"


def test_oracle_floor_holds():
    """No candidate may score a lower MAE than a target-seeing oracle (the inverted-metric tell)."""
    bake = fp.run_bakeoff(_simulate(), _FAST)
    assert bake.oracle_floor_ok
    assert float(bake.leaderboard["oos_mae"].min()) >= -1e-9


def test_pbo_and_dsr_are_computed():
    bake = fp.run_bakeoff(_simulate(noise=0.6), _FAST)
    # with 6 classes → 5 folds, PBO/DSR should be available (not None)
    assert bake.pbo is not None
    assert bake.dsr is not None
    assert 0.0 <= bake.pbo.pbo <= 1.0


# ══════════════════════════════════════════════════════════════════════════════════════
# 4. The leakage contract — by CLASS
# ══════════════════════════════════════════════════════════════════════════════════════


def test_a_future_class_cannot_change_an_earlier_classs_prior():
    """Tamper a LATER class's production; every earlier class's prior must be byte-identical,
    because each class's map is fit ONLY on strictly-prior classes."""
    sim = _simulate(noise=0.6)
    factory = lambda: fp.PartialPoolProjector(prior_scale=2.0)
    base = fp.emit_priors(sim, factory, _FAST)

    tampered = sim.copy()
    late = tampered["arrival_season"].max()
    m = (tampered["arrival_season"] == late) & (tampered["position_group"].isin(_OFFENSE))
    tampered.loc[m, "scrimmage_prod"] = 99999.0
    after = fp.emit_priors(tampered, factory, _FAST)

    early = base[base["arrival_season"] < late].merge(
        after[after["arrival_season"] < late],
        on=["player_id", "arrival_season"], suffixes=("_a", "_b"))
    assert len(early) > 0
    assert np.allclose(early["projected_production_z_a"], early["projected_production_z_b"]), (
        "a future class's production moved an earlier class's prior — the training window leaks")


def test_tampering_a_PRIOR_class_DOES_change_the_later_prior():
    """The complement: the leakage guard must be able to FAIL. Tampering a class the map DOES
    train on must move the downstream prior (so 'no change on future tamper' means something)."""
    sim = _simulate(noise=0.6)
    factory = lambda: fp.PartialPoolProjector(prior_scale=2.0)
    base = fp.emit_priors(sim, factory, _FAST)

    tampered = sim.copy()
    early_season = sorted(sim["arrival_season"].unique())[1]  # a class used to train later classes
    m = (tampered["arrival_season"] == early_season) & (tampered["position_group"] == "QB")
    tampered.loc[m, "scrimmage_prod"] = tampered.loc[m, "scrimmage_prod"] * 0.0 + 1.0
    after = fp.emit_priors(tampered, factory, _FAST)

    latest = sim["arrival_season"].max()
    b = base[(base["arrival_season"] == latest) & (base["position_group"] == "QB")]
    a = after[(after["arrival_season"] == latest) & (after["position_group"] == "QB")]
    merged = b.merge(a, on="player_id", suffixes=("_a", "_b"))
    assert not np.allclose(merged["projected_production_z_a"], merged["projected_production_z_b"]), (
        "tampering a TRAINING class did not move the downstream prior — the leakage guard is blind")


def test_seed_class_is_never_emitted():
    priors = fp.emit_priors(_simulate(), lambda: fp.PartialPoolProjector(2.0), _FAST)
    assert priors["arrival_season"].min() > fp.SEED_ARRIVAL_SEASON
    assert (priors["n_prior_classes"] >= 1).all()


# ══════════════════════════════════════════════════════════════════════════════════════
# 5. Output + team-aggregate contract
# ══════════════════════════════════════════════════════════════════════════════════════


def test_end_to_end_run_grain_and_columns():
    run = fp.run_freshman_projection(_simulate(noise=0.6), _FAST)
    p = run.priors
    assert not p.duplicated(subset=["player_id", "arrival_season"]).any()
    for c in ("sport", "player_id", "arrival_season", "arrival_team", "position_group",
              "projected_production_z", "projected_production_z_sd", "box_production_available",
              "is_true_freshman_prior", "n_prior_classes", "model_version"):
        assert c in p.columns, f"missing prior column {c}"
    assert (p["projected_production_z_sd"] > 0).all()
    assert np.isfinite(p["projected_production_z"]).all()
    # OL/ST recruits are still emitted (rating-only prior), flagged
    assert (~p["box_production_available"]).any()


def test_team_aggregate_is_the_p1_3_join_grain():
    run = fp.run_freshman_projection(_simulate(noise=0.6), _FAST)
    t = run.team_priors
    assert not t.duplicated(subset=["season", "team"]).any()
    for c in ("sport", "season", "team", "team_season_key", "n_incoming_freshmen",
              "freshman_class_projected_production", "freshman_class_avg_projected_production",
              "freshman_class_top_projected_production", "freshman_class_avg_rating",
              "blue_chip_count"):
        assert c in t.columns, f"missing team-aggregate column {c}"
    # the aggregate sums to the per-recruit priors it rolls up
    chk = (run.priors.groupby(["arrival_season", "arrival_team"])["projected_production_z"].sum()
           .reset_index())
    m = t.merge(chk, left_on=["season", "team"], right_on=["arrival_season", "arrival_team"])
    assert np.allclose(m["freshman_class_projected_production"], m["projected_production_z"])


def test_projection_tracks_realized_production_out_of_sample():
    """The behavioural gate: the emitted (strictly-prior-fit) projection must correlate positively
    with realized standardized production on the recruits who actually produced."""
    sim = _simulate(noise=0.4)
    run = fp.run_freshman_projection(sim, _FAST)
    tgt = fp.build_target(sim)[["player_id", "arrival_season", "production_z", "has_target"]]
    merged = run.priors.merge(tgt, on=["player_id", "arrival_season"])
    merged = merged[merged["has_target"]]
    rho = float(np.corrcoef(merged["projected_production_z"], merged["production_z"])[0, 1])
    assert rho > 0.2, f"projection↔realized correlation only {rho:.2f} — no signal recovered"
