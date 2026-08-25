"""test_nf_inj3b_ship_runners.py — NF-INJ3b-SHIP nodes 4+5 (the flipped diff; the D10 combined read).

What has to hold about these two runners, and why each is not obvious:

  1. NEITHER PUBLISHES. No `--publish`, no S3 write, and the flipped-diff runner never touches
     `SERVING_ENABLED` on disk. A dry-run runner that could publish is one flag away from doing so.
  2. THE FLIPPED BOARD IS THE COMMITTED ONE. NF-INJ3b-M forced the policy on in memory and supplied
     a feed by hand; if this runner did either, it would measure the same thing -M measured rather
     than the thing that would ship.
  3. THE COMPARISON IS MATERIAL AND SCOPED, NEVER BITWISE, and the rookie-band control is an
     ENVELOPE — a single draw cannot establish that a column is deterministic (the rule states a
     RANGE), and the first cut of that attribution reported a false positive because of it.
  4. THE COMBINED READ BINDS TO A BOARD, NOT A DATE, and records the publish-state it saw so a
     later reader can tell whether it still applies.
  5. NEITHER CLOBBERS A DECIDED STORY'S ARTIFACTS.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import (
    run_nf_inj3b_ship_combined_read as CR,
)
from quant_sports_intel_models.football.nfl.fantasy import (
    run_nf_inj3b_ship_flipped_diff as FD,
)

_FD_SRC = Path(FD.__file__).read_text()
_CR_SRC = Path(CR.__file__).read_text()


def _code_only(src: str) -> str:
    tree = ast.parse(textwrap.dedent(src))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    return ast.unparse(tree)


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestNeitherRunnerPublishes:
    @pytest.mark.parametrize("name", ["flipped_diff", "combined_read"])
    def test_no_publish_flag_and_no_lake_write(self, name):
        """⚠️ It asserts on the ARGUMENT and the WRITER, not on the token anywhere in the file.
        Both runners' reports SAY "no `--publish` flag exists on this runner" in their own prose, so
        a bare token scan fails on the honest sentence rather than on a real flag — the INC-38
        prose-satisfies-the-guard class, facing the other way."""
        code = _code_only(_FD_SRC if name == "flipped_diff" else _CR_SRC)
        assert 'add_argument("--publish"' not in code, f"{name} grew a publish flag"
        assert 'add_argument("--s3' not in code, f"{name} grew an S3 flag"
        for banned in ("s3io.write_dataframe", "import boto3", "boto3.client"):
            assert banned not in code, f"{name} can reach S3 ({banned})"

    def test_the_flipped_diff_never_writes_the_policy_flag(self):
        """⛔ It measures the COMMITTED flip. A runner that set the flag would be measuring its own
        assumption, and one that set it on disk would be a live flip wearing a dry run's clothes."""
        code = _code_only(_FD_SRC)
        assert "POLICY.SERVING_ENABLED =" not in code
        assert "SERVING_ENABLED = " not in code

    def test_the_flipped_diff_REFUSES_to_run_with_the_policy_OFF(self):
        """⭐ Otherwise the 'flipped' board IS the incumbent and the whole diff measures NOTHING
        while reporting a clean result — the vacuous-run class (NF1.7 (a))."""
        code = _code_only(inspect.getsource(FD.run))
        assert "if not POLICY.serving_enabled():" in code
        assert "raise RuntimeError(" in code


class TestTheFlippedBoardIsTheCommittedOne:
    def test_it_forces_nothing_and_supplies_no_feed(self):
        """NF-INJ3b-M forced the policy on IN MEMORY and hand-supplied a covariate feed, because
        neither the flip nor the feed existed. Doing either here would re-measure -M rather than
        measure what would ship."""
        code = _code_only(inspect.getsource(FD.build_flipped))
        assert "injury_covariates" not in code, "the flipped board must use the SELF-BUILT feed"
        assert "serving_on" not in code, "the flipped board must not force the policy"
        assert "NF15.build_season_projection(" in code

    def test_it_refuses_a_board_whose_NF1_5_reorder_was_a_NO_OP(self):
        """A no-op re-order silently removes the give-back and produces the proportional answer in
        disguise (NF-INJ3b-M's own first-cut defect)."""
        assert "_assert_reorder_fired(" in _code_only(inspect.getsource(FD.build_flipped))


