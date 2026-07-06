"""E11.1-W12 — fire-tests: each migrated sensor STILL fires on a forced bad condition.

The AC for the monitoring migration is not "no error" — it is "force a stale/missing condition
→ the sensor still alerts." These tests drive each sensor's generator with a fake Dagster
context and monkeypatched read helpers (so NO network/S3), and assert the right outcome:

  * alert/HALT sensors RAISE on the bad condition (the raise is the page) and SkipReason when
    healthy;
  * the odds_current_rebuild sensor (INC-21) fires a RunRequest when the slate is loaded and
    SkipReason — never an error — when it is not;
  * the trigger sensors (morning_watchdog, statcast catch-up) emit a RunRequest on the gap.

`slow`-marked: importing the `pipeline` package (to reach the sensor defs) pulls in dagster +
all assets/jobs (~5s), well over the 5s fast-gate budget. Skipped entirely if dagster is not
installed in the test env.
"""
from __future__ import annotations

import importlib
import os
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.slow

# pipeline.resources builds a SnowflakeResource at import (bracket env access) — give it dummy
# values so importing the sensor defs never needs real Snowflake env (no connection is made).
for _k in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_ROLE"):
    os.environ.setdefault(_k, "dummy_for_tests")

dagster = pytest.importorskip("dagster")
from dagster import build_sensor_context  # noqa: E402

_ET = ZoneInfo("America/New_York")


def _mod(name: str):
    """The sensor MODULE (not the SensorDefinition that shadows its name in the package)."""
    return importlib.import_module(f"pipeline.sensors.{name}")


class _DummyConn:
    """Stand-in for the lakehouse connection when the read helpers themselves are patched."""

    def close(self):
        pass


def _drive(sensor_def, ctx):
    """Run a sensor generator to completion. Returns ('raise', msg) or ('yield', [typenames]).
    Generator sensors execute lazily on consumption, so the raise surfaces inside list()."""
    try:
        items = list(sensor_def(ctx))
    except Exception as exc:  # noqa: BLE001
        return ("raise", str(exc))
    return ("yield", [type(x).__name__ for x in items])


def _names(result):
    assert result[0] == "yield", f"expected yields, got raise: {result[1]}"
    return result[1]


# ──────────────────────────────────────────────────────────────────────────────
# odds_current_rebuild_sensor (INC-21) — fires the rebuild; never errors on a bad read
# ──────────────────────────────────────────────────────────────────────────────

def test_odds_current_rebuild_fires_runrequest_when_slate_loaded():
    m = _mod("odds_current_rebuild_sensor")
    now = datetime.now(UTC)
    # Window: opens 3h before first pitch, closes at last pitch. Put now inside it.
    m._query_slate = lambda et: (now - timedelta(hours=1), now + timedelta(hours=3))
    out = _drive(m.odds_current_rebuild_sensor, build_sensor_context())
    assert out[0] == "yield" and "RunRequest" in out[1], \
        f"expected a RunRequest (odds rebuild should fire in-window), got {out}"


def test_odds_current_rebuild_skips_not_errors_when_slate_missing():
    """INC-21 core: a missing slate must SkipReason (fail-open), never raise — and post-W12 it
    never KeyErrors on a missing inline key because there is no Snowflake read at all."""
    m = _mod("odds_current_rebuild_sensor")
    m._query_slate = lambda et: (None, None)
    out = _drive(m.odds_current_rebuild_sensor, build_sensor_context())
    assert out == ("yield", ["SkipReason"]), f"expected a single SkipReason, got {out}"


# ──────────────────────────────────────────────────────────────────────────────
# odds_freshness_alert_sensor (HALT) — raises on stale capture / low quota
# ──────────────────────────────────────────────────────────────────────────────

class _FakeOddsConn:
    """A duck()-shaped fake whose execute() returns canned freshness/quota rows in order."""

    def __init__(self, latest, remaining):
        self._results = [(latest,), (remaining,) if remaining is not None else None]
        self._i = 0

    def execute(self, sql, params=None):
        res = self._results[self._i]
        self._i += 1
        return _FakeRel(res)

    def close(self):
        pass


class _FakeRel:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


