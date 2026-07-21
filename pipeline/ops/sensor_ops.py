import os
import subprocess
import sys

from dagster import In, Nothing, OpExecutionContext, Out, RetryPolicy, op

from betting_ml.utils.game_day import current_game_date_iso  # INC-22 — canonical US baseball-day
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
# Story A2.15 (2026-06-15) — FIXED a recurring failure: the then-`catchup_dbt_rebuild` ran
# `dbtf build` (models + TESTS) on the stg_batter_pitches+ subtree, so a single data-quality
# TEST failing on the recent statcast batch redded the whole catchup (3× retry tripling the
# wasted compute) while the weekday daily job — which runs `dbtf run` — stayed green. It was
# switched to `dbtf run` (models only); the test suite runs once in the daily build op.
# E9.41b (2026-07-18) — that dbt step is now OBSOLETE: post-W11-E the pitch marts are S3
# views and stg_batter_pitches is enabled=false on the SF target, so the selector matched
# nothing (silent no-op). The op was repurposed to `catchup_refresh_ext_tables` (an external-
# table REFRESH), and `catchup_ingest_statcast` was fixed to actually run the S3 ingest — both
# had silently no-op'd since W11-E, leaving the whole catch-up self-heal dead.
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
    return current_game_date_iso()  # INC-22 — US baseball-day (LA), not the UTC box clock


def _intraday_s3_rebuild_on() -> bool:
    """Gate for lineup_intraday_s3_feature_rebuild (the 824819-loop fix). Default OFF
    until validated on the box (the runtime gate — CI mocks all S3/SF IO and cannot see
    the --w8b build). Flip LINEUP_INTRADAY_S3_REBUILD=1 in the box env_file after a real
    lineup_monitor_job run proves the chain green + a post_lineup row lands."""
    return os.environ.get("LINEUP_INTRADAY_S3_REBUILD") == "1"


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
    """Land yesterday's not-yet-loaded Statcast pitch data — the sensor's whole purpose.

    E11.1-W11-E / E9.41b — the LIVE pitch substrate is the S3 `stg_batter_pitches` parquet written
    by ingest_statcast_to_s3.py (pulls Baseball Savant, incremental → auto-resumes from last-loaded
    to yesterday, idempotent per-day delete+write). The Snowflake `savant.batter_pitches` write is
    RETIRED (W11_BATTER_PITCHES_SF_RETIRED=1) and the SF-target stg_batter_pitches model is
    enabled=false. So on the box this MUST run the S3 ingest: the pre-fix behaviour (skip the SF
    write and RETURN) landed NOTHING, so the freshness sensor — which polls the S3 parquet for
    yesterday's pitches — spun uselessly every 30 min until the next 08:00 daily
    ingest_statcast_to_s3_op, silently breaking the whole catch-up self-heal after W11-E. Mirrors
    the daily ingest_statcast_to_s3_op exactly (idempotent → safe across the sensor's retries).
    """
    if os.environ.get("W11_BATTER_PITCHES_SF_RETIRED") == "1":
        _run_script(context, "ingest_statcast_to_s3.py")
        return
    _run_script(context, "savant_ingestion.py", ["batter_pitches"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing), retry_policy=_CATCHUP_RETRY)
