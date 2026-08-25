"""test_nf_inj3b_ship_stamp_guard.py — NF-INJ3b-SHIP nodes 2+3 (D6 stamp guard; THE FLIP).

THE FAILURE THE GUARD KILLS, and it is a residual risk this repo created ON PURPOSE: a served build
that lost its covariate feed serves the INCUMBENT caps while the board-wide policy stamp goes on
claiming the certified hurdle. `injury_games_serving` made that possible (it must let NF1.5's
internal research frame declare `feed_supplied=False`, or the whole build dies) and said where the
answer belongs: *"guard the ARTIFACT at publish"*.

The four legs the acceptance criterion names, driven end-to-end:

  stamp present + rows unchanged  -> FAIL   (`STAMPED_BUT_UNSERVED` / `STAMPED_BUT_UNMOVED`)
  stamp absent  + rows changed    -> FAIL   (`MOVED_WITHOUT_STAMP`)
  a legitimate flip               -> PASS   (`FLIPPED_AND_MOVED`)
  a legitimate flag-off build     -> PASS   (`INCUMBENT_CLEAN`, no fitted stamp)

Plus the FLIP's own boundaries, every one pinned TWO-SIDED: RES/PUP move, SUS/NFI do not, the
rookie frame never reaches the certified arm at all, and `fitted_status` stays unreachable.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX
from quant_sports_intel_models.football.nfl.fantasy import injury_games_policy as POLICY
from quant_sports_intel_models.football.nfl.fantasy import injury_games_publish_guard as GUARD
from quant_sports_intel_models.football.nfl.fantasy import injury_games_serving as SERVE
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP

_EX_SRC = Path(EX.__file__).read_text()
NAN = np.nan


def _code_only(src: str) -> str:
    tree = ast.parse(textwrap.dedent(src))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    return ast.unparse(tree)


def _board(stamp: str | None, served: list, incumbent: list) -> pd.DataFrame:
    """A minimal built board: the policy stamp plus the two per-row evidence columns."""
    df = pd.DataFrame({GUARD.SERVED_COL: served, GUARD.INCUMBENT_COL: incumbent})
    if stamp is not None:
        df[GUARD.STAMP_COL] = stamp
    return df


FITTED, INCUMBENT = POLICY.MODEL_VERSION, POLICY.INCUMBENT_MODEL_VERSION


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheFourLegs:
    def test_a_legitimate_flip_PASSES(self):
        r = GUARD.evaluate(_board(FITTED, [3.10, 1.02, NAN], [5.80, 7.90, NAN]))
        assert r["verdict"] == "FLIPPED_AND_MOVED" and r["passed"] is True
        assert r["n_fitted"] == 2 and r["n_moved"] == 2

    def test_a_legitimate_flag_off_build_PASSES_with_no_fitted_stamp(self):
        r = GUARD.evaluate(_board(INCUMBENT, [NAN, NAN, NAN], [5.80, 7.90, NAN]))
        assert r["verdict"] == "INCUMBENT_CLEAN" and r["passed"] is True
        assert r["claims_fitted"] is False and r["n_certified"] == 2

    def test_the_stamp_present_but_NO_ROW_SERVED_is_REFUSED(self):
        """⭐ THE NAMED FAILURE: the build forgot its feed. Certified rows were available and every
        one kept the incumbent cap, while the board stamps the fitted arm."""
        r = GUARD.evaluate(_board(FITTED, [NAN, NAN, NAN], [5.80, 7.90, NAN]))
        assert r["verdict"] == "STAMPED_BUT_UNSERVED" and r["passed"] is False
        assert "covariate feed" in r["detail"]

    def test_the_stamp_present_but_rows_UNCHANGED_is_REFUSED(self):
        """A flip that moved nothing is a claim the artifact does not support."""
        r = GUARD.evaluate(_board(FITTED, [5.80, 7.90], [5.80, 7.90]))
        assert r["verdict"] == "STAMPED_BUT_UNMOVED" and r["passed"] is False

    def test_rows_changed_with_NO_fitted_stamp_is_REFUSED(self):
        r = GUARD.evaluate(_board(INCUMBENT, [3.10, NAN], [5.80, NAN]))
        assert r["verdict"] == "MOVED_WITHOUT_STAMP" and r["passed"] is False

    def test_an_absent_stamp_column_with_moved_rows_is_ALSO_refused(self):
        """The stamp can be missing as well as wrong; both are 'the rows are not accounted for'."""
        r = GUARD.evaluate(_board(None, [3.10, NAN], [5.80, NAN]))
        assert r["verdict"] == "MOVED_WITHOUT_STAMP" and r["passed"] is False


class TestItCannotBeSatisfiedVacuously:
    def test_a_board_with_NO_certified_rows_passes_but_is_NOT_reported_as_a_clean_flip(self):
        """⭐ NF-D20: count the rows the mechanism could act on BEFORE crediting a pass. An
        off-season board has nothing to publish wrongly — that is a pass, and it is a DIFFERENT
        fact from 'the flip works', so it carries its own verdict rather than hiding inside one."""
        r = GUARD.evaluate(_board(FITTED, [NAN, NAN], [NAN, NAN]))
        assert r["verdict"] == "NO_CERTIFIED_ROWS" and r["passed"] is True
        assert r["verdict"] != "FLIPPED_AND_MOVED"
        assert "NOT evidence that the flip works" in r["detail"]

    def test_a_board_claiming_the_fitted_arm_with_NO_evidence_columns_is_UNVERIFIABLE(self):
        """NF1.7 (a): an unverifiable artifact is a failure, never a pass."""
        r = GUARD.evaluate(pd.DataFrame({GUARD.STAMP_COL: [FITTED]}))
        assert r["verdict"] == "UNVERIFIABLE" and r["passed"] is False

    def test_a_board_predating_the_story_is_an_honest_absence_not_a_failure(self):
        r = GUARD.evaluate(pd.DataFrame({"player_id": ["a"]}))
        assert r["verdict"] == "PRE_STORY_BOARD" and r["passed"] is True

    def test_two_concatenated_builds_are_a_HARD_ERROR_not_a_majority_vote(self):
        df = _board(FITTED, [3.1, 3.1], [5.8, 5.8])
        df[GUARD.STAMP_COL] = [FITTED, INCUMBENT]
        with pytest.raises(ValueError, match="distinct values"):
            GUARD.evaluate(df)


class TestTheComparisonIsMaterialNeverBitwise:
    def test_a_sub_tolerance_move_does_NOT_count_as_a_flip(self):
        """⛔ NF-INJ3c §6 (card QkpAHBYa): no board comparison in this repo may be bitwise. A cap
        that moved a row by 1e-12 did not move it in any sense an operator or a drafter can see."""
        r = GUARD.evaluate(_board(FITTED, [5.8 + 1e-12], [5.8]))
        assert r["verdict"] == "STAMPED_BUT_UNMOVED"

    def test_the_tolerance_is_a_declared_constant_and_the_guard_uses_it(self):
        assert GUARD.MATERIAL_ATOL == 1e-9
        code = _code_only(inspect.getsource(GUARD.evaluate))
        assert "MATERIAL_ATOL" in code and "np.abs(served - incumbent)" in code


class TestTheGuardReadsTheARTIFACTNotThePolicy:
    def test_the_verdict_does_not_consult_serving_enabled(self):
        """⛔ A guard that asked the policy whether serving was on would keep reading correct while
        the served board drifted — the NF-C0e class, inside the guard written to catch it."""
        code = _code_only(inspect.getsource(GUARD.evaluate))
        assert "serving_enabled" not in code
        assert "POLICY.SERVING_ENABLED" not in code

    def test_the_verdict_is_INDEPENDENT_of_the_ambient_flag(self, monkeypatch):
        moved = _board(FITTED, [3.10, NAN], [5.80, NAN])
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", False)
        off = GUARD.evaluate(moved)["verdict"]
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", True)
        assert GUARD.evaluate(moved)["verdict"] == off == "FLIPPED_AND_MOVED"

    def test_the_evidence_column_names_come_from_the_board_builder(self):
        """One owner: a rename in `season_projection` must not leave the guard reading a column
        nobody writes any more (which would silently become UNVERIFIABLE, or worse, PRE_STORY)."""
        assert (GUARD.SERVED_COL, GUARD.INCUMBENT_COL) == tuple(SP.INJURY_GAMES_EVIDENCE_COLS)


class TestItIsWiredIntoThePublishPath:
    def test_the_exporter_calls_the_guard(self):
        """⚠️ THE CALL, not the definition. The first cut of this clause matched the name anywhere
        in the module and stayed GREEN with the call site deleted — satisfied by `def
        assert_injury_games_stamp_coherent(...)` itself. That is the NF-C0e wired-vs-invoked defect
        occurring INSIDE the guard written to catch it, and only the RED proof found it."""
        code = _code_only(inspect.getsource(EX.main))
        assert "assert_injury_games_stamp_coherent(" in code, (
            "`main` no longer calls the stamp guard — it is defined and never invoked")

    def test_it_runs_beside_the_NF_K1_position_guard_before_the_upload_decision(self):
        code = _code_only(_EX_SRC)
        i_k1 = code.index("assert_published_position_coverage(out_dir")
        i_us = code.index("assert_injury_games_stamp_coherent(")
        i_pub = code.index("_maybe_publish(")
        assert i_k1 < i_us < i_pub, (
            "the stamp guard must run after the board is staged and BEFORE the upload decision")

    def test_a_failing_verdict_RAISES_SystemExit_so_it_survives_the_exporters_own_except(self):
        """⭐ LOAD-BEARING: the projections block is wrapped in `except Exception`, which does NOT
        catch `SystemExit` (a `BaseException`). A refusal raised as a plain exception would be
        swallowed and logged as 'projections.json SKIPPED'."""
        code = _code_only(inspect.getsource(EX.assert_injury_games_stamp_coherent))
        assert "raise SystemExit(" in code
        with pytest.raises(SystemExit, match="PUBLISH REFUSED"):
            EX.assert_injury_games_stamp_coherent(_board(FITTED, [5.8], [5.8]), 2026)

    def test_it_RAISES_on_a_dry_run_too_not_only_on_publish(self):
        """NF-K1's rule: a board whose provenance stamp is wrong is defective whether or not it is
        uploaded, and staging is where the operator can still act. The guard therefore takes no
        publish flag at all."""
        sig = inspect.signature(EX.assert_injury_games_stamp_coherent)
        assert "publish" not in sig.parameters and "strict" not in sig.parameters

    def test_an_unreadable_board_is_UNVERIFIED_and_never_scored_healthy(self, caplog):
        """NF1.7 (a). It must not refuse either — that would be a new refusal in a path this story
        did not measure (the exporter tolerates a missing projections artifact by design)."""
        with caplog.at_level("WARNING"):
            assert EX.assert_injury_games_stamp_coherent(None, 2026) is None
        assert any("DID NOT RUN" in r.getMessage() for r in caplog.records)
        assert not any("OK" in r.getMessage() for r in caplog.records)

    def test_the_verdict_rides_on_the_manifest_not_only_a_run_log(self):
        """E11.30: 'we checked, it came back clean' must be visible on the artifact."""
        assert 'manifest["injuryGamesStamp"] = _inj_stamp' in _EX_SRC

    def test_the_published_payload_carries_the_policy_stamp_read_off_the_board(self):
        pdf = pd.DataFrame({"injury_games_status": ["fitted_hurdle"],
                            "injury_games_model_version": [FITTED]})
        assert EX.injury_games_stamp(pdf) == {"status": "fitted_hurdle",
                                              "injury_games_model_version": FITTED}

    def test_the_payload_stamp_is_NOT_read_from_the_policy_module(self):
        code = _code_only(inspect.getsource(EX.injury_games_stamp))
        assert "POLICY" not in code and "injury_games_policy" not in code

    def test_the_per_row_evidence_is_NOT_published(self):
        """Build provenance, not a served field: shipping what the incumbent cap WOULD have said
        invites a surface to render it."""
        assert GUARD.SERVED_COL not in EX._INJURY_GAMES_COLUMNS
        assert GUARD.INCUMBENT_COL not in EX._INJURY_GAMES_COLUMNS


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE FLIP — every boundary pinned TWO-SIDED
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _serving_frame(statuses: list[str], seasons_missed: list[float] | None = None) -> pd.DataFrame:
    n = len(statuses)
    return pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)],
        "proj_status": statuses,
        "seasons_missed": (np.zeros(n) if seasons_missed is None
                           else np.asarray(seasons_missed, dtype=float)),
        "proj_games": np.full(n, 14.0),
        "onset_carryover": np.ones(n),
        "weeks_since_last_game": np.full(n, 12.0),
        "prior_games": np.full(n, 4.0),
        "log1p_prior_fp": np.full(n, 3.0),
        "is_qb": np.zeros(n),
    })


class TestTheFlipIsON:
    def test_the_committed_flag_matches_the_recorded_operator_ruling(self):
        """⭐ The flip is a RECORDED DECISION (operator ruling D5=A, 2026-08-24), so the flag and
        the record must agree. `assert_coherent` already refuses a flip that contradicts the
        study's DISPOSITION; this pins the other half — that the flag is what the ruling says."""
        assert POLICY.SERVING_ENABLED is True
        assert POLICY.serving_enabled() is True
        assert POLICY.DISPOSITION == "SHIP"
        src = Path(POLICY.__file__).read_text()
        assert "D5=A" in src, "the flip must carry the ruling that authorised it"

    def test_the_certified_population_is_still_RES_PUP_only(self):
        assert POLICY.CERTIFIED_STATUSES == ("RES", "PUP")
        assert POLICY.INCUMBENT_STATUSES == ("SUS", "NFI")
        assert not set(POLICY.CERTIFIED_STATUSES) & set(POLICY.INCUMBENT_STATUSES)

    @pytest.mark.parametrize("status", ["RES", "PUP"])
    def test_a_certified_status_MOVES_off_the_incumbent_cap(self, status, monkeypatch):
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", True)
        df = _serving_frame([status])
        got, prov = SERVE.served_injury_games(df)
        inc = SP.injury_availability_games(df)
        assert prov["path"] == "fitted_hurdle"
        assert abs(float(got[0]) - float(inc[0])) > GUARD.MATERIAL_ATOL, (
            f"{status} is certified but the fitted arm did not move it — a two-sided boundary "
            f"needs the certified side to actually differ, or the SUS/NFI side proves nothing")

    @pytest.mark.parametrize("status", ["SUS", "NFI"])
    def test_an_incumbent_held_status_does_NOT_move(self, status, monkeypatch):
        """PM boundary D2: zero live rows, exploratory channels — the constants stand until a live
        row exists and a registered read covers them.

        ⚠️ THE FIXTURE CARRIES A CERTIFIED ROW BESIDE THE HELD ONE, and that is load-bearing. The
        first cut passed a frame of one SUS/NFI row — on which `certified.any()` is False, so the
        boundary branch NEVER EXECUTES and the clause passed on a fixture the defect could not
        reach. Deleting the `np.where(certified, ...)` selection left it GREEN. A guard on an
        `and`-composed rule needs a fixture that satisfies every OTHER clause (NF-D17)."""
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", True)
        df = _serving_frame(["RES", status])
        got, prov = SERVE.served_injury_games(df)
        inc = SP.injury_availability_games(df)
        assert prov["path"] == "fitted_hurdle", "the fitted branch must actually run, or vacuous"
        assert abs(float(got[0]) - float(inc[0])) > GUARD.MATERIAL_ATOL, (
            "the certified row must move, or the held row proving nothing is meaningless")
        assert float(got[1]) == float(inc[1]), f"{status} must keep the incumbent constant"

    def test_an_unflagged_row_is_untouched_by_either_path(self, monkeypatch):
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", True)
        df = _serving_frame(["RES", None])
        got, _ = SERVE.served_injury_games(df)
        assert float(got[1]) == 14.0

    def test_a_flagged_RETURNER_keeps_the_incumbent_cap(self, monkeypatch):
        """⚠️ A READING of ruling D5=A, flagged for the PM, not a ruling — see
        `injury_games_policy.RETURNER_BOUNDARY`. NF-INJ3b's preregistration §3 EXCLUDED returners
        from the scored population (their served games compose this cap AND NF-D11's absence prior,
        so this arm's contribution is not separably recoverable), so the arm is uncertified on them.
        The live 2026 board carries FOUR such rows, and holding them makes the served population
        exactly the 22 NF-INJ3b-M measured."""
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", True)
        df = _serving_frame(["RES", "RES"], seasons_missed=[0.0, 2.0])
        got, prov = SERVE.served_injury_games(df)
        inc = SP.injury_availability_games(df)
        assert prov["n_fitted"] == 1, "only the non-returner may take the fitted arm"
        assert abs(float(got[0]) - float(inc[0])) > GUARD.MATERIAL_ATOL
        assert float(got[1]) == float(inc[1]), "the returner must keep the incumbent constant"
        assert "seasons_missed" in prov["returner_boundary"]

    def test_a_certified_row_with_a_NON_FINITE_covariate_RAISES(self, monkeypatch):
        """⚠️⚠️ MEASURED, NOT HYPOTHETICAL. `nf_inj3_injury_games._design` does `.fillna(0.0)` on
        every covariate, so a certified row the feed missed does NOT NaN and does NOT raise — it
        evaluates at the intercept-only design and returns a plausible number under the fitted
        arm's stamp. NF-INJ3b-M's feed covered only the study's 22 rows, so its FOUR flagged RES
        returners were zero-filled and every one collapsed to the SAME 0.47 games, including the
        row carrying that record's largest single point move. Column PRESENCE was checked; VALUES
        were not."""
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", True)
        df = _serving_frame(["RES", "RES"])
        df.loc[1, "onset_carryover"] = np.nan
        with pytest.raises(ValueError, match="NOT FINITE"):
            SERVE.served_injury_games(df)

    def test_a_non_finite_value_on_an_UNCERTIFIED_row_is_fine(self):
        """Two-sided: the check must not refuse a board over a row the arm will never touch."""
        df = _serving_frame(["RES", "SUS"])
        df.loc[1, "onset_carryover"] = np.nan
        got, prov = SERVE.served_injury_games(df)
        assert prov["path"] == "fitted_hurdle" and prov["n_fitted"] == 1

    def test_the_returner_boundary_lives_in_the_POLICY_not_restated_in_the_server(self):
        """Both population boundaries have exactly one home, so a future change moves one line."""
        code = _code_only(inspect.getsource(SERVE.served_injury_games))
        # ⚠️ the SERVED mask specifically, not the name anywhere in the function: the finiteness
        # pre-check also calls `certified_rows`, so a bare name match would stay GREEN with the
        # real boundary reverted (the RED proof caught exactly that).
        assert "certified = POLICY.certified_rows(df)" in code
        assert "certified = status.isin(" not in code

    def test_a_frame_without_seasons_missed_is_not_silently_broken(self):
        """A research frame that cannot express the returner condition has no returners to protect;
        it must not raise, and it must not lose the STATUS boundary either."""
        df = _serving_frame(["RES", "SUS"]).drop(columns=["seasons_missed"])
        assert list(POLICY.certified_rows(df)) == [True, False]

    def test_the_refused_arm_stays_refused_AND_unreachable(self):
        """⛔ `fitted_status` wins 4/7 folds at p=0.1265 and is far cheaper to serve, which is
        exactly why choosing it now would be picking an arm after seeing the scores (PM D2)."""
        assert "fitted_status" in POLICY.REFUSED_ARMS
        assert POLICY.ARM == "hurdle_transfer" and POLICY.ARM not in POLICY.REFUSED_ARMS
        with pytest.raises(RuntimeError, match="REFUSED_ARMS"):
            _assert_coherent_with_arm("fitted_status")

    def test_the_rookie_frame_still_never_reaches_the_certified_veteran_hurdle(self):
        """NF-INJ3c's routing — the boundary this story must NOT alter. A rookie's formal cap is the
        incumbent constants, structurally: `project_rookies` calls `injury_availability_games`
        directly and never `injury_games_serving`."""
        code = _code_only(inspect.getsource(SP.project_rookies))
        assert "injury_availability_games(" in code
        assert "served_injury_games" not in code and "injury_games_serving" not in code


