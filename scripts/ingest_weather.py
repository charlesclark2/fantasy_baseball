"""
ingest_weather.py
-----------------
Fetches game-day weather for outdoor MLB parks and upserts rows into
baseball_data.statsapi.weather_raw.

Primary source: Open-Meteo (https://open-meteo.com) — no API key required.
Fallback source: OpenWeatherMap — requires OPENWEATHERMAP_API_KEY env var.

Usage:
    uv run python scripts/ingest_weather.py [--date YYYY-MM-DD] [--dry-run] [--source open-meteo|openweathermap]

    --date    DATE  Game date to fetch (default: today).
    --dry-run FLAG  Print planned operations without writing to Snowflake or calling APIs.
    --source  TEXT  Weather API source (default: open-meteo).

Historical backfill:
    The script automatically detects past dates and uses the appropriate
    historical endpoint. For open-meteo, dates older than 5 days use
    archive-api.open-meteo.com. For openweathermap, the timemachine endpoint
    is used for any past date.

Snowflake authentication (same pattern as other ingest scripts):
    Private key (preferred): SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER,
        SNOWFLAKE_WAREHOUSE, SNOWFLAKE_PRIVATE_KEY_PATH, SNOWFLAKE_ROLE
    Password fallback: SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER,
        SNOWFLAKE_PASSWORD, SNOWFLAKE_WAREHOUSE, SNOWFLAKE_ROLE
"""

import argparse
import logging
import os
import sys
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

WEATHER_RAW_TABLE = "baseball_data.statsapi.weather_raw"

# Open-Meteo endpoints (no API key required)
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL  = "https://archive-api.open-meteo.com/v1/archive"
# Open-Meteo archive typically has data up to ~5 days before today
OPEN_METEO_ARCHIVE_LAG_DAYS = 5

# OpenWeatherMap endpoints (requires OPENWEATHERMAP_API_KEY)
OPENWEATHERMAP_TIMEMACHINE_URL = "https://api.openweathermap.org/data/3.0/onecall/timemachine"
OPENWEATHERMAP_FORECAST_URL    = "https://api.openweathermap.org/data/3.0/onecall"

