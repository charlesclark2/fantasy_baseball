"""Picks endpoints.

GET /picks/today  — today's qualified bets with conviction scores
GET /picks/history — last 30 days with outcomes and CLV
GET /picks/ev     — all markets for a date with EV + Kelly (no qualified_bet filter)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.backend.models.picks import (
    DataQuality,
    HistoricalPick,
    HistoryPicksResponse,
    Pick,
    TodayPicksResponse,
)
from app.backend.services.s3_cache import get_cache, set_cache
from app.backend.services.snowflake import execute_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/picks", tags=["picks"])

_TARGET_ENV = os.getenv("TARGET_ENV", "dev")
_ML_SCHEMA = (
    "baseball_data.betting_ml"
    if _TARGET_ENV == "prod"
    else "baseball_data.betting_ml_dev"
)

_TODAY_QUERY = f"""
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk
            ORDER BY
                CASE WHEN lineup_confirmed THEN 0 ELSE 1 END,
                inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions
    WHERE game_date = CURRENT_DATE
      AND qualified_bet = TRUE
),
base AS (
    SELECT * FROM ranked WHERE _rn = 1
),
h2h AS (
    SELECT
        b.game_pk,
        b.game_date,
        'h2h'                           AS market_type,
        b.calibrated_win_prob           AS model_prob,
        b.h2h_market_implied_prob       AS bovada_devig_prob,
        b.h2h_edge                      AS edge,
        b.game_conviction_score,
        b.lineup_confirmed,
        NULL::FLOAT                     AS win_prob_ci_low,
        NULL::FLOAT                     AS win_prob_ci_high,
        b.home_team,
        b.away_team,
        b.inserted_at
    FROM base b
    WHERE b.h2h_edge IS NOT NULL
),
totals AS (
    SELECT
        b.game_pk,
        b.game_date,
        'totals'                        AS market_type,
        b.totals_model_prob             AS model_prob,
        b.over_prob_consensus           AS bovada_devig_prob,
        b.totals_edge                   AS edge,
        b.game_conviction_score,
        b.lineup_confirmed,
        NULL::FLOAT                     AS win_prob_ci_low,
        NULL::FLOAT                     AS win_prob_ci_high,
        b.home_team,
        b.away_team,
        b.inserted_at
    FROM base b
    WHERE b.totals_edge IS NOT NULL
      AND NOT COALESCE(b.bullpen_signal_ood, FALSE)
)
SELECT * FROM h2h
UNION ALL
SELECT * FROM totals
ORDER BY game_pk, market_type
"""

_FRESHNESS_QUERY = f"""
SELECT MAX(inserted_at) AS last_updated_at
FROM {_ML_SCHEMA}.daily_model_predictions
WHERE game_date = CURRENT_DATE
"""

_HISTORY_QUERY = f"""
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk
            ORDER BY
                CASE WHEN lineup_confirmed THEN 0 ELSE 1 END,
                inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions
    WHERE game_date >= DATEADD(day, -30, CURRENT_DATE)
      AND qualified_bet = TRUE
),
base AS (
    SELECT * FROM ranked WHERE _rn = 1
),
h2h AS (
    SELECT
        b.game_pk,
        b.game_date,
        'h2h'                                       AS market_type,
        b.calibrated_win_prob                       AS model_prob,
        b.h2h_market_implied_prob                   AS bovada_devig_prob,
        b.h2h_edge                                  AS edge,
        b.game_conviction_score,
        b.lineup_confirmed,
        NULL::FLOAT                                 AS win_prob_ci_low,
        NULL::FLOAT                                 AS win_prob_ci_high,
        b.home_team,
        b.away_team,
        b.inserted_at,
        clv.clv,
        clv.clv_positive,
        clv.actual_outcome
    FROM base b
    LEFT JOIN baseball_data.betting.mart_clv_labeled_games clv
        ON clv.game_pk = b.game_pk AND clv.market_type = 'h2h'
    WHERE b.h2h_edge IS NOT NULL
),
totals AS (
    SELECT
        b.game_pk,
        b.game_date,
        'totals'                                    AS market_type,
        b.totals_model_prob                         AS model_prob,
        b.over_prob_consensus                       AS bovada_devig_prob,
        b.totals_edge                               AS edge,
        b.game_conviction_score,
        b.lineup_confirmed,
        NULL::FLOAT                                 AS win_prob_ci_low,
        NULL::FLOAT                                 AS win_prob_ci_high,
        b.home_team,
        b.away_team,
        b.inserted_at,
        clv.clv,
        clv.clv_positive,
        clv.actual_outcome
    FROM base b
    LEFT JOIN baseball_data.betting.mart_clv_labeled_games clv
        ON clv.game_pk = b.game_pk AND clv.market_type = 'totals'
    WHERE b.totals_edge IS NOT NULL
)
SELECT * FROM h2h
UNION ALL
SELECT * FROM totals
ORDER BY game_date DESC, game_pk, market_type
"""

_EV_QUERY_TODAY = f"""
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk
            ORDER BY
                CASE WHEN lineup_confirmed THEN 0 ELSE 1 END,
                inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions
    WHERE game_date = CURRENT_DATE
),
base AS (
    SELECT * FROM ranked WHERE _rn = 1
),
h2h AS (
    SELECT
        b.game_pk,
        b.game_date,
        'h2h'                           AS market_type,
        b.calibrated_win_prob           AS model_prob,
        b.h2h_market_implied_prob       AS bovada_devig_prob,
        b.h2h_edge                      AS edge,
        b.game_conviction_score,
        b.lineup_confirmed,
        b.qualified_bet,
        NULL::FLOAT                     AS win_prob_ci_low,
        NULL::FLOAT                     AS win_prob_ci_high,
        b.home_team,
        b.away_team,
        b.h2h_kelly_fraction            AS kelly_fraction,
        b.total_line_consensus,
        b.inserted_at
    FROM base b
    WHERE b.h2h_market_implied_prob IS NOT NULL
),
totals AS (
    SELECT
        b.game_pk,
        b.game_date,
        'totals'                        AS market_type,
        b.totals_model_prob             AS model_prob,
        b.over_prob_consensus           AS bovada_devig_prob,
        b.totals_edge                   AS edge,
        b.game_conviction_score,
        b.lineup_confirmed,
        COALESCE(b.qualified_bet, FALSE) AND NOT COALESCE(b.bullpen_signal_ood, FALSE) AS qualified_bet,
        NULL::FLOAT                     AS win_prob_ci_low,
        NULL::FLOAT                     AS win_prob_ci_high,
        b.home_team,
        b.away_team,
        b.totals_kelly_fraction         AS kelly_fraction,
        b.total_line_consensus,
        b.inserted_at
    FROM base b
    WHERE b.over_prob_consensus IS NOT NULL
)
SELECT * FROM h2h
UNION ALL
SELECT * FROM totals
ORDER BY game_pk, market_type
"""

_EV_QUERY_DATE = f"""
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk
            ORDER BY
                CASE WHEN lineup_confirmed THEN 0 ELSE 1 END,
                inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions
    WHERE game_date = %(target_date)s
),
base AS (
    SELECT * FROM ranked WHERE _rn = 1
),
h2h AS (
    SELECT
        b.game_pk,
        b.game_date,
        'h2h'                           AS market_type,
        b.calibrated_win_prob           AS model_prob,
        b.h2h_market_implied_prob       AS bovada_devig_prob,
        b.h2h_edge                      AS edge,
        b.game_conviction_score,
        b.lineup_confirmed,
        b.qualified_bet,
        NULL::FLOAT                     AS win_prob_ci_low,
        NULL::FLOAT                     AS win_prob_ci_high,
        b.home_team,
        b.away_team,
        b.h2h_kelly_fraction            AS kelly_fraction,
        b.total_line_consensus,
        b.inserted_at
    FROM base b
    WHERE b.h2h_market_implied_prob IS NOT NULL
),
totals AS (
    SELECT
        b.game_pk,
        b.game_date,
        'totals'                        AS market_type,
        b.totals_model_prob             AS model_prob,
        b.over_prob_consensus           AS bovada_devig_prob,
        b.totals_edge                   AS edge,
        b.game_conviction_score,
        b.lineup_confirmed,
        COALESCE(b.qualified_bet, FALSE) AND NOT COALESCE(b.bullpen_signal_ood, FALSE) AS qualified_bet,
        NULL::FLOAT                     AS win_prob_ci_low,
        NULL::FLOAT                     AS win_prob_ci_high,
        b.home_team,
        b.away_team,
        b.totals_kelly_fraction         AS kelly_fraction,
        b.total_line_consensus,
        b.inserted_at
    FROM base b
    WHERE b.over_prob_consensus IS NOT NULL
)
SELECT * FROM h2h
UNION ALL
SELECT * FROM totals
ORDER BY game_pk, market_type
"""


def _pipeline_status(last_updated_at: datetime | None) -> str:
    if last_updated_at is None:
        return "no_predictions"
    age_hours = (datetime.now(timezone.utc) - last_updated_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
    return "ok" if age_hours < 6 else "stale"


@router.get("/today", response_model=TodayPicksResponse)
def get_picks_today() -> TodayPicksResponse:
    cached = get_cache("picks/today.json")
    if cached is not None:
        return TodayPicksResponse(**cached)

    try:
        rows = execute_query(_TODAY_QUERY)
        freshness = execute_query(_FRESHNESS_QUERY)
    except Exception as exc:
        logger.exception("Snowflake query failed for /picks/today")
        raise HTTPException(status_code=503, detail="Data unavailable") from exc

    last_updated_at: datetime | None = None
    if freshness and freshness[0].get("LAST_UPDATED_AT"):
        last_updated_at = freshness[0]["LAST_UPDATED_AT"]

    picks = [
        Pick(
            game_pk=r["GAME_PK"],
            game_date=r["GAME_DATE"],
            market_type=r["MARKET_TYPE"],
            model_prob=r.get("MODEL_PROB"),
            bovada_devig_prob=r.get("BOVADA_DEVIG_PROB"),
            edge=r.get("EDGE"),
            game_conviction_score=r.get("GAME_CONVICTION_SCORE"),
            win_prob_ci_low=r.get("WIN_PROB_CI_LOW"),
            win_prob_ci_high=r.get("WIN_PROB_CI_HIGH"),
            lineup_confirmed=r.get("LINEUP_CONFIRMED"),
            home_team=r.get("HOME_TEAM"),
            away_team=r.get("AWAY_TEAM"),
        )
        for r in rows
    ]

    data_quality = DataQuality(
        signal_completeness_score=None,
        last_updated_at=last_updated_at,
        pipeline_status=_pipeline_status(last_updated_at),
    )

    result = TodayPicksResponse(picks=picks, data_quality=data_quality)
    set_cache("picks/today.json", result.model_dump(mode="json"))
    return result


@router.get("/history", response_model=HistoryPicksResponse)
def get_picks_history() -> HistoryPicksResponse:
    try:
        rows = execute_query(_HISTORY_QUERY)
    except Exception as exc:
        logger.exception("Snowflake query failed for /picks/history")
        raise HTTPException(status_code=503, detail="Data unavailable") from exc

    picks = [
        HistoricalPick(
            game_pk=r["GAME_PK"],
            game_date=r["GAME_DATE"],
            market_type=r["MARKET_TYPE"],
            model_prob=r.get("MODEL_PROB"),
            bovada_devig_prob=r.get("BOVADA_DEVIG_PROB"),
            edge=r.get("EDGE"),
            game_conviction_score=r.get("GAME_CONVICTION_SCORE"),
            win_prob_ci_low=r.get("WIN_PROB_CI_LOW"),
            win_prob_ci_high=r.get("WIN_PROB_CI_HIGH"),
            lineup_confirmed=r.get("LINEUP_CONFIRMED"),
            home_team=r.get("HOME_TEAM"),
            away_team=r.get("AWAY_TEAM"),
            clv=r.get("CLV"),
            clv_positive=r.get("CLV_POSITIVE"),
            actual_outcome=r.get("ACTUAL_OUTCOME"),
        )
        for r in rows
    ]

    return HistoryPicksResponse(picks=picks, total=len(picks))


@router.get("/ev")
def get_picks_ev(date: str = Query(default=None, description="YYYY-MM-DD; defaults to today")) -> dict:
    if date:
        try:
            from datetime import date as _date
            _date.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        query = _EV_QUERY_DATE
        params = {"target_date": date}
    else:
        query = _EV_QUERY_TODAY
        params = None

    try:
        rows = execute_query(query, params)
    except Exception as exc:
        logger.exception("Snowflake query failed for /picks/ev")
        raise HTTPException(status_code=503, detail="Data unavailable") from exc

    return {"picks": rows, "total": len(rows)}
