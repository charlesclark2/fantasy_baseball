"""write_api_cache.py
--------------------
Queries Snowflake once after predict_today_morning completes and writes
API-ready JSON to S3 so FastAPI can serve requests without hitting Snowflake.

Called by write_api_cache_op in daily_ingestion_ops.py.

S3 key pattern: api-cache/{YYYY-MM-DD}/{endpoint}.json
Endpoints written: picks/today.json, picks/ev.json, picks/history.json, performance/summary.json

Env vars required:
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH  (preferred)  or  SNOWFLAKE_PRIVATE_KEY (PEM/base64)
    CACHE_BUCKET                             (S3 bucket name)

Exits 0 on full success, 1 if either write fails.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
from datetime import datetime, timezone

import boto3
import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from betting_ml.utils.game_day import current_game_date_iso  # INC-22 — canonical US baseball-day

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


def _connect() -> snowflake.connector.SnowflakeConnection:
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


def _query(conn: snowflake.connector.SnowflakeConnection, sql: str) -> list[dict]:
    cur = conn.cursor(snowflake.connector.DictCursor)
    cur.execute(sql)
    return cur.fetchall()


# ── S3 cache write ───────────────────────────────────────────────────────────

def _write_s3(bucket: str, key: str, data: dict | list) -> None:
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, default=str),
        ContentType="application/json",
    )
    log.info("Wrote s3://%s/%s", bucket, key)


# ── Query definitions (mirrors app/backend/routers/picks.py + performance.py) ─

_PICKS_TODAY_SQL = """
WITH ranked AS (
    SELECT
        p.*,
        g.game_date AS game_start_utc,
        ROW_NUMBER() OVER (
            PARTITION BY p.game_pk
            ORDER BY p.inserted_at DESC
        ) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions p
    LEFT JOIN baseball_data.betting.stg_statsapi_games g ON g.game_pk = p.game_pk
    WHERE p.game_date = CURRENT_DATE
      AND p.prediction_type = 'post_lineup'
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
        NULL::FLOAT                                  AS market_total_line
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
        b.total_line_consensus                       AS market_total_line
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
            ORDER BY inserted_at DESC
        ) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions
    WHERE game_date = CURRENT_DATE
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
        NULL::FLOAT                                  AS pred_total_runs
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
        b.pred_total_runs
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
WHERE game_date = CURRENT_DATE
"""

_BANKROLL_SQL = """
SELECT total_bets, wins, win_rate, mean_clv,
       net_pnl_flat, net_pnl_kelly, sharpe_ratio
FROM baseball_data.betting.mart_bankroll_state
ORDER BY recorded_at DESC
LIMIT 1
"""

_CLV_SUMMARY_SQL = """
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


# ── Builders ─────────────────────────────────────────────────────────────────

