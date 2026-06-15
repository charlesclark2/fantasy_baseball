import os
import subprocess
import sys
from datetime import date

from dagster import In, Nothing, OpExecutionContext, Out, RetryPolicy, op

SCRIPTS_DIR = "/app/scripts"
APP_DIR = "/app"
DBT_DIR = "/app/dbt"
_EB_DIR = "/app/betting_ml/scripts/eb_priors"

# Epic A1 (Pipeline SLA & Reliability): the sensor-fired catch-up ops are idempotent
# re-attempts (incremental ingestion + MERGE-keyed dbt rebuilds), so a transient
# Snowflake hiccup (warehouse resume, incremental-MERGE lock, network blip) should
# self-heal rather than page. The 2026-06-11 single failure looked like a textbook
# transient — but it did NOT self-heal: catchup_dbt_rebuild has failed EVERY run
# since 2026-06-11 05:17 (all 3 attempts exhausted). Root cause is NOT transient: it
# runs `dbtf build` (models + TESTS) on the stg_batter_pitches+ subtree, whereas the
# weekday daily build runs `dbtf run` (models only) — so a data-quality TEST failing
# on the recent statcast batch reds the catchup while the daily job stays green. The
# retry just 3x's the runtime and delays surfacing it; the actual failing test is in
# the dbt run-summary tail (see _failure_detail + the _run_dbt ERROR-log of it).
_CATCHUP_RETRY = RetryPolicy(max_retries=2, delay=60)  # delay in seconds


def _failure_detail(result) -> str:
    """Diagnostic tail for a failed subprocess. dbt-fusion writes everything to
    STDOUT and leaves stderr EMPTY, so a bare `{stderr}` lost the real error to
    Dagster's 50k log truncation (incident 2026-06-11). Prefer stderr, else fall
    back to the stdout tail (which carries dbt's end-of-run failure summary)."""
    err = (result.stderr or "").strip()
    if err:
        return err[-4000:]
    out_tail = (result.stdout or "")[-4000:]
    return f"(stderr empty — stdout tail)\n{out_tail}"


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
        raise Exception(f"{os.path.basename(script)} failed (exit {result.returncode})\n{_failure_detail(result)}")


def _run_dbt(context: OpExecutionContext, args: list[str]) -> None:
    cmd = ["dbtf"] + args + ["--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR]
    context.log.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=APP_DIR)
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        # Log the dbt failure tail as its OWN short ERROR event. The full stdout
        # above is truncated to its 50k HEAD by Dagster (dbt's end-of-run failure
        # summary lives in the tail), and under _CATCHUP_RETRY the raised exception
        # is swallowed as RetryRequestedFromPolicy — so without this the failing
        # model/test is invisible in the cloud logs (incident 2026-06-11/12).
        detail = _failure_detail(result)
        context.log.error(f"dbtf {args[0]} failed (exit {result.returncode}) — failure tail:\n{detail}")
        raise Exception(f"dbtf {args[0]} failed (exit {result.returncode})\n{detail}")


# ── Statcast catch-up job ops (statcast_freshness_sensor) ─────────────────────
# Lightweight "land yesterday's pitch data, then make today's slate whole" chain,
# fired by statcast_freshness_sensor when Statcast publishes later than the 07:00
# daily run. savant_ingestion is incremental (auto-resumes from last_loaded+1 to
# yesterday), so this needs no date args and is idempotent across retries.

@op(out=Out(Nothing), retry_policy=_CATCHUP_RETRY)
def catchup_ingest_statcast(context: OpExecutionContext) -> None:
    """Re-attempt Statcast pitch ingestion for the not-yet-loaded day(s)."""
    _run_script(context, "savant_ingestion.py", ["batter_pitches"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing), retry_policy=_CATCHUP_RETRY)
def catchup_dbt_rebuild(context: OpExecutionContext) -> None:
    """Rebuild the pitch-derived subtree so the newly-landed completed games flow
    into mart_game_results → mart_game_spine → rolling marts → feature store.
    Posteriors run next (they read mart_game_results), then dbt_umpire_feature_-
    rebuild folds them into the feature marts before the re-score."""
    _run_dbt(context, [
        "build",
        "--select", "stg_batter_pitches+",
        "--target", "baseball_betting_and_fantasy",
    ])


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
def lineup_ingest_umpires(context: OpExecutionContext) -> None:
    """Story 30.5 — ingest today's HP-umpire ASSIGNMENT here, on the afternoon
    lineup-confirm path, NOT just in the 07:00 daily job. Root cause of the
    assignment staleness: the daily early/late ops run ~08 ET, hours BEFORE MLB
    posts HP umpires, so they wrote 0–partial rows (nothing since 2026-06-04).
    The lineup monitor fires within ~5h of first pitch — when umps ARE posted —
    so this is when the assignment is actually available for the post_lineup
    re-score (the actionable bet). ingest_umpires.py is now idempotent
    (delete-then-insert scoped to statsapi + today's game_pks), so re-running on
    every sensor tick is safe. Soft-fail: never block the post-lineup re-score."""
    try:
        _run_script(context, "ingest_umpires.py", ["--date", _today()])
    except Exception as e:
        context.log.warning(f"Lineup-path umpire assignment ingest failed (non-fatal): {e}")


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
    """Rebuild the lineup + starter + downstream game features with the fresh
    confirmed-lineup posteriors, BEFORE lineup_predict reads the feature store —
    so the post-lineup prediction reflects who is actually playing. Models are
    table-materialized; the full rebuild re-reads eb_batter_posteriors_raw."""
    _run_dbt(context, [
        "build",
        "--select",
        # Story 30.5 — recompute the ump z-scores from the just-ingested HP
        # assignment (lineup_ingest_umpires) so feature_pregame_game_features
        # picks up today's umpire. dbt resolves order via refs.
        "stg_statsapi_umpire_game_log",
        "feature_pregame_umpire_features",
        # Story 30.6 LEVER 2 (2026-06-14) — rebuild starter_features on the
        # post-lineup path too, NOT just in the morning daily job. The prior
        # lineup_dbt_staging_rebuild step just refreshed stg_statsapi_probable_-
        # pitchers; without this the actionable post-lineup bet re-reads the
        # MORNING starter table and never sees a starter scratched/announced
        # after the morning build. feature_pregame_starter_features now sources
        # the fresh staging directly (fix A), so this makes the bet's starter
        # block consistent with the just-refreshed probable. Symmetric completion
        # of fix A; closes the scratch/late-probable serve-time gap.
        "feature_pregame_starter_features",
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
