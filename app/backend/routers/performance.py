"""Performance endpoints.

GET /performance/summary    — fund-level P&L, win rate, mean CLV, Sharpe ratio
GET /performance/by-model   — breakdown by market_type and signal_group
GET /performance/model      — model skill metrics (Brier/CLV/win-rate) with season filter
GET /performance/bets       — per-user settled bets for P&L curve with season filter
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.backend.dependencies import get_user_id
from app.backend.models.performance import (
    MarketMetrics,
    ModelBreakdown,
    ModelMetricsResponse,
    PerformanceBet,
    PerformanceBetsResponse,
    PerformanceByModelResponse,
    PerformanceSummary,
)
from app.backend.services.dynamo import list_bets
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


# ── C1: model skill metrics ───────────────────────────────────────────────────

_MODEL_METRICS_QUERY = """
SELECT
    YEAR(game_date)                                           AS season,
    market_type,
    COUNT(*)                                                  AS n_predictions,
    AVG(POWER(model_prob - actual_outcome, 2))                AS brier_score,
    AVG(clv)                                                  AS avg_clv,
    AVG(CASE WHEN clv_positive THEN 1.0 ELSE 0.0 END)        AS clv_positive_pct,
    AVG(actual_outcome)                                       AS win_rate
FROM baseball_data.betting.mart_clv_labeled_games
WHERE actual_outcome IS NOT NULL
  {season_filter}
GROUP BY 1, 2
ORDER BY 1, 2
"""


@router.get("/model", response_model=ModelMetricsResponse)
def get_model_metrics(season: Optional[int] = None) -> ModelMetricsResponse:
    cache_key = f"performance/model_{season or 'all'}.json"
    cached = get_cache(cache_key)
    if cached is not None:
        return ModelMetricsResponse(**cached)

    season_filter = "AND YEAR(game_date) = %(season)s" if season else ""
    query = _MODEL_METRICS_QUERY.format(season_filter=season_filter)
    params = {"season": season} if season else None

    try:
        rows = execute_query(query, params)
    except Exception as exc:
        logger.exception("Snowflake query failed for /performance/model")
        raise HTTPException(status_code=503, detail="Data unavailable") from exc

    markets = [
        MarketMetrics(
            season=r["SEASON"],
            market_type=r["MARKET_TYPE"],
            n_predictions=r.get("N_PREDICTIONS") or 0,
            brier_score=r.get("BRIER_SCORE"),
            avg_clv=r.get("AVG_CLV"),
            clv_positive_pct=r.get("CLV_POSITIVE_PCT"),
            win_rate=r.get("WIN_RATE"),
        )
        for r in rows
    ]
    result = ModelMetricsResponse(season=season, markets=markets)
    set_cache(cache_key, result.model_dump(mode="json"))
    return result


# ── C1: per-user settled bets ─────────────────────────────────────────────────

@router.get("/bets", response_model=PerformanceBetsResponse)
def get_performance_bets(
    season: Optional[int] = None,
    user_id: str = Depends(get_user_id),
) -> PerformanceBetsResponse:
    try:
        all_bets = list_bets(user_id)
    except Exception as exc:
        logger.exception("DynamoDB read failed for /performance/bets user=%s", user_id)
        raise HTTPException(status_code=503, detail="Data unavailable") from exc

    # settled = outcome recorded; optionally filter by score_date year
    settled = [
        b for b in all_bets
        if b.get("outcome") is not None
        and (season is None or str(b.get("score_date", "")).startswith(str(season)))
    ]

    net_pnl: float | None = None
    if settled:
        pls = [b.get("profit_loss") for b in settled if b.get("profit_loss") is not None]
        net_pnl = sum(pls) if pls else None

    bets_out = [
        PerformanceBet(
            bet_id=b["bet_id"],
            game_pk=int(b["game_pk"]),
            score_date=str(b.get("score_date", "")),
            matchup=b.get("matchup"),
            market=b["market"],
            bookmaker=b.get("bookmaker"),
            american_odds=int(b["american_odds"]) if b.get("american_odds") is not None else None,
            stake=float(b.get("stake", 0)),
            outcome=b.get("outcome"),
            profit_loss=float(b["profit_loss"]) if b.get("profit_loss") is not None else None,
            ev=float(b["ev"]) if b.get("ev") is not None else None,
            model_prob=float(b["model_prob"]) if b.get("model_prob") is not None else None,
            placed_at=str(b.get("placed_at", "")),
        )
        for b in settled
    ]

    # total = bets placed in the selected season (settled + pending); use placed_at for filter
    if season:
        total_count = sum(
            1 for b in all_bets
            if str(b.get("placed_at", "")).startswith(str(season))
        )
    else:
        total_count = len(all_bets)

    return PerformanceBetsResponse(
        season=season,
        bets=bets_out,
        total=total_count,
        settled_count=len(settled),
        net_pnl=net_pnl,
    )
