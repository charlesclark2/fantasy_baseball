"""NF-W2d guards — re-gating the injury-availability family with 2025 in the fold set.

Every guard here is RED-PROVEN against deliberately-broken source (`TestRedProofs` mutates the
module source IN-PROCESS and asserts the mutation LANDED before running the guard — the
E11.24 #682 lesson: a RED-proof that can silently no-op reports a false "the guard caught it").
Any guard that iterates over matches asserts NON-VACUITY (NF1.7 (a) / INC-38).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2b as W2B
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2d as W2D
from quant_sports_intel_models.football.nfl.pit import leakage_guard as LG

_MODULE = Path(W2D.__file__)
_PREREG = (Path(W2D.__file__).resolve().parents[0]
           / "ablation_results" / "nf_w2d_preregistration.md")


# ── fixtures: the smallest frame that exercises the two-era family ──────────────────────────────
def _feat(rows: list[dict]) -> pd.DataFrame:
    """A modeled-matrix stub carrying only what the injury engineering reads."""
    df = pd.DataFrame(rows)
    df["label"] = df.get("label", pd.Series([WF.LABEL_PLAYED] * len(df)))
    df["position"] = df.get("position", pd.Series(["WR"] * len(df)))
    df["_target_gameday"] = pd.to_datetime(df["_target_gameday"])
    # the NF-W1 window stamp the shared PIT record builder reads (a week before the target game)
    df["_window_end_day"] = df.get(
        "_window_end_day", df["_target_gameday"] - pd.Timedelta(days=8))
    return df.reset_index(drop=True)


def _capture(season, week, gsis, stamp, report="questionable", practice="dnp") -> dict:
    return {"subject_key": f"{season}|{week}|{gsis}|nfl", "season": season, "week": week,
            "gsis_id": gsis, "position": "WR", "report_status": report,
            "practice_status": practice, "capture_timestamp": stamp}


def _store(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _nflverse(rows: list[dict]) -> pd.DataFrame:
    cols = ["season", "week", "gsis_id", "report_status", "practice_status", "date_modified"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(
        {c: pd.Series(dtype="object") for c in cols})


# ══ 1. The ONE registered change: the fold set ══════════════════════════════════════════════════
class TestOnlyTheFoldSetChanged:
    def test_2025_leaves_shadow_and_joins_the_gated_set(self):
        assert W2D.TEST_BLOCKS_W2D == W2B.TEST_BLOCKS_W2B + W2B.SHADOW_BLOCKS_W2B
        assert len(W2D.TEST_BLOCKS_W2D) == 14
        assert (2025, 1) in W2D.TEST_BLOCKS_W2D and (2025, 2) in W2D.TEST_BLOCKS_W2D
        assert W2D.SHADOW_BLOCKS_W2D == (), "nothing may remain shadow — 2025 is now measurable"

    def test_the_legacy_control_set_is_exactly_the_w2b_gated_set(self):
        assert W2D.LEGACY_BLOCKS_W2D == W2B.TEST_BLOCKS_W2B
        assert W2D.LEGACY_SEASONS == frozenset({2019, 2020, 2021, 2022, 2023, 2024})
        assert 2025 not in W2D.LEGACY_SEASONS

    @pytest.mark.parametrize("name", [
        "REAL_ARMS_W2D", "FOIL_W2D", "PROD_INCUMBENT_W2D", "ANCHORS_W2D", "ORACLE_OF_FORM_W2D",
        "FEATURES_W2D", "FEATURES_BASE_RATE_W2D", "RATE_FEATURES_W2D", "USED_FAMILIES_W2D",
    ])
    def test_every_field_constant_is_the_SAME_OBJECT_as_w2bs(self, name):
        """Identity, not equality — a re-typed copy is a constant that can drift silently."""
        w2b_name = {"REAL_ARMS_W2D": "REAL_ARMS_W2B", "FOIL_W2D": "FOIL_W2B",
                    "PROD_INCUMBENT_W2D": "PROD_INCUMBENT", "ANCHORS_W2D": "ANCHORS_W2B",
                    "ORACLE_OF_FORM_W2D": "ORACLE_OF_FORM_W2B", "FEATURES_W2D": "FEATURES_W2B",
                    "FEATURES_BASE_RATE_W2D": "FEATURES_BASE_RATE",
                    "RATE_FEATURES_W2D": "RATE_FEATURES",
                    "USED_FAMILIES_W2D": "USED_FAMILIES_W2B"}[name]
        assert getattr(W2D, name) is getattr(W2B, w2b_name)

    def test_the_runner_imports_the_w2b_reducer_rather_than_reimplementing_it(self):
        src = (_MODULE.parent / "run_nf_w2d_2025_regate.py").read_text()
        body = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
        assert "run_nf_w2b_injury_rate_bakeoff import" in body
        for fn in ("run_fold", "select_position"):
            assert f"\n    {fn},\n" in body, f"{fn} must be IMPORTED from the W2b runner"
            assert f"\ndef {fn}(" not in body, f"{fn} must not be re-implemented in the W2d runner"


# ══ 2. The vocabulary map — assert the CANONICAL contract, never the adapter's own output ═══════
class TestPracticeVocabularyMap:
    def test_it_maps_onto_the_canonical_nflverse_strings(self):
        """NF-C0e: reading a value back under the key the code wrote can never catch a wrong key,
        so this asserts the canonical nflverse vocabulary literally."""
        got = W2D.normalize_wayback_practice(pd.Series(["dnp", "limited", "full"])).tolist()
        assert got == ["did not participate in practice",
                       "limited participation in practice",
                       "full participation in practice"]

    def test_the_canonical_strings_are_the_ones_the_incumbent_engineering_matches_on(self):
        """The map is only correct if the incumbent's own comparison literals agree with it —
        pinned against W2's source so a rename upstream cannot silently zero the family."""
        w2_src = Path(W2.__file__).read_text()
        for canonical in (W2D.CANONICAL_PRACTICE_DNP, W2D.CANONICAL_PRACTICE_LIMITED):
            assert f'"{canonical}"' in w2_src

    def test_an_unrecognised_token_becomes_nan_never_passes_through(self):
        out = W2D.normalize_wayback_practice(pd.Series(["dnp", "did-not-practice", "", None]))
        assert out.iloc[0] == W2D.CANONICAL_PRACTICE_DNP
        assert [pd.isna(v) for v in out.iloc[1:]] == [True, True, True]

    def test_cross_source_agreement_the_two_adapters_engineer_the_same_column(self):
        """A wayback DNP and an nflverse DNP must produce the SAME engineered value — the
        cross-adapter agreement guard a single-adapter test structurally cannot provide."""
        legacy = _feat([{"season": 2019, "week": 5, "gsis_id": "A",
                       "_target_gameday": "2019-10-06"}])
        legacy_inj = W2D.combine_injury_sources(
            _nflverse([{"season": 2019, "week": 5, "gsis_id": "A", "report_status": "out",
                        "practice_status": W2D.CANONICAL_PRACTICE_DNP,
                        "date_modified": "2019-10-04T12:00:00+00:00"}]),
            _empty_wayback())
        a = W2D.engineer_injury_features_w2d(legacy, legacy_inj)

        cap = _feat([{"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-06"}])
        cap_inj = W2D.combine_injury_sources(_nflverse([]), W2D.wayback_injury_rows(
            _store([_capture(2025, 5, "A", "2025-10-04T12:00:00+00:00", "out", "dnp")])))
        b = W2D.engineer_injury_features_w2d(cap, cap_inj)

        for col in W2.INJURY_FEATURES:
            assert float(a[col].iloc[0]) == float(b[col].iloc[0]), col


