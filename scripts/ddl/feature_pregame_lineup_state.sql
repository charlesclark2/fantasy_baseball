-- =============================================================================
-- DDL: baseball_data.betting_features.feature_pregame_lineup_state
-- Story: Epic 15.2 — Lineup state SCD-2
--
-- Grain: (game_pk, home_away, valid_from) — one row per distinct lineup
--        composition state per game per side.
--
-- SCD-2 change-detection: record_hash over slot_1..9 player_ids.
-- A new row is written whenever any batting slot's player changes (scratch,
-- replacement). Positions and has_full_lineup are carried forward but not
-- part of the hash — position moves within the same player do not trigger
-- a new state.
--
-- Source: baseball_data.statsapi.monthly_schedule (append-only post-Epic-T).
--   valid_from = ingestion_ts: when this lineup state was first observed in
--   a Stats API ingest. All snapshots for the same lineup composition collapse
--   to a single SCD-2 row via hash-based change detection.
--
-- Coverage:
--   Forward-only from Epic T conversion date (2026-05-12).
--   Pre-Epic-T rows have NULL ingestion_ts and are excluded; their lineup
--   history is permanently unrecoverable.
--
-- AS-OF query pattern (point-in-time):
--   WHERE game_pk = :game_pk
--     AND home_away = :side
--     AND valid_from <= :prediction_ts
--     AND (valid_to IS NULL OR valid_to > :prediction_ts)
--
-- Reference implementation: feature_pregame_market_features (Story 15.1).
-- =============================================================================

CREATE TABLE IF NOT EXISTS baseball_data.betting_features.feature_pregame_lineup_state (

    -- -------------------------------------------------------------------------
    -- Natural key
    -- -------------------------------------------------------------------------
    game_pk             NUMBER          NOT NULL,
    home_away           VARCHAR(4)      NOT NULL,   -- 'home' | 'away'

    -- -------------------------------------------------------------------------
    -- Game metadata
    -- -------------------------------------------------------------------------
    official_date       DATE,
    has_full_lineup     BOOLEAN,                    -- all 9 slots populated

    -- -------------------------------------------------------------------------
    -- Lineup slots (player_id + position abbreviation per batting slot)
    -- -------------------------------------------------------------------------
    slot_1_player_id    NUMBER,
    slot_1_position     VARCHAR(5),
    slot_2_player_id    NUMBER,
    slot_2_position     VARCHAR(5),
    slot_3_player_id    NUMBER,
    slot_3_position     VARCHAR(5),
    slot_4_player_id    NUMBER,
    slot_4_position     VARCHAR(5),
    slot_5_player_id    NUMBER,
    slot_5_position     VARCHAR(5),
    slot_6_player_id    NUMBER,
    slot_6_position     VARCHAR(5),
    slot_7_player_id    NUMBER,
    slot_7_position     VARCHAR(5),
    slot_8_player_id    NUMBER,
    slot_8_position     VARCHAR(5),
    slot_9_player_id    NUMBER,
    slot_9_position     VARCHAR(5),

    -- -------------------------------------------------------------------------
    -- Source metadata
    -- -------------------------------------------------------------------------
    ingestion_ts        TIMESTAMP_NTZ,              -- Stats API ingest timestamp of this snapshot

    -- -------------------------------------------------------------------------
    -- SCD-2 columns (Story 2.4 convention)
    -- -------------------------------------------------------------------------
    valid_from          TIMESTAMP_NTZ   NOT NULL,   -- = ingestion_ts of first observation of this state
    valid_to            TIMESTAMP_NTZ,              -- NULL when this is the current row
    is_current          BOOLEAN         NOT NULL,
    record_hash         VARCHAR(32)     NOT NULL,   -- MD5 over slot_1..9 player_ids; drives change detection
    computed_at         TIMESTAMP_NTZ   NOT NULL    -- when the backfill/writer wrote this row

);

ALTER TABLE baseball_data.betting_features.feature_pregame_lineup_state
    ADD CONSTRAINT pk_lineup_state
    PRIMARY KEY (game_pk, home_away, valid_from);

COMMENT ON TABLE baseball_data.betting_features.feature_pregame_lineup_state IS
    'SCD-2 store for pre-game lineup state. One row per distinct lineup composition per (game_pk, home_away). Enables point-in-time lineup replay for pre-scratch vs. post-scratch predictions. Coverage: Epic T conversion date (2026-05-12) onward. Story 15.2.';
