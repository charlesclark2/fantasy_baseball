"""
backfill_observed_weather.py
-----------------------------
One-shot backfill of observed_at_first_pitch weather for all completed
outdoor MLB games from 2021 through the current season.

Source: Open-Meteo archive endpoint (https://archive-api.open-meteo.com/v1/archive)
  — no API key required; goes back to 1940.

Target: baseball_data.statsapi.weather_raw
  weather_observation_type = 'observed_at_first_pitch'
  hours_to_first_pitch      = NULL

Strategy:
  1. Query mart_game_results × stg_statsapi_venues × ref_venues for all
     completed outdoor games in the date range.
  2. Skip game_pks that already have an observed_at_first_pitch row.
  3. For each remaining game, hit the Open-Meteo archive endpoint with the
     actual game date and pick the hourly reading closest to first pitch time.
  4. INSERT the row with weather_observation_type='observed_at_first_pitch'.
  5. Throttle to ~2 req/s (Open-Meteo free tier: 10k/day).

Usage:
    # Full backfill 2021–current year
    uv run python scripts/backfill_observed_weather.py

    # Single season
    uv run python scripts/backfill_observed_weather.py --start-year 2024 --end-year 2024

    # Dry-run (print games without writing)
    uv run python scripts/backfill_observed_weather.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import date, datetime, timezone

import requests
import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# E11.1-W11 Tier-C: leg-gated dual-write to the shared weather_raw S3 mirror (W11_RAW_WRITE_MODE,
# default 'snowflake' → unchanged). SF INSERT on 'snowflake'/'both'; an S3 mirror with INC-20
# latest-per-period retention on 's3'/'both'. Shares the writer + retention key with ingest_weather.
import sys  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from utils.lakehouse_raw_writer import (  # noqa: E402
    WEATHER_RAW_RETENTION_KEY,
    lakehouse_write_legs,
    w11_write_mode,
    weather_mirror_rows,
    write_raw_rows_s3_retained,
)

_LAKEHOUSE_SOURCE = "weather_raw"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

WEATHER_RAW_TABLE   = "baseball_data.statsapi.weather_raw"
OPEN_METEO_ARCHIVE  = "https://archive-api.open-meteo.com/v1/archive"
REQUEST_DELAY       = 0.5   # seconds between API calls (~2 req/s)
REQUEST_TIMEOUT     = 30
MAX_RETRIES         = 3
RETRY_BACKOFF       = 10

_PENDING_GAMES_SQL = """
    SELECT
        g.game_pk,
        g.game_date::DATE        AS game_date,
        g.game_year,
        g.venue_id,
        v.latitude,
        v.longitude
    FROM baseball_data.betting.mart_game_results g
    JOIN (
        SELECT venue_id, latitude, longitude
        FROM baseball_data.betting.stg_statsapi_venues
        QUALIFY ROW_NUMBER() OVER (PARTITION BY venue_id ORDER BY ingest_date DESC) = 1
    ) v ON g.venue_id = v.venue_id
    JOIN baseball_data.betting.ref_venues rv ON g.venue_id = rv.venue_id
    WHERE g.game_type = 'R'
      AND g.game_year BETWEEN %(start_year)s AND %(end_year)s
      AND rv.roof_type IN ('open', 'convertible')
      AND g.game_pk NOT IN (
          SELECT DISTINCT game_pk
          FROM baseball_data.statsapi.weather_raw
          WHERE weather_observation_type = 'observed_at_first_pitch'
      )
    ORDER BY g.game_date
"""

_INSERT_SQL = f"""
INSERT INTO {WEATHER_RAW_TABLE} (
    game_pk, venue_id, game_datetime_utc, fetch_offset_hours,
    temp_f, wind_speed_mph, wind_direction_deg, humidity_pct,
    condition_text, api_source, weather_observation_type, hours_to_first_pitch, loaded_at
)
SELECT
    %(game_pk)s::INTEGER,
    %(venue_id)s::INTEGER,
    %(game_datetime_utc)s::TIMESTAMP_NTZ,
    %(fetch_offset_hours)s::FLOAT,
    %(temp_f)s::FLOAT,
    %(wind_speed_mph)s::FLOAT,
    %(wind_direction_deg)s::INTEGER,
    %(humidity_pct)s::INTEGER,
    NULL::VARCHAR,
    'open-meteo'::VARCHAR,
    'observed_at_first_pitch'::VARCHAR,
    NULL::INTEGER,
    CURRENT_TIMESTAMP
