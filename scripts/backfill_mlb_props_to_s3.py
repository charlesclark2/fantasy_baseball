"""
backfill_mlb_props_to_s3.py
------------------------------------
DEPRECATED — superseded by scripts/backfill_multisport_props_to_s3.py

This script used the wrong historical endpoint (/v4/historical/sports/{sport}/odds)
which does not support player prop markets and returns INVALID_MARKET.  The correct
endpoint is /v4/historical/sports/{sport}/events/{eventId}/odds (two-step: get event
IDs first, then fetch props per event).  Use backfill_multisport_props_to_s3.py
for all MLB + multi-sport prop backfill work.
------------------------------------
Backfill historical MLB player prop lines from The Odds API directly to
S3 Parquet.  Zero Snowflake writes.

S3 layout — Hive-partitioned by market, season, and date:
    s3://baseball-betting-ml-artifacts/
        mlb/props/market={market_key}/season={season}/date={game_date}/data.parquet

One file per (market_key, season, calendar date).
Each row = one (event × snapshot_ts × bookmaker × player).

Idempotency: a (market_key, season, date) partition that already exists in
S3 is skipped on re-run (the Parquet file IS the checkpoint; no external
state required).

All phase-1 markets are requested in a SINGLE API call per date-snapshot to
minimise credit spend.  The response is then fanned out to separate S3
partitions per market.

Credit cost: 10 × #markets × #regions per API call (standard formula — the
probe mode measures the actual per-call cost from the x-requests-remaining
header delta and uses that for the full projection).

Snapshot strategy: 2 UTC snapshots per calendar date capture closing lines:
  17:00 UTC = noon ET    — before afternoon games (1pm ET starts)
  23:30 UTC = 6:30pm ET  — before prime-time games (7pm ET starts)

Phase-1 prop markets (--markets default):
  pitcher_strikeouts, pitcher_outs, batter_total_bases, batter_hits,
  batter_home_runs

Leakage safety: commenceTimeFrom/To scopes each API call to games on that
calendar day (00:00 UTC → next-day 07:00 UTC).  Training code must
additionally filter snapshot_ts < commence_time when using lines as features.

Season ranges: 2023 start capped at 2023-05-03 per E5.1 spec (the probe
will confirm the true floor; earlier data is a bonus).

Usage:
    # PHASE 0 — Probe first (mandatory before backfill, ~70 credits):
    uv run scripts/backfill_mlb_props_to_s3.py --mode probe

    # Dry-run (estimate credits, no API calls):
    uv run scripts/backfill_mlb_props_to_s3.py --dry-run

    # Quick diagnostic (N API calls, verbose):
    uv run scripts/backfill_mlb_props_to_s3.py --mode backfill --limit 3

    # Full props backfill (long-running — hand to operator):
    uv run scripts/backfill_mlb_props_to_s3.py --mode backfill

    # Resume (idempotent — existing partitions auto-skipped):
    uv run scripts/backfill_mlb_props_to_s3.py --mode backfill

    # Validate after run (DuckDB):
    duckdb -c "SELECT market_key, season, COUNT(DISTINCT date) AS dates, COUNT(*) AS rows \\
               FROM read_parquet('s3://baseball-betting-ml-artifacts/mlb/props/**/*.parquet') \\
               GROUP BY 1, 2 ORDER BY 1, 2"

Environment (from ../.env):
    ODDS_API_KEY            Required (main key).
    AWS_ACCESS_KEY_ID       Required (or EC2/Railway instance role).
    AWS_SECRET_ACCESS_KEY   Required (or EC2/Railway instance role).
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
SPORT             = "baseball_mlb"
S3_PREFIX         = "mlb/props"

PHASE1_MARKETS = [
    "pitcher_strikeouts",
    "pitcher_outs",
    "batter_total_bases",
    "batter_hits",
    "batter_home_runs",
]
DEFAULT_MARKETS   = ",".join(PHASE1_MARKETS)
DEFAULT_REGIONS   = "us,eu"
DEFAULT_SNAPSHOTS = ["17:00", "23:30"]
REQUEST_DELAY     = 1.0

# Season label = year the MLB season started.
# 2023 start capped at the spec-documented API floor (probe may find earlier data).
# 2026 end = today - 1 (yesterday's games are the latest with settled props).
_today = date.today()
SEASON_RANGES: dict[int, tuple[date, date]] = {
    2023: (date(2023,  5,  3), date(2023, 11,  4)),  # E5.1 spec floor; WS ends ~Nov 1
    2024: (date(2024,  3, 20), date(2024, 11,  2)),  # Opening Day 3/20; WS ends Nov 2
    2025: (date(2025,  3, 27), date(2025, 11,  5)),  # Opening Day 3/27; WS ends ~Nov 4 est.
    2026: (date(2026,  3, 26), _today - timedelta(days=1)),
}

# Probe candidates: (season_label, probe_date).
# All fall on mid-week game days (weekday, mid-season) to avoid off-days.
# 2021/2022 test whether the API floor pre-dates the 2023-05-03 spec cutoff.
PROBE_CANDIDATES: list[tuple[int, date]] = [
    (2021, date(2021,  6, 16)),  # Wednesday mid-2021
    (2022, date(2022,  6, 15)),  # Wednesday mid-2022
    (2023, date(2023,  4,  5)),  # Wednesday early-2023 (before spec cutoff)
    (2023, date(2023,  5,  3)),  # The E5.1 spec floor date
    (2023, date(2023,  6,  7)),  # Wednesday safely after the floor
    (2024, date(2024,  6, 12)),  # Wednesday mid-2024 (recent full-season check)
]

# Credit surplus as of 2026-06-23 (from MS.0 run report)
CREDIT_SURPLUS = 3_770_000
# Reserve buffer — E5.1 + MS.2 share the same pool; leave room for MS.2
CREDIT_RESERVE  = 500_000


# ── S3 helpers ─────────────────────────────────────────────────────────────────

def make_s3_client():
    return boto3.client("s3", region_name=AWS_REGION)


def s3_key(market_key: str, season: int, game_date: date) -> str:
    return f"{S3_PREFIX}/market={market_key}/season={season}/date={game_date}/data.parquet"


def scan_existing_s3_partitions(s3_client, market_key: str) -> set[tuple[int, str]]:
    """Return set of (season, date_str) already written for *market_key*."""
    existing: set[tuple[int, str]] = set()
    prefix = f"{S3_PREFIX}/market={market_key}/"
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
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


def write_to_s3(s3_client, df: pd.DataFrame, market_key: str, season: int, game_date: date) -> None:
    key   = s3_key(market_key, season, game_date)
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


def fetch_historical_props(
    snapshot_ts: str,
    markets: str,
    regions: str,
    date_obj: date,
    sleep_seconds: float,
) -> tuple[list[dict], int | None, int | None]:
    """
    Fetch historical MLB odds at *snapshot_ts* scoped to *date_obj* games.

    Uses the standard historical odds endpoint with prop market keys.
    commenceTimeFrom/To restrict the response to events on *date_obj*
    (00:00 UTC → next-day 07:00 UTC covers all mainland US time zones,
    including late Pacific games starting ~10pm ET = 02:00 UTC next day).

    Returns (events, credits_used, credits_remaining).
    Empty list on 404.  Exits on 401/403/429.
    """
    url = f"{ODDS_API_BASE_URL}/historical/sports/{SPORT}/odds"

    day_start = datetime(date_obj.year, date_obj.month, date_obj.day, 0, 0, 0, tzinfo=timezone.utc)
    next_day  = date_obj + timedelta(days=1)
    day_end   = datetime(next_day.year, next_day.month, next_day.day, 7, 0, 0, tzinfo=timezone.utc)

    params = {
        "apiKey":           _get_api_key(),
        "date":             snapshot_ts,
        "regions":          regions,
        "markets":          markets,
        "oddsFormat":       "american",
        "commenceTimeFrom": _iso_utc(day_start),
        "commenceTimeTo":   _iso_utc(day_end),
    }

    log.debug("  GET %s  snapshot=%s  markets=%s  regions=%s",
              url, snapshot_ts, markets, regions)

    try:
        resp = requests.get(url, params=params, timeout=30)
    except requests.RequestException as exc:
        log.warning("  Request error: %s — treating as empty", exc)
        time.sleep(sleep_seconds)
        return [], None, None

    used      = _parse_int_header(resp.headers.get("x-requests-used"))
    remaining = _parse_int_header(resp.headers.get("x-requests-remaining"))

    if resp.status_code in (401, 403):
        print(f"\nFATAL: HTTP {resp.status_code} — check ODDS_API_KEY / plan tier.",
              file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 429:
        print("\nFATAL: HTTP 429 — rate limit.  Re-run with --sleep-seconds 2.\n",
              file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 404:
        log.debug("  snapshot=%s  status=404", snapshot_ts)
        time.sleep(sleep_seconds)
        return [], used, remaining

    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        log.warning("  HTTP error %s  body=%.300s", exc, resp.text)
        time.sleep(sleep_seconds)
        return [], used, remaining

    payload = resp.json()
    events  = (
        payload.get("data", []) if isinstance(payload, dict)
        else (payload if isinstance(payload, list) else [])
    )

    log.debug("  snapshot=%s  events=%d  credits_used=%s  remaining=%s",
              snapshot_ts, len(events), used, remaining)
    time.sleep(sleep_seconds)
    return events, used, remaining


# ── Row extraction ─────────────────────────────────────────────────────────────

def _pivot_prop_outcomes(outcomes: list[dict]) -> dict[str, dict]:
    """
    Pivot Over/Under outcome pairs into {player_name: {line, over_price, under_price}}.

    Each player prop market has paired outcomes with the same 'description'
    (player name) and 'point' (line).  Unpaired outcomes (only over or only
    under) are retained with None for the missing side.
    """
    players: dict[str, dict] = {}
    for o in outcomes:
        side   = (o.get("name") or "").strip().lower()
        player = (o.get("description") or "").strip()
        if not player:
            continue
        if player not in players:
            players[player] = {"line": None, "over_price": None, "under_price": None}
        line = o.get("point")
        if line is not None:
            players[player]["line"] = float(line)
        if side == "over":
            players[player]["over_price"] = o.get("price")
        elif side == "under":
            players[player]["under_price"] = o.get("price")
    return players


def props_to_rows(
    events: list[dict],
    season: int,
    snapshot_ts: str,
    load_id: str,
    ingested_at: str,
) -> dict[str, list[dict]]:
    """
    Extract player prop rows from API events.

    Returns dict[market_key → list[row]] so the caller can write separate
    S3 partitions per market without re-fetching.  One row per
    (event × bookmaker × player); line/over_price/under_price columns.
    """
    by_market: dict[str, list[dict]] = {}

    for event in events:
        home_team     = event.get("home_team", "")
        away_team     = event.get("away_team", "")
        commence_time = event.get("commence_time", "")
        event_id      = event.get("id", "")

        for bk in event.get("bookmakers", []):
            bk_key   = bk.get("key", "")
            bk_title = bk.get("title", "")

            for market in bk.get("markets", []):
                market_key = market.get("key", "")
                outcomes   = market.get("outcomes", [])
                if not market_key or not outcomes:
                    continue

                for player_name, vals in _pivot_prop_outcomes(outcomes).items():
                    if vals["over_price"] is None and vals["under_price"] is None:
                        continue  # no usable pricing

                    row = {
                        "sport":           SPORT,
                        "season":          season,
                        "event_id":        event_id,
                        "commence_time":   commence_time,
                        "home_team":       home_team,
                        "away_team":       away_team,
                        "snapshot_ts":     snapshot_ts,
                        "bookmaker_key":   bk_key,
                        "bookmaker_title": bk_title,
                        "market_key":      market_key,
                        "player_name":     player_name,
                        "line":            vals["line"],
                        "over_price":      vals["over_price"],
                        "under_price":     vals["under_price"],
                        "load_id":         load_id,
                        "ingested_at":     ingested_at,
                    }
                    by_market.setdefault(market_key, []).append(row)

    return by_market


# ── Date iterator ──────────────────────────────────────────────────────────────

def date_range(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ── Dry-run budget estimator ───────────────────────────────────────────────────

def print_budget_estimate(
    markets: str,
    regions: str,
    snapshots: list[str],
    measured_credits_per_call: int | None = None,
) -> None:
    n_markets        = len([m for m in markets.split(",") if m.strip()])
    n_regions        = len([r for r in regions.split(",") if r.strip()])
    estimated_cr     = 10 * n_markets * n_regions
    credits_per_call = measured_credits_per_call if measured_credits_per_call else estimated_cr
    label            = "(measured)" if measured_credits_per_call else "(estimated: 10 × markets × regions)"

    print("\n── CREDIT BUDGET ESTIMATE ─────────────────────────────────────")
    print(f"  Sport           : {SPORT}")
    print(f"  Markets         : {markets}  ({n_markets})")
    print(f"  Regions         : {regions}  ({n_regions})")
    print(f"  Snapshots/date  : {', '.join(snapshots)} UTC  ({len(snapshots)} calls/date)")
    print(f"  Credits/call    : {credits_per_call}  {label}")
    print(f"  Credits/date    : {credits_per_call * len(snapshots)}")
    print()

    grand_days = grand_calls = 0
    print("  Seasons:")
    for season, (start, end) in sorted(SEASON_RANGES.items()):
        n = (end - start).days + 1
        s_calls   = n * len(snapshots)
        s_credits = s_calls * credits_per_call
        grand_days  += n
        grand_calls += s_calls
        print(f"    {season}: {start} → {end}  ({n} cal-days, ~{s_credits:,} credits)")

    grand_credits  = grand_calls * credits_per_call
    active_pct     = 0.75  # MLB has games ~75% of cal-days during the season
    active_credits = int(grand_days * active_pct) * len(snapshots) * credits_per_call

    print()
    print(f"  Total calendar dates : {grand_days:,}")
    print(f"  Total API calls      : {grand_calls:,}  (worst-case, all cal-days)")
    print(f"  Credits (worst-case) : {grand_credits:,}")
    print(f"  Credits (est. actual): ~{active_credits:,}  (~{int(active_pct*100)}% of days have games)")
    print()
    available = CREDIT_SURPLUS - CREDIT_RESERVE
    print(f"  Credit surplus       : ~{CREDIT_SURPLUS:,}  (as of 2026-06-23)")
    print(f"  Reserve for MS.2     : {CREDIT_RESERVE:,}  (multi-sport props)")
    print(f"  Available for E5.1   : ~{available:,}")
    go_nogo = "✓ GO" if active_credits <= available else "✗ CAUTION — may exceed available budget"
    print(f"  Go/No-go             : {go_nogo}")
    print(f"  Post-E5.1 surplus    : ~{CREDIT_SURPLUS - active_credits:,}  (worst-case active-days)")
    print(f"  Cutoff               : 2026-07-17 (5M → 100K/month drop)")
    print()


# ── Probe mode ─────────────────────────────────────────────────────────────────

def run_probe(sleep_seconds: float) -> None:
    """
    PHASE 0 — confirm historical MLB player props availability.

    Step 1: cheap calls (1 market × 1 region = 10 cr each) across candidate
            dates to confirm props exist, find the earliest date, enumerate
            events, and note whether any bookmakers carry prop markets.

    Step 2: one full-cost call (all 5 markets × 2 regions) on a known-good
            date to (a) enumerate all market keys returned, (b) measure the
            actual credits charged via the x-requests-remaining delta.

    Step 3: project the full backfill cost using the measured per-call cost
            and report go/no-go against the available credit budget.

    If no historical prop data is found at all, STOP and report — props from
    The Odds API may not exist (as was the case for F5 / halftime lines).
    """
    _get_api_key()

    print("\n══ MLB PLAYER PROPS — PHASE 0 PROBE ══════════════════════════════")
    print(f"  Sport    : {SPORT}")
    print(f"  Markets  : pitcher_strikeouts  (cheap probe)")
    print(f"  Regions  : us  (10 credits/call)")
    print()
    print("Step 1 — candidate date sweep")
    print("-" * 60)

    total_probe_calls  = 0
    found: list[tuple[int, date, int]] = []   # (season_label, probe_date, n_events)
    last_remaining: int | None = None

    for season_label, probe_date in PROBE_CANDIDATES:
        snapshot_ts = f"{probe_date}T17:00:00Z"
        events, _, remaining = fetch_historical_props(
            snapshot_ts   = snapshot_ts,
            markets       = "pitcher_strikeouts",
            regions       = "us",
            date_obj      = probe_date,
            sleep_seconds = sleep_seconds,
        )
        total_probe_calls += 1
        if remaining is not None:
            last_remaining = remaining

        n_events = len(events)
        # Count games that have at least one bookmaker offering pitcher_strikeouts
        games_with_props = sum(
            1 for ev in events
            if any(
                mk.get("key") == "pitcher_strikeouts"
                for bk in ev.get("bookmakers", [])
                for mk in bk.get("markets", [])
            )
        )
        # Rough player count (unique player names in pitcher_strikeouts outcomes)
        player_names: set[str] = set()
        for ev in events:
            for bk in ev.get("bookmakers", []):
                for mk in bk.get("markets", []):
                    if mk.get("key") == "pitcher_strikeouts":
                        for o in mk.get("outcomes", []):
                            desc = (o.get("description") or "").strip()
                            if desc:
                                player_names.add(desc)

        if n_events > 0:
            status = (f"✓  events={n_events}  games_w/props={games_with_props}"
                      f"  ~{len(player_names)} players  remaining={remaining}")
            found.append((season_label, probe_date, n_events))
        else:
            status = f"✗  no data (404 or empty response)  remaining={remaining}"

        print(f"  {probe_date}  (season {season_label})  →  {status}")

    print()
    print(f"Step 1 complete: {total_probe_calls} calls  (~{total_probe_calls * 10} credits)")
    print()

    # ── No data found at all ───────────────────────────────────────────────────
    if not found:
        print("=" * 65)
        print("RESULT: The Odds API does NOT offer historical MLB player props.")
        print()
        print("E5.1 historical backfill is BLOCKED on this data source.")
        print("This is a real finding, not a failure.")
        print()
        print("Next steps:")
        print("  • Alternative sources (paid): Sportradar, StatsPerform,")
        print("    Action Network PRO, or a sports-data broker.")
        print("  • Scope as E2.0c-style story (evaluate free/paid alt source).")
        print("  • Update build_roadmap.md: E5.1 → BLOCKED.")
        print("=" * 65)
        return

    # ── Data found: run Step 2 full-market enumeration ────────────────────────
    earliest = min(d for _, d, _ in found)
    print(f"Earliest date with data : {earliest}")
    print()

    # Use the most recent known-good date for the full-market call
    ref_season, ref_date, _ = max(found, key=lambda t: t[1])
    snap_ts = f"{ref_date}T17:00:00Z"

    print("Step 2 — full-market enumeration")
    print("-" * 60)
    print(f"  Date     : {ref_date}  (season {ref_season})")
    print(f"  Markets  : {DEFAULT_MARKETS}")
    print(f"  Regions  : {DEFAULT_REGIONS}")
    print(f"  Estimated cost : ~{10 * len(PHASE1_MARKETS) * 2} credits")
    print()

    remaining_before_full = last_remaining
    full_events, _, full_remaining = fetch_historical_props(
        snapshot_ts   = snap_ts,
        markets       = DEFAULT_MARKETS,
        regions       = DEFAULT_REGIONS,
        date_obj      = ref_date,
        sleep_seconds = sleep_seconds,
    )
    total_probe_calls += 1

    # Measure actual credit cost from the header delta
    if remaining_before_full is not None and full_remaining is not None:
        measured_credits = remaining_before_full - full_remaining
    else:
        n_m = len(PHASE1_MARKETS)
        n_r = len([r for r in DEFAULT_REGIONS.split(",") if r.strip()])
        measured_credits = 10 * n_m * n_r
        print("  WARNING: could not measure credit cost from headers; using estimate.")

    # Enumerate all market keys and bookmakers returned
    markets_found: dict[str, set[str]] = {}
    bookmakers_found: set[str] = set()
    for ev in full_events:
        for bk in ev.get("bookmakers", []):
            bookmakers_found.add(bk.get("key", ""))
            for mk in bk.get("markets", []):
                mk_key = mk.get("key", "")
                markets_found.setdefault(mk_key, set()).add(bk.get("key", ""))

    print(f"  Events returned  : {len(full_events)}")
    print(f"  Bookmakers seen  : {len(bookmakers_found)}  ({', '.join(sorted(bookmakers_found))})")
    print(f"  Measured cost    : {measured_credits} credits  (from x-requests-remaining delta)")
    print(f"  Remaining after  : {full_remaining:,}" if full_remaining else "  Remaining after  : unknown")
    print()

    if markets_found:
        print("  Markets returned:")
        for mk, books in sorted(markets_found.items()):
            books_str = ", ".join(sorted(books)[:6])
            extra     = "…" if len(books) > 6 else ""
            print(f"    {mk:<40}  {len(books)} books  ({books_str}{extra})")
    else:
        print("  WARNING: no prop markets found in this response.")
        print("  The API returned events but no prop lines at this snapshot.")
        print("  Try a different snapshot time (23:30 UTC) or a different date.")
    print()

    # ── Step 3: project full backfill cost ────────────────────────────────────
    credits_per_call = max(measured_credits, 1)

    print("Step 3 — full backfill credit projection")
    print("-" * 60)
    print_budget_estimate(
        markets                   = DEFAULT_MARKETS,
        regions                   = DEFAULT_REGIONS,
        snapshots                 = DEFAULT_SNAPSHOTS,
        measured_credits_per_call = credits_per_call,
    )

    # Compute active-days estimate for go/no-go
    total_days  = sum((end - start).days + 1 for start, end in SEASON_RANGES.values())
    active_days = int(total_days * 0.75)
    proj_credits = active_days * len(DEFAULT_SNAPSHOTS) * credits_per_call
    available    = CREDIT_SURPLUS - CREDIT_RESERVE

    print("── PROBE SUMMARY ──────────────────────────────────────────────────")
    print(f"  Earliest data date   : {earliest}")
    print(f"  Data pre-dates spec  : {'YES — update SEASON_RANGES start!' if earliest < date(2023, 5, 3) else 'No (2023-05-03 floor confirmed)'}")
    print(f"  Markets confirmed    : {', '.join(sorted(markets_found.keys())) or 'NONE'}")
    print(f"  Measured cr/call     : {credits_per_call}")
    print(f"  Projected total      : ~{proj_credits:,} credits  (active-days estimate)")
    print(f"  Available budget     : ~{available:,} credits  ({CREDIT_SURPLUS:,} − {CREDIT_RESERVE:,} reserve)")

    if not markets_found:
        print()
        print("  GO/NO-GO: ✗ HOLD — no prop markets were returned by the API.")
        print("  Run with --mode probe again at a different date/snapshot, or")
        print("  declare E5.1 BLOCKED (The Odds API has no historical MLB props).")
    elif proj_credits <= available:
        print()
        print("  GO/NO-GO: ✓ GO — projected cost fits within the available budget.")
        print()
        print("  Next step — hand the full backfill to the operator:")
        print(f"    uv run scripts/backfill_mlb_props_to_s3.py --mode backfill")
        if earliest < date(2023, 5, 3):
            print()
            print(f"  TIP: data exists before 2023-05-03.  Update SEASON_RANGES[2023] start")
            print(f"  from date(2023, 5, 3) to date({earliest.year}, {earliest.month}, {earliest.day})")
            print(f"  (or the earliest MLB Opening Day that precedes {earliest}) to capture")
            print(f"  more historical data before re-running the backfill.")
    else:
        print()
        print("  GO/NO-GO: ✗ CAUTION — projected cost may exceed available budget.")
        print("  Options:")
        print("    1. Narrow to 3 priority markets:")
        print("       --markets pitcher_strikeouts,batter_total_bases,batter_home_runs")
        print("    2. Drop Pinnacle (eu region) to save ~50% credits:")
        print("       --regions us")
        print("    3. Reduce to 1 snapshot per day (closing only):")
        print("       --snapshots 23:30")
        print("    Re-run --dry-run after adjusting to re-project.")

    print()
    print(f"  Total probe API calls : {total_probe_calls}  (~{total_probe_calls * 10} credits est.)")
    print()
    print("Commit this output as the probe report before running the backfill.")
    print()


# ── Main backfill ──────────────────────────────────────────────────────────────

def run_backfill(
    markets: str,
    regions: str,
    snapshots: list[str],
    sleep_seconds: float,
    force: bool,
    limit: int | None,
) -> None:
    markets_list     = [m.strip() for m in markets.split(",") if m.strip()]
    n_markets        = len(markets_list)
    n_regions        = len([r for r in regions.split(",") if r.strip()])
    credits_per_call = 10 * n_markets * n_regions

    s3          = make_s3_client()
    load_id     = str(uuid.uuid4())
    ingested_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Pre-scan existing partitions (one ListObjects pass per market)
    if not force:
        log.info("Scanning S3 for existing partitions (%d markets)...", len(markets_list))
        existing: dict[str, set[tuple[int, str]]] = {
            mk: scan_existing_s3_partitions(s3, mk) for mk in markets_list
        }
        log.info("  Existing: %s", {mk: len(v) for mk, v in existing.items()})
    else:
        existing = {mk: set() for mk in markets_list}
        log.info("--force: bypassing idempotency check")

    total_calls    = 0
    total_rows     = 0
    total_written  = 0
    total_skipped  = 0
    limit_reached  = False
    last_remaining: int | None = None
    season_summary: dict[int, dict] = {}

    for season, (season_start, season_end) in sorted(SEASON_RANGES.items()):
        if limit_reached:
            break

        log.info("\n══ Season %d: %s → %s ══", season, season_start, season_end)
        s_written = s_skipped = s_rows = 0

        for game_date in date_range(season_start, season_end):
            if limit_reached:
                break

            date_str = str(game_date)

            # Skip dates where ALL markets already exist
            missing = [
                mk for mk in markets_list
                if (season, date_str) not in existing.get(mk, set())
            ]
            if not missing:
                s_skipped += 1
                total_skipped += 1
                continue

            # Fetch all markets in one call per snapshot
            date_rows_by_market: dict[str, list[dict]] = {mk: [] for mk in markets_list}

            for snap_time in snapshots:
                if limit is not None and total_calls >= limit:
                    limit_reached = True
                    log.info("--limit %d reached — stopping early", limit)
                    break

                snapshot_ts = f"{date_str}T{snap_time}:00Z"
                events, _, remaining = fetch_historical_props(
                    snapshot_ts   = snapshot_ts,
                    markets       = markets,
                    regions       = regions,
                    date_obj      = game_date,
                    sleep_seconds = sleep_seconds,
                )
                total_calls += 1
                if remaining is not None:
                    last_remaining = remaining

                if events:
                    rows_by_mk = props_to_rows(
                        events      = events,
                        season      = season,
                        snapshot_ts = snapshot_ts,
                        load_id     = load_id,
                        ingested_at = ingested_at,
                    )
                    for mk, rows in rows_by_mk.items():
                        if mk in date_rows_by_market:
                            date_rows_by_market[mk].extend(rows)

                    n_players = sum(len(v) for v in rows_by_mk.values())
                    log.info("  %s %s  events=%d  player_rows=%d  remaining=%s",
                             date_str, snap_time, len(events), n_players, remaining)

            # Write only missing-market partitions for this date
            for mk in missing:
                rows = date_rows_by_market.get(mk, [])
                if rows:
                    df = pd.DataFrame(rows)
                    df = df.drop_duplicates(
                        subset=["event_id", "snapshot_ts", "bookmaker_key", "player_name"]
                    )
                    write_to_s3(s3, df, mk, season, game_date)
                    s_rows    += len(df)
                    total_rows += len(df)
                    s_written  += 1
                    total_written += 1
                else:
                    log.debug("  %s %s — no rows", date_str, mk)

        season_summary[season] = {"written": s_written, "skipped": s_skipped, "rows": s_rows}
        log.info("  Season %d done: %d partitions written / %d skipped / %d rows",
                 season, s_written, s_skipped, s_rows)

    # ── Coverage report ────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("MLB PROPS BACKFILL — COVERAGE REPORT")
    print("=" * 65)
    print(f"  Load ID             : {load_id}")
    print(f"  Ingested at         : {ingested_at}")
    print(f"  Sport               : {SPORT}")
    print(f"  Markets             : {markets}")
    print(f"  Regions             : {regions}")
    print(f"  Snapshots/date      : {', '.join(snapshots)} UTC")
    print(f"  Credits/API call    : {credits_per_call}  (estimated; actual from x-requests-last)")
    print(f"  Total API calls     : {total_calls:,}")
    print(f"  Est. credits spent  : ~{total_calls * credits_per_call:,}")
    if last_remaining is not None:
        print(f"  Credits remaining   : {last_remaining:,}  (x-requests-remaining)")
    print()
    for season, s in sorted(season_summary.items()):
        print(f"  Season {season}:  "
              f"written={s['written']:>6}  skipped={s['skipped']:>6}  rows={s['rows']:>10,}")
    print()
    print(f"  Total partitions written : {total_written:,}")
    print(f"  Total rows               : {total_rows:,}")
    print()
    print(f"  S3 location: s3://{BUCKET}/{S3_PREFIX}/")
    print()
    print("  DuckDB validation:")
    print(f"    duckdb -c \"SELECT market_key, season,")
    print(f"               COUNT(DISTINCT date) AS dates, COUNT(*) AS rows")
    print(f"               FROM read_parquet('s3://{BUCKET}/{S3_PREFIX}/**/*.parquet')")
    print(f"               GROUP BY 1, 2 ORDER BY 1, 2\"")
    print()
    print("  Per-market row check:")
    for mk in markets_list:
        print(f"    duckdb -c \"SELECT season, COUNT(DISTINCT date) AS dates, COUNT(*) AS rows,")
        print(f"               COUNT(DISTINCT player_name) AS players")
        print(f"               FROM read_parquet('s3://{BUCKET}/{S3_PREFIX}/market={mk}/**/*.parquet')")
        print(f"               GROUP BY 1 ORDER BY 1\"")
    print()


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Backfill historical MLB player prop lines from The Odds API → S3 Parquet.  "
            "Zero Snowflake writes.  Run --mode probe FIRST to confirm availability + cost."
        )
    )
    p.add_argument(
        "--mode",
        default="probe",
        choices=["probe", "backfill"],
        help=(
            "probe: confirm prop availability, enumerate markets, measure credit cost, "
            "project full cost, report go/no-go (~70 credits — MANDATORY FIRST STEP).  "
            "backfill: run full historical backfill (long-running; hand to operator)."
        ),
    )
    p.add_argument(
        "--markets",
        default=DEFAULT_MARKETS,
        metavar="MARKETS",
        help=f"Comma-separated prop market keys (default: {DEFAULT_MARKETS}).",
    )
    p.add_argument(
        "--regions",
        default=DEFAULT_REGIONS,
        metavar="REGIONS",
        help=(
            f"Comma-separated region keys (default: {DEFAULT_REGIONS}).  "
            "Cost = 10 × markets × regions per call.  'eu' adds Pinnacle (sharp reference)."
        ),
    )
    p.add_argument(
        "--snapshots",
        default=",".join(DEFAULT_SNAPSHOTS),
        metavar="HH:MM,...",
        help=(
            f"Comma-separated UTC snapshot times per date "
            f"(default: {','.join(DEFAULT_SNAPSHOTS)}).  "
            "17:00Z = noon ET (day games); 23:30Z = 6:30pm ET (evening games)."
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
        help="Re-fetch partitions already in S3 (bypasses idempotency).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N total API calls (useful for quick diagnostic runs).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Estimate credits from SEASON_RANGES and exit without API calls or S3 writes.",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    snapshots = [s.strip() for s in args.snapshots.split(",") if s.strip()]
    if not snapshots:
        print("ERROR: --snapshots is empty.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print_budget_estimate(args.markets, args.regions, snapshots)
        return

    if args.mode == "probe":
        run_probe(args.sleep_seconds)
    else:
        run_backfill(
            markets       = args.markets,
            regions       = args.regions,
            snapshots     = snapshots,
            sleep_seconds = args.sleep_seconds,
            force         = args.force,
            limit         = args.limit,
        )


if __name__ == "__main__":
    main()
