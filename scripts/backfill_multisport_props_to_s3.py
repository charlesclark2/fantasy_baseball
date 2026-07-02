"""
backfill_multisport_props_to_s3.py
───────────────────────────────────
Historical player-prop odds backfill for MLB, NFL, NCAAF, and NCAAB.
Writes Hive-partitioned Parquet directly to S3.  Zero Snowflake writes.

WHY THIS EXISTS
Player props require a two-step approach on The Odds API's historical API.
The main historical odds endpoint (/v4/historical/sports/{sport}/odds) only
supports featured markets (h2h, spreads, totals) and returns INVALID_MARKET for
any player prop key.  Historical player props are served on the event-level
endpoint:
    Step 1: GET /v4/historical/sports/{sport}/events
            → returns event IDs for a game date  (1 credit/date)
    Step 2: GET /v4/historical/sports/{sport}/events/{eventId}/odds
            → returns player-prop odds for one game  (10 × markets × regions cr/event)

Historical prop data has been archived since 2023-05-03T05:30:00Z.

S3 LAYOUT
    s3://baseball-betting-ml-artifacts/
        {sport_label}/props/market={market_key}/season={season}/date={game_date}/data.parquet

One Parquet file per (sport, market_key, season, calendar_date).
Each row = one (event × snapshot_ts × bookmaker × player).

CREDIT BUDGET (as of 2026-06-30 — pre-7/1 reset; verify live with GET /v4/sports)
    Live balance      : ~544,000 credits, EXPIRING at the 7/1 reset
    Post-reset         : refreshes to ~5M, good to ~7/17 (then drops to 100k/mo)
    Strategy          : run ACROSS the reset — spend the expiring ~544k on the
                        top-value MLB player props (batter_runs_scored, batter_rbis),
                        then auto-continue on the fresh 5M (idempotent skip).
    Value rank        : batter_runs_scored+batter_rbis → batter_hits_runs_rbis →
                        spreads (2026 catch-up) → F5/period set (2026 catch-up).
    Idempotency       : existing (market,season,date) partitions auto-skip, so a
                        stalled-at-2025-08-11 market grabs only the 2025-08-12+ gap.

IDEMPOTENCY
A (market_key, season, date) partition that already exists in S3 is skipped on
re-run.  The Parquet file IS the checkpoint — no external state required.

USAGE
    # PHASE 0 — Probe first (mandatory, confirms availability + projects cost):
    uv run scripts/backfill_multisport_props_to_s3.py --mode probe

    # Probe a single sport:
    uv run scripts/backfill_multisport_props_to_s3.py --mode probe --sport baseball_mlb

    # Dry-run (no API calls, shows credit estimate from rough game counts):
    uv run scripts/backfill_multisport_props_to_s3.py --mode backfill --dry-run

    # Full backfill (long-running — hand to operator):
    uv run scripts/backfill_multisport_props_to_s3.py --mode backfill

    # One sport only:
    uv run scripts/backfill_multisport_props_to_s3.py --mode backfill --sport baseball_mlb

    # Resume (idempotent — existing partitions auto-skipped):
    uv run scripts/backfill_multisport_props_to_s3.py --mode backfill --sport baseball_mlb

    # Validate after run (DuckDB):
    duckdb -c "
      SELECT sport, market_key, season, COUNT(DISTINCT date) dates, COUNT(*) rows
      FROM read_parquet('s3://baseball-betting-ml-artifacts/*/props/**/*.parquet')
      GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"

ENVIRONMENT (.env)
    ODDS_API_KEY, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
"""

import argparse
import io
import logging
import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
BUCKET            = "baseball-betting-ml-artifacts"
AWS_REGION        = "us-east-2"
REQUEST_DELAY     = 1.0  # seconds between API calls

# 2026-06-30: current cycle = ~544k expiring at the 7/1 reset, then refreshes to
# ~5M (good to ~7/17). The intended grab runs ACROSS the reset (use the expiring
# ~544k, then auto-continue on the fresh 5M via idempotency), so this per-session
# ceiling is deliberately left ABOVE 544k — it must not stop a market mid-run at
# the reset boundary. The Odds API itself hard-stops at 0; the 5M post-reset is the
# real headroom. (Verify the live balance with GET /v4/sports before each run.)
CREDIT_SURPLUS    = 888_000    # per-session soft ceiling (NOT the live balance)
CREDIT_RESERVE    = 88_000    # ~10% hold-back; stop well before 0
CREDIT_AVAILABLE  = CREDIT_SURPLUS - CREDIT_RESERVE  # 800,000

# Historical prop data floor (per Odds API docs)
PROP_FLOOR = date(2023, 5, 3)

_today = date.today()

# ── Sports configuration ────────────────────────────────────────────────────────
# Value-ranked; backfill runs in this order and stops when budget runs low.

