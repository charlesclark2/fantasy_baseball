"""write_serving_store.py
-----------------------
Dagster write-path: queries Snowflake after predict_today_morning completes,
builds the same JSON payloads FastAPI serves, and writes them to the Railway
PostgreSQL serving store (api_cache + daily_picks tables).

Also writes to S3 (same as write_api_cache.py) during the transition period.
Once PG has been stable for 2+ weeks, the S3 path can be deprecated.

Called by write_serving_store_op in pipeline/ops/daily_ingestion_ops.py.

SQL mirrors:
  - picks/today + picks/ev + picks/history + performance/summary:
      write_api_cache.py (kept in sync manually; picks.py is the source of truth
      for game-detail SQL)
  - game detail (12 queries per game batch):
      app/backend/routers/picks.py _*_QUERY constants

Env vars required:
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH  (preferred)  or  SNOWFLAKE_PRIVATE_KEY (PEM/base64)
    DATABASE_URL                (Railway PG connection string)
    CACHE_BUCKET                (S3 bucket name; optional — skipped if not set)

Exits 0 on full success, 1 if any write fails.
"""

from __future__ import annotations

import base64
import decimal
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone

import boto3
import psycopg2
import psycopg2.extras
import snowflake.connector

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)


# ── Snowflake connection ─────────────────────────────────────────────────────

def _load_private_key() -> bytes:
    pk_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if pk_path:
        with open(pk_path, "rb") as fh:
            pem_bytes = fh.read()
    else:
        key_val = os.environ.get("SNOWFLAKE_PRIVATE_KEY", "").strip()
        if not key_val:
            raise RuntimeError("Neither SNOWFLAKE_PRIVATE_KEY_PATH nor SNOWFLAKE_PRIVATE_KEY is set")
        if not key_val.startswith("-----"):
            key_val = base64.b64decode(key_val).decode("utf-8")
        pem_bytes = key_val.encode("utf-8")
    p_key = serialization.load_pem_private_key(pem_bytes, password=None, backend=default_backend())
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _sf_connect() -> snowflake.connector.SnowflakeConnection:
    kwargs = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database="baseball_data",
        private_key=_load_private_key(),
    )
    role = os.environ.get("SNOWFLAKE_ROLE")
    if role:
        kwargs["role"] = role
    return snowflake.connector.connect(**kwargs)


def _sf_query(conn: snowflake.connector.SnowflakeConnection, sql: str, params: dict | None = None) -> list[dict]:
    cur = conn.cursor(snowflake.connector.DictCursor)
    cur.execute(sql, params)
    return cur.fetchall()


def _sf_query_batch(conn, sql_template: str, game_pks: list[int]) -> list[dict]:
    """Runs sql_template with {game_pk_list} replaced by the int list. Safe: game_pks are DB integers."""
    if not game_pks:
        return []
    gp_list = ",".join(str(g) for g in game_pks)
    cur = conn.cursor(snowflake.connector.DictCursor)
    cur.execute(sql_template.format(game_pk_list=gp_list))
    return cur.fetchall()


# ── PostgreSQL connection ─────────────────────────────────────────────────────

def _json_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _pg_json(payload: dict):
    return psycopg2.extras.Json(payload, dumps=lambda o: json.dumps(o, default=_json_default))


def _pg_connect() -> psycopg2.extensions.connection | None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        log.warning("DATABASE_URL not set — skipping PG writes")
        return None
    return psycopg2.connect(dsn=url)


def _pg_set_cache(pg, cache_key: str, today: str, payload: dict, is_permanent: bool = False) -> None:
    with pg.cursor() as cur:
        cur.execute(
            """
            INSERT INTO api_cache (cache_key, cache_date, payload, is_permanent, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (cache_key, cache_date) DO UPDATE SET
                payload      = EXCLUDED.payload,
                is_permanent = api_cache.is_permanent OR EXCLUDED.is_permanent,
                updated_at   = NOW()
            """,
            (cache_key, today, _pg_json(payload), is_permanent),
        )
    pg.commit()


