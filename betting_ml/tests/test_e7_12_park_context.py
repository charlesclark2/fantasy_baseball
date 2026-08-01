"""E7.12 SLICE 1 — the minor-league park / level-run-environment / small-sample hardening of the
MiLB→MLB MLE.

These tests exist because the slice's whole failure mode is that it can **look** like it worked. Dividing
a rate by a dispersed number and shrinking it toward a mean both lower MAE against a regressed target on
their own, so every test below is aimed at one of three questions:

  1. is the arithmetic RIGHT (LOO subtraction exact, the SQL and the pandas rate formulas identical,
     the shrink reciprocal-preserving)?
  2. is the incumbent PRESERVED (`ContextSpec()` byte-exact, `weight_col=None` byte-exact)?
  3. do the ANCHORS actually FIRE (a planted park effect is recovered; a placebo win BLOCKS the ship;
     a dead join BLOCKS the ship) — because an anchor that cannot fail is an anchor that passes on
     nothing (the NF1.7 lesson).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle.milb_mle import (
    MleConfig,
    PartialPoolProjector,
    build_target,
    compute_rate_metrics_from_counts,
    compute_woba_from_counts,
    emit_projections,
)
from betting_ml.scripts.milb_mle.park_context import (
    PF_CLAMP,
    PF_METRICS,
    STABILIZATION_PA,
    ContextSpec,
    apply_context,
    context_coverage,
    exposure_weighted_pf,
    park_factors_from_buckets,
    rates_from_reduced,
    reduced_aggregate_sql,
    reduced_from_counts,
    reliability_weight,
    shrink_log_pf,
    woba_numerator_sql,
)
from betting_ml.scripts.milb_mle.run_e7_12_slice1 import (
    LADDER,
    bh_fdr,
    deflation_report,
    directional_read,
    run_ladder,
)

_BAT_COLS = [
    "bat_plate_appearances", "bat_at_bats", "bat_hits", "bat_doubles", "bat_triples",
    "bat_home_runs", "bat_walks", "bat_intentional_walks", "bat_hit_by_pitch", "bat_sac_flies",
    "bat_strike_outs", "bat_total_bases",
]


def _random_counts(n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    pa = rng.integers(80, 900, n)
    bb = rng.binomial(pa, 0.09)
    so = rng.binomial(pa, 0.22)
    hbp = rng.binomial(pa, 0.01)
    sf = rng.binomial(pa, 0.008)
    ab = pa - bb - hbp - sf
    h = rng.binomial(np.maximum(ab, 1), 0.26)
    dbl = rng.binomial(h, 0.20)
    tpl = rng.binomial(np.maximum(h - dbl, 0), 0.03)
    hr = rng.binomial(np.maximum(h - dbl - tpl, 0), 0.12)
    return pd.DataFrame({
        "bat_plate_appearances": pa, "bat_at_bats": ab, "bat_hits": h, "bat_doubles": dbl,
        "bat_triples": tpl, "bat_home_runs": hr, "bat_walks": bb,
        "bat_intentional_walks": rng.binomial(bb, 0.05), "bat_hit_by_pitch": hbp,
        "bat_sac_flies": sf, "bat_strike_outs": so,
        "bat_total_bases": h + dbl + 2 * tpl + 3 * hr,
    })


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The arithmetic — one formula home, three consumers
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_reduced_bucket_reproduces_the_e7_3_rate_formulas_exactly():
    """⭐ The park bucket carries 8 numbers per side instead of 24 so the leave-one-player-out table
    stays a tractable frame. That compression is only safe if a rate over the reduced form is IDENTICAL
    to a rate over the full box line — otherwise the park factor and the player's own rate would be
    computed by two subtly different formulas and the adjustment would be measuring the difference."""
    df = _random_counts(400, seed=7)
    full = compute_rate_metrics_from_counts(df)
    red = reduced_from_counts(df, "h")
    got = rates_from_reduced(red, "h")
    for m in PF_METRICS:
        np.testing.assert_allclose(got[m], full[f"minor_{m}"].to_numpy(float), rtol=0, atol=1e-12)


def test_the_generated_sql_wOBA_numerator_matches_the_python_constant():
    """The wOBA weights necessarily appear in SQL (the buckets are summed in DuckDB over 4.6M rows).
    They are EMITTED from `milb_mle._WOBA_W` rather than retyped — this proves the emitter and the
    Python formula agree on real numbers, so the two can never drift."""
    duckdb = pytest.importorskip("duckdb")
    df = _random_counts(200, seed=11)
    con = duckdb.connect()
    con.register("t", df)
    sql_num = con.execute(f"select {woba_numerator_sql()} as n from t").df()["n"].to_numpy(float)
    red = reduced_from_counts(df, "x")
    np.testing.assert_allclose(sql_num, red["x_woba_num"].to_numpy(float), rtol=0, atol=1e-9)
    # and the reduced num/den really is wOBA
    woba = np.divide(red["x_woba_num"].to_numpy(float), red["x_woba_den"].to_numpy(float))
    np.testing.assert_allclose(woba, compute_woba_from_counts(df).to_numpy(float), atol=1e-12)


def test_the_full_reduced_aggregate_sql_round_trips_through_duckdb():
    """`reduced_aggregate_sql` is the SUM side of the same contract — a typo in one field name would
    produce a bucket missing a column and a park factor silently computed on zeros."""
    duckdb = pytest.importorskip("duckdb")
    df = _random_counts(150, seed=13)
    con = duckdb.connect()
    con.register("t", df)
    got = con.execute(f"select {reduced_aggregate_sql('h')} from t").df()
    want = reduced_from_counts(df, "h").sum()
    for f in ("pa", "ab", "so", "bb", "h", "tb", "woba_num", "woba_den"):
        assert f"h_{f}" in got.columns
        assert got[f"h_{f}"].iloc[0] == pytest.approx(float(want[f"h_{f}"]), rel=1e-9)


def test_leave_one_player_out_subtraction_is_exact():
    """LOO is `rate(bucket − player)`, and in the reduced representation that is exact subtraction of
    numerators and denominators. Prove it against the brute-force answer (rebuild the bucket from the
    other players' rows) — if this drifted, the headline arm would be silently non-LOO, which is the
    exact confound the slice exists to avoid."""
    df = _random_counts(30, seed=17)
    red = reduced_from_counts(df, "h")
    bucket = red.sum()
    for i in (0, 5, 29):
        loo = bucket - red.iloc[i]
        brute = reduced_from_counts(df.drop(index=df.index[i]), "h").sum()
        for f in ("pa", "ab", "so", "bb", "h", "tb", "woba_num", "woba_den"):
            assert loo[f"h_{f}"] == pytest.approx(float(brute[f"h_{f}"]), rel=1e-9)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The park factor: shrink, clamp, exposure
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_shrink_is_reciprocal_preserving_and_pulls_a_thin_park_to_neutral():
    """Log-space shrinkage is not decoration. A 1.30 park and a 0.769 park are the same park effect
    facing opposite directions; shrinking them in LINEAR space would break that symmetry and quietly
    bias every adjusted rate in one direction."""
    hi = shrink_log_pf([1.30], [1e9])[0]
    lo = shrink_log_pf([1.0 / 1.30], [1e9])[0]
    assert hi * lo == pytest.approx(1.0, rel=1e-9)
    half_hi = shrink_log_pf([1.30], [2000.0], pseudo_pa=2000.0)[0]
    half_lo = shrink_log_pf([1.0 / 1.30], [2000.0], pseudo_pa=2000.0)[0]
    assert half_hi * half_lo == pytest.approx(1.0, rel=1e-9)
    # a park with almost no sample is neutral, not a confident extreme
    assert shrink_log_pf([1.60], [10.0])[0] == pytest.approx(1.0, abs=0.01)
    # and a broken bucket is clamped, not shipped
    assert shrink_log_pf([9.0], [1e9])[0] == pytest.approx(PF_CLAMP[1])
    assert shrink_log_pf([0.01], [1e9])[0] == pytest.approx(PF_CLAMP[0])


def test_a_park_factor_uses_the_BINDING_side_of_the_ratio_as_its_sample():
    """8,000 home PA against 40 road PA is a 40-PA estimate. Taking the home count as `n_eff` would let
    a wild ratio off a handful of road games ship at nearly full weight."""
    buckets = pd.DataFrame([{
        "h_pa": 8000.0, "h_ab": 7200.0, "h_so": 1600.0, "h_bb": 700.0, "h_h": 1900.0,
        "h_tb": 3000.0, "h_woba_num": 2400.0, "h_woba_den": 7900.0,
        "r_pa": 40.0, "r_ab": 36.0, "r_so": 4.0, "r_bb": 4.0, "r_h": 14.0,
        "r_tb": 30.0, "r_woba_num": 18.0, "r_woba_den": 40.0,
    }])
    got = park_factors_from_buckets(buckets)
    assert got["pf_n_eff_pa"].iloc[0] == 40.0
    for m in PF_METRICS:
        raw, shrunk = got[f"pf_{m}_raw"].iloc[0], got[f"pf_{m}"].iloc[0]
        # the BINDING side (40 PA) buys ~2% of the raw signal; the home side (8,000 PA) would buy 80%
        binding = shrink_log_pf([raw], [40.0])[0]
        wrong = shrink_log_pf([raw], [8000.0])[0]
        assert shrunk == pytest.approx(binding), m
        assert abs(shrunk - 1.0) < 0.03, (m, shrunk)
        if abs(raw - 1.0) > 0.2:      # only meaningful where the raw ratio is actually extreme
            assert abs(wrong - 1.0) > 5 * abs(shrunk - 1.0), (
                m, "using the home count as n_eff would ship a 40-PA ratio at near-full weight")


def test_exposure_weighting_is_a_geometric_mean_and_reports_uncovered_PA():
    """A multiplicative factor's correct centre is the geometric mean; and a player whose parks are half
    un-factored must SHOW that (a 0.5 coverage share), not silently read as 'played in neutral parks'."""
    exp = pd.DataFrame({
        "player_id": ["a", "a", "b", "b"],
        "level": ["Triple-A"] * 4,
        "pa_exposure": [300.0, 300.0, 100.0, 100.0],
        "pf_iso": [1.20, 1.0 / 1.20, 1.10, np.nan],
        "pf_woba": [1.0, 1.0, 1.0, 1.0],
        "pf_k_pct": [1.0, 1.0, 1.0, 1.0],
        "pf_bb_pct": [1.0, 1.0, 1.0, 1.0],
    })
    got = exposure_weighted_pf(exp, PF_METRICS, "pf_", "pa_exposure", ("player_id", "level"))
    a = got[got["player_id"] == "a"].iloc[0]
    b = got[got["player_id"] == "b"].iloc[0]
    assert a["pf_iso_exposure"] == pytest.approx(1.0, abs=1e-9)   # 1.2 and 1/1.2 cancel geometrically
    assert a["pf_iso_covered_pa_share"] == pytest.approx(1.0)
    assert b["pf_iso_exposure"] == pytest.approx(1.10, abs=1e-9)  # the NaN park contributes nothing
    assert b["pf_iso_covered_pa_share"] == pytest.approx(0.5)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The incumbent must be preserved byte-exactly
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _toy_pairs(n: int = 240, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    lvl = rng.choice(["Triple-A", "Double-A"], n)
    minor_k = np.clip(rng.normal(0.22, 0.05, n), 0.05, 0.45)
    return pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)],
        "level": lvl,
        "league": rng.choice(["IL", "PCL", "EL"], n),
        "age": rng.normal(23.5, 1.6, n),
        "minor_pa": rng.integers(160, 900, n).astype(float),
        "minor_k_pct": minor_k,
        "minor_iso": np.clip(rng.normal(0.16, 0.05, n), 0.02, 0.40),
        "minor_woba": np.clip(rng.normal(0.340, 0.04, n), 0.20, 0.50),
        "minor_bb_pct": np.clip(rng.normal(0.09, 0.03, n), 0.01, 0.25),
        "mlb_pa": rng.integers(160, 1400, n).astype(float),
        "mlb_k_pct": np.clip(0.60 * minor_k + 0.10 + rng.normal(0, 0.025, n), 0.05, 0.45),
        "mlb_iso": np.clip(rng.normal(0.145, 0.04, n), 0.02, 0.40),
        "mlb_woba": np.clip(rng.normal(0.315, 0.03, n), 0.20, 0.50),
        "mlb_bb_pct": np.clip(rng.normal(0.085, 0.02, n), 0.01, 0.25),
        "has_mlb_label": True,
        "debut_cohort": rng.choice([2018, 2019, 2020, 2021, 2022, 2023], n),
    })


def test_an_empty_ContextSpec_is_a_byte_exact_no_op():
    """⭐ THE LADDER'S BASELINE MUST BE THE REAL INCUMBENT, NOT A RE-IMPLEMENTATION OF IT. If
    `ContextSpec()` moved a single rate, every 'lift vs E7.3' number in the report would be measured
    against something E7.3 never ran (the NF1.8 `_NF17_WINNER_LABEL` trap, one rung over)."""
    pairs = _toy_pairs()
    for m in PF_METRICS:
        out = apply_context(pairs, None, ContextSpec(), m)
        pd.testing.assert_series_equal(out[f"minor_{m}"], pairs[f"minor_{m}"], check_names=False)
        assert ContextSpec().is_noop and ContextSpec().label == "baseline"


def test_the_partial_pool_with_no_weight_col_is_byte_identical_to_the_e7_3_fit():
    """The `weight_col` add to `PartialPoolProjector` is a live change to a SHIPPED E7.3 code path.
    Default-None must reproduce the incumbent fit exactly, or every downstream E7.3/E7.5 number moved
    silently when this slice landed."""
    pairs = _toy_pairs()
    data = build_target(pairs, MleConfig(metric="k_pct"))
    train, test = data.iloc[:180], data.iloc[180:]
    a, _ = PartialPoolProjector(prior_scale=2.0).fit(train).predict(test)
    b, _ = PartialPoolProjector(prior_scale=2.0, weight_col=None).fit(train).predict(test)
    np.testing.assert_allclose(a, b, rtol=0, atol=0)
    # and a weight column DOES change the fit (otherwise the arm would be a silent no-op)
    c, _ = PartialPoolProjector(prior_scale=2.0, weight_col="mlb_pa").fit(train).predict(test)
    assert not np.allclose(a, c)


def test_observation_weights_are_normalised_and_tail_clipped():
    """A weighted fit has no partial pooling ACROSS observations — the shrinkage lives in the
    coefficient prior. Unclipped label-PA weights would let one 3,000-PA veteran outvote thirty rookies,
    and an un-normalised scale would silently move sigma2 and with it every posterior width."""
    pairs = _toy_pairs()
    data = build_target(pairs, MleConfig(metric="k_pct"))
    t = data[data["has_target"]].reset_index(drop=True)
    t.loc[0, "mlb_pa"] = 1e6
    t.loc[1, "mlb_pa"] = np.nan
    w = PartialPoolProjector(weight_col="mlb_pa")._weights(t)
    assert w is not None and np.all(w > 0)
    assert w.max() <= 5.0 + 1e-9 and w.min() >= 0.2 - 1e-9
    assert np.isfinite(w).all()
    assert PartialPoolProjector()._weights(t) is None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The small-sample hardening does what the story asked for
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_reliability_regresses_ISO_harder_than_K_pct_at_equal_sample():
    """⭐ THE STORY'S EXPLICIT ASK, as an assertion. A single regression slope is one number and cannot
    say 'regress power harder than discipline'; per-component stabilisation points can. At 160 PA the
    literature constants keep ~73% of a K% deviation and ~50% of an ISO deviation."""
    pa = 160.0
    r_k = reliability_weight([pa], STABILIZATION_PA["k_pct"])[0]
    r_iso = reliability_weight([pa], STABILIZATION_PA["iso"])[0]
    assert r_k > r_iso, "K% must be trusted MORE than ISO at equal PA — it stabilises fastest"
    assert r_k == pytest.approx(160 / 220, abs=1e-9)
    assert r_iso == pytest.approx(160 / 320, abs=1e-9)
    assert STABILIZATION_PA["k_pct"] < STABILIZATION_PA["bb_pct"] < STABILIZATION_PA["iso"] \
        < STABILIZATION_PA["woba"], "the ordering IS the measured translatability ordering"


def test_reliability_shrinks_a_thin_line_harder_than_a_thick_one():
    """The whole point of the heteroskedastic shrink: a 160-PA A-ball line must move MORE than a
    900-PA AAA line. A constant-r foil that moved them equally would be the degenerate."""
    pairs = pd.DataFrame({
        "player_id": ["thin", "thick"], "level": ["Single-A", "Triple-A"],
        "minor_pa": [160.0, 900.0], "minor_iso": [0.300, 0.300],
        "env_level_iso": [0.140, 0.140],
    })
    out = apply_context(pairs, None, ContextSpec(reliability=1.0), "iso")
    thin, thick = out.loc[0, "minor_iso"], out.loc[1, "minor_iso"]
    assert abs(thin - 0.140) < abs(thick - 0.140), "the thin line must be pulled harder to the anchor"
    # the degenerate foil moves them by the SAME fraction — which is exactly why it must lose
    const = apply_context(pairs, None,
                          ContextSpec(reliability=1.0, constant_reliability=True), "iso")
    r = const["minor_iso_reliability"].to_numpy(float)
    assert r[0] == pytest.approx(r[1])


def test_a_missing_context_row_is_an_honest_no_op_never_a_fabricated_factor():
    """A player the context join misses must keep his raw rate. Fabricating 1.0 and a factor of 1.0 are
    the same number here, but the coverage report must be able to tell them apart."""
    pairs = _toy_pairs(40)
    ctx = pd.DataFrame({"player_id": ["p0"], "level": [pairs.loc[0, "level"]],
                        "pf_iso_exposure": [1.25]})
    out = apply_context(pairs, ctx, ContextSpec(park="exposure"), "iso")
    assert out.loc[0, "minor_iso"] == pytest.approx(pairs.loc[0, "minor_iso"] / 1.25)
    assert out.loc[1, "minor_iso"] == pytest.approx(pairs.loc[1, "minor_iso"])
    cov = context_coverage(out, "iso", ContextSpec(park="exposure"))
    assert cov["pct_rows_moved"] == pytest.approx(100.0 / 40, abs=1e-6)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The anchors must FIRE — an anchor that cannot fail passes on nothing (NF1.7 lesson 1)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _planted_park_pairs(park_effect: float, n: int = 700, seed: int = 5):
    """A synthetic world where the park effect is REAL and KNOWN.

    True MLB ISO is a clean function of true talent. The OBSERVED minor ISO is talent inflated by the
    player's park. So dividing by the right park factor must recover talent and improve translation —
    and dividing by a PERMUTED factor must make it worse. If the harness cannot separate those two
    worlds, no result it produces about real parks means anything.
    """
    rng = np.random.default_rng(seed)
    park = rng.choice(np.array([1.0, park_effect, 1.0 / park_effect]), n)
    talent = np.clip(rng.normal(0.160, 0.045, n), 0.03, 0.35)
    observed = np.clip(talent * park, 0.01, 0.60)
    pairs = pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)],
        "level": rng.choice(["Triple-A", "Double-A"], n),
        "league": rng.choice(["IL", "EL"], n),
        "age": rng.normal(23.5, 1.5, n),
        "minor_pa": rng.integers(300, 700, n).astype(float),
        "minor_iso": observed,
        "mlb_pa": rng.integers(300, 900, n).astype(float),
        "mlb_iso": np.clip(0.75 * talent + 0.03 + rng.normal(0, 0.012, n), 0.02, 0.40),
        "has_mlb_label": True,
        "debut_cohort": rng.choice([2017, 2018, 2019, 2020, 2021, 2022, 2023], n),
    })
    ctx = pd.DataFrame({
        "player_id": pairs["player_id"], "level": pairs["level"],
        "pf_iso_exposure": park, "pf_iso_exposure_noloo": park,
        "pf_iso_home": park, "env_iso": 0.160, "env_level_iso": 0.160,
    })
    return pairs, ctx


def test_the_ladder_recovers_a_PLANTED_park_effect_and_the_placebo_loses():
    """⭐ THE LOAD-BEARING TEST. On a world with a real 25% park effect the park arm must BEAT the
    baseline, the permuted-park PLACEBO must LOSE to it, and the verdict must be ADD. This is what makes
    every anchor in the report a live check rather than a sentence."""
    pairs, ctx = _planted_park_pairs(1.25)
    arms = tuple(r for r in LADDER
                 if r.label in ("S0_baseline", "S1_park_exposure", "A_park_placebo",
                                "A_park_noloo", "I_reliability_only", "A_rel_constant"))
    res = run_ladder(pairs, ctx, "iso", arms)
    lb = res.leaderboard.set_index("arm")["oos_mae"]
    assert lb["S1_park_exposure"] < lb["S0_baseline"], (
        "a REAL park effect must be recovered by dividing it out", lb.to_dict())
    assert lb["A_park_placebo"] > lb["S1_park_exposure"], (
        "the permuted-park placebo must LOSE to the real park", lb.to_dict())
    assert not res.anchors["placebo_vs_real_park"]["violated"]
    assert not res.anchors["noloo_vs_loo"]["violated"]
    assert res.verdict == "ADD", res.reasons


def test_a_null_world_does_not_produce_an_ADD():
    """The other side of the same instrument: with NO park effect planted, the park arm must not clear
    the gate. A harness that says ADD on noise would ship a mirage into a draft board."""
    pairs, ctx = _planted_park_pairs(1.0, seed=9)   # every factor is exactly 1.0 → nothing to recover
    arms = tuple(r for r in LADDER
                 if r.label in ("S0_baseline", "S1_park_exposure", "A_park_placebo",
                                "A_park_noloo", "I_reliability_only", "A_rel_constant"))
    res = run_ladder(pairs, ctx, "iso", arms)
    # a factor of exactly 1.0 moves nothing → the dead-join guard must catch it rather than let a
    # byte-identical arm read as an honest null
    assert res.verdict in ("DROP", "BLOCKED"), res.reasons
    assert res.verdict != "ADD"


def test_a_context_join_that_matches_nothing_can_never_be_selected_and_trips_the_run_level_guard():
    """A context join that silently matches nothing produces an arm byte-identical to the baseline. Its
    MAE TIES, so it reads as an honest null — but it is the repo's silent-empty class, and shipping it
    as 'measured, no effect' would be a false negative nobody could see.

    Two defences, at two altitudes, because a per-metric BLOCK would be wrong (a genuinely neutral park
    factor on K% is the PREDICTED outcome and must not read as a fault): per metric the dead arm is
    merely UNSELECTABLE and reported; across metrics `dead_context_join` HALTs, because a join that
    moves NOTHING ANYWHERE cannot be four coincidental neutral factors."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import dead_context_join

    pairs, _ = _planted_park_pairs(1.25, n=300)
    empty_ctx = pd.DataFrame({"player_id": ["nobody"], "level": ["Triple-A"],
                              "pf_iso_exposure": [1.3]})
    arms = tuple(r for r in LADDER if r.label in ("S0_baseline", "S1_park_exposure"))
    res = run_ladder(pairs, empty_ctx, "iso", arms)
    assert res.verdict == "DROP", res.reasons
    assert not res.leaderboard.set_index("arm").loc["S1_park_exposure", "active"]
    assert any("NO-OP arms" in r for r in res.reasons), res.reasons
    health = dead_context_join({"iso": res})
    assert not health["context_join_alive"] and "DEAD JOIN" in health["reading"]


def test_every_arm_is_scored_on_the_SAME_labelled_population():
    """If a rung ever changed `has_target`, the arms would be compared on different PLAYERS — the
    cheapest way an ablation lies. `run_ladder` asserts it; this proves the assertion is reachable."""
    pairs, ctx = _planted_park_pairs(1.25, n=300)
    arms = tuple(r for r in LADDER if r.label in ("S0_baseline", "S1_park_exposure"))
    res = run_ladder(pairs, ctx, "iso", arms)          # must not raise
    assert set(res.leaderboard["arm"]) == {"S0_baseline", "S1_park_exposure"}

    bad = pairs.copy()
    with pytest.raises(AssertionError, match="LABELLED POPULATION"):
        import betting_ml.scripts.milb_mle.run_e7_12_slice1 as mod
        orig = mod._adjusted
        try:
            def sabotage(p, c, s, m):
                out = orig(p, c, s, m)
                if s.park != "off":
                    out.loc[out.index[:50], "minor_pa"] = 1.0   # drops rows below the PA floor
                return out
            mod._adjusted = sabotage
            mod.run_ladder(bad, ctx, "iso", arms)
        finally:
            mod._adjusted = orig


def test_the_placebo_is_deterministic_and_preserves_the_factor_distribution():
    """A placebo that moves between runs cannot be a gate; a placebo that changes the marginal
    distribution is testing something other than 'the wrong park'."""
    pairs, ctx = _planted_park_pairs(1.25, n=400)
    a = apply_context(pairs, ctx, ContextSpec(park="placebo"), "iso")["minor_iso_park_factor"]
    b = apply_context(pairs, ctx, ContextSpec(park="placebo"), "iso")["minor_iso_park_factor"]
    np.testing.assert_allclose(a, b)
    real = apply_context(pairs, ctx, ContextSpec(park="exposure"), "iso")["minor_iso_park_factor"]
    np.testing.assert_allclose(np.sort(a.to_numpy(float)), np.sort(real.to_numpy(float)))
    assert not np.allclose(a.to_numpy(float), real.to_numpy(float))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Deflation must be readable — four numbers, not one (NF1.8)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_deflation_separates_a_TIE_from_a_REAL_separation():
    """CLAUDE.md: a high PBO on a TIED field is the NULL, not evidence of overfitting; the discriminator
    is whether picking the in-sample winner COST anything. Both halves are pinned here so a future
    session cannot condemn a tie on PBO alone — nor bless a real overfit."""
    rng = np.random.default_rng(4)
    idx = list(range(2016, 2026))
    tie = pd.DataFrame({f"clone{i}": 0.030 + rng.normal(0, 0.00008, len(idx)) for i in range(6)},
                       index=idx)
    got = deflation_report(tie)
    assert got["pbo"] is not None
    assert got["os_gap_pct"] < 1.0, got            # picking any clone costs ~nothing
    assert got["contender_spread_pct"] < 2.0, got
    assert sum(f["IS_half_wins"] for f in got["flips"]) > 0

    real = tie.copy()
    real["winner"] = 0.024
    sep = deflation_report(real)
    assert sep["pbo"] == 0.0, sep
    assert sep["flips"][0]["config"] == "winner"


def test_deflation_over_the_eligible_set_excludes_the_anchors():
    """A deflation statistic computed over a field that CONTAINS its own deliberately-bad anchors
    measures the anchors, not the contest (the NF-D14 / NF1.8 lesson). The eligible-set restriction is
    what keeps the reported spread meaningful."""
    idx = list(range(2016, 2026))
    m = pd.DataFrame({"a": 0.030, "b": 0.0301, "anchor": 0.060}, index=idx)
    full = deflation_report(m)
    elig = deflation_report(m, eligible=["a", "b"])
    assert full["full_spread_pct"] > 50.0
    assert elig["full_spread_pct"] < 1.0
    assert elig["n_configs"] == 2


def test_bh_fdr_controls_the_four_metric_family():
    """Four metrics is a four-test family. Uncorrected, one lucky p=0.04 reads as a discovery."""
    assert bh_fdr({"a": 0.001, "b": 0.20, "c": 0.60, "d": 0.90}, alpha=0.10) == {
        "a": True, "b": False, "c": False, "d": False}
    all_null = bh_fdr({"a": 0.30, "b": 0.40, "c": 0.50, "d": 0.60}, alpha=0.10)
    assert not any(all_null.values())
    assert bh_fdr({}) == {}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The pre-registered directional falsification
# ══════════════════════════════════════════════════════════════════════════════════════════════

class _FakeResult:
    def __init__(self, lift):
        self.leaderboard = pd.DataFrame([{"arm": "S1_park_exposure", "pct_lift_vs_S0": lift}])


def test_the_directional_read_flags_a_lift_that_is_NOT_park_shaped():
    """Parks move balls in play. A lift that is just as big on K%/BB% as on ISO/wOBA is generic
    shrinkage in a park costume, and the report must SAY so regardless of how the gates landed."""
    park_shaped = directional_read({"iso": _FakeResult(1.8), "woba": _FakeResult(1.2),
                                    "k_pct": _FakeResult(0.05), "bb_pct": _FakeResult(0.02)})
    assert park_shaped["direction_consistent_with_a_park_mechanism"]
    assert park_shaped["reading"].startswith("✅")

    uniform = directional_read({"iso": _FakeResult(1.0), "woba": _FakeResult(1.0),
                                "k_pct": _FakeResult(1.4), "bb_pct": _FakeResult(1.3)})
    assert not uniform["direction_consistent_with_a_park_mechanism"]
    assert "generic shrinkage" in uniform["reading"]


def test_the_ladder_carries_all_three_degenerate_anchors_and_they_are_non_selectable():
    """An anchor silently dropped from the ladder is an anchor that passes on nothing. Pin the set."""
    labels = {r.label for r in LADDER}
    for required in ("A_park_placebo", "A_park_noloo", "A_rel_constant"):
        assert required in labels, required
        assert not next(r for r in LADDER if r.label == required).selectable
    assert next(r for r in LADDER if r.label == "S0_baseline").spec.is_noop


def test_the_e7_3_winner_prior_scales_are_pinned_literals_not_recomputed():
    """The reference the whole ladder measures against must not be rebuilt from the code the slice
    changes — that is how a harness silently compares a change against itself (NF1.8)."""
    import inspect

    import betting_ml.scripts.milb_mle.run_e7_12_slice1 as mod
    src = inspect.getsource(mod)
    assert 'E73_WINNER_PRIOR_SCALE: dict[str, float] = {"woba": 4.0, "k_pct": 2.0, ' \
           '"bb_pct": 4.0, "iso": 2.0}' in src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The BUILDER's SQL, executed end-to-end against DuckDB fixtures
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⚠️ THIS IS THE RUNTIME GATE THE REST OF CI CANNOT PROVIDE. CLAUDE.md: "CI mocks ALL IO by design →
# the fast gate CANNOT see the bug class that keeps biting." The park-context assembly is ~200 lines of
# generated SQL with a self-join window, a full-outer join and a leave-one-player-out subtraction — every
# one of which would fail SILENTLY (an empty frame, a NULL factor, a doubled bucket) on the box and
# nowhere else. So the SQL is executed here against in-memory fixtures: no S3, no credentials, but the
# real query text, the real joins and the real arithmetic.

def _synthetic_milb_logs(seed: int = 21) -> pd.DataFrame:
    """A small two-season Triple-A league: 4 teams, home-and-home, one park (team 1) that inflates
    extra-base hits by ~40%. Every column the builder reads is present and typed as the E7.1 ingest
    lands it."""
    rng = np.random.default_rng(seed)
    rows, game_pk = [], 1000
    teams = [1, 2, 3, 4]
    hot_park = 1
    for season in (2022, 2023):
        for home in teams:
            for away in teams:
                if home == away:
                    continue
                for rep in range(14):          # 14 meetings each way per season
                    game_pk += 1
                    day = 1 + (rep % 28)
                    for side, team in (("home", home), ("away", away)):
                        for slot in range(9):
                            pid = team * 100 + slot
                            pa = int(rng.integers(3, 6))
                            ab = pa - int(rng.binomial(pa, 0.10))
                            h = int(rng.binomial(max(ab, 1), 0.26))
                            xbh_p = 0.42 if home == hot_park else 0.30
                            dbl = int(rng.binomial(h, xbh_p * 0.7))
                            hr = int(rng.binomial(max(h - dbl, 0), xbh_p * 0.5))
                            rows.append({
                                "game_pk": game_pk, "player_id": pid, "team_id": team,
                                "team_side": side, "season": season,
                                "level_name": "Triple-A", "league_name": "IL",
                                "game_type": "R", "is_batter": True,
                                "official_date": f"{season}-06-{day:02d}",
                                "venue_id": home * 10, "venue_name": f"Park {home}",
                                "age": 23.0,
                                "bat_plate_appearances": pa, "bat_at_bats": ab, "bat_hits": h,
                                "bat_doubles": dbl, "bat_triples": 0, "bat_home_runs": hr,
                                "bat_walks": pa - ab, "bat_intentional_walks": 0,
                                "bat_hit_by_pitch": 0, "bat_sac_flies": 0,
                                "bat_strike_outs": int(rng.binomial(pa, 0.22)),
                                "bat_total_bases": h + dbl + 3 * hr,
                            })
    return pd.DataFrame(rows)


def _fixture_connect(logs: pd.DataFrame, debut_sql: str, debut_table: str = "mart_batter_rolling_stats"):
    """A FRESH DuckDB per call — `build_park_context` closes its connection in a `finally`, so a shared
    handle works exactly once and then throws. Returning a factory keeps the fixture honest about that.

    Accepts (and ignores) the `ReducedSpec` the real `_connect` takes, so one fixture serves both sides.
    """
    import duckdb

    def factory(*_args, **_kwargs):
        con = duckdb.connect()
        con.register("_logs", logs)
        con.execute("create view milb_logs as select * from _logs")
        con.execute(f"create view {debut_table} as {debut_sql}")
        return con
    return factory


_NO_DEBUTS = "select 999999 as batter_id, DATE '2019-01-01' as game_date, 2019 as game_year"
_ALL_DEBUT_2023 = ("select distinct player_id as batter_id, DATE '2023-01-01' as game_date, "
                   "2023 as game_year from _logs")


def test_the_builder_sql_runs_end_to_end_and_recovers_a_planted_park(monkeypatch):
    """⭐ The whole builder, executed. Team 1's park is planted ~40% hotter for extra-base hits; the
    assembled context must give team-1 players a materially ABOVE-1 exposure-weighted ISO factor and
    everyone else something nearer neutral — and it must do so through the real window self-join, the
    real full-outer join and the real LOO subtraction."""
    pytest.importorskip("duckdb")
    import betting_ml.scripts.milb_mle.build_park_context as bpc

    logs = _synthetic_milb_logs()
    monkeypatch.setattr(bpc, "_connect", _fixture_connect(logs, _NO_DEBUTS))

    ctx = bpc.build_park_context(levels=("Triple-A",), window=3, season_floor=None)
    assert not ctx.empty, "the assembly produced NOTHING — the joins are dead"
    assert set(ctx.columns) >= {"player_id", "level", "pf_iso_exposure", "pf_iso_exposure_noloo",
                                "pf_iso_home", "env_iso", "env_level_iso", "context_pa"}
    assert ctx.duplicated(subset=["player_id", "level"]).sum() == 0, "the context grain must be unique"
    assert ctx["pf_iso_exposure"].notna().all()

    ctx["team"] = ctx["player_id"].astype(int) // 100
    hot = float(ctx.loc[ctx["team"] == 1, "pf_iso_exposure"].mean())
    cold = float(ctx.loc[ctx["team"] != 1, "pf_iso_exposure"].mean())
    assert hot > cold, (hot, cold)
    assert hot > 1.02, ("the planted hitter's park must resolve ABOVE neutral", hot)

    # the SUMMARY's face-validity guard must see real dispersion (a spreadless table is a dead join)
    summary = bpc.summarise(ctx)
    assert summary["iso"]["spread_p95_p05"] > 0.01, summary

    # …and the pre-debut cut is honoured: give everyone a 2023 debut and the 2023 PA must vanish
    monkeypatch.setattr(bpc, "_connect", _fixture_connect(logs, _ALL_DEBUT_2023))
    cut = bpc.build_park_context(levels=("Triple-A",), window=3, season_floor=None)
    assert float(cut["context_pa"].sum()) < float(ctx["context_pa"].sum()), (
        "a post-debut MiLB game must NOT count toward the pre-debut exposure weights")


def test_leave_one_player_out_bites_and_removes_a_HOME_SIDE_exposure_bias(monkeypatch):
    """The LOO subtraction is the load-bearing correctness property of this slice and it lives inside
    the SQL. Two things are pinned here — and the second is a FINDING this test taught us.

    ⭐ **THE CLASSIC TEAM-BASED PARK FACTOR IS ALREADY FAIRLY ROBUST TO SELF-INCLUSION.** A player on the
    home team lands in BOTH buckets — his home games in the numerator, his road games in the denominator
    — so his own bat largely cancels and the non-LOO bias is SMALL in the symmetric case. That makes the
    LOO correction cheap insurance rather than a large move, and the report says so rather than
    overclaiming. The bias stops being small exactly where exposure is UNBALANCED, which is the case
    built below: a home-only masher inflates his park's numerator and never its denominator, so the
    non-LOO factor is biased UP and dividing by it would shrink him toward the mean using his own
    production. LOO must undo precisely that, and the balanced player must barely move."""
    pytest.importorskip("duckdb")
    import betting_ml.scripts.milb_mle.build_park_context as bpc

    logs = _synthetic_milb_logs(seed=33)
    # a HOME-ONLY masher on team 1: present in home_bucket(1), absent from road_bucket(1)
    drop = (logs["player_id"] == 100) & ~((logs["team_id"] == 1) & (logs["team_side"] == "home"))
    logs = logs[~drop].copy()
    star = logs["player_id"] == 100
    logs.loc[star, "bat_hits"] = 4
    logs.loc[star, "bat_doubles"] = 1
    logs.loc[star, "bat_home_runs"] = 3
    logs.loc[star, "bat_total_bases"] = 14
    monkeypatch.setattr(bpc, "_connect", _fixture_connect(logs, _NO_DEBUTS))

    ctx = bpc.build_park_context(levels=("Triple-A",), window=3, season_floor=None)
    row = ctx[ctx["player_id"] == "100"].iloc[0]
    loo, noloo = float(row["pf_iso_exposure"]), float(row["pf_iso_exposure_noloo"])
    assert loo != pytest.approx(noloo, abs=1e-9), (
        "LOO and non-LOO are IDENTICAL — the subtraction is not happening, and the headline arm would "
        "be silently self-shrinking (the confound this slice exists to avoid)")
    assert loo < noloo, (
        "removing a home-only masher's own production must LOWER the park factor he is divided by; "
        "otherwise the adjustment regresses him toward the mean using his own bat", loo, noloo)
    # a BALANCED player is barely moved — asserted so a future session does not read the small
    # symmetric-case correction as a broken subtraction
    bal = ctx[ctx["player_id"] == "201"].iloc[0]
    assert abs(float(bal["pf_iso_exposure"]) - float(bal["pf_iso_exposure_noloo"])) < abs(loo - noloo)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. --apply must be a COMPLETE drop-in replacement, and must write NOTHING on a null slice
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _multi_metric_pairs(n: int = 700, seed: int = 41):
    """Four metrics; only ISO carries a planted park effect."""
    rng = np.random.default_rng(seed)
    park = rng.choice(np.array([1.0, 1.22, 1 / 1.22]), n)
    iso_t = np.clip(rng.normal(0.160, 0.045, n), 0.03, 0.35)
    k_t = np.clip(rng.normal(0.22, 0.05, n), 0.05, 0.45)
    pairs = pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)],
        "level": rng.choice(["Triple-A", "Double-A"], n),
        "league": rng.choice(["IL", "EL"], n),
        "age": rng.normal(23.5, 1.5, n),
        "minor_pa": rng.integers(250, 800, n).astype(float),
        "minor_iso": np.clip(iso_t * park, 0.01, 0.6),
        "minor_k_pct": k_t,
        "minor_bb_pct": np.clip(rng.normal(0.09, 0.03, n), 0.01, 0.25),
        "minor_woba": np.clip(rng.normal(0.34, 0.04, n), 0.20, 0.50),
        "mlb_pa": rng.integers(250, 1200, n).astype(float),
        "mlb_iso": np.clip(0.75 * iso_t + 0.03 + rng.normal(0, 0.015, n), 0.02, 0.40),
        "mlb_k_pct": np.clip(0.6 * k_t + 0.10 + rng.normal(0, 0.025, n), 0.05, 0.45),
        "mlb_bb_pct": np.clip(rng.normal(0.085, 0.02, n), 0.01, 0.25),
        "mlb_woba": np.clip(rng.normal(0.315, 0.03, n), 0.20, 0.50),
        "has_mlb_label": True,
        "debut_cohort": rng.choice([2017, 2018, 2019, 2020, 2021, 2022, 2023], n),
    })
    ctx = pd.DataFrame({"player_id": pairs.player_id, "level": pairs.level})
    for m in PF_METRICS:
        f = park if m == "iso" else np.ones(n)
        ctx[f"pf_{m}_exposure"] = f
        ctx[f"pf_{m}_exposure_noloo"] = f
        ctx[f"pf_{m}_home"] = f
        ctx[f"env_{m}"] = 1.0
        ctx[f"env_level_{m}"] = 1.0
    return pairs, ctx