def test_odds_freshness_raises_on_stale_capture(monkeypatch):
    m = _mod("odds_freshness_alert_sensor")
    import pipeline.utils.alerting as alerting
    monkeypatch.setattr(alerting, "send_alert", lambda *a, **k: True)
    # latest capture 5 hours ago (≫ 90 min) → STALE.
    stale = datetime.utcnow() - timedelta(hours=5)
    import betting_ml.utils.lakehouse_monitor as lhm
    monkeypatch.setattr(lhm, "duck", lambda: _FakeOddsConn(stale, 544674))
    out = _drive(m.odds_freshness_alert_sensor, build_sensor_context())
    assert out[0] == "raise" and "STALE" in out[1], f"stale capture must raise, got {out}"


def test_odds_freshness_raises_on_low_main_quota(monkeypatch):
    m = _mod("odds_freshness_alert_sensor")
    import pipeline.utils.alerting as alerting
    monkeypatch.setattr(alerting, "send_alert", lambda *a, **k: True)
    fresh = datetime.utcnow() - timedelta(minutes=10)
    import betting_ml.utils.lakehouse_monitor as lhm
    # main-key remaining 1234 (< 10000 floor) → LOW quota alert.
    monkeypatch.setattr(lhm, "duck", lambda: _FakeOddsConn(fresh, 1234))
    out = _drive(m.odds_freshness_alert_sensor, build_sensor_context())
    assert out[0] == "raise" and "quota" in out[1].lower(), f"low quota must raise, got {out}"


def test_odds_freshness_healthy_skips(monkeypatch):
    m = _mod("odds_freshness_alert_sensor")
    fresh = datetime.utcnow() - timedelta(minutes=10)
    import betting_ml.utils.lakehouse_monitor as lhm
    monkeypatch.setattr(lhm, "duck", lambda: _FakeOddsConn(fresh, 90000))
    out = _drive(m.odds_freshness_alert_sensor, build_sensor_context())
    assert out == ("yield", ["SkipReason"]), f"healthy capture must skip, got {out}"


# ──────────────────────────────────────────────────────────────────────────────
# schedule_freshness_alert_sensor (HALT) — raises when stg missing on a game day
# ──────────────────────────────────────────────────────────────────────────────

def _full_day_window(m, monkeypatch):
    """Force the sensor's UTC window wide open so the test isn't clock-dependent.

    Use time.min/time.max, NOT time(0,0)/time(23,59): the sensor gate is
    `current_time > _WINDOW_CLOSE_UTC → SkipReason`, so a time(23,59) close still
    skips for the whole 23:59:00–23:59:59 UTC minute — a real CI flake when the run
    lands in that minute (the raise-expecting tests got SkipReason). time.max is
    never `<` any wall-clock time, so the window is genuinely all-day."""
    monkeypatch.setattr(m, "_WINDOW_OPEN_UTC", time.min)
    monkeypatch.setattr(m, "_WINDOW_CLOSE_UTC", time.max)


def test_schedule_freshness_raises_when_stg_missing_but_raw_has_games(monkeypatch):
    m = _mod("schedule_freshness_alert_sensor")
    import pipeline.utils.alerting as alerting
    monkeypatch.setattr(alerting, "send_alert", lambda *a, **k: True)
    _full_day_window(m, monkeypatch)
    monkeypatch.setattr(m, "_get_connection", lambda: _DummyConn())
    monkeypatch.setattr(m, "_monthly_schedule_age_hours", lambda c: 0.5)        # raw fresh
    monkeypatch.setattr(m, "_monthly_schedule_has_today", lambda c, t: True)    # raw has today
    monkeypatch.setattr(m, "_stg_games_has_today", lambda c, t: False)          # stg DID NOT build
    out = _drive(m.schedule_freshness_alert_sensor, build_sensor_context())
    assert out[0] == "raise" and "stg_statsapi_games" in out[1], \
        f"missing stg build on a game day must raise, got {out}"


