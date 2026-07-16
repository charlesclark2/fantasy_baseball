"""Fast-gate unit tests for the NCAAF-P0.3 college↔NFL player-ID xref (feeder spine).

Pure/offline only — the whole xref is built over LOCAL Delta fixtures via the SAME
DuckDB-over-Delta code that runs on the S3 box (parity), so this stays in the fast gate:
no network, no S3, no warehouse. It reproduces the AC's validation without the lake:

  • the deterministic draft-slot baseline reproduces at 100% on the fixture (99.7% on real),
    with the row counts ASSERTED — NO cartesian inflation (the P0.1 NaN-to-NaN trap);
  • the NULL / duplicate combine slug does NOT multiply rows (the trap, in SQL dress);
  • name normalisation makes a `Jr.` surname agree (the 2–8% disagreement is formatting);
  • the UDFA fuzzy residual resolves a real undrafted player, EXCLUDES a drafted one, and
    does NOT false-match a player with no roster row;
  • a transfer's college_athlete_id is stable across schools;
  • the emitted mart is 1-row-per-gsis_id (duplicate NFL key impossible).
"""
from __future__ import annotations

import pytest

from quant_sports_intel_models.football.ncaaf.feeder import name_norm
from quant_sports_intel_models.football.ncaaf.feeder import xref
from quant_sports_intel_models.football.ncaaf.ingest import s3io


# ── fixture: a small but representative local Delta lake ─────────────────────────────────
def _land(root, source, season, records):
    s3io.write_records(records, sport="ncaaf", source=source, season=season, local_root=root)


@pytest.fixture(scope="module")
def lake(tmp_path_factory):
    """Build a local Delta lake once (module-scoped — Delta commits aren't free) and return
    the resolver + the built xref result."""
    root = str(tmp_path_factory.mktemp("ncaaf_lake"))

    # CFBD draft picks — 2015 (3 slots incl. a Jr. suffix) + 2016 (2 slots).
    _land(root, "cfbd_draft_picks", 2015, [
        {"year": 2015, "overall": 1, "round": 1, "collegeAthleteId": 1001,
         "name": "Jameis Winston", "position": "QB", "collegeTeam": "Florida State", "collegeConference": "ACC"},
        {"year": 2015, "overall": 2, "round": 1, "collegeAthleteId": 1002,
         "name": "Marcus Mariota", "position": "QB", "collegeTeam": "Oregon", "collegeConference": "Pac-12"},
        {"year": 2015, "overall": 10, "round": 1, "collegeAthleteId": 1010,
         "name": "Todd Gurley Jr.", "position": "RB", "collegeTeam": "Georgia", "collegeConference": "SEC"},
    ])
    _land(root, "cfbd_draft_picks", 2016, [
        {"year": 2016, "overall": 1, "round": 1, "collegeAthleteId": 1101,
         "name": "Jared Goff", "position": "QB", "collegeTeam": "California", "collegeConference": "Pac-12"},
        {"year": 2016, "overall": 4, "round": 1, "collegeAthleteId": 1104,
         "name": "Ezekiel Elliott", "position": "RB", "collegeTeam": "Ohio State", "collegeConference": "Big Ten"},
    ])

    # nflverse draft picks — matching slots; note Gurley has NO 'Jr.' on the NFL side.
    _land(root, "nflverse_draft_picks", 2015, [
        {"season": 2015, "pick": 1, "round": 1, "gsis_id": "00-0031234", "pfr_player_id": "WinsJa00",
         "cfb_player_id": "jameis-winston-1", "pfr_player_name": "Jameis Winston", "position": "QB",
         "college": "Florida State", "car_av": 55, "games": 90, "hof": "false"},
        {"season": 2015, "pick": 2, "round": 1, "gsis_id": "00-0031235", "pfr_player_id": "MariMa00",
         "cfb_player_id": "marcus-mariota-1", "pfr_player_name": "Marcus Mariota", "position": "QB",
         "college": "Oregon", "car_av": 48, "games": 80, "hof": "false"},
        {"season": 2015, "pick": 10, "round": 1, "gsis_id": "00-0031240", "pfr_player_id": "GurlTo00",
         "cfb_player_id": "todd-gurley-1", "pfr_player_name": "Todd Gurley", "position": "RB",
         "college": "Georgia", "car_av": 52, "games": 85, "probowls": 3, "allpro": 1, "hof": "false"},
    ])
    _land(root, "nflverse_draft_picks", 2016, [
        {"season": 2016, "pick": 1, "round": 1, "gsis_id": "00-0033104", "pfr_player_id": "GoffJa00",
         "cfb_player_id": "jared-goff-1", "pfr_player_name": "Jared Goff", "position": "QB",
         "college": "California", "car_av": 70, "games": 120, "hof": "false"},
        {"season": 2016, "pick": 4, "round": 1, "gsis_id": "00-0033107", "pfr_player_id": "ElliEz00",
         "cfb_player_id": "ezekiel-elliott-1", "pfr_player_name": "Ezekiel Elliott", "position": "RB",
         "college": "Ohio State", "car_av": 60, "games": 110, "hof": "false"},
    ])

    # combine — 2 real slugs + a NULL slug + a DUPLICATE slug (both are the NaN-trap: must NOT multiply).
    _land(root, "nflverse_combine", 2015, [
        {"cfb_id": "jameis-winston-1", "forty": 4.97, "vertical": 28.5, "broad_jump": 103,
         "cone": 7.16, "shuttle": 4.34, "ht": "6-4", "wt": 231},
        {"cfb_id": "marcus-mariota-1", "forty": 4.52, "vertical": 36.0, "ht": "6-4", "wt": 222},
        {"cfb_id": "marcus-mariota-1", "forty": 9.99, "ht": "0-0", "wt": 0},   # DUP slug → dedup, no multiply
        {"cfb_id": None, "forty": 4.4, "ht": "6-0", "wt": 200},                 # NULL slug → dropped, no multiply
    ])

    # nflverse players — the UDFA universe.
    _land(root, "nflverse_players", 0, [
        {"gsis_id": "00-0099001", "display_name": "Chris Moore", "position": "WR",
         "college_name": "Cincinnati", "entry_year": 2016, "draft_number": None},           # UDFA → matches roster
        {"gsis_id": "00-0033104", "display_name": "Jared Goff", "position": "QB",
         "college_name": "California", "entry_year": 2016, "draft_number": 1},               # drafted → excluded
        {"gsis_id": "00-0099002", "display_name": "Ghost Player", "position": "LB",
         "college_name": "Nowhere State", "entry_year": 2016, "draft_number": None},         # no roster → no match
    ])

    # roster — the UDFA's college identity + a transfer with a STABLE id across two schools.
    _land(root, "roster", 2015, [
        {"id": 2001, "firstName": "Chris", "lastName": "Moore", "position": "WR", "team": "Cincinnati"},
        {"id": 3001, "firstName": "Transfer", "lastName": "Player", "position": "RB", "team": "Alabama"},
    ])
    _land(root, "roster", 2016, [
        {"id": 2001, "firstName": "Chris", "lastName": "Moore", "position": "WR", "team": "Cincinnati"},
        {"id": 3001, "firstName": "Transfer", "lastName": "Player", "position": "RB", "team": "Auburn"},
    ])

    res = xref.build_xref(xref.local_lake(root), draft_seasons=[2015, 2016])
    return {"root": root, "res": res, "mart": res.mart, "report": res.report}


