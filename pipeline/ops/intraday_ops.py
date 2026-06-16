import os
import subprocess
import sys
from datetime import date

from dagster import In, Nothing, OpExecutionContext, Out, SkipReason, op

SCRIPTS_DIR = "/app/scripts"
APP_DIR = "/app"
DBT_DIR = "/app/dbt"

# Story A2.16 port (2026-06-15) — these helpers ran `subprocess.run` with NO timeout
# (the A2.16 fix only reached sensor_ops.py). Incident 2026-06-15: the intraday
# odds_snapshot_ingest op (`parlay_api_ingestion.py odds`) WEDGED on a hung Parlay API
# request (~19:55 EDT) and the op never returned, blocking the snapshot. A hard
# subprocess ceiling converts an infinite hang into a bounded failure the sensor can
# retry cleanly. Odds polls get a TIGHTER 600s ceiling (a poll is seconds of work, so a
# hang should fail within the snapshot cadence, not sit for 30 min); dbt rebuilds keep
# the 1800s default.
_SUBPROCESS_TIMEOUT = 1800   # seconds (30 min) default
_POLL_TIMEOUT = 600          # seconds (10 min) — fast-fail ceiling for API polls


def _run_script(context: OpExecutionContext, script: str, args: list[str] | None = None,
                timeout: int = _SUBPROCESS_TIMEOUT) -> None:
    path = script if os.path.isabs(script) else f"{SCRIPTS_DIR}/{script}"
    cmd = [sys.executable, path] + (args or [])
    context.log.info(f"Running: {' '.join(cmd)} (timeout {timeout}s)")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=APP_DIR, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Exception(f"{os.path.basename(script)} exceeded {timeout}s hard timeout and was killed")
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        raise Exception(f"{os.path.basename(script)} failed (exit {result.returncode})\n{result.stderr}")


def _run_dbt(context: OpExecutionContext, args: list[str], timeout: int = _SUBPROCESS_TIMEOUT) -> None:
    cmd = ["dbtf"] + args + ["--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR]
    context.log.info(f"Running: {' '.join(cmd)} (timeout {timeout}s)")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=APP_DIR, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Exception(f"dbtf {args[0]} exceeded {timeout}s hard timeout and was killed")
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        raise Exception(f"dbtf {args[0]} failed (exit {result.returncode})\n{result.stderr}")


def _today() -> str:
    return date.today().strftime("%Y-%m-%d")


# ── Odds Snapshot ────────────────────────────────────────────────────────────

@op(out={"has_games": Out(bool)})
def check_games_today(context: OpExecutionContext) -> bool:
    """Query Snowflake to check if there are regular-season games today."""
    import snowflake.connector
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, load_pem_private_key,
    )

    key_path = os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]
    with open(key_path, "rb") as f:
        pem = f.read()
    key = load_pem_private_key(pem, password=None, backend=default_backend())
    private_key_bytes = key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        role=os.environ.get("SNOWFLAKE_ROLE", ""),
        database="baseball_data",
        private_key=private_key_bytes,
    )
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM baseball_data.betting.stg_statsapi_games "
            "WHERE official_date = %s AND game_type = 'R'",
            [date.today().isoformat()],
        )
        count = cur.fetchone()[0]
        cur.close()
    finally:
        conn.close()

    has_games = count > 0
    if has_games:
        context.log.info(f"Found {count} regular-season game(s) today — proceeding with odds snapshot.")
    else:
        context.log.info("No regular-season games today — odds snapshot will be skipped.")
    return has_games


@op(ins={"has_games": In(bool)}, out=Out(Nothing))
def odds_snapshot_ingest(context: OpExecutionContext, has_games: bool) -> None:
    if not has_games:
        context.log.info("No games today — skipping odds snapshot ingestion.")
        return
    _run_script(context, "parlay_api_ingestion.py", ["events"], timeout=_POLL_TIMEOUT)
    _run_script(context, "parlay_api_ingestion.py", ["odds"], timeout=_POLL_TIMEOUT)
    _run_script(context, "parlay_api_ingestion.py", ["line-movement"], timeout=_POLL_TIMEOUT)


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def odds_snapshot_dbt_rebuild(context: OpExecutionContext) -> None:
    _run_dbt(context, [
        "run",
        "--select",
        "stg_parlayapi_odds",
        "mart_odds_outcomes",
        "mart_closing_line_value",
        "mart_prediction_clv",
        "--target", "baseball_betting_and_fantasy",
    ])


