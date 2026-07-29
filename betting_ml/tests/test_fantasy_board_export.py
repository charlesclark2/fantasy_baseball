"""NF3 — the JSON contract the fantasy browse surfaces read.

The three browse surfaces (Projections / Rankings / League Board) render straight off the blobs
`export_draft_board_json.py` stages to S3, so this pins the keys and the honest-uncertainty fields
they depend on. A silently-renamed or dropped key here is invisible to the type checker (the blobs
are plain JSON at runtime) and would blank a column in production — exactly the class of bug the
repo's "a field the store has but the UI doesn't get" landmine describes.

Pure/offline: builds tiny DataFrames, no lake read, no S3.
"""

from __future__ import annotations

import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as ex


# ── name display ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("JOSH ALLEN", "Josh Allen"),
        ("CHRISTIAN MCCAFFREY", "Christian McCaffrey"),
        ("JAMES COOK III", "James Cook III"),      # generational suffix, not "Iii"
        ("OLLIE GORDON II", "Ollie Gordon II"),
        ("ULYSSES BENTLEY IV", "Ulysses Bentley IV"),
        ("IVORY QUEEN", "Ivory Queen"),            # a name that merely LOOKS like a suffix
    ],
)
def test_titlecase(raw, expected):
    assert ex._titlecase(raw) == expected


# ── the league-board blob (Rankings + League Board) ───────────────────────────


def _board_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": "00-1", "player_name": "JAMES COOK III", "position": "RB",
                "team_id": "BUF", "is_rookie": False, "proj_games": 16.2,
                "league_points": 201.2, "league_points_p10": 150.0, "league_points_p90": 260.0,
                "replacement_points": 115.9, "vor": 85.3, "vor_p10": 34.1, "vor_p90": 144.1,
                "positional_rank": 8, "overall_rank": 11,
            },
            {   # FB must fold into RB — the board never surfaces a position the UI has no colour for
                "player_id": "00-2", "player_name": "A FULLBACK", "position": "FB",
                "team_id": "SF", "is_rookie": False, "proj_games": 15.0,
                "league_points": 40.0, "league_points_p10": 20.0, "league_points_p90": 60.0,
                "replacement_points": 115.9, "vor": -75.9, "vor_p10": -95.9, "vor_p90": -55.9,
                "positional_rank": 90, "overall_rank": 400,
            },
        ]
    )


def test_board_record_carries_the_points_interval():
    # ptsP10/ptsP90 is what the Rankings surface draws its 80% band from. Without it the column
    # silently renders "—" for every row.
    recs = ex.board_records(_board_frame(), byes={"BUF": 7})
    cook = recs[0]
    assert cook["ptsP10"] == 150.0 and cook["ptsP90"] == 260.0
    assert cook["vorP10"] == 34.1 and cook["vorP90"] == 144.1
    assert cook["name"] == "James Cook III"
    assert cook["bye"] == 7


def test_board_folds_fb_into_rb():
    recs = ex.board_records(_board_frame())
    assert {r["pos"] for r in recs} == {"RB"}


def test_kdst_placeholders_share_the_board_shape():
    # The optimizer + browse surfaces iterate one list; a placeholder missing a key the skill rows
    # have would read as `undefined` mid-render.
    board = ex.board_records(_board_frame())
    kdst = ex.kdst_records(["BUF"], {"BUF": "Tyler Bass"}, {"BUF": 7})
    assert kdst, "expected K/DST placeholders"
    for rec in kdst:
        assert set(rec) == set(board[0]), "K/DST placeholder shape drifted from the skill rows"
        assert rec["pts"] is None and rec["vor"] is None, "placeholders must carry no projection"


# ── the projections blob (Projections surface) ────────────────────────────────


def _projection_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": "00-1", "player_name": "JOSH ALLEN", "position": "QB", "team_id": "BUF",
                "source": "veteran", "is_rookie": False, "draft_overall": None, "confidence": "high",
                "proj_games": 16.5, "proj_pass_att": 457.6, "proj_pass_cmp": 303.6,
                "proj_pass_yds": 3504.4, "proj_pass_td": 24.0, "proj_pass_int": 9.1,
                "proj_rush_att": 89.6, "proj_rush_yds": 456.9, "proj_rush_td": 10.3,
                "proj_targets": 0.0, "proj_rec": 0.0, "proj_rec_yds": 1.6, "proj_rec_td": 0.2,
                "proj_fumbles_lost": 0.5, "proj_two_pt": None,
                "proj_fp_std": 325.7, "proj_fp_half": 325.7, "proj_fp_ppr": 325.7,
                "fp_ppr_sd": 73.0, "fp_ppr_p10": 232.2, "fp_ppr_p90": 419.2,
                "uncertainty_type": "empirical",
            },
            {
                "player_id": "R-1", "player_name": "Fernando Mendoza", "position": "QB",
                "team_id": None, "source": "rookie", "is_rookie": True, "draft_overall": 1.0,
                "confidence": "low", "proj_games": 12.4, "proj_pass_att": 614.5,
                "proj_pass_cmp": 373.5, "proj_pass_yds": 4099.7, "proj_pass_td": 20.6,
                "proj_pass_int": 14.7, "proj_rush_att": 68.9, "proj_rush_yds": 342.9,
                "proj_rush_td": 3.0, "proj_targets": 0.0, "proj_rec": 0.0, "proj_rec_yds": 0.0,
                "proj_rec_td": 0.0, "proj_fumbles_lost": 0.4, "proj_two_pt": None,
                "proj_fp_std": 268.3, "proj_fp_half": 268.3, "proj_fp_ppr": 268.3,
                "fp_ppr_sd": 97.7, "fp_ppr_p10": 26.5, "fp_ppr_p90": 277.0,
                "uncertainty_type": "calibrated",
            },
        ]
    )