def test_apply_re_emits_EVERY_metric_even_the_ones_that_were_dropped():
    """🪤 THE FOOTGUN. E8.0's board reads `mle_k_pct`, `mle_bb_pct` AND `mle_iso` from ONE wide table, so
    a re-emission carrying only the metrics that WON would silently delete two of the board's three
    batter inputs — every prospect's composite would quietly renormalise onto whatever survived. A
    partial write is not a partial improvement, it is a regression."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import build_applied_projections

    pairs, ctx = _multi_metric_pairs()
    arms = tuple(r for r in LADDER if r.label in ("S0_baseline", "S1_park_exposure",
                                                  "A_park_placebo", "A_park_noloo",
                                                  "I_reliability_only", "A_rel_constant"))
    results = {m: run_ladder(pairs, ctx, m, arms) for m in ("k_pct", "iso")}
    assert results["iso"].verdict == "ADD", results["iso"].reasons
    assert results["k_pct"].verdict != "ADD", "a neutral park factor must not produce an ADD"

    applied: dict = {}
    wide, changed = build_applied_projections(pairs, ctx, results, applied)
    assert changed and set(applied) == {"iso"}
    for m in ("k_pct", "iso"):
        assert f"mle_{m}" in wide.columns and wide[f"mle_{m}"].notna().any(), m
    # per-metric provenance makes it visible WHICH columns actually moved
    assert set(wide["iso_context_spec"].unique()) == {"park:exposure"}
    assert set(wide["k_pct_context_spec"].unique()) == {"baseline"}
    assert set(wide["model_version"].unique()) == {"milb_mle_v2_parkctx"}


def test_a_dropped_metric_is_re_emitted_byte_exactly_as_the_incumbent():
    """The DROP metrics are re-emitted rather than copied, so 're-emitting the incumbent' has to mean
    exactly that. If it drifted by even a rounding step, a null slice would still move every prospect's
    projection — the worst possible outcome for a run whose whole finding is 'nothing changed'."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import build_applied_projections

    pairs, ctx = _multi_metric_pairs(n=400, seed=44)
    arms = tuple(r for r in LADDER if r.label in ("S0_baseline", "S1_park_exposure"))
    results = {"k_pct": run_ladder(pairs, ctx, "k_pct", arms)}
    applied: dict = {}
    wide, changed = build_applied_projections(pairs, ctx, results, applied)
    assert not changed and applied == {}

    incumbent = emit_projections(
        build_target(pairs, MleConfig(metric="k_pct")),
        lambda: PartialPoolProjector(prior_scale=results["k_pct"].prior_scale),
        MleConfig(metric="k_pct"))
    merged = wide[["player_id", "level", "mle_k_pct"]].merge(
        incumbent[["player_id", "level", "mle_k_pct"]], on=["player_id", "level"],
        suffixes=("_new", "_old"))
    assert len(merged) == len(incumbent) > 0
    np.testing.assert_allclose(merged["mle_k_pct_new"], merged["mle_k_pct_old"], rtol=0, atol=1e-12)


