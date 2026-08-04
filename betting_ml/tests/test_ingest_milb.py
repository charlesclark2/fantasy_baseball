"""E7.1 — fast-gate unit tests for scripts/ingest_milb_to_s3.py (pure logic only).

No IO: the module's Delta/S3 paths import deltalake/boto3 LAZILY inside functions, so
importing the module + exercising the flatteners/parsers touches no network or S3. This
mirrors the suite's "fast-gate tests inspect source or import pure logic, never pipeline"
rule (CLAUDE.md) — nothing here imports `pipeline`.
"""
import importlib.util
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPT = REPO / "scripts" / "ingest_milb_to_s3.py"

_spec = importlib.util.spec_from_file_location("ingest_milb_to_s3", _SCRIPT)
milb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(milb)


# ── level / history constants match the verified-live API reality ──────────────

def test_sport_levels_are_the_four_minor_ids():
    assert milb.SPORT_LEVELS == {11: "Triple-A", 12: "Double-A", 13: "High-A", 14: "Single-A"}


def test_earliest_season_floor():
    # Probed live 2026-07-22: 2004 and earlier return totalGames=0 for every minor sportId.
    assert milb.EARLIEST_SEASON == 2005


# ── age is a leakage-safe point-in-time value, never the API currentAge ────────

def test_age_is_point_in_time_from_birthdate():
    # born 2000-06-21; on 2024-06-21 exactly 24.0 yrs
    assert milb._age_years("2000-06-21", date(2024, 6, 21)) == 24.0
    # six months earlier => clearly under 24 (guards against using the API's
    # as-of-today currentAge, which would be constant regardless of game date)
    assert milb._age_years("2000-06-21", date(2023, 12, 21)) < 23.6


def test_age_handles_missing_or_bad_birthdate():
    assert milb._age_years(None, date(2024, 6, 1)) is None
    assert milb._age_years("", date(2024, 6, 1)) is None
    assert milb._age_years("not-a-date", date(2024, 6, 1)) is None


# ── _int coerces the API's mixed str/int/None cleanly ──────────────────────────

def test_int_coercion():
    assert milb._int("753282") == 753282
    assert milb._int(431) == 431
    assert milb._int(None) is None
    assert milb._int("") is None
    assert milb._int("N/A") is None


# ── schedule flatten pulls level / league / affiliate / park from the hydrate ──

def _hydrated_game():
    return {
        "gamePk": 753282, "season": 2024, "officialDate": "2024-06-15",
        "gameDate": "2024-06-15T23:05:00Z", "gameType": "R", "gameNumber": 1,
        "doubleHeader": "N", "scheduledInnings": 9,
        "status": {"detailedState": "Final", "abstractGameState": "Final"},
        "venue": {"id": 3810, "name": "Coolray Field"},
        "seriesDescription": "Regular Season",
        "teams": {
            "home": {"team": {
                "id": 431, "name": "Gwinnett Stripers",
                "sport": {"id": 11, "name": "Triple-A"},
                "league": {"id": 117, "name": "International League"},
                "division": {"name": "International League West"},
                "parentOrgId": 144, "parentOrgName": "Atlanta Braves",
            }},
            "away": {"team": {
                "id": 452, "name": "Memphis Redbirds",
                "league": {"id": 117, "name": "International League"},
                "parentOrgId": 138, "parentOrgName": "St. Louis Cardinals",
            }},
        },
    }


def test_flatten_schedule_game():
    row = milb._flatten_schedule_game(_hydrated_game(), sport_id=11)
    assert row["game_pk"] == 753282
    assert row["sport_id"] == 11 and row["level_name"] == "Triple-A"
    assert row["season"] == 2024 and row["official_date"] == "2024-06-15"
    assert row["status_abstract"] == "Final"
    assert row["venue_id"] == 3810 and row["venue_name"] == "Coolray Field"
    assert row["home_parent_org_name"] == "Atlanta Braves"
    assert row["away_parent_org_name"] == "St. Louis Cardinals"
    assert row["home_league_name"] == "International League"


# ── boxscore flatten → per-player rows carrying every AC field ──────────────────

