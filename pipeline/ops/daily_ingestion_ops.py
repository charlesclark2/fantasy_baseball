import os
import subprocess
import sys
from datetime import date, timedelta

from dagster import HookContext, In, MetadataValue, Nothing, Out, failure_hook, op

SCRIPTS_DIR = "/app/scripts"
APP_DIR = "/app"
DBT_DIR = "/app/dbt"


def _run_script(context, script: str, args: list[str] | None = None) -> str:
    """Run a Python script and return its stdout. Raises on non-zero exit."""
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
    return result.stdout or ""


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
    # Open-Meteo is an external free API that occasionally returns 502/timeout.
    # Weather is not on the critical path to predict_today_morning — soft-fail
    # so a transient outage doesn't require a full manual re-run of the job.
    try:
        _run_script(context, "ingest_weather.py", ["--date", _today()])
    except Exception as e:
        context.log.warning(f"Weather ingest failed (non-fatal, predictions will run without weather): {e}")


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
    # A1.3: Now blocking for run_env and offense signals. check_signal_freshness.py
    # exits non-zero if either required signal has zero coverage on the latest
    # completed slate — that propagates as an exception here and fails the op,
    # preventing predict_today_morning from running on stale/missing inputs.
    # Secondary signals (starter, bullpen, matchup) remain non-blocking in the script.
    stdout = _run_script(context, "check_signal_freshness.py", ["--env", _target_env()])
    for line in stdout.splitlines():
        if line.startswith("[METRIC] signal_completeness_score="):
            try:
                score = float(line.split("=", 1)[1])
                context.add_output_metadata({"signal_completeness_score": MetadataValue.float(score)})
            except ValueError:
                pass


@failure_hook
def signal_freshness_failure_hook(context: HookContext) -> None:
    """Email-style alert when signal_freshness_check blocks the daily pipeline."""
    if context.op.name != "signal_freshness_check":
        return
    context.log.error(
        "[ALERT] signal_freshness_check FAILED — minimum required signals (run_env or offense) "
        f"are absent for today's completed slate. predict_today_morning will not run. "
        "Manual intervention required before game time. "
        "Check generate_run_env_signals_op and generate_offense_signals_op in the Dagster UI."
    )


# ── Epic O.4 / 16.4 — end-of-day sequential posterior updates ────────────────
# Advance the player / team / matchup-cell sequential-Bayes chains by one day for
# YESTERDAY's completed games. These run INSIDE the daily job (not a separate
# 05:00 UTC schedule) because yesterday's pitch data only lands during THIS job's
# statcast ingest → dbt_daily_build; the updates must run after that. Placed
# before dbt_umpire_feature_rebuild so the feature_pregame_game_features rebuild
# there picks up the freshly-chained team posteriors.
#
# `--date yesterday` (a fixed single day, NOT _recent_completed_dates()): the
# chains are strictly sequential and this job runs daily, so yesterday is the one
# missing day. The scripts are NOT idempotent per-date (re-running a chained date
# double-counts the observation), so a fixed single date is required; a missed day
# is recovered via `--backfill --season`. Off-days no-op gracefully (0 games → 0
# rows).
#
# The team bullpen_xwoba metric depends on eb_bullpen_posteriors (reliever-PA
# membership), which is produced by compute_bullpen_posteriors.py (Epic 6A) — NOT
# by any sequential script. That refresh was never wired into this job, so
# eb_bullpen_posteriors / eb_bullpen_team_posteriors went stale (last 2026-05-28)
# while off_xwoba + win_prob kept advancing, leaving the team bullpen-seq feature
# AND the deployed champion's team_eb_bullpen_xwoba imputed on live games. Fixed by
# compute_eb_bullpen_posteriors_op below, which MUST run before
# update_team_posteriors_op (bullpen branch reads it) and before the
# dbt_umpire_feature_rebuild that rebuilds feature_pregame_game_features. The script
# MERGE-upserts both tables, so a daily --game-date is idempotent/re-runnable.

_SEQ_DIR = "/app/betting_ml/scripts/sequential_bayes"
_EB_DIR = "/app/betting_ml/scripts/eb_priors"


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def compute_eb_bullpen_posteriors_op(context):
    _run_script(
        context,
        f"{_EB_DIR}/compute_bullpen_posteriors.py",
        ["--game-date", _one_day_ago()],
    )


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def update_player_posteriors_op(context):
    _run_script(context, f"{_SEQ_DIR}/update_player_posteriors.py", ["--date", _one_day_ago()])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def update_team_posteriors_op(context):
    _run_script(context, f"{_SEQ_DIR}/update_team_posteriors.py", ["--date", _one_day_ago()])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def update_matchup_cell_posteriors_op(context):
    _run_script(context, f"{_SEQ_DIR}/update_matchup_cell_posteriors.py", ["--date", _one_day_ago()])


