"""E7.16 — the point-in-time MLB Pipeline comp cohort + the leakage scan + E7.14's source study.

Fast-gate: pure numpy/pandas plus a LOCAL DuckDB fixture for the assembly SQL. No S3, no Snowflake.

Every test here pins a failure that produces a BETTER-LOOKING answer than the honest one, which is
the only class this story could have shipped wrong:

  * an as-of feature that is secretly post-hoc (the whole reason the cohort was rebuilt);
  * a leak DETECTOR that flags nothing because it can flag nothing (NF1.7 (a));
  * an ordering arm scored on a different, easier population than its foil;
  * a "we tested it, nothing there" that is really "our gate is unattainable at this N".
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.prospect_board import build_pipeline_cohort as bpc
from betting_ml.scripts.prospect_board import run_e7_14_source_accuracy as e714
from betting_ml.scripts.prospect_board import run_e7_16_pipeline_comps as e716
from betting_ml.scripts.prospect_board.comp_validation import (
    LEAK_BLOCK_PURITY,
    LEAK_BLOCK_SHARE,
    leakage_scan,
)

_RNG = np.random.default_rng(716)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. As-of age — the single line that keeps the archive point-in-time
# ══════════════════════════════════════════════════════════════════════════════════════════════


class TestAsOfAge:
    def test_the_buxton_case_age_is_as_of_the_board_not_as_of_today(self):
        """⭐ THE MEASURED CONTAMINATION, pinned. MLB's archived page returns Byron Buxton's CURRENT
        age (32) on the 2015 board, where he was 21. Reading `age_current` would put eleven years of
        hindsight into a point-in-time feature; the birth date is static and the board date is
        known, so the honest value is exactly computable."""
        age = bpc.as_of_age(pd.Series(["1993-12-18"]), pd.Series(["2015-02-01"]))
        assert age.iloc[0] == pytest.approx(21.1, abs=0.1)

    def test_it_never_reads_a_current_suffixed_column(self):
        """The `_current` suffix exists so this mistake is visible at the call site. Make it
        mechanical: the assembly SQL must not select ANY of them."""
        sql = bpc._assembly_sql(3, 2015, 2022)
        for col in ("age_current", "org_current", "affiliate_team_current",
                    "parent_org_name_current"):
            assert col not in sql, f"{col} is a LIVE record, not an as-of one (mlb_pipeline.py §1)"

    def test_a_missing_birth_date_is_nan_not_a_fabricated_age(self):
        age = bpc.as_of_age(pd.Series([None, ""]), pd.Series(["2015-02-01", "2015-02-01"]))
        assert age.isna().all()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The assembly SQL, executed for real against a local DuckDB fixture
# ══════════════════════════════════════════════════════════════════════════════════════════════


def _fixture_conn():
    """A local stand-in for the three lakehouse sources. The point is that the REAL SQL string runs:
    a lakehouse assembly is otherwise CI-invisible and a broken one is found only after an S3 read."""
    duckdb = pytest.importorskip("duckdb")
    conn = duckdb.connect()
    conn.execute("""
        create table pipeline_ranks as select * from (values
          (2015, '2015-02-01', '111', 'top100', 5,  'SS',  'Alpha One',  '1994-06-01', 2018, 2012, 55.0, 2015, null),
          (2015, '2015-02-01', '111', 'org',    1,  'SS',  'Alpha One',  '1994-06-01', 2018, 2012, 55.0, 2015, 'LAD'),
          (2015, '2015-02-01', '222', 'org',    2,  'RHP', 'Beta Two',   '1993-01-15', 2017, 2011, 45.0, 2015, 'LAD'),
          (2015, '2015-02-01', '333', 'org',    3,  'CF',  'Gamma Three','1996-03-20', 2019, 2014, 40.0, 2015, 'SFG')
        ) t(season, as_of_date, mlbam_id, list_type, rank, position, player_name, birth_date,
            eta, draft_year, pipeline_grade_overall, bio_season, org)
    """)
    conn.execute("""
        create table milb_logs as select * from (values
          ('111', '2014-06-01', 2014, 'Double-A', true,  false, 'R'),
          ('111', '2014-07-01', 2014, 'Triple-A', true,  false, 'R'),
          ('222', '2014-06-01', 2014, 'Double-A', false, true,  'R'),
          ('333', '2014-06-01', 2014, 'Single-A', true,  false, 'R'),
          ('111', '2015-06-01', 2015, 'Triple-A', true,  false, 'R')
        ) t(player_id, official_date, season, level_name, is_batter, is_pitcher, game_type)
    """)
    for col in bpc._BAT_SUMS + bpc._PIT_SUMS:
        conn.execute(f"alter table milb_logs add column {col} double default 10")
    conn.execute("""
        create table mart_batter_rolling_stats as select * from (values
          ('111', '2016-05-01', 2016, 400, 110, 20, 40, 90),
          ('111', '2014-05-01', 2014,  30,   8,  1,  3,  9)
        ) t(batter_id, game_date, game_year, pa_count, hits, home_runs, walks, strikeouts)
    """)
    conn.execute("""
        create table mart_pitcher_rolling_stats as select * from (values
          ('222', '2016-05-01', 2016, 500, 100, 40, 130, 12)
        ) t(pitcher_id, game_date, game_year, batters_faced, hits_allowed, walks, strikeouts,
            home_runs_allowed)
    """)
    return conn


class TestAssemblySQL:
    def test_the_real_sql_runs_and_collapses_a_player_to_one_row_per_season(self):
        """⭐ A ranked player is on BOTH the Top 100 and his org list. Those are two views of ONE
        opinion; keeping both would double-count one realized outcome — E7.13 defect 2.3 one level
        up (there it was one person across seasons, here within a season)."""
        conn = _fixture_conn()
        raw = conn.execute(bpc._assembly_sql(3, 2015, 2022)).df()
        assert len(raw) == 3, "one row per (season, player), not one per list"
        alpha = raw.loc[raw["mlbam_id"] == "111"].iloc[0]
        assert alpha["overall_rank"] == 5 and alpha["org_rank"] == 1, "both ranks survive the collapse"

    def test_the_minor_line_is_strictly_before_the_board_date(self):
        """The as-of guard. Alpha has a 2015-06-01 game — AFTER the 2015-02-01 board — which must
        not enter his as-of line, or the comp is keyed to the query's own future."""
        conn = _fixture_conn()
        raw = conn.execute(bpc._assembly_sql(3, 2015, 2022)).df()
        alpha = raw.loc[raw["mlbam_id"] == "111"].iloc[0]
        assert alpha["milb_games"] == 2, "the post-board game leaked into the as-of line"
        assert alpha["top_level_pre_board"] == "Triple-A"

    def test_pre_board_mlb_exposure_is_a_control_not_an_outcome(self):
        """Alpha's 2014 MLB cameo predates the board: it belongs in `pre_board_mlb_pa` (a control)
        and must NOT be counted in the outcome window."""
        conn = _fixture_conn()
        raw = conn.execute(bpc._assembly_sql(3, 2015, 2022)).df()
        alpha = raw.loc[raw["mlbam_id"] == "111"].iloc[0]
        assert alpha["pre_board_mlb_pa"] == 30
        assert alpha["mlb_pa"] == 400, "the outcome window must exclude pre-board exposure"

    def test_a_player_who_never_reached_mlb_carries_zeros_not_nulls(self):
        """The survivorship decision, at the source: a bust is a realized 0, never missing data."""
        conn = _fixture_conn()
        raw = conn.execute(bpc._assembly_sql(3, 2015, 2022)).df()
        df, _ = bpc._derive(raw, horizon=3, min_debut_pa=100, min_debut_bf=150)
        gamma = df.loc[df["mlbam_id"] == "333"].iloc[0]
        assert gamma["fantasy_points"] == 0.0 and not gamma["debuted"]


