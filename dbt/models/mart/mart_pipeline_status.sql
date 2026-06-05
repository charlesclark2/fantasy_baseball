{{
    config(
        materialized='view',
        schema='betting',
    )
}}

/*
mart_pipeline_status — A1.3

Thin view over baseball_data.betting_ml.pipeline_status for the Streamlit app.
Adds a derived `is_fresh` flag: predictions are considered fresh when the
pipeline completed successfully and predict_today_complete_ts is within the
last 6 hours. The app shows a warning banner when is_fresh = FALSE.
*/

SELECT
    run_date,
    job_start_ts,
    predict_today_complete_ts,
    lineup_confirmed_complete_ts,
    signal_completeness_score,
    n_games_scored,
    n_qualified_bets,
    pipeline_status,
    updated_at,
    CASE
        WHEN pipeline_status = 'complete'
         AND predict_today_complete_ts >= DATEADD('hour', -6, CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()))
        THEN TRUE
        ELSE FALSE
    END AS is_fresh
FROM baseball_data.betting_ml.pipeline_status
