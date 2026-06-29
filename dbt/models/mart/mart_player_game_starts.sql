-- =============================================================================
-- mart_player_game_starts.sql   (Story 33.1 Task 1a)
-- Grain: one row per (game_pk, team, side, player_id) — a CONFIRMED STARTER.
-- Purpose: the leakage-safe START FACT for the playing-time probability model
--          (33.1) and the expected-lineup feature family (33.3). The team-game
--          spine (mart_game_spine, unpivoted home/away) joined to the posted
--          lineups (stg_statsapi_lineups, one row = one starter). Coverage: 2015+.
--
-- DuckDB branch (E11.1-W6): reads the migrated mart_game_spine (W5) +
-- stg_statsapi_lineups (W6). Snowflake (else) branch is a thin view over the
-- lakehouse_ext external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

with spine as (

    select
        game_pk,
        game_date::date as game_date,
        game_year,
        home_team,
        away_team
    from mart_game_spine

),

team_games as (

    select game_pk, game_date, game_year, home_team as team, away_team as opp_team, 'home' as side from spine
    union all
    select game_pk, game_date, game_year, away_team as team, home_team as opp_team, 'away' as side from spine

),

starters as (

    select
        game_pk,
        home_away      as side,
        official_date,
        player_id,
        full_name,
        batting_order,
        position_code
    from stg_statsapi_lineups

)

select
    tg.game_pk,
    s.official_date,
    tg.game_year,
    tg.team,
    tg.opp_team,
    tg.side,
    s.player_id,
    s.full_name,
    s.batting_order,
    s.position_code,
    (s.position_code = '1')::boolean as is_pitcher_slot
from team_games tg
join starters s
    on s.game_pk = tg.game_pk
   and s.side    = tg.side

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.mart_player_game_starts

{% endif %}
