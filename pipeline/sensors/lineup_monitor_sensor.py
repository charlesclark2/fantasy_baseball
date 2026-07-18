import os
import subprocess
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dagster import (
    DefaultScheduleStatus,
    DefaultSensorStatus,
    RunRequest,
    ScheduleEvaluationContext,
    SensorEvaluationContext,
    SkipReason,
    schedule,
    sensor,
)

from pipeline.jobs.sensor_jobs import lineup_monitor_job

SCRIPTS_DIR = "/app/scripts"
APP_DIR = "/app"

_ET = ZoneInfo("America/New_York")
# E11.1-W12: the cadence-gate slate read moved off Snowflake to the S3 lakehouse
# (stg_statsapi_games) via DuckDB. (The lineup_monitor.py subprocess below keeps its own
# data access — its state table is a separate W13 migration, out of this wave's scope.)

# --- Early-game-aware cadence -------------------------------------------------
# The lineup-confirmed re-score must land >= 30 min before first pitch (Epic A1
# SLA). A flat hourly poll misses mid-day games: a 1:10pm ET game whose lineups
# post ~3h out can be re-scored as late as ~20 min pre-game (incident 2026-06-10,
# game 822970 BOS@TB). So we poll every _TIGHT_INTERVAL once any game is within
# _ACTIVE_LEAD of first pitch, and fall back to _IDLE_INTERVAL when the slate is
# hours away (keeps overnight Snowflake/subprocess load low). minimum_interval
# is the hard floor; the cursor (ISO ts of the last real monitor run) throttles
# the heavier monitor subprocess between floor ticks.
_FLOOR_SECONDS = 600                       # sensor wakes at most every 10 min
_TIGHT_INTERVAL = timedelta(minutes=10)    # active window: act on every floor tick
_IDLE_INTERVAL = timedelta(minutes=60)     # quiet window: hourly baseline
_ACTIVE_LEAD = timedelta(hours=5)          # "active" once first pitch is <= 5h out
# E11.20-COST (2026-07-16): beyond this horizon the monitor subprocess is SKIPPED entirely —
# no Snowflake session at all. MLB lineups post ~1–4h before first pitch (the active lead is
# 5h), so a tick with the next first pitch >8h out (overnight before an evening slate, the
# All-Star break, post-last-first-pitch) can only ever find nothing — yet each such run cost
# a warehouse resume (SELECT state + probables join + pipeline_run_log INSERT + COMMIT),
# 24/7, ~50 sessions/day. Measured: the lineup-monitor tick touched 273/336 30-min buckets/wk
# and ran through the break days at full cadence. The lineup_monitor_state dedup makes the
# skip safe: on re-entering the horizon every confirmed-but-unseen lineup is caught on the
# first tick. The no-games gate reads the S3 lakehouse via DuckDB (no SF wake) — the same
# proven read the sensor's cadence gate has used since W12. Fail-open: a lookup error runs
# the monitor anyway.
_MONITOR_HORIZON = timedelta(hours=8)

# INC-32 (2026-07-18) — HARD ceiling on the lineup_monitor.py subprocess run INSIDE the
# sensor evaluation. The op-side helpers got a 30-min ceiling on 2026-06-15 (a wedged dbt
# subprocess hung a whole run), but the SENSOR path's own subprocess.run below was left with
# NO timeout. When lineup_monitor.py wedges (its state table is still Snowflake — a warehouse
# resume / hung connection that never returns), the sensor evaluation BLOCKS the Dagster
# sensor-daemon worker thread FOREVER. The daemon evaluates sensors on a bounded thread pool,
# so one permanently-blocked eval starves the pool → sensor evaluations STOP mid-slate (7/17:
# evals ceased ~21:30Z, 7 of 15 games never got post_lineup). This is the "silently not
# running" mode E11.23's default_status=RUNNING self-start does NOT cover — the sensor is still
# nominally RUNNING, it just never produces a tick. A hard timeout converts the infinite hang
# into a fast, visible SkipReason so the next tick (and the daemon) keep going. lineup_monitor.py
# is a quick state query (seconds when healthy); 300s is a generous ceiling well under the 600s
# sensor floor. The heartbeat in check_monitors_healthy_op is the backstop if a tick still stalls.
_MONITOR_SUBPROCESS_TIMEOUT = 300  # seconds (5 min) — hard ceiling per lineup_monitor.py run


