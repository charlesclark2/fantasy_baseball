import os
import subprocess
import sys

from dagster import In, Nothing, OpExecutionContext, Out, SkipReason, op

from betting_ml.monitoring.alert_text import exc_digest  # INC-42 — page the TAIL, not the head
from betting_ml.monitoring.intraday_tick_budget import (  # E11.26 — cadence-derived tick budget
    LEG_TIMEOUT_SECONDS as _TICK_LEG_TIMEOUT,
)
from betting_ml.utils.bounded_subprocess import run_bounded  # E11.26 — kills the process GROUP
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
        # E11.26 — run_bounded, not subprocess.run: it starts the child in its OWN process group
        # and kills the GROUP on expiry (and on a Dagster run-monitoring termination, which the
        # new `dagster/max_runtime` ceiling makes a routine path). subprocess.run kills only the
        # direct child, so an orphaned grandchild kept burning one of the box's two vCPUs — a
        # pinned box starves the Dagster daemon, which is the compounding half of INC-32.
        result = run_bounded(cmd, env=env, cwd=APP_DIR, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # INC-42 — the diagnosis is at the TAIL of the child's output, so surface it rather than
        # raising a bare "it timed out" that pages identically for every cause.
        tail = ((exc.stdout or "") + (exc.stderr or ""))[-2000:]
        raise Exception(
            f"{os.path.basename(script)} exceeded {timeout}s hard timeout and its process group "
            f"was KILLED (E11.26 tick budget)\n(output tail)\n{tail}"
        ) from exc
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


def _tick_sf_free() -> bool:
    """E11.20 phase-2a STEP 3 gate (default-OFF): retire the 30-min capture tick's two
    Snowflake legs — `intraday_lineup_rebuild` (dbt SF staging rebuild) and the trailing
    `refresh_w1_external_tables.py` in `_schedule_lakehouse_intraday`.

    REQUIRES `SCHEDULE_LAKEHOUSE_INTRADAY=1`: that is what runs the `--w7b-only` S3 rebuild
    (+ the W7B_SERVING ext refresh) that keeps `stg_statsapi_lineups_wide`/`_probable_pitchers`
    fresh in the S3 parquet — the thing the lineup monitor (LINEUP_MONITOR_S3=1) and the `--s3`
    serving/predict (W7b-2) read INSTEAD of the SF tables. Dropping the dbt rebuild WITHOUT that
    S3 rebuild would leave lineups stale on both paths → the monitor goes blind (post_lineup never
    fires). So this returns False (KEEP the SF legs) unless BOTH flags are set — read fresh from the
    env (not a module constant) so a box env flip takes effect on code reload without an import edit.

    NOTE this flag owns ONLY the refresh + dbt legs. The capture INSERT + the export bridge are
    retired by the monthly_schedule writer flip (W11_RAW_WRITE_MODE), which is order-coupled to its
    own bridge retirement (INC-31). The tick is fully Snowflake-free only when BOTH flips are done.
    """
    return (os.environ.get("TICK_SF_FREE") == "1"
            and os.environ.get("SCHEDULE_LAKEHOUSE_INTRADAY") == "1")


def _w6_odds_sf_free() -> bool:
    """E11.20 phase-2b gate (default-OFF): retire the INTRADAY odds tick's two Snowflake
    legs — the `dbt run` SF VIEW rebuild (`stg_oddsapi_odds` + `mart_odds_outcomes`) in
    `odds_current_dbt_rebuild`, and the trailing `refresh_w1_external_tables.py --w6-odds`
    in `_w6_lakehouse_intraday(scope='odds')`. Both keep the Snowflake `lakehouse_ext`/
    `betting.*` views of mart_odds_outcomes + mart_game_odds_bridge fresh — a per-tick
    warehouse WAKE (~12-14 fires/game-day, the measured phase-2b lever).

    REQUIRES `W6_LAKEHOUSE_INTRADAY=1`: that is what runs `run_w1_lakehouse.py
    --w6-odds-current` (the DuckDB/S3 parquet rebuild of mart_odds_outcomes' _current bucket
    + mart_game_odds_bridge) — the read source the --s3 predict/serving (W7B_*) and the
    backend `lakehouse_query` actually use. Retiring the SF legs WITHOUT that S3 rebuild
    would leave served odds STALE on every path, so this returns False (KEEP the SF legs)
    unless BOTH flags are set. Read fresh from env (not a module constant) so a box flip
    takes effect on reload.

    Consumer audit (2026-07-26): the ONLY intraday readers of these two marts —
    /app/scripts/predict_today.py (its `--s3` aux/Bovada odds reads route through DuckDB),
    write_serving_store.py --book-odds --s3, and app/backend/routers/picks.py
    (`lakehouse_query`) — read the S3 parquet, NOT the SF views/ext tables. The remaining
    SF readers (check_odds_coverage_op + the 2 dbt feature models that `ref` these marts)
    run in the DAILY build, kept fresh by the daily lakehouse_spine_odds_bridge_op /
    refresh_w1_external_tables_op — so INTRADAY freshness of the SF views buys nothing. The
    SF-only predict twin (betting_ml/scripts/predict_today.py) is invoked only by the
    deprecated Streamlit UI, not the pipeline. This flag owns ONLY the intraday odds path;
    the once/day CLV path (odds_clv_dbt_rebuild) keeps its SF legs (1 fire/day, low wake,
    feeds the daily-run CLV SF consumers).
    """
    return (os.environ.get("W6_ODDS_SF_FREE") == "1"
            and os.environ.get("W6_LAKEHOUSE_INTRADAY") == "1")


def _schedule_lakehouse_intraday(context: OpExecutionContext) -> None:
    """Refresh the S3 lakehouse game-state (stg_statsapi_games) AND the wide lineup table
    (stg_statsapi_lineups_wide) from the just-captured native monthly_schedule snapshot, so prod
    stops serving a day-stale 'Preview' game-state and TODAY's confirmed lineups are actually seen.

    Sequence mirrors the daily run_w1_lakehouse_op for this tier, scoped to today's raw:
      run_w1_lakehouse.py --w3pre-only                                     (rebuild games flatten)
      run_w1_lakehouse.py --w7b-only                                       (rebuild lineups_wide etc.)
      refresh_w1_external_tables.py                                        (refresh ext-table metadata)

    E11.20 phase-2a (2026-07-24, bridge retirement): the old first leg
    `export_odds_raw_to_s3.py --source monthly_schedule --since <today>` is RETIRED. Since the
    monthly_schedule writer flipped S3-native (W11_RAW_WRITE_MODE=s3), intraday_schedule_capture's
    own `ingest_statsapi.py schedule` call (which runs BEFORE this helper) already writes today's
    monthly_schedule raw to S3 — so the export bridge was a redundant SECOND writer of the same key
    (INC-31 clobber shape) AND a per-tick Snowflake READ of the now-frozen SF table (a warehouse
    wake). Dropping it makes the writer the sole S3 author and removes one tick SF touch; the
    --w3pre/--w7b rebuilds below read the S3 raw the writer just wrote.

    INC-31 (2026-07-10) — WHY --w7b-only is here: the S3 stg_statsapi_lineups_wide parquet is
    otherwise rebuilt ONLY by the once-daily (morning) run, but a slate's lineups post through the
    afternoon/evening. Everything downstream reads that parquet — lineup_monitor.py detects confirmed
    lineups via betting.stg_statsapi_lineups_wide (→ lakehouse_ext → this parquet), and the --s3
    serving reads (write_serving_store / picks.py) build the pick-detail lineup card from it. So a
    stale parquet makes the lineup monitor BLIND to today's confirmations (post_lineup predict never
    fires) AND leaves the pick-detail lineup card empty for the whole live slate. Rebuilding it on the
    same intraday cadence as the games flatten — UPSTREAM of the lineup monitor's read — closes both.
    The refresh below must cover stg_statsapi_lineups_wide so the SF view the monitor reads reflects it.
    ⚠️ COST/fast-follow: --w7b-only rebuilds the whole W7b mini-wave (injury chain + probable_pitchers
    + lineups_wide), reusing the existing W2/W4/W6 parquet (light, but not lineups-only). A scoped
    --w7b-lineups-only build is the fast-follow if the per-tick cost matters.
    """
    if not _SCHEDULE_INTRADAY_ENABLED:
        context.log.info(
            "Intraday schedule lakehouse refresh disabled "
            "(set SCHEDULE_LAKEHOUSE_INTRADAY=1 to enable) — skipping."
        )
        return
    # INC-41 (2026-08-06) — THE TWO REBUILDS ARE INDEPENDENT AND MUST FAIL INDEPENDENTLY.
    # They used to share one try block, so when --w3pre-only raised (a vendor INT32_MIN odds price
    # overflowing abs() in stg_oddsapi_odds) the very next line NEVER RAN: --w7b-only was not
    # attempted at all, the lineups parquet froze at 20:08Z, and the lineup monitor reported "No
    # newly confirmed lineups" for 6.5h while three games went unscored past first pitch. An
    # ODDS-flatten failure has no business stopping the LINEUPS rebuild — they read different raw
    # feeds and serve different consumers. Each leg now gets its own try/except so one poisoned
    # vendor price can cost at most its own table.
    _legs_failed: list[tuple[str, str]] = []
    for _flag, _what in (("--w3pre-only", "game-state + odds flatten"),
                         ("--w7b-only", "lineups_wide / probable_pitchers")):
        try:
            _run_script(context, "run_w1_lakehouse.py", [_flag], timeout=_TICK_LEG_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 — ALERT-loud-but-continue, per leg
            # INC-42 — ⛔ NOT `str(exc)[:300]`. `_run_script` raises with the child's ENTIRE
            # traceback, whose payload (the exception type + message) is at the TAIL, so a head
            # slice keeps the frames and drops the diagnosis — every cause paged identically.
            _legs_failed.append((_flag, exc_digest(exc)))
            context.log.warning(f"⚠️ {_flag} ({_what}) FAILED — continuing to the next leg: {exc}")

    try:
        # E11.20 phase-2a step 3: the trailing SF ext-table REFRESH is retired under TICK_SF_FREE.
        # It refreshes a broad set, but the tick only REBUILT games/lineups (--w3pre/--w7b above) —
        # every other group is a data no-op re-listing (rebuilt by the DAILY run, not the tick). So
        # skipping it only stops the games/lineups SF ext tables updating intraday, and post-W7b-2 +
        # LINEUP_MONITOR_S3=1 nothing reads those intraday (they lag to the daily refresh). The S3
        # parquet built above is what the monitor + --s3 serving actually read.
        if _tick_sf_free():
            context.log.info(
                "[TICK_SF_FREE] skipping refresh_w1_external_tables — no game-hours consumer reads "
                "the SF ext tables intraday post-W7b-2; the --w3pre/--w7b S3 parquet is the read source."
            )
        else:
            _run_script(context, "refresh_w1_external_tables.py", timeout=_TICK_LEG_TIMEOUT)
    except Exception as exc:  # ALERT-loud-but-continue — never crash the schedule capture op
        _legs_failed.append(("refresh_w1_external_tables", exc_digest(exc)))  # INC-42 (tail, not head)
        context.log.warning(f"⚠️ external-table refresh FAILED: {exc}")

    # INC-41 — ALERT-TIER MUST ACTUALLY PAGE (the E11.30 finding, still live in this op).
    # This warning text has predicted the outage verbatim since it was written — "the lineup
    # monitor may miss today's confirmed lineups" — and on 2026-08-06 it printed every 30 minutes
    # for 6.5 hours into a step log nobody was watching, while the job reported SUCCESS. A tier
    # label enforced only by a comment is not enforced at all. Page on it.
    if _legs_failed:
        _detail = "; ".join(f"{leg}: {err}" for leg, err in _legs_failed)
        context.log.warning(
            f"⚠️ Intraday schedule lakehouse refresh FAILED — served game-state/lineups are now "
            f"STALE (games may show as pre-game 'Preview', or the lineup monitor may miss today's "
            f"confirmed lineups): {_detail}"
        )
        try:
            from pipeline.utils.alerting import send_alert
            send_alert(
                subject="Intraday lakehouse refresh FAILED — lineups/game-state going stale",
                message=(
                    "run_w1_lakehouse intraday leg(s) failed, so the S3 parquet the lineup monitor "
                    "and --s3 serving read is FROZEN at its last good build.\n\n"
                    "Consequence if unfixed: the lineup monitor sees no newly confirmed lineups, so "
                    "post_lineup predictions silently stop for the rest of the slate (INC-41, "
                    "2026-08-06: 3 games unscored past first pitch, 6.5h, no page).\n\n"
                    f"Failing leg(s): {_detail}"
                ),
                severity="CRITICAL",
                dedup_key="intraday_lakehouse_refresh_failed",
            )
        except Exception as alert_exc:  # noqa: BLE001 — paging must never crash the capture op
            context.log.warning(f"send_alert failed for intraday lakehouse refresh: {alert_exc}")


def _w6_lakehouse_intraday(context: OpExecutionContext, scope: str) -> None:
    """scope='odds' — light current-odds path: export today's raw → run_w1_lakehouse
    --w6-odds-current (rewrite ONLY mart_odds_outcomes' _current bucket + bridge) → refresh
    --w6-odds (mart_odds_outcomes + mart_game_odds_bridge external tables).
    scope='clv'  — once/day post-game: export the daily_model_predictions mirror + today's raw
    → run_w1_lakehouse --w6 (full, incl. the post-hoc CLV/line-movement marts) → refresh
    --w6-clv (closing_line_value + prediction_clv + line_movement)."""
    today = _today()

    # ⛔ THE RAW mlb_odds_raw MIRROR EXPORT IS RETIRED (E11.20 phase-2b, 2026-07-27).
    #
    # It used to run `export_odds_raw_to_s3.py --source mlb_odds_raw --since <today>` UNGATED on
    # every odds cycle as a belt-and-suspenders backstop for the 30-min host cron. That rationale
    # died on 2026-07-05, when odds capture flipped S3-NATIVE and the Snowflake write was dropped:
    # `baseball_data.oddsapi.mlb_odds_raw` has been FROZEN at ingestion_ts 2026-07-05T23:00:14 ever
    # since (verified: 0 rows with ingestion_ts::date >= today). The host cron was retired then for
    # exactly this reason (capture.crontab line 35 is commented out) — this op call was missed.
    #
    # What it actually did every tick: `SELECT DISTINCT ingestion_ts::date FROM …mlb_odds_raw WHERE
    # ingestion_ts::date >= '<today>'` returned ZERO rows, so the export loop never executed and
    # nothing was written. A pure COMPUTE_WH WAKE accomplishing nothing — ~10-14 per game-day
    # (observed 2026-07-27 at 15:35, 16:05, 17:05, 18:06, 19:06, 20:06, 21:07, 22:07 …). It is one
    # of the wakes that SURVIVED the W6 flip, because W6 retired the two mart legs, not this bridge.
    #
    # The S3-native capture is the sole writer and is healthy: lakehouse_raw/mlb_odds_raw/
    # dt=2026-07-27 carried 46 part-files with the newest at 22:30:09Z, a ~30-min cadence.
    # Removing this call changes NO data — it only stops waking the warehouse.
    context.log.info(
        "[E11.20 phase-2b] mlb_odds_raw export bridge RETIRED — odds capture is S3-native and its "
        "Snowflake table has been frozen since 2026-07-05; the export was a no-op warehouse wake."
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
            # E11.20 phase-2b: the trailing SF ext-table REFRESH is retired under
            # W6_ODDS_SF_FREE — nothing reads the mart_odds_outcomes / mart_game_odds_bridge
            # SF ext tables intraday (all intraday consumers read the --w6-odds-current S3
            # parquet above). The DAILY lakehouse_spine_odds_bridge_op /
            # refresh_w1_external_tables_op still refresh these ext tables for the daily SF
            # readers (check_odds_coverage_op + the 2 dbt feature models). Gated (else-run),
            # not removed, so pre-flip boxes that still read SF stay fresh.
            if _w6_odds_sf_free():
                context.log.info(
                    "[W6_ODDS_SF_FREE] skipping refresh_w1_external_tables --w6-odds — no "
                    "game-hours consumer reads the SF odds ext tables intraday; the "
                    "--w6-odds-current S3 parquet is the read source."
                )
            else:
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
    # E11.20 phase-2b (W6_ODDS_SF_FREE): post-cutover this dbt run only rebuilds the Snowflake
    # VIEW definition (a data no-op — the view is stable between deploys, and the DAILY build
    # rebuilds it when a deploy changes it). No game-hours consumer reads the SF views intraday
    # (all --s3), so retire this per-tick warehouse wake. Gated, not removed — inert + LOUD if
    # W6_ODDS_SF_FREE is set WITHOUT W6_LAKEHOUSE_INTRADAY (then the --w6-odds-current S3 rebuild
    # below is off, so the SF legs are NOT safe to drop → fall back to running the rebuild).
    if _w6_odds_sf_free():
        context.log.info(
            "[W6_ODDS_SF_FREE] skipping the intraday `dbt run stg_oddsapi_odds mart_odds_outcomes` "
            "SF view rebuild — no game-hours consumer reads the SF views intraday; the "
            "--w6-odds-current S3 parquet (below) is the read source."
        )
    else:
        if os.environ.get("W6_ODDS_SF_FREE") == "1":
            context.log.warning(
                "⚠️ W6_ODDS_SF_FREE=1 but W6_LAKEHOUSE_INTRADAY is OFF — NOT retiring the SF odds "
                "legs (the --w6-odds-current S3 rebuild is what makes them safe to drop); running "
                "the dbt view rebuild as before to avoid stale served odds."
            )
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

    E11.20-COST (2026-07-16): append --s3 when BOTH W7B_LAKEHOUSE_S3 (the serving read cutover,
    same flag the daily write_serving_store_op keys on) AND W6_LAKEHOUSE_INTRADAY (the intraday
    S3 mart_odds_outcomes rebuild, run just upstream in this same job) are on. Without --s3 this
    op read Snowflake on EVERY odds cycle through game hours (~15 warehouse-waking sessions/day
    of probable-pitcher/game-detail SELECTs, measured 72–85 30-min buckets/wk). Both flags
    required: --s3 with the intraday S3 rebuild OFF would re-freeze the line-movement chart at
    the morning serve — the exact regression the 2026-07-03 --game-detail fix cured. The --s3
    read path itself is the daily-proven one (INC-23 audited).
    """
    args = ["--book-odds", "--game-detail"]
    if os.environ.get("W7B_LAKEHOUSE_S3", "0") == "1" and _W6_INTRADAY_ENABLED:
        args.append("--s3")
    try:
        _run_script(context, "write_serving_store.py", args)
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
    """E11.7 tier: **HALT** for the schedule ingest, **ALERT-loud-but-continue** for the lakehouse
    legs it fans into (`_schedule_lakehouse_intraday`) — the split INC-37 and INC-41 established.

    E11.26 — every leg is capped at the cadence-derived `LEG_TIMEOUT_SECONDS`, not the module's
    1800s default (which IS this job's own 30-minute cadence, so it bounded nothing useful). A
    timeout is a CLEAN LOUD FAILURE in both tiers, never a swallow:
      * the ingest leg raises out of the op → the job fails → `run_failure_alert_sensor` pages
        (⚠️ at **ERROR**, not CRITICAL: that sensor monitors every job but reserves CRITICAL for the
        four names in its `_HALT_TIER_JOBS` set, and `intraday_schedule_job` is deliberately not one
        of them. The HALT tier is about this OP's behaviour — it raises rather than swallowing — not
        about the page's severity. ERROR is the right level for a 30-minute tick: a single missed
        capture is not slate-fatal because the next tick is 30 minutes away, and the slate-fatal
        version of this failure is `ingest_statsapi_schedule` inside the DAILY job, which INC-37
        moved to `s6` and which IS in `_HALT_TIER_JOBS`);
      * a rebuild leg's timeout is caught per-leg, recorded in `_legs_failed`, and paged CRITICAL
        through the INC-41 `send_alert` path — the OTHER leg still runs, which is the independence
        INC-41 exists to preserve and which a run-level termination would destroy.
    """
    # INC-37 — --lookahead-days 3: run_schedule iterates WHOLE months, so on the last day of a
    # month `--end-date today` fetches ONLY that month and the captured blob holds ZERO games for
    # the 1st of the next month. The daily lakehouse build then flattens a schedule that stops at
    # the month boundary and the entire next-day slate loses every pregame feature block
    # (observed 2026-06-01, 07-01 and 08-01). The lookahead makes the last few captures of every
    # month also fetch the next month, so the hole cannot open.
    #
    # INC-38 — --lookback-days 3, the mirror. This tick is the caller that MOST needs it: the
    # daily op has passed `--start-date <yesterday>` since 2026-07-15, but the S3 raw writer
    # replaces the whole dt=<fire date> partition with only the months ITS fire pulled, so this
    # month-only tick running minutes later CLOBBERED the daily's wider fetch — which is why the
    # 07-15 cure never actually held. Without the lookback nothing revisits a month after the 1st,
    # so a game that first-pitches after 00:00 UTC on the 1st never gets its Final + score written
    # and every user bet on it sits PENDING forever (INC-38: 14 of 15 games frozen on 07-31).
    _run_script(context, "ingest_statsapi.py", [
        "schedule",
        "--start-date", _today(),
        "--end-date", _today(),
        "--lookahead-days", "3",
        "--lookback-days", "3",
        "--capture-reason", "intraday_gameday",
    ], timeout=_TICK_LEG_TIMEOUT)
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

    E11.20 phase-2a step 3 (TICK_SF_FREE): once the lineup monitor reads the S3 parquet
    (LINEUP_MONITOR_S3=1) and the intraday serving/predict read S3 (W7b-2), NO intraday
    consumer reads these SF staging tables — the S3 parquet (kept fresh by the --w7b build
    in _schedule_lakehouse_intraday) is the read source — so this SF dbt rebuild is retired.
    """
    if _tick_sf_free():
        context.log.warning(
            "⚠️ [TICK_SF_FREE] intraday_lineup_rebuild SKIPPED — the SF staging dbt rebuild is "
            "retired (E11.20 phase-2a step 3). The S3 stg_statsapi_lineups_wide/_probable_pitchers "
            "parquet (built by _schedule_lakehouse_intraday --w7b-only) is the intraday read source "
            "for the lineup monitor (LINEUP_MONITOR_S3) + the --s3 serving/predict (W7b-2)."
        )
        return
    if os.environ.get("TICK_SF_FREE") == "1":
        # Flag set but the S3 rebuild that REPLACES this leg isn't running — do NOT retire, or the
        # monitor goes blind. Loud so the misconfig is visible (the flag looks on but is inert).
        context.log.warning(
            "⚠️ TICK_SF_FREE=1 but SCHEDULE_LAKEHOUSE_INTRADAY is OFF — NOT retiring the SF lineup "
            "rebuild (the --w7b S3 rebuild that would replace it isn't running). Set "
            "SCHEDULE_LAKEHOUSE_INTRADAY=1 first. Running the SF dbt rebuild as a safe fallback."
        )
    _run_dbt(context, [
        "run",
        "--select",
        "stg_statsapi_lineups",
        "stg_statsapi_lineups_wide",
        "stg_statsapi_probable_pitchers",
        "--target", "baseball_betting_and_fantasy",
    ], timeout=_TICK_LEG_TIMEOUT)
