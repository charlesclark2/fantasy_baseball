"""NF-W3 guards — the game-environment component (team play-volume + pass/rush allocation).

Discipline carried from the NF-W family, applied here:
  · every RED-proof mutates the source IN-PROCESS and ASSERTS THE MUTATION LANDED before running
    the guard (E11.24 #682 — a red-proof that silently no-ops reports a false "the guard caught
    it", and that reads as a finding);
  · every guard that ITERATES over matches asserts NON-VACUITY (NF1.7 (a) / INC-38 — an empty
    match set passes on nothing);
  · every clause of an AND-composed rule gets its OWN ISOLATING fixture, satisfying every other
    clause, so only the clause under test can flip the result (NF-D17 — a fixture that trips two
    clauses proves neither);
  · a source-inspection guard is written so PROSE can neither satisfy nor trip it (INC-38).
"""
from __future__ import annotations

import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

_MODULE = Path(GE.__file__)
_RUNNER = _MODULE.parent / "run_nf_w3_game_environment.py"
_PREREG = _MODULE.parent / "ablation_results" / "nf_w3_preregistration.md"


def _mutated(path: Path, old: str, new: str, name: str):
    """Load `path` with one deliberate break applied — asserting the break LANDED first."""
    src = path.read_text()
    assert old in src, f"RED-proof target not found in {path.name}: {old!r}"
    mutated = src.replace(old, new, 1)
    assert mutated != src, "the mutation did not change the source — the RED-proof would no-op"
    mod = types.ModuleType(name)
    mod.__file__ = str(path)
    exec(compile(mutated, str(path), "exec"), mod.__dict__)  # noqa: S102 — test harness
    return mod


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Provenance — four clauses, four ISOLATING fixtures (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestProvenanceClausesAreIndependentlyRedProvable:
    def test_the_real_feature_list_passes_and_is_not_empty(self):
        assert len(GE.FEATURES) > 0, "a provenance check over zero features passes on nothing"
        GE.assert_feature_provenance_w3(GE.FEATURES)

    def test_unknown_family_is_rejected(self):
        """ISOLATING: a family nobody certified, carrying no leaky/era/banned token."""
        col = "mystery_family__usage"
        assert not any(tok in col for tok in GE.ERA_FORBIDDEN_TOKENS)
        assert not any(tok in col for tok in GE.BANNED_SOURCE_TOKENS)
        with pytest.raises(WF.LeakageError, match="unknown provenance"):
            GE.assert_feature_provenance_w3([col])

    def test_a_leaky_token_is_rejected_under_a_certified_family(self):
        """ISOLATING: family is certified, token is not an era or deferred token — only the leaky
        clause can fire."""
        col = "team_environment__home_score"
        assert col.split("__", 1)[0] in GE.USED_FAMILIES
        assert not any(tok in col for tok in GE.ERA_FORBIDDEN_TOKENS)
        assert not any(tok in col for tok in GE.BANNED_SOURCE_TOKENS)
        with pytest.raises(WF.LeakageError, match="leaky"):
            GE.assert_feature_provenance_w3([col])

    def test_a_participation_era_token_is_rejected(self):
        """ISOLATING: certified family, not leaky, not a deferred source — only the era clause."""
        col = "opponent_matchup__pressure_rate_l4"
        assert col.split("__", 1)[0] in GE.USED_FAMILIES
        assert not any(tok == col or col.endswith(f"_{tok}") or col.startswith(f"{tok}_")
                       for tok in WF.LEAKY_COLUMNS)
        assert not any(tok in col for tok in GE.BANNED_SOURCE_TOKENS)
        with pytest.raises(WF.LeakageError, match="participation-era"):
            GE.assert_feature_provenance_w3([col])

    def test_a_deferred_contract_source_is_rejected(self):
        """ISOLATING: certified family, not leaky by the token-boundary rule, no era token."""
        col = "team_environment__spread_line_move"
        assert col.split("__", 1)[0] in GE.USED_FAMILIES
        assert not any(tok == col or col.endswith(f"_{tok}") or col.startswith(f"{tok}_")
                       for tok in WF.LEAKY_COLUMNS)
        assert not any(tok in col for tok in GE.ERA_FORBIDDEN_TOKENS)
        with pytest.raises(WF.LeakageError, match="deferred-contract"):
            GE.assert_feature_provenance_w3([col])

    def test_red_proof_deleting_the_era_clause_lets_a_participation_feature_through(self):
        mod = _mutated(
            _MODULE,
            'era = [c for c in cols if any(tok in c for tok in ERA_FORBIDDEN_TOKENS)]',
            'era = []',
            "ge_no_era")
        mod.assert_feature_provenance_w3(["opponent_matchup__pressure_rate_l4"])  # no raise
        with pytest.raises(WF.LeakageError):
            GE.assert_feature_provenance_w3(["opponent_matchup__pressure_rate_l4"])

    def test_the_env_block_injected_into_layer_b_also_passes_provenance(self):
        assert len(GE.ENV_FEATURES) > 0
        GE.assert_feature_provenance_w3(GE.ENV_FEATURES)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The SOURCE query may not READ a deferred column — and PROSE may neither satisfy nor trip it
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheAggregationSqlIsCheckedAtTheSource:
    def test_the_real_aggregation_sql_is_clean(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w3_game_environment as R,
        )
        assert len(GE.BANNED_SOURCE_TOKENS) > 0, "an empty ban list checks nothing"
        GE.assert_source_query_is_clean(R.TEAM_BOX_SQL)

    def test_reading_a_market_column_is_rejected(self):
        with pytest.raises(WF.LeakageError, match="deferred-contract"):
            GE.assert_source_query_is_clean("select avg(spread_line) from pbp")

    def test_a_prose_mention_in_a_comment_cannot_TRIP_the_check(self):
        """INC-38, one direction: an explanatory comment naming the banned column is not a read."""
        GE.assert_source_query_is_clean(
            "-- deliberately does not read spread_line or temp\nselect count(*) from pbp")

    def test_a_prose_mention_cannot_SATISFY_a_real_read_either(self):
        """INC-38, the other direction: a comment claiming cleanliness above a genuine read must
        still be rejected — otherwise the check tests the comment."""
        with pytest.raises(WF.LeakageError):
            GE.assert_source_query_is_clean(
                "-- no market columns are read here\nselect avg(total_line) from pbp")

    def test_red_proof_not_stripping_comments_makes_the_check_fire_on_prose(self):
        mod = _mutated(
            _MODULE,
            'body = "\\n".join(ln.split("--", 1)[0] for ln in sql.splitlines()).lower()',
            'body = sql.lower()',
            "ge_no_strip")
        with pytest.raises(WF.LeakageError):
            mod.assert_source_query_is_clean("-- does not read spread_line\nselect 1")
        GE.assert_source_query_is_clean("-- does not read spread_line\nselect 1")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The measured franchise-code defect: pbp uses MODERN codes, schedules keeps ERA codes
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _sched(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"season": s, "week": w, "home_team": h, "away_team": a,
          "gameday": g, "div_game": 0} for s, w, h, a, g in rows])