def _beyond_monitor_horizon(mins: float | None) -> str | None:
    """Return a human skip-reason when the monitor should not run at all this tick:
    no upcoming Preview games today (break day / post-last-first-pitch), or the next
    first pitch is beyond _MONITOR_HORIZON. None → run the monitor."""
    if mins is None:
        return "no upcoming games today — monitor skipped (no Snowflake session)"
    horizon_min = _MONITOR_HORIZON.total_seconds() / 60.0
    if mins > horizon_min:
        return (f"next first pitch in {mins:.0f} min (> {horizon_min:.0f} min horizon) — "
                f"monitor skipped (no Snowflake session)")
    return None


def _parse_output(stdout: str, key: str) -> str | None:
    """Extract value from '[OUTPUT] key=value' lines written by the monitor scripts."""
    for line in stdout.splitlines():
        if line.startswith(f"[OUTPUT] {key}="):
            return line.split("=", 1)[1].strip()
    return None


def _minutes_to_next_first_pitch(now_et: datetime) -> float | None:
    """Minutes until the earliest not-yet-started regular-season game on today's
    ET calendar day, or None if there are no upcoming games. Cheap query — safe
    to run every tick. `game_date` is the StatsAPI first-pitch instant stored as
    TIMESTAMP_TZ (tz-aware); a game already past first pitch but still flagged
    'Preview' clamps to 0 (treated as active)."""
    from betting_ml.utils.lakehouse_monitor import duck, lh, to_utc_datetime

    conn = duck()
    try:
        row = conn.execute(
            f"SELECT MIN(game_date) FROM read_parquet('{lh('stg_statsapi_games')}', "
            f"union_by_name=true) WHERE official_date = ? AND game_type = 'R' "
            f"AND abstract_game_state = 'Preview'",
            [now_et.date().isoformat()],
        ).fetchone()
    finally:
        conn.close()

    if not row or row[0] is None:
        return None
    # game_date reads back as an ISO VARCHAR from the lakehouse (INC-23); to_utc_datetime
    # coerces str/naive/aware to a tz-aware UTC datetime so we never .tzinfo/.astimezone a str
    # (the INC-23 sensor-crash class). Subtracting the ET-aware `now_et` is tz-correct.
    first_pitch = to_utc_datetime(row[0])
    return max(0.0, (first_pitch - now_et).total_seconds() / 60.0)


# E11.23: default_status=RUNNING so the sensor SELF-STARTS on the box (and after any
# Dagster-DB reset / re-host like INC-16) instead of booting STOPPED and silently never
# firing (the class that killed this sensor for 2 days, 2026-07-02). check_monitors_healthy_op
# alarms if it is ever manually STOPPED.
@sensor(job=lineup_monitor_job, minimum_interval_seconds=_FLOOR_SECONDS,
        default_status=DefaultSensorStatus.RUNNING)
