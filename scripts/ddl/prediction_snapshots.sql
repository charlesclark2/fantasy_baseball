-- prediction_snapshots.sql
-- Grain: one row per game_pk × target × reconstruction_type
--
-- Populated by:
--   predict_today.py             → reconstruction_type = 'live'    (Phase 9+, daily)
--   backfill_prediction_snapshots.py → reconstruction_type = 'best_effort' (one-time, Phase 9)
--
-- Purpose: Enable full CLV reconstruction for any historical game by storing
-- the exact feature snapshot used at prediction time plus the artifact URI.
-- See implementation_guide.md Story 13.4 for full context.
--
-- LEAKAGE GUARD: This table stores point-in-time snapshots; never join to
-- game outcome tables without a game_date < outcome_date predicate.

CREATE TABLE IF NOT EXISTS baseball_data.betting.prediction_snapshots (
    game_pk                     INTEGER         NOT NULL,
    target                      VARCHAR(30)     NOT NULL,   -- home_win | total_runs | run_diff
    model_version               VARCHAR(20)     NOT NULL,
    predicted_at                TIMESTAMP_NTZ   NOT NULL,
    predicted_at_confidence     VARCHAR(10),               -- exact | bounded | unknown
    prediction                  FLOAT,
    feature_snapshot            VARIANT,                    -- raw input features as JSON (pre-imputation)
    model_artifact_s3_uri       VARCHAR(500),
    reconstruction_type         VARCHAR(20)     NOT NULL,   -- live | best_effort
    inserted_at                 TIMESTAMP_NTZ   NOT NULL    DEFAULT CURRENT_TIMESTAMP()
);
