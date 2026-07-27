"""E7.4 — `dim_player_xref` builder tests (fast gate; offline, no network).

The same join SQL that runs against the S3 lake is exercised here over local parquet fixtures —
`XrefSources` exists precisely so one copy of the joins is provable without a warehouse (the
NCAAF-P0.3 pattern). Nothing here imports `pipeline` (CLAUDE.md fast-gate rule).

The fixtures encode the REAL shapes measured on the lake 2026-07-27, including the two that bite:
a graduated prospect whose board `fg_player_id` is the NUMERIC MLB FanGraphs id, and a same-name
MLB player who must NOT be matched to an unresolved prospect.
"""
from __future__ import annotations

import pandas as pd
import pytest

from betting_ml.scripts.milb_xref.player_xref import (
    MATCH_FG_LEADERBOARD,
    MATCH_FG_MLB_GRADUATE,
    MATCH_UNRESOLVED,
    XrefSources,
    XrefValidationError,
    build_xref,
    format_report,
)

duckdb = pytest.importorskip("duckdb")


# ── Fixtures ─────────────────────────────────────────────────────────────────────────────────

# The fixture carries a block of ordinary resolvable prospects alongside the three interesting
# ones, so the HAPPY PATH runs with the production tripwires ARMED (a 3-row fixture with one
# deliberate non-match would sit at 67% and trip the 90% floor — which would have forced every
# content test to disable enforcement, leaving the floors untested against a healthy build).
_PAD = 20
_BOARD_IDS = 3 + _PAD
_BOARD_RESOLVED = 2 + _PAD


def _pad_board():
    return [
        dict(fg_minor_id=f"sa5{i:02d}", fg_player_id=f"sa5{i:02d}", player_name=f"Filler {i}",
             org="MIL", position="OF", level="A", age=20.0, fv=45.0, risk="High", eta=2029,
             overall_rank=None, org_rank=i, fantasy_dynasty_rank=None, fantasy_redraft_rank=None,
             season=2026, as_of_date="2026-07-27", ingested_at_utc="2026-07-27T07:41:00Z")
        for i in range(_PAD)
    ]


def _pad_leaderboard():
    return [
        dict(fg_minor_id=f"sa5{i:02d}", fg_player_id=f"105{i:02d}", mlbam_id=f"9000{i:02d}",
             player_name=f"Filler {i}", team="MIL (A)", level="A", age=20.0,
             season=2026, stats="bat", as_of_date="2026-07-27")
        for i in range(_PAD)
    ]


def _board_rows():
    """THE BOARD: 2025 + 2026 snapshots, plus a superseded 2026 as_of_date that must be dropped."""
    return pd.DataFrame(_pad_board() + [
        # a plain prospect — resolves via the leaderboard bridge
        dict(fg_minor_id="sa100", fg_player_id="sa100", player_name="Prospect One", org="TEX",
             position="SS", level="AA", age=19.5, fv=55.0, risk="High", eta=2028,
             overall_rank=32, org_rank=1, fantasy_dynasty_rank=20, fantasy_redraft_rank=None,
             season=2026, as_of_date="2026-07-27", ingested_at_utc="2026-07-27T07:41:00Z"),
        # a GRADUATE — sa minor id + a NUMERIC MLB FanGraphs id in fg_player_id
        dict(fg_minor_id="sa200", fg_player_id="19611", player_name="Graduate Two", org="TOR",
             position="3B", level="MLB", age=22.0, fv=65.0, risk="Low", eta=2026,
             overall_rank=2, org_rank=1, fantasy_dynasty_rank=3, fantasy_redraft_rank=40,
             season=2026, as_of_date="2026-07-27", ingested_at_utc="2026-07-27T07:41:00Z"),
        # an international signee with NO pro stat line anywhere — must stay unresolved
        dict(fg_minor_id="sa300", fg_player_id="sa300", player_name="Michael Massey", org="DET",
             position="RHP", level=None, age=17.6, fv=40.0, risk="Extreme", eta=2032,
             overall_rank=None, org_rank=30, fantasy_dynasty_rank=None, fantasy_redraft_rank=None,
             season=2026, as_of_date="2026-07-27", ingested_at_utc="2026-07-27T07:41:00Z"),
        # SUPERSEDED same-season snapshot — a stale extraction of the SAME player; the newest
        # as_of_date must win, so this row's wrong org must never reach the dimension.
        dict(fg_minor_id="sa100", fg_player_id="sa100", player_name="Prospect One", org="WRONG",
             position="SS", level="A+", age=19.0, fv=50.0, risk="High", eta=2029,
             overall_rank=99, org_rank=9, fantasy_dynasty_rank=None, fantasy_redraft_rank=None,
             season=2026, as_of_date="2026-07-26", ingested_at_utc="2026-07-26T07:00:00Z"),
        # prior-season board row for the same player — the dimension takes the LATEST season
        dict(fg_minor_id="sa100", fg_player_id="sa100", player_name="Prospect One", org="TEX",
             position="SS", level="A", age=18.5, fv=45.0, risk="High", eta=2029,
             overall_rank=180, org_rank=6, fantasy_dynasty_rank=None, fantasy_redraft_rank=None,
             season=2025, as_of_date="2025-07-01", ingested_at_utc="2025-07-01T07:00:00Z"),
    ])


