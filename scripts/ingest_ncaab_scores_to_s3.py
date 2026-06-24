"""
ingest_ncaab_scores_to_s3.py
------------------------------
Pull NCAAB game outcomes (2020–2025) from ESPN's unofficial scoreboard API
(no key required) and write Hive-partitioned Parquet to S3.
Zero Snowflake writes, zero Odds API credits.

S3 layout:
    s3://baseball-betting-ml-artifacts/
        ncaab/scores/season={season}/date={game_date}/data.parquet

Schema:
    sport, season, game_date, source_event_id,
    home_team_source, away_team_source,   # ESPN displayName ("Duke Blue Devils")
    home_team_odds, away_team_odds,        # mapped Odds API name (nullable via crosswalk)
    home_score, away_score, winner,
    completed, neutral_site,
    home_h1, home_h2, home_ot,           # half + OT scores from ESPN linescores
    away_h1, away_h2, away_ot,
    period_scores_json,
    load_id, ingested_at

Crosswalk strategy:
    ESPN displayName is typically "School Mascot" (matches Odds API format).
    A static correction dict handles known mismatches (UConn, Louisiana, etc.).
    The --validate report shows join coverage once both datasets are in S3.

ESPN endpoint (unofficial, no auth):
    https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard
    ?dates=YYYYMMDD&limit=200&groups=50  (groups=50 = Division I)

Rate-limiting: ~0.3s sleep between requests; ~150 days/season × 5 seasons = ~750 calls.

Usage:
    uv run scripts/ingest_ncaab_scores_to_s3.py
    uv run scripts/ingest_ncaab_scores_to_s3.py --season 2023
    uv run scripts/ingest_ncaab_scores_to_s3.py --dry-run
    uv run scripts/ingest_ncaab_scores_to_s3.py --validate

Environment (.env in repo root):
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
"""

import argparse
import io
import json
import logging
import os
import sys
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

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

ESPN_BASE  = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
BUCKET     = "baseball-betting-ml-artifacts"
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-2")
SPORT      = "basketball_ncaab"
ODDS_S3    = "ncaab/odds"
SCORES_S3  = "ncaab/scores"
SLEEP_S    = 0.3

# Season ranges: label = year season started (2020 = 2020-21 season)
SEASON_RANGES: dict[int, tuple[date, date]] = {
    2020: (date(2020, 11, 25), date(2021,  4,  5)),
    2021: (date(2021, 11,  9), date(2022,  4,  4)),
    2022: (date(2022, 11,  7), date(2023,  4,  3)),
    2023: (date(2023, 11,  6), date(2024,  4,  8)),
    2024: (date(2024, 11,  4), date(2025,  4,  7)),
    2025: (date(2025, 11,  3), date(2026,  4,  6)),
}