def _pg_upsert_picks(pg, rows: list[dict], today: str) -> None:
    """Upserts individual pick rows into daily_picks for portfolio filtering."""
    if not rows:
        return
    with pg.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO daily_picks
                    (game_pk, prediction_date, market, home_team, away_team, game_time_utc,
                     model_prob, bovada_prob, edge, ev, kelly_fraction, qualified_bet,
                     game_conviction_score, lineup_confirmed, pick_side,
                     model_total_runs, market_total_line, total_line_consensus, pred_total_runs)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (game_pk, market, prediction_date) DO UPDATE SET
                    model_prob            = EXCLUDED.model_prob,
                    bovada_prob           = EXCLUDED.bovada_prob,
                    edge                  = EXCLUDED.edge,
                    ev                    = EXCLUDED.ev,
                    kelly_fraction        = EXCLUDED.kelly_fraction,
                    qualified_bet         = EXCLUDED.qualified_bet,
                    game_conviction_score = EXCLUDED.game_conviction_score,
                    lineup_confirmed      = EXCLUDED.lineup_confirmed,
                    pick_side             = EXCLUDED.pick_side,
                    model_total_runs      = EXCLUDED.model_total_runs,
                    market_total_line     = EXCLUDED.market_total_line,
                    total_line_consensus  = EXCLUDED.total_line_consensus,
                    pred_total_runs       = EXCLUDED.pred_total_runs
                """,
                (
                    r["GAME_PK"], today, r["MARKET_TYPE"],
                    r.get("HOME_TEAM"), r.get("AWAY_TEAM"),
                    _ts(r.get("GAME_START_UTC")),
                    r.get("MODEL_PROB"), r.get("BOVADA_DEVIG_PROB"),
                    r.get("EDGE"),
                    # EV rows carry kelly/qualified; today rows may not
                    r.get("EV"), r.get("KELLY_FRACTION"), r.get("QUALIFIED_BET"),
                    r.get("GAME_CONVICTION_SCORE"), r.get("LINEUP_CONFIRMED"),
                    r.get("PICK_SIDE"),
                    r.get("MODEL_TOTAL_RUNS"), r.get("MARKET_TOTAL_LINE"),
                    r.get("TOTAL_LINE_CONSENSUS"), r.get("PRED_TOTAL_RUNS"),
                ),
            )
    pg.commit()


# ── S3 write ─────────────────────────────────────────────────────────────────

def _write_s3(bucket: str, key: str, data: dict | list) -> None:
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, default=str),
        ContentType="application/json",
    )
    log.info("Wrote s3://%s/%s", bucket, key)


# ── SQL — bulk endpoint queries (mirrors write_api_cache.py) ─────────────────

_PICKS_TODAY_SQL = """
WITH ranked AS (
    SELECT
        p.*,
        g.game_date AS game_start_utc,
        ROW_NUMBER() OVER (
            PARTITION BY p.game_pk
            ORDER BY
                CASE WHEN p.prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                p.inserted_at DESC
        ) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions p
    LEFT JOIN baseball_data.betting.stg_statsapi_games g ON g.game_pk = p.game_pk
    WHERE p.game_date = %(today)s
      AND p.prediction_type IN ('post_lineup', 'morning')
),
base AS (SELECT * FROM ranked WHERE _rn = 1),
h2h AS (
    SELECT
        b.game_pk, b.game_date,
        'h2h'                                        AS market_type,
        b.calibrated_win_prob                        AS model_prob,
        b.h2h_market_implied_prob                    AS bovada_devig_prob,
        b.layer4_h2h_edge                            AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        NULL::FLOAT                                  AS win_prob_ci_low,
        NULL::FLOAT                                  AS win_prob_ci_high,
        b.home_team, b.away_team,
        b.layer4_h2h_decision                        AS pick_side,
        b.game_start_utc,
        b.inserted_at,
        NULL::FLOAT                                  AS model_total_runs,
        NULL::FLOAT                                  AS market_total_line,
        b.prediction_type
    FROM base b
    WHERE b.layer4_h2h_decision IN ('home', 'away')
),
totals AS (
    SELECT
        b.game_pk, b.game_date,
        'totals'                                     AS market_type,
        b.totals_model_prob                          AS model_prob,
        b.over_prob_consensus                        AS bovada_devig_prob,
        b.layer4_totals_over_signal                  AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        NULL::FLOAT                                  AS win_prob_ci_low,
        NULL::FLOAT                                  AS win_prob_ci_high,
        b.home_team, b.away_team,
        b.layer4_totals_decision                     AS pick_side,
        b.game_start_utc,
        b.inserted_at,
        b.pred_total_runs                            AS model_total_runs,
        b.total_line_consensus                       AS market_total_line,
        b.prediction_type
    FROM base b
    WHERE b.layer4_totals_decision IN ('over', 'under')
)
SELECT * FROM h2h UNION ALL SELECT * FROM totals
ORDER BY game_start_utc, game_pk, market_type
"""

_EV_TODAY_SQL = """
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk
            ORDER BY
                CASE WHEN prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                inserted_at DESC
        ) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions
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
        b.game_pk, b.game_date, b.game_start_utc,
        'h2h'                                        AS market_type,
        b.calibrated_win_prob                        AS model_prob,
        b.h2h_market_implied_prob                    AS bovada_devig_prob,
        b.layer4_h2h_edge                            AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        b.layer4_h2h_decision <> 'abstain'           AS qualified_bet,
        b.home_team, b.away_team,
        b.h2h_kelly_fraction                         AS kelly_fraction,
        b.total_line_consensus,
        NULL::FLOAT                                  AS pred_total_runs,
        b.prediction_type
    FROM base b
    WHERE b.h2h_market_implied_prob IS NOT NULL
),
totals AS (
    SELECT
        b.game_pk, b.game_date, b.game_start_utc,
        'totals'                                     AS market_type,
        b.totals_model_prob                          AS model_prob,
        b.over_prob_consensus                        AS bovada_devig_prob,
        b.layer4_totals_over_signal                  AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        b.layer4_totals_decision <> 'abstain'        AS qualified_bet,
        b.home_team, b.away_team,
        b.totals_kelly_fraction                      AS kelly_fraction,
        b.total_line_consensus,
        b.pred_total_runs,
        b.prediction_type
    FROM base b
    WHERE b.over_prob_consensus IS NOT NULL
)
SELECT * FROM h2h UNION ALL SELECT * FROM totals
ORDER BY game_pk, market_type
"""

_HISTORY_SQL = """
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk
            ORDER BY
                CASE WHEN lineup_confirmed THEN 0 ELSE 1 END,
                inserted_at DESC
        ) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions
    WHERE game_date >= DATEADD(day, -30, CURRENT_DATE)
      AND qualified_bet = TRUE
),
base AS (SELECT * FROM ranked WHERE _rn = 1),
h2h AS (
    SELECT
        b.game_pk, b.game_date,
        'h2h'                                       AS market_type,
        b.calibrated_win_prob                       AS model_prob,
        b.h2h_market_implied_prob                   AS bovada_devig_prob,
        b.h2h_edge                                  AS edge,
        b.game_conviction_score,
        b.lineup_confirmed,
        NULL::FLOAT                                 AS win_prob_ci_low,
        NULL::FLOAT                                 AS win_prob_ci_high,
        b.home_team, b.away_team, b.inserted_at,
        clv.clv, clv.clv_positive, clv.actual_outcome
    FROM base b
    LEFT JOIN baseball_data.betting.mart_clv_labeled_games clv
        ON clv.game_pk = b.game_pk AND clv.market_type = 'h2h'
    WHERE b.h2h_edge IS NOT NULL
),
totals AS (
    SELECT
        b.game_pk, b.game_date,
        'totals'                                    AS market_type,
        b.totals_model_prob                         AS model_prob,
        b.over_prob_consensus                       AS bovada_devig_prob,
        b.totals_edge                               AS edge,
        b.game_conviction_score,
        b.lineup_confirmed,
        NULL::FLOAT                                 AS win_prob_ci_low,
        NULL::FLOAT                                 AS win_prob_ci_high,
        b.home_team, b.away_team, b.inserted_at,
        clv.clv, clv.clv_positive, clv.actual_outcome
    FROM base b
    LEFT JOIN baseball_data.betting.mart_clv_labeled_games clv
        ON clv.game_pk = b.game_pk AND clv.market_type = 'totals'
    WHERE b.totals_edge IS NOT NULL
)
SELECT * FROM h2h UNION ALL SELECT * FROM totals
ORDER BY game_date DESC, game_pk, market_type
"""

_FRESHNESS_SQL = """
SELECT MAX(inserted_at) AS last_updated_at
FROM baseball_data.betting_ml.daily_model_predictions
WHERE game_date = %(today)s
"""

_BANKROLL_SQL = """
SELECT total_bets, wins, win_rate, mean_clv,
       net_pnl_flat, net_pnl_kelly, sharpe_ratio
FROM baseball_data.betting.mart_bankroll_state
ORDER BY recorded_at DESC LIMIT 1
"""

_CLV_SUMMARY_SQL = """
SELECT
    COUNT(*)                                                       AS total_bets,
    SUM(CASE WHEN actual_outcome = 1 AND clv_positive THEN 1
             WHEN actual_outcome = 0 AND NOT clv_positive THEN 1
             ELSE 0 END)                                           AS wins,
    AVG(clv)                                                       AS mean_clv,
    SUM(CASE WHEN clv_positive THEN 1.0 ELSE -1.0 END)            AS net_pnl_flat