"""


def _load_private_key() -> bytes | None:
    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not key_path:
        return None
    with open(key_path, "rb") as fh:
        raw = fh.read()
    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    key = load_pem_private_key(
        raw,
        password=passphrase.encode() if passphrase else None,
        backend=default_backend(),
    )
    return key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())


def get_snowflake_conn():
    kwargs = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE"),
        role=os.environ.get("SNOWFLAKE_ROLE"),
    )
    pk = _load_private_key()
    if pk:
        kwargs["private_key"] = pk
    else:
        kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(**kwargs)


def fetch_archive_weather(lat: float, lon: float, game_dt: datetime) -> dict | None:
    """Fetch hourly archive weather from Open-Meteo for game_dt."""
    game_date_str = game_dt.strftime("%Y-%m-%d")
    params = {
        "latitude":         lat,
        "longitude":        lon,
        "hourly":           "temperature_2m,windspeed_10m,winddirection_10m,relativehumidity_2m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit":  "mph",
        "timezone":         "UTC",
        "start_date":       game_date_str,
        "end_date":         game_date_str,
    }

    if game_dt.tzinfo is not None:
        naive_dt = game_dt.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        naive_dt = game_dt

    backoff = RETRY_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(OPEN_METEO_ARCHIVE, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            break
        except requests.RequestException as exc:
            log.warning("  [%d/%d] Open-Meteo error: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(backoff)
                backoff *= 2
    else:
        return None

    hourly = data.get("hourly", {})
    times  = hourly.get("time", [])
    if not times:
        return None

    def _parse(t: str) -> datetime:
        return datetime.strptime(t, "%Y-%m-%dT%H:%M")

    best_idx = min(range(len(times)), key=lambda i: abs((_parse(times[i]) - naive_dt).total_seconds()))

    temps = hourly.get("temperature_2m", [])
    winds = hourly.get("windspeed_10m", [])
    dirs  = hourly.get("winddirection_10m", [])
    humid = hourly.get("relativehumidity_2m", [])

    def _get(lst: list, idx: int):
        return lst[idx] if idx < len(lst) else None

    return {
        "temp_f":             _get(temps, best_idx),
        "wind_speed_mph":     _get(winds, best_idx),
        "wind_direction_deg": int(_get(dirs, best_idx)) if _get(dirs, best_idx) is not None else None,
        "humidity_pct":       int(_get(humid, best_idx)) if _get(humid, best_idx) is not None else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill observed_at_first_pitch weather for completed outdoor games"
    )
    parser.add_argument("--start-year", type=int, default=2021)
    parser.add_argument("--end-year",   type=int, default=date.today().year)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print games without writing to Snowflake")
    args = parser.parse_args()

    log.info("Connecting to Snowflake…")
    conn = get_snowflake_conn()

    try:
        with conn.cursor() as cur:
            cur.execute(_PENDING_GAMES_SQL, {
                "start_year": args.start_year,
                "end_year":   args.end_year,
            })
            rows = cur.fetchall()
            col_names = [d[0].lower() for d in cur.description]
            games = [dict(zip(col_names, row)) for row in rows]

        log.info("Found %d games needing observed weather backfill (%d–%d)",
                 len(games), args.start_year, args.end_year)

        if args.dry_run:
            for g in games[:20]:
                print(f"  game_pk={g['game_pk']}  date={g['game_date']}  "
                      f"venue={g['venue_id']}  lat={g['latitude']}  lon={g['longitude']}")
            if len(games) > 20:
                print(f"  … and {len(games) - 20} more")
            return

        # E11.1-W11 Tier-C: which legs run (SF INSERT and/or S3 mirror).
        do_sf, do_s3 = lakehouse_write_legs(w11_write_mode())
        log.info("write_mode=%s (sf=%s, s3=%s)", w11_write_mode(), do_sf, do_s3)

        inserted = 0
        skipped  = 0
        now_utc  = datetime.now(timezone.utc)
        mirror: list[dict] = []

        for i, g in enumerate(games, start=1):
            game_pk  = g["game_pk"]
            venue_id = g["venue_id"]
            lat      = g["latitude"]
            lon      = g["longitude"]
            game_dt  = g["game_date"]

            if lat is None or lon is None:
                log.warning("[%d/%d] game_pk=%d: missing coordinates — skipping", i, len(games), game_pk)
                skipped += 1
                continue

            if isinstance(game_dt, date) and not isinstance(game_dt, datetime):
                game_dt = datetime(game_dt.year, game_dt.month, game_dt.day, 19, 0, 0,
                                   tzinfo=timezone.utc)
            elif isinstance(game_dt, str):
                game_dt = datetime.fromisoformat(game_dt)
            if game_dt.tzinfo is None:
                game_dt = game_dt.replace(tzinfo=timezone.utc)

            if (i % 100) == 1:
                log.info("[%d/%d] game_pk=%d  date=%s", i, len(games), game_pk, g["game_date"])

            weather = fetch_archive_weather(lat, lon, game_dt)
            if weather is None:
                log.warning("  game_pk=%d: no archive data — skipping", game_pk)
                skipped += 1
                time.sleep(REQUEST_DELAY)
                continue

            game_dt_utc = game_dt.astimezone(timezone.utc)
            fetch_offset = round((now_utc - game_dt_utc).total_seconds() / 3600, 1)

            insert_params = {
                "game_pk":           game_pk,
                "venue_id":          venue_id,
                "game_datetime_utc": game_dt_utc.strftime("%Y-%m-%d %H:%M:%S"),
                "fetch_offset_hours": fetch_offset,
                "temp_f":            weather["temp_f"],
                "wind_speed_mph":    weather["wind_speed_mph"],
                "wind_direction_deg": weather["wind_direction_deg"],
                "humidity_pct":      weather["humidity_pct"],
            }
            if do_sf:
                with conn.cursor() as cur:
                    cur.execute(_INSERT_SQL, insert_params)
            # S3 mirror row — the columns the _INSERT_SQL hardcodes as literals (obs-type / api_source /
            # NULL condition & checkpoint) are set explicitly so the mirror matches the SF row exactly.
            mirror.append({
                **insert_params,
                "condition_text":           None,
                "api_source":               "open-meteo",
                "weather_observation_type": "observed_at_first_pitch",
                "hours_to_first_pitch":     None,
            })
            inserted += 1

            time.sleep(REQUEST_DELAY)

        if do_s3 and mirror:
            n = write_raw_rows_s3_retained(
                _LAKEHOUSE_SOURCE, weather_mirror_rows(mirror),
                key_cols=WEATHER_RAW_RETENTION_KEY, ts_col="loaded_at",
            )
            log.info("mirrored %d observed row(s) → S3 lakehouse_raw/%s/ (retained latest-per-period)",
                     n, _LAKEHOUSE_SOURCE)

        log.info("Backfill complete — %d inserted, %d skipped.", inserted, skipped)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