def _boxscore():
    return {"teams": {
        "home": {"players": {
            "ID644433": {
                "person": {"id": 644433, "fullName": "Chadwick Tromp"},
                "position": {"code": "2", "abbreviation": "C"},
                "battingOrder": "500", "parentTeamId": 144,
                "stats": {"batting": {"plateAppearances": 4, "atBats": 4, "hits": 2,
                                      "homeRuns": 1, "rbi": 2, "strikeOuts": 1,
                                      "baseOnBalls": 0}, "pitching": {}},
            },
            "ID111": {  # bench player who never appeared — dropped
                "person": {"id": 111, "fullName": "Bench Guy"},
                "position": {"code": "7", "abbreviation": "LF"},
                "stats": {"batting": {}, "pitching": {}},
            },
        }},
        "away": {"players": {
            "ID676979": {
                "person": {"id": 676979, "fullName": "Dylan Dodd"},
                "position": {"code": "1", "abbreviation": "P"},
                "parentTeamId": 138,
                "stats": {"batting": {}, "pitching": {"inningsPitched": "5.0",
                          "strikeOuts": 5, "earnedRuns": 2, "battersFaced": 18,
                          "baseOnBalls": 0}},
            },
        }},
    }}


def test_flatten_boxscore_grain_and_ac_fields():
    sched = milb._flatten_schedule_game(_hydrated_game(), sport_id=11)
    people = {
        644433: {"birthDate": "1995-03-21", "batSide": {"code": "R"}, "pitchHand": {"code": "R"}},
        676979: {"birthDate": "1999-06-21", "batSide": {"code": "L"}, "pitchHand": {"code": "L"}},
    }
    rows = milb.flatten_boxscore(_boxscore(), sched, people, "2026-07-22T00:00:00+00:00")
    # bench player (no batting, no pitching) is dropped → 2 rows
    assert len(rows) == 2
    by_id = {r["player_id"]: r for r in rows}

    batter = by_id[644433]
    assert batter["team_side"] == "home" and batter["level_name"] == "Triple-A"
    assert batter["league_name"] == "International League"
    assert batter["affiliate_org_name"] == "Atlanta Braves"   # home side's org
    assert batter["venue_name"] == "Coolray Field"
    assert batter["official_date"] == "2024-06-15"
    assert batter["is_batter"] is True and batter["is_pitcher"] is False
    assert batter["bat_hits"] == 2 and batter["bat_home_runs"] == 1
    assert batter["age"] == milb._age_years("1995-03-21", date(2024, 6, 15))
    assert batter["ingestion_ts"] == "2026-07-22T00:00:00+00:00"

    pitcher = by_id[676979]
    assert pitcher["team_side"] == "away"
    assert pitcher["affiliate_org_name"] == "St. Louis Cardinals"  # away side's org
    assert pitcher["is_pitcher"] is True
    assert pitcher["pit_innings_pitched"] == "5.0"   # kept as string
    assert pitcher["pit_strike_outs"] == 5


# ── CLI parsers ─────────────────────────────────────────────────────────────────

def test_parse_seasons_range_and_list():
    assert milb._parse_seasons("2005-2008") == [2005, 2006, 2007, 2008]
    assert milb._parse_seasons("2024") == [2024]
    assert milb._parse_seasons("2005,2007,2009") == [2005, 2007, 2009]


def test_parse_month():
    assert milb._parse_month("2024-06") == (2024, 6)
    assert milb._parse_month(None) is None


def test_iter_months_spans_year_boundary():
    assert list(milb.iter_months((2024, 11), (2025, 2))) == [
        (2024, 11), (2024, 12), (2025, 1), (2025, 2)]
    assert list(milb.iter_months((2024, 6), (2024, 6))) == [(2024, 6)]


def test_partition_cols_pin_the_three_partition_keys():
    # idempotent partition-skip + O(one month) overwrite hinge on this triple
    assert milb.PARTITION_COLS == ["season", "sport_id", "month"]