# ── the deterministic slot baseline (the 99.7% spine reproduced) ─────────────────────────
def test_slot_baseline_reproduced_no_cartesian(lake):
    rep = lake["report"]
    # every fixture slot resolves (100% here; 99.7% on real data) …
    assert rep["slot_match_pct"] == 100.0
    assert rep["slot_matched"] == rep["slot_total"] == 5
    # … and the join did NOT multiply rows: matched ≤ min(sides), 1 row per matched slot.
    assert rep["slot_matched"] <= min(rep["cfbd_picks_deduped"], rep["nfl_picks_deduped"])
    slot = lake["mart"][lake["mart"]["match_method"] == "deterministic_slot"]
    assert len(slot) == 5
    # every slot row carries BOTH ids (the crosswalk is complete for drafted players)
    assert slot["gsis_id"].notna().all()
    assert slot["college_athlete_id"].notna().all()


def test_per_class_report(lake):
    per = {r["season"]: r for r in lake["report"]["per_class"]}
    assert per[2015]["matched"] == per[2015]["cfbd_picks"] == 3
    assert per[2016]["matched"] == per[2016]["cfbd_picks"] == 2
    assert per[2015]["match_pct"] == 100.0


# ── the combine attach must be strictly 1:1 (the NaN-to-NaN trap) ────────────────────────
def test_combine_attach_no_multiply(lake):
    mart, rep = lake["mart"], lake["report"]
    # 5 slot rows + 1 UDFA = 6; a NULL slug and a DUPLICATE slug in combine must NOT inflate.
    assert rep["total_rows"] == 6
    assert len(mart) == 6
    # Winston + Mariota attach a 40-time; the dup Mariota slug did not create a 2nd Mariota row.
    assert (mart["player_name"] == "Marcus Mariota").sum() == 1
    mariota = mart[mart["player_name"] == "Marcus Mariota"].iloc[0]
    assert mariota["forty"] == 4.52          # the real row won the dedup, not the 9.99 junk row
    assert rep["combine_attached"] == 2
    assert rep["has_forty"] == 2


# ── name normalisation: the Jr. surname must agree ──────────────────────────────────────
def test_surname_agreement_after_normalisation(lake):
    mart = lake["mart"]
    gurley = mart[mart["gsis_id"] == "00-0031240"].iloc[0]
    # CFBD "Todd Gurley Jr." vs nflverse "Todd Gurley" → agree after suffix strip.
    assert bool(gurley["surname_agree"]) is True
    assert lake["report"]["surname_agree_pct"] == 100.0


