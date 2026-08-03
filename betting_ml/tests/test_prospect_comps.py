"""E7.13 — the PECOTA-style prospect COMP engine (`prospect_board/prospect_comps.py`).

Fast-gate: pure pandas/numpy, no IO, no `pipeline` import.

Every test here pins a rule whose violation produces output that looks *better* than the honest
version — a rosier median, a tighter band, a closer comp — and would therefore ship unnoticed:

  * the busts staying in the pool (a survivor-only pool inflates every median);
  * the retained board's `level` staying OUT of the feature set (it is a near-perfect one-sided
    tell that a player never debuted — an engine using it validates beautifully and is useless);
  * the component-coverage floor (without it two players sharing only an FV grade score at
    distance EXACTLY 0.0 and sort to the top of the comp list);
  * person-deduplication (the pool is one row per board-season, so one man's career could carry
    7 of 15 votes in a distribution read as an average over 15 careers);
  * un-matured comps staying out (an unfinished career reads as a bust).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.prospect_board.prospect_comps import (
    COMPONENT_FEATURES,
    COMP_LEVEL_RANK,
    COMP_RANK_WEIGHT,
    DEFAULT_K,
    FEATURE_WEIGHTS,
    LEAKED_COLUMNS,
    MIN_COMPONENT_COVERAGE,
    MIN_POOL_BUST_SHARE,
    OUTCOME_TIERS,
    SCOUTING_ONLY_FEATURES,
    CompConfig,
    CompsError,
    assert_no_leaked_features,
    attach_comp_ranking,
    attach_comps,
    build_pool,
    build_query_profile,
    calibrate_quality_cuts,
    collapse_pairs_to_career_line,
    comp_distribution,
    comp_note,
    distance_matrix,
    find_comps,
    fit_pool_stats,
    format_comp_names,
    level_from_token,
    matured_pool,
    outcome_tier,
    pitcher_role,
    position_group,
    validate_pool,
    weighted_quantile,
)

_RNG = np.random.default_rng(20260801)


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────

def _cohort(n: int = 400, player_type: str = "batter", seasons=(2018, 2019, 2020),
            bust_share: float = 0.6, horizon: int = 3) -> pd.DataFrame:
    """A synthetic E7.8-shaped cohort. Outcome is deliberately CORRELATED with the component line
    so a working engine can be distinguished from a broken one (the NF1.7 lesson: prove the
    machinery discriminates before trusting any null it produces)."""
    k = _RNG.normal(0.22, 0.05, n).clip(0.05, 0.45)
    quality = (0.30 - k) * 10                             # low K% = good
    # Promote the top (1 − bust_share) by a noisy quality score: an EXACT bust share (so the
    # survivorship guard is tested at a known level) with the outcome genuinely correlated with the
    # component line (so a working engine is distinguishable from a broken one).
    score = quality + _RNG.normal(0, 0.5, n)
    debuted = score > np.quantile(score, bust_share)
    fp = np.where(debuted, np.clip(200 + 400 * quality + _RNG.normal(0, 90, n), 1, None), 0.0)
    pos = _RNG.choice(["SS", "2B", "CF", "1B", "C"] if player_type == "batter"
                      else ["SP", "RHP", "MIRP"], n)
    return pd.DataFrame({
        "player_key": [f"p{i:04d}" for i in range(n)],
        "player_name": [f"Player {i:04d}" for i in range(n)],
        "player_type": player_type,
        "board_season": _RNG.choice(list(seasons), n),
        "horizon_seasons": horizon,
        "position": pos,
        "top_level_pre_board": _RNG.choice(["Single-A", "High-A", "Double-A", "Triple-A"], n),
        "level": np.where(debuted, "MLB", "AA"),          # the CONTAMINATED retained-board column
        "age": _RNG.normal(22, 1.6, n),
        "fv": _RNG.choice([35.0, 40.0, 45.0, 50.0, 55.0], n),
        "pro_experience_years": _RNG.integers(0, 6, n),
        "minor_pa": _RNG.integers(120, 1500, n).astype(float),
        "minor_k_pct": k,
        "minor_bb_pct": _RNG.normal(0.09, 0.02, n).clip(0.02, 0.20),
        "minor_iso": _RNG.normal(0.16, 0.05, n).clip(0.02, 0.40),
        "minor_gb_pct": _RNG.normal(0.45, 0.07, n).clip(0.2, 0.7),
        "minor_start_share": _RNG.random(n),
        "debuted": debuted,
        "fantasy_points": fp,
    })


@pytest.fixture()
def pool_bat() -> pd.DataFrame:
    return build_pool(_cohort(), player_type="batter")


@pytest.fixture()
def stats_bat(pool_bat):
    return fit_pool_stats(pool_bat, player_type="batter")


# ── 1. Leakage ───────────────────────────────────────────────────────────────────────────────

class TestLeakageGuards:
    """The retained board's `level` is the player's CURRENT level. See prospect_comps §(2)."""

    @pytest.mark.parametrize("col", ["level", "in_majors", "debuted", "fantasy_points",
                                     "mlb_pa", "exposure", "outcome_tier"])
    def test_leaked_column_raises(self, col):
        with pytest.raises(CompsError, match="leaked feature"):
            assert_no_leaked_features(["age", col])

    def test_shipped_weights_are_clean(self):
        for ptype, w in FEATURE_WEIGHTS.items():
            assert_no_leaked_features(w)                       # must not raise
            assert not set(w) & LEAKED_COLUMNS, ptype

    def test_level_from_token_refuses_mlb(self):
        """A player already in the majors has no MINOR level. Ranking him above Triple-A would
        smuggle the outcome in through the level feature — the exact leak, one column over."""
        assert level_from_token("MLB") is None
        assert level_from_token("AAA") == "triple-a"
        assert level_from_token("A+") == "high-a"
        assert level_from_token("DSL") == "complex"

    def test_engine_never_reads_the_contaminated_level(self, pool_bat, stats_bat):
        """The synthetic pool sets `level='MLB'` iff the player debuted — a perfect leak. If the
        engine touched it, comps would separate on outcome; the feature set must not contain it."""
        assert "level" not in stats_bat.features
        assert pool_bat["level"].nunique() == 2                # the fixture really is contaminated
        assert (pool_bat.groupby("level")["debuted"].nunique() == 1).all()

    def test_weights_sum_to_one_and_exclude_no_signal_metrics(self):
        for ptype, w in FEATURE_WEIGHTS.items():
            assert sum(w.values()) == pytest.approx(1.0)
        # E7.3 NO-SIGNAL metrics must be ABSENT, not down-weighted (board_assembly's rule).
        assert "minor_woba" not in FEATURE_WEIGHTS["batter"]
        assert "minor_hr_rate" not in FEATURE_WEIGHTS["pitcher"]
        assert "minor_xwoba_against" not in FEATURE_WEIGHTS["pitcher"]

    def test_fv_split_matches_the_e7_8_verdict(self):
        """Pitchers 0.70 / batters 0.35 — `board_assembly.FV_WEIGHT_BY_TYPE`, unchanged. A drift
        here would silently re-decide 'when do we trust the scouts' in a second place."""
        assert FEATURE_WEIGHTS["pitcher"]["fv"] == pytest.approx(0.70)
        assert FEATURE_WEIGHTS["batter"]["fv"] == pytest.approx(0.35)


# ── 2. Survivorship ──────────────────────────────────────────────────────────────────────────

class TestSurvivorship:
    """The #1 way a comp engine ships broken: a pool of players who made it."""

    def test_pool_with_the_busts_removed_hard_fails(self, pool_bat):
        survivors = pool_bat.loc[pool_bat["debuted"]].reset_index(drop=True)
        with pytest.raises(CompsError, match="non-debut share"):
            validate_pool(survivors)

    def test_honest_pool_passes_and_reports_its_bust_share(self, pool_bat):
        rep = validate_pool(pool_bat)
        assert rep["bust_share"] >= MIN_POOL_BUST_SHARE
        assert rep["n_pool"] == len(pool_bat)

    def test_survivor_pool_inflates_the_median_it_would_have_reported(self, pool_bat, stats_bat):
        """The reason the guard is a HARD FAIL and not a warning: measured on the same query, a
        survivor-only pool reports a materially higher median with no other visible difference."""
        query = pool_bat.head(30)
        honest, _ = find_comps(query, pool_bat, stats_bat, CompConfig())
        surv = pool_bat.loc[pool_bat["debuted"]].reset_index(drop=True)
        rosy, _ = find_comps(query, surv, fit_pool_stats(surv, player_type="batter"), CompConfig())
        assert rosy["comp_fp_median"].median() > honest["comp_fp_median"].median()
        assert rosy["comp_bust_rate"].mean() < honest["comp_bust_rate"].mean()