def test_schedule_freshness_raises_when_raw_stale(monkeypatch):
    m = _mod("schedule_freshness_alert_sensor")
    import pipeline.utils.alerting as alerting
    monkeypatch.setattr(alerting, "send_alert", lambda *a, **k: True)
    _full_day_window(m, monkeypatch)
    monkeypatch.setattr(m, "_get_connection", lambda: _DummyConn())
    monkeypatch.setattr(m, "_monthly_schedule_age_hours", lambda c: 99.0)       # raw STALE (≫ 12h)
    monkeypatch.setattr(m, "_monthly_schedule_has_today", lambda c, t: True)
    monkeypatch.setattr(m, "_stg_games_has_today", lambda c, t: True)
    out = _drive(m.schedule_freshness_alert_sensor, build_sensor_context())
    assert out[0] == "raise" and "STALE" in out[1], f"stale raw schedule must raise, got {out}"


def test_schedule_freshness_healthy_skips(monkeypatch):
    m = _mod("schedule_freshness_alert_sensor")
    _full_day_window(m, monkeypatch)
    monkeypatch.setattr(m, "_get_connection", lambda: _DummyConn())
    monkeypatch.setattr(m, "_monthly_schedule_age_hours", lambda c: 0.5)
    monkeypatch.setattr(m, "_monthly_schedule_has_today", lambda c, t: True)
    monkeypatch.setattr(m, "_stg_games_has_today", lambda c, t: True)
    out = _drive(m.schedule_freshness_alert_sensor, build_sensor_context())
    assert out == ("yield", ["SkipReason"]), f"healthy schedule must skip, got {out}"


# ──────────────────────────────────────────────────────────────────────────────
# clv_alert_sensor (alert) — raises when rolling positive-CLV rate collapses
# ──────────────────────────────────────────────────────────────────────────────

def test_clv_alert_raises_on_low_pct_positive(monkeypatch):
    m = _mod("clv_alert_sensor")
    import pipeline.utils.alerting as alerting
    monkeypatch.setattr(alerting, "send_alert", lambda *a, **k: True)
    monkeypatch.setattr(m, "_compute_rolling_stats",
                        lambda: {"n_rows": 80, "pct_positive_clv": 0.20, "mean_clv": -0.03})
    out = _drive(m.clv_alert_sensor, build_sensor_context())
    assert out[0] == "raise" and "CLV ALERT" in out[1], f"low pct_positive must raise, got {out}"


def test_clv_alert_healthy_skips(monkeypatch):
    m = _mod("clv_alert_sensor")
    monkeypatch.setattr(m, "_compute_rolling_stats",
                        lambda: {"n_rows": 80, "pct_positive_clv": 0.50, "mean_clv": 0.001})
    out = _drive(m.clv_alert_sensor, build_sensor_context())
    assert out == ("yield", ["SkipReason"]), f"healthy CLV must skip, got {out}"


# ──────────────────────────────────────────────────────────────────────────────
# model_health_alert_sensor (alert) — raises when the gate FAILs
# ──────────────────────────────────────────────────────────────────────────────

def test_model_health_raises_on_gate_fail(monkeypatch):
    m = _mod("model_health_alert_sensor")
    import pipeline.utils.alerting as alerting
    import betting_ml.utils.lakehouse_monitor as lhm
    import betting_ml.monitoring.model_health_metrics as mh
    monkeypatch.setattr(alerting, "send_alert", lambda *a, **k: True)
    monkeypatch.setattr(lhm, "monitor_connection", lambda: _DummyConn())
    # matchup coverage OK, but the skill gate FAILs for home_win. Post-INC-24 calibration, the
    # home_win FAIL leg is FLAT OUTPUT (spread), not corr/Brier (which are at-ceiling advisory).
    monkeypatch.setattr(mh, "check_post_lineup_matchup_coverage",
                        lambda *a, **k: {"alert_fired": False, "avg_coverage": 1.0, "n_games": 15})
    monkeypatch.setattr(mh, "evaluate", lambda *a, **k: {
        "home_win": {"verdict": "FAIL",
                     "fail_reasons": "spread 0.012 < 0.025 (flat output)",
                     "calibrated_corr": 0.01, "calibrated_spread": 0.012,
                     "calibrated_brier": 0.25, "no_skill_brier": 0.25, "calibrated_accuracy": 0.5,
                     "advisory_flags": "corr 0.010 < 0.05", "get": dict().get},
        "total_runs": {"verdict": "PASS", "fail_reasons": ""},
        "run_differential": {"verdict": "PASS", "fail_reasons": ""},
    })
    out = _drive(m.model_health_alert_sensor, build_sensor_context())
    assert out[0] == "raise" and "MODEL HEALTH ALERT" in out[1], f"gate FAIL must raise, got {out}"


