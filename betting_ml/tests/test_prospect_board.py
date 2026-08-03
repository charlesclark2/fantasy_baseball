"""E8.0 — the LEAN prospect draft board (`betting_ml/scripts/prospect_board/`).

Fast-gate: pure pandas, no IO, no `pipeline` import. Everything here pins a rule that would fail
QUIETLY on draft day — a player silently missing from the AL sheet, a projection scored as if a
missing metric were a bad one, a 20-PA sample outranking a 400-PA one, or the E7.8 position
asymmetry drifting out of the blend.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.prospect_board.board_assembly import (
    AGE_WEIGHT_IN_MODEL_SCORE,
    BOARD_LEVEL_RANK,
    EXPORT_DROP_COLUMNS,
    FV_WEIGHT_BY_TYPE,
    MLE_METRIC_WEIGHTS,
    ORG_TO_LEAGUE,
    ProspectBoardError,
    assemble_board,
    assign_league,
    attach_scores,
    board_column_order,
    classify_player_type,
    extract_board_json_fields,
    format_report,
    level_rank,
    normalize_level,
    parse_grade,
    select_mle_row_per_player,
    split_sheets,
)


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────

def _board_row(fg_id, name, org, pos, level, age, fv, eta=2028, rank=None, raw=None):
    return {
        "fg_minor_id": fg_id, "mlbam_id": None, "player_name": name, "org": org,
        "position": pos, "level": level, "age": age, "fv": fv, "risk": "Med", "eta": eta,
        "overall_rank": rank, "org_rank": 1, "fantasy_dynasty_rank": rank,
        "fantasy_redraft_rank": None, "season": 2026, "as_of_date": "2026-07-27",
        "fg_player_id": fg_id, "raw_json": json.dumps(raw or {}),
    }


@pytest.fixture
def board():
    return pd.DataFrame([
        _board_row("sa1", "Bat Young", "NYY", "SS", "AA", 20.0, 60, rank=1,
                   raw={"Hit": "40 / 60", "Game": "45 / 60", "Raw": "55 / 65", "Spd": "70 / 70",
                        "Fld": "50 / 55", "Bats": "R", "Throws": "R", "TLDR": "fast"}),
        _board_row("sa2", "Bat Old", "LAD", "1B", "AA", 25.0, 45, rank=200,
                   raw={"Hit": "40 / 50", "Spd": "30 / 30", "Bats": "L", "Throws": "L"}),
        _board_row("sa3", "Arm Good", "SFG", "SP", "AAA", 22.0, 55, rank=30,
                   raw={"FB": "60 / 70", "SL": "55 / 60", "CMD": "45 / 55", "Throws": "R"}),
        _board_row("sa4", "Arm Meh", "TBR", "SIRP", "A+", 21.0, 40, rank=None,
                   raw={"FB": "50 / 55"}),
        # complex-league kid: identity but NO MLE line — must survive as an FV-only row
        _board_row("sa5", "Complex Kid", "ATH", "CF", "CPX", 18.0, 45, rank=None, raw={}),
    ])


@pytest.fixture
def xref():
    return pd.DataFrame({
        "fg_minor_id": ["sa1", "sa2", "sa3", "sa4", "sa5"],
        "mlbam_id": ["1001", "1002", "1003", "1004", "1005"],
    })


@pytest.fixture
def mle_bat():
    return pd.DataFrame([
        # sa1 has BOTH an A+ line (big sample) and a thin AA line — the AA one must NOT win
        {"player_id": "1001", "level": "High-A", "minor_pa": 420.0, "mle_k_pct": 0.19,
         "mle_k_pct_sd": 0.03, "mle_bb_pct": 0.11, "mle_bb_pct_sd": 0.02, "mle_iso": 0.19,
         "mle_iso_sd": 0.03},
        {"player_id": "1001", "level": "Double-A", "minor_pa": 25.0, "mle_k_pct": 0.31,
         "mle_k_pct_sd": 0.09, "mle_bb_pct": 0.05, "mle_bb_pct_sd": 0.05, "mle_iso": 0.05,
         "mle_iso_sd": 0.09},
        {"player_id": "1002", "level": "Double-A", "minor_pa": 500.0, "mle_k_pct": 0.28,
         "mle_k_pct_sd": 0.03, "mle_bb_pct": 0.06, "mle_bb_pct_sd": 0.02, "mle_iso": 0.10,
         "mle_iso_sd": 0.03},
    ])


@pytest.fixture
def mle_pit():
    return pd.DataFrame([
        {"player_id": "1003", "level": "Triple-A", "minor_pa": 400.0, "mle_k_pct": 0.27,
         "mle_k_pct_sd": 0.03, "mle_bb_pct": 0.07, "mle_bb_pct_sd": 0.02, "mle_gb_pct": 0.52,
         "mle_gb_pct_sd": 0.04},
        {"player_id": "1004", "level": "High-A", "minor_pa": 300.0, "mle_k_pct": 0.20,
         "mle_k_pct_sd": 0.03, "mle_bb_pct": 0.12, "mle_bb_pct_sd": 0.02, "mle_gb_pct": 0.38,
         "mle_gb_pct_sd": 0.04},
    ])


# ── the AL/NL map: the column a single-league dynasty draft filters on ───────────────────────

def test_all_thirty_clubs_are_mapped_and_the_leagues_are_balanced():
    assert len(ORG_TO_LEAGUE) == 30
    counts = pd.Series(list(ORG_TO_LEAGUE.values())).value_counts().to_dict()
    assert counts == {"AL": 15, "NL": 15}


@pytest.mark.parametrize("org,league", [
    ("NYY", "AL"), ("ATH", "AL"), ("OAK", "AL"), ("KCR", "AL"), ("KC", "AL"),
    ("SFG", "NL"), ("SD", "NL"), ("WSN", "NL"), ("wsh", "NL"), (" LAD ", "NL"),
])
def test_org_aliases_and_whitespace_resolve(org, league):
    assert assign_league(org) == league


def test_an_unknown_org_is_none_not_a_guess():
    assert assign_league("XXX") is None
    assert assign_league(None) is None
    assert assign_league("") is None


def test_an_unmapped_org_fails_the_build_rather_than_nulling_the_league(board, xref, mle_bat,
                                                                       mle_pit):
    """A NULL `mlb_league` silently removes a player from the ONLY sheet the operator drafts off."""
    board.loc[0, "org"] = "ZZZ"
    with pytest.raises(ProspectBoardError, match="AL/NL"):
        assemble_board(board, xref, mle_bat, mle_pit)
    # ...and the escape hatch is explicit, never the default
    out, rep = assemble_board(board, xref, mle_bat, mle_pit, strict_league=False)
    assert rep["unmapped_orgs"] == ["ZZZ"]
    assert out["mlb_league"].isna().sum() == 1


# ── levels ───────────────────────────────────────────────────────────────────────────────────

def test_the_two_level_vocabularies_normalize_to_one():
    """THE BOARD says `A+`; the E7.3 MLE tables say `High-A`. 'Highest level' must mean the same
    thing on both sides of the join or the MLE row selection picks the wrong line."""
    assert normalize_level("High-A") == normalize_level("A+") == "A+"
    assert normalize_level("Double-A") == normalize_level("aa") == "AA"
    assert normalize_level("Triple-A") == "AAA"
    assert level_rank("Triple-A") > level_rank("Double-A") > level_rank("High-A") > level_rank("A")
    assert level_rank("MLB") == max(BOARD_LEVEL_RANK.values())


def test_an_unknown_level_ranks_zero_so_it_never_wins_a_max():
    assert normalize_level("Winter Ball") is None
    assert level_rank("Winter Ball") == 0


# ── grades ───────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,future,present", [("40 / 60", 60.0, 40.0), ("55", 55.0, 55.0),
                                                (70, 70.0, 70.0)])
def test_the_future_grade_is_the_one_a_dynasty_owner_drafts(raw, future, present):
    assert parse_grade(raw) == future
    assert parse_grade(raw, "present") == present


def test_an_ungraded_tool_is_none_never_zero():
    """A 0 would read as 'scouted, and terrible' and would drag any mean it entered."""
    for blank in ("", "   ", None, np.nan):
        assert parse_grade(blank) is None


def test_board_json_extraction_survives_a_malformed_blob():
    """One bad row must not cost the operator his board on draft morning."""
    out = extract_board_json_fields("{not json")
    assert out["grade_hit"] is None and out["bats"] is None
    assert extract_board_json_fields(None)["tldr"] is None


def test_speed_grade_falls_back_to_the_numeric_field():
    assert extract_board_json_fields(json.dumps({"Spd": "", "fSpd": 65}))["grade_spd"] == 65.0


# ── player type ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pos,expected", [
    ("SP", "pitcher"), ("SIRP", "pitcher"), ("MIRP", "pitcher"), ("RHP", "pitcher"),
    ("SS", "batter"), ("CF", "batter"), ("C", "batter"), ("TWP", "two_way"), (None, "batter"),
])
def test_player_type_comes_from_the_scouting_position(pos, expected):
    assert classify_player_type(pos) == expected


# ── picking ONE MLE line ─────────────────────────────────────────────────────────────────────

def test_a_thin_line_at_a_higher_level_does_not_beat_a_real_one_below_it(mle_bat):
    """The bug this exists to stop: a prospect promoted 3 weeks ago has a 25-PA AA line and a
    420-PA A+ line, and 'highest level' alone would project him off 25 PA."""
    picked = select_mle_row_per_player(mle_bat, min_pa=100.0)
    row = picked.loc[picked["player_id"] == "1001"].iloc[0]
    assert row["mle_level"] == "High-A"
    assert row["mle_pa"] == 420.0
    assert len(picked) == picked["player_id"].nunique()


def test_a_player_below_the_floor_everywhere_keeps_his_largest_sample(mle_bat):
    thin = mle_bat[mle_bat["player_id"] == "1001"].copy()
    picked = select_mle_row_per_player(thin, min_pa=10_000.0)
    assert len(picked) == 1
    assert picked.iloc[0]["mle_pa"] == 420.0     # the biggest sample, not the highest level


# ── scoring ──────────────────────────────────────────────────────────────────────────────────

def test_the_metric_weights_are_the_measured_translation_correlations():
    """Weights are proportional to each metric's OOS translation corr, and the NO-SIGNAL metrics
    are absent entirely — including wOBA at any weight would launder a measured null into a rank."""
    bat = MLE_METRIC_WEIGHTS["batter"]
    assert set(bat) == {"mle_k_pct", "mle_bb_pct", "mle_iso", "mle_sb_rate"}
    assert bat["mle_k_pct"][0] > bat["mle_bb_pct"][0] > bat["mle_iso"][0]   # 0.637 > 0.491 > 0.429
    # E8.3: SB rate translates BEST of anything on this board (0.702), so it must carry the
    # LARGEST batter weight. A weight below k_pct's would mean someone hand-tuned it down.
    assert bat["mle_sb_rate"][0] > bat["mle_k_pct"][0]
    assert bat["mle_sb_rate"] == (0.702, True)          # more steals = more fantasy value
    assert "mle_woba" not in bat                                            # 0.220 = no-signal
    # the SUCCESS half is a measured null (0.230, fails PBO) and must never be carried
    assert not any("succ" in k for k in bat)
    pit = MLE_METRIC_WEIGHTS["pitcher"]
    assert set(pit) == {"mle_p_gb_pct", "mle_p_bb_pct", "mle_p_k_pct"}
    assert max(pit.values(), key=lambda t: t[0]) == pit["mle_p_gb_pct"]     # 0.551 = the strong one
    assert not any(k.endswith("hr_rate") or "xwoba" in k for k in pit)


def test_the_k_pct_direction_inverts_between_bats_and_arms():
    """A batter wants a LOW K%; a pitcher wants a HIGH one. Getting this backwards would invert
    half the board and still look plausible."""
    assert MLE_METRIC_WEIGHTS["batter"]["mle_k_pct"][1] is False
    assert MLE_METRIC_WEIGHTS["pitcher"]["mle_p_k_pct"][1] is True
    assert MLE_METRIC_WEIGHTS["batter"]["mle_bb_pct"][1] is True
    assert MLE_METRIC_WEIGHTS["pitcher"]["mle_p_bb_pct"][1] is False


def test_the_fv_weight_encodes_the_e7_8_position_asymmetry():
    """E7.8: FV COMPLEMENTS us for arms (gates cleared) and SUBSTITUTES for us on bats (no stage
    cleared) ⇒ the scouts must lead for pitchers and confirm for hitters."""
    assert FV_WEIGHT_BY_TYPE["pitcher"] > 0.5 > FV_WEIGHT_BY_TYPE["batter"]


def test_a_missing_metric_is_renormalized_away_not_scored_as_bad():
    df = pd.DataFrame({
        "player_type": ["batter", "batter"], "level": ["AA", "AA"], "age": [21.0, 21.0],
        "fv": [50.0, 50.0], "grade_spd": [40.0, 40.0],
        "mle_k_pct": [0.18, 0.18], "mle_bb_pct": [0.12, 0.12],
        "mle_iso": [0.20, np.nan], "mle_sb_rate": [0.06, 0.06],
    })
    out = attach_scores(df)
    assert out["mle_coverage"].iloc[0] == 1.0
    assert out["mle_coverage"].iloc[1] < 1.0
    assert out["mle_score"].notna().all()          # scored on what he has, not punished


def test_a_player_with_no_mle_at_all_still_gets_a_blend_from_fv(board, xref, mle_bat, mle_pit):
    out, rep = assemble_board(board, xref, mle_bat, mle_pit)
    kid = out.loc[out["player_name"] == "Complex Kid"].iloc[0]
    assert pd.isna(kid["mle_k_pct"])                       # no projection exists
    assert kid["disagreement_label"] == "n/a (no MLE line)"
    assert pd.notna(kid["blend_score"])                    # ...but he is still ranked, not dropped
    assert rep["board_rows"] == 5


def test_age_relative_to_level_is_measured_against_the_same_level(board, xref, mle_bat, mle_pit):
    out, _ = assemble_board(board, xref, mle_bat, mle_pit)
    aa = out[out["level"] == "AA"].set_index("player_name")
    assert aa.loc["Bat Young", "age_vs_level"] < 0 < aa.loc["Bat Old", "age_vs_level"]
    assert aa.loc["Bat Young", "age_score"] > aa.loc["Bat Old", "age_score"]


def test_the_model_score_is_the_documented_mix_of_line_and_age():
    df = pd.DataFrame({
        "player_type": ["batter", "batter"], "level": ["AA", "AA"], "age": [20.0, 24.0],
        "fv": [55.0, 45.0], "grade_spd": [50.0, 50.0],
        "mle_k_pct": [0.18, 0.28], "mle_bb_pct": [0.12, 0.06], "mle_iso": [0.20, 0.09],
    })
    out = attach_scores(df)
    expected = (out["mle_score"] * (1 - AGE_WEIGHT_IN_MODEL_SCORE)
                + out["age_score"] * AGE_WEIGHT_IN_MODEL_SCORE).round(1)
    pd.testing.assert_series_equal(out["model_score"], expected, check_names=False)


def test_speed_first_prospects_are_flagged_because_sb_is_invisible_to_the_mle(board, xref,
                                                                             mle_bat, mle_pit):
    out, _ = assemble_board(board, xref, mle_bat, mle_pit)
    flagged = set(out.loc[out["speed_flag"] != "", "player_name"])
    assert flagged == {"Bat Young"}      # 70 future speed; the 30-grade player is not flagged


def test_disagreement_is_a_residual_not_the_raw_gap():
    """🚨 THE REGRESSION ARTIFACT. Two imperfectly-correlated rankings pull toward each other at
    the extremes, so the RAW gap labels the whole top of the board 'SCOUTS HIGHER' and the whole
    bottom 'WE'RE HIGHER' — a re-encoding of FV rank wearing a disagreement's clothes. (Caught on
    the first real 1,286-player run: 10 of the top 12.) Here: our score tracks FV closely but with
    the extremes compressed, exactly the shape that fools the raw gap."""
    n = 40
    fv = np.linspace(20, 80, n)
    df = pd.DataFrame({
        "player_type": ["batter"] * n, "level": ["AA"] * n, "age": [21.0] * n,
        "fv": fv, "grade_spd": [50.0] * n,
        "mle_k_pct": np.linspace(0.30, 0.15, n), "mle_bb_pct": np.linspace(0.05, 0.13, n),
        "mle_iso": np.linspace(0.08, 0.22, n),
    })
    out = attach_scores(df)
    raw_gap = out["model_score"] - out["fv_pctile"]
    # the raw gap is monotone in FV and spans tens of points — that IS the artifact
    assert raw_gap.iloc[0] > 5 > raw_gap.iloc[-1] + 5
    assert raw_gap.max() - raw_gap.min() > 10
    # ...and the residual removes it entirely: here our score IS the scouts' order, so nobody
    # disagrees with anybody and the whole column collapses to ~0
    assert out["disagreement"].abs().max() < 2.0
    assert (out["disagreement_label"] == "agree").all()


def test_a_genuine_outlier_still_gets_flagged_after_the_artifact_is_removed():
    """Removing the regression artifact must not remove the signal: a player whose translated line
    is far better than his grade-mates' is exactly what the column exists to surface."""
    n = 40
    df = pd.DataFrame({
        "player_type": ["batter"] * n, "level": ["AA"] * n, "age": [21.0] * n,
        "fv": np.linspace(20, 80, n), "grade_spd": [50.0] * n,
        "mle_k_pct": np.linspace(0.30, 0.15, n), "mle_bb_pct": np.linspace(0.05, 0.13, n),
        "mle_iso": np.linspace(0.08, 0.22, n),
    })
    # a 35-FV player carrying the best line on the board
    df.loc[2, ["mle_k_pct", "mle_bb_pct", "mle_iso"]] = [0.13, 0.15, 0.25]
    out = attach_scores(df)
    assert out.loc[2, "disagreement"] > 15.0
    assert out.loc[2, "disagreement_label"] == "WE'RE HIGHER"