FROM baseball_data.betting.mart_clv_labeled_games
WHERE actual_outcome IS NOT NULL
"""

# ── Game-detail batch queries (source-of-truth: picks.py _*_QUERY constants) ─
# Use {game_pk_list} as a safe integer-list placeholder (filled by _sf_query_batch).

_GAME_STATUS_BATCH = """
SELECT
    g.game_pk,
    g.abstract_game_state,
    g.home_score,
    g.away_score,
    g.home_is_winner,
    g.home_team_name,
    g.away_team_name,
    g.home_wins,
    g.home_losses,
    g.away_wins,
    g.away_losses,
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
WHERE g.game_pk IN ({game_pk_list})
"""

_STARTERS_BATCH = """
WITH game_meta AS (
    SELECT game_pk, game_date, YEAR(game_date) AS game_year
    FROM baseball_data.betting.stg_statsapi_games
    WHERE game_pk IN ({game_pk_list})
),
starters AS (
    SELECT game_pk, side, probable_pitcher_id, probable_pitcher_name
    FROM baseball_data.betting.stg_statsapi_probable_pitchers
    WHERE game_pk IN ({game_pk_list})
    QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk, side ORDER BY ingestion_ts DESC) = 1
),
current_season AS (
    SELECT
        s.game_pk,
        g.pitcher_id,
        COUNT(*) AS starts,
        ROUND(SUM(g.runs_allowed) * 9.0 / NULLIF(SUM(g.innings_pitched), 0), 2) AS ra9,
        ROUND((SUM(g.walks) + SUM(g.hits_allowed)) / NULLIF(SUM(g.innings_pitched), 0), 2) AS whip,
        ROUND(SUM(g.strikeouts)::FLOAT / NULLIF(SUM(g.batters_faced), 0) * 100, 1) AS k_pct
    FROM baseball_data.betting.mart_starting_pitcher_game_log g
    JOIN starters s ON g.pitcher_id = s.probable_pitcher_id
    JOIN game_meta gm ON gm.game_pk = s.game_pk
    WHERE g.game_year = gm.game_year
      AND g.game_date < gm.game_date
    GROUP BY s.game_pk, g.pitcher_id
),
prior_season AS (
    SELECT
        s.game_pk,
        g.pitcher_id,
        COUNT(*) AS starts,
        ROUND(SUM(g.runs_allowed) * 9.0 / NULLIF(SUM(g.innings_pitched), 0), 2) AS ra9,
        ROUND((SUM(g.walks) + SUM(g.hits_allowed)) / NULLIF(SUM(g.innings_pitched), 0), 2) AS whip,
        ROUND(SUM(g.strikeouts)::FLOAT / NULLIF(SUM(g.batters_faced), 0) * 100, 1) AS k_pct
    FROM baseball_data.betting.mart_starting_pitcher_game_log g
    JOIN starters s ON g.pitcher_id = s.probable_pitcher_id
    JOIN game_meta gm ON gm.game_pk = s.game_pk
    WHERE g.game_year = gm.game_year - 1
    GROUP BY s.game_pk, g.pitcher_id
),
last5 AS (
    SELECT sub.game_pk, sub.pitcher_id, MEDIAN(sub.innings_pitched) AS median_ip_last5
    FROM (
        SELECT s.game_pk, g.pitcher_id, g.innings_pitched,
               ROW_NUMBER() OVER (PARTITION BY s.game_pk, g.pitcher_id ORDER BY g.game_date DESC) AS rn
        FROM baseball_data.betting.mart_starting_pitcher_game_log g
        JOIN starters s ON g.pitcher_id = s.probable_pitcher_id
        JOIN game_meta gm ON gm.game_pk = s.game_pk
        WHERE g.game_date < gm.game_date
    ) sub
    WHERE sub.rn <= 5
    GROUP BY sub.game_pk, sub.pitcher_id
)
SELECT
    s.game_pk,
    s.side,
    s.probable_pitcher_id,
    s.probable_pitcher_name,
    gm.game_year                                                AS current_season_year,
    cs.starts                                                   AS current_starts,
    cs.ra9                                                      AS current_ra9,
    cs.whip                                                     AS current_whip,
    cs.k_pct                                                    AS current_k_pct,
    gm.game_year - 1                                            AS prior_season_year,
    ps.starts                                                   AS prior_starts,
    ps.ra9                                                      AS prior_ra9,
    ps.whip                                                     AS prior_whip,
    ps.k_pct                                                    AS prior_k_pct,
    IFF(COALESCE(l5.median_ip_last5, 5.0) < 2.5, TRUE, FALSE)  AS is_opener
FROM starters s
JOIN game_meta gm ON gm.game_pk = s.game_pk
LEFT JOIN current_season cs ON cs.game_pk = s.game_pk AND cs.pitcher_id = s.probable_pitcher_id
LEFT JOIN prior_season ps ON ps.game_pk = s.game_pk AND ps.pitcher_id = s.probable_pitcher_id
LEFT JOIN last5 l5 ON l5.game_pk = s.game_pk AND l5.pitcher_id = s.probable_pitcher_id
"""

_BOVADA_BATCH = """
WITH pre_game AS (
    SELECT
        g.game_pk,
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
    WHERE g.game_pk IN ({game_pk_list})
      AND o.bookmaker_key = 'bovada'
      AND o.ingestion_ts::TIMESTAMP_NTZ < g.game_date::TIMESTAMP_NTZ
),
-- Latest snapshot per game where BOTH home and away h2h outcomes exist.
-- Falls back to an earlier snapshot rather than showing a one-sided line.
best_h2h_snap AS (
    SELECT game_pk, MAX(ingestion_ts) AS best_ts
    FROM (
        SELECT game_pk, ingestion_ts
        FROM pre_game
        WHERE market_key = 'h2h'
        GROUP BY game_pk, ingestion_ts
        HAVING SUM(CASE WHEN is_home_outcome     THEN 1 ELSE 0 END) >= 1
           AND SUM(CASE WHEN NOT is_home_outcome THEN 1 ELSE 0 END) >= 1
    ) paired
    GROUP BY game_pk
)
SELECT p.game_pk, p.market_key, p.outcome_name, p.outcome_price_american, p.outcome_point,
       p.is_home_outcome, p.ingestion_ts
FROM pre_game p
JOIN best_h2h_snap s ON s.game_pk = p.game_pk AND p.ingestion_ts = s.best_ts
WHERE p.market_key = 'h2h'
UNION ALL
SELECT game_pk, market_key, outcome_name, outcome_price_american, outcome_point,
       is_home_outcome, ingestion_ts
FROM pre_game
WHERE market_key != 'h2h'
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY game_pk, market_key, outcome_name
    ORDER BY ingestion_ts DESC
) = 1
ORDER BY game_pk, market_key, is_home_outcome DESC
"""

_TEAM_FEATURES_BATCH = """
SELECT
    game_pk,
    home_off_woba_30d, away_off_woba_30d,
    home_off_xwoba_30d, away_off_xwoba_30d,
    home_off_runs_per_game_30d, away_off_runs_per_game_30d,
    home_starter_xwoba_against_30d, away_starter_xwoba_against_30d,
    home_starter_k_pct_30d, away_starter_k_pct_30d,
    home_starter_pitcher_hand, away_starter_pitcher_hand,
    home_lineup_vs_away_starter_xwoba_adj, away_lineup_vs_home_starter_xwoba_adj,
    home_bp_xwoba_against_14d, away_bp_xwoba_against_14d,
    home_bp_innings_pitched_14d, away_bp_innings_pitched_14d,
    home_days_rest, away_days_rest,
    park_run_factor_3yr, elo_diff
FROM baseball_data.betting_features.feature_pregame_game_features
WHERE game_pk IN ({game_pk_list})
QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY game_date DESC) = 1
"""

_LINEUP_BATCH = """
WITH wide AS (
    SELECT * FROM baseball_data.betting.stg_statsapi_lineups_wide
    WHERE game_pk IN ({game_pk_list})
),
slots AS (
    SELECT game_pk, home_away, official_date, 1 AS slot, slot_1_player_id AS player_id, slot_1_full_name AS player_name, slot_1_position AS position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 2, slot_2_player_id, slot_2_full_name, slot_2_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 3, slot_3_player_id, slot_3_full_name, slot_3_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 4, slot_4_player_id, slot_4_full_name, slot_4_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 5, slot_5_player_id, slot_5_full_name, slot_5_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 6, slot_6_player_id, slot_6_full_name, slot_6_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 7, slot_7_player_id, slot_7_full_name, slot_7_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 8, slot_8_player_id, slot_8_full_name, slot_8_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 9, slot_9_player_id, slot_9_full_name, slot_9_position FROM wide
),
season_stats AS (
    SELECT
        rs.batter_id,
        rs.ops_std   AS season_ops,
        rs.xwoba_std AS season_xwoba
    FROM baseball_data.betting.mart_batter_rolling_stats rs
    JOIN slots s ON rs.batter_id = s.player_id
        AND rs.game_year  = YEAR(s.official_date)
        AND rs.game_date  < s.official_date
    QUALIFY ROW_NUMBER() OVER (PARTITION BY rs.batter_id ORDER BY rs.game_date DESC) = 1
)
SELECT s.game_pk, s.home_away, s.slot, s.player_id, s.player_name, s.position,
       st.season_ops, st.season_xwoba