SPORTS_CONFIG: dict[str, dict] = {
    "baseball_mlb": {
        "label"   : "mlb",
        "display" : "MLB",
        "markets" : [
            # Player props — kept fresh forward by the daily --player-props-only cron
            # (E5.1b: batter_runs_scored/rbis/hits_runs_rbis added 2026-06-30; the
            # historical backfill + the daily catch-up share this one canonical list).
            "pitcher_strikeouts",
            "pitcher_outs",
            "batter_total_bases",
            "batter_hits",
            "batter_home_runs",
            "batter_runs_scored",
            "batter_rbis",
            "batter_hits_runs_rbis",
            # Tier 1 — highest edge-lane value (F5 + NRFI)
            "h2h_1st_5_innings",
            "totals_1st_5_innings",
            "totals_1st_1_innings",
            "alternate_totals_1st_5_innings",
            # Tier 2 — F1/F3/F7 derivatives + F5 run-line
            "h2h_1st_1_innings",
            "h2h_1st_3_innings",
            "totals_1st_3_innings",
            "h2h_1st_7_innings",
            "totals_1st_7_innings",
            "spreads_1st_5_innings",
            "alternate_spreads_1st_5_innings",
            # Tier 3 — full-game derivatives (confirmed gaps in S3)
            "alternate_team_totals",
            "alternate_spreads",
            "spreads",
        ],
        # Season label = calendar year (MLB season is within one calendar year).
        # 2023 start = Odds API prop floor; probe may confirm earlier.
        "season_ranges": {
            2023: (date(2023,  5,  3), date(2023, 11,  4)),
            2024: (date(2024,  3, 20), date(2024, 11,  2)),
            2025: (date(2025,  3, 27), date(2025, 11,  5)),
            2026: (date(2026,  3, 26), _today - timedelta(days=1)),
        },
        # Two snapshots: noon ET (afternoon games) + 6:30 pm ET (prime-time games)
        "snapshots"   : ["17:00", "23:30"],
        "probe_date"  : date(2024, 6, 12),
        "probe_season": 2024,
        # Estimated total games WITH prop coverage across all configured seasons.
        # Used for dry-run cost estimates only; probe gives the real number.
        # MLB: ~2,430 games/season × 4 seasons × ~75% prop coverage ≈ 7,300
        "_est_total_events": 7_300,
    },
    "americanfootball_nfl": {
        "label"   : "nfl",
        "display" : "NFL",
        "markets" : [
            # Player props (already backfilled)
            "player_pass_yds",
            "player_rush_yds",
            "player_reception_yds",
            "player_receptions",
            "player_anytime_td",
            "player_pass_yds_alternate",
            "player_rush_yds_alternate",
            "player_reception_yds_alternate",
            "player_receptions_alternate",
            # Tier 1 — 1st-half game markets
            "h2h_h1",
            "spreads_h1",
            "totals_h1",
            # Tier 2 — 1st quarter + team totals + alts
            "h2h_q1",
            "spreads_q1",
            "totals_q1",
            "team_totals",
            "team_totals_h1",
            "alternate_spreads",
            "alternate_totals",
            "alternate_spreads_h1",
            "alternate_totals_h1",
            # Tier 3 — 2nd half + remaining quarters + alt team totals
            "h2h_h2",
            "spreads_h2",
            "totals_h2",
            "h2h_q2",
            "spreads_q2",
            "totals_q2",
            "h2h_q3",
            "spreads_q3",
            "totals_q3",
            "h2h_q4",
            "spreads_q4",
            "totals_q4",
            "alternate_team_totals",
        ],
        # Season label = year the season starts (NFL season spans two calendar years).
        "season_ranges": {
            2023: (date(2023,  9,  7), date(2024,  2, 11)),  # Super Bowl LVIII
            2024: (date(2024,  9,  5), date(2025,  2,  9)),
            2025: (date(2025,  9,  4), date(2026,  2,  8)),  # estimate
        },
        "snapshots"   : ["17:00", "23:30"],
        "probe_date"  : date(2024,  1, 14),  # 2023-season divisional playoffs
        "probe_season": 2023,
        # NFL: ~285 games/season × 3 seasons × ~90% prop coverage ≈ 770
        "_est_total_events": 770,
    },
    "americanfootball_ncaaf": {
        "label"   : "ncaaf",
        "display" : "NCAAF",
        "markets" : [
            # Player props (already backfilled)
            "player_pass_yds",
            "player_rush_yds",
            "player_reception_yds",
            "player_pass_yds_alternate",
            "player_rush_yds_alternate",
            "player_reception_yds_alternate",
            # Tier 1 — 1st-half game markets
            "h2h_h1",
            "spreads_h1",
            "totals_h1",
            # Tier 2 — 1st quarter + team totals + alts
            "h2h_q1",
            "spreads_q1",
            "totals_q1",
            "team_totals",
            "team_totals_h1",
            "alternate_spreads",
            "alternate_totals",
            "alternate_spreads_h1",
            "alternate_totals_h1",
            # Tier 3 — 2nd half + remaining quarters + alt team totals
            "h2h_h2",
            "spreads_h2",
            "totals_h2",
            "h2h_q2",
            "spreads_q2",
            "totals_q2",
            "h2h_q3",
            "spreads_q3",
            "totals_q3",
            "h2h_q4",
            "spreads_q4",
            "totals_q4",
            "alternate_team_totals",
        ],
        "season_ranges": {
            2023: (date(2023,  8, 26), date(2024,  1, 22)),  # through CFP championship
            2024: (date(2024,  8, 24), date(2025,  1, 20)),
            2025: (date(2025,  8, 23), date(2026,  1, 19)),  # estimate
        },
        "snapshots"   : ["17:00", "23:30"],
        "probe_date"  : date(2024,  1,  8),  # CFP Championship (2023 season)
        "probe_season": 2023,
        # NCAAF: ~800 games/season in API coverage × 3 seasons × ~60% prop coverage ≈ 1,440
        "_est_total_events": 1_440,
    },
    "basketball_ncaab": {
        "label"   : "ncaab",
        "display" : "NCAAB",
        "markets" : [
            # Player props (already backfilled)
            "player_points",
            "player_rebounds",
            "player_assists",
            "player_points_alternate",
            "player_rebounds_alternate",
            "player_assists_alternate",
            # Tier 1 — 1st-half game markets
            "h2h_h1",
            "spreads_h1",
            "totals_h1",
            # Tier 2 — 2nd half + team totals + alts (halves only; no q1-q4 for NCAAB)
            "h2h_h2",
            "spreads_h2",
            "totals_h2",
            "team_totals",
            "team_totals_h1",
            "alternate_spreads",
            "alternate_totals",
            "alternate_spreads_h1",
            "alternate_totals_h1",
            # Tier 3 — alt team totals + 2nd-half alts
            "alternate_team_totals",
            "alternate_spreads_h2",
            "alternate_totals_h2",
        ],
        # Season label = calendar year the season STARTS in November.
        "season_ranges": {
            2023: (date(2023, 11,  6), date(2024,  4,  8)),
            2024: (date(2024, 11,  4), date(2025,  4,  7)),
            2025: (date(2025, 11,  3), _today - timedelta(days=1)),
        },
        # Single snapshot only; NCAAB has many games/day but major-conference prop
        # coverage is a fraction of total games → single snapshot to control cost.
        "snapshots"   : ["17:00"],
        "probe_date"  : date(2024,  4,  6),  # Final Four Saturday (UConn/NC State/Alabama/Purdue)
        "probe_season": 2024,
        # NCAAB: ~1,500 games/season with prop coverage × 3 seasons ≈ 4,500.
        # ⚠ This is the most uncertain estimate; the probe is authoritative here.
        "_est_total_events": 4_500,
    },
}

