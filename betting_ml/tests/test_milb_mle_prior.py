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


def test_iso_pseudocount_is_mle_at_zero_pa_and_shrinks_with_pa():
    assert mp.iso_pseudocount_posterior_mean(0.170, 0.0475, pa=0, obs_iso=0.10) == 0.170
    v = mp.iso_pseudocount_posterior_mean(0.170, 0.0475, pa=50, obs_iso=0.10)
    assert 0.10 < v < 0.170                                   # between prior and obs


def test_iso_pseudocount_does_not_explode_on_tiny_sample_extreme_obs():
    # a rookie with 3 PA and obs_iso=1.5 (a couple extra-base hits) — the case where the Normal-Normal
    # update blew eb_iso past 1.0. The pseudo-count blend (κ_iso ≫ pa) must keep it near the prior.
    v = mp.iso_pseudocount_posterior_mean(0.155, 0.0475, pa=3, obs_iso=1.5)
    assert 0.15 < v < 0.30, f"eb_iso={v} — pseudo-count failed to regularize a tiny-sample extreme obs"
    # the incumbent Normal-Normal genuinely DOES explode here (documents WHY the pseudo-count is needed)
    assert mp.normal_posterior_mean(0.155, 0.0475, pa=3, obs_iso=1.5) > 1.0
    # κ_iso is a sensible equivalent-PA strength (comparable to the K%/BB% pseudo-counts)
    assert 50 < mp.iso_kappa(0.0475) < 250


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


# ══════════════════════════════════════════════════════════════════════════════════════
# E7.5b — the HEAD-TO-HEAD gate (a re-derived prior vs the CURRENTLY-SERVED one)
# ══════════════════════════════════════════════════════════════════════════════════════
#
# These are BEHAVIOURAL guards on the gate itself, not on any particular run's verdict. The gate decides
# whether a new MLE is allowed onto the LIVE run_diff / pre_lineup betting contract, so what has to be
# pinned is that it can actually SAY NO — and that each of its anchors FIRES on the input it exists to
# catch. A gate proven only on a passing case passes on nothing (the NF1.7 (a) lesson).


def _perturb(df, metric, *, better, scale=0.5, seed=11):
    """A challenger frame derived from `df` whose `mle_<metric>` is closer to (better) or further from
    (worse) the realized MLB label. Everything else is byte-identical, so any score difference is
    attributable to the metric's emission alone — a matched foil (NF-D10)."""
    out = df.copy()
    mcol, tcol = f"mle_{metric}", f"mlb_{metric}"
    rng = np.random.default_rng(seed)
    gap = out[tcol] - out[mcol]
    if better:
        out[mcol] = out[mcol] + scale * gap
    else:
        out[mcol] = out[mcol] - scale * gap + rng.normal(0, 0.01, len(out))
    return out


def test_head_to_head_ships_a_genuinely_better_challenger():
    inc = _synth(translate=True)
    ch = _perturb(inc, "k_pct", better=True)
    r = mp.head_to_head_metric(ch, inc, "k_pct")
    assert r.beats_on_nll and r.beats_on_crps
    assert r.fold_win_rate >= mp.H2H_MIN_FOLD_WIN_RATE
    assert r.ships(fdr_survives=True)


def test_head_to_head_refuses_a_worse_challenger():
    """The whole point: an MLE that improved on some OTHER objective must be able to FAIL here."""
    inc = _synth(translate=True)
    ch = _perturb(inc, "k_pct", better=False)
    r = mp.head_to_head_metric(ch, inc, "k_pct")
    assert not r.beats_on_nll
    assert not r.ships(fdr_survives=True)


def test_head_to_head_refuses_a_tie_even_when_bh_passes():
    """A byte-identical challenger is a TIE, not a win — `<` is strict, and a tie must never ship a swap
    on a live betting contract."""
    inc = _synth(translate=True)
    r = mp.head_to_head_metric(inc.copy(), inc, "iso")
    assert not r.beats_on_nll and not r.ships(fdr_survives=True)


