-- =============================================================================
-- fg_zips_hitting_raw
-- Append-only raw table for FanGraphs ZiPS / Steamer hitting projections.
-- Grain: one row per ingestion run × batter × projection_type.
-- projection_type: 'rzips' (in-season ZiPS), 'steamer', or 'zips_YYYY' (historical).
-- =============================================================================

USE DATABASE baseball_data;

CREATE SCHEMA IF NOT EXISTS fangraphs;

USE SCHEMA fangraphs;

CREATE TABLE IF NOT EXISTS fg_zips_hitting_raw (

    -- ── Grain columns ───────────────────────────────────────────────────────
    season              INTEGER         NOT NULL,
    batter_name         VARCHAR(256),
    fg_batter_id        VARCHAR(64),
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