# ESPN displayName → Odds API team name corrections.
# Only needed where they differ; most match exactly.
ESPN_CROSSWALK: dict[str, str] = {
    # UConn is often "Connecticut" in Odds API
    "Connecticut Huskies":                   "Connecticut Huskies",   # ESPN matches
    "UConn Huskies":                         "Connecticut Huskies",
    "Connecticut":                           "Connecticut Huskies",
    # Louisiana schools
    "Louisiana Ragin' Cajuns":               "Louisiana Ragin' Cajuns",
    "Louisiana-Lafayette Ragin' Cajuns":     "Louisiana Ragin' Cajuns",
    "UL Monroe Warhawks":                    "Louisiana Monroe Warhawks",
    "Louisiana Monroe Warhawks":             "Louisiana Monroe Warhawks",
    # Abbreviation-style schools
    "UTEP Miners":                           "UTEP Miners",
    "UTSA Roadrunners":                      "UTSA Roadrunners",
    "UAB Blazers":                           "UAB Blazers",
    "VCU Rams":                              "VCU Rams",
    "SMU Mustangs":                          "SMU Mustangs",
    "TCU Horned Frogs":                      "TCU Horned Frogs",
    "BYU Cougars":                           "BYU Cougars",
    "LMU Lions":                             "Loyola Marymount Lions",
    # Long name edge cases
    "Loyola Chicago Ramblers":               "Loyola Chicago Ramblers",
    "Loyola (IL) Ramblers":                  "Loyola Chicago Ramblers",
    "Saint Mary's Gaels":                    "Saint Mary's (CA) Gaels",
    "Saint Mary's (CA) Gaels":              "Saint Mary's (CA) Gaels",
    "Hawai'i Rainbow Warriors":              "Hawaii Rainbow Warriors",
    "Hawaii Rainbow Warriors":               "Hawaii Rainbow Warriors",
    "Illinois-Chicago Flames":               "UIC Flames",
    "Appalachian State Mountaineers":        "Appalachian State Mountaineers",
    "Cal Poly Mustangs":                     "Cal Poly Mustangs",
    "Miami Hurricanes":                      "Miami (FL) Hurricanes",   # Odds API disambiguates
    "North Carolina State Wolfpack":         "NC State Wolfpack",
    "NC State Wolfpack":                     "NC State Wolfpack",
    "Texas A&M-Corpus Christi Islanders":   "Texas A&M Corpus Christi Islanders",
    "USC Trojans":                           "USC Trojans",
    "Pittsburgh Panthers":                   "Pittsburgh Panthers",
    "Penn State Nittany Lions":              "Penn State Nittany Lions",
    "Ole Miss Rebels":                       "Ole Miss Rebels",
    "Mississippi Rebels":                    "Ole Miss Rebels",
    "FGCU Eagles":                           "Florida Gulf Coast Eagles",
    "Florida Gulf Coast Eagles":             "Florida Gulf Coast Eagles",
    "UC Santa Barbara Gauchos":              "UC Santa Barbara Gauchos",
    "UCSB Gauchos":                          "UC Santa Barbara Gauchos",
    "Long Beach State 49ers":                "Long Beach State 49ers",
    "Cal State Fullerton Titans":            "Cal State Fullerton Titans",
    "LIU Sharks":                            "LIU Sharks",
    "Robert Morris Colonials":               "Robert Morris Colonials",
    "SIU Edwardsville Cougars":              "SIUE Cougars",
    "SIUE Cougars":                          "SIUE Cougars",
}


def _map_team(espn_name: str) -> str:
    """Return the Odds API name for an ESPN displayName; falls back to raw name."""
    return ESPN_CROSSWALK.get(espn_name, espn_name)


# ── S3 helpers ──────────────────────────────────────────────────────────────────

def make_s3():
    return boto3.client("s3", region_name=AWS_REGION)


def _scores_key(season: int, game_date: str) -> str:
    return f"{SCORES_S3}/season={season}/date={game_date}/data.parquet"


def existing_s3_dates(s3) -> set[tuple[int, str]]:
    found: set[tuple[int, str]] = set()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=f"{SCORES_S3}/"):
        for obj in page.get("Contents", []):
            key   = obj["Key"]
            parts = key.split("/")
            sp    = next((p for p in parts if p.startswith("season=")), None)
            dp    = next((p for p in parts if p.startswith("date=")),   None)
            if sp and dp:
                try:
                    found.add((int(sp[len("season="):]), dp[len("date="):]))
                except ValueError:
                    pass
    return found


def write_parquet(s3, df: pd.DataFrame, key: str) -> None:
    table = pa.Table.from_pandas(df, preserve_index=False)
    buf   = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)
    s3.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())
    log.info("  Wrote %d rows → s3://%s/%s", len(df), BUCKET, key)


# ── ESPN fetch ───────────────────────────────────────────────────────────────────

def fetch_day(game_date: date, max_retries: int = 4) -> list[dict]:
    """Fetch all NCAAB games from ESPN for one calendar date (with exponential backoff)."""
    date_str = game_date.strftime("%Y%m%d")
    params   = {"dates": date_str, "limit": 300, "groups": 50}  # groups=50 = Division I

    for attempt in range(max_retries):
        try:
            resp = requests.get(ESPN_BASE, params=params, timeout=30)
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                log.warning("  ESPN request error on %s (attempt %d/%d): %s — retry in %ds",
                            game_date, attempt + 1, max_retries, e, wait)
                time.sleep(wait)
                continue
            log.warning("  ESPN request error on %s (gave up): %s", game_date, e)
            time.sleep(SLEEP_S)
            return []

        if resp.status_code == 404:
            time.sleep(SLEEP_S)
            return []

        if resp.status_code in (500, 502, 503, 504):
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                log.warning("  ESPN HTTP %s on %s (attempt %d/%d) — retry in %ds",
                            resp.status_code, game_date, attempt + 1, max_retries, wait)
                time.sleep(wait)
                continue
            log.warning("  ESPN HTTP %s on %s (gave up after %d attempts)",
                        resp.status_code, game_date, max_retries)
            time.sleep(SLEEP_S)
            return []

        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            log.warning("  ESPN HTTP %s on %s", e, game_date)
            time.sleep(SLEEP_S)
            return []

        time.sleep(SLEEP_S)
        return resp.json().get("events", [])

    return []


