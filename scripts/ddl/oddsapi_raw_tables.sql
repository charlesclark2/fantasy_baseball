-- =============================================================================
-- oddsapi_raw_tables.sql
-- Creates the baseball_data.oddsapi schema and its two raw ingestion tables:
--   mlb_events_raw  — one row per API call to the /events endpoint
--   mlb_odds_raw    — one row per API call to the /odds  endpoint
--
-- Design principles:
--   • Append-only: rows are never updated; every ingest run adds new rows.
--   • Full fidelity: raw_json stores the complete API response as VARIANT.
--   • Observability: metadata columns (source_endpoint, request_url, etc.)
--     enable auditing and replay without re-querying the API.
--   • Ergonomics: extracted relational columns support fast filtering and
--     downstream dbt joins without requiring JSON parsing for common fields.
-- =============================================================================

USE DATABASE baseball_data;

CREATE SCHEMA IF NOT EXISTS oddsapi;

USE SCHEMA oddsapi;

-- ---------------------------------------------------------------------------
-- mlb_events_raw
-- One row per ingestion run against the Odds API /v4/sports/baseball_mlb/events
-- endpoint. raw_json holds the full response array/object exactly as received.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mlb_events_raw (

    -- ── Ingestion metadata ──────────────────────────────────────────────────
    ingestion_ts            TIMESTAMP_NTZ   NOT NULL,   -- wall-clock time the row was written to Snowflake
    load_id                 VARCHAR(64),                -- UUID / run identifier grouping rows from the same run
    source_system           VARCHAR(64)     DEFAULT 'the_odds_api',
    process_name            VARCHAR(128)    DEFAULT 'odds_api_ingestion.py',
    source_endpoint         VARCHAR(256),               -- e.g. /v4/sports/baseball_mlb/events
    request_url             VARCHAR(2048),              -- fully resolved URL including query string
    request_params          VARIANT,                    -- parameters dict sent with the request
    http_status_code        NUMBER(3),                  -- HTTP response status (200, 429, etc.)
    x_requests_used         NUMBER,                     -- value of X-Requests-Used response header
    x_requests_remaining    NUMBER,                     -- value of X-Requests-Remaining response header

    -- ── Raw payload ─────────────────────────────────────────────────────────
    raw_json                VARIANT         NOT NULL,   -- full API response stored as received

    -- ── Extracted relational fields (convenience; not authoritative) ────────
    event_id                VARCHAR(64),                -- event.id
    sport_key               VARCHAR(64),                -- event.sport_key
    sport_title             VARCHAR(128),               -- event.sport_title
    commence_time           TIMESTAMP_NTZ,              -- event.commence_time (UTC)
    home_team               VARCHAR(128),               -- event.home_team
    away_team               VARCHAR(128)                -- event.away_team
);

-- ---------------------------------------------------------------------------
-- mlb_odds_raw
-- One row per ingestion run against the Odds API /v4/sports/baseball_mlb/odds
-- endpoint. raw_json holds the full response array/object exactly as received.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mlb_odds_raw (

    -- ── Ingestion metadata ──────────────────────────────────────────────────
    ingestion_ts            TIMESTAMP_NTZ   NOT NULL,
    load_id                 VARCHAR(64),
    source_system           VARCHAR(64)     DEFAULT 'the_odds_api',
    process_name            VARCHAR(128)    DEFAULT 'odds_api_ingestion.py',
    source_endpoint         VARCHAR(256),               -- e.g. /v4/sports/baseball_mlb/odds
    request_url             VARCHAR(2048),
    request_params          VARIANT,                    -- includes markets, regions, oddsFormat, etc.
    http_status_code        NUMBER(3),
    x_requests_used         NUMBER,
    x_requests_remaining    NUMBER,

    -- ── Raw payload ─────────────────────────────────────────────────────────
    raw_json                VARIANT         NOT NULL,

    -- ── Extracted relational fields (convenience; not authoritative) ────────
    event_id                VARCHAR(64),                -- event.id
    sport_key               VARCHAR(64),
    sport_title             VARCHAR(128),
    commence_time           TIMESTAMP_NTZ,
    home_team               VARCHAR(128),
    away_team               VARCHAR(128),
    bookmakers_count        NUMBER                      -- ARRAY_SIZE(event.bookmakers) for quick payload breadth check
);
