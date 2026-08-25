"""NF-INJ3 guards — the injury-games bake-off's load-bearing invariants.

⭐ EACH CLAUSE GETS ITS OWN ISOLATING FIXTURE (NF-D17): a fixture that trips more than one clause
proves none of them, because deleting the clause under test leaves the guard green. Every test here
is RED-proven against deliberately-broken source by `nf_inj3_red_proof.py`.

Fast-gate safe: imports only `quant_sports_intel_models…`, never `pipeline` (the E11.23 rule).
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import nf_inj3_injury_games as IG
from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj3_injury_games as R
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP


def _code_only(src: str) -> str:
    """Source with comments and docstrings removed. A source-inspection clause must not be
    satisfiable — or falsifiable — by PROSE (INC-38)."""
    tree = ast.parse(textwrap.dedent(src))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    return ast.unparse(tree)


def _pop(n=120, seed=0):
    """A minimal in-fold population: every column the arms read, nothing they do not."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "proj_status": rng.choice(["RES", "PUP", "SUS"], n, p=[0.8, 0.1, 0.1]),
        "eg": rng.uniform(1, 17, n),
        "realized_games": rng.integers(0, 18, n).astype(float),
        "prior_games": rng.integers(0, 18, n).astype(float),
        "log1p_prior_fp": rng.uniform(0, 5, n),
        "is_qb": rng.integers(0, 2, n).astype(float),
        "onset_carryover": rng.integers(0, 2, n).astype(float),
        "weeks_since_last_game": rng.integers(0, 18, n).astype(float),
        "target_season": rng.choice([2016, 2017, 2018], n),
    })


# ── the incumbent is the SHIPPED map, not a re-implementation (NF-C0e) ─────────────────────────
class TestIncumbentIsTheShippedMap:
    def test_incumbent_arm_delegates_to_season_projection(self):
        """A study that RE-DERIVES the shipped logic measures something else. `incumbent_games`
        must call the production function, so the arm scored and the arm served cannot drift."""
        src = inspect.getsource(IG.incumbent_games)
        tree = ast.parse(textwrap.dedent(src))
        calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert "SP.injury_availability_games" in calls, (
            "the incumbent arm must DELEGATE to season_projection.injury_availability_games, "
            f"never re-implement the blend; calls found: {sorted(calls)}")

    def test_it_reproduces_the_production_map_numerically(self):
        eg = np.array([0.0, 2.0, 4.0, 9.0, 15.0, 17.0])
        st = pd.Series(["RES"] * 6)
        got = IG.incumbent_games(st, eg)
        want = SP.injury_availability_games(
            pd.DataFrame({"proj_games": eg, "proj_status": st.to_numpy()}))
        assert np.allclose(got, want)

    def test_recovering_the_pre_cap_games_round_trips_exactly(self):
        """The inversion is what lets every other arm see the model's PRE-cap estimate. If it is
        not a bijection, every non-incumbent arm is fed the wrong input."""
        eg = np.array([0.5, 3.0, 4.0, 4.0001, 8.0, 16.0, 17.0])
        st = pd.Series(["RES"] * 5 + ["SUS"] * 2)
        served = IG.incumbent_games(st, eg)
        assert np.allclose(IG.recover_pre_cap_games(served, st), eg, atol=1e-9)


# ── the metric: CRPS selects, MAE is measurably inverted (NF-D11 / NF-D14) ─────────────────────
class TestMetricIsNotInverted:
    def test_all_zero_degenerate_loses_crps_but_wins_mae(self):
        """⭐ THE TWO-SIDED ANCHOR. On a zero-heavy target whose conditional MEDIAN sits at the
        floor, MAE PAYS FOR PESSIMISM — so a metric the nihilist wins cannot select. This fixture
        asserts BOTH halves: the nihilist must LOSE the selecting metric and WIN the disclosed one,
        which is what proves CRPS is the right primary rather than merely the chosen one."""
        y = np.array([0.0] * 60 + list(range(1, 18)) * 2, dtype=float)
        n, phi = 17, 1.0
        nihilist = IG.score_arm(np.zeros(len(y)), y, n, phi)
        honest = IG.score_arm(np.full(len(y), y.mean()), y, n, phi)
        assert nihilist["crps"] > honest["crps"], "the nihilist must LOSE CRPS"
        assert nihilist["mae"] < honest["mae"], (
            "the fixture must actually EXHIBIT the inversion, or this test proves nothing")

    def test_crps_is_exact_discrete_not_a_quantile_grid(self):
        """A coarse quantile grid silently TIES arms whose means differ by less than its step
        (NF-W4). A point-mass predictive must score exactly 0 against its own outcome."""
        pmf = np.zeros((1, 18)); pmf[0, 5] = 1.0
        assert IG.crps_discrete(pmf, np.array([5.0]))[0] == pytest.approx(0.0, abs=1e-12)
        assert IG.crps_discrete(pmf, np.array([7.0]))[0] == pytest.approx(2.0, abs=1e-12)

    def test_two_means_a_hair_apart_do_not_tie(self):
        y = np.array([0.0] * 30 + [4.0] * 30)
        a = IG.score_arm(np.full(60, 2.00), y, 17, 1.0)["crps"]
        b = IG.score_arm(np.full(60, 2.02), y, 17, 1.0)["crps"]
        assert a != b, "the reducer must resolve sub-grid mean differences"


