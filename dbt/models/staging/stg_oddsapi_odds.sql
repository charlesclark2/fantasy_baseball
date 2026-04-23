{{
    config(
        materialized='table'
    )
}}

-- Grain: one row per (ingestion_ts, event_id, bookmaker_key, market_key,
--        outcome_name). Each ingestion run is a distinct odds snapshot in time.
-- Historical snapshots are preserved so downstream models can track odds
-- movement. Within a single load_id, rows are deduplicated across
-- market/region calls to prevent the same bookmaker appearing twice when it
-- is included in both the us and us2 region responses.
--
-- Three levels of lateral flatten:
--   1. bookmakers[]  → one row per bookmaker per event
--   2. markets[]     → one row per market per bookmaker per event
--   3. outcomes[]    → one row per outcome per market per bookmaker per event

with source as (

    select
        ingestion_ts,
        load_id,
        request_params,
        x_requests_used,
        x_requests_remaining,
        raw_json
    from {{ source('oddsapi', 'mlb_odds_raw') }}
    where raw_json is not null
      and raw_json:id is not null
      and raw_json:bookmakers is not null

),

bookmakers_flattened as (

    select
        src.ingestion_ts,
        src.load_id,
        src.request_params,
        src.x_requests_used,
        src.x_requests_remaining,
        src.raw_json:id::varchar                        as event_id,
        src.raw_json:sport_key::varchar                 as sport_key,
        src.raw_json:sport_title::varchar               as sport_title,
        src.raw_json:commence_time::timestamp_ntz       as commence_time,
        src.raw_json:home_team::varchar                 as home_team,
        src.raw_json:away_team::varchar                 as away_team,
        bkm.value                                       as bookmaker
    from source src,
    lateral flatten(input => src.raw_json:bookmakers) bkm

),

markets_flattened as (

    select
        bf.ingestion_ts,
        bf.load_id,
        bf.request_params,
        bf.x_requests_used,
        bf.x_requests_remaining,
        bf.event_id,
        bf.sport_key,
        bf.sport_title,
        bf.commence_time,
        bf.home_team,
        bf.away_team,
        bf.bookmaker:key::varchar                       as bookmaker_key,
        bf.bookmaker:title::varchar                     as bookmaker_title,
        bf.bookmaker:last_update::timestamp_ntz         as bookmaker_last_update,
        mkt.value                                       as market
    from bookmakers_flattened bf,
    lateral flatten(input => bf.bookmaker:markets) mkt

),

outcomes_flattened as (

    select
        mf.ingestion_ts,
        mf.load_id,
        mf.request_params,
        mf.x_requests_used,
        mf.x_requests_remaining,
        mf.event_id,
        mf.sport_key,
        mf.sport_title,
        mf.commence_time,
        mf.home_team,
        mf.away_team,
        mf.bookmaker_key,
        mf.bookmaker_title,
        mf.bookmaker_last_update,
        mf.market:key::varchar                          as market_key,
        mf.market:last_update::timestamp_ntz            as market_last_update,
        out.value:name::varchar                         as outcome_name,
        out.value:price::integer                        as outcome_price_american,
        out.value:point::float                          as outcome_point,
        -- Deduplicate within a load_id: if the same bookmaker × market ×
        -- outcome appeared in both the us and us2 region responses for this
        -- run, keep only one row (the first encountered by index order).
        row_number() over (
            partition by
                mf.load_id,
                mf.event_id,
                mf.bookmaker_key,
                mf.market:key::varchar,
                out.value:name::varchar
            order by mf.ingestion_ts
        ) as _rn
    from markets_flattened mf,
    lateral flatten(input => mf.market:outcomes) out

)

select
    -- Ingestion metadata
    ingestion_ts,
    load_id,
    request_params:markets::varchar                     as market_requested,
    request_params:regions::varchar                     as region_requested,
    x_requests_used,
    x_requests_remaining,

    -- Event identifiers
    event_id,
    sport_key,
    sport_title,
    commence_time,
    home_team,
    away_team,

    -- Bookmaker
    bookmaker_key,
    bookmaker_title,
    bookmaker_last_update,

    -- Market
    market_key,
    market_last_update,

    -- Outcome
    outcome_name,
    outcome_price_american,
    outcome_point          -- non-null for totals (Over/Under line); null for h2h

from outcomes_flattened
where _rn = 1