# A1.11 Stage 4 — forward-looking EB posteriors for TODAY's slate (the games
# being predicted), NOT yesterday's results. This is the key difference from the
# sequential/bullpen ops above (which advance yesterday's beliefs via
# _one_day_ago): a lineup/starter EB posterior is specific to today's confirmed
# lineup / probable pitcher, so it must be COMPUTED for today and cannot carry
# forward. Both scripts MERGE on natural keys ((game_pk, batting_slot, batter_id)
# and (game_pk, pitcher_id)), so a daily --game-date is idempotent/re-runnable —
# which also lets the lineup_monitor sensor safely recompute lineups once they
# confirm. Outputs feed feature_pregame_starter_features /
# feature_pregame_lineup_features, rebuilt in dbt_umpire_feature_rebuild below.
# Before this op existed these tables went stale (compute_*_posteriors.py had no
# Dagster op at all) — same failure class as compute_eb_bullpen_posteriors_op
# above. See project_posterior_staleness_jun2026 / reference_bullpen_freshness_chain.
@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def compute_starter_posteriors_op(context):
    _run_script(context, f"{_EB_DIR}/compute_starter_posteriors.py", ["--game-date", _today()])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def compute_lineup_posteriors_op(context):
    # Best-effort morning pass on whatever lineups have posted; the lineup_monitor
    # sensor recomputes authoritatively once each game's lineup is confirmed.
    _run_script(context, f"{_EB_DIR}/compute_lineup_posteriors.py", ["--game-date", _today()])


# ── Predict phase ────────────────────────────────────────────────────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_umpires_late(context):
    # Retry after dbt-build (~10–11 AM ET) when assignments are reliably posted.
    # Soft-fail: umpire data is not on the critical path; a transient API error
    # should not require a full manual re-run of the job.
    try:
        _run_script(context, "ingest_umpires.py", ["--date", _today()])
    except Exception as e:
        context.log.warning(f"Late umpire ingest failed (non-fatal): {e}")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def dbt_umpire_feature_rebuild(context):
    # mart_bullpen_effectiveness + feature_pregame_team_features are rebuilt HERE
    # (after compute_eb_bullpen_posteriors_op writes yesterday's EB posteriors at
    # s17) — not just at dbt_daily_build (s16, which runs before that source exists).
    # The mart's 7-day lookback merge-updates yesterday's row from NULL eb to the
    # freshly-written value; the two table-materialized features then pass it through
    # to feature_pregame_game_features.{home,away}_bp_eb_xwoba. dbt resolves build
    # order from the ref graph. See reference_bullpen_freshness_chain.
    #
    # A1.11 Stage 4 — also rebuild the lineup + starter features here so today's
    # forward-looking EB posteriors (written by compute_lineup/starter_posteriors_op
    # in the posterior cluster just above) land in feature_pregame_game_features.
    # Both are table-materialized, so the full rebuild simply re-reads the fresh
    # eb_batter_posteriors_raw / eb_starter_posteriors sources.
    _run_dbt(context, [
        "build",
        "--select",
        "stg_statsapi_umpire_game_log",
        "feature_pregame_umpire_features",
        "mart_bullpen_effectiveness",
        "feature_pregame_team_features",
        "feature_pregame_starter_features",
        "feature_pregame_lineup_features",
        "feature_pregame_game_features",
        "--target", "baseball_betting_and_fantasy",
    ])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def predict_today_morning(context):
    _run_script(context, "predict_today.py", ["--prediction-type", "morning"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def update_pipeline_status(context):
    """Upsert today's pipeline run summary into pipeline_status after predict_today_morning."""
    _run_script(context, "update_pipeline_status.py")


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


# ── API cache warm (A0.3) ────────────────────────────────────────────────────

@op(
    ins={"predict_done": In(Nothing)},
    out=Out(Nothing),
    description="Writes API-ready JSON to S3 cache after predictions complete. "
                "Prevents Snowflake queries on every API request.",
)
def write_api_cache_op(context):
    """
    Queries Snowflake once after predict_today_morning completes and writes
    API-ready JSON to S3 so FastAPI never hits Snowflake per-request.

    TODO: implement full cache write logic in A0.3 completion:
    1. Query daily_model_predictions for today's qualified picks
    2. Query mart_clv_labeled_games for recent history
    3. Query mart_bankroll_state (or fallback) for performance summary
    4. Write each to S3 via set_cache()

    For now: log a warning so the cache miss path (Snowflake fallback)
    in FastAPI handles requests correctly.
    """
    context.log.warning(
        "write_api_cache_op is a stub — FastAPI will fall back to Snowflake "
        "for today's picks. Implement full cache write before beta launch."
    )


# ── Backfill phase ───────────────────────────────────────────────────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def backfill_prediction_log(context):
    _run_script(context, "backfill_prediction_log.py")
