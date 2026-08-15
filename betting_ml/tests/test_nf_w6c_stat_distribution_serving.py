"""Guards for NF-W6c — the NF-W6b per-stat distributions wired onto the served raw line.

Fast-gate, no lake IO: everything exercises the PURE serving module
(`quant_sports_intel_models.football.nfl.fantasy.stat_distribution_serving`) plus committed
records; the runners are imported only inside test methods (their module scope is IO-free).

WHAT THIS SUITE IS DEFENDING, and why each clause exists:
  · this is a WIRING story, so the load-bearing risk is a SECOND IMPLEMENTATION — a serving copy
    of the hurdle/quantile/tail/mixture that drifts from the certified one (MH2.1 (b): serve the
    object that was validated). `TestNoSecondImplementation` makes that mechanically impossible
    to ship, not merely discouraged;
  · the served set must be exactly the record's SHIP verdicts — a null or CLOSED cell quietly
    riding this story's infrastructure into serving is the failure PM Decisions B/C forbid;
  · the served representation is a CONTRACT read by consumers, so its pins are asserted against
    the NF-W6b RECORD, never against the code that produces them (a test that reads a value back
    under the key the code wrote is a restatement of the code — NF-C0e);
  · the deploy hold rests on the registry STATUS field, so it is proved TWO-SIDED (NF-W2b): the
    staged entry is invisible to the serving-facing query, and the same query WOULD see it if its
    status were champion.

Discipline inherited from the NF-W3/W6b/MARGIN suites: every clause has an ISOLATING fixture
(every other clause satisfied, so only the clause under test can flip the result — NF-D17);
iterating guards assert NON-VACUITY first (an empty match set passes on nothing — DSR-CONV);
source scans run comment-stripped and structural checks use AST, so prose can neither satisfy nor
trip them (INC-38).
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from betting_ml.governance import gates as G
from betting_ml.governance import registry as R
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import stat_distribution_serving as SDS
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions as SD
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

_MODULE = Path(SDS.__file__)
_FANTASY = _MODULE.parent
_BUILD_RUNNER = _FANTASY / "run_nf_w6c_serve_stat_distributions.py"
_STAGE_RUNNER = _FANTASY / "run_nf_w6c_stage_registry.py"
_RECORD_JSON = _FANTASY / "ablation_results" / "nf_w6b_stat_distributions.json"
_RECORD_MD = _FANTASY / "ablation_results" / "nf_w6b_stat_distributions.md"

#: The six cells NF-W6b shipped — restated here ONLY so a silent edit to both the module and the
#: record still fails; the record is the authority and is checked against it below.
EXPECTED_SERVED = {
    "QB|passing_tds", "QB|passing_yards", "QB|rushing_yards",
    "RB|rushing_yards", "TE|receiving_yards", "WR|receiving_yards",
}


def _stripped(path: Path) -> str:
    """Source with line comments removed — so an explanatory comment can neither satisfy nor trip
    a scan (INC-38: a guard prose can satisfy is vacuous)."""
    return "\n".join(ln.split("#", 1)[0] for ln in path.read_text().splitlines())


def _code_only(path: Path) -> str:
    """Source with EVERY docstring removed as well — the strictest form, for scans whose banned
    token legitimately appears in the module's own prose."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        body = getattr(node, "body", [])
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


def _record() -> dict:
    return json.loads(_RECORD_JSON.read_text())


def _good_bank(n: int = 5, atom_levels: int = 40) -> np.ndarray:
    """A well-formed served bank: finite, monotone, (n, 199), with a real zero atom."""
    row = np.concatenate([np.zeros(atom_levels),
                          np.linspace(0.5, 60.0, SDS.N_LEVELS - atom_levels)])
    return np.repeat(row[None, :], n, axis=0)


