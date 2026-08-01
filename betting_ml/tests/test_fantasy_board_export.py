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
    # NF1.6 — the honest low-predictability marker, declared on EVERY record (false for the skill
    # positions) so the client never has to know which positions are soft.
    "lowPred", "predNote",
    # NF1.6 — the K/DST raw components. Present on every record in the SAME `_STAT_KEYS` idiom (a WR
    # simply has no `fgMade`), so the browse table needs no per-position branching.
    "fgAtt", "fgMade", "fg039", "fg4049", "fg50", "fgMiss", "patAtt", "patMade",
    "sacks", "defInt", "fumRec", "defTd", "stTd", "safety", "blocked", "paTot", "paPerG",
    # NF-C0b — the nine points-allowed TIER buckets (expected GAMES in each bucket). Never
    # displayed; they are the scoring INPUT that lets a hand-entered D/ST tier table be applied
    # EXACTLY (the table is linear in these columns) rather than approximated. Dropping one would
    # silently downgrade a custom D/ST scheme to "captured, not applied".
    "paG0", "paG1_6", "paG7_13", "paG14_17", "paG18_20", "paG21_27", "paG28_34", "paG35_45",
    "paG46p",
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


def test_projection_records_carry_bio_when_available():
    """NF3.1 — bio (birth date/height/weight/college/experience/headshot) passed through from
    `player_bio_map`, keyed the same way `rookie_teams` is. Absent for a player the bio map has
    nothing for — OPTIONAL keys (like `lowPred`/`adp` before their own fill step), never a
    null-filled column, so an older cached export without them is unaffected."""
    recs = ex.projection_records(
        _projection_frame(),
        rookie_teams={"R-1": "LV"},
        bio={
            "00-1": {
                "birthDate": "1996-05-21", "heightIn": 77, "weightLb": 237,
                "college": "Wyoming", "yearsExp": 8, "headshot": "https://example.com/allen.png",
            },
        },
    )
    allen, rookie = recs
    assert allen["birthDate"] == "1996-05-21"
    assert allen["heightIn"] == 77
    assert allen["weightLb"] == 237
    assert allen["college"] == "Wyoming"
    assert allen["yearsExp"] == 8
    assert allen["headshot"] == "https://example.com/allen.png"
    assert "birthDate" not in rookie  # not in the bio map -> keys omitted entirely, not null


def test_projection_records_omit_bio_keys_when_bio_not_supplied():
    recs = ex.projection_records(_projection_frame(), rookie_teams={"R-1": "LV"})
    for rec in recs:
        assert "birthDate" not in rec
        assert "headshot" not in rec


# ── interval data quality ─────────────────────────────────────────────────────


def _rec(name, p10, p90, point):
    return {"name": name, "fpP10": p10, "fpP90": p90, "fpPpr": point}


def test_interval_audit_is_quiet_on_healthy_per_player_bands():
    healthy = [_rec("A", 100.0, 200.0, 150.0), _rec("B", 80.0, 190.0, 130.0)]
    assert ex.audit_interval_quality(healthy) == []


def test_interval_audit_flags_a_band_shared_across_players():
    # The rookie failure mode: one band pasted onto many players is a CLASS-level range. It is
    # invisible to any per-row check — only comparing rows to each other reveals it.
    shared = [_rec("A", 26.5, 277.0, 268.3), _rec("B", 26.5, 277.0, 30.0), _rec("C", 26.5, 277.0, 40.0)]
    findings = ex.audit_interval_quality(shared)
    assert any("shared" in f for f in findings), findings
    assert any("3" in f for f in findings), findings


def test_interval_audit_flags_a_point_outside_its_own_band():
    findings = ex.audit_interval_quality([_rec("A", 100.0, 200.0, 260.0)])
    assert any("OUTSIDE" in f for f in findings), findings


def test_interval_audit_flags_a_point_pinned_to_the_bands_extreme_tail():
    # A shared band cannot centre on every player it covers, so this is the tell-tale symptom.
    findings = ex.audit_interval_quality([_rec("A", 26.5, 277.0, 270.0)])
    assert any("extreme 5% tail" in f for f in findings), findings


def test_interval_audit_never_raises_on_missing_bands():
    # ALERT-tier: the audit warns, it must never break an export.
    assert ex.audit_interval_quality([{"name": "A", "fpP10": None, "fpP90": None, "fpPpr": 10.0}]) == []
    assert ex.audit_interval_quality([]) == []


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


def test_adp_nickname_aliases_resolve_to_the_nflverse_name():
    # A first-name nickname mismatch (FFC "Kenny Gainwell" vs nflverse "KENNETH GAINWELL") drops a
    # real draftable player's ADP SILENTLY — nothing errors, the column just reads "—". The alias
    # map is the cure; this pins the ones we have found so a normalizer change can't undo them.
    from quant_sports_intel_models.football.nfl.fantasy import adp_source as A

    assert A._normalize_name("Kenny Gainwell") == A._normalize_name("KENNETH GAINWELL")
    assert A._normalize_name("Hollywood Brown") == A._normalize_name("MARQUISE BROWN")


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
