import os
import subprocess
import sys

from dagster import In, Nothing, OpExecutionContext, Out, SkipReason, op

from betting_ml.utils.game_day import current_game_date_iso  # INC-22 — canonical US baseball-day
from pipeline.ops._dbt_exec import _run_dbt

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
    # E11.3 — propagate job name so script-level Snowflake sessions get tagged.
    env = {**os.environ, "DAGSTER_JOB_NAME": context.job_name}
    context.log.info(f"Running: {' '.join(cmd)} (timeout {timeout}s)")
    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=APP_DIR, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Exception(f"{os.path.basename(script)} exceeded {timeout}s hard timeout and was killed")
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        raise Exception(f"{os.path.basename(script)} failed (exit {result.returncode})\n{result.stderr}")


def _today() -> str:
    # INC-22 — the US baseball-day in the canonical TZ (LA), NOT the UTC box clock. These
    # ops fire INTRADAY (incl. evening, past 00:00 UTC) feeding --since/--start-date today
    # to the odds/schedule/weather refreshes; a UTC date.today() would resolve TOMORROW
    # after 00:00 UTC and export/capture an empty future date → stale served prices/lineups.
    return current_game_date_iso()


# ── E11.1-W6 INTRADAY lakehouse refresh ──────────────────────────────────────
# After W6 cutover, mart_odds_outcomes / mart_game_odds_bridge are VIEWS over S3-backed
# lakehouse_ext external tables, so the Snowflake `dbt run` below only rebuilds the VIEW (a
# no-op for data). Served PRICES now stay fresh only if the S3 parquet is rebuilt + the
# external table REFRESHed on the odds-capture cadence (the INC-16 odds-freshness failure if
# missed). This is gated behind W6_LAKEHOUSE_INTRADAY so it's a clean NO-OP until cutover (the
# external tables don't exist yet); the operator flips the env var to "1" AFTER creating the
# external tables + validating parity. ALERT-tier: a failure warns LOUD (stale prices must be
# visible) but does NOT crash the odds capture/rebuild op.
_W6_INTRADAY_ENABLED = os.environ.get("W6_LAKEHOUSE_INTRADAY", "0") == "1"


# ── INTRADAY schedule/game-state lakehouse refresh (Preview-stuck root-cause fix) ──
# ROOT CAUSE: ingest_statsapi.py writes monthly_schedule ONLY to native Snowflake (its
# writer was never S3-flipped). Prod stg_statsapi_games (abstract_game_state, game_date)
# reads the S3 lakehouse_ext external table — refreshed only by the once-daily
# run_w1_lakehouse_op (export monthly_schedule → rebuild → refresh). Crucially the daily
# op passes only --w6, which REGISTERS stg_statsapi_games as a view over existing parquet
# but does NOT rebuild that parquet (the W3pre flatten that owns it is opt-in, not passed).
# Net: game-state in the lakehouse lags ~a full ingest cycle, so yesterday's games stay in
# pre-game "Preview" through the evening — and the serving caches that bake those games read
# the stale snapshot (empty lineups / no Final → no permanent blob). The 30-min intraday
# schedule capture updates NATIVE + rebuilds the lineup VIEWS, but never re-exports
# monthly_schedule to S3 nor rebuilds the games flatten, so it can't fix this.
#
# FIX (this helper): after the native capture, run the proven daily chain scoped to the
# schedule tier — export today's monthly_schedule raw → S3, rebuild the W3pre flatten
# (--w3pre-only rebuilds stg_statsapi_games' output parquet from that raw), then refresh
# the external-table metadata so Snowflake serves the fresh game-state immediately.
#
# Gated OFF by default (clean no-op until the operator validates on the box) and ALERT-tier
# (warn LOUD but never crash the schedule capture) — mirroring _w6_lakehouse_intraday.
_SCHEDULE_INTRADAY_ENABLED = os.environ.get("SCHEDULE_LAKEHOUSE_INTRADAY", "0") == "1"


def _schedule_lakehouse_intraday(context: OpExecutionContext) -> None:
    """Refresh the S3 lakehouse game-state (stg_statsapi_games) from the just-captured native
    monthly_schedule snapshot, so prod stops serving a day-stale 'Preview' game-state.

    Sequence mirrors the daily run_w1_lakehouse_op for this tier, scoped to today's raw:
      export_odds_raw_to_s3.py --source monthly_schedule --since <today>   (native → S3 raw)
      run_w1_lakehouse.py --w3pre-only                                     (rebuild games flatten)
      refresh_w1_external_tables.py                                        (refresh ext-table metadata)
    """
    if not _SCHEDULE_INTRADAY_ENABLED:
        context.log.info(
            "Intraday schedule lakehouse refresh disabled "
            "(set SCHEDULE_LAKEHOUSE_INTRADAY=1 to enable) — skipping."
        )
        return
    try:
        today = _today()
        _run_script(context, "export_odds_raw_to_s3.py", ["--source", "monthly_schedule", "--since", today])
        _run_script(context, "run_w1_lakehouse.py", ["--w3pre-only"])
        _run_script(context, "refresh_w1_external_tables.py")
    except Exception as exc:  # ALERT-loud-but-continue — never crash the schedule capture op
        context.log.warning(
            f"⚠️ Intraday schedule lakehouse refresh FAILED — served game-state/lineups may be "
            f"STALE (games may show as pre-game 'Preview'): {exc}"
        )