class TestTheComparisonIsMaterialAndScoped:
    def test_the_tolerance_is_declared_and_is_not_bitwise(self):
        assert FD.RTOL == FD.ATOL == 1e-9

    def test_material_treats_a_sub_tolerance_move_as_unchanged(self):
        a = pd.Series([1.0, 2.0, 3.0])
        b = pd.Series([1.0 + 1e-12, 2.0 + 1.0, 3.0])
        assert list(FD._material(a, b)) == [False, True, False]

    def test_material_treats_NaN_vs_NaN_as_unchanged(self):
        """A column both boards leave empty has not moved; counting it would make every all-NaN
        provenance column look like a change on every run."""
        a = pd.Series([np.nan, 1.0])
        b = pd.Series([np.nan, 1.0])
        assert not FD._material(a, b).any()

    def test_the_diff_is_scoped_by_population(self):
        code = _code_only(inspect.getsource(FD._scoped_diff))
        for pop in ("rookie", "veteran_fitted", "veteran_other"):
            assert pop in code


class TestTheRookieBandControlIsAnEnvelope:
    def _diffs(self, counts, mags):
        return [{"populations": {"rookie": {"columns": {
            "fp_ppr_sd": {"n_moved": c, "max_abs": m},
            "fp_ppr_p10": {"n_moved": 0, "max_abs": 0.0},
            "fp_ppr_p90": {"n_moved": 0, "max_abs": 0.0}}}}}
            for c, m in zip(counts, mags)]

    def _flip(self, n, mx):
        return {"populations": {"rookie": {"columns": {
            "fp_ppr_sd": {"n_moved": n, "max_abs": mx},
            "fp_ppr_p10": {"n_moved": 0, "max_abs": 0.0},
            "fp_ppr_p90": {"n_moved": 0, "max_abs": 0.0}}}}}

    def test_a_move_INSIDE_the_control_envelope_is_NOT_attributed(self):
        """⚠️ THE DEFECT THIS EXISTS FOR, and it is measured not hypothetical. The first cut read
        ONE control; that draw moved 0 `fp_ppr_sd` cells, the flipped board moved 3 by 0.01, and it
        came back ATTRIBUTABLE for a quantity the flip structurally cannot touch. The rule states a
        RANGE (0-21 cells), so one draw that moves nothing establishes nothing (NF-D20)."""
        r = FD._rookie_band_attribution(self._flip(3, 0.01),
                                        self._diffs([0, 11, 4, 0, 7], [0.0, 0.13, 0.1, 0.0, 0.1]))
        assert r["per_column"]["fp_ppr_sd"]["attributable_to_the_flip"] is False
        assert r["any_attributable"] is False
        assert r["per_column"]["fp_ppr_sd"]["control_moved_range"] == [0, 11]

    def test_a_move_OUTSIDE_the_envelope_IS_attributed(self):
        """Two-sided: an envelope that can never fire is worse than no check."""
        r = FD._rookie_band_attribution(self._flip(40, 9.0),
                                        self._diffs([0, 11, 4, 0, 7], [0.0, 0.13, 0.1, 0.0, 0.1]))
        assert r["per_column"]["fp_ppr_sd"]["attributable_to_the_flip"] is True
        assert r["any_attributable"] is True

    def test_a_single_control_draw_is_refused_as_a_DEFAULT(self):
        """The default must not be the setting that produced the false positive."""
        sig = inspect.signature(FD.run)
        assert sig.parameters["n_controls"].default >= 3

    def test_the_envelope_is_reported_whether_or_not_anything_is_attributed(self):
        r = FD._rookie_band_attribution(self._flip(1, 0.01), self._diffs([0, 2], [0.0, 0.1]))
        for v in r["per_column"].values():
            assert "control_moved_range" in v and "n_controls" in v


