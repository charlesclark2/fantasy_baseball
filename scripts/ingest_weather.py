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

# E11.1-W11 Tier-C: leg-gated dual-write (W11_RAW_WRITE_MODE, its OWN env — default 'snowflake' =
# unchanged). SF INSERT on 'snowflake'/'both'; an S3 mirror to lakehouse_raw/weather_raw/ on
# 's3'/'both', with INC-20 latest-per-period retention (re-fetch re-runs collapse per checkpoint).
# The hourly all-slate-park series is a separate S3-ONLY source (weather_intraday_series).
sys.path.insert(0, os.path.dirname(__file__))
from utils.lakehouse_raw_writer import (  # noqa: E402
    WEATHER_RAW_RETENTION_KEY,
    WEATHER_SERIES_RETENTION_KEY,
    lakehouse_write_legs,
    w11_write_mode,
    weather_mirror_rows,
    weather_series_rows,
    write_raw_rows_s3_retained,
)

_LAKEHOUSE_SOURCE = "weather_raw"
_SERIES_SOURCE = "weather_intraday_series"

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


def _persist_weather_row(
    conn,
    do_sf: bool,
    game_pk: int,
    venue_id: int,
    game_dt: datetime,
    weather: dict,
    source: str,
    observation_type: str,
    hours_to_first_pitch: int | None = None,
) -> dict:
    """Build the canonical weather_raw row dict; INSERT it into Snowflake when do_sf is set.

    E11.1-W11 Tier-C: returns the row so the caller can collect it for the S3 mirror leg
    (write_raw_rows_s3_retained). game_datetime_utc is a space-separated UTC string (matches the
    SF DDL + the export bridge's str(TIMESTAMP_NTZ) format) so the duckdb branch's try_cast is
    format-uniform. loaded_at is NOT set here — the SF DDL DEFAULT stamps it, and weather_mirror_rows
    stamps the S3 copy (so both legs agree)."""
    now = datetime.now(timezone.utc)
    if game_dt.tzinfo is not None:
        game_dt_utc = game_dt.astimezone(timezone.utc)
    else:
        game_dt_utc = game_dt.replace(tzinfo=timezone.utc)

    fetch_offset_hours = round((now - game_dt_utc).total_seconds() / 3600, 1)

    row = {
        "game_pk":                  game_pk,
        "venue_id":                 venue_id,
        "game_datetime_utc":        game_dt_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "fetch_offset_hours":       fetch_offset_hours,
        "temp_f":                   weather["temp_f"],
        "wind_speed_mph":           weather["wind_speed_mph"],
        "wind_direction_deg":       weather["wind_direction_deg"],
        "humidity_pct":             weather["humidity_pct"],
        "condition_text":           weather["condition_text"],
        "api_source":               source,
        "weather_observation_type": observation_type,
        "hours_to_first_pitch":     hours_to_first_pitch,
    }

    if do_sf:
        with conn.cursor() as cur:
            cur.execute(_INSERT_SQL, row)

    return row

# ── Checkpoint detection (forecast_intraday) ───────────────────────────────────

def _nearest_checkpoint(hours_until: float) -> int | None:
    """Return the checkpoint value if hours_until is within INTRADAY_WINDOW_HOURS of one."""
    for cp in INTRADAY_CHECKPOINTS:
        if abs(hours_until - cp) <= INTRADAY_WINDOW_HOURS:
            return cp
    return None

# ── Main ingestion logic ───────────────────────────────────────────────────────

def _flush_s3_mirror(rows: list[dict]) -> None:
    """Mirror collected weather_raw rows to S3 with INC-20 latest-per-period retention."""
    if not rows:
        return
    n = write_raw_rows_s3_retained(
        _LAKEHOUSE_SOURCE, weather_mirror_rows(rows),
        key_cols=WEATHER_RAW_RETENTION_KEY, ts_col="loaded_at",
    )
    log.info("mirrored %d row(s) → S3 lakehouse_raw/%s/ (retained latest-per-period)", n, _LAKEHOUSE_SOURCE)


def _already_fetched(conn, do_sf: bool, game_date: str, observation_type: str,
                     hours_to_first_pitch: int | None) -> set:
    """game_pks already having a row for this (date, obs-type, checkpoint). SF-only optimisation —
    skips redundant weather-API calls. In s3-only mode there is no SF to read, so return empty and
    let the retention writer collapse any re-fetch (correctness holds; only extra API calls)."""
    if not do_sf:
        return set()
    with conn.cursor() as cur:
        cur.execute(_ALREADY_FETCHED_SQL, {
            "game_date":            game_date,
            "observation_type":     observation_type,
            "hours_to_first_pitch": hours_to_first_pitch,
        })
        return {row[0] for row in cur.fetchall()}


