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


def _two_days_ago() -> str:
    return (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")


def _one_day_ago() -> str:
    return (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")


def _target_env() -> str:
    # prod deployment sets TARGET_ENV=prod; branch/local default to dev.
    return os.environ.get("TARGET_ENV", "dev")


def _recent_completed_dates() -> list[str]:
    # Sub-model signal generators are anchored on mart_game_results, which is
    # pitch-derived (completed games only). After ingest_statcast + dbt_daily_build,
    # yesterday's games are present. A 2-day completed-game window mirrors the
    # SCD-2 ops' 2-day lookback buffer — robust to ingestion lag / a missed run,
    # and idempotent (MERGE / SCD-2 skip unchanged rows). Today is excluded: its
    # games have no pitch data yet, so it would score zero rows.
    return [_two_days_ago(), _one_day_ago()]


def _is_sunday() -> bool:
    return date.today().weekday() == 6


def _dbt_daily_build_args() -> list[str]:
    # `dbtf run` on most days (models only — fast, cheap); a periodic `dbtf
    # build` (run + tests) to catch data-quality issues. The weekly Sunday pass
    # also uses --full-refresh to correct incremental drift. Running tests every
    # day would roughly double warehouse cost for little marginal signal, so the
    # weekly build is the data-integrity checkpoint. NOTE: despite the op name
    # `dbt_daily_build`, most days execute a `run`, not a `build`. Add a midweek
    # build day here if a ~weekly test cadence proves too sparse.
    today = date.today()
    target = ["--target", "baseball_betting_and_fantasy"]
    if today.weekday() == 6:  # Sunday: weekly full rebuild + full test suite
        return ["build", "--full-refresh"] + target
    return ["run"] + target


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
def ingest_sprint_speed(context):
    if not _is_sunday():
        context.log.info("Not Sunday — skipping sprint speed")
        return
    _run_script(context, "ingest_sprint_speed.py", ["--season", str(date.today().year)])


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


# ── Epic O.2 — Sub-model signal generation ───────────────────────────────────
# Each op scores the recently-completed game window (see _recent_completed_dates)
# and MERGEs into its signal table. These keep feature_pregame_sub_model_signals
# current as new games complete — the Layer-3 training feed. They do NOT score
# today's upcoming slate (the generators are anchored on the pitch-derived
# mart_game_results), so they do not feed today's predict_today; that link is
# Epic 9. concurrency_key tags the ops for the "snowflake_write" pool if/when the
# job moves off in_process_executor.

_SUB_MODEL_OP_TAGS = {"dagster/concurrency_key": "snowflake_write"}


@op(ins={"start": In(Nothing)}, out=Out(Nothing), tags=_SUB_MODEL_OP_TAGS)
def generate_run_env_signals_op(context):
    env = _target_env()
    for d in _recent_completed_dates():
        _run_script(context, "/app/betting_ml/scripts/generate_run_env_signals.py",
                    ["--date", d, "--env", env])


@op(ins={"start": In(Nothing)}, out=Out(Nothing), tags=_SUB_MODEL_OP_TAGS)
def generate_offense_signals_op(context):
    env = _target_env()
    for d in _recent_completed_dates():
        _run_script(context, "/app/betting_ml/scripts/offense_v2/generate_offense_signals.py",
                    ["--date", d, "--env", env])


@op(ins={"start": In(Nothing)}, out=Out(Nothing), tags=_SUB_MODEL_OP_TAGS)
def generate_starter_signals_op(context):
    env = _target_env()
    for d in _recent_completed_dates():
        _run_script(context, "/app/betting_ml/scripts/starter_v1/generate_starter_signals.py",
                    ["--date", d, "--env", env])


@op(ins={"start": In(Nothing)}, out=Out(Nothing), tags=_SUB_MODEL_OP_TAGS)
def generate_starter_ip_signals_op(context):
    env = _target_env()
    for d in _recent_completed_dates():
        _run_script(context, "/app/betting_ml/scripts/starter_v1/generate_starter_ip_signals.py",
                    ["--date", d, "--env", env])


@op(ins={"start": In(Nothing)}, out=Out(Nothing), tags=_SUB_MODEL_OP_TAGS)
def generate_bullpen_signals_op(context):
    # Champion is v2; --v2-only keeps the daily op fast. (bullpen_v1 is superseded
    # by 6D; drop the flag if v1 needs to advance daily too.) Wired downstream of
    # the starter-IP op because bullpen_v2 Candidate B reads starter_ip_signals
    # (starter_ip_p20_outs) for exposure scaling.
    env = _target_env()
    for d in _recent_completed_dates():
        _run_script(context, "/app/betting_ml/scripts/generate_bullpen_signals.py",
                    ["--date", d, "--env", env, "--v2-only"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing), tags=_SUB_MODEL_OP_TAGS)
def generate_matchup_signals_op(context):
    # Epic 8.6 / O.6. matchup_v1 writes to mart_sub_model_signals via the SCD-2
    # writer. signal_available is false for games without enough lineup/pitcher
    # archetype-posterior coverage (early-season call-ups, sparse history) — that
    # is expected and handled by the freshness check (matchup is reported but
    # excluded from the catastrophic completeness floor).
    env = _target_env()
    for d in _recent_completed_dates():
        _run_script(context, "/app/betting_ml/scripts/eb_priors/generate_matchup_signals.py",
                    ["--date", d, "--env", env])


@op(
    ins={
        "run_env_done":   In(Nothing),
        "offense_done":   In(Nothing),
        "starter_done":   In(Nothing),
        "starter_ip_done": In(Nothing),
        "bullpen_done":   In(Nothing),
        "matchup_done":   In(Nothing),
    },
    out=Out(Nothing),
)
def dbt_sub_model_signals_rebuild(context):
    # Fan-in: refresh the wide PIVOT once all six signal tables are written.
    _run_dbt(context, [
        "build",
        "--select", "feature_pregame_sub_model_signals",
        "--target", "baseball_betting_and_fantasy",
    ])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def signal_freshness_check(context):
    # NON-BLOCKING for now: predict_today does not yet consume these signals
    # (Epic 9), so a signal gap must not block predictions. The script still
    # exits non-zero on catastrophic loss; we log it as a warning rather than
    # raising. Flip to blocking (drop the try/except) once Epic 9 wires the
    # signals into predict_today.
    try:
        _run_script(context, "check_signal_freshness.py", ["--env", _target_env()])
    except Exception as e:
        context.log.warning(f"Signal freshness check reported a problem: {e}")


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


# ── SCD-2 incremental updates ────────────────────────────────────────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def update_market_features_scd2(context):
    # Runs after dbt_daily_build so mart_odds_outcomes contains today's fresh odds.
    # 2-day lookback is a safe buffer against ingestion delays or partial runs.
    _run_script(context, "backfill_market_features_scd2.py", ["--since", _two_days_ago()])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def dbt_pregame_odds_rebuild(context):
    # Rebuild feature_pregame_odds_features (and its dependents) now that the
    # SCD-2 table has been updated with today's line state.
    _run_dbt(context, [
        "build",
        "--select", "feature_pregame_odds_features+",
        "--target", "baseball_betting_and_fantasy",
    ])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def update_lineup_state_scd2(context):
    # Runs after dbt_daily_build so monthly_schedule contains today's fresh lineup data.
    # 2-day lookback processes upcoming games where pre-game scratches are most likely.
    _run_script(context, "backfill_lineup_state_scd2.py", ["--since", _two_days_ago()])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def dbt_lineup_feature_rebuild(context):
    # Rebuild feature_pregame_injury_status (SCD-2 promotion from stg) and all
    # downstream nodes, which includes feature_pregame_lineup_features.
    # Selecting from the upstream injury model ensures both are rebuilt in
    # dependency order in a single dbt invocation.
    _run_dbt(context, [
        "build",
        "--select", "feature_pregame_injury_status+",
        "--target", "baseball_betting_and_fantasy",
    ])


# ── Player profile update (weekly) ───────────────────────────────────────────

@op(out=Out(Nothing))
def ingest_player_profiles_update(context):
    """Weekly update: fetch changed profiles via people/changes + detect new call-ups."""
    _run_script(context, "ingest_player_profiles.py", ["update"])


# ── Backfill phase ───────────────────────────────────────────────────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def backfill_prediction_log(context):
    _run_script(context, "backfill_prediction_log.py")