class TestTheAnchorCheck:
    def test_it_reproduces_on_the_measured_figures(self):
        a = FD._anchor_check({"mean_d_proj_games": -2.6104, "mean_d_pts_ppr": -1.4402,
                              "n_flagged": 22})
        assert a["reproduces"] is True

    def test_an_order_of_magnitude_divergence_FAILS(self):
        """The anchor is a HALT condition, not a gate: a materially different number means the
        committed flip is not what the operator accepted."""
        a = FD._anchor_check({"mean_d_proj_games": -0.2, "mean_d_pts_ppr": -0.1, "n_flagged": 22})
        assert a["reproduces"] is False
        assert "HALT" in a["if_it_fails"]

    def test_the_anchor_is_the_RECORDED_M_figure_not_a_number_chosen_here(self):
        assert FD.ANCHOR["mean_d_proj_games"] == -2.6104
        assert FD.ANCHOR["mean_d_pts_ppr"] == -1.2341


class TestTheCombinedReadBindsToABoard:
    def test_it_reads_a_STAGED_directory_not_S3(self):
        """⚠️ The S3 read is the board already PUBLISHED and structurally cannot show a change that
        has not shipped. The decision-relevant board is the one that WOULD ship."""
        code = _code_only(inspect.getsource(CR.placement))
        assert "PR.run(staged, origin=None)" in code
        assert "_S3" not in code and "_fetch" not in code

    def test_it_records_the_publish_state_the_read_is_valid_FOR(self):
        """⚠️ It asserts on the RETURNED DICT, not on the identifier appearing in the function. The
        `binds_to` sentence NAMES all three keys to explain what invalidates the read, so a source
        scan is satisfied by the prose with the fields deleted (the RED proof caught exactly that —
        the INC-38 class, this time with the explanation satisfying the guard)."""
        blob = {"players": [{"rookie": True}, {"rookie": False}]}
        import json as _json
        d = pytest.importorskip("pathlib")
        tmp = d.Path(__import__("tempfile").mkdtemp())
        (tmp / "projections.json").write_text(_json.dumps(
            {"season": 2026, **blob, "injury_games_policy": {"status": "fitted_hurdle"}}))
        (tmp / "manifest.json").write_text(_json.dumps({"reportedAbsenceCount": 3}))
        state = CR.publish_state(tmp)
        assert state["reported_absence_count"] == 3
        assert state["n_rookie_rows"] == 1
        assert state["injury_games_policy"] == {"status": "fitted_hurdle"}
        assert "RE-RUN" in state["binds_to"]

    def test_it_says_so_when_the_state_changes(self):
        assert "binds_to" in _code_only(inspect.getsource(CR.publish_state))
        assert "RE-RUN" in _CR_SRC

    def test_a_missing_staged_board_RAISES_rather_than_reporting_a_pass(self, tmp_path):
        with pytest.raises(SystemExit, match="no staged board"):
            CR.run(tmp_path, "x.duckdb", tmp_path)

    def test_it_writes_under_its_OWN_stem_never_a_decided_one(self):
        """The D4 rule: a post-decision story never clobbers a decided story's audit trail."""
        assert CR._INTERVAL_STEM.startswith("nf_inj3b_ship_")
        code = _code_only(inspect.getsource(CR.interval))
        assert "'--out'" in code and "_INTERVAL_STEM" in code

    def test_it_MEASURES_that_the_decided_artifacts_are_intact(self):
        """MEASURED at the call site, never assumed from the runners' source (NF-C0e)."""
        code = _code_only(inspect.getsource(CR.run))
        assert "before = _digests()" in code and "after = _digests()" in code
        names = {p.name for p in CR._DECIDED}
        assert names == {"nf_tr2b_placement_read.json", "nf1_9_interval_revalidation.json"}
