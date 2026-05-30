-- =============================================================================
-- starter_suppression_signals.sql
-- Story 5.3 (2026-05-29)
-- =============================================================================
-- Per game-side distributional starter suppression signals from the starter_v1 model
-- (LightGBM + Normal sigma or NGBoost Normal — champion selected by walk-forward CV NLL).
-- Written by betting_ml/scripts/starter_v1/generate_starter_signals.py via
-- VARCHAR temp table + MERGE (no PARSE_JSON; no USE statements).
--
-- Grain: game_pk × side × model_version
-- Primary key enforces one row per (game, side, model) — MERGE is idempotent.
-- Coverage: 2020–2026 regular season (Statcast xwOBA starts 2020).
-- =============================================================================

CREATE TABLE IF NOT EXISTS baseball_data.betting_features.starter_suppression_signals (
    game_pk                    VARCHAR(20)   NOT NULL,
    side                       VARCHAR(4)    NOT NULL,   -- 'home' or 'away'
    game_date                  DATE          NOT NULL,
    game_year                  INTEGER       NOT NULL,
    starter_suppression_mu     FLOAT         NOT NULL,   -- predicted mean xwOBA-against
    starter_suppression_sigma  FLOAT         NOT NULL,   -- Normal sigma (per-row for NGBoost; constant for LGBM)
    starter_suppression_signal FLOAT         NOT NULL,   -- z-score vs. season mean; negative = better suppression
    uncertainty                FLOAT         NOT NULL,   -- 80% PI width: 2 × 1.28 × sigma
    model_version              VARCHAR(20)   NOT NULL,   -- 'starter_v1'
    ingestion_ts               TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (game_pk, side, model_version)
);
