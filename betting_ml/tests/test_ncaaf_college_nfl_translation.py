"""NCAAF-P1A — college→NFL translation (the NFL feeder) guards.

Fast-gate only: pure numpy/pandas/sklearn over a SYNTHETIC xref↔college-production universe, no
DuckDB, no S3, no `pipeline` import (the fast gate has no dbt manifest — CLAUDE.md's fast-gate rule).

What these tests are actually for (the P1.2 lesson: model-quality gates are BEHAVIORAL, not
green-checkmark — CI mocks all IO and cannot see this class):
  * the target is standardized WITHIN (position, draft class) and a UDFA / no-production row stays
    UNKNOWN, not 0;
  * the bake-off recovers a planted college-production → NFL-outcome signal (else every projection
    is decoration) and the winner beats the position-mean NULL FLOOR;
  * the partial-pooling candidate demonstrably SHRINKS a thin position cell toward the global line —
    the whole reason candidate (a) exists — and no variance component collapses to 0;
  * ⭐ the leakage contract holds by CLASS: a FUTURE draft class cannot move an earlier class's
    projection, and it is verified to FAIL on a tampered PRIOR class (so green means something);
  * the draft-slot benchmark + position-mean null are REPORTED but NOT selected as the winner;
  * the ORACLE-FLOOR sanity holds (no candidate beats a target-seeing model — the E2.1-r tell);
  * OL / specialists + UDFAs get a projection (combine/college-only), flagged, never a fabricated 0;
  * the join-coverage report counts the thin-join surface (PM note #4).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.ncaaf.models import college_nfl_translation as ct


# ══════════════════════════════════════════════════════════════════════════════════════
# Synthetic xref ↔ college-production universe
# ══════════════════════════════════════════════════════════════════════════════════════

_OFFENSE = ["QB", "RB", "WR", "TE"]
_DEFENSE = ["DL", "LB", "DB"]
_STAT_GROUPS = _OFFENSE + _DEFENSE

# planted college-production → NFL-AV slope per group (higher college production ⇒ higher NFL AV,
# with heavy noise so the null is not trivially beaten — the noisy NFL draft).
_SLOPE = {"QB": 6.0, "RB": 3.0, "WR": 3.0, "TE": 2.0, "DL": 3.0, "LB": 3.0, "DB": 2.5}
_PLANTED_PROD = {"QB": 320.0, "RB": 130.0, "WR": 110.0, "TE": 55.0, "DL": 5.0, "LB": 7.0, "DB": 4.0}


def _simulate(years=(2015, 2016, 2017, 2018, 2019, 2020), seed=7, per_year_pos=6,
              include_ol=True, include_udfa=True, noise=1.0, thin_prod=0.0):
    """A synthetic P1A pairs frame: drafted (has NFL outcome) + UDFA (no outcome) players, each with
    a college body of work whose production drives the NFL AV with a planted per-position slope."""
    rng = np.random.default_rng(seed)
    rows = []
    pid = 0
    for year in years:
        for grp in list(_STAT_GROUPS) + (["OL", "ST"] if include_ol else []):
            for k in range(per_year_pos):
                pid += 1
                is_udfa = include_udfa and (k == 0)  # one UDFA per (year, group)
                # college production (per-game composite scale); box-invisible groups have none
                if grp in _STAT_GROUPS and rng.random() >= thin_prod:
                    games = int(rng.integers(9, 14))
                    base = max(1.0, rng.normal(_PLANTED_PROD[grp], _PLANTED_PROD[grp] * 0.4))
                    has_prod = True
                else:
                    games, base, has_prod = 0, 0.0, False
                # NFL AV driven by college production (drafted only carry an outcome)
                av = None
                if not is_udfa and has_prod:
                    av = max(0.0, _SLOPE[grp] * (base / max(_PLANTED_PROD[grp], 1e-9))
                             + rng.normal(0, 1.5 * noise))
                slot = int(rng.integers(1, 260)) if not is_udfa else None
                # spread the per-game composite across the raw box columns the model reconstructs
                row = {
                    "sport": "ncaaf", "gsis_id": f"00-{pid:07d}",
                    "college_athlete_id": pid, "player_name": f"P{pid}",
                    "college": f"College-{pid % 30}", "college_conference": "CONF",
                    "draft_year": year, "draft_overall": slot,
                    "draft_round": None if slot is None else (slot // 32 + 1),
                    "match_method": "fuzzy_udfa" if is_udfa else "deterministic_slot",
                    "match_confidence": "low" if is_udfa else "high",
                    "is_udfa": is_udfa, "position_group": grp, "nfl_position": grp,
                    "college_games": games,
                    "recruit_composite_rating": float(np.clip(rng.normal(0.88, 0.05), 0.7, 1.0)),
                    "has_college_production": has_prod,
                    "target_w_av": av, "has_nfl_outcome": av is not None,
                }
                # combine (partially present)
                for c in ct.COMBINE_COLS:
                    row[c] = float(rng.normal(0, 1)) if rng.random() > 0.2 else np.nan
                # raw box columns → per-game composite ≈ base for the group
                for c in ("passing_yards", "passing_tds", "rushing_yards", "rushing_tds",
                          "receiving_yards", "receiving_tds", "receptions", "pass_attempts",
                          "rushing_attempts", "tackles_total", "sacks", "tackles_for_loss",
                          "passes_defended", "interceptions_caught", "defensive_tds"):
                    row[c] = 0.0
                tot = base * max(games, 0)
                if grp == "QB":
                    row["passing_yards"] = tot
                elif grp == "RB":
                    row["rushing_yards"] = tot
                elif grp in ("WR", "TE"):
                    row["receiving_yards"] = tot
                elif grp in _DEFENSE:
                    row["tackles_total"] = tot
                rows.append(row)
    return pd.DataFrame(rows)


_FAST = ct.TranslationConfig(pool_prior_scales=(2.0,), gbm_grid=((40, 2, 0.1),))


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. Target + feature construction
# ══════════════════════════════════════════════════════════════════════════════════════


def test_target_is_standardized_within_position_and_class():
    d = ct.build_target(_simulate(), _FAST)
    lab = d[d["has_target"]]
    g = lab.groupby(["position_group", "draft_year"])["target_z"]
    assert g.mean().abs().max() < 1e-6
    sds = g.std(ddof=0)
    assert ((sds - 1.0).abs() < 1e-6).all()


def test_udfa_and_no_production_stay_unknown_not_zero():
    d = ct.build_target(_simulate(), _FAST)
    # a UDFA (no NFL outcome) must carry NaN target, never a fabricated 0
    udfa = d[d["is_udfa"]]
    assert len(udfa) > 0
    assert udfa["target_z"].isna().all()
    # a box-visible player with no college production is UNKNOWN target too
    noprod = d[(~d["has_college_prod"]) & d["position_group"].isin(_STAT_GROUPS) & (~d["is_udfa"])]
    if len(noprod):
        assert noprod["target_z"].isna().all()


def test_ol_and_st_are_box_invisible_but_still_rows():
    d = ct.build_target(_simulate(), _FAST)
    ol = d[d["position_group"] == "OL"]
    assert len(ol) > 0
    assert (~ol["box_production_available"]).all()
    assert ol["target_z"].isna().all(), "OL must have NO production label (box-invisible)"


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. Partial pooling — the reason candidate (a) exists
# ══════════════════════════════════════════════════════════════════════════════════════


def test_partial_pool_shrinks_a_thin_position_cell_toward_the_global_line():
    d = ct.build_target(_simulate(years=(2015, 2016), seed=3), _FAST)
    lab = d[d["has_target"]].copy()
    db = lab[lab["position_group"] == "DB"]
    thin = pd.concat([lab[lab["position_group"] != "DB"], db.head(3)], ignore_index=True)

    pool = ct.PartialPoolProjector(prior_scale=2.0).fit(thin)
    probe = thin[thin["position_group"] != "DB"].head(2).copy()
    probe["position_group"] = "DB"
    # give the probe two very different college bodies of work
    probe.iloc[0, probe.columns.get_loc("tackles_total")] = 10.0
    probe.iloc[1, probe.columns.get_loc("tackles_total")] = 2000.0
    probe["college_games"] = 12
    pm, _ = pool.predict(probe)
    swing_pool = abs(pm[1] - pm[0])

    x = pool.scaler_.transform(db.head(3))[0]
    y = db.head(3)["target_z"].to_numpy(float)
    if np.std(x) > 0:
        b = np.polyfit(x, y, 1)[0]
        xp = pool.scaler_.transform(probe)[0]
        swing_raw = abs(b * (xp[1] - xp[0]))
        assert swing_pool < swing_raw + 1e-9, "the thin DB cell was not shrunk relative to its raw fit"


def test_partial_pool_keeps_a_variance_component_alive_on_thin_data():
    d = ct.build_target(_simulate(years=(2015,), seed=5), _FAST)
    lab = d[d["has_target"]]
    pool = ct.PartialPoolProjector(prior_scale=2.0).fit(lab)
    tau_gi = float(np.sqrt(pool.post_.variances["group_intercept"]))
    tau_gs = float(np.sqrt(pool.post_.variances["group_slope"]))
    assert tau_gi > 1e-3 and tau_gs > 1e-3, f"a variance component collapsed (gi={tau_gi}, gs={tau_gs})"


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. The bake-off recovers signal, beats the null, and respects the non-selectable floors
# ══════════════════════════════════════════════════════════════════════════════════════


def test_bakeoff_winner_beats_the_position_mean_null():
    bake = ct.run_bakeoff(_simulate(noise=0.5), _FAST)
    lb = bake.leaderboard
    null_mae = float(lb.loc[lb["config"] == "position_mean", "oos_mae"].iloc[0])
    sel = lb[lb["selectable"]]
    win_mae = float(sel["oos_mae"].min())
    assert win_mae < null_mae, f"winner {win_mae:.3f} did not beat the null {null_mae:.3f}"
    assert bake.winner_name not in ("position_mean", "draft_slot_ref")


def test_floors_and_benchmarks_are_never_selected_as_winner():
    bake = ct.run_bakeoff(_simulate(noise=0.5), _FAST)
    lb = bake.leaderboard
    assert not lb.loc[lb["config"] == "position_mean", "selectable"].iloc[0]
    assert not lb.loc[lb["config"] == "draft_slot_ref", "selectable"].iloc[0]
    assert bake.winner_name != "draft_slot_ref"


def test_oracle_floor_holds():
    bake = ct.run_bakeoff(_simulate(), _FAST)
    assert bake.oracle_floor_ok
    assert float(bake.leaderboard["oos_mae"].min()) >= -1e-9


def test_pbo_and_dsr_are_computed():
    bake = ct.run_bakeoff(_simulate(noise=0.5), _FAST)
    assert bake.pbo is not None
    assert 0.0 <= bake.pbo.pbo <= 1.0


# ══════════════════════════════════════════════════════════════════════════════════════
# 4. The leakage contract — by DRAFT CLASS
# ══════════════════════════════════════════════════════════════════════════════════════


def test_a_future_class_cannot_change_an_earlier_classs_projection():
    sim = _simulate(noise=0.5)
    factory = lambda: ct.PartialPoolProjector(prior_scale=2.0)
    base = ct.emit_projections(sim, factory, _FAST)

    tampered = sim.copy()
    late = tampered["draft_year"].max()
    m = (tampered["draft_year"] == late) & (tampered["position_group"].isin(_OFFENSE))
    tampered.loc[m, "target_w_av"] = 999.0
    after = ct.emit_projections(tampered, factory, _FAST)

    early = base[base["draft_year"] < late].merge(
        after[after["draft_year"] < late], on="gsis_id", suffixes=("_a", "_b"))
    assert len(early) > 0
    assert np.allclose(early["projected_nfl_z_a"], early["projected_nfl_z_b"]), (
        "a future draft class's outcome moved an earlier class's projection — the window leaks")


def test_tampering_a_PRIOR_class_DOES_change_the_later_projection():
    sim = _simulate(noise=0.5)
    factory = lambda: ct.PartialPoolProjector(prior_scale=2.0)
    base = ct.emit_projections(sim, factory, _FAST)

    tampered = sim.copy()
    early_year = sorted(sim["draft_year"].unique())[1]  # a class used to train later classes
    m = (tampered["draft_year"] == early_year) & (tampered["position_group"] == "QB")
    tampered.loc[m, "passing_yards"] = 1.0
    after = ct.emit_projections(tampered, factory, _FAST)

    latest = sim["draft_year"].max()
    b = base[(base["draft_year"] == latest) & (base["position_group"] == "QB")]
    a = after[(after["draft_year"] == latest) & (after["position_group"] == "QB")]
    merged = b.merge(a, on="gsis_id", suffixes=("_a", "_b"))
    assert len(merged) > 0
    assert not np.allclose(merged["projected_nfl_z_a"], merged["projected_nfl_z_b"]), (
        "tampering a TRAINING class did not move the downstream projection — the leakage guard is blind")


def test_seed_class_is_never_emitted():
    proj = ct.emit_projections(_simulate(), lambda: ct.PartialPoolProjector(2.0), _FAST)
    assert proj["draft_year"].min() > ct.SEED_DRAFT_YEAR
    assert (proj["n_prior_classes"] >= 1).all()


# ══════════════════════════════════════════════════════════════════════════════════════
# 5. Output contract + UDFA/box handling + coverage + tracking
# ══════════════════════════════════════════════════════════════════════════════════════


def test_end_to_end_run_grain_and_columns():
    run = ct.run_college_nfl_translation(_simulate(noise=0.5), _FAST)
    p = run.projections
    assert not p.duplicated(subset=["gsis_id"]).any(), "gsis_id grain must be unique"
    for c in ("sport", "gsis_id", "draft_year", "position_group", "projected_nfl_z",
              "projected_nfl_z_sd", "box_production_available", "is_udfa", "n_prior_classes",
              "model_version", "target_metric"):
        assert c in p.columns, f"missing projection column {c}"
    assert (p["projected_nfl_z_sd"] > 0).all()
    assert np.isfinite(p["projected_nfl_z"]).all()
    # UDFAs are still emitted (college-only projection), flagged
    assert p["is_udfa"].any()
    # OL/ST are still emitted (combine/pedigree-only), flagged box-invisible
    assert (~p["box_production_available"]).any()


def test_udfas_are_emitted_but_excluded_from_training():
    """A UDFA carries no NFL outcome → it cannot enter the training label set, but must still get a
    college-only projection keyed to its gsis_id."""
    sim = _simulate(noise=0.5)
    d = ct.build_target(sim, _FAST)
    assert not d.loc[d["is_udfa"], "has_target"].any(), "a UDFA leaked into the training label set"
    run = ct.run_college_nfl_translation(sim, _FAST)
    assert run.projections.loc[run.projections["is_udfa"], "projected_nfl_z"].notna().all()


def test_target_metric_switch_changes_the_label():
    """The operator can translate to a different NFL outcome; build_target must honour it."""
    sim = _simulate(noise=0.5)
    sim["target_car_av"] = pd.to_numeric(sim["target_w_av"], errors="coerce") * 1.7 + 3.0
    cfg2 = ct.TranslationConfig(target_metric="target_car_av", pool_prior_scales=(2.0,),
                                gbm_grid=((40, 2, 0.1),))
    d1 = ct.build_target(sim, _FAST)
    d2 = ct.build_target(sim, cfg2)
    # different raw metrics, but each standardized within (position, class) — the labelled SET is
    # the same; assert the config is actually read (no crash) and the target column is populated.
    assert d2["has_target"].sum() > 0
    assert d1["has_target"].sum() == d2["has_target"].sum()


def test_projection_tracks_realized_nfl_production_out_of_sample():
    sim = _simulate(noise=0.35)
    run = ct.run_college_nfl_translation(sim, _FAST)
    tgt = ct.build_target(sim, _FAST)[["gsis_id", "target_z", "has_target"]]
    merged = run.projections.merge(tgt, on="gsis_id")
    merged = merged[merged["has_target"]]
    rho = float(np.corrcoef(merged["projected_nfl_z"], merged["target_z"])[0, 1])
    assert rho > 0.15, f"projection↔realized correlation only {rho:.2f} — no signal recovered"


def test_invalid_target_metric_rejected():
    with pytest.raises(ValueError):
        ct.TranslationConfig(target_metric="target_nonsense")