def test_the_run_level_dead_join_check_separates_a_dead_join_from_a_neutral_factor():
    """The cross-metric question. A neutral park factor for K% and a join that matches nobody produce
    the SAME per-arm evidence; only 'did the context move ANYTHING?' tells them apart. Getting this
    wrong in either direction is expensive: BLOCK on a neutral factor and the predicted result reads as
    a fault; PASS on a dead join and four dead arms read as four honest nulls."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import dead_context_join

    class _R:
        def __init__(self, moved):
            self.leaderboard = pd.DataFrame([
                {"arm": "S0_baseline", "kind": "ladder", "pct_rows_moved": 0.0},
                {"arm": "S1_park_exposure", "kind": "ladder", "pct_rows_moved": moved},
            ])

    neutral_k_live_iso = dead_context_join({"k_pct": _R(0.0), "iso": _R(96.0)})
    assert neutral_k_live_iso["context_join_alive"]
    assert neutral_k_live_iso["reading"].startswith("✅")

    all_dead = dead_context_join({"k_pct": _R(0.0), "iso": _R(0.0)})
    assert not all_dead["context_join_alive"]
    assert "DEAD JOIN" in all_dead["reading"]


def test_a_no_op_arm_is_unselectable_rather_than_a_hard_block():
    """A park factor of ~1.0 on a discipline metric is the PREDICTED outcome, not a fault. It must make
    the arm unselectable (it is the baseline in disguise and cannot be 'the winner') and be reported —
    never BLOCK the metric, which would turn the falsification's expected result into an error."""
    pairs, ctx = _multi_metric_pairs(n=400, seed=46)
    arms = tuple(r for r in LADDER if r.label in ("S0_baseline", "S1_park_exposure"))
    res = run_ladder(pairs, ctx, "k_pct", arms)
    assert res.verdict == "DROP", res.reasons
    row = res.leaderboard.set_index("arm").loc["S1_park_exposure"]
    assert not row["active"]
    assert any("NO-OP arms" in r for r in res.reasons), res.reasons


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. The PAIRED anchor — it must still FIRE on real self-shrinkage after being loosened off a tie
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⚠️ CONTEXT, so a future session can audit the decision. The FIRST version of these anchors compared two
# mean MAEs with a 1e-9 tolerance, and on the real 2026-07-31 run it declared a violation on `k_pct` off a
# 1e-5 gap — a numerical TIE read as fatal evidence (the E2.1-r / NF1.8 error, pointed the other way), and
# a tie that this module's own docstring PREDICTED before the run. Loosening a guard because it fired is
# normally the overfit move, so the correction is only legitimate if the guard still catches what it
# exists to catch. That is what these tests pin: `paired_anchor` separates a tie from a systematic
# advantage, and a constructed self-shrinkage world still DISQUALIFIES the park.