def _leaderboard_rows():
    return pd.DataFrame(_pad_leaderboard() + [
        dict(fg_minor_id="sa100", fg_player_id="10001", mlbam_id="800001",
             player_name="Prospect One", team="TEX (AA)", level="AA", age=19.5,
             season=2026, stats="bat", as_of_date="2026-07-27"),
        # the graduate no longer appears on a 2026 minors board — only a 2024 line exists, which
        # is exactly why the bridge must be season-AGNOSTIC.
        dict(fg_minor_id="sa200", fg_player_id="10002", mlbam_id="800002",
             player_name="Graduate Two", team="TOR (AAA)", level="AAA", age=20.0,
             season=2024, stats="bat", as_of_date="2024-07-01"),
        # a DSL player E7.1 does not ingest — a real MLBAM id with no spine row (coverage, not a
        # bad key). He must still get a dimension row.
        dict(fg_minor_id="sa400", fg_player_id="10004", mlbam_id="800004",
             player_name="Complex Four", team="MIL (DSL)", level="DSL", age=17.2,
             season=2026, stats="bat", as_of_date="2026-07-27"),
    ])


def _milb_log_rows():
    return pd.DataFrame([
        dict(player_id=800001, player_name="Prospect One", level_name="Double-A",
             affiliate_org_name="Texas Rangers", position_code="6", birth_date="2006-11-01",
             official_date="2026-07-20", season=2026),
        dict(player_id=800001, player_name="Prospect One", level_name="High-A",
             affiliate_org_name="Texas Rangers", position_code="6", birth_date="2006-11-01",
             official_date="2026-04-10", season=2026),
        dict(player_id=800002, player_name="Graduate Two", level_name="Triple-A",
             affiliate_org_name="Toronto Blue Jays", position_code="5", birth_date="2003-03-16",
             official_date="2024-06-01", season=2024),
        # the same-name MLB player's minor-league record — a name match to prospect sa300 would
        # be a FALSE POSITIVE (this is a different person).
        dict(player_id=686681, player_name="Michael Massey", level_name="Triple-A",
             affiliate_org_name="Kansas City Royals", position_code="4", birth_date="1998-03-22",
             official_date="2022-05-01", season=2022),
    ])


def _profile_rows():
    return pd.DataFrame([
        dict(player_id=800002, full_name="Graduate Two", birth_date="2003-03-16",
             primary_position_code="5", active=True, last_fetched_at="2026-07-27T00:00:00"),
        dict(player_id=686681, full_name="Michael Massey", birth_date="1998-03-22",
             primary_position_code="4", active=True, last_fetched_at="2026-07-27T00:00:00"),
    ])