def _empty_wayback() -> pd.DataFrame:
    df = _store([_capture(2025, 1, "Z", "2025-09-01T00:00:00+00:00")]).iloc[0:0]
    return W2D.wayback_injury_rows(df)


# ══ 3. Coverage: `observed` is per-row, and NULL is never imputed to healthy ════════════════════
class TestPerRowCoverage:
    def test_a_capture_at_the_gameday_instant_is_INADMISSIBLE_strictly_before(self):
        f = _feat([{"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"}])
        inj = W2D.combine_injury_sources(_nflverse([]), W2D.wayback_injury_rows(
            _store([_capture(2025, 5, "A", "2025-10-05T00:00:00+00:00")])))
        out = W2D.engineer_injury_features_w2d(f, inj)
        assert float(out["injury_report__observed"].iloc[0]) == 0.0
        assert pd.isna(out["injury_report__listed"].iloc[0])

    def test_the_coverage_bound_is_one_game_week_inclusive_and_excludes_beyond_it(self):
        f = _feat([{"season": 2025, "week": 12, "gsis_id": "A", "_target_gameday": "2025-11-27"}])
        inbound = W2D.combine_injury_sources(_nflverse([]), W2D.wayback_injury_rows(
            _store([_capture(2025, 12, "A", "2025-11-20T00:00:00+00:00")])))  # exactly 7.0 d
        stale = W2D.combine_injury_sources(_nflverse([]), W2D.wayback_injury_rows(
            _store([_capture(2025, 12, "A", "2025-11-16T00:00:00+00:00")])))  # 11 d
        assert float(W2D.engineer_injury_features_w2d(f, inbound)[
            "injury_report__observed"].iloc[0]) == 1.0
        assert float(W2D.engineer_injury_features_w2d(f, stale)[
            "injury_report__observed"].iloc[0]) == 0.0

    def test_an_uncovered_player_week_is_NaN_never_a_healthy_zero(self):
        """⛔ NO fillna(0): the difference between 'unmeasured' and 'not listed' is the whole
        point of the observed flag."""
        f = _feat([{"season": 2025, "week": 12, "gsis_id": "A", "_target_gameday": "2025-11-27"}])
        inj = W2D.combine_injury_sources(_nflverse([]), W2D.wayback_injury_rows(
            _store([_capture(2025, 12, "B", "2025-11-01T00:00:00+00:00")])))
        out = W2D.engineer_injury_features_w2d(f, inj)
        assert float(out["injury_report__observed"].iloc[0]) == 0.0
        nan_cols = [c for c in W2.INJURY_FEATURES if c != "injury_report__observed"]
        assert nan_cols, "vacuity: no columns under test"
        for c in nan_cols:
            assert pd.isna(out[c].iloc[0]), f"{c} must be NaN when the family is unobserved"

    def test_a_COVERED_row_absent_from_the_report_reads_NOT_LISTED_not_unmeasured(self):
        """A readable league-wide report the row is absent from IS an observation."""
        f = _feat([
            {"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"},
            {"season": 2025, "week": 5, "gsis_id": "B", "_target_gameday": "2025-10-05"},
        ])
        inj = W2D.combine_injury_sources(_nflverse([]), W2D.wayback_injury_rows(
            _store([_capture(2025, 5, "A", "2025-10-03T12:00:00+00:00")])))
        out = W2D.engineer_injury_features_w2d(f, inj).set_index("gsis_id")
        assert float(out.loc["A", "injury_report__listed"]) == 1.0
        assert float(out.loc["B", "injury_report__observed"]) == 1.0
        assert float(out.loc["B", "injury_report__listed"]) == 0.0

    def test_capture_era_dedup_happens_AFTER_admissibility_not_before(self):
        """A LATER inadmissible capture must not shadow an EARLIER admissible one — the capture
        store holds several genuine as-of observations of one player-week."""
        f = _feat([{"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"}])
        inj = W2D.combine_injury_sources(_nflverse([]), W2D.wayback_injury_rows(_store([
            _capture(2025, 5, "A", "2025-10-03T12:00:00+00:00", "out", "dnp"),
            {**_capture(2025, 5, "A", "2025-10-06T12:00:00+00:00", "questionable", "full"),
             "subject_key": "2025|5|A|espn"},
        ])))
        out = W2D.engineer_injury_features_w2d(f, inj)
        assert float(out["injury_report__listed"].iloc[0]) == 1.0
        assert float(out["injury_report__status_out"].iloc[0]) == 1.0, (
            "the admissible earlier capture must be consumed, not the inadmissible later one")

    def test_among_admissible_captures_the_latest_wins(self):
        f = _feat([{"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"}])
        inj = W2D.combine_injury_sources(_nflverse([]), W2D.wayback_injury_rows(_store([
            _capture(2025, 5, "A", "2025-10-01T12:00:00+00:00", "questionable", "limited"),
            {**_capture(2025, 5, "A", "2025-10-04T12:00:00+00:00", "out", "dnp"),
             "subject_key": "2025|5|A|espn"},
        ])))
        out = W2D.engineer_injury_features_w2d(f, inj)
        assert float(out["injury_report__status_out"].iloc[0]) == 1.0
        assert float(out["injury_report__status_questionable"].iloc[0]) == 0.0