def test_the_paired_anchor_separates_a_tie_from_a_systematic_advantage():
    idx = list(range(2016, 2027))
    rng = np.random.default_rng(11)
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import paired_anchor

    # a TIE: the challenger is better on some folds, worse on others, mean ≈ 0
    base = 0.040 + rng.normal(0, 0.0005, len(idx))
    tie = pd.DataFrame({"defender": base, "challenger": base + rng.normal(0, 2e-5, len(idx))}, index=idx)
    got = paired_anchor(tie, "challenger", "defender")
    assert not got["violated"], got
    assert got["p_challenger_better"] > 0.10

    # SYSTEMATIC: the challenger is better on essentially every fold
    sysd = pd.DataFrame({"defender": base,
                         "challenger": base - 0.0008 + rng.normal(0, 5e-5, len(idx))}, index=idx)
    got = paired_anchor(sysd, "challenger", "defender")
    assert got["violated"], got
    assert got["challenger_fold_wins"] == len(idx)

    # ⚠️ ZERO VARIANCE is the MOST systematic case, not an untestable one — a t-test guard that bails
    # on it would let a challenger that wins by the same amount every fold pass on nothing.
    const_win = pd.DataFrame({"defender": base, "challenger": base - 0.0008}, index=idx)
    assert paired_anchor(const_win, "challenger", "defender")["violated"]
    const_tie = pd.DataFrame({"defender": base, "challenger": base.copy()}, index=idx)
    assert not paired_anchor(const_tie, "challenger", "defender")["violated"]

    # a MISSING anchor is NOT a pass — it must be reported as unavailable (NF1.7 lesson 1)
    absent = paired_anchor(tie, "nope", "defender")
    assert absent["available"] is False and absent["violated"] is False