def test_model_health_raises_on_matchup_coverage_gap(monkeypatch):
    m = _mod("model_health_alert_sensor")
    import pipeline.utils.alerting as alerting
    import betting_ml.utils.lakehouse_monitor as lhm
    import betting_ml.monitoring.model_health_metrics as mh
    monkeypatch.setattr(alerting, "send_alert", lambda *a, **k: True)
    monkeypatch.setattr(lhm, "monitor_connection", lambda: _DummyConn())
    # evaluate() is called before the matchup check; patch it so the dummy conn is never used.
    monkeypatch.setattr(mh, "evaluate", lambda *a, **k: None)
    monkeypatch.setattr(mh, "check_post_lineup_matchup_coverage",
                        lambda *a, **k: {"alert_fired": True, "fail_reason": "INC-17 class: null matchup block",
                                         "avg_coverage": 0.83, "n_games": 15})
    out = _drive(m.model_health_alert_sensor, build_sensor_context())
    assert out[0] == "raise" and "INC-17" in out[1], f"matchup coverage gap must raise, got {out}"


# ──────────────────────────────────────────────────────────────────────────────
# pregame_alert_sensor (alert) — raises when no lineup-confirmed predictions in-window
# ──────────────────────────────────────────────────────────────────────────────

def test_pregame_alert_raises_when_no_confirmed_predictions(monkeypatch):
    m = _mod("pregame_alert_sensor")
    # Put now inside the 55–30-min pre-game window.
    monkeypatch.setattr(m, "_get_earliest_first_pitch_utc",
                        lambda t: datetime.now(UTC) + timedelta(minutes=45))
    monkeypatch.setattr(m, "_get_n_scheduled", lambda t: 10)
    monkeypatch.setattr(m, "_get_post_lineup_status",
                        lambda t: {"n_post_lineup": 0, "n_confirmed": 0})
    out = _drive(m.pregame_alert_sensor, build_sensor_context())
    assert out[0] == "raise" and "NO lineup-confirmed" in out[1], \
        f"no confirmed predictions in-window must raise, got {out}"


def test_pregame_alert_healthy_skips(monkeypatch):
    m = _mod("pregame_alert_sensor")
    monkeypatch.setattr(m, "_get_earliest_first_pitch_utc",
                        lambda t: datetime.now(UTC) + timedelta(minutes=45))
    monkeypatch.setattr(m, "_get_n_scheduled", lambda t: 10)
    monkeypatch.setattr(m, "_get_post_lineup_status",
                        lambda t: {"n_post_lineup": 10, "n_confirmed": 10})
    out = _drive(m.pregame_alert_sensor, build_sensor_context())
    assert out == ("yield", ["SkipReason"]), f"confirmed predictions must skip, got {out}"


# ──────────────────────────────────────────────────────────────────────────────
# conviction_pick_alert_sensor (alert) — emails the picks as a raised digest
# ──────────────────────────────────────────────────────────────────────────────

def test_conviction_digest_raises_with_picks(monkeypatch):
    m = _mod("conviction_pick_alert_sensor")
    monkeypatch.setattr(m, "_get_earliest_first_pitch_utc",
                        lambda t: datetime.now(UTC) + timedelta(minutes=60))
    monkeypatch.setattr(m, "_get_conviction_picks", lambda t: [{
        "home_team_abbrev": "NYY", "away_team_abbrev": "BOS",
        "layer4_h2h_decision": "home", "calibrated_win_prob": 0.58,
        "h2h_market_implied_prob": 0.52, "layer4_h2h_conviction_disagree": 0.01,
        "layer4_h2h_bovada_ml_home": -130, "layer4_h2h_bovada_ml_away": 110,
    }])
    out = _drive(m.conviction_pick_alert_sensor, build_sensor_context())
    assert out[0] == "raise" and "CONVICTION" in out[1], f"picks must raise a digest, got {out}"