# Every key the Projections table reads. Dropping one blanks a column with no error.
_PROJECTION_KEYS = {
    "id", "name", "pos", "team", "bye", "rookie", "draftPick", "conf", "g", "adp",
    "fpStd", "fpHalf", "fpPpr", "fpSd", "fpP10", "fpP90", "uncType",
    "passAtt", "passCmp", "passYds", "passTd", "passInt",
    "rushAtt", "rushYds", "rushTd", "tgt", "rec", "recYds", "recTd", "fum", "twoPt",
}


def test_projection_records_carry_the_full_contract():
    recs = ex.projection_records(_projection_frame(), rookie_teams={"R-1": "LV"}, byes={"BUF": 7})
    assert [r["name"] for r in recs] == ["Josh Allen", "Fernando Mendoza"]  # sorted by PPR desc
    for rec in recs:
        assert set(rec) == _PROJECTION_KEYS


def test_projection_records_keep_the_honest_uncertainty_fields():
    allen, rookie = ex.projection_records(_projection_frame(), rookie_teams={"R-1": "LV"})
    # the 80% band + how it was derived are the honest-framing payload — never drop them
    assert (allen["fpP10"], allen["fpP90"], allen["uncType"]) == (232.2, 419.2, "empirical")
    assert (rookie["fpP10"], rookie["fpP90"], rookie["uncType"]) == (26.5, 277.0, "calibrated")
    assert allen["conf"] == "high" and rookie["conf"] == "low"


def test_projection_rookie_gets_a_backfilled_team_and_int_draft_slot():
    _, rookie = ex.projection_records(_projection_frame(), rookie_teams={"R-1": "LV"})
    assert rookie["rookie"] is True
    assert rookie["team"] == "LV"          # MVP-1 leaves a rookie's team NULL
    assert rookie["draftPick"] == 1        # an int, not 1.0


# ── market ADP (the reference column) ─────────────────────────────────────────


def test_every_shipped_preset_maps_to_an_adp_format():
    # A preset with no mapping would silently fall back to PPR — which on a superflex board makes
    # every QB look like a huge "value" that is purely a mismatched-reference artefact.
    from quant_sports_intel_models.football.nfl.fantasy.league_presets import PRESETS

    for name in PRESETS:
        assert ex.PRESET_ADP_FORMAT.get(name), f"preset {name} has no ADP format mapping"
    assert ex.PRESET_ADP_FORMAT["superflex"] == "2qb", "superflex must use the 2QB ADP sample"


def test_attach_adp_matches_on_normalized_name_and_position():
    recs = ex.board_records(_board_frame())
    # the ADP side spells him differently (suffix + case) — the shared normalizer must still match
    matched = ex._attach_adp(recs, {("james cook", "RB"): 41.3})
    assert matched == 1
    assert recs[0]["adp"] == 41.3


def test_attach_adp_leaves_an_undrafted_player_null():
    # Undrafted in that sample is a real signal (nobody is taking him), not a data gap — it must
    # stay null rather than defaulting to a number that would sort as though he were drafted early.
    recs = ex.board_records(_board_frame())
    assert ex._attach_adp(recs, {}) == 0
    assert all(r["adp"] is None for r in recs)


def test_adp_is_declared_even_when_the_fetch_never_runs():
    # `adp` is part of the record shape, not something _attach_adp introduces — otherwise a failed
    # FFC fetch would ship records missing a key the UI reads.
    assert "adp" in ex.board_records(_board_frame())[0]
    assert "adp" in ex.projection_records(_projection_frame())[0]


def test_adp_lookup_is_best_effort(monkeypatch):
    # FFC is an external free API; a failure must degrade the ADP column, never fail the export.
    from quant_sports_intel_models.football.nfl.fantasy import adp_source as A

    monkeypatch.setattr(A, "fetch_ffc_adp", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert ex.adp_lookup(2026, "ppr", 12) == {}


def test_projection_veteran_draft_slot_stays_null():
    # A veteran has no draft_overall — it must stay null, never collapse to 0 (which would render
    # as a bogus "Pick 0" in the table).
    allen, _ = ex.projection_records(_projection_frame())
    assert allen["draftPick"] is None
    assert allen["team"] == "BUF"