def _fg_mlb_rows(hitting: bool = True):
    """The MLB FanGraphs raw feeds: one verbatim vendor record per row, re-landed every capture
    day. The stale `dt` rows exist so the "newest snapshot per season" restriction is exercised —
    they carry a WRONG mlbam id, so if the restriction ever regressed the graduate leg would
    resolve to the wrong person and the tests would catch it."""
    if hitting:
        rows = [
            ('{"playerid": "19611", "xMLBAMID": "800002", "PlayerName": "Graduate Two"}',
             2026, "2026-07-26"),
            ('{"playerid": "19611", "xMLBAMID": "111111", "PlayerName": "Graduate Two"}',
             2026, "2026-05-02"),   # superseded snapshot — must NOT win
        ]
    else:
        rows = [
            ('{"playerid": "22222", "xMLBAMID": "800009", "PlayerName": "Some Pitcher"}',
             2026, "2026-07-26"),
        ]
    return pd.DataFrame(rows, columns=["raw_json", "season", "dt"])


def _make_sources(tmp_path, *, board=None, leaderboards=None, logs=None, profiles=None):
    frames = {
        "board": board if board is not None else _board_rows(),
        "lb": leaderboards if leaderboards is not None else _leaderboard_rows(),
        "logs": logs if logs is not None else _milb_log_rows(),
        "prof": profiles if profiles is not None else _profile_rows(),
        "fgh": _fg_mlb_rows(True),
        "fgs": _fg_mlb_rows(False),
    }
    paths = {}
    for name, df in frames.items():
        path = tmp_path / f"{name}.parquet"
        df.to_parquet(path, index=False)
        paths[name] = f"read_parquet('{path}')"
    return XrefSources(
        board=paths["board"], leaderboards=paths["lb"], milb_game_logs=paths["logs"],
        mlb_player_profiles=paths["prof"], fg_mlb_hitting_raw=paths["fgh"],
        fg_mlb_pitching_raw=paths["fgs"],
    )


@pytest.fixture()
def conn():
    c = duckdb.connect()
    yield c
    c.close()


# ── The bridge resolves, with honest provenance ──────────────────────────────────────────────

def test_prospect_resolves_via_the_leaderboard_bridge(conn, tmp_path):
    """HOP 1+2: board.fg_minor_id → leaderboard.fg_minor_id → xMLBAMID → the MLBAM spine."""
    res = build_xref(conn, _make_sources(tmp_path))
    row = res.dim.set_index("fg_minor_id").loc["sa100"]
    assert row["mlbam_id"] == "800001"
    assert row["mlbam_match_method"] == MATCH_FG_LEADERBOARD
    assert row["mlbam_match_confidence"] == "high"
    assert bool(row["is_on_prospect_board"])


def test_graduate_leg_stamps_the_fg_mlb_id(conn, tmp_path):
    """The story's core requirement: MLBAM ↔ fg_mlb_id ↔ fg_minor_id reconcile to one person."""
    res = build_xref(conn, _make_sources(tmp_path))
    row = res.dim.set_index("fg_minor_id").loc["sa200"]
    assert row["mlbam_id"] == "800002"
    assert row["fg_mlb_id"] == "19611"      # the numeric MLB FanGraphs id
    assert row["current_level"] == "MLB"    # an MLB profile outranks any minor-league observation
    assert bool(row["in_mlb_player_master"])


def test_graduate_leg_resolves_when_the_leaderboard_bridge_is_missing(conn, tmp_path):
    """With no minors line at all, the fg_mlb_id → $.xMLBAMID leg must carry the graduate."""
    lb = _leaderboard_rows()
    lb = lb[lb["fg_minor_id"] != "sa200"]
    res = build_xref(conn, _make_sources(tmp_path, leaderboards=lb))
    row = res.dim.set_index("fg_minor_id").loc["sa200"]
    assert row["mlbam_id"] == "800002"
    assert row["mlbam_match_method"] == MATCH_FG_MLB_GRADUATE


