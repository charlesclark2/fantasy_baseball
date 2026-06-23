"""Picks endpoints.

GET /picks/today  — today's qualified bets with conviction scores
GET /picks/history — last 30 days with outcomes and CLV
GET /picks/ev     — all markets for a date with EV + Kelly (no qualified_bet filter)
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from app.backend.models.picks import (
    BookOddsComparison,
    BovadaH2H,
    BovadaLines,
    BovadaTotals,
    DataQuality,
    EVPick,
    EVPicksResponse,
    FeaturedPickResponse,
    FeaturedYesterday,
    GameContext,
    GameDetailResponse,
    GameLineups,
    GamePerfFeatures,
    GamePicksResponse,
    GameScore,
    GameStarters,
    H2HRecord,
    HistoricalPick,
    HistoryPicksResponse,
    LineMovement,
    LineupPlayer,
    Pick,
    PickDriver,
    PickExplanationPayload,
    PickExplanationTarget,
    PublicBetting,
    StarterStats,
    TeamPerfStats,
    TeamRecentForm,
    TodayPicksResponse,
    UmpireInfo,
    WeatherInfo,
)
from app.backend.dependencies import get_optional_user_id
from app.backend.services import pg
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

_FEATURED_TODAY_QUERY = f"""
WITH ranked AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (
            PARTITION BY p.game_pk
            ORDER BY
                -- Prefer rows that actually carry market data: a degraded run
                -- (post_lineup with NULL odds/abstain decisions) must never shadow
                -- a complete morning row and get filtered out downstream.
                CASE WHEN (p.h2h_market_implied_prob IS NOT NULL OR p.over_prob_consensus IS NOT NULL) THEN 0 ELSE 1 END,
                CASE WHEN p.prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                p.inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions p
    WHERE p.game_date = %(today)s
      AND p.prediction_type IN ('post_lineup', 'morning')
),
base AS (SELECT * FROM ranked WHERE _rn = 1),
h2h AS (
    SELECT
        b.game_pk,
        b.home_team,
        b.away_team,
        'h2h'                                                         AS market_type,
        b.calibrated_win_prob                                         AS model_prob,
        b.h2h_market_implied_prob                                     AS market_prob,
        ABS(b.calibrated_win_prob - b.h2h_market_implied_prob)        AS edge,
        b.win_prob_ci_low,
        b.win_prob_ci_high,
        b.game_datetime,
        b.game_date,
        b.prediction_type,
        b.layer4_h2h_decision                                         AS pick_side
    FROM base b
    WHERE b.layer4_h2h_conviction_flag = TRUE
      AND b.layer4_h2h_decision IN ('home', 'away')
),
totals AS (
    SELECT
        b.game_pk,
        b.home_team,
        b.away_team,
        'totals'                                                       AS market_type,
        b.totals_model_prob                                            AS model_prob,
        b.over_prob_consensus                                          AS market_prob,
        ABS(b.totals_model_prob - b.over_prob_consensus)               AS edge,
        b.win_prob_ci_low,
        b.win_prob_ci_high,
        b.game_datetime,
        b.game_date,
        b.prediction_type,
        b.layer4_totals_decision                                       AS pick_side
    FROM base b
    WHERE b.layer4_h2h_conviction_flag = TRUE
      AND b.layer4_totals_decision IN ('over', 'under')
)
SELECT game_pk, home_team, away_team, market_type, model_prob, market_prob,
       edge, win_prob_ci_low, win_prob_ci_high, game_datetime, game_date, prediction_type,
       pick_side
FROM h2h
UNION ALL
SELECT game_pk, home_team, away_team, market_type, model_prob, market_prob,
       edge, win_prob_ci_low, win_prob_ci_high, game_datetime, game_date, prediction_type,
       pick_side
FROM totals
ORDER BY game_datetime ASC NULLS LAST, game_pk ASC
LIMIT 1
"""

_FEATURED_STALE_FALLBACK_QUERY = f"""
WITH ranked AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (
            PARTITION BY p.game_pk
            ORDER BY
                -- Prefer rows that actually carry market data: a degraded run
                -- (post_lineup with NULL odds/abstain decisions) must never shadow
                -- a complete morning row and get filtered out downstream.
                CASE WHEN (p.h2h_market_implied_prob IS NOT NULL OR p.over_prob_consensus IS NOT NULL) THEN 0 ELSE 1 END,
                CASE WHEN p.prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                p.inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions p
    WHERE p.game_date = DATEADD(day, -1, %(today)s::DATE)
      AND p.prediction_type IN ('post_lineup', 'morning')
),
base AS (SELECT * FROM ranked WHERE _rn = 1),
h2h AS (
    SELECT
        b.game_pk,
        b.home_team,
        b.away_team,
        'h2h'                                                         AS market_type,
        b.calibrated_win_prob                                         AS model_prob,
        b.h2h_market_implied_prob                                     AS market_prob,
        ABS(b.calibrated_win_prob - b.h2h_market_implied_prob)        AS edge,
        b.win_prob_ci_low,
        b.win_prob_ci_high,
        b.game_datetime,
        b.game_date,
        b.prediction_type,
        clv.actual_outcome,
        b.layer4_h2h_decision                                         AS pick_side
    FROM base b
    LEFT JOIN baseball_data.betting.mart_clv_labeled_games clv
        ON clv.game_pk = b.game_pk AND clv.market_type = 'h2h'
    WHERE b.layer4_h2h_conviction_flag = TRUE
      AND b.layer4_h2h_decision IN ('home', 'away')
),
totals AS (
    SELECT
        b.game_pk,
        b.home_team,
        b.away_team,
        'totals'                                                       AS market_type,
        b.totals_model_prob                                            AS model_prob,
        b.over_prob_consensus                                          AS market_prob,
        ABS(b.totals_model_prob - b.over_prob_consensus)               AS edge,
        b.win_prob_ci_low,
        b.win_prob_ci_high,
        b.game_datetime,
        b.game_date,
        b.prediction_type,
        clv.actual_outcome,
        b.layer4_totals_decision                                       AS pick_side
    FROM base b
    LEFT JOIN baseball_data.betting.mart_clv_labeled_games clv
        ON clv.game_pk = b.game_pk AND clv.market_type = 'totals'
    WHERE b.layer4_h2h_conviction_flag = TRUE
      AND b.layer4_totals_decision IN ('over', 'under')
)
SELECT game_pk, home_team, away_team, market_type, model_prob, market_prob,
       edge, win_prob_ci_low, win_prob_ci_high, game_datetime, game_date, prediction_type,
       actual_outcome, pick_side
FROM h2h
UNION ALL
SELECT game_pk, home_team, away_team, market_type, model_prob, market_prob,
       edge, win_prob_ci_low, win_prob_ci_high, game_datetime, game_date, prediction_type,
       actual_outcome, pick_side
FROM totals
ORDER BY actual_outcome DESC NULLS LAST, ABS(edge) DESC NULLS LAST, game_datetime ASC NULLS LAST
LIMIT 1
"""

_FEATURED_YESTERDAY_QUERY = f"""
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk
            ORDER BY CASE WHEN lineup_confirmed THEN 0 ELSE 1 END, inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions
    WHERE game_date = DATEADD(day, -1, %(today)s::DATE)
      AND qualified_bet = TRUE
),
base AS (SELECT * FROM ranked WHERE _rn = 1),
h2h AS (
    SELECT b.game_pk, b.home_team, b.away_team, 'h2h' AS market_type,
           clv.actual_outcome
    FROM base b
    LEFT JOIN baseball_data.betting.mart_clv_labeled_games clv
        ON clv.game_pk = b.game_pk AND clv.market_type = 'h2h'
    WHERE b.layer4_h2h_decision IN ('home', 'away')
),
totals AS (
    SELECT b.game_pk, b.home_team, b.away_team, 'totals' AS market_type,
           clv.actual_outcome
    FROM base b
    LEFT JOIN baseball_data.betting.mart_clv_labeled_games clv
        ON clv.game_pk = b.game_pk AND clv.market_type = 'totals'
    WHERE b.layer4_totals_decision IN ('over', 'under')
)
SELECT * FROM h2h
UNION ALL
SELECT * FROM totals
ORDER BY actual_outcome DESC NULLS LAST, game_pk, market_type
LIMIT 1
"""

_ET = ZoneInfo("America/New_York")

# Story 30.15 — per-game explanation (pick_explanation JSON + pick_narrative VARCHAR).
# Separate lightweight query so the complex UNION ALL game queries don't need extra columns.
_EXPLANATION_QUERY = f"""
SELECT pick_explanation, pick_narrative, prediction_type
FROM {_ML_SCHEMA}.daily_model_predictions
WHERE game_pk = %(game_pk)s
  AND pick_explanation IS NOT NULL
ORDER BY
    CASE WHEN prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
    inserted_at DESC