# ══════════════════════════════════════════════════════════════════════════════════
# E8.7 — sportId 16 ("Rookie") spans SEVERAL rungs, so the level cannot come from the
# sportId. These guards pin the three ways that mapping can silently go wrong.
# Every one was verified to FAIL against a deliberately-broken derive_level_name
# (a flat `16 -> "Rookie"`, a name-keyed map, and a game-level level_name).
# ══════════════════════════════════════════════════════════════════════════════════

def test_sport_id_16_is_ingestible_but_not_in_the_one_id_one_level_map():
    # SPORT_LEVELS is the "sportId IS the rung" map and 16 must NEVER join it — a flat
    # 16 -> "Rookie" entry is exactly the rung-collapsing bug.
    assert 16 not in milb.SPORT_LEVELS
    assert milb.ROOKIE_SPORT_ID == 16
    assert milb.INGESTIBLE_SPORT_IDS == (11, 12, 13, 14, 16)


def test_sport_id_16_resolves_dsl_and_cpx_to_DIFFERENT_rungs():
    """The headline trap: DSL (board rank 1) and CPX (rank 2) are different rungs.

    Fails on a flat `16: "Rookie"` mapping, which returns one level for both.
    """
    dsl = milb.derive_level_name(16, 130, "Dominican Summer League")
    cpx_fcl = milb.derive_level_name(16, 124, "Florida Complex League")
    cpx_acl = milb.derive_level_name(16, 121, "Arizona Complex League")
    assert dsl == "DSL"
    assert cpx_fcl == cpx_acl == "CPX"
    assert dsl != cpx_fcl, "DSL and CPX collapsed to one rung — the level ladder is corrupt"


def test_level_is_keyed_on_league_ID_so_the_2021_RENAME_does_not_drop_pre_2021_rows():
    """Leagues 121/124 were RENAMED in 2021 (Arizona League→ACL, Gulf Coast→FCL).

    A name-keyed map returns None for the pre-2021 spellings and silently loses every
    pre-2021 CPX row — which is most of the ladder's history. Probed live 2026-08-03.
    """
    assert milb.derive_level_name(16, 121, "Arizona League") == "CPX"        # ≤2020 spelling
    assert milb.derive_level_name(16, 124, "Gulf Coast League") == "CPX"     # ≤2020 spelling
    assert milb.derive_level_name(16, 121, "Arizona Complex League") == "CPX"  # 2021+ spelling
    assert milb.derive_level_name(16, 124, "Florida Complex League") == "CPX"  # 2021+ spelling


def test_historical_rookie_advanced_leagues_stay_distinct_from_complex():
    # Appalachian/Pioneer were rookie-ADVANCED (a rung above complex), affiliated ≤2020.
    # Folding them into CPX would put a higher rung's lines into the complex cell.
    assert milb.derive_level_name(16, 120, "Appalachian League") == "Rookie-Adv"
    assert milb.derive_level_name(16, 128, "Pioneer League") == "Rookie-Adv"
    # Venezuelan Summer is the DSL's sibling rung, not a complex league.
    assert milb.derive_level_name(16, 134, "Venezuelan Summer League") == "DSL"


def test_unrecognised_league_yields_None_rather_than_a_guessed_rung():
    """A NULL level is skipped downstream; a WRONG level silently corrupts a rung.

    Both strays below are REAL sportId-16 opponents found in the live probe.
    """
    assert milb.derive_level_name(16, 107, "College Baseball") is None
    assert milb.derive_level_name(16, 126, "Northwest League") is None
    assert milb.derive_level_name(16, None, None) is None


def test_sport_ids_11_to_14_are_untouched_by_the_league_derivation():
    # Regression: the E8.7 change must not alter any existing level. The league id is
    # deliberately ignored for these sportIds.
    for sid, level in milb.SPORT_LEVELS.items():
        assert milb.derive_level_name(sid, 117, "International League") == level
        assert milb.derive_level_name(sid, 130, "Dominican Summer League") == level