def test_bh_fdr_is_binding_not_advisory():
    """Every other condition can hold and the metric still must not ship if BH-FDR rejects it."""
    inc = _synth(translate=True)
    ch = _perturb(inc, "bb_pct", better=True)
    r = mp.head_to_head_metric(ch, inc, "bb_pct")
    assert r.ships(fdr_survives=True)
    assert not r.ships(fdr_survives=False)


def test_scores_are_computed_on_the_matched_intersection_only():
    """A re-fit can ADD players. Scoring each arm on its own rows compares two populations and calls the
    difference a model effect — so the eval set is the intersection, and the drop is REPORTED."""
    inc = _synth(translate=True)
    ch = _perturb(inc, "iso", better=True)
    extra = ch[ch["player_id"] == "5"].copy()
    extra["player_id"] = "brand_new_prospect"
    ch = pd.concat([ch, extra], ignore_index=True)
    r = mp.head_to_head_metric(ch, inc, "iso")
    base = mp.head_to_head_metric(_perturb(inc, "iso", better=True), inc, "iso")
    assert r.n_challenger_only == 1 and r.n_incumbent_only == 0
    assert r.n_scored == base.n_scored          # the extra player did NOT enter the eval set
    assert any("intersection" in n for n in r.notes)


def test_permutation_degenerate_loses_and_the_anchor_fires_when_there_is_no_content():
    """The permutation preserves the marginal EXACTLY and destroys only the per-player pairing, so it is
    the statement 'is there per-player content here at all'. It must lose when there IS content — and the
    anchor must FIRE (block the ship) when the challenger is pure noise, or it is a decorative check."""
    inc = _synth(translate=True)
    r = mp.head_to_head_metric(_perturb(inc, "k_pct", better=True), inc, "k_pct")
    assert r.permuted.nll > r.challenger.nll and r.degenerates_lose

    noise = inc.copy()
    rng = np.random.default_rng(4)
    noise["mle_k_pct"] = rng.permutation(noise["mle_k_pct"].to_numpy())
    rn = mp.head_to_head_metric(noise, inc, "k_pct")
    assert not rn.degenerates_lose or not rn.ships(fdr_survives=True)


def test_oracle_floor_is_per_form_and_holds_for_both_arms():
    """NF-D16 (g‴): each arm is floored by the peeking version of ITS OWN form. A shared ceiling would
    veto a legitimately-better arm as a false metric inversion. Neither arm may beat its own oracle."""
    inc = _synth(translate=True)
    for better in (True, False):
        r = mp.head_to_head_metric(_perturb(inc, "iso", better=better), inc, "iso")
        assert r.challenger.nll >= r.oracle_challenger.nll - 1e-9
        assert r.incumbent.nll >= r.oracle_incumbent.nll - 1e-9
        assert r.oracle_floor_holds


def test_coverage_is_a_floor_not_a_target():
    """E2.1-r / NF1.8: the guard must reject an UNDER-covering challenger and stay silent on an
    OVER-covering one. A two-sided band here would make coverage a target — the inversion this repo has
    already paid for twice."""
    base = mp.head_to_head_metric(_synth(translate=True), _synth(translate=True), "k_pct")
    under = replace_cov(base, 0.40, 0.60)
    over = replace_cov(base, 0.95, 0.99)
    assert not under.coverage_floor_holds
    assert over.coverage_floor_holds


def replace_cov(r, cov68, cov90):
    import copy
    out = copy.deepcopy(r)
    out.challenger = mp.ArmScores(out.challenger.name, out.challenger.nll, out.challenger.crps,
                                  out.challenger.mae, cov68, cov90)
    return out