def test_a_real_self_shrinkage_world_still_DISQUALIFIES_the_park():
    """⭐ THE TEST THAT LICENSES THE LOOSENING. Build a world where the non-LOO factor is genuinely
    self-inclusive — each player's factor tracks his OWN minor line, so dividing by it shrinks him
    toward the mean and lowers MAE for reasons that have nothing to do with a venue. The anchor must
    still catch it, and the park must be removed from selection while the NON-park rungs survive."""
    rng = np.random.default_rng(77)
    n = 700
    talent = np.clip(rng.normal(0.160, 0.045, n), 0.03, 0.35)
    noise = rng.normal(0, 0.030, n)
    observed = np.clip(talent + noise, 0.01, 0.60)                     # noisy, NO park effect at all
    pairs = pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)],
        "level": rng.choice(["Triple-A", "Double-A"], n),
        "league": rng.choice(["IL", "EL"], n),
        "age": rng.normal(23.5, 1.5, n),
        "minor_pa": rng.integers(300, 700, n).astype(float),
        "minor_iso": observed,
        "mlb_pa": rng.integers(300, 900, n).astype(float),
        "mlb_iso": np.clip(0.75 * talent + 0.03 + rng.normal(0, 0.012, n), 0.02, 0.40),
        "has_mlb_label": True,
        "debut_cohort": rng.choice([2017, 2018, 2019, 2020, 2021, 2022, 2023], n),
    })
    true_pf = np.ones(n)                                   # the honest factor: no park effect exists
    # ⭐ THE CONFOUND, FAITHFULLY. A self-inclusive factor is inflated by the player's OWN sampling
    # NOISE, so dividing by it strips his own error and leaves something closer to true talent. It is
    # NOT merely a monotone compression of his observed rate — a linear model would just absorb that in
    # its slope, which is why an earlier version of this fixture produced no confound at all.
    self_pf = 1.0 + 0.9 * noise / float(observed.mean())
    ctx = pd.DataFrame({
        "player_id": pairs["player_id"], "level": pairs["level"],
        "pf_iso_exposure": true_pf, "pf_iso_exposure_noloo": self_pf, "pf_iso_home": true_pf,
        "env_iso": 0.160, "env_level_iso": 0.160,
    })
    arms = tuple(r for r in LADDER
                 if r.label in ("S0_baseline", "S1_park_exposure", "S2_level_env",
                                "A_park_placebo", "A_park_noloo"))
    res = run_ladder(pairs, ctx, "iso", arms)
    assert res.anchors["noloo_vs_loo"]["violated"], res.anchors["noloo_vs_loo"]
    assert any("PARK DISQUALIFIED" in r for r in res.reasons), res.reasons
    # the park is out of selection…
    assert not res.winner.startswith("S1_park"), res.winner
    # …and the disqualification is SCOPED — a non-park rung is still allowed to be judged
    assert res.verdict in ("ADD", "DROP") and res.verdict != "BLOCKED"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. SLICE 1p — the PITCHER side
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# The pitcher slice reuses every piece of machinery above (E7.3p's "harness reused, not forked"
# precedent, one rung up): the same ladder labels, the same three degenerate anchors, the same
# deflation, the same LOO subtraction. Only the box-count vocabulary changes. So these tests do not
# re-prove the mathematics — they prove the three things a PORT can get wrong:
#
#   1. the pitcher rate formulas and the pitcher SQL agree with `compute_pitcher_rate_metrics_from_counts`
#      (a park factor computed on a subtly different definition of GB% than the model's feature would be
#      a silent, permanent bias);
#   2. the pitcher build's sample/exposure unit is TBF, not PA (a copy-paste `_pa` in the shrink would
#      make every pitcher park factor read as maximally thin and collapse to neutral — a null that looks
#      like an honest measurement);
#   3. the two sides are genuinely the SAME ladder, and the pitcher emission is a COMPLETE drop-in for
#      the three metrics E8.0's board actually reads.