@op(out=Out(Nothing))
def odds_current_dbt_rebuild(context: OpExecutionContext) -> None:
    """LIGHT rebuild of the *current-odds* path off the Odds-API raw capture — only
    `stg_oddsapi_odds` + `mart_odds_outcomes` (the lines a prediction/edge read).

    Story 12.3.7 / A2.18 — the I/O-bound capture runs every 30 min on a Railway cron
    (off the Dagster+ bill) into `oddsapi.mlb_odds_raw`. This op is fired by
    `odds_current_rebuild_sensor` on a DYNAMIC game-hours window (hourly from 3h before
    first pitch to last first pitch, + one near-close tick), NOT on every capture — so
    Dagster pays for ~12-14 light rebuilds on a game day and 0 on dark days, instead of
    ~48 full-chain rebuilds. The heavy post-hoc CLV/line-movement marts are split out to
    `odds_clv_dbt_rebuild` (once/day post-game) since they can't compute anything until
    the closing line locks at first pitch."""
    _run_dbt(context, [
        "run",
        "--select",
        "stg_oddsapi_odds",
        "mart_odds_outcomes",
        "--target", "baseball_betting_and_fantasy",
    ])


@op(out=Out(Nothing))
def odds_clv_dbt_rebuild(context: OpExecutionContext) -> None:
    """FULL post-game rebuild of the CLV / line-movement marts (Story 12.3.7 / A2.18).

    `mart_closing_line_value`, `mart_prediction_clv`, `mart_odds_line_movement` are all
    full-CTAS and all POST-HOC — the closing line doesn't exist until first pitch, so
    rebuilding them intraday is wasted compute. `odds_clv_rebuild_schedule` runs this
    ONCE/day after the last game (08:00 UTC). Re-runs the light path first so CLV is
    computed on the complete day (including any final post-last-pitch snapshots that the
    near-close current rebuild didn't catch). Includes `mart_odds_line_movement` (the old
    Parlay odds_snapshot path omitted it) so the open/close series stays fresh for the
    Epic-12 market meta-model."""
    _run_dbt(context, [
        "run",
        "--select",
        "stg_oddsapi_odds",
        "mart_odds_outcomes",
        "mart_closing_line_value",
        "mart_prediction_clv",
        "mart_odds_line_movement",
        "--target", "baseball_betting_and_fantasy",
    ])


# ── Intraday Weather ─────────────────────────────────────────────────────────

@op(out=Out(Nothing))
def intraday_weather_capture(context: OpExecutionContext) -> None:
    today = _today()
    for hours in [24, 6, 3, 1]:
        try:
            _run_script(context, "ingest_weather.py", [
                "--date", today,
                "--observation-type", "forecast_intraday",
                "--hours-to-first-pitch", str(hours),
            ])
        except Exception as e:
            context.log.warning(f"T-{hours}h weather capture failed (non-fatal): {e}")
    try:
        _run_script(context, "ingest_weather.py", ["--observation-type", "observed_at_first_pitch"])
    except Exception as e:
        context.log.warning(f"Observed-at-first-pitch capture failed (non-fatal): {e}")


# ── Intraday Schedule ────────────────────────────────────────────────────────

@op(out=Out(Nothing))
def intraday_schedule_capture(context: OpExecutionContext) -> None:
    _run_script(context, "ingest_statsapi.py", [
        "schedule",
        "--start-date", _today(),
        "--end-date", _today(),
        "--capture-reason", "intraday_gameday",
    ])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def intraday_lineup_rebuild(context: OpExecutionContext) -> None:
    """Rebuild lineup staging models so lineup_monitor_sensor sees confirmed lineups.

    stg_statsapi_lineups[_wide] are TABLE materializations — they only reflect
    data as of the last dbt run. intraday_schedule_capture refreshes the raw
    monthly_schedule source every 30 min, but without this rebuild the sensor
    always queries a stale table built at 12:00 UTC morning.
    """
    _run_dbt(context, [
        "run",
        "--select",
        "stg_statsapi_lineups",
        "stg_statsapi_lineups_wide",
        "stg_statsapi_probable_pitchers",
        "--target", "baseball_betting_and_fantasy",
    ])