def _run_forecast_pregame(conn, game_date: str, source: str, do_sf: bool, do_s3: bool) -> None:
    """Original daily pre-game forecast ingestion path."""
    with conn.cursor() as cur:
        cur.execute(_SCHEDULE_SQL, {"game_date": game_date})
        rows = cur.fetchall()
        col_names = [d[0].lower() for d in cur.description]
        games = [dict(zip(col_names, row)) for row in rows]

    if not games:
        log.info("No outdoor-park games found for %s — nothing to fetch.", game_date)
        return

    already_done = _already_fetched(conn, do_sf, game_date, "forecast_pregame", None)

    pending = [g for g in games if g["game_pk"] not in already_done]
    log.info(
        "Found %d outdoor-park games (%d already have forecast_pregame, skipping).",
        len(pending), len(already_done),
    )

    mirror: list[dict] = []
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

        mirror.append(_persist_weather_row(conn, do_sf, game_pk, venue_id, game_dt, weather,
                                           source, "forecast_pregame", None))
        log.info("  Saved: temp=%.1f°F  wind=%.1f mph (dir=%s°)  humidity=%s%%",
                 weather["temp_f"] or 0, weather["wind_speed_mph"] or 0,
                 weather["wind_direction_deg"], weather["humidity_pct"])
        success += 1

    if do_s3:
        _flush_s3_mirror(mirror)

    total = len(pending)
    log.info("forecast_pregame complete — %d/%d outdoor parks fetched.", success, total)
    if total > 0 and success == 0:
        log.error("All weather fetches failed.")
        sys.exit(1)


def _run_observed_at_first_pitch(conn, game_date: str, source: str, do_sf: bool, do_s3: bool) -> None:
    """Fetch observed weather from archive endpoint for completed games on game_date."""
    with conn.cursor() as cur:
        cur.execute(_COMPLETED_GAMES_SQL, {"game_date": game_date})
        rows = cur.fetchall()
        col_names = [d[0].lower() for d in cur.description]
        games = [dict(zip(col_names, row)) for row in rows]

    if not games:
        log.info("No completed outdoor-park games found for %s — nothing to fetch.", game_date)
        return

    already_done = _already_fetched(conn, do_sf, game_date, "observed_at_first_pitch", None)

    pending = [g for g in games if g["game_pk"] not in already_done]
    log.info(
        "Found %d completed outdoor games (%d already have observed row, skipping).",
        len(pending), len(already_done),
    )

    mirror: list[dict] = []
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

        weather = {**weather, "condition_text": weather.get("condition_text")}
        mirror.append(_persist_weather_row(conn, do_sf, game_pk, venue_id, game_dt, weather,
                                           "open-meteo", "observed_at_first_pitch", None))
        log.info("  Saved observed: temp=%.1f°F  wind=%.1f mph",
                 weather["temp_f"] or 0, weather["wind_speed_mph"] or 0)
        success += 1

    if do_s3:
        _flush_s3_mirror(mirror)

    log.info("observed_at_first_pitch complete — %d/%d games fetched.", success, len(pending))


def _run_forecast_intraday(conn, game_date: str, source: str, hours_to_first_pitch: int,
                           do_sf: bool, do_s3: bool) -> None:
    """Fetch intraday forecast snapshot for today's games at a specific checkpoint."""
    with conn.cursor() as cur:
        cur.execute(_SCHEDULE_SQL, {"game_date": game_date})
        rows = cur.fetchall()
        col_names = [d[0].lower() for d in cur.description]
        games = [dict(zip(col_names, row)) for row in rows]

    if not games:
        log.info("No outdoor-park games found for %s — nothing to fetch.", game_date)
        return

    already_done = _already_fetched(conn, do_sf, game_date, "forecast_intraday", hours_to_first_pitch)

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

    mirror: list[dict] = []
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

        mirror.append(_persist_weather_row(conn, do_sf, game_pk, venue_id, game_dt, weather,
                                           source, "forecast_intraday", hours_to_first_pitch))
        log.info("  Saved T-%dh: temp=%.1f°F  wind=%.1f mph",
                 hours_to_first_pitch, weather["temp_f"] or 0, weather["wind_speed_mph"] or 0)
        success += 1

    if do_s3:
        _flush_s3_mirror(mirror)

    log.info("forecast_intraday T-%dh complete — %d/%d fetched.", hours_to_first_pitch, success, len(eligible))


