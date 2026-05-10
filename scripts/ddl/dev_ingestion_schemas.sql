-- =============================================================================
-- dev_ingestion_schemas.sql
-- Creates parlayapi_dev and oddsapi_dev schemas for DEV.4 --target dev testing.
-- Tables are cloned from prod using CREATE TABLE ... LIKE so schema stays in sync.
-- Run once; fully idempotent (CREATE SCHEMA IF NOT EXISTS + CREATE TABLE IF NOT EXISTS).
--
-- All names fully qualified — no USE statements.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- parlayapi_dev  (mirrors baseball_data.parlayapi)
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS baseball_data.parlayapi_dev;

CREATE TABLE IF NOT EXISTS baseball_data.parlayapi_dev.mlb_events_raw
    LIKE baseball_data.parlayapi.mlb_events_raw;

CREATE TABLE IF NOT EXISTS baseball_data.parlayapi_dev.mlb_odds_raw
    LIKE baseball_data.parlayapi.mlb_odds_raw;

CREATE TABLE IF NOT EXISTS baseball_data.parlayapi_dev.mlb_matches_raw
    LIKE baseball_data.parlayapi.mlb_matches_raw;

CREATE TABLE IF NOT EXISTS baseball_data.parlayapi_dev.mlb_line_movement_raw
    LIKE baseball_data.parlayapi.mlb_line_movement_raw;

CREATE TABLE IF NOT EXISTS baseball_data.parlayapi_dev.mlb_canonical_events_raw
    LIKE baseball_data.parlayapi.mlb_canonical_events_raw;

-- ---------------------------------------------------------------------------
-- oddsapi_dev  (mirrors baseball_data.oddsapi)
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS baseball_data.oddsapi_dev;

CREATE TABLE IF NOT EXISTS baseball_data.oddsapi_dev.mlb_events_raw
    LIKE baseball_data.oddsapi.mlb_events_raw;

CREATE TABLE IF NOT EXISTS baseball_data.oddsapi_dev.mlb_odds_raw
    LIKE baseball_data.oddsapi.mlb_odds_raw;