# Value-ranked allocation order — script processes sports in this order and
# stops when the budget (CREDIT_AVAILABLE) is exhausted.
VALUE_RANK = [
    "baseball_mlb",
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "basketball_ncaab",
]

# ── PyArrow schema ─────────────────────────────────────────────────────────────

PARQUET_SCHEMA = pa.schema([
    pa.field("sport",          pa.string()),
    pa.field("season",         pa.int32()),
    pa.field("event_id",       pa.string()),
    pa.field("commence_time",  pa.string()),
    pa.field("home_team",      pa.string()),
    pa.field("away_team",      pa.string()),
    pa.field("snapshot_ts",    pa.string()),
    pa.field("bookmaker_key",  pa.string()),
    pa.field("market_key",     pa.string()),
    pa.field("player_name",    pa.string()),
    pa.field("line",           pa.float64()),
    pa.field("over_price",     pa.float64()),
    pa.field("under_price",    pa.float64()),
    pa.field("load_id",        pa.string()),
    pa.field("ingested_at",    pa.string()),
])

# ── Helpers ─────────────────────────────────────────────────────────────────────

def _snap_ts(game_date: date, hhmm: str) -> str:
    """'2024-06-12' + '17:00' → '2024-06-12T17:00:00Z'"""
    h, m = hhmm.split(":")
    return f"{game_date}T{h}:{m}:00Z"


def _date_range(start: date, end: date) -> list[date]:
    dates, d = [], start
    while d <= end:
        dates.append(d)
        d += timedelta(days=1)
    return dates


def _season_for_date(sport: str, d: date) -> int | None:
    """Return the season label for a date, or None if outside all ranges."""
    for season, (start, end) in SPORTS_CONFIG[sport]["season_ranges"].items():
        if start <= d <= end:
            return season
    return None


def _credits_per_event(markets: list[str], regions: list[str]) -> int:
    """Standard formula: 10 × #markets × #regions."""
    return 10 * len(markets) * len(regions)


# Player-prop market keys all carry one of these prefixes (batter_*/pitcher_*/
# player_*); the period/derivative/spread keys do not. The daily forward cron
# uses --player-props-only to capture JUST these from a sport's canonical list,
# so the prop surface stays fresh without re-buying the (separately-captured)
# game-level derivatives. Adding a prop to a sport's `markets` auto-includes it.
_PLAYER_PROP_PREFIXES = ("batter_", "pitcher_", "player_")


def _filter_player_props(markets: list[str]) -> list[str]:
    """Keep only player-prop keys (batter_*/pitcher_*/player_*), order preserved."""
    return [m for m in markets if m.startswith(_PLAYER_PROP_PREFIXES)]


# ── API helpers ────────────────────────────────────────────────────────────────

_RETRY_DELAYS = [5, 15, 45]  # seconds between retries (3 attempts total)


def _fetch_with_retry(url: str, params: dict, timeout: int) -> requests.Response:
    """requests.get with retry on Timeout/ConnectionError. Raises on final failure."""
    last_exc: Exception | None = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            log.warning("Network error (attempt %d/%d) — retrying in %ds …",
                        attempt, len(_RETRY_DELAYS) + 1, delay)
            time.sleep(delay)
        try:
            return requests.get(url, params=params, timeout=timeout)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_exc = exc
    raise last_exc  # type: ignore[misc]


# ── API calls ──────────────────────────────────────────────────────────────────

def fetch_historical_events(
    sport: str,
    game_date: date,
    snapshot: str,
    api_key: str,
) -> tuple[list[dict], int]:
    """
    GET /v4/historical/sports/{sport}/events

    Returns (events_list, credits_remaining).  Cost: 1 credit.
    The commence window covers 00:00Z → next-day 07:00Z to capture
    late Pacific games.
    """
    url = f"{ODDS_API_BASE_URL}/historical/sports/{sport}/events"
    params = {
        "apiKey"           : api_key,
        "date"             : _snap_ts(game_date, snapshot),
        "commenceTimeFrom" : f"{game_date}T00:00:00Z",
        "commenceTimeTo"   : f"{game_date + timedelta(days=1)}T07:00:00Z",
    }
    resp = _fetch_with_retry(url, params=params, timeout=20)
    resp.raise_for_status()
    remaining = resp.headers.get("x-requests-remaining", "?")
    data = resp.json()
    events = data.get("data", [])
    try:
        remaining_int = int(remaining)
    except (ValueError, TypeError):
        remaining_int = -1
    return events, remaining_int