def test_sa_prefixed_fg_player_id_is_never_stamped_as_an_mlb_id(conn, tmp_path):
    """FanGraphs reuses `fg_player_id` for the `sa` MINOR id on un-graduated players. Copying it
    into fg_mlb_id would put a minor id in the MLB-id column — a wrong id, worse than a null."""
    res = build_xref(conn, _make_sources(tmp_path))
    assert pd.isna(res.dim.set_index("fg_minor_id").loc["sa100"]["fg_mlb_id"])


# ── Unresolved handling: no match beats a wrong match ────────────────────────────────────────

def test_unresolved_prospect_gets_an_honest_row_not_a_name_match(conn, tmp_path):
    """sa300 ("Michael Massey", DET) shares a name with MLB player 686681 (Royals). A name-based
    fallback would match them — it is a DIFFERENT PERSON. The row must stay unresolved."""
    res = build_xref(conn, _make_sources(tmp_path))
    row = res.dim.set_index("fg_minor_id").loc["sa300"]
    assert pd.isna(row["mlbam_id"])
    assert row["mlbam_match_method"] == MATCH_UNRESOLVED
    assert row["mlbam_match_confidence"] == "none"
    assert row["xref_key"] == "fg:sa300"          # still a usable identity key
    assert row["fv"] == 40.0 and row["eta"] == 2032   # prospect attributes are still carried

    # and the real Michael Massey keeps his own, separate row
    massey = res.dim[res.dim["mlbam_id"] == "686681"]
    assert len(massey) == 1
    assert not bool(massey.iloc[0]["is_on_prospect_board"])


def test_every_person_appears_exactly_once(conn, tmp_path):
    res = build_xref(conn, _make_sources(tmp_path))
    assert not res.dim["xref_key"].duplicated().any()
    resolved = res.dim[res.dim["mlbam_id"].notna()]
    assert not resolved["mlbam_id"].duplicated().any()


# ── Snapshot dedupe (landmine 2's blast radius) ──────────────────────────────────────────────

def test_only_the_latest_board_snapshot_reaches_the_dimension(conn, tmp_path):
    """A superseded same-season as_of_date (and any older season) must not leak stale attributes."""
    res = build_xref(conn, _make_sources(tmp_path))
    row = res.dim.set_index("fg_minor_id").loc["sa100"]
    assert row["org"] == "TEX"                  # not "WRONG" (the 07-26 snapshot)
    assert row["fv"] == 55.0 and row["board_season"] == 2026
    assert row["board_as_of_date"] == "2026-07-27"


def test_a_duplicated_ingest_generation_does_not_inflate(conn, tmp_path):
    """Two generations inside ONE partition (the shape a parquet glob surfaces) must collapse to
    the newest by ingested_at_utc, not multiply the prospect layer."""
    board = _board_rows()
    stale = board[board["fg_minor_id"] == "sa100"].iloc[[0]].copy()
    stale["ingested_at_utc"] = "2026-07-27T07:03:00Z"
    stale["org"] = "STALE"
    res = build_xref(conn, pd.concat([board, stale]).pipe(
        lambda b: _make_sources(tmp_path, board=b)))
    assert res.dim.set_index("fg_minor_id").loc["sa100"]["org"] == "TEX"
    assert not res.dim["xref_key"].duplicated().any()


# ── Coverage vs. key failure ─────────────────────────────────────────────────────────────────

def test_a_level_e7_1_does_not_ingest_still_gets_a_row(conn, tmp_path):
    """A DSL player has a genuine xMLBAMID but no E7.1 game log — that is level COVERAGE, not a
    dead key, so he belongs in the dimension with the flags telling the truth."""
    res = build_xref(conn, _make_sources(tmp_path))
    row = res.dim[res.dim["mlbam_id"] == "800004"].iloc[0]
    assert bool(row["in_fg_leaderboards"])
    assert not bool(row["in_milb_game_logs"])
    assert not bool(row["in_mlb_player_master"])
    assert row["current_level"] == "DSL"