def _assert_coherent_with_arm(arm: str) -> None:
    """Run the policy's own coherence check with a substituted ARM, without mutating the module."""
    import types
    ns = types.SimpleNamespace()
    for k in ("SERVING_ENABLED", "DISPOSITION", "SOURCE_MODEL", "CERTIFIED_STATUSES",
              "INCUMBENT_STATUSES", "REFUSED_ARMS"):
        setattr(ns, k, getattr(POLICY, k))
    ns.ARM = arm
    src = inspect.getsource(POLICY.assert_coherent)
    g = dict(vars(POLICY))
    g.update(ARM=arm)
    exec(compile(textwrap.dedent(src), "<policy>", "exec"), g)
    g["assert_coherent"]()


class TestTheRollbackIsTheSameCodePath:
    @pytest.mark.parametrize("status", ["RES", "PUP", "SUS", "NFI"])
    def test_serving_OFF_returns_the_incumbent_cap_byte_for_byte(self, status, monkeypatch):
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", False)
        df = _serving_frame([status])
        got, prov = SERVE.served_injury_games(df)
        assert np.array_equal(got, SP.injury_availability_games(df))
        assert prov["path"] == "incumbent"

    def test_the_row_log_is_filled_on_EVERY_path_including_the_incumbent_ones(self, monkeypatch):
        """⭐ The load-bearing half: a row log that only existed on the happy path would leave 'the
        policy is on but this build served the incumbent' indistinguishable from a board that was
        never asked to flip — which is the whole failure the guard exists to catch."""
        df = _serving_frame(["RES", "SUS"])
        for enabled, feed in ((False, None), (True, False)):
            monkeypatch.setattr(POLICY, "SERVING_ENABLED", enabled)
            rl: dict = {}
            SERVE.served_injury_games(df, feed_supplied=feed, row_log=rl)
            assert list(rl["certified"]) == [True, False]
            assert np.isfinite(rl["incumbent"]).all()
            assert not np.isfinite(rl["fitted"]).any(), "no row was produced by the fitted arm"

    def test_the_evidence_columns_distinguish_certified_from_served(self, monkeypatch):
        """`injury_games_incumbent` is filled on every CERTIFIED row and `injury_games_served` only
        where the fitted arm produced a value — the asymmetry that lets the guard tell 'forgot the
        feed' apart from 'no certified rows on this board'."""
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", True)
        df = _serving_frame(["RES", "SUS", None])
        rl: dict = {}
        SERVE.served_injury_games(df, feed_supplied=False, row_log=rl)
        rl["player_id"] = df["player_id"].astype(str).to_numpy()
        out = SP.stamp_injury_games_evidence(df.copy(), rl)
        assert np.isfinite(out["injury_games_incumbent"]).tolist() == [True, False, False]
        assert not np.isfinite(out["injury_games_served"]).any()
        assert GUARD.evaluate(out.assign(**{GUARD.STAMP_COL: FITTED})
                              )["verdict"] == "STAMPED_BUT_UNSERVED"