# ══ 4. Per-column absence (MH2.1 (c)) — "no practice line" ≠ "practiced fully" ══════════════════
class TestPerColumnAbsence:
    def test_a_listed_row_whose_capture_has_no_practice_line_gets_NaN_not_zero(self):
        f = _feat([{"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"}])
        inj = W2D.combine_injury_sources(_nflverse([]), W2D.wayback_injury_rows(
            _store([_capture(2025, 5, "A", "2025-10-03T12:00:00+00:00", "out", None)])))
        out = W2D.engineer_injury_features_w2d(f, inj)
        assert float(out["injury_report__listed"].iloc[0]) == 1.0
        assert float(out["injury_report__status_out"].iloc[0]) == 1.0
        for c in ("injury_report__practice_dnp", "injury_report__practice_limited"):
            assert pd.isna(out[c].iloc[0]), f"{c}: no practice info is not 'practiced fully'"

    def test_the_same_row_WITH_a_practice_line_gets_a_real_zero_or_one(self):
        f = _feat([{"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"}])
        inj = W2D.combine_injury_sources(_nflverse([]), W2D.wayback_injury_rows(
            _store([_capture(2025, 5, "A", "2025-10-03T12:00:00+00:00", "out", "limited")])))
        out = W2D.engineer_injury_features_w2d(f, inj)
        assert float(out["injury_report__practice_limited"].iloc[0]) == 1.0
        assert float(out["injury_report__practice_dnp"].iloc[0]) == 0.0

    def test_a_covered_but_UNLISTED_row_keeps_a_meaningful_practice_zero(self):
        """No designation at all is a genuine observation of 'no DNP' — only a LISTED row with a
        practice-blind source is unknown."""
        f = _feat([
            {"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"},
            {"season": 2025, "week": 5, "gsis_id": "B", "_target_gameday": "2025-10-05"},
        ])
        inj = W2D.combine_injury_sources(_nflverse([]), W2D.wayback_injury_rows(
            _store([_capture(2025, 5, "A", "2025-10-03T12:00:00+00:00", "out", None)])))
        out = W2D.engineer_injury_features_w2d(f, inj).set_index("gsis_id")
        assert float(out.loc["B", "injury_report__practice_dnp"]) == 0.0


# ══ 5. Provenance: the record SHAPE follows the stamp kind; the capture instant is never ════════
#      laundered into the vendor slot
class TestProvenanceShape:
    def test_a_wayback_record_declares_its_absent_source_timestamp(self):
        rec = W2D._record(source=W2D.WAYBACK_STORE_SOURCE, payload="p", tier="injury",
                          stamp="2025-10-03T12:00:00+00:00", kind=W2D.STAMP_WAYBACK)
        assert rec["source_timestamp"] is None
        assert rec["source_timestamp_absent_reason"].strip()
        assert rec["vendor_release_timestamp"] is None
        assert LG.check_provenance_present(rec) == []

    def test_an_nflverse_record_carries_date_modified_in_the_vendor_slot(self):
        rec = W2D._record(source="nflverse_injuries", payload="p", tier="injury",
                          stamp="2019-10-03T12:00:00+00:00", kind=W2D.STAMP_NFLVERSE)
        assert rec["source_timestamp"] == "2019-10-03T12:00:00+00:00"
        assert LG.check_provenance_present(rec) == []

    def test_an_undeclared_null_source_timestamp_is_REJECTED(self):
        """Proves the declaration is load-bearing, not documentation."""
        rec = W2D._record(source=W2D.WAYBACK_STORE_SOURCE, payload="p", tier="injury",
                          stamp="2025-10-03T12:00:00+00:00", kind=W2D.STAMP_WAYBACK)
        rec.pop("source_timestamp_absent_reason")
        findings = LG.check_provenance_present(rec)
        assert findings, "a null source_timestamp with no reason must be refused"
        assert any(f.reason is LG.Rejection.PROVENANCE_MISSING for f in findings)

    def test_the_gate_emits_the_wayback_shape_for_2025_rows_and_counts_them(self):
        f = _feat([
            {"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"},
            {"season": 2019, "week": 5, "gsis_id": "A", "_target_gameday": "2019-10-06"},
        ])
        inj = W2D.combine_injury_sources(
            _nflverse([{"season": 2019, "week": 5, "gsis_id": "A", "report_status": "out",
                        "practice_status": W2D.CANONICAL_PRACTICE_DNP,
                        "date_modified": "2019-10-04T12:00:00+00:00"}]),
            W2D.wayback_injury_rows(
                _store([_capture(2025, 5, "A", "2025-10-03T12:00:00+00:00")])))
        eng = W2D.engineer_injury_rate_features_w2d(
            W2D.engineer_injury_features_w2d(f, inj))
        recs = W2D.injury_guard_records_w2d(eng)
        assert len(recs) == 2, "vacuity: both eras must produce a consumed record"
        by_src = {r["capture_source"]: r for r in recs}
        assert by_src[W2D.WAYBACK_STORE_SOURCE]["source_timestamp"] is None
        assert by_src["nflverse_injuries"]["source_timestamp"] is not None
        audit = W2D.run_pit_gate_w2d(eng)
        assert audit["rows_dropped"] == 0
        assert audit["wayback_records_checked"] >= 1