# ── deflation wiring ──────────────────────────────────────────────────────────────────────────
class TestDeflationWiring:
    def test_pbo_is_computed_on_negated_crps(self):
        """`cscv_pbo` picks the in-sample ARGMAX and CRPS is a LOSS. Getting the sign wrong reports
        the field upside down — a silently inverted gate, not an error."""
        src = inspect.getsource(R.deflation)
        assert '-f["arms"][a]["crps"]' in src, (
            "PBO must be fed NEGATED CRPS; a positive-CRPS matrix ranks the field backwards")

    def test_degenerates_are_declared_before_scoring_not_derived(self):
        """DSR-CONV: an arm qualifies as a degenerate BY DESIGN, never by DECLARATION after it
        loses. The set must be a module constant, not computed from any result."""
        assert isinstance(IG.DEGENERATE_ARMS, tuple) and IG.DEGENERATE_ARMS
        assert set(IG.DEGENERATE_ARMS) <= set(IG.ARMS)
        src = inspect.getsource(IG)
        decl = [ln for ln in src.splitlines() if ln.startswith("DEGENERATE_ARMS")]
        assert decl and "(" in decl[0], "DEGENERATE_ARMS must be a literal constant"

    def test_the_mh2_1a_diagnostic_is_marked_inadmissible(self):
        """The reference-arm-excluded DSR is a DIAGNOSTIC. Marking it admissible would license a
        post-hoc re-read of a registered gate (E2.1-r / MH2.2)."""
        d = R._deflation_diagnostics(
            np.array([0.1, 0.2, 0.3, 0.1, 0.25, 0.2, 0.15]),
            {"incumbent": 0.0, "w": 0.7, "x": 0.5, "all_zero": -0.8},
            {"incumbent": 0.0, "w": 0.7, "x": 0.5}, "w")
        assert d["mh2_1a_v_over_non_reference"]["admissible_to_act_on"] is False

    def test_a_dsr_reached_by_deleting_the_winner_is_refused(self):
        """NF-W7h — the trim diagnostic must REFUSE when the dropped arm IS the winner."""
        d = R._deflation_diagnostics(np.array([0.1] * 7),
                                     {"a": 0.1, "b": 0.12, "w": 9.0},
                                     {"a": 0.1, "b": 0.12, "w": 9.0}, "w")
        assert d["nf_w7h_drop_most_extreme"]["evaluable"] is False


# ── the matched foil (NF-D10 / NF-D15) ────────────────────────────────────────────────────────
class TestMatchedFoil:
    def test_the_foil_strips_exactly_the_timing_columns_and_nothing_else(self):
        """The foil is the ATTRIBUTION. If it differs from the primary by anything other than the
        declared timing columns, the paired delta stops being the timing channel."""
        train, ev = _pop(120, 1), _pop(40, 2)
        _, p_primary = IG.arm_mu("timing_aware", train, ev, 17)
        _, p_foil = IG.arm_mu(IG.MATCHED_FOIL, train, ev, 17)
        assert set(p_primary["features"]) - set(p_foil["features"]) == set(IG.TIMING_FEATURES)
        assert set(p_foil["features"]) - set(p_primary["features"]) == set()

    def test_the_foil_is_not_shippable(self):
        assert IG.MATCHED_FOIL not in IG.ARMS, (
            "the matched foil must sit OUTSIDE the declared field — it is an attribution device, "
            "never a candidate to select")


# ── fail-loudly: a device that cannot fit must not silently no-op (NF1.7 (a)) ──────────────────
class TestFailsLoudly:
    def test_a_too_thin_in_fold_history_raises(self):
        with pytest.raises(ValueError, match="MIN_FIT_N"):
            IG.arm_mu("timing_aware", _pop(IG.MIN_FIT_N - 1, 3), _pop(10, 4), 17)

    def test_a_thin_status_cell_records_its_fallback_rather_than_hiding_it(self):
        train = _pop(120, 5)
        train.loc[train.index[:118], "proj_status"] = "RES"
        train.loc[train.index[118:], "proj_status"] = "SUS"     # a 2-row SUS cell
        _, prov = IG.fit_status_levels(train)
        assert prov["SUS"]["used_fallback"] is True and "why" in prov["SUS"]
        assert prov["RES"]["used_fallback"] is False

    def test_a_missing_own_form_oracle_is_recorded_as_NOT_evaluable(self):
        """An anchor that fails to fit makes its own check VACUOUSLY TRUE. It must be recorded as a
        failed check, never absorbed into a pass."""
        fold = {"arms": {a: {"crps": 1.0} for a in IG.ARMS + (IG.MATCHED_FOIL,)},
                "oracles": {}, "matched_n": None}
        out = R.anchor_audit([fold] * 3, "timing_aware")
        assert out["timing_aware"]["evaluable"] is False
        assert "respects_oracle" not in out["timing_aware"]
        assert out["_matched_n_control"]["evaluable"] is False

    def test_a_missing_artifacts_dir_raises_rather_than_returning_an_empty_population(self):
        """NF-INFRA1 — the builds are gitignored and absent from a fresh worktree. A build that
        reads NOTHING must not report success."""
        with pytest.raises(FileNotFoundError, match="artifacts"):
            R.artifacts_dir("/tmp/nf_inj3_definitely_not_a_dir")


