"""
ingest_weather.py
-----------------
Fetches game-day weather for outdoor MLB parks and inserts rows into
baseball_data.statsapi.weather_raw (append-only, no MERGE).

Primary source: Open-Meteo (https://open-meteo.com) — no API key required.
Fallback source: OpenWeatherMap — requires OPENWEATHERMAP_API_KEY env var.

Observation types (--observation-type):
  forecast_pregame        Pre-game forecast fetched hours before first pitch.
                          Default daily ingestion behavior.
  observed_at_first_pitch Actual observed conditions fetched from archive
                          endpoint after the game starts. For yesterday's
                          completed games (or use --date for specific date).
  forecast_intraday       Rolling forecast snapshots at fixed checkpoints before
                          first pitch. Requires --hours-to-first-pitch {24,6,3,1}.

Usage:
    # Daily pre-game forecast (default)
    uv run python scripts/ingest_weather.py --date YYYY-MM-DD

    # Observed conditions for yesterday's completed games (morning batch)
    uv run python scripts/ingest_weather.py --observation-type observed_at_first_pitch

    # Intraday forecast at T-6h checkpoint (called by hourly cron)
    uv run python scripts/ingest_weather.py --observation-type forecast_intraday --hours-to-first-pitch 6

    --dry-run   Print planned operations without writing to Snowflake or calling APIs.
    --source    Weather API source (default: open-meteo).

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
from datetime import date, datetime, timedelta, timezone

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

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL  = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_ARCHIVE_LAG_DAYS = 5

OPENWEATHERMAP_TIMEMACHINE_URL = "https://api.openweathermap.org/data/3.0/onecall/timemachine"
OPENWEATHERMAP_FORECAST_URL    = "https://api.openweathermap.org/data/3.0/onecall"

_HTTP_TIMEOUT_SEC = 30
_HTTP_MAX_ATTEMPTS = 3
_HTTP_BACKOFF_BASE_SEC = 2.0

# Checkpoints for forecast_intraday (hours before first pitch)
INTRADAY_CHECKPOINTS = [24, 6, 3, 1]
# A capture fires if the current time is within this many hours of a checkpoint
INTRADAY_WINDOW_HOURS = 0.33  # ±20 minutes


def _get_with_retry(url: str, params: dict) -> dict | None:
    """GET with retry/backoff. Returns parsed JSON dict or None on persistent failure."""
    import time
    last_exc: Exception | None = None
    for attempt in range(1, _HTTP_MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, params=params, timeout=_HTTP_TIMEOUT_SEC)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_exc = exc
            if attempt < _HTTP_MAX_ATTEMPTS:
                sleep_s = _HTTP_BACKOFF_BASE_SEC * (2 ** (attempt - 1))
                log.warning("HTTP attempt %d/%d failed (%s); retrying in %.1fs",
                            attempt, _HTTP_MAX_ATTEMPTS, exc, sleep_s)
                time.sleep(sleep_s)
    log.warning("HTTP request failed after %d attempts: %s", _HTTP_MAX_ATTEMPTS, last_exc)
    return None

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
    _raw_account = os.environ["SNOWFLAKE_ACCOUNT"]
    account = _raw_account.strip()
    if "://" in account:
        account = account.split("://", 1)[1]
    account = account.split("/", 1)[0]
    account = account.split(".snowflakecomputing.com", 1)[0]
    if account != _raw_account:
        log.warning("SNOWFLAKE_ACCOUNT normalized: raw=%r -> used=%r", _raw_account, account)
    if any(c in account for c in "./"):
        log.warning(
            "SNOWFLAKE_ACCOUNT still contains a dot/slash after normalization: %r "
            "— the connector will reject this; fix the env var to the bare "
            "org-account identifier (e.g. IHUPICS-DP59975).", account)
    kwargs: dict = dict(
        account=account,
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

# ── Schedule queries ───────────────────────────────────────────────────────────

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

# Fetch completed outdoor games for observed_at_first_pitch ingestion
_COMPLETED_GAMES_SQL = """
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
      AND g.abstract_game_state = 'Final'
      AND rv.roof_type IN ('open', 'convertible')
    ORDER BY g.game_date