class TestDerive:
    def test_a_bio_from_after_the_season_is_a_hard_stop(self):
        """The whole premise of this cohort is that the grade is as-of. A future-dated scouting
        report means `mlb_pipeline._select_bio` has regressed, and the study must not run on it."""
        conn = _fixture_conn()
        raw = conn.execute(bpc._assembly_sql(3, 2015, 2022)).df()
        raw.loc[0, "bio_season"] = 2018
        with pytest.raises(bpc.CohortValidationError, match="DATED AFTER"):
            bpc._derive(raw, horizon=3, min_debut_pa=100, min_debut_bf=150)

    def test_player_type_comes_from_the_position_then_the_game_logs(self):
        conn = _fixture_conn()
        raw = conn.execute(bpc._assembly_sql(3, 2015, 2022)).df()
        df, rep = bpc._derive(raw, horizon=3, min_debut_pa=100, min_debut_bf=150)
        types = dict(zip(df["mlbam_id"], df["player_type"]))
        assert types["111"] == "batter" and types["222"] == "pitcher"
        assert rep["unknown_position_tokens"] == []


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The leakage scan — and the proof it can fire
# ══════════════════════════════════════════════════════════════════════════════════════════════


def _leak_frame(n=2000, leak_share=0.35):
    """A cohort with (a) an honest graded predictor and (b) a post-hoc status column carrying the
    measured `level` signature: a large block of rows of which essentially none debuted."""
    grade = _RNG.normal(0, 1, n)
    debuted = _RNG.random(n) < 1 / (1 + np.exp(-grade))
    status = np.where(np.arange(n) < int(n * leak_share), "minors", "MLB")
    debuted[np.arange(n) < int(n * leak_share)] = False       # the one-sided block
    return pd.DataFrame({"debuted": debuted, "honest_grade": grade, "post_hoc_status": status})