FROM slots s
LEFT JOIN season_stats st ON st.batter_id = s.player_id
WHERE s.player_id IS NOT NULL
ORDER BY s.game_pk, s.home_away, s.slot
"""

_BOX_SCORE_BATCH = """
WITH pa_end AS (
    SELECT
        game_pk, batter_id, player_name, inning_half, at_bat_number,
        plate_appearance_event, woba_value, woba_denom, xwoba
    FROM baseball_data.betting.stg_batter_pitches
    WHERE game_pk IN ({game_pk_list}) AND woba_denom = 1
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY game_pk, batter_id, at_bat_number
        ORDER BY pitch_number DESC
    ) = 1
)
SELECT
    game_pk, batter_id, player_name,
    CASE WHEN UPPER(inning_half) = 'TOP' THEN 'away' ELSE 'home' END AS home_away,
    COUNT(*)                                                                                            AS pa,
    SUM(CASE WHEN plate_appearance_event NOT IN (
        'walk','intent_walk','hit_by_pitch','sac_fly','sac_bunt',
        'catcher_interf','sac_fly_double_play'
    ) THEN 1 ELSE 0 END)                                                                                AS ab,
    SUM(CASE WHEN plate_appearance_event IN ('single','double','triple','home_run') THEN 1 ELSE 0 END)  AS h,
    SUM(CASE WHEN plate_appearance_event IN ('strikeout','strikeout_double_play') THEN 1 ELSE 0 END)    AS k,
    SUM(CASE WHEN plate_appearance_event IN ('walk','intent_walk') THEN 1 ELSE 0 END)                   AS bb,
    SUM(CASE WHEN plate_appearance_event = 'home_run' THEN 1 ELSE 0 END)                                AS hr,
    ROUND(SUM(COALESCE(xwoba, woba_value, 0) * woba_denom) / NULLIF(SUM(woba_denom), 0), 3)            AS xwoba_game
FROM pa_end
GROUP BY game_pk, batter_id, player_name, inning_half
ORDER BY game_pk, home_away, batter_id
"""

_WEATHER_BATCH = """
SELECT game_pk, temp_f, wind_speed_mph, wind_component_mph, is_dome, weather_observation_type
FROM baseball_data.betting_features.feature_pregame_weather_features
WHERE game_pk IN ({game_pk_list})
QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY game_pk) = 1
"""

_PUBLIC_BETTING_BATCH = """
SELECT game_pk,
    home_ml_money_pct, away_ml_money_pct,
    home_ml_ticket_pct, away_ml_ticket_pct,
    over_money_pct, under_money_pct,
    over_ticket_pct, under_ticket_pct,
    ml_sharp_signal, total_sharp_signal
FROM baseball_data.betting_features.feature_pregame_public_betting_features
WHERE game_pk IN ({game_pk_list})
QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY game_pk) = 1
"""

_LINE_MOVEMENT_BATCH = """
SELECT game_pk,
    open_home_win_prob, pregame_home_win_prob, h2h_line_movement,
    open_total_line, pregame_total_line, total_line_movement
FROM baseball_data.betting.mart_odds_line_movement
WHERE game_pk IN ({game_pk_list})
QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY game_pk) = 1
"""

_RECENT_FORM_BATCH = """
WITH game_meta AS (
    SELECT game_pk, game_date, home_team_id, away_team_id
    FROM baseball_data.betting.stg_statsapi_games
    WHERE game_pk IN ({game_pk_list})
),
home_recent AS (
    SELECT
        gm.game_pk,
        'home' AS team_side,
        CASE WHEN g.home_team_id = gm.home_team_id THEN g.home_is_winner
             ELSE g.away_is_winner END AS won,
        ROW_NUMBER() OVER (PARTITION BY gm.game_pk ORDER BY g.game_date DESC) AS rn
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
        gm.game_pk,
        'away' AS team_side,
        CASE WHEN g.home_team_id = gm.away_team_id THEN g.home_is_winner
             ELSE g.away_is_winner END AS won,
        ROW_NUMBER() OVER (PARTITION BY gm.game_pk ORDER BY g.game_date DESC) AS rn
    FROM baseball_data.betting.stg_statsapi_games g
    CROSS JOIN game_meta gm
    WHERE g.abstract_game_state = 'Final'
      AND g.game_date < gm.game_date
      AND YEAR(g.game_date) = YEAR(gm.game_date)
      AND g.home_is_winner IS NOT NULL
      AND (g.home_team_id = gm.away_team_id OR g.away_team_id = gm.away_team_id)
),
combined AS (SELECT * FROM home_recent UNION ALL SELECT * FROM away_recent)
SELECT game_pk, team_side,
    SUM(CASE WHEN rn <= 5  AND won = TRUE  THEN 1 ELSE 0 END) AS l5_wins,
    SUM(CASE WHEN rn <= 5  AND won = FALSE THEN 1 ELSE 0 END) AS l5_losses,
    SUM(CASE WHEN rn <= 5  THEN 1 ELSE 0 END)                 AS l5_games,
    SUM(CASE WHEN rn <= 10 AND won = TRUE  THEN 1 ELSE 0 END) AS l10_wins,
    SUM(CASE WHEN rn <= 10 AND won = FALSE THEN 1 ELSE 0 END) AS l10_losses,
    SUM(CASE WHEN rn <= 10 THEN 1 ELSE 0 END)                 AS l10_games