# ══ 6. Source combination refuses what it cannot reconcile ══════════════════════════════════════
class TestSourceCombination:
    def test_a_pre_2025_capture_row_is_REFUSED_not_silently_filtered(self):
        """⭐ The reachability half: if BOTH sides were filtered into disjointness the overlap
        check could never fire, which is the vacuous-guard class (the first cut had exactly that
        defect and this test is what found it)."""
        wb = W2D.wayback_injury_rows(_store([_capture(2019, 5, "A", "2019-10-03T00:00:00+00:00")]))
        nf = _nflverse([{"season": 2019, "week": 5, "gsis_id": "A", "report_status": "out",
                         "practice_status": W2D.CANONICAL_PRACTICE_DNP,
                         "date_modified": "2019-10-04T12:00:00+00:00"}])
        with pytest.raises(ValueError, match="refused, never reconciled"):
            W2D.combine_injury_sources(nf, wb)

    def test_stampless_post_2024_nflverse_rows_are_EXCLUDED_not_refused(self):
        """They genuinely exist and are genuinely inadmissible — an exclusion, not an error."""
        nf = _nflverse([
            {"season": 2019, "week": 5, "gsis_id": "A", "report_status": "out",
             "practice_status": W2D.CANONICAL_PRACTICE_DNP,
             "date_modified": "2019-10-04T12:00:00+00:00"},
            {"season": 2025, "week": 5, "gsis_id": "A", "report_status": "out",
             "practice_status": W2D.CANONICAL_PRACTICE_DNP, "date_modified": None},
        ])
        out = W2D.combine_injury_sources(nf, _empty_wayback())
        assert set(out["season"]) == {2019}, "the stampless 2025 nflverse row must not survive"

    def test_an_unrecognised_store_schema_raises_rather_than_yielding_an_empty_family(self):
        with pytest.raises(ValueError, match="missing"):
            W2D.wayback_injury_rows(pd.DataFrame({"season": [2025], "week": [5]}))

    def test_an_unparseable_capture_stamp_rejects_the_build(self):
        with pytest.raises(ValueError, match="capture_timestamp"):
            W2D.wayback_injury_rows(_store([_capture(2025, 5, "A", "not-a-timestamp")]))


# ══ 7. The reproduction control fails CLOSED ════════════════════════════════════════════════════
class TestReproductionControl:
    @staticmethod
    def _fold(label, value):
        return {"label": label,
                "scores": {arm: {p: value for p in WP.POSITIONS}
                           for arm in ("base_rate", *W2D.REAL_ARMS_W2D)}}

    def _run(self, tmp_path, monkeypatch, prior, folds):
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w2d_2025_regate as R
        art = tmp_path / "nf_w2b_injury_rate_bakeoff.json"
        if prior is not None:
            art.write_text(json.dumps(prior))
        monkeypatch.setattr(R, "_W2B_ARTIFACT", art)
        return R.reproduction_control(folds)

    def test_a_missing_artifact_is_UNEVALUABLE_never_a_pass(self, tmp_path, monkeypatch):
        got = self._run(tmp_path, monkeypatch, None, [self._fold("2019H1", 1.0)])
        assert got["state"] == "UNEVALUABLE" and got["passes"] is False

    def test_zero_comparisons_is_UNEVALUABLE_never_a_pass(self, tmp_path, monkeypatch):
        """A control that compared nothing has proven nothing (NF1.7 (a))."""
        got = self._run(tmp_path, monkeypatch, {"fold_results": []},
                        [self._fold("2025H1", 1.0)])  # 2025 is not a legacy fold
        assert got["state"] == "UNEVALUABLE" and got["comparisons"] == 0

    def test_matching_legacy_folds_PASS_and_actually_compared_something(self, tmp_path, monkeypatch):
        f = self._fold("2019H1", 1.0)
        got = self._run(tmp_path, monkeypatch, {"fold_results": [f]},
                        [self._fold("2019H1", 1.0), self._fold("2025H1", 9.0)])
        assert got["passes"] is True
        assert got["comparisons"] == len(WP.POSITIONS) * (1 + len(W2D.REAL_ARMS_W2D))

    def test_a_perturbed_legacy_fold_FAILS(self, tmp_path, monkeypatch):
        got = self._run(tmp_path, monkeypatch, {"fold_results": [self._fold("2019H1", 1.0)]},
                        [self._fold("2019H1", 1.0 + 1e-6)])
        assert got["passes"] is False and got["state"] == "FAIL" and got["mismatches"]

    def test_a_missing_arm_in_the_prior_FAILS_rather_than_being_skipped(self, tmp_path, monkeypatch):
        prior = self._fold("2019H1", 1.0)
        prior["scores"].pop("inj_override")
        got = self._run(tmp_path, monkeypatch, {"fold_results": [prior]},
                        [self._fold("2019H1", 1.0)])
        assert got["passes"] is False and got["missing"]

    def test_an_invalid_run_cannot_present_per_position_verdicts(self):
        src = (_MODULE.parent / "run_nf_w2d_2025_regate.py").read_text()
        body = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
        assert 'if not repro["passes"]:' in body
        assert "INVALID_RUN" in body
        assert body.index('if not repro["passes"]:') < body.index('out["verdict"] = verdicts')


