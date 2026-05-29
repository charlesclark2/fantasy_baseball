-- =============================================================================
-- offense_v1_signals.sql
-- Story 4.3 (2026-05-28)
-- =============================================================================
-- Per game-side offensive quality signals from the offense_v1 LightGBM model.
-- Written by betting_ml/scripts/offense_v1/generate_offense_signals.py via
-- VARCHAR temp table + MERGE (no PARSE_JSON; no USE statements).
--
-- Grain: game_pk × side × model_version
-- Primary key enforces one row per (game, side, model) — MERGE is idempotent.
-- =============================================================================

CREATE TABLE IF NOT EXISTS baseball_data.betting_features.offense_v1_signals (
    game_pk          VARCHAR(20)       NOT NULL,
    side             VARCHAR(4)        NOT NULL,   -- 'home' or 'away'
    game_date        DATE              NOT NULL,
    game_year        INTEGER           NOT NULL,
    pred_runs_raw    FLOAT             NOT NULL,   -- bias-corrected LightGBM prediction
    runs_index       FLOAT             NOT NULL,   -- 100 × pred_runs_raw / season_league_avg_pred
    model_version    VARCHAR(20)       NOT NULL,   -- e.g. 'offense_v1'
    ingestion_ts     TIMESTAMP_NTZ     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (game_pk, side, model_version)
);
