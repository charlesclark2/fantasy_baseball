"""Picks endpoints.

GET /picks/today  — today's qualified bets with conviction scores
GET /picks/history — last 30 days with outcomes and CLV
GET /picks/ev     — all markets for a date with EV + Kelly (no qualified_bet filter)
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.backend.models.picks import (
    DataQuality,
    EVPick,
    EVPicksResponse,
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
        p.*,
        g.game_date                                  AS game_start_utc,
        ROW_NUMBER() OVER (
            PARTITION BY p.game_pk
            ORDER BY p.inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions p
    LEFT JOIN baseball_data.betting.stg_statsapi_games g ON g.game_pk = p.game_pk
    WHERE p.game_date = %(today)s
      AND p.prediction_type = 'post_lineup'
),
base AS (
    SELECT * FROM ranked WHERE _rn = 1
),
h2h AS (
    SELECT
        b.game_pk,
        b.game_date,
        'h2h'                                        AS market_type,
        b.calibrated_win_prob                        AS model_prob,
        b.h2h_market_implied_prob                    AS bovada_devig_prob,
        b.layer4_h2h_edge                            AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        NULL::FLOAT                                  AS win_prob_ci_low,
        NULL::FLOAT                                  AS win_prob_ci_high,
        b.home_team,
        b.away_team,
        b.layer4_h2h_decision                        AS pick_side,
        b.game_start_utc,
        b.inserted_at,
        NULL::FLOAT                                  AS model_total_runs,
        NULL::FLOAT                                  AS market_total_line
    FROM base b
    WHERE b.layer4_h2h_decision IN ('home', 'away')
),
totals AS (
    SELECT
        b.game_pk,
        b.game_date,
        'totals'                                     AS market_type,
        b.totals_model_prob                          AS model_prob,
        b.over_prob_consensus                        AS bovada_devig_prob,
        b.layer4_totals_over_signal                  AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        NULL::FLOAT                                  AS win_prob_ci_low,
        NULL::FLOAT                                  AS win_prob_ci_high,
        b.home_team,
        b.away_team,
        b.layer4_totals_decision                     AS pick_side,
        b.game_start_utc,
        b.inserted_at,
        b.pred_total_runs                            AS model_total_runs,
        b.total_line_consensus                       AS market_total_line
    FROM base b
    WHERE b.layer4_totals_decision IN ('over', 'under')
)
SELECT * FROM h2h
UNION ALL
SELECT * FROM totals
ORDER BY game_start_utc, game_pk, market_type
"""

