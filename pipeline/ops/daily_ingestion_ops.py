import os
import subprocess
import sys
from datetime import date, timedelta

from dagster import In, Nothing, Out, op

SCRIPTS_DIR = "/app/scripts"
APP_DIR = "/app"
DBT_DIR = "/app/dbt"


def _run_script(context, script: str, args: list[str] | None = None) -> None:
    path = script if os.path.isabs(script) else f"{SCRIPTS_DIR}/{script}"
    cmd = [sys.executable, path] + (args or [])
    context.log.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=APP_DIR)
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        raise Exception(f"{os.path.basename(script)} failed (exit {result.returncode})\n{result.stderr}")


def _run_dbt(context, args: list[str]) -> None:
    cmd = ["dbtf"] + args + ["--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR]
    context.log.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=APP_DIR)
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        raise Exception(f"dbtf {args[0]} failed (exit {result.returncode})\n{result.stderr}")


def _today() -> str:
    return date.today().strftime("%Y-%m-%d")


def _seven_days_ago() -> str:
    return (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")


def _is_sunday() -> bool:
    return date.today().weekday() == 6


def _dbt_daily_build_args() -> list[str]:
    today = date.today()
    target = ["--target", "baseball_betting_and_fantasy"]
    if today.weekday() == 6:
        return ["build", "--full-refresh"] + target
    elif today.day % 2 == 1:
        return ["build"] + target
    else:
        return ["run"] + target


# ── Odds API (disabled by default; retain for reactivation) ─────────────────

@op(out=Out(Nothing))
def ingest_odds_api_events(context):
    if os.getenv("ODDS_API_ENABLED", "false").lower() != "true":
        context.log.info("ODDS_API_ENABLED != true — skipping Odds API events")
        return
    _run_script(context, "odds_api_ingestion.py", ["events"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_odds_api_odds(context):
    if os.getenv("ODDS_API_ENABLED", "false").lower() != "true":
        context.log.info("ODDS_API_ENABLED != true — skipping Odds API odds")
        return
    _run_script(context, "odds_api_ingestion.py", ["odds"])


# ── Parlay API ───────────────────────────────────────────────────────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_parlay_events(context):
    _run_script(context, "parlay_api_ingestion.py", ["events"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_parlay_canonical_events(context):
    _run_script(context, "parlay_api_ingestion.py", ["events-canonical"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_parlay_odds(context):
    _run_script(context, "parlay_api_ingestion.py", ["odds"])


# ── Daily ingestion ──────────────────────────────────────────────────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_action_network(context):
    _run_script(context, "ingest_actionnetwork_betting.py", ["--date", _today()])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_statcast(context):
    _run_script(context, "savant_ingestion.py", ["batter_pitches"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_statsapi_schedule(context):
    _run_script(context, "ingest_statsapi.py", ["schedule"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_weather(context):
    _run_script(context, "ingest_weather.py", ["--date", _today()])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_umpires_early(context):
    # MLB often hasn't posted HP assignments at ~08:00 ET; non-fatal if empty.
    try:
        _run_script(context, "ingest_umpires.py", ["--date", _today()])
    except Exception as e:
        context.log.warning(f"Early umpire ingest failed (expected before ~10 AM ET): {e}")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_fangraphs_stuff_plus(context):
    if not _is_sunday():
        context.log.info("Not Sunday — skipping Stuff+")
        return
    _run_script(context, "ingest_fangraphs_stuff_plus.py", [
        "--season", str(date.today().year),
        "--window-types", "14d,30d,season",
    ])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_fangraphs_catcher_framing(context):
    if not _is_sunday():
        context.log.info("Not Sunday — skipping catcher framing")
        return
    _run_script(context, "ingest_catcher_framing.py", ["--season", str(date.today().year)])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_fangraphs_hitting_leaderboard(context):
    _run_script(context, "ingest_fangraphs_hitting_leaderboard.py", [
        "--season", str(date.today().year),
        "--window-types", "season",
    ])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_transactions(context):
    _run_script(context, "ingest_transactions.py", [
        "--start-date", _seven_days_ago(),
        "--end-date", _today(),
    ])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_oaa(context):
    _run_script(context, "ingest_oaa.py", ["--season", str(date.today().year)])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def compute_elo(context):
    _run_script(context, "/app/betting_ml/scripts/compute_elo.py")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def check_data_freshness(context):
    # Non-blocking: log a warning rather than failing the run.
    try:
        _run_script(context, "check_data_freshness.py")
    except Exception as e:
        context.log.warning(f"Data freshness check failed: {e}")


# ── dbt daily build ──────────────────────────────────────────────────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def dbt_daily_build(context):
    # Sunday → full-refresh; odd day → build; even day → run
    _run_dbt(context, _dbt_daily_build_args())


# ── Predict phase ────────────────────────────────────────────────────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_umpires_late(context):
    # Retry after dbt-build (~10–11 AM ET) when assignments are reliably posted.
    _run_script(context, "ingest_umpires.py", ["--date", _today()])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def dbt_umpire_feature_rebuild(context):
    _run_dbt(context, [
        "build",
        "--select",
        "stg_statsapi_umpire_game_log",
        "feature_pregame_umpire_features",
        "feature_pregame_game_features",
        "--target", "baseball_betting_and_fantasy",
    ])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def predict_today_morning(context):
    _run_script(context, "predict_today.py", ["--prediction-type", "morning"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def check_prediction_coverage(context):
    _run_script(context, "check_prediction_coverage.py")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def dbt_mart_prediction_clv(context):
    _run_dbt(context, ["build", "--select", "mart_prediction_clv", "--target", "baseball_betting_and_fantasy"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def compute_model_health(context):
    _run_script(context, "compute_model_health.py")


# ── Backfill phase ───────────────────────────────────────────────────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def backfill_prediction_log(context):
    _run_script(context, "backfill_prediction_log.py")