# ══ 8. The revision clause is reported as INACTIVE, not as a pass (NF-D20) ══════════════════════
class TestRevisionClauseActivity:
    def test_it_separates_subject_multiplicity_from_SOURCE_multiplicity(self):
        raw = _store([
            _capture(2025, 5, "A", "2025-10-01T00:00:00+00:00"),
            {**_capture(2025, 5, "A", "2025-10-02T00:00:00+00:00"),
             "subject_key": "2025|5|A|espn"},
        ])
        got = W2D.revision_clause_activity(raw)
        assert got["store_subject_max_captures"] == 1
        assert got["store_subjects_with_multiple_captures"] == 0
        assert got["player_weeks_with_multiple_source_captures"] == 1
        assert "INACTIVE" in got["clause_state"] and "not a pass" in got["clause_state"]

    def test_a_genuine_second_capture_of_one_subject_reads_ACTIVE(self):
        raw = _store([
            _capture(2025, 5, "A", "2025-10-01T00:00:00+00:00"),
            _capture(2025, 5, "A", "2025-10-02T00:00:00+00:00"),  # same subject_key
        ])
        got = W2D.revision_clause_activity(raw)
        assert got["store_subject_max_captures"] == 2
        assert "ACTIVE" in got["clause_state"]

    def test_a_frame_that_cannot_express_the_clause_raises(self):
        with pytest.raises(ValueError, match="subject_key"):
            W2D.revision_clause_activity(pd.DataFrame({"season": [2025]}))


# ══ 9. The coverage report recomputes and reports per-COLUMN, never a pooled mean ═══════════════
class TestCoverageReport:
    def _built(self):
        rows = [{"season": 2025, "week": 5, "gsis_id": g, "_target_gameday": "2025-10-05"}
                for g in ("A", "B", "C")]
        rows.append({"season": 2025, "week": 12, "gsis_id": "A",
                     "_target_gameday": "2025-11-27"})
        f = _feat(rows)
        wb = W2D.wayback_injury_rows(_store([
            _capture(2025, 5, "A", "2025-10-03T12:00:00+00:00", "out", "dnp"),
            {**_capture(2025, 5, "B", "2025-10-03T12:00:00+00:00", "questionable", None),
             "subject_key": "2025|5|B|espn"},
            _capture(2025, 12, "A", "2025-11-10T00:00:00+00:00"),   # 17 d stale ⇒ uncovered
        ]))
        inj = W2D.combine_injury_sources(_nflverse([]), wb)
        eng = W2D.engineer_injury_rate_features_w2d(W2D.engineer_injury_features_w2d(f, inj))
        return W2D.coverage_report(eng, wb)

    def test_the_uncovered_week_is_named_and_the_primary_bound_is_reported(self):
        got = self._built()
        assert got["coverage_primary_bound_days"] == W2D.COVERAGE_MAX_AGE_DAYS
        assert got["uncovered_weeks"] == [12]
        assert got["coverage_primary"] == 0.75

    def test_the_diagnostic_bounds_are_reported_and_are_not_the_primary(self):
        got = self._built()
        assert set(got["coverage_diagnostic_only"]) == {"3d", "unbounded"}
        assert got["coverage_diagnostic_only"]["unbounded"] == 1.0
        assert got["coverage_primary"] != got["coverage_diagnostic_only"]["unbounded"]

    def test_absence_is_reported_PER_COLUMN_not_pooled(self):
        got = self._built()
        per_col = got["per_column_absence_over_listed"]
        assert per_col, "vacuity: no per-column absence was computed"
        assert per_col["injury_report__status_out"] == 0.0
        assert per_col["injury_report__practice_dnp"] == 0.5, (
            "one of the two listed rows came from a practice-blind source")