class TestLeakageScan:
    def test_it_fires_on_the_one_sided_block(self):
        """⭐ THE POSITIVE CONTROL. E7.13's `level` was caught by exactly this crosstab: 1,908 rows
        on one side of which ONE debuted. A detector that has never fired on a known positive
        carries no information when it comes back clean (NF1.7 (a))."""
        scan = leakage_scan(_leak_frame(), ["post_hoc_status", "honest_grade"])
        row = scan.set_index("column").loc["post_hoc_status"]
        assert bool(row["leak_flag"])
        assert row["one_sided_bin_share"] >= LEAK_BLOCK_SHARE
        assert row["one_sided_bin_debut_rate"] <= LEAK_BLOCK_PURITY

    def test_an_honest_graded_predictor_does_not_fire(self):
        """The other half of the two-sided proof: a real scouting grade separates the outcome (the
        live `fv` sits at AUC 0.70) without producing a pure block. Flagging it would make the scan
        useless — every informative feature would be a 'leak'."""
        scan = leakage_scan(_leak_frame(), ["post_hoc_status", "honest_grade"])
        row = scan.set_index("column").loc["honest_grade"]
        assert not bool(row["leak_flag"])
        assert 0.6 < row["auc_vs_outcome"] < 0.75

    def test_a_numeric_column_is_binned_so_the_block_test_applies_to_it_too(self):
        """A post-hoc NUMERIC column shows up as a pure decile, not as a high AUC — so binning is
        load-bearing, not cosmetic."""
        df = _leak_frame()
        df["post_hoc_numeric"] = np.where(df["post_hoc_status"] == "minors", -99.0,
                                          _RNG.normal(0, 1, len(df)))
        scan = leakage_scan(df, ["post_hoc_numeric"]).set_index("column")
        assert bool(scan.loc["post_hoc_numeric", "leak_flag"])

    def test_an_absent_column_is_reported_absent_not_silently_skipped(self):
        scan = leakage_scan(_leak_frame(), ["nope"]).set_index("column")
        assert scan.loc["nope", "present"] is False or not scan.loc["nope", "present"]


class TestLeakageControl:
    def test_a_scan_that_cannot_fire_is_a_hard_stop(self):
        """If the control cohort no longer reproduces the known leak, the clean verdict on the
        Pipeline cohort proves nothing — so it raises rather than reporting a pass."""
        clean = _leak_frame(leak_share=0.0)
        clean["level"] = "MLB"
        with pytest.raises(e716.LeakageControlError, match="did NOT flag"):
            e716.leakage_report(_leak_frame(), clean)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Matched support — the ordering defect E7.16 found and fixed