def test_disagreement_labels_stay_in_the_declared_vocabulary(board, xref, mle_bat, mle_pit):
    out, _ = assemble_board(board, xref, mle_bat, mle_pit)
    assert set(out["disagreement_label"]) <= {"WE'RE HIGHER", "SCOUTS HIGHER", "agree",
                                              "n/a (no MLE line)"}
    assert (out.loc[out["disagreement"].isna(), "disagreement_label"]
            == "n/a (no MLE line)").all()


def test_graduated_prospects_are_flagged_and_get_their_own_tab(board, xref, mle_bat, mle_pit):
    """231 of the real board's 1,286 prospects are listed AT MLB — usually not draftable in a
    minor-league dynasty draft, so the board must say so rather than let the operator infer it."""
    board.loc[0, "level"] = "MLB"
    out, _ = assemble_board(board, xref, mle_bat, mle_pit)
    assert (out.loc[out["level"] == "MLB", "in_majors"] != "").all()
    assert (out.loc[out["level"] != "MLB", "in_majors"] == "").all()
    sheets = split_sheets(out)
    assert len(sheets["Minors only"]) == len(out) - 1


# ── assembly + export shape ──────────────────────────────────────────────────────────────────

def test_the_board_joins_and_reports_its_match_rates(board, xref, mle_bat, mle_pit):
    out, rep = assemble_board(board, xref, mle_bat, mle_pit)
    assert rep["matched_mlbam"] == 5 and rep["matched_mlbam_rate"] == 1.0
    assert rep["with_batter_mle"] == 2 and rep["with_pitcher_mle"] == 2
    assert rep["with_any_mle"] == 4
    assert len(out) == 5 and out["board_rank"].tolist() == [1, 2, 3, 4, 5]
    assert out.iloc[0]["player_name"] == "Bat Young"          # default sort = FV desc
    assert "EXPECTED, not a defect" in format_report(rep)