_PIT_COLS = [
    "pit_batters_faced", "pit_strike_outs", "pit_walks", "pit_home_runs",
    "pit_ground_outs", "pit_air_outs",
]


def _random_pit_counts(n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    tbf = rng.integers(20, 900, n)
    out = pd.DataFrame({"pit_batters_faced": tbf})
    out["pit_strike_outs"] = rng.binomial(tbf, 0.23)
    out["pit_walks"] = rng.binomial(tbf, 0.09)
    out["pit_home_runs"] = rng.binomial(tbf, 0.03)
    out["pit_ground_outs"] = rng.binomial(tbf, 0.20)
    out["pit_air_outs"] = rng.binomial(tbf, 0.18)
    # not part of the reduced representation, but `compute_pitcher_rate_metrics_from_counts` also
    # derives start-share and reads these directly
    out["pit_games_played"] = rng.integers(1, 30, n)
    out["pit_games_started"] = 0
    return out


def test_the_pitcher_reduced_bucket_reproduces_the_e7_3p_rate_formulas_exactly():
    """The reduced 6-field representation must be a LOSSLESS stand-in for the full `pit_*` line, or the
    park factor is computed on a different quantity than the model's feature — a bias that would never
    surface as an error, only as a permanently slightly-wrong projection."""
    from betting_ml.scripts.milb_mle.milb_mle import compute_pitcher_rate_metrics_from_counts
    from betting_ml.scripts.milb_mle.park_context import (
        PITCHER_REDUCED,
        pitcher_reduced_from_counts,
    )

    df = _random_pit_counts(300, seed=7)
    direct = compute_pitcher_rate_metrics_from_counts(df)
    reduced = pitcher_reduced_from_counts(df, "x")
    rates = rates_from_reduced(reduced, "x", PITCHER_REDUCED.pf_metrics, PITCHER_REDUCED)
    for m in PITCHER_REDUCED.pf_metrics:
        np.testing.assert_allclose(rates[m], direct[f"minor_{m}"].to_numpy(float),
                                   rtol=0, atol=1e-12, err_msg=m)


def test_the_pitcher_reduced_aggregate_sql_round_trips_through_duckdb():
    """The SQL emitter and the pandas reducer are two implementations of one definition. They are
    generated from the same `ReducedSpec`, but 'generated from the same place' is a claim; executing
    both and diffing is a proof."""
    duckdb = pytest.importorskip("duckdb")
    from betting_ml.scripts.milb_mle.park_context import (
        PITCHER_REDUCED,
        pitcher_reduced_from_counts,
    )

    df = _random_pit_counts(120, seed=11)
    con = duckdb.connect()
    con.register("t", df)
    sql = reduced_aggregate_sql("x", "", PITCHER_REDUCED)
    got = con.execute(f"select {sql} from t").df()
    want = pitcher_reduced_from_counts(df, "x").sum().to_frame().T
    for f in PITCHER_REDUCED.fields:
        assert float(got[f"x_{f}"].iloc[0]) == pytest.approx(float(want[f"x_{f}"].iloc[0])), f


def test_a_pitcher_park_factor_uses_TBF_as_its_binding_sample_not_PA():
    """🪤 THE COPY-PASTE TRAP THIS PORT COULD MOST EASILY HIDE. The EB shrink weights a park factor by
    the BINDING side's sample. On the pitcher side that field is `tbf`; a leftover `_pa` lookup would
    either KeyError (loud, fine) or — worse, if a `pa` column happened to exist — silently weight every
    factor by the wrong number and collapse the whole table toward neutral. A collapsed park table
    produces an honest-looking null, which is the expensive failure.
    """
    from betting_ml.scripts.milb_mle.park_context import PITCHER_REDUCED

    # a park with a big, WELL-MEASURED HR effect: 40,000 TBF a side over the window
    buckets = pd.DataFrame({
        "h_tbf": [40_000.0], "h_so": [9_000.0], "h_bb": [3_600.0], "h_hr": [1_600.0],
        "h_go": [8_000.0], "h_ao": [7_200.0],
        "r_tbf": [40_000.0], "r_so": [9_000.0], "r_bb": [3_600.0], "r_hr": [1_000.0],
        "r_go": [8_000.0], "r_ao": [7_200.0],
    })
    pf = park_factors_from_buckets(buckets, PITCHER_REDUCED.pf_metrics, 2000.0, PF_CLAMP,
                                   "h", "r", PITCHER_REDUCED)
    assert float(pf["pf_n_eff_pa"].iloc[0]) == 40_000.0, "the shrink weight must be TBF, not 0/NaN"
    # raw factor is 1.6; at 40k TBF vs a 2k pseudo-count the shrink should barely touch it
    assert float(pf["pf_hr_rate_raw"].iloc[0]) == pytest.approx(1.6)
    assert float(pf["pf_hr_rate"].iloc[0]) > 1.5, (
        "a well-measured 60% HR park must survive the shrink", pf.to_dict("records"))
    # and the metrics with identical buckets must come out neutral
    assert float(pf["pf_k_pct"].iloc[0]) == pytest.approx(1.0)


def _synthetic_milb_pitcher_logs(seed: int = 23) -> pd.DataFrame:
    """A two-season Triple-A league where team 1's park inflates HOME RUNS ALLOWED by ~60%."""
    rng = np.random.default_rng(seed)
    rows, game_pk = [], 5000
    teams, hot_park = [1, 2, 3, 4], 1
    for season in (2022, 2023):
        for home in teams:
            for away in teams:
                if home == away:
                    continue
                for rep in range(14):
                    game_pk += 1
                    day = 1 + (rep % 28)
                    for side, team in (("home", home), ("away", away)):
                        for slot in range(4):          # 4 pitchers a side
                            pid = team * 100 + slot
                            tbf = int(rng.integers(8, 20))
                            hr_p = 0.055 if home == hot_park else 0.030
                            rows.append({
                                "game_pk": game_pk, "player_id": pid, "team_id": team,
                                "team_side": side, "season": season,
                                "level_name": "Triple-A", "league_name": "IL",
                                "game_type": "R", "is_pitcher": True, "is_batter": False,
                                "official_date": f"{season}-06-{day:02d}",
                                "venue_id": home * 10, "venue_name": f"Park {home}",
                                "age": 24.0,
                                "pit_batters_faced": tbf,
                                "pit_strike_outs": int(rng.binomial(tbf, 0.23)),
                                "pit_walks": int(rng.binomial(tbf, 0.09)),
                                "pit_home_runs": int(rng.binomial(tbf, hr_p)),
                                "pit_ground_outs": int(rng.binomial(tbf, 0.20)),
                                "pit_air_outs": int(rng.binomial(tbf, 0.18)),
                            })
    return pd.DataFrame(rows)


_NO_PITCHER_DEBUTS = "select 999999 as pitcher_id, DATE '2019-01-01' as game_date, 2019 as game_year"


def test_the_pitcher_builder_sql_runs_end_to_end_and_recovers_a_planted_HR_park(monkeypatch):
    """⭐ The RUNTIME GATE for the pitcher port. The whole ~200-line generated assembly — the window
    self-join, the full-outer join, the LOO subtraction — executed against in-memory fixtures with the
    pitcher vocabulary. A wrong column name, a stale `is_batter`, a `bat_plate_appearances` left in the
    exposure CTE: every one of those fails SILENTLY on the box (empty frame, all-NULL factor) and
    nowhere else. CI mocks IO; this does not mock the SQL."""
    pytest.importorskip("duckdb")
    import betting_ml.scripts.milb_mle.build_park_context as bpc
    from betting_ml.scripts.milb_mle.park_context import PITCHER_REDUCED

    logs = _synthetic_milb_pitcher_logs()
    monkeypatch.setattr(bpc, "_connect", _fixture_connect(
        logs, _NO_PITCHER_DEBUTS, "mart_pitcher_rolling_stats"))

    ctx = bpc.build_park_context(levels=("Triple-A",), window=3, season_floor=None,
                                 spec=PITCHER_REDUCED)
    assert not ctx.empty, "the pitcher assembly produced NOTHING — the joins are dead"
    assert set(ctx.columns) >= {"player_id", "level", "pf_hr_rate_exposure",
                                "pf_hr_rate_exposure_noloo", "pf_hr_rate_home",
                                "env_hr_rate", "env_level_hr_rate", "context_pa"}
    assert ctx.duplicated(subset=["player_id", "level"]).sum() == 0
    assert ctx["pf_hr_rate_exposure"].notna().all()
    # ⭐ the planted effect must be RECOVERED: team-1 pitchers throw half their innings in the hot park
    ctx["team"] = ctx["player_id"].astype(int) // 100
    hot = ctx.loc[ctx["team"] == 1, "pf_hr_rate_exposure"].mean()
    rest = ctx.loc[ctx["team"] != 1, "pf_hr_rate_exposure"].mean()
    assert hot > rest > 0, (hot, rest)
    assert hot > 1.02, ("the planted HR park must show up above neutral", hot)
    # …and it must NOT bleed into the metrics no park effect was planted in
    k_spread = (ctx.groupby("team")["pf_k_pct_exposure"].mean().max()
                - ctx.groupby("team")["pf_k_pct_exposure"].mean().min())
    hr_spread = (ctx.groupby("team")["pf_hr_rate_exposure"].mean().max()
                 - ctx.groupby("team")["pf_hr_rate_exposure"].mean().min())
    assert hr_spread > k_spread, ("a HR-only park effect must not appear as a K% park effect",
                                  hr_spread, k_spread)


def _planted_pitcher_park_pairs(park_effect: float, n: int = 700, seed: int = 15):
    """A pitcher world where the HR park effect is REAL and KNOWN — the sibling of
    `_planted_park_pairs`, on the pitcher metric set."""
    rng = np.random.default_rng(seed)
    park = rng.choice(np.array([1.0, park_effect, 1.0 / park_effect]), n)
    talent = np.clip(rng.normal(0.030, 0.009, n), 0.005, 0.09)
    pairs = pd.DataFrame({
        "player_id": [f"q{i}" for i in range(n)],
        "level": rng.choice(["Triple-A", "Double-A"], n),
        "league": rng.choice(["IL", "EL"], n),
        "age": rng.normal(24.0, 1.5, n),
        "minor_pa": rng.integers(300, 700, n).astype(float),      # TBF, per the E7.3p alias
        "minor_hr_rate": np.clip(talent * park, 0.001, 0.15),
        "minor_k_pct": np.clip(rng.normal(0.24, 0.05, n), 0.05, 0.45),
        "minor_bb_pct": np.clip(rng.normal(0.09, 0.03, n), 0.01, 0.25),
        "minor_gb_pct": np.clip(rng.normal(0.52, 0.07, n), 0.20, 0.80),
        # ⚠️ `mlb_pa`, NOT `mlb_tbf` — E7.3p stores batters-faced under the SHARED name so the harness
        # needs no pitcher fork. This fixture originally said `mlb_tbf` and the weight-column guard
        # caught it, which is the guard doing exactly its job.
        "mlb_pa": rng.integers(300, 900, n).astype(float),
        "mlb_hr_rate": np.clip(0.8 * talent + 0.006 + rng.normal(0, 0.0022, n), 0.001, 0.09),
        "mlb_k_pct": np.clip(rng.normal(0.22, 0.04, n), 0.05, 0.45),
        "mlb_bb_pct": np.clip(rng.normal(0.088, 0.02, n), 0.01, 0.25),
        "mlb_gb_pct": np.clip(rng.normal(0.44, 0.05, n), 0.15, 0.75),
        "has_mlb_label": True,
        "debut_cohort": rng.choice([2017, 2018, 2019, 2020, 2021, 2022, 2023], n),
    })
    ctx = pd.DataFrame({"player_id": pairs["player_id"], "level": pairs["level"]})
    for m in ("k_pct", "bb_pct", "hr_rate", "gb_pct"):
        f = park if m == "hr_rate" else np.ones(n)
        ctx[f"pf_{m}_exposure"] = f
        ctx[f"pf_{m}_exposure_noloo"] = f
        ctx[f"pf_{m}_home"] = f
        ctx[f"env_{m}"] = float(pairs[f"minor_{m}"].mean())
        ctx[f"env_level_{m}"] = float(pairs[f"minor_{m}"].mean())
    return pairs, ctx


_PITCHER_SMOKE_ARMS = ("S0_baseline", "S1_park_exposure", "A_park_placebo", "A_park_noloo",
                       "I_reliability_only", "A_rel_constant")


def test_the_pitcher_ladder_recovers_a_PLANTED_park_effect_and_the_placebo_loses():
    """The load-bearing anchor test, re-run on the pitcher side. An anchor that has never been shown to
    FIRE on this side's data is an anchor that passes on nothing (NF1.7 lesson 1) — the ladder being
    shared is not by itself evidence that it still discriminates under the pitcher vocabulary."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import PITCHER_SIDE, ladder_for

    pairs, ctx = _planted_pitcher_park_pairs(1.30)
    arms = tuple(r for r in ladder_for(PITCHER_SIDE) if r.label in _PITCHER_SMOKE_ARMS)
    res = run_ladder(pairs, ctx, "hr_rate", arms, side=PITCHER_SIDE)
    lb = res.leaderboard.set_index("arm")["oos_mae"]
    assert lb["S1_park_exposure"] < lb["S0_baseline"], (
        "a REAL pitcher park effect must be recovered by dividing it out", lb.to_dict())
    assert lb["A_park_placebo"] > lb["S1_park_exposure"], (
        "the permuted-park placebo must LOSE to the real park", lb.to_dict())
    assert not res.anchors["placebo_vs_real_park"]["violated"]
    assert res.verdict == "ADD", res.reasons
    assert res.prior_scale == 4.0, "hr_rate must inherit E7.3p's pinned partial_pool@4.0"


def test_a_null_pitcher_world_does_not_produce_an_ADD():
    """The other side of the instrument on the pitcher data. With no effect planted, no ADD."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import PITCHER_SIDE, ladder_for

    pairs, ctx = _planted_pitcher_park_pairs(1.0, seed=19)
    arms = tuple(r for r in ladder_for(PITCHER_SIDE) if r.label in _PITCHER_SMOKE_ARMS)
    res = run_ladder(pairs, ctx, "hr_rate", arms, side=PITCHER_SIDE)
    assert res.verdict != "ADD", res.reasons


def test_xwoba_against_can_have_no_park_factor_and_is_never_fabricated_as_one():
    """`xwoba_against`'s minor feature IS the AAA-Statcast summary — there is no box-line home/road
    bucket to form a ratio from, so it is deliberately absent from the pitcher park-factor set. The
    thing to prove is that its absence is an honest NO-OP rather than a silently fabricated 1.0 that
    would let a park arm 'win' on a metric parks were never applied to."""
    from betting_ml.scripts.milb_mle.park_context import PITCHER_REDUCED

    assert "xwoba_against" not in PITCHER_REDUCED.pf_metrics
    assert "xwoba_against" not in PITCHER_REDUCED.rate_parts

    pairs, ctx = _planted_pitcher_park_pairs(1.30, n=200, seed=21)
    pairs["minor_xwoba_against"] = np.clip(np.random.default_rng(3).normal(0.320, 0.03, len(pairs)),
                                           0.20, 0.50)
    adj = apply_context(pairs, ctx, ContextSpec(park="exposure"), "xwoba_against")
    # no pf_xwoba_against_* column exists → factor 1.0 everywhere, the rate untouched
    np.testing.assert_allclose(adj["minor_xwoba_against_park_factor"], 1.0)
    np.testing.assert_allclose(adj["minor_xwoba_against"].to_numpy(float),
                               pairs["minor_xwoba_against"].to_numpy(float), rtol=0, atol=1e-12)
    cov = context_coverage(adj, "xwoba_against", ContextSpec(park="exposure"))
    assert float(cov["pct_rows_moved"]) == 0.0, "an absent factor must move NOTHING, not 'a little'"


def test_EVERY_rung_survives_a_metric_with_NO_context_columns_at_all():
    """🪤 THE BUG THIS EXISTS FOR — and the reason it is a whole-ladder test rather than one more branch.

    `pd.to_numeric(df.get(<missing>))` returns a **scalar** `np.float64('nan')`, not an empty Series, so
    any downstream `.where` / `.isna()` / `.fillna()` raises `AttributeError` deep inside the arm loop.
    The PARK branch was written null-safe from the start; its LEVEL-ENV and RELIABILITY-ANCHOR siblings
    were not — and pitcher `xwoba_against` legitimately has NO context columns at all, so the real run
    crashed on the fifth metric after four had already scored.

    ⭐ The lesson the test encodes: I had *predicted* the absent-column case and tested the ONE branch I
    was thinking about. A premise that applies to three branches needs a test that exercises all three,
    so this walks the ENTIRE ladder rather than naming branches — a new rung is covered automatically.
    """
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import PITCHER_SIDE, ladder_for

    pairs, ctx = _planted_pitcher_park_pairs(1.30, n=150, seed=31)
    rng = np.random.default_rng(5)
    pairs["minor_xwoba_against"] = np.clip(rng.normal(0.320, 0.03, len(pairs)), 0.20, 0.50)
    pairs["mlb_xwoba_against"] = np.clip(rng.normal(0.315, 0.03, len(pairs)), 0.20, 0.50)
    # the context has NOT ONE column for this metric — no pf_*, no env_*, no env_level_*
    assert not [c for c in ctx.columns if "xwoba_against" in c]

    baseline = pairs["minor_xwoba_against"].to_numpy(float)
    for rung in ladder_for(PITCHER_SIDE):
        adj = apply_context(pairs, ctx, rung.spec, "xwoba_against")      # must not raise
        np.testing.assert_allclose(adj["minor_xwoba_against_park_factor"], 1.0,
                                   err_msg=f"{rung.label}: fabricated a park factor")
        np.testing.assert_allclose(adj["minor_xwoba_against_env_ratio"], 1.0,
                                   err_msg=f"{rung.label}: fabricated a run-environment ratio")
        if rung.spec.reliability is None:
            # with no context to apply, a non-reliability rung must be a byte-exact no-op
            np.testing.assert_allclose(adj["minor_xwoba_against"].to_numpy(float), baseline,
                                       rtol=0, atol=1e-12, err_msg=f"{rung.label} moved the rate")
        else:
            # the reliability shrink needs only `minor_pa`, so it legitimately still applies — and with
            # no level anchor it must fall back to the population mean rather than to NaN
            assert np.isfinite(adj["minor_xwoba_against"].to_numpy(float)).all(), rung.label


def test_apply_re_emits_EVERY_pitcher_metric_the_board_reads():
    """🪤 The pitcher instance of the partial-write footgun. E8.0 reads `mle_p_gb_pct`, `mle_p_bb_pct`
    AND `mle_p_k_pct` from ONE wide table, so a re-emission carrying only the winners would silently
    delete two of the board's three pitcher inputs and quietly renormalise every arm's composite."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import (
        PITCHER_SIDE,
        build_applied_projections,
        ladder_for,
    )

    pairs, ctx = _planted_pitcher_park_pairs(1.30, n=600, seed=27)
    arms = tuple(r for r in ladder_for(PITCHER_SIDE) if r.label in _PITCHER_SMOKE_ARMS)
    results = {m: run_ladder(pairs, ctx, m, arms, side=PITCHER_SIDE)
               for m in ("hr_rate", "k_pct", "gb_pct", "bb_pct")}
    assert results["hr_rate"].verdict == "ADD", results["hr_rate"].reasons

    applied: dict = {}
    wide, changed = build_applied_projections(pairs, ctx, results, applied, PITCHER_SIDE)
    assert changed
    for m in PITCHER_SIDE.board_metrics:
        assert f"mle_{m}" in wide.columns and wide[f"mle_{m}"].notna().any(), m
    assert set(wide["player_type"].unique()) == {"pitcher"}
    assert set(wide["model_version"].unique()) == {"milb_mle_pitcher_v2_parkctx"}
    # a metric that did NOT clear is re-emitted under the byte-exact incumbent, with provenance saying so
    for m, r in results.items():
        if r.verdict != "ADD":
            assert set(wide[f"{m}_context_spec"].unique()) == {"baseline"}, m


def test_the_e7_3p_winner_prior_scales_are_pinned_literals_not_recomputed():
    """Same discipline as the batter map: the reference the pitcher ladder measures against must not be
    rebuilt from the code the slice changes (NF1.8)."""
    import inspect

    import betting_ml.scripts.milb_mle.run_e7_12_slice1 as mod
    src = inspect.getsource(mod)
    assert '"k_pct": 4.0, "bb_pct": 4.0, "hr_rate": 4.0, "gb_pct": 2.0, "xwoba_against": 2.0' in src


def test_both_sides_run_the_SAME_ladder_with_the_same_anchors():
    """The claim 'harness reused, not forked' has to be mechanically true, or the two sides drift and a
    cross-side comparison stops meaning anything."""
    from dataclasses import replace as _replace

    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import (
        BATTER_SIDE,
        PITCHER_SIDE,
        ladder_for,
    )

    b, p = ladder_for(BATTER_SIDE), ladder_for(PITCHER_SIDE)
    assert [r.label for r in b] == [r.label for r in p]
    assert [r.kind for r in b] == [r.kind for r in p]
    for rb, rp in zip(b, p):
        assert _replace(rb.spec, weight_col=None) == _replace(rp.spec, weight_col=None), rb.label
    # the three degenerate anchors must survive the port
    assert {r.label for r in p if r.kind == "anchor"} == {
        "A_park_placebo", "A_park_noloo", "A_rel_constant"}


def test_the_label_weight_column_is_mlb_pa_on_BOTH_sides_because_E7_3p_shares_the_name():
    """⚠️ E7.3p stores the pitcher's batters-faced under the SHARED `mlb_pa`/`minor_pa` names, precisely
    so the harness needs no pitcher fork. A plausible-looking `mlb_tbf` does not exist in the pairs."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import BATTER_SIDE, PITCHER_SIDE

    assert BATTER_SIDE.reduced.label_weight_col == "mlb_pa"
    assert PITCHER_SIDE.reduced.label_weight_col == "mlb_pa"


def test_a_BAD_weight_column_RAISES_instead_of_reaching_the_report_as_a_RESULT():
    """🪤 THE BUG THIS GUARD EXISTS FOR — found on the pitcher port, where the label exposure is stored
    under the shared name `mlb_pa` and a plausible-looking `mlb_tbf` does not exist.

    Neither failure mode announces itself, and they fail DIFFERENTLY:

      (a) column ABSENT → `_weights` throws inside the fold loop, whose `except` exists precisely so a
          degenerate fold cannot kill the sweep → every fold fails → the arm scores NaN and VANISHES
          from the leaderboard and the deflation count. Two pre-registered arms silently stop existing.
      (b) column PRESENT but all-NaN → `_weights` median-fills, the all-NaN median falls back to 1.0 →
          every weight is exactly 1 → the arm is BYTE-IDENTICAL to the baseline and is reported as
          "label weighting is a clean null" for a mechanism that was never applied.

    (b) is the worse one: a missing arm is an absence, a byte-exact no-op is a **manufactured confident
    negative**. Both halves are asserted against the real mechanism, not against a described one.
    """
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import BATTER_SIDE, ladder_for

    base, ctx = _planted_park_pairs(1.25, n=200, seed=8)
    arms = tuple(r for r in ladder_for(BATTER_SIDE)
                 if r.label in ("S0_baseline", "I_labelweight_only"))

    # (b) the byte-exact no-op is REAL — prove the fit truly cannot tell an all-NaN weight from none
    allnan = base.copy()
    allnan["mlb_pa"] = np.nan
    lab = build_target(allnan, MleConfig(metric="iso"))
    lab = lab[lab["has_target"]]
    a, _ = PartialPoolProjector(prior_scale=2.0).fit(lab).predict(lab)
    b, _ = PartialPoolProjector(prior_scale=2.0, weight_col="mlb_pa").fit(lab).predict(lab)
    np.testing.assert_allclose(a, b, rtol=0, atol=1e-12,
                               err_msg="if an all-NaN weight column ever stops no-opping, this guard "
                                       "is guarding nothing")
    with pytest.raises(AssertionError, match="NO positive values"):
        run_ladder(allnan, ctx, "iso", arms)

    # (a) absent → the arm would score NaN and vanish; the ladder must refuse instead
    with pytest.raises(AssertionError, match="ABSENT from the pairs table"):
        run_ladder(base.drop(columns=["mlb_pa"]), ctx, "iso", arms)


def test_the_pitcher_directional_falsification_is_the_ball_in_play_metrics():
    """Parks move batted balls, not the strike zone — the same physical claim as the batter side, which
    is what makes the pitcher run an independent REPLICATION rather than a restatement. Pinned so the
    split cannot be quietly rewritten after seeing the result."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import PITCHER_SIDE

    assert PITCHER_SIDE.park_sensitive == ("hr_rate", "gb_pct")
    assert PITCHER_SIDE.park_insensitive == ("k_pct", "bb_pct")
    assert not set(PITCHER_SIDE.park_sensitive) & set(PITCHER_SIDE.park_insensitive)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 11. BH-FDR AS AN ENFORCED GATE, and the POST-HOC ablation-down arms
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_bh_fdr_is_ENFORCED_not_merely_reported():
    """🪤 THE DEFECT THIS CLOSES, AND WHY IT STAYED HIDDEN FOR A WHOLE RELEASE.

    `bh_fdr` was computed in `main()` and written into the report, but `build_applied_projections` keys
    off `verdict == "ADD"` — which the per-metric fold-win-rate bar sets on its own. So a metric could
    FAIL the family-wise correction and still be published. It was invisible on the batter run because
    all four metrics passed FDR, so enforcing it would have changed nothing; it went live on the pitcher
    run, where `k_pct` cleared 73% of folds at p=0.113 with FDR=False.

    ⭐ A computed-but-unconsumed statistic is the quiet cousin of the silent-empty class: the number is
    right, it is printed, and nothing reads it. This asserts the wiring, which is the part that broke —
    `bh_fdr`'s arithmetic already has its own test.
    """
    import inspect

    import betting_ml.scripts.milb_mle.run_e7_12_slice1 as mod
    src = inspect.getsource(mod.main)
    fdr_at = src.index("fdr = bh_fdr(pvals)")
    # the CALL SITE, not a mention — the explanatory comment names the function too
    apply_at = src.index("build_applied_projections(pairs")
    assert fdr_at < apply_at, "FDR must be resolved BEFORE the emission decides what to write"
    gate = src[fdr_at:apply_at]
    assert 'r.verdict = "DROP"' in gate and "fdr.get(m) is False" in gate, (
        "an ADD that fails BH-FDR must be downgraded before it can be published")


def test_an_ADD_that_fails_BH_FDR_is_downgraded_and_re_emitted_as_the_incumbent():
    """End-to-end on the decision, not the string: a metric whose winner fails the family correction
    must come out of `build_applied_projections` byte-exact as the incumbent."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import (
        BATTER_SIDE,
        build_applied_projections,
        ladder_for,
    )

    pairs, ctx = _planted_park_pairs(1.25, n=500, seed=12)
    arms = tuple(r for r in ladder_for(BATTER_SIDE)
                 if r.label in ("S0_baseline", "S1_park_exposure", "A_park_placebo", "A_park_noloo"))
    res = run_ladder(pairs, ctx, "iso", arms)
    assert res.verdict == "ADD", res.reasons

    # simulate what main() does when BH rejects this metric
    res.verdict, res.winner = "DROP", "S0_baseline"
    applied: dict = {}
    wide, changed = build_applied_projections(pairs, ctx, {"iso": res}, applied, BATTER_SIDE)
    assert not changed and applied == {}, "an FDR-downgraded metric must not be counted as applied"
    assert set(wide["iso_context_spec"].unique()) == {"baseline"}

    incumbent = emit_projections(
        build_target(pairs, MleConfig(metric="iso")),
        lambda: PartialPoolProjector(prior_scale=res.prior_scale), MleConfig(metric="iso"))
    merged = wide[["player_id", "level", "mle_iso"]].merge(
        incumbent[["player_id", "level", "mle_iso"]], on=["player_id", "level"],
        suffixes=("_new", "_old"))
    assert len(merged) == len(incumbent) > 0
    np.testing.assert_allclose(merged["mle_iso_new"], merged["mle_iso_old"], rtol=0, atol=1e-12)