def _w6_lakehouse_intraday(context: OpExecutionContext, scope: str) -> None:
    """scope='odds' — light current-odds path: export today's raw → run_w1_lakehouse
    --w6-odds-current (rewrite ONLY mart_odds_outcomes' _current bucket + bridge) → refresh
    --w6-odds (mart_odds_outcomes + mart_game_odds_bridge external tables).
    scope='clv'  — once/day post-game: export the daily_model_predictions mirror + today's raw
    → run_w1_lakehouse --w6 (full, incl. the post-hoc CLV/line-movement marts) → refresh
    --w6-clv (closing_line_value + prediction_clv + line_movement)."""
    today = _today()

    # ⭐ The RAW S3 odds mirror (lakehouse_raw/mlb_odds_raw) is mirror-tier and read 24/7 by the
    # odds_freshness sensor + the W3pre flatten. Export it UNGATED on every odds cycle so it can't
    # go stale when the 30-min host-cron `exec` is flaky (2026-07-03: the mirror stalled at 17:00
    # UTC while Snowflake raw was fresh to 22:00). Idempotent (overwrite_partition) — redundant with
    # the host cron but that redundancy is the point (belt + suspenders). ALERT-tier: never crash.
    try:
        _run_script(context, "export_odds_raw_to_s3.py", ["--source", "mlb_odds_raw", "--since", today])
    except Exception as exc:  # ALERT-loud-but-continue
        context.log.warning(
            f"⚠️ odds raw S3 mirror export FAILED — the 24/7 odds-freshness read may lag: {exc}"
        )

    # The S3 MART rebuild + external-table refresh is cutover-sensitive (it rewrites the served
    # mart_odds_outcomes parquet), so it stays gated behind W6_LAKEHOUSE_INTRADAY — a clean no-op
    # until cutover. The raw mirror above still refreshes regardless.
    if not _W6_INTRADAY_ENABLED:
        context.log.info(
            "W6 lakehouse intraday MART refresh disabled (set W6_LAKEHOUSE_INTRADAY=1 post-cutover) — "
            "raw mirror refreshed above; skipping the mart rebuild."
        )
        return
    try:
        if scope == "odds":
            _run_script(context, "run_w1_lakehouse.py", ["--w6-odds-current"])
            _run_script(context, "refresh_w1_external_tables.py", ["--w6-odds"])
        else:  # clv
            _run_script(context, "export_w6_raw_to_s3.py", ["--table", "daily_model_predictions"])
            _run_script(context, "run_w1_lakehouse.py", ["--w6"])
            _run_script(context, "refresh_w1_external_tables.py", ["--w6-clv"])
    except Exception as exc:  # ALERT-loud-but-continue — never crash the capture op
        context.log.warning(
            f"⚠️ W6 lakehouse intraday refresh ({scope}) FAILED — served odds/CLV may be STALE: {exc}"
        )


# ── Odds Snapshot ────────────────────────────────────────────────────────────

@op(out={"has_games": Out(bool)})
def check_games_today(context: OpExecutionContext) -> bool:
    """Check whether there are regular-season games today (gates the odds snapshot job).

    E11.1-W12 (INC-21 class): this read used the same `open(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"])`
    footgun as odds_current_rebuild_sensor — on the box the PATH env var is set unconditionally but
    the key file is only written when the inline SNOWFLAKE_PRIVATE_KEY is present, so a gap made this
    op fail. Now reads stg_statsapi_games from the S3 lakehouse via DuckDB (instance-role
    credential_chain — Snowflake-free)."""
    from betting_ml.utils.lakehouse_monitor import duck, lh

    conn = duck()
    try:
        (count,) = conn.execute(
            f"SELECT COUNT(*) FROM read_parquet('{lh('stg_statsapi_games')}', union_by_name=true) "
            f"WHERE official_date = ? AND game_type = 'R'",
            [_today()],  # INC-22 — US baseball-day (LA), not the UTC box clock
        ).fetchone()
    finally:
        conn.close()

    has_games = count > 0
    if has_games:
        context.log.info(f"Found {count} regular-season game(s) today — proceeding with odds snapshot.")
    else:
        context.log.info("No regular-season games today — odds snapshot will be skipped.")
    return has_games


# E11.1-W11-E: the parlay-based intraday odds ops (odds_snapshot_ingest → parlay_api_ingestion.py
# events/odds/line-movement; odds_snapshot_dbt_rebuild → stg_parlayapi_odds) were already UNWIRED
# (no @job referenced them — the Odds-API odds_current_rebuild path superseded them at the E11.6
# Parlay decommission). Deleted here with the parlay_api ingestion + stg_parlayapi_* models.


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
    # E11.1-W6: post-cutover, the dbt run above only rebuilds the Snowflake VIEW — the real
    # served-price freshness comes from the S3 today-partition rebuild + external-table REFRESH.
    _w6_lakehouse_intraday(context, scope="odds")


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
    # E11.1-W6: post-cutover these are VIEWS — rebuild the S3 parquet (full --w6, incl. the
    # post-hoc CLV/line-movement marts on the complete day) + REFRESH the CLV external tables.
    _w6_lakehouse_intraday(context, scope="clv")


