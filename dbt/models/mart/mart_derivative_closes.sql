-- =============================================================================
-- mart_derivative_closes.sql
-- Grain: one row per (game_pk, market_key, bookmaker_key, outcome_name)
-- Purpose: Closing derivative-market odds (team totals, alternate totals, F5
--          totals / moneyline). "Closing" = last pre-game snapshot in
--          stg_derivative_odds (actual_snapshot_ts <= commence_time).
--
-- ⚠️  EVAL/CLV-ONLY — never joined into training feature matrices.
-- Source: stg_derivative_odds.  Join: event_id → mart_game_odds_bridge → game_pk.
--
-- DuckDB branch (E11.1-W6): reads the migrated stg_derivative_odds (W3pre) +
-- mart_game_odds_bridge (W6). Snowflake (else) branch is a thin view over the
-- lakehouse_ext external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

with derivative_odds as (

    select
        event_id,
        commence_time,
        home_team,
        away_team,
        actual_snapshot_ts,
        bookmaker_key,
        bookmaker_title,
        market_key,
        outcome_name,
        outcome_description,
        outcome_price_american,
        outcome_price_decimal,
        outcome_point,
        row_number() over (
            partition by event_id, market_key, bookmaker_key, outcome_name
            order by actual_snapshot_ts desc
        ) as snap_rank
    from stg_derivative_odds
    where actual_snapshot_ts <= commence_time

),

closing as (

    select *
    from derivative_odds
    where snap_rank = 1

),

game_bridge as (

    select
        game_pk,
        odds_api_event_id,
        parlay_api_event_id
    from mart_game_odds_bridge
    where game_pk is not null

)

select
    b.game_pk,
    c.event_id,
    c.commence_time,
    c.home_team,
    c.away_team,

    c.actual_snapshot_ts                    as close_snapshot_ts,

    c.bookmaker_key,
    c.bookmaker_title,

    c.market_key,

    c.outcome_name,
    c.outcome_description,
    c.outcome_price_american,
    c.outcome_price_decimal,
    c.outcome_point,

    case
        when c.market_key in ('team_totals', 'alternate_totals', 'totals_h1')
         and lower(c.outcome_name) = 'over'
            then true
        when c.market_key in ('team_totals', 'alternate_totals', 'totals_h1')
         and lower(c.outcome_name) = 'under'
            then false
        else null
    end::boolean                            as is_over,

    case
        when c.outcome_price_decimal is not null and c.outcome_price_decimal > 1.0
            then 1.0 / c.outcome_price_decimal
        else null
    end::double                              as raw_implied_prob

from closing c
inner join game_bridge b
    on (
        c.event_id = b.odds_api_event_id
        or c.event_id = b.parlay_api_event_id
    )

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.mart_derivative_closes

{% endif %}