def _ts(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _build_picks_payload(rows: list[dict], freshness_rows: list[dict]) -> dict:
    last_updated_at = None
    if freshness_rows and freshness_rows[0].get("LAST_UPDATED_AT"):
        last_updated_at = _ts(freshness_rows[0]["LAST_UPDATED_AT"])

    if last_updated_at:
        ts_dt = datetime.fromisoformat(last_updated_at.replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - ts_dt.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        pipeline_status = "ok" if age_h < 6 else "stale"
    else:
        pipeline_status = "no_predictions"

    picks = [
        {
            "game_pk": r["GAME_PK"],
            "game_date": str(r["GAME_DATE"]),
            "market_type": r["MARKET_TYPE"],
            "model_prob": r.get("MODEL_PROB"),
            "bovada_devig_prob": r.get("BOVADA_DEVIG_PROB"),
            "edge": r.get("EDGE"),
            "game_conviction_score": r.get("GAME_CONVICTION_SCORE"),
            "win_prob_ci_low": r.get("WIN_PROB_CI_LOW"),
            "win_prob_ci_high": r.get("WIN_PROB_CI_HIGH"),
            "lineup_confirmed": r.get("LINEUP_CONFIRMED"),
            "home_team": r.get("HOME_TEAM"),
            "away_team": r.get("AWAY_TEAM"),
            "pick_side": r.get("PICK_SIDE"),
            "game_start_utc": _ts(r.get("GAME_START_UTC")),
            "model_total_runs": r.get("MODEL_TOTAL_RUNS"),
            "market_total_line": r.get("MARKET_TOTAL_LINE"),
        }
        for r in rows
    ]

    return {
        "picks": picks,
        "data_quality": {
            "signal_completeness_score": None,
            "last_updated_at": last_updated_at,
            "pipeline_status": pipeline_status,
        },
    }


def _build_ev_payload(rows: list[dict]) -> dict:
    picks = [
        {
            "game_pk": r["GAME_PK"],
            "game_date": str(r.get("GAME_DATE") or ""),
            "game_start_utc": _ts(r.get("GAME_START_UTC")),
            "market_type": r["MARKET_TYPE"],
            "model_prob": r.get("MODEL_PROB"),
            "bovada_devig_prob": r.get("BOVADA_DEVIG_PROB"),
            "edge": r.get("EDGE"),
            "game_conviction_score": r.get("GAME_CONVICTION_SCORE"),
            "lineup_confirmed": r.get("LINEUP_CONFIRMED"),
            "qualified_bet": r.get("QUALIFIED_BET"),
            "home_team": r.get("HOME_TEAM"),
            "away_team": r.get("AWAY_TEAM"),
            "kelly_fraction": r.get("KELLY_FRACTION"),
            "total_line_consensus": r.get("TOTAL_LINE_CONSENSUS"),
            "pred_total_runs": r.get("PRED_TOTAL_RUNS"),
        }
        for r in rows
    ]
    return {"picks": picks, "total": len(picks)}


def _build_history_payload(rows: list[dict]) -> dict:
    picks = [
        {
            "game_pk": r["GAME_PK"],
            "game_date": str(r["GAME_DATE"]),
            "market_type": r["MARKET_TYPE"],
            "model_prob": r.get("MODEL_PROB"),
            "bovada_devig_prob": r.get("BOVADA_DEVIG_PROB"),
            "edge": r.get("EDGE"),
            "game_conviction_score": r.get("GAME_CONVICTION_SCORE"),
            "win_prob_ci_low": r.get("WIN_PROB_CI_LOW"),
            "win_prob_ci_high": r.get("WIN_PROB_CI_HIGH"),
            "lineup_confirmed": r.get("LINEUP_CONFIRMED"),
            "home_team": r.get("HOME_TEAM"),
            "away_team": r.get("AWAY_TEAM"),
            "clv": r.get("CLV"),
            "clv_positive": r.get("CLV_POSITIVE"),
            "actual_outcome": r.get("ACTUAL_OUTCOME"),
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
        "total_bets": total,
        "wins": wins,
        "win_rate": r.get("WIN_RATE") if source == "mart_bankroll_state" else (wins / total if total > 0 else None),
        "mean_clv": r.get("MEAN_CLV"),
        "net_pnl_flat": r.get("NET_PNL_FLAT"),
        "net_pnl_kelly": r.get("NET_PNL_KELLY"),
        "sharpe_ratio": r.get("SHARPE_RATIO"),
        "source": source,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    bucket = os.environ.get("CACHE_BUCKET")
    if not bucket:
        log.error("CACHE_BUCKET env var not set — cannot write cache")
        return 1

    today = current_game_date_iso()  # INC-22 — US baseball-day (LA), matches the read prefix + game_date
    prefix = f"api-cache/{today}"

    try:
        conn = _connect()
    except Exception:
        log.exception("Snowflake connection failed")
        return 1

    errors = 0

    # ── picks/today.json ────────────────────────────────────────────────────
    try:
        picks_rows = _query(conn, _PICKS_TODAY_SQL)
        fresh_rows = _query(conn, _FRESHNESS_SQL)
        payload = _build_picks_payload(picks_rows, fresh_rows)
        _write_s3(bucket, f"{prefix}/picks/today.json", payload)
        log.info("picks/today.json: %d picks", len(picks_rows))
    except Exception:
        log.exception("Failed to write picks/today.json")
        errors += 1

    # ── picks/ev.json ───────────────────────────────────────────────────────
    try:
        ev_rows = _query(conn, _EV_TODAY_SQL)
        payload = _build_ev_payload(ev_rows)
        _write_s3(bucket, f"{prefix}/picks/ev.json", payload)
        log.info("picks/ev.json: %d rows", len(ev_rows))
    except Exception:
        log.exception("Failed to write picks/ev.json")
        errors += 1

    # ── picks/history.json ──────────────────────────────────────────────────
    try:
        history_rows = _query(conn, _HISTORY_SQL)
        payload = _build_history_payload(history_rows)
        _write_s3(bucket, f"{prefix}/picks/history.json", payload)
        log.info("picks/history.json: %d rows", len(history_rows))
    except Exception:
        log.exception("Failed to write picks/history.json")
        errors += 1

    # ── performance/summary.json ────────────────────────────────────────────
    try:
        try:
            perf_rows = _query(conn, _BANKROLL_SQL)
            source = "mart_bankroll_state"
        except Exception:
            log.warning("mart_bankroll_state unavailable — falling back to mart_clv_labeled_games")
            perf_rows = _query(conn, _CLV_SUMMARY_SQL)
            source = "mart_clv_labeled_games"
        if not perf_rows:
            log.warning("mart_bankroll_state empty — falling back to mart_clv_labeled_games")
            perf_rows = _query(conn, _CLV_SUMMARY_SQL)
            source = "mart_clv_labeled_games"
        payload = _build_performance_payload(perf_rows, source)
        _write_s3(bucket, f"{prefix}/performance/summary.json", payload)
        log.info("performance/summary.json: source=%s", source)
    except Exception:
        log.exception("Failed to write performance/summary.json")
        errors += 1

    conn.close()
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
