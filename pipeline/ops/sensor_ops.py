import os
import subprocess
import sys
from datetime import date

from dagster import In, Nothing, OpExecutionContext, Out, RetryPolicy, op

from pipeline.ops._dbt_exec import _failure_detail, _run_dbt

SCRIPTS_DIR = "/app/scripts"
APP_DIR = "/app"
DBT_DIR = "/app/dbt"
_EB_DIR = "/app/betting_ml/scripts/eb_priors"

# Epic A1 (Pipeline SLA & Reliability): the sensor-fired catch-up ops are idempotent
# re-attempts (incremental ingestion + MERGE-keyed dbt rebuilds), so a transient
# Snowflake hiccup (warehouse resume, incremental-MERGE lock, network blip) should
# self-heal rather than page.
#
# Story A2.15 (2026-06-15) — FIXED the recurring failure this comment used to
# describe: catchup_dbt_rebuild had failed EVERY run since 2026-06-11 (all 3 retries
# exhausted) because it ran `dbtf build` (models + TESTS) on the stg_batter_pitches+
# subtree, so a single data-quality TEST failing on the recent statcast batch redded
# the whole catchup (and the 3× retry tripled the wasted Snowflake + Dagster compute)
# while the weekday daily job — which runs `dbtf run` — stayed green. catchup_dbt_-
# rebuild now also runs `dbtf run` (models only); the test suite runs once in the
# daily job's build op (see _dbt_daily_build_args). If a real data-quality issue
# needs surfacing, the daily build is the gate, not every catch-up tick.
_CATCHUP_RETRY = RetryPolicy(max_retries=2, delay=60)  # delay in seconds

# Incident 2026-06-15 — a `lineup_dbt_clv_rebuild` `dbtf run` subprocess WEDGED
# (no active Snowflake query; the dbt-fusion CLI process simply stopped exiting).
# Both subprocess helpers ran with NO timeout, so the op — and the whole
# lineup_monitor_job run — hung indefinitely (in_process_executor), while the
# 10-min sensor stacked fresh runs on top. A hard subprocess ceiling converts an
# infinite hang into a fast, visible op failure (retryable / surfaced in the cloud
# logs). Intraday lineup dbt rebuilds are incremental (minutes); the catch-up
# rebuild over stg_batter_pitches+ is the longest healthy run, so 30 min is a
# generous ceiling that still bounds the hang far below the 4h run_monitoring cap.
_SUBPROCESS_TIMEOUT = 1800  # seconds (30 min) — hard ceiling per subprocess op


def _today() -> str:
    return date.today().strftime("%Y-%m-%d")