# ══ 10. The rate family follows the same per-row observed flag ══════════════════════════════════
class TestRateFamily:
    def test_rates_are_group_level_and_unobserved_rows_stay_NaN(self):
        rows = [{"season": 2025, "week": 5, "gsis_id": g, "_target_gameday": "2025-10-05"}
                for g in ("A", "B", "C", "D")]
        rows.append({"season": 2025, "week": 12, "gsis_id": "A",
                     "_target_gameday": "2025-11-27"})
        f = _feat(rows)
        inj = W2D.combine_injury_sources(_nflverse([]), W2D.wayback_injury_rows(_store([
            _capture(2025, 5, "A", "2025-10-03T12:00:00+00:00", "out", "dnp"),
        ])))
        eng = W2D.engineer_injury_rate_features_w2d(W2D.engineer_injury_features_w2d(f, inj))
        wk5 = eng[eng.week == 5]
        assert wk5["injury_rate__listed"].nunique() == 1, "a rate must be constant within a group"
        assert float(wk5["injury_rate__listed"].iloc[0]) == 0.25
        assert float(wk5["injury_rate__status_out"].iloc[0]) == 0.25
        wk12 = eng[eng.week == 12]
        assert float(wk12["injury_rate__observed"].iloc[0]) == 0.0
        rate_cols = [c for c in W2D.RATE_FEATURES_W2D if c != "injury_rate__observed"]
        assert rate_cols
        for c in rate_cols:
            assert pd.isna(wk12[c].iloc[0]), c

    def test_the_rate_stamp_kind_declares_capture_provenance_conservatively(self):
        f = _feat([{"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"}])
        inj = W2D.combine_injury_sources(_nflverse([]), W2D.wayback_injury_rows(
            _store([_capture(2025, 5, "A", "2025-10-03T12:00:00+00:00")])))
        eng = W2D.engineer_injury_rate_features_w2d(W2D.engineer_injury_features_w2d(f, inj))
        assert eng["_rate_stamp_kind"].iloc[0] == W2D.STAMP_WAYBACK
        rec = W2D.rate_guard_records_w2d(eng)
        assert len(rec) == 1 and rec[0]["source_timestamp"] is None


# ══ 11. Metric + deploy-held invariants ═════════════════════════════════════════════════════════
class TestMetricAndDeployHeld:
    def test_crps_selects_and_mae_never_does(self):
        assert WP.SELECTION_METRIC == "crps_q39"
        src = (_MODULE.parent / "run_nf_w2d_2025_regate.py").read_text()
        assert "mean_mae_report_only" in src and "never selects" in src

    def test_the_degenerate_anchors_are_in_the_field_and_the_gate_reads_them(self):
        assert "nihilist_zero" in W2D.ANCHORS_W2D and "pos_marginal" in W2D.ANCHORS_W2D
        assert "degenerates_lose" in W2B.ANCHOR_CHECKS

    def test_the_deflation_convention_is_the_unchanged_whole_field_fantasy_call(self):
        w2b_runner = (_MODULE.parent / "run_nf_w2b_injury_rate_bakeoff.py").read_text()
        assert "M14.deflated_sharpe(deltas, np.asarray(trial_srs))" in w2b_runner
        w2d = " ".join((_MODULE.parent / "run_nf_w2d_2025_regate.py").read_text().split())
        assert "No field trim, no convention" in w2d
        # ⭐ a CALL-SITE regex, not a name occurrence — the runner's prose names the function
        # while never calling it, and `"M14.deflated_sharpe" in src` cannot tell those apart
        # (the DSR-CONV #690 lesson: a name in a string/dict key is not a call site).
        assert not re.search(r"M14\.deflated_sharpe\s*\(", w2d), (
            "NF-W2d must not call the deflation itself — it uses the W2b reducer unchanged")
        assert re.search(r"M14\.deflated_sharpe\s*\(", w2b_runner), (
            "vacuity check: the call-site regex must actually match where a call DOES exist")

    def test_nothing_in_the_story_writes_to_a_registry_or_a_serving_surface(self):
        forbidden = ("append_captures", "put_object", "--publish", "s3.put", "boto3.client",
                     "stage_registry", "POST_FLIP_SPEC")
        for path in (_MODULE, _MODULE.parent / "run_nf_w2d_2025_regate.py"):
            body = path.read_text()
            hits = [t for t in forbidden if t in body]
            assert not hits, f"{path.name} must be deploy-held; found {hits}"

    def test_the_preregistration_is_committed_and_names_the_binding_choices(self):
        assert _PREREG.exists()
        text = _PREREG.read_text()
        for token in ("COVERAGE_MAX_AGE_DAYS = 7", "Reproduction control", "best_alpha = 0",
                      "deploy-held", "Fresh registration", "CRPS"):
            assert token.lower() in text.lower(), token