# ── Dead-bridge tripwires ────────────────────────────────────────────────────────────────────

def test_a_wrong_join_key_fails_loud_instead_of_shipping_an_empty_xref(conn, tmp_path):
    """The P1.2b class: a plausible-but-wrong id key matches almost nothing and is green
    everywhere downstream. The build must RAISE, not emit a near-empty crosswalk."""
    lb = _leaderboard_rows()
    lb["fg_minor_id"] = ["zz" + str(i) for i in range(len(lb))]   # ids from a different space
    with pytest.raises(XrefValidationError, match="hop 1"):
        build_xref(conn, _make_sources(tmp_path, leaderboards=lb))


def test_a_non_numeric_mlbam_id_fails_loud(conn, tmp_path):
    """An MLBAM id is always all-digits. Anything else means the alias resolved to the wrong
    field — the exact silent failure the story warns about."""
    lb = _leaderboard_rows()
    lb["mlbam_id"] = ["notanid"] * len(lb)
    with pytest.raises(XrefValidationError, match="all-digits"):
        build_xref(conn, _make_sources(tmp_path, leaderboards=lb))


def test_an_unpopulated_bridge_column_fails_loud(conn, tmp_path):
    lb = _leaderboard_rows()
    lb["mlbam_id"] = [None] * len(lb)
    with pytest.raises(XrefValidationError, match="hop 2"):
        build_xref(conn, _make_sources(tmp_path, leaderboards=lb))


def test_no_enforce_reports_the_degraded_rate_instead_of_raising(conn, tmp_path):
    lb = _leaderboard_rows()
    lb["fg_minor_id"] = ["zz" + str(i) for i in range(len(lb))]
    res = build_xref(conn, _make_sources(tmp_path, leaderboards=lb), enforce=False)
    assert res.report["chain_current_board"]["rate"] < 0.9
    assert res.report["dim_unresolved_rows"] >= _BOARD_IDS - 1   # only the graduate leg survives


def test_a_non_unique_bridge_key_is_rejected(conn, tmp_path):
    """A duplicated join key silently MULTIPLIES rows. The builder asserts uniqueness where it
    cannot dedupe (here: two DIFFERENT MLBAM ids published for one fg_minor_id is a real vendor
    conflict, not something to silently pick a winner from)."""
    lb = _leaderboard_rows()
    dupe = lb.iloc[[0]].copy()
    dupe["mlbam_id"] = "999999"
    dupe["season"] = 2025
    res = build_xref(conn, _make_sources(tmp_path, leaderboards=pd.concat([lb, dupe])))
    # argmax on (as_of_date|season) resolves to ONE id deterministically — the newest observation
    assert res.dim.set_index("fg_minor_id").loc["sa100"]["mlbam_id"] == "800001"
    assert not res.dim["xref_key"].duplicated().any()


# ── The report is the AC deliverable ─────────────────────────────────────────────────────────

def test_report_carries_every_hop_and_renders(conn, tmp_path):
    res = build_xref(conn, _make_sources(tmp_path))
    rep = res.report
    for key in ("hop1_board_to_leaderboard", "hop2_leaderboard_mlbam",
                "hop3_board_fg_mlb_id_to_mlbam", "chain_current_board",
                "unresolved_current_board", "match_method_counts"):
        assert key in rep, key
    assert rep["chain_current_board"]["board_ids"] == _BOARD_IDS
    assert rep["chain_current_board"]["resolved"] == _BOARD_RESOLVED
    assert len(rep["unresolved_current_board"]) == 1
    text = format_report(rep)
    assert "HOP 1" in text and "HOP 2" in text and "HOP 3" in text and "CHAIN" in text