def test_an_unresolved_identity_stays_on_the_board_fv_only(board, xref, mle_bat, mle_pit):
    """E7.4 refuses a fuzzy name leg (a name match produced a false positive). An unresolved
    prospect is emitted honestly rather than dropped or guessed at."""
    out, rep = assemble_board(board, xref[xref["fg_minor_id"] != "sa5"], mle_bat, mle_pit)
    assert len(out) == 5
    assert rep["matched_mlbam"] == 4
    assert out.loc[out["player_name"] == "Complex Kid", "mlbam_id"].isna().all()


def test_a_duplicated_board_snapshot_is_a_hard_error(board, xref, mle_bat, mle_pit):
    """The tombstoned-glob failure mode (E7.4 landmine 2): duplicated rows inflate every count and
    look like a bigger board rather than a broken read."""
    dupe = pd.concat([board, board.iloc[[0]]], ignore_index=True)
    with pytest.raises(ProspectBoardError, match="duplicate fg_minor_id"):
        assemble_board(dupe, xref, mle_bat, mle_pit)


def test_pitcher_columns_never_land_on_a_hitter_row(board, xref, mle_bat, mle_pit):
    out, _ = assemble_board(board, xref, mle_bat, mle_pit)
    bats = out[out["player_type"] == "batter"]
    arms = out[out["player_type"] == "pitcher"]
    assert bats["mle_p_k_pct"].isna().all()
    assert arms["mle_k_pct"].isna().all()
    assert arms["mle_p_gb_pct"].notna().sum() == 2


