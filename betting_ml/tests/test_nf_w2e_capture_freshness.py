"""NF-W2e guards — the capture-freshness ladder.

RED-proofs mutate the module source IN-PROCESS and assert the mutation LANDED before running the
guard (E11.24 #682). Guards that iterate assert NON-VACUITY (NF1.7 (a) / INC-38), and each clause
of an AND-composed rule gets its own ISOLATING fixture (NF-D17).
"""
from __future__ import annotations

import re
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from betting_ml.utils import cv_power
from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2b as W2B
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2d as W2D
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2e as W2E

_MODULE = Path(W2E.__file__)
_RUNNER = _MODULE.parent / "run_nf_w2e_capture_freshness.py"
_PREREG = _MODULE.parent / "ablation_results" / "nf_w2e_preregistration.md"


def _feat(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["label"] = df.get("label", pd.Series([WF.LABEL_PLAYED] * len(df)))
    df["position"] = df.get("position", pd.Series(["WR"] * len(df)))
    df["_target_gameday"] = pd.to_datetime(df["_target_gameday"])
    df["_window_end_day"] = df["_target_gameday"] - pd.Timedelta(days=8)
    return df.reset_index(drop=True)


def _capture(season, week, gsis, stamp, report="questionable", practice="dnp", src="nfl") -> dict:
    return {"subject_key": f"{season}|{week}|{gsis}|{src}", "season": season, "week": week,
            "gsis_id": gsis, "position": "WR", "report_status": report,
            "practice_status": practice, "capture_timestamp": stamp}


def _nflverse(rows: list[dict]) -> pd.DataFrame:
    cols = ["season", "week", "gsis_id", "report_status", "practice_status", "date_modified"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(
        {c: pd.Series(dtype="object") for c in cols})


def _inj(nflverse_rows, capture_rows):
    wb = W2D.wayback_injury_rows(pd.DataFrame(capture_rows)) if capture_rows else \
        W2D.wayback_injury_rows(pd.DataFrame([_capture(2025, 1, "Z", "2025-09-01T00:00:00+00:00")]).iloc[0:0])
    return W2D.combine_injury_sources(_nflverse(nflverse_rows), wb)


# ══ 1. The registered ladder + the power ceiling ════════════════════════════════════════════════
class TestRegistration:
    def test_the_ladder_is_monotone_and_the_incumbent_is_its_loosest_rung(self):
        bounds = [c for _, c in W2E.FRESHNESS_LADDER]
        assert W2E.FRESHNESS_LADDER[0][0] == W2E.INCUMBENT_RUNG
        assert bounds[0] == W2D.COVERAGE_MAX_AGE_DAYS, "rung 1 must BE the NF-W2d construction"
        assert bounds[1] < bounds[0] and bounds[-1] is None, "the ladder must tighten monotonically"
        assert len(W2E.LADDER_ARMS) == 3

    def test_the_stratum_boundary_is_the_validated_one_not_a_free_knob(self):
        assert W2E.VALIDATED_STRATUM_BOUNDARY_DAYS == 1.0
        assert dict(W2E.FRESHNESS_LADDER)["inj_fresh1d"] == W2E.VALIDATED_STRATUM_BOUNDARY_DAYS, (
            "the ladder's middle rung must sit exactly at the VALIDATED stratifier boundary — a "
            "different value would be a tuned knob")

    def test_the_foil_is_the_unchanged_w2b_object(self):
        assert W2E.FOIL_W2E is W2B.FOIL_W2B

    def test_the_power_ceiling_is_real_and_computed(self):
        """⛔ At 2 active folds NO gate is clearable — the study must not claim otherwise."""
        n = len(W2E.CAPTURE_ERA_BLOCKS)
        assert n == 2
        assert cv_power.fold_consistency_clause(n).attainable is False
        assert cv_power.pbo_evaluable(n) is False
        assert cv_power.sign_test_floor(n) > WP.FDR_Q
        assert cv_power.dsr_ceiling(n) < WP.DSR_MIN
        assert W2E.VERDICT_W2E == "NO_CERTIFICATION_POSSIBLE"

    def test_the_runner_never_emits_a_ship_verdict(self):
        body = _RUNNER.read_text()
        assert "NO_CERTIFICATION_POSSIBLE" in body
        assert not re.search(r'"verdict"\s*:\s*"SHIP"', body)
        assert re.search(r'W2E\.VERDICT_W2E for pos in WP\.POSITIONS', body), (
            "every position's verdict must be pinned to the registered constant")

    def test_the_preregistration_is_committed_and_states_the_ceiling(self):
        assert _PREREG.exists()
        t = _PREREG.read_text().lower()
        for token in ("cannot certify", "dsr_ceiling", "0.9214", "deploy-held",
                      "best_alpha = 0", "both directions"):
            assert token.lower() in t, token


# ══ 2. Coverage vs consumption are SEPARATE — the load-bearing design choice ═════════════════════
class TestCoverageAndConsumptionAreSeparate:
    @staticmethod
    def _rows():
        # two players, week 5: A captured 3d out, B captured 0.2d out. Coverage (7d) holds for both.
        f = _feat([{"season": 2025, "week": 5, "gsis_id": g, "_target_gameday": "2025-10-05"}
                   for g in ("A", "B")])
        caps = [_capture(2025, 5, "A", "2025-10-02T00:00:00+00:00", "out", "dnp"),
                _capture(2025, 5, "B", "2025-10-04T19:12:00+00:00", "questionable", "limited",
                         src="espn")]
        return f, _inj([], caps)

    def test_tightening_consumption_does_NOT_shrink_the_observed_population(self):
        f, inj = self._rows()
        loose = W2E.engineer_rung(f, inj, consumption_max_age_days=7.0)
        tight = W2E.engineer_rung(f, inj, consumption_max_age_days=1.0)
        obs_l = pd.to_numeric(loose["injury_report__observed"], errors="coerce")
        obs_t = pd.to_numeric(tight["injury_report__observed"], errors="coerce")
        assert obs_l.tolist() == obs_t.tolist() == [1.0, 1.0], (
            "coverage must stay on the 7-day bound for every rung, or the ladder confounds "
            "features with population")

    def test_tightening_consumption_DOES_drop_the_stale_designation(self):
        """The other side — the knob must actually do something (a no-op ladder tests nothing)."""
        f, inj = self._rows()
        loose = W2E.engineer_rung(f, inj, consumption_max_age_days=7.0).set_index("gsis_id")
        tight = W2E.engineer_rung(f, inj, consumption_max_age_days=1.0).set_index("gsis_id")
        assert float(loose.loc["A", "injury_report__listed"]) == 1.0
        assert float(tight.loc["A", "injury_report__listed"]) == 0.0, "A's 3d-old capture drops"
        assert float(tight.loc["B", "injury_report__listed"]) == 1.0, "B's fresh capture survives"
        # and the dropped row is NOT-LISTED (an observation), never NaN (unmeasured)
        assert float(tight.loc["A", "injury_report__observed"]) == 1.0
        assert not pd.isna(tight.loc["A", "injury_report__listed"])

    def test_the_freshest_rung_drops_a_SUPERSEDED_designation(self):
        """The carry-over extreme: A is listed only in an older capture that B's fresher capture
        has superseded ⇒ under `inj_freshest`, A reads NOT LISTED."""
        f, inj = self._rows()
        freshest = W2E.engineer_rung(f, inj, consumption_max_age_days=None).set_index("gsis_id")
        assert float(freshest.loc["B", "injury_report__listed"]) == 1.0
        assert float(freshest.loc["A", "injury_report__listed"]) == 0.0
        assert float(freshest.loc["A", "injury_report__observed"]) == 1.0

    def test_a_row_listed_in_the_freshest_capture_survives_every_rung(self):
        f, inj = self._rows()
        vals = [float(W2E.engineer_rung(f, inj, consumption_max_age_days=c)
                      .set_index("gsis_id").loc["B", "injury_report__listed"])
                for _, c in W2E.FRESHNESS_LADDER]
        assert vals == [1.0, 1.0, 1.0]


# ══ 3. The ladder is INERT before 2025 — mechanically ═══════════════════════════════════════════
class TestInertnessBefore2025:
    @staticmethod
    def _mixed():
        f = _feat([
            {"season": 2019, "week": 5, "gsis_id": "A", "_target_gameday": "2019-10-06"},
            {"season": 2019, "week": 5, "gsis_id": "B", "_target_gameday": "2019-10-06"},
            {"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"},
        ])
        inj = _inj(
            [{"season": 2019, "week": 5, "gsis_id": "A", "report_status": "out",
              "practice_status": W2D.CANONICAL_PRACTICE_DNP,
              "date_modified": "2019-10-02T00:00:00+00:00"}],   # 4 days out — a TIGHT rung would
            [_capture(2025, 5, "A", "2025-10-02T00:00:00+00:00", "out", "dnp")])  # drop it if it applied
        return f, inj

    def test_every_rung_leaves_the_legacy_rows_byte_identical(self):
        f, inj = self._mixed()
        rungs = {n: W2E.engineer_rung(f, inj, consumption_max_age_days=c)
                 for n, c in W2E.FRESHNESS_LADDER}
        got = W2E.assert_ladder_inert_before_2025(rungs)
        assert got["passes"] is True and got["state"] == "PASS"
        assert got["cells_compared"] > 0, "vacuity: the control must compare something"
        assert got["legacy_rows"] == 2
        # and specifically: a 4-day-old LEGACY stamp survives the 1-day rung
        tight = rungs["inj_fresh1d"]
        legacy_a = tight[(tight.season == 2019) & (tight.gsis_id == "A")]
        assert float(legacy_a["injury_report__listed"].iloc[0]) == 1.0

    def test_the_control_FAILS_when_a_rung_touches_the_legacy_era(self):
        f, inj = self._mixed()
        rungs = {n: W2E.engineer_rung(f, inj, consumption_max_age_days=c)
                 for n, c in W2E.FRESHNESS_LADDER}
        broken = rungs["inj_fresh1d"].copy()
        broken.loc[broken.season == 2019, "injury_report__listed"] = 0.0
        got = W2E.assert_ladder_inert_before_2025({**rungs, "inj_fresh1d": broken})
        assert got["passes"] is False and got["differences"]

    def test_the_control_REFUSES_a_frame_with_no_legacy_rows(self):
        f = _feat([{"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"}])
        inj = _inj([], [_capture(2025, 5, "A", "2025-10-02T00:00:00+00:00")])
        rungs = {n: W2E.engineer_rung(f, inj, consumption_max_age_days=c)
                 for n, c in W2E.FRESHNESS_LADDER}
        with pytest.raises(ValueError, match="vacuous|no pre-2025"):
            W2E.assert_ladder_inert_before_2025(rungs)


# ══ 4. Population identity + activity ═══════════════════════════════════════════════════════════
class TestPopulationAndActivity:
    @staticmethod
    def _rungs():
        f = _feat([{"season": 2025, "week": 5, "gsis_id": g, "_target_gameday": "2025-10-05"}
                   for g in ("A", "B", "C")])
        inj = _inj([], [_capture(2025, 5, "A", "2025-10-02T00:00:00+00:00"),
                        _capture(2025, 5, "B", "2025-10-04T19:12:00+00:00", src="espn")])
        return {n: W2E.engineer_rung(f, inj, consumption_max_age_days=c)
                for n, c in W2E.FRESHNESS_LADDER}

    def test_the_population_is_identical_across_rungs(self):
        got = W2E.assert_population_identical(self._rungs())
        assert got["passes"] is True
        assert len({v["observed_rows"] for v in got["per_rung"].values()}) == 1

    def test_it_FAILS_when_a_rung_changes_the_observed_set(self):
        rungs = self._rungs()
        broken = rungs["inj_freshest"].copy()
        broken.loc[0, "injury_report__observed"] = 0.0
        got = W2E.assert_population_identical({**rungs, "inj_freshest": broken})
        assert got["passes"] is False and got["mismatched_rungs"] == ["inj_freshest"]

    def test_activity_counts_fall_monotonically_down_the_ladder(self):
        act = W2E.ladder_activity(self._rungs())
        counts = [act[n]["listed_capture_era_rows"] for n in W2E.LADDER_ARMS]
        assert counts == sorted(counts, reverse=True), counts
        assert act[W2E.INCUMBENT_RUNG]["share_of_incumbent"] == 1.0


# ══ 5. The clustered read — rows in a week are not independent draws ════════════════════════════
class TestClusteredRead:
    def test_the_clustered_se_exceeds_the_naive_one_under_shared_cluster_noise(self):
        rng = np.random.default_rng(0)
        cl = np.repeat(np.arange(12), 40)
        d = rng.normal(0.1, 1.0, 480) + np.repeat(rng.normal(0, 1.0, 12), 40)
        got = W2E.clustered_paired_delta(d, cl)
        assert got["state"] == "OK" and got["n_clusters"] == 12
        assert got["clustered_se"] > got["naive_se"]
        assert got["se_inflation_x"] > 1.0

    def test_it_can_overturn_a_naive_significance(self):
        """The reason the clustered SE is the PRIMARY and not a footnote."""
        rng = np.random.default_rng(0)
        cl = np.repeat(np.arange(10), 50)
        d = rng.normal(0.15, 1.0, 500) + np.repeat(rng.normal(0, 0.9, 10), 50)
        got = W2E.clustered_paired_delta(d, cl)
        naive_excludes_zero = abs(got["mean_delta"]) > 1.96 * got["naive_se"]
        assert naive_excludes_zero and got["spans_zero"], (
            "this fixture must be one where the naive SE would have claimed significance the "
            "clustered SE refuses — otherwise the guard proves nothing")

    @pytest.mark.parametrize("delta,clusters", [
        (np.array([1.0]), np.array([1])),                 # n < 2
        (np.ones(50), np.zeros(50)),                      # a single cluster
    ])
    def test_it_fails_CLOSED_rather_than_substituting_the_naive_se(self, delta, clusters):
        got = W2E.clustered_paired_delta(delta, clusters)
        assert got["state"] == "UNEVALUABLE"
        assert "mean_delta" not in got or got.get("clustered_se") is None


# ══ 6. Runner-level controls fail closed ════════════════════════════════════════════════════════
class TestRunnerControls:
    def test_the_measured_tie_control_is_unevaluable_when_its_folds_were_not_scored(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        got = R.measured_tie_control([{"label": "2025H1", "scores": {}}])
        assert got["state"] == "UNEVALUABLE" and got["passes"] is False
        assert got["missing_folds"] == list(W2E.MEASURED_TIE_FOLDS)

    def test_the_measured_tie_control_PASSES_on_agreeing_rungs_and_compared_something(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        scores = {arm: {p: 1.0 for p in WP.POSITIONS} for arm in W2E.LADDER_ARMS}
        got = R.measured_tie_control([{"label": f, "scores": scores}
                                      for f in W2E.MEASURED_TIE_FOLDS])
        assert got["passes"] is True
        assert got["comparisons"] == len(W2E.MEASURED_TIE_FOLDS) * 2 * len(WP.POSITIONS)

    def test_the_measured_tie_control_FAILS_on_a_disagreeing_rung(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        scores = {arm: {p: 1.0 for p in WP.POSITIONS} for arm in W2E.LADDER_ARMS}
        scores["inj_fresh1d"] = {p: 1.0 + 1e-6 for p in WP.POSITIONS}
        got = R.measured_tie_control([{"label": f, "scores": scores}
                                      for f in W2E.MEASURED_TIE_FOLDS])
        assert got["passes"] is False and got["differences"]

    def test_an_invalid_run_refuses_to_report_a_freshness_effect(self):
        body = _RUNNER.read_text()
        assert "INVALID RUN" in body
        assert "nothing below is a freshness effect" in body
        assert body.index("if not valid:") < body.index('"verdict_text": verdict_text')

    def test_the_alignment_control_refuses_misaligned_rungs(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        a = pd.DataFrame({"season": [2025, 2025], "week": [1, 2], "gsis_id": ["A", "B"]})
        b = a.iloc[::-1].reset_index(drop=True)
        got = R.assert_rows_aligned({W2E.INCUMBENT_RUNG: a, "inj_fresh1d": a, "inj_freshest": b})
        assert got["passes"] is False and got["misaligned_rungs"] == ["inj_freshest"]

    def test_the_stratifier_validation_refuses_a_thin_pair_set(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        store = pd.DataFrame([_capture(2025, 5, "A", "2025-10-02T00:00:00+00:00")])
        feat = _feat([{"season": 2025, "week": 5, "gsis_id": "A",
                       "_target_gameday": "2025-10-05"}])
        got = R.stratifier_validation(store, feat)
        assert got["state"] == "UNEVALUABLE", "a stratifier that cannot be validated may not be read"


# ══ 6b. The reading aids: multiplicity + the cross-era check ════════════════════════════════════
class TestReadingAids:
    @staticmethod
    def _cap(deltas: dict[str, dict[str, tuple[float, float]]]) -> dict:
        return {"per_rung": {arm: {pos: {"state": "OK", "mean_delta": d, "clustered_se": se}
                                   for pos, (d, se) in by.items()}
                             for arm, by in deltas.items()}}

    def test_bh_is_computed_over_EVERY_reported_comparison_not_just_the_headline(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        cap = self._cap({arm: {p: (0.01, 0.005) for p in WP.POSITIONS}
                         for arm in ("inj_fresh1d", "inj_freshest")})
        got = R.multiplicity_note(cap)
        assert got["n_comparisons"] == 8, "2 rungs x 4 positions must all be corrected"
        assert all("bh_cutoff_q10" in c for c in got["comparisons"])
        assert got["comparisons"][0]["bh_cutoff_q10"] < got["comparisons"][-1]["bh_cutoff_q10"]

    def test_an_ALL_row_is_excluded_so_the_pooled_read_does_not_inflate_the_correction(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        cap = self._cap({"inj_fresh1d": {**{p: (0.01, 0.005) for p in WP.POSITIONS},
                                         "ALL": (0.01, 0.005)}})
        assert R.multiplicity_note(cap)["n_comparisons"] == len(WP.POSITIONS)

    def test_it_is_unevaluable_when_nothing_is_comparable(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        assert R.multiplicity_note({"per_rung": {}})["state"] == "UNEVALUABLE"

    def test_the_cross_era_check_reads_BOTH_directions(self):
        """⭐ A within-era gradient licenses an era EXPLANATION only if the eras differ in the
        right direction — so this reader must be able to say both things."""
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )

        def frame(legacy_age_days, capture_age_days):
            rows, stamps = [], []
            for season, age in ((2019, legacy_age_days), (2025, capture_age_days)):
                for i in range(40):
                    gd = pd.Timestamp(f"{season}-10-06")
                    rows.append({"season": season, "week": 5, "gsis_id": f"P{i}",
                                 "_target_gameday": gd, "position": "WR",
                                 "label": WF.LABEL_PLAYED, "injury_report__listed": 1.0})
                    stamps.append(gd.tz_localize("UTC") - pd.Timedelta(days=age))
            df = pd.DataFrame(rows)
            df["_inj_dm_utc"] = stamps
            return df

        fresher = R.era_stratum_shares(frame(legacy_age_days=3.0, capture_age_days=0.5))
        assert fresher["capture_era_is_fresher_on_this_cut"] is True
        assert "cannot explain" in fresher["reading"]
        staler = R.era_stratum_shares(frame(legacy_age_days=0.5, capture_age_days=3.0))
        assert staler["capture_era_is_fresher_on_this_cut"] is False
        assert "directionally CAPABLE" in staler["reading"]
        assert staler["caveat"], "the not-the-same-clock caveat must always ride along"

    def test_a_ci_that_spans_zero_is_narrated_as_a_TIE_not_a_loss(self):
        """⭐ The distinction the whole carry-over reading rests on.

        `inj_freshest` pooled is -0.0008 with a CI spanning zero — dropping every superseded
        designation changes NOTHING, which REFUTES carry-over as the mechanism. A two-way
        BEATS/LOSES word narrates that same number as a LOSS, i.e. as weak evidence that carrying
        stale designations HELPS, which is the opposite conclusion off identical arithmetic
        (NF1.8: a direction statistic cannot tell a tie from a loss).

        One ISOLATING fixture per branch (NF-D17) — each holds `spans_zero` and the sign
        independently so exactly one clause can decide the word.
        """
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        # sign NEGATIVE both times; only spans_zero differs ⇒ isolates the tie clause
        assert R.direction_word({"mean_delta": -0.00076, "spans_zero": True}) == "TIES"
        assert R.direction_word({"mean_delta": -0.03523, "spans_zero": False}) == "LOSES TO"
        # sign POSITIVE both times; only spans_zero differs ⇒ isolates it from the other side
        assert R.direction_word({"mean_delta": 0.00076, "spans_zero": True}) == "TIES"
        assert R.direction_word({"mean_delta": 0.03523, "spans_zero": False}) == "BEATS"
        # spans_zero FIXED False; only the sign differs ⇒ isolates the sign clause
        assert R.direction_word({"mean_delta": 1.0, "spans_zero": False}) == "BEATS"
        assert R.direction_word({"mean_delta": -1.0, "spans_zero": False}) == "LOSES TO"

    def test_an_unevaluable_read_fails_closed_to_TIES(self):
        """NF1.7 (a): an absent `spans_zero` is a check that did not run, never a directional
        finding. A default of False would narrate a missing interval as a certified direction."""
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        assert R.direction_word({}) == "TIES"
        assert R.direction_word({"mean_delta": -0.5}) == "TIES"

    def test_the_verdict_text_is_DERIVED_by_both_paths_not_stored(self):
        """A stored verdict sentence cannot be corrected without a 17-minute refit, which is the
        pressure that leaves a known-wrong sentence in an artifact. Both the scoring path and
        `--reanalyze` must build it from the same pure function."""
        body = _RUNNER.read_text()
        calls = re.findall(r"compose_verdict_text\s*\(", body)
        assert len(calls) >= 3, (
            f"expected a def + a call on each path, found {len(calls)} occurrences")
        reanalyze = body[body.index("def _reanalyze("):body.index("def main(")]
        assert 'out["verdict_text"] = compose_verdict_text(' in reanalyze, (
            "--reanalyze must RE-DERIVE the verdict text, not write the stored one through")

    def test_an_invalid_run_never_gets_a_direction_sentence(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        cap = self._cap({"inj_fresh1d": {"ALL": (-0.5, 0.01)}})
        cap["per_rung"]["inj_fresh1d"]["ALL"]["spans_zero"] = False
        bad = R.compose_verdict_text(False, {"inert": {"state": "FAIL", "passes": False}}, cap)
        assert "INVALID RUN" in bad and "LOSES TO" not in bad
        good = R.compose_verdict_text(True, {}, cap)
        assert "LOSES TO" in good, "a valid run with a real direction must still say it"

    def test_an_absent_interval_never_reads_as_excluding_zero(self):
        """The word and the parenthetical must fail closed TOGETHER — 'TIES … (excludes zero)'
        is a self-contradicting sentence, and the half a reader trusts is the parenthetical."""
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        txt = R.compose_verdict_text(True, {}, self._cap({"inj_fresh1d": {"ALL": (-0.5, 0.01)}}))
        assert "TIES" in txt and "interval UNEVALUABLE" in txt
        assert "excludes zero" not in txt and "spans zero" not in txt

    def test_the_cross_era_check_is_unevaluable_with_no_listed_rows(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        df = pd.DataFrame({"season": [2025], "week": [5], "gsis_id": ["A"],
                           "_target_gameday": [pd.Timestamp("2025-10-05")],
                           "injury_report__listed": [0.0], "_inj_dm_utc": [pd.NaT]})
        assert R.era_stratum_shares(df)["state"] == "UNEVALUABLE"


# ══ 7. Deploy-held ══════════════════════════════════════════════════════════════════════════════
class TestDeployHeld:
    def test_nothing_writes_to_a_registry_or_serving_surface(self):
        forbidden = ("append_captures", "put_object", "--publish", "stage_registry",
                     "POST_FLIP_SPEC", "boto3.client")
        for path in (_MODULE, _RUNNER):
            hits = [t for t in forbidden if t in path.read_text()]
            assert not hits, f"{path.name}: {hits}"

    def test_the_incumbent_construction_is_not_modified_by_this_story(self):
        """NF-W2e may MEASURE an alternative construction; it may not change NF-W2d's."""
        assert dict(W2E.FRESHNESS_LADDER)[W2E.INCUMBENT_RUNG] == W2D.COVERAGE_MAX_AGE_DAYS
        w2d_src = Path(W2D.__file__).read_text()
        assert "COVERAGE_MAX_AGE_DAYS = 7.0" in w2d_src, (
            "the NF-W2d construction constant must be untouched by NF-W2e")


# ══ 8. RED-proofs (mutation asserted to have landed) ════════════════════════════════════════════
class TestRedProofs:
    @staticmethod
    def _mutated(old: str, new: str):
        src = _MODULE.read_text()
        assert old in src, f"RED-proof target not found: {old!r}"
        m = src.replace(old, new, 1)
        assert m != src, "the mutation did not change the source — it would no-op"
        mod = types.ModuleType("w2e_mut")
        mod.__file__ = str(_MODULE)
        exec(compile(m, str(_MODULE), "exec"), mod.__dict__)  # noqa: S102 — test harness
        return mod

    @staticmethod
    def _mutated_runner(old: str, new: str):
        src = _RUNNER.read_text()
        assert old in src, f"RED-proof target not found: {old!r}"
        m = src.replace(old, new, 1)
        assert m != src, "the mutation did not change the source — it would no-op"
        mod = types.ModuleType("w2e_runner_mut")
        mod.__file__ = str(_RUNNER)
        exec(compile(m, str(_RUNNER), "exec"), mod.__dict__)  # noqa: S102 — test harness
        return mod

    def test_a_two_way_direction_word_mislabels_THIS_STORYS_headline_as_a_loss(self):
        """The pre-fix wording was `BEATS if mean_delta > 0 else LOSES TO` — two-way, so a CI
        spanning zero could only come out as a LOSS. Fed the ACTUAL pooled `inj_freshest` read
        (-0.00076, CI [-0.01499, 0.01348]) it says LOSES TO, which reads as evidence that
        carrying stale designations HELPS — the opposite of the measured conclusion (a tie ⇒
        carry-over REFUTED). Same arithmetic, inverted finding."""
        mod = self._mutated_runner(
            'if all_read.get("spans_zero", True):\n        return "TIES"\n    return',
            "return")
        real = {"mean_delta": -0.00076, "spans_zero": True}
        assert mod.direction_word(real) == "LOSES TO", (
            "the mutation must land: the two-way word must narrate the real tie as a loss")
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w2e_capture_freshness as R,
        )
        assert R.direction_word(real) == "TIES"

    def test_collapsing_coverage_into_consumption_shrinks_the_population_and_is_caught(self):
        """⭐ THE defect the separation exists to prevent: if coverage followed the consumption
        bound, tightening the ladder would change the SCORED ROWS, and every rung comparison
        would confound features with population."""
        mod = self._mutated(
            "f = W2D.attach_coverage(feat, injuries, max_age_days=W2D.COVERAGE_MAX_AGE_DAYS)",
            "f = W2D.attach_coverage(feat, injuries, max_age_days=(consumption_max_age_days "
            "or W2D.COVERAGE_MAX_AGE_DAYS))")
        # ⭐ ISOLATING fixture: coverage is a WEEK-level property, so week 5 (whose freshest
        # capture is 0.2 d old) stays covered under either bound and would prove nothing. Week 9's
        # ONLY capture is 3 days old — under a 7-day coverage bound it is covered, under a 1-day
        # one it is not. That is the row the collapse moves.
        f = _feat([{"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"},
                   {"season": 2025, "week": 5, "gsis_id": "B", "_target_gameday": "2025-10-05"},
                   {"season": 2025, "week": 9, "gsis_id": "A", "_target_gameday": "2025-11-02"}])
        inj = _inj([], [_capture(2025, 5, "A", "2025-10-02T00:00:00+00:00"),
                        _capture(2025, 5, "B", "2025-10-04T19:12:00+00:00", src="espn"),
                        _capture(2025, 9, "A", "2025-10-30T00:00:00+00:00")])
        broken = {n: mod.engineer_rung(f, inj, consumption_max_age_days=c)
                  for n, c in W2E.FRESHNESS_LADDER}
        assert mod.assert_population_identical(broken)["passes"] is False, (
            "the mutation must land: collapsing the bounds changes the observed population")
        live = {n: W2E.engineer_rung(f, inj, consumption_max_age_days=c)
                for n, c in W2E.FRESHNESS_LADDER}
        assert W2E.assert_population_identical(live)["passes"] is True

    def test_a_ladder_rung_that_leaked_into_the_legacy_era_is_caught(self):
        """Applying the consumption bound to the LEGACY path too would silently reprice 2016–2024,
        and the 'freshness effect' would really be a legacy leak. The inertness control is what
        stands between those two readings, so it must be shown to FIRE on the leak."""
        mod = self._mutated(
            'f = f.merge(legacy[keep], on=["season", "week", "gsis_id"], how="left")',
            'legacy = legacy[pd.to_datetime(legacy["_dm_utc"], utc=True) '
            '>= pd.Timestamp("2100-01-01", tz="UTC")] if consumption_max_age_days == 1.0 '
            'else legacy\n    f = f.merge(legacy[keep], on=["season", "week", "gsis_id"], '
            'how="left")')
        f = _feat([
            {"season": 2019, "week": 5, "gsis_id": "A", "_target_gameday": "2019-10-06"},
            {"season": 2025, "week": 5, "gsis_id": "A", "_target_gameday": "2025-10-05"},
        ])
        inj = _inj([{"season": 2019, "week": 5, "gsis_id": "A", "report_status": "out",
                     "practice_status": W2D.CANONICAL_PRACTICE_DNP,
                     "date_modified": "2019-10-02T00:00:00+00:00"}],
                   [_capture(2025, 5, "A", "2025-10-02T00:00:00+00:00")])
        broken = {n: mod.engineer_rung(f, inj, consumption_max_age_days=c)
                  for n, c in W2E.FRESHNESS_LADDER}
        leaked = broken["inj_fresh1d"]
        assert float(leaked.loc[leaked.season == 2019, "injury_report__listed"].iloc[0]) == 0.0, (
            "the mutation must land: the tight rung repriced a LEGACY row")
        assert mod.assert_ladder_inert_before_2025(broken)["passes"] is False, (
            "the inertness control MUST fire on a legacy leak")
        live = {n: W2E.engineer_rung(f, inj, consumption_max_age_days=c)
                for n, c in W2E.FRESHNESS_LADDER}
        assert W2E.assert_ladder_inert_before_2025(live)["passes"] is True

    def test_dropping_the_cluster_correction_understates_the_se(self):
        mod = self._mutated("var = (gsum ** 2).sum() / (n ** 2) * (k / (k - 1))",
                            "var = d.var(ddof=1) / n")
        rng = np.random.default_rng(0)
        cl = np.repeat(np.arange(12), 40)
        d = rng.normal(0.1, 1.0, 480) + np.repeat(rng.normal(0, 1.0, 12), 40)
        broken, live = mod.clustered_paired_delta(d, cl), W2E.clustered_paired_delta(d, cl)
        assert np.isclose(broken["clustered_se"], broken["naive_se"], rtol=1e-6), (
            "the mutation must land: the 'clustered' SE collapses to the naive one")
        assert live["clustered_se"] > live["naive_se"]

    def test_a_verdict_constant_that_claimed_certification_would_be_caught(self):
        mod = self._mutated('VERDICT_W2E = "NO_CERTIFICATION_POSSIBLE"', 'VERDICT_W2E = "SHIP"')
        assert mod.VERDICT_W2E == "SHIP"
        assert W2E.VERDICT_W2E == "NO_CERTIFICATION_POSSIBLE", (
            "the live constant must refuse to certify at 2 active folds")

    def test_moving_the_middle_rung_off_the_validated_boundary_is_caught(self):
        mod = self._mutated('("inj_fresh1d", 1.0),', '("inj_fresh1d", 2.5),')
        assert dict(mod.FRESHNESS_LADDER)["inj_fresh1d"] == 2.5
        with pytest.raises(AssertionError):
            assert (dict(mod.FRESHNESS_LADDER)["inj_fresh1d"]
                    == mod.VALIDATED_STRATUM_BOUNDARY_DAYS)
        assert (dict(W2E.FRESHNESS_LADDER)["inj_fresh1d"]
                == W2E.VALIDATED_STRATUM_BOUNDARY_DAYS)
