-- =============================================================================
-- create_actionnetwork_public_betting_raw.sql
-- Card 8.R — Action Network public betting percentages.
-- Grain: one row per (game_date, an_game_id). Idempotent via MERGE on those keys.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS baseball_data.actionnetwork;

CREATE TABLE IF NOT EXISTS baseball_data.actionnetwork.public_betting_raw (
    game_date              DATE         NOT NULL,
    an_game_id             VARCHAR(50),
    home_team_abbr         VARCHAR(10),
    away_team_abbr         VARCHAR(10),
    home_ml_money_pct      FLOAT,
    away_ml_money_pct      FLOAT,
    home_ml_ticket_pct     FLOAT,
    away_ml_ticket_pct     FLOAT,
    over_money_pct         FLOAT,
    under_money_pct        FLOAT,
    over_ticket_pct        FLOAT,
    under_ticket_pct       FLOAT,
    book_ids_used          VARCHAR(200),
    ingestion_timestamp    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
);