def _box(rows: list[tuple]) -> pd.DataFrame:
    out = []
    for s, w, t in rows:
        out.append({"season": s, "week": w, "team": t, "off_plays": 62, "pass_plays": 36,
                    "sacks": 2, "drives": 11, "epa_per_play": 0.0, "success_rate": 0.45,
                    "proe": -1.0, "no_huddle": 0.09, "points": 21,
                    "neutral_pass_rate": 0.55, "sec_per_play": 27.0})
    return pd.DataFrame(out)


class TestFranchiseCodeAlignment:
    """The nflverse defect this story measured: `pbp.posteam` is normalised to the CURRENT
    franchise code while `schedules` keeps the ERA code (pbp `LAC`/`LV` vs schedule `SD`/`OAK`
    through 2019). A raw join NaNs exactly those rows — and pandas matches NaN against NaN, so
    they then CROSS-JOIN and silently DUPLICATE."""

    def test_the_measured_2016_mismatch_is_rejected(self):
        box = _box([(2016, 1, "LAC"), (2016, 1, "LV")])
        sch = _sched([(2016, 1, "SD", "OAK", "2016-09-11")])
        with pytest.raises(WF.LeakageError, match="franchise codes"):
            GE.assert_team_codes_align(box, sch)

    def test_canonicalisation_resolves_it(self):
        box = _box([(2016, 1, "LAC"), (2016, 1, "LV")])
        sch = GE.canonicalize_team_codes(_sched([(2016, 1, "SD", "OAK", "2016-09-11")]),
                                         ("home_team", "away_team"))
        GE.assert_team_codes_align(box, sch)  # no raise

    def test_the_canon_map_is_not_empty(self):
        assert GE.TEAM_CODE_CANON, "an empty canon map makes canonicalisation a no-op"

    def test_a_row_with_no_schedule_match_raises_rather_than_becoming_a_nan_join(self):
        """ISOLATING: the per-season code SETS align (both sides know AAA and BBB), so
        `assert_team_codes_align` cannot fire — only the post-merge NaN guard can. Team AAA plays
        in week 2 with no week-2 schedule row."""
        box = _box([(2020, 1, "AAA"), (2020, 1, "BBB"), (2020, 2, "AAA"), (2020, 2, "BBB")])
        sch = _sched([(2020, 1, "AAA", "BBB", "2020-09-13"),
                      (2020, 2, "BBB", "AAA", "2020-09-20")])
        sch = sch[~((sch["season"] == 2020) & (sch["week"] == 2))]
        GE.assert_team_codes_align(box[box.week == 1], sch)  # sets align on the evaluable season
        with pytest.raises(WF.LeakageError, match="did not match the schedule"):
            GE.build_team_game_frame(box, sch)

    def test_red_proof_removing_canonicalisation_reintroduces_the_defect(self):
        mod = _mutated(
            _MODULE,
            'schedule = canonicalize_team_codes(schedule, ("home_team", "away_team"))',
            'schedule = schedule.copy()',
            "ge_no_canon")
        box = _box([(2016, 1, "LAC"), (2016, 1, "LV")])
        sch = _sched([(2016, 1, "SD", "OAK", "2016-09-11")])
        with pytest.raises(WF.LeakageError):
            mod.build_team_game_frame(box, sch)
        # and the real module handles the same input
        GE.build_team_game_frame(box, sch)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. T2 is UNCONDITIONAL on the realized denominator — a BEHAVIOURAL guard, not a source grep
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _team_frame(n: int = 1500, seed: int = 7) -> pd.DataFrame:
    """A well-conditioned synthetic team-game panel: enough rows for a 36-feature GLM to fit, and
    a target that genuinely depends on a feature so the arms are not fitting pure noise."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "season": 2020, "week": np.tile(np.arange(1, 11), n // 10)[:n],
        "team": np.repeat([f"T{i}" for i in range(n // 10)], 10)[:n],
        "gw": np.tile(np.arange(1, 11), n // 10)[:n],
    })
    for c in GE.FEATURES:
        df[c] = rng.normal(0, 1, n)
    drive = df["team_environment__pass_share_l4"].to_numpy()
    df["pass_share"] = np.clip(0.58 + 0.05 * drive + rng.normal(0, 0.04, n), 0.05, 0.95)
    df["off_plays"] = np.clip(62 + 3 * drive + rng.normal(0, 5, n), 30, 95).round()
    df["team_environment__off_plays_l4"] = 62 + 2 * drive
    return df


class TestPassShareArmsNeverReadTheRealizedDenominatorAtTest:
    """The realized play count encodes game script; letting it into a TEST-time predictive would
    hand every T2 arm a value serving does not have. Measured, not asserted in prose: perturbing
    the realized `off_plays` on the TEST rows must not move a single quantile."""

    @pytest.mark.parametrize("arm", ["binom_glm", "betabinom"])
    def test_perturbing_realized_off_plays_on_test_rows_changes_nothing(self, arm):
        df = _team_frame()
        train, test = df.iloc[:1200], df.iloc[1200:].reset_index(drop=True)
        base = GE.ARM_FITTERS[arm](train, test, GE.FEATURES, "pass_share")
        assert np.isfinite(base).all(), (
            "an all-NaN predictive would make this comparison vacuous — the fixture must fit")
        wrecked = test.copy()
        wrecked["off_plays"] = 1.0  # an absurd realized denominator
        after = GE.ARM_FITTERS[arm](train, wrecked, GE.FEATURES, "pass_share")
        assert np.allclose(base, after), (
            f"{arm} read the realized test-row denominator — T2 must be unconditional")

    def test_the_test_time_trial_count_is_the_lagged_column(self):
        df = _team_frame()
        n = GE._test_trials(df)
        lagged = pd.to_numeric(df["team_environment__off_plays_l4"], errors="coerce").to_numpy()
        assert np.allclose(n, np.rint(np.clip(lagged, 5.0, None)))
        assert not np.allclose(n, df["off_plays"].to_numpy())

    def test_the_trial_count_is_an_INTEGER_or_scipy_silently_returns_nan(self):
        """⚠️ `scipy.stats.binom`/`betabinom` return NaN for a non-integer `n`, and a 4-game
        rolling mean is non-integer almost always — so an unrounded trial count makes both T2 GLM
        arms emit NaN on most rows, which `np.nanmean` then averages away, scoring them on a
        silently different population. Measured, not asserted."""
        from scipy.stats import binom
        assert np.isnan(binom.ppf(0.5, 62.25, 0.58)), (
            "the premise of this guard no longer holds — re-derive it before trusting the round")
        n = GE._test_trials(_team_frame())
        assert np.all(n == np.rint(n))

    def test_the_reducer_refuses_a_non_finite_predictive(self):
        q = np.zeros((4, len(GE.Q_LEVELS)))
        GE.assert_finite_predictive(q, "clean")          # no raise
        q[2, 5] = np.nan
        with pytest.raises(ValueError, match="non-finite"):
            GE.assert_finite_predictive(q, "dirty")

    def test_red_proof_using_the_realized_denominator_makes_the_arm_move(self):
        mod = _mutated(
            _MODULE,
            'n = pd.to_numeric(test["team_environment__off_plays_l4"], errors="coerce")',
            'n = pd.to_numeric(test["off_plays"], errors="coerce")',
            "ge_realized_n")
        df = _team_frame()
        train, test = df.iloc[:1200], df.iloc[1200:].reset_index(drop=True)
        wrecked = test.copy()
        wrecked["off_plays"] = 1.0
        a = mod.fit_binom_glm(train, test, mod.FEATURES, "pass_share")
        b = mod.fit_binom_glm(train, wrecked, mod.FEATURES, "pass_share")
        assert not np.allclose(a, b), "the mutation must land: the leak must be observable"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. ⛔ no fillna(0) — a missing lagged window stays NaN (behavioural)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestMissingLaggedWindowsStayNaN:
    def test_a_first_appearance_has_NaN_priors_not_zero(self):
        box = _box([(2020, 1, "AAA"), (2020, 1, "BBB")])
        sch = _sched([(2020, 1, "AAA", "BBB", "2020-09-13")])
        out = GE.build_team_game_frame(box, sch)
        assert len(out) == 2
        for col in ("team_environment__off_plays_l4",
                    "team_environment__off_plays_prior_season",
                    "team_environment__pass_share_s2d"):
            assert out[col].isna().all(), (
                f"{col} was filled rather than left NaN — 0 plays is a LEGAL value, so an "
                f"imputed 0 is a fabricated observation (the NF-W0b contract)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Verdict vocabulary — three-way, DERIVED, failing closed; word and parenthetical agree
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestVerdictVocabulary:
    @pytest.mark.parametrize("d,lo,hi,expect", [
        (0.5, 0.1, 0.9, "BEATS"),
        (-0.5, -0.9, -0.1, "LOSES TO"),
        (-0.0008, -0.0150, 0.0135, "TIES"),      # the NF-W2e shape: negative point, spans zero
        (0.5, -0.1, 1.1, "TIES"),
        (None, None, None, "TIES"),               # unevaluable ⇒ fails CLOSED (NF1.7 (a))
        (0.5, None, None, "TIES"),
        (float("nan"), 0.1, 0.9, "TIES"),
    ])
    def test_three_way_and_fails_closed(self, d, lo, hi, expect):
        assert GE.direction_word(d, lo, hi) == expect

    def test_the_word_and_its_parenthetical_can_never_contradict(self):
        """The first NF-W2e cut said `TIES … (excludes zero)` — a self-contradicting sentence
        whose half a reader trusts is the parenthetical."""
        cases = [(0.5, 0.1, 0.9), (-0.5, -0.9, -0.1), (-0.0008, -0.0150, 0.0135),
                 (None, None, None), (0.5, -0.1, 1.1)]
        assert len(cases) > 0
        for d, lo, hi in cases:
            s = GE.verdict_sentence("a", "b", d, lo, hi)
            if "TIES" in s:
                assert "excludes zero" not in s, s
            else:
                assert "spans zero" not in s and "unevaluable" not in s, s

    def test_red_proof_a_two_way_word_narrates_a_tie_as_a_loss(self):
        """Fed a real spans-zero read, a two-way word inverts the conclusion off identical
        arithmetic — the NF-W2e reporting defect."""
        mod = _mutated(
            _MODULE,
            '    if lo > 0:\n        return "BEATS"\n    if hi < 0:\n        return "LOSES TO"\n'
            '    return "TIES"',
            '    return "BEATS" if mean_delta > 0 else "LOSES TO"',
            "ge_two_way")
        assert mod.direction_word(-0.0008, -0.0150, 0.0135) == "LOSES TO", (
            "the mutation must land, or this proves nothing")
        assert GE.direction_word(-0.0008, -0.0150, 0.0135) == "TIES"

    def test_paired_ci95_is_unevaluable_below_three_folds(self):
        m, lo, hi = GE.paired_ci95(np.array([0.1, 0.2]))
        assert lo is None and hi is None
        assert GE.direction_word(m, lo, hi) == "TIES"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. Gate composition — ONE ISOLATING FIXTURE PER CLAUSE (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _passing_sel() -> dict:
    return {
        "beats_foil": True,
        "fold_clause": {"passes": True, "required": 6, "attainable": True},
        "pbo": 0.05, "dsr": 0.99,
        "anchors": {
            "nihilist_loses": True, "marginal_loses": True, "zero_width_loses": True,
            "max_width_loses": True, "winner_beats_permuted": True,
            "permuted_lift_not_significant": True,
            "no_arm_beats_own_oracle": True,
            "oracle_floors_respected_at_matched_n": True,
        },
        "coverage": {"blocking_shortfall": False},
    }


class TestEveryGateClauseIsIndependentlyDecisive:
    def test_the_all_pass_baseline_ships(self):
        g = GE.compose_gate(_passing_sel(), fdr_pass=True)
        assert g["ship"] and all(g["checks"].values())

    @pytest.mark.parametrize("mutate,expect_false", [
        (lambda s: s.update({"beats_foil": False}), "beats_foil"),
        (lambda s: s["fold_clause"].update({"passes": False}), "fold_consistency"),
        (lambda s: s.update({"pbo": 0.5}), "pbo_ok"),
        (lambda s: s.update({"pbo": None}), "pbo_ok"),
        (lambda s: s.update({"dsr": 0.5}), "dsr_ok"),
        (lambda s: s.update({"dsr": None}), "dsr_ok"),
        (lambda s: s["anchors"].update({"nihilist_loses": False}), "degenerates_lose"),
        (lambda s: s["anchors"].update({"marginal_loses": False}), "degenerates_lose"),
        (lambda s: s["anchors"].update({"zero_width_loses": False}), "degenerates_lose"),
        (lambda s: s["anchors"].update({"max_width_loses": False}), "degenerates_lose"),
        (lambda s: s["anchors"].update({"winner_beats_permuted": False}), "permutation_behaves"),
        (lambda s: s["anchors"].update({"permuted_lift_not_significant": False}),
         "permutation_behaves"),
        (lambda s: s["anchors"].update({"oracle_floors_respected_at_matched_n": False}),
         "oracle_floors_respected"),
        (lambda s: s["coverage"].update({"blocking_shortfall": True}), "coverage_floor_ok"),
    ])
    def test_flipping_exactly_one_input_fails_exactly_that_check(self, mutate, expect_false):
        sel = _passing_sel()
        mutate(sel)
        g = GE.compose_gate(sel, fdr_pass=True)
        assert g["checks"][expect_false] is False, expect_false
        assert not g["ship"]
        others = [k for k, v in g["checks"].items() if v is False and k != expect_false]
        assert others == [], f"the fixture is not isolating — it also tripped {others}"

    def test_fdr_is_its_own_decisive_clause(self):
        g = GE.compose_gate(_passing_sel(), fdr_pass=False)
        assert g["checks"]["fdr_ok"] is False and not g["ship"]
        assert [k for k, v in g["checks"].items() if v is False] == ["fdr_ok"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The permutation clause FAILS CLOSED on a None p-value (an explicit story requirement)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestThePermutationClauseFailsClosed:
    @staticmethod
    def _clause(mean_lift: float, p):
        return bool(mean_lift <= 0 or (p is not None and p >= 0.05))

    def test_an_unevaluable_p_with_a_positive_permuted_lift_fails(self):
        assert self._clause(0.02, None) is False, (
            "a None p-value must never satisfy the clause — an unevaluable check is not a pass")

    def test_a_negative_permuted_lift_passes_without_needing_a_p(self):
        assert self._clause(-0.01, None) is True

    def test_the_runner_uses_this_exact_shape(self):
        """Source-anchored so the clause cannot drift away from the guard: matched on the CALL
        form, with comments stripped, so prose can neither satisfy nor trip it (INC-38)."""
        body = "\n".join(ln.split("#", 1)[0] for ln in _RUNNER.read_text().splitlines())
        hits = body.count("(p_perm is not None and p_perm >= 0.05)")
        assert hits >= 1, "the fail-closed permutation clause is not present in the runner"
        hits_b = body.count("(p_shuf is not None and p_shuf >= 0.05)")
        assert hits_b >= 1, "Layer B's fail-closed shuffle clause is not present in the runner"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. The per-form oracle floor is enforced AT MATCHED n (NF1.9 (f) / NF-D16 (g‴))
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestOracleFloorAtMatchedN:
    def test_one_ceiling_per_form_not_one_shared_ceiling(self):
        for target, arms in GE.REAL_ARMS.items():
            assert len(arms) >= 3, f"{target} must field ≥3 learner classes (§0.5)"
            names = {GE.oracle_of(a) for a in arms}
            assert len(names) == len(arms), "each arm needs its OWN form's ceiling (NF-D16 g‴)"
            assert set(GE.anchors_for(target)) >= names | {GE.matched_n_of(a) for a in arms}

    @staticmethod
    def _clause(arm, oracle, matched_n):
        return bool((arm > oracle) or (oracle < matched_n))

    def test_an_arm_losing_to_its_own_oracle_passes(self):
        assert self._clause(arm=1.00, oracle=0.90, matched_n=1.20)

    def test_beating_a_capacity_starved_oracle_is_admissible(self):
        """The measured shape: kNN on a 274-row test block is capacity-starved, so the real arm
        (trained on ~3k rows) legitimately beats it — and the matched-n control shows the oracle
        still beats the same form at the oracle's own sample scale."""
        assert self._clause(arm=0.0578, oracle=0.0582, matched_n=0.0592)

    def test_beating_an_oracle_that_is_ALSO_worse_than_matched_n_is_refused(self):
        assert not self._clause(arm=0.90, oracle=0.95, matched_n=0.93)

    def test_the_strict_reading_is_still_reported_beside_the_gated_one(self):
        body = "\n".join(ln.split("#", 1)[0] for ln in _RUNNER.read_text().splitlines())
        assert '"no_arm_beats_own_oracle"' in body, (
            "the STRICT reading must stay in the artifact — the matched-n admission may not hide")
        assert '"oracle_floors_respected_at_matched_n"' in body


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. Multiplicity: two DECLARED families, and the STRICTER binds (MH2 (a))
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTwoFamilyFdrBindsOnTheStricterReading:
    def test_families_are_declared_in_the_module_not_discovered_by_the_runner(self):
        assert set(GE.FDR_FAMILIES) == {"component", "downstream"}
        assert set(GE.FDR_FAMILIES["component"]) == set(GE.TARGETS)
        assert set(GE.FDR_FAMILIES["downstream"]) == set(WP.POSITIONS)

    def test_binding_is_the_AND_of_own_family_and_pooled(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w3_game_environment as R,
        )
        comp = {"off_plays": 0.001, "pass_share": 0.04}
        down = {p: 0.30 for p in WP.POSITIONS}
        out = R.fdr_two_families(comp, down)
        assert set(out["binding"]) == set(comp) | set(down)
        for k, v in out["binding"].items():
            assert v == bool(out["own_family"][k] and out["pooled"][k])

    def test_a_hypothesis_can_pass_its_own_family_and_be_refused_by_the_pooled_one(self):
        """ISOLATING: `pass_share` at p=0.09 clears BH inside a 2-test family (cutoff 0.10) but
        not inside the pooled 6-test correction — which is exactly the case the AND exists for."""
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w3_game_environment as R,
        )
        comp = {"off_plays": 0.001, "pass_share": 0.09}
        down = {p: 0.90 for p in WP.POSITIONS}
        out = R.fdr_two_families(comp, down)
        assert out["own_family"]["pass_share"] is True
        assert out["pooled"]["pass_share"] is False
        assert out["binding"]["pass_share"] is False

    def test_a_none_pvalue_never_binds(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w3_game_environment as R,
        )
        out = R.fdr_two_families({"off_plays": None, "pass_share": 0.001},
                                 {p: 0.001 for p in WP.POSITIONS})
        assert out["binding"]["off_plays"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 11. Layer B cannot pass on nothing — the non-vacuity assertion on the env block
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestLayerBIsNotVacuous:
    def test_an_unattached_env_block_raises_instead_of_silently_comparing_champion_to_itself(
            self, monkeypatch):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w3_game_environment as R,
        )
        player = pd.DataFrame({
            "season": 2020, "week": [1, 1, 2, 2], "team": ["AAA", "BBB", "AAA", "BBB"],
            "opponent": ["BBB", "AAA", "BBB", "AAA"], "position": "WR",
            "fantasy_points": [10.0, 2.0, 5.0, 7.0], "gw": [1, 1, 2, 2],
        })
        for c in WP.FEATURES:
            player[c] = 0.0
        team = pd.DataFrame({"season": 2020, "week": [1, 1], "team": ["AAA", "BBB"],
                             "opponent": ["BBB", "AAA"], "off_plays": 62.0, "pass_share": 0.6})
        fold = WP.Fold("2020H1", np.array([0, 1]), np.array([2, 3]), 2020, 1)
        # an EMPTY env table is exactly what a broken join produces
        monkeypatch.setattr(R, "env_projection_table",
                            lambda *a, **k: pd.DataFrame(
                                columns=["season", "week", "team", "opponent",
                                         "_pt_off_plays", "_sd_off_plays",
                                         "_pt_pass_share", "_sd_pass_share"]))
        monkeypatch.setattr(WP, "fit_lgbm_hurdle",
                            lambda tr, te, f: np.zeros((len(te), len(WP.Q_LEVELS))))
        with pytest.raises(ValueError, match="env block did not attach"):
            R.run_layer_b_fold(fold, fold, player, team, {t: "foil_team_eb" for t in GE.TARGETS})

    def test_the_declared_layer_b_field_is_exactly_two_arms(self):
        """MH2 (a): the field is PRE-REGISTERED and may be neither trimmed nor grown after a
        score. Anchors live outside it so they cannot inflate PBO/DSR (MH2.1 (a))."""
        assert GE.LAYER_B_ELIGIBLE == (GE.LAYER_B_FOIL, *GE.LAYER_B_REAL_ARMS)
        assert len(GE.LAYER_B_ELIGIBLE) == 2
        assert not set(GE.LAYER_B_ANCHORS) & set(GE.LAYER_B_ELIGIBLE)

    def test_anchors_are_excluded_from_the_layer_a_eligible_field(self):
        for t in GE.TARGETS:
            elig, anch = set(GE.eligible_labels(t)), set(GE.anchors_for(t))
            assert not elig & anch, "an anchor in the eligible field deflates against itself"
            assert len(elig) == len(GE.REAL_ARMS[t]) + len(GE.FOILS)
            assert len(anch) > 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 12. CONSTRAINT_REFUSED is hand-classified, and publishes NO sample-size re-test trigger
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestHandClassification:
    def test_anchor_only_failure_is_constraint_refused_with_no_retest_trigger(self):
        checks = {c: True for c in GE.STATISTICAL_CHECKS}
        checks.update({c: True for c in GE.ANCHOR_CHECKS})
        checks["oracle_floors_respected"] = False
        v = GE.hand_classify_refusal(checks)
        assert v["state"] == "CONSTRAINT_REFUSED"
        assert v["retest_trigger"] is None, (
            "a deterministic-constraint refusal must never publish a 'more seasons' trigger "
            "(NF-D18: the remedy is a different mechanism, never more data)")

    def test_a_statistical_failure_hands_back_to_classify_null(self):
        checks = {c: True for c in GE.STATISTICAL_CHECKS}
        checks.update({c: True for c in GE.ANCHOR_CHECKS})
        checks["dsr_ok"] = False
        checks["oracle_floors_respected"] = False
        assert GE.hand_classify_refusal(checks) is None

    def test_an_all_pass_check_set_is_not_a_refusal(self):
        checks = {c: True for c in (*GE.STATISTICAL_CHECKS, *GE.ANCHOR_CHECKS)}
        assert GE.hand_classify_refusal(checks) is None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 13. Deploy-held: this story promotes, publishes and serves nothing
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestDeployHeld:
    """⭐ AST-based, not a text grep: this module's own docstring says it "promotes nothing", and a
    substring scan would trip on that sentence — a guard that a DESCRIPTION can trip is the mirror
    of one that prose can satisfy (INC-38). So the scan reads IMPORTS and CALL TARGETS only."""

    FORBIDDEN_IMPORTS = frozenset({"boto3", "botocore", "s3fs"})
    FORBIDDEN_CALLS = frozenset({
        "put_object", "upload_file", "upload_fileobj", "write_serving_store",
        "register_champion", "promote_champion", "publish",
    })

    @staticmethod
    def _names(path: Path) -> tuple[set[str], set[str], int]:
        import ast
        tree = ast.parse(path.read_text())
        imports: set[str] = set()
        calls: set[str] = set()
        nodes = 0
        for node in ast.walk(tree):
            nodes += 1
            if isinstance(node, ast.Import):
                imports.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute):
                    calls.add(fn.attr)
                elif isinstance(fn, ast.Name):
                    calls.add(fn.id)
        return imports, calls, nodes

    def test_neither_file_imports_or_calls_a_serving_surface(self):
        scanned = 0
        for path in (_MODULE, _RUNNER):
            imports, calls, nodes = self._names(path)
            scanned += nodes
            assert not (imports & self.FORBIDDEN_IMPORTS), f"{path.name}: {imports & self.FORBIDDEN_IMPORTS}"
            assert not (calls & self.FORBIDDEN_CALLS), f"{path.name}: {calls & self.FORBIDDEN_CALLS}"
        assert scanned > 1000, "the AST scan found almost no source — it would pass on nothing"

    def test_red_proof_the_scan_would_catch_a_real_write(self):
        """The scan must be able to FAIL: a synthetic module doing the forbidden thing is caught,
        so a green result on the real files means something."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
            fh.write("import boto3\nboto3.client('s3').put_object(Bucket='b', Key='k')\n")
            tmp = Path(fh.name)
        imports, calls, _ = self._names(tmp)
        assert imports & self.FORBIDDEN_IMPORTS and calls & self.FORBIDDEN_CALLS
        tmp.unlink()

    def test_the_preregistration_exists_and_declares_the_two_layer_gate(self):
        text = _PREREG.read_text()
        assert "best_alpha = 0" in text and "deploy-held" in text
        assert "Layer B" in text and "not a served model" in text
        assert "captured-stays-captured" in text


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 14. Fold axis + power are design quantities, checked in advance
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestFoldAxisAndPower:
    def test_the_fold_axis_is_the_nf_w1_axis_verbatim(self):
        assert GE.TEST_BLOCKS == WP.TEST_BLOCKS and GE.PURGE_WEEKS == WP.PURGE_WEEKS, (
            "Layer B is only a MATCHED comparison if both layers run the same blocks")

    def test_no_gate_is_structurally_unattainable_at_eight_folds(self):
        from betting_ml.utils import cv_power
        n = len(GE.TEST_BLOCKS)
        clause = cv_power.fold_consistency_clause(n)
        assert clause.attainable and clause.wins_required <= n
        assert cv_power.pbo_evaluable(n)
        assert cv_power.sign_test_floor(n) < GE.FDR_Q
        assert cv_power.dsr_ceiling(n) > GE.DSR_MIN, (
            "a DSR ceiling below the gate would make the null a design artifact, not a finding")