def _run(cmd: list[str], timeout: int = _SUBPROCESS_TIMEOUT):
    """subprocess.run with a hard timeout. On timeout the child is killed and a
    clear Exception is raised so the op FAILS FAST (retryable / visible) instead of
    hanging the run forever (incident 2026-06-15)."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, cwd=APP_DIR, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        tail = (e.stdout or "")[-2000:] if isinstance(e.stdout, str) else ""
        raise Exception(
            f"subprocess exceeded {timeout}s hard timeout and was killed: "
            f"{' '.join(cmd[:3])}…\n(stdout tail)\n{tail}"
        ) from e


def _run_script(context: OpExecutionContext, script: str, args: list[str] | None = None,
                timeout: int = _SUBPROCESS_TIMEOUT) -> None:
    path = script if os.path.isabs(script) else f"{SCRIPTS_DIR}/{script}"
    cmd = [sys.executable, path] + (args or [])
    context.log.info(f"Running: {' '.join(cmd)}")
    result = _run(cmd, timeout=timeout)
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        raise Exception(f"{os.path.basename(script)} failed (exit {result.returncode})\n{_failure_detail(result)}")


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
        "run",
        "--select", "stg_batter_pitches+",
        "--target", "baseball_betting_and_fantasy",
    ])


# ── Lineup Monitor job ops ────────────────────────────────────────────────────

@op(out=Out(Nothing))
def lineup_ingest_schedule(context: OpExecutionContext) -> None:
    """Re-ingest schedule to pick up retroactive lineup confirmations.

    E11.4 (2026-06-19) — NOT USED in lineup_monitor_job. The Railway
    schedule_capture cron (services/schedule_capture/) handles statsapi schedule
    ingestion every 30 min off Dagster's bill. Retained here for manual/emergency
    use from the Dagster UI."""
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


@op(out=Out(Nothing))
def lineup_ingest_umpires(context: OpExecutionContext) -> None:
    """Story 30.5 — ingest today's HP-umpire ASSIGNMENT here, on the afternoon
    lineup-confirm path, NOT just in the 07:00 daily job. Root cause of the
    assignment staleness: the daily early/late ops run ~08 ET, hours BEFORE MLB
    posts HP umpires, so they wrote 0–partial rows (nothing since 2026-06-04).
    The lineup monitor fires within ~5h of first pitch — when umps ARE posted —
    so this is when the assignment is actually available for the post_lineup
    re-score (the actionable bet). ingest_umpires.py is now idempotent
    (delete-then-insert scoped to statsapi + today's game_pks), so re-running on
    every sensor tick is safe. Soft-fail: never block the post-lineup re-score.

    E11.4 (2026-06-19) — removed `start` input: umpire ingest is now the first op
    in lineup_monitor_job (lineup_ingest_schedule was removed; schedule_capture cron
    handles statsapi ingestion off Dagster's bill)."""
    try:
        _run_script(context, "ingest_umpires.py", ["--date", _today(), "--skip-if-exists"])
    except Exception as e:
        context.log.warning(f"Lineup-path umpire assignment ingest failed (non-fatal): {e}")


# Story A2.11 — the EB lineup/starter posteriors are now dbt models built inside
# lineup_dbt_feature_rebuild (the eb_* models are incremental and merge-keyed on the
# natural grain, so a confirmed-lineup re-score is idempotent). The standalone
# lineup_compute_posteriors Python op was removed.


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lineup_dbt_feature_rebuild(context: OpExecutionContext) -> None:
    """Rebuild the lineup + starter + downstream game features with the fresh
    confirmed-lineup posteriors, BEFORE lineup_predict reads the feature store —
    so the post-lineup prediction reflects who is actually playing. Models are
    table-materialized; the full rebuild re-reads eb_batter_posteriors_raw."""
    _run_dbt(context, [
        "run",
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
        # Story A2.11 — build the EB starter/lineup posteriors (now dbt models)
        # here too, before the features that ref() them, so the confirmed-lineup
        # re-score reflects the actual batters/probable. Incremental → only the
        # confirmed games are recomputed.
        "eb_starter_posteriors",
        "eb_batter_posteriors_raw",
        "feature_pregame_starter_features",
        "feature_pregame_lineup_features",
        # Story 30.6 (2026-06-15) — feature_pregame_game_features is a PASSTHROUGH of
        # feature_pregame_game_features_raw (a table): _raw does the actual home/away
        # starter+lineup JOINs. Without _raw here, the post-lineup re-score rebuilt
        # game_features from a STALE _raw, so the freshly-rebuilt confirmed-lineup +
        # starter blocks NEVER reached the actionable bet — a prime suspect for the
        # 30.6 "post_lineup serve still coinflip" symptom. Include _raw so the bet
        # rides the confirmed-lineup matrix. dbt orders via refs.
        "feature_pregame_game_features_raw",
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
def lineup_dbt_clv_rebuild(context: OpExecutionContext) -> None:
    """Recompute the CLV marts against the just-written post-lineup predictions.

    E11.9 (2026-06-22) — was `+stg_statsapi_lineups+ mart_closing_line_value
    mart_prediction_clv`. The `+stg_statsapi_lineups+` selector rebuilt the ENTIRE
    lineup→feature-store subtree (feature_pregame_lineup_features →
    feature_pregame_game_features_raw → feature_pregame_game_features + every other
    descendant) a SECOND time on every lineup trigger — immediately after
    lineup_dbt_feature_rebuild already built it one op earlier. Neither CLV mart
    consumes those models: mart_closing_line_value refs stg_statsapi_games / odds
    marts / mart_game_odds_bridge, and mart_prediction_clv refs
    daily_model_predictions + mart_closing_line_value. So the feature re-build was
    pure waste — a top contributor to the 6/22 audit's feature_pregame full-CTAS
    count. Select ONLY the two CLV marts; their upstreams are kept fresh by the odds
    path + daily build."""
    _run_dbt(context, [
        "run",
        "--select",
        "mart_closing_line_value",
        "mart_prediction_clv",
        "--target", "baseball_betting_and_fantasy",
    ])