def test_the_export_tabs_cover_the_league_split_the_draft_needs(board, xref, mle_bat, mle_pit):
    out, _ = assemble_board(board, xref, mle_bat, mle_pit)
    sheets = split_sheets(out)
    assert {"All", "AL", "NL", "Hitters", "Pitchers", "Disagreements"} <= set(sheets)
    assert len(sheets["AL"]) + len(sheets["NL"]) == len(out)      # every player lands in a league
    assert set(sheets["AL"]["org"]) == {"NYY", "TBR", "ATH"}
    assert len(sheets["Hitters"]) + len(sheets["Pitchers"]) == len(out)


def test_split_sheets_adds_a_pipeline_only_tab_when_the_column_is_present(board, xref, mle_bat,
                                                                          mle_pit):
    """E8.0b: once `fold_pipeline_into_e8_0_board` has unioned MLB-Pipeline-only players in
    (`on_fangraphs_board=False`), the export needs a dedicated tab so those rows are discoverable
    rather than buried at the bottom of the 'All' sort."""
    out, _ = assemble_board(board, xref, mle_bat, mle_pit)
    out = out.assign(on_fangraphs_board=True)
    extra = out.iloc[[0]].copy()
    extra["on_fangraphs_board"] = False
    extra["pipeline_overall_rank"] = 5
    extra["mlbam_id"] = "9999999"
    combo = pd.concat([out, extra], ignore_index=True)

    sheets = split_sheets(combo)
    assert "Pipeline-only" in sheets
    assert len(sheets["Pipeline-only"]) == 1
    assert sheets["Pipeline-only"]["mlbam_id"].iloc[0] == "9999999"


