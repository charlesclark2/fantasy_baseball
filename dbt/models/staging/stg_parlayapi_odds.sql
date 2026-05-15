{{
    config(
        materialized='table'
    )
}}

-- Grain: one row per (ingestion_ts, event_id, bookmaker_key, market_key, outcome_name).
-- Mirrors stg_oddsapi_odds output schema with three additions:
--   • source_system = 'parlay_api' discriminator column
--   • canonical_event_id (Parlay API cross-source stable event ID; null for historical rows)
--   • doubleheader_ambiguous flag (true when StatsAPI records a DH for this matchup/date)
--
-- Schema differences vs Odds API (documented for downstream model awareness):
--   • commence_time is a slate placeholder (19:00:00Z) for all games — not actual start time
--   • market_last_update is null for historical odds rows (field absent from historical endpoint)
--   • bookmaker_last_update is the placeholder timestamp in historical rows
--   • region_requested is always null — Parlay API has no region parameter
--   • x_requests_used/remaining are always null — Parlay API does not expose these headers
--   • bookmaker keys use _an suffix in historical data (draftkings_an, fanduel_an, etc.)
--     vs non-suffixed in live data (draftkings, fanduel) — same books, different key strings

with source as (

    select
        ingestion_ts,
        load_id,
        request_params,
        x_requests_used,
        x_requests_remaining,
        raw_json
    from {{ source('parlayapi', 'mlb_odds_raw') }}
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
        src.raw_json:canonical_event_id::varchar        as canonical_event_id,
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
        bf.canonical_event_id,
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
        mf.canonical_event_id,
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
        out.value:point::float                          as outcome_point
    from markets_flattened mf,
    lateral flatten(input => mf.market:outcomes) out
    -- Parlay API sends explicit JSON null for some away-side prices (e.g. Caesars).
    -- In Snowflake VARIANT, JSON null is a VARIANT null — not SQL NULL — so
    -- `IS NOT NULL` passes it through; the ::integer cast then produces SQL NULL.
    -- Filtering on the cast value catches both missing keys and explicit JSON nulls.
    where out.value:price::integer is not null

),

-- Canonical events carry the real scheduled start time (not the 19:00:00Z placeholder
-- used by the /odds endpoint). Join on canonical_event_id to get the ET-corrected
-- game_date for West Coast games that cross midnight UTC (Parlay API uses UTC dates,
-- Stats API uses local-time dates; they diverge by 1 day for late West Coast starts).
canonical_game_dates as (

    select distinct
        canonical_event_id,
        game_date as canonical_game_date
    from {{ ref('stg_parlayapi_canonical_events') }}
    where canonical_event_id is not null

),

doubleheader_dates as (

    -- Matchups where StatsAPI records a traditional (Y) or split (S) doubleheader.
    -- Used to flag Parlay API rows where the event may represent only one of two games.
    select distinct
        game_date::date     as game_date,
        home_team_name,
        away_team_name
    from {{ ref('stg_statsapi_games') }}
    where double_header in ('Y', 'S')

)

select
    -- Ingestion metadata
    o.ingestion_ts,
    o.load_id,
    o.request_params:markets::varchar                    as market_requested,
    null::varchar                                        as region_requested,
    o.x_requests_used,
    o.x_requests_remaining,

    -- Source discriminator
    'parlay_api'::varchar                                as source_system,

    -- Event identifiers
    o.event_id,
    o.canonical_event_id,
    o.sport_key,
    o.sport_title,
    o.commence_time,
    -- Use ET-corrected game_date from canonical events when available.
    -- The /odds endpoint uses 19:00:00Z as a placeholder, so its UTC date
    -- is correct for most games but wrong for West Coast games that cross
    -- midnight UTC. The canonical endpoint has the real start time; we
    -- converted it to ET in stg_parlayapi_canonical_events.
    coalesce(ce.canonical_game_date, o.commence_time::date) as game_date,
    o.home_team,
    o.away_team,

    -- True when StatsAPI shows a doubleheader for this (date, home, away) combination.
    -- The Parlay API collapses both DH games into a single event; this flag surfaces
    -- that ambiguity so downstream models can exclude or caveat affected rows until
    -- the API issue is resolved (support ticket open as of 2026-05-10).
    case
        when dh.home_team_name is not null then true
        else false
    end::boolean                                         as doubleheader_ambiguous,

    -- Bookmaker
    o.bookmaker_key,
    o.bookmaker_title,
    o.bookmaker_last_update,

    -- Market
    o.market_key,
    o.market_last_update,

    -- Outcome
    o.outcome_name,
    o.outcome_price_american,
    case
        when o.outcome_price_american >= 100
            then (o.outcome_price_american / 100.0) + 1.0
        when o.outcome_price_american = 0
            then null
        else (100.0 / abs(o.outcome_price_american)) + 1.0
    end::float                                           as outcome_price_decimal,
    o.outcome_point

from outcomes_flattened o
left join canonical_game_dates ce
    on  o.canonical_event_id  = ce.canonical_event_id
left join doubleheader_dates dh
    on  coalesce(ce.canonical_game_date, o.commence_time::date) = dh.game_date
    and o.home_team           = dh.home_team_name
    and o.away_team           = dh.away_team_name