_FRESHNESS_QUERY = f"""
SELECT MAX(inserted_at) AS last_updated_at
FROM {_ML_SCHEMA}.daily_model_predictions
WHERE game_date = %(today)s
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
            ORDER BY inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions
    WHERE game_date = %(today)s
      AND prediction_type = 'post_lineup'
),
base AS (
    SELECT r.*, g.game_date AS game_start_utc
    FROM ranked r
    LEFT JOIN baseball_data.betting.stg_statsapi_games g ON g.game_pk = r.game_pk
    WHERE r._rn = 1
),
h2h AS (
    SELECT
        b.game_pk,
        b.game_date,
        b.game_start_utc,
        'h2h'                                        AS market_type,
        b.calibrated_win_prob                        AS model_prob,
        b.h2h_market_implied_prob                    AS bovada_devig_prob,
        b.layer4_h2h_edge                            AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        b.layer4_h2h_decision <> 'abstain'           AS qualified_bet,
        b.home_team,
        b.away_team,
        b.h2h_kelly_fraction                         AS kelly_fraction,
        b.total_line_consensus,
        NULL::FLOAT                                  AS pred_total_runs
    FROM base b
    WHERE b.h2h_market_implied_prob IS NOT NULL
),
totals AS (
    SELECT
        b.game_pk,
        b.game_date,
        b.game_start_utc,
        'totals'                                     AS market_type,
        b.totals_model_prob                          AS model_prob,
        b.over_prob_consensus                        AS bovada_devig_prob,
        b.layer4_totals_over_signal                  AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        b.layer4_totals_decision <> 'abstain'        AS qualified_bet,
        b.home_team,
        b.away_team,
        b.totals_kelly_fraction                      AS kelly_fraction,
        b.total_line_consensus,
        b.pred_total_runs
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
            ORDER BY inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions
    WHERE game_date = %(target_date)s
      AND prediction_type = 'post_lineup'
),
base AS (
    SELECT r.*, g.game_date AS game_start_utc
    FROM ranked r
    LEFT JOIN baseball_data.betting.stg_statsapi_games g ON g.game_pk = r.game_pk
    WHERE r._rn = 1
),
h2h AS (
    SELECT
        b.game_pk,
        b.game_date,
        b.game_start_utc,
        'h2h'                                        AS market_type,
        b.calibrated_win_prob                        AS model_prob,
        b.h2h_market_implied_prob                    AS bovada_devig_prob,
        b.layer4_h2h_edge                            AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        b.layer4_h2h_decision <> 'abstain'           AS qualified_bet,
        b.home_team,
        b.away_team,
        b.h2h_kelly_fraction                         AS kelly_fraction,
        b.total_line_consensus,
        NULL::FLOAT                                  AS pred_total_runs
    FROM base b
    WHERE b.h2h_market_implied_prob IS NOT NULL
),
totals AS (
    SELECT
        b.game_pk,
        b.game_date,
        b.game_start_utc,
        'totals'                                     AS market_type,
        b.totals_model_prob                          AS model_prob,
        b.over_prob_consensus                        AS bovada_devig_prob,
        b.layer4_totals_over_signal                  AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        b.layer4_totals_decision <> 'abstain'        AS qualified_bet,
        b.home_team,
        b.away_team,
        b.totals_kelly_fraction                      AS kelly_fraction,
        b.total_line_consensus,
        b.pred_total_runs
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

    today = date.today().isoformat()
    try:
        rows = execute_query(_TODAY_QUERY, params={"today": today})
        freshness = execute_query(_FRESHNESS_QUERY, params={"today": today})
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
            pick_side=r.get("PICK_SIDE"),
            game_start_utc=r.get("GAME_START_UTC"),
            model_total_runs=r.get("MODEL_TOTAL_RUNS"),
            market_total_line=r.get("MARKET_TOTAL_LINE"),
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
    cached = get_cache("picks/history.json")
    if cached is not None:
        return HistoryPicksResponse(**cached)

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

    result = HistoryPicksResponse(picks=picks, total=len(picks))
    set_cache("picks/history.json", result.model_dump(mode="json"))
    return result


@router.get("/ev", response_model=EVPicksResponse)
def get_picks_ev(date: str = Query(default=None, description="YYYY-MM-DD; defaults to today")) -> EVPicksResponse:
    from datetime import date as _date
    today_str = _date.today().isoformat()
    if date:
        try:
            _date.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        query = _EV_QUERY_DATE
        params = {"target_date": date}
        cache_key = None  # don't cache historical date lookups
    else:
        query = _EV_QUERY_TODAY
        params = {"today": today_str}
        cache_key = "picks/ev.json"

    if cache_key:
        cached = get_cache(cache_key)
        if cached is not None:
            return EVPicksResponse(**cached)

    try:
        rows = execute_query(query, params)
    except Exception as exc:
        logger.exception("Snowflake query failed for /picks/ev")
        raise HTTPException(status_code=503, detail="Data unavailable") from exc

    picks = [
        EVPick(
            game_pk=r["GAME_PK"],
            game_date=r.get("GAME_DATE"),
            game_start_utc=r.get("GAME_START_UTC"),
            market_type=r["MARKET_TYPE"],
            model_prob=r.get("MODEL_PROB"),
            bovada_devig_prob=r.get("BOVADA_DEVIG_PROB"),
            edge=r.get("EDGE"),
            game_conviction_score=r.get("GAME_CONVICTION_SCORE"),
            lineup_confirmed=r.get("LINEUP_CONFIRMED"),
            qualified_bet=r.get("QUALIFIED_BET"),
            home_team=r.get("HOME_TEAM"),
            away_team=r.get("AWAY_TEAM"),
            kelly_fraction=r.get("KELLY_FRACTION"),
            total_line_consensus=r.get("TOTAL_LINE_CONSENSUS"),
            pred_total_runs=r.get("PRED_TOTAL_RUNS"),
        )
        for r in rows
    ]
    result = EVPicksResponse(picks=picks, total=len(picks))
    if cache_key:
        set_cache(cache_key, result.model_dump(mode="json"))
    return result