# ── Book-odds serving store refresh ─────────────────────────────────────────

@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def write_book_odds_op(context: OpExecutionContext) -> None:
    """Refresh the served per-book odds AND the game-detail blobs after each mart rebuild.

    Runs write_serving_store.py --book-odds --game-detail standalone — the script resolves
    today's game_pks directly from daily_model_predictions when --picks is not also passed
    (picks_rows are fetched whenever --game-detail is set).

    ⭐ --game-detail is REQUIRED here (added 2026-07-03): the "Line Movement Over Time" chart
    (`line_movement_series`) is produced ONLY by the game-detail serving write, which otherwise
    runs just once/day in the daily job — so the served chart froze at the morning serve (~7:30
    AM) while raw odds kept flowing. Re-writing the game-detail blob on the intraday odds cadence
    (this op fires per odds_current_rebuild cycle) extends the chart through the day. It re-reads
    mart_odds_outcomes (rebuilt by odds_current_dbt_rebuild just upstream) so the fresh snapshots
    land; predictions are unchanged (pre-lineup), only the odds/line-movement fields refresh.
    Failures are non-fatal (logged, not re-raised) so a serving-store outage doesn't kill the
    odds rebuild job.
    """
    try:
        _run_script(context, "write_serving_store.py", ["--book-odds", "--game-detail"])
    except Exception as exc:
        context.log.warning(f"write_book_odds_op failed (non-fatal): {exc}")


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
    # ⭐ E11.1-W11 Tier-C — the hourly all-slate-park weather TIME-SERIES (E13.16 precursor). S3-only,
    # captured_at-tagged; mirror-tier ALERT-continue so a series failure never kills the capture op.
    # (The live hourly path is the host-cron weather-capture container's entrypoint; this op mirrors it
    # for Dagster manual re-runs.)
    try:
        _run_script(context, "ingest_weather.py", ["--observation-type", "intraday_series"])
    except Exception as e:
        context.log.warning(f"Intraday weather-series capture failed (non-fatal): {e}")


# ── Intraday Public Betting (E11.1-W11-D addendum) ───────────────────────────

@op(out=Out(Nothing))
def intraday_public_betting_capture(context: OpExecutionContext) -> None:
    """Hourly ActionNetwork public-betting capture across the pre-game window (W11-D addendum).

    Builds a public-% time-series aligned to the odds line trajectory so E13.16 can later test whether
    the line moves AGAINST the public % (reverse line movement / sharp-money divergence). Each hourly
    run appends a distinct-captured_at snapshot to BOTH the migration raw mirror (public_betting_raw,
    which the SCD-2 chain turns into an intraday shift) AND the dedicated append-only trajectory
    (public_betting_intraday_series) — nothing is collapsed, so every hour is kept for the game-day.

    Requires the S3 write leg (W11_RAW_WRITE_MODE=s3|both) for the mirror/series to be written; with the
    default 'snowflake' the run just re-inserts the SF row (harmless) and warns the series was skipped.
    ALERT-loud-but-continue: a capture miss must never crash — the trajectory tolerates a dropped hour
    (dedup + the append model absorb it), and this is a supplemental signal, not a serving input.

    Cadence note (probed 2026-07-01): the AN publicbetting endpoint carries no explicit updated_at; its
    per-game `num_bets` counter increments continuously (a freshness proxy). Hourly is a safe default —
    if AN refreshes ~hourly this aligns; slower is harmless (the snapshot repeats, dedup handles it);
    faster just means we sample the trajectory hourly (aliasing noted, still a fine starting resolution).
    """
    try:
        _run_script(context, "ingest_actionnetwork_betting.py",
                    ["--date", _today(), "--intraday-series"], timeout=_POLL_TIMEOUT)
    except Exception as e:  # noqa: BLE001 — supplemental signal; a missed hour must not crash the op
        context.log.warning(f"intraday public-betting capture failed (non-fatal): {e}")


# ── Intraday Schedule ────────────────────────────────────────────────────────

@op(out=Out(Nothing))
def intraday_schedule_capture(context: OpExecutionContext) -> None:
    _run_script(context, "ingest_statsapi.py", [
        "schedule",
        "--start-date", _today(),
        "--end-date", _today(),
        "--capture-reason", "intraday_gameday",
    ])
    # Propagate the freshly-captured native snapshot to the S3 lakehouse so prod's
    # game-state (stg_statsapi_games) stops lagging a full ingest cycle behind native —
    # the Preview-stuck root cause. Gated/ALERT-tier no-op until the operator enables it.
    _schedule_lakehouse_intraday(context)


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
