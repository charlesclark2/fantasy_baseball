import os
import subprocess
import sys
import threading
from datetime import date, timedelta

from dagster import HookContext, In, MetadataValue, Nothing, Out, failure_hook, op

from betting_ml.utils.game_day import current_game_date, current_game_date_iso  # INC-22 — canonical US baseball-day
from pipeline.ops._dbt_exec import _run_dbt

SCRIPTS_DIR = "/app/scripts"
APP_DIR = "/app"
DBT_DIR = "/app/dbt"


def _run_script(context, script: str, args: list[str] | None = None,
                *, timeout: int | None = None) -> str:
    """Run a Python script, STREAMING its stdout/stderr to the Dagster log line-by-line,
    and return its stdout. Raises on non-zero exit, or (when `timeout` wall-clock seconds is
    given) kills the process and raises if it overruns.

    Why streaming, not capture_output: the previous `subprocess.run(capture_output=True)`
    buffered ALL output until the child EXITED, so a long build like `run_w1_lakehouse.py
    --w6` was a silent black box for its whole run — you couldn't tell a slow mart from a
    hung S3 read. Popen + `-u`/PYTHONUNBUFFERED flush each `print()` live, and per-pipe drain
    threads preserve the exact old contract (return = stdout only; stderr → log.warning; the
    exception carries stderr). `timeout` gives a hard wall-clock ceiling so a stalled httpfs
    read (http_timeout×http_retries can otherwise park ~tens of minutes) fails LOUD instead of
    hanging the HALT-tier op indefinitely."""
    path = script if os.path.isabs(script) else f"{SCRIPTS_DIR}/{script}"
    # -u: unbuffered child stdio so prints stream promptly (block-buffered otherwise off a tty).
    cmd = [sys.executable, "-u", path] + (args or [])
    # E11.3 — propagate job name so script-level Snowflake sessions get QUERY_TAG set.
    env = {**os.environ, "DAGSTER_JOB_NAME": context.job_name, "PYTHONUNBUFFERED": "1"}
    context.log.info(f"Running: {' '.join(cmd)}"
                     + (f"  (wall-clock cap {timeout}s)" if timeout else ""))
    proc = subprocess.Popen(
        cmd, env=env, cwd=APP_DIR, text=True, bufsize=1,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    out_lines: list[str] = []
    err_lines: list[str] = []

    def _drain(pipe, sink, logfn):
        for line in pipe:
            line = line.rstrip("\n")
            sink.append(line)
            logfn(line)

    t_out = threading.Thread(target=_drain, args=(proc.stdout, out_lines, context.log.info), daemon=True)
    t_err = threading.Thread(target=_drain, args=(proc.stderr, err_lines, context.log.warning), daemon=True)
    t_out.start()
    t_err.start()

    killed = {"flag": False}

    def _kill():
        killed["flag"] = True
        proc.kill()

    timer = threading.Timer(timeout, _kill) if timeout else None
    if timer:
        timer.start()
    try:
        proc.wait()
    finally:
        if timer:
            timer.cancel()
    t_out.join(timeout=5)
    t_err.join(timeout=5)

    stdout = "\n".join(out_lines)
    stderr = "\n".join(err_lines)
    if killed["flag"]:
        raise Exception(
            f"{os.path.basename(script)} exceeded its {timeout}s wall-clock cap and was KILLED "
            f"(likely a stalled S3/httpfs read — see http_timeout/http_retries in run_w1_lakehouse.py). "
            f"Last stdout:\n" + "\n".join(out_lines[-40:])
        )
    if proc.returncode != 0:
        raise Exception(f"{os.path.basename(script)} failed (exit {proc.returncode})\n{stderr}")
    return stdout


# INC-22 — anchor "today" and every day-relative window to the canonical US baseball-day
# (LA), so the daily ingest windows can't roll to the UTC-tomorrow if a run/catch-up
# crosses 00:00 UTC. (The genuine calendar uses below — weekday() for the Sunday weekly
# gate, .year for the season — stay on date.today(); they are not the serving slate.)
def _today() -> str:
    return current_game_date_iso()


def _seven_days_ago() -> str:
    return (current_game_date() - timedelta(days=7)).strftime("%Y-%m-%d")


def _two_days_ago() -> str:
    return (current_game_date() - timedelta(days=2)).strftime("%Y-%m-%d")


def _one_day_ago() -> str:
    return (current_game_date() - timedelta(days=1)).strftime("%Y-%m-%d")


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


def _w9_s3_read_args() -> list[str]:
    # E11.1-W9-tail: when W9_LAKEHOUSE_S3_READS=1, the 7 sub-model signal generators READ their
    # feature/mart sources (mart_game_results, the feature_pregame_* layer, the bullpen marts,
    # mart_team_defense_quality_rolling, starter_ip_signals) from the S3 lakehouse (DuckDB)
    # instead of native Snowflake — finishing the W9 source-repoint now that the feature layer
    # is in S3 (W8b). The SCD-2 / MERGE WRITES stay on Snowflake (the W9 export-mirror copies
    # those OUTPUTS to S3; a DuckDB accumulate rewrite is the W7a-wipe class W9 forbids).
    # DISTINCT from W9_LAKEHOUSE_S3 (the output-mirror flag, already live): the read repoint
    # gets its OWN default-OFF gate so the operator validates it with a real box run (the
    # matchup-4-latent-bugs lesson — parity validates reads, not accumulate) before flipping it.
    return ["--s3"] if os.environ.get("W9_LAKEHOUSE_S3_READS") == "1" else []


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


def _w7b_intraday_serving_on() -> bool:
    # E11.20 phase-2a W7b-2: the INTRADAY predict + serving path (lineup_monitor_job's
    # lineup_predict + write_serving_store_intraday_op) reads S3 instead of the Snowflake staging
    # VIEWS — the last game-hours SF-view readers (per the monthly_schedule_s3_flip_design consumer
    # audit), so this unblocks deleting the capture tick's ext-refresh + dbt-staging legs (step 3).
    #
    # SEPARATE default-OFF gate from W7B_LAKEHOUSE_S3 (which is enforced-ON for the morning/daily
    # path): flipping the serving-critical post_lineup path deserves its own soak, and merging must
    # be a runtime no-op. Instant rollback = unset W7B_INTRADAY_S3.
    #
    # COUPLED to W6_LAKEHOUSE_INTRADAY: the serving write includes --book-odds, whose --s3 read of
    # mart_odds_outcomes is only intraday-FRESH when the W6 intraday rebuild is on. Without it the
    # blob would serve stale morning odds AND clobber write_book_odds_op's fresh SF write (the
    # 2026-07-03 line-movement-freeze class — write_book_odds_op guards its own --s3 the same way).
    # Also depends on LINEUP_INTRADAY_S3_REBUILD=1 (s2b, enforced) keeping the S3 features fresh.
    return os.environ.get("W7B_INTRADAY_S3") == "1" and os.environ.get("W6_LAKEHOUSE_INTRADAY") == "1"


def _w7b_intraday_s3_args() -> list[str]:
    """`--s3` for the intraday predict + serving callers, gated by W7b-2 (see _w7b_intraday_serving_on)."""
    return ["--s3"] if _w7b_intraday_serving_on() else []


def _w8a_serving_on() -> bool:
    # E11.1-W8a: the cutover switch. When 1, the Snowflake dbt build's else branches read the
    # W8a lakehouse_ext external tables (the upstream feature layer + EB posteriors compute on
    # DuckDB→S3), so the W8a DuckDB build is on the critical path → HALT. Default OFF so merging
    # the dual-branch models is a no-op until the operator creates the W8a external tables, builds
    # the parquet, validates parity (scripts/parity_check_w8a.py), DROP+rebuilds the 5 EB
    # incrementals, and flips this (mirrors W7B_LAKEHOUSE_S3). Snowflake-native is the rollback.
    return os.environ.get("W8A_LAKEHOUSE_S3") == "1"


def _w8a_mirror_on() -> bool:
    # The W8a precursor export + DuckDB build run when cutover is ON (the else branches read the
    # external tables) OR during the parallel run (W8A_LAKEHOUSE_PARALLEL=1) so parity_check_w8a
    # has fresh S3 data to compare against the live native tables BEFORE the flip.
    return _w8a_serving_on() or os.environ.get("W8A_LAKEHOUSE_PARALLEL") == "1"


def _run_w8a_mirror(context, script: str, args: list[str] | None = None) -> str:
    """Run a W8a precursor export / DuckDB build at the correct failure tier (mirror of
    _run_mirror, gated on the W8a flags). HALT once W8A_LAKEHOUSE_S3=1 (the feature build reads
    the W8a external tables → stale/partial = wrong features); ALERT-loud-but-continue during the
    parallel window (W8A_LAKEHOUSE_PARALLEL=1, parity-only — the dbt else branches aren't merged/
    flipped yet, so a build failure must NOT take down the W6-critical run_w1_lakehouse_op).

    Returns the script's stdout (empty string when a parallel-window failure was swallowed) so a
    caller can page on a `[METRIC] …` line the script already emits (INC-37)."""
    if _w8a_serving_on():
        return _run_script(context, script, args)  # HALT — the feature build reads this
    try:
        return _run_script(context, script, args)
    except Exception as e:  # noqa: BLE001 — parity-only during the parallel window
        context.log.warning(
            f"[W8a parallel] mirror '{os.path.basename(script)}' failed (non-fatal; the dbt "
            f"build still computes these models natively, parity_check_w8a will show the gap): {e}"
        )
        return ""


def _w8b_serving_on() -> bool:
    # E11.1-W8b: the serving-aggregator cutover switch. When 1, the Snowflake dbt build's else
    # branches read the W8b lakehouse_ext external tables (the complex upstream + matchup models +
    # the aggregator feature_pregame_game_features_raw + its wrapper compute on DuckDB→S3), so the
    # W8b DuckDB build is on the critical path → HALT. Default OFF so merging the dual-branch models
    # is a no-op until the operator creates the W8b external tables, builds the parquet, validates
    # parity (scripts/parity_check_w8b.py) + a per-ROW ext-table fetch + predict_today matchup
    # non-null, DROP+rebuilds the 2 aggregator incrementals, and flips this. Snowflake-native is
    # rollback. ⚠️ requires W8A_LAKEHOUSE_S3=1 first (the aggregator reads the W8a feature layer).
    return os.environ.get("W8B_LAKEHOUSE_S3") == "1"


def _w8b_mirror_on() -> bool:
    # The W8b precursor export + DuckDB build run when cutover is ON (the else branches read the
    # external tables) OR during the parallel run (W8B_LAKEHOUSE_PARALLEL=1) so parity_check_w8b has
    # fresh S3 data to compare against the live native tables BEFORE the flip.
    return _w8b_serving_on() or os.environ.get("W8B_LAKEHOUSE_PARALLEL") == "1"


def _run_w8b_mirror(context, script: str, args: list[str] | None = None) -> None:
    """Run a W8b precursor export / DuckDB build at the correct failure tier (mirror of
    _run_w8a_mirror, gated on the W8b flags). HALT once W8B_LAKEHOUSE_S3=1 (the serving feature
    build reads the W8b external tables → stale/partial = wrong served features); ALERT-loud-but-
    continue during the parallel window (W8B_LAKEHOUSE_PARALLEL=1, parity-only — the dbt else
    branches aren't merged/flipped yet, so a build failure must NOT take down run_w1_lakehouse_op)."""
    if _w8b_serving_on():
        _run_script(context, script, args)  # HALT — the serving feature build reads this
        return
    try:
        _run_script(context, script, args)
    except Exception as e:  # noqa: BLE001 — parity-only during the parallel window
        context.log.warning(
            f"[W8b parallel] mirror '{os.path.basename(script)}' failed (non-fatal; the dbt "
            f"build still computes these models natively, parity_check_w8b will show the gap): {e}"
        )


def _w11_w4w5_nightly_on() -> bool:
    # E11.1-W11 (ingestion FINISH wave): the Tier-A raw writers now dual-write S3 and the 8 consumer
    # duckdb branches were repointed lakehouse_loc → lakehouse_raw_loc (the SF-sourced W4/W5 snapshot →
    # the live-writer raw mirror). But run_w1_lakehouse.py --w4/--w5 (the parquet REBUILD) is NOT in the
    # daily op — only the ext-table REFRESH is (refresh_w1_external_tables_op's default set includes
    # W4_TABLES+W5_TABLES). So without this the W4/W5 lakehouse/ parquet would freeze at the last manual
    # rebuild and the repointed reads would go stale. This gate wires a nightly --w4-only/--w5-only
    # rebuild; the existing refresh op then re-reads the fresh parquet. Default OFF: flip to 1 only after
    # (1) W11_RAW_WRITE_MODE=both on the daily job (so the live writers keep the raw mirror fresh),
    # (2) a box-validated --w4-only/--w5-only run (RUNTIME GATE), and (3) the W4/W5 lakehouse_ext tables
    # exist. Merging default-OFF is a true no-op (the un-gated glue is just this env read).
    return os.environ.get("W11_W4W5_NIGHTLY") == "1"


def _run_w11_nightly(context, script: str, args: list[str] | None = None) -> None:
    """E11.1-W11 nightly W4/W5 parquet rebuild at mirror-tier (ALERT-loud-but-continue). The W4/W5 marts
    have NO request-time read (per the run_w1_lakehouse_op W4/W5 notes) — they feed the dbt feature build,
    which retains its Snowflake-native path — so a rebuild failure must NOT take down the W6-critical
    run_w1_lakehouse_op. Log a WARNING (visible in Dagster) and continue; the next day's run retries."""
    try:
        _run_script(context, script, args)
    except Exception as e:  # noqa: BLE001 — non-serving W11 rebuild; must not HALT the daily job
        context.log.warning(
            f"[W11 nightly] rebuild '{os.path.basename(script)}' {' '.join(args or [])} failed "
            f"(non-fatal; the dbt feature build still computes these models natively): {e}"
        )


def _w11b_umpire_nightly_on() -> bool:
    # E11.1-W11 Tier-B: the 4 umpire writers now dual-write the umpire_game_log raw mirror and the
    # 4 umpire dbt models (2 stg + 2 feature) were dual-branched to read it. run_w1_lakehouse.py
    # --w11b (the parquet REBUILD) is NOT in the daily op by default — only the ext-table REFRESH is
    # once the W11b tables are added to a refresh path. This gate wires a nightly --w11b-only rebuild
    # + the --w11b ext-table refresh so lakehouse_ext.feature_pregame_umpire_* (read by the W8b
    # aggregator precursor view + the dbt else branch after cutover) stays fresh from the live raw
    # mirror. Default OFF: flip to 1 only after (1) W11_RAW_WRITE_MODE=both on the daily job (the live
    # writers keep the raw mirror fresh), (2) the W11b lakehouse_ext tables exist
    # (generate_w11b_external_tables.py), and (3) a box-validated --w11b-only run + per-ROW ext fetch
    # (the RUNTIME GATE). Merging default-OFF is a true no-op (the un-gated glue is just this env read).
    return os.environ.get("W11B_UMPIRE_NIGHTLY") == "1"


def _w11c_weather_nightly_on() -> bool:
    # E11.1-W11 Tier-C: the 2 weather writers (ingest_weather / backfill_observed_weather) now
    # dual-write the weather_raw raw mirror and the 4 weather dbt models (2 stg + 2 feature) were
    # dual-branched to read it. run_w1_lakehouse.py --w11c (the parquet REBUILD) is NOT in the daily op
    # by default. This gate wires a nightly --w11c-only rebuild + the --w11c ext-table refresh so
    # lakehouse_ext.feature_pregame_weather_* (read by the W8b aggregator precursor view + the game-
    # features chain + the dbt else branch after cutover) stays fresh from the live raw mirror. Self-
    # contained (only precursor is the raw parquet + the ref_venues seed CSV). Default OFF: flip to 1
    # only after (1) W11_RAW_WRITE_MODE=both on the daily job (the live writers keep the raw mirror
    # fresh), (2) the W11c lakehouse_ext tables exist (generate_w11c_external_tables.py), and (3) a
    # box-validated --w11c-only run + per-ROW ext fetch (the RUNTIME GATE). Merging default-OFF is a
    # true no-op (the un-gated glue is just this env read).
    return os.environ.get("W11C_WEATHER_NIGHTLY") == "1"


def _w11d_public_betting_nightly_on() -> bool:
    # E11.1-W11 Tier-D: ingest_actionnetwork_betting now dual-writes the public_betting_raw mirror and
    # the 4 public-betting dbt models (2 stg + 2 feature) were dual-branched to read it. run_w1_lakehouse
    # .py --w11d (the parquet REBUILD) is NOT in the daily op by default. This gate wires a nightly
    # --w11d-only rebuild + the --w11d ext-table refresh so lakehouse_ext.feature_pregame_public_betting_*
    # (read by the W8b aggregator precursor view + the dbt else branch after cutover) stays fresh from
    # the live raw mirror. Runs AFTER --w8b in the op (the snapshots stg joins feature_pregame_game_
    # features, built by --w8b). Default OFF: flip to 1 only after (1) W11_RAW_WRITE_MODE=both on the
    # daily job (the live writer keeps the raw mirror fresh), (2) the W11d lakehouse_ext tables exist
    # (generate_w11d_external_tables.py), and (3) a box-validated --w11d-only run + per-ROW ext fetch
    # (the RUNTIME GATE). Merging default-OFF is a true no-op (the un-gated glue is just this env read).
    return os.environ.get("W11D_PUBLIC_BETTING_NIGHTLY") == "1"


def _w11tx_transactions_nightly_on() -> bool:
    # E11.22: ingest_transactions dual-writes the player_transactions raw mirror and
    # stg_statsapi_transactions was repointed to read lakehouse_ext.stg_statsapi_transactions.
    # run_w1_lakehouse.py --w11tx (the parquet REBUILD) is NOT in the daily op by default. This gate
    # wires a nightly --w11tx-only rebuild + the --w11tx ext-table refresh so
    # lakehouse_ext.stg_statsapi_transactions (read by the daily dbt build's stg_statsapi_transactions →
    # injury-status chain after the read-cutover) stays fresh from the live raw mirror. Self-contained
    # (reads only the raw mirror). Default OFF: flip to 1 only after (1) W11_RAW_WRITE_MODE=both/s3 keeps
    # the raw mirror fresh, (2) the W11tx lakehouse_ext table exists (generate_w11tx_external_table.py),
    # and (3) a box-validated --w11tx-only run + per-ROW ext fetch (the RUNTIME GATE). Once ON + verified,
    # the SF raw player_transactions is droppable. Merging default-OFF is a true no-op (the un-gated glue
    # is just this env read).
    return os.environ.get("W11TX_TRANSACTIONS_NIGHTLY") == "1"


def _w3pre_daily_on() -> bool:
    # E11.1-W11 / INC-23 residual: wire the W3pre odds/staging flatten into the daily
    # run_w1_lakehouse_op so mart_derivative_closes stops topping out at ~Apr-1 (E13.14
    # leans on it). The daily op's --w6 call REGISTERS stg_derivative_odds as a view over
    # the existing parquet but never REBUILDS it; only --w3pre (_build_w3pre) rebuilds that
    # parquet from lakehouse_raw/derivative_odds_raw/. With this flag ON the daily op also
    # re-exports the derivative-odds raw tier (the recurring bridge) and passes --w3pre so
    # stg_derivative_odds is fresh before --w6 builds mart_derivative_closes. Mirrors the proven
    # intraday-schedule pattern (_schedule_lakehouse_intraday: export raw → --w3pre → refresh).
    # NOTE (E11.1-W11-E, 2026-07-03): the live derivative writer (derivative_odds_backfill.py
    # cmd_capture) can now ALSO dual-write S3 directly (gated by W11_RAW_WRITE_MODE). So this
    # bridge is OPTION A (keep it ON via this gate — proven, works from the full container) and
    # the writer flip is OPTION B (retire this bridge once the rebuilt derivative-capture image is
    # validated writing to lakehouse_raw/derivative_odds_raw/ on the box). Default OFF (W11
    # coordination discipline) so merging is a no-op until the operator runs the one-time
    # derivative_odds_raw gap-fill backfill + validates on the box, then flips it.
    return os.environ.get("W11_W3PRE_DAILY") == "1"


def _run_mirror(context, script: str, args: list[str] | None = None) -> None:
    """Run a W7b S3 export-mirror / mini-wave build at the CORRECT failure tier.

    The mirror feeds the `--s3` serving READERS. Once W7B_LAKEHOUSE_S3=1 a stale/partial S3
    mirror = wrong served picks → **HALT** (propagate the failure; same as _run_script).

    During the parallel window (W7B_LAKEHOUSE_PARALLEL=1 but serving still on Snowflake) the
    mirror is **parity-ONLY** — predictions/serving do not read it yet — so a mirror failure must
    NOT take down the serving-critical predict/build path. That's **ALERT-loud-but-continue** per
    the CLAUDE.md tier contract: log a WARNING (visible in Dagster), op succeeds, and that
    morning's parity_check_w7b simply shows the gap. (Wiring the mirror as HALT during the
    parallel run is what red-lined predict_today_morning on 2026-06-29.)
    """
    if _w7b_serving_on():
        _run_script(context, script, args)  # HALT — serving reads this mirror
        return
    try:
        _run_script(context, script, args)
    except Exception as e:  # noqa: BLE001 — parity-only during the parallel window
        context.log.warning(
            f"[W7b parallel] mirror '{os.path.basename(script)}' failed (non-fatal; serving "
            f"still reads Snowflake, parity_check will show the gap): {e}"
        )


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


def _batter_pitches_sf_retired() -> bool:
    """E11.1-W11-E: retire the REDUNDANT savant.batter_pitches Snowflake write.

    `savant_ingestion.py batter_pitches` (write_pandas DELETE+INSERT → savant.batter_pitches) is
    fully SHADOWED by ingest_statcast_to_s3_op, which writes the S3 stg_batter_pitches parquet that
    stg_batter_pitches' duckdb branch reads (the SF table is read only by the SF-target dbt build,
    never on the box/serving path). ingest_statcast_to_s3_op runs immediately AFTER this op in the
    daily job (s5b depends on s5) and is itself HALT-tier — so once parity is confirmed on the box,
    the SF write is pure cost. With W11_BATTER_PITCHES_SF_RETIRED=1 this op skips the SF ingestion
    (the S3 op feeds stg_batter_pitches). Default OFF → merging is a no-op until the operator verifies
    parity and opts in; then the operator can DROP savant.batter_pitches. ALERT-continue on skip."""
    return os.environ.get("W11_BATTER_PITCHES_SF_RETIRED") == "1"


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_statcast(context):
    if _batter_pitches_sf_retired():
        context.log.warning(
            "WARNING: [W11-E] savant.batter_pitches SF write RETIRED "
            "(W11_BATTER_PITCHES_SF_RETIRED=1) — ingest_statcast_to_s3_op feeds stg_batter_pitches. "
            "Skipping the redundant Snowflake ingestion."
        )
        return
    _run_script(context, "savant_ingestion.py", ["batter_pitches"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_statsapi_schedule(context):
    # Start the pull at YESTERDAY, not the default (first-of-current-month). run_schedule iterates
    # whole months, so on a normal day start=yesterday is in the current month → still ONE month
    # fetch (no extra cost); only on the 1st does it also re-pull the PREVIOUS month.
    #
    # WHY (found 2026-07-15): the default current-month-only pull strands the LAST day of a month.
    # Late West-coast games still 'In Progress' at the final same-month schedule capture were never
    # re-fetched once the calendar rolled — statsapi kept reporting them 'Live' in the lakehouse
    # forever (6/30's 4 frozen games). This also blinded finalize_prior_slate_game_detail_op on the
    # 1st: it reads stg_statsapi_games for yesterday, which the month-only pull hadn't refreshed.
    # Re-pulling from yesterday guarantees the prior day's finals land regardless of month boundary.
    #
    # INC-37 (2026-08-01) — TWO changes here, both load-bearing:
    #   1. This op now runs BEFORE the S3 lakehouse chain in daily_ingestion_job (it used to run
    #      AFTER lk1-lk10), so the W3pre flatten reads a schedule captured in the SAME run rather
    #      than whatever the last intraday capture happened to leave in S3. That is the INC-25
    #      rule applied to the schedule: a consumer cut over to an S3 mirror must be rebuilt
    #      DOWNSTREAM of the refresh that feeds it.
    #   2. --lookahead-days 3 makes the last few captures of every month ALSO fetch the NEXT
    #      month. Without it the final capture of a month contains ZERO games for the 1st, so a
    #      consumer that flattens before the new month's first capture builds a universe that
    #      stops at the month boundary (the INC-37 signature: the whole 08-01 morning tier fell
    #      to intraday_fallback; the same thing happened on 06-01 and 07-01).
    _run_script(context, "ingest_statsapi.py",
                ["schedule", "--start-date", _one_day_ago(), "--lookahead-days", "3"])


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


# ═════════════════════════════════════════════════════════════════════════════════════
# E11.20 ⭐ THE run_w1_lakehouse_op DECOMPOSITION (operator-requested 2026-07-06)
#
# run_w1_lakehouse_op had grown into a MONOLITH: one HALT-tier op running 8+ sequential
# subprocess stages (schedule export → W1+W2+W3+W6 build → W7b → spine/odds-bridge → W8a
# → W5b/W8b → the 6 gated W11 nightly tiers) behind a single 45-min wall cap — one Dagster
# duration for everything, one retry unit (a W8b failure re-ran the whole 20+-min pitch
# rebuild), and no per-wave timing to attribute the daily job's 40+ min.
#
# It is now DECOMPOSED into the per-wave ops below. Design rules:
#   • Each op preserves EXACTLY the tier + gate + subprocess command of its stage in the
#     old monolith (--w6 split into --w1-only/--w2-only/--w3-only/[--w3pre-only]/--w6-only,
#     which run() defines as value-identical partial paths reusing the prior wave's S3
#     output — the old combined process also re-read each wave's output from S3).
#   • The daily job graph (daily_ingestion_job.py) wires them in the old in-op order —
#     the ordering invariants (schedule export before W6 Group-C; spine before the odds
#     bridge; --w8a before --w5b before --w8b; W11d after W8b) are now GRAPH EDGES.
#   • A gated-off stage logs a WARNING (ALERT tier — a graceful skip must be loud, never
#     an invisible `if`), then succeeds.
#   • Per-op wall caps replace the shared 2700s cap: a stalled httpfs read fails loudly
#     inside its own wave, and each op's Dagster duration is the E11.21 timing table.
#   • E11.20 Delta: the W1 op is Delta-mode-aware via run_w1_lakehouse.py
#     (LAKEHOUSE_DELTA_W1 off|mirror|cutover — daily O(current-season) partition swap
#     under mirror/cutover; lakehouse_delta_maintenance_op compacts/vacuums after).
# ═════════════════════════════════════════════════════════════════════════════════════


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lakehouse_schedule_export_op(context):
    # ⛔ THE monthly_schedule EXPORT BRIDGE IS RETIRED (E11.20 phase-2b, 2026-07-27).
    #
    # This op used to run `export_odds_raw_to_s3.py --source monthly_schedule`. Its premise —
    # "ingest_statsapi.py is Snowflake-only, so a stale S3 snapshot drops today's lineups" —
    # STOPPED BEING TRUE on 2026-07-20, when the schedule capture flipped S3-native and the
    # native `statsapi.monthly_schedule` writer was retired (that table has been FROZEN at
    # ingestion_ts 2026-07-20T17:00:26 ever since). Phase-2a retired the INTRADAY copy of this
    # same bridge (guarded by test_cost_wake_gates.py) but MISSED this daily one.
    #
    # Left running, it did active DAMAGE, not just a stale read — the INC-31 clobber shape with
    # teeth. Invoked with no `--since`, the script runs `prune_partitions()`, which DELETES every
    # lakehouse_raw/monthly_schedule/dt= partition outside its own latest-per-month keep set —
    # computed from the FROZEN table. So each daily run wiped the partitions the S3-native capture
    # had written. Observed 2026-07-27: the raw tier held only dt=2026-05-31, dt=2026-06-30 and
    # dt=__nullts__ (schedule dates 2015-04-05..2026-05-31 — NO July data at all); the sole July
    # partition, dt=2026-07-27, existed only because the capture wrote it at 22:30Z, AFTER that
    # day's 12:02Z prune. Consequence: `stg_statsapi_probable_pitchers` flattened a ~7/20-era
    # schedule, so the daily --w8a build published an eb_starter_posteriors with a decaying tail
    # (7/23=5, 7/24=1, 7/25+=0 rows) for days — the E11.20 phase-2b W8b blocker.
    #
    # The S3-native capture is now the SOLE writer of this key, per the INC-31 rule ("the native
    # build must be the SOLE writer of that S3 key"). The op is KEPT (not deleted) so the daily
    # graph's ordering edges are unchanged, and logs loudly rather than skipping invisibly.
    #
    # ⚠️ FOLLOW-UP: the prune also carried the INC-20 retention duty (collapsing accumulating month
    # snapshots so the flatten does not OOM). The native capture writes ~450 KB/day (vs the bridge's
    # 31.8 MB blobs), so there is ample headroom, but retention now belongs WITH the native writer —
    # it must not come back as a bridge that reads a retired table.
    context.log.warning(
        "[E11.20 phase-2b] monthly_schedule export bridge RETIRED — the S3-native schedule capture "
        "is the sole writer of lakehouse_raw/monthly_schedule/. Re-adding the export here would "
        "re-run its destructive prune against a Snowflake table frozen since 2026-07-20."
    )


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lakehouse_w1_pitch_marts_op(context):
    # HALT — the 7 mart_pitch_* pitch-level marts (E11.1-W1d: served via external tables /
    # the feature build; on the critical path). E11.20: Delta-mode-aware —
    # LAKEHOUSE_DELTA_W1=off → legacy full-history parquet COPY; mirror → parquet +
    # Delta season-partition write (validation window); cutover → Delta (DuckDB readers
    # via delta_scan) + the SF-COMPAT season-bucket parquet mirror (keeps the ext tables
    # fresh for the raw-SQL SF stragglers — the INC-27 class), BOTH daily writes
    # O(current-season) (the measured-perf headline; the full-history rebuild is the
    # explicit opt-in `--delta-full` backfill, NOT the daily default).
    _run_script(context, "run_w1_lakehouse.py", ["--w1-only"], timeout=1800)


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lakehouse_w2_marts_op(context):
    # HALT — the 8 W2 pitch-derived batch marts (rolling stats / game logs; feed the
    # feature build). Reads the W1 output just written (parquet, or delta_scan under
    # cutover — run_w1_lakehouse._register_mart_views is Delta-aware).
    _run_script(context, "run_w1_lakehouse.py", ["--w2-only"], timeout=1800)


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lakehouse_w3_marts_op(context):
    # HALT — the 11 W3 handedness/archetype/tto splits + bullpen/reliever marts (feed
    # feature_pregame_* + write_serving_store).
    _run_script(context, "run_w1_lakehouse.py", ["--w3-only"], timeout=1800)


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lakehouse_w3pre_flatten_op(context):
    # Gated (W11_W3PRE_DAILY, INC-23): rebuild the W3pre odds/staging flatten so
    # stg_derivative_odds is fresh before the W6 build registers it. HALT when ON (same as the
    # old monolith, where --w3pre rode the HALT call; _build_w3pre defensively SKIPs any source
    # with no raw parquet). ALERT-loud skip when OFF.
    # E11.24 (2026-07-29): the Snowflake raw bridge this op used to run first is RETIRED — see the
    # block below. The flatten reads lakehouse_raw/derivative_odds_raw/ directly, which the
    # S3-native capture is the sole writer of, so nothing was lost with it.
    if not _w3pre_daily_on():
        context.log.warning(
            "[lakehouse-w3pre] W11_W3PRE_DAILY unset — skipping the W3pre flatten rebuild "
            "(stg_derivative_odds stays at its last build)."
        )
        return
    # ⛔ E11.24 (2026-07-29) — THE DERIVATIVE-ODDS BRIDGE IS RETIRED (the 4th instance of the
    # retired-writer-bridge class, after monthly_schedule and mlb_odds_raw). It ran
    # `export_odds_raw_to_s3.py --source derivative_odds_raw --since <7d ago>` on every daily
    # build, but derivative capture is S3-NATIVE (W11_RAW_WRITE_MODE=s3), so
    # `oddsapi.derivative_odds_raw` has been FROZEN at ingestion_ts 2026-07-07T00:00:07 —
    # measured 2026-07-29: 22 days stale, **0 rows in the 7-day window**. The export therefore
    # selected zero rows and wrote nothing; its only effect was to RESUME COMPUTE_WH (5
    # provisioning waits in 8 days). The S3-native capture is the sole writer of
    # lakehouse_raw/derivative_odds_raw/ (the INC-31 rule), which is what --w3pre-only reads.
    # Verified before removal: no dbt `source()` reader and no raw-SQL consumer anywhere in the
    # repo (the INC-27 grep-the-whole-repo rule).
    _run_script(context, "run_w1_lakehouse.py", ["--w3pre-only"], timeout=1800)


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lakehouse_w6_odds_marts_op(context):
    # HALT — the 13 W6 odds/CLV + odds-serving marts + the 2 Group-C staging flattens
    # (mart_odds_outcomes serves from S3 — live since W6; the _history/_current date
    # buckets are BOTH rewritten here daily, while the intraday odds cycle rewrites only
    # _current). daily_model_predictions is NOT re-exported here — this runs BEFORE
    # predict_today; the CLV marts refresh post-predict via the gated odds_clv path.
    _run_script(context, "run_w1_lakehouse.py", ["--w6-only"], timeout=2700)


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lakehouse_w7b_serving_op(context):
    # Mirror-tier (HALT once W7B_LAKEHOUSE_S3=1, ALERT-continue in the parallel window) —
    # the W7b prediction/serving mini-wave (mart_player_profile_identity injury chain +
    # probable_pitchers/lineups_wide serving backlog). ALERT-loud skip when gated off.
    if not _w7b_mirror_on():
        context.log.warning(
            "[lakehouse-w7b] W7B_LAKEHOUSE_S3/PARALLEL unset — skipping the W7b "
            "mini-wave rebuild (its parquet stays at the last build)."
        )
        return
    _run_mirror(context, "export_w7b_precursors_to_s3.py")
    _run_mirror(context, "run_w1_lakehouse.py", ["--w7b-only"])


def _alert_if_nothing_assessed(context, check_name: str, assessed: int | None,
                               unassessed_rows: int, *, dedup_key: str) -> None:
    """INC-37 — page WARN when a tier guard verified NOTHING but rows exist.

    THE FAILURE THIS CLOSES (2026-08-01): both tier guards skip a serving tier under
    MIN_GAMES_FOR_CHECK (=5) and then print `problem_count=0` / `alert_count=0`. During the
    INC-37 remediation a mis-run left 4 of 15 games served; BOTH tiers fell under the floor, so
    both guards reported zero problems while 11 games sat unserved. `tiers_assessed=0` was the
    only tell and no op read it. A check that could not evaluate must never read as healthy —
    the same three-valued treatment spine_horizon.classify applies to an absent metric.

    Deliberately narrow so it cannot become alert fatigue: it fires ONLY when `assessed == 0`
    AND rows exist. A genuinely small slate with SOME assessable tier stays silent, and a
    zero-prediction day never reaches here (the scripts return before emitting rows).
    WARN, not CRITICAL: "we could not verify" is not "we found a problem".
    """
    if assessed is None or assessed > 0 or unassessed_rows <= 0:
        return
    msg = (
        f"{check_name}: NOTHING was assessed for today's slate — {unassessed_rows} served row(s) "
        f"exist but every serving tier was under the minimum-games floor, so the check's "
        f"'0 problems' result is VACUOUS, not a pass (INC-37). The usual cause is that most of "
        f"the slate is missing: cross-check the served row count per tier against the scheduled "
        f"slate (scripts/check_prediction_coverage.py) before trusting any green result today."
    )
    context.log.warning("[ALERT] " + msg)
    try:
        from pipeline.utils.alerting import send_alert
        send_alert("Serving check could not verify today's slate", msg,
                   severity="WARN", dedup_key=dedup_key)
    except Exception as e:  # noqa: BLE001 — a failed page must not fail the op
        context.log.warning(f"[{check_name}] send_alert failed (non-fatal): {e}")


def _alert_on_stale_spine(context, stdout: str) -> None:
    """INC-37 — page when the just-built mart_game_spine does not reach today.

    ALERT-tier (never raises): the decision logic is the pure classifier in
    betting_ml.monitoring.spine_horizon, so it is unit-testable without a live build. Any failure
    inside the alerting path itself is swallowed — a monitor must never be the thing that takes
    down the op it is watching.
    """
    from betting_ml.monitoring.spine_horizon import classify, parse_spine_covers_today

    severity, message = classify(parse_spine_covers_today(stdout))
    if severity is None:
        context.log.info(f"[spine-staleness] OK — {message}")
        return
    context.log.warning(f"[ALERT] spine-staleness: {message}")
    try:
        from pipeline.utils.alerting import send_alert
        send_alert(
            "Game spine does not reach today's slate",
            message,
            severity=severity,
            dedup_key="spine_staleness",
        )
    except Exception as e:  # noqa: BLE001 — a failed page must not fail the build
        context.log.warning(f"[spine-staleness] send_alert failed (non-fatal): {e}")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lakehouse_spine_odds_bridge_op(context):
    # W8a-mirror tier — the 2026-07-02 spine-freeze + odds-bridge-freeze cures, verbatim
    # from the monolith: rebuild mart_game_spine (W5 Group A — the scheduled-game universe
    # the --w8a/--w8b feature build reads; a frozen spine silently degrades predict_today
    # to the intraday fallback) and then the odds-serving hot set off the FRESH spine
    # (mart_odds_outcomes _current + mart_game_odds_bridge + their ext-table refresh —
    # E1_11_BUG Defect 3: a bridge built off the previous run's spine froze has_odds=0 →
    # market-blind predict). check_odds_coverage_op (downstream) verifies the result.
    if not _w8a_mirror_on():
        context.log.warning(
            "[lakehouse-spine] W8A_LAKEHOUSE_S3/PARALLEL unset — skipping the spine + "
            "odds-bridge rebuild (spine-staleness ALERTs would fire at the source on use)."
        )
        return
    #
    # INC-37 (2026-08-01) — the spine-staleness detector inside run_w1_lakehouse has fired
    # correctly on every occurrence of this class (06-01, 07-01, 08-01) and NEVER notified
    # anyone: it wrote a stderr WARNING into the step log and nothing else, which is the E11.30
    # "ALERT-tier meant detected-but-unpaged" finding in its purest form. It now emits a
    # `[METRIC] spine_covers_today=` line and we page on it here. Keyed on the SAME condition as
    # the existing banner, so this adds no new false-positive surface. Never HALTs — the op's own
    # tier is unchanged; a stale spine is a loud page, not a reason to take the slate down.
    spine_out = _run_w8a_mirror(context, "run_w1_lakehouse.py", ["--w5-only", "--w5-group-a-only"])
    _alert_on_stale_spine(context, spine_out)
    _run_w8a_mirror(context, "run_w1_lakehouse.py", ["--w6-odds-current"])
    _run_w8a_mirror(context, "refresh_w1_external_tables.py", ["--w6-odds"])
    # E9.41 (2026-07-19) — mart_game_results is NOW fresh (--w5-group-a above), so rebuild the 3
    # CLV-label marts off it. The daily W6 build (lk6) ran BEFORE this refresh, so it built
    # mart_clv_labeled_games against a DAY-OLD mart_game_results → the mirror was a full day stale
    # (the featured "Yesterday" recap + /performance never settled yesterday). This targeted pass
    # (mart_closing_line_value already built at lk6) makes the CLV-label mirror current, then
    # refreshes its ext tables so the SF-target reads see it too.
    _run_w8a_mirror(context, "run_w1_lakehouse.py", ["--clv-labels-only"])
    _run_w8a_mirror(context, "refresh_w1_external_tables.py", ["--w6-clv"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lakehouse_w8a_feature_layer_op(context):
    # W8a-mirror tier (HALT once W8A_LAKEHOUSE_S3=1) — the W8a Python-table/seed
    # precursor mirrors + the upstream feature layer + EB posteriors DuckDB build + the
    # W8a ext-table refresh. The W9 signal stores it reads are mirrored by
    # export_w9_signals_to_s3_op (its own graph node, INC-25 ordering).
    if not _w8a_mirror_on():
        context.log.warning(
            "[lakehouse-w8a] W8A_LAKEHOUSE_S3/PARALLEL unset — skipping the W8a feature "
            "layer + EB posteriors rebuild."
        )
        return
    _run_w8a_mirror(context, "export_w8a_precursors_to_s3.py")
    _run_w8a_mirror(context, "run_w1_lakehouse.py", ["--w8a-only"])
    _run_w8a_mirror(context, "refresh_w1_external_tables.py", ["--w8a"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lakehouse_w8b_aggregator_op(context):
    # W8b-mirror tier (HALT once W8B_LAKEHOUSE_S3=1) — the SERVING-AGGREGATOR wave, AFTER
    # W8a (the aggregator reads the W8a feature layer): W5b Group-B marts first (they read
    # the eb_bullpen_team_posteriors parquet W8a just wrote; the aggregator reads W5b —
    # the 2026-07-02 W5b-staleness cure), then the W8b precursor mirrors, the complex
    # upstream + matchup models + the aggregator + wrapper, and the W8b ext-table refresh.
    if not _w8b_mirror_on():
        context.log.warning(
            "[lakehouse-w8b] W8B_LAKEHOUSE_S3/PARALLEL unset — skipping the W5b + W8b "
            "serving-aggregator rebuild."
        )
        return
    _run_w8b_mirror(context, "run_w1_lakehouse.py", ["--w5b-only"])
    _run_w8b_mirror(context, "export_w8b_precursors_to_s3.py")
    _run_w8b_mirror(context, "run_w1_lakehouse.py", ["--w8b-only"])
    _run_w8b_mirror(context, "refresh_w1_external_tables.py", ["--w8b"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lakehouse_w11_nightly_op(context):
    # Mirror-tier (ALERT-continue) — the gated W11/E11.22 nightly rebuilds, verbatim from
    # the monolith's tail: W4/W5 (FanGraphs/sprint/OAA marts off the repointed raw
    # mirrors; AFTER --w8a per the documented order), the umpire (W11b), weather (W11c),
    # transactions (W11tx) and public-betting (W11d — AFTER --w8b: its snapshots stg joins
    # feature_pregame_game_features) tiers. Each sub-tier keeps its own gate; a gated-off
    # tier logs a WARNING (loud skip).
    ran_any = False
    if _w11_w4w5_nightly_on():
        ran_any = True
        _run_w11_nightly(context, "run_w1_lakehouse.py", ["--w4-only"])
        _run_w11_nightly(context, "run_w1_lakehouse.py", ["--w5-only"])
    else:
        context.log.warning("[lakehouse-w11] W11_W4W5_NIGHTLY unset — skipping the W4/W5 nightly rebuild.")
    if _w11b_umpire_nightly_on():
        ran_any = True
        _run_w11_nightly(context, "run_w1_lakehouse.py", ["--w11b-only"])
        _run_w11_nightly(context, "refresh_w1_external_tables.py", ["--w11b"])
    else:
        context.log.warning("[lakehouse-w11] W11B_UMPIRE_NIGHTLY unset — skipping the umpire nightly rebuild.")
    if _w11c_weather_nightly_on():
        ran_any = True
        _run_w11_nightly(context, "run_w1_lakehouse.py", ["--w11c-only"])
        _run_w11_nightly(context, "refresh_w1_external_tables.py", ["--w11c"])
    else:
        context.log.warning("[lakehouse-w11] W11C_WEATHER_NIGHTLY unset — skipping the weather nightly rebuild.")
    if _w11tx_transactions_nightly_on():
        ran_any = True
        _run_w11_nightly(context, "run_w1_lakehouse.py", ["--w11tx-only"])
        _run_w11_nightly(context, "refresh_w1_external_tables.py", ["--w11tx"])
    else:
        context.log.warning("[lakehouse-w11] W11TX_TRANSACTIONS_NIGHTLY unset — skipping the transactions nightly rebuild.")
    if _w11d_public_betting_nightly_on():
        ran_any = True
        _run_w11_nightly(context, "run_w1_lakehouse.py", ["--w11d-only"])
        _run_w11_nightly(context, "refresh_w1_external_tables.py", ["--w11d"])
    else:
        context.log.warning("[lakehouse-w11] W11D_PUBLIC_BETTING_NIGHTLY unset — skipping the public-betting nightly rebuild.")
    if not ran_any:
        context.log.warning("[lakehouse-w11] every W11 nightly gate is unset — op was a full no-op.")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def lakehouse_delta_maintenance_op(context):
    # E11.20 — WARN-but-continue: Delta compaction + vacuum for the migrated tables (the
    # REQUIRED companion to the daily partition write — spike gotcha #7: every incremental
    # write adds small files; unmaintained, read planning degrades). Vacuum retention is
    # clamped ≥168h in scripts/utils/delta_lake.py (below that, time-travel is physically
    # destroyed — spike gotcha #3). Off the critical path: a maintenance failure defers
    # compaction to tomorrow, never blocks serving. ALERT-loud skip when Delta is off.
    from betting_ml.utils.delta_lakehouse import delta_w1_mode

    if delta_w1_mode() == "off":
        context.log.warning(
            "[delta-maintenance] LAKEHOUSE_DELTA_W1=off — skipping Delta compaction/vacuum."
        )
        return
    try:
        _run_script(context, "delta_maintenance.py", timeout=1200)
    except Exception as e:  # noqa: BLE001 — maintenance defers to the next run; never HALT
        context.log.warning(f"[delta-maintenance] compaction/vacuum failed (non-fatal; "
                            f"retried on the next daily run): {e}")


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
def check_odds_coverage_op(context):
    """Durable odds-coverage DQ guard (2026-07-02 incident — E1_11_BUG Defect 3).

    Detects the "bridge freeze" class: mart_game_odds_bridge has 0 has_odds rows for the
    CURRENT slate even though mart_game_spine (games) AND mart_odds_outcomes (odds events)
    are both fresh — i.e. the bridge parquet did not rebuild, so predict_today would run
    MARKET-BLIND with no error, no null-alert. Placed right after the odds marts are
    (re)built + external tables refreshed (run_w1_lakehouse_op --w6 → refresh_w1_external_
    tables_op) and before the prediction path, so a freeze is caught before predict.

    Tier: ALERT-loud-but-continue by DEFAULT (RUNTIME-GATE-safe rollout). check_odds_coverage.py
    exits 0 and only WARNs unless ODDS_COVERAGE_STRICT=1, which promotes a CURRENT-slate FREEZE
    to a non-zero exit → HALT here. The FREEZE test requires odds_events>0, so it can NEVER
    false-fire when books simply have not posted yet (that path is NO_ODDS_YET, benign). Flip
    ODDS_COVERAGE_STRICT=1 in the box env_file after confirming it does not false-fire.

    E11.30: in the (default) non-strict path the script always exits 0, so the `except` below
    NEVER fires for a FREEZE — the op used to only `context.log.warning`, a detection with no
    notification (the E11.27 finding: "ALERT-tier" had quietly meant "logged, nobody paged").
    It now pages via send_alert on the script's discriminating `odds_coverage_freeze` metric —
    the strict/HALT path still needs no separate page: raising there fails the op, which fails
    daily_ingestion_job, which run_failure_alert_sensor already pages CRITICAL for."""
    strict = os.environ.get("ODDS_COVERAGE_STRICT") == "1"
    try:
        stdout = _run_script(context, "check_odds_coverage.py", ["--env", _target_env()])
    except Exception as e:
        # Non-strict: never take down serving during rollout (ALERT-continue). Strict: the
        # script exited non-zero on a current-slate FREEZE (or a genuine crash) → let it HALT
        # (run_failure_alert_sensor pages CRITICAL on the resulting job failure).
        if strict:
            raise
        context.log.warning(
            "[ALERT] check_odds_coverage flagged an odds-coverage problem "
            f"(non-blocking; set ODDS_COVERAGE_STRICT=1 to HALT): {e}"
        )
        return
    freeze = False
    for line in stdout.splitlines():
        if line.startswith("[METRIC] odds_coverage_score="):
            try:
                score = float(line.split("=", 1)[1])
                context.add_output_metadata({"odds_coverage_score": MetadataValue.float(score)})
            except ValueError:
                pass
        elif line.startswith("[METRIC] odds_coverage_freeze="):
            freeze = line.split("=", 1)[1].strip() == "1"
    if freeze:
        from pipeline.utils.alerting import send_alert
        send_alert(
            "Odds bridge FREEZE on current slate",
            "mart_game_odds_bridge has 0 has_odds rows for today's slate despite fresh "
            "spine + odds events (the bridge did not rebuild) — predictions will run "
            "MARKET-BLIND. See the Dagster step log (check_odds_coverage_op) for detail. "
            "Remediate: rebuild the bridge (run_w1_lakehouse.py --w6-odds-current + "
            "refresh_w1_external_tables.py --w6-odds) and confirm the spine (--w5-group-a) "
            "rebuild runs daily BEFORE --w6.",
            severity="CRITICAL",
            dedup_key="odds_coverage_freeze",
        )


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def check_feature_block_coverage_op(context):
    """Durable served-feature-block coverage guard (F2 / F2-recurrence — E1_11_BUG).

    Detects the "silently-zeroed block" class: a whole feature block (the umpire z-scores
    fired 2026-07-02 AND again 2026-07-03) materializes ~100% NULL in served
    feature_pregame_game_features while every other block + the row COUNT stay intact — an
    ext-table VALUE:-case mismatch or a precursor build not wired into the daily job (the
    deferred W11b umpire cutover). Predictions then run on an amputated feature set with no
    error. Placed after the external tables are refreshed (refresh_w1_external_tables_op) and
    before predict, alongside check_odds_coverage_op. Self-calibrating: it compares each
    block's coverage on recently-PLAYED slates to the block's own older baseline, so it fires
    only when a normally-full block collapses (never on posting-timing or coverage-gapped blocks).

    Tier: ALERT-loud-but-continue by DEFAULT (RUNTIME-GATE-safe rollout). The script exits 0
    and only WARNs unless FEATURE_COVERAGE_STRICT=1, which promotes any DEGRADED block to a
    non-zero exit → HALT here. Flip FEATURE_COVERAGE_STRICT=1 in the box env_file after the
    W11b umpire cutover restores the block and it is confirmed not to false-fire.

    E11.30: the non-strict (default) path always exits 0, so a DEGRADED block used to only
    reach `context.log.warning` — a detection nobody was paged on (the F2 class this guard
    exists for could recur silently). It now pages via send_alert on the script's
    `feature_block_degraded_count` metric (never set by a SKIPPED/coverage-gapped block, so it
    can't false-fire on a block that is legitimately partial by era/source); CRITICAL when a
    whole-slate date outage is present (`feature_block_date_outage_count`, the E9.53 signature
    the window-aggregate alone would dilute away), ERROR otherwise."""
    strict = os.environ.get("FEATURE_COVERAGE_STRICT") == "1"
    try:
        stdout = _run_script(context, "check_feature_block_coverage.py", ["--env", _target_env()])
    except Exception as e:
        if strict:
            raise
        context.log.warning(
            "[ALERT] check_feature_block_coverage flagged a collapsed feature block "
            f"(non-blocking; set FEATURE_COVERAGE_STRICT=1 to HALT): {e}"
        )
        return
    degraded_count = 0
    date_outage_count = 0
    for line in stdout.splitlines():
        if line.startswith("[METRIC] feature_block_min_cov_ratio="):
            try:
                ratio = float(line.split("=", 1)[1])
                context.add_output_metadata(
                    {"feature_block_min_cov_ratio": MetadataValue.float(ratio)})
            except ValueError:
                pass
        elif line.startswith("[METRIC] feature_block_date_outage_count="):
            try:
                date_outage_count = int(line.split("=", 1)[1])
            except ValueError:
                pass
        elif line.startswith("[METRIC] feature_block_degraded_count="):
            try:
                degraded_count = int(line.split("=", 1)[1])
            except ValueError:
                pass
    if degraded_count > 0:
        from pipeline.utils.alerting import send_alert
        send_alert(
            "Feature block SILENTLY COLLAPSED",
            f"{degraded_count} served feature block(s) collapsed on recently-played slates "
            f"({date_outage_count} whole-slate date outage(s)) — predictions run on an "
            "amputated feature set. See the Dagster step log (check_feature_block_coverage_op) "
            "for which block(s). Likely an ext-table VALUE:-case mismatch or a precursor build "
            "not wired into the daily job.",
            severity="CRITICAL" if date_outage_count > 0 else "ERROR",
            dedup_key="feature_block_degraded",
        )


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def check_served_prediction_integrity_op(context):
    """E11.22 served-prediction integrity gate — the permanent INPUT-integrity monitor.

    Reads TODAY's written daily_model_predictions right after predict and ALARMS, per
    serving tier, on the exact migration failure classes that row-count parity misses and
    the standing 30-day model-health sensor only surfaces WEEKS later downstream:
      - INC-22   predictions dated beyond the US baseball date (UTC-roll / wrong-date serve)
      - INC-25   the slate silently fell to intraday_fallback (data_source != feature_store)
      - INC-17-P2 post_lineup feature_coverage_score collapsed (a lineup block went null)
      - INC-24   a target's output went FLAT (near-constant / all-null — market-blind /
                 constant-imputed features)
    Reuses the model-health MIN_SPREAD_* / coverage thresholds so serve-time and the 30-day
    gate can never drift. Placed AFTER predict (it inspects what predict actually served);
    fans out from predict so it never blocks the serving writes.

    Tier: ALERT-loud-but-continue by DEFAULT (RUNTIME-GATE-safe rollout). The script exits 0
    and only WARNs unless SERVED_INTEGRITY_STRICT=1, which promotes any integrity problem to a
    non-zero exit → HALT here. Flip SERVED_INTEGRITY_STRICT=1 in the box env_file after it is
    confirmed on a live slate not to false-fire.

    E11.30: this is the op the E11.27 finding names directly — it ALREADY had a
    feature_store_frac<0.80 fallback detector (among others) when the intraday_fallback
    blind spot persisted for days, because the non-strict path only reached
    `context.log.warning` and nobody was paged; a human hand-querying the column was the
    only alarm. It now pages via send_alert on the script's discriminating
    `served_integrity_problem_count` metric (0 = healthy; every problem class it counts —
    wrong-date, fallback, coverage collapse, flat output, blank target-book price — is a
    genuine served-data defect, so this can't fire on a benign/chronic baseline)."""
    strict = os.environ.get("SERVED_INTEGRITY_STRICT") == "1"
    try:
        stdout = _run_script(context, "check_served_prediction_integrity.py", ["--env", _target_env()])
    except Exception as e:
        if strict:
            raise
        context.log.warning(
            "[ALERT] check_served_prediction_integrity flagged a served-slate integrity problem "
            f"(non-blocking; set SERVED_INTEGRITY_STRICT=1 to HALT): {e}"
        )
        return
    problem_count = 0
    assessed = None
    unassessed_rows = 0
    for line in stdout.splitlines():
        if line.startswith("[METRIC] served_integrity_problem_count="):
            try:
                problem_count = int(line.split("=", 1)[1])
                context.add_output_metadata(
                    {"served_integrity_problem_count": MetadataValue.int(problem_count)})
            except ValueError:
                pass
        elif line.startswith("[METRIC] served_integrity_tiers_assessed="):
            try:
                assessed = int(line.split("=", 1)[1])
            except ValueError:
                pass
        elif line.startswith("[METRIC] served_integrity_unassessed_rows="):
            try:
                unassessed_rows = int(line.split("=", 1)[1])
            except ValueError:
                pass
    _alert_if_nothing_assessed(context, "served-prediction integrity", assessed, unassessed_rows,
                               dedup_key="served_integrity_unassessed")
    if problem_count > 0:
        from pipeline.utils.alerting import send_alert
        send_alert(
            "Served-prediction integrity problem",
            f"{problem_count} integrity problem(s) on today's served slate — the model served "
            "a degraded/flat/mis-dated feature vector or a blank target-book price. See the "
            "Dagster step log (check_served_prediction_integrity_op) for the per-tier detail. "
            "Investigate with: rescore_audit --since <date> --compare-live, load_todays_features "
            "coverage gate, W8a/W8b served parquet freshness, and the odds/feature-block "
            "coverage guards.",
            severity="CRITICAL",
            dedup_key="served_prediction_integrity",
        )


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def check_intraday_fallback_op(context):
    """E11.27 — per-slate intraday_fallback monitor (the silent-degrade blind-spot closer,
    E11.24 §8 / INC-35).

    `predict_today`'s feature-source selection silently falls through to the intraday assembly
    (data_source='intraday_fallback' / 'intraday_assembly') whenever the feature store has no
    rows for today or its coverage is below the gate — no HALT, no alarm. This is a distinct,
    NARROWER signal from `check_served_prediction_integrity_op`: it is keyed specifically on the
    SERIOUS fallback signature (a slate-wide/high-share fallback, and/or any tier with
    feature_store=0 — the phase-2b tz-incident fingerprint) while explicitly staying silent on
    the CHRONIC ~1-game/slate baseline (INC-35) so the check never cries wolf. See the script's
    module docstring (scripts/check_intraday_fallback.py) for the full threshold rationale.

    Tier: ALERT-loud-but-continue, ALWAYS (E11.7) — this check has NO --strict escalation and
    NEVER HALTs; a degraded slate is advisory, not a reason to fail the daily job. Runs beside
    check_served_prediction_integrity_op (both fan out from predict so neither blocks the
    serving writes); genuinely PAGES via send_alert (not just a log line) so the blind spot this
    closes doesn't just move from 'nothing watches it' to 'a log line nobody reads'."""
    try:
        stdout = _run_script(context, "check_intraday_fallback.py", ["--env", _target_env()])
    except Exception as e:  # noqa: BLE001 — ALERT-tier: a transient S3/DuckDB read issue must
        # never take down the daily job.
        context.log.warning(
            f"[ALERT] check_intraday_fallback could not run (non-blocking; a transient S3/"
            f"DuckDB read issue is itself informative but must not HALT): {e}"
        )
        return
    alert_count = 0
    zero_fs_tiers = 0
    assessed = None
    unassessed_rows = 0
    for line in stdout.splitlines():
        if line.startswith("[METRIC] intraday_fallback_tiers_assessed="):
            try:
                assessed = int(line.split("=", 1)[1])
            except ValueError:
                pass
        elif line.startswith("[METRIC] intraday_fallback_unassessed_rows="):
            try:
                unassessed_rows = int(line.split("=", 1)[1])
            except ValueError:
                pass
        elif line.startswith("[METRIC] intraday_fallback_alert_count="):
            try:
                alert_count = int(line.split("=", 1)[1])
                context.add_output_metadata(
                    {"intraday_fallback_alert_count": MetadataValue.int(alert_count)})
            except ValueError:
                pass
        elif line.startswith("[METRIC] intraday_fallback_zero_feature_store_tiers="):
            try:
                zero_fs_tiers = int(line.split("=", 1)[1])
                context.add_output_metadata(
                    {"intraday_fallback_zero_feature_store_tiers": MetadataValue.int(zero_fs_tiers)})
            except ValueError:
                pass
        elif line.startswith("[METRIC] intraday_fallback_chronic_games="):
            try:
                n = int(line.split("=", 1)[1])
                context.add_output_metadata(
                    {"intraday_fallback_chronic_games": MetadataValue.int(n)})
            except ValueError:
                pass
    _alert_if_nothing_assessed(context, "intraday_fallback monitor", assessed, unassessed_rows,
                               dedup_key="intraday_fallback_unassessed")
    if alert_count == 0:
        return
    from pipeline.utils.alerting import send_alert
    severity = "CRITICAL" if zero_fs_tiers > 0 else "WARN"
    send_alert(
        "Serving slate fell to intraday_fallback",
        f"{alert_count} serving tier(s) hit the serious intraday_fallback threshold today "
        f"({zero_fs_tiers} with feature_store=0 — the phase-2b tz-incident fingerprint). "
        "See the Dagster step log (check_intraday_fallback_op) for per-tier detail. "
        "Investigate: load_todays_features' coverage gate, W8a/W8b served parquet freshness, "
        "and the daily-job build ordering (INC-25 class).",
        severity=severity,
        dedup_key="intraday_fallback",
    )


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def check_w11_tail_coverage_op(context):
    """INC-37 — the daily TODAY-guard for the W11 serving tail (umpire / weather /
    public_betting), the three feature blocks the six-block coverage gate CANNOT see.

    `_FEATURE_STORE_COVERAGE_BLOCKS` — the set `predict_today` gates on and
    `check_feature_block_coverage_op` asserts over — covers lineup, starter, team_rolling,
    bullpen_eb, sequential and odds. It does not cover the W11 tail, and
    `check_feature_block_coverage` structurally cannot: it EXCLUDES the anchor date and asserts
    only over dates already in the store, so it is a store-HISTORY guard, never a TODAY guard.
    On 2026-08-01 the month-boundary schedule hole built the whole tail on a July-only game
    universe — `feature_pregame_weather_features` and `feature_pregame_public_betting_features`
    held 0 of 15 slate games and a front-end panel had no rows — while the coverage gate read a
    healthy 0.878 and nothing paged. `scripts/check_w11_tail_coverage.py` was written as the
    missing today-guard but stayed a MANUAL post-rebuild step, so the blind spot was still open
    in prod. This op closes it: the E11.30 rule that an ALERT-tier op must actually call
    send_alert, keyed on the discriminating verdict the script already computes.

    TWO RUNS, ONE PER SLATE — and that is the crux, not an optimisation. The script's BUILD_GAP
    verdict (the feed HAS the slate, the built table does not) is only a DEFECT for a block whose
    feed lands BEFORE the build that consumes it. Measured 2026-08-01 UTC: public_betting's
    ActionNetwork ingest (s4, 12:00) precedes the ~12:40 `lakehouse_w11_nightly_op` build, but
    `ingest_weather` (s7) writes forecast_pregame at 12:50 and `ingest_umpires.py --date today`
    (s8/s17) lands 12:0x–16:39 — both AFTER it. Paging on the current slate for umpire/weather
    would therefore fire CRITICAL every single morning on the normal build cadence, which is the
    alert-fatigue failure mode this check's own two-sided design exists to avoid. So
    public_betting is judged on TODAY (the same-day INC-37 detector) and umpire/weather on the
    PRIOR slate, where exactly one build cycle has elapsed — the same exemption
    `check_feature_block_coverage._DATE_OUTAGE_SKIP_NEWEST` already makes for the same reason.
    The policy + severities live in `betting_ml.monitoring.w11_tail_coverage` (import-safe /
    unit-testable without the dbt manifest).

    Tier: ALERT-loud-but-continue, ALWAYS (E11.7) — no strict escalation exists here and it NEVER
    HALTs: a blank transparency panel must never withhold a slate's predictions. Fans out from
    predict (which is far downstream of the W11 build it validates), so it can never gate the
    serving writes. The script's own `--strict` stays the OPERATOR's acceptance-gate mode after a
    targeted rebuild/flip — a stricter question ("did the rebuild I just ran cover this slate")
    than the daily monitor's.

    A finite subprocess timeout is mandatory (INC-32): an un-timed-out DuckDB/S3 read on a daemon
    path can wedge a worker thread."""
    from betting_ml.monitoring.w11_tail_coverage import (
        classify,
        parse_block_coverage,
        parse_block_verdicts,
    )

    today, prior = _today(), _one_day_ago()

    def _run(day: str) -> str:
        try:
            return _run_script(context, "check_w11_tail_coverage.py", ["--date", day],
                               timeout=900)
        except Exception as e:  # noqa: BLE001 — ALERT tier: a transient S3/DuckDB read issue
            # must never take down the daily job. An empty stdout reads as UNVERIFIED
            # downstream (never as healthy), so the failure still surfaces as a WARN page.
            context.log.warning(
                f"[ALERT] check_w11_tail_coverage could not run for {day} (non-blocking; the "
                f"slate's W11 tail is UNVERIFIED for this run, not verified-healthy): {e}"
            )
            return ""

    today_out, prior_out = _run(today), _run(prior)

    for label, out in (("today", today_out), ("prior_slate", prior_out)):
        verdicts = parse_block_verdicts(out)
        for block, (n, m) in parse_block_coverage(out).items():
            context.add_output_metadata(
                {f"w11_tail_{label}_{block}": MetadataValue.text(
                    f"{n}/{m} {verdicts.get(block, 'UNVERIFIED')}")})

    severity, msg = classify(today_out, prior_out, today_date=today, prior_date=prior)
    if severity is None:
        context.log.info(msg)
        return
    context.log.warning("[ALERT] " + msg)
    from pipeline.utils.alerting import send_alert
    send_alert("W11 serving tail coverage gap", msg, severity=severity,
               dedup_key="w11_tail_coverage")


# ── E11.23 — silently-not-running guard (the cutover-runtime-landmine detector) ───────
# The E11.1 cutover left a class of RUNTIME failures CI can't see (it mocks all IO): intraday
# refresh jobs shipped GATED-OFF and serving-critical sensors/schedules that boot STOPPED, so
# they SILENTLY NEVER RUN — odds froze 3 days with NO alert; the lineup monitor was dead 2 days.
# The default_status=RUNNING flips on those sensors/schedules are the structural cure; THIS op is
# the DETECTOR. It runs inside the daily job (itself now self-starting) and ALARMS if a
# serving-critical monitor is manually STOPPED, or a permanently-on intraday flag is unset.
#
# Tier: ALERT-loud-but-continue (E11.7). It NEVER raises — a dead monitor must not also take down
# the daily job; it emails CRITICAL + logs a WARNING so the silence becomes VISIBLE. The
# intended-state table in BOX_OPERATIONS.md §10 is the source of truth for the sets below.

@op(out=Out(Nothing))
def check_monitors_healthy_op(context):
    """ALARM (never HALT) if a serving-critical sensor/schedule is STOPPED or a permanently-on
    intraday flag is unset — the E11.23 cure for the 'silently never runs' class the cutover left.
    Standalone (no upstream): a heartbeat that runs every daily job regardless of the ingest chain.
    The critical sets + required flags + pure detectors live in
    ``betting_ml.monitoring.monitor_health`` (import-safe / unit-testable without the dbt manifest)."""
    from betting_ml.monitoring.monitor_health import (
        REQUIRED_INTRADAY_FLAGS,
        flag_problems,
        stale_running_sensor_ticks,
        stopped_critical_instigators,
    )

    problems = flag_problems(os.environ)
    # Instance introspection is best-effort — an ephemeral/CI instance that can't answer must not
    # crash the guard (ALERT-tier); the flag check above always runs.
    try:
        problems.extend(stopped_critical_instigators(context.instance))
    except Exception as e:  # noqa: BLE001
        context.log.warning(
            f"monitor-state introspection unavailable (intraday-flag check still ran): {e}"
        )
    # INC-32: also page if a critical sensor is still RUNNING but its ticks have STALLED (the
    # sensor-daemon-wedged mode E11.23's STOPPED check is blind to — 7/17 all evals stopped
    # ~21:30Z). Best-effort / never crashes the guard.
    try:
        import time as _time
        problems.extend(stale_running_sensor_ticks(context.instance, _time.time()))
    except Exception as e:  # noqa: BLE001
        context.log.warning(f"sensor-tick staleness check unavailable: {e}")
    context.add_output_metadata({"monitor_problems": MetadataValue.int(len(problems))})
    if not problems:
        context.log.info(
            "Monitor health OK: no critical sensor/schedule STOPPED; all %d required intraday "
            "flags set.", len(REQUIRED_INTRADAY_FLAGS),
        )
        return
    msg = (
        "SILENTLY-NOT-RUNNING ALERT (E11.23): serving-critical monitors are OFF or intraday "
        "refreshes are gated off — they FAIL SILENT (the odds-froze-3-days class). "
        + "; ".join(problems)
        + ". Fix: START the STOPPED sensor/schedule in Dagit (toggle on) and/or set the missing "
        "flag(s) in the box env_file + redeploy. Intended-state table: "
        "services/dagster/aws/BOX_OPERATIONS.md §10."
    )
    context.log.warning("[ALERT] " + msg)
    from pipeline.utils.alerting import send_alert
    send_alert("Monitor silently not running", msg, severity="CRITICAL", dedup_key="monitor_health")


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
                    ["--date", d, "--env", env] + _w9_s3_read_args())


@op(ins={"start": In(Nothing)}, out=Out(Nothing), tags=_SUB_MODEL_OP_TAGS)
def generate_offense_signals_op(context):
    env = _target_env()
    for d in _recent_completed_dates():
        _run_script(context, "/app/betting_ml/scripts/offense_v2/generate_offense_signals.py",
                    ["--date", d, "--env", env] + _w9_s3_read_args())


@op(ins={"start": In(Nothing)}, out=Out(Nothing), tags=_SUB_MODEL_OP_TAGS)
def generate_totals_generative_signals_op(context):
    # E2.5 — per-side GENERATIVE totals signal (totals_generative_v1). Scores the recently-completed
    # window with the champion (LightGBM Poisson mean + E2.3 held-out per-side r); is_oos is True on
    # the current partial season (the champion never trained on it). The leakage-safe HISTORICAL
    # backfill (walk-forward as-of scoring) is a ONE-TIME operator run:
    #   generate_totals_generative_signals.py --backfill --leakage-safe --s3
    # This daily op only advances the recent completed dates (mirrors generate_offense_signals_op).
    env = _target_env()
    for d in _recent_completed_dates():
        _run_script(context, "/app/betting_ml/scripts/totals_generative/generate_totals_generative_signals.py",
                    ["--date", d, "--env", env] + _w9_s3_read_args())


@op(ins={"start": In(Nothing)}, out=Out(Nothing), tags=_SUB_MODEL_OP_TAGS)
def generate_starter_signals_op(context):
    env = _target_env()
    for d in _recent_completed_dates():
        _run_script(context, "/app/betting_ml/scripts/starter_v1/generate_starter_signals.py",
                    ["--date", d, "--env", env] + _w9_s3_read_args())


@op(ins={"start": In(Nothing)}, out=Out(Nothing), tags=_SUB_MODEL_OP_TAGS)
def generate_starter_ip_signals_op(context):
    env = _target_env()
    for d in _recent_completed_dates():
        _run_script(context, "/app/betting_ml/scripts/starter_v1/generate_starter_ip_signals.py",
                    ["--date", d, "--env", env] + _w9_s3_read_args())


@op(ins={"start": In(Nothing)}, out=Out(Nothing), tags=_SUB_MODEL_OP_TAGS)
def generate_bullpen_signals_op(context):
    # Champion is v2; --v2-only keeps the daily op fast. (bullpen_v1 is superseded
    # by 6D; drop the flag if v1 needs to advance daily too.) Wired downstream of
    # the starter-IP op because bullpen_v2 Candidate B reads starter_ip_signals
    # (starter_ip_p20_outs) for exposure scaling.
    env = _target_env()
    for d in _recent_completed_dates():
        _run_script(context, "/app/betting_ml/scripts/generate_bullpen_signals.py",
                    ["--date", d, "--env", env, "--v2-only"] + _w9_s3_read_args())


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
                    ["--date", d, "--env", env] + _w9_s3_read_args())


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
                    ["--date", d, "--env", env] + _w9_s3_read_args())


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def dbt_sub_model_signals_rebuild(context):
    # Materialize the wide PIVOT (feature_pregame_sub_model_signals) in Snowflake. INC-25: this now
    # runs AFTER export_w9_signals_to_s3_op (stores→S3) + rebuild_sub_model_signals_consumer_op
    # (rebuilds the consumer S3 parquet from the fresh stores). On the SF target the model is
    # `select * from lakehouse_ext.feature_pregame_sub_model_signals` (reads that fresh parquet); on
    # a native target it builds the pivot directly from the live SF stores — both are fresh here.
    _run_dbt(context, [
        "run",
        "--select", "feature_pregame_sub_model_signals",
        "--target", "baseball_betting_and_fantasy",
    ])


# ── E11.1-W9 — sub-model SIGNAL-STORE export-mirror → S3 ─────────────────────
# Mirror the 5 signal stores (mart_sub_model_signals + the 4 betting_features signal
# tables) Snowflake → S3 parquet so the W8 feature-layer consumer can read the signal
# path from S3. ADDITIVE dual-write: the generators keep writing Snowflake (the live
# accumulate path); this copies their OUTPUT to S3 (accumulate-safe by construction —
# a full-table copy carries every SCD-2 history row). Gated default-OFF.
def _w9_mirror_on() -> bool:
    # E11.1-W9 cutover switch (default OFF → the op is a no-op until the operator validates
    # the mirror via scripts/parity_check_w9_signals.py and flips it; mirrors W7A_LAKEHOUSE_S3 /
    # W6_LAKEHOUSE_INTRADAY). Snowflake stays the live signal path during the W9 window.
    return os.environ.get("W9_LAKEHOUSE_S3") == "1"


@op(
    ins={
        "run_env_done":       In(Nothing),
        "offense_done":       In(Nothing),
        "totals_gen_done":    In(Nothing),
        "starter_done":       In(Nothing),
        "starter_ip_done":    In(Nothing),
        "bullpen_done":       In(Nothing),
        "matchup_done":       In(Nothing),
        "env_state_done":     In(Nothing),
        "defense_quality_done": In(Nothing),
    },
    out=Out(Nothing),
)
def export_w9_signals_to_s3_op(context):
    # E11.7 failure tier: ALERT-loud-but-continue (MIRROR tier) — a Snowflake→S3 export failure must
    # never HALT the serving pipeline; if the mirror is stale the consumer rebuild + freshness gate
    # catch it downstream.
    # INC-25 (2026-07-01): this op is now the FAN-IN of all 9 signal generators and runs BEFORE
    # rebuild_sub_model_signals_consumer_op + dbt_sub_model_signals_rebuild. After the W8a cutover the
    # Snowflake consumer feature_pregame_sub_model_signals reads the S3 parquet built from these
    # stores, so the store parquets MUST be refreshed (here) before the consumer parquet is rebuilt —
    # otherwise the consumer serves a slate-stale pivot (the INC-25 root cause). It also emits an
    # at-the-source coverage ALERT (export_w9_signals_to_s3._alert_empty_source_groups).
    if not _w9_mirror_on():
        context.log.info("W9_LAKEHOUSE_S3 != 1 — skipping W9 signal-store mirror (default OFF).")
        return
    try:
        _run_script(context, "export_w9_signals_to_s3.py")
        # Best-effort external-table refresh so the lakehouse_ext W9 views see the fresh parquet
        # (no native reader depends on them yet; --w9 is best-effort and never raises on a miss).
        _run_script(context, "refresh_w1_external_tables.py", ["--w9"])
    except Exception as exc:  # noqa: BLE001 — MIRROR tier; never block the serving pipeline.
        context.log.warning(
            "WARNING: export_w9_signals_to_s3_op failed; continuing (the W9 S3 signal mirror "
            "may be stale/partial — serving still reads Snowflake, parity_check_w9_signals will "
            f"show the gap). Error: {exc}"
        )


# ── INC-25 — post-generator consumer-parquet rebuild ─────────────────────────
@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def rebuild_sub_model_signals_consumer_op(context):
    """INC-25 (P0 serving-down fix): rebuild the feature_pregame_sub_model_signals CONSUMER S3
    parquet from the freshly-exported W9 stores, then refresh its external table — so the Snowflake
    consumer (`select * from lakehouse_ext.feature_pregame_sub_model_signals` post-W8a-cutover)
    reflects the CURRENT slate before dbt_sub_model_signals_rebuild materializes it and
    signal_freshness_check gates on it.

    ROOT CAUSE it fixes: the full --w8a build runs at daily-job START (run_w1_lakehouse_op, line ~76),
    BEFORE the day's signal generators write the stores and BEFORE export_w9_signals_to_s3_op mirrors
    them to S3 → the consumer parquet it produced lagged the stores by a full slate, so the SCD-2
    groups (run_env/bullpen/matchup/env/defense) read empty on the freshest completed slate and
    signal_freshness_check HALTed the job (starter_ip happened to be present in the prior-day parquet
    → the lone survivor). Fans out from export_w9_signals_to_s3_op; must precede
    dbt_sub_model_signals_rebuild.

    Failure tier: only meaningful once the W8a cutover is live (W8A_LAKEHOUSE_S3=1) — that is when the
    SF consumer reads the S3 parquet. Then it is SERVING-CRITICAL (a stale/failed rebuild HALTs the
    freshness gate anyway), so let _run_script raise (HALT). Pre-cutover the SF consumer builds the
    pivot natively from the live SF stores (always fresh) → this op is a no-op."""
    if not _w8a_serving_on():
        context.log.info(
            "W8A_LAKEHOUSE_S3 != 1 — the SF consumer builds the pivot natively from the live stores "
            "(fresh); skipping the INC-25 consumer-parquet rebuild (default OFF)."
        )
        return
    # HALT tier: rebuild the single consumer parquet from the fresh W9 store parquets, then refresh
    # just that external table (both narrow/fast — a single pivot + one ALTER … REFRESH).
    _run_script(context, "run_w1_lakehouse.py", ["--sub-model-signals-only"])
    _run_script(context, "refresh_w1_external_tables.py", ["--sub-model-signals"])


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
    # E11.20 phase 1.5: under W7A_LAKEHOUSE_S3=1 (cut over on the box) the PA substrate
    # reads from the S3 lakehouse — the last DAILY Snowflake read of the W1 pitch-mart
    # family, a precondition for dropping the SF mart_pitch_* views (rollout doc §6 step 6).
    # 2026-07-22: --catchup (was --date yesterday) advances the chain over EVERY completed date
    # missing since the frontier, in order — self-healing if yesterday's completed-game source
    # wasn't ready when this ran (the fragile single-day advance permanently skipped such a day →
    # the team-seq 7/21 NULL). Order-preserving; see betting_ml/scripts/sequential_bayes/catchup.py.
    _run_script(context, f"{_SEQ_DIR}/update_player_posteriors.py",
                ["--catchup"] + _w7a_s3_args())


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def update_team_posteriors_op(context):
    # 2026-07-22: --catchup (was --date yesterday) — self-healing ordered advance; see the note on
    # update_player_posteriors_op + catchup.py. Directly fixes the team-seq 7/21 permanent-skip.
    _run_script(context, f"{_SEQ_DIR}/update_team_posteriors.py", ["--catchup"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def update_matchup_cell_posteriors_op(context):
    # 2026-07-22: --catchup (was --date yesterday) — self-healing ordered advance; see the note on
    # update_player_posteriors_op + catchup.py.
    _run_script(context, f"{_SEQ_DIR}/update_matchup_cell_posteriors.py",
                ["--catchup"] + _w7a_s3_args())


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
    # INC (2026-06-23): the op HALTed the whole daily job when the centroids/scaler pkls were
    # missing from the image — now loaded from S3 + non-blocking.
    #
    # 2026-07-06 (E11.22): PROMOTED WARN → ALERT (send_alert). The prior WARN-tier swallow said
    # "the source-scoped freshness monitor pages if the table goes stale" — but the W7a cutover
    # (W7A_LAKEHOUSE_S3=1) made this op write the S3 parquet ONLY (the SF mart is frozen), while
    # check_data_freshness.py still watches the FROZEN SF table → it CANNOT page. Result: the op
    # failed silently 2026-06-28→07-05 (baked-image drift in the --s3 persist), serving 9-day-stale
    # archetype posteriors → INC-17 post_lineup coverage 0.822 < 0.85, caught only downstream. So the
    # op must page ITSELF. Still ALERT-tier (loud-but-continue): a failure never HALTs the serving job.
    try:
        _run_script(context, f"{_EB_DIR}/compute_archetype_posteriors.py",
                    ["--mode", "today"] + _w7a_s3_args())
    except Exception as exc:  # noqa: BLE001 — peripheral; never block the serving pipeline.
        msg = (
            "update_archetype_posteriors_op failed; continuing without a fresh archetype refresh. "
            "The archetype-matchup block (a heavy home_win component) will serve STALE and silently "
            "degrade post_lineup feature_coverage until this lands — under W7A_LAKEHOUSE_S3 the write "
            f"is S3-parquet-only, so the SF-watching freshness monitor will NOT catch it. Error: {exc}"
        )
        context.log.warning("[ALERT] " + msg)
        from pipeline.utils.alerting import send_alert
        send_alert("Archetype posteriors refresh failed", msg,
                   severity="ERROR", dedup_key="archetype_posteriors_refresh")


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
    # build removes it. Mirror tier (_run_mirror): HALT once serving reads S3 (a stale/partial S3
    # matrix = wrong served picks), but ALERT-loud-but-continue during the parallel window — when
    # serving still reads Snowflake the mirror is parity-only and must NOT red-line the predict op.
    if _w7b_mirror_on():
        _run_mirror(context, "export_features_to_s3.py")
    # E9.50 (was E9.9): the morning pre-lineup pick email is RETIRED — a pre-lineup row is
    # a preview (lineups unconfirmed), never actionable, so this run no longer passes
    # --notify. The sole pick alert is now the post-lineup digest fired from lineup_predict
    # (pipeline/ops/sensor_ops.py) once a game's lineup is confirmed.
    _run_script(
        context, "predict_today.py",
        ["--prediction-type", "morning"] + _w7b_s3_args(),
    )
    # Re-export predictions Snowflake→S3 AFTER scoring (predict_today still WRITES to Snowflake
    # in W7b-1) so the downstream write_serving_store_op --s3 + the request-path last-resort serve
    # TODAY's picks from S3 (the W6 daily_model_predictions freshness contract). Mirror tier.
    if _w7b_mirror_on():
        _run_mirror(context, "export_w6_raw_to_s3.py", ["--table", "daily_model_predictions"])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def generate_pick_narratives_op(context):
    # E9.13 — generate plain-English pick narrative text via Snowflake Cortex after
    # SHAP pick_explanation is written by predict_today. Runs for today's date only;
    # the script skips rows where pick_narrative is already populated (idempotent).
    # Soft-fail: a Cortex outage must not block write_serving_store_op — the app
    # renders SHAP drivers from pick_explanation when pick_narrative is NULL.
    #
    # INC-32 hardening (2026-07-19): this op is the ONLY step on the daily's predict→serve
    # dependency edge (write_serving_store_op / write_api_cache_op wait on predict_done=this),
    # and it loops calling Snowflake Cortex COMPLETE sequentially per game with NO client-side
    # timeout. The 7/19 daily verified CLEAN (Dagit --steps: this op ran 1.0 min, predict→serve
    # 4 min — the story's "2h stall" was a misread of a normal intraday serve), so this is NOT a
    # fix for an observed stall — it is defense-in-depth against the LATENT wedge: a hung/slow
    # Cortex call (warehouse queue, model backlog) would park this loop and, since the serve waits
    # on it, hold the serve hostage — the same un-timed-subprocess class as INC-32(A/B). A hard
    # wall-clock cap converts that unbounded risk into a bounded, LOUD degrade: the kill raises,
    # the soft-fail except catches it, and the serve proceeds on the last-good narratives (the
    # app already renders SHAP drivers when pick_narrative is NULL). 900s is far above a healthy
    # run (sequential Cortex ~1–3s/pick, pick-delta guard skips unchanged slates). The same op
    # also fronts the serve in lineup_monitor_job — this covers both.
    try:
        _run_script(context, "/app/betting_ml/scripts/generate_pick_narratives.py",
                    ["--date", _today(), "--pick-delta-guard"], timeout=900)
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


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def check_injury_status_health_op(context):
    """E9.48 injury / IL status guard — runs immediately after the injury chain rebuilds.

    THE OUTAGE IT PREVENTS (2026-07-29, P1 user-facing TRUST failure): player pages
    served a WRONG IL status for 62 of the 187 players flagged as currently on the
    Injured List — Jesús Luzardo read "On IL since 2024-06-19" while starting for PHI.
    An interval is CURRENT iff no later classified event exists, so ONE missed clearing
    event pins a player as injured forever, silently, across seasons. Nothing errored;
    nothing was empty; there was no way to notice except by asserting on the data.

    Two checks (pure logic in betting_ml/monitoring/injury_status_health.py):
      • FEED FRESHNESS  — the roster-transaction feed stopped advancing (every status
        frozen at that date). Also surfaces the structural Nov–Feb ingest hole.
      • IL PLAUSIBILITY — anyone flagged CURRENTLY on the IL who has played an MLB game
        since. This is the bug signature itself and reads no description text, so a
        Stats API rewording cannot blind it.

    Tier: ALERT-loud-but-continue. The IL badge is a profile adornment, not the serving
    path, so a stale feed must never HALT the daily job — but it must never pass
    silently either. INJURY_STATUS_STRICT=1 promotes to HALT.

    E11.30: the non-strict path used to only re-log the script's [METRIC] lines — a
    detection with no notification. It now pages via send_alert, but DISCRIMINATES between
    the two independent checks the script reports (see injury_status_health.py):
      - il_plausibility=IMPLAUSIBLE is the E9.48 bug signature itself (a player flagged
        CURRENTLY on the IL who has since played) — CRITICAL, always page.
      - il_plausibility=UNKNOWN (the chain produced zero current-IL rows, mid-season) — WARN.
      - feed_freshness=STALE/UNKNOWN ALONE (il_plausibility OK) does NOT page: the script's
        own docstring documents this as EXPECTED in the off-season (ingest_transactions'
        7-day lookback only runs from the in-season daily job, so Nov-Feb is a known,
        already-understood hole) — paging on it daily for ~4 months would be exactly the
        alert-fatigue failure mode this story warns against for a condition nobody would
        act on differently. It still logs loudly either way."""
    strict = os.environ.get("INJURY_STATUS_STRICT") == "1"
    try:
        # Bounded S3 read — a finite timeout so a stalled httpfs read can never park the
        # daily job on an advisory check (INC-32 class).
        stdout = _run_script(context, "check_injury_status_health.py", timeout=600)
    except Exception as e:
        if strict:
            raise
        context.log.warning(
            "[ALERT] check_injury_status_health flagged a stale or implausible IL status "
            f"(non-blocking; set INJURY_STATUS_STRICT=1 to HALT): {e}"
        )
        return
    metrics: dict[str, str] = {}
    for line in stdout.splitlines():
        if line.startswith("[METRIC] injury_status_"):
            key, _, val = line[len("[METRIC] "):].partition("=")
            metrics[key] = val.strip()
            (context.log.warning if val.strip() not in ("1", "OK") else context.log.info)(line.strip())
    if metrics.get("injury_status_ok") == "1":
        return
    il_status = metrics.get("injury_status_il_plausibility", "OK")
    severity = "CRITICAL" if il_status == "IMPLAUSIBLE" else ("WARN" if il_status == "UNKNOWN" else None)
    if severity is None:
        return  # feed_freshness-only failure — the documented off-season gap; log-only.
    from pipeline.utils.alerting import send_alert
    send_alert(
        "Injury/IL status check failed",
        f"feed_freshness={metrics.get('injury_status_feed_freshness')}, "
        f"il_plausibility={il_status}. See the Dagster step log (check_injury_status_health_op) "
        "for detail. IMPLAUSIBLE means a player flagged CURRENTLY on the IL has played an MLB "
        "game since (the E9.48 clearing/reconciliation logic is not being applied); UNKNOWN "
        "means the injury chain produced zero current-IL rows mid-season.",
        severity=severity,
        dedup_key="injury_status_health",
    )


# ── Player profile update (weekly) ───────────────────────────────────────────

@op(out=Out(Nothing))
def ingest_player_profiles_update(context):
    """Weekly update: fetch changed profiles via people/changes + detect new call-ups.
    E11.20 phase 1.5: under W7A_LAKEHOUSE_S3=1 the mart_pitch_play_event ID-universe scan
    reads from the S3 lakehouse (precondition for dropping the SF mart_pitch_* views)."""
    _run_script(context, "ingest_player_profiles.py", _w7a_s3_args() + ["update"])


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

    E11.20 phase-2a (W7b-2): the intraday path reads S3 when W7B_INTRADAY_S3=1 AND
    W6_LAKEHOUSE_INTRADAY=1 (see _w7b_intraday_serving_on). The W7b-1 blocker — "intraday feature
    freshness needs the W7b-2 DuckDB feature build" — is closed by lineup_intraday_s3_feature_rebuild
    (s2b, --w8b-only, enforced via LINEUP_INTRADAY_S3_REBUILD), which rebuilds the S3 W8b feature
    parquet upstream of predict. Default-OFF gate so merging is a no-op; instant rollback = unset the
    flag. See docs/w7b2_intraday_serving_s3_flip_design.md.
    """
    s3_args = _w7b_intraday_s3_args()
    if os.environ.get("W7B_INTRADAY_S3") == "1" and not s3_args:
        context.log.warning(
            "W7B_INTRADAY_S3=1 but W6_LAKEHOUSE_INTRADAY!=1 — intraday serving stays on Snowflake "
            "(the --book-odds --s3 read needs the W6 intraday odds rebuild, or it serves stale odds "
            "and clobbers write_book_odds_op). Set W6_LAKEHOUSE_INTRADAY=1 to complete the W7b-2 flip."
        )
    _run_script(context, "write_serving_store.py", ["--picks", "--game-detail", "--book-odds", *s3_args])


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def finalize_prior_slate_game_detail_op(context):
    """Re-write YESTERDAY's game-detail blobs so they land status='Final' with box scores.

    ROOT CAUSE this closes (found 2026-07-15): the model-vs-market "who called it" scorecards
    require the cached game-detail blob to be status='Final' with both scores, but NOTHING was
    re-writing a slate's game-detail blobs AFTER its games ended:

      • The intraday refresher `write_book_odds_op` runs on `odds_current_rebuild_sensor`, whose
        window CLOSES at the last game's first pitch (odds don't matter after that) — so the last
        game-detail write of the day catches every game still mid-`Live`, never `Final`.
      • The daily `write_serving_store_op` writes game-detail for TODAY only; it never revisits the
        completed slate.

    Net effect: game-detail blobs froze at 'Live'/'Preview', `build_scorecard_from_detail` returned
    None, and whole dates showed 0 model-vs-market scorecards (24 dates were only ever healed by
    manual backfills). This op is that backfill made a daily, once-post-game step: it runs in the
    morning daily job (~08:00 UTC / 05:00 PT), by which point every prior-day game — including the
    latest West-coast night game — is Final in the source. `--game-detail` alone re-resolves the
    slate's game_pks from predictions and re-assembles each blob (it does NOT touch picks/today or
    picks/ev, which guard on --picks); a Final blob with lineups is then permanentized by the writer.

    Targets `current_game_date() - 1` (the completed slate) — never today's in-progress slate. Uses
    the SAME `--s3` gating as write_serving_store_op (`_w7b_s3_args`) so it reads whichever backend
    production serves from. WARN-tier (post-game enrichment, per the failure-handling contract): a
    failure logs LOUD and the op still succeeds — finalizing historical scorecards must never HALT
    the daily serving path.
    """
    yesterday = _one_day_ago()
    try:
        _run_script(context, "write_serving_store.py",
                    ["--game-detail", "--date", yesterday, *_w7b_s3_args()])
    except Exception as exc:
        context.log.warning(
            f"finalize_prior_slate_game_detail_op failed for {yesterday} (non-fatal): {exc}")


# ── User bet settlement (Performance page redesign, story B1) ─────────────────

def _run_settlement(context) -> None:
    """Shared settlement body (WARN-tier). Runs settle_user_bets.py — now Snowflake-FREE
    (scores/K totals read from the S3 lakehouse via DuckDB). A failure is logged, never
    raised: settlement is off the critical prediction path, and the next pass (daily morning
    OR an evening settle_user_bets_job) retries. Soft-fail mirrors ingest_umpire_scorecards.
    """
    try:
        _run_script(context, "settle_user_bets.py")
    except Exception as e:
        context.log.warning(f"User-bet settlement failed (non-fatal, retried next pass): {e}")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def settle_user_bets_op(context):
    """Settle pending DynamoDB user-bets against final scores — the DAILY morning pass.

    Wired into daily_ingestion_job after dbt_daily_build. This is a leaf op
    (settle_user_bets_op(start=s16) — nothing downstream depends on it), so a settlement
    error must not flip the job to FAILURE. NOTE (E11.20 phase-2a): the morning pass ALONE
    left a whole slate's afternoon/evening finals unsettled for 12-24h — the evening
    settle_user_bets_job (settle_user_bets_scheduled_op) closes that gap.
    """
    _run_settlement(context)


@op(out=Out(Nothing))
def settle_user_bets_scheduled_op(context):
    """Standalone settle op for the EVENING settle_user_bets_job (E11.20 phase-2a).

    No `start` input, so it is the sole node of an evening-cadence job. Same WARN-tier body
    as the daily settle_user_bets_op. The once-daily morning pass left evening finals
    unsettled 12-24h; these evening passes settle same-night — and it is FREE now that the
    settle script is Snowflake-free (S3/DuckDB reads → no warehouse wake per pass).
    """
    _run_settlement(context)


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


# ── E5.5 — daily pitcher K-projection generation (the /props page) ─────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def write_pitcher_k_projections_op(context):
    """Score today's probable starters with the E5.2 K model and write the K-projection serving
    payloads (DynamoDB primary + S3 fallback) + daily index that power the /props page.

    WARN-tier (E11.7): peripheral/app-cosmetic transparency surface. A failure must never block
    predictions or the serving writes — the writer already exits 0 on any internal error, but we
    guard here too. Reads: probable pitchers (Snowflake, IDs) + the cached E5.2 feature frame +
    live K-prop lines (S3 DuckDB). Writes: pitcher_k_projection/* (DynamoDB + S3). Honest framing:
    projections only, best_alpha=0 — never a bet rec (E5.4 null).
    """
    try:
        _run_script(context, "write_pitcher_k_projections.py")
    except Exception as exc:  # noqa: BLE001
        context.log.warning(
            "WARNING: write_pitcher_k_projections_op failed (non-fatal — the /props page may be "
            f"stale for today; predictions and serving are unaffected): {exc}"
        )


# ── E5.1b — daily pitcher-strikeout prop catch-up (the /props surface) ─────────

# The ONLY player-prop market the app's Player Props page surfaces (E5.5 K-projection
# model-vs-book). write_pitcher_k_projections.py reads ONLY
# mlb/props/market=pitcher_strikeouts/, so the daily forward pull stays scoped to that one
# market even after E5.0 (2026-08-01) widened the LIVE host cron (below) to the phase-1 set
# (pitcher_strikeouts/outs, batter_total_bases/hits/home_runs, --regions us,eu) and E5.0b
# (same day) widened it again to batter_runs_scored/batter_rbis/batter_hits_runs_rbis — this
# op staying pitcher_strikeouts-only means enabling PROPS_DAILY_INGEST can only double-pay for
# pitcher_strikeouts (the pre-existing risk this op's docstring already warns about), never for
# any of the 7 markets E5.0/E5.0b added. Widen this constant only if this op itself is ever
# promoted off host-cron for the wider set — and if you do, retire the matching host-cron
# markets in the SAME change (never both for the same market — see the docstring below).
_PROPS_DAILY_MARKETS = "pitcher_strikeouts"


def _props_daily_ingest_on() -> bool:
    """E5.1b daily pitcher-strikeout prop forward catch-up. Default-OFF so the op is a
    safe no-op until the operator flips PROPS_DAILY_INGEST=1. The flag ALSO gates external
    paid Odds API spend, so it must not run implicitly."""
    return os.environ.get("PROPS_DAILY_INGEST") == "1"


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ingest_player_props_op(context):
    """Advance mlb/props/market=pitcher_strikeouts/ to yesterday (the Player Props page feed).

    WARN-tier (E11.7): peripheral / non-serving. Player props write STRAIGHT to S3
    (no Snowflake table, no dbt model) and are NOT on the predict/serving path — a
    failure here must never block predictions. Runs `backfill_multisport_props_to_s3.py
    --markets pitcher_strikeouts`, which is idempotent: existing (market, season, date) S3
    partitions auto-skip, so a daily run only pays credits for the new slate. Scoped to
    pitcher_strikeouts — the ONLY market the app's Player Props page consumes (E5.5
    K-projection); write_pitcher_k_projections_op downstream reads only that market.

    Source = Odds API *historical* events endpoint → the run inherently lands today-1
    (a date's props are not archived until it is in the past; today's live props are
    never available from this endpoint). Gated behind PROPS_DAILY_INGEST (default OFF)
    because it spends external paid API credits — a gated-off run logs a loud skip
    (ALERT tier) rather than silently no-op'ing.

    ⚠️ REDUNDANT with the ALREADY-ACTIVE host cron `services/dagster/aws/capture.crontab`
    (the `0 13 * * *` props line, re-enabled 2026-07-01 — verified firing: the 7/1 slate
    landed at 13:02 UTC on 7/2; E5.0 2026-08-01 widened that same line to the phase-1 market
    set — pitcher_strikeouts/outs, batter_total_bases/hits/home_runs — plus `--regions us,eu`
    for Pinnacle; E5.0b, same day, widened it again to add batter_runs_scored/batter_rbis/
    batter_hits_runs_rbis, the E13.14 cross-market RV probe substrate). This op is the
    Dagster-native ALTERNATIVE (observable in the run UI; a step toward retiring host-cron) —
    scoped to pitcher_strikeouts only, so it overlaps with just that one market of the host
    cron's now-wider set. Enable EXACTLY ONE PATH PER MARKET — running both for
    pitcher_strikeouts double-pays credits for the same idempotent pull. Default OFF ⇒ host
    cron stays the live mechanism for all of these markets.

    Writes: s3://baseball-betting-ml-artifacts/mlb/props/market=pitcher_strikeouts/season=<yr>/date=<d>/
    """
    if not _props_daily_ingest_on():
        context.log.warning(
            "WARNING: ingest_player_props_op skipped — PROPS_DAILY_INGEST != 1 (no-op; the "
            "mlb/props/ pitcher_strikeouts surface will NOT advance until the operator sets the flag)."
        )
        return
    try:
        _run_script(
            context,
            "backfill_multisport_props_to_s3.py",
            ["--mode", "backfill", "--sport", "baseball_mlb", "--markets", _PROPS_DAILY_MARKETS],
        )
    except Exception as exc:  # noqa: BLE001
        context.log.warning(
            "WARNING: ingest_player_props_op failed (non-fatal — the /props page K-prop lines may "
            f"lag by a day; predictions and serving are unaffected): {exc}"
        )