"""

_ALREADY_FETCHED_SQL = f"""
    SELECT game_pk
    FROM {WEATHER_RAW_TABLE}
    WHERE DATE(game_datetime_utc) = %(game_date)s
      AND weather_observation_type = %(observation_type)s
      AND (%(hours_to_first_pitch)s IS NULL OR hours_to_first_pitch = %(hours_to_first_pitch)s)
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

    data = _get_with_retry(url, params)
    if data is None:
        log.warning("Open-Meteo request failed (lat=%.4f lon=%.4f) after retries", lat, lon)
        return None

    hourly = data.get("hourly", {})
    times  = hourly.get("time", [])
    if not times:
        log.warning("Open-Meteo returned no hourly data for (%.4f, %.4f)", lat, lon)
        return None

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

    data = _get_with_retry(url, params)
    if data is None:
        log.warning("OpenWeatherMap request failed (lat=%.4f lon=%.4f) after retries", lat, lon)
        return None

    hourly_list = data.get("hourly") or data.get("data", [])
    if not hourly_list:
        log.warning("OpenWeatherMap returned no hourly data for (%.4f, %.4f)", lat, lon)
        return None

    best = min(hourly_list, key=lambda h: abs(h.get("dt", 0) - game_ts))

    temp_k = best.get("temp")
    temp_f = round((temp_k - 273.15) * 9 / 5 + 32, 1) if temp_k is not None else None

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

# ── Snowflake INSERT (append-only) ────────────────────────────────────────────

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
    %(condition_text)s::VARCHAR,
    %(api_source)s::VARCHAR,
    %(weather_observation_type)s::VARCHAR,
    %(hours_to_first_pitch)s::INTEGER,
    CURRENT_TIMESTAMP