def fetch_event_props(
    sport: str,
    event_id: str,
    snap_ts: str,
    markets: list[str],
    regions: list[str],
    api_key: str,
) -> tuple[dict | None, int]:
    """
    GET /v4/historical/sports/{sport}/events/{eventId}/odds

    Returns (event_dict_or_None, credits_remaining).
    Cost: 10 × len(markets) × len(regions) credits.
    Returns None on 404 (event not found at this timestamp).
    """
    url = f"{ODDS_API_BASE_URL}/historical/sports/{sport}/events/{event_id}/odds"
    params = {
        "apiKey"     : api_key,
        "date"       : snap_ts,
        "markets"    : ",".join(markets),
        "regions"    : ",".join(regions),
        "oddsFormat" : "american",
    }
    try:
        resp = _fetch_with_retry(url, params=params, timeout=30)
        remaining = resp.headers.get("x-requests-remaining", "?")
        try:
            remaining_int = int(remaining)
        except (ValueError, TypeError):
            remaining_int = -1
        if resp.status_code == 404:
            return None, remaining_int
        resp.raise_for_status()
        data = resp.json()
        # The historical event-odds endpoint wraps its response in {"data": {...}}
        event = data.get("data") or data
        if isinstance(event, list):
            event = event[0] if event else None
        return event, remaining_int
    except (requests.exceptions.HTTPError,
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError) as exc:
        log.warning("Fetch error for event %s snap %s (all retries exhausted): %s",
                    event_id, snap_ts, exc)
        return None, -1


# ── Live (current-lines) API calls — the intraday /props feed (E5.5) ─────────────
# The historical endpoint only serves ARCHIVED snapshots (yesterday and earlier). The
# LIVE per-event endpoint serves the CURRENT lines for UPCOMING games, so the Player
# Props page can refresh intraday on the same cadence as the other odds crons. Same
# two-step shape as the historical path, minus the `date` snapshot param. (Mirrors
# derivative_odds_backfill.fetch_live_event_derivative_odds.)

def fetch_live_events(
    sport: str,
    game_date: date,
    api_key: str,
) -> tuple[list[dict], int]:
    """GET /v4/sports/{sport}/events (LIVE) for games commencing on game_date.

    Returns (events_list, credits_remaining).  Cost: 1 credit.  Server-side filtered
    to the day's commence window (00:00Z → next-day 07:00Z, to catch late Pacific games).
    """
    url = f"{ODDS_API_BASE_URL}/sports/{sport}/events"
    params = {
        "apiKey"           : api_key,
        "commenceTimeFrom" : f"{game_date}T00:00:00Z",
        "commenceTimeTo"   : f"{game_date + timedelta(days=1)}T07:00:00Z",
        "dateFormat"       : "iso",
    }
    resp = _fetch_with_retry(url, params=params, timeout=20)
    resp.raise_for_status()
    remaining = resp.headers.get("x-requests-remaining", "?")
    data = resp.json()
    events = data if isinstance(data, list) else data.get("data", [])
    try:
        remaining_int = int(remaining)
    except (ValueError, TypeError):
        remaining_int = -1
    return events, remaining_int


def fetch_live_event_props(
    sport: str,
    event_id: str,
    markets: list[str],
    regions: list[str],
    api_key: str,
) -> tuple[dict | None, int]:
    """GET /v4/sports/{sport}/events/{eventId}/odds (LIVE — no date param → CURRENT lines).

    Returns (event_dict_or_None, credits_remaining).  Cost: 10 × markets × regions.
    Returns None on 404 (event not found) / 422 (no data for these markets).
    """
    url = f"{ODDS_API_BASE_URL}/sports/{sport}/events/{event_id}/odds"
    params = {
        "apiKey"     : api_key,
        "markets"    : ",".join(markets),
        "regions"    : ",".join(regions),
        "oddsFormat" : "american",
    }
    try:
        resp = _fetch_with_retry(url, params=params, timeout=30)
        remaining = resp.headers.get("x-requests-remaining", "?")
        try:
            remaining_int = int(remaining)
        except (ValueError, TypeError):
            remaining_int = -1
        if resp.status_code in (404, 422):
            return None, remaining_int
        resp.raise_for_status()
        data = resp.json()
        event = data.get("data") or data
        if isinstance(event, list):
            event = event[0] if event else None
        return event, remaining_int
    except (requests.exceptions.HTTPError,
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError) as exc:
        log.warning("Live fetch error for event %s (all retries exhausted): %s", event_id, exc)
        return None, -1


# ── Row extraction ─────────────────────────────────────────────────────────────

def _pivot_prop_outcomes(outcomes: list[dict]) -> dict[str, dict]:
    """Pivot outcomes → {player_name: {line, over_price, under_price}}.

    Player props: description=player name, name=Over/Under, point=line.
    Game markets (h2h, spreads): no description, name=team/side, price=moneyline.
    For game markets, price is stored in over_price; under_price is left None.
    """
    players: dict[str, dict] = {}
    for o in outcomes:
        side   = (o.get("name") or "").strip()
        player = (o.get("description") or side).strip()
        if not player:
            continue
        if player not in players:
            players[player] = {"line": None, "over_price": None, "under_price": None}
        if (line := o.get("point")) is not None:
            players[player]["line"] = float(line)
        side_lower = side.lower()
        if side_lower == "over":
            players[player]["over_price"] = o.get("price")
        elif side_lower == "under":
            players[player]["under_price"] = o.get("price")
        else:
            # Game market: name is team/side label; store moneyline in over_price
            players[player]["over_price"] = o.get("price")
    return players