def test_split_sheets_has_no_pipeline_only_tab_on_a_plain_e8_0_board(board, xref, mle_bat, mle_pit):
    """A plain E8.0 board (no consensus fold) never carries `on_fangraphs_board` — this must be a
    strict extension, never a behavior change for the existing export."""
    out, _ = assemble_board(board, xref, mle_bat, mle_pit)
    sheets = split_sheets(out)
    assert "Pipeline-only" not in sheets


def test_the_column_order_never_silently_drops_a_new_column(board, xref, mle_bat, mle_pit):
    out, _ = assemble_board(board, xref, mle_bat, mle_pit)
    extra = out.assign(brand_new_column=1)
    assert board_column_order(extra)[-1] == "brand_new_column"
    assert board_column_order(out)[:4] == ["board_rank", "player_name", "org", "mlb_league"]


def test_the_vendor_blob_is_not_carried_into_the_export(board, xref, mle_bat, mle_pit):
    """`raw_json` is ~5 KB of FanGraphs blob per player — carrying it made the CSV 7 MB and pushed
    the readable columns off the right-hand edge of the sheet. Its useful contents are already
    unpacked into real columns."""
    out, _ = assemble_board(board, xref, mle_bat, mle_pit)
    assert "raw_json" not in out.columns
    assert not (EXPORT_DROP_COLUMNS & set(out.columns))
    assert {"grade_hit", "bats", "tldr"} <= set(out.columns)     # ...but the unpacked bits stay