def _parse_linescore(ls: list) -> list[Optional[int]]:
    """Parse ESPN linescores list of {value} dicts."""
    out = []
    for entry in ls:
        try:
            out.append(int(float(entry.get("value", entry))))
        except (TypeError, ValueError):
            out.append(None)
    return out


def event_to_row(event: dict, season: int, game_date: str,
                 load_id: str, ingested_at: str) -> Optional[dict]:
    competitions = event.get("competitions", [])
    if not competitions:
        return None
    comp = competitions[0]

    status    = comp.get("status", {})
    completed = bool(status.get("type", {}).get("completed", False))

    competitors = comp.get("competitors", [])
    if len(competitors) < 2:
        return None

    home_comp = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
    away_comp = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

    home_name = home_comp.get("team", {}).get("displayName", "")
    away_name = away_comp.get("team", {}).get("displayName", "")

    try:
        home_score: Optional[int] = int(home_comp["score"]) if completed else None
        away_score: Optional[int] = int(away_comp["score"]) if completed else None
    except (KeyError, ValueError, TypeError):
        home_score = away_score = None
        completed  = False

    winner = None
    if completed and home_score is not None and away_score is not None:
        if home_score > away_score:
            winner = "home"
        elif away_score > home_score:
            winner = "away"
        else:
            winner = "tie"

    # Half scores from linescores (index 0 = H1, 1 = H2, 2+ = OT)
    home_ls = _parse_linescore(home_comp.get("linescores", []))
    away_ls = _parse_linescore(away_comp.get("linescores", []))

    def _p(ls: list, idx: int) -> Optional[int]:
        return ls[idx] if idx < len(ls) else None

    period_scores = {"home": home_ls, "away": away_ls} if (home_ls or away_ls) else {}

    neutral_site = bool(comp.get("neutralSite", False))

    return {
        "sport":              SPORT,
        "season":             season,
        "game_date":          game_date,
        "source_event_id":    str(event.get("id", "")),
        "home_team_source":   home_name,
        "away_team_source":   away_name,
        "home_team_odds":     _map_team(home_name) if home_name else None,
        "away_team_odds":     _map_team(away_name) if away_name else None,
        "home_score":         home_score,
        "away_score":         away_score,
        "winner":             winner,
        "completed":          completed,
        "neutral_site":       neutral_site,
        "home_h1":            _p(home_ls, 0),
        "home_h2":            _p(home_ls, 1),
        "home_ot":            _p(home_ls, 2),
        "away_h1":            _p(away_ls, 0),
        "away_h2":            _p(away_ls, 1),
        "away_ot":            _p(away_ls, 2),
        "period_scores_json": json.dumps(period_scores) if period_scores else None,
        "load_id":            load_id,
        "ingested_at":        ingested_at,
    }


# ── Validate ────────────────────────────────────────────────────────────────────

