"""
backfill_multisport_odds_to_s3.py
------------------------------------
Backfill historical odds for NFL, NCAAF, and NCAAB from The Odds API directly
to S3 Parquet. Zero Snowflake writes.

S3 layout — sport-named top-level prefixes within baseball-betting-ml-artifacts:
    s3://baseball-betting-ml-artifacts/
        nfl/odds/season={season}/date={date}/data.parquet
        ncaaf/odds/season={season}/date={date}/data.parquet
        ncaab/odds/season={season}/date={date}/data.parquet

One file per (sport, season, calendar date). Each Parquet row = one
(event × snapshot_ts × bookmaker).
Idempotency: if the S3 key for a date already exists, the date is skipped on
re-run (the Parquet file IS the checkpoint; no external state required).

Credit cost: 10 × #markets × #regions per API call.
Default: 3 markets (h2h,spreads,totals) × 2 regions (us,eu) = 60 cr/call.
At 3 snapshots/date: 180 cr/date. Full 6-season / 3-sport run ≈ ~480K credits.

Snapshot strategy: 3 fixed UTC times per calendar date capture pre-game closing
lines across all time zones:
  16:00 UTC = 11am ET  — before early NFL/NCAAF kickoffs
  20:00 UTC = 3pm  ET  — between NFL afternoon windows
  23:30 UTC = 6:30pm ET — before prime-time kickoffs / NCAAB evening games

commenceTimeFrom/To scope each API call to that calendar day's games only
(00:00 UTC → +1day 05:00 UTC), preventing adjacent-date bleed.

NOTE — Historical scores: The Odds API has NO historical scores endpoint
(confirmed 2026-06-23). The live /v4/sports/{sport}/scores endpoint only looks
back daysFrom days (max 3). Historical game outcomes must come from sport-native
free sources:
  NFL:   nfl_data_py / nflverse GitHub releases
  NCAAF: CollegeFootballData API (CFBD, free)
  NCAAB: ESPN API (unofficial) or sports-reference

Usage:
    # Dry-run (estimate credits, no API calls):
    uv run scripts/backfill_multisport_odds_to_s3.py --dry-run

    # Full odds backfill (default mode):
    uv run scripts/backfill_multisport_odds_to_s3.py

    # Probe for pre-2021 season availability (~1 API call per candidate):
    uv run scripts/backfill_multisport_odds_to_s3.py --mode probe

    # Single sport:
    uv run scripts/backfill_multisport_odds_to_s3.py --sport americanfootball_nfl

    # Resume (idempotent — already-written dates are skipped automatically):
    uv run scripts/backfill_multisport_odds_to_s3.py

    # Quick diagnostic (N calls only, verbose logging):
    uv run scripts/backfill_multisport_odds_to_s3.py --limit 3

    # Validate after run (DuckDB — per sport):
    duckdb -c "SELECT season, COUNT(DISTINCT date) AS dates, COUNT(*) AS rows \\
               FROM read_parquet('s3://baseball-betting-ml-artifacts/nfl/odds/**/*.parquet') \\
               GROUP BY 1 ORDER BY 1"

Environment (from ../.env):
    ODDS_API_KEY            Required (main key — historical endpoint).
    AWS_ACCESS_KEY_ID       Required (or EC2 instance role).
    AWS_SECRET_ACCESS_KEY   Required (or EC2 instance role).
    AWS_DEFAULT_REGION      Optional (default: us-east-2).
"""

import argparse
import io
import json
import logging
import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import boto3
import botocore.exceptions
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
BUCKET     = "baseball-betting-ml-artifacts"
AWS_REGION = "us-east-2"

DEFAULT_MARKETS   = "h2h,spreads,totals"
DEFAULT_REGIONS   = "us,eu"
DEFAULT_SNAPSHOTS = ["16:00", "20:00", "23:30"]
REQUEST_DELAY     = 1.0

SPORT_DISPLAY = {
    "americanfootball_nfl":   "NFL",
    "americanfootball_ncaaf": "NCAAF",
    "basketball_ncaab":       "NCAAB",
}

# Top-level S3 prefix per sport (sport-named buckets within baseball-betting-ml-artifacts)
SPORT_S3_PREFIX = {
    "americanfootball_nfl":   "nfl/odds",
    "americanfootball_ncaaf": "ncaaf/odds",
    "basketball_ncaab":       "ncaab/odds",
}