# ── the permutation anchor ────────────────────────────────────────────────────────────────────
class TestPermutationAnchor:
    def test_it_preserves_the_within_cell_marginal_exactly(self):
        ev = _pop(200, 6)
        out = IG.permute_timing(ev, seed=7)
        for c in IG.TIMING_FEATURES:
            for key, idx in ev.groupby([ev["proj_status"].astype(str),
                                        ev["target_season"]]).groups.items():
                assert (sorted(ev.loc[idx, c]) == sorted(out.loc[idx, c])), (
                    f"cell {key} marginal of {c} changed — the anchor must destroy LINKAGE only")

    def test_it_actually_changes_the_linkage(self):
        ev = _pop(200, 8)
        out = IG.permute_timing(ev, seed=9)
        assert any((ev[c].to_numpy() != out[c].to_numpy()).any() for c in IG.TIMING_FEATURES), (
            "a permutation that changes nothing is a vacuous anchor")


# ── population construction ───────────────────────────────────────────────────────────────────
class TestPopulation:
    def test_no_prior_game_means_the_LONGEST_absence_not_a_missing_one(self):
        """A `fillna(0)` here would read as 'he just played', which is the exact opposite of the
        truth for a player with no prior-season game at all.

        ⭐ RE-ANCHORED by NF-INJ3b-SHIP onto `IG.derive_covariates`, the ONE owner the served feed
        also calls (the derivation was extracted verbatim from `build_population`). Re-anchoring an
        existing property onto a new implementation is the correct move; deleting or weakening it
        because the source moved is how a retired guard silently stops guarding (MH2.7 (ii)).

        ⭐ AND IT NOW MEASURES THE SENTINEL RATHER THAN GREPPING FOR IT: a source-text assertion
        cannot tell `fillna(weeks.max())` apart from a comment mentioning it (INC-38)."""
        src = inspect.getsource(IG.derive_covariates)
        assert '.fillna(weeks.max()' in src, (
            "the sentinel for 'never played last season' must be the FULL prior season, never 0")
        # played through week 3 of an 18-week season, vs never played at all
        frame = pd.DataFrame({
            "position": ["RB", "RB"], "prior_games": [3.0, 0.0], "prior_fp": [10.0, 0.0],
            "last_week_played": [3.0, np.nan], "prior_season_weeks": [18.0, 18.0],
            "prior_end_status": ["ACT", "ACT"]})
        w = IG.derive_covariates(frame)["weeks_since_last_game"].to_numpy()
        assert w[0] == 15.0
        assert w[1] == 18.0, ("a player with NO prior-season game must take the FULL prior season "
                              "as his absence, not 0 and not NaN")

    def test_the_covariate_derivation_has_exactly_ONE_owner(self):
        """NF-INJ3b-SHIP: the arm was FITTED on `build_population`'s covariates and is now SERVED on
        `injury_covariate_feed`'s. Both must be the same function, or the served model is not the
        certified one (NF-C0e)."""
        pop = _code_only(inspect.getsource(R.build_population))
        assert "IG.derive_covariates(" in pop, (
            "build_population no longer derives its covariates through the shared owner — the "
            "fitted and served definitions can now drift")
        for banned in ("log1p_prior_fp\"] = ", "onset_carryover\"] = ", "weeks_since_last_game\"] = "):
            assert banned not in pop, (
                f"build_population re-derives {banned!r} inline again — there must be exactly one "
                f"definition of each covariate in the repo")

    def test_the_era_floor_is_a_constant_not_a_result(self):
        assert IG.ERA_MIN_SEASON == 2016
        assert IG.FOLDS[0] > IG.ERA_MIN_SEASON, "folds must leave burn-in history to fit on"

    def test_the_declared_field_size_matches_the_declared_arms(self):
        assert IG.DECLARED_FIELD_SIZE == len(IG.ARMS)


# ── the pre-registration exists and is not edited by the run ──────────────────────────────────
def test_the_preregistration_is_committed_and_the_runner_points_at_it():
    prereg = (Path(R.__file__).resolve().parent / "ablation_results"
              / "nf_inj3_preregistration.md")
    assert prereg.exists(), "the pre-registration must be committed BEFORE the run (E2.1-r)"
    body = prereg.read_text()
    for token in ("timing_aware", "hurdle_transfer", "all_zero", "no_cap",
                  IG.MATCHED_FOIL, "DECLARED_FIELD_SIZE = 7"):
        assert token in body, f"{token} must be DECLARED FORWARD in the pre-registration"


def test_the_served_arm_is_still_the_incumbent():
    """🔒 Deploy-held. Nothing here serves until the PM records a disposition."""
    assert R.SERVED_ARM == "incumbent"