def run_validate(seasons: list[int]) -> None:
    try:
        import duckdb
    except ImportError:
        print("duckdb not available", file=sys.stderr)
        return

    ak     = os.environ.get("AWS_ACCESS_KEY_ID", "")
    sk     = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    region = AWS_REGION
    con    = duckdb.connect()
    con.execute(f"CREATE SECRET aws_s3 (TYPE S3, KEY_ID '{ak}', SECRET '{sk}', REGION '{region}')")

    try:
        scores_count = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('s3://{BUCKET}/{SCORES_S3}/**/*.parquet')"
        ).fetchone()[0]
    except Exception as e:
        print(f"Scores not in S3 yet ({e})", file=sys.stderr)
        return

    try:
        result = con.execute(f"""
            WITH scores AS (
                SELECT DISTINCT season, game_date, home_team_odds, away_team_odds
                FROM read_parquet('s3://{BUCKET}/{SCORES_S3}/**/*.parquet')
                WHERE completed AND home_team_odds IS NOT NULL
            ),
            odds AS (
                SELECT DISTINCT season,
                    CAST(commence_time AS DATE) AS game_date,
                    home_team, away_team
                FROM read_parquet('s3://{BUCKET}/{ODDS_S3}/**/*.parquet')
            ),
            joined AS (
                SELECT o.season,
                    CASE WHEN s.game_date IS NOT NULL THEN 1 ELSE 0 END AS is_match
                FROM odds o
                LEFT JOIN scores s
                    ON o.season = s.season
                    AND o.game_date = s.game_date
                    AND o.home_team = s.home_team_odds
                    AND o.away_team = s.away_team_odds
            )
            SELECT season, COUNT(*) odds_games, SUM(is_match) matched_count,
                ROUND(100.0*SUM(is_match)/COUNT(*), 1) pct_matched
            FROM joined GROUP BY season ORDER BY season
        """).fetchdf()
    except Exception as e:
        print(f"Odds data not in S3 ({e}); scores rows = {scores_count}")
        return

    print("\n" + "=" * 55)
    print("NCAAB SCORES ↔ ODDS JOIN COVERAGE")
    print("=" * 55)
    print(result.to_string(index=False))
    t_odds  = result["odds_games"].sum()
    t_match = result["matched_count"].sum()
    print(f"\n  Overall: {t_match}/{t_odds} = {100*t_match/max(t_odds,1):.1f}%")
    print()


# ── Main ────────────────────────────────────────────────────────────────────────

def _date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def run(seasons: list[int], dry_run: bool) -> None:
    s3          = make_s3()
    load_id     = str(uuid.uuid4())
    ingested_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    log.info("Scanning S3 for existing score partitions …")
    existing = existing_s3_dates(s3)
    log.info("  %d date partitions already present", len(existing))

    total_written = total_skipped = total_games = 0

    for season in seasons:
        if season not in SEASON_RANGES:
            log.warning("Season %d not in SEASON_RANGES — skipping", season)
            continue

        season_start, season_end = SEASON_RANGES[season]
        log.info("\n── NCAAB Season %d (%s → %s) ──", season, season_start, season_end)

        by_date: dict[str, list[dict]] = defaultdict(list)
        n_days = (season_end - season_start).days + 1
        log.info("  Iterating %d calendar days …", n_days)

        for day in _date_range(season_start, season_end):
            date_str = str(day)
            if (season, date_str) in existing:
                total_skipped += 1
                continue

            events = fetch_day(day)
            if not events:
                continue

            for event in events:
                row = event_to_row(event, season, date_str, load_id, ingested_at)
                if row:
                    by_date[date_str].append(row)

        for game_date, rows in sorted(by_date.items()):
            total_games += len(rows)
            if dry_run:
                log.info("  DRY-RUN  season=%d  date=%s  rows=%d", season, game_date, len(rows))
                continue
            df  = pd.DataFrame(rows)
            key = _scores_key(season, game_date)
            write_parquet(s3, df, key)
            total_written += 1

        log.info("Season %d: %d dates with games, %d total games",
                 season, len(by_date), sum(len(v) for v in by_date.values()))

    print(f"\nNCAAB scores: {total_written} dates written, {total_skipped} dates skipped, "
          f"{total_games} games")
    if dry_run:
        print("(dry-run — no S3 writes)")
    print(f"\nDuckDB validation:\n"
          f'  duckdb -c "SELECT season, COUNT(*) games, SUM(completed::INT) completed\n'
          f"  FROM read_parquet('s3://{BUCKET}/{SCORES_S3}/**/*.parquet')\n"
          f'  GROUP BY 1 ORDER BY 1"')


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ingest NCAAB game scores to S3 via ESPN API.")
    p.add_argument("--season", type=int, help="Single season year label, e.g. 2023 = 2023-24 season.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--validate", action="store_true", help="Print join-coverage vs odds data.")
    return p


def main() -> None:
    args    = build_parser().parse_args()
    seasons = [args.season] if args.season else list(SEASON_RANGES.keys())
    if args.validate:
        run_validate(seasons)
        return
    run(seasons, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