def test_conviction_no_picks_skips(monkeypatch):
    m = _mod("conviction_pick_alert_sensor")
    monkeypatch.setattr(m, "_get_earliest_first_pitch_utc",
                        lambda t: datetime.now(UTC) + timedelta(minutes=60))
    monkeypatch.setattr(m, "_get_conviction_picks", lambda t: [])  # predictions ready, 0 picks
    out = _drive(m.conviction_pick_alert_sensor, build_sensor_context())
    assert out == ("yield", ["SkipReason"]), f"0 conviction picks must skip, got {out}"


# ──────────────────────────────────────────────────────────────────────────────
# statcast_freshness_sensor (HALT) — SLA breach raises; pre-deadline gap RunRequests
# ──────────────────────────────────────────────────────────────────────────────

def test_statcast_sla_breach_raises(monkeypatch):
    m = _mod("statcast_freshness_sensor")
    import pipeline.utils.alerting as alerting
    monkeypatch.setattr(alerting, "send_alert", lambda *a, **k: True)
    monkeypatch.setattr(m, "_EARLIEST", time(0, 0))  # bypass the 04:00-ET early gate
    monkeypatch.setattr(m, "_conn", lambda: _DummyConn())
    monkeypatch.setattr(m, "_had_rs_games", lambda c, d: True)
    monkeypatch.setattr(m, "_pitches_present", lambda c, d: False)
    # first pitch 1h ago → deadline (first_pitch − 2h) is in the past → SLA breach.
    monkeypatch.setattr(m, "_first_pitch_et", lambda c, d: datetime.now(_ET) - timedelta(hours=1))
    out = _drive(m.statcast_freshness_sensor, build_sensor_context())
    assert out[0] == "raise" and "SLA BREACH" in out[1], f"SLA breach must raise, got {out}"


def test_statcast_gap_before_deadline_fires_catchup(monkeypatch):
    m = _mod("statcast_freshness_sensor")
    monkeypatch.setattr(m, "_EARLIEST", time(0, 0))
    monkeypatch.setattr(m, "_conn", lambda: _DummyConn())
    monkeypatch.setattr(m, "_had_rs_games", lambda c, d: True)
    monkeypatch.setattr(m, "_pitches_present", lambda c, d: False)
    # first pitch 6h away → deadline well in the future → fire the catch-up RunRequest.
    monkeypatch.setattr(m, "_first_pitch_et", lambda c, d: datetime.now(_ET) + timedelta(hours=6))
    out = _drive(m.statcast_freshness_sensor, build_sensor_context())
    assert out[0] == "yield" and "RunRequest" in out[1], \
        f"missing pitches before deadline must fire the catch-up, got {out}"


# ──────────────────────────────────────────────────────────────────────────────
# morning_watchdog_sensor (trigger) — RunRequests the daily job when morning preds missing
# ──────────────────────────────────────────────────────────────────────────────

def test_morning_watchdog_fires_when_predictions_missing(monkeypatch):
    m = _mod("morning_watchdog_sensor")
    monkeypatch.setattr(m, "_WINDOW_START", time.min)
    monkeypatch.setattr(m, "_WINDOW_END", time.max)  # time.max: window never closes (avoid the 23:59-UTC skip flake)
    monkeypatch.setattr(m, "_has_morning_predictions", lambda t: False)
    monkeypatch.setattr(m, "_has_games_today", lambda t: True)
    out = _drive(m.morning_watchdog_sensor, build_sensor_context())
    assert out[0] == "yield" and "RunRequest" in out[1], \
        f"missing morning predictions on a game day must fire the daily job, got {out}"


def test_morning_watchdog_skips_when_present(monkeypatch):
    m = _mod("morning_watchdog_sensor")
    monkeypatch.setattr(m, "_WINDOW_START", time.min)
    monkeypatch.setattr(m, "_WINDOW_END", time.max)  # time.max: window never closes (avoid the 23:59-UTC skip flake)
    monkeypatch.setattr(m, "_has_morning_predictions", lambda t: True)
    out = _drive(m.morning_watchdog_sensor, build_sensor_context())
    assert out == ("yield", ["SkipReason"]), f"present predictions must skip, got {out}"