def catchup_refresh_ext_tables(context: OpExecutionContext) -> None:
    """Make the just-landed pitch data VISIBLE to the Snowflake-target reads (was catchup_dbt_rebuild).

    E11.1-W11-E / E9.41b — the pitch-derived marts (mart_game_results, mart_clv_labeled_games, the
    rolling marts, the feature precursors) are now VIEWS over the S3 stg_batter_pitches parquet, so
    they need no dbt rebuild. The old `dbtf run --select stg_batter_pitches+` was a silent NO-OP on
    the Snowflake target — stg_batter_pitches is enabled=false there (duckdb-target view only) →
    `NoNodesForSelectionCriteria` / "Nothing to do". What the SF-target reads DO need is the external
    tables REFRESHed to pick up the file the catch-up just wrote (AUTO_REFRESH=FALSE) — exactly the
    daily refresh_w1_external_tables_op after ingest_statcast_to_s3_op. A cheap ALTER … REFRESH of
    the REQUIRED tier (stg_batter_pitches + the W1 pitch marts); harmless when serving reads S3
    directly (--s3). The downstream posteriors + dbt_umpire_feature_rebuild then read the now-fresh
    mart_game_results before the re-score, and finalize_prior_slate_game_detail_op settles
    yesterday's game-detail Finals → the "who called it" scorecards same-day (E9.41b).
    """
    _run_script(context, "refresh_w1_external_tables.py")


