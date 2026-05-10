-- =============================================================================
-- parlayapi_raw_tables.sql
-- Creates the raw ingestion tables inside the baseball_data.parlayapi schema.
-- Schema must already exist (created manually 2026-05-09).
-- All tables use fully qualified names (database.schema.table) — no USE statements.
--
-- Tables:
--   mlb_events_raw         — one row per call to /v1/sports/baseball_mlb/events
--   mlb_odds_raw           — one row per call to /v1/sports/baseball_mlb/odds
--   mlb_matches_raw        — one row per call to /v1/historical/sports/baseball_mlb/matches
--   mlb_line_movement_raw  — one row per call to /v1/sports/baseball_mlb/line-movement
--
-- Design principles:
--   • Append-only: rows are never updated; every ingest run adds new rows.
--   • Full fidelity: raw_json stores the complete API response as VARIANT.
--   • Observability: metadata columns enable auditing and replay without
--     re-querying the API.
--   • Ergonomics: extracted relational columns support fast filtering and
--     downstream dbt joins without requiring JSON parsing for common fields.
--
-- Auth note: Parlay API does not return x-requests-used/remaining headers.
--   The x_requests_used / x_requests_remaining columns are retained for
--   schema symmetry with oddsapi tables but will always be NULL.
--   Credit tracking is handled via call-count logging in the ingestion script.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- mlb_events_raw
-- One row per ingestion run against /v1/sports/baseball_mlb/events.
-- raw_json holds the full response array exactly as received.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS baseball_data.parlayapi.mlb_events_raw (

    -- ── Ingestion metadata ──────────────────────────────────────────────────
    ingestion_ts            TIMESTAMP_NTZ   NOT NULL,   -- wall-clock time the row was written to Snowflake
    load_id                 VARCHAR(64),                -- UUID grouping rows from the same run
    source_system           VARCHAR(64)     DEFAULT 'parlay_api',
    process_name            VARCHAR(128)    DEFAULT 'parlay_api_ingestion.py',
    source_endpoint         VARCHAR(256),               -- e.g. /v1/sports/baseball_mlb/events
    request_url             VARCHAR(2048),              -- fully resolved URL including query string
    request_params          VARIANT,                    -- parameters dict sent with the request
    http_status_code        NUMBER(3),                  -- HTTP response status (200, 403, etc.)
    x_requests_used         NUMBER,                     -- always NULL — Parlay API does not expose this header
    x_requests_remaining    NUMBER,                     -- always NULL — Parlay API does not expose this header
    call_sequence           NUMBER,                     -- 1-based counter of API calls within this run

    -- ── Raw payload ─────────────────────────────────────────────────────────
    raw_json                VARIANT         NOT NULL,   -- full API response stored as received

    -- ── Extracted relational fields (convenience; not authoritative) ────────
    event_id                VARCHAR(64),                -- event.id (Parlay-specific event identifier)
    canonical_event_id      VARCHAR(64),                -- event.canonical_event_id (cross-source stable ID)
    sport_key               VARCHAR(64),                -- event.sport_key
    sport_title             VARCHAR(128),               -- event.sport_title
    commence_time           TIMESTAMP_NTZ,              -- event.commence_time (UTC)
    home_team               VARCHAR(128),               -- event.home_team
    away_team               VARCHAR(128)                -- event.away_team
);

-- ---------------------------------------------------------------------------
-- mlb_odds_raw
-- One row per ingestion run against /v1/sports/baseball_mlb/odds.
-- raw_json holds the full response array exactly as received.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS baseball_data.parlayapi.mlb_odds_raw (

    -- ── Ingestion metadata ──────────────────────────────────────────────────
    ingestion_ts            TIMESTAMP_NTZ   NOT NULL,
    load_id                 VARCHAR(64),
    source_system           VARCHAR(64)     DEFAULT 'parlay_api',
    process_name            VARCHAR(128)    DEFAULT 'parlay_api_ingestion.py',
    source_endpoint         VARCHAR(256),               -- e.g. /v1/sports/baseball_mlb/odds
    request_url             VARCHAR(2048),
    request_params          VARIANT,                    -- includes markets, regions, oddsFormat, etc.
    http_status_code        NUMBER(3),
    x_requests_used         NUMBER,                     -- always NULL — Parlay API does not expose this header
    x_requests_remaining    NUMBER,                     -- always NULL — Parlay API does not expose this header
    call_sequence           NUMBER,                     -- 1-based counter; one call per region per market batch

    -- ── Raw payload ─────────────────────────────────────────────────────────
    raw_json                VARIANT         NOT NULL,

    -- ── Extracted relational fields (convenience; not authoritative) ────────
    event_id                VARCHAR(64),                -- event.id
    canonical_event_id      VARCHAR(64),                -- event.canonical_event_id
    sport_key               VARCHAR(64),
    sport_title             VARCHAR(128),
    commence_time           TIMESTAMP_NTZ,
    home_team               VARCHAR(128),
    away_team               VARCHAR(128),
    bookmakers_count        NUMBER                      -- ARRAY_SIZE(event.bookmakers) for quick payload breadth check
);