def event_to_rows(
    event: dict,
    season: int,
    snap_ts: str,
    load_id: str,
    ingested_at: str,
) -> dict[str, list[dict]]:
    """
    Convert a single event's prop-odds response into rows keyed by market.

    Returns {market_key: [row, ...]}.
    Row schema: sport, season, event_id, commence_time, home_team, away_team,
    snapshot_ts, bookmaker_key, market_key, player_name, line, over_price,
    under_price, load_id, ingested_at.
    """
    if not event:
        return {}

    sport_key      = event.get("sport_key", "")
    event_id       = event.get("id", "")
    commence_time  = event.get("commence_time", "")
    home_team      = event.get("home_team", "")
    away_team      = event.get("away_team", "")

    rows_by_market: dict[str, list[dict]] = {}

    for bm in event.get("bookmakers", []):
        bm_key = bm.get("key", "")
        for mkt in bm.get("markets", []):
            mkt_key = mkt.get("key", "")
            players = _pivot_prop_outcomes(mkt.get("outcomes", []))
            for player_name, odds in players.items():
                row = {
                    "sport"         : sport_key,
                    "season"        : season,
                    "event_id"      : event_id,
                    "commence_time" : commence_time,
                    "home_team"     : home_team,
                    "away_team"     : away_team,
                    "snapshot_ts"   : snap_ts,
                    "bookmaker_key" : bm_key,
                    "market_key"    : mkt_key,
                    "player_name"   : player_name,
                    "line"          : odds["line"],
                    "over_price"    : odds["over_price"],
                    "under_price"   : odds["under_price"],
                    "load_id"       : load_id,
                    "ingested_at"   : ingested_at,
                }
                rows_by_market.setdefault(mkt_key, []).append(row)

    return rows_by_market


# ── S3 helpers ─────────────────────────────────────────────────────────────────

def s3_key(sport_label: str, market_key: str, season: int, game_date: date) -> str:
    return (
        f"{sport_label}/props/market={market_key}/season={season}"
        f"/date={game_date}/data.parquet"
    )


