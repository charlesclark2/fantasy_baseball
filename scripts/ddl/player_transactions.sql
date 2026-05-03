-- =============================================================================
-- player_transactions.sql
-- DDL for baseball_data.statsapi.player_transactions
-- Card 7.I — Injury / Confirmed Lineup Features
-- =============================================================================
-- Stores MLB player roster transaction events fetched from the Stats API
-- transactions endpoint:
--   GET https://statsapi.mlb.com/api/v1/transactions?sportId=1
--         &startDate=YYYY-MM-DD&endDate=YYYY-MM-DD
--
-- Populated daily by scripts/ingest_transactions.py with a 7-day lookback
-- to capture retroactive IL placements that post-date game day.
-- =============================================================================

CREATE TABLE IF NOT EXISTS baseball_data.statsapi.player_transactions (
    transaction_id       VARCHAR(30)     NOT NULL,
    player_id            INTEGER         NOT NULL,
    player_name          VARCHAR(120),
    team_id              INTEGER,
    team_name            VARCHAR(100),
    transaction_date     DATE            NOT NULL,
    effective_date       DATE,
    resolution_date      DATE,
    type_code            VARCHAR(60)     NOT NULL,
    type_description     VARCHAR(255),
    description          VARCHAR(2000),
    ingestion_ts         TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    load_id              VARCHAR(36)     NOT NULL DEFAULT UUID_STRING(),
    raw_json             VARIANT,
    PRIMARY KEY (transaction_id)
);
