"""Performance endpoints.

GET /performance/summary    — fund-level P&L, win rate, mean CLV, Sharpe ratio
GET /performance/by-model   — breakdown by market_type and signal_group
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.backend.models.performance import ModelBreakdown, PerformanceByModelResponse, PerformanceSummary
from app.backend.services.s3_cache import get_cache, set_cache
from app.backend.services.snowflake import execute_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/performance", tags=["performance"])

# Primary source: mart_bankroll_state (Epic 22.3). Falls back to mart_clv_labeled_games.
_BANKROLL_SUMMARY_QUERY = """
SELECT
    total_bets,
    wins,
    win_rate,
    mean_clv,
    net_pnl_flat,
    net_pnl_kelly,
    sharpe_ratio
FROM baseball_data.betting.mart_bankroll_state
ORDER BY recorded_at DESC
LIMIT 1
"""

_CLV_SUMMARY_QUERY = """
SELECT
    COUNT(*)                                                      AS total_bets,
    SUM(CASE WHEN actual_outcome = 1 AND clv_positive THEN 1
             WHEN actual_outcome = 0 AND NOT clv_positive THEN 1
             ELSE 0 END)                                          AS wins,
    AVG(clv)                                                      AS mean_clv,
    SUM(CASE WHEN clv_positive THEN 1.0 ELSE -1.0 END)           AS net_pnl_flat
FROM baseball_data.betting.mart_clv_labeled_games
WHERE actual_outcome IS NOT NULL
"""

_BY_MODEL_QUERY = """
SELECT
    market_type,
    NULL                                                          AS signal_group,
    COUNT(*)                                                      AS total_bets,
    SUM(CASE WHEN actual_outcome = 1 AND clv_positive THEN 1
             WHEN actual_outcome = 0 AND NOT clv_positive THEN 1
             ELSE 0 END)                                          AS wins,
    AVG(clv)                                                      AS mean_clv,
    SUM(CASE WHEN clv_positive THEN 1.0 ELSE -1.0 END)           AS net_pnl_flat
FROM baseball_data.betting.mart_clv_labeled_games
WHERE actual_outcome IS NOT NULL
GROUP BY market_type
ORDER BY market_type
"""


@router.get("/summary", response_model=PerformanceSummary)
def get_performance_summary() -> PerformanceSummary:
    cached = get_cache("performance/summary.json")
    if cached is not None:
        return PerformanceSummary(**cached)

    try:
        rows = execute_query(_BANKROLL_SUMMARY_QUERY)
        if rows:
            r = rows[0]
            result = PerformanceSummary(
                total_bets=r.get("TOTAL_BETS") or 0,
                wins=r.get("WINS") or 0,
                win_rate=r.get("WIN_RATE"),
                mean_clv=r.get("MEAN_CLV"),
                net_pnl_flat=r.get("NET_PNL_FLAT"),
                net_pnl_kelly=r.get("NET_PNL_KELLY"),
                sharpe_ratio=r.get("SHARPE_RATIO"),
                source="mart_bankroll_state",
            )
            set_cache("performance/summary.json", result.model_dump(mode="json"))
            return result
    except Exception:
        logger.warning("mart_bankroll_state unavailable — falling back to mart_clv_labeled_games")

    try:
        rows = execute_query(_CLV_SUMMARY_QUERY)
    except Exception as exc:
        logger.exception("Snowflake query failed for /performance/summary")
        raise HTTPException(status_code=503, detail="Data unavailable") from exc

    if not rows:
        return PerformanceSummary()

    r = rows[0]
    total = r.get("TOTAL_BETS") or 0
    wins = r.get("WINS") or 0
    result = PerformanceSummary(
        total_bets=total,
        wins=wins,
        win_rate=wins / total if total > 0 else None,
        mean_clv=r.get("MEAN_CLV"),
        net_pnl_flat=r.get("NET_PNL_FLAT"),
        source="mart_clv_labeled_games",
    )
    set_cache("performance/summary.json", result.model_dump(mode="json"))
    return result


@router.get("/by-model", response_model=PerformanceByModelResponse)
def get_performance_by_model() -> PerformanceByModelResponse:
    try:
        rows = execute_query(_BY_MODEL_QUERY)
    except Exception as exc:
        logger.exception("Snowflake query failed for /performance/by-model")
        raise HTTPException(status_code=503, detail="Data unavailable") from exc

    breakdown = [
        ModelBreakdown(
            market_type=r["MARKET_TYPE"],
            signal_group=r.get("SIGNAL_GROUP"),
            total_bets=r.get("TOTAL_BETS") or 0,
            wins=r.get("WINS") or 0,
            win_rate=(r.get("WINS") or 0) / r["TOTAL_BETS"] if r.get("TOTAL_BETS") else None,
            mean_clv=r.get("MEAN_CLV"),
            net_pnl_flat=r.get("NET_PNL_FLAT"),
        )
        for r in rows
    ]
    return PerformanceByModelResponse(breakdown=breakdown)
