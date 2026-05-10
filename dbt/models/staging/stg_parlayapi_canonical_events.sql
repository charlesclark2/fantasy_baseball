{{
    config(
        materialized='table'
    )
}}

-- Grain: one row per (ingestion_ts, canonical_event_id).
-- Source: mlb_canonical_events_raw — one row per ingestion run; raw_json is the
-- full response array from /v1/sports/baseball_mlb/events/canonical.
--
-- Key purpose: expose real per-game scheduled start times (commence_time) for
-- use in leakage guards. The /events and /odds endpoints return 19:00:00Z as a
-- placeholder for all games; this endpoint returns the actual scheduled time.
--
-- API response shape (confirmed 2026-05-10):
--   canonical_event_id, commence_time, game_date, home_team, away_team,
--   sport_key, source_count, sources{} (per-book raw team names).
--   Note: no `id` field — canonical_event_id is the only event identifier here.
--   Join to stg_parlayapi_odds on canonical_event_id to get Parlay event_id.
--
-- Design notes:
--   • commence_time is an empty string "" for games without a confirmed start
--     time (e.g., multi-day scheduling placeholders). NULLIF converts to null.
--   • game_date comes directly from the response as a YYYY-MM-DD string;
--     prefer it over casting commence_time (which may be null/empty).
--   • source_count: number of bookmaker sources tracking this event.

with source as (

    select
        ingestion_ts,
        load_id,
        raw_json
    from {{ source('parlayapi', 'mlb_canonical_events_raw') }}
    where raw_json is not null

),

events_flattened as (

    select
        src.ingestion_ts,
        src.load_id,
        evt.value:canonical_event_id::varchar               as canonical_event_id,
        evt.value:sport_key::varchar                        as sport_key,
        evt.value:home_team::varchar                        as home_team,
        evt.value:away_team::varchar                        as away_team,
        -- Real scheduled start time. Empty string → null via NULLIF.
        nullif(evt.value:commence_time::varchar, '')::timestamp_ntz  as commence_time,
        -- game_date from the response (reliable even when commence_time is null)
        try_to_date(evt.value:game_date::varchar)           as game_date,
        -- Number of bookmaker sources tracking this event
        evt.value:source_count::integer                     as source_count
    from source src,
    lateral flatten(input => src.raw_json) evt
    where evt.value:canonical_event_id::varchar is not null

)

select

    -- ── Ingestion metadata ────────────────────────────────────────────────────
    ingestion_ts,
    load_id,

    -- ── Event identifier (canonical only — no Parlay event_id here) ──────────
    canonical_event_id,

    -- ── Teams ─────────────────────────────────────────────────────────────────
    home_team,
    away_team,
    sport_key,

    -- ── Real scheduled start time (key output) ────────────────────────────────
    commence_time,
    game_date,

    -- ── Coverage metadata ─────────────────────────────────────────────────────
    source_count

from events_flattened