@pytest.mark.parametrize("raw,full,last", [
    ("T.J. Watt Jr.", "tj watt", "watt"),
    ("Ka'imi Fairbairn", "kaimi fairbairn", "fairbairn"),
    ("José Ramírez III", "jose ramirez", "ramirez"),
    ("Amon-Ra St. Brown", "amon ra st brown", "brown"),
    (None, "", ""),
])
def test_name_norm_python_spec(raw, full, last):
    assert name_norm.normalize_name(raw) == full
    assert name_norm.normalize_last(raw) == last


# ── the UDFA fuzzy residual ─────────────────────────────────────────────────────────────
def test_udfa_fuzzy_match_resolves_known_case(lake):
    mart = lake["mart"]
    moore = mart[mart["gsis_id"] == "00-0099001"]
    assert len(moore) == 1
    row = moore.iloc[0]
    assert row["match_method"] == "fuzzy_udfa"
    assert bool(row["is_udfa"]) is True
    assert row["college_athlete_id"] == 2001          # recovered the CFBD college identity
    assert row["match_score"] >= 0.92
    assert row["match_confidence"] in ("medium", "low")
    # a UDFA has no draft slot ⇒ null draft fields + null target (undrafted → no outcome row)
    import pandas as pd

    assert pd.isna(row["draft_overall"])
    assert pd.isna(row["target_car_av"])


def test_udfa_excludes_drafted_and_unmatched(lake):
    gsis = set(lake["mart"]["gsis_id"])
    # Jared Goff is drafted (has draft_number) → he's in via the SLOT path, not duplicated as UDFA
    goff = lake["mart"][lake["mart"]["gsis_id"] == "00-0033104"]
    assert len(goff) == 1
    assert goff.iloc[0]["match_method"] == "deterministic_slot"
    # Ghost Player has no roster row → no false match, absent from the xref entirely
    assert "00-0099002" not in gsis
    assert lake["report"]["udfa_matched"] == 1


# ── transfers: the college_athlete_id is stable across schools ───────────────────────────
def test_transfer_stable_college_athlete_id(lake):
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL delta; LOAD delta")
    uri = s3io.local_table_uri(lake["root"], "ncaaf", "roster")
    rows = con.execute(
        f"select distinct json_extract_string(raw_json,'$.id') id, "
        f"json_extract_string(raw_json,'$.team') team, season "
        f"from delta_scan('{uri}') where json_extract_string(raw_json,'$.id')='3001' order by season"
    ).fetchall()
    # one athlete id, two schools across two seasons — the id is the stable spine, school drifts.
    assert {r[0] for r in rows} == {"3001"}
    assert {r[1] for r in rows} == {"Alabama", "Auburn"}


# ── the emitted mart is 1-row-per-NFL-player ────────────────────────────────────────────
def test_mart_unique_gsis_id(lake):
    mart = lake["mart"]
    non_null = mart.loc[mart["gsis_id"].notna(), "gsis_id"]
    assert non_null.is_unique
    assert (mart["sport"] == "ncaaf").all()
    assert (mart["xref_version"] == xref.XREF_VERSION).all()


# ── the anti-cartesian guard actually raises (defensive, not just asserted) ──────────────
def test_combine_multiply_is_caught(lake, monkeypatch):
    """If a duplicate combine slug ever DID multiply the slot xref (the NaN-to-NaN trap that
    faked a ~100% match in P0.1), build_xref must RAISE — never silently emit a 2× mart. Force
    it by swapping in a combine stage that skips the 1-per-slug dedup; the fixture's duplicate
    'marcus-mariota-1' slug then multiplies Mariota's row and the guard fires."""
    from quant_sports_intel_models.football.ncaaf.feeder.xref import _j

    def _no_dedup_combine(con, lk):
        con.execute(f"""
            create or replace temp view _combine as
            select {_j('raw_json','cfb_id')} as cfb_id,
                   try_cast({_j('raw_json','forty')} as double)    as forty,
                   try_cast({_j('raw_json','vertical')} as double) as vertical,
                   try_cast({_j('raw_json','bench')} as double)    as bench,
                   try_cast({_j('raw_json','broad_jump')} as double) as broad_jump,
                   try_cast({_j('raw_json','cone')} as double)     as cone,
                   try_cast({_j('raw_json','shuttle')} as double)  as shuttle,
                   {_j('raw_json','ht')}                           as combine_ht,
                   try_cast({_j('raw_json','wt')} as double)       as combine_wt
            from {lk('nflverse_combine')}
            where {_j('raw_json','cfb_id')} is not null
        """)

    monkeypatch.setattr(xref, "_stage_combine", _no_dedup_combine)
    with pytest.raises(xref.XrefValidationError):
        xref.build_xref(xref.local_lake(lake["root"]), draft_seasons=[2015, 2016])
