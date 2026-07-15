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
