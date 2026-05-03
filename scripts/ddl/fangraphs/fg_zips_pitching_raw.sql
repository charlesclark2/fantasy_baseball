-- =============================================================================
-- fg_zips_pitching_raw
-- Append-only raw table for FanGraphs ZiPS / Steamer pitching projections.
-- Grain: one row per ingestion run × pitcher × projection_type.
-- projection_type: 'rzips' (in-season ZiPS), 'steamer', or 'zips_YYYY' (historical).
-- =============================================================================

USE DATABASE baseball_data;

CREATE SCHEMA IF NOT EXISTS fangraphs;

USE SCHEMA fangraphs;

CREATE TABLE IF NOT EXISTS fg_zips_pitching_raw (

    -- ── Grain columns ───────────────────────────────────────────────────────
    season              INTEGER         NOT NULL,
    pitcher_name        VARCHAR(256),
    fg_pitcher_id       VARCHAR(64),
    projection_type     VARCHAR(64),

    -- ── Ingestion metadata ──────────────────────────────────────────────────
    load_id             VARCHAR(64)     NOT NULL,
    ingestion_ts        TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_endpoint     VARCHAR(1024),
    request_params      VARIANT,
    http_status_code    INTEGER,

    -- ── Payload ─────────────────────────────────────────────────────────────
    raw_json            VARIANT         NOT NULL

);