# ── 3. Maturity (distinct from leakage) ──────────────────────────────────────────────────────

class TestMaturity:
    def test_unmatured_comps_are_excluded(self):
        pool = build_pool(_cohort(seasons=(2018, 2022), horizon=3), player_type="batter")
        kept = matured_pool(pool, as_of_season=2023)
        # 2018 + 3 = 2021 < 2023 ✅ ; 2022 + 3 = 2025 ≥ 2023 ❌
        assert set(kept["board_season"].dropna().unique()) == {2018}

    def test_no_matured_comps_raises_rather_than_returning_an_empty_board(self):
        pool = build_pool(_cohort(seasons=(2024,), horizon=3), player_type="batter")
        with pytest.raises(CompsError, match="matured"):
            matured_pool(pool, as_of_season=2025)


# ── 4. The component-coverage floor ──────────────────────────────────────────────────────────

class TestComponentCoverageFloor:
    """Without this floor two players sharing only an FV grade score at distance EXACTLY 0.0."""

    def test_fv_only_pair_is_distance_zero_without_the_floor(self):
        """Reproduces the live defect on a 2-row pool: an FV-only match is a PERFECT match."""
        feats = ("minor_k_pct", "fv")
        w = np.array([0.3, 0.7])
        q = np.array([[np.nan, 0.0]])
        p = np.array([[np.nan, 0.0]])
        d, cov = distance_matrix(q, p, w)
        assert d[0, 0] == pytest.approx(0.0)
        assert cov[0, 0] == pytest.approx(0.7)      # clears a 0.5 TOTAL-weight floor on FV alone

    def test_floor_rejects_the_grade_only_pair(self, stats_bat, pool_bat):
        blind = pool_bat.copy()
        for m in COMPONENT_FEATURES["batter"]:
            blind[m] = np.nan
        cfg = CompConfig(min_component_coverage=MIN_COMPONENT_COVERAGE)
        summary, _ = find_comps(pool_bat.head(5), blind, stats_bat, cfg)
        assert (summary["comp_k"] == 0).all()

    def test_floor_disabled_admits_them(self, stats_bat, pool_bat):
        blind = pool_bat.copy()
        for m in COMPONENT_FEATURES["batter"]:
            blind[m] = np.nan
        summary, _ = find_comps(pool_bat.head(5), blind, stats_bat,
                                CompConfig(min_component_coverage=0.0))
        assert (summary["comp_k"] > 0).all()          # proves the floor is what rejects them


