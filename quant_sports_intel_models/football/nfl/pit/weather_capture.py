"""weather_capture.py — TIME-CRITICAL forward capture of NFL game-site weather FORECASTS.

⏰ WHY THIS CANNOT WAIT AND CANNOT BE BACKFILLED. The Open-Meteo *archive* endpoint returns what
the weather ACTUALLY WAS, not what the forecast SAID on a historical Tuesday. A model that builds
on Tuesday sees a forecast; a backtest built from the archive sees the outcome. Training on the
outcome and serving on the forecast is a hard leak in one direction and a hard distribution shift
in the other — NF-W0's defect #1, which also showed `schedules.temp`/`wind` are realized
game-book values (0 of 177 unplayed 2026 games carry a temp). The ONLY way to get an honest
Tuesday forecast for week 3 is to have fetched it on week 3's Tuesday. Every uncaptured week is
permanently absent from the training frame.

THREE ADAPTATIONS vs MLB's `scripts/ingest_weather.py` (the story's own list, all load-bearing):

  1. THE LADDER REACHES T-120h. MLB's checkpoints top out at T-24h because a baseball build is
     same-day. An NFL **Tuesday** build for a Sunday game stands ~5 days out, so copying MLB
     verbatim would give the Tue/Fri builds NO WEATHER AT ALL — the exact feature the story
     exists to make backtestable. Ladder: [120, 72, 48, 24, 3, 1].
  2. S3-NATIVE, SNOWFLAKE-FREE. MLB writes `statsapi.weather_raw`; this writes the append-only
     PIT Delta store under `nfl/pit/weather/` with the §13 stamps, plus the write-once raw
     payload under `nfl/pit_raw/weather/`.
  3. GATE ON THE PER-GAME `roof`, NOT the team's `is_dome_home`. `stg_nfl_team_geo.is_dome_home`
     is documented INFORMATIONAL — a team can play a neutral-site/international game outdoors,
     and 8 of 2026's games are international. See `venues.py` for both live findings (a blank
     `roof` is a retractable venue whose state is not yet knowable; a neutral-site game is not at
     the home team's coordinates).

TIER: WARN / ALERT-loud-but-continue. A per-game fetch failure must never sink the batch — the
next checkpoint on the ladder catches the game again, and a partially-captured slate is far
better than none. But the manifest reports every skip, and a leg that captured NOTHING for a
slate that HAS eligible games is escalated (`escalate=True`) so the caller can page: "0 rows and
no error" is the silent-empty signature this repo keeps getting bitten by.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from . import store
from .schedule import ScheduledGame, current_season, read_schedule
from .timestamps import CaptureStamps, now_utc
from .venues import VenueResolutionError, resolve_venue

log = logging.getLogger(__name__)

CAPTURE_SOURCE = "weather"

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

#: Hours-before-kickoff checkpoints. T-120h ≈ the Tuesday build for a Sunday game (the reason the
#: ladder is not MLB's); T-1h ≈ the final pre-kickoff state.
CHECKPOINT_LADDER: tuple[int, ...] = (120, 72, 48, 24, 3, 1)

#: A capture fires when the game sits within ±this many hours of a checkpoint. Sized for an
#: HOURLY cron with margin: ±0.75h means a fire that slips by up to 45 minutes still lands the
#: checkpoint, and consecutive ladder rungs (min gap 2h, at 3h→1h) can never both match.
CHECKPOINT_WINDOW_HOURS = 0.75

#: The weekly-build snapshot. Distinct OBSERVATION TYPE from the ladder rungs so a consumer can
#: ask for "the weekly build's forecast" without reconstructing which rung that was.
OBS_PREGAME = "forecast_pregame"
OBS_INTRADAY = "forecast_intraday"

#: Response fields that move on every call without the FORECAST changing (server timing). Excluded
#: from the content hash — see `timestamps.payload_sha256`, and `hash_excluded_keys` on every row.
HASH_VOLATILE_KEYS: tuple[str, ...] = ("_generationtime_ms",)

_HTTP_TIMEOUT_SEC = 30
_HTTP_MAX_ATTEMPTS = 3
_HTTP_BACKOFF_BASE_SEC = 2.0

#: Requested hourly variables. `precipitation_probability` + `precipitation` are NFL-relevant in a
#: way they are not for MLB (a game is played through rain), and wind gusts matter for kicking.
_HOURLY_VARS = (
    "temperature_2m,relativehumidity_2m,precipitation,precipitation_probability,"
    "windspeed_10m,windgusts_10m,winddirection_10m,cloudcover,pressure_msl"
)


def _get_with_retry(url: str, params: dict) -> dict | None:
    import time

    import requests

    last: Exception | None = None
    for attempt in range(1, _HTTP_MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, params=params, timeout=_HTTP_TIMEOUT_SEC)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < _HTTP_MAX_ATTEMPTS:
                time.sleep(_HTTP_BACKOFF_BASE_SEC * (2 ** (attempt - 1)))
    log.warning("Open-Meteo request failed after %d attempts: %s", _HTTP_MAX_ATTEMPTS, last)
    return None


def nearest_checkpoint(hours_until_kickoff: float, ladder=CHECKPOINT_LADDER,
                       window: float = CHECKPOINT_WINDOW_HOURS) -> int | None:
    """The ladder rung this moment belongs to, or None if it belongs to no rung.

    PURE — this is the scheduling decision the hourly cron makes, so it is unit-tested offline
    rather than inferred from a live run.
    """
    if hours_until_kickoff < 0:
        return None  # kicked off: there is no pre-kickoff forecast left to capture
    for cp in ladder:
        if abs(hours_until_kickoff - cp) <= window:
            return cp
    return None


def fetch_forecast(lat: float, lon: float, kickoff_utc: datetime) -> dict | None:
    """The Open-Meteo hourly FORECAST at the kickoff hour. Free, no API key.

    ⛔ Always the FORECAST endpoint, never the archive — the archive returns observations, which
    is the very substitution this capture exists to prevent. A kickoff too far out for the
    forecast horizon simply returns no matching hour, which is an honest empty, not an outcome.
    """
    day = kickoff_utc.astimezone(timezone.utc).strftime("%Y-%m-%d")
    payload = _get_with_retry(
        OPEN_METEO_FORECAST_URL,
        {
            "latitude": lat, "longitude": lon, "hourly": _HOURLY_VARS,
            "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
            "precipitation_unit": "inch", "timezone": "UTC",
            # An explicit start/end date pins the kickoff day. ⛔ Do NOT also pass `forecast_days`
            # — Open-Meteo 400s on the combination (measured 2026-08-05), and a 400 here reads
            # exactly like a transient outage in the log. The forecast endpoint already reaches
            # 16 days, so T-120h (5 days) sits well inside its horizon without the extra param.
            "start_date": day, "end_date": day,
        },
    )
    if payload is None:
        return None
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        log.warning("Open-Meteo returned no hourly series for (%.4f, %.4f) on %s", lat, lon, day)
        return None

    target = kickoff_utc.astimezone(timezone.utc).replace(tzinfo=None)
    best = min(
        range(len(times)),
        key=lambda i: abs((datetime.strptime(times[i], "%Y-%m-%dT%H:%M") - target).total_seconds()),
    )

    def at(name: str):
        series = hourly.get(name) or []
        return series[best] if best < len(series) else None

    return {
        "forecast_hour_utc": times[best],
        "temp_f": at("temperature_2m"),
        "humidity_pct": at("relativehumidity_2m"),
        "precip_in": at("precipitation"),
        "precip_prob_pct": at("precipitation_probability"),
        "wind_speed_mph": at("windspeed_10m"),
        "wind_gust_mph": at("windgusts_10m"),
        "wind_direction_deg": at("winddirection_10m"),
        "cloud_cover_pct": at("cloudcover"),
        "pressure_msl_hpa": at("pressure_msl"),
        # The vendor's own model-run stamp: the closest thing Open-Meteo publishes to a
        # `vendor_release_timestamp`. Absent on some responses → stays NULL rather than invented.
        "_generationtime_ms": payload.get("generationtime_ms"),
        "_utc_offset_seconds": payload.get("utc_offset_seconds"),
    }


def eligible_games(
    games: list[ScheduledGame], *, now: datetime, checkpoint: int | None, ladder=CHECKPOINT_LADDER,
) -> list[tuple[ScheduledGame, int]]:
    """(game, checkpoint) pairs due for capture at `now`.

    `checkpoint=None` = auto mode (the hourly cron): each game is matched against the whole
    ladder. A pinned checkpoint captures every game currently inside THAT rung's window.
    """
    out: list[tuple[ScheduledGame, int]] = []
    for g in games:
        hours = (g.kickoff_utc - now).total_seconds() / 3600.0
        if checkpoint is None:
            cp = nearest_checkpoint(hours, ladder=ladder)
        else:
            cp = checkpoint if abs(hours - checkpoint) <= CHECKPOINT_WINDOW_HOURS else None
        if cp is not None:
            out.append((g, cp))
    return out


def pregame_games(games: list[ScheduledGame], *, now: datetime, horizon_hours: float = 168.0
                  ) -> list[tuple[ScheduledGame, str]]:
    """Games for the WEEKLY-BUILD snapshot: every not-yet-kicked-off game inside `horizon_hours`.

    Keyed on the game's own week so the weekly capture is idempotent per (game, week-build) — a
    Tuesday re-fire produces the same `capture_id` and is deduplicated by the store rather than
    appended twice.
    """
    out = []
    for g in games:
        hours = (g.kickoff_utc - now).total_seconds() / 3600.0
        if 0 <= hours <= horizon_hours:
            out.append((g, f"week{g.week}"))
    return out


def _row_for(game: ScheduledGame, venue, forecast: dict, *, observation_type: str,
             checkpoint_label: str, now: datetime) -> dict:
    hours_to_kickoff = round((game.kickoff_utc - now).total_seconds() / 3600.0, 3)
    subject = f"{game.game_id}|{observation_type}|{checkpoint_label}"
    stamps = CaptureStamps.build(
        capture_source=CAPTURE_SOURCE,
        subject_key=subject,
        checkpoint=checkpoint_label,
        payload=forecast,
        # Open-Meteo stamps every response with its own server timing, so two IDENTICAL forecasts
        # hash differently and every benign re-fetch would look like a content change. Declared
        # (and stored as `hash_excluded_keys`) rather than silently dropped.
        hash_exclude=HASH_VOLATILE_KEYS,
        # A FORECAST's feature_timestamp is the moment the forecast was OBTAINED, not the hour it
        # describes. The described hour is in the FUTURE; calling that the feature time would make
        # every forecast look like it leaked (feature_timestamp > projection_timestamp) and the
        # guard would reject the whole leg. `forecast_hour_utc` is carried separately.
        feature_timestamp=now,
        capture_timestamp=now,
        # Open-Meteo publishes no per-response as-of/model-run timestamp. A DECLARED absence, so
        # the guard can tell "the vendor doesn't publish one" from "our writer forgot".
        source_timestamp=None,
        vendor_release_timestamp=None,
    )
    row = stamps.as_dict()
    row.update(
        {
            "record_tier": "weather",
            "source_timestamp_absent_reason": "open-meteo publishes no per-response model-run as-of stamp",
            "game_id": game.game_id,
            "season": game.season,
            "week": game.week,
            "game_type": game.game_type,
            "home_team": game.home_team,
            "away_team": game.away_team,
            "kickoff_timestamp": game.kickoff_utc.isoformat(),
            "observation_type": observation_type,
            "checkpoint_label": checkpoint_label,
            "hours_to_kickoff": hours_to_kickoff,
            "venue_name": venue.venue_name,
            "latitude": venue.latitude,
            "longitude": venue.longitude,
            "is_neutral_site": venue.is_neutral_site,
            # The roof facts, stored rather than applied: `roof_known=False` marks a retractable
            # venue whose state is NOT yet knowable, so a consumer can gate honestly instead of
            # inheriting a post-hoc `closed`/`open` (venues.py FINDING 1).
            "roof_raw": venue.roof_raw,
            "roof_known": venue.roof_known,
            "is_fixed_dome": venue.is_fixed_dome,
            "api_source": "open-meteo",
        }
    )
    for k, v in forecast.items():
        row[k.lstrip("_") if k.startswith("_") else k] = v
    row["payload"] = forecast
    return row


def run_weather_capture(
    season: int | None = None,
    *,
    observation_type: str = OBS_INTRADAY,
    checkpoint: int | None = None,
    now: datetime | None = None,
    games: list[ScheduledGame] | None = None,
    bucket: str | None = None,
    local_root: str | None = None,
    dry_run: bool = False,
    fetch=fetch_forecast,
) -> dict:
    """Capture one pass of NFL game-site weather forecasts. Returns a manifest.

    `fetch` is injectable so the whole decision path (schedule → venue → ladder → stamps → store)
    is testable offline without a network call — the fetch is the ONLY part that needs the wire.
    """
    now = now or now_utc()
    season = season if season is not None else current_season(now)
    if games is None:
        games = read_schedule(season)

    if observation_type == OBS_PREGAME:
        due = pregame_games(games, now=now)
    else:
        due = [(g, f"T-{cp}h") for g, cp in eligible_games(games, now=now, checkpoint=checkpoint)]

    manifest = {
        "season": season, "observation_type": observation_type, "checkpoint": checkpoint,
        "now": now.isoformat(), "games_in_season": len(games), "games_due": len(due),
        "captured": 0, "skipped_dome": 0, "skipped_venue_unresolved": 0, "fetch_failed": 0,
        "refusals": [], "written": 0, "skipped_duplicate": 0, "skipped_recapture": 0,
        "revisions": [], "escalate": False,
    }

    rows: list[dict] = []
    eligible = 0
    for game, label in due:
        try:
            venue = resolve_venue(game.as_venue_input())
        except VenueResolutionError as exc:
            # ⛔ REFUSED, never fetched at the home team's coordinates — silently capturing the
            # wrong city is worse than capturing nothing (venues.py FINDING 2).
            manifest["skipped_venue_unresolved"] += 1
            manifest["refusals"].append(str(exc))
            log.warning("ALERT [nfl/pit/weather] %s", exc)
            continue
        if not venue.capture:
            manifest["skipped_dome"] += 1
            continue
        eligible += 1
        if dry_run:
            continue
        forecast = fetch(venue.latitude, venue.longitude, game.kickoff_utc)
        if not forecast:
            manifest["fetch_failed"] += 1
            log.warning(
                "ALERT [nfl/pit/weather] no forecast for %s @ %s (%s) — the next ladder rung "
                "retries it", game.game_id, venue.venue_name, label,
            )
            continue
        rows.append(_row_for(game, venue, forecast, observation_type=observation_type,
                             checkpoint_label=label, now=now))

    manifest["eligible"] = eligible
    manifest["captured"] = len(rows)

    if rows and not dry_run:
        written = store.append_captures(
            rows, source=CAPTURE_SOURCE, bucket=bucket, local_root=local_root,
            # A forecast is a MOVING quantity: a re-read inside the same ladder rung legitimately
            # differs and is not a vendor revision. The first capture stands as that rung's record.
            semantics=store.LIVE_VALUE_SEMANTICS,
        )
        manifest.update(
            {k: written[k] for k in ("written", "skipped_duplicate", "skipped_recapture", "revisions")}
        )

    # THE SILENT-EMPTY GUARD: eligible games but nothing captured is the "0 rows and no error"
    # signature — escalate rather than returning a clean-looking manifest.
    if eligible and not dry_run and manifest["captured"] == 0:
        manifest["escalate"] = True
        log.warning(
            "ALERT [nfl/pit/weather] %d eligible game(s) but ZERO captured — this slate's forecast "
            "is being LOST and cannot be backfilled.", eligible,
        )
    return manifest
