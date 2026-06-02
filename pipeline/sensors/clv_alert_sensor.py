"""
clv_alert_sensor.py — Epic 12 Story 12.2

Daily sensor: computes the rolling 2-week pct_positive_clv from
feature_pregame_meta_model_features. If it drops below 0.35, raises an
exception so Dagster marks the tick as failed and sends the standard
email-on-failure notification.

Alert threshold: pct_positive_clv < 0.35 over any 14-day rolling window.
This threshold signals that the model's edge direction is wrong more than
65% of the time — a strong indicator of model drift or data quality issues.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from dagster import SensorEvaluationContext, SkipReason, sensor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

_ALERT_THRESHOLD = 0.35
_ROLLING_DAYS = 14
_DATABASE = "baseball_data"
_FEATURE_TABLE = f"{_DATABASE}.betting_features.feature_pregame_meta_model_features"

_ROLLING_QUERY = """
select
    count(*)                                            as n_rows,
    avg(clv_positive::integer)                          as pct_positive_clv,
    avg(clv)                                            as mean_clv
from {table}
where game_date >= '{cutoff}'
  and clv is not null
""".format(
    table=_FEATURE_TABLE,
    cutoff="{cutoff}",
)


def _compute_rolling_stats() -> dict | None:
    from betting_ml.utils.data_loader import get_snowflake_connection

    cutoff = (date.today() - timedelta(days=_ROLLING_DAYS)).isoformat()
    query = _ROLLING_QUERY.format(cutoff=cutoff)

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(query)
        row = cur.fetchone()
    finally:
        conn.close()

    if row is None or row[0] == 0:
        return None

    return {
        "n_rows": int(row[0]),
        "pct_positive_clv": float(row[1]) if row[1] is not None else None,
        "mean_clv": float(row[2]) if row[2] is not None else None,
    }


@sensor(minimum_interval_seconds=86400)  # run at most once per day
def clv_alert_sensor(context: SensorEvaluationContext):
    """
    Daily sensor: alerts if rolling 2-week pct_positive_clv drops below 0.35.

    When the threshold is breached the sensor raises an exception, marking the
    tick as failed and triggering Dagster's standard email-on-failure alert.
    When healthy it yields SkipReason with summary stats.
    """
    stats = _compute_rolling_stats()

    if stats is None:
        yield SkipReason(
            f"No CLV-labeled rows in the last {_ROLLING_DAYS} days — nothing to check."
        )
        return

    pct_pos = stats["pct_positive_clv"]
    n = stats["n_rows"]
    mean_clv = stats["mean_clv"]

    context.log.info(
        "Rolling %d-day CLV stats: n=%d  pct_positive=%.1f%%  mean_clv=%.4f",
        _ROLLING_DAYS,
        n,
        (pct_pos or 0) * 100,
        mean_clv or 0,
    )

    if pct_pos is not None and pct_pos < _ALERT_THRESHOLD:
        raise Exception(
            f"CLV ALERT: pct_positive_clv={pct_pos:.1%} < threshold {_ALERT_THRESHOLD:.0%} "
            f"over last {_ROLLING_DAYS} days (n={n}, mean_clv={mean_clv:+.4f}). "
            f"Check feature_pregame_meta_model_features for model drift or data issues."
        )

    yield SkipReason(
        f"CLV healthy: pct_positive={pct_pos:.1%} >= {_ALERT_THRESHOLD:.0%} "
        f"(n={n}, mean_clv={mean_clv:+.4f})"
    )
