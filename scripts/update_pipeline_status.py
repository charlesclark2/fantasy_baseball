"""
update_pipeline_status.py — A1.3

Upserts one row per game day into baseball_data.betting_ml.pipeline_status after
predict_today_morning completes. The row summarises the morning pipeline run so
the Streamlit app and mart_pipeline_status can surface freshness to users.

Called by the update_pipeline_status Dagster op at the end of daily_ingestion_job,
immediately after predict_today_morning.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

_ML_SCHEMA = "baseball_data.betting_ml"
_FEATURES_SCHEMA = "baseball_data.betting_features"
_MART_SCHEMA = "baseball_data.betting"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_ML_SCHEMA}.pipeline_status (
    run_date                     DATE          NOT NULL,
    job_start_ts                 TIMESTAMP_NTZ,
    predict_today_complete_ts    TIMESTAMP_NTZ,
    lineup_confirmed_complete_ts TIMESTAMP_NTZ,
    signal_completeness_score    FLOAT,
    n_games_scored               INT,
    n_qualified_bets             INT,
    pipeline_status              VARCHAR(16),
    updated_at                   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_pipeline_status PRIMARY KEY (run_date)
)
"""

# N floor groups that count toward the completeness score (matches check_signal_freshness.py).
_FLOOR_COLS = [
    "run_env_mu_v4",
    "pred_runs_mu_v2",
    "starter_suppression_mu_v1",
    "starter_ip_mu_v1",
    "bullpen_mu_v2",
]
_N_FLOOR = len(_FLOOR_COLS)


def _completeness_expr() -> str:
    parts = [f"IFF(s.{c} IS NOT NULL, 1, 0)" for c in _FLOOR_COLS]
    return " + ".join(parts)


def main() -> None:
    today = date.today().isoformat()
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()

        cur.execute(_DDL)

        # Today's prediction summary from daily_model_predictions.
        cur.execute(f"""
            SELECT
                COUNT(DISTINCT game_pk)                                       AS n_games_scored,
                COUNT(CASE WHEN qualified_bet = TRUE THEN 1 END)             AS n_qualified_bets,
                MIN(inserted_at)                                              AS job_start_ts,
                MAX(CASE WHEN prediction_type = 'morning'
                         THEN inserted_at END)                                AS predict_today_complete_ts,
                MAX(CASE WHEN prediction_type = 'post_lineup'
                         THEN inserted_at END)                                AS lineup_confirmed_complete_ts
            FROM {_ML_SCHEMA}.daily_model_predictions
            WHERE score_date = '{today}'
        """)
        cols = [d[0].lower() for d in cur.description]
        preds = dict(zip(cols, cur.fetchone()))

        # Scheduled regular-season games today.
        cur.execute(f"""
            SELECT COUNT(*) AS n_scheduled
            FROM {_MART_SCHEMA}.stg_statsapi_games
            WHERE official_date = '{today}' AND game_type = 'R'
        """)
        n_scheduled = cur.fetchone()[0] or 0

        # Signal completeness score: average over the latest completed game slate.
        comp_expr = _completeness_expr()
        cur.execute(f"""
            WITH latest_date AS (
                SELECT MAX(game_date) AS ref_date
                FROM {_MART_SCHEMA}.mart_game_results
                WHERE game_type = 'R' AND home_final_score IS NOT NULL
            ),
            sig AS (
                SELECT ({comp_expr}) / {_N_FLOOR}.0 AS completeness
                FROM {_FEATURES_SCHEMA}.feature_pregame_sub_model_signals s
                JOIN {_MART_SCHEMA}.mart_game_results g ON g.game_pk = s.game_pk
                JOIN latest_date d ON g.game_date = d.ref_date
            )
            SELECT COALESCE(AVG(completeness), 0.0) AS signal_completeness_score
            FROM sig
        """)
        signal_score = float(cur.fetchone()[0] or 0.0)

        n_games = int(preds.get("n_games_scored") or 0)
        if n_games == 0:
            status = "failed"
        elif n_scheduled > 0 and n_games >= n_scheduled:
            status = "complete"
        else:
            status = "partial"

        # DELETE + INSERT (idempotent; safe for a single row per day).
        cur.execute(
            f"DELETE FROM {_ML_SCHEMA}.pipeline_status WHERE run_date = %s",
            [today],
        )
        cur.execute(
            f"""
            INSERT INTO {_ML_SCHEMA}.pipeline_status (
                run_date, job_start_ts, predict_today_complete_ts,
                lineup_confirmed_complete_ts, signal_completeness_score,
                n_games_scored, n_qualified_bets, pipeline_status, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP())
            """,
            [
                today,
                preds.get("job_start_ts"),
                preds.get("predict_today_complete_ts"),
                preds.get("lineup_confirmed_complete_ts"),
                signal_score,
                n_games,
                int(preds.get("n_qualified_bets") or 0),
                status,
            ],
        )

        print(
            f"pipeline_status upserted: run_date={today} status={status} "
            f"n_games={n_games}/{n_scheduled} signal_score={signal_score:.2f}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
