"""test_nf_inj3b_m_counterfactual.py — NF-INJ3b-M nodes 3+4.

The counterfactual is what closes NF-INJ3b's blocking §5(d). Three things make it a MEASUREMENT
rather than an estimate, and each is guarded here:

  1. the wiring is INERT with the policy off — the served board is the incumbent, byte-for-byte;
  2. NF1.5's re-order must actually FIRE — a no-op silently removes the give-back the whole story
     exists to measure, and produces a confident number that is the proportional answer in disguise;
  3. nothing publishes — no `--publish`, no lake write, and the on-disk flip stays False.

⭐ (2) is not hypothetical: this story's own first cut passed the wrong report suffix, NF1.5 scored
**0 of 758** veterans, and the diff still ran and printed a number.
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import injury_games_policy as POLICY
from quant_sports_intel_models.football.nfl.fantasy import injury_games_serving as SERVE
from quant_sports_intel_models.football.nfl.fantasy import nf_inj3_injury_games as IG
from quant_sports_intel_models.football.nfl.fantasy import (
    run_nf_inj3b_m_counterfactual as CF,
)
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP

_CF_SRC = Path(CF.__file__).read_text()
_SP_SRC = Path(SP.__file__).read_text()


def _code_only(src: str) -> str:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    return ast.unparse(tree)


def _board(n: int = 40, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    st = np.array((["RES"] * 2 + ["PUP"] + ["SUS"] + [None] * 6) * (n // 10 + 1),
                  dtype=object)[:n]
    return pd.DataFrame({"proj_status": st, "proj_games": rng.uniform(1, 17, n)})


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheWiringIsInertUntilTheOperatorFlipsIt:
    def test_the_injury_step_is_ROUTED_through_the_policy(self):
        """Wired, and provably wired at the real call site — not just importable (NF-C0e)."""
        code = _code_only(_SP_SRC)
        assert "served_injury_games" in code, "the injury step no longer routes through the policy"
        assert "injury_covariates" in code, "the covariate feed is gone"

    @pytest.mark.parametrize("blend", [0.7, 0.3, 1.0])
    def test_with_the_policy_OFF_the_served_games_are_the_incumbent_byte_for_byte(
            self, blend, monkeypatch):
        """⭐ The rollback IS the same code path, at every blend the caller may pass — a wiring that
        only matches at the DEFAULT blend would silently change any non-default caller.

        ⭐ RE-ANCHORED by NF-INJ3b-SHIP. This clause used to read the AMBIENT flag (`assert
        POLICY.SERVING_ENABLED is False`), which was true only while the story was deploy-held; once
        operator ruling D5=A flipped it, that assertion described a retired world. The PROPERTY it
        defends — the rollback path is byte-identical to the incumbent — did not change and is now
        driven explicitly, which also makes it strictly stronger: it holds whatever the ambient flag
        is, so it survives the next flip in either direction (MH2.7 (ii): re-anchor, never delete)."""
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", False)
        df = _board()
        got, prov = SERVE.served_injury_games(df, eg=df["proj_games"].to_numpy(), blend=blend)
        want = SP.injury_availability_games(df, blend=blend)
        assert np.array_equal(got, want)
        assert prov["path"] == "incumbent"

    def test_a_flipped_on_policy_that_INTENDS_to_serve_but_lacks_covariates_RAISES(self, monkeypatch):
        """⛔ It must never fall back to the incumbent while stamping the fitted arm's version —
        that would serve one model under another's name (NF-C0e)."""
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", True)
        df = _board()                              # carries NO design covariates
        assert SERVE.missing_covariates(df), "fixture already has the covariates — vacuous"
        with pytest.raises(ValueError, match="covariate"):
            SERVE.served_injury_games(df)          # feed_supplied unset ⇒ intends to serve

    def test_a_call_site_that_DECLARES_no_feed_gets_the_incumbent_and_it_is_RECORDED(
            self, monkeypatch):
        """⭐ MEASURED, not hypothetical: `project_veterans` is also called by NF1.5's INTERNAL
        research-frame assembly, which has no feed. Forcing the policy on process-wide made every
        such call demand covariates and the whole build died. The distinction is EXPLICIT — a
        caller DECLARES it is not serving — and the incumbent path is recorded, never silent."""
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", True)
        df = _board()
        got, prov = SERVE.served_injury_games(df, feed_supplied=False)
        want = SP.injury_availability_games(df)
        assert np.array_equal(got, want)
        assert prov["path"] == "incumbent_no_feed"
        assert prov["model_version"] == POLICY.INCUMBENT_MODEL_VERSION
        assert "no covariate feed" in prov["reason"]

    def test_season_projection_DECLARES_whether_it_supplied_a_feed(self):
        """The call site must pass the declaration — otherwise the strict branch is unreachable and
        the whole distinction is décor (NF-C0e: wired ≠ invoked)."""
        code = _code_only(_SP_SRC)
        assert "feed_supplied=injury_covariates is not None" in code.replace("(", "").replace(")", "")