def test_the_posthoc_arms_are_OFF_by_default_so_the_published_ladder_is_reproducible():
    """The opt-in IS the honesty mechanism. The batter slice is already PUBLISHED against the
    pre-registered ladder; if post-hoc arms leaked into the default field, that run would silently stop
    being reproducible and a reader could not tell which arms were pre-registered."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import (
        LADDER,
        POSTHOC_RUNGS,
        BATTER_SIDE,
        PITCHER_SIDE,
        ladder_for,
    )

    for side in (BATTER_SIDE, PITCHER_SIDE):
        assert ladder_for(side) == tuple(LADDER), f"{side.player_type}: default field must be pristine"
        with_ph = ladder_for(side, include_posthoc=True)
        assert len(with_ph) == len(LADDER) + len(POSTHOC_RUNGS)
        assert [r.label for r in with_ph[:len(LADDER)]] == [r.label for r in LADDER]
    # every post-hoc arm must be labelled as such, and must be a strict SUBSET of the winning stack's
    # mechanisms (an ablation-DOWN, never a new mechanism smuggled in after seeing results)
    s5 = next(r for r in LADDER if r.label == "S5_full_labelweight").spec
    for r in POSTHOC_RUNGS:
        assert r.kind == "posthoc", r.label
        assert r.spec.park == "off", f"{r.label}: a post-hoc arm must not introduce a park mode"
        assert not r.spec.level_env or s5.level_env
        assert r.spec.reliability is None or r.spec.reliability == s5.reliability
        assert r.spec.weight_col == s5.weight_col
        assert r.spec != s5, f"{r.label}: identical to the pre-registered winner, not an ablation"


def test_a_posthoc_arm_is_selectable_and_counted_in_the_deflation_field():
    """A post-hoc arm that could win but was excluded from the deflation would be free search — the
    whole point of admitting them explicitly is that a wider field costs what a wider field costs."""
    from betting_ml.scripts.milb_mle.run_e7_12_slice1 import PITCHER_SIDE, ladder_for

    pairs, ctx = _planted_pitcher_park_pairs(1.30, n=500, seed=33)
    arms = ladder_for(PITCHER_SIDE, include_posthoc=True)
    res = run_ladder(pairs, ctx, "hr_rate", arms, side=PITCHER_SIDE)
    lb = res.leaderboard.set_index("arm")
    for r in (x for x in arms if x.kind == "posthoc"):
        assert r.label in lb.index, f"{r.label} was not scored"
        assert bool(lb.loc[r.label, "selectable"]), f"{r.label} must be able to win"
    n_elig = res.deflation.get("n_eligible")
    if n_elig is not None:
        assert int(n_elig) >= len([x for x in arms if x.kind == "posthoc"]), (
            "post-hoc arms must enter the eligible set the deflation is computed over")