# Season date ranges: (sport, season) → (start_date, end_date)
# Season label = year the season STARTED (NFL 2024 = Sep 2024 – Feb 2025).
# Ranges include bowl games, playoffs, and championship weekends.
SEASON_RANGES: dict[str, dict[int, tuple[date, date]]] = {
    "americanfootball_nfl": {
        2020: (date(2020,  9, 10), date(2021,  2,  7)),  # probe confirmed 1 event
        2021: (date(2021, 9,  9), date(2022, 2, 13)),
        2022: (date(2022, 9,  8), date(2023, 2, 12)),
        2023: (date(2023, 9,  7), date(2024, 2, 11)),
        2024: (date(2024, 9,  5), date(2025, 2,  9)),
        2025: (date(2025, 9,  4), date(2026, 2,  8)),   # Super Bowl LX est. — verify exact date
    },
    "americanfootball_ncaaf": {
        2020: (date(2020,  9,  3), date(2021,  1, 11)),  # probe confirmed 26 events
        2021: (date(2021, 8, 28), date(2022, 1, 10)),
        2022: (date(2022, 8, 27), date(2023, 1,  9)),
        2023: (date(2023, 8, 26), date(2024, 1, 22)),
        2024: (date(2024, 8, 24), date(2025, 1, 20)),
        2025: (date(2025, 8, 23), date(2026, 1, 19)),   # CFP championship est. — verify exact date
    },
    "basketball_ncaab": {
        # Label = year season started (2021 = 2021-22 season)
        2020: (date(2020, 11, 25), date(2021,  4,  5)),  # probe confirmed 36 events
        2021: (date(2021, 11,  9), date(2022, 4,  4)),
        2022: (date(2022, 11,  7), date(2023, 4,  3)),
        2023: (date(2023, 11,  6), date(2024, 4,  8)),
        2024: (date(2024, 11,  4), date(2025, 4,  7)),
        2025: (date(2025, 11,  3), date(2026, 4,  6)),   # NCAA championship est. — verify exact date
    },
}

# S3 prefix for scores output (parallel to SPORT_S3_PREFIX for odds)
SPORT_S3_SCORES_PREFIX = {
    "americanfootball_nfl":   "nfl/scores",
    "americanfootball_ncaaf": "ncaaf/scores",
    "basketball_ncaab":       "ncaab/scores",
}

# Pre-2021 probe candidates: (probe_date, suggested_season_start, suggested_season_end).
# --mode probe fires one API call per entry and reports data availability.
# Add confirmed seasons to SEASON_RANGES above before running the full backfill.
PROBE_CANDIDATES: dict[str, dict[int, tuple[date, date, date]]] = {
    "americanfootball_nfl": {
        2018: (date(2018,  9,  9), date(2018,  9,  6), date(2019,  2,  3)),
        2019: (date(2019,  9,  8), date(2019,  9,  5), date(2020,  2,  2)),
        2020: (date(2020,  9, 10), date(2020,  9, 10), date(2021,  2,  7)),
    },
    "americanfootball_ncaaf": {
        2019: (date(2019,  9,  7), date(2019,  8, 24), date(2020,  1, 13)),
        2020: (date(2020, 10, 10), date(2020,  9,  3), date(2021,  1, 11)),
    },
    "basketball_ncaab": {
        # 2019 = 2019-20 season (COVID cancelled March Madness)
        2019: (date(2020,  1, 15), date(2019, 11,  5), date(2020,  3, 11)),
        2020: (date(2020, 12,  5), date(2020, 11, 25), date(2021,  4,  5)),
    },
}


# ── S3 helpers ─────────────────────────────────────────────────────────────────

def make_s3_client():
    return boto3.client("s3", region_name=AWS_REGION)


def s3_key(sport: str, season: int, game_date: date) -> str:
    prefix = SPORT_S3_PREFIX[sport]
    return f"{prefix}/season={season}/date={game_date}/data.parquet"


def s3_scores_key(sport: str, season: int, game_date: date) -> str:
    prefix = SPORT_S3_SCORES_PREFIX[sport]
    return f"{prefix}/season={season}/date={game_date}/data.parquet"


def scan_existing_s3_dates_for_prefix(s3_client, prefix: str) -> set[tuple[int, str]]:
    """Return set of (season, date_str) already written under *prefix*."""
    existing: set[tuple[int, str]] = set()
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=f"{prefix}/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith("/data.parquet"):
                continue
            parts = key.split("/")
            season_part = next((p for p in parts if p.startswith("season=")), None)
            date_part   = next((p for p in parts if p.startswith("date=")),   None)
            if season_part and date_part:
                try:
                    existing.add((int(season_part[len("season="):]), date_part[len("date="):]))
                except ValueError:
                    pass
    return existing


def scan_existing_s3_dates(s3_client, sport: str) -> set[tuple[int, str]]:
    """Return set of (season, date_str) already written to S3 for this sport's odds prefix."""
    return scan_existing_s3_dates_for_prefix(s3_client, SPORT_S3_PREFIX[sport])


def write_to_s3(s3_client, df: pd.DataFrame, sport: str, season: int, game_date: date) -> None:
    key   = s3_key(sport, season, game_date)
    table = pa.Table.from_pandas(df, preserve_index=False)
    buf   = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)
    s3_client.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())
    log.info("    Wrote %d rows → s3://%s/%s", len(df), BUCKET, key)


