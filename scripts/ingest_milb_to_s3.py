"""
ingest_milb_to_s3.py   (E7.1 — MiLB game-log / box ingestion → S3 Delta lakehouse)
----------------------------------------------------------------------------------
Ingest minor-league schedule + boxscores from the MLB Stats API and land two
Delta tables on S3 (SF-FREE, instance-role S3 auth):

    baseball/milb/schedule          — one row per game (the game universe)
    baseball/milb/player_game_logs  — one row per (game_pk, player_id): the staged
                                      per-player game log carrying level / league /
                                      affiliate / park / date / age + the box line.

Levels (Stats API minor `sportId`s — VERIFIED live 2026-07-22):
    11 Triple-A · 12 Double-A · 13 High-A · 14 Single-A
    16 "Rookie"  — E8.7: the COMPLEX tier. ⚠️ ONE sportId, SEVERAL distinct rungs.

⭐ E8.7 — WHY sportId 16 CANNOT USE THE `SPORT_LEVELS` ONE-ID-ONE-LEVEL MAPPING (probed live
   2026-08-03; every number below is measured, not read off a doc):
  • sportId 16 ("Rookie") contains THREE live leagues — Dominican Summer (130), Florida Complex
    (124), Arizona Complex (121) — plus, historically, Venezuelan Summer (134), Appalachian (120)
    and Pioneer (128). The board ranks DSL and CPX as DIFFERENT rungs, so a flat `16: "Rookie"`
    mapping COLLAPSES two rungs and corrupts the level ladder.
  • ⚠️ AND THE LEAGUE **NAME** IS NOT A DURABLE KEY — it was RENAMED mid-history for exactly the
    two leagues that make up CPX: league 124 "Gulf Coast League" → "Florida Complex League" and
    league 121 "Arizona League" → "Arizona Complex League", both at the 2021 reorganisation. A
    name-keyed map silently drops every pre-2021 CPX row. The level is therefore derived from the
    league **ID**, with the name kept only as a last-resort fallback for an unseen id.
  • ⚠️ AND THE LEVEL IS PER-**TEAM**, NOT PER-GAME: 2 of 10,364 probed sportId-16 games are
    cross-league, and the stray opponents include league 107 "College Baseball" and league 126
    "Northwest League". A single game-level `level_name` would mislabel those rows, so each side
    carries its own `home_level_name` / `away_level_name` and a player row inherits ITS OWN side's.
  • An UNRECOGNISED league id yields level_name=None (and a counted warning) — never a guess. A
    NULL level is skipped by every downstream level filter; a WRONG level silently corrupts a rung.
  • Boxscore field parity confirmed: sportId-16 boxscores carry identical `plateAppearances` /
    `stolenBases` / `caughtStealing` / `hits` / `doubles` … so BATTING_FIELDS/PITCHING_FIELDS are
    UNCHANGED. (sportId 17 is Winter Leagues, NOT the DSL — it is deliberately not ingested.)

⭐ API reality (probed live, not coded-to-docs — the recurring E7/P0.1/N0.x lesson):
  • schedule?sportId=<N>&startDate&endDate&hydrate=team,venue,linescore returns, per
    game, the FULL team object with sport(=level) / league / division / parentOrgId /
    parentOrgName(=MLB affiliate) AND venue(=park) in ONE call — no per-team fetch.
  • game/<gamePk>/boxscore → teams.{home,away}.players[pID].stats.{batting,pitching}
    is the SINGLE-GAME line (seasonStats is separate), with person.id, position,
    battingOrder, parentTeamId. This IS the per-player game-log grain.
  • Age is NOT in the boxscore — it is derived from people?personIds=<...>.birthDate
    (batched) + the game officialDate (a point-in-time age; the API's currentAge is
    as-of-today = leakage, never used).
  • Deepest history the schedule/boxscore endpoints return = season 2005 (2004 and
    earlier return totalGames=0 for every minor sportId). EARLIEST_SEASON pins this.

Storage / idempotency:
  • Delta-aware, SF-FREE. Delta tables written via delta-rs (deltalake==1.6) through
    scripts/utils/delta_lake.storage_options() — the instance-role-safe S3 auth that
    dodges the AKID / empty-env-var landmine (CLAUDE.md boto3 + delta-rs object_store).
  • Partitioned by (season, sport_id, month). A (season, sport_id, month) partition is
    written with an overwrite predicate pinning those three cols → idempotent + O(one
    month), resumable at month grain.
  • Idempotent partition-skip: a month partition already present is SKIPPED on backfill
    unless --force. The CURRENT month is always re-pulled (absorbs late box updates),
    mirroring the statcast trailing-lookback pattern.
  • Every row carries a leakage-safe ingestion_ts (ISO-UTC VARCHAR — the lakehouse_raw
    convention; a downstream as-of join filters ingestion_ts <= decision_time). Stored
    as VARCHAR so no binary-timestamp scale bite (INC-23); cast at the use-site.

Usage (all SF-FREE — AWS creds via the instance role / env only):
    # Verification stub — one sport, one month, cap the game fetches, no write:
    uv run python scripts/ingest_milb_to_s3.py --seasons 2024 --sport-ids 11 \
        --start-month 2024-06 --end-month 2024-06 --max-games 3 --dry-run

    # Real small slice (one sport, one month):
    uv run python scripts/ingest_milb_to_s3.py --seasons 2024 --sport-ids 11 \
        --start-month 2024-06 --end-month 2024-06

    # Incremental (current season, all levels, current + prior month) — the daily op:
    uv run python scripts/ingest_milb_to_s3.py --incremental

    # FULL historical backfill (>1 min — HAND TO OPERATOR, runs off-box; resumable):
    uv run python scripts/ingest_milb_to_s3.py --seasons 2005-2026
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

# scripts/utils reused for the instance-role-safe Delta S3 auth + a boto3 client.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

BUCKET = "baseball-betting-ml-artifacts"
REGION = "us-east-2"
# The story's `.../milb/` prefix. Delta table dirs live directly under it, isolated
# from the existing baseball/lakehouse/ (no ext-table glob touches milb/ so there is
# no glob-dup risk — the delta_lakehouse LAKEHOUSE_DELTA co-location caveat is moot).
MILB_S3_PREFIX = "baseball/milb"
SCHEDULE_TABLE = "schedule"
LOGS_TABLE = "player_game_logs"

# VERIFIED live 2026-07-22 — the minor sportIds whose level IS the sportId (one id → one rung).
SPORT_LEVELS: dict[int, str] = {
    11: "Triple-A",
    12: "Double-A",
    13: "High-A",
    14: "Single-A",
}

# E8.7 — the one sportId whose level is NOT determined by the sportId (see the module docstring).
ROOKIE_SPORT_ID = 16

# league_id → rung, VERIFIED live 2026-08-03 across seasons 2008…2026. Keyed on the **ID** because the
# NAME was renamed in 2021 for both CPX leagues (121 "Arizona League"→"Arizona Complex League";
# 124 "Gulf Coast League"→"Florida Complex League"), so a name-keyed map loses all pre-2021 CPX rows.
#
#   DSL     — foreign summer/complex ball, the lowest affiliated rung (board rank 1).
#   CPX     — domestic complex ball (board rank 2).
#   Rookie-Adv — the short-season rookie-ADVANCED leagues, a rung ABOVE complex. Affiliated only
#               through 2020 (Appalachian went collegiate-summer and Pioneer went independent in
#               2021), so this rung is HISTORY-ONLY and cannot appear for a current prospect. It is
#               kept DISTINCT here rather than folded into CPX — the lakehouse preserves the
#               distinction even where the board's rank vocabulary approximates it.
ROOKIE_LEAGUE_LEVELS: dict[int, str] = {
    130: "DSL",          # Dominican Summer League
    134: "DSL",          # Venezuelan Summer League (through ~2015) — same rung, different league
    121: "CPX",          # Arizona League → Arizona Complex League (renamed 2021)
    124: "CPX",          # Gulf Coast League → Florida Complex League (renamed 2021)
    120: "Rookie-Adv",   # Appalachian League (affiliated ≤2020)
    128: "Rookie-Adv",   # Pioneer League (affiliated ≤2020)
}

# Last-resort fallback for a league id never seen in the probe, matched on the NAME. Deliberately
# narrow: it exists so a NEW complex league (a hypothetical league 1xx) is not silently dropped, not
# so an arbitrary opponent gets a guessed rung.
_ROOKIE_LEAGUE_NAME_HINTS: tuple[tuple[str, str], ...] = (
    ("dominican summer", "DSL"),
    ("venezuelan summer", "DSL"),
    ("complex league", "CPX"),
)

# Every sportId this script knows how to ingest.
INGESTIBLE_SPORT_IDS: tuple[int, ...] = tuple(SPORT_LEVELS) + (ROOKIE_SPORT_ID,)


def sport_label(sport_id: int) -> str:
    """A human label for logging. sportId 16 spans several rungs, so it logs as the TIER name."""
    return SPORT_LEVELS.get(sport_id) or ("Rookie/Complex" if sport_id == ROOKIE_SPORT_ID
                                          else f"sport{sport_id}")


def derive_level_name(sport_id: int, league_id: int | None, league_name: str | None) -> str | None:
    """The rung for ONE TEAM in one game.

    For sportIds 11–14 the sportId IS the rung. For sportId 16 the rung comes from the team's
    league ID (name only as a fallback) — see the module docstring for why neither the sportId nor
    the league NAME is a usable key there. Returns None for an unrecognised league: a NULL level is
    skipped by every downstream level filter, whereas a GUESSED level silently corrupts a rung.
    """
    if sport_id != ROOKIE_SPORT_ID:
        return SPORT_LEVELS.get(sport_id)
    if league_id is not None:
        level = ROOKIE_LEAGUE_LEVELS.get(int(league_id))
        if level:
            return level
    if league_name:
        low = str(league_name).strip().lower()
        for needle, level in _ROOKIE_LEAGUE_NAME_HINTS:
            if needle in low:
                return level
    return None

# Deepest history the schedule/boxscore endpoints return (probed: 2005 has games,
# 2004 and earlier return totalGames=0 for every minor sportId).
EARLIEST_SEASON = 2005

STATSAPI = "https://statsapi.mlb.com/api/v1"
SCHEDULE_URL = f"{STATSAPI}/schedule"
BOXSCORE_URL = f"{STATSAPI}/game/{{game_pk}}/boxscore"
PEOPLE_URL = f"{STATSAPI}/people"
SCHEDULE_HYDRATE = "team,venue,linescore"

REQUEST_TIMEOUT = 30
REQUEST_DELAY = 0.25          # polite delay between game/box fetches
MAX_RETRIES = 3
RETRY_BACKOFF = 5
PEOPLE_BATCH = 100            # people?personIds= chunk size

# Statuses that mean the box line is meaningful (played games only).
FINAL_STATES = {"Final", "Game Over", "Completed Early"}

# Boxscore batting fields kept, camelCase → bat_<snake>. Single-game line.
BATTING_FIELDS: dict[str, str] = {
    "gamesPlayed": "bat_games_played",
    "plateAppearances": "bat_plate_appearances",
    "atBats": "bat_at_bats",
    "runs": "bat_runs",
    "hits": "bat_hits",
    "doubles": "bat_doubles",
    "triples": "bat_triples",
    "homeRuns": "bat_home_runs",
    "rbi": "bat_rbi",
    "baseOnBalls": "bat_walks",
    "intentionalWalks": "bat_intentional_walks",
    "hitByPitch": "bat_hit_by_pitch",
    "strikeOuts": "bat_strike_outs",
    "stolenBases": "bat_stolen_bases",
    "caughtStealing": "bat_caught_stealing",
    "sacBunts": "bat_sac_bunts",
    "sacFlies": "bat_sac_flies",
    "groundIntoDoublePlay": "bat_gidp",
    "groundOuts": "bat_ground_outs",
    "airOuts": "bat_air_outs",
    "totalBases": "bat_total_bases",
    "leftOnBase": "bat_left_on_base",
}

# Boxscore pitching fields kept, camelCase → pit_<snake>. Single-game line.
PITCHING_FIELDS: dict[str, str] = {
    "gamesPlayed": "pit_games_played",
    "gamesStarted": "pit_games_started",
    "inningsPitched": "pit_innings_pitched",  # STRING like "5.0" from the API
    "battersFaced": "pit_batters_faced",
    "atBats": "pit_at_bats",
    "hits": "pit_hits",
    "runs": "pit_runs",
    "earnedRuns": "pit_earned_runs",
    "homeRuns": "pit_home_runs",
    "baseOnBalls": "pit_walks",
    "intentionalWalks": "pit_intentional_walks",
    "hitByPitch": "pit_hit_by_pitch",
    "strikeOuts": "pit_strike_outs",
    "numberOfPitches": "pit_number_of_pitches",
    "strikes": "pit_strikes",
    "wins": "pit_wins",
    "losses": "pit_losses",
    "saves": "pit_saves",
    "holds": "pit_holds",
    "blownSaves": "pit_blown_saves",
    "outs": "pit_outs",
    "groundOuts": "pit_ground_outs",
    "airOuts": "pit_air_outs",
    "completeGames": "pit_complete_games",
    "shutouts": "pit_shutouts",
}


# ── Stats API fetchers ─────────────────────────────────────────────────────────

def _get_json(session: requests.Session, url: str, params: dict | None = None) -> dict:
    """GET with bounded retry/backoff; assert a JSON body (a wrong path can 200 HTML)."""
    backoff = RETRY_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "")
            if "application/json" not in ctype:
                raise ValueError(f"non-JSON response ({ctype}) from {url}")
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt >= MAX_RETRIES:
                raise
            log.warning("  [%d/%d] %s — retry in %ds", attempt, MAX_RETRIES, exc, backoff)
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError("unreachable")


def fetch_schedule_month(session, sport_id: int, year: int, month: int) -> list[dict]:
    """All games for one (sport_id, year, month), each flattened to a schedule row."""
    start = date(year, month, 1)
    end = _last_day_of_month(year, month)
    payload = _get_json(session, SCHEDULE_URL, {
        "sportId": sport_id,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "hydrate": SCHEDULE_HYDRATE,
    })
    rows: list[dict] = []
    for d in payload.get("dates", []):
        for g in d.get("games", []):
            rows.append(_flatten_schedule_game(g, sport_id))
    return rows


def fetch_boxscore(session, game_pk: int) -> dict:
    return _get_json(session, BOXSCORE_URL.format(game_pk=game_pk))


def fetch_people(session, person_ids: list[int]) -> dict[int, dict]:
    """Batched people lookup → {id: person}. Only birthDate/bats/throws are used."""
    out: dict[int, dict] = {}
    for i in range(0, len(person_ids), PEOPLE_BATCH):
        chunk = person_ids[i:i + PEOPLE_BATCH]
        payload = _get_json(session, PEOPLE_URL, {
            "personIds": ",".join(str(p) for p in chunk),
        })
        for p in payload.get("people", []):
            out[int(p["id"])] = p
        time.sleep(REQUEST_DELAY)
    return out


# ── Flatteners ─────────────────────────────────────────────────────────────────

def _last_day_of_month(year: int, month: int) -> date:
    import calendar
    return date(year, month, calendar.monthrange(year, month)[1])


def _flatten_schedule_game(g: dict, sport_id: int) -> dict:
    """One hydrated schedule game → a flat schedule row (game metadata)."""
    home = g.get("teams", {}).get("home", {}).get("team", {}) or {}
    away = g.get("teams", {}).get("away", {}).get("team", {}) or {}
    venue = g.get("venue", {}) or {}
    status = g.get("status", {}) or {}

    def _team_cols(t: dict, side: str) -> dict:
        league_id = _int((t.get("league") or {}).get("id"))
        league_name = (t.get("league") or {}).get("name")
        return {
            f"{side}_team_id": _int(t.get("id")),
            f"{side}_team_name": t.get("name"),
            f"{side}_league_id": league_id,
            f"{side}_league_name": league_name,
            # E8.7: the rung is a property of the TEAM's league, not of the game's sportId — a
            # sportId-16 game can be cross-league (measured: 2 of 10,364), so each side carries its
            # own level and a player row inherits ITS OWN side's, never the game's.
            f"{side}_level_name": derive_level_name(sport_id, league_id, league_name),
            f"{side}_division_name": (t.get("division") or {}).get("name"),
            f"{side}_parent_org_id": _int(t.get("parentOrgId")),
            f"{side}_parent_org_name": t.get("parentOrgName"),
        }

    home_cols, away_cols = _team_cols(home, "home"), _team_cols(away, "away")
    # Game-level `level_name` is retained for the 11–14 levels (where it is exact) and for cheap
    # partition-level filtering. On a cross-league sportId-16 game it takes the home side's rung and
    # is therefore APPROXIMATE — which is precisely why the per-side columns exist and why
    # flatten_boxscore prefers them.
    game_level = home_cols["home_level_name"] or away_cols["away_level_name"]

    row = {
        "game_pk": _int(g.get("gamePk")),
        "sport_id": sport_id,
        "level_name": game_level,
        "season": _int(g.get("season")),
        "official_date": g.get("officialDate"),
        "game_date": g.get("gameDate"),
        "game_type": g.get("gameType"),
        "game_number": _int(g.get("gameNumber")),
        "double_header": g.get("doubleHeader"),
        "status_detailed": status.get("detailedState"),
        "status_abstract": status.get("abstractGameState"),
        "scheduled_innings": _int(g.get("scheduledInnings")),
        "venue_id": _int(venue.get("id")),
        "venue_name": venue.get("name"),
        "series_description": g.get("seriesDescription"),
    }
    row.update(home_cols)
    row.update(away_cols)
    return row


def _age_years(birth_date: str | None, on: date) -> float | None:
    """Point-in-time age in years (float) on the game date, from an ISO birthDate."""
    if not birth_date:
        return None
    try:
        b = date.fromisoformat(birth_date[:10])
    except ValueError:
        return None
    return round((on - b).days / 365.25, 2)


def flatten_boxscore(
    box: dict,
    sched: dict,
    people: dict[int, dict],
    ingestion_ts: str,
) -> list[dict]:
    """One boxscore + its schedule row + people cache → per-player game-log rows.

    Denormalises the AC fields (level / league / affiliate / park / date / age) onto
    every player row so player_game_logs is self-contained for E7.3.
    """
    official = sched.get("official_date")
    on_date = date.fromisoformat(official) if official else None
    rows: list[dict] = []
    for side in ("home", "away"):
        team_block = box.get("teams", {}).get(side, {}) or {}
        players = team_block.get("players", {}) or {}
        # the player's own team + its affiliate/league come from the schedule side
        team_id = sched.get(f"{side}_team_id")
        for _key, pl in players.items():
            person = pl.get("person", {}) or {}
            pid = _int(person.get("id"))
            if pid is None:
                continue
            stats = pl.get("stats", {}) or {}
            batting = stats.get("batting", {}) or {}
            pitching = stats.get("pitching", {}) or {}
            # skip players who neither batted nor pitched (bench who never appeared)
            if not batting and not pitching:
                continue
            pos = pl.get("position", {}) or {}
            bio = people.get(pid, {}) or {}
            row = {
                # identity / grain
                "game_pk": sched.get("game_pk"),
                "player_id": pid,
                "player_name": person.get("fullName"),
                "team_side": side,
                "team_id": team_id,
                "parent_team_id": _int(pl.get("parentTeamId")),
                # game context (AC: level / league / affiliate / park / date)
                "sport_id": sched.get("sport_id"),
                # E8.7: THIS side's rung (see _flatten_schedule_game). Falls back to the game-level
                # value only for a pre-E8.7 schedule row that predates the per-side columns.
                "level_name": sched.get(f"{side}_level_name") or sched.get("level_name"),
                "season": sched.get("season"),
                "official_date": official,
                "game_type": sched.get("game_type"),
                "league_id": sched.get(f"{side}_league_id"),
                "league_name": sched.get(f"{side}_league_name"),
                "affiliate_org_id": sched.get(f"{side}_parent_org_id"),
                "affiliate_org_name": sched.get(f"{side}_parent_org_name"),
                "venue_id": sched.get("venue_id"),
                "venue_name": sched.get("venue_name"),
                # player bio (AC: age)
                "age": _age_years(bio.get("birthDate"), on_date) if on_date else None,
                "birth_date": (bio.get("birthDate") or None),
                "bat_side": (bio.get("batSide") or {}).get("code"),
                "pitch_hand": (bio.get("pitchHand") or {}).get("code"),
                # role in this game
                "position_code": pos.get("code"),
                "position_abbrev": pos.get("abbreviation"),
                "batting_order": _int(pl.get("battingOrder")),
                "is_pitcher": bool(pitching),
                "is_batter": bool(batting) and int(batting.get("plateAppearances", 0) or 0) > 0,
                # leakage-safe provenance
                "ingestion_ts": ingestion_ts,
            }
            for api_col, staged in BATTING_FIELDS.items():
                row[staged] = _int(batting.get(api_col)) if batting else None
            for api_col, staged in PITCHING_FIELDS.items():
                if staged == "pit_innings_pitched":
                    row[staged] = pitching.get(api_col) if pitching else None
                else:
                    row[staged] = _int(pitching.get(api_col)) if pitching else None
            rows.append(row)
    return rows


def _int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


# ── Delta write layer (instance-role-safe S3 auth) ──────────────────────────────

PARTITION_COLS = ["season", "sport_id", "month"]


def _table_uri(table: str) -> str:
    return f"s3://{BUCKET}/{MILB_S3_PREFIX}/{table}"


def _storage_options() -> dict:
    """delta-rs S3 storage_options with concrete instance-role creds (dodges the
    AKID/empty-env landmine). Reuses the shared, hardened resolver."""
    try:
        from utils.delta_lake import storage_options
    except ImportError:  # pragma: no cover
        from scripts.utils.delta_lake import storage_options
    return storage_options()


def _delta_table(table: str):
    from deltalake import DeltaTable
    from deltalake.exceptions import TableNotFoundError
    try:
        return DeltaTable(_table_uri(table), storage_options=_storage_options())
    except TableNotFoundError:
        return None


def existing_partitions(table: str) -> set[tuple[int, int, int]]:
    """The (season, sport_id, month) partitions already present in a Delta table."""
    dt = _delta_table(table)
    if dt is None:
        return set()
    out: set[tuple[int, int, int]] = set()
    for p in dt.partitions():  # list of {col: str_value}
        try:
            out.add((int(p["season"]), int(p["sport_id"]), int(p["month"])))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def write_partition(table: str, df: pd.DataFrame, season: int, sport_id: int, month: int) -> int:
    """Idempotently write ONE (season, sport_id, month) partition (overwrite predicate
    pins all three cols → O(one month), re-runnable). schema_mode='merge' makes an
    additive column change a metadata commit, not a rebuild."""
    from deltalake import write_deltalake
    df = df.copy()
    df["season"] = int(season)
    df["sport_id"] = int(sport_id)
    df["month"] = int(month)
    table_arrow = pa.Table.from_pandas(df, preserve_index=False)
    uri = _table_uri(table)
    exists = _delta_table(table) is not None
    kwargs = dict(storage_options=_storage_options())
    if not exists:
        write_deltalake(uri, table_arrow, mode="overwrite",
                        partition_by=PARTITION_COLS, **kwargs)
    else:
        write_deltalake(
            uri, table_arrow, mode="overwrite",
            predicate=f"season = {int(season)} AND sport_id = {int(sport_id)} AND month = {int(month)}",
            schema_mode="merge", **kwargs,
        )
    return len(df)


# ── Month iteration ─────────────────────────────────────────────────────────────

def iter_months(start: tuple[int, int], end: tuple[int, int]):
    """Yield (year, month) from start to end inclusive."""
    y, m = start
    ey, em = end
    while (y, m) <= (ey, em):
        yield y, m
        m += 1
        if m > 12:
            m, y = 1, y + 1


# ── Main run ─────────────────────────────────────────────────────────────────────

def run(
    seasons: list[int],
    sport_ids: list[int],
    start_month: tuple[int, int] | None,
    end_month: tuple[int, int] | None,
    force: bool,
    dry_run: bool,
    max_games: int | None,
    current_month: tuple[int, int],
) -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": "credence-milb-ingest/1.0 (research)"})

    sched_done = set() if (force or dry_run) else existing_partitions(SCHEDULE_TABLE)
    logs_done = set() if (force or dry_run) else existing_partitions(LOGS_TABLE)
    people_cache: dict[int, dict] = {}

    fire_ts = datetime.now(timezone.utc).isoformat()
    grand_games = grand_log_rows = grand_sched_rows = 0

    for season in seasons:
        # month window for this season. Default = the MiLB span Mar–Oct. An explicit
        # --start-month/--end-month applies to the season it names; for other seasons
        # in a multi-season backfill the default span is used (so '2005-2026' just
        # sweeps Mar–Oct of every season without a per-season flag).
        start_mo = start_month[1] if (start_month and start_month[0] == season) else 3
        end_mo = end_month[1] if (end_month and end_month[0] == season) else 10

        for sport_id in sport_ids:
            for (yr, mo) in iter_months((season, start_mo), (season, end_mo)):
                part = (season, sport_id, mo)
                is_current = (yr, mo) == current_month
                already = part in sched_done and part in logs_done
                if already and not is_current and not force:
                    log.info("[%d %s %04d-%02d] partition present — SKIP (idempotent)",
                             season, sport_label(sport_id), yr, mo)
                    continue

                log.info("[%d %s %04d-%02d] fetching schedule…",
                         season, sport_label(sport_id), yr, mo)
                try:
                    sched_rows = fetch_schedule_month(session, sport_id, yr, mo)
                except Exception as exc:  # noqa: BLE001
                    log.warning("  schedule fetch failed: %s — skipping month", exc)
                    continue

                played = [r for r in sched_rows if r.get("status_abstract") == "Final"]
                log.info("  %d game(s), %d final", len(sched_rows), len(played))
                if max_games is not None:
                    played = played[:max_games]

                # per-player logs from each final game's boxscore
                log_rows: list[dict] = []
                need_people: set[int] = set()
                boxes: list[tuple[dict, dict]] = []
                for gi, srow in enumerate(played, 1):
                    gpk = srow["game_pk"]
                    if dry_run:
                        log.info("    [%d/%d] (dry-run) game_pk=%s", gi, len(played), gpk)
                        continue
                    try:
                        box = fetch_boxscore(session, gpk)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("    game_pk=%s box fetch failed: %s — skip", gpk, exc)
                        continue
                    boxes.append((box, srow))
                    for s in ("home", "away"):
                        for pl in (box.get("teams", {}).get(s, {}).get("players", {}) or {}).values():
                            pid = _int((pl.get("person") or {}).get("id"))
                            if pid is not None and pid not in people_cache:
                                need_people.add(pid)
                    time.sleep(REQUEST_DELAY)

                if not dry_run and need_people:
                    log.info("    fetching %d new player bios…", len(need_people))
                    people_cache.update(fetch_people(session, sorted(need_people)))

                for box, srow in boxes:
                    log_rows.extend(flatten_boxscore(box, srow, people_cache, fire_ts))

                grand_games += len(boxes)
                if dry_run:
                    grand_sched_rows += len(sched_rows)
                    continue

                # write both partitions (schedule always; logs when non-empty)
                if sched_rows:
                    n = write_partition(SCHEDULE_TABLE, pd.DataFrame(sched_rows), season, sport_id, mo)
                    grand_sched_rows += n
                    log.info("  → wrote %d schedule row(s)", n)
                if log_rows:
                    n = write_partition(LOGS_TABLE, pd.DataFrame(log_rows), season, sport_id, mo)
                    grand_log_rows += n
                    log.info("  → wrote %d player-game-log row(s)", n)

    log.info(
        "DONE — %d game(s) boxscored | %d schedule row(s) | %d player-game-log row(s)%s",
        grand_games, grand_sched_rows, grand_log_rows,
        "  [DRY-RUN — no writes]" if dry_run else "",
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_seasons(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(s) for s in spec.split(",") if s.strip()]


def _parse_month(spec: str | None) -> tuple[int, int] | None:
    if not spec:
        return None
    y, m = spec.split("-")
    return int(y), int(m)


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest MiLB schedule + boxscores → S3 Delta lakehouse.")
    ap.add_argument("--seasons", default=None,
                    help="Season(s): '2024', '2005,2006', or a range '2005-2026'. "
                         f"Backfill floor is {EARLIEST_SEASON} (API returns nothing earlier).")
    ap.add_argument("--sport-ids", default=None,
                    help="Comma list of minor sportIds (default all: 11,12,13,14).")
    ap.add_argument("--start-month", default=None, metavar="YYYY-MM",
                    help="First month (default: March of each season).")
    ap.add_argument("--end-month", default=None, metavar="YYYY-MM",
                    help="Last month (default: October of each season).")
    ap.add_argument("--incremental", action="store_true",
                    help="Current season, all levels, current + prior month (the daily op). "
                         "Always re-pulls (absorbs late box updates).")
    ap.add_argument("--force", action="store_true",
                    help="Re-pull + overwrite even partitions already present.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Fetch schedules + list gamePks; make NO boxscore fetches beyond "
                         "listing and NO S3 writes.")
    ap.add_argument("--max-games", type=int, default=None,
                    help="Cap boxscore fetches per month (a verification stub).")
    args = ap.parse_args()

    today = date.today()
    current_month = (today.year, today.month)

    if args.incremental:
        # Daily refresh: re-pull the CURRENT month every day (force → the month partition
        # is rewritten, so a game that went Final overnight + any late box revision are
        # absorbed). Extend to the PRIOR month only in the first 3 days of a month — that
        # is the only window where yesterday's finals can still land in last month's
        # partition. Kept WITHIN today.year so run()'s per-season month window (which pins
        # start/end to the season) stays valid; off-season months just fetch 0 games (cheap).
        include_prior = today.day <= 3 and today.month > 1
        seasons = [today.year]
        sport_ids = list(INGESTIBLE_SPORT_IDS)
        start_month = (today.year, today.month - 1) if include_prior else current_month
        end_month = current_month
        force = True  # incremental always re-pulls (absorbs late finals/revisions)
    else:
        if not args.seasons:
            ap.error("--seasons is required unless --incremental")
        seasons = [s for s in _parse_seasons(args.seasons) if s >= EARLIEST_SEASON]
        dropped = [s for s in _parse_seasons(args.seasons) if s < EARLIEST_SEASON]
        if dropped:
            log.warning("Seasons < %d dropped (API returns no MiLB games): %s",
                        EARLIEST_SEASON, dropped)
        if not seasons:
            ap.error(f"No seasons >= {EARLIEST_SEASON} to ingest.")
        sport_ids = [int(s) for s in args.sport_ids.split(",")] if args.sport_ids else list(INGESTIBLE_SPORT_IDS)
        start_month = _parse_month(args.start_month)
        end_month = _parse_month(args.end_month)
        force = args.force

    bad = [s for s in sport_ids if s not in INGESTIBLE_SPORT_IDS]
    if bad:
        ap.error(f"Unknown sportId(s) {bad}; valid minor sportIds: {sorted(INGESTIBLE_SPORT_IDS)}")

    log.info(
        "MiLB ingest — seasons=%s sport_ids=%s months=%s..%s force=%s dry_run=%s max_games=%s",
        seasons, sport_ids, args.start_month or "Mar", args.end_month or "Oct",
        force, args.dry_run, args.max_games,
    )
    run(seasons, sport_ids, start_month, end_month, force, args.dry_run, args.max_games, current_month)


if __name__ == "__main__":
    main()