# ── Prospect Savant: THEIRS, and clearly so ──────────────────────────────────────────────────

def test_prospect_savant_columns_are_prefixed_so_they_can_never_be_quoted_as_ours():
    from betting_ml.scripts.prospect_board import prospect_savant as ps

    for mapping in (ps._HITTER_FIELDS, ps._PITCHER_FIELDS):
        assert all(v.startswith("ps_") for v in mapping.values())


def test_prospect_savant_rows_without_the_vendor_id_are_dropped_not_name_matched():
    from betting_ml.scripts.prospect_board import prospect_savant as ps

    frame = ps.normalize_rows(
        [{"MinorMasterId": "sa1", "MLBAMId": 1001.0, "xwoba": 0.340, "pa": 300},
         {"MinorMasterId": None, "player_name": "No Id Guy", "xwoba": 0.400, "pa": 300}],
        "hitters", "AA")
    assert list(frame["fg_minor_id"]) == ["sa1"]
    assert frame.iloc[0]["ps_mlbam_id"] == "1001"
    assert frame.iloc[0]["ps_xwoba"] == 0.340


def test_untracked_levels_come_back_null_not_zero():
    """🚨 THE FEED WRITES 0.0, NOT NULL, WHERE A LEVEL HAS NO HAWK-EYE. Every AA row carries
    `xwoba = 0.0` / `ev = 0.0` / `velo = 0.0` (batted-ball tracking is Triple-A only — the same
    coverage wall E7.2 hit). Shipped verbatim, a 0.000 expected-wOBA-against renders on the board
    as a PERFECT pitcher. The whole tracking-gated group is nulled together, keyed on `ev`."""
    from betting_ml.scripts.prospect_board import prospect_savant as ps

    untracked = ps.normalize_rows(
        [{"MinorMasterId": "sa9", "xwoba": 0.0, "ev": 0.0, "velo": 0.0, "hhrate": 0.0,
          "barrelpa": 0.0, "whiffrate": 31.8, "krate": 24.6, "xfip": 3.15, "tbf": 277}],
        "pitchers", "AA").iloc[0]
    for col in ("ps_xwoba", "ps_ev", "ps_velo", "ps_hardhit_pct"):
        assert pd.isna(untracked[col]), f"{col} kept the 0-as-missing sentinel"
    # the rates ARE real at every level and must survive
    assert untracked["ps_whiff_pct"] == 31.8 and untracked["ps_xfip"] == 3.15

    tracked = ps.normalize_rows(
        [{"MinorMasterId": "sa8", "xwoba": 0.330, "ev": 88.3, "barrelpa": 0.0, "pa": 401}],
        "hitters", "AAA").iloc[0]
    assert tracked["ps_xwoba"] == 0.330
    assert tracked["ps_barrel_pct"] == 0.0      # a real 0 at a TRACKED level is kept