def _rookie_game(home_league=(130, "Dominican Summer League"),
                 away_league=(130, "Dominican Summer League")):
    return {
        "gamePk": 800001, "season": 2025, "officialDate": "2025-07-08",
        "gameDate": "2025-07-08T15:00:00Z", "gameType": "R", "gameNumber": 1,
        "doubleHeader": "N", "scheduledInnings": 9,
        "status": {"detailedState": "Final", "abstractGameState": "Final"},
        "venue": {"id": 5000, "name": "Complex Field 2"},
        "seriesDescription": "Regular Season",
        "teams": {
            "home": {"team": {"id": 2001, "name": "DSL Reds",
                              "sport": {"id": 16, "name": "Rookie"},
                              "league": {"id": home_league[0], "name": home_league[1]},
                              "parentOrgId": 113, "parentOrgName": "Cincinnati Reds"}},
            "away": {"team": {"id": 2002, "name": "DSL Rockies",
                              "league": {"id": away_league[0], "name": away_league[1]},
                              "parentOrgId": 115, "parentOrgName": "Colorado Rockies"}},
        },
    }


def test_schedule_row_carries_a_PER_SIDE_level():
    row = milb._flatten_schedule_game(_rookie_game(), sport_id=16)
    assert row["sport_id"] == 16
    assert row["home_level_name"] == "DSL" and row["away_level_name"] == "DSL"
    assert row["level_name"] == "DSL"


def test_a_CROSS_LEAGUE_rookie_game_labels_each_side_with_its_OWN_rung():
    """Measured: 2 of 10,364 probed sportId-16 games are cross-league.

    A single game-level level_name necessarily mislabels one side of these.
    """
    g = _rookie_game(home_league=(121, "Arizona Complex League"),
                     away_league=(107, "College Baseball"))
    row = milb._flatten_schedule_game(g, sport_id=16)
    assert row["home_level_name"] == "CPX"
    assert row["away_level_name"] is None, "a College Baseball opponent must not inherit a rung"


def test_player_rows_inherit_THEIR_OWN_SIDE_rung_not_the_games():
    """The load-bearing one: a player's level must follow the player's team.

    Fixture is built so ONLY the per-side lookup can produce the right answer — the
    game-level `level_name` is CPX, so an away player reading it would be given CPX.
    """
    g = _rookie_game(home_league=(121, "Arizona Complex League"),
                     away_league=(130, "Dominican Summer League"))
    sched = milb._flatten_schedule_game(g, sport_id=16)
    assert sched["level_name"] == "CPX"  # game-level value = the home side's
    box = {"teams": {
        "home": {"players": {"ID9001": {
            "person": {"id": 9001, "fullName": "Home Complex Bat"},
            "position": {"code": "6", "abbreviation": "SS"},
            "stats": {"batting": {"plateAppearances": 4, "atBats": 4, "hits": 1,
                                  "stolenBases": 1, "caughtStealing": 0}, "pitching": {}}}}},
        "away": {"players": {"ID9002": {
            "person": {"id": 9002, "fullName": "Away DSL Bat"},
            "position": {"code": "4", "abbreviation": "2B"},
            "stats": {"batting": {"plateAppearances": 3, "atBats": 3, "hits": 2,
                                  "stolenBases": 2, "caughtStealing": 1}, "pitching": {}}}}},
    }}
    rows = milb.flatten_boxscore(box, sched, {}, "2026-08-03T00:00:00+00:00")
    by_id = {r["player_id"]: r for r in rows}
    assert by_id[9001]["level_name"] == "CPX"
    assert by_id[9002]["level_name"] == "DSL", \
        "away player inherited the GAME's rung instead of its own team's"
    # E8.7's whole point: the SB inputs the board needs are present on a complex line.
    assert by_id[9002]["bat_stolen_bases"] == 2 and by_id[9002]["bat_caught_stealing"] == 1
    assert by_id[9002]["bat_plate_appearances"] == 3


def test_the_sport_id_help_string_matches_the_ACTUAL_default_set():
    """A stale --help default is what an operator copy-pastes from. Pin it to the real set.

    (E8.7 shipped this string reading '11,12,13,14' after 16 was already in the default.)
    """
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport-ids")
    src = _SCRIPT.read_text()
    expected = ",".join(str(s) for s in milb.INGESTIBLE_SPORT_IDS)
    assert f"default all: {expected}" in src, (
        f"--sport-ids help does not name the real default set ({expected})"
    )
