-- =============================================================================
-- DDL: baseball_data.betting_features.feature_pregame_market_features
-- Story: Epic 15.1 — Market state / odds snapshots SCD-2
--
-- Grain: (game_pk, market_type, bookmaker_key, valid_from) — one row per
--        distinct line state per bookmaker per market per game.
--
-- SCD-2 change-detection: record_hash over (home_moneyline_american,
-- away_moneyline_american, total_line, over_american, under_american).
-- A new row is written whenever any of these values changes. Vig-adjusted
-- implied probs and vig scalars are derived from prices and recomputed on
-- insert; they are not part of the change-detection hash.
--
-- Market types:
--   h2h     — moneyline; totals columns are NULL
--   totals  — over/under line; h2h columns are NULL
--
-- Coverage:
--   Odds API:   2021-01-01 onward (append-only, full replay possible)
--   Parlay API: 2026-05-26 onward (live start date)
--
-- AS-OF query pattern (point-in-time):
--   WHERE valid_from <= :prediction_ts
--     AND (valid_to IS NULL OR valid_to > :prediction_ts)
--     AND bookmaker_key = 'lowvig'
--     AND market_type = 'h2h'
--
-- Reference implementation: mart_sub_model_signals (Story 2.4 SCD-2 pattern).
-- =============================================================================

CREATE TABLE IF NOT EXISTS baseball_data.betting_features.feature_pregame_market_features (

    -- -------------------------------------------------------------------------
    -- Natural key
    -- -------------------------------------------------------------------------
    game_pk             NUMBER          NOT NULL,
    market_type         VARCHAR(20)     NOT NULL,   -- 'h2h' | 'totals'
    bookmaker_key       VARCHAR(50)     NOT NULL,

    -- -------------------------------------------------------------------------
    -- Game metadata
    -- -------------------------------------------------------------------------
    game_date           DATE,
    commence_time       TIMESTAMP_NTZ,

    -- -------------------------------------------------------------------------
    -- h2h market columns (NULL for totals rows)
    -- -------------------------------------------------------------------------
    home_moneyline_american     FLOAT,
    away_moneyline_american     FLOAT,
    home_moneyline_decimal      FLOAT,
    away_moneyline_decimal      FLOAT,
    home_implied_prob           FLOAT,  -- vig-adjusted: raw_home / (raw_home + raw_away)
    away_implied_prob           FLOAT,  -- vig-adjusted: raw_away / (raw_home + raw_away)
    total_market_vig            FLOAT,  -- sum(1/decimal) - 1 across both outcomes

    -- -------------------------------------------------------------------------
    -- totals market columns (NULL for h2h rows)
    -- -------------------------------------------------------------------------
    total_line                  FLOAT,
    over_american               FLOAT,
    under_american              FLOAT,
    over_decimal                FLOAT,
    under_decimal               FLOAT,
    over_implied_prob           FLOAT,  -- vig-adjusted
    under_implied_prob          FLOAT,  -- vig-adjusted
    totals_market_vig           FLOAT,

    -- -------------------------------------------------------------------------
    -- Source metadata
    -- -------------------------------------------------------------------------
    source_system       VARCHAR(20),                -- 'odds_api' | 'parlay_api'
    ingestion_ts        TIMESTAMP_NTZ,              -- original ingestion_ts from mart_odds_outcomes

    -- -------------------------------------------------------------------------
    -- SCD-2 columns (Story 2.4 convention)
    -- -------------------------------------------------------------------------
    valid_from          TIMESTAMP_NTZ   NOT NULL,   -- = ingestion_ts of this snapshot
    valid_to            TIMESTAMP_NTZ,              -- NULL when this is the current row
    is_current          BOOLEAN         NOT NULL,
    record_hash         VARCHAR(32)     NOT NULL,   -- MD5 over price columns; drives change detection
    computed_at         TIMESTAMP_NTZ   NOT NULL    -- when the backfill/writer wrote this row

);

ALTER TABLE baseball_data.betting_features.feature_pregame_market_features
    ADD CONSTRAINT pk_market_features
    PRIMARY KEY (game_pk, market_type, bookmaker_key, valid_from);

COMMENT ON TABLE baseball_data.betting_features.feature_pregame_market_features IS
    'SCD-2 store for pre-game market state (moneyline and totals). One row per distinct line state per (game_pk, market_type, bookmaker_key). Enables point-in-time odds replay for CLV reconstruction and walk-forward backtesting. Story 15.1.';
