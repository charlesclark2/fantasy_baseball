"""Pipeline status endpoint (A1.4 — application prediction freshness indicator).

GET /pipeline/status — today's pipeline freshness for the dashboard status dot.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter

from app.backend.models.pipeline import PipelineStatus
from app.backend.services.snowflake import execute_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["pipeline"])

_TARGET_ENV = os.getenv("TARGET_ENV", "dev")
_ML_SCHEMA = (
    "baseball_data.betting_ml"
    if _TARGET_ENV == "prod"
    else "baseball_data.betting_ml_dev"
)

_STATUS_COLS = """
    run_date,
    predict_today_complete_ts,
    lineup_confirmed_complete_ts,
    pipeline_status,
    n_games_scored,
    n_qualified_bets,
    signal_completeness_score,
    avg_feature_coverage_score,
    updated_at
"""

_STATUS_QUERY = f"""
SELECT {_STATUS_COLS}
FROM {_ML_SCHEMA}.pipeline_status
WHERE run_date = CURRENT_DATE
"""

# Most-recent row regardless of date — used only by the admin panel (fallback_latest)
# so it shows the last completed run when today's row isn't written yet. The public
# dashboard dot keeps the today-only query so it never implies stale data is "today".
_LATEST_QUERY = f"""
SELECT {_STATUS_COLS}
FROM {_ML_SCHEMA}.pipeline_status
ORDER BY run_date DESC
LIMIT 1
"""


def _derive(row: dict | None) -> PipelineStatus:
    """Map a pipeline_status row to the freshness indicator the UI renders."""
    if not row:
        return PipelineStatus()  # defaults: red / "Pipeline running…"

    # Snowflake DictCursor returns uppercase column names.
    status = (row.get("PIPELINE_STATUS") or "missing").lower()
    predictions_ready = status == "complete" and (row.get("N_GAMES_SCORED") or 0) > 0
    lineup_confirmed = row.get("LINEUP_CONFIRMED_COMPLETE_TS") is not None
    # Most recent of the two completion stamps (lineup re-score is the later one).
    last_updated_at = row.get("LINEUP_CONFIRMED_COMPLETE_TS") or row.get("PREDICT_TODAY_COMPLETE_TS")

    if predictions_ready and lineup_confirmed:
        indicator = "green"
        message = "Predictions based on confirmed lineups"
    elif predictions_ready:
        indicator = "yellow"
        message = "Predictions based on projected lineups — will update when lineups confirm"
    else:
        indicator = "red"
        message = "Pipeline running — check back in a few minutes"

    return PipelineStatus(
        run_date=row.get("RUN_DATE"),
        predictions_ready=predictions_ready,
        lineup_confirmed=lineup_confirmed,
        last_updated_at=last_updated_at,
        n_games_scored=int(row.get("N_GAMES_SCORED") or 0),
        n_qualified_bets=int(row.get("N_QUALIFIED_BETS") or 0),
        signal_completeness_score=row.get("SIGNAL_COMPLETENESS_SCORE"),
        avg_feature_coverage_score=row.get("AVG_FEATURE_COVERAGE_SCORE"),
        pipeline_status=status,
        indicator=indicator,
        message=message,
    )


@router.get("/status", response_model=PipelineStatus)
def get_pipeline_status(fallback_latest: bool = False) -> PipelineStatus:
    """Return today's prediction freshness for the dashboard status indicator.

    Intentionally uncached — this is a liveness signal and must reflect the
    latest pipeline run. Returns the red/"running" default if no row exists yet.

    fallback_latest (admin-only): when today's row isn't written yet, fall back to
    the most recent run so the admin System Health panel shows the last completed run
    instead of an empty/red card. The public dashboard dot leaves this False so it
    never presents a prior day's "complete" as if it were today's.
    """
    try:
        rows = execute_query(_STATUS_QUERY)
        if not rows and fallback_latest:
            rows = execute_query(_LATEST_QUERY)
    except Exception:
        logger.exception("pipeline status query failed")
        return PipelineStatus()  # fail safe → red dot rather than 500
    return _derive(rows[0] if rows else None)