def write_to_s3(
    rows: list[dict],
    key: str,
    s3_client,
    bucket: str,
) -> None:
    df = pd.DataFrame(rows)
    df["season"] = df["season"].astype("int32")
    for col in ("line", "over_price", "under_price"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    table = pa.Table.from_pandas(df, schema=PARQUET_SCHEMA, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)
    s3_client.put_object(Bucket=bucket, Key=key, Body=buf.read())
    log.info("  S3 ← s3://%s/%s  (%d rows)", bucket, key, len(rows))


def scan_existing_s3_partitions(
    sport_label: str,
    markets: list[str],
    s3_client,
    bucket: str,
) -> set[tuple[str, int, date]]:
    """Return set of (market_key, season, date) that already exist in S3."""
    prefix = f"{sport_label}/props/"
    existing: set[tuple[str, int, date]] = set()
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith("data.parquet"):
                continue
            parts = key.split("/")
            # expected: {label}/props/market={m}/season={s}/date={d}/data.parquet
            if len(parts) < 6:
                continue
            try:
                mkt = parts[2].split("=", 1)[1]
                ssn = int(parts[3].split("=", 1)[1])
                gd  = date.fromisoformat(parts[4].split("=", 1)[1])
                existing.add((mkt, ssn, gd))
            except (IndexError, ValueError):
                continue
    return existing


# ── Probe mode ─────────────────────────────────────────────────────────────────

def run_probe(
    sports: list[str],
    regions: list[str],
    api_key: str,
    sleep_secs: float,
    markets_override: list[str] | None = None,
    player_props_only: bool = False,
) -> None:
    print()
    print("══ MULTI-SPORT PLAYER PROPS — PHASE 0 PROBE ════════════════════════════════")
    print("  Endpoint: /v4/historical/sports/{sport}/events/{eventId}/odds")
    print("  (Player props require the two-step events endpoint, not /sports/{sport}/odds.)")
    print()

    total_projected = 0

    for sport in sports:
        cfg = SPORTS_CONFIG[sport]
        probe_date   = cfg["probe_date"]
        markets      = markets_override if markets_override else cfg["markets"]
        if player_props_only:
            markets = _filter_player_props(markets)
        snapshots    = cfg["snapshots"]
        snap         = snapshots[0]
        snap_ts_str  = _snap_ts(probe_date, snap)
        cr_per_event = _credits_per_event(markets, regions)

        print(f"── {cfg['display']} ({sport}) {'─' * (50 - len(cfg['display']) - len(sport))}")
        print(f"   Date={probe_date}  snapshot={snap}  markets={len(markets)}  "
              f"regions={','.join(regions)}  cr/event≈{cr_per_event}")
        print()

        # Step 1: get event IDs for probe date (1 credit)
        print("   Step 1 — fetch event list (~1 credit) ...")
        try:
            events, remaining = fetch_historical_events(sport, probe_date, snap, api_key)
        except requests.exceptions.RequestException as exc:
            print(f"   ✗  Events fetch FAILED: {exc}")
            print()
            time.sleep(sleep_secs)
            continue

        n_events = len(events)
        print(f"   → {n_events} events found  credits_remaining={remaining}")

        if not events:
            print(f"   ✗  No events on {probe_date} for {cfg['display']}.")
            print("      Try a different probe_date — this date may have no games.")
            print()
            time.sleep(sleep_secs)
            continue

        # Step 2: fetch props for first event (cr_per_event credits)
        event0   = events[0]
        event_id = event0.get("id", "")
        home     = event0.get("home_team", "?")
        away     = event0.get("away_team", "?")
        rem_before = remaining

        print(f"   Step 2 — fetch props for {away} @ {home}  (expected ~{cr_per_event} cr) ...")
        time.sleep(sleep_secs)
        event_data, remaining_after = fetch_event_props(
            sport, event_id, snap_ts_str, markets, regions, api_key
        )

        if rem_before >= 0 and remaining_after >= 0:
            actual_cost = rem_before - remaining_after
            print(f"   → credits consumed: {actual_cost}  "
                  f"(expected {cr_per_event})  credits_remaining={remaining_after}")
        else:
            actual_cost = cr_per_event
            print(f"   → credits_remaining={remaining_after}  "
                  f"(using expected cost {cr_per_event})")

        if not event_data or not event_data.get("bookmakers"):
            print("   ✗  No bookmaker prop data returned.")
            print("      Props may not yet be archived for this date/sport.")
            print()
            time.sleep(sleep_secs)
            continue

        # Enumerate available market keys in the response
        market_keys_seen: set[str] = set()
        bm_count = 0
        for bm in event_data.get("bookmakers", []):
            bm_count += 1
            for mkt in bm.get("markets", []):
                market_keys_seen.add(mkt.get("key", ""))

        print(f"   ✓  AVAILABLE — {bm_count} bookmakers")
        print(f"      Markets returned: {sorted(market_keys_seen)}")
        print()

        # Cost projection
        total_game_days = sum(
            (end - start).days + 1
            for start, end in cfg["season_ranges"].values()
        )
        est_events_per_day = n_events  # probe day as representative sample
        # Prop coverage isn't guaranteed for every event (lower-tier books vary)
        prop_fraction = 0.75
        est_events_total = int(total_game_days * est_events_per_day * prop_fraction)
        est_credits = est_events_total * len(snapshots) * actual_cost

        print(f"   Cost projection:")
        print(f"     game-days across all seasons : {total_game_days:,}")
        print(f"     events/day (probe day)        : {est_events_per_day}")
        print(f"     prop coverage estimate        : {prop_fraction:.0%}")
        print(f"     snapshots/day                 : {len(snapshots)}")
        print(f"     credits/event                 : {actual_cost}")
        print(f"     ESTIMATED TOTAL               : ~{est_credits:,} credits")
        total_projected += est_credits
        print()

        time.sleep(sleep_secs)

    # Summary
    print("═" * 79)
    print(f"Total projected credits (all probed sports) : ~{total_projected:,}")
    print(f"Available budget                             : ~{CREDIT_AVAILABLE:,}")
    if total_projected <= CREDIT_AVAILABLE:
        print(f"  ✓ GO — fits within budget.")
    else:
        print(f"  ⚠  May exceed budget — consider narrowing markets, regions, or sports.")
    print()
    print("Next step: if projections look reasonable, run:")
    print("    uv run scripts/backfill_multisport_props_to_s3.py --mode backfill")
    print("═" * 79)
    print()


# ── Backfill mode ──────────────────────────────────────────────────────────────

def run_backfill(
    sports: list[str],
    regions: list[str],
    api_key: str,
    s3_client,
    sleep_secs: float,
    limit: int | None,
    force: bool,
    dry_run: bool,
    markets_override: list[str] | None = None,
    player_props_only: bool = False,
) -> None:
    if dry_run:
        print()
        print("══ DRY-RUN CREDIT ESTIMATE ═════════════════════════════════════════════════")
        print("  (Estimates use static game-count tables; probe gives authoritative numbers.)")
        print("  (NFL/NCAAF/NCAAB estimates are especially rough — run --mode probe first.)")
        print()
        total = 0
        for sport in sports:
            cfg        = SPORTS_CONFIG[sport]
            markets    = markets_override if markets_override else cfg["markets"]
            if player_props_only:
                markets = _filter_player_props(markets)
            snapshots  = cfg["snapshots"]
            est_events = cfg["_est_total_events"]
            cr         = _credits_per_event(markets, regions)
            sport_cost = est_events * len(snapshots) * cr
            print(f"  {cfg['display']:6s}  ~{est_events:,} events (est.)  "
                  f"{len(snapshots)} snap(s)  {cr} cr/event  → ~{sport_cost:,} cr")
            total += sport_cost
        print()
        print(f"  TOTAL     ~{total:,} credits")
        print(f"  Available ~{CREDIT_AVAILABLE:,} credits")
        if total <= CREDIT_AVAILABLE:
            print("  ✓ GO (rough estimate)")
        else:
            print("  ⚠  May exceed budget — run --mode probe for accurate numbers.")
        print("═" * 79)
        print()
        return

    ingested_at = datetime.now(timezone.utc).isoformat()
    load_id     = str(uuid.uuid4())
    calls_made  = 0
    credits_est = 0

    for sport in sports:
        cfg      = SPORTS_CONFIG[sport]
        label    = cfg["label"]
        markets  = markets_override if markets_override else cfg["markets"]
        if player_props_only:
            markets = _filter_player_props(markets)
        regions_ = regions
        snaps    = cfg["snapshots"]
        if not markets:
            log.warning("  %s — no markets after --player-props-only filter; skipping.",
                        cfg["display"])
            continue
        cr_per_event = _credits_per_event(markets, regions_)

        log.info("════ %s — scanning existing S3 partitions …", cfg["display"])
        existing = (
            scan_existing_s3_partitions(label, markets, s3_client, BUCKET)
            if not force else set()
        )
        log.info("  %d existing (market, season, date) partitions found", len(existing))

        # Collect all (season, date) pairs that are NOT fully covered
        all_dates: list[tuple[int, date]] = []
        for season, (start, end) in cfg["season_ranges"].items():
            for d in _date_range(start, end):
                # A date is "complete" if ALL markets already exist for it
                all_covered = all(
                    (mkt, season, d) in existing for mkt in markets
                )
                if not all_covered:
                    all_dates.append((season, d))

        if limit:
            all_dates = all_dates[:limit]

        log.info("  %d (season, date) pairs to process", len(all_dates))

        for season, game_date in all_dates:
            # Budget guard
            if CREDIT_AVAILABLE - credits_est < cr_per_event * 50:
                log.warning(
                    "Budget low (~%d est. remaining) — stopping %s.",
                    CREDIT_AVAILABLE - credits_est, cfg["display"],
                )
                break

            snap = snaps[0]  # use first snapshot for events list fetch
            log.info("  %s  season=%d  snap=%s", game_date, season, snap)

            # Step 1: fetch event IDs for this date
            try:
                events, remaining = fetch_historical_events(
                    sport, game_date, snap, api_key
                )
                calls_made += 1
            except requests.exceptions.RequestException as exc:
                log.warning("Events fetch failed for %s %s: %s", sport, game_date, exc)
                time.sleep(sleep_secs)
                continue

            if not events:
                log.info("    no events — skipping")
                time.sleep(sleep_secs)
                continue

            # Step 2: fetch props for all snapshots, accumulate across all
            # snapshots into one dict, then write once per market per date.
            # NOTE: rows_by_market is intentionally OUTSIDE the snapshot loop —
            # initialising it inside caused the second snapshot to overwrite the
            # first S3 write with a smaller row set (games past commence_time
            # are leakage-filtered at the later snapshot, so the surviving file
            # would be missing early-game coverage AND we paid for both pulls).
            rows_by_market: dict[str, list[dict]] = {}

            for snap_hhmm in snaps:
                snap_ts_str = _snap_ts(game_date, snap_hhmm)

                for event in events:
                    event_id      = event.get("id", "")
                    commence_time = event.get("commence_time", "")

                    # Leakage safety: skip events that already started at this snapshot
                    try:
                        ct = datetime.fromisoformat(
                            commence_time.replace("Z", "+00:00")
                        )
                        st = datetime.fromisoformat(snap_ts_str.replace("Z", "+00:00"))
                        if st >= ct:
                            continue  # game already started at this snapshot
                    except (ValueError, AttributeError):
                        pass  # if we can't parse, proceed anyway

                    event_data, remaining = fetch_event_props(
                        sport, event_id, snap_ts_str, markets, regions_, api_key
                    )
                    calls_made += 1
                    credits_est += cr_per_event
                    time.sleep(sleep_secs)

                    if not event_data:
                        continue

                    event_rows = event_to_rows(
                        event_data, season, snap_ts_str, load_id, ingested_at
                    )
                    for mkt_key, rows in event_rows.items():
                        rows_by_market.setdefault(mkt_key, []).extend(rows)

            # Write once after all snapshots — one Parquet per (market, season, date)
            for mkt_key, rows in rows_by_market.items():
                if not rows:
                    continue
                key = s3_key(label, mkt_key, season, game_date)
                write_to_s3(rows, key, s3_client, BUCKET)

            log.info(
                "  done  date=%s  calls_so_far=%d  est_credits_used=%d  api_remaining=%s",
                game_date, calls_made, credits_est, remaining,
            )

    log.info("Backfill complete.  Total calls: %d  Est. credits used: %d",
             calls_made, credits_est)


# ── Live mode ────────────────────────────────────────────────────────────────────

def _live_season_for_date(sport: str, d: date) -> int | None:
    """Season LABEL for a LIVE (today) pull.

    `_season_for_date` caps the CURRENT season's range end at `_today - 1` (a HISTORICAL
    backfill artifact — the historical endpoint has no data for today), so it returns None
    for TODAY, which is exactly the date the live feed targets. Here we resolve the season
    by START (the season a date belongs to), tolerating a date that sits just past the
    capped end, but still bounding to a plausible in-season window (~250 days from start,
    covering a full MLB season) so a genuine OFFSEASON date returns None (→ live no-ops).
    """
    for season, (start, end) in sorted(
        SPORTS_CONFIG[sport]["season_ranges"].items(), reverse=True
    ):
        if start <= d <= max(end, start + timedelta(days=250)):
            return season
    return None


def _us_baseball_day() -> date:
    """Today on the US baseball calendar (America/Los_Angeles), NOT UTC. The box runs
    UTC, so a bare date.today() rolls to UTC-tomorrow in the US evening (INC-22 class) —
    which would make the live pull fetch the wrong slate and write a date=<tomorrow>
    partition the K-projection writer (which reads the US baseball day) never sees. Use
    the canonical helper when available; fall back to UTC date only if it can't import."""
    try:
        from betting_ml.utils.game_day import current_game_date
        return current_game_date()
    except Exception:  # noqa: BLE001 — standalone/local fallback
        return date.today()


def run_live(
    sports: list[str],
    regions: list[str],
    api_key: str,
    s3_client,
    sleep_secs: float,
    markets_override: list[str] | None = None,
    player_props_only: bool = False,
) -> None:
    """Intraday CURRENT-lines pull for today's slate (the Player Props page feed).

    Unlike run_backfill (historical, idempotent, yesterday-and-earlier), this ALWAYS
    re-fetches today's upcoming games from the LIVE endpoint and OVERWRITES the
    date=<today> partition with the latest snapshot — so an hourly cron keeps the served
    prop lines fresh, on par with the h2h/totals odds crons. snapshot_ts = fetch time.
    Off-hours the live events endpoint returns no upcoming games → the run no-ops cheaply.
    """
    ingested_at = datetime.now(timezone.utc).isoformat()
    load_id     = str(uuid.uuid4())
    snap_ts_str = ingested_at  # the live snapshot IS "now"
    game_date   = _us_baseball_day()
    calls_made  = 0
    credits_est = 0

    log.info("══ LIVE props pull — game_date=%s (US baseball day) ══", game_date)

    for sport in sports:
        cfg     = SPORTS_CONFIG[sport]
        label   = cfg["label"]
        markets = markets_override if markets_override else cfg["markets"]
        if player_props_only:
            markets = _filter_player_props(markets)
        if not markets:
            log.warning("  %s — no markets to fetch; skipping.", cfg["display"])
            continue
        season = _live_season_for_date(sport, game_date)
        if season is None:
            log.info("  %s — %s is outside the configured season window (offseason); skipping.",
                     cfg["display"], game_date)
            continue
        cr_per_event = _credits_per_event(markets, regions)

        # Step 1: today's upcoming events (live, 1 credit)
        try:
            events, remaining = fetch_live_events(sport, game_date, api_key)
            calls_made += 1
        except requests.exceptions.RequestException as exc:
            log.warning("Live events fetch failed for %s %s: %s", sport, game_date, exc)
            continue
        log.info("  %s  %s  %d upcoming events  markets=%s  cr/event≈%d  api_remaining=%s",
                 cfg["display"], game_date, len(events), ",".join(markets), cr_per_event, remaining)
        if not events:
            log.info("    no upcoming events — nothing to write (off-window or offday).")
            continue

        # Step 2: current props per event
        rows_by_market: dict[str, list[dict]] = {}
        for event in events:
            event_id = event.get("id", "")
            event_data, remaining = fetch_live_event_props(
                sport, event_id, markets, regions, api_key
            )
            calls_made  += 1
            credits_est += cr_per_event
            time.sleep(sleep_secs)
            if not event_data:
                continue
            event_rows = event_to_rows(event_data, season, snap_ts_str, load_id, ingested_at)
            for mkt_key, rows in event_rows.items():
                rows_by_market.setdefault(mkt_key, []).extend(rows)

        # Step 3: OVERWRITE today's partition per market with the latest snapshot
        for mkt_key, rows in rows_by_market.items():
            if not rows:
                continue
            key = s3_key(label, mkt_key, season, game_date)
            write_to_s3(rows, key, s3_client, BUCKET)

        log.info("  %s live done  calls=%d  est_credits=%d  api_remaining=%s",
                 cfg["display"], calls_made, credits_est, remaining)

    log.info("Live pull complete.  Total calls: %d  Est. credits: %d", calls_made, credits_est)


# ── CLI ────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Historical MLB/NFL/NCAAF/NCAAB player-prop backfill → S3 Parquet.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--mode",
        choices=["probe", "backfill", "live"],
        default="probe",
        help="probe (default): confirm availability + project cost.  "
             "backfill: full HISTORICAL pull (yesterday & earlier, idempotent).  "
             "live: intraday CURRENT-lines pull for today's slate (overwrites date=today; "
             "the /props page feed — run hourly during game hours).",
    )
    p.add_argument(
        "--sport",
        choices=list(SPORTS_CONFIG.keys()),
        default=None,
        help="Run for one sport only (default: all in value rank order).",
    )
    p.add_argument(
        "--regions",
        default="us",
        help="Comma-separated regions (default: us).  Add eu for Pinnacle coverage.",
    )
    p.add_argument(
        "--sleep-seconds",
        type=float,
        default=REQUEST_DELAY,
        help=f"Seconds between API calls (default: {REQUEST_DELAY}).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap on (season, date) pairs per sport — useful for smoke-testing.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch and overwrite existing S3 partitions.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print credit estimates only; make no API or S3 calls.",
    )
    p.add_argument(
        "--markets",
        default=None,
        help=(
            "Comma-separated market keys to override the sport's default market list. "
            "Use this to backfill a single new market without re-fetching existing ones. "
            "Example: --sport baseball_mlb --markets h2h_1st_5_innings"
        ),
    )
    p.add_argument(
        "--player-props-only",
        action="store_true",
        help=(
            "Restrict the run to player-prop keys (batter_*/pitcher_*/player_*) from "
            "the resolved market list — the daily forward catch-up cron. Combined with "
            "the dynamic season-end (today−1) + idempotent partition skip, a daily run "
            "advances mlb/props/ to yesterday for just the props. "
            "Example: --sport baseball_mlb --player-props-only"
        ),
    )
    return p