def lineup_monitor_sensor(context: SensorEvaluationContext):
    """
    Early-game-aware lineup monitor. Polls every 10 min while any game is within
    5h of first pitch (so mid-day slates get their lineup-confirmed re-score well
    inside the Epic A1 30-min SLA), and hourly otherwise. Runs lineup_monitor.py
    to detect newly confirmed lineups / starter changes; emits a RunRequest
    (game_pks in op config) when found, else a SkipReason.

    Transient failures (Snowflake, subprocess) are swallowed as SkipReason so a
    flaky tick never fails the sensor.
    """
    now_et = datetime.now(_ET)

    # --- cadence gate: how soon is the next first pitch?
    try:
        mins = _minutes_to_next_first_pitch(now_et)
    except Exception as e:
        # Don't go dark if the schedule lookup hiccups — act this tick.
        context.log.warning(f"first-pitch lookup failed ({e}); running monitor anyway.")
        mins = 0.0

    # E11.20-COST: outside the monitor horizon, don't run the SF-querying subprocess at all
    # (previously the idle path still ran it hourly, 24/7 — even on no-game days).
    horizon_skip = _beyond_monitor_horizon(mins)
    if horizon_skip is not None:
        yield SkipReason(f"Horizon gate — {horizon_skip}.")
        return

    active = mins is not None and mins <= _ACTIVE_LEAD.total_seconds() / 60.0
    desired = _TIGHT_INTERVAL if active else _IDLE_INTERVAL

    last_run = None
    if context.cursor:
        try:
            last_run = datetime.fromisoformat(context.cursor)
        except ValueError:
            last_run = None

    if last_run is not None and (now_et - last_run) < desired:
        nxt = "no upcoming games" if mins is None else f"next pitch in {mins:.0f} min"
        yield SkipReason(
            f"Throttled — {int(desired.total_seconds() // 60)} min cadence "
            f"({'active' if active else 'idle'}; {nxt}); last run {last_run:%H:%M}."
        )
        return

    # Due to run — stamp the cursor now so the throttle measures real monitor runs.
    context.update_cursor(now_et.isoformat())

    yield _evaluate_lineup_monitor(context.log, triggered_by="lineup_monitor_sensor")


def _evaluate_lineup_monitor(log, triggered_by: str):
    """Run lineup_monitor.py and return a RunRequest for newly-confirmed game_pks, or a
    SkipReason if there is nothing new to score / the monitor errored.

    Shared by lineup_monitor_sensor (cadence-throttled tick) and lineup_monitor_schedule_*
    (fixed 30-min cron). The DEDUP lives entirely in lineup_monitor.py via lineup_monitor_state:
    it emits has_new_games=true ONLY for games not yet triggered (or a game in state that still
    lacks a post_lineup row / had a pitcher change), so firing this on a fixed cron re-scores each
    confirmed lineup at most once — exactly "fire off one time, don't re-run" — while still catching
    legitimate late scratches. Returns (not yields) so both a sensor and a schedule can wrap it.
    """
    script = os.path.join(SCRIPTS_DIR, "lineup_monitor.py")
    try:
        # INC-32: hard timeout so a wedged lineup_monitor.py (hung Snowflake connection) can
        # NEVER block the sensor-daemon worker thread indefinitely (→ all sensor evals stop
        # mid-slate). On timeout the child is killed and we skip this tick; the next tick retries.
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            cwd=APP_DIR,
            timeout=_MONITOR_SUBPROCESS_TIMEOUT,
        )
        if result.stdout:
            log.info(result.stdout)
        if result.stderr:
            log.warning(result.stderr)
        if result.returncode != 0:
            return SkipReason(
                f"lineup_monitor.py exited {result.returncode} — skipping tick. "
                f"stderr: {result.stderr[:400]}"
            )
    except subprocess.TimeoutExpired:
        # The killed child freed the daemon thread — page loud (a persistent timeout means the
        # monitor's Snowflake state read is wedging every tick) but never block the daemon.
        log.warning(
            f"[ALERT] lineup_monitor.py exceeded {_MONITOR_SUBPROCESS_TIMEOUT}s and was KILLED "
            "(INC-32 sensor-daemon-block guard). Skipping this tick; investigate the "
            "lineup_monitor_state Snowflake read if this recurs."
        )
        return SkipReason(
            f"lineup_monitor.py exceeded {_MONITOR_SUBPROCESS_TIMEOUT}s hard timeout — killed, "
            "tick skipped so the daemon keeps evaluating."
        )
    except Exception as e:
        return SkipReason(f"lineup_monitor.py failed to run: {e}")

    has_new = _parse_output(result.stdout, "has_new_games")
    game_pks = _parse_output(result.stdout, "new_game_pks") or ""

    if has_new != "true":
        return SkipReason("No newly confirmed lineups — nothing to trigger.")

    log.info(f"New lineups confirmed for game_pks: {game_pks}")
    # No run_key: deduplication is already handled by lineup_monitor_state in
    # Snowflake. Using run_key here would prevent pitcher-change re-triggers,
    # since the game_pks string would be identical to the original lineup trigger.
    return RunRequest(
        run_config={
            "ops": {
                "lineup_predict": {
                    "config": {"game_pks": game_pks}
                }
            }
        },
        tags={"triggered_by": triggered_by, "game_pks": game_pks},
    )