@op(ins={"start": In(Nothing)}, out=Out(Nothing), retry_policy=_CATCHUP_RETRY)
def catchup_rebuild_outcome_mirrors(context: OpExecutionContext) -> None:
    """E9.41 — rebuild the settled-outcome S3 MIRROR parquets after a late game's Statcast lands.

    The serving reads (the featured "Yesterday" recap self-heal, finalize_prior_slate_game_detail_op,
    the /performance tally) read mart_game_results + mart_clv_labeled_games as S3 MIRROR parquets
    written by the daily --w5-group-a / --clv-labels-only build. catchup_ingest_statcast refreshes
    only the stg_batter_pitches parquet, so WITHOUT this the late game's outcome never reaches those
    mirrors until the next 08:00 daily run (2026-07-19 SF/SEA: mart_game_results was a day behind and
    mart_clv_labeled_games two — the recap stayed 'pending'). Rebuild mart_game_results (--w5-group-a)
    off the fresh pitches, then the CLV-label marts (--clv-labels-only) off the fresh
    mart_game_results, then refresh the CLV ext tables. Runs before the posteriors (which read
    mart_game_results) so they too reflect the completed games. Idempotent (parquet COPYs)."""
    _run_script(context, "run_w1_lakehouse.py", ["--w5-only", "--w5-group-a-only"])
    _run_script(context, "run_w1_lakehouse.py", ["--clv-labels-only"])
    _run_script(context, "refresh_w1_external_tables.py", ["--w6-clv"])


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
def lineup_intraday_s3_feature_rebuild(context: OpExecutionContext) -> None:
    """Regenerate the S3 W8b feature parquet for the confirmed-lineup re-score.

    THE GAP THIS CLOSES (2026-06-30, game 824819 restart loop): post-W8b-cutover the
    served feature_pregame_lineup_features / matchups / aggregator are a COPY of a
    DAILY-FROZEN S3 parquet — the dbt prod (else) branch is `select * from
    lakehouse_ext.<model>`. The NEXT op (lineup_dbt_feature_rebuild) only RE-COPIES that
    external table; it does NOT regenerate the S3 parquet (that is the daily
    run_w1_lakehouse_op, which is absent from this job). So a lineup/starter confirmation
    that posts AFTER the morning --w8b build never reaches the post_lineup re-score → the
    game's away/home side is missing/stale in the aggregator → predict writes no
    post_lineup row → lineup_monitor re-triggers it every tick FOREVER (the 824819 loop).

    This op rebuilds the S3 chain BEFORE the feature copy, mirroring the daily order:
      1. backfill_lineup_state_scd2  — MERGE the just-rebuilt staging into the SCD-2
         feature_pregame_lineup_state (the daily update_lineup_state_scd2 op runs only at
         07:00; an intraday confirmation never reaches the SCD-2 without this).
      2. export_w8b_precursors_to_s3 --table feature_pregame_lineup_state — mirror the
         fresh SCD-2 state to S3 (the only precursor that changes intraday; the rest stay
         from the morning build, which --w8b-only reuses).
      3. run_w1_lakehouse --w8b-only — rebuild the feature/matchup/aggregator parquet from
         the fresh mirror.
      4. refresh_w1_external_tables --w8b — point lakehouse_ext at the new parquet, so the
         downstream lineup_dbt_feature_rebuild copies FRESH rows.

    GATING: default-OFF (LINEUP_INTRADAY_S3_REBUILD) for the box validation window. When
    off this is a logged no-op and the job behaves exactly as before (no regression).
    TIER: MIRROR / ALERT-loud-but-continue — a rebuild failure is logged LOUD but does NOT
    raise, so the post_lineup re-score still runs on the last-good S3 features (degraded >
    no prediction at all), the next sensor tick retries, and the 30.13 serve-time freshness
    gate backstops genuine staleness. A failure here must never block the WHOLE slate's
    re-score just because one game's intraday rebuild broke.

    ⚠️ COST: this runs the full --w8b-only build (all-history, ~minutes) on every firing.
    Acceptable as the correctness fix; the fast-follow is scoping --w8b to today's games."""
    if not _intraday_s3_rebuild_on():
        context.log.warning(
            "lineup_intraday_s3_feature_rebuild SKIPPED (LINEUP_INTRADAY_S3_REBUILD != 1) — "
            "the post-lineup re-score reads the daily-frozen S3 features; an intraday lineup/"
            "starter confirmation posted after the morning --w8b build will NOT be reflected "
            "(the 824819 stale-side class). Flip the flag on the box once validated."
        )
        return
    # Dependent chain — on the FIRST failure, log LOUD + return (never raise: predict must
    # still run on the last-good S3 features rather than the whole slate getting no re-score).
    steps: list[tuple[str, list[str]]] = [
        ("backfill_lineup_state_scd2.py", ["--since", _today()]),
        ("export_w8b_precursors_to_s3.py", ["--table", "feature_pregame_lineup_state"]),
        ("run_w1_lakehouse.py", ["--w8b-only"]),
        ("refresh_w1_external_tables.py", ["--w8b"]),
    ]
    failed_step = None
    try:
        for script, args in steps:
            failed_step = script  # remember which script we were on if _run_script raises
            _run_script(context, script, args)
        failed_step = None
        context.log.info("Intraday S3 W8b feature parquet regenerated — ext tables refreshed.")
    except Exception as e:  # ALERT-loud-but-continue (mirror tier)
        # INC-32 (2026-07-18): the mirror-tier except only did context.log.warning, which nobody
        # watches — so a failure here degrades post_lineup coverage SILENTLY. (The 7/17 0.833 <
        # 0.85 INC-17 miss was root-caused to the sensor-daemon stop + the dbt-runner wedge, NOT
        # this op — the 4 rebuild scripts verified HEALTHY on the box, incl. region-robust DuckDB
        # S3 reads. But a transient S3/SF/OOM here would still hide unseen.) A mirror-tier op must
        # be ALERT-LOUD per E11.7 — so PAGE (SNS email) AND record WHICH step failed, so the next
        # failure is diagnosable on a live slate instead of dying in op logs. Still NON-RAISING
        # (predict must run on the last-good S3 features; the next sensor tick retries).
        msg = (
            f"lineup_intraday_s3_feature_rebuild FAILED at step {failed_step!r} ({e}) — CONTINUING "
            f"so the post-lineup re-score still runs on the last-good S3 features. A PERSISTENT "
            f"failure means intraday lineup changes are NOT reaching the serve → post_lineup "
            f"coverage degrades below the 0.85 INC-17 gate. Investigate {failed_step!r} on the box."
        )
        context.log.warning("[ALERT] " + msg)
        try:
            from pipeline.utils.alerting import send_alert
            send_alert(
                "Intraday lineup S3 rebuild failing",
                msg,
                severity="CRITICAL",
                dedup_key="lineup_intraday_s3_rebuild",
            )
        except Exception as alert_exc:  # noqa: BLE001 — alerting must never break the mirror tier
            context.log.warning(f"send_alert failed (non-fatal): {alert_exc}")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lineup_dbt_feature_rebuild(context: OpExecutionContext) -> None:
    """Rebuild the lineup + starter + downstream game features with the fresh
    confirmed-lineup posteriors, BEFORE lineup_predict reads the feature store —
    so the post-lineup prediction reflects who is actually playing. Models are
    table-materialized; the full rebuild re-reads eb_batter_posteriors_raw.

    NB (2026-06-30): post-W8b these models' prod branch is `select * from lakehouse_ext.*`,
    so this op COPIES the S3 ext table — it does not regenerate the S3 parquet. The
    preceding lineup_intraday_s3_feature_rebuild op regenerates that parquet so this copy
    picks up an intraday lineup change (else the post_lineup re-score is daily-frozen)."""
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
    # E9.9: --notify here too — if the morning slate had 0 qualified plays but a
    # confirmed lineup re-score produces some, users still get alerted. Idempotent
    # per slate (DynamoDB conditional put) so morning + post-lineup fire at most once.
    args = ["--prediction-type", "post_lineup", "--lineup-confirmed", "--notify"]
    if game_pks:
        args += ["--game-pks", game_pks]
    # E11.20 phase-2a (W7b-2): read features/marts from S3 instead of the Snowflake staging views
    # when the flip is on. The S3 features are kept intraday-fresh by lineup_intraday_s3_feature_
    # rebuild (s2b) upstream in this job; predict still WRITES daily_model_predictions to Snowflake
    # (--s3 is reads-only) + mirrors to S3, so serving reads consistent picks either way. Shares the
    # daily-ops gate helper (default-OFF W7B_INTRADAY_S3 + W6_LAKEHOUSE_INTRADAY). Instant rollback =
    # unset the flag. See docs/w7b2_intraday_serving_s3_flip_design.md.
    from pipeline.ops.daily_ingestion_ops import _w7b_intraday_s3_args
    args += _w7b_intraday_s3_args()
    _run_script(context, "predict_today.py", args)

    # E11.20 phase-2a (2026-07-20) — MIRROR the just-written post_lineup rows to S3.
    # predict_today_morning has always done this; lineup_predict did NOT, so the S3
    # daily_model_predictions parquet carried ZERO post_lineup rows for the current slate
    # until the next morning's daily run re-exported it. Found by
    # scripts/parity_check_lineup_monitor.py: SF had 9 post_lineup games, S3 had 0.
    #
    # Why it matters (the flip blocker): under LINEUP_MONITOR_S3=1 the monitor's Step-2b
    # "does this game already have a post_lineup row?" check reads that parquet. A stale
    # ZERO makes every already-triggered game look like a failed run, so the monitor
    # re-triggers it on EVERY tick — the infinite re-trigger loop INC-32 just fixed
    # (game 823523, ~4h of re-fires). The parity gate caught it before the flag flipped.
    #
    # Serving is NOT affected either way: write_serving_store_intraday_op deliberately
    # reads Snowflake (no --s3) in W7b-1, which is why post_lineup picks reach users today.
    # This export also freshens the API's direct-S3 LAST-RESORT read of intraday picks,
    # which until now could only ever see the morning rows.
    # ALERT-loud-but-continue: a mirror failure must never fail the re-score that already
    # succeeded — but it must be visible, because a silent miss re-arms the loop above.
    try:
        _run_script(context, "export_w6_raw_to_s3.py", ["--table", "daily_model_predictions"])
    except Exception as exc:  # noqa: BLE001 — mirror tier
        context.log.warning(
            f"⚠️ post_lineup S3 mirror FAILED — the S3 daily_model_predictions parquet is "
            f"now STALE for this slate. Serving is unaffected (intraday serve reads "
            f"Snowflake), but do NOT run with LINEUP_MONITOR_S3=1 until this is healthy: "
            f"the monitor's Step-2b would re-trigger every game every tick. Error: {exc}"
        )


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