# ── 5. Person deduplication ──────────────────────────────────────────────────────────────────

class TestPersonDedup:
    def test_one_person_cannot_carry_multiple_votes(self, pool_bat, stats_bat):
        """The pool is one row per (board season, player); a duplicated person would let one
        career dominate the distribution the board reads as an average over k careers."""
        dup = pd.concat([pool_bat] * 4, ignore_index=True)      # every person, 4 board seasons
        summary, detail = find_comps(pool_bat.head(20), dup, stats_bat, CompConfig(k=10))
        per_query = detail.groupby("query_index")["comp_name"].agg(["size", "nunique"])
        assert (per_query["size"] == per_query["nunique"]).all()

    def test_query_is_purged_from_its_own_comp_set(self, pool_bat, stats_bat):
        summary, detail = find_comps(pool_bat.head(20), pool_bat, stats_bat, CompConfig())
        names = pool_bat["player_name"].to_numpy()
        for qi, grp in detail.groupby("query_index"):
            assert names[qi] not in set(grp["comp_name"])


# ── 6. Distance mechanics ────────────────────────────────────────────────────────────────────

class TestDistance:
    def test_identical_rows_are_distance_zero_and_full_coverage(self):
        z = np.array([[0.5, -1.0, 0.2]])
        w = np.array([0.5, 0.3, 0.2])
        d, cov = distance_matrix(z, z, w)
        assert d[0, 0] == pytest.approx(0.0)
        assert cov[0, 0] == pytest.approx(1.0)

    def test_missing_feature_costs_coverage_not_a_fabricated_zero(self):
        """A missing feature must not be imputed to the pool centre and then scored as a match —
        that is the 'forbidden fabricated neutral' (E7.12-S6)."""
        w = np.array([0.5, 0.5])
        q = np.array([[1.0, np.nan]])
        p = np.array([[1.0, 3.0]])
        d, cov = distance_matrix(q, p, w)
        assert cov[0, 0] == pytest.approx(0.5)
        assert d[0, 0] == pytest.approx(0.0)   # scored on the ONE feature they share, and said so

    def test_distance_is_monotone_in_the_gap(self):
        w = np.array([1.0])
        p = np.array([[0.0], [1.0], [2.0]])
        d, _ = distance_matrix(np.array([[0.0]]), p, w)
        assert d[0, 0] < d[0, 1] < d[0, 2]

    def test_unstandardized_features_would_let_one_unit_dominate(self, pool_bat, stats_bat):
        """The reason robust-z comes first: ISO ranges ~0.3 and age ~14, so a raw distance trades
        them at ~45:1 by accident of units."""
        assert stats_bat.scale["minor_iso"] < stats_bat.scale["age_vs_level"]

    def test_mahalanobis_arm_runs_and_orders_sensibly(self, pool_bat, stats_bat):
        s, _ = find_comps(pool_bat.head(10), pool_bat, stats_bat,
                          CompConfig(metric="mahalanobis", name="maha"))
        assert (s["comp_k"] > 0).all()
        assert s["comp_mean_distance"].between(0, 1).all()

    def test_unknown_metric_raises(self, pool_bat, stats_bat):
        with pytest.raises(CompsError, match="unknown metric"):
            find_comps(pool_bat.head(2), pool_bat, stats_bat, CompConfig(metric="cosine"))


# ── 7. The engine actually finds similar players (prove it discriminates) ────────────────────

