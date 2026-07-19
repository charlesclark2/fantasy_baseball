"""
statcast_freshness_sensor.py — pipeline SLA hardening (post-incident 2026-06-10).

Root cause it addresses: Baseball Savant publishes day-D Statcast later than the
07:00-ET daily run can reliably see it, so `ingest_statcast` lands nothing for
"yesterday" and the whole pitch-derived chain (mart_game_results → feature store
→ every _one_day_ago posterior) silently runs a day behind. The daily run exits
green, so it hid for days.

This sensor makes the cadence data-driven instead of clock-driven: it polls for
yesterday's pitch data and, the moment Savant has it, fires `statcast_catchup_job`
to land it + make today's slate whole — with a hard deadline before first pitch.

Cadence (every 30 min; all date/time reasoning in US/Eastern = the baseball day):
  - Before _EARLIEST ET            → skip (yesterday's data won't be up yet).
  - No regular-season games yesterday → skip (nothing to wait for).
  - Yesterday's pitch data present   → skip ("fresh").
  - Missing & > _DEADLINE_LEAD before today's first pitch → RunRequest the
        catch-up (hourly run_key ⇒ bounded retries; self-stops once data lands).
  - Missing & within _DEADLINE_LEAD of first pitch → log ERROR + SkipReason. This
        is the loud signal the daily run never had; attach a Dagster+ alert policy
        to this sensor to page on it.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dagster import DefaultSensorStatus, RunRequest, SensorEvaluationContext, SkipReason, sensor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.jobs.sensor_jobs import statcast_catchup_job

_ET = ZoneInfo("America/New_York")
_EARLIEST = time(4, 0)              # don't bother before 04:00 ET
_DEADLINE_LEAD = timedelta(hours=2)  # must be in ≥ 2h before today's first pitch
_DEFAULT_DEADLINE = time(13, 0)     # used when today has no games to anchor on

# E11.1-W12: reads moved off Snowflake to the S3 lakehouse via DuckDB (instance-role
# credential_chain). `stg_statsapi_games` is the flattened slate; `stg_batter_pitches`
# (year-partitioned) is the S3 home of the Savant pitch data the old `savant.batter_pitches`
# raw fed. Snowflake-free — see betting_ml.utils.lakehouse_monitor.


def _conn():
    from betting_ml.utils.lakehouse_monitor import duck
    return duck()


def _had_rs_games(conn, d: date) -> bool:
    from betting_ml.utils.lakehouse_monitor import lh

    (n,) = conn.execute(
        f"SELECT COUNT(*) FROM read_parquet('{lh('stg_statsapi_games')}', union_by_name=true) "
        f"WHERE official_date = ? AND game_type = 'R'",
        [d.isoformat()],
    ).fetchone()
    return int(n) > 0


def _pitches_present(conn, d: date) -> bool:
    # stg_batter_pitches.game_date is a DATE; read only the year=YYYY/ partition so we don't
    # scan every season's pitch parquet (a full-glob metadata scan is ~10s, the partition ~2s).
    # A missing year= partition (no export yet for that season) means no pitches → False, NOT a
    # tick failure — that's exactly the season-start "fire the catchup" case the sensor handles.
    from betting_ml.utils.lakehouse_monitor import is_missing_glob, lh_year

    try:
        (n,) = conn.execute(
            f"SELECT COUNT(*) FROM read_parquet('{lh_year('stg_batter_pitches', d.year)}', "
            f"union_by_name=true) WHERE game_date = ?",
            [d.isoformat()],
        ).fetchone()
    except Exception as exc:  # noqa: BLE001
        if is_missing_glob(exc):
            return False
        raise
    return int(n) > 0


def _first_pitch_et(conn, d: date) -> datetime | None:
    """Earliest first-pitch for date d, as an aware US/Eastern datetime.
    game_date is the StatsAPI first-pitch instant stored as a tz-aware UTC timestamp in the
    lakehouse; a naive value is defensively treated as UTC."""
    from betting_ml.utils.lakehouse_monitor import lh, to_utc_datetime

    # 2026-07-19: exclude Postponed rows — a postponed game keeps its ORIGINAL (past) first-pitch
    # instant under the makeup official_date, so an unfiltered MIN can be hours in the past and
    # instantly "breach" the deadline (the 823523 rained-out-Saturday false CRITICAL).
    row = conn.execute(
        f"SELECT MIN(game_date) FROM read_parquet('{lh('stg_statsapi_games')}', union_by_name=true) "
        f"WHERE official_date = ? AND game_type = 'R' AND detailed_state <> 'Postponed'",
        [d.isoformat()],
    ).fetchone()
    if not row or row[0] is None:
        return None
    # game_date reads back as an ISO VARCHAR from the lakehouse (INC-23); to_utc_datetime coerces
    # str/naive/aware to a tz-aware UTC datetime (never .astimezone/.tzinfo a str) before the ET view.
    return to_utc_datetime(row[0]).astimezone(_ET)


# E11.23: default_status=RUNNING — self-start on the box / after a DB reset (INC-16 class).
@sensor(job=statcast_catchup_job, minimum_interval_seconds=1800,
        default_status=DefaultSensorStatus.RUNNING)
def statcast_freshness_sensor(context: SensorEvaluationContext):
    now_et = datetime.now(_ET)
    today = now_et.date()
    yesterday = today - timedelta(days=1)

    if now_et.time() < _EARLIEST:
        yield SkipReason("Before 04:00 ET — yesterday's Statcast won't be published yet.")
        return

    try:
        conn = _conn()
    except Exception as e:  # transient connection issue — don't error the sensor
        yield SkipReason(f"Lakehouse (DuckDB/S3) connection failed: {e}")
        return
    try:
        if not _had_rs_games(conn, yesterday):
            yield SkipReason(f"No regular-season games on {yesterday} — nothing to wait for.")
            return
        if _pitches_present(conn, yesterday):
            yield SkipReason(f"Statcast for {yesterday} already present — fresh.")
            return

        first_pitch = _first_pitch_et(conn, today)
    finally:
        conn.close()

    deadline = (first_pitch - _DEADLINE_LEAD) if first_pitch else \
        datetime.combine(today, _DEFAULT_DEADLINE, tzinfo=_ET)

    if now_et >= deadline:
        fp = first_pitch.strftime("%H:%M ET") if first_pitch else "n/a"
        # E11.8 (INC-5 / monitor-the-monitors): yield SkipReason here was a silent
        # path — the tick never failed, so no alert fired. Raising converts the SLA
        # breach into a visible tick failure; the sensor still retries on every
        # subsequent 30-min tick, so Statcast arriving later self-heals.
        msg = (
            f"[SLA BREACH] Statcast for {yesterday} still not published within "
            f"{_DEADLINE_LEAD} of today's first pitch ({fp}). "
            f"Today's slate will score WITHOUT {yesterday}'s completed games. "
            f"Manual check: uv run python scripts/savant_ingestion.py batter_pitches"
        )
        # INC-16-P6: email directly (Dagster+ tick-failure alerting is gone post-cutover).
        from pipeline.utils.alerting import send_alert
        send_alert("Statcast SLA breach", msg, severity="CRITICAL",
                   dedup_key=f"statcast_sla:{yesterday}")
        raise Exception(msg)

    # Missing, before the deadline → fire the catch-up. Hourly run_key bounds
    # retries to ~1/hour; once the catch-up lands the data the next tick sees it
    # present and skips.
    run_key = f"statcast-catchup-{yesterday}-{now_et:%H}"
    context.log.info(f"Statcast for {yesterday} not yet landed; firing catch-up (run_key={run_key}).")
    yield RunRequest(
        run_key=run_key,
        tags={"triggered_by": "statcast_freshness_sensor", "catchup_date": yesterday.isoformat()},
    )