-- ---------------------------------------------------------------------------
-- mlb_matches_raw
-- One row per ingestion run against /v1/historical/sports/baseball_mlb/matches.
-- Returns a flat per-bookmaker-source array (not nested like /odds).
-- Includes game results (home_score, away_score, result) and has_odds flag.
-- Useful for: game result enrichment, ML-only historical odds, has_odds auditing.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS baseball_data.parlayapi.mlb_matches_raw (

    -- ── Ingestion metadata ──────────────────────────────────────────────────
    ingestion_ts            TIMESTAMP_NTZ   NOT NULL,
    load_id                 VARCHAR(64),
    source_system           VARCHAR(64)     DEFAULT 'parlay_api',
    process_name            VARCHAR(128)    DEFAULT 'parlay_api_ingestion.py',
    source_endpoint         VARCHAR(256),               -- e.g. /v1/historical/sports/baseball_mlb/matches
    request_url             VARCHAR(2048),
    request_params          VARIANT,                    -- includes date= param
    http_status_code        NUMBER(3),
    call_sequence           NUMBER,

    -- ── Raw payload ─────────────────────────────────────────────────────────
    raw_json                VARIANT         NOT NULL,   -- full response array; one element per (game × source)

    -- ── Extracted relational fields (convenience; not authoritative) ────────
    -- These come from the flat /matches schema (different from /events nesting)
    game_date               DATE,                       -- matches[].game_date
    sport_key               VARCHAR(64),
    home_team               VARCHAR(128),
    away_team               VARCHAR(128),
    season                  VARCHAR(8),                 -- matches[].season
    record_count            NUMBER                      -- ARRAY_SIZE(response) for quick completeness check
);

-- ---------------------------------------------------------------------------
-- mlb_line_movement_raw
-- One row per ingestion run against /v1/sports/baseball_mlb/line-movement.
-- Called once per event_id. raw_json holds the full snapshots array.
--
-- IMPORTANT — downstream pipeline note:
--   raw_json contains a snapshots[] array of timestamped price changes.
--   Any staging or mart model consuming this table must account for the
--   nested structure: one top-level record per (event × source × market),
--   each with an arbitrary-length snapshots array. Do NOT flatten to a
--   single row per event without first deciding whether to explode snapshots
--   (for time-series features) or summarize (opening/closing price only).
--   See Section 2.4 of parlay_api_endpoint_mapping.md for the full schema.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS baseball_data.parlayapi.mlb_line_movement_raw (

    -- ── Ingestion metadata ──────────────────────────────────────────────────
    ingestion_ts            TIMESTAMP_NTZ   NOT NULL,
    load_id                 VARCHAR(64),
    source_system           VARCHAR(64)     DEFAULT 'parlay_api',
    process_name            VARCHAR(128)    DEFAULT 'parlay_api_ingestion.py',
    source_endpoint         VARCHAR(256),               -- e.g. /v1/sports/baseball_mlb/line-movement
    request_url             VARCHAR(2048),
    request_params          VARIANT,                    -- includes eventId= param
    http_status_code        NUMBER(3),
    call_sequence           NUMBER,                     -- 1-based counter; one call per event_id per run

    -- ── Raw payload ─────────────────────────────────────────────────────────
    raw_json                VARIANT         NOT NULL,   -- full response array for this event_id

    -- ── Extracted relational fields (convenience; not authoritative) ────────
    event_id                VARCHAR(64),                -- the eventId queried
    home_team               VARCHAR(128),               -- from first record in response array
    away_team               VARCHAR(128),               -- from first record in response array
    record_count            NUMBER,                     -- ARRAY_SIZE(response) — number of (source × market) records returned
    markets_captured        VARIANT                     -- ARRAY_AGG of distinct market_key values (for auditing coverage)
);