# ══ 12. RED-proofs — each mutation is asserted to have LANDED before the guard runs ═════════════
class TestRedProofs:
    """E11.24 #682: a RED-proof that can silently no-op reports a false 'the guard caught it'.
    Every case mutates the module source IN-PROCESS, asserts the text actually changed, reloads,
    and requires the named guard to FAIL."""

    @staticmethod
    def _reload_with(source_swap: tuple[str, str]):
        import importlib
        import types
        old, new = source_swap
        src = _MODULE.read_text()
        assert old in src, f"RED-proof mutation target not found in source: {old!r}"
        mutated = src.replace(old, new, 1)
        assert mutated != src, "RED-proof mutation did not change the source — it would no-op"
        mod = types.ModuleType("w2d_mutated")
        mod.__file__ = str(_MODULE)
        exec(compile(mutated, str(_MODULE), "exec"), mod.__dict__)  # noqa: S102 — test harness
        importlib.invalidate_caches()
        return mod

    def test_dropping_the_absent_reason_makes_the_gate_reject_wayback_records(self):
        mod = self._reload_with((
            'rec["source_timestamp_absent_reason"] = WAYBACK_SOURCE_TS_ABSENT_REASON',
            'pass',
        ))
        rec = mod._record(source="wayback_injuries", payload="p", tier="injury",
                          stamp="2025-10-03T12:00:00+00:00", kind=mod.STAMP_WAYBACK)
        assert LG.check_provenance_present(rec), (
            "with the declaration removed the guard MUST reject — proving the live code's "
            "declaration is load-bearing")

    def test_laundering_the_capture_instant_into_the_vendor_slot_is_detectable(self):
        mod = self._reload_with(('rec["source_timestamp"] = None',
                                 'rec["source_timestamp"] = stamp'))
        rec = mod._record(source="wayback_injuries", payload="p", tier="injury",
                          stamp="2025-10-03T12:00:00+00:00", kind=mod.STAMP_WAYBACK)
        assert rec["source_timestamp"] is not None
        # the live module must NOT behave this way
        live = W2D._record(source="wayback_injuries", payload="p", tier="injury",
                           stamp="2025-10-03T12:00:00+00:00", kind=W2D.STAMP_WAYBACK)
        assert live["source_timestamp"] is None

    def test_relaxing_the_LOAD_BEARING_strict_bound_admits_a_gameday_stamp(self):
        """⭐ ISOLATED on the LEGACY path, deliberately: admissibility is an AND of `observed`,
        stamp-presence and the strict bound, and an nflverse row is `observed` by its era and
        never passes through the capture pre-filter — so the strict bound is the ONLY clause that
        can flip (NF-D17: a fixture that trips a second clause proves nothing about the first)."""
        f = _feat([{"season": 2019, "week": 5, "gsis_id": "A",
                    "_target_gameday": "2019-10-06"}])
        nf = _nflverse([{"season": 2019, "week": 5, "gsis_id": "A", "report_status": "out",
                         "practice_status": W2D.CANONICAL_PRACTICE_DNP,
                         "date_modified": "2019-10-06T00:00:00+00:00"}])  # AT the instant
        mod = self._reload_with(('(f["_dm_utc"] < gameday_utc).to_numpy()',
                                 '(f["_dm_utc"] <= gameday_utc).to_numpy()'))
        broken = mod.engineer_injury_features_w2d(
            f, mod.combine_injury_sources(nf, _empty_wayback()))
        live = W2D.engineer_injury_features_w2d(
            f, W2D.combine_injury_sources(nf, _empty_wayback()))
        assert float(broken["injury_report__observed"].iloc[0]) == 1.0
        assert float(live["injury_report__observed"].iloc[0]) == 1.0
        assert float(broken["injury_report__listed"].iloc[0]) == 1.0, (
            "the mutation must land: a `<=` bound consumes the gameday-instant stamp")
        assert float(live["injury_report__listed"].iloc[0]) == 0.0, (
            "the live strict-< bound must consume nothing stamped AT the instant")

    def test_the_capture_pre_filters_strict_bound_is_REDUNDANT_and_says_so(self):
        """⭐ An honest negative RED-proof (NF-D17). The capture branch's own `< _g` cannot be
        RED-proven in ISOLATION, because `admissible` refuses the same row a line later — so
        relaxing only the pre-filter changes NOTHING observable. That is defence-in-depth, not
        two independent guarantees, and this test states it rather than presenting a guard that
        cannot fail. Relaxing BOTH clauses together IS observable, which is what proves the pair
        is load-bearing."""
        f = _feat([
            {"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"},
            {"season": 2025, "week": 5, "gsis_id": "B", "_target_gameday": "2025-10-05"},
        ])
        store = _store([
            _capture(2025, 5, "B", "2025-10-03T12:00:00+00:00"),          # establishes coverage
            {**_capture(2025, 5, "A", "2025-10-05T00:00:00+00:00", "out", "dnp"),
             "subject_key": "2025|5|A|espn"},                             # AT the instant
        ])

        def _listed(mod):
            out = mod.engineer_injury_features_w2d(
                f, mod.combine_injury_sources(_nflverse([]), mod.wayback_injury_rows(store))
            ).set_index("gsis_id")
            assert float(out.loc["A", "injury_report__observed"]) == 1.0, "coverage must hold"
            return float(out.loc["A", "injury_report__listed"])

        pre_only = self._reload_with(('(cand["_dm_utc"] < cand["_g"])',
                                      '(cand["_dm_utc"] <= cand["_g"])'))
        assert _listed(pre_only) == 0.0, (
            "relaxing ONLY the pre-filter is inert — `admissible` still refuses")
        both_src = _MODULE.read_text().replace(
            '(cand["_dm_utc"] < cand["_g"])', '(cand["_dm_utc"] <= cand["_g"])', 1).replace(
            '(f["_dm_utc"] < gameday_utc).to_numpy()',
            '(f["_dm_utc"] <= gameday_utc).to_numpy()', 1)
        assert both_src != _MODULE.read_text(), "both-clause mutation must land"
        import types
        mod = types.ModuleType("w2d_both")
        mod.__file__ = str(_MODULE)
        exec(compile(both_src, str(_MODULE), "exec"), mod.__dict__)  # noqa: S102 — test harness
        assert _listed(mod) == 1.0, (
            "relaxing BOTH clauses IS observable — the pair genuinely enforces the bound")
        assert _listed(W2D) == 0.0, "the live pair refuses a gameday-instant capture"

    def test_fillna_zero_on_an_unobserved_row_breaks_the_null_discipline(self):
        mod = self._reload_with((
            'f["injury_report__listed"] = np.where(observed, admissible.astype(float), np.nan)',
            'f["injury_report__listed"] = admissible.astype(float)',
        ))
        f = _feat([{"season": 2025, "week": 12, "gsis_id": "A", "_target_gameday": "2025-11-27"}])
        store = _store([_capture(2025, 12, "A", "2025-11-01T00:00:00+00:00")])
        inj = mod.combine_injury_sources(_nflverse([]), mod.wayback_injury_rows(store))
        broken = mod.engineer_injury_features_w2d(f, inj)
        assert float(broken["injury_report__listed"].iloc[0]) == 0.0, (
            "the mutation must produce the healthy-zero the live code refuses")
        live = W2D.engineer_injury_features_w2d(f, W2D.combine_injury_sources(
            _nflverse([]), W2D.wayback_injury_rows(store)))
        assert pd.isna(live["injury_report__listed"].iloc[0])

    def test_a_wrong_practice_key_map_zeroes_the_family_and_the_canonical_guard_catches_it(self):
        mod = self._reload_with(('"dnp": CANONICAL_PRACTICE_DNP', '"dnp": "dnp"'))
        got = mod.normalize_wayback_practice(pd.Series(["dnp"])).tolist()
        assert got == ["dnp"], "the mutation must land"
        # the NF-C0e guard asserts the CANONICAL contract, so it goes red on this mutation
        with pytest.raises(AssertionError):
            assert got == [W2D.CANONICAL_PRACTICE_DNP]
        # and the wrong key silently produces an all-zero engineered feature
        f = _feat([{"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"}])
        store = _store([_capture(2025, 5, "A", "2025-10-03T12:00:00+00:00", "out", "dnp")])
        inj = mod.combine_injury_sources(_nflverse([]), mod.wayback_injury_rows(store))
        broken = mod.engineer_injury_features_w2d(f, inj)
        assert float(broken["injury_report__practice_dnp"].iloc[0]) == 0.0
        live = W2D.engineer_injury_features_w2d(f, W2D.combine_injury_sources(
            _nflverse([]), W2D.wayback_injury_rows(store)))
        assert float(live["injury_report__practice_dnp"].iloc[0]) == 1.0

    def test_widening_the_coverage_bound_covers_the_thanksgiving_week_the_data_cannot_support(self):
        mod = self._reload_with(("COVERAGE_MAX_AGE_DAYS = 7.0", "COVERAGE_MAX_AGE_DAYS = 60.0"))
        assert mod.COVERAGE_MAX_AGE_DAYS == 60.0
        f = _feat([{"season": 2025, "week": 12, "gsis_id": "A", "_target_gameday": "2025-11-27"}])
        store = _store([_capture(2025, 12, "A", "2025-11-01T00:00:00+00:00")])  # 26 d stale
        broken = mod.engineer_injury_features_w2d(
            f, mod.combine_injury_sources(_nflverse([]), mod.wayback_injury_rows(store)))
        assert float(broken["injury_report__observed"].iloc[0]) == 1.0
        live = W2D.engineer_injury_features_w2d(f, W2D.combine_injury_sources(
            _nflverse([]), W2D.wayback_injury_rows(store)))
        assert float(live["injury_report__observed"].iloc[0]) == 0.0, (
            "the registered one-game-week bound must refuse a 26-day-old capture")


