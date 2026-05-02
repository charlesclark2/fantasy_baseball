-- =============================================================================
-- weather_raw.sql
-- Creates the baseball_data.statsapi.weather_raw table for storing raw
-- game-day weather API payloads per outdoor-park game.
--
-- Grain: one row per game_pk × venue_id (upserted on each ingestion run).
-- Dome parks are excluded at ingest time — no rows for roof_type = 'fixed'.
--
-- Source API: Open-Meteo (primary, no key) or OpenWeatherMap (fallback).
-- Ingest script: scripts/ingest_weather.py
-- =============================================================================

USE DATABASE baseball_data;

USE SCHEMA statsapi;

CREATE TABLE IF NOT EXISTS weather_raw (

    -- ── Game identifiers ───────────────────────────────────────────────────────
    game_pk             INTEGER        NOT NULL,   -- MLB Stats API game identifier
    venue_id            INTEGER        NOT NULL,   -- MLB Stats API venue identifier

    -- ── Scheduling context ─────────────────────────────────────────────────────
    game_datetime_utc   TIMESTAMP_NTZ  NOT NULL,   -- scheduled first pitch (UTC)
    fetch_offset_hours  FLOAT,                     -- hours before first pitch when fetched
                                                   -- negative = fetched after game started

    -- ── Weather conditions at first pitch ─────────────────────────────────────
    temp_f              FLOAT,                     -- temperature (°F)
    wind_speed_mph      FLOAT,                     -- wind speed (mph)
    wind_direction_deg  INTEGER,                   -- meteorological wind direction (degrees)
                                                   -- 0/360 = from North, 90 = from East
    humidity_pct        INTEGER,                   -- relative humidity (%)
    condition_text      TEXT,                      -- API weather condition description

    -- ── Ingestion metadata ─────────────────────────────────────────────────────
    api_source          TEXT,                      -- 'open-meteo' or 'openweathermap'
    loaded_at           TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP,

    -- ── Constraint ────────────────────────────────────────────────────────────
    CONSTRAINT pk_weather_raw PRIMARY KEY (game_pk, venue_id)
);