FROM combined WHERE rn <= 10
GROUP BY game_pk, team_side
"""

_H2H_BATCH = """
WITH game_meta AS (
    SELECT game_pk, game_date, home_team_id, away_team_id
    FROM baseball_data.betting.stg_statsapi_games
    WHERE game_pk IN ({game_pk_list})
),
h2h_games AS (
    SELECT
        gm.game_pk,
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
SELECT game_pk,
    SUM(CASE WHEN home_team_won = TRUE  THEN 1 ELSE 0 END) AS home_wins,
    SUM(CASE WHEN home_team_won = FALSE THEN 1 ELSE 0 END) AS away_wins,
    COUNT(*)                                                AS games_played,
    ROUND(AVG(total_runs), 2)                              AS avg_total_runs
FROM h2h_games
GROUP BY game_pk
"""

_UMPIRE_BATCH = """
SELECT game_pk, umpire_name, ump_games_sample,
    CASE WHEN ump_k_pct_trailing  IS NULL THEN NULL ELSE ump_k_pct_zscore  END AS ump_k_pct_zscore,
    CASE WHEN ump_bb_pct_trailing IS NULL THEN NULL ELSE ump_bb_pct_zscore END AS ump_bb_pct_zscore,
    ump_runs_per_game_zscore, ump_run_impact_zscore
FROM baseball_data.betting_features.feature_pregame_umpire_features
WHERE game_pk IN ({game_pk_list})
QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY game_pk DESC) = 1
"""

_GAME_PICKS_BATCH = """
WITH ranked AS (
    SELECT
        p.*,
        g.game_date AS game_start_utc,
        ROW_NUMBER() OVER (PARTITION BY p.game_pk ORDER BY p.inserted_at DESC) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions p
    LEFT JOIN baseball_data.betting.stg_statsapi_games g ON g.game_pk = p.game_pk
    WHERE p.game_pk IN ({game_pk_list})
      AND p.prediction_type = 'post_lineup'
),
base AS (SELECT * FROM ranked WHERE _rn = 1),
h2h AS (
    SELECT b.game_pk, b.game_date, 'h2h' AS market_type,
        b.calibrated_win_prob AS model_prob, b.h2h_market_implied_prob AS bovada_devig_prob,
        b.layer4_h2h_edge AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed, NULL::FLOAT AS win_prob_ci_low, NULL::FLOAT AS win_prob_ci_high,
        b.home_team, b.away_team, b.layer4_h2h_decision AS pick_side,
        b.game_start_utc, b.inserted_at AS predicted_at,
        NULL::FLOAT AS model_total_runs, NULL::FLOAT AS market_total_line
    FROM base b WHERE b.layer4_h2h_decision IN ('home','away')
),
totals AS (
    SELECT b.game_pk, b.game_date, 'totals' AS market_type,
        b.totals_model_prob AS model_prob, b.over_prob_consensus AS bovada_devig_prob,
        b.layer4_totals_over_signal AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed, NULL::FLOAT AS win_prob_ci_low, NULL::FLOAT AS win_prob_ci_high,
        b.home_team, b.away_team, b.layer4_totals_decision AS pick_side,
        b.game_start_utc, b.inserted_at AS predicted_at,
        b.pred_total_runs AS model_total_runs, b.total_line_consensus AS market_total_line
    FROM base b WHERE b.layer4_totals_decision IN ('over','under')
)
SELECT * FROM h2h UNION ALL SELECT * FROM totals
ORDER BY game_pk, market_type
"""


# ── Payload builders ──────────────────────────────────────────────────────────

def _ts(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _flt(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _build_picks_payload(rows: list[dict], freshness_rows: list[dict]) -> dict:
    last_updated_at = None
    if freshness_rows and freshness_rows[0].get("LAST_UPDATED_AT"):
        last_updated_at = _ts(freshness_rows[0]["LAST_UPDATED_AT"])
    if last_updated_at:
        try:
            ts_dt = datetime.fromisoformat(last_updated_at.replace("Z", "+00:00"))
            age_h = (datetime.now(timezone.utc) - ts_dt.replace(tzinfo=timezone.utc)).total_seconds() / 3600
            pipeline_status = "ok" if age_h < 6 else "stale"
        except Exception:
            pipeline_status = "ok"
    else:
        pipeline_status = "no_predictions"
    picks = [
        {
            "game_pk": r["GAME_PK"], "game_date": str(r["GAME_DATE"]),
            "market_type": r["MARKET_TYPE"], "model_prob": r.get("MODEL_PROB"),
            "bovada_devig_prob": r.get("BOVADA_DEVIG_PROB"), "edge": r.get("EDGE"),
            "game_conviction_score": r.get("GAME_CONVICTION_SCORE"),
            "win_prob_ci_low": r.get("WIN_PROB_CI_LOW"), "win_prob_ci_high": r.get("WIN_PROB_CI_HIGH"),
            "lineup_confirmed": r.get("LINEUP_CONFIRMED"), "home_team": r.get("HOME_TEAM"),
            "away_team": r.get("AWAY_TEAM"), "pick_side": r.get("PICK_SIDE"),
            "game_start_utc": _ts(r.get("GAME_START_UTC")),
            "model_total_runs": r.get("MODEL_TOTAL_RUNS"), "market_total_line": r.get("MARKET_TOTAL_LINE"),
        }
        for r in rows
    ]
    is_preliminary = bool(rows) and any(
        (r.get("PREDICTION_TYPE") or "") == "morning" for r in rows
    )
    return {"picks": picks, "data_quality": {"signal_completeness_score": None,
        "last_updated_at": last_updated_at, "pipeline_status": pipeline_status},
        "is_preliminary": is_preliminary}


def _build_ev_payload(rows: list[dict]) -> dict:
    picks = [
        {
            "game_pk": r["GAME_PK"], "game_date": str(r.get("GAME_DATE") or ""),
            "game_start_utc": _ts(r.get("GAME_START_UTC")), "market_type": r["MARKET_TYPE"],
            "model_prob": r.get("MODEL_PROB"), "bovada_devig_prob": r.get("BOVADA_DEVIG_PROB"),
            "edge": r.get("EDGE"), "game_conviction_score": r.get("GAME_CONVICTION_SCORE"),
            "lineup_confirmed": r.get("LINEUP_CONFIRMED"), "qualified_bet": r.get("QUALIFIED_BET"),
            "home_team": r.get("HOME_TEAM"), "away_team": r.get("AWAY_TEAM"),
            "kelly_fraction": r.get("KELLY_FRACTION"), "total_line_consensus": r.get("TOTAL_LINE_CONSENSUS"),
            "pred_total_runs": r.get("PRED_TOTAL_RUNS"),
        }
        for r in rows
    ]
    is_preliminary = bool(rows) and any(
        (r.get("PREDICTION_TYPE") or "") == "morning" for r in rows
    )
    return {"picks": picks, "total": len(picks), "is_preliminary": is_preliminary}


def _build_history_payload(rows: list[dict]) -> dict:
    picks = [
        {
            "game_pk": r["GAME_PK"], "game_date": str(r["GAME_DATE"]), "market_type": r["MARKET_TYPE"],
            "model_prob": r.get("MODEL_PROB"), "bovada_devig_prob": r.get("BOVADA_DEVIG_PROB"),
            "edge": r.get("EDGE"), "game_conviction_score": r.get("GAME_CONVICTION_SCORE"),
            "win_prob_ci_low": r.get("WIN_PROB_CI_LOW"), "win_prob_ci_high": r.get("WIN_PROB_CI_HIGH"),
            "lineup_confirmed": r.get("LINEUP_CONFIRMED"), "home_team": r.get("HOME_TEAM"),
            "away_team": r.get("AWAY_TEAM"), "clv": r.get("CLV"),
            "clv_positive": r.get("CLV_POSITIVE"), "actual_outcome": r.get("ACTUAL_OUTCOME"),
        }
        for r in rows
    ]
    return {"picks": picks, "total": len(picks)}


def _build_performance_payload(rows: list[dict], source: str) -> dict:
    if not rows:
        return {"total_bets": 0, "wins": 0, "source": source}
    r = rows[0]
    total = r.get("TOTAL_BETS") or 0
    wins = r.get("WINS") or 0
    return {
        "total_bets": total, "wins": wins,
        "win_rate": r.get("WIN_RATE") if source == "mart_bankroll_state" else (wins / total if total > 0 else None),
        "mean_clv": r.get("MEAN_CLV"), "net_pnl_flat": r.get("NET_PNL_FLAT"),
        "net_pnl_kelly": r.get("NET_PNL_KELLY"), "sharpe_ratio": r.get("SHARPE_RATIO"),
        "source": source,
    }


def _assemble_game_detail_payloads(sf, game_pks: list[int], final_game_pks: set[int]) -> dict[int, tuple[dict, bool]]:
    """Runs all 12 batch queries and assembles per-game detail dicts.

    Returns {game_pk: (payload_dict, is_final)}.
    """
    log.info("Assembling game detail for %d games", len(game_pks))

    # Run all 12 batch queries
    status_rows     = _sf_query_batch(sf, _GAME_STATUS_BATCH, game_pks)
    starter_rows    = _sf_query_batch(sf, _STARTERS_BATCH, game_pks)
    bovada_rows     = _sf_query_batch(sf, _BOVADA_BATCH, game_pks)
    features_rows   = _sf_query_batch(sf, _TEAM_FEATURES_BATCH, game_pks)
    lineup_rows     = _sf_query_batch(sf, _LINEUP_BATCH, game_pks)
    box_score_rows  = _sf_query_batch(sf, _BOX_SCORE_BATCH, game_pks)
    weather_rows    = _sf_query_batch(sf, _WEATHER_BATCH, game_pks)
    pb_rows         = _sf_query_batch(sf, _PUBLIC_BETTING_BATCH, game_pks)
    lm_rows         = _sf_query_batch(sf, _LINE_MOVEMENT_BATCH, game_pks)
    form_rows       = _sf_query_batch(sf, _RECENT_FORM_BATCH, game_pks)
    h2h_rows        = _sf_query_batch(sf, _H2H_BATCH, game_pks)
    umpire_rows     = _sf_query_batch(sf, _UMPIRE_BATCH, game_pks)
    pick_rows       = _sf_query_batch(sf, _GAME_PICKS_BATCH, game_pks)

    # Index by game_pk
    status_by_pk   = {r["GAME_PK"]: r for r in status_rows}
    features_by_pk = {r["GAME_PK"]: r for r in features_rows}
    weather_by_pk  = {r["GAME_PK"]: r for r in weather_rows}
    pb_by_pk       = {r["GAME_PK"]: r for r in pb_rows}
    lm_by_pk       = {r["GAME_PK"]: r for r in lm_rows}
    h2h_by_pk      = {r["GAME_PK"]: r for r in h2h_rows}
    umpire_by_pk   = {r["GAME_PK"]: r for r in umpire_rows}

    starters_by_pk  = defaultdict(list)
    for r in starter_rows:
        starters_by_pk[r["GAME_PK"]].append(r)

    bovada_by_pk = defaultdict(list)
    for r in bovada_rows:
        bovada_by_pk[r["GAME_PK"]].append(r)

    lineup_by_pk = defaultdict(list)
    for r in lineup_rows:
        lineup_by_pk[r["GAME_PK"]].append(r)

    box_score_by_pk = defaultdict(dict)
    for r in box_score_rows:
        bid = r.get("BATTER_ID")
        if bid is not None:
            box_score_by_pk[r["GAME_PK"]][int(bid)] = r

    form_by_pk = defaultdict(list)
    for r in form_rows:
        form_by_pk[r["GAME_PK"]].append(r)

    picks_by_pk = defaultdict(list)
    for r in pick_rows:
        picks_by_pk[r["GAME_PK"]].append(r)

    result: dict[int, tuple[dict, bool]] = {}

    for gp in game_pks:
        # ── picks ──
        picks_out = [
            {
                "game_pk": r["GAME_PK"], "game_date": str(r["GAME_DATE"]),
                "market_type": r["MARKET_TYPE"], "model_prob": r.get("MODEL_PROB"),
                "bovada_devig_prob": r.get("BOVADA_DEVIG_PROB"), "edge": r.get("EDGE"),
                "game_conviction_score": r.get("GAME_CONVICTION_SCORE"),
                "win_prob_ci_low": r.get("WIN_PROB_CI_LOW"), "win_prob_ci_high": r.get("WIN_PROB_CI_HIGH"),
                "lineup_confirmed": r.get("LINEUP_CONFIRMED"), "home_team": r.get("HOME_TEAM"),
                "away_team": r.get("AWAY_TEAM"), "pick_side": r.get("PICK_SIDE"),
                "game_start_utc": _ts(r.get("GAME_START_UTC")),
                "model_total_runs": r.get("MODEL_TOTAL_RUNS"), "market_total_line": r.get("MARKET_TOTAL_LINE"),
                "predicted_at": _ts(r.get("PREDICTED_AT")),
            }
            for r in picks_by_pk[gp]
        ]

        # ── game status ──
        game_score = None
        home_team_name = None
        away_team_name = None
        sr = status_by_pk.get(gp)
        if sr:
            state = str(sr.get("ABSTRACT_GAME_STATE") or "Preview")
            hw_raw = _int(sr.get("HOME_WINS"))
            hl_raw = _int(sr.get("HOME_LOSSES"))
            aw_raw = _int(sr.get("AWAY_WINS"))
            al_raw = _int(sr.get("AWAY_LOSSES"))
            if state == "Final" and hw_raw is not None:
                home_won = bool(sr.get("HOME_IS_WINNER"))
                hw = hw_raw - (1 if home_won else 0)
                hl = hl_raw - (0 if home_won else 1) if hl_raw is not None else None
                aw = aw_raw - (0 if home_won else 1) if aw_raw is not None else None
                al = al_raw - (1 if home_won else 0) if al_raw is not None else None
            else:
                hw, hl, aw, al = hw_raw, hl_raw, aw_raw, al_raw
            game_score = {
                "home_score": _int(sr.get("HOME_SCORE")),
                "away_score": _int(sr.get("AWAY_SCORE")),
                "status": state if state in ("Live", "Final") else "Preview",
                "home_wins": hw, "home_losses": hl,
                "away_wins": aw, "away_losses": al,
                "home_pyth_pct": _flt(sr.get("HOME_PYTH_PCT")),
                "home_pyth_residual": _flt(sr.get("HOME_PYTH_RESIDUAL")),
                "away_pyth_pct": _flt(sr.get("AWAY_PYTH_PCT")),
                "away_pyth_residual": _flt(sr.get("AWAY_PYTH_RESIDUAL")),
            }
            home_team_name = sr.get("HOME_TEAM_NAME")
            away_team_name = sr.get("AWAY_TEAM_NAME")

        is_final = game_score is not None and game_score.get("status") == "Final"

        # ── starters ──
        starters = None
        home_sp = None
        away_sp = None
        for row in starters_by_pk[gp]:
            sp = {
                "pitcher_id": row.get("PROBABLE_PITCHER_ID"),
                "name": row.get("PROBABLE_PITCHER_NAME"),
                "is_opener": bool(row.get("IS_OPENER", False)),
                "season": row.get("CURRENT_SEASON_YEAR"),
                "starts": row.get("CURRENT_STARTS"),
                "ra9": row.get("CURRENT_RA9"), "whip": row.get("CURRENT_WHIP"),
                "k_pct": row.get("CURRENT_K_PCT"),
                "prior_season": row.get("PRIOR_SEASON_YEAR"),
                "prior_starts": row.get("PRIOR_STARTS"),
                "prior_ra9": row.get("PRIOR_RA9"), "prior_whip": row.get("PRIOR_WHIP"),
                "prior_k_pct": row.get("PRIOR_K_PCT"),
            }
            if str(row.get("SIDE", "")).lower() == "home":
                home_sp = sp
            else:
                away_sp = sp
        if home_sp or away_sp:
            starters = {"home": home_sp, "away": away_sp}

        # ── Bovada lines ──
        bovada_lines = None
        bov = bovada_by_pk[gp]
        h2h_bov = [r for r in bov if str(r.get("MARKET_KEY", "")).lower() == "h2h"]
        tot_bov = [r for r in bov if str(r.get("MARKET_KEY", "")).lower() == "totals"]
        bov_h2h = None
        if h2h_bov:
            home_r = next((r for r in h2h_bov if r.get("IS_HOME_OUTCOME")), None)
            away_r = next((r for r in h2h_bov if not r.get("IS_HOME_OUTCOME")), None)
            snap = str(max(r["INGESTION_TS"] for r in h2h_bov)) if h2h_bov else None
            bov_h2h = {
                "home_american": _int(home_r["OUTCOME_PRICE_AMERICAN"]) if home_r and home_r.get("OUTCOME_PRICE_AMERICAN") is not None else None,
                "away_american": _int(away_r["OUTCOME_PRICE_AMERICAN"]) if away_r and away_r.get("OUTCOME_PRICE_AMERICAN") is not None else None,
                "snapshot_utc": snap,
            }
        bov_totals = None
        if tot_bov:
            over_r  = next((r for r in tot_bov if str(r.get("OUTCOME_NAME", "")).lower() == "over"), None)
            under_r = next((r for r in tot_bov if str(r.get("OUTCOME_NAME", "")).lower() == "under"), None)
            snap = str(max(r["INGESTION_TS"] for r in tot_bov)) if tot_bov else None
            bov_totals = {
                "line": _flt(over_r["OUTCOME_POINT"]) if over_r and over_r.get("OUTCOME_POINT") is not None else None,
                "over_american": _int(over_r["OUTCOME_PRICE_AMERICAN"]) if over_r and over_r.get("OUTCOME_PRICE_AMERICAN") is not None else None,
                "under_american": _int(under_r["OUTCOME_PRICE_AMERICAN"]) if under_r and under_r.get("OUTCOME_PRICE_AMERICAN") is not None else None,
                "snapshot_utc": snap,
            }
        if bov_h2h or bov_totals:
            bovada_lines = {"h2h": bov_h2h, "totals": bov_totals}

        # ── team features ──
        team_features = None
        fr = features_by_pk.get(gp)
        if fr:
            team_features = {
                "home": {
                    "off_woba_30d": _flt(fr.get("HOME_OFF_WOBA_30D")),
                    "off_xwoba_30d": _flt(fr.get("HOME_OFF_XWOBA_30D")),
                    "off_runs_per_game_30d": _flt(fr.get("HOME_OFF_RUNS_PER_GAME_30D")),
                    "starter_xwoba_against_30d": _flt(fr.get("HOME_STARTER_XWOBA_AGAINST_30D")),
                    "starter_k_pct_30d": _flt(fr.get("HOME_STARTER_K_PCT_30D")),
                    "starter_hand": fr.get("HOME_STARTER_PITCHER_HAND"),
                    "lineup_vs_sp_xwoba_adj": _flt(fr.get("HOME_LINEUP_VS_AWAY_STARTER_XWOBA_ADJ")),
                    "bp_xwoba_against_14d": _flt(fr.get("HOME_BP_XWOBA_AGAINST_14D")),
                    "bp_innings_pitched_14d": _flt(fr.get("HOME_BP_INNINGS_PITCHED_14D")),
                    "days_rest": _flt(fr.get("HOME_DAYS_REST")),
                },
                "away": {
                    "off_woba_30d": _flt(fr.get("AWAY_OFF_WOBA_30D")),
                    "off_xwoba_30d": _flt(fr.get("AWAY_OFF_XWOBA_30D")),
                    "off_runs_per_game_30d": _flt(fr.get("AWAY_OFF_RUNS_PER_GAME_30D")),
                    "starter_xwoba_against_30d": _flt(fr.get("AWAY_STARTER_XWOBA_AGAINST_30D")),
                    "starter_k_pct_30d": _flt(fr.get("AWAY_STARTER_K_PCT_30D")),
                    "starter_hand": fr.get("AWAY_STARTER_PITCHER_HAND"),
                    "lineup_vs_sp_xwoba_adj": _flt(fr.get("AWAY_LINEUP_VS_HOME_STARTER_XWOBA_ADJ")),
                    "bp_xwoba_against_14d": _flt(fr.get("AWAY_BP_XWOBA_AGAINST_14D")),
                    "bp_innings_pitched_14d": _flt(fr.get("AWAY_BP_INNINGS_PITCHED_14D")),
                    "days_rest": _flt(fr.get("AWAY_DAYS_REST")),
                },
                "park_run_factor": _flt(fr.get("PARK_RUN_FACTOR_3YR")),
                "elo_diff": _flt(fr.get("ELO_DIFF")),
            }

        # ── lineups + box score ──
        lineups = None
        home_players = []
        away_players = []
        bs_map = box_score_by_pk[gp] if is_final else {}
        for row in lineup_by_pk[gp]:
            pid = row.get("PLAYER_ID")
            bs = bs_map.get(int(pid)) if pid is not None else None
            player = {
                "slot": _int(row["SLOT"]), "player_id": _int(pid),
                "player_name": row.get("PLAYER_NAME"), "position": row.get("POSITION"),
                "season_ops": _flt(row.get("SEASON_OPS")), "season_xwoba": _flt(row.get("SEASON_XWOBA")),
                "game_pa": _int(bs["PA"]) if bs and bs.get("PA") is not None else None,
                "game_ab": _int(bs["AB"]) if bs and bs.get("AB") is not None else None,
                "game_h": _int(bs["H"]) if bs and bs.get("H") is not None else None,
                "game_k": _int(bs["K"]) if bs and bs.get("K") is not None else None,
                "game_bb": _int(bs["BB"]) if bs and bs.get("BB") is not None else None,
                "game_hr": _int(bs["HR"]) if bs and bs.get("HR") is not None else None,
                "game_xwoba": _flt(bs["XWOBA_GAME"]) if bs and bs.get("XWOBA_GAME") is not None else None,
            }
            if str(row.get("HOME_AWAY", "")).lower() == "home":
                home_players.append(player)
            else:
                away_players.append(player)
        if home_players or away_players:
            lineups = {"home": home_players, "away": away_players}

        # ── weather ──
        weather = None
        wr = weather_by_pk.get(gp)
        if wr:
            weather = {
                "temp_f": _flt(wr.get("TEMP_F")), "wind_speed_mph": _flt(wr.get("WIND_SPEED_MPH")),
                "wind_component_mph": _flt(wr.get("WIND_COMPONENT_MPH")),
                "is_dome": bool(wr.get("IS_DOME", False)),
                "observation_type": wr.get("WEATHER_OBSERVATION_TYPE"),
            }

        # ── public betting ──
        public_betting = None
        pb = pb_by_pk.get(gp)
        if pb:
            public_betting = {
                "home_ml_money_pct": _flt(pb.get("HOME_ML_MONEY_PCT")),
                "away_ml_money_pct": _flt(pb.get("AWAY_ML_MONEY_PCT")),
                "home_ml_ticket_pct": _flt(pb.get("HOME_ML_TICKET_PCT")),
                "away_ml_ticket_pct": _flt(pb.get("AWAY_ML_TICKET_PCT")),
                "over_money_pct": _flt(pb.get("OVER_MONEY_PCT")),
                "under_money_pct": _flt(pb.get("UNDER_MONEY_PCT")),
                "over_ticket_pct": _flt(pb.get("OVER_TICKET_PCT")),
                "under_ticket_pct": _flt(pb.get("UNDER_TICKET_PCT")),
                "ml_sharp_signal": _flt(pb.get("ML_SHARP_SIGNAL")),
                "total_sharp_signal": _flt(pb.get("TOTAL_SHARP_SIGNAL")),
            }

        # ── line movement ──
        line_movement = None
        lm = lm_by_pk.get(gp)
        if lm:
            line_movement = {
                "open_home_win_prob": _flt(lm.get("OPEN_HOME_WIN_PROB")),
                "pregame_home_win_prob": _flt(lm.get("PREGAME_HOME_WIN_PROB")),
                "h2h_line_movement": _flt(lm.get("H2H_LINE_MOVEMENT")),
                "open_total_line": _flt(lm.get("OPEN_TOTAL_LINE")),
                "pregame_total_line": _flt(lm.get("PREGAME_TOTAL_LINE")),
                "total_line_movement": _flt(lm.get("TOTAL_LINE_MOVEMENT")),
            }

        # ── recent form + H2H ──
        game_context = None
        home_form = None
        away_form = None
        for row in form_by_pk[gp]:
            form = {
                "l5_wins": _int(row.get("L5_WINS")), "l5_losses": _int(row.get("L5_LOSSES")),
                "l5_games": _int(row.get("L5_GAMES")), "l10_wins": _int(row.get("L10_WINS")),
                "l10_losses": _int(row.get("L10_LOSSES")), "l10_games": _int(row.get("L10_GAMES")),
            }
            if str(row.get("TEAM_SIDE", "")).lower() == "home":
                home_form = form
            else:
                away_form = form
        h2h_rec = None
        hr = h2h_by_pk.get(gp)
        if hr:
            gp_count = _int(hr.get("GAMES_PLAYED"))
            if gp_count and gp_count > 0:
                h2h_rec = {
                    "home_wins": _int(hr.get("HOME_WINS")), "away_wins": _int(hr.get("AWAY_WINS")),
                    "games_played": gp_count, "avg_total_runs": _flt(hr.get("AVG_TOTAL_RUNS")),
                }
        if home_form or away_form or h2h_rec:
            game_context = {"home_form": home_form, "away_form": away_form, "h2h": h2h_rec}

        # ── umpire ──
        umpire = None
        ur = umpire_by_pk.get(gp)
        if ur:
            umpire = {
                "name": ur.get("UMPIRE_NAME"), "k_pct_zscore": _flt(ur.get("UMP_K_PCT_ZSCORE")),
                "runs_per_game_zscore": _flt(ur.get("UMP_RUNS_PER_GAME_ZSCORE")),
                "run_impact_zscore": _flt(ur.get("UMP_RUN_IMPACT_ZSCORE")),
                "bb_pct_zscore": _flt(ur.get("UMP_BB_PCT_ZSCORE")),
                "games_sample": _int(ur.get("UMP_GAMES_SAMPLE")),
            }

        payload = {
            "picks": picks_out, "total": len(picks_out),
            "home_team_name": home_team_name, "away_team_name": away_team_name,
            "game_score": game_score, "starters": starters, "bovada_lines": bovada_lines,
            "team_features": team_features, "lineups": lineups, "weather": weather,
            "public_betting": public_betting, "line_movement": line_movement,
            "umpire": umpire, "game_context": game_context,
        }
        result[gp] = (payload, is_final)

    return result


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    today = date.today().isoformat()
    bucket = os.environ.get("CACHE_BUCKET")

    try:
        sf = _sf_connect()
    except Exception:
        log.exception("Snowflake connection failed")
        return 1

    pg = _pg_connect()
    errors = 0

    # ── picks/today ─────────────────────────────────────────────────────────
    picks_rows: list[dict] = []
    try:
        picks_rows = _sf_query(sf, _PICKS_TODAY_SQL, {"today": today})
        fresh_rows = _sf_query(sf, _FRESHNESS_SQL, {"today": today})
        if not picks_rows:
            log.info("No predictions for %s — skipping picks/today cache write", today)
        else:
            payload = _build_picks_payload(picks_rows, fresh_rows)
            if pg:
                _pg_set_cache(pg, "picks/today", today, payload)
                log.info("PG: picks/today written (%d picks)", len(picks_rows))
            if bucket:
                _write_s3(bucket, f"api-cache/{today}/picks/today.json", payload)
    except Exception:
        log.exception("Failed to write picks/today")
        errors += 1

    # ── picks/ev ────────────────────────────────────────────────────────────
    ev_rows: list[dict] = []
    try:
        ev_rows = _sf_query(sf, _EV_TODAY_SQL, {"today": today})
        if not ev_rows:
            log.info("No EV rows for %s — skipping picks/ev cache write", today)
        else:
            payload = _build_ev_payload(ev_rows)
            if pg:
                _pg_set_cache(pg, "picks/ev", today, payload)
                log.info("PG: picks/ev written (%d rows)", len(ev_rows))
            if bucket:
                _write_s3(bucket, f"api-cache/{today}/picks/ev.json", payload)
    except Exception:
        log.exception("Failed to write picks/ev")
        errors += 1

    # ── individual daily_picks rows (portfolio filtering) ───────────────────
    if pg and (picks_rows or ev_rows):
        try:
            # Merge picks+ev rows; picks carry pick_side, ev rows carry kelly/qualified
            merged = {(r["GAME_PK"], r["MARKET_TYPE"]): r for r in picks_rows}
            for r in ev_rows:
                key = (r["GAME_PK"], r["MARKET_TYPE"])
                if key in merged:
                    merged[key].update({k: r[k] for k in ("KELLY_FRACTION", "QUALIFIED_BET",
                        "TOTAL_LINE_CONSENSUS", "PRED_TOTAL_RUNS") if k in r})
                else:
                    merged[key] = r
            _pg_upsert_picks(pg, list(merged.values()), today)
            log.info("PG: daily_picks upserted (%d rows)", len(merged))
        except Exception:
            log.exception("Failed to upsert daily_picks rows")
            errors += 1

    # ── picks/history ───────────────────────────────────────────────────────
    try:
        history_rows = _sf_query(sf, _HISTORY_SQL)
        payload = _build_history_payload(history_rows)
        if pg:
            _pg_set_cache(pg, "picks/history", today, payload)
            log.info("PG: picks/history written (%d rows)", len(history_rows))
        if bucket:
            _write_s3(bucket, f"api-cache/{today}/picks/history.json", payload)
    except Exception:
        log.exception("Failed to write picks/history")
        errors += 1

    # ── performance/summary ─────────────────────────────────────────────────
    try:
        try:
            perf_rows = _sf_query(sf, _BANKROLL_SQL)
            source = "mart_bankroll_state"
        except Exception:
            log.warning("mart_bankroll_state unavailable — falling back")
            perf_rows = _sf_query(sf, _CLV_SUMMARY_SQL)
            source = "mart_clv_labeled_games"
        if not perf_rows:
            perf_rows = _sf_query(sf, _CLV_SUMMARY_SQL)
            source = "mart_clv_labeled_games"
        payload = _build_performance_payload(perf_rows, source)
        if pg:
            _pg_set_cache(pg, "performance/summary", today, payload)
            log.info("PG: performance/summary written (source=%s)", source)
        if bucket:
            _write_s3(bucket, f"api-cache/{today}/performance/summary.json", payload)
    except Exception:
        log.exception("Failed to write performance/summary")
        errors += 1

    # ── game detail blobs (one blob per game) ───────────────────────────────
    game_pks = list({r["GAME_PK"] for r in picks_rows} | {r["GAME_PK"] for r in ev_rows})
    if game_pks and pg:
        try:
            final_pks: set[int] = set()
            detail_map = _assemble_game_detail_payloads(sf, game_pks, final_pks)
            for gp, (detail_payload, is_final) in detail_map.items():
                cache_key = f"picks/game/{gp}"
                _pg_set_cache(pg, cache_key, today, detail_payload, is_permanent=is_final)
                if bucket and is_final:
                    _write_s3(bucket, f"api-cache/permanent/{cache_key}.json", detail_payload)
                elif bucket:
                    _write_s3(bucket, f"api-cache/{today}/{cache_key}.json", detail_payload)
            log.info("PG: game detail written for %d games", len(detail_map))
        except Exception:
            log.exception("Failed to write game detail blobs")
            errors += 1

    sf.close()
    if pg:
        pg.close()

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
