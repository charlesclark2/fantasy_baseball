"""
conviction_pick_alert_sensor.py — Story 28.6b

Emails the day's H2H conviction-gate picks (the 28.2 disagreement gate) once per
day, in the pre-game window, so they can be placed MANUALLY without opening the
Streamlit app. US-manual-only by design: we never auto-place bets — this sensor
is the actionable surface for the manual bettor.

A "conviction pick" = today's post_lineup prediction where the two independent
H2H estimators agree (layer4_h2h_conviction_flag = TRUE) and the rule took a side
(layer4_h2h_decision in home/away).

Alert mechanism (same as pregame_alert_sensor): raises an exception with the picks
formatted in the message, which marks the tick FAILED and triggers Dagster Cloud's
email-on-failure. The "failure" IS the alert — a healthy no-picks day skips quietly.

Cursor stores the last date a digest was finalized so at most one email fires per
calendar day. The cursor is only set once post_lineup predictions exist, so a tick
that lands before the post-lineup run does not prematurely mark the day done.

IMPORTANT (status): the conviction strategy is SHADOW/unconfirmed — its 28.2
backtest edge is within noise and its real-book ROI is selection-inflated. These
alerts are informational for manual review; act on them at your own discretion
until monitor_conviction_h2h.py reports a live CONFIRM.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from dagster import DefaultSensorStatus, SensorEvaluationContext, SkipReason, sensor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Fire when now_utc is in [first_pitch - LEAD, first_pitch - CLOSE]. A wider lead
# than the pipeline watchdog so there's time to place the bets before first pitch.
_ALERT_LEAD_MIN = 75
_ALERT_CLOSE_MIN = 20

# E11.1-W12: reads moved off Snowflake to the S3 lakehouse via DuckDB (instance-role
# credential_chain — Snowflake-free). stg_statsapi_games + daily_model_predictions are both
# already on S3 (with all the layer4_h2h_* conviction columns).


def _get_earliest_first_pitch_utc(today: str) -> datetime | None:
    from betting_ml.utils.lakehouse_monitor import duck, lh, to_utc_datetime

    conn = duck()
    try:
        # game_date reads back as an ISO VARCHAR from the lakehouse (INC-23); MIN on ISO strings
        # still gives the earliest first pitch — to_utc_datetime coerces it (never .tzinfo it).
        row = conn.execute(
            f"""
            SELECT MIN(game_date) AS earliest_utc
            FROM read_parquet('{lh('stg_statsapi_games')}', union_by_name=true)
            WHERE official_date = ? AND game_type = 'R'
            """,
            [today],
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return to_utc_datetime(row[0])
    finally:
        conn.close()


def _get_conviction_picks(today: str) -> list[dict] | None:
    """Today's post_lineup conviction picks. Returns None if NO post_lineup rows
    exist yet (predictions not written), else the (possibly empty) pick list."""
    from betting_ml.utils.lakehouse_monitor import duck, lh

    conn = duck()
    try:
        dmp = f"read_parquet('{lh('daily_model_predictions')}', union_by_name=true)"
        (n_post_lineup,) = conn.execute(
            f"SELECT COUNT(*) FROM {dmp} WHERE score_date = ? AND prediction_type = 'post_lineup'",
            [today],
        ).fetchone()
        if int(n_post_lineup) == 0:
            return None  # predictions not ready — do not finalize the day

        rel = conn.execute(
            f"""
            SELECT home_team_abbrev, away_team_abbrev,
                   layer4_h2h_decision,
                   calibrated_win_prob,
                   h2h_market_implied_prob,
                   layer4_h2h_conviction_disagree,
                   layer4_h2h_bovada_ml_home,
                   layer4_h2h_bovada_ml_away
            FROM {dmp}
            WHERE score_date = ?
              AND prediction_type = 'post_lineup'
              AND layer4_h2h_conviction_flag = TRUE
              AND layer4_h2h_decision IN ('home', 'away')
            ORDER BY layer4_h2h_conviction_disagree
            """,
            [today],
        )
        cols = [d[0].lower() for d in rel.description]
        return [dict(zip(cols, r)) for r in rel.fetchall()]
    finally:
        conn.close()


def _format_pick(p: dict) -> str:
    decision = (p.get("layer4_h2h_decision") or "").lower()
    home, away = p.get("home_team_abbrev") or "?", p.get("away_team_abbrev") or "?"
    pick_team = home if decision == "home" else away
    odds = p.get("layer4_h2h_bovada_ml_home") if decision == "home" else p.get("layer4_h2h_bovada_ml_away")
    odds_str = f"{int(odds):+d}" if odds is not None else "n/a"
    model_p = p.get("calibrated_win_prob")
    mkt_p = p.get("h2h_market_implied_prob")
    # model/market P are P(home win); show the bet side's probability
    mp = model_p if decision == "home" else (1.0 - model_p if model_p is not None else None)
    kp = mkt_p if decision == "home" else (1.0 - mkt_p if mkt_p is not None else None)
    mp_str = f"{mp:.1%}" if mp is not None else "n/a"
    kp_str = f"{kp:.1%}" if kp is not None else "n/a"
    agree = p.get("layer4_h2h_conviction_disagree")
    agree_str = f"{agree:.3f}" if agree is not None else "n/a"
    return (f"  {away} @ {home} — BET {pick_team} ML @ Bovada {odds_str}  "
            f"(model {mp_str} vs market {kp_str}; estimator agreement Δ={agree_str})")


# E11.23: default_status=RUNNING — self-start on the box / after a DB reset (INC-16 class).
@sensor(minimum_interval_seconds=600, default_status=DefaultSensorStatus.RUNNING)
def conviction_pick_alert_sensor(context: SensorEvaluationContext):
    """Email today's H2H conviction picks once, in the pre-game window."""
    today = date.today().isoformat()

    if context.cursor == today:
        yield SkipReason(f"Already sent conviction digest for {today}.")
        return

    try:
        first_pitch_utc = _get_earliest_first_pitch_utc(today)
    except Exception as exc:
        yield SkipReason(f"Could not fetch first pitch time: {exc}")
        return

    if first_pitch_utc is None:
        yield SkipReason(f"No regular-season games scheduled for {today}.")
        return

    now_utc = datetime.now(UTC)
    window_open = first_pitch_utc - timedelta(minutes=_ALERT_LEAD_MIN)
    window_close = first_pitch_utc - timedelta(minutes=_ALERT_CLOSE_MIN)

    if now_utc < window_open:
        yield SkipReason(f"Window opens at {window_open.strftime('%H:%M')} UTC.")
        return
    if now_utc > window_close:
        yield SkipReason(f"Window closed at {window_close.strftime('%H:%M')} UTC without a digest.")
        return

    try:
        picks = _get_conviction_picks(today)
    except Exception as exc:
        yield SkipReason(f"Snowflake conviction query failed — skipping tick: {exc}")
        return

    if picks is None:
        yield SkipReason("post_lineup predictions not written yet — waiting.")
        return

    # Predictions exist → finalize the day (at most one digest).
    context.update_cursor(today)

    if not picks:
        yield SkipReason(f"Predictions ready, 0 conviction picks for {today}.")
        return

    lines = "\n".join(_format_pick(p) for p in picks)
    raise Exception(
        f"🎯 Diamond Edge — {len(picks)} H2H CONVICTION pick(s) for {today} "
        f"(place MANUALLY at Bovada; SHADOW/unconfirmed — informational):\n{lines}\n\n"
        f"Conviction gate = both independent H2H estimators agree within 0.02. "
        f"Strategy is in its forward-test window (monitor_conviction_h2h.py); not yet CONFIRMED."
    )