class TestEngineDiscriminates:
    """NF1.7 lesson 1: prove the machinery works on a planted signal BEFORE trusting any output."""

    def test_nearest_beats_random_at_recovering_the_outcome(self, pool_bat, stats_bat):
        query = pool_bat.head(120)
        near, _ = find_comps(query, pool_bat, stats_bat, CompConfig(name="near"))
        rand, _ = find_comps(query, pool_bat, stats_bat,
                             CompConfig(neighbour_rule="random", name="rand", seed=7))
        truth = query["fantasy_points"].to_numpy(float)
        err_near = np.nanmean(np.abs(near["comp_fp_median"].to_numpy(float) - truth))
        err_rand = np.nanmean(np.abs(rand["comp_fp_median"].to_numpy(float) - truth))
        assert err_near < err_rand, (err_near, err_rand)

    def test_oracle_neighbours_are_the_floor(self, pool_bat, stats_bat):
        """A peeking arm at MATCHED family/k/eligible-set (NF1.7(b)/NF1.9(f)). Nothing may beat it;
        a real arm that does means the metric is inverted, not that the arm is good."""
        query = pool_bat.head(120).copy()
        oracle, _ = find_comps(query, pool_bat, stats_bat,
                               CompConfig(neighbour_rule="oracle", name="oracle"),
                               query_outcome_col="fantasy_points")
        near, _ = find_comps(query, pool_bat, stats_bat, CompConfig(name="near"))
        truth = query["fantasy_points"].to_numpy(float)
        e_or = np.nanmean(np.abs(oracle["comp_fp_median"].to_numpy(float) - truth))
        e_near = np.nanmean(np.abs(near["comp_fp_median"].to_numpy(float) - truth))
        assert e_or < e_near


# ── 8. Coverage honesty ──────────────────────────────────────────────────────────────────────

class TestCoverageHonesty:
    def test_thin_row_widens_its_band(self):
        fp = np.array([0.0, 0.0, 50.0, 300.0, 600.0])
        deb = np.array([False, False, True, True, True])
        tiers = ["never_reached", "never_reached", "fringe", "regular", "impact"]
        d = np.linspace(0.05, 0.3, 5)
        wide = comp_distribution(fp, deb, tiers, d, thin=True)
        tight = comp_distribution(fp, deb, tiers, d, thin=False)
        assert wide["comp_band_quantiles"] == "p05-p90"
        assert tight["comp_band_quantiles"] == "p10-p90"
        assert wide["comp_band_lo"] <= tight["comp_band_lo"]

    def test_note_leads_with_the_bust_count(self):
        d = {"comp_k": 15, "comp_n_never_reached": 9, "comp_n_fringe": 3, "comp_n_regular": 2,
             "comp_n_impact": 1, "comp_band_lo": 0.0, "comp_band_hi": 291.0,
             "comp_fp_median": 12.0, "comp_band_quantiles": "p10-p90"}
        note = comp_note(d, "fair")
        assert note.startswith("9 of 15 comps never reached MLB")
        assert "THIN" not in note
        assert "THIN" in comp_note(d, "thin")

    def test_scouting_only_note_says_so(self):
        d = {"comp_k": 15, "comp_n_never_reached": 12, "comp_band_lo": 0.0, "comp_band_hi": 40.0,
             "comp_fp_median": 0.0, "comp_band_quantiles": "p05-p90"}
        assert "GRADE-AND-AGE" in comp_note(d, "thin", basis="scouting_only")

    def test_no_comps_is_stated_not_faked(self):
        assert comp_note({"comp_k": 0}, "none").startswith("No comparable")

    def test_comp_names_carry_their_distances(self):
        s = format_comp_names(["A B", "C D", "E F", "G H"], [0.02, 0.031, 0.2, 0.4], n=3)
        assert s == "A B (0.02), C D (0.03), E F (0.20)"

    def test_quality_cuts_are_calibrated_not_invented(self, pool_bat, stats_bat):
        lo, hi = calibrate_quality_cuts(pool_bat, stats_bat, CompConfig(), sample=150)
        assert 0 < lo < hi < 1

    def test_scouting_only_can_never_be_strong(self):
        """A grade-and-age match is never 'strong' however close the two numbers happen to be."""
        pool = build_pool(_cohort(n=300), player_type="batter")
        # the fallback is SYMMETRIC by design — a record-less prospect is comped only against pool
        # rows that are also record-less, so both sides are known by grade and age alone
        for m in COMPONENT_FEATURES["batter"]:
            pool.loc[pool.index[150:], m] = np.nan
        recordless = pool.head(40).copy()
        for m in COMPONENT_FEATURES["batter"]:
            recordless[m] = np.nan
        recordless["minor_pa"] = 0.0
        out, detail, rep = attach_comps(recordless, pool, player_type="batter",
                                        as_of_season=2026)
        got = out.loc[out["comp_k"].fillna(0) > 0]
        assert not got.empty
        assert set(got["comp_basis"]) == {"scouting_only"}
        assert set(got["comp_quality"]) == {"thin"}
        assert set(SCOUTING_ONLY_FEATURES) == {"age", "fv"}