def main() -> None:
    args   = _build_parser().parse_args()
    sports = [args.sport] if args.sport else list(VALUE_RANK)
    regions = [r.strip() for r in args.regions.split(",") if r.strip()]

    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        log.error("ODDS_API_KEY not set — check .env")
        sys.exit(1)

    markets_override = (
        [m.strip() for m in args.markets.split(",") if m.strip()]
        if args.markets else None
    )

    if args.mode == "probe":
        run_probe(sports, regions, api_key, args.sleep_seconds, markets_override,
                  args.player_props_only)
        return

    if args.mode == "live":
        s3_client = boto3.client(
            "s3",
            region_name=os.getenv("AWS_DEFAULT_REGION", AWS_REGION),
        )
        run_live(sports, regions, api_key, s3_client, args.sleep_seconds,
                 markets_override, args.player_props_only)
        return

    # Backfill mode — needs S3
    if not args.dry_run:
        s3_client = boto3.client(
            "s3",
            region_name=os.getenv("AWS_DEFAULT_REGION", AWS_REGION),
        )
    else:
        s3_client = None

    run_backfill(
        sports           = sports,
        regions          = regions,
        api_key          = api_key,
        s3_client        = s3_client,
        sleep_secs       = args.sleep_seconds,
        limit            = args.limit,
        force            = args.force,
        dry_run          = args.dry_run,
        markets_override = markets_override,
        player_props_only = args.player_props_only,
    )


if __name__ == "__main__":
    main()