# ══════════════════════════════════════════════════════════════════════════════════════════════


class TestMatchedSupport:
    def test_an_arm_defined_on_an_easier_subpopulation_cannot_win_on_that_alone(self):
        """⭐ THE REGRESSION TEST FOR THE E7.16 ORDERING FIX.

        Construct a `narrow` arm that is defined ONLY on the easy half of the cohort and is a pure
        COPY of the incumbent there — it carries exactly zero extra skill. Scored the naive way (each
        arm on its own finite rows) it beats the incumbent outright, because the easy half is easier
        to order. On matched support it must tie. Measured on the live data this defect was worth
        +0.0935 of apparent rank-IC on batters — 87% of the headline it produced.
        """
        from betting_ml.scripts.prospect_board.comp_validation import rank_ic

        n = 800
        easy = np.arange(n) < n // 2
        signal = _RNG.normal(0, 1, n)
        # the easy half is ordered almost perfectly; the hard half is nearly noise
        y = np.where(easy, signal + _RNG.normal(0, 0.2, n), signal + _RNG.normal(0, 3.0, n))
        incumbent = signal
        narrow = np.where(easy, signal, np.nan)          # identical content, narrower support

        naive = rank_ic(narrow, y) - rank_ic(incumbent, y)
        matched = rank_ic(narrow[easy], y[easy]) - rank_ic(incumbent[easy], y[easy])
        assert naive > 0.05, "the fixture must reproduce the defect for the test to mean anything"
        assert matched == pytest.approx(0.0, abs=1e-9), (
            "on matched support a content-identical arm must TIE — any residual is the population, "
            "which is exactly what the fix removes")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Verdict logic — a clean fold plan is what discharges E7.13's withheld ship
# ══════════════════════════════════════════════════════════════════════════════════════════════


class TestVerdict:
    def test_clearing_the_gates_on_a_relaxed_plan_is_still_not_a_ship(self):
        """E7.13's exact situation: every gate cleared, on folds that grant hindsight."""
        assert e716._verdict({"blend_gates_all_pass": True}, strict=False) \
            == "BLEND_ELIGIBLE_NOT_WIRED"

    def test_clearing_them_on_a_strictly_matured_plan_discharges_the_caveat(self):
        assert e716._verdict({"blend_gates_all_pass": True}, strict=True) == "BLEND_WIRE"

    def test_a_failed_gate_is_display_only_on_either_plan(self):
        for strict in (True, False):
            assert e716._verdict({"blend_gates_all_pass": False}, strict=strict) == "DISPLAY_ONLY"


class TestGateSensitivity:
    def test_it_names_the_binding_constraint_rather_than_blaming_dsr(self):
        """"It just missed DSR" is only true if DSR is the ONLY failing gate. When something else
        fails too, saying so is the difference between an attributable null and a shrug."""
        scored = {
            "gates": {"anchors_pass": True, "pbo_lt_0_2": True,
                      "dsr_contender_ge_0_95": False, "fdr_survives": False},
            "arms": {"a": {"crps": 100.0, "selectable": True},
                     "b": {"crps": 100.1, "selectable": True},
                     "anchor": {"crps": 1.0, "selectable": False}},
            "paired": {},
        }
        out = e716.gate_sensitivity(scored)
        assert out["binding_constraint"] == "not_dsr_alone"
        assert out["would_pass_without_the_dsr_gate"] is False
        assert set(out["failing_gates"]) == {"dsr_contender_ge_0_95", "fdr_survives"}

    def test_it_reports_how_wide_the_tie_the_selection_was_resolved_inside(self):
        """A pick made inside a 0.1% gap is a coin flip, and NF1.8 requires that be visible beside
        the verdict — reported, never re-picked on."""
        scored = {"gates": {"dsr_contender_ge_0_95": False},
                  "arms": {"a": {"crps": 100.0, "selectable": True},
                           "b": {"crps": 100.1, "selectable": True}},
                  "paired": {}}
        out = e716.gate_sensitivity(scored)
        assert out["selected"] == "a" and out["runner_up"] == "b"
        assert out["selection_margin_pct"] == pytest.approx(0.1, abs=0.01)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. E7.14 — power arithmetic and the cohort join
