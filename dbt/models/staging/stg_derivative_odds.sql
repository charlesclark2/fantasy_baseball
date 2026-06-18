{{
    config(
        materialized='incremental',
        incremental_strategy='append',
        unique_key=None
    )
}}

-- Grain: one row per (actual_snapshot_ts, event_id, bookmaker_key, market_key, outcome_name).
-- Source: baseball_data.oddsapi.derivative_odds_raw, written by
--         scripts/derivative_odds_backfill.py (E2.0).
--
-- ⚠️  EVAL/CLV-ONLY — these are derivative-market closing lines (team totals,
--     alternate totals, first-5-innings). They exist solely for validation of
--     E2 derivative gates (E2.6) and CLV measurement. They must NEVER be joined
--     into model training feature matrices (market-blind constraint, §0.1 Principle 3).
--
-- Markets present:
--   team_totals      — individual team run total (Over/Under; point=line)
--   alternate_totals — alternate full-game total lines
--   h2h_h1           — first-half (F5 innings 1–5) moneyline
--   totals_h1        — first-half (F5) run total Over/Under
--
-- Three-level lateral flatten: bookmakers[] → markets[] → outcomes[]

with source as (

    select
        ingestion_ts,
        load_id,
        event_id,
        requested_snapshot_ts,
        actual_snapshot_ts,
        previous_snapshot_ts,
        next_snapshot_ts,
        markets_requested,
        regions_requested,
        x_requests_remaining,
        x_requests_last,
        raw_json
    from {{ source('oddsapi', 'derivative_odds_raw') }}
    where raw_json is not null
      and raw_json:id is not null
      and raw_json:bookmakers is not null
    {% if is_incremental() %}
    and actual_snapshot_ts > (select coalesce(max(actual_snapshot_ts), '2023-05-03'::timestamp_ntz) from {{ this }})
    {% endif %}

),

bookmakers_flattened as (

    select
        src.ingestion_ts,
        src.load_id,
        src.event_id,
        src.requested_snapshot_ts,
        src.actual_snapshot_ts,
        src.previous_snapshot_ts,
        src.next_snapshot_ts,
        src.markets_requested,
        src.regions_requested,
        src.x_requests_remaining,
        src.x_requests_last,
        src.raw_json:id::varchar                        as event_id_json,
        src.raw_json:sport_key::varchar                 as sport_key,
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
        bf.event_id,
        bf.requested_snapshot_ts,
        bf.actual_snapshot_ts,
        bf.previous_snapshot_ts,
        bf.next_snapshot_ts,
        bf.markets_requested,
        bf.regions_requested,
        bf.x_requests_remaining,
        bf.x_requests_last,
        bf.sport_key,
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
        mf.event_id,
        mf.requested_snapshot_ts,
        mf.actual_snapshot_ts,
        mf.previous_snapshot_ts,
        mf.next_snapshot_ts,
        mf.markets_requested,
        mf.regions_requested,
        mf.x_requests_remaining,
        mf.x_requests_last,
        mf.sport_key,
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
        -- description carries the team name for team_totals outcomes
        out.value:description::varchar                  as outcome_description
    from markets_flattened mf,
    lateral flatten(input => mf.market:outcomes) out
    where out.value:price::integer is not null

)

select
    -- Ingestion metadata
    ingestion_ts,
    load_id,
    requested_snapshot_ts,
    actual_snapshot_ts,
    previous_snapshot_ts,
    next_snapshot_ts,
    markets_requested,
    regions_requested,
    x_requests_remaining,
    x_requests_last,

    -- Event identifiers
    event_id,
    sport_key,
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
    outcome_description,
    outcome_price_american,
    case
        when outcome_price_american >= 100
            then (outcome_price_american / 100.0) + 1.0
        when outcome_price_american = 0
            then null
        else (100.0 / abs(outcome_price_american)) + 1.0
    end::float                                          as outcome_price_decimal,
    outcome_point

from outcomes_flattened