# ── 9. Taxonomy ──────────────────────────────────────────────────────────────────────────────

class TestTaxonomy:
    @pytest.mark.parametrize("pos,expected", [
        ("SS", "IF_MID"), ("2B", "IF_MID"), ("3B", "IF_CORNER"), ("1B/3B", "IF_CORNER"),
        ("CF", "OF"), ("LF", "OF"), ("C", "C"), ("C/1B", "C"),
    ])
    def test_batter_groups(self, pos, expected):
        assert position_group(pos, "batter") == expected

    def test_unresolved_arm_resolves_by_measured_start_share(self):
        """The 2018–2020 boards say RHP/LHP where the 2026 board says SP/SIRP/MIRP. A literal
        position filter would fail to match ACROSS ERAS; role comes from the workload record."""
        assert pitcher_role("RHP", 0.9) == "SP"
        assert pitcher_role("RHP", 0.1) == "RP"
        assert pitcher_role("LHP", None) == "SP"           # modal prospect arm
        assert pitcher_role("MIRP", 0.9) == "RP"           # an explicit token wins over workload

    def test_sirp_is_grouped_with_starters(self):
        """SIRP arms START in the minors — every component feature here is measured over that
        workload. Grouping them with one-inning arms would comp starter rates to reliever rates."""
        assert pitcher_role("SIRP", 0.0) == "SP"

    def test_player_type_overrides_an_ambiguous_token(self):
        assert position_group("TWP", "pitcher") in {"SP", "RP"}
        assert position_group("4C", "batter") == "IF_CORNER"

    def test_level_ranks_are_ordered(self):
        r = COMP_LEVEL_RANK
        assert r["complex"] < r["single-a"] < r["high-a"] < r["double-a"] < r["triple-a"]


# ── 10. Outcome tiers ────────────────────────────────────────────────────────────────────────

class TestOutcomeTiers:
    def test_non_debut_is_its_own_tier(self):
        assert outcome_tier(0.0, False, (100.0, 400.0)) == "never_reached"
        assert outcome_tier(900.0, False, (100.0, 400.0)) == "never_reached"

    @pytest.mark.parametrize("fp,expected", [(50, "fringe"), (250, "regular"), (900, "impact")])
    def test_debuted_tiers_split_at_the_pool_cuts(self, fp, expected):
        assert outcome_tier(fp, True, (100.0, 400.0)) == expected

    def test_tiers_are_exhaustive(self):
        cuts = (100.0, 400.0)
        seen = {outcome_tier(fp, d, cuts) for fp in (0, 50, 250, 900) for d in (True, False)}
        assert seen <= set(OUTCOME_TIERS)

    def test_tier_cuts_come_from_the_debuted_subpopulation(self, pool_bat):
        st = fit_pool_stats(pool_bat, player_type="batter")
        deb = pool_bat.loc[pool_bat["debuted"], "fantasy_points"]
        assert st.tier_cuts[0] == pytest.approx(float(deb.quantile(0.50)))
        assert st.tier_cuts[1] == pytest.approx(float(deb.quantile(0.85)))


# ── 11. Weighted quantiles ───────────────────────────────────────────────────────────────────

class TestWeightedQuantile:
    def test_equal_weights_match_numpy(self):
        v = _RNG.normal(size=200)
        got = weighted_quantile(v, np.ones_like(v), [0.1, 0.5, 0.9])
        exp = np.quantile(v, [0.1, 0.5, 0.9], method="averaged_inverted_cdf")
        assert np.allclose(got, exp, atol=0.1)

    def test_weight_shifts_the_median_toward_the_weighted_mass(self):
        v = np.array([0.0, 100.0])
        assert weighted_quantile(v, np.array([9.0, 1.0]), 0.5) < 50
        assert weighted_quantile(v, np.array([1.0, 9.0]), 0.5) > 50

    def test_all_zero_weight_returns_nan_not_a_number(self):
        assert np.isnan(weighted_quantile(np.array([1.0, 2.0]), np.zeros(2), 0.5))


# ── 12. The query side is built in the POOL's units ──────────────────────────────────────────

