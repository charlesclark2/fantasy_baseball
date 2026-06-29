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
# v6 (de-leaked bake-off champion) went live 2026-06-23. Floor prevents the 30-day
# window from mixing v4/v5 predictions (known-low-spread, near-zero live skill from
# a different root cause) with the v6 era being measured here (INC-17 diagnosis).
# Safe to delete/update when the v6 window alone is long enough (>30 days from floor).
_GATE_FLOOR_DATE = date(2026, 6, 23)
# Pin to the deployed champion version so mixed-model noise (v4/v5 backfill rows
# competing with v6 in the dedup) doesn't inflate or deflate the measured spread.
# Update this when a new champion is promoted.
_MODEL_VERSION = "v6"


@sensor(minimum_interval_seconds=86400)  # at most once per day
def model_health_alert_sensor(context: SensorEvaluationContext):
    """Alert if the deployed model's live skill degrades (serving/calibration regression)."""
    from betting_ml.monitoring import model_health_metrics as mh
    from betting_ml.utils.data_loader import get_snowflake_connection

    end = date.today()
    start = max(end - timedelta(days=_ROLLING_DAYS), _GATE_FLOOR_DATE)
    window = f"{start.isoformat()}→{end.isoformat()}"
    # INC-17-P3: check yesterday's post_lineup slate for lineup-gated feature coverage.
    # Yesterday is guaranteed to have had its post_lineup pass written at game time;
    # today's may not exist yet when the sensor fires in the morning.
    matchup_check_date = end - timedelta(days=1)

    conn = get_snowflake_connection()
    try:
        result = mh.evaluate(conn, _SCHEMA, start, end,
                             model_version=_MODEL_VERSION,
                             prediction_type=_PREDICTION_TYPE)
        matchup_result = mh.check_post_lineup_matchup_coverage(
            conn, _SCHEMA, matchup_check_date
        )
    finally:
        conn.close()

    # INC-17-P3: post_lineup matchup block coverage alert (fires independently of skill gate).
    if matchup_result["alert_fired"]:
        from pipeline.utils.alerting import send_alert  # INC-16-P6
        matchup_msg = (
            f"INC-17 CLASS ALERT: {matchup_result['fail_reason']} "
            f"Run: uv run python scripts/ops/model_health_metrics.py "
            f"--since {matchup_check_date.isoformat()} --prediction-type post_lineup "
            f"--schema {_SCHEMA}"
        )
        context.log.warning("post_lineup matchup coverage LOW: %s", matchup_result["fail_reason"])
        send_alert("post_lineup matchup block null (INC-17 class)", matchup_msg,
                   severity="ERROR", dedup_key="model_health:post_lineup_matchup")
        raise Exception(matchup_msg)

    context.log.info(
        "post_lineup matchup coverage OK for %s: avg_coverage=%.3f n_games=%d",
        matchup_check_date, matchup_result.get("avg_coverage", float("nan")),
        matchup_result.get("n_games", 0),
    )

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
        hw_spread = result["home_win"].get("calibrated_spread", float("nan"))
        flat_note = (
            " NOTE: home_win calibrated_spread is very low — check for flat-output "
            "model (de-leak removed primary discriminator?) before assuming serving regression."
            if hw_spread < mh.MIN_SPREAD_PROB * 2 else ""
        )
        msg = (
            f"MODEL HEALTH ALERT ({_MODEL_VERSION}): gate FAILED for {failed} over {window} "
            f"({_PREDICTION_TYPE}). {details}.{flat_note} "
            f"Diagnose: (1) run rescore_audit --since {start.isoformat()} --compare-live "
            f"(serving vs training-time features); (2) check consensus_win_prob spread in pred log "
            f"(flat output → architecture; large corr jump on rescore → serving gap). Inspect: "
            f"uv run python scripts/ops/model_health_metrics.py --since {start.isoformat()} "
            f"--prediction-type {_PREDICTION_TYPE} --schema {_SCHEMA} --model-version {_MODEL_VERSION}"
        )
        from pipeline.utils.alerting import send_alert  # INC-16-P6
        send_alert("Model health gate FAILED", msg, severity="ERROR",
                   dedup_key=f"model_health:{_PREDICTION_TYPE}")
        raise Exception(msg)

    yield SkipReason(f"Model health OK {window} ({_PREDICTION_TYPE}): {verdicts}")
