"""
ingest_ncaaf_scores_to_s3.py
------------------------------
Pull NCAAF game outcomes (2020–2025) from the CollegeFootballData API
(free key, https://collegefootballdata.com) and write Hive-partitioned
Parquet to S3.  Zero Snowflake writes, zero Odds API credits.

S3 layout:
    s3://baseball-betting-ml-artifacts/
        ncaaf/scores/season={season}/date={game_date}/data.parquet

Schema:
    sport, season, game_date, source_event_id,
    home_team_source, away_team_source,   # CFBD school name ("Alabama")
    home_team_odds, away_team_odds,        # mapped Odds API name ("Alabama Crimson Tide")
    home_score, away_score, winner,
    completed, neutral_site,
    home_q1..q4, home_ot, away_q1..q4, away_ot,  # quarter scores from line_scores
    period_scores_json,                            # {"home":[…],"away":[…]}
    season_type, week,
    load_id, ingested_at

Crosswalk strategy:
    1. Fetch /teams once to build school → "school mascot" map.
    2. Apply static corrections for known CFBD ↔ Odds API name differences.
    3. Store both source name and mapped Odds API name; null if no mapping found.
    The join-coverage report (--validate) shows what % of odds games matched.

Usage:
    uv run scripts/ingest_ncaaf_scores_to_s3.py
    uv run scripts/ingest_ncaaf_scores_to_s3.py --season 2024
    uv run scripts/ingest_ncaaf_scores_to_s3.py --dry-run
    uv run scripts/ingest_ncaaf_scores_to_s3.py --validate

Environment (.env in repo root):
    CFBD_API_KEY            Required (free at collegefootballdata.com/key)
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
from datetime import datetime, timezone
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

CFBD_BASE  = "https://api.collegefootballdata.com"
BUCKET     = "baseball-betting-ml-artifacts"
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-2")
SPORT      = "americanfootball_ncaaf"
ODDS_S3    = "ncaaf/odds"
SCORES_S3  = "ncaaf/scores"
SEASONS    = [2020, 2021, 2022, 2023, 2024, 2025]

# Static corrections for cases where CFBD school+mascot ≠ Odds API name.
# Format: "CFBD school" → "Odds API full name"
# These override the dynamically built school→mascot crosswalk.
STATIC_CORRECTIONS: dict[str, str] = {
    "Ole Miss":                        "Mississippi Rebels",
    "LSU":                             "LSU Tigers",
    "SMU":                             "SMU Mustangs",
    "TCU":                             "TCU Horned Frogs",
    "UCF":                             "UCF Knights",
    "FIU":                             "FIU Panthers",
    "FAU":                             "Florida Atlantic Owls",
    "UConn":                           "Connecticut Huskies",
    "UMass":                           "Massachusetts Minutemen",
    "UTEP":                            "UTEP Miners",
    "UTSA":                            "UTSA Roadrunners",
    "UAB":                             "UAB Blazers",
    "USF":                             "South Florida Bulls",
    "ULM":                             "Louisiana Monroe Warhawks",
    "Hawai'i":                         "Hawaii Rainbow Warriors",
    "Hawaii":                          "Hawaii Rainbow Warriors",
    "BYU":                             "BYU Cougars",
    "Miami (FL)":                      "Miami Hurricanes",
    "Miami":                           "Miami Hurricanes",      # Odds API uses "Miami (FL)" sometimes
    "Florida International":           "FIU Panthers",
    "Louisiana":                       "Louisiana Ragin' Cajuns",
    "App State":                       "Appalachian State Mountaineers",
    "Appalachian State":               "Appalachian State Mountaineers",
    "Western Kentucky":                "Western Kentucky Hilltoppers",
    "Coastal Carolina":                "Coastal Carolina Chanticleers",
    "San José State":                  "San Jose State Spartans",
    "San Jose State":                  "San Jose State Spartans",
    "North Carolina State":            "NC State Wolfpack",
    "NC State":                        "NC State Wolfpack",
    "Mississippi State":               "Mississippi State Bulldogs",
    "Penn State":                      "Penn State Nittany Lions",
    "Iowa State":                      "Iowa State Cyclones",
    "Ohio State":                      "Ohio State Buckeyes",
    "Michigan State":                  "Michigan State Spartans",
    "Oklahoma State":                  "Oklahoma State Cowboys",
    "Arizona State":                   "Arizona State Sun Devils",
    "Florida State":                   "Florida State Seminoles",
    "Kansas State":                    "Kansas State Wildcats",
    "Washington State":                "Washington State Cougars",
    "Oregon State":                    "Oregon State Beavers",
    "Colorado State":                  "Colorado State Rams",
    "Utah State":                      "Utah State Aggies",
    "Boise State":                     "Boise State Broncos",
    "San Diego State":                 "San Diego State Aztecs",
    "Fresno State":                    "Fresno State Bulldogs",
    "New Mexico State":                "New Mexico State Aggies",
    "Alabama-Birmingham":              "UAB Blazers",
}


def _cfbd_key() -> str:
    k = os.environ.get("CFBD_API_KEY", "")
    if not k:
        raise EnvironmentError("CFBD_API_KEY is not set (free key at collegefootballdata.com/key)")
    return k


def _cfbd_headers() -> dict:
    return {"Authorization": f"Bearer {_cfbd_key()}"}


# ── Crosswalk ──────────────────────────────────────────────────────────────────

def build_crosswalk() -> dict[str, str]:
    """Fetch CFBD /teams and build school → 'school mascot' Odds API name map."""
    log.info("Fetching CFBD /teams for crosswalk …")
    try:
        resp = requests.get(f"{CFBD_BASE}/teams", headers=_cfbd_headers(), timeout=30)
        resp.raise_for_status()
        teams = resp.json()
    except Exception as e:
        log.warning("Could not fetch /teams (%s) — using static corrections only", e)
        return {}

    crosswalk: dict[str, str] = {}
    for t in teams:
        school  = t.get("school", "")
        mascot  = t.get("mascot") or ""
        if not school:
            continue
        if school in STATIC_CORRECTIONS:
            crosswalk[school] = STATIC_CORRECTIONS[school]
        elif mascot:
            crosswalk[school] = f"{school} {mascot}"
        else:
            crosswalk[school] = school

    # Apply static corrections on top (overrides dynamic)
    crosswalk.update(STATIC_CORRECTIONS)
    log.info("  Crosswalk: %d teams", len(crosswalk))
    return crosswalk


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


# ── CFBD fetch ──────────────────────────────────────────────────────────────────

def fetch_games_for_season(season: int) -> list[dict]:
    """Fetch regular + postseason games from CFBD for one season year."""
    games: list[dict] = []
    for season_type in ("regular", "postseason"):
        url  = f"{CFBD_BASE}/games"
        params = {"year": season, "seasonType": season_type}
        try:
            resp = requests.get(url, headers=_cfbd_headers(), params=params, timeout=30)
            if resp.status_code == 404:
                log.warning("  CFBD 404 for season=%d type=%s", season, season_type)
                continue
            resp.raise_for_status()
            batch = resp.json()
            log.info("  season=%d  type=%-12s  games=%d", season, season_type, len(batch))
            if batch and not games:  # log first game keys once for diagnostics
                log.debug("  First game keys: %s", list(batch[0].keys()))
            games.extend(batch)
        except Exception as e:
            log.warning("  Error fetching season=%d type=%s: %s", season, season_type, e)
        time.sleep(0.3)
    return games


def _game_date(start_date: str) -> Optional[str]:
    """Extract YYYY-MM-DD from CFBD start_date ISO string."""
    if not start_date:
        return None
    try:
        dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        # Try plain date prefix
        return start_date[:10] if len(start_date) >= 10 else None


def _parse_line_scores(lst) -> list[Optional[int]]:
    if not lst:
        return []
    out = []
    for v in lst:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            out.append(None)
    return out


# ── Row builder ──────────────────────────────────────────────────────────────────

def game_to_row(game: dict, season: int, crosswalk: dict[str, str],
                load_id: str, ingested_at: str) -> Optional[dict]:
    # CFBD v2 API uses camelCase; v1 used snake_case.  Try both.
    home       = game.get("home_team")  or game.get("homeTeam")  or ""
    away       = game.get("away_team")  or game.get("awayTeam")  or ""
    start_date = game.get("start_date") or game.get("startDate") or ""
    game_date  = _game_date(start_date)
    if not game_date or not home or not away:
        return None

    # Use key-presence check so a 0-score shutout isn't treated as missing.
    home_pts: Optional[int] = game["home_points"] if "home_points" in game else game.get("homePoints")
    away_pts: Optional[int] = game["away_points"] if "away_points" in game else game.get("awayPoints")

    completed = home_pts is not None and away_pts is not None
    winner = None
    if completed:
        if home_pts > away_pts:
            winner = "home"
        elif away_pts > home_pts:
            winner = "away"
        else:
            winner = "tie"

    home_line = _parse_line_scores(game.get("home_line_scores") or game.get("homeLineScores") or [])
    away_line = _parse_line_scores(game.get("away_line_scores") or game.get("awayLineScores") or [])
    neutral   = game["neutral_site"] if "neutral_site" in game else game.get("neutralSite", False)
    s_type    = game.get("season_type") or game.get("seasonType") or ""

    def _get_period(scores: list, idx: int) -> Optional[int]:
        return scores[idx] if idx < len(scores) else None

    period_scores = {"home": home_line, "away": away_line} if (home_line or away_line) else {}

    return {
        "sport":              SPORT,
        "season":             season,
        "game_date":          game_date,
        "source_event_id":    str(game.get("id", "")),
        "home_team_source":   home,
        "away_team_source":   away,
        "home_team_odds":     crosswalk.get(home),
        "away_team_odds":     crosswalk.get(away),
        "home_score":         int(home_pts) if home_pts is not None else None,
        "away_score":         int(away_pts) if away_pts is not None else None,
        "winner":             winner,
        "completed":          completed,
        "neutral_site":       bool(neutral),
        "home_q1":            _get_period(home_line, 0),
        "home_q2":            _get_period(home_line, 1),
        "home_q3":            _get_period(home_line, 2),
        "home_q4":            _get_period(home_line, 3),
        "home_ot":            _get_period(home_line, 4),
        "away_q1":            _get_period(away_line, 0),
        "away_q2":            _get_period(away_line, 1),
        "away_q3":            _get_period(away_line, 2),
        "away_q4":            _get_period(away_line, 3),
        "away_ot":            _get_period(away_line, 4),
        "period_scores_json": json.dumps(period_scores) if period_scores else None,
        "season_type":        s_type,
        "week":               game.get("week"),
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
    print("NCAAF SCORES ↔ ODDS JOIN COVERAGE")
    print("=" * 55)
    print(result.to_string(index=False))
    t_odds = result["odds_games"].sum()
    t_match = result["matched_count"].sum()
    print(f"\n  Overall: {t_match}/{t_odds} = {100*t_match/max(t_odds,1):.1f}%")
    print()


# ── Main ────────────────────────────────────────────────────────────────────────

def run(seasons: list[int], dry_run: bool) -> None:
    _cfbd_key()  # fail fast if missing
    s3          = make_s3()
    load_id     = str(uuid.uuid4())
    ingested_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    crosswalk = build_crosswalk()

    log.info("Scanning S3 for existing score partitions …")
    existing = existing_s3_dates(s3)
    log.info("  %d date partitions already present", len(existing))

    from collections import defaultdict
    total_written = total_skipped = total_games = 0

    for season in seasons:
        log.info("\n── NCAAF Season %d ──", season)
        games     = fetch_games_for_season(season)
        by_date: dict[str, list[dict]] = defaultdict(list)

        for game in games:
            row = game_to_row(game, season, crosswalk, load_id, ingested_at)
            if row and row["game_date"]:
                by_date[row["game_date"]].append(row)

        for game_date, rows in sorted(by_date.items()):
            total_games += len(rows)
            if (season, game_date) in existing:
                total_skipped += 1
                continue
            if dry_run:
                log.info("  DRY-RUN  season=%d  date=%s  rows=%d", season, game_date, len(rows))
                continue
            df  = pd.DataFrame(rows)
            key = _scores_key(season, game_date)
            write_parquet(s3, df, key)
            total_written += 1

        log.info("Season %d done: %d game-dates, %d games",
                 season, len(by_date), sum(len(v) for v in by_date.values()))

    print(f"\nNCAF scores: {total_written} dates written, {total_skipped} skipped, {total_games} games")
    if dry_run:
        print("(dry-run — no S3 writes)")
    unmapped = [s for s in STATIC_CORRECTIONS if s not in crosswalk]
    print(f"\nCrosswall coverage: {len(crosswalk)} teams mapped")
    print(f"\nDuckDB validation:\n"
          f'  duckdb -c "SELECT season, COUNT(*) games, SUM(completed::INT) completed\n'
          f"  FROM read_parquet('s3://{BUCKET}/{SCORES_S3}/**/*.parquet')\n"
          f'  GROUP BY 1 ORDER BY 1"')


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ingest NCAAF game scores to S3 via CFBD API.")
    p.add_argument("--season", type=int, help="Single season year (default: all 2020-2025).")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--validate", action="store_true", help="Print join-coverage vs odds data.")
    return p


def main() -> None:
    args    = build_parser().parse_args()
    seasons = [args.season] if args.season else SEASONS
    if args.validate:
        run_validate(seasons)
        return
    run(seasons, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