class TestQuerySideUnits:
    """The apples-to-oranges trap: the pool's line is career-to-date across ALL levels, the E7.3
    pairs table's is career-at-ONE-level. Mixing them is a systematic bias wearing similarity's
    clothes."""

    def _pairs(self) -> pd.DataFrame:
        return pd.DataFrame({
            "player_id": ["1", "1", "2"],
            "level": ["Double-A", "Triple-A", "High-A"],
            "first_minor_season": [2022, 2024, 2023],
            "last_minor_season": [2023, 2025, 2025],
            "bat_plate_appearances": [400.0, 200.0, 500.0],
            "bat_at_bats": [360.0, 180.0, 450.0],
            "bat_hits": [90.0, 54.0, 120.0],
            "bat_doubles": [20.0, 10.0, 25.0],
            "bat_triples": [2.0, 1.0, 3.0],
            "bat_home_runs": [10.0, 8.0, 12.0],
            "bat_walks": [40.0, 18.0, 45.0],
            "bat_intentional_walks": [0.0, 0.0, 0.0],
            "bat_hit_by_pitch": [0.0, 2.0, 5.0],
            "bat_sac_flies": [0.0, 0.0, 0.0],
            "bat_strike_outs": [80.0, 50.0, 110.0],
            "bat_total_bases": [144.0, 90.0, 187.0],
        })

    def test_levels_are_summed_not_picked(self):
        car = collapse_pairs_to_career_line(self._pairs(), player_type="batter")
        p1 = car.loc[car["player_id"] == "1"].iloc[0]
        assert p1["minor_pa"] == 600.0                        # 400 + 200, not either alone
        assert p1["minor_k_pct"] == pytest.approx(130.0 / 600.0)

    def test_level_is_the_most_recent_season_not_the_highest(self):
        car = collapse_pairs_to_career_line(self._pairs(), player_type="batter")
        assert car.loc[car["player_id"] == "1", "comp_level"].iloc[0] == "triple-a"
        assert car.loc[car["player_id"] == "2", "comp_level"].iloc[0] == "high-a"

    def test_query_profile_prefers_the_game_log_level_over_a_board_saying_mlb(self):
        board = pd.DataFrame({"mlbam_id": [1.0], "player_name": ["X"], "position": ["SS"],
                              "level": ["MLB"], "age": [22.0], "fv": [50.0]})
        car = collapse_pairs_to_career_line(self._pairs(), player_type="batter")
        q = build_query_profile(board, car, player_type="batter", as_of_season=2026)
        assert q["comp_level"].iloc[0] == "triple-a"
        assert q["level_rank"].iloc[0] == COMP_LEVEL_RANK["triple-a"]
        assert q["pro_experience_years"].iloc[0] == 2026 - 2022


# ── 13. End-to-end ───────────────────────────────────────────────────────────────────────────

class TestAttachComps:
    def test_board_gains_the_comp_columns_and_keeps_its_own(self, pool_bat):
        board = pool_bat.head(40).copy()
        out, detail, rep = attach_comps(board, pool_bat, player_type="batter", as_of_season=2026)
        assert len(out) == len(board)
        assert set(board.columns) <= set(out.columns)
        for col in ("comp_names", "comp_note", "comp_quality", "comp_bust_rate", "comp_k"):
            assert col in out.columns
        assert rep["bust_share"] >= MIN_POOL_BUST_SHARE
        assert len(detail) == int(out["comp_k"].fillna(0).sum())

    def test_detail_is_auditable_back_to_the_named_comp(self, pool_bat):
        board = pool_bat.head(10).copy()
        out, detail, _ = attach_comps(board, pool_bat, player_type="batter", as_of_season=2026)
        first = detail.loc[detail["comp_rank"] == 1].set_index("query_player_name")
        for _, row in out.iterrows():
            if int(row["comp_k"] or 0) == 0:
                continue
            assert first.loc[row["player_name"], "comp_name"] in row["comp_names"]

    def test_bust_rate_is_one_minus_debut_rate_of_the_named_comps(self, pool_bat):
        board = pool_bat.head(15).copy()
        out, detail, _ = attach_comps(board, pool_bat, player_type="batter", as_of_season=2026)
        for qi, grp in detail.groupby("query_index"):
            n_never = int((grp["comp_outcome_tier"] == "never_reached").sum())
            assert n_never == int(out.iloc[qi]["comp_n_never_reached"])

    def test_k_is_reported_and_respected(self, pool_bat):
        out, _, rep = attach_comps(pool_bat.head(10), pool_bat, player_type="batter",
                                   as_of_season=2026, cfg=CompConfig(k=9, name="k9"))
        assert rep["k"] == 9
        assert out["comp_k"].max() <= 9

    def test_default_k_is_in_the_pre_registered_range(self):
        assert 10 <= DEFAULT_K <= 25


# ── 14. The comp term inside the RANKING ─────────────────────────────────────────────────────