def test_the_probed_route_shape_is_pinned():
    """Probed live 2026-07-27: `/leaders/{hitters|pitchers}/{level}/{season}/{min_pitches}/
    {age_min}/{age_max}` — `batters` 404s, and the params after the season are a workload floor
    and an age window (confirmed by varying them), not assumed from a doc."""
    from betting_ml.scripts.prospect_board import prospect_savant as ps

    assert ps.leaders_url("pitchers", "AAA", 2026, min_pitches=100, age_min=16, age_max=28) == \
        "https://oriolebird.pythonanywhere.com/leaders/pitchers/AAA/2026/100/16/28"
    with pytest.raises(ps.ProspectSavantError):
        ps.leaders_url("batters", "AAA", 2026)
    assert "CPX" not in ps.LEVELS and "DSL" not in ps.LEVELS    # probed: both return zero rows


def test_savant_columns_merge_onto_the_board(board, xref, mle_bat, mle_pit):
    sav = pd.DataFrame([{"fg_minor_id": "sa1", "ps_level": "AA", "ps_xwoba": 0.355,
                         "ps_pa": 300.0}])
    out, rep = assemble_board(board, xref, mle_bat, mle_pit, sav)
    assert rep["with_prospect_savant"] == 1
    assert out.loc[out["player_name"] == "Bat Young", "ps_xwoba"].iloc[0] == 0.355


def test_the_savant_id_crosscheck_catches_a_wrong_identity(board, xref, mle_bat, mle_pit):
    """We join Prospect Savant on `fg_minor_id` alone, so THEIR MLBAM id is an independent second
    answer to 'who is this?' — a free third-party audit of the E7.4 bridge. On the real 2026 board
    it agrees 1,006/1,006; a mismatch is a wrong identity nothing else on this board would catch."""
    sav = pd.DataFrame([
        {"fg_minor_id": "sa1", "ps_mlbam_id": "1001", "ps_level": "AA", "ps_xwoba": 0.355},
        {"fg_minor_id": "sa2", "ps_mlbam_id": "9999", "ps_level": "AA", "ps_xwoba": 0.300},
    ])
    _, rep = assemble_board(board, xref, mle_bat, mle_pit, sav)
    cross = rep["savant_id_crosscheck"]
    assert cross["comparable"] == 2 and cross["agree"] == 1 and cross["rate"] == 0.5
    assert cross["disagreeing_players"][0]["player_name"] == "Bat Old"
    assert "MISMATCH Bat Old" in format_report(rep)