def test_head_to_head_is_purged_by_cohort_and_self_calibrates_each_arm():
    inc = _synth(cohorts=(2016, 2017, 2018), per=30, translate=True)
    ch = _perturb(inc, "k_pct", better=True)
    r = mp.head_to_head_metric(ch, inc, "k_pct")
    assert r.n_cohorts == 2                      # 2016 is the seed — never scored
    assert len(r.cohort_nll_delta) == 2
    # each arm carries its OWN self-calibrated sd (the challenger is sharper, so its σ is smaller)
    assert r.challenger_sigma < r.incumbent_sigma


def test_bh_fdr_never_passes_an_unevaluable_test():
    survive = mp.bh_fdr({"a": 0.001, "b": None, "c": float("nan")})
    assert survive["a"] and not survive["b"] and not survive["c"]


# ══════════════════════════════════════════════════════════════════════════════════════
# E7.5b — the per-metric HOLD-BACK merge (what lands on the serving key)
# ══════════════════════════════════════════════════════════════════════════════════════
#
# "A metric that does not clear keeps the served incumbent VERBATIM" is the entire safety argument for
# shipping SOME metrics off a new MLE while withholding others. Verbatim is therefore asserted here, not
# trusted to a join.

from pathlib import Path  # noqa: E402

from betting_ml.scripts.milb_mle import run_mle_prior_recalibration as runner  # noqa: E402


def _prior_table(ids, *, k=0.22, bb=0.08, iso=0.15, kappa=100.0, sd=0.047, level="Triple-A"):
    return pd.DataFrame({
        "batter_id": [str(i) for i in ids], "mle_level": level, "is_prospect": False,
        "mle_k_pct": k, "k_pct_prior_kappa": kappa,
        "mle_bb_pct": bb, "bb_pct_prior_kappa": kappa,
        "mle_iso": iso, "iso_prior_sd": sd,
    })


def test_holdback_keeps_the_served_columns_byte_identical():
    served = _prior_table(range(5), k=0.20, bb=0.07, iso=0.14, kappa=80.0, sd=0.049)
    challenger = _prior_table(range(6), k=0.30, bb=0.09, iso=0.19, kappa=150.0, sd=0.041)
    for m in ("k_pct", "bb_pct", "iso"):
        challenger[f"{m}_source"] = "milb_mle_v2"

    out, stats = runner.apply_holdbacks(challenger, served, holdback=["k_pct"])
    j = served.merge(out, on="batter_id", suffixes=("_srv", "_new"))
    # held back → byte-identical to what is serving
    assert (j["mle_k_pct_srv"] == j["mle_k_pct_new"]).all()
    assert (j["k_pct_prior_kappa_srv"] == j["k_pct_prior_kappa_new"]).all()
    # shipped → the challenger's values, unchanged by the merge
    assert (j["mle_iso_new"] == 0.19).all() and (j["mle_bb_pct_new"] == 0.09).all()
    # provenance says which arm each metric came from
    assert set(out["k_pct_source"]) == {"milb_mle_v1_served"}
    assert set(out["iso_source"]) == {"milb_mle_v2"}
    assert stats["holdback_verbatim_verified"] is True
    # the new batter has no served k_pct → NULL → the served build falls back to the generic prior for
    # that metric only (he has no prior at all today, so this can only add coverage)
    assert out.loc[out.batter_id == "5", "mle_k_pct"].isna().all()
    assert out.loc[out.batter_id == "5", "mle_iso"].notna().all()


def test_holdback_refuses_when_a_served_batter_would_lose_his_prior():
    """A re-fit that DROPS a player would silently delete his served rookie prior. Refuse, don't absorb."""
    served = _prior_table(range(5))
    challenger = _prior_table(range(4))
    for m in ("k_pct", "bb_pct", "iso"):
        challenger[f"{m}_source"] = "milb_mle_v2"
    with pytest.raises(ValueError, match="absent from the re-derived table"):
        runner.apply_holdbacks(challenger, served, holdback=["k_pct"])


