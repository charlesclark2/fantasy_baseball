-- =============================================================================
-- mart_park_run_factors.sql
-- Grain: one row per venue_id per game_year (regular season, >= 10 games played)
-- Purpose: Empirical run environment per ballpark. Captures how many total runs
--          per game are scored at each park in a given season, plus a 3-year
--          rolling average as a stable park run factor for ML features.
--          Physical park characteristics (dimensions, elevation) are in
--          stg_statsapi_venues; this model captures the observed run signal.
-- =============================================================================

{{
    config(
        materialized = 'table'
    )
}}

with game_results as (

    select
        venue_id,
        venue_name,
        game_year,
        home_final_score + away_final_score as total_runs
    from {{ ref('mart_game_results') }}
    where game_type = 'R'
      and venue_id is not null

),

season_totals as (

    select
        venue_id,
        venue_name,
        game_year,
        count(*)        as game_count,
        avg(total_runs) as runs_per_game_at_park
    from game_results
    group by venue_id, venue_name, game_year

),

with_rolling as (

    select
        venue_id,
        venue_name,
        game_year,
        game_count,
        runs_per_game_at_park,
        avg(runs_per_game_at_park) over (
            partition by venue_id
            order by game_year
            rows between 2 preceding and current row
        ) as park_run_factor_3yr
    from season_totals

)

select *
from with_rolling
where game_count >= 10
