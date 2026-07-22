"""E11.20-COST wake-kill guards (2026-07-16).

MEASURED PROBLEM: ~80% of Snowflake spend (≈3.7 of ~4.5 credits/day) was warehouse
resume-minimums/idle tails from 24/7 tick chains, not query compute — the warehouse was
awake in all 24 hours of every day, including All-Star-break days with zero games
(2.4–2.7 credits/day of pure drip). The three cures these tests pin:

1. The lineup monitor's SF-querying subprocess is HORIZON-GATED — skipped entirely
   (no Snowflake session) when no Preview game is within _MONITOR_HORIZON. Previously
   the sensor idle path ran it hourly 24/7 and the cron backstop ran it 28×/day
   unconditionally (273/336 30-min buckets/wk touched).
2. The host-cron schedule-capture line stays DISABLED — the Dagster
   intraday_schedule_capture_* schedules are the sole owner (the INC-22 Option-2
   step-3 double-fire burned a duplicate SF INSERT + 3-model dbt rebuild every 30 min,
   288/336 buckets/wk, plus INC-30-class dbt-runner 409 contention).
3. write_book_odds_op reads S3 (--s3) instead of Snowflake on the intraday odds cadence
   when BOTH W7B_LAKEHOUSE_S3 and W6_LAKEHOUSE_INTRADAY are on — and NEVER --s3 with the
   intraday S3 mart rebuild off (that would re-freeze the line-movement chart at the
   morning serve, the regression the 2026-07-03 --game-detail fix cured).

Source-inspection throughout: fast-gate tests must not import `pipeline` (its __init__
reads the dbt manifest, absent in the fast gate).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SENSOR = (REPO / "pipeline" / "sensors" / "lineup_monitor_sensor.py").read_text()
INTRADAY = (REPO / "pipeline" / "ops" / "intraday_ops.py").read_text()
CRONTAB = (REPO / "services" / "dagster" / "aws" / "capture.crontab").read_text()
DAILY_OPS = (REPO / "pipeline" / "ops" / "daily_ingestion_ops.py").read_text()
SENSOR_OPS = (REPO / "pipeline" / "ops" / "sensor_ops.py").read_text()


class TestLineupMonitorHorizonGate:
    def test_horizon_constant_and_helper_exist(self):
        assert "_MONITOR_HORIZON" in SENSOR and "_beyond_monitor_horizon" in SENSOR, (
            "the lineup-monitor horizon gate is gone — the SF-querying subprocess would "
            "run 24/7 again (~50 warehouse-waking sessions/day, incl. no-game days)."
        )

    def test_sensor_gates_before_running_the_monitor(self):
        sensor_body = SENSOR[SENSOR.find("def lineup_monitor_sensor"):SENSOR.find("def _evaluate_lineup_monitor")]
        gate = sensor_body.find("_beyond_monitor_horizon")
        run = sensor_body.find("_evaluate_lineup_monitor(")
        assert gate != -1 and run != -1 and gate < run, (
            "lineup_monitor_sensor must apply the horizon gate BEFORE invoking the "
            "monitor subprocess — the idle path used to run it hourly around the clock."
        )

    def test_schedule_backstop_carries_the_same_gate(self):
        body = SENSOR[SENSOR.find("def _lineup_schedule_body"):SENSOR.find("@schedule")]
        assert "_beyond_monitor_horizon" in body and "_minutes_to_next_first_pitch" in body, (
            "_lineup_schedule_body lost the horizon gate — the 28×/day cron backstop "
            "would run the SF monitor unconditionally again (break days included)."
        )

    def test_gate_fails_open_on_lookup_error(self):
        body = SENSOR[SENSOR.find("def _lineup_schedule_body"):SENSOR.find("@schedule")]
        assert re.search(r"except Exception.*\n.*running monitor anyway", body), (
            "the schedule-body slate lookup must fail OPEN (run the monitor) — a flaky "
            "parquet read must never make the lineup monitor go dark near first pitch."
        )

    def test_skip_semantics_no_games_and_beyond_horizon(self):
        helper = SENSOR[SENSOR.find("def _beyond_monitor_horizon"):SENSOR.find("@sensor")]
        assert "if mins is None" in helper, "no-upcoming-games (break day) must skip"
        assert "mins > horizon_min" in helper, "beyond-horizon must skip"
        assert "return None" in helper, "inside the horizon must RUN (return None)"


class TestScheduleCaptureSingleOwner:
    def test_host_cron_schedule_capture_stays_disabled(self):
        """Every schedule-capture run line in capture.crontab must be commented out —
        the Dagster intraday_schedule_capture_* schedules are the sole owner."""
        active = [
            ln for ln in CRONTAB.splitlines()
            if "run --rm schedule-capture" in ln and not ln.lstrip().startswith("#")
        ]
        assert not active, (
            f"capture.crontab re-activates the host schedule-capture cron ({active}) — "
            "with the Dagster intraday_schedule_capture_* schedules RUNNING this "
            "double-fires the SF monthly_schedule INSERT + 3-model dbt rebuild every "
            "30 min (the #1 measured warehouse-waker) and 409-contends the dbt-runner."
        )


class TestBookOddsIntradayS3:
    def test_s3_requires_both_flags(self):
        body = INTRADAY[INTRADAY.find("def write_book_odds_op"):INTRADAY.find("def intraday_weather_capture")]
        assert re.search(
            r'W7B_LAKEHOUSE_S3.*==\s*"1"\s+and\s+_W6_INTRADAY_ENABLED', body), (
            "write_book_odds_op must append --s3 ONLY when BOTH W7B_LAKEHOUSE_S3 and "
            "W6_LAKEHOUSE_INTRADAY are on — --s3 without the intraday S3 mart rebuild "
            "re-freezes the served line-movement chart at the morning serve."
        )

    def test_s3_is_conditional_not_hardcoded(self):
        body = INTRADAY[INTRADAY.find("def write_book_odds_op"):INTRADAY.find("def intraday_weather_capture")]
        assert '"--book-odds", "--game-detail"' in body and 'args.append("--s3")' in body, (
            "the base args must stay --book-odds --game-detail with --s3 appended "
            "conditionally (hardcoding --s3 breaks pre-cutover boxes; dropping it "
            "re-opens ~15 SF warehouse-waking sessions/day through game hours)."
        )


class TestTickSfFreeStep3:
    """E11.20 phase-2a STEP 3 — the 30-min capture tick retires its two Snowflake legs
    (intraday_lineup_rebuild dbt SF staging + the trailing refresh_w1_external_tables) under a
    default-OFF TICK_SF_FREE gate that REQUIRES SCHEDULE_LAKEHOUSE_INTRADAY (the --w7b S3 rebuild
    that replaces the dbt leg). Merging is a runtime no-op; the flip is operator/box work."""

    def _helper(self) -> str:
        return INTRADAY[INTRADAY.find("def _tick_sf_free"):INTRADAY.find("def _w6_lakehouse_intraday")]

    def test_gate_requires_both_flags(self):
        assert re.search(
            r'TICK_SF_FREE"\)\s*==\s*"1"\s+and\s+os\.environ\.get\("SCHEDULE_LAKEHOUSE_INTRADAY"\)\s*==\s*"1"',
            self._helper()), (
            "_tick_sf_free must require BOTH TICK_SF_FREE and SCHEDULE_LAKEHOUSE_INTRADAY — dropping "
            "the SF lineup rebuild WITHOUT the --w7b S3 rebuild leaves lineups stale on both paths "
            "and the lineup monitor goes blind (post_lineup never fires)."
        )

    def test_lineup_rebuild_skips_before_dbt_when_gated(self):
        body = INTRADAY[INTRADAY.find("def intraday_lineup_rebuild"):]
        body = body[:body.find("\n@op") if "\n@op" in body[10:] else len(body)]
        gate = body.find("if _tick_sf_free():")
        ret = body.find("return", gate)
        dbt = body.find("_run_dbt(")
        assert gate != -1 and ret != -1 and dbt != -1 and gate < ret < dbt, (
            "intraday_lineup_rebuild must check _tick_sf_free() and return BEFORE _run_dbt — the "
            "SF staging rebuild is the leg being retired."
        )

    def test_lineup_rebuild_misconfig_is_loud_and_falls_back(self):
        body = INTRADAY[INTRADAY.find("def intraday_lineup_rebuild"):INTRADAY.find("--target", INTRADAY.find("def intraday_lineup_rebuild"))]
        # TICK_SF_FREE set but SCHEDULE_LAKEHOUSE_INTRADAY off ⇒ warn loud + still run the dbt rebuild.
        assert 'os.environ.get("TICK_SF_FREE") == "1"' in body and "log.warning" in body, (
            "when TICK_SF_FREE=1 but SCHEDULE_LAKEHOUSE_INTRADAY is OFF, the op must warn LOUD and "
            "fall back to running the dbt rebuild (never silently skip and blind the monitor)."
        )

    def test_ext_refresh_is_gated_not_removed(self):
        body = INTRADAY[INTRADAY.find("def _schedule_lakehouse_intraday"):INTRADAY.find("def _w6_lakehouse_intraday")]
        assert "if _tick_sf_free():" in body and 'refresh_w1_external_tables.py")' in body, (
            "the tick's refresh_w1_external_tables must be gated on _tick_sf_free() (else-run), not "
            "hardcoded-removed — removing it unconditionally breaks pre-flip boxes that still read SF."
        )

    def test_tick_sf_free_does_not_gate_the_capture_insert_or_export_bridge(self):
        # Step 3 owns ONLY the refresh + dbt legs. The SF INSERT (ingest_statsapi schedule) and the
        # export bridge (export_odds_raw_to_s3 --source monthly_schedule) are the writer-flip's to
        # retire (order-coupled to W11_RAW_WRITE_MODE / INC-31). They must NOT hang off TICK_SF_FREE.
        body = INTRADAY[INTRADAY.find("def _schedule_lakehouse_intraday"):INTRADAY.find("def _w6_lakehouse_intraday")]
        bridge_line = [ln for ln in body.splitlines() if "export_odds_raw_to_s3.py" in ln and "monthly_schedule" in ln]
        assert bridge_line, "export bridge line not found"
        # the bridge export is unconditional in this helper (its own SCHEDULE_LAKEHOUSE_INTRADAY gate is
        # at the top); it must not be wrapped by a _tick_sf_free() branch.
        assert "if _tick_sf_free" not in bridge_line[0]


class TestW7b2IntradayServingS3:
    """E11.20 phase-2a W7b-2 — the intraday predict + serving read S3 instead of the Snowflake
    staging views (the last game-hours SF-view readers), gated default-OFF so merging is a no-op
    and the flip soaks independently of the enforced-ON morning/daily W7B_LAKEHOUSE_S3."""

    def _helper(self) -> str:
        return DAILY_OPS[DAILY_OPS.find("def _w7b_intraday_serving_on"):DAILY_OPS.find("def _w8a_serving_on")]

    def test_gate_is_separate_default_off_flag(self):
        assert 'os.environ.get("W7B_INTRADAY_S3") == "1"' in self._helper(), (
            "W7b-2 must gate on its OWN default-OFF W7B_INTRADAY_S3, NOT reuse the enforced-ON "
            "W7B_LAKEHOUSE_S3 — reusing it would flip the serving-critical intraday path on merge "
            "with no soak."
        )

    def test_gate_requires_w6_intraday_for_book_odds_freshness(self):
        assert re.search(
            r'W7B_INTRADAY_S3.*==\s*"1"\s+and\s+os\.environ\.get\("W6_LAKEHOUSE_INTRADAY"\)\s*==\s*"1"',
            self._helper()), (
            "the intraday serving --s3 must require W6_LAKEHOUSE_INTRADAY too — its --book-odds leg "
            "reads mart_odds_outcomes, only intraday-fresh when the W6 rebuild is on; else it serves "
            "stale morning odds and clobbers write_book_odds_op (the 2026-07-03 freeze class)."
        )

    def test_intraday_serving_op_appends_the_gated_args_not_hardcoded_s3(self):
        body = DAILY_OPS[DAILY_OPS.find("def write_serving_store_intraday_op"):
                         DAILY_OPS.find("def finalize_prior_slate_game_detail_op")]
        assert "_w7b_intraday_s3_args()" in body, (
            "write_serving_store_intraday_op must append the W7b-2 gated --s3 args, so the flip is "
            "flag-controlled (instant rollback) not a hardcoded read-path change."
        )
        assert '"--picks", "--game-detail", "--book-odds"' in body, "the base intraday args must stay"

    def test_lineup_predict_appends_the_gated_args(self):
        body = SENSOR_OPS[SENSOR_OPS.find("def lineup_predict"):SENSOR_OPS.find("def lineup_dbt_clv_rebuild")]
        assert "_w7b_intraday_s3_args()" in body, (
            "lineup_predict (the tick's post_lineup predict) must append the W7b-2 gated --s3 args — "
            "it is one of the two game-hours SF-view readers the flip moves off Snowflake."
        )
