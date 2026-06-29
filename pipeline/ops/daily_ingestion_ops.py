import os
import subprocess
import sys
from datetime import date, timedelta

from dagster import HookContext, In, MetadataValue, Nothing, Out, failure_hook, op

from pipeline.ops._dbt_exec import _run_dbt

SCRIPTS_DIR = "/app/scripts"
APP_DIR = "/app"
DBT_DIR = "/app/dbt"


def _run_script(context, script: str, args: list[str] | None = None) -> str:
    """Run a Python script and return its stdout. Raises on non-zero exit."""
    path = script if os.path.isabs(script) else f"{SCRIPTS_DIR}/{script}"
    cmd = [sys.executable, path] + (args or [])
    # E11.3 — propagate job name so script-level Snowflake sessions get QUERY_TAG set.
    env = {**os.environ, "DAGSTER_JOB_NAME": context.job_name}
    context.log.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=APP_DIR)
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        raise Exception(f"{os.path.basename(script)} failed (exit {result.returncode})\n{result.stderr}")
    return result.stdout or ""


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


def _w7a_s3_args() -> list[str]:
    # E11.1-W7a: when W7A_LAKEHOUSE_S3=1, the matchup-signal consumers + the archetype
    # posterior builder READ the cluster / posterior / pitch substrate from the S3 lakehouse
    # (DuckDB) instead of native Snowflake — so the operator can DROP the native
    # cluster_batters/cluster_pitchers/compute_archetype_posteriors Snowflake builds (the W7a
    # credit drop). The SCD-2 / posterior WRITES stay on Snowflake. Default OFF so merging the
    # code is a no-op until the operator creates the W7 external tables, seeds the S3 parquet,
    # and validates parity (mirrors the W6_LAKEHOUSE_INTRADAY cutover gate).
    return ["--s3"] if os.environ.get("W7A_LAKEHOUSE_S3") == "1" else []


def _w7b_serving_on() -> bool:
    # E11.1-W7b: the cutover switch. When 1, the DAILY prediction/serving READ path
    # (predict_today_morning + write_serving_store_op) reads the S3 lakehouse via DuckDB
    # instead of Snowflake. Default OFF so merging is a no-op until the operator validates the
    # multi-day parallel run (scripts/parity_check_w7b.py) and flips it (mirrors W7A_LAKEHOUSE_S3
    # / W6_LAKEHOUSE_INTRADAY). Snowflake stays the instant rollback (set back to 0).
    return os.environ.get("W7B_LAKEHOUSE_S3") == "1"


def _w7b_mirror_on() -> bool:
    # The feature + predictions S3 export-mirrors (export_features_to_s3 / export_w6
    # daily_model_predictions) run when serving is ON (the --s3 readers need fresh S3) OR during
    # the parallel run (W7B_LAKEHOUSE_PARALLEL=1) so parity_check_w7b has fresh S3 data to compare
    # against Snowflake BEFORE the serving flip. Either flag populates S3; only W7B_LAKEHOUSE_S3
    # flips the actual serving reads. (W7b-1 export-mirror keeps the dbt feature BUILD on
    # Snowflake; W7b-2 converts the build to DuckDB and retires the mirror.)
    return _w7b_serving_on() or os.environ.get("W7B_LAKEHOUSE_PARALLEL") == "1"