def test_holdback_verbatim_assertion_fires_on_a_corrupted_merge():
    """The verbatim check must be able to FAIL, or it is decorative (NF1.7 (a)). A NON-UNIQUE served key
    is the realistic defect: the merge fans out and a batter ends up carrying two different priors."""
    served = pd.concat([_prior_table(range(5), k=0.20),
                        _prior_table(["3"], k=0.31)], ignore_index=True)   # batter 3 twice, disagreeing
    challenger = _prior_table(range(5), k=0.30)
    for m in ("k_pct", "bb_pct", "iso"):
        challenger[f"{m}_source"] = "milb_mle_v2"
    with pytest.raises(ValueError, match="NOT byte-identical"):
        runner.apply_holdbacks(challenger, served, holdback=["k_pct"])


def test_metric_column_map_matches_what_the_dbt_consumer_reads():
    """`eb_batter_posteriors_raw` selects these six columns by name off the served parquet. A metric
    whose columns drift out of `_METRIC_COLS` would be silently un-holdbackable."""
    sql = (Path(__file__).resolve().parents[2]
           / "dbt/models/eb_posteriors/eb_batter_posteriors_raw.sql").read_text()
    cte = sql.split("mle_prior as (", 1)[1].split("from milb_mle_prior", 1)[0]
    for m, cols in runner._METRIC_COLS.items():
        for c in cols:
            assert c in cte, f"{m}: served column {c} is not read by the eb_batter_posteriors_raw CTE"


# ══════════════════════════════════════════════════════════════════════════════════════
# E7.5b — the post-land SERVING verifier's state classifier
# ══════════════════════════════════════════════════════════════════════════════════════
#
# The verifier is IO-bound (DuckDB over S3), so what CI can pin is its DECISION LOGIC. It must name the
# right CAUSE, not just fail: right after --s3 lands a new prior the downstream table is legitimately
# stale, and calling that "the join is dead" sends an operator hunting a bug that isn't there.

from betting_ml.scripts.milb_mle import verify_mle_prior_serving as verify  # noqa: E402


def test_reach_verified_when_every_metric_serves_the_mle_value():
    state, msgs = verify.classify_reach({"eb_k_pct": 434, "eb_bb_pct": 434, "eb_iso": 434}, 434)
    assert state == "VERIFIED" and msgs == []


def test_reach_calls_a_partial_miss_a_STALE_REBUILD_not_a_dead_join():
    """All six prior columns arrive through ONE left join, so it cannot match for one metric and miss
    for another — a metric hitting proves the join is alive. This is the real post-land state."""
    state, msgs = verify.classify_reach({"eb_k_pct": 434, "eb_bb_pct": 1, "eb_iso": 2}, 434)
    assert state == "PENDING_REBUILD"
    assert len(msgs) == 2
    assert all("join is ALIVE" in m and "STALE" in m for m in msgs)
    assert not any("dead" in m for m in msgs)


def test_reach_calls_a_total_miss_a_DEAD_JOIN():
    state, msgs = verify.classify_reach({"eb_k_pct": 0, "eb_bb_pct": 0, "eb_iso": 3}, 434)
    assert state == "DEGRADED"
    assert len(msgs) == 3 and all("join is dead" in m for m in msgs)


def test_reach_never_scores_an_unevaluable_check_as_a_pass():
    """NF1.7 (a): no cold-start rows means the identity could not be tested — that is not a pass."""
    state, msgs = verify.classify_reach({"eb_k_pct": 0, "eb_bb_pct": 0, "eb_iso": 0}, 0)
    assert state == "UNEVALUABLE" and msgs == []


def test_reach_states_are_all_actionable_failures_except_verified():
    """PENDING_REBUILD and DEGRADED both carry messages, so both exit non-zero — they differ in the
    ACTION they name, never in whether they are silent."""
    for hits in ({"a": 10, "b": 0}, {"a": 0, "b": 0}):
        state, msgs = verify.classify_reach(hits, 10)
        assert state != "VERIFIED" and msgs