# ── 30-min cron backstop (2026-07-07) — DEMOTED to manual-fallback (INC-32, 2026-07-18) ──────────
# HISTORY: added 2026-07-07 because the lineup_monitor_SENSOR tick was unreliable on the box
# (repeated manual kicks). It drove the SAME lineup_monitor_job off a fixed 30-min cron as a
# reliable complement, relying on lineup_monitor.py's lineup_monitor_state dedup to keep a game
# firing at most once.
#
# WHY DEMOTED (INC-32): running BOTH the sensor (every 10 min) AND these schedules (:15/:45) is a
# check-then-act RACE — when a sensor tick and a schedule tick evaluate within the same window,
# BOTH spawn lineup_monitor.py and read lineup_monitor_state BEFORE either inserts, so BOTH see the
# game as "new" and BOTH emit a RunRequest → TWO full job runs, each firing its own dbt-runner
# POSTs. The concurrency cap serializes them but both still run the whole graph → wasted work +
# multiplied 409/queue contention (a direct contributor to the INC-32 stall/late-daily cluster).
# The sensor's unreliability — the ONLY reason for this backstop — is now fixed at the source
# (INC-32: the sensor's lineup_monitor.py subprocess has a hard timeout so it can no longer wedge
# the daemon) AND a tick-staleness heartbeat in check_monitors_healthy_op PAGES if the sensor ever
# goes dark. So the redundant second driver buys nothing and costs contention → the SENSOR is now
# the SOLE driver. These schedules stay DEFINED (default_status=STOPPED) as an operator-toggled
# manual fallback; if you ever re-enable one, expect the double-fire above to return.
# Two exprs cover the game-day window 14:00-03:30 UTC (cron can't wrap midnight); :15/:45 offset
# lands after the schedule_capture staging refresh (:00/:30).
def _lineup_schedule_body(context: ScheduleEvaluationContext):
    # E11.20-COST (2026-07-16): the cron backstop previously ran the SF-querying monitor
    # subprocess UNCONDITIONALLY 28×/day (14:00–03:30 UTC) — including break days and hours
    # with no first pitch anywhere near. Same horizon gate as the sensor (DuckDB-over-S3
    # slate read, no SF wake); fail-open on lookup errors so the backstop never goes dark.
    now_et = datetime.now(_ET)
    try:
        mins = _minutes_to_next_first_pitch(now_et)
    except Exception as e:
        context.log.warning(f"first-pitch lookup failed ({e}); running monitor anyway.")
        mins = 0.0
    horizon_skip = _beyond_monitor_horizon(mins)
    if horizon_skip is not None:
        return SkipReason(f"Horizon gate — {horizon_skip}.")
    return _evaluate_lineup_monitor(context.log, triggered_by="lineup_monitor_schedule")


# INC-32: default_status=STOPPED — the SENSOR is the sole driver; these are a manual fallback only
# (re-enabling one reintroduces the double-fire race documented above).
@schedule(job=lineup_monitor_job, cron_schedule="15,45 14-23 * * *",
          name="lineup_monitor_schedule_daytime",
          default_status=DefaultScheduleStatus.STOPPED)
def lineup_monitor_schedule_daytime(context: ScheduleEvaluationContext):
    return _lineup_schedule_body(context)


@schedule(job=lineup_monitor_job, cron_schedule="15,45 0-3 * * *",
          name="lineup_monitor_schedule_overnight",
          default_status=DefaultScheduleStatus.STOPPED)
def lineup_monitor_schedule_overnight(context: ScheduleEvaluationContext):
    return _lineup_schedule_body(context)
