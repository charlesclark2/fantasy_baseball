{{
    config(
        materialized='table'
    )
}}

-- Grain: one row per (ingestion_ts, event_id, bookmaker_key, market_key, player, snapshot_ts).
-- Two lateral flattens:
--   1. raw_json array  → one record per (source × market_key × player)
--   2. record.snapshots[] → one row per timestamped price point
--
-- Schema note: the line-movement endpoint uses "source" (e.g. "fanduel") as the
-- bookmaker key — this is the non-suffixed live key, matching stg_parlayapi_odds.bookmaker_key
-- for live data. Historical (_an suffix) books are not present — this endpoint is live-only.
--
-- VARIANT null guard: Snowflake passes JSON null through IS NOT NULL when reading VARIANT;
-- cast to integer produces SQL NULL. Filter on the cast value, not the VARIANT value.

with source as (

    select
        ingestion_ts,
        load_id,
        raw_json,
        event_id,
        home_team,
        away_team
    from {{ source('parlayapi', 'mlb_line_movement_raw') }}
    where raw_json is not null
      and event_id is not null

),

records_flattened as (

    select
        src.ingestion_ts,
        src.load_id,
        src.event_id,
        src.home_team,
        src.away_team,
        rec.value:source::varchar           as bookmaker_key,
        rec.value:player::varchar           as player,
        rec.value:market_key::varchar       as market_key,
        rec.value:line::float               as current_line,
        rec.value:count::integer            as snapshot_count,
        rec.value:hours_tracked::float      as hours_tracked,
        rec.value:opening_over::integer     as opening_over_price,
        rec.value:current_over::integer     as current_over_price,
        rec.value:over_movement::integer    as over_movement,
        rec.value:opening_under::integer    as opening_under_price,
        rec.value:current_under::integer    as current_under_price,
        rec.value:snapshots                 as snapshots_raw
    from source src,
    lateral flatten(input => src.raw_json) rec
    where rec.value:source::varchar is not null
      and rec.value:market_key::varchar is not null

),

snapshots_flattened as (

    select
        rf.ingestion_ts,
        rf.load_id,
        rf.event_id,
        rf.home_team,
        rf.away_team,
        rf.bookmaker_key,
        rf.player,
        rf.market_key,
        rf.current_line,
        rf.snapshot_count,
        rf.hours_tracked,
        rf.opening_over_price,
        rf.current_over_price,
        rf.over_movement,
        rf.opening_under_price,
        rf.current_under_price,
        snap.value:time::timestamp_ntz      as snapshot_ts,
        snap.value:timestamp_ms::number     as snapshot_ts_ms,
        snap.value:over_price::integer      as snapshot_over_price,
        snap.value:under_price::integer     as snapshot_under_price,
        snap.value:line::float              as snapshot_line
    from records_flattened rf,
    lateral flatten(input => rf.snapshots_raw) snap
    where snap.value:over_price::integer is not null

)

select

    -- ── Ingestion metadata ────────────────────────────────────────────────────
    ingestion_ts,
    load_id,

    -- ── Event ─────────────────────────────────────────────────────────────────
    event_id,
    home_team,
    away_team,

    -- ── Record-level: one (bookmaker × market × player) series ───────────────
    bookmaker_key,
    player,                                                     -- null for team markets (h2h, totals)
    market_key,
    current_line,                                               -- total/prop line; null for moneyline
    snapshot_count,                                             -- number of snapshots Parlay has tracked
    hours_tracked,                                              -- hours this market has been tracked

    -- Opening and current prices (American odds) at the record level
    opening_over_price,
    opening_under_price,
    current_over_price,
    current_under_price,
    over_movement,                                              -- current_over - opening_over

    -- ── Snapshot-level: one timestamped price point ───────────────────────────
    snapshot_ts,                                                -- authoritative timestamp; use for leakage guards
    snapshot_ts_ms,                                             -- millisecond epoch (raw from API)
    snapshot_over_price,
    snapshot_under_price,
    snapshot_line,                                              -- line value at this snapshot (for props/totals)

    -- ── Decimal conversions (snapshot prices) ────────────────────────────────
    case
        when snapshot_over_price >= 100
            then (snapshot_over_price / 100.0) + 1.0
        when snapshot_over_price = 0
            then null
        else (100.0 / abs(snapshot_over_price)) + 1.0
    end::float                                                  as snapshot_over_price_decimal,

    case
        when snapshot_under_price >= 100
            then (snapshot_under_price / 100.0) + 1.0
        when snapshot_under_price = 0
            then null
        else (100.0 / abs(snapshot_under_price)) + 1.0
    end::float                                                  as snapshot_under_price_decimal,

    -- ── Market type flags ─────────────────────────────────────────────────────
    (player is not null)::boolean                               as is_player_prop,
    (market_key = 'moneyline')::boolean                         as is_h2h_market,
    (market_key = 'totals')::boolean                            as is_totals_market

from snapshots_flattened