LIMIT 1
"""


def _parse_explanation(raw: str | dict | None) -> PickExplanationPayload | None:
    """Parse pick_explanation VARCHAR → PickExplanationPayload; returns None on any failure."""
    if not raw:
        return None
    try:
        import json
        data = json.loads(raw) if isinstance(raw, str) else raw
        targets: dict[str, PickExplanationTarget] = {}
        for k, v in (data.get("targets") or {}).items():
            drivers = [PickDriver(**d) for d in (v.get("drivers") or [])]
            targets[k] = PickExplanationTarget(
                method=v.get("method", ""),
                units=v.get("units", ""),
                base_value=v.get("base_value"),
                prediction=v.get("prediction"),
                toward=v.get("toward", ""),
                drivers=drivers,
                note=v.get("note"),
            )
        return PickExplanationPayload(
            served_tier=data.get("served_tier"),
            basis=data.get("basis", "model_reasoning"),
            disclaimer=data.get("disclaimer", ""),
            targets=targets,
        )
    except Exception:
        logger.warning("Could not parse pick_explanation JSON")
        return None


def _top_drivers_for_market(
    expl: PickExplanationPayload | None, market_type: str, n: int = 3
) -> list[PickDriver] | None:
    """Return top-n drivers for the relevant target given the market."""
    if not expl:
        return None
    target_key = "home_win" if market_type == "h2h" else "total_runs"
    target = expl.targets.get(target_key)
    if not target or not target.drivers:
        return None
    return target.drivers[:n]


def _format_game_time_et(game_start_utc: datetime | None) -> str | None:
    if game_start_utc is None:
        return None
    try:
        if game_start_utc.tzinfo is None:
            game_start_utc = game_start_utc.replace(tzinfo=timezone.utc)
        et = game_start_utc.astimezone(_ET)
        return et.strftime("%-I:%M %p ET")
    except Exception:
        return None


def _ai_summary(market_type: str, model_prob: float | None, edge: float | None) -> str:
    mp = round((model_prob or 0) * 100, 1)
    ep = round((edge or 0) * 100, 1)
    sign = "+" if ep >= 0 else ""
    if market_type == "h2h":
        return (
            f"Model assigns {mp}% win probability — "
            f"a {sign}{ep}pp edge over the Bovada closing line."
        )
    return (
        f"Totals model assigns {mp}% probability this game goes over — "
        f"a {sign}{ep}pp edge over the consensus line."
    )


def _build_featured_result(
    r: dict,
    yesterday_obj: "FeaturedYesterday | None",
    is_stale: bool,
    expl: PickExplanationPayload | None = None,
    narrative: str | None = None,
) -> FeaturedPickResponse:
    edge_raw = r.get("EDGE")
    model_prob = r.get("MODEL_PROB")
    market_type = r.get("MARKET_TYPE") or ""
    away = r.get("AWAY_TEAM") or ""
    home = r.get("HOME_TEAM") or ""
    prediction_type = r.get("PREDICTION_TYPE") or ""
    game_date_raw = r.get("GAME_DATE")
    if hasattr(game_date_raw, "isoformat"):
        pick_date: str | None = game_date_raw.isoformat()
    else:
        pick_date = str(game_date_raw) if game_date_raw else None
    top_drivers = _top_drivers_for_market(expl, market_type, n=3)
    served_tier = expl.served_tier if expl else None
    return FeaturedPickResponse(
        game_pk=r.get("GAME_PK"),
        matchup=f"{away} @ {home}",
        game_time_et=_format_game_time_et(r.get("GAME_DATETIME")),
        market_type=market_type,
        edge=round(edge_raw * 100, 2) if edge_raw is not None else None,
        model_prob=model_prob,
        market_prob=r.get("MARKET_PROB"),
        ci_low=r.get("WIN_PROB_CI_LOW"),
        ci_high=r.get("WIN_PROB_CI_HIGH"),
        conviction_label="HIGH CONVICTION",
        ai_summary=_ai_summary(market_type, model_prob, edge_raw),
        yesterday=None if is_stale else yesterday_obj,
        is_stale=is_stale,
        is_preliminary=not is_stale and prediction_type == "morning",
        pick_date=pick_date,
        home_team=home or None,
        away_team=away or None,
        pick_side=r.get("PICK_SIDE"),
        model_narrative=narrative,
        top_drivers=top_drivers,
        served_tier=served_tier,
    )


@router.get("/featured", response_model=FeaturedPickResponse)
def get_featured_pick() -> FeaturedPickResponse:
    today = datetime.now(_ET).date().isoformat()

    # Railway PG is the primary serving path — written by write_serving_store.py after
    # each predict run. No Snowflake query on a PG hit.
    _pg_hit = pg.get_cache("picks/featured", today)
    if _pg_hit is not None and _pg_hit.get("game_pk") is not None:
        try:
            return FeaturedPickResponse(**_pg_hit)
        except Exception:
            logger.warning("PG stale/invalid for picks/featured, re-fetching from Snowflake")

    # S3/in-process cache: only populated once narrative is available
    cached = get_cache(f"picks/featured_{today}.json")
    if cached is not None and cached.get("game_pk") is not None and cached.get("model_narrative") is not None:
        return FeaturedPickResponse(**cached)

    try:
        rows = execute_query(_FEATURED_TODAY_QUERY, params={"today": today})
        yesterday_rows = execute_query(_FEATURED_YESTERDAY_QUERY, params={"today": today})
    except Exception as exc:
        logger.exception("Snowflake query failed for /picks/featured")
        raise HTTPException(status_code=503, detail="Data unavailable") from exc

    yesterday: FeaturedYesterday | None = None
    if yesterday_rows:
        yr = yesterday_rows[0]
        outcome_flag = yr.get("ACTUAL_OUTCOME")
        if outcome_flag is not None:
            away = yr.get("AWAY_TEAM") or ""
            home = yr.get("HOME_TEAM") or ""
            yesterday = FeaturedYesterday(
                matchup=f"{away} @ {home}",
                market_type=yr.get("MARKET_TYPE") or "",
                outcome="Won" if outcome_flag == 1 else "Lost",
            )

    if rows:
        game_pk_for_expl = rows[0].get("GAME_PK")
        expl_payload: PickExplanationPayload | None = None
        narrative_str: str | None = None
        if game_pk_for_expl:
            try:
                expl_rows = execute_query(_EXPLANATION_QUERY, params={"game_pk": game_pk_for_expl})
                if expl_rows:
                    expl_payload = _parse_explanation(expl_rows[0].get("PICK_EXPLANATION"))
                    narrative_str = expl_rows[0].get("PICK_NARRATIVE")
            except Exception:
                logger.warning("Could not load explanation for featured pick game_pk=%s", game_pk_for_expl)
        result = _build_featured_result(rows[0], yesterday, is_stale=False,
                                        expl=expl_payload, narrative=narrative_str)
        # Only cache once explanation data is present; otherwise re-query on next request
        # so the narrative populates as soon as generate_pick_narratives.py runs.
        if narrative_str is not None:
            set_cache(f"picks/featured_{today}.json", result.model_dump(mode="json"))
        return result

    # No picks today — fall back to yesterday's champion pick (don't cache: re-check on next request)
    try:
        stale_rows = execute_query(_FEATURED_STALE_FALLBACK_QUERY, params={"today": today})
    except Exception:
        logger.exception("Snowflake query failed for /picks/featured stale fallback")
        return FeaturedPickResponse(game_pk=None)

    if not stale_rows:
        return FeaturedPickResponse(game_pk=None)

    stale_game_pk = stale_rows[0].get("GAME_PK")
    stale_expl: PickExplanationPayload | None = None
    stale_narrative: str | None = None
    if stale_game_pk:
        try:
            stale_expl_rows = execute_query(_EXPLANATION_QUERY, params={"game_pk": stale_game_pk})
            if stale_expl_rows:
                stale_expl = _parse_explanation(stale_expl_rows[0].get("PICK_EXPLANATION"))
                stale_narrative = stale_expl_rows[0].get("PICK_NARRATIVE")
        except Exception:
            logger.warning("Could not load explanation for stale pick game_pk=%s", stale_game_pk)
    return _build_featured_result(stale_rows[0], None, is_stale=True,
                                  expl=stale_expl, narrative=stale_narrative)


_TODAY_QUERY = f"""
WITH ranked AS (
    SELECT
        p.*,
        g.game_date                                                          AS game_start_utc,
        MAX(p.meta_p_clv_positive) OVER (PARTITION BY p.game_pk)            AS _meta_p,
        MAX(p.meta_ci_low) OVER (PARTITION BY p.game_pk)                    AS _meta_ci_low,
        MAX(p.meta_ci_high) OVER (PARTITION BY p.game_pk)                   AS _meta_ci_high,
        MAX(p.totals_meta_p_clv_positive) OVER (PARTITION BY p.game_pk)     AS _totals_meta_p,
        MAX(p.totals_meta_ci_low) OVER (PARTITION BY p.game_pk)             AS _totals_meta_ci_low,
        MAX(p.totals_meta_ci_high) OVER (PARTITION BY p.game_pk)            AS _totals_meta_ci_high,
        ROW_NUMBER() OVER (
            PARTITION BY p.game_pk
            ORDER BY
                -- Prefer rows that actually carry market data: a degraded run
                -- (post_lineup with NULL odds/abstain decisions) must never shadow
                -- a complete morning row and get filtered out downstream.
                CASE WHEN (p.h2h_market_implied_prob IS NOT NULL OR p.over_prob_consensus IS NOT NULL) THEN 0 ELSE 1 END,
                CASE WHEN p.prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                p.inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions p
    LEFT JOIN baseball_data.betting.stg_statsapi_games g ON g.game_pk = p.game_pk
    WHERE p.game_date = %(today)s
      AND p.prediction_type IN ('post_lineup', 'morning')
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
        b.game_conviction_score,
        b.gate_signals_met,
        b.lineup_confirmed,
        b.win_prob_ci_low,
        b.win_prob_ci_high,
        b.win_prob_ci_width,
        b.home_team,
        b.away_team,
        b.layer4_h2h_decision                        AS pick_side,
        b.game_start_utc,
        b.inserted_at,
        NULL::FLOAT                                  AS model_total_runs,
        NULL::FLOAT                                  AS market_total_line,
        b.prediction_type,
        b._meta_p                                    AS meta_p_clv_positive,
        b._meta_ci_low                               AS meta_ci_low,
        b._meta_ci_high                              AS meta_ci_high
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
        (b.totals_model_prob - b.over_prob_consensus) AS edge,
        b.game_conviction_score,
        b.gate_signals_met,
        b.lineup_confirmed,
        b.win_prob_ci_low,
        b.win_prob_ci_high,
        b.win_prob_ci_width,
        b.home_team,
        b.away_team,
        b.layer4_totals_decision                     AS pick_side,
        b.game_start_utc,
        b.inserted_at,
        b.pred_total_runs                            AS model_total_runs,
        b.total_line_consensus                       AS market_total_line,
        b.prediction_type,
        b._totals_meta_p                             AS meta_p_clv_positive,
        b._totals_meta_ci_low                        AS meta_ci_low,
        b._totals_meta_ci_high                       AS meta_ci_high
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
        b.gate_signals_met,
        b.lineup_confirmed,
        b.win_prob_ci_low,
        b.win_prob_ci_high,
        b.win_prob_ci_width,
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
        ABS(b.totals_model_prob - b.over_prob_consensus) AS edge,  -- prob-points edge (totals_edge is unpopulated upstream)
        b.game_conviction_score,
        b.gate_signals_met,
        b.lineup_confirmed,
        b.win_prob_ci_low,
        b.win_prob_ci_high,
        b.win_prob_ci_width,
        b.home_team,
        b.away_team,
        b.inserted_at,
        clv.clv,
        clv.clv_positive,
        clv.actual_outcome
    FROM base b
    LEFT JOIN baseball_data.betting.mart_clv_labeled_games clv
        ON clv.game_pk = b.game_pk AND clv.market_type = 'totals'
    WHERE b.totals_model_prob IS NOT NULL AND b.over_prob_consensus IS NOT NULL
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
                -- Prefer rows that actually carry market data: a degraded run
                -- (post_lineup with NULL odds/abstain decisions) must never shadow
                -- a complete morning row and get filtered out downstream.
                CASE WHEN (h2h_market_implied_prob IS NOT NULL OR over_prob_consensus IS NOT NULL) THEN 0 ELSE 1 END,
                CASE WHEN prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions
    WHERE game_date = %(today)s
      AND prediction_type IN ('post_lineup', 'morning')
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
        b.game_conviction_score,
        b.lineup_confirmed,
        b.layer4_h2h_decision <> 'abstain'           AS qualified_bet,
        b.home_team,
        b.away_team,
        b.h2h_kelly_fraction                         AS kelly_fraction,
        b.total_line_consensus,
        NULL::FLOAT                                  AS pred_total_runs,
        b.prediction_type
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
        (b.totals_model_prob - b.over_prob_consensus) AS edge,
        b.game_conviction_score,
        b.lineup_confirmed,
        b.layer4_totals_decision <> 'abstain'        AS qualified_bet,
        b.home_team,
        b.away_team,
        b.totals_kelly_fraction                      AS kelly_fraction,
        b.total_line_consensus,
        b.pred_total_runs,
        b.prediction_type
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
                -- Prefer rows that actually carry market data: a degraded run
                -- (post_lineup with NULL odds/abstain decisions) must never shadow
                -- a complete morning row and get filtered out downstream.
                CASE WHEN (h2h_market_implied_prob IS NOT NULL OR over_prob_consensus IS NOT NULL) THEN 0 ELSE 1 END,
                CASE WHEN prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions
    WHERE game_date = %(target_date)s
      AND prediction_type IN ('post_lineup', 'morning')
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
        b.game_conviction_score,
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
        (b.totals_model_prob - b.over_prob_consensus) AS edge,
        b.game_conviction_score,
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

_GAME_QUERY = f"""
WITH ranked AS (
    SELECT
        *,
        MAX(meta_p_clv_positive) OVER (PARTITION BY game_pk)            AS _meta_p,
        MAX(meta_ci_low) OVER (PARTITION BY game_pk)                    AS _meta_ci_low,
        MAX(meta_ci_high) OVER (PARTITION BY game_pk)                   AS _meta_ci_high,
        MAX(totals_meta_p_clv_positive) OVER (PARTITION BY game_pk)     AS _totals_meta_p,
        MAX(totals_meta_ci_low) OVER (PARTITION BY game_pk)             AS _totals_meta_ci_low,
        MAX(totals_meta_ci_high) OVER (PARTITION BY game_pk)            AS _totals_meta_ci_high,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk
            ORDER BY
                -- Prefer rows that actually carry market data: a degraded run
                -- (post_lineup with NULL odds/abstain decisions) must never shadow
                -- a complete morning row and get filtered out downstream.
                CASE WHEN (h2h_market_implied_prob IS NOT NULL OR over_prob_consensus IS NOT NULL) THEN 0 ELSE 1 END,
                CASE WHEN prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                inserted_at DESC
        ) AS _rn
    FROM {_ML_SCHEMA}.daily_model_predictions
    WHERE game_pk = %(game_pk)s
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
        'h2h'                                        AS market_type,
        b.calibrated_win_prob                        AS model_prob,
        b.h2h_market_implied_prob                    AS bovada_devig_prob,
        b.layer4_h2h_edge                            AS edge,
        b.game_conviction_score,
        b.gate_signals_met,
        b.lineup_confirmed,
        b.win_prob_ci_low,
        b.win_prob_ci_high,
        b.win_prob_ci_width,
        b.home_team,
        b.away_team,
        NULLIF(b.layer4_h2h_decision, 'abstain')    AS pick_side,
        b.game_start_utc,
        b.inserted_at,
        b.pred_total_runs                            AS model_total_runs,
        b.total_line_consensus                       AS market_total_line,
        b._meta_p                                    AS meta_p_clv_positive,
        b._meta_ci_low                               AS meta_ci_low,
        b._meta_ci_high                              AS meta_ci_high
    FROM base b
    WHERE b.h2h_market_implied_prob IS NOT NULL
),
totals AS (
    SELECT
        b.game_pk,
        b.game_date,
        'totals'                                     AS market_type,
        b.totals_model_prob                          AS model_prob,
        b.over_prob_consensus                        AS bovada_devig_prob,
        (b.totals_model_prob - b.over_prob_consensus) AS edge,
        b.game_conviction_score,
        b.gate_signals_met,
        b.lineup_confirmed,
        b.win_prob_ci_low,
        b.win_prob_ci_high,
        b.win_prob_ci_width,
        b.home_team,
        b.away_team,
        NULLIF(b.layer4_totals_decision, 'abstain') AS pick_side,
        b.game_start_utc,
        b.inserted_at,
        b.pred_total_runs                            AS model_total_runs,
        b.total_line_consensus                       AS market_total_line,
        b._totals_meta_p                             AS meta_p_clv_positive,
        b._totals_meta_ci_low                        AS meta_ci_low,
        b._totals_meta_ci_high                       AS meta_ci_high
    FROM base b
    WHERE b.over_prob_consensus IS NOT NULL
)
SELECT * FROM h2h
UNION ALL
SELECT * FROM totals
ORDER BY market_type
"""

_GAME_STATUS_QUERY = """
SELECT
    g.abstract_game_state,
    g.home_score,
    g.away_score,
    g.home_team_name,
    g.away_team_name,
    g.home_wins,
    g.home_losses,
    g.away_wins,
    g.away_losses,
    g.home_is_winner,
    g.home_team_id,
    g.away_team_id,
    hp.pythagorean_win_exp_30d AS home_pyth_pct,
    hp.pythagorean_residual_30d AS home_pyth_residual,
    ap.pythagorean_win_exp_30d AS away_pyth_pct,
    ap.pythagorean_residual_30d AS away_pyth_residual
FROM baseball_data.betting.stg_statsapi_games g
LEFT JOIN baseball_data.betting.mart_team_pythagorean_rolling hp
    ON hp.game_pk = g.game_pk AND hp.team_id = g.home_team_id
LEFT JOIN baseball_data.betting.mart_team_pythagorean_rolling ap
    ON ap.game_pk = g.game_pk AND ap.team_id = g.away_team_id
WHERE g.game_pk = %(game_pk)s
LIMIT 1
"""

_STARTERS_QUERY = """
WITH game_meta AS (
    SELECT game_date, YEAR(game_date) AS game_year
    FROM baseball_data.betting.stg_statsapi_games
    WHERE game_pk = %(game_pk)s
    LIMIT 1
),
starters AS (
    SELECT side, probable_pitcher_id, probable_pitcher_name
    FROM baseball_data.betting.stg_statsapi_probable_pitchers
    WHERE game_pk = %(game_pk)s
),
-- Season-to-date stats in the same season as the game, before game date (point-in-time)
current_season AS (
    SELECT
        g.pitcher_id,
        COUNT(*)                                                                             AS starts,
        ROUND(SUM(g.runs_allowed) * 9.0 / NULLIF(SUM(g.innings_pitched), 0), 2)            AS ra9,
        ROUND((SUM(g.walks) + SUM(g.hits_allowed)) / NULLIF(SUM(g.innings_pitched), 0), 2) AS whip,
        ROUND(SUM(g.strikeouts)::FLOAT / NULLIF(SUM(g.batters_faced), 0) * 100, 1)         AS k_pct
    FROM baseball_data.betting.mart_starting_pitcher_game_log g
    CROSS JOIN game_meta gm
    WHERE g.pitcher_id IN (SELECT probable_pitcher_id FROM starters WHERE probable_pitcher_id IS NOT NULL)
      AND g.game_year = gm.game_year
      AND g.game_date < gm.game_date
    GROUP BY g.pitcher_id
),
-- Full prior-season stats — shown as context when current-season sample is sparse
prior_season AS (
    SELECT
        g.pitcher_id,
        COUNT(*)                                                                             AS starts,
        ROUND(SUM(g.runs_allowed) * 9.0 / NULLIF(SUM(g.innings_pitched), 0), 2)            AS ra9,
        ROUND((SUM(g.walks) + SUM(g.hits_allowed)) / NULLIF(SUM(g.innings_pitched), 0), 2) AS whip,
        ROUND(SUM(g.strikeouts)::FLOAT / NULLIF(SUM(g.batters_faced), 0) * 100, 1)         AS k_pct
    FROM baseball_data.betting.mart_starting_pitcher_game_log g
    CROSS JOIN game_meta gm
    WHERE g.pitcher_id IN (SELECT probable_pitcher_id FROM starters WHERE probable_pitcher_id IS NOT NULL)
      AND g.game_year = gm.game_year - 1
    GROUP BY g.pitcher_id
),
-- Last 5 starts before game date — median IP < 2.5 flags opener usage
last5 AS (
    SELECT sub.pitcher_id, MEDIAN(sub.innings_pitched) AS median_ip_last5
    FROM (
        SELECT g.pitcher_id, g.innings_pitched,
               ROW_NUMBER() OVER (PARTITION BY g.pitcher_id ORDER BY g.game_date DESC) AS rn
        FROM baseball_data.betting.mart_starting_pitcher_game_log g
        CROSS JOIN game_meta gm
        WHERE g.pitcher_id IN (SELECT probable_pitcher_id FROM starters WHERE probable_pitcher_id IS NOT NULL)
          AND g.game_date < gm.game_date
    ) sub
    WHERE sub.rn <= 5
    GROUP BY sub.pitcher_id
)
SELECT
    s.side,
    s.probable_pitcher_id,
    s.probable_pitcher_name,
    gm.game_year                                                 AS current_season_year,
    cs.starts                                                    AS current_starts,
    cs.ra9                                                       AS current_ra9,
    cs.whip                                                      AS current_whip,
    cs.k_pct                                                     AS current_k_pct,
    gm.game_year - 1                                             AS prior_season_year,
    ps.starts                                                    AS prior_starts,
    ps.ra9                                                       AS prior_ra9,
    ps.whip                                                      AS prior_whip,
    ps.k_pct                                                     AS prior_k_pct,
    IFF(COALESCE(l5.median_ip_last5, 5.0) < 2.5, TRUE, FALSE)   AS is_opener
FROM starters s
CROSS JOIN game_meta gm
LEFT JOIN current_season cs ON cs.pitcher_id = s.probable_pitcher_id
LEFT JOIN prior_season ps ON ps.pitcher_id = s.probable_pitcher_id
LEFT JOIN last5 l5 ON l5.pitcher_id = s.probable_pitcher_id
"""

_BOVADA_LINES_QUERY = """
WITH pre_game AS (
    SELECT
        o.market_key,
        o.outcome_name,
        o.outcome_price_american,
        o.outcome_point,
        o.is_home_outcome,
        o.ingestion_ts
    FROM baseball_data.betting.mart_odds_outcomes o
    JOIN baseball_data.betting.stg_statsapi_games g
        ON g.official_date = o.commence_date
    JOIN baseball_data.betting.dim_team_name_lookup gh
        ON gh.name_lower = lower(regexp_replace(trim(g.home_team_name), '^G[12] ', ''))
    JOIN baseball_data.betting.dim_team_name_lookup ga
        ON ga.name_lower = lower(regexp_replace(trim(g.away_team_name), '^G[12] ', ''))
    JOIN baseball_data.betting.dim_team_name_lookup oh
        ON oh.name_lower = lower(regexp_replace(trim(o.home_team), '^G[12] ', ''))
       AND oh.team_id = gh.team_id
    JOIN baseball_data.betting.dim_team_name_lookup oa
        ON oa.name_lower = lower(regexp_replace(trim(o.away_team), '^G[12] ', ''))
       AND oa.team_id = ga.team_id
    WHERE g.game_pk = %(game_pk)s
      AND o.bookmaker_key = 'bovada'
      AND o.ingestion_ts::TIMESTAMP_NTZ < g.game_date::TIMESTAMP_NTZ
)
SELECT
    market_key,
    outcome_name,
    outcome_price_american,
    outcome_point,
    is_home_outcome,
    ingestion_ts
FROM pre_game
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY market_key, outcome_name
    ORDER BY ingestion_ts DESC
) = 1
ORDER BY market_key, is_home_outcome DESC
"""

_TEAM_FEATURES_QUERY = f"""
SELECT
    home_off_woba_30d,
    away_off_woba_30d,
    home_off_xwoba_30d,
    away_off_xwoba_30d,
    home_off_runs_per_game_30d,
    away_off_runs_per_game_30d,
    home_starter_xwoba_against_30d,
    away_starter_xwoba_against_30d,
    home_starter_k_pct_30d,
    away_starter_k_pct_30d,
    home_starter_pitcher_hand,
    away_starter_pitcher_hand,
    home_lineup_vs_away_starter_xwoba_adj,
    away_lineup_vs_home_starter_xwoba_adj,
    home_bp_xwoba_against_14d,
    away_bp_xwoba_against_14d,
    home_bp_innings_pitched_14d,
    away_bp_innings_pitched_14d,
    home_days_rest,
    away_days_rest,
    park_run_factor_3yr,
    elo_diff,
    umpire_name,
    ump_k_pct_zscore,
    ump_runs_per_game_zscore,
    ump_run_impact_zscore,
    ump_bb_pct_zscore,
    ump_games_sample
FROM baseball_data.betting_features.feature_pregame_game_features
WHERE game_pk = %(game_pk)s
ORDER BY game_date DESC
LIMIT 1
"""


_LINEUP_QUERY = """
WITH wide AS (
    SELECT *
    FROM baseball_data.betting.stg_statsapi_lineups_wide
    WHERE game_pk = %(game_pk)s
),
slots AS (
    SELECT home_away, official_date, 1 AS slot, slot_1_player_id AS player_id, slot_1_full_name AS player_name, slot_1_position AS position FROM wide
    UNION ALL SELECT home_away, official_date, 2, slot_2_player_id, slot_2_full_name, slot_2_position FROM wide
    UNION ALL SELECT home_away, official_date, 3, slot_3_player_id, slot_3_full_name, slot_3_position FROM wide
    UNION ALL SELECT home_away, official_date, 4, slot_4_player_id, slot_4_full_name, slot_4_position FROM wide
    UNION ALL SELECT home_away, official_date, 5, slot_5_player_id, slot_5_full_name, slot_5_position FROM wide
    UNION ALL SELECT home_away, official_date, 6, slot_6_player_id, slot_6_full_name, slot_6_position FROM wide
    UNION ALL SELECT home_away, official_date, 7, slot_7_player_id, slot_7_full_name, slot_7_position FROM wide
    UNION ALL SELECT home_away, official_date, 8, slot_8_player_id, slot_8_full_name, slot_8_position FROM wide
    UNION ALL SELECT home_away, official_date, 9, slot_9_player_id, slot_9_full_name, slot_9_position FROM wide
),
season_stats AS (
    SELECT
        rs.batter_id,
        rs.ops_std   AS season_ops,
        rs.xwoba_std AS season_xwoba
    FROM baseball_data.betting.mart_batter_rolling_stats rs
    JOIN slots s
        ON  rs.batter_id  = s.player_id
        AND rs.game_year  = YEAR(s.official_date)
        AND rs.game_date  < s.official_date
    QUALIFY ROW_NUMBER() OVER (PARTITION BY rs.batter_id ORDER BY rs.game_date DESC) = 1
)
SELECT
    s.home_away,
    s.slot,
    s.player_id,
    s.player_name,
    s.position,
    st.season_ops,
    st.season_xwoba
FROM slots s
LEFT JOIN season_stats st ON st.batter_id = s.player_id
WHERE s.player_id IS NOT NULL
ORDER BY s.home_away, s.slot
"""

_BOX_SCORE_QUERY = """
WITH pa_end AS (
    SELECT
        batter_id,
        player_name,
        inning_half,
        at_bat_number,
        plate_appearance_event,
        woba_value,
        woba_denom,
        xwoba
    FROM baseball_data.betting.stg_batter_pitches
    WHERE game_pk = %(game_pk)s
      AND woba_denom = 1
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY batter_id, at_bat_number
        ORDER BY pitch_number DESC
    ) = 1
)
SELECT
    batter_id,
    player_name,
    CASE WHEN UPPER(inning_half) = 'TOP' THEN 'away' ELSE 'home' END AS home_away,
    COUNT(*)                                                                                           AS pa,
    SUM(CASE WHEN plate_appearance_event NOT IN (
        'walk','intent_walk','hit_by_pitch','sac_fly','sac_bunt',
        'catcher_interf','sac_fly_double_play'
    ) THEN 1 ELSE 0 END)                                                                               AS ab,
    SUM(CASE WHEN plate_appearance_event IN ('single','double','triple','home_run') THEN 1 ELSE 0 END) AS h,
    SUM(CASE WHEN plate_appearance_event IN ('strikeout','strikeout_double_play') THEN 1 ELSE 0 END)   AS k,
    SUM(CASE WHEN plate_appearance_event IN ('walk','intent_walk') THEN 1 ELSE 0 END)                  AS bb,
    SUM(CASE WHEN plate_appearance_event = 'home_run' THEN 1 ELSE 0 END)                               AS hr,
    ROUND(
        SUM(COALESCE(xwoba, woba_value, 0) * woba_denom) / NULLIF(SUM(woba_denom), 0),
        3
    )                                                                                                   AS xwoba_game
FROM pa_end
GROUP BY batter_id, player_name, inning_half
ORDER BY home_away, batter_id
"""


_WEATHER_QUERY = """
SELECT
    temp_f,
    wind_speed_mph,
    wind_component_mph,
    is_dome,
    weather_observation_type
FROM baseball_data.betting_features.feature_pregame_weather_features
WHERE game_pk = %(game_pk)s
LIMIT 1
"""

_PUBLIC_BETTING_QUERY = """
SELECT
    home_ml_money_pct,
    away_ml_money_pct,
    home_ml_ticket_pct,
    away_ml_ticket_pct,
    over_money_pct,
    under_money_pct,
    over_ticket_pct,
    under_ticket_pct,
    ml_sharp_signal,
    total_sharp_signal
FROM baseball_data.betting_features.feature_pregame_public_betting_features
WHERE game_pk = %(game_pk)s
LIMIT 1
"""

_LINE_MOVEMENT_QUERY = """
SELECT
    open_home_win_prob,
    pregame_home_win_prob,
    h2h_line_movement,
    open_total_line,
    pregame_total_line,
    total_line_movement
FROM baseball_data.betting.mart_odds_line_movement
WHERE game_pk = %(game_pk)s
LIMIT 1
"""

_RECENT_FORM_QUERY = """
WITH game_meta AS (
    SELECT game_date, home_team_id, away_team_id
    FROM baseball_data.betting.stg_statsapi_games
    WHERE game_pk = %(game_pk)s
    LIMIT 1
),
home_recent AS (
    SELECT
        CASE WHEN g.home_team_id = gm.home_team_id THEN g.home_is_winner
             ELSE g.away_is_winner END   AS won,
        ROW_NUMBER() OVER (ORDER BY g.game_date DESC) AS rn
    FROM baseball_data.betting.stg_statsapi_games g
    CROSS JOIN game_meta gm
    WHERE g.abstract_game_state = 'Final'
      AND g.game_date < gm.game_date
      AND YEAR(g.game_date) = YEAR(gm.game_date)
      AND g.home_is_winner IS NOT NULL
      AND (g.home_team_id = gm.home_team_id OR g.away_team_id = gm.home_team_id)
),
away_recent AS (
    SELECT
        CASE WHEN g.home_team_id = gm.away_team_id THEN g.home_is_winner
             ELSE g.away_is_winner END   AS won,
        ROW_NUMBER() OVER (ORDER BY g.game_date DESC) AS rn
    FROM baseball_data.betting.stg_statsapi_games g
    CROSS JOIN game_meta gm
    WHERE g.abstract_game_state = 'Final'
      AND g.game_date < gm.game_date
      AND YEAR(g.game_date) = YEAR(gm.game_date)
      AND g.home_is_winner IS NOT NULL
      AND (g.home_team_id = gm.away_team_id OR g.away_team_id = gm.away_team_id)
)
SELECT 'home' AS team_side,
    SUM(CASE WHEN rn <= 5  AND won = TRUE  THEN 1 ELSE 0 END) AS l5_wins,
    SUM(CASE WHEN rn <= 5  AND won = FALSE THEN 1 ELSE 0 END) AS l5_losses,
    SUM(CASE WHEN rn <= 5  THEN 1 ELSE 0 END)                 AS l5_games,
    SUM(CASE WHEN rn <= 10 AND won = TRUE  THEN 1 ELSE 0 END) AS l10_wins,
    SUM(CASE WHEN rn <= 10 AND won = FALSE THEN 1 ELSE 0 END) AS l10_losses,
    SUM(CASE WHEN rn <= 10 THEN 1 ELSE 0 END)                 AS l10_games
FROM home_recent WHERE rn <= 10
UNION ALL
SELECT 'away' AS team_side,
    SUM(CASE WHEN rn <= 5  AND won = TRUE  THEN 1 ELSE 0 END) AS l5_wins,
    SUM(CASE WHEN rn <= 5  AND won = FALSE THEN 1 ELSE 0 END) AS l5_losses,
    SUM(CASE WHEN rn <= 5  THEN 1 ELSE 0 END)                 AS l5_games,
    SUM(CASE WHEN rn <= 10 AND won = TRUE  THEN 1 ELSE 0 END) AS l10_wins,
    SUM(CASE WHEN rn <= 10 AND won = FALSE THEN 1 ELSE 0 END) AS l10_losses,
    SUM(CASE WHEN rn <= 10 THEN 1 ELSE 0 END)                 AS l10_games
FROM away_recent WHERE rn <= 10
"""

# Point-in-time H2H computed directly from game results before the current game date.
# Uses home_team_id/away_team_id from the game itself so no abbreviation params needed.
_H2H_QUERY = """
WITH game_meta AS (
    SELECT game_date, home_team_id, away_team_id
    FROM baseball_data.betting.stg_statsapi_games
    WHERE game_pk = %(game_pk)s LIMIT 1
),
h2h_games AS (
    SELECT
        CASE WHEN g.home_team_id = gm.home_team_id THEN g.home_is_winner
             ELSE g.away_is_winner END AS home_team_won,
        g.home_score + g.away_score   AS total_runs
    FROM baseball_data.betting.stg_statsapi_games g
    CROSS JOIN game_meta gm
    WHERE g.abstract_game_state = 'Final'
      AND YEAR(g.game_date) = YEAR(gm.game_date)
      AND g.game_date < gm.game_date
      AND g.home_is_winner IS NOT NULL
      AND (
        (g.home_team_id = gm.home_team_id AND g.away_team_id = gm.away_team_id)
        OR (g.home_team_id = gm.away_team_id AND g.away_team_id = gm.home_team_id)
      )
)
SELECT
    SUM(CASE WHEN home_team_won = TRUE  THEN 1 ELSE 0 END) AS home_wins,
    SUM(CASE WHEN home_team_won = FALSE THEN 1 ELSE 0 END) AS away_wins,
    COUNT(*)                                                AS games_played,
    ROUND(AVG(total_runs), 2)                              AS avg_total_runs
FROM h2h_games
"""

# Null-guard k%/bb% z-scores — source k_pct/bb_pct are NULL in umpire_game_log
# (UmpScorecards API doesn't provide pitch-call breakdown), so the feature pipeline
# defaults those z-scores to 0.0. Expose NULL so the UI shows "n/a" instead of
# a misleading "avg".
_UMPIRE_QUERY = """
SELECT
    umpire_name,
    ump_games_sample,
    CASE WHEN ump_k_pct_trailing  IS NULL THEN NULL ELSE ump_k_pct_zscore  END AS ump_k_pct_zscore,
    CASE WHEN ump_bb_pct_trailing IS NULL THEN NULL ELSE ump_bb_pct_zscore END AS ump_bb_pct_zscore,
    ump_runs_per_game_zscore,
    ump_run_impact_zscore
FROM baseball_data.betting_features.feature_pregame_umpire_features
WHERE game_pk = %(game_pk)s
ORDER BY game_pk DESC
LIMIT 1
"""


def _pipeline_status(last_updated_at: datetime | None) -> str:
    if last_updated_at is None:
        return "no_predictions"
    age_hours = (datetime.now(timezone.utc) - last_updated_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
    return "ok" if age_hours < 6 else "stale"


def _apply_portfolio_filter(result: "TodayPicksResponse", user_id: str) -> "TodayPicksResponse":
    """Filter a TodayPicksResponse picks list by the user's portfolio preferences."""
    try:
        prefs = pg.get_user_portfolio(user_id)
        min_ev = prefs.get("min_ev_threshold") or 0.02
        markets = prefs.get("markets") or ["h2h", "totals"]
        if isinstance(markets, str):
            import json as _json
            markets = _json.loads(markets)
        filtered = [
            p for p in result.picks
            if p.market_type in markets and (p.edge is None or p.edge >= min_ev)
        ]
        return TodayPicksResponse(picks=filtered, data_quality=result.data_quality)
    except Exception:
        logger.warning("Portfolio filter failed for user=%s — returning unfiltered", user_id)
        return result


@router.get("/today", response_model=TodayPicksResponse)
def get_picks_today(
    apply_portfolio: bool = Query(False, description="Filter picks by the authenticated user's portfolio preferences"),
    user_id: str | None = Depends(get_optional_user_id),
    date: str | None = Query(None, description="YYYY-MM-DD; defaults to ET today. Pass the client's local date to avoid midnight timezone seams."),
) -> TodayPicksResponse:
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
            today = date
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    else:
        today = datetime.now(_ET).date().isoformat()

    # PG primary read path (A2.12)
    pg_hit = pg.get_cache("picks/today", today)
    if pg_hit is not None:
        try:
            result = TodayPicksResponse(**pg_hit)
            if apply_portfolio and user_id:
                result = _apply_portfolio_filter(result, user_id)
            return result
        except Exception:
            logger.warning("PG picks/today invalid — falling through")

    # S3 secondary
    cached = get_cache("picks/today.json")
    if cached is not None:
        try:
            result = TodayPicksResponse(**cached)
            if apply_portfolio and user_id:
                result = _apply_portfolio_filter(result, user_id)
            return result
        except Exception:
            pass

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
            gate_signals_met=r.get("GATE_SIGNALS_MET"),
            win_prob_ci_low=r.get("WIN_PROB_CI_LOW"),
            win_prob_ci_high=r.get("WIN_PROB_CI_HIGH"),
            win_prob_ci_width=r.get("WIN_PROB_CI_WIDTH"),
            meta_p_clv_positive=r.get("META_P_CLV_POSITIVE"),
            meta_ci_low=r.get("META_CI_LOW"),
            meta_ci_high=r.get("META_CI_HIGH"),
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

    is_preliminary = bool(rows) and any(
        (r.get("PREDICTION_TYPE") or "") == "morning" for r in rows
    )
    result = TodayPicksResponse(picks=picks, data_quality=data_quality, is_preliminary=is_preliminary)
    payload = result.model_dump(mode="json")
    pg.set_cache("picks/today", today, payload)
    set_cache("picks/today.json", payload)
    if apply_portfolio and user_id:
        result = _apply_portfolio_filter(result, user_id)
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
            gate_signals_met=r.get("GATE_SIGNALS_MET"),
            win_prob_ci_low=r.get("WIN_PROB_CI_LOW"),
            win_prob_ci_high=r.get("WIN_PROB_CI_HIGH"),
            win_prob_ci_width=r.get("WIN_PROB_CI_WIDTH"),
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
    today_str = datetime.now(_ET).date().isoformat()
    if date and date != today_str:
        try:
            datetime.strptime(date, "%Y-%m-%d")
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
        pg_hit = pg.get_cache("picks/ev", today_str)
        if pg_hit is not None:
            try:
                return EVPicksResponse(**pg_hit)
            except Exception:
                logger.warning("PG picks/ev invalid — falling through")
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
    is_preliminary = bool(rows) and any(
        (r.get("PREDICTION_TYPE") or "") == "morning" for r in rows
    )
    result = EVPicksResponse(picks=picks, total=len(picks), is_preliminary=is_preliminary)
    if cache_key:
        payload = result.model_dump(mode="json")
        pg.set_cache("picks/ev", today_str, payload)
        set_cache(cache_key, payload)
    return result


@router.get("/{game_pk}/detail", response_model=GameDetailResponse)
def get_game_detail(game_pk: int) -> GameDetailResponse:
    params = {"game_pk": game_pk}

    # Cache check — PG primary, then S3 (permanent for Final games, date-scoped for live)
    from datetime import date as _date
    _today_str = _date.today().isoformat()
    _game_pg_key = f"picks/game/{game_pk}"
    _game_cache_key = f"picks/game/{game_pk}.json"

    _pg_cached = pg.get_cache(_game_pg_key, _today_str)
    if _pg_cached is not None and _pg_cached.get("picks"):
        try:
            return GameDetailResponse(**_pg_cached)
        except Exception:
            logger.warning("PG stale/invalid for game_pk=%s, re-fetching", game_pk)

    _cached = get_cache(_game_cache_key, permanent=True) or get_cache(_game_cache_key)
    if _cached is not None and _cached.get("picks"):
        try:
            return GameDetailResponse(**_cached)
        except Exception:
            logger.warning("Stale/invalid S3 cache for game_pk=%s, re-fetching", game_pk)

    # Base picks
    try:
        pick_rows = execute_query(_GAME_QUERY, params=params)
    except Exception as exc:
        logger.exception("Snowflake query failed for /picks/%s/detail (picks)", game_pk)
        raise HTTPException(status_code=503, detail="Data unavailable") from exc

    if not pick_rows:
        raise HTTPException(status_code=404, detail="Game not found")

    picks = [
        Pick(
            game_pk=r["GAME_PK"],
            game_date=r["GAME_DATE"],
            market_type=r["MARKET_TYPE"],
            model_prob=r.get("MODEL_PROB"),
            bovada_devig_prob=r.get("BOVADA_DEVIG_PROB"),
            edge=r.get("EDGE"),
            game_conviction_score=r.get("GAME_CONVICTION_SCORE"),
            gate_signals_met=r.get("GATE_SIGNALS_MET"),
            win_prob_ci_low=r.get("WIN_PROB_CI_LOW"),
            win_prob_ci_high=r.get("WIN_PROB_CI_HIGH"),
            win_prob_ci_width=r.get("WIN_PROB_CI_WIDTH"),
            meta_p_clv_positive=r.get("META_P_CLV_POSITIVE"),
            meta_ci_low=r.get("META_CI_LOW"),
            meta_ci_high=r.get("META_CI_HIGH"),
            lineup_confirmed=r.get("LINEUP_CONFIRMED"),
            home_team=r.get("HOME_TEAM"),
            away_team=r.get("AWAY_TEAM"),
            pick_side=r.get("PICK_SIDE"),
            game_start_utc=r.get("GAME_START_UTC"),
            model_total_runs=r.get("MODEL_TOTAL_RUNS"),
            market_total_line=r.get("MARKET_TOTAL_LINE"),
            predicted_at=r.get("INSERTED_AT"),
        )
        for r in pick_rows
    ]

    # Story 30.15 — pick explanation + narrative
    pick_explanation: PickExplanationPayload | None = None
    pick_narrative: str | None = None
    try:
        expl_rows = execute_query(_EXPLANATION_QUERY, params=params)
        if expl_rows:
            pick_explanation = _parse_explanation(expl_rows[0].get("PICK_EXPLANATION"))
            pick_narrative = expl_rows[0].get("PICK_NARRATIVE")
    except Exception:
        logger.warning("Could not load pick explanation for game_pk=%s", game_pk)

    # Game status + full team names + pre-game records
    game_score: GameScore | None = None
    home_team_name: str | None = None
    away_team_name: str | None = None
    try:
        status_rows = execute_query(_GAME_STATUS_QUERY, params=params)
        if status_rows:
            sr = status_rows[0]
            state = str(sr.get("ABSTRACT_GAME_STATE") or "Preview")

            def _int(key: str) -> int | None:
                v = sr.get(key)
                return int(v) if v is not None else None

            hw_raw = _int("HOME_WINS")
            hl_raw = _int("HOME_LOSSES")
            aw_raw = _int("AWAY_WINS")
            al_raw = _int("AWAY_LOSSES")

            # StatsAPI stores post-game record for Final games; subtract result to recover pre-game
            if state == "Final" and hw_raw is not None:
                home_won = bool(sr.get("HOME_IS_WINNER"))
                hw = hw_raw - (1 if home_won else 0)
                hl = hl_raw - (0 if home_won else 1) if hl_raw is not None else None
                aw = aw_raw - (0 if home_won else 1) if aw_raw is not None else None
                al = al_raw - (1 if home_won else 0) if al_raw is not None else None
            else:
                hw, hl, aw, al = hw_raw, hl_raw, aw_raw, al_raw

            def _flt(key: str) -> float | None:
                v = sr.get(key)
                try:
                    return float(v) if v is not None else None
                except (TypeError, ValueError):
                    return None

            game_score = GameScore(
                home_score=_int("HOME_SCORE"),
                away_score=_int("AWAY_SCORE"),
                status=state if state in ("Live", "Final") else "Preview",
                home_wins=hw,
                home_losses=hl,
                away_wins=aw,
                away_losses=al,
                home_pyth_pct=_flt("HOME_PYTH_PCT"),
                home_pyth_residual=_flt("HOME_PYTH_RESIDUAL"),
                away_pyth_pct=_flt("AWAY_PYTH_PCT"),
                away_pyth_residual=_flt("AWAY_PYTH_RESIDUAL"),
            )
            home_team_name = sr.get("HOME_TEAM_NAME")
            away_team_name = sr.get("AWAY_TEAM_NAME")
    except Exception:
        logger.warning("Could not load game status for game_pk=%s", game_pk)

    # Probable starters — current-season + prior-season stats
    starters: GameStarters | None = None
    try:
        starter_rows = execute_query(_STARTERS_QUERY, params=params)
        home_sp: StarterStats | None = None
        away_sp: StarterStats | None = None
        for row in starter_rows:
            sp = StarterStats(
                pitcher_id=row.get("PROBABLE_PITCHER_ID"),
                name=row.get("PROBABLE_PITCHER_NAME"),
                is_opener=bool(row.get("IS_OPENER", False)),
                season=row.get("CURRENT_SEASON_YEAR"),
                starts=row.get("CURRENT_STARTS"),
                ra9=row.get("CURRENT_RA9"),
                whip=row.get("CURRENT_WHIP"),
                k_pct=row.get("CURRENT_K_PCT"),
                prior_season=row.get("PRIOR_SEASON_YEAR"),
                prior_starts=row.get("PRIOR_STARTS"),
                prior_ra9=row.get("PRIOR_RA9"),
                prior_whip=row.get("PRIOR_WHIP"),
                prior_k_pct=row.get("PRIOR_K_PCT"),
            )
            if str(row.get("SIDE", "")).lower() == "home":
                home_sp = sp
            else:
                away_sp = sp
        if home_sp or away_sp:
            starters = GameStarters(home=home_sp, away=away_sp)
    except Exception:
        logger.warning("Could not load starters for game_pk=%s", game_pk)

    # Bovada lines
    bovada_lines: BovadaLines | None = None
    try:
        bov_rows = execute_query(_BOVADA_LINES_QUERY, params=params)
        h2h_rows = [r for r in bov_rows if str(r.get("MARKET_KEY", "")).lower() == "h2h"]
        tot_rows = [r for r in bov_rows if str(r.get("MARKET_KEY", "")).lower() == "totals"]

        bov_h2h: BovadaH2H | None = None
        if h2h_rows:
            home_r = next((r for r in h2h_rows if r.get("IS_HOME_OUTCOME")), None)
            away_r = next((r for r in h2h_rows if not r.get("IS_HOME_OUTCOME")), None)
            snap = str(max(r["INGESTION_TS"] for r in h2h_rows)) if h2h_rows else None
            bov_h2h = BovadaH2H(
                home_american=int(home_r["OUTCOME_PRICE_AMERICAN"]) if home_r and home_r.get("OUTCOME_PRICE_AMERICAN") is not None else None,
                away_american=int(away_r["OUTCOME_PRICE_AMERICAN"]) if away_r and away_r.get("OUTCOME_PRICE_AMERICAN") is not None else None,
                snapshot_utc=snap,
            )

        bov_totals: BovadaTotals | None = None
        if tot_rows:
            over_r = next((r for r in tot_rows if str(r.get("OUTCOME_NAME", "")).lower() == "over"), None)
            under_r = next((r for r in tot_rows if str(r.get("OUTCOME_NAME", "")).lower() == "under"), None)
            snap = str(max(r["INGESTION_TS"] for r in tot_rows)) if tot_rows else None
            bov_totals = BovadaTotals(
                line=float(over_r["OUTCOME_POINT"]) if over_r and over_r.get("OUTCOME_POINT") is not None else None,
                over_american=int(over_r["OUTCOME_PRICE_AMERICAN"]) if over_r and over_r.get("OUTCOME_PRICE_AMERICAN") is not None else None,
                under_american=int(under_r["OUTCOME_PRICE_AMERICAN"]) if under_r and under_r.get("OUTCOME_PRICE_AMERICAN") is not None else None,
                snapshot_utc=snap,
            )

        if bov_h2h or bov_totals:
            bovada_lines = BovadaLines(h2h=bov_h2h, totals=bov_totals)
    except Exception:
        logger.warning("Could not load Bovada lines for game_pk=%s", game_pk)

    # Team performance features
    team_features: GamePerfFeatures | None = None
    try:
        feat_rows = execute_query(_TEAM_FEATURES_QUERY, params=params)
        if feat_rows:
            fr = feat_rows[0]

            def _f(key: str) -> float | None:
                val = fr.get(key.upper())
                if val is None:
                    return None
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return None

            home_perf = TeamPerfStats(
                off_woba_30d=_f("home_off_woba_30d"),
                off_xwoba_30d=_f("home_off_xwoba_30d"),
                off_runs_per_game_30d=_f("home_off_runs_per_game_30d"),
                starter_xwoba_against_30d=_f("home_starter_xwoba_against_30d"),
                starter_k_pct_30d=_f("home_starter_k_pct_30d"),
                starter_hand=fr.get("HOME_STARTER_PITCHER_HAND"),
                lineup_vs_sp_xwoba_adj=_f("home_lineup_vs_away_starter_xwoba_adj"),
                bp_xwoba_against_14d=_f("home_bp_xwoba_against_14d"),
                bp_innings_pitched_14d=_f("home_bp_innings_pitched_14d"),
                days_rest=_f("home_days_rest"),
            )
            away_perf = TeamPerfStats(
                off_woba_30d=_f("away_off_woba_30d"),
                off_xwoba_30d=_f("away_off_xwoba_30d"),
                off_runs_per_game_30d=_f("away_off_runs_per_game_30d"),
                starter_xwoba_against_30d=_f("away_starter_xwoba_against_30d"),
                starter_k_pct_30d=_f("away_starter_k_pct_30d"),
                starter_hand=fr.get("AWAY_STARTER_PITCHER_HAND"),
                lineup_vs_sp_xwoba_adj=_f("away_lineup_vs_home_starter_xwoba_adj"),
                bp_xwoba_against_14d=_f("away_bp_xwoba_against_14d"),
                bp_innings_pitched_14d=_f("away_bp_innings_pitched_14d"),
                days_rest=_f("away_days_rest"),
            )
            team_features = GamePerfFeatures(
                home=home_perf,
                away=away_perf,
                park_run_factor=_f("park_run_factor_3yr"),
                elo_diff=_f("elo_diff"),
            )

    except Exception:
        logger.warning("Could not load team features for game_pk=%s", game_pk)

    # Umpire — sourced from dedicated umpire features table so k%/bb% nulls are preserved
    umpire: UmpireInfo | None = None
    try:
        ump_rows = execute_query(_UMPIRE_QUERY, params=params)
        if ump_rows:
            ur = ump_rows[0]
            def _uf(key: str) -> float | None:
                val = ur.get(key.upper())
                if val is None:
                    return None
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return None
            ump_sample_raw = ur.get("UMP_GAMES_SAMPLE")
            umpire = UmpireInfo(
                name=ur.get("UMPIRE_NAME"),
                k_pct_zscore=_uf("ump_k_pct_zscore"),
                runs_per_game_zscore=_uf("ump_runs_per_game_zscore"),
                run_impact_zscore=_uf("ump_run_impact_zscore"),
                bb_pct_zscore=_uf("ump_bb_pct_zscore"),
                games_sample=int(ump_sample_raw) if ump_sample_raw is not None else None,
            )
    except Exception:
        logger.warning("Could not load umpire data for game_pk=%s", game_pk)

    # Weather
    weather: WeatherInfo | None = None
    try:
        wx_rows = execute_query(_WEATHER_QUERY, params=params)
        if wx_rows:
            wr = wx_rows[0]
            weather = WeatherInfo(
                temp_f=float(wr["TEMP_F"]) if wr.get("TEMP_F") is not None else None,
                wind_speed_mph=float(wr["WIND_SPEED_MPH"]) if wr.get("WIND_SPEED_MPH") is not None else None,
                wind_component_mph=float(wr["WIND_COMPONENT_MPH"]) if wr.get("WIND_COMPONENT_MPH") is not None else None,
                is_dome=bool(wr.get("IS_DOME", False)),
                observation_type=wr.get("WEATHER_OBSERVATION_TYPE"),
            )
    except Exception:
        logger.warning("Could not load weather for game_pk=%s", game_pk)

    # Public betting action
    public_betting: PublicBetting | None = None
    try:
        pb_rows = execute_query(_PUBLIC_BETTING_QUERY, params=params)
        if pb_rows:
            pb = pb_rows[0]

            def _pf(key: str) -> float | None:
                v = pb.get(key.upper())
                try:
                    return float(v) if v is not None else None
                except (TypeError, ValueError):
                    return None

            public_betting = PublicBetting(
                home_ml_money_pct=_pf("home_ml_money_pct"),
                away_ml_money_pct=_pf("away_ml_money_pct"),
                home_ml_ticket_pct=_pf("home_ml_ticket_pct"),
                away_ml_ticket_pct=_pf("away_ml_ticket_pct"),
                over_money_pct=_pf("over_money_pct"),
                under_money_pct=_pf("under_money_pct"),
                over_ticket_pct=_pf("over_ticket_pct"),
                under_ticket_pct=_pf("under_ticket_pct"),
                ml_sharp_signal=_pf("ml_sharp_signal"),
                total_sharp_signal=_pf("total_sharp_signal"),
            )
    except Exception:
        logger.warning("Could not load public betting for game_pk=%s", game_pk)

    # Line movement
    line_movement: LineMovement | None = None
    try:
        lm_rows = execute_query(_LINE_MOVEMENT_QUERY, params=params)
        if lm_rows:
            lm = lm_rows[0]

            def _lf(key: str) -> float | None:
                v = lm.get(key.upper())
                try:
                    return float(v) if v is not None else None
                except (TypeError, ValueError):
                    return None

            line_movement = LineMovement(
                open_home_win_prob=_lf("open_home_win_prob"),
                pregame_home_win_prob=_lf("pregame_home_win_prob"),
                h2h_line_movement=_lf("h2h_line_movement"),
                open_total_line=_lf("open_total_line"),
                pregame_total_line=_lf("pregame_total_line"),
                total_line_movement=_lf("total_line_movement"),
            )
    except Exception:
        logger.warning("Could not load line movement for game_pk=%s", game_pk)

    # Recent form + H2H
    game_context: GameContext | None = None
    try:
        form_rows = execute_query(_RECENT_FORM_QUERY, params=params)
        home_form: TeamRecentForm | None = None
        away_form: TeamRecentForm | None = None
        for row in form_rows:
            form = TeamRecentForm(
                l5_wins=int(row["L5_WINS"]) if row.get("L5_WINS") is not None else None,
                l5_losses=int(row["L5_LOSSES"]) if row.get("L5_LOSSES") is not None else None,
                l5_games=int(row["L5_GAMES"]) if row.get("L5_GAMES") is not None else None,
                l10_wins=int(row["L10_WINS"]) if row.get("L10_WINS") is not None else None,
                l10_losses=int(row["L10_LOSSES"]) if row.get("L10_LOSSES") is not None else None,
                l10_games=int(row["L10_GAMES"]) if row.get("L10_GAMES") is not None else None,
            )
            if str(row.get("TEAM_SIDE", "")).lower() == "home":
                home_form = form
            else:
                away_form = form

        # H2H computed point-in-time from stg_statsapi_games (game_pk drives date filter)
        h2h: H2HRecord | None = None
        h2h_rows = execute_query(_H2H_QUERY, params=params)
        if h2h_rows:
            hr = h2h_rows[0]
            gp = hr.get("GAMES_PLAYED")
            if gp is not None and int(gp) > 0:
                h2h = H2HRecord(
                    home_wins=int(hr["HOME_WINS"]) if hr.get("HOME_WINS") is not None else None,
                    away_wins=int(hr["AWAY_WINS"]) if hr.get("AWAY_WINS") is not None else None,
                    games_played=int(gp),
                    avg_total_runs=float(hr["AVG_TOTAL_RUNS"]) if hr.get("AVG_TOTAL_RUNS") is not None else None,
                )

        if home_form or away_form or h2h:
            game_context = GameContext(home_form=home_form, away_form=away_form, h2h=h2h)
    except Exception:
        logger.warning("Could not load game context for game_pk=%s", game_pk)

    # Batting lineups (always) + box score (completed games only)
    lineups: GameLineups | None = None
    try:
        lineup_rows = execute_query(_LINEUP_QUERY, params=params)

        # Build a box-score lookup keyed by batter_id if the game is final
        box_score_map: dict[int, dict] = {}
        if game_score and game_score.status == "Final":
            try:
                bs_rows = execute_query(_BOX_SCORE_QUERY, params=params)
                for bs in bs_rows:
                    bid = bs.get("BATTER_ID")
                    if bid is not None:
                        box_score_map[int(bid)] = bs
            except Exception:
                logger.warning("Could not load box score for game_pk=%s", game_pk)

        if lineup_rows:
            home_players: list[LineupPlayer] = []
            away_players: list[LineupPlayer] = []
            for row in lineup_rows:
                pid = row.get("PLAYER_ID")
                bs = box_score_map.get(int(pid)) if pid is not None else None
                player = LineupPlayer(
                    slot=int(row["SLOT"]),
                    player_id=int(pid) if pid is not None else None,
                    player_name=row.get("PLAYER_NAME"),
                    position=row.get("POSITION"),
                    season_ops=float(row["SEASON_OPS"]) if row.get("SEASON_OPS") is not None else None,
                    season_xwoba=float(row["SEASON_XWOBA"]) if row.get("SEASON_XWOBA") is not None else None,
                    game_pa=int(bs["PA"]) if bs and bs.get("PA") is not None else None,
                    game_ab=int(bs["AB"]) if bs and bs.get("AB") is not None else None,
                    game_h=int(bs["H"]) if bs and bs.get("H") is not None else None,
                    game_k=int(bs["K"]) if bs and bs.get("K") is not None else None,
                    game_bb=int(bs["BB"]) if bs and bs.get("BB") is not None else None,
                    game_hr=int(bs["HR"]) if bs and bs.get("HR") is not None else None,
                    game_xwoba=float(bs["XWOBA_GAME"]) if bs and bs.get("XWOBA_GAME") is not None else None,
                )
                if str(row.get("HOME_AWAY", "")).lower() == "home":
                    home_players.append(player)
                else:
                    away_players.append(player)
            if home_players or away_players:
                lineups = GameLineups(home=home_players, away=away_players)
    except Exception:
        logger.warning("Could not load lineups for game_pk=%s", game_pk)

    result = GameDetailResponse(
        picks=picks,
        total=len(picks),
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        game_score=game_score,
        starters=starters,
        bovada_lines=bovada_lines,
        team_features=team_features,
        lineups=lineups,
        weather=weather,
        public_betting=public_betting,
        line_movement=line_movement,
        umpire=umpire,
        game_context=game_context,
        pick_explanation=pick_explanation,
        pick_narrative=pick_narrative,
    )

    # Write to cache: Final games are immutable → always permanent.
    # Explanation presence does not gate caching; if explanation is backfilled later the
    # permanent cache row is simply overwritten on the next request that misses.
    _is_final = game_score is not None and game_score.status == "Final"
    _payload = result.model_dump(mode="json")
    pg.set_cache(_game_pg_key, _today_str, _payload, is_permanent=_is_final)
    set_cache(_game_cache_key, _payload, permanent=_is_final)

    return result


@router.get("/{game_pk}/odds-comparison", response_model=BookOddsComparison)
def get_odds_comparison(game_pk: int) -> BookOddsComparison:
    """A0.4.32 — Per-book odds comparison for a game.

    Returns all six books (Pinnacle, BetMGM, Caesars, FanDuel, DraftKings, Bovada)
    in one payload for both h2h and totals markets. Model EV / edge / de-vigged market %
    are pre-computed server-side. Pinnacle is the sharp low-vig reference anchor.

    This is a market transparency tool — our h2h/totals models have no demonstrated
    market edge, so EVs are informational only. All bets are manual.
    """
    _pg_key = f"picks/book-odds/{game_pk}"

    # Book-odds are "latest available" — use get_cache_latest so blobs written for a prior
    # date (e.g. during backfill or --date testing) are still served correctly.
    _pg_cached = pg.get_cache_latest(_pg_key)
    if _pg_cached is not None and (_pg_cached.get("h2h") or _pg_cached.get("totals")):
        try:
            return BookOddsComparison(**_pg_cached)
        except Exception:
            logger.warning("PG book-odds invalid for game_pk=%s, returning empty", game_pk)

    # If no PG data yet (book-odds write hasn't run), return an empty shell so
    # the frontend can display gracefully. Do NOT query Snowflake live at request time.
    logger.info("No book-odds cache for game_pk=%s — returning empty payload", game_pk)
    return BookOddsComparison(game_pk=game_pk)


@router.get("/{game_pk}", response_model=GamePicksResponse)
def get_pick_by_game_pk(game_pk: int) -> GamePicksResponse:
    try:
        rows = execute_query(_GAME_QUERY, params={"game_pk": game_pk})
    except Exception as exc:
        logger.exception("Snowflake query failed for /picks/%s", game_pk)
        raise HTTPException(status_code=503, detail="Data unavailable") from exc

    if not rows:
        raise HTTPException(status_code=404, detail="Game not found")

    picks = [
        Pick(
            game_pk=r["GAME_PK"],
            game_date=r["GAME_DATE"],
            market_type=r["MARKET_TYPE"],
            model_prob=r.get("MODEL_PROB"),
            bovada_devig_prob=r.get("BOVADA_DEVIG_PROB"),
            edge=r.get("EDGE"),
            game_conviction_score=r.get("GAME_CONVICTION_SCORE"),
            gate_signals_met=r.get("GATE_SIGNALS_MET"),
            win_prob_ci_low=r.get("WIN_PROB_CI_LOW"),
            win_prob_ci_high=r.get("WIN_PROB_CI_HIGH"),
            win_prob_ci_width=r.get("WIN_PROB_CI_WIDTH"),
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
    return GamePicksResponse(picks=picks, total=len(picks))