class TestTheReorderMustActuallyFire:
    """⭐ THE DEFECT THIS STORY HIT: NF1.5 scoring 0 of 758 veterans removes the give-back, and the
    diff still produces a number."""

    def test_a_no_op_reorder_is_REFUSED(self):
        with pytest.raises(RuntimeError, match="NO-OP"):
            CF._assert_reorder_fired({"eligible": np.zeros(758, dtype=bool)})

    def test_a_reorder_that_fired_is_accepted(self):
        elig = np.zeros(758, dtype=bool)
        elig[:500] = True
        CF._assert_reorder_fired({"eligible": elig})          # must not raise

    def test_an_UNVERIFIABLE_reorder_is_refused_not_assumed(self):
        """NF1.7 (a): a check that could not run is never a pass."""
        with pytest.raises(RuntimeError, match="cannot be verified"):
            CF._assert_reorder_fired({})

    def test_the_builder_reads_the_shipped_captures_own_record(self):
        """The `capture` OUT-param is the build's own account of what it did — not a re-derivation
        of the ordering here, which would drift (NF-C0e)."""
        src = _code_only(inspect.getsource(CF.build_board_frame))
        assert "capture=cap" in src and "_assert_reorder_fired(cap)" in src

    def test_an_empty_nf1_5_selection_is_refused_before_the_build(self):
        """Resolved ONCE in `nf15_inputs` (hoisted out of the three builds), so the refusal lives
        there — and it must run BEFORE any board is built."""
        src = _code_only(inspect.getsource(CF.nf15_inputs))
        assert re.search(r"if not sel:", src), "an empty selection would silently no-op the re-order"
        assert "stage1" in src, "a report with no stage1 must also be refused"


class TestNothingPublishes:
    def test_the_runner_has_no_publish_flag_and_no_lake_write(self):
        """⚠️ Match a real ARGV FORM, not a substring: the packet's own PROSE explains that there is
        no `--publish` flag, and a bare substring scan is satisfied by that sentence (INC-38's
        prose-cannot-satisfy lesson, facing the other way — here prose FAILED a correct guard)."""
        code = _code_only(_CF_SRC)
        assert not re.search(r'add_argument\(\s*[\'"]--publish', code), "a --publish flag exists"
        assert "s3io" not in code and "write_dataframe" not in code

    def test_the_counterfactual_forces_the_flag_IN_MEMORY_and_restores_it(self):
        """⭐ RE-ANCHORED by NF-INJ3b-SHIP, and the rename is the honest part. While NF-INJ3b-M ran,
        the on-disk flag was `False` and this clause asserted it — the counterfactual must not have
        been a live flip. Operator ruling D5=A has since flipped it deliberately, so an assertion
        that it is `False` would now pin a RETIRED decision and would fail for a reason that has
        nothing to do with the counterfactual's own honesty.

        What that honesty actually rests on is unchanged and is what is asserted here: the runner
        forces the flag IN MEMORY and RESTORES THE PREVIOUS VALUE in a `finally` — so it can neither
        leak a flip nor, now, leak a rollback. The on-disk flag's agreement with the recorded PM
        ruling is pinned by `test_nf_inj3b_ship_flip.py`, where it belongs."""
        src = _code_only(inspect.getsource(CF.build_board_frame))
        # forced on, and restored in a finally — a counterfactual that leaked would be a live flip
        assert "POLICY.SERVING_ENABLED = bool(serving_on)" in src
        assert "POLICY.SERVING_ENABLED = prev_flag" in src
        assert "finally" in inspect.getsource(CF.build_board_frame)

    def test_the_report_records_that_the_disk_flag_was_never_changed(self):
        assert "serving_enabled_on_disk" in _CF_SRC
        assert "forced_on_in_memory_for_the_counterfactual_only" in _CF_SRC


class TestTheMeasurementIsHonest:
    def test_a_noise_floor_is_measured_from_a_REPLICATE_build(self):
        """⭐ The board build is NOT bit-deterministic run to run, so a diff that credited every
        non-zero delta would be reporting the build's own noise."""
        code = _code_only(_CF_SRC)
        assert "_noise_floor(" in code
        assert code.count("build_board_frame(") >= 3, (
            "the baseline must be built TWICE (baseline + replicate) plus the counterfactual")

    def test_superflex_is_read_separately_because_the_VOR_shield_does_not_cover_it(self):
        assert CF.SUPERFLEX_CONFIGS == ("superflex_10", "superflex_12")
        assert set(CF.SUPERFLEX_CONFIGS) <= {s for s, _, _ in CF.CONFIGS}
        assert "ADDITIVE-ONLY" in _CF_SRC

    def test_every_published_config_is_read_including_both_team_counts(self):
        stems = {s for s, _, _ in CF.CONFIGS}
        assert len(stems) == 14, stems
        for preset in ("standard", "standard_3wr", "half_ppr", "half_ppr_3wr",
                       "full_ppr", "full_ppr_3wr", "superflex"):
            assert {f"{preset}_10", f"{preset}_12"} <= stems

    def test_the_covariate_feed_is_taken_from_the_bake_offs_own_builder(self):
        src = _code_only(inspect.getsource(CF.injury_covariates))
        assert "R3.build_population" in src, "re-deriving the covariates would drift (NF-C0e)"
        assert "REQUIRED_COVARIATES" in src

    def test_no_proportional_shortcut_appears_anywhere(self):
        """§5(d) forbids `pts x arm_games / incumbent_games`. Both boards are BUILT."""
        code = _code_only(_CF_SRC)
        assert "build_board_frame" in code
        assert not re.search(r"proj_fp_ppr.*\*.*proj_games.*/", code)