class TestCompRanking:
    """`attach_comp_ranking` is the only place a comp number touches the order you draft in."""

    def _board(self) -> pd.DataFrame:
        return pd.DataFrame({
            "board_rank": [1, 2, 3, 4, 5],
            "player_name": list("ABCDE"),
            "player_type": ["batter"] * 5,
            "fv": [60.0, 50.0, 50.0, 50.0, 40.0],
            "fv_pctile": [95.0, 60.0, 60.0, 60.0, 20.0],
            "model_score": [50.0, 50.0, 50.0, 50.0, 50.0],
            "blend_score": [80.0, 55.0, 55.0, 55.0, 32.0],
            #                 ↓ bad comps      ↓ good comps      ↓ no comps
            "comp_fp_median": [5.0, 10.0, 400.0, np.nan, 200.0],
        })

    def test_a_better_comp_read_moves_a_player_up_within_his_grade(self):
        out = attach_comp_ranking(self._board())
        order = out.loc[out["fv"] == 50.0, "player_name"].tolist()
        assert order[0] == "C"                      # best comps among the three 50-FV players

    def test_fv_still_dominates_the_sort(self):
        """⭐ THE LOAD-BEARING INVARIANT. The measured winner keeps E8.0's FV-first shape and only
        changes the TIEBREAK — re-sorting on blend+comp instead tested better on batters but was
        unstable on pitchers. A 60-FV player with the worst comps on the board must still outrank
        every 50-FV player, or this function has quietly become a different ordering."""
        b = self._board()
        b.loc[0, "comp_fp_median"] = 0.0             # the 60 FV gets the worst comps possible
        out = attach_comp_ranking(b)
        assert out.iloc[0]["player_name"] == "A"
        assert out.loc[out["player_name"] == "A", "board_rank"].iloc[0] == 1

    def test_a_row_without_comps_keeps_its_own_score_and_is_not_penalised(self):
        out = attach_comp_ranking(self._board())
        d = out.loc[out["player_name"] == "D"].iloc[0]
        assert pd.isna(d["comp_score"])
        assert d["model_score"] == pytest.approx(d["model_score_no_comps"])

    def test_the_pre_comp_ordering_is_preserved_for_audit(self):
        out = attach_comp_ranking(self._board())
        assert set(out["board_rank_no_comps"]) == {1, 2, 3, 4, 5}
        assert out["comp_rank_delta"].sum() == 0          # both are permutations of 1..n
        # positive delta = the comps moved him UP the board
        c = out.loc[out["player_name"] == "C"].iloc[0]
        assert c["comp_rank_delta"] > 0

    def test_zero_weight_is_a_no_op_on_the_ordering(self):
        """The weight is the whole mechanism — at 0 the board must be byte-identical in order."""
        b = self._board()
        out = attach_comp_ranking(b, weight=0.0)
        assert out["player_name"].tolist() == b["player_name"].tolist()
        assert (out["comp_rank_delta"] == 0).all()

    def test_percentiles_are_taken_within_player_type(self):
        """Batters and pitchers are ranked against their own kind — a cross-type comp percentile
        would compare a GB% neighbourhood to an ISO one and call the result an ordering."""
        b = self._board()
        b["player_type"] = ["batter", "batter", "pitcher", "pitcher", "pitcher"]
        out = attach_comp_ranking(b)
        for t in ("batter", "pitcher"):
            sub = out.loc[out["player_type"] == t, "comp_score"].dropna()
            if len(sub) > 1:
                assert sub.max() == pytest.approx(100.0)

    def test_the_weight_is_the_measured_one(self):
        """0.30 is the E7.13 ordering study's clean-fold winner on BOTH player types, not a round
        number. A silent drift here changes the board with no measurement behind it."""
        assert COMP_RANK_WEIGHT == 0.30


# ── 15. E8.1 — the comp term is part of THE BOARD, not of one script ─────────────────────────