# ══ 13. The legacy era is untouched at the COLUMN level (the CRPS control's cheap sibling) ══════
class TestLegacyEraUntouched:
    def test_the_nflverse_path_reproduces_W2s_engineering_exactly(self):
        rows = [
            {"season": 2019, "week": 5, "gsis_id": "A", "_target_gameday": "2019-10-06"},
            {"season": 2019, "week": 5, "gsis_id": "B", "_target_gameday": "2019-10-06"},
            {"season": 2019, "week": 5, "gsis_id": "C", "_target_gameday": "2019-10-03"},
        ]
        inj_rows = [
            {"season": 2019, "week": 5, "gsis_id": "A", "report_status": "out",
             "practice_status": W2D.CANONICAL_PRACTICE_DNP,
             "date_modified": "2019-10-04T12:00:00+00:00"},
            # C's stamp lands AFTER its Thursday gameday ⇒ inadmissible in both harnesses
            {"season": 2019, "week": 5, "gsis_id": "C", "report_status": "questionable",
             "practice_status": W2D.CANONICAL_PRACTICE_LIMITED,
             "date_modified": "2019-10-04T12:00:00+00:00"},
        ]
        w2_out = W2.engineer_injury_features(_feat(rows), _nflverse(inj_rows))
        w2d_out = W2D.engineer_injury_features_w2d(
            _feat(rows), W2D.combine_injury_sources(_nflverse(inj_rows), _empty_wayback()))
        assert len(W2.INJURY_FEATURES) == 7
        for col in W2.INJURY_FEATURES:
            np.testing.assert_allclose(
                w2_out[col].to_numpy(dtype=float), w2d_out[col].to_numpy(dtype=float),
                err_msg=f"{col} moved on the legacy era")

    def test_the_legacy_rate_family_reproduces_W2bs_engineering_exactly(self):
        rows = [{"season": 2019, "week": 5, "gsis_id": g, "position": "WR",
                 "_target_gameday": "2019-10-06"} for g in ("A", "B", "C", "D")]
        inj_rows = [{"season": 2019, "week": 5, "gsis_id": "A", "report_status": "out",
                     "practice_status": W2D.CANONICAL_PRACTICE_DNP,
                     "date_modified": "2019-10-04T12:00:00+00:00"}]
        w2b = W2B.engineer_injury_rate_features(
            W2.engineer_injury_features(_feat(rows), _nflverse(inj_rows)))
        w2d = W2D.engineer_injury_rate_features_w2d(W2D.engineer_injury_features_w2d(
            _feat(rows), W2D.combine_injury_sources(_nflverse(inj_rows), _empty_wayback())))
        for col in W2B.RATE_FEATURES:
            np.testing.assert_allclose(
                w2b[col].to_numpy(dtype=float), w2d[col].to_numpy(dtype=float),
                err_msg=f"{col} moved on the legacy era")