def _w7b_s3_args() -> list[str]:
    # E11.1-W7b: append --s3 to predict_today.py / write_serving_store.py ONLY on cutover.
    return ["--s3"] if _w7b_serving_on() else []


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
    #
    # E11.1-W1d: mart_pitch_* are now views over S3 external tables (tag:w1_lakehouse).
    # They are excluded from every Snowflake dbt build — the views are static and the
    # external tables are refreshed by refresh_w1_external_tables_op before this step.
    today = date.today()
    target = ["--target", "baseball_betting_and_fantasy"]
    exclude = ["--exclude", "tag:w1_lakehouse"]
    if today.weekday() == 6:  # Sunday: weekly full rebuild + full test suite
        return ["build", "--full-refresh"] + target + exclude
    # Story A2.15 (2026-06-15): the dbt TEST suite was the single biggest Snowflake +
    # Dagster cost driver — tests ran on every intraday/catchup tick via the scattered
    # `build` ops (now all converted to `run`). This op is the ONE place the test suite
    # runs: the Sunday full-refresh build above, plus a lightweight (no --full-refresh)
    # test build every 3rd day as a midweek data-quality checkpoint. Every other day →
    # models-only `run`. Dial the cadence with the modulus (% 2 = every other day; drop
    # this block = Sunday-only/weekly). The whole-project build here covers the tests for
    # every model the daily/intraday `run` ops rebuild.
    if today.toordinal() % 3 == 0:
        return ["build"] + target + exclude
    return ["run"] + target + exclude


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
    # WARN-tier (INC-16 / E11.7 gap): FanGraphs is behind a Cloudflare JS challenge
    # served through flaresolverr (IP-bound cf_clearance). A flaresolverr/FanGraphs
    # outage must degrade quietly — Stuff+ enrichment is a nullable LEFT JOIN with a
    # Statcast fallback, so predictions still run — instead of raising into the daily
    # job. Catch → log.warning → op succeeds.
    try:
        _run_script(context, "ingest_fangraphs_stuff_plus.py", [
            "--season", str(date.today().year),
            "--window-types", "14d,30d,season",
        ])
    except Exception as e:
        context.log.warning(
            f"FanGraphs Stuff+ ingest failed (non-fatal; predictions fall back to "
            f"Statcast — lose Stuff+ enrichment only): {e}"
        )


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_fangraphs_catcher_framing(context):
    if not _is_sunday():
        context.log.info("Not Sunday — skipping catcher framing")
        return
    _run_script(context, "ingest_catcher_framing.py", ["--season", str(date.today().year)])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_fangraphs_hitting_leaderboard(context):
    # WARN-tier (INC-16 / E11.7 gap): same Cloudflare/flaresolverr dependency as
    # Stuff+. FanGraphs hitting-leaderboard features are nullable LEFT JOINs →
    # an outage degrades quietly rather than failing the daily ingestion job.
    try:
        _run_script(context, "ingest_fangraphs_hitting_leaderboard.py", [
            "--season", str(date.today().year),
            "--window-types", "season",
        ])
    except Exception as e:
        context.log.warning(
            f"FanGraphs hitting-leaderboard ingest failed (non-fatal; predictions "
            f"run without the FanGraphs hitting enrichment): {e}"
        )


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
    # Story A2.16-D3 (2026-06-15) — soft-fail (mirrors ingest_weather / settle_user_-
    # bets). OAA is a Baseball Savant scrape that occasionally 5xx/timeouts; it was the
    # one remaining non-critical external-API ingest still HARD-failing the whole daily
    # job (e.g. 2x on 2026-06-02 → no predictions those runs + manual re-runs). OAA is
    # a season-CUMULATIVE defense metric that moves slowly and imputes if stale, so a
    # missed daily refresh just reuses yesterday's value — never worth blocking predict.
    try:
        _run_script(context, "ingest_oaa.py", ["--season", str(date.today().year)])
    except Exception as e:
        context.log.warning(f"OAA ingest failed (non-fatal, predictions use prior OAA): {e}")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_statcast_to_s3_op(context):
    # E11.1-W1d HALT: mart_pitch_* are now served from S3 external tables; this
    # ingest is on the critical path. Failure stops the daily job before the
    # feature build reads stale pitch data.
    _run_script(context, "ingest_statcast_to_s3.py")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def run_w1_lakehouse_op(context):
    # E11.1-W1d HALT: rebuilds all 7 mart_pitch_* S3 Parquets. Now on the
    # critical path — the Snowflake external tables (and the downstream feature
    # build) depend on this write completing successfully.
    # E11.1-W2: run_w1_lakehouse.py ALSO builds the 8 W2 pitch-derived marts
    # (registering the W1 marts as views first). Kept in THIS op (not a separate
    # Railway cron) — the E11.0b "use a cron" guidance existed to avoid Dagster+
    # serverless run-minute billing, which E11.15 eliminated by self-hosting
    # Dagster (cost = held RAM, not run-minutes). Ordered before dbt_daily_build
    # so the W2 external tables are fresh for the morning feature build.
    # E11.1-W3: the no-arg call ALSO builds the 11 W3 pitch-derived marts
    # (handedness/archetype/tto splits + the bullpen/reliever marts) right after W2 — same
    # default-on rationale (their whole upstream closure is already in S3). They feed
    # feature_pregame_* + write_serving_store, so they ride this HALT-tier op too.
    # E11.1-W3pre: run_w1_lakehouse.py can ALSO build the odds/staging flatten tier
    # (stg_oddsapi_*, stg_derivative_odds, stg_statsapi_games) but ONLY under the opt-in
    # --w3pre flag (NOT passed here yet). Wiring it in is a deliberate follow-up: it needs
    # the lakehouse_raw/ tier populated first (scripts/export_odds_raw_to_s3.py + flipped
    # writers) and the serving-coupled cutover validated — otherwise an empty raw tier
    # would fail this HALT-tier op. Until then this no-arg call builds only W1 + W2.
    # E11.1-W4: run_w1_lakehouse.py can ALSO build the FanGraphs/posteriors-cluster/raw-savant
    # marts (6) + their FanGraphs precursor subtree under the opt-in --w4 flag (NOT passed
    # here yet). Like W3pre, it needs the precursor parquet first (scripts/export_w4_raw_to_s3.py
    # + the migrated DuckDB builders fit_granular_park_priors.py --s3 / cluster_pitchers.py
    # --seed,--s3) and the cutover validated — else an empty precursor tier would fail this
    # HALT-tier op. Flip to "--w4" once validated. (W4 read-path audit: none request-time read.)
    #
    # E11.1-W5: run_w1_lakehouse.py can ALSO build the mart_game_results/mart_game_spine
    # team/game chain (Group A, 10 marts) + the 4 W4-deferred marts + stg_batter_sprint_speed
    # (Group B) under the opt-in --w5 flag (NOT passed here yet). Like W3pre/W4, it needs the
    # precursor parquet first (scripts/export_w5_raw_to_s3.py: the seeds + eb_park_factors_raw +
    # eb_bullpen_team_posteriors + oaa_team_season_raw + sprint_speed_raw) and the W3pre
    # stg_statsapi_games parquet, plus cutover validated — else an empty precursor tier would
    # fail this HALT-tier op. Flip to "--w5" once validated. (W5 careful tier: only the
    # game-detail Snowflake FALLBACK reads mart_team_pythagorean_rolling, behind the DynamoDB
    # serving cache — no other request-time read; post-cutover it serves the S3-backed view.)
    #
    # E11.1-W6: run_w1_lakehouse.py ALSO builds the 13 odds/CLV + odds-serving marts + the 2
    # Group-C staging flattens under --w6 (flipped ON at the W6 cutover, after the lakehouse_ext
    # W6 external tables were created + parity validated). Precursors:
    #   • monthly_schedule re-export (the line BELOW, BEFORE the --w6 build): the 3 Group-C lineup
    #     marts (stg_statsapi_lineups → mart_player_game_starts / mart_team_schedule_context)
    #     flatten it, and ingest_statsapi.py is Snowflake-only (W3pre never S3-flipped its writer),
    #     so a stale snapshot drops today's lineups → matchup features NULL for live serving (the
    #     INC-17 P2 class). Parity at backfill showed DuckDB ~1.4% < Snowflake purely from this lag.
    #   • daily_model_predictions is NOT re-exported here — this op runs BEFORE predict_today, so
    #     the CLV marts (mart_prediction_clv / mart_clv_labeled_games) are refreshed POST-predict
    #     by the gated intraday odds_clv_dbt_rebuild path (export dmp → --w6 → refresh --w6-clv).
    # ⭐ mart_odds_outcomes is date-bucketed (_history/_current); this daily --w6 rewrites BOTH
    # buckets, while the intraday odds_current_rebuild path (pipeline/ops/intraday_ops.py, gated
    # W6_LAKEHOUSE_INTRADAY) rewrites ONLY _current each odds cycle so served prices stay fresh.
    _run_script(context, "export_odds_raw_to_s3.py", ["--source", "monthly_schedule"])
    # E11.1-W7b: when the S3 mirror is on, ALSO build the prediction/serving mini-wave parquet
    # (mart_player_profile_identity injury chain + the probable_pitchers/lineups_wide serving-mart
    # backlog) so the --s3 readers + the request-path last-resort resolve them. Requires the
    # player_transactions precursor export (run by the operator/cutover wiring) to exist first.
    if _w7b_mirror_on():
        _run_script(context, "export_w7b_precursors_to_s3.py")
        _run_script(context, "run_w1_lakehouse.py", ["--w6", "--w7b"])
    else:
        _run_script(context, "run_w1_lakehouse.py", ["--w6"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def refresh_w1_external_tables_op(context):
    # E11.1-W1d HALT: refresh Snowflake external table metadata so the feature
    # build sees the parquets just written by run_w1_lakehouse_op.
    # AUTO_REFRESH=FALSE on the external tables requires an explicit REFRESH call
    # after each S3 write. Failure here would serve stale pitch features.
    # E11.1-W2: refresh_w1_external_tables.py now also REFRESHes the 8 W2 external
    # tables (W2_TABLES) — same HALT rationale (W2 marts feed the feature build).
    # E11.1-W3: it ALSO refreshes the 11 W3 external tables (W3_TABLES), also HALT —
    # the W3 marts feed feature_pregame_* + write_serving_store.
    # E11.1-W3pre: it ALSO refreshes the W3pre stg external tables (W3PRE_TABLES) — a
    # no-op until those external tables are created (generate_w3pre_external_tables.py),
    # at which point the daily refresh keeps the odds/staging flatten fresh for serving.
    # E11.1-W4: it ALSO refreshes the W4 external tables (W4_TABLES, best-effort/WARN until
    # the generator runs) — the FanGraphs/posteriors/savant marts + precursor subtree.
    # Promote W4_TABLES to the `required` set once --w4 is default-on above.
    _run_script(context, "refresh_w1_external_tables.py")


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
    args = _dbt_daily_build_args()
    if args[0] != "build":
        # run days: source_status-aware incremental rebuild, no test gate.
        _run_dbt(context, args, use_state=True)
        return
    # build days (Sunday --full-refresh + every-3rd midweek): split models from tests
    # so a peripheral data-quality failure never blocks predictions. INC-6 (2026-06-21):
    # a bad StatsAPI bio row exit-1'd the Sunday build and blocked all predictions.
    # Step 1 — model rebuild (gates pipeline; preserves --full-refresh on Sunday).
    run_args = ["run"] + args[1:]
    _run_dbt(context, run_args, use_state=False)
    # Step 2 — test suite (non-blocking: warns, never fails the op).
    target_args = []
    if "--target" in args:
        idx = args.index("--target")
        target_args = args[idx : idx + 2]
    try:
        _run_dbt(context, ["test"] + target_args, use_state=False)
    except Exception as exc:
        context.log.warning(
            f"[dbt test] non-blocking suite had failures — predictions are NOT blocked:\n{exc}"
        )


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
                    ["--date", d, "--env", env] + _w7a_s3_args())


@op(ins={"start": In(Nothing)}, out=Out(Nothing), tags=_SUB_MODEL_OP_TAGS)
def generate_env_state_signals_op(context):
    # Epic 27.2. Runs the Story 27.1 Kalman filter over all historical data
    # (loads all of mart_game_results since 2021 to build the filter state
    # trajectory) then emits four env_state_v1 signals per (game_pk, side) for
    # the recently-completed game window.  The filter computation is fast
    # (<30s); the full historical load is required to avoid leakage — the
    # pregame state for date T is derived from all games with game_date < T.
    env = _target_env()
    for d in _recent_completed_dates():
        _run_script(context, "/app/betting_ml/scripts/generate_env_state_signals.py",
                    ["--date", d, "--env", env])


@op(ins={"start": In(Nothing)}, out=Out(Nothing), tags=_SUB_MODEL_OP_TAGS)
def generate_defense_quality_signals_op(context):
    # Story 27.4. Reads mart_team_defense_quality_rolling (dbt-built, prior-season
    # OAA + EB-smoothed sprint speed) and emits three defense_quality_v1 signals
    # per (game_pk, side) for the recently-completed game window.  The mart is
    # leakage-safe by construction (game_year-1 OAA and sprint speed only), so
    # no historical rebuild is required — just score the completed window.
    # Shared signal for Epic 27 (totals) and Epic 28 (H2H) per R33.
    env = _target_env()
    for d in _recent_completed_dates():
        _run_script(context, "/app/betting_ml/scripts/generate_defense_quality_signals.py",
                    ["--date", d, "--env", env])


@op(
    ins={
        "run_env_done":       In(Nothing),
        "offense_done":       In(Nothing),
        "starter_done":       In(Nothing),
        "starter_ip_done":    In(Nothing),
        "bullpen_done":       In(Nothing),
        "matchup_done":       In(Nothing),
        "env_state_done":     In(Nothing),
        "defense_quality_done": In(Nothing),
    },
    out=Out(Nothing),
)
def dbt_sub_model_signals_rebuild(context):
    # Fan-in: refresh the wide PIVOT once all eight signal tables are written.
    _run_dbt(context, [
        "run",
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
# membership). Story A2.11: this is now a dbt model, refreshed by
# dbt_build_bullpen_posteriors_op below, which MUST run before
# update_team_posteriors_op (bullpen branch reads it) and before the
# dbt_umpire_feature_rebuild that rebuilds feature_pregame_game_features. The models
# are incremental (merge on grain), so a daily build is idempotent/re-runnable.

_SEQ_DIR = "/app/betting_ml/scripts/sequential_bayes"
_EB_DIR = "/app/betting_ml/scripts/eb_priors"


# Story A2.11 — the EB bullpen posteriors are now dbt models (replaced
# compute_bullpen_posteriors.py). Built HERE, before update_team_posteriors_op,
# whose bullpen_xwoba branch reads eb_bullpen_posteriors. Incremental models, so a
# daily build only recomputes the current window. int_bullpen_ali_by_season is the
# aLI-leverage support model (recomputes current+prior season).
@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def dbt_build_bullpen_posteriors_op(context):
    _run_dbt(context, [
        "run", "--select",
        "int_bullpen_ali_by_season",
        "eb_bullpen_posteriors",
        "eb_bullpen_team_posteriors",
        "--target", "baseball_betting_and_fantasy",
    ])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def update_player_posteriors_op(context):
    _run_script(context, f"{_SEQ_DIR}/update_player_posteriors.py", ["--date", _one_day_ago()])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def update_team_posteriors_op(context):
    _run_script(context, f"{_SEQ_DIR}/update_team_posteriors.py", ["--date", _one_day_ago()])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def update_matchup_cell_posteriors_op(context):
    _run_script(context, f"{_SEQ_DIR}/update_matchup_cell_posteriors.py",
                ["--date", _one_day_ago()] + _w7a_s3_args())


# INC-2 (2026-06-22): compute_archetype_posteriors.py had NO scheduled caller and
# silently stopped on 2026-05-31 — mart_player_archetype_posteriors served 3-week-
# stale batter/pitcher cluster assignments (the archetype-matchup contract block, a
# heavy home_win component) for all of June. Wired here in statcast_catchup_job after
# the sequential posteriors so it refreshes daily once the completed-game data lands,
# BEFORE the feature rebuild reads mart_player_archetype_posteriors. `--mode today`
# is the daily incremental (writes the current as_of_date); target table is hard-
# pinned to prod baseball_data.betting, so no TARGET_ENV needed.
@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def update_archetype_posteriors_op(context):
    # E11.7 failure tier: ALERT-loud-but-continue. Archetype posteriors are a peripheral
    # model-input refresh (the archetype-matchup block degrades gracefully — the pipeline
    # ran for weeks on stale posteriors with no serving outage), so a failure here must NOT
    # HALT the serving-critical daily job (predictions / dbt rebuilds run downstream).
    # Log a loud WARNING and succeed; the source-scoped freshness monitor (E11.8) pages if
    # the table goes stale. INC (2026-06-23): the op HALTed the whole daily job when the
    # centroids/scaler pkls were missing from the image — now loaded from S3 + non-blocking.
    try:
        _run_script(context, f"{_EB_DIR}/compute_archetype_posteriors.py",
                    ["--mode", "today"] + _w7a_s3_args())
    except Exception as exc:  # noqa: BLE001 — peripheral; never block the serving pipeline.
        context.log.warning(
            "WARNING: update_archetype_posteriors_op failed; continuing without a fresh "
            "archetype refresh (mart_player_archetype_posteriors may be stale — the freshness "
            f"monitor will alert if so). Error: {exc}"
        )


# Story A2.11 — the forward-looking TODAY's-slate EB posteriors (starter + lineup)
# are now dbt models: eb_starter_posteriors (sourced from the full probable-pitcher
# spine → covers +1/+2-day games, closing the Story 30.6 residual) and
# eb_batter_posteriors_raw. They are built inside dbt_umpire_feature_rebuild below
# (incremental, so daily/lineup-tick builds only recompute the recent window), which
# runs AFTER the sequential update ops so the as-of sequential column is fresh.
# The old compute_{starter,lineup}_posteriors_op Python ops were removed here.


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
def ingest_umpire_scorecards(context):
    # Story 30.5 — recurring UmpScorecards TENDENCY load (the missing daily feed).
    # ingest_umpires.py above stamps only today's HP-umpire NAME; this pulls the
    # per-game tendency metrics (run impact / accuracy / favor) the trailing-3yr
    # z-scores in feature_pregame_umpire_features are computed from, so they stay
    # current as the season progresses. Trailing 7-day window (script default)
    # catches scorecards posted a day or two after the game. Runs BEFORE
    # dbt_umpire_feature_rebuild so the fresh rows feed the feature rebuild.
    # Soft-fail: tendency history is not on the critical path (predict-side
    # imputation handles a still-null ump feature) and must never block predict.
    try:
        _run_script(context, "ingest_umpire_scorecards.py")
    except Exception as e:
        context.log.warning(f"UmpScorecards tendency ingest failed (non-fatal): {e}")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def dbt_umpire_feature_rebuild(context):
    # mart_bullpen_effectiveness + feature_pregame_team_features are rebuilt HERE
    # (after dbt_build_bullpen_posteriors_op writes yesterday's EB posteriors at
    # s17) — not just at dbt_daily_build (s16, which runs before that source exists).
    # The mart's 7-day lookback merge-updates yesterday's row from NULL eb to the
    # freshly-written value; the two table-materialized features then pass it through
    # to feature_pregame_game_features.{home,away}_bp_eb_xwoba. dbt resolves build
    # order from the ref graph. See reference_bullpen_freshness_chain.
    #
    # Story A2.11 — build the forward-looking TODAY's-slate EB posteriors here too
    # (eb_starter_posteriors + eb_batter_posteriors_raw, now dbt models), so they
    # land in feature_pregame_{starter,lineup,game}_features. They ref()
    # player_sequential_posteriors (as-of), so this op runs AFTER the sequential
    # update ops. Incremental → only the recent window is recomputed. dbt resolves
    # build order from the ref graph.
    _run_dbt(context, [
        "run",
        "--select",
        "stg_statsapi_umpire_game_log",
        "feature_pregame_umpire_features",
        "mart_bullpen_effectiveness",
        "feature_pregame_team_features",
        "eb_starter_posteriors",
        "eb_batter_posteriors_raw",
        "feature_pregame_starter_features",
        "feature_pregame_lineup_features",
        # Story 30.6 (2026-06-15) — feature_pregame_game_features is a PASSTHROUGH of
        # feature_pregame_game_features_raw (a table, not ephemeral): _raw does the
        # actual home/away starter+lineup+umpire+team JOINs, game_features just adds
        # the seasonnorm columns. Rebuilding the upstream feature tables WITHOUT _raw
        # left game_features passing through a stale _raw, so fresh starter/lineup
        # values never reached the serve until the next FULL `dbtf build`. Include
        # _raw here so the targeted daily rebuild actually propagates. dbt orders via refs.
        "feature_pregame_game_features_raw",
        "feature_pregame_game_features",
        "--target", "baseball_betting_and_fantasy",
    ])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def predict_today_morning(context):
    # E11.1-W7b: when the S3 mirror is on (parallel run or cutover), refresh the feature
    # export-mirror BEFORE scoring so predict_today --s3 reads today's freshly-built features
    # from S3 (the dbt feature BUILD stays on Snowflake in W7b-1; the mirror copies its OUTPUT
    # → S3 parquet). >1 min full export — the W7b-1 export-mirror cost; W7b-2's DuckDB feature
    # build removes it. HALT tier: a mirror failure must stop the cycle (a stale/partial S3
    # matrix = wrong served picks), which _run_script enforces by raising on non-zero exit.
    if _w7b_mirror_on():
        _run_script(context, "export_features_to_s3.py")
    _run_script(context, "predict_today.py", ["--prediction-type", "morning"] + _w7b_s3_args())
    # Re-export predictions Snowflake→S3 AFTER scoring (predict_today still WRITES to Snowflake
    # in W7b-1) so the downstream write_serving_store_op --s3 + the request-path last-resort serve
    # TODAY's picks from S3 (the W6 daily_model_predictions freshness contract).
    if _w7b_mirror_on():
        _run_script(context, "export_w6_raw_to_s3.py", ["--table", "daily_model_predictions"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def generate_pick_narratives_op(context):
    # E9.13 — generate plain-English pick narrative text via Snowflake Cortex after
    # SHAP pick_explanation is written by predict_today. Runs for today's date only;
    # the script skips rows where pick_narrative is already populated (idempotent).
    # Soft-fail: a Cortex outage must not block write_serving_store_op — the app
    # renders SHAP drivers from pick_explanation when pick_narrative is NULL.
    try:
        _run_script(context, "/app/betting_ml/scripts/generate_pick_narratives.py",
                    ["--date", _today(), "--pick-delta-guard"])
    except Exception as e:
        context.log.warning(f"Narrative generation failed (non-fatal, picks shown without text): {e}")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def update_pipeline_status(context):
    """Upsert today's pipeline run summary into pipeline_status after predict_today_morning."""
    _run_script(context, "update_pipeline_status.py")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def check_prediction_coverage(context):
    _run_script(context, "check_prediction_coverage.py")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def dbt_mart_prediction_clv(context):
    _run_dbt(context, ["run", "--select", "mart_prediction_clv", "--target", "baseball_betting_and_fantasy"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def compute_model_health(context):
    _run_script(context, "compute_model_health.py")


# ── Story 28.3 — Magnitude H2H kill-criterion monitor ────────────────────────

@op(out=Out(Nothing))
def monitor_magnitude_h2h_op(context):
    """Weekly read-only monitor for the magnitude H2H kill criterion (Story 28.3).

    Logs real-book ROI, Brier scores, tripwire state, and accrual progress to
    Dagster so the CONFIRM/KILL gate is auditable without manual script runs.
    """
    _run_script(context, "ops/monitor_magnitude_h2h.py", ["--schema", "betting_ml"])


@op(out=Out(Nothing))
def monitor_conviction_h2h_op(context):
    """Weekly read-only monitor for the conviction-gate H2H kill criterion (Story 28.6b).

    Same discipline as the magnitude monitor: logs real-book ROI, Brier, tripwire,
    and accrual for the 28.2 disagreement-gate selective strategy. SHADOW/manual —
    no automated bets fire off this; it only makes the CONFIRM/KILL gate auditable.
    """
    _run_script(context, "ops/monitor_conviction_h2h.py", ["--schema", "betting_ml"])


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
        "run",
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
        "run",
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
    """Queries Snowflake and writes picks/today + performance/summary to S3."""
    _run_script(context, "write_api_cache.py")


@op(
    ins={"predict_done": In(Nothing)},
    out=Out(Nothing),
    description="Writes prediction outputs to Railway PostgreSQL serving store "
                "after predictions complete. Primary read path for all FastAPI endpoints.",
)
def write_serving_store_op(context):
    """Queries Snowflake (or the S3 lakehouse via DuckDB when W7B_LAKEHOUSE_S3=1) and writes
    picks/today, picks/ev, game detail, and performance/summary to the Railway PG api_cache +
    daily_picks tables. Also writes to S3 during the transition period."""
    # E11.1-W7b: --s3 reads the serving store from the S3 lakehouse on cutover. predict_today_morning
    # has already refreshed the feature mirror + re-exported today's daily_model_predictions → S3,
    # so today's picks are fresh. No-op until W7B_LAKEHOUSE_S3=1 (instant rollback by unsetting it).
    _run_script(context, "write_serving_store.py", _w7b_s3_args())


@op(
    ins={"predict_done": In(Nothing)},
    out=Out(Nothing),
    description="Intraday-scoped serving store write: picks, game-detail, and book-odds only. "
                "Used by sensor jobs (lineup_monitor, statcast_catchup) where teams/players/"
                "history/performance don't change — daily_ingestion_job owns the full run_all.",
)
def write_serving_store_intraday_op(context):
    """Volatile sections only: --picks --game-detail --book-odds.

    E11.10 (2026-06-23): lineup_monitor fires ~every 10 min intraday. Running
    run_all (--teams --players --history --performance) on each fire was ~8 min of
    wasted wall-clock — those sections are static within a day and owned by the
    once-daily daily_ingestion_job. This variant cuts each intraday fire to the
    three sections that actually change when a lineup or odds update posts.

    E11.1-W7b: this INTRADAY path stays on Snowflake in W7b-1 (no --s3). The export-mirror is
    daily-cadence (a full-history feature re-export every ~10-min intraday fire is too costly),
    and today's lineup-driven feature freshness needs the W6-style _current-bucket split or the
    W7b-2 DuckDB feature build → so the daily morning path goes S3 first; the intraday/post-lineup
    serving path is the documented W7b remaining tail. (The request-path last-resort that serves
    these intraday picks IS direct-S3 — it reads the daily-mirrored parquet + the W6 intraday odds.)
    """
    _run_script(context, "write_serving_store.py", ["--picks", "--game-detail", "--book-odds"])


# ── User bet settlement (Performance page redesign, story B1) ─────────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def settle_user_bets_op(context):
    """Settle pending DynamoDB user-bets against final scores.

    Bets live in DynamoDB (OLTP); scores live in Snowflake (OLAP). Runs after
    dbt_daily_build, where last night's finals (stg_statsapi_games) are fresh.
    Off the critical prediction path — failure here must not block predictions.
    Soft-fail (mirrors ingest_umpire_scorecards): this is a leaf op
    (settle_user_bets_op(start=s16) — nothing downstream depends on it), so a
    settlement error (missing script, transient DynamoDB/Snowflake hiccup) must
    not flip daily_ingestion_job to FAILURE and fire the Run Failure alert. The
    warning is logged for monitoring; unsettled bets are retried next daily run.
    """
    try:
        _run_script(context, "settle_user_bets.py")
    except Exception as e:
        context.log.warning(f"User-bet settlement failed (non-fatal, retried next run): {e}")


# ── Backfill phase ───────────────────────────────────────────────────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def backfill_prediction_log(context):
    _run_script(context, "backfill_prediction_log.py")


# ── E9.31b — Zone-overlay daily generation ───────────────────────────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def build_zone_matchup_overlay_op(context):
    """Generate today's batter × starter zone-overlay JSONs and write to S3.

    WARN-tier (E11.7 / e13_10_app_handoff_spec §3): peripheral/app-cosmetic.
    A failure here must never block predictions or the serving writes. The
    backend reads S3 directly for these files; they are NOT on the predict path.

    Reads: stg_statsapi_lineups + stg_statsapi_probable_pitchers (Snowflake, IDs only).
    Heavy compute: S3 lakehouse DuckDB (never Snowflake per E13.10 cost-aware rule).
    Writes: s3://baseball-betting-ml-artifacts/baseball/serving/zone_matchup/overlay/as_of=<date>/
    """
    try:
        _run_script(context, "generate_zone_overlays_today.py")
    except Exception as exc:  # noqa: BLE001
        context.log.warning(
            "WARNING: build_zone_matchup_overlay_op failed (non-fatal — zone heatmaps may be "
            f"absent for today's picks, predictions and serving are unaffected): {exc}"
        )