class TestNativeCompWiringMatchesTheAugmenter:
    """E7.13 shipped the comp-aware order inside `attach_comp_ranking`, called ONLY by the separate
    `build_prospect_comps.py` re-export. So a plain `build_prospect_board.py` rebuild produced a
    board that had silently reverted to the PRE-comp ordering — invisible, because a reverted board
    looks exactly like a correct one. E8.1 wires the term into the build itself.

    ⚠️ The operator drafts off the AUGMENTER's file, so the native path must not be a SECOND
    ordering. These pin that it is the same one.
    """

    def _board(self) -> pd.DataFrame:
        return pd.DataFrame({
            "board_rank": [1, 2, 3, 4, 5, 6],
            "player_name": list("ABCDEF"),
            "player_type": ["batter", "batter", "pitcher", "pitcher", "two_way", "batter"],
            "fv": [60.0, 50.0, 50.0, 50.0, 50.0, 40.0],
            "fv_pctile": [95.0, 60.0, 60.0, 60.0, 60.0, 20.0],
            "model_score": [50.0, 50.0, 50.0, 50.0, 50.0, 50.0],
            "blend_score": [80.0, 55.0, 55.0, 55.0, 55.0, 32.0],
            "comp_fp_median": [5.0, 10.0, 400.0, np.nan, 200.0, 90.0],
        })

    def test_the_two_entry_points_are_the_same_implementation(self):
        """`prospect_comps.attach_comp_ranking` (E7.13's public name, used by the augmenter) and
        `board_assembly.apply_comp_term` (where the scoring now lives, used by the native build)
        must return the IDENTICAL frame. They delegate, so this is structural — the test exists to
        catch a future edit that re-forks the arithmetic into two copies."""
        from betting_ml.scripts.prospect_board.board_assembly import apply_comp_term

        b = self._board()
        pd.testing.assert_frame_equal(attach_comp_ranking(b), apply_comp_term(b))

    def test_a_csv_round_trip_does_not_change_the_order(self):
        """⭐ THE BYTE-FOR-BYTE CLAIM, made runnable. The augmenter reads an EXPORTED CSV; the native
        path scores the in-memory frame. If a CSV round-trip could permute the board the two would
        be different orderings even running identical code — so prove it cannot.

        (The real hazard is tie-breaking: `sort_values` on multiple keys is stable, so rows tied on
        all three sort keys keep their INCOMING order. Both paths therefore have to hand the sort the
        same incoming order — which is why the term is applied AFTER the pre-comp rank, not inside
        `attach_scores`.)"""
        import io

        b = self._board()
        native = attach_comp_ranking(b)
        via_csv = attach_comp_ranking(pd.read_csv(io.StringIO(b.to_csv(index=False))))
        assert native["player_name"].tolist() == via_csv["player_name"].tolist()
        assert native["board_rank"].tolist() == via_csv["board_rank"].tolist()
        pd.testing.assert_series_equal(native["comp_rank_delta"], via_csv["comp_rank_delta"])

    def test_ties_on_every_sort_key_keep_the_pre_comp_order(self):
        """The tie case the placement decision is about: identical fv / model_score / blend_score and
        NO comps at all must leave the board exactly as it came in, in `board_rank` order."""
        b = pd.DataFrame({
            "board_rank": [1, 2, 3],
            "player_name": ["X", "Y", "Z"],
            "player_type": ["batter"] * 3,
            "fv": [50.0] * 3, "fv_pctile": [60.0] * 3,
            "model_score": [50.0] * 3, "blend_score": [55.0] * 3,
            "comp_fp_median": [np.nan] * 3,
        })
        out = attach_comp_ranking(b)
        assert out["player_name"].tolist() == ["X", "Y", "Z"]
        assert (out["comp_rank_delta"] == 0).all()

    def test_the_board_runner_actually_applies_the_comp_term(self, monkeypatch, tmp_path):
        """⭐ THE ACTUAL FOOTGUN GUARD — and it exercises the real `main()` wiring rather than
        grepping the source, because a source-inspection check can be satisfied by a COMMENT that
        merely mentions the call (the INC-38 lesson).

        Everything that touches S3 is stubbed; the assertion is that a default `main([])` reaches
        `attach_comps_to_board`. Delete the wiring and this goes red."""
        import betting_ml.scripts.prospect_board.build_prospect_board as runner
        import betting_ml.scripts.prospect_board.build_prospect_comps as augmenter

        calls: list[pd.DataFrame] = []

        def _fake_attach(board, **kwargs):
            calls.append(board)
            return attach_comp_ranking(board), pd.DataFrame(), {"ranking": {"rows_moved": 0}}

        monkeypatch.setattr(runner, "_connect", lambda: object())
        # 5-tuple since E8.3 added the stolen-base projections as a fifth input.
        monkeypatch.setattr(runner, "load_inputs", lambda conn, **kw: (
            pd.DataFrame({"season": [2026], "as_of_date": ["2026-07-27"]}),
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()))
        monkeypatch.setattr(runner, "assemble_board",
                            lambda *a, **kw: (self._board().assign(season=2026), {}))
        monkeypatch.setattr(runner, "write_exports", lambda *a, **kw: [])
        monkeypatch.setattr(augmenter, "attach_comps_to_board", _fake_attach)
        # The comp inputs are gitignored research artifacts. Point the runner's existence check at
        # real files in tmp_path rather than stubbing `Path.exists` globally — the check itself is a
        # guard worth keeping live in this test (it is what turns a missing artifact into a HARD
        # stop instead of a silently pre-comp board).
        for name in ("DEFAULT_POOL", "DEFAULT_PAIRS_BAT", "DEFAULT_PAIRS_PIT"):
            stub = tmp_path / f"{name.lower()}.parquet"
            stub.write_bytes(b"")
            monkeypatch.setattr(augmenter, name, stub)

        assert runner.main(["--out-dir", str(tmp_path), "--skip-pipeline-consensus"]) == 0
        assert calls, ("build_prospect_board.main() did not apply the E7.13 comp term — a plain "
                       "board rebuild has silently reverted to the PRE-comp ordering (E8.1)")

    def test_skipping_comps_is_opt_in_not_the_default(self):
        """The pre-E8.1 behaviour still has to be REACHABLE (the artifacts are gitignored, so a
        fresh machine needs an escape hatch) — but it must never be what you get by accident."""
        import betting_ml.scripts.prospect_board.build_prospect_board as runner

        parser_src = Path(runner.__file__).read_text(encoding="utf-8")
        assert '"--skip-comps", action="store_true"' in parser_src
        assert '"--comps"' not in parser_src, (
            "comps must be ON by default (a --skip-comps opt-OUT), never an opt-IN flag: an "
            "opt-in restores the exact footgun E8.1 closed."
        )