def _serve_frame(n_per_pos: int = 3) -> pd.DataFrame:
    """A minimal serve frame carrying every identity column the served rows need."""
    rows = []
    for i, pos in enumerate(SD.POSITIONS):
        for j in range(n_per_pos):
            rows.append({"gsis_id": f"00-{i}{j}", "position": pos, "team": "AAA",
                         "season": 2025, "week": 18, "gw": 174})
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestServedSetIsTheRecordsShipVerdicts:
    """The served cells are exactly what the gates certified — nothing more, nothing less."""

    def test_the_record_parses_and_is_non_vacuous(self):
        """⭐ Every clause below reads the record; if it stopped parsing they would pass on
        nothing (DSR-CONV). This is the anti-vacuity anchor for the whole class."""
        rec = _record()
        ship = {c for c, v in rec["verdict"]["cells"].items() if v == "SHIP"}
        assert len(ship) == 6, f"the record no longer carries 6 SHIP cells: {sorted(ship)}"
        assert len(rec["selections"]) == 8, (
            f"the record no longer carries all 8 contested cells: {sorted(rec['selections'])}")

    def test_served_cells_are_exactly_the_records_ship_cells(self):
        ship = {c for c, v in _record()["verdict"]["cells"].items() if v == "SHIP"}
        assert set(SDS.SERVED_CELLS) == ship == EXPECTED_SERVED, (
            f"SERVED_CELLS {set(SDS.SERVED_CELLS)} != the record's SHIP set {ship}")

    def test_each_served_form_is_the_records_winner_for_that_cell(self):
        sels = _record()["selections"]
        assert SDS.SERVED_CELLS, "no served cells — this loop would pass on nothing"
        for cell, form in SDS.SERVED_CELLS.items():
            assert form == sels[cell]["winner"], (
                f"{cell}: serving {form!r} but the record certified {sels[cell]['winner']!r} — "
                f"serving a form the gates did not select (MH2.1 (b))")

    def test_the_recorded_nulls_are_withheld_not_served(self):
        rec = _record()["verdict"]["cells"]
        nulls = {c for c, v in rec.items() if v != "SHIP"}
        assert nulls, "the record shows no null cells — this clause would pass on nothing"
        assert set(SDS.WITHHELD_NULL_CELLS) == nulls, (
            f"withheld set {set(SDS.WITHHELD_NULL_CELLS)} != the record's nulls {nulls}")
        assert not (set(SDS.SERVED_CELLS) & nulls), "a recorded NULL cell is being served"

    def test_the_closed_td_no_cells_can_never_be_served(self):
        assert SDS.CLOSED_CELLS == SD.CLOSED_CELLS, "the CLOSED set drifted from the pure module"
        assert not (set(SDS.SERVED_CELLS) & set(SDS.CLOSED_CELLS)), (
            "a CLOSED TD-NO cell is being served — re-opening needs a different MECHANISM")

    def test_the_points_hurdle_champion_is_untouched(self):
        """NF-W6b never tested total fantasy points and never beat it — these sit BESIDE it."""
        stats = {c.split("|", 1)[1] for c in SDS.SERVED_CELLS}
        assert stats and "fantasy_points" not in stats, (
            "a served cell targets total fantasy points — the points champion is out of scope")
        assert stats <= set(SD.STATS), f"served stats {stats} escape the NF-W6b stat set"


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestNoSecondImplementation:
    """The serving module POINTS at the certified constructions; it does not restate them.

    ⭐ The clause that matters most in a wiring story. A drifted serving copy of the hurdle or the
    tail would pass every representation check while serving a different object than the one the
    gates certified."""

    def test_dispatch_targets_are_the_certified_arm_functions_by_identity(self):
        assert SDS.ARM_DISPATCH, "empty dispatch — this loop would pass on nothing"
        assert SDS.ARM_DISPATCH["lgbm_quantile_tail"] is SD.arm_lgbm_quantile_tail
        assert SDS.ARM_DISPATCH["lgbm_hurdle_tail"] is SD.arm_lgbm_hurdle_tail

    def test_the_knn_adapter_calls_the_certified_function_and_nothing_else(self):
        """The one wrapper — it exists to normalize a return shape, not to fit anything."""
        tree = ast.parse(_MODULE.read_text())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_knn")
        calls = {ast.unparse(c.func) for c in ast.walk(fn) if isinstance(c, ast.Call)}
        assert calls == {"SD.arm_knn_quantile"}, (
            f"_knn calls {calls} — it must do nothing but delegate to the certified arm")

    def test_the_serving_module_imports_no_learner_at_all(self):
        """A re-implementation would need one. Neither lightgbm nor sklearn may appear."""
        tree = ast.parse(_MODULE.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported, "no imports parsed — this clause would pass on nothing"
        for banned in ("lightgbm", "sklearn", "lgb"):
            assert banned not in imported, (
                f"the serving module imports {banned!r} — a learner here means a SECOND "
                f"implementation of a certified construction (MH2.1 (b))")

    def test_the_serving_module_defines_no_construction_of_its_own(self):
        """No fit/predict verb reaches the module's CODE: it slices, encodes and checks.

        Scanned over `ast.unparse`d code with every docstring dropped, so neither the module's own
        prose (which necessarily says "fit") nor a comment can satisfy or trip it (INC-38)."""
        code = _code_only(_MODULE)
        assert "def serve_banks" in code, "the code scan lost the module — it would be vacuous"
        for verb in (".fit(", ".predict(", ".predict_proba(", "mixture_quantiles"):
            assert verb not in code, (
                f"{verb!r} appears in the serving module's CODE — constructions live in "
                f"`stat_distributions`; this module only dispatches")

    def test_every_served_form_has_a_dispatch_entry(self):
        assert SDS.SERVED_CELLS, "no served cells — this loop would pass on nothing"
        for cell, form in SDS.SERVED_CELLS.items():
            assert form in SDS.ARM_DISPATCH, f"{cell}: form {form!r} has no dispatch entry"

    def test_the_feature_set_is_the_champion_set_unchanged(self):
        assert SDS.FEATURES == list(WP.FEATURES), (
            "the served feature set drifted from the champion set — ⛔ no new features (the "
            "NF-W6b prereg constraint carries to serving)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestServedRepresentationMatchesTheRecord:
    """The 199-level contract is asserted against the RECORD, not against the code."""

    def test_the_grid_is_the_one_source_of_levels(self):
        assert SDS.EVAL_LEVELS is MC.EVAL_LEVELS, (
            "the served grid is a COPY of MC.EVAL_LEVELS — one source, or the two drift")
        assert SDS.N_LEVELS == 199

    def test_the_index_pins_come_from_the_records_own_consumer_contract(self):
        """The record states the reading rule in prose; the module must implement THAT rule."""
        md = _RECORD_MD.read_text()
        m = re.search(r"q10/q90 at indices\s*(\d+)\s*/\s*(\d+)", md)
        assert m, "the record no longer states its q10/q90 index pin — the anchor is gone"
        assert (SDS.IDX_Q10, SDS.IDX_Q90) == (int(m.group(1)), int(m.group(2))), (
            f"module indices ({SDS.IDX_Q10}, {SDS.IDX_Q90}) disagree with the record's "
            f"({m.group(1)}, {m.group(2)})")
        assert SDS.IDX_Q50 == int(np.searchsorted(MC.EVAL_LEVELS, 0.50))

    def test_the_record_pins_the_199_level_representation(self):
        md = _RECORD_MD.read_text()
        assert "(n, 199) MONOTONE quantile bank" in md, (
            "the record no longer pins the 199-level monotone representation")
        assert SDS.representation_manifest()["levels"] == 199

    def test_the_atom_reading_is_the_share_of_grid_levels_at_zero(self):
        """P(0) is read off the bank exactly as the record says consumers must read it."""
        atom = 40
        enc = SDS.encode_bank(_good_bank(n=2, atom_levels=atom))
        assert np.allclose(enc["p_zero"], atom / SDS.N_LEVELS)

    def test_the_summaries_are_level_index_reads_of_the_bank(self):
        bank = _good_bank(n=3, atom_levels=10)
        enc = SDS.encode_bank(bank)
        assert np.allclose(enc["q10"], bank[:, SDS.IDX_Q10])
        assert np.allclose(enc["q50"], bank[:, SDS.IDX_Q50])
        assert np.allclose(enc["q90"], bank[:, SDS.IDX_Q90])
        assert np.allclose(enc["mean"], bank.mean(axis=1))


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheRepresentationCheckFailsClosed:
    """One isolating fixture per clause: the base bank satisfies every OTHER clause, so only the
    clause under test can flip the verdict (NF-D17)."""

    def test_the_base_fixture_passes_so_each_break_below_is_attributable(self):
        SDS.assert_served_representation(_good_bank(), "QB|passing_yards")

    def test_a_wrong_width_bank_is_refused(self):
        with pytest.raises(ValueError, match="expected"):
            SDS.assert_served_representation(_good_bank()[:, :-1], "QB|passing_yards")

    def test_a_non_finite_bank_is_refused(self):
        bad = _good_bank()
        bad[1, 100] = np.nan
        with pytest.raises(ValueError, match="non-finite"):
            SDS.assert_served_representation(bad, "QB|passing_yards")

    def test_a_non_monotone_bank_is_refused_not_silently_sorted(self):
        """⭐ The serving boundary must not repair what it is there to detect."""
        bad = _good_bank()
        bad[0, 150], bad[0, 151] = bad[0, 151], bad[0, 150] - 5.0
        with pytest.raises(ValueError, match="monotone"):
            SDS.assert_served_representation(bad, "QB|passing_yards")

    def test_a_row_count_mismatch_between_slice_and_bank_is_refused(self):
        serve = _serve_frame().query("position == 'QB'").reset_index(drop=True)
        with pytest.raises(ValueError, match="disagree"):
            SDS.served_rows(serve, _good_bank(n=len(serve) + 1), "QB|passing_yards")

    def test_served_rows_refuses_a_slice_of_the_wrong_position(self):
        serve = _serve_frame().query("position == 'RB'").reset_index(drop=True)
        with pytest.raises(ValueError, match="position"):
            SDS.served_rows(serve, _good_bank(n=len(serve)), "QB|passing_yards")

    def test_a_summary_producer_that_drifts_from_the_declared_contract_is_refused(self,
                                                                                  monkeypatch):
        """SUMMARY_COLUMNS is a DECLARATION; this is the consumer that makes it real."""
        monkeypatch.setattr(SDS, "encode_bank",
                            lambda bank: {"p_zero": np.zeros(len(bank))})
        serve = _serve_frame().query("position == 'QB'").reset_index(drop=True)
        with pytest.raises(ValueError, match="drifted"):
            SDS.served_rows(serve, _good_bank(n=len(serve)), "QB|passing_yards")

    def test_served_rows_emits_the_identity_and_summary_contract(self):
        serve = _serve_frame().query("position == 'QB'").reset_index(drop=True)
        out = SDS.served_rows(serve, _good_bank(n=len(serve)), "QB|passing_yards")
        for col in ("cell", "stat", "form", *SDS.ID_COLUMNS, *SDS.SUMMARY_COLUMNS, "quantiles"):
            assert col in out.columns, f"served rows are missing {col!r}"
        assert len(out["quantiles"].iloc[0]) == SDS.N_LEVELS


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestServingTrainContainment:
    """Serving with MORE data than was certified is the safe direction — and it is MEASURED."""

    @staticmethod
    def _feat(max_gw: int = 20) -> pd.DataFrame:
        return pd.DataFrame({"gw": np.repeat(np.arange(max_gw + 1), 4),
                             "position": list(SD.POSITIONS) * (max_gw + 1)})

    def test_the_serving_train_contains_the_purged_fold_train(self):
        out = SDS.assert_serving_train_is_a_superset(self._feat(), serve_gw=20)
        assert out["n_serving_train"] > out["n_fold_train"] > 0
        assert out["extra_rows_vs_fold_train"] == out["n_serving_train"] - out["n_fold_train"]
        assert out["purge_weeks"] == WP.PURGE_WEEKS

    def test_an_empty_fold_train_is_refused_rather_than_passing_vacuously(self):
        """⭐ NF1.7 (a): a containment that holds because one side is empty proves nothing."""
        with pytest.raises(ValueError, match="EMPTY"):
            SDS.assert_serving_train_is_a_superset(self._feat(max_gw=5), serve_gw=0)

    def test_a_serving_train_that_drops_fold_rows_is_refused(self, monkeypatch):
        """The isolating break: keep the fold rule, shrink the serving rule below it."""
        monkeypatch.setattr(SDS, "serving_train_mask",
                            lambda feat, gw: (pd.to_numeric(feat["gw"]) < gw - 5).to_numpy(bool))
        with pytest.raises(ValueError, match="does not contain"):
            SDS.assert_serving_train_is_a_superset(self._feat(), serve_gw=20)

    def test_the_serving_mask_never_includes_the_served_week(self):
        feat = self._feat()
        assert not SDS.serving_train_mask(feat, 20)[feat["gw"].to_numpy() >= 20].any(), (
            "the serving train reaches the served week — the fit would see its own target")


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestSharedFitsAreAnIdentityNotAnApproximation:
    """Two cells sharing one (arm, stat) fit is legitimate because `SD.arm_*` takes no position
    argument — so the shared call and a per-cell call return the same rows. Proved with a stub."""

    @staticmethod
    def _stub_dispatch(calls: list):
        def _arm(train, serve, features, stat):
            calls.append((stat, len(serve)))
            base = np.arange(len(serve), dtype=float)[:, None]
            return base + np.linspace(0.0, 1.0, SDS.N_LEVELS)[None, :], {"stub": True}
        return _arm

    def test_the_six_cells_need_exactly_four_distinct_fits(self):
        keys = SDS.served_fit_keys()
        assert len(keys) == 4, f"expected 4 distinct (arm, stat) fits, got {keys}"
        assert len(SDS.SERVED_CELLS) == 6
        assert ("lgbm_hurdle_tail", "rushing_yards") in keys
        assert ("lgbm_hurdle_tail", "receiving_yards") in keys

    def test_each_distinct_fit_is_dispatched_once_over_the_whole_serve_frame(self, monkeypatch):
        calls: list = []
        monkeypatch.setattr(SDS, "ARM_DISPATCH",
                            {k: self._stub_dispatch(calls) for k in SDS.ARM_DISPATCH})
        serve = _serve_frame(n_per_pos=3)
        banks, notes = SDS.serve_banks(serve, serve)
        assert len(calls) == len(SDS.served_fit_keys()), (
            f"{len(calls)} fits for {len(SDS.served_fit_keys())} distinct (arm, stat) keys")
        assert {n for _, n in calls} == {len(serve)}, (
            "a fit did not see the whole serve frame — NF-W6b scored the full frame and sliced "
            "after, and the slice-after order is what makes the rows byte-identical")
        assert set(banks) == set(SDS.SERVED_CELLS)
        assert notes["n_fits"] == len(SDS.served_fit_keys())

    def test_cells_sharing_a_fit_receive_their_own_position_rows(self, monkeypatch):
        calls: list = []
        monkeypatch.setattr(SDS, "ARM_DISPATCH",
                            {k: self._stub_dispatch(calls) for k in SDS.ARM_DISPATCH})
        serve = _serve_frame(n_per_pos=3)
        banks, _ = SDS.serve_banks(serve, serve)
        pos = serve["position"].astype(str).to_numpy()
        for cell in ("RB|rushing_yards", "QB|rushing_yards"):
            expect = np.arange(len(serve), dtype=float)[pos == cell.split("|")[0]]
            assert np.allclose(banks[cell][:, 0], expect), (
                f"{cell} did not receive its own position's rows out of the shared fit")

    def test_a_serve_frame_with_an_unmodeled_position_is_refused(self):
        serve = _serve_frame()
        serve.loc[0, "position"] = "K"
        with pytest.raises(ValueError, match="positions outside"):
            SDS.serve_banks(serve, serve)


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestDeployHoldAndGovernance:
    """The hold rests on the registry STATUS field — proved two-sided (NF-W2b)."""

    @staticmethod
    def _entry() -> dict:
        return {"model_family": SDS.MODEL_FAMILY, "target": SDS.REGISTRY_TARGET,
                "served_version": SDS.SERVED_VERSION,
                "artifact_uri": "repo:x.json", "promotion_status": R.STAGED_STATUS}

    def test_a_staged_entry_is_invisible_to_the_serving_facing_query(self, tmp_path):
        path = tmp_path / "reg.yaml"
        R.register(SDS.MODEL_FAMILY, SDS.REGISTRY_TARGET, self._entry(), path=path)
        assert R.served_entry(SDS.MODEL_FAMILY, SDS.REGISTRY_TARGET, path) is None

    def test_the_same_query_would_see_it_as_champion_so_the_hold_is_the_status_field(
            self, tmp_path):
        """⭐ The other side: without this, 'invisible' could mean the entry simply isn't there."""
        path = tmp_path / "reg.yaml"
        entry = self._entry() | {"promotion_status": R.SERVED_STATUS,
                                 "fallback_artifact_uri": "repo:y.json",
                                 "validation_report": "test"}
        R.register(SDS.MODEL_FAMILY, SDS.REGISTRY_TARGET, entry, path=path)
        seen = R.served_entry(SDS.MODEL_FAMILY, SDS.REGISTRY_TARGET, path)
        assert seen and seen["served_version"] == SDS.SERVED_VERSION

    def test_the_staging_script_stages_and_never_promotes_or_publishes(self):
        src = _stripped(_STAGE_RUNNER)
        assert "P.stage(" in src, "the staging script does not stage — this clause is vacuous"
        for forbidden in ("P.promote(", "P.publish(", "P.rollback("):
            assert forbidden not in src, (
                f"{forbidden} in the staging script — NF-W6c stages only; promotion is a "
                f"separate, PM-gated step")

    def test_the_target_does_not_collide_with_the_staged_points_challenger(self):
        assert SDS.REGISTRY_TARGET != "weekly_projection", (
            "NF-W6c must not share NF-W2b's target — per-stat distributions version apart from "
            "the points model")
        assert R.entry_key(SDS.MODEL_FAMILY, SDS.REGISTRY_TARGET, SDS.SERVED_VERSION) != \
            R.entry_key(SDS.MODEL_FAMILY, "weekly_projection", "nfl_fantasy_w2b_v1")

    def test_the_build_runner_has_no_publish_path_at_all(self):
        """Docstrings stripped: the runner's own prose SAYS "no boto3", which a naive scan reads
        as a hit — the first cut of this guard failed on exactly that (INC-38, both directions)."""
        src = _code_only(_BUILD_RUNNER)
        assert "def main" in src, "the code scan lost the runner — it would be vacuous"
        for forbidden in ("boto3", "--publish", "s3://", "upload_file", "put_object"):
            assert forbidden not in src, (
                f"{forbidden!r} in the build runner — it writes LOCAL artifacts only; a publish "
                f"flag that cannot legally be used is the documented-but-never-set class")

    def test_the_promote_blockers_name_the_weekly_serving_path(self):
        assert SDS.PROMOTE_BLOCKERS, "no blockers recorded — the hold has no stated reason"
        joined = " ".join(SDS.PROMOTE_BLOCKERS)
        assert "NF-C6" in joined and "NF-G0" in joined, (
            "the recorded blockers no longer name the weekly serving path and the governance "
            "review — the deploy hold's reason must live in the system of record")


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestNoScorerConsumesTheDistributionsYet:
    """The parity tax is claimed NOT to trigger — so that claim is made falsifiable.

    The three implementations of one scoring policy (fantasy_engine / the browser TS scorer / the
    Lambda scorer) must move together the moment any of them reads these distributions."""

    _SCORERS = ("fantasy_engine/scoring.py",
                "frontend/lib/league-config.ts",
                "app/backend/services/projection_fields.py")
    _TOKENS = ("stat_distribution_serving", "nf_w6c", "weekly_stat_distribution",
               SDS.SERVED_VERSION)

    def _root(self) -> Path:
        return Path(SDS.__file__).resolve().parents[4]

    def test_the_scorer_files_exist_so_the_scan_below_is_not_vacuous(self):
        found = [p for p in self._SCORERS if (self._root() / p).is_file()]
        assert found, (f"none of {self._SCORERS} exist — the parity-tax scan would pass on "
                       f"nothing; re-point it at the real scorers")

    def test_no_scorer_reads_the_served_distributions(self):
        root = self._root()
        for rel in self._SCORERS:
            path = root / rel
            if not path.is_file():
                continue
            low = path.read_text().lower()
            for token in self._TOKENS:
                assert token.lower() not in low, (
                    f"{rel} references {token!r} — a scorer now consumes the per-stat "
                    f"distributions, so the three-implementations parity tax TRIGGERS and "
                    f"`test_nf_epic1_parity.py` must be extended in the same change")


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestHonestFraming:
    """An edge/ROI/win-rate claim must be unable to reach anything this story emits."""

    def test_the_emitted_manifest_and_blockers_carry_no_forbidden_claim(self):
        man = SDS.representation_manifest()
        texts = [man["uncertainty_framing"], man["zero_atom"], *SDS.PROMOTE_BLOCKERS]
        assert len(texts) >= 3, "no copy to screen — this clause would pass on nothing"
        result = G.track_record_copy_compatible(texts)
        assert result.passed, f"forbidden claim in emitted copy: {result.detail}"

    def test_the_report_banner_the_runner_writes_carries_no_forbidden_claim(self):
        """The banner is the copy a reader actually sees, so it is screened as copy."""
        banner = [ln for ln in _BUILD_RUNNER.read_text().splitlines() if "Edge-independent" in ln]
        assert banner, "the report banner is gone — this clause would pass on nothing"
        assert G.track_record_copy_compatible(banner).passed

    def test_the_screen_would_catch_a_forbidden_claim(self):
        """⭐ Two-sided: a screen that cannot fail is not a screen."""
        assert not G.track_record_copy_compatible(
            ["these distributions are market-beating"]).passed

    def test_the_modules_declare_edge_independence_and_the_deploy_hold(self):
        for path in (_MODULE, _BUILD_RUNNER, _STAGE_RUNNER):
            doc = ast.get_docstring(ast.parse(path.read_text())) or ""
            assert doc, f"{path.name} has no module docstring"
        for path in (_MODULE, _BUILD_RUNNER):
            doc = ast.get_docstring(ast.parse(path.read_text())) or ""
            assert "DEPLOY-HELD" in doc and "best_alpha" in doc, (
                f"{path.name} no longer declares the deploy hold / edge independence")

    def test_the_realized_label_readout_never_gates_control_flow(self):
        """⭐ The structural half, and the one that matters: a settled verdict must not be
        re-decidable by a fresh fit (E2.1-r). So the smoke's result may reach the payload and the
        report — and nothing else. No branch, no raise, no exit may read it."""
        tree = ast.parse(_BUILD_RUNNER.read_text())
        producers = {"serving_smoke", "readout"}
        deciders = [n for n in ast.walk(tree)
                    if isinstance(n, (ast.If, ast.Assert, ast.Raise, ast.While))]
        assert deciders, "no control flow parsed in the runner — this clause would be vacuous"
        for node in deciders:
            names = {ast.unparse(c.func).split(".")[-1]
                     for c in ast.walk(node) if isinstance(c, ast.Call)}
            assert not (names & producers), (
                f"the serving smoke reaches control flow in {ast.unparse(node)[:70]!r} — a "
                f"fresh-fit readout must never decide anything (E2.1-r)")

    def test_the_emitted_artifact_labels_the_readout_as_never_a_gate(self):
        """The content half — read off the ARTIFACT a reader actually receives, not off a
        docstring the test could be fitted to."""
        smoke = _FANTASY / "ablation_results" / "nf_w6c_served_stat_distributions_smoke.json"
        if not smoke.is_file():
            pytest.skip("no smoke artifact committed yet")
        cells = json.loads(smoke.read_text())["serving_smoke"]
        assert len(cells) == len(EXPECTED_SERVED), "the artifact lost cells — clause is vacuous"
        for cell, entry in cells.items():
            assert "never a gate" in entry["note"].lower(), (
                f"{cell}: the emitted readout lost its non-gate framing")


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheGuardsAboveCanActuallyFail:
    """RED proofs — a guard that cannot fail is worse than no guard (NF1.7 (a) / INC-38 / NF-D17).

    Each case applies ONE deliberate break, ASSERTS THE BREAK LANDED (a RED proof that silently
    no-ops reports a false "the guard caught it" — E11.24 #682), then invokes THE REAL CLAUSE and
    requires it to fail. The clause is called, never restated: a re-typed predicate would prove
    only that the copy works."""

    @staticmethod
    def _breaks(pairs: list[tuple[object, object]]) -> None:
        for before, after in pairs:
            assert before != after, "the mutation did not change anything — the RED proof no-ops"

    @staticmethod
    def _clause_must_fail(clause, *args) -> None:
        """Run a real clause under the applied break and require it to FAIL.

        ⚠️ Catches `BaseException`: a clause whose own `pytest.raises` stops firing fails with
        `pytest.fail.Exception`, which derives from BaseException — NOT Exception. A
        `pytest.raises(Exception)` here silently misses that whole family, which is how the first
        cut of two of these proofs passed the break through."""
        try:
            clause(*args)
        except BaseException as exc:  # noqa: BLE001 — the point is to catch pytest's Failed too
            assert isinstance(exc, (AssertionError, pytest.fail.Exception)), (
                f"the clause failed for an unrelated reason ({type(exc).__name__}: {exc}) — the "
                f"RED proof is not attributable to the break")
            return
        raise AssertionError(
            f"{getattr(clause, '__name__', clause)} PASSED on deliberately broken input — the "
            f"guard cannot fail, so it is not a guard (NF1.7 (a) / INC-38)")

    def test_red_serving_a_recorded_null_cell_is_caught(self, monkeypatch):
        broken = dict(SDS.SERVED_CELLS) | {"RB|receiving_yards": "lgbm_hurdle_tail"}
        self._breaks([(dict(SDS.SERVED_CELLS), broken)])
        monkeypatch.setattr(SDS, "SERVED_CELLS", broken)
        self._clause_must_fail(
            TestServedSetIsTheRecordsShipVerdicts().test_the_recorded_nulls_are_withheld_not_served)

    def test_red_serving_a_closed_td_no_cell_is_caught(self, monkeypatch):
        broken = dict(SDS.SERVED_CELLS) | {"QB|rushing_tds": "knn_quantile"}
        self._breaks([(dict(SDS.SERVED_CELLS), broken)])
        monkeypatch.setattr(SDS, "SERVED_CELLS", broken)
        self._clause_must_fail(
            TestServedSetIsTheRecordsShipVerdicts().test_the_closed_td_no_cells_can_never_be_served)

    def test_red_serving_a_form_the_gates_did_not_certify_is_caught(self, monkeypatch):
        broken = dict(SDS.SERVED_CELLS) | {"QB|passing_tds": "lgbm_hurdle_tail"}
        self._breaks([(dict(SDS.SERVED_CELLS), broken)])
        monkeypatch.setattr(SDS, "SERVED_CELLS", broken)
        self._clause_must_fail(
            TestServedSetIsTheRecordsShipVerdicts().test_each_served_form_is_the_records_winner_for_that_cell)

    def test_red_a_drifted_index_pin_is_caught(self, monkeypatch):
        self._breaks([(SDS.IDX_Q10, SDS.IDX_Q10 + 1)])
        monkeypatch.setattr(SDS, "IDX_Q10", SDS.IDX_Q10 + 1)
        self._clause_must_fail(
            TestServedRepresentationMatchesTheRecord().test_the_index_pins_come_from_the_records_own_consumer_contract)

    def test_red_an_atom_reading_that_is_not_the_share_of_zero_levels_is_caught(self, monkeypatch):
        monkeypatch.setattr(SDS, "encode_bank", lambda bank: {
            "p_zero": np.zeros(len(bank)), "q10": np.asarray(bank)[:, SDS.IDX_Q10],
            "q50": np.asarray(bank)[:, SDS.IDX_Q50], "q90": np.asarray(bank)[:, SDS.IDX_Q90],
            "mean": np.asarray(bank).mean(axis=1)})
        assert SDS.encode_bank(_good_bank(1, 40))["p_zero"][0] == 0.0, "the break did not land"
        self._clause_must_fail(
            TestServedRepresentationMatchesTheRecord().test_the_atom_reading_is_the_share_of_grid_levels_at_zero)

    def test_red_a_representation_check_that_sorts_instead_of_raising_is_caught(self, monkeypatch):
        def _sorts_it_away(bank, cell):
            np.sort(np.asarray(bank, dtype=float), axis=1)
        monkeypatch.setattr(SDS, "assert_served_representation", _sorts_it_away)
        self._clause_must_fail(
            TestTheRepresentationCheckFailsClosed().test_a_non_monotone_bank_is_refused_not_silently_sorted)

    def test_red_a_containment_check_that_ignores_missing_rows_is_caught(self, monkeypatch):
        monkeypatch.setattr(SDS, "assert_serving_train_is_a_superset",
                            lambda feat, serve_gw: {"serve_gw": serve_gw, "n_serving_train": 1,
                                                    "n_fold_train": 1,
                                                    "extra_rows_vs_fold_train": 0,
                                                    "purge_weeks": WP.PURGE_WEEKS})
        self._clause_must_fail(
            TestServingTrainContainment().test_a_serving_train_that_drops_fold_rows_is_refused,
            monkeypatch)

    def test_red_a_build_runner_that_gained_a_publish_path_is_caught(self, monkeypatch, tmp_path):
        broken = tmp_path / "runner.py"
        src = _BUILD_RUNNER.read_text()
        mutated = src.replace("def main(argv=None) -> int:",
                              "def main(argv=None) -> int:\n    import boto3  # noqa", 1)
        self._breaks([(src, mutated)])
        broken.write_text(mutated)
        monkeypatch.setitem(globals(), "_BUILD_RUNNER", broken)
        self._clause_must_fail(
            TestDeployHoldAndGovernance().test_the_build_runner_has_no_publish_path_at_all)

    def test_red_a_staging_script_that_promotes_is_caught(self, monkeypatch, tmp_path):
        broken = tmp_path / "stage.py"
        src = _STAGE_RUNNER.read_text()
        mutated = src.replace("    result = P.stage(",
                              "    P.promote(entry=None)\n    result = P.stage(", 1)
        self._breaks([(src, mutated)])
        broken.write_text(mutated)
        monkeypatch.setitem(globals(), "_STAGE_RUNNER", broken)
        self._clause_must_fail(
            TestDeployHoldAndGovernance().test_the_staging_script_stages_and_never_promotes_or_publishes)

    def test_red_a_scorer_that_started_reading_the_distributions_is_caught(self, monkeypatch,
                                                                          tmp_path):
        """The parity-tax tripwire: prove it fires the moment a scorer references the artifact."""
        root = tmp_path
        (root / "fantasy_engine").mkdir(parents=True)
        (root / "fantasy_engine" / "scoring.py").write_text(
            "from ... import stat_distribution_serving as SDS\n")
        klass = TestNoScorerConsumesTheDistributionsYet()
        monkeypatch.setattr(klass, "_root", lambda: root)
        self._clause_must_fail(klass.test_no_scorer_reads_the_served_distributions)

    def test_red_a_serving_module_that_imported_a_learner_is_caught(self, monkeypatch, tmp_path):
        broken = tmp_path / "serving.py"
        src = _MODULE.read_text()
        mutated = src.replace("import numpy as np", "import lightgbm\nimport numpy as np", 1)
        self._breaks([(src, mutated)])
        broken.write_text(mutated)
        monkeypatch.setitem(globals(), "_MODULE", broken)
        self._clause_must_fail(
            TestNoSecondImplementation().test_the_serving_module_imports_no_learner_at_all)


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestFastGateSafety:
    """The pure module must stay importable in the fast gate (E11.23)."""

    def test_the_serving_module_does_not_import_pipeline_or_boto3(self):
        tree = ast.parse(_MODULE.read_text())
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module.split(".")[0])
        assert mods, "no imports parsed — this clause would pass on nothing"
        assert not ({"pipeline", "boto3"} & mods), (
            f"the serving module imports {sorted({'pipeline', 'boto3'} & mods)} — the fast gate "
            f"cannot import `pipeline` (no dbt manifest) and this module does no IO")

    def test_the_module_scope_does_no_file_io(self):
        """`record_reference` reads the record — but only when CALLED, never at import.

        AST over MODULE-LEVEL statements only (a function body may read files); a line-prefix
        scan would also see the docstring, which is prose."""
        tree = ast.parse(_MODULE.read_text())
        module_level = [n for n in tree.body
                        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                              ast.ClassDef, ast.Import, ast.ImportFrom))]
        assert module_level, "no module-level statements parsed — this clause is vacuous"
        for node in module_level:
            calls = {ast.unparse(c.func) for c in ast.walk(node) if isinstance(c, ast.Call)}
            leaked = {c for c in calls if c.endswith(("read_text", "read_bytes", "read_parquet",
                                                      "load_registry"))}
            assert not leaked, (f"module-scope IO {sorted(leaked)} in "
                                f"{ast.unparse(node)[:60]!r} — every importer would pay for it")