# ── Odds API ───────────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise EnvironmentError("ODDS_API_KEY is not set.")
    return key


def _parse_int_header(v: str | None) -> int | None:
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_historical_odds(
    sport: str,
    snapshot_ts: str,
    markets: str,
    regions: str,
    date_obj: date,
    sleep_seconds: float,
) -> tuple[list[dict], int | None, int | None]:
    """
    Fetch historical odds for *sport* at *snapshot_ts* scoped to *date_obj*.

    commenceTimeFrom / commenceTimeTo restrict the response to events on
    *date_obj* only (00:00 UTC → +1day 05:00 UTC), so adjacent-date games
    (e.g. Monday Night Football bleeding into Tuesday UTC) are excluded.

    Returns (events, credits_used, credits_remaining).
    Empty list on 404. Exits on 401/403/429.
    """
    url = f"{ODDS_API_BASE_URL}/historical/sports/{sport}/odds"

    day_start = datetime(date_obj.year, date_obj.month, date_obj.day, 0, 0, 0, tzinfo=timezone.utc)
    next_day  = date_obj + timedelta(days=1)
    day_end   = datetime(next_day.year, next_day.month, next_day.day, 5, 0, 0, tzinfo=timezone.utc)

    params = {
        "apiKey":           _get_api_key(),
        "date":             snapshot_ts,
        "regions":          regions,
        "markets":          markets,
        "oddsFormat":       "american",
        "commenceTimeFrom": _iso_utc(day_start),
        "commenceTimeTo":   _iso_utc(day_end),
    }

    log.debug("  GET %s  sport=%s  snapshot=%s", url, sport, snapshot_ts)

    try:
        resp = requests.get(url, params=params, timeout=30)
    except requests.RequestException as exc:
        log.warning("  Request error: %s — treating as empty", exc)
        time.sleep(sleep_seconds)
        return [], None, None

    used      = _parse_int_header(resp.headers.get("x-requests-used"))
    remaining = _parse_int_header(resp.headers.get("x-requests-remaining"))

    if resp.status_code in (401, 403):
        print(f"\nFATAL: HTTP {resp.status_code} — check ODDS_API_KEY / plan tier.", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 429:
        print("\nFATAL: HTTP 429 — rate limit. Re-run with --sleep-seconds 2.\n", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 404:
        time.sleep(sleep_seconds)
        return [], used, remaining

    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        log.warning("  HTTP error %s — treating as empty", exc)
        time.sleep(sleep_seconds)
        return [], used, remaining

    payload = resp.json()
    events  = payload.get("data", []) if isinstance(payload, dict) else (payload if isinstance(payload, list) else [])

    log.debug("  snapshot=%s  events=%d  credits_used=%s  remaining=%s",
              snapshot_ts, len(events), used, remaining)
    time.sleep(sleep_seconds)
    return events, used, remaining


def _in_day_window(commence_time_str: str, day_start: datetime, day_end: datetime) -> bool:
    """Return True if the game commences within [day_start, day_end] UTC."""
    try:
        ct = datetime.fromisoformat(commence_time_str.replace("Z", "+00:00"))
        return day_start <= ct <= day_end
    except (ValueError, AttributeError):
        return False


def fetch_historical_scores(
    sport: str,
    game_date: date,
    sleep_seconds: float,
) -> tuple[list[dict], int | None, int | None]:
    """
    Fetch historical scores for *sport* games that started on *game_date*.

    The scores endpoint uses `daysFrom` (not commenceTimeFrom/To like the odds
    endpoint). We request daysFrom=2 at a next-day 16:00 UTC snapshot so all
    time-zone-late games are complete, then client-side filter to game_date's
    window (00:00 UTC on game_date → 05:00 UTC on game_date+1).

    Returns (games, credits_used, credits_remaining).
    Empty list on 404. Exits on 401/403/429.
    """
    url = f"{ODDS_API_BASE_URL}/historical/sports/{sport}/scores"

    day_start = datetime(game_date.year, game_date.month, game_date.day, 0, 0, 0, tzinfo=timezone.utc)
    next_day  = game_date + timedelta(days=1)
    day_end   = datetime(next_day.year, next_day.month, next_day.day, 5, 0, 0, tzinfo=timezone.utc)
    snapshot  = datetime(next_day.year, next_day.month, next_day.day, 16, 0, 0, tzinfo=timezone.utc)

    params = {
        "apiKey":   _get_api_key(),
        "date":     _iso_utc(snapshot),
        "daysFrom": 2,   # 2-day lookback so noon-ET games (16:00 UTC) are included
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
    except requests.RequestException as exc:
        log.warning("  Scores request error: %s — treating as empty", exc)
        time.sleep(sleep_seconds)
        return [], None, None

    used      = _parse_int_header(resp.headers.get("x-requests-used"))
    remaining = _parse_int_header(resp.headers.get("x-requests-remaining"))

    if resp.status_code in (401, 403):
        print(f"\nFATAL: HTTP {resp.status_code} — check ODDS_API_KEY / plan tier.", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 429:
        print("\nFATAL: HTTP 429 — rate limit. Re-run with --sleep-seconds 2.\n", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 404:
        log.warning("  scores  date=%s  status=404  url=%s  body=%.200s",
                    game_date, url, resp.text)
        time.sleep(sleep_seconds)
        return [], used, remaining

    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        log.warning("  scores  date=%s  HTTP error %s  body=%.200s",
                    game_date, exc, resp.text)
        time.sleep(sleep_seconds)
        return [], used, remaining

    payload   = resp.json()
    all_games = payload.get("data", []) if isinstance(payload, dict) else (payload if isinstance(payload, list) else [])
    games     = [g for g in all_games if _in_day_window(g.get("commence_time", ""), day_start, day_end)]

    log.info("  scores  date=%s  status=%d  all_games=%d  day_games=%d  remaining=%s",
             game_date, resp.status_code, len(all_games), len(games), remaining)
    if all_games and not games:
        log.warning("  FILTER DROP: all_games=%d but day_games=0 for %s (window %s→%s)",
                    len(all_games), game_date, _iso_utc(day_start), _iso_utc(day_end))
        for g in all_games[:3]:
            log.warning("    sample commence_time=%s", g.get("commence_time"))
    time.sleep(sleep_seconds)
    return games, used, remaining


# ── Field extraction ───────────────────────────────────────────────────────────

def _find_market(markets: list[dict], key: str) -> list[dict]:
    for m in markets:
        if m.get("key") == key:
            return m.get("outcomes", [])
    return []


def _extract_h2h(outcomes: list[dict], home_team: str) -> tuple[int | None, int | None]:
    home_ml = away_ml = None
    for o in outcomes:
        price = o.get("price")
        if o.get("name") == home_team:
            home_ml = price
        else:
            away_ml = price
    return home_ml, away_ml


def _extract_spread(outcomes: list[dict], home_team: str) -> tuple[float | None, int | None, int | None]:
    home_spread = home_price = away_price = None
    for o in outcomes:
        if o.get("name") == home_team:
            home_spread = o.get("point")
            home_price  = o.get("price")
        else:
            away_price = o.get("price")
    if home_spread is not None:
        home_spread = float(home_spread)
    return home_spread, home_price, away_price


def _extract_totals(outcomes: list[dict]) -> tuple[float | None, int | None, int | None]:
    total_line = over_price = under_price = None
    for o in outcomes:
        name = (o.get("name") or "").lower()
        if name == "over":
            over_price = o.get("price")
            if o.get("point") is not None:
                total_line = float(o["point"])
        elif name == "under":
            under_price = o.get("price")
            if total_line is None and o.get("point") is not None:
                total_line = float(o["point"])
    return total_line, over_price, under_price


def _american_to_prob(price: int | None) -> float | None:
    if price is None:
        return None
    if price == 0:
        return 0.5
    return (abs(price) / (abs(price) + 100)) if price < 0 else (100 / (price + 100))


# ── Row builder ────────────────────────────────────────────────────────────────

def events_to_rows(
    events: list[dict],
    sport: str,
    season: int,
    snapshot_ts: str,
    load_id: str,
    ingested_at: str,
) -> list[dict]:
    """One row per (event × bookmaker); drops bookmakers with no markets data."""
    rows: list[dict] = []
    for event in events:
        home_team     = event.get("home_team", "")
        away_team     = event.get("away_team", "")
        commence_time = event.get("commence_time", "")
        event_id      = event.get("id", "")

        for bk in event.get("bookmakers", []):
            bk_markets = bk.get("markets", [])

            h2h_outcomes     = _find_market(bk_markets, "h2h")
            spread_outcomes  = _find_market(bk_markets, "spreads")
            totals_outcomes  = _find_market(bk_markets, "totals")

            home_ml, away_ml                         = _extract_h2h(h2h_outcomes, home_team)
            home_spread, home_spread_price, away_spread_price = _extract_spread(spread_outcomes, home_team)
            total_line, over_price, under_price      = _extract_totals(totals_outcomes)

            if home_ml is None and home_spread is None and total_line is None:
                continue  # bookmaker carried nothing at this snapshot

            rows.append({
                "sport":              sport,
                "season":             season,
                "event_id":           event_id,
                "commence_time":      commence_time,
                "home_team":          home_team,
                "away_team":          away_team,
                "snapshot_ts":        snapshot_ts,
                "bookmaker_key":      bk.get("key", ""),
                "bookmaker_title":    bk.get("title", ""),
                "home_ml":            home_ml,
                "away_ml":            away_ml,
                "home_spread":        home_spread,
                "home_spread_price":  home_spread_price,
                "away_spread_price":  away_spread_price,
                "total_line":         total_line,
                "over_price":         over_price,
                "under_price":        under_price,
                "home_win_prob":      _american_to_prob(home_ml),
                "raw_bookmaker_json": json.dumps(bk),
                "load_id":            load_id,
                "ingested_at":        ingested_at,
            })
    return rows


def scores_to_rows(
    games: list[dict],
    sport: str,
    season: int,
    load_id: str,
    ingested_at: str,
) -> list[dict]:
    """One row per game containing final score data."""
    rows: list[dict] = []
    for game in games:
        home_team  = game.get("home_team", "")
        away_team  = game.get("away_team", "")
        home_score = away_score = None
        for s in (game.get("scores") or []):
            try:
                val = int(s["score"])
            except (KeyError, TypeError, ValueError):
                val = None
            if s.get("name") == home_team:
                home_score = val
            elif s.get("name") == away_team:
                away_score = val

        rows.append({
            "sport":         sport,
            "season":        season,
            "event_id":      game.get("id", ""),
            "commence_time": game.get("commence_time", ""),
            "home_team":     home_team,
            "away_team":     away_team,
            "completed":     bool(game.get("completed", False)),
            "home_score":    home_score,
            "away_score":    away_score,
            "load_id":       load_id,
            "ingested_at":   ingested_at,
        })
    return rows


# ── Date iterator ──────────────────────────────────────────────────────────────

def date_range(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ── Dry-run budget estimator ───────────────────────────────────────────────────

def print_budget_estimate(sports: list[str], markets: str, regions: str, snapshots: list[str]) -> None:
    n_markets        = len([m for m in markets.split(",") if m.strip()])
    n_regions        = len([r for r in regions.split(",") if r.strip()])
    credits_per_call = 10 * n_markets * n_regions
    credits_per_date = credits_per_call * len(snapshots)

    print("\n── CREDIT BUDGET ESTIMATE ─────────────────────────────────")
    print(f"Markets         : {markets}  ({n_markets} markets)")
    print(f"Regions         : {regions}  ({n_regions} regions)")
    print(f"Snapshots/date  : {', '.join(snapshots)} UTC  ({len(snapshots)} calls/date)")
    print(f"Credits/API call: {credits_per_call}")
    print(f"Credits/date    : {credits_per_date}")
    print()

    grand_dates = grand_calls = 0
    for sport in sports:
        ranges = SEASON_RANGES.get(sport, {})
        sport_dates = 0
        print(f"  {SPORT_DISPLAY.get(sport, sport)}")
        for season, (start, end) in sorted(ranges.items()):
            n = (end - start).days + 1
            sport_dates += n
            season_credits = n * credits_per_date
            print(f"    {season}: {start} → {end}  ({n} cal-days, ~{season_credits:,} credits)")
        sport_calls    = sport_dates * len(snapshots)
        sport_credits  = sport_calls * credits_per_call
        grand_dates   += sport_dates
        grand_calls   += sport_calls
        print(f"    subtotal: {sport_dates} dates × {len(snapshots)} snaps = {sport_calls:,} calls  "
              f"({sport_credits:,} credits)")
        print()

    grand_credits = grand_calls * credits_per_call
    active_pct    = 0.40  # ~40% of cal-days have games across the three sports
    active_credits = int(grand_dates * active_pct) * credits_per_date

    print(f"Total calendar dates : {grand_dates:,}")
    print(f"Total API calls      : {grand_calls:,}")
    print(f"Total credits (worst): {grand_credits:,}  (all calendar days)")
    print(f"Est. credits (actual): ~{active_credits:,}  (~{int(active_pct*100)}% of days have games)")
    print()
    print("Headroom note: MLB ongoing ops use ~50K credits through 2026-07-17.")
    print(f"Even worst-case {grand_credits:,} leaves ~{4_500_000 - grand_credits:,} of the 4.5M surplus.")
    print("\nDry-run complete.\n")


# ── Main backfill ──────────────────────────────────────────────────────────────

def run_backfill(
    sports: list[str],
    markets: str,
    regions: str,
    snapshots: list[str],
    sleep_seconds: float,
    force: bool,
) -> None:
    n_markets        = len([m for m in markets.split(",") if m.strip()])
    n_regions        = len([r for r in regions.split(",") if r.strip()])
    credits_per_call = 10 * n_markets * n_regions

    s3          = make_s3_client()
    load_id     = str(uuid.uuid4())
    ingested_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    total_calls_made   = 0
    total_rows         = 0
    total_dates_written = 0
    last_remaining: int | None = None
    sport_summary: dict[str, dict] = {}

    for sport in sports:
        ranges = SEASON_RANGES.get(sport, {})
        if not ranges:
            log.warning("No season ranges defined for %s — skipping", sport)
            continue

        log.info("\n══ %s ══", SPORT_DISPLAY.get(sport, sport))

        if not force:
            log.info("Scanning S3 for already-loaded dates ...")
            existing = scan_existing_s3_dates(s3, sport)
            log.info("  %d date(s) already in S3", len(existing))
        else:
            existing = set()
            log.info("--force: skipping idempotency check")

        sport_rows    = 0
        sport_written = 0
        sport_skipped = 0

        for season, (season_start, season_end) in sorted(ranges.items()):
            log.info("  Season %d: %s → %s", season, season_start, season_end)

            for game_date in date_range(season_start, season_end):
                date_str = str(game_date)

                if (season, date_str) in existing:
                    sport_skipped += 1
                    continue

                date_rows: list[dict] = []

                for snap_time in snapshots:
                    snapshot_ts = f"{date_str}T{snap_time}:00Z"

                    events, used, remaining = fetch_historical_odds(
                        sport         = sport,
                        snapshot_ts   = snapshot_ts,
                        markets       = markets,
                        regions       = regions,
                        date_obj      = game_date,
                        sleep_seconds = sleep_seconds,
                    )
                    total_calls_made += 1
                    if remaining is not None:
                        last_remaining = remaining

                    if events:
                        rows = events_to_rows(
                            events      = events,
                            sport       = sport,
                            season      = season,
                            snapshot_ts = snapshot_ts,
                            load_id     = load_id,
                            ingested_at = ingested_at,
                        )
                        date_rows.extend(rows)
                        log.info("    %s %s  events=%d  rows_added=%d  credits_remaining=%s",
                                 date_str, snap_time, len(events), len(rows), remaining)

                if date_rows:
                    df = pd.DataFrame(date_rows)
                    # Dedup within the file on the natural key
                    df = df.drop_duplicates(subset=["event_id", "snapshot_ts", "bookmaker_key"])
                    write_to_s3(s3, df, sport, season, game_date)
                    sport_rows    += len(df)
                    total_rows    += len(df)
                    sport_written += 1
                    total_dates_written += 1
                else:
                    log.debug("  %s — no events returned at any snapshot", date_str)

        log.info("  %s done: %d written / %d skipped / %d rows",
                 SPORT_DISPLAY.get(sport, sport), sport_written, sport_skipped, sport_rows)

        sport_summary[sport] = {
            "dates_written": sport_written,
            "dates_skipped": sport_skipped,
            "rows":          sport_rows,
        }

    # Coverage report
    print("\n" + "=" * 65)
    print("MULTI-SPORT ODDS BACKFILL — COVERAGE REPORT")
    print("=" * 65)
    print(f"  Load ID           : {load_id}")
    print(f"  Ingested at       : {ingested_at}")
    print(f"  Markets           : {markets}")
    print(f"  Regions           : {regions}")
    print(f"  Snapshots/date    : {', '.join(snapshots)} UTC")
    print(f"  Credits/API call  : {credits_per_call}")
    print(f"  Total API calls   : {total_calls_made:,}")
    print(f"  Est. credits spent: ~{total_calls_made * credits_per_call:,}")
    if last_remaining is not None:
        print(f"  Credits remaining : {last_remaining:,}")
    print()
    for sport, s in sport_summary.items():
        print(f"  {SPORT_DISPLAY.get(sport, sport):6}  "
              f"written={s['dates_written']:>4}  "
              f"skipped={s['dates_skipped']:>4}  "
              f"rows={s['rows']:>8,}")
    print()
    print(f"  Total dates written : {total_dates_written:,}")
    print(f"  Total rows          : {total_rows:,}")
    print()
    print("  S3 locations:")
    for sport in sport_summary:
        prefix = SPORT_S3_PREFIX.get(sport, "")
        print(f"    {SPORT_DISPLAY.get(sport, sport):6} → s3://{BUCKET}/{prefix}/")
    print()
    print("  DuckDB validation (per sport):")
    for sport in sport_summary:
        prefix = SPORT_S3_PREFIX.get(sport, "")
        label  = SPORT_DISPLAY.get(sport, sport)
        print(f"    # {label}")
        print(f'    duckdb -c "SELECT season, COUNT(DISTINCT date) AS dates, COUNT(*) AS rows')
        print(f"    FROM read_parquet('s3://{BUCKET}/{prefix}/**/*.parquet')")
        print(f'    GROUP BY 1 ORDER BY 1"')
    print()


def run_scores_backfill(
    sports: list[str],
    sleep_seconds: float,
    force: bool,
    limit: int | None = None,
) -> None:
    """Backfill historical game scores for each sport/season/date to S3 Parquet."""
    s3          = make_s3_client()
    load_id     = str(uuid.uuid4())
    ingested_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    total_calls  = 0
    total_rows   = 0
    last_remaining: int | None = None
    sport_summary: dict[str, dict] = {}

    for sport in sports:
        ranges = SEASON_RANGES.get(sport, {})
        if not ranges:
            log.warning("No season ranges defined for %s — skipping", sport)
            continue

        log.info("\n══ %s (scores) ══", SPORT_DISPLAY.get(sport, sport))
        scores_prefix = SPORT_S3_SCORES_PREFIX[sport]

        if not force:
            log.info("Scanning S3 for already-loaded score dates ...")
            existing = scan_existing_s3_dates_for_prefix(s3, scores_prefix)
            log.info("  %d date(s) already in S3", len(existing))
        else:
            existing = set()
            log.info("--force: skipping idempotency check")

        sport_rows    = 0
        sport_written = 0
        sport_skipped = 0

        sport_calls = 0
        for season, (season_start, season_end) in sorted(ranges.items()):
            log.info("  Season %d: %s → %s", season, season_start, season_end)

            for game_date in date_range(season_start, season_end):
                if limit is not None and sport_calls >= limit:
                    log.info("  --limit %d reached — stopping early", limit)
                    break
                date_str = str(game_date)

                if (season, date_str) in existing:
                    sport_skipped += 1
                    continue

                games, used, remaining = fetch_historical_scores(
                    sport         = sport,
                    game_date     = game_date,
                    sleep_seconds = sleep_seconds,
                )
                sport_calls += 1
                total_calls += 1
                if remaining is not None:
                    last_remaining = remaining

                if games:
                    rows = scores_to_rows(
                        games       = games,
                        sport       = sport,
                        season      = season,
                        load_id     = load_id,
                        ingested_at = ingested_at,
                    )
                    if rows:
                        df    = pd.DataFrame(rows)
                        key   = s3_scores_key(sport, season, game_date)
                        table = pa.Table.from_pandas(df, preserve_index=False)
                        buf   = io.BytesIO()
                        pq.write_table(table, buf, compression="snappy")
                        buf.seek(0)
                        s3.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())
                        log.info("    Wrote %d rows (scores) → s3://%s/%s", len(df), BUCKET, key)
                        sport_rows    += len(df)
                        total_rows    += len(df)
                        sport_written += 1
                        log.info("    %s  games=%d  completed=%d  remaining=%s",
                                 date_str, len(games),
                                 sum(1 for r in rows if r.get("completed")),
                                 remaining)
                else:
                    log.debug("  %s — no score events returned", date_str)

        log.info("  %s scores: %d written / %d skipped / %d rows",
                 SPORT_DISPLAY.get(sport, sport), sport_written, sport_skipped, sport_rows)
        sport_summary[sport] = {
            "dates_written": sport_written,
            "dates_skipped": sport_skipped,
            "rows":          sport_rows,
        }

    print("\n" + "=" * 65)
    print("MULTI-SPORT SCORES BACKFILL — COVERAGE REPORT")
    print("=" * 65)
    print(f"  Load ID           : {load_id}")
    print(f"  Ingested at       : {ingested_at}")
    print(f"  Total API calls   : {total_calls:,}")
    print(f"  Est. credits spent: ~{total_calls * 10:,}  (10/call, no market multiplier)")
    if last_remaining is not None:
        print(f"  Credits remaining : {last_remaining:,}")
    print()
    for sport, s in sport_summary.items():
        print(f"  {SPORT_DISPLAY.get(sport, sport):6}  "
              f"written={s['dates_written']:>4}  "
              f"skipped={s['dates_skipped']:>4}  "
              f"rows={s['rows']:>8,}")
    print()
    print(f"  Total rows: {total_rows:,}")
    print()
    print("  DuckDB validation (per sport):")
    for sport in sport_summary:
        prefix = SPORT_S3_SCORES_PREFIX.get(sport, "")
        label  = SPORT_DISPLAY.get(sport, sport)
        print(f"    # {label}")
        print(f'    duckdb -c "SELECT season, COUNT(*) AS games, SUM(completed::INT) AS completed')
        print(f"    FROM read_parquet('s3://{BUCKET}/{prefix}/**/*.parquet')")
        print(f'    GROUP BY 1 ORDER BY 1"')
    print()


def run_probe(sports: list[str], sleep_seconds: float) -> None:
    """
    Probe The Odds API for pre-2021 season data availability.

    Fires one cheap API call (h2h, us region = 10 credits) per candidate
    (sport × season) and reports how many events are available. Prints
    suggested SEASON_RANGES additions for any seasons that return data.
    """
    _get_api_key()  # fail fast if key missing

    total_calls = 0
    found: dict[str, list[tuple[int, date, date, int]]] = {}

    print("\n── SEASON PROBE ──────────────────────────────────────────────")
    print("Testing pre-2021 seasons for API data availability (~10 cr/call)...")
    print()

    for sport in sports:
        candidates = PROBE_CANDIDATES.get(sport, {})
        if not candidates:
            print(f"  {SPORT_DISPLAY.get(sport, sport)}: no probe candidates defined")
            continue

        print(f"  {SPORT_DISPLAY.get(sport, sport)}")
        found[sport] = []

        for candidate_season, (probe_date, sug_start, sug_end) in sorted(candidates.items()):
            events, _, remaining = fetch_historical_odds(
                sport         = sport,
                snapshot_ts   = f"{probe_date}T16:00:00Z",
                markets       = "h2h",
                regions       = "us",
                date_obj      = probe_date,
                sleep_seconds = sleep_seconds,
            )
            total_calls += 1
            n = len(events)
            status = f"✓ {n} events" if n > 0 else "✗ no data"
            print(f"    {candidate_season}  probe={probe_date}  →  {status}"
                  f"  (credits_remaining={remaining})")
            if n > 0:
                found[sport].append((candidate_season, sug_start, sug_end, n))

    print()
    print(f"Total probe calls: {total_calls}  (~{total_calls * 10} credits)")
    print()

    has_additions = any(v for v in found.values())
    if has_additions:
        print("── SUGGESTED SEASON_RANGES ADDITIONS ────────────────────────")
        print("Add these entries to SEASON_RANGES in this script, then re-run:\n")
        for sport in sports:
            additions = found.get(sport, [])
            if not additions:
                continue
            print(f'    # {SPORT_DISPLAY.get(sport, sport)}')
            print(f'    "{sport}": {{')
            for season, sug_start, sug_end, n in additions:
                print(f"        {season}: (date({sug_start.year}, {sug_start.month:2d}, {sug_start.day:2d}),"
                      f" date({sug_end.year}, {sug_end.month:2d}, {sug_end.day:2d})),"
                      f"  # {n} events on probe date")
            print("    }")
            print()
    else:
        print("No pre-2021 data found — SEASON_RANGES is already at API coverage limits.")
    print()


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Backfill multi-sport historical odds (NFL/NCAAF/NCAAB) "
            "from The Odds API → S3 Parquet. Zero Snowflake writes."
        )
    )
    p.add_argument(
        "--sport",
        default="all",
        metavar="SPORT",
        help=(
            f"Sport to backfill, or 'all' (default: all). "
            f"Choices: {', '.join(SPORT_DISPLAY.keys())}."
        ),
    )
    p.add_argument(
        "--markets",
        default=DEFAULT_MARKETS,
        metavar="MARKETS",
        help=f"Comma-separated market keys (default: {DEFAULT_MARKETS}).",
    )
    p.add_argument(
        "--regions",
        default=DEFAULT_REGIONS,
        metavar="REGIONS",
        help=(
            f"Comma-separated region keys (default: {DEFAULT_REGIONS}). "
            "Cost = 10 × markets × regions per call. 'eu' adds Pinnacle."
        ),
    )
    p.add_argument(
        "--snapshots",
        default=",".join(DEFAULT_SNAPSHOTS),
        metavar="HH:MM,...",
        help=(
            f"Comma-separated UTC snapshot times per date "
            f"(default: {','.join(DEFAULT_SNAPSHOTS)}). "
            "Each snapshot = 1 API call."
        ),
    )
    p.add_argument(
        "--sleep-seconds",
        type=float,
        default=REQUEST_DELAY,
        metavar="N",
        help=f"Sleep between API calls in seconds (default: {REQUEST_DELAY}).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-fetch dates already in S3 (bypasses idempotency skip).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N API calls (per sport). Useful for quick diagnostic runs.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Estimate credits and exit without making any API calls or S3 writes.",
    )
    p.add_argument(
        "--mode",
        default="odds",
        choices=["odds", "probe"],
        help=(
            "odds: backfill game-line odds h2h/spreads/totals (default). "
            "probe: test pre-2021 season availability (~10 cr/candidate, no writes). "
            "NOTE: scores mode removed — The Odds API has no historical scores endpoint; "
            "use nfl_data_py (NFL), CFBD (NCAAF), or ESPN API (NCAAB) for game outcomes."
        ),
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    if args.sport == "all":
        sports = list(SPORT_DISPLAY.keys())
    elif args.sport in SPORT_DISPLAY:
        sports = [args.sport]
    else:
        print(f"ERROR: unknown sport '{args.sport}'. Choices: {', '.join(SPORT_DISPLAY.keys())}", file=sys.stderr)
        sys.exit(1)

    snapshots = [s.strip() for s in args.snapshots.split(",") if s.strip()]
    if not snapshots:
        print("ERROR: --snapshots is empty.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print_budget_estimate(sports, args.markets, args.regions, snapshots)
        return

    if args.mode == "probe":
        run_probe(sports, args.sleep_seconds)
    else:
        run_backfill(
            sports        = sports,
            markets       = args.markets,
            regions       = args.regions,
            snapshots     = snapshots,
            sleep_seconds = args.sleep_seconds,
            force         = args.force,
        )


if __name__ == "__main__":
    main()
