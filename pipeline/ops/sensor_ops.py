import os
import subprocess
import sys
from datetime import date

from dagster import In, Nothing, OpExecutionContext, Out, op

SCRIPTS_DIR = "/app/scripts"
APP_DIR = "/app"
DBT_DIR = "/app/dbt"
_EB_DIR = "/app/betting_ml/scripts/eb_priors"


def _today() -> str:
    return date.today().strftime("%Y-%m-%d")


def _run_script(context: OpExecutionContext, script: str, args: list[str] | None = None) -> None:
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


def _run_dbt(context: OpExecutionContext, args: list[str]) -> None:
    cmd = ["dbtf"] + args + ["--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR]
    context.log.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=APP_DIR)
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        raise Exception(f"dbtf {args[0]} failed (exit {result.returncode})\n{result.stderr}")


# ── Lineup Monitor job ops ────────────────────────────────────────────────────

@op(out=Out(Nothing))
def lineup_ingest_schedule(context: OpExecutionContext) -> None:
    """Re-ingest schedule to pick up retroactive lineup confirmations."""
    _run_script(context, "ingest_statsapi.py", ["schedule"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lineup_dbt_staging_rebuild(context: OpExecutionContext) -> None:
    """Rebuild lineup and probable pitcher staging models."""
    _run_dbt(context, [
        "run",
        "--select",
        "stg_statsapi_lineups",
        "stg_statsapi_lineups_wide",
        "stg_statsapi_probable_pitchers",
        "--target", "baseball_betting_and_fantasy",
    ])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lineup_compute_posteriors(context: OpExecutionContext) -> None:
    """A1.11 Stage 4 — recompute EB lineup posteriors now that lineups are
    CONFIRMED (lineup_dbt_staging_rebuild just refreshed stg_statsapi_lineups).
    This is the authoritative pass: the morning daily job's compute_lineup_-
    posteriors_op runs best-effort on whatever had posted then. MERGE-keyed on
    (game_pk, batting_slot, batter_id), so re-running each sensor tick is
    idempotent. See project_posterior_staleness_jun2026."""
    _run_script(context, f"{_EB_DIR}/compute_lineup_posteriors.py", ["--game-date", _today()])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lineup_dbt_feature_rebuild(context: OpExecutionContext) -> None:
    """Rebuild the lineup + downstream game features with the fresh confirmed-
    lineup posteriors, BEFORE lineup_predict reads the feature store — so the
    post-lineup prediction reflects who is actually playing. Both models are
    table-materialized; the full rebuild re-reads eb_batter_posteriors_raw."""
    _run_dbt(context, [
        "build",
        "--select",
        "feature_pregame_lineup_features",
        "feature_pregame_game_features",
        "--target", "baseball_betting_and_fantasy",
    ])


@op(
    config_schema={"game_pks": str},
    ins={"start": In(Nothing)},
    out=Out(Nothing),
)
def lineup_predict(context: OpExecutionContext) -> None:
    """Run post-lineup predictions for the newly confirmed game_pks."""
    game_pks = context.op_config["game_pks"]
    args = ["--prediction-type", "post_lineup", "--lineup-confirmed"]
    if game_pks:
        args += ["--game-pks", game_pks]
    _run_script(context, "predict_today.py", args)


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lineup_odds_snapshot(context: OpExecutionContext) -> None:
    """Capture post-lineup odds snapshot via Parlay API."""
    _run_script(context, "parlay_api_ingestion.py", ["events"])
    _run_script(context, "parlay_api_ingestion.py", ["odds"])
    _run_script(context, "parlay_api_ingestion.py", ["line-movement"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lineup_dbt_clv_rebuild(context: OpExecutionContext) -> None:
    """Rebuild lineup-dependent feature models and CLV mart."""
    _run_dbt(context, [
        "run",
        "--select",
        "+stg_statsapi_lineups+",
        "mart_closing_line_value",
        "mart_prediction_clv",
        "--target", "baseball_betting_and_fantasy",
    ])


# ── Pre-game Snapshot job ops ─────────────────────────────────────────────────

@op(out=Out(Nothing))
def pregame_odds_snapshot(context: OpExecutionContext) -> None:
    """Capture pre-game odds snapshot via Parlay API."""
    _run_script(context, "parlay_api_ingestion.py", ["events"])
    _run_script(context, "parlay_api_ingestion.py", ["odds"])
    _run_script(context, "parlay_api_ingestion.py", ["line-movement"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def pregame_dbt_clv_rebuild(context: OpExecutionContext) -> None:
    """Rebuild CLV mart with the new pre-game snapshot."""
    _run_dbt(context, [
        "run",
        "--select",
        "mart_closing_line_value",
        "mart_prediction_clv",
        "--target", "baseball_betting_and_fantasy",
    ])
