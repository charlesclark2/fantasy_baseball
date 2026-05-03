-- =============================================================================
-- fg_hitting_leaderboard_raw
-- Append-only raw table for FanGraphs hitting leaderboard rolling snapshots.
-- Grain: one row per ingestion run × batter × window_type × window date range.
-- window_type: '7d', '14d', '30d', 'season'
-- =============================================================================

USE DATABASE baseball_data;

CREATE SCHEMA IF NOT EXISTS fangraphs;

USE SCHEMA fangraphs;

CREATE TABLE IF NOT EXISTS fg_hitting_leaderboard_raw (

    -- ── Grain columns ───────────────────────────────────────────────────────
    season              INTEGER         NOT NULL,
    window_type         VARCHAR(16)     NOT NULL,
    window_start        DATE            NOT NULL,
    window_end          DATE            NOT NULL,

    -- ── Ingestion metadata ──────────────────────────────────────────────────
    load_id             VARCHAR(64)     NOT NULL,
    ingestion_ts        TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_endpoint     VARCHAR(1024),
    request_params      VARIANT,
    http_status_code    INTEGER,

    -- ── Payload ─────────────────────────────────────────────────────────────
    raw_json            VARIANT         NOT NULL

);
