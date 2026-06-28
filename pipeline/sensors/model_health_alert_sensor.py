"""
model_health_alert_sensor.py — Epic A2 Story A2.6

Daily standing health gate for the DEPLOYED prediction model. Runs the A2.1 honest
live-skill metrics (`betting_ml.monitoring.model_health_metrics.evaluate`) over a rolling window
of completed games and RAISES an exception — marking the tick failed and firing Dagster's
standard email-on-failure alert — when any target's gate FAILs on a sufficient sample.
Healthy or insufficient-sample → SkipReason with a summary.

This is Epic A2's regression backstop. The original incident: discriminative features
served null → the home_win model collapsed to a flat predictor (spread ~0.016, corr ~0,
Brier ≈ no-skill) and it went UNNOTICED because only Brier/ECE were tracked. After the
serving + calibration fixes the model is healthy (spread restored, corr recovered). If
serving silently breaks again, home_win spread/corr collapse and this gate fires.

Design notes:
  * Measured on `post_lineup` predictions — the honest surface. The matchup features
    (lineup archetype / cluster / h2h) are lineup-gated, so morning predictions
    structurally lack them and would understate skill.
  * Floored at the deploy date so the rolling window never measures PRE-fix logged
    predictions (which carry the old flat calibrated_win_prob). Until ≥ MIN_GAMES
    post-fix games accumulate the gate reports INSUFFICIENT and skips (no false alarm).
    The floor self-expires once the rolling window starts after it (~30 days post-deploy).
  * Thresholds live in model_health_metrics (MIN_CORR_*, MIN_SPREAD_*, BRIER_MARGIN) —
    the gate and the ad-hoc report use identical criteria.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from dagster import SensorEvaluationContext, SkipReason, sensor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
# NOTE: model_health_metrics now lives in the installable `betting_ml` package
# (betting_ml.monitoring), NOT under scripts/ — scripts/ is not shipped to the
# Dagster code location in prod, which caused ModuleNotFoundError here. Do not
# re-add scripts/ops to sys.path; import from the package below.

_ROLLING_DAYS = 30
_PREDICTION_TYPE = "post_lineup"
_SCHEMA = "betting_ml"                 # prod prediction log
# Serving + calibration fixes went live 2026-06-10; don't gate on pre-fix predictions.
# Safe to delete this floor once the rolling window naturally starts after it.
_GATE_FLOOR_DATE = date(2026, 6, 10)


@sensor(minimum_interval_seconds=86400)  # at most once per day
def model_health_alert_sensor(context: SensorEvaluationContext):
    """Alert if the deployed model's live skill degrades (serving/calibration regression)."""
    from betting_ml.monitoring import model_health_metrics as mh
    from betting_ml.utils.data_loader import get_snowflake_connection

    end = date.today()
    start = max(end - timedelta(days=_ROLLING_DAYS), _GATE_FLOOR_DATE)
    window = f"{start.isoformat()}→{end.isoformat()}"

    conn = get_snowflake_connection()
    try:
        result = mh.evaluate(conn, _SCHEMA, start, end, prediction_type=_PREDICTION_TYPE)
    finally:
        conn.close()

    if result is None:
        yield SkipReason(f"No completed {_PREDICTION_TYPE} predictions in {window}.")
        return

    verdicts = {t: m["verdict"] for t, m in result.items()}
    hw = result["home_win"]
    context.log.info(
        "Model health %s (%s): %s | home_win corr=%.3f spread=%.3f Brier=%.3f (no-skill %.3f)",
        window, _PREDICTION_TYPE, verdicts,
        hw["calibrated_corr"], hw["calibrated_spread"], hw["calibrated_brier"], hw["no_skill_brier"],
    )

    failed = [t for t, v in verdicts.items() if v == "FAIL"]
    if failed:
        details = " | ".join(f"{t}: {result[t]['fail_reasons']}" for t in failed)
        msg = (
            f"MODEL HEALTH ALERT: gate FAILED for {failed} over {window} ({_PREDICTION_TYPE}). "
            f"{details}. Likely a serving/calibration regression — the deployed model's "
            f"discrimination has degraded (cf. the 2026-06 audit). Inspect with: "
            f"uv run python scripts/ops/model_health_metrics.py --since {start.isoformat()} "
            f"--prediction-type {_PREDICTION_TYPE} --schema {_SCHEMA}"
        )
        from pipeline.utils.alerting import send_alert  # INC-16-P6
        send_alert("Model health gate FAILED", msg, severity="ERROR",
                   dedup_key=f"model_health:{_PREDICTION_TYPE}")
        raise Exception(msg)

    yield SkipReason(f"Model health OK {window} ({_PREDICTION_TYPE}): {verdicts}")