# ── Snowflake connection ───────────────────────────────────────────────────────

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
    kwargs: dict = dict(
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

# ── Schedule query ─────────────────────────────────────────────────────────────

_SCHEDULE_SQL = """
    SELECT
        g.game_pk,
        g.venue_id,
        g.game_date                     AS game_datetime_utc,
        v.latitude,
        v.longitude,
        rv.roof_type
    FROM baseball_data.betting.stg_statsapi_games g
    JOIN (
        SELECT venue_id, latitude, longitude
        FROM baseball_data.betting.stg_statsapi_venues
        QUALIFY ROW_NUMBER() OVER (PARTITION BY venue_id ORDER BY ingest_date DESC) = 1
    ) v ON g.venue_id = v.venue_id
    JOIN baseball_data.betting.ref_venues rv ON g.venue_id = rv.venue_id
    WHERE g.official_date = %(game_date)s
      AND rv.roof_type IN ('open', 'convertible')
    ORDER BY g.game_date
"""

_ALREADY_FETCHED_SQL = f"""
    SELECT game_pk
    FROM {WEATHER_RAW_TABLE}
    WHERE DATE(game_datetime_utc) = %(game_date)s
      AND fetch_offset_hours < -1
"""

# ── Open-Meteo fetching ────────────────────────────────────────────────────────

def _fetch_open_meteo(lat: float, lon: float, game_dt: datetime) -> dict | None:
    """Fetch hourly weather from Open-Meteo and pick the hour closest to game_dt."""
    game_date_str = game_dt.strftime("%Y-%m-%d")
    target_date = game_dt.date() if hasattr(game_dt, "date") else date.today()
    lag = (date.today() - target_date).days

    url = OPEN_METEO_ARCHIVE_URL if lag > OPEN_METEO_ARCHIVE_LAG_DAYS else OPEN_METEO_FORECAST_URL
    params = {
        "latitude":        lat,
        "longitude":       lon,
        "hourly":          "temperature_2m,windspeed_10m,winddirection_10m,relativehumidity_2m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone":        "UTC",
        "start_date":      game_date_str,
        "end_date":        game_date_str,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("Open-Meteo request failed (lat=%.4f lon=%.4f): %s", lat, lon, exc)
        return None

    hourly = data.get("hourly", {})
    times  = hourly.get("time", [])
    if not times:
        log.warning("Open-Meteo returned no hourly data for (%.4f, %.4f)", lat, lon)
        return None

    # Normalize game_dt to a naive UTC datetime for comparison
    if game_dt.tzinfo is not None:
        naive_dt = game_dt.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        naive_dt = game_dt

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
        "condition_text":     None,
    }

# ── OpenWeatherMap fetching (fallback) ────────────────────────────────────────

def _fetch_openweathermap(lat: float, lon: float, game_dt: datetime) -> dict | None:
    """Fetch weather from OpenWeatherMap. Requires OPENWEATHERMAP_API_KEY env var."""
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not api_key:
        log.error("OPENWEATHERMAP_API_KEY is not set; cannot use openweathermap source.")
        return None

    target_date = game_dt.date() if hasattr(game_dt, "date") else date.today()
    is_historical = (date.today() - target_date).days > 0

    if game_dt.tzinfo is None:
        game_dt = game_dt.replace(tzinfo=timezone.utc)
    game_ts = int(game_dt.timestamp())

    if is_historical:
        url    = OPENWEATHERMAP_TIMEMACHINE_URL
        params = {"lat": lat, "lon": lon, "dt": game_ts, "appid": api_key}
    else:
        url    = OPENWEATHERMAP_FORECAST_URL
        params = {"lat": lat, "lon": lon, "exclude": "minutely,daily,alerts", "appid": api_key}

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("OpenWeatherMap request failed (lat=%.4f lon=%.4f): %s", lat, lon, exc)
        return None

    hourly_list = data.get("hourly") or data.get("data", [])
    if not hourly_list:
        log.warning("OpenWeatherMap returned no hourly data for (%.4f, %.4f)", lat, lon)
        return None

    best = min(hourly_list, key=lambda h: abs(h.get("dt", 0) - game_ts))

    # Kelvin → Fahrenheit: F = (K − 273.15) × 9/5 + 32
    temp_k = best.get("temp")
    temp_f = round((temp_k - 273.15) * 9 / 5 + 32, 1) if temp_k is not None else None

    # m/s → mph: 1 m/s = 2.237 mph
    wind_mps = best.get("wind_speed")
    wind_mph = round(wind_mps * 2.237, 1) if wind_mps is not None else None

    weather_list = best.get("weather", [{}])
    condition = weather_list[0].get("description") if weather_list else None

    return {
        "temp_f":             temp_f,
        "wind_speed_mph":     wind_mph,
        "wind_direction_deg": best.get("wind_deg"),
        "humidity_pct":       best.get("humidity"),
        "condition_text":     condition,
    }


def fetch_weather(source: str, lat: float, lon: float, game_dt: datetime) -> dict | None:
    if source == "open-meteo":
        return _fetch_open_meteo(lat, lon, game_dt)
    elif source == "openweathermap":
        return _fetch_openweathermap(lat, lon, game_dt)
    else:
        raise ValueError(f"Unknown weather source: {source!r}")

# ── Snowflake upsert ───────────────────────────────────────────────────────────

_MERGE_SQL = f"""
MERGE INTO {WEATHER_RAW_TABLE} AS tgt
USING (
    SELECT
        %(game_pk)s::INTEGER                   AS game_pk,
        %(venue_id)s::INTEGER                  AS venue_id,
        %(game_datetime_utc)s::TIMESTAMP_NTZ   AS game_datetime_utc,
        %(fetch_offset_hours)s                 AS fetch_offset_hours,
        %(temp_f)s                             AS temp_f,
        %(wind_speed_mph)s                     AS wind_speed_mph,
        %(wind_direction_deg)s                 AS wind_direction_deg,
        %(humidity_pct)s                       AS humidity_pct,
        %(condition_text)s                     AS condition_text,
        %(api_source)s                         AS api_source,
        CURRENT_TIMESTAMP()                    AS loaded_at
) AS src
ON tgt.game_pk = src.game_pk AND tgt.venue_id = src.venue_id
WHEN MATCHED THEN UPDATE SET
    game_datetime_utc   = src.game_datetime_utc,
    fetch_offset_hours  = src.fetch_offset_hours,
    temp_f              = src.temp_f,
    wind_speed_mph      = src.wind_speed_mph,
    wind_direction_deg  = src.wind_direction_deg,
    humidity_pct        = src.humidity_pct,
    condition_text      = src.condition_text,
    api_source          = src.api_source,
    loaded_at           = src.loaded_at
WHEN NOT MATCHED THEN INSERT (
    game_pk, venue_id, game_datetime_utc, fetch_offset_hours,
    temp_f, wind_speed_mph, wind_direction_deg, humidity_pct,
    condition_text, api_source, loaded_at
) VALUES (
    src.game_pk, src.venue_id, src.game_datetime_utc, src.fetch_offset_hours,
    src.temp_f, src.wind_speed_mph, src.wind_direction_deg, src.humidity_pct,
    src.condition_text, src.api_source, src.loaded_at
)
"""


def _upsert_weather_row(
    conn,
    game_pk: int,
    venue_id: int,
    game_dt: datetime,
    weather: dict,
    source: str,
) -> None:
    now = datetime.now(timezone.utc)
    if game_dt.tzinfo is not None:
        game_dt_utc = game_dt.astimezone(timezone.utc)
    else:
        game_dt_utc = game_dt.replace(tzinfo=timezone.utc)

    fetch_offset_hours = round((now - game_dt_utc).total_seconds() / 3600, 1)

    with conn.cursor() as cur:
        cur.execute(_MERGE_SQL, {
            "game_pk":            game_pk,
            "venue_id":           venue_id,
            "game_datetime_utc":  game_dt_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "fetch_offset_hours": fetch_offset_hours,
            "temp_f":             weather["temp_f"],
            "wind_speed_mph":     weather["wind_speed_mph"],
            "wind_direction_deg": weather["wind_direction_deg"],
            "humidity_pct":       weather["humidity_pct"],
            "condition_text":     weather["condition_text"],
            "api_source":         source,
        })

# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest game-day weather for outdoor MLB parks into weather_raw."
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        metavar="YYYY-MM-DD",
        help="Game date to fetch weather for (default: today).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned operations without writing to Snowflake or calling APIs.",
    )
    parser.add_argument(
        "--source",
        choices=["open-meteo", "openweathermap"],
        default="open-meteo",
        help="Weather API source (default: open-meteo, no API key required).",
    )
    args = parser.parse_args()

    game_date = args.date
    log.info(
        "Fetching weather — date=%s  source=%s  dry_run=%s",
        game_date, args.source, args.dry_run,
    )

    if args.dry_run:
        log.info("DRY RUN: no Snowflake writes or API calls.")
        log.info("  Would query stg_statsapi_games for outdoor-park games on %s", game_date)
        log.info("  Would fetch weather via %s for each outdoor park", args.source)
        log.info("  Would upsert weather rows into %s", WEATHER_RAW_TABLE)
        log.info("  roof_type filter: open, convertible  (fixed/dome parks are skipped)")
        return

    conn = get_snowflake_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(_SCHEDULE_SQL, {"game_date": game_date})
            rows = cur.fetchall()
            col_names = [d[0].lower() for d in cur.description]
            games = [dict(zip(col_names, row)) for row in rows]

        if not games:
            log.info("No outdoor-park games found for %s — nothing to fetch.", game_date)
            return

        with conn.cursor() as cur:
            cur.execute(_ALREADY_FETCHED_SQL, {"game_date": game_date})
            already_done = {row[0] for row in cur.fetchall()}

        pending = [g for g in games if g["game_pk"] not in already_done]
        log.info(
            "Found %d outdoor-park games (%d already fetched near first pitch, skipping).",
            len(pending), len(already_done),
        )

        success = 0
        for g in pending:
            game_pk  = g["game_pk"]
            venue_id = g["venue_id"]
            lat      = g["latitude"]
            lon      = g["longitude"]
            game_dt  = g["game_datetime_utc"]

            if isinstance(game_dt, str):
                game_dt = datetime.fromisoformat(game_dt)

            if lat is None or lon is None:
                log.warning("Skipping venue_id=%d — missing GPS coordinates.", venue_id)
                continue

            log.info(
                "Fetching  game_pk=%-8d venue_id=%-5d  lat=%.4f  lon=%.4f",
                game_pk, venue_id, lat, lon,
            )
            weather = fetch_weather(args.source, lat, lon, game_dt)
            if weather is None:
                log.warning("No weather data returned for game_pk=%d — skipping.", game_pk)
                continue

            _upsert_weather_row(conn, game_pk, venue_id, game_dt, weather, args.source)
            log.info(
                "  Saved: temp=%.1f°F  wind=%.1f mph (dir=%s°)  humidity=%s%%",
                weather["temp_f"] or 0,
                weather["wind_speed_mph"] or 0,
                weather["wind_direction_deg"],
                weather["humidity_pct"],
            )
            success += 1

        total = len(pending)
        log.info("Weather ingestion complete — %d/%d outdoor parks fetched.", success, total)
        if total > 0 and success == 0:
            log.error("All weather fetches failed.")
            sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