def _run_intraday_series(conn, game_date: str, source: str) -> None:
    """⭐ E11.1-W11-C ADDITION — hourly weather snapshot for EVERY slate park (not just the
    T-24/6/3/1h checkpoints), stored S3-ONLY as weather_intraday_series with an explicit captured_at.

    WHY: build a dense weather TIME-SERIES aligned to the odds line-movement series → the E13.16
    weather→line-movement hypothesis (do books lag weather updates → a totals timing edge). Every
    outdoor slate park is captured once per invocation (the weather_capture cron fires hourly), tagged
    with captured_at / captured_hour so the trajectory is reconstructable. Retention keeps the LATEST
    snapshot per (game, hour) within the game-day — the hours are the SIGNAL, so we do NOT collapse
    across hours (only a true intra-hour re-run collapses). S3-only: this is a brand-new source with
    no Snowflake table to decommission (aligns with 'all ingestion strictly to S3')."""
    with conn.cursor() as cur:
        cur.execute(_SCHEDULE_SQL, {"game_date": game_date})
        rows = cur.fetchall()
        col_names = [d[0].lower() for d in cur.description]
        games = [dict(zip(col_names, row)) for row in rows]

    if not games:
        log.info("intraday_series: no outdoor-park games for %s — nothing to capture.", game_date)
        return

    captured_at = datetime.now(timezone.utc)
    now_utc = captured_at
    mirror: list[dict] = []
    for g in games:
        game_pk  = g["game_pk"]
        venue_id = g["venue_id"]
        lat      = g["latitude"]
        lon      = g["longitude"]
        game_dt  = g["game_datetime_utc"]

        if isinstance(game_dt, str):
            game_dt = datetime.fromisoformat(game_dt)
        if game_dt.tzinfo is None:
            game_dt = game_dt.replace(tzinfo=timezone.utc)
        if lat is None or lon is None:
            log.warning("intraday_series: skipping venue_id=%s — missing GPS coordinates.", venue_id)
            continue

        weather = fetch_weather(source, lat, lon, game_dt)
        if weather is None:
            log.warning("intraday_series: no weather for game_pk=%d — skipping.", game_pk)
            continue

        hours_to_first_pitch = round((game_dt - now_utc).total_seconds() / 3600, 2)
        mirror.append({
            "game_pk":                  game_pk,
            "venue_id":                 venue_id,
            "game_datetime_utc":        game_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "hours_to_first_pitch":     hours_to_first_pitch,
            "temp_f":                   weather["temp_f"],
            "wind_speed_mph":           weather["wind_speed_mph"],
            "wind_direction_deg":       weather["wind_direction_deg"],
            "humidity_pct":             weather["humidity_pct"],
            "condition_text":           weather["condition_text"],
            "api_source":               source,
            "weather_observation_type": "forecast_intraday_series",
        })

    if not mirror:
        log.info("intraday_series: nothing captured for %s.", game_date)
        return

    n = write_raw_rows_s3_retained(
        _SERIES_SOURCE, weather_series_rows(mirror, captured_at=captured_at.isoformat()),
        key_cols=WEATHER_SERIES_RETENTION_KEY, ts_col="captured_at",
    )
    log.info("intraday_series: captured %d slate-park snapshot(s) → S3 lakehouse_raw/%s/ "
             "(captured_at=%s, retained latest-per-hour)", n, _SERIES_SOURCE, captured_at.isoformat())

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
        choices=["forecast_pregame", "observed_at_first_pitch", "forecast_intraday",
                 "intraday_series"],
        default="forecast_pregame",
        help=(
            "Type of weather observation to capture (default: forecast_pregame). "
            "intraday_series = the ⭐ hourly all-slate-park time-series (E13.16 precursor); "
            "captures EVERY outdoor slate park once, S3-only, tagged with captured_at."
        ),
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

    # E11.1-W11 Tier-C: which legs run (SF INSERT and/or S3 mirror) per W11_RAW_WRITE_MODE (default
    # 'snowflake' → unchanged). The intraday_series is ALWAYS S3-only (a brand-new source).
    do_sf, do_s3 = lakehouse_write_legs(w11_write_mode())

    log.info(
        "Weather ingest — date=%s  observation_type=%s  hours_to_first_pitch=%s  "
        "write_mode=%s (sf=%s, s3=%s)  dry_run=%s",
        game_date, args.observation_type, args.hours_to_first_pitch, w11_write_mode(),
        do_sf, do_s3, args.dry_run,
    )

    if args.dry_run:
        log.info("DRY RUN: no Snowflake writes or API calls.")
        log.info("  Would fetch %s weather via %s for outdoor parks on %s",
                 args.observation_type, args.source, game_date)
        return

    conn = get_snowflake_conn()
    try:
        if args.observation_type == "forecast_pregame":
            _run_forecast_pregame(conn, game_date, args.source, do_sf, do_s3)
        elif args.observation_type == "observed_at_first_pitch":
            _run_observed_at_first_pitch(conn, game_date, args.source, do_sf, do_s3)
        elif args.observation_type == "forecast_intraday":
            _run_forecast_intraday(conn, game_date, args.source, args.hours_to_first_pitch,
                                   do_sf, do_s3)
        elif args.observation_type == "intraday_series":
            # S3-only new source (the E13.16 precursor); do_sf/do_s3 don't gate it.
            _run_intraday_series(conn, game_date, args.source)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
