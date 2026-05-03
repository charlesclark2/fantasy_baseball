-- =============================================================================
-- fg_stuff_plus_raw
-- Append-only raw table for FanGraphs Stuff+ pitching leaderboard.
-- Grain: one row per ingestion run × pitcher.
-- Full player row from the API response stored in raw_json VARIANT.
-- Stuff+ data is available from the 2020 season onward.
-- =============================================================================

USE DATABASE baseball_data;

CREATE SCHEMA IF NOT EXISTS fangraphs;

USE SCHEMA fangraphs;

CREATE TABLE IF NOT EXISTS fg_stuff_plus_raw (

    -- ── Grain columns ───────────────────────────────────────────────────────
    season              INTEGER         NOT NULL,
    pitcher_name        VARCHAR(256),
    fg_pitcher_id       VARCHAR(64),

    -- ── Ingestion metadata ──────────────────────────────────────────────────
    load_id             VARCHAR(64)     NOT NULL,
    ingestion_ts        TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_endpoint     VARCHAR(1024),
    request_params      VARIANT,
    http_status_code    INTEGER,

    -- ── Payload ─────────────────────────────────────────────────────────────
    raw_json            VARIANT         NOT NULL

);
