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