"""


def _insert_weather_row(
    conn,
    game_pk: int,
    venue_id: int,
    game_dt: datetime,
    weather: dict,
    source: str,
    observation_type: str,
    hours_to_first_pitch: int | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    if game_dt.tzinfo is not None:
        game_dt_utc = game_dt.astimezone(timezone.utc)
    else:
        game_dt_utc = game_dt.replace(tzinfo=timezone.utc)

    fetch_offset_hours = round((now - game_dt_utc).total_seconds() / 3600, 1)

    with conn.cursor() as cur:
        cur.execute(_INSERT_SQL, {
            "game_pk":              game_pk,
            "venue_id":             venue_id,
            "game_datetime_utc":    game_dt_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "fetch_offset_hours":   fetch_offset_hours,
            "temp_f":               weather["temp_f"],
            "wind_speed_mph":       weather["wind_speed_mph"],
            "wind_direction_deg":   weather["wind_direction_deg"],
            "humidity_pct":         weather["humidity_pct"],
            "condition_text":       weather["condition_text"],
            "api_source":           source,
            "weather_observation_type": observation_type,
            "hours_to_first_pitch": hours_to_first_pitch,
        })

# ── Checkpoint detection (forecast_intraday) ───────────────────────────────────

def _nearest_checkpoint(hours_until: float) -> int | None:
    """Return the checkpoint value if hours_until is within INTRADAY_WINDOW_HOURS of one."""
    for cp in INTRADAY_CHECKPOINTS:
        if abs(hours_until - cp) <= INTRADAY_WINDOW_HOURS:
            return cp
    return None

# ── Main ingestion logic ───────────────────────────────────────────────────────

def _run_forecast_pregame(conn, game_date: str, source: str) -> None:
    """Original daily pre-game forecast ingestion path."""
    with conn.cursor() as cur:
        cur.execute(_SCHEDULE_SQL, {"game_date": game_date})
        rows = cur.fetchall()
        col_names = [d[0].lower() for d in cur.description]
        games = [dict(zip(col_names, row)) for row in rows]

    if not games:
        log.info("No outdoor-park games found for %s — nothing to fetch.", game_date)
        return

    with conn.cursor() as cur:
        cur.execute(_ALREADY_FETCHED_SQL, {
            "game_date":          game_date,
            "observation_type":   "forecast_pregame",
            "hours_to_first_pitch": None,
        })
        already_done = {row[0] for row in cur.fetchall()}

    pending = [g for g in games if g["game_pk"] not in already_done]
    log.info(
        "Found %d outdoor-park games (%d already have forecast_pregame, skipping).",
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

        log.info("Fetching  game_pk=%-8d venue_id=%-5d  lat=%.4f  lon=%.4f",
                 game_pk, venue_id, lat, lon)
        weather = fetch_weather(source, lat, lon, game_dt)
        if weather is None:
            log.warning("No weather data returned for game_pk=%d — skipping.", game_pk)
            continue

        _insert_weather_row(conn, game_pk, venue_id, game_dt, weather, source,
                            "forecast_pregame", None)
        log.info("  Saved: temp=%.1f°F  wind=%.1f mph (dir=%s°)  humidity=%s%%",
                 weather["temp_f"] or 0, weather["wind_speed_mph"] or 0,
                 weather["wind_direction_deg"], weather["humidity_pct"])
        success += 1

    total = len(pending)
    log.info("forecast_pregame complete — %d/%d outdoor parks fetched.", success, total)
    if total > 0 and success == 0:
        log.error("All weather fetches failed.")
        sys.exit(1)


def _run_observed_at_first_pitch(conn, game_date: str, source: str) -> None:
    """Fetch observed weather from archive endpoint for completed games on game_date."""
    with conn.cursor() as cur:
        cur.execute(_COMPLETED_GAMES_SQL, {"game_date": game_date})
        rows = cur.fetchall()
        col_names = [d[0].lower() for d in cur.description]
        games = [dict(zip(col_names, row)) for row in rows]

    if not games:
        log.info("No completed outdoor-park games found for %s — nothing to fetch.", game_date)
        return

    with conn.cursor() as cur:
        cur.execute(_ALREADY_FETCHED_SQL, {
            "game_date":            game_date,
            "observation_type":     "observed_at_first_pitch",
            "hours_to_first_pitch": None,
        })
        already_done = {row[0] for row in cur.fetchall()}

    pending = [g for g in games if g["game_pk"] not in already_done]
    log.info(
        "Found %d completed outdoor games (%d already have observed row, skipping).",
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

        log.info("Fetching observed  game_pk=%-8d venue_id=%-5d", game_pk, venue_id)
        weather = _fetch_open_meteo(lat, lon, game_dt)
        if weather is None:
            log.warning("No observed weather returned for game_pk=%d — skipping.", game_pk)
            continue

        _insert_weather_row(conn, game_pk, venue_id, game_dt, weather, "open-meteo",
                            "observed_at_first_pitch", None)
        log.info("  Saved observed: temp=%.1f°F  wind=%.1f mph",
                 weather["temp_f"] or 0, weather["wind_speed_mph"] or 0)
        success += 1

    log.info("observed_at_first_pitch complete — %d/%d games fetched.", success, len(pending))


def _run_forecast_intraday(conn, game_date: str, source: str, hours_to_first_pitch: int) -> None:
    """Fetch intraday forecast snapshot for today's games at a specific checkpoint."""
    with conn.cursor() as cur:
        cur.execute(_SCHEDULE_SQL, {"game_date": game_date})
        rows = cur.fetchall()
        col_names = [d[0].lower() for d in cur.description]
        games = [dict(zip(col_names, row)) for row in rows]

    if not games:
        log.info("No outdoor-park games found for %s — nothing to fetch.", game_date)
        return

    with conn.cursor() as cur:
        cur.execute(_ALREADY_FETCHED_SQL, {
            "game_date":            game_date,
            "observation_type":     "forecast_intraday",
            "hours_to_first_pitch": hours_to_first_pitch,
        })
        already_done = {row[0] for row in cur.fetchall()}

    now_utc = datetime.now(timezone.utc)
    eligible = []
    for g in games:
        if g["game_pk"] in already_done:
            continue
        game_dt = g["game_datetime_utc"]
        if isinstance(game_dt, str):
            game_dt = datetime.fromisoformat(game_dt)
        if game_dt.tzinfo is None:
            game_dt = game_dt.replace(tzinfo=timezone.utc)
        hours_until = (game_dt - now_utc).total_seconds() / 3600
        cp = _nearest_checkpoint(hours_until)
        if cp == hours_to_first_pitch:
            eligible.append((g, game_dt))

    log.info(
        "forecast_intraday T-%dh: %d games within ±20min window (%d already captured).",
        hours_to_first_pitch, len(eligible), len(already_done),
    )

    success = 0
    for g, game_dt in eligible:
        game_pk  = g["game_pk"]
        venue_id = g["venue_id"]
        lat      = g["latitude"]
        lon      = g["longitude"]

        if lat is None or lon is None:
            log.warning("Skipping venue_id=%d — missing GPS coordinates.", venue_id)
            continue

        log.info("Fetching T-%dh forecast  game_pk=%-8d venue_id=%-5d",
                 hours_to_first_pitch, game_pk, venue_id)
        weather = fetch_weather(source, lat, lon, game_dt)
        if weather is None:
            log.warning("No forecast returned for game_pk=%d — skipping.", game_pk)
            continue

        _insert_weather_row(conn, game_pk, venue_id, game_dt, weather, source,
                            "forecast_intraday", hours_to_first_pitch)
        log.info("  Saved T-%dh: temp=%.1f°F  wind=%.1f mph",
                 hours_to_first_pitch, weather["temp_f"] or 0, weather["wind_speed_mph"] or 0)
        success += 1

    log.info("forecast_intraday T-%dh complete — %d/%d fetched.", hours_to_first_pitch, success, len(eligible))

# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest game-day weather for outdoor MLB parks into weather_raw."
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help=(
            "Game date to fetch weather for. "
            "Defaults to today for forecast_pregame/forecast_intraday; "
            "yesterday for observed_at_first_pitch."
        ),
    )
    parser.add_argument(
        "--observation-type",
        choices=["forecast_pregame", "observed_at_first_pitch", "forecast_intraday"],
        default="forecast_pregame",
        help="Type of weather observation to capture (default: forecast_pregame).",
    )
    parser.add_argument(
        "--hours-to-first-pitch",
        type=int,
        choices=INTRADAY_CHECKPOINTS,
        default=None,
        help=(
            "Required for forecast_intraday. "
            "Literal checkpoint value written to hours_to_first_pitch column: {24, 6, 3, 1}. "
            "Only games within ±20min of this checkpoint are captured."
        ),
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

    if args.observation_type == "forecast_intraday" and args.hours_to_first_pitch is None:
        parser.error("--hours-to-first-pitch is required when --observation-type=forecast_intraday")

    if args.date:
        game_date = args.date
    elif args.observation_type == "observed_at_first_pitch":
        game_date = (date.today() - timedelta(days=1)).isoformat()
    else:
        game_date = date.today().isoformat()

    log.info(
        "Weather ingest — date=%s  observation_type=%s  hours_to_first_pitch=%s  dry_run=%s",
        game_date, args.observation_type, args.hours_to_first_pitch, args.dry_run,
    )

    if args.dry_run:
        log.info("DRY RUN: no Snowflake writes or API calls.")
        log.info("  Would fetch %s weather via %s for outdoor parks on %s",
                 args.observation_type, args.source, game_date)
        return

    conn = get_snowflake_conn()
    try:
        if args.observation_type == "forecast_pregame":
            _run_forecast_pregame(conn, game_date, args.source)
        elif args.observation_type == "observed_at_first_pitch":
            _run_observed_at_first_pitch(conn, game_date, args.source)
        elif args.observation_type == "forecast_intraday":
            _run_forecast_intraday(conn, game_date, args.source, args.hours_to_first_pitch)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