# ══════════════════════════════════════════════════════════════════════════════════════════════


class TestMultiplicityFloor:
    def test_five_folds_cannot_certify_anything_and_says_so(self):
        """⭐ The finding that keeps E7.14's null honest: with a fold sign test the smallest
        attainable p is 2/2^5 = 0.0625, while BH's rank-1 cutoff over 5 tests is 0.01. NO effect of
        any magnitude can pass — so "we tested it, nothing there" would be false."""
        out = e714._multiplicity_floor(5, 5)
        assert out["attainable"] is False
        assert out["smallest_attainable_sign_p"] == pytest.approx(0.0625)
        assert out["bh_rank1_cutoff"] == pytest.approx(0.01)
        assert out["folds_required_to_certify"] == 8

    def test_it_reports_attainable_once_the_folds_are_there(self):
        assert e714._multiplicity_floor(8, 5)["attainable"] is True


class TestFoldSignTest:
    def test_all_folds_agreeing_gives_the_floor_not_zero(self):
        assert e714._fold_sign_p(np.array([0.1] * 5)) == pytest.approx(0.0625)

    def test_a_split_decision_is_not_significant(self):
        assert e714._fold_sign_p(np.array([0.1, -0.1, 0.1, -0.1, 0.1])) > 0.5

    def test_zeros_are_dropped_not_counted_as_agreement(self):
        assert e714._fold_sign_p(np.array([0.1, 0.0, 0.1])) == pytest.approx(0.5)


class TestHeadToHead:
    def _cohorts(self):
        pipe = pd.DataFrame({
            "board_season": [2018, 2018, 2019], "player_key": ["1", "2", "1"],
            "overall_rank": [3, np.nan, 5], "org_rank": [1, 2, 1], "fv": [55.0, 45.0, 60.0],
            "org": ["LAD", "LAD", "LAD"], "player_type": ["batter"] * 3,
            "fantasy_points": [300.0, 0.0, 250.0],
        })
        fg = pd.DataFrame({
            "board_season": [2018, 2018, 2019], "player_key": ["1", "2", "3"],
            "overall_rank": [4, np.nan, 8], "org_rank": [2, 1, 1], "fv": [50.0, 50.0, 55.0],
            "org": ["LAD", "LAD", "SFG"], "as_of_date": ["2018-07-01"] * 3,
        })
        return pipe, fg

    def test_the_cohort_is_the_intersection_and_is_reported_before_scoring(self):
        pipe, fg = self._cohorts()
        both, rep = e714.build_head_to_head(pipe, fg)
        assert rep["head_to_head_rows"] == 2          # (2018,'1'), (2018,'2') — not (2019,'1')
        assert rep["head_to_head_seasons"] == [2018]
        assert set(both["player_key"]) == {"1", "2"}

    def test_a_duplicate_person_season_row_is_a_hard_stop(self):
        """A duplicate would double-count one realized outcome into the ordering statistic."""
        pipe, fg = self._cohorts()
        fg = pd.concat([fg, fg.iloc[[0]]], ignore_index=True)
        with pytest.raises(ValueError, match="duplicate"):
            e714.build_head_to_head(pipe, fg)

    def test_org_ranks_are_compared_within_org_not_across_orgs(self):
        """An org rank is a statement about a club's farm. Comparing '3rd best Dodger' with '3rd
        best Rockie' on one scale is not a comparison — both sources get the same handicap."""
        df = pd.DataFrame({"board_season": [2018] * 4, "org": ["LAD", "LAD", "SFG", "SFG"],
                           "r": [1, 2, 1, 2]})
        pct = e714._within_org_pctile(df, "r")
        assert pct.iloc[0] == pct.iloc[2] and pct.iloc[1] == pct.iloc[3]
        assert pct.iloc[0] > pct.iloc[1]
