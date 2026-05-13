-- =============================================================================
-- stg_statsapi_probable_pitchers.sql
-- Grain: one row per game_pk per side (home / away)
-- Purpose: Extract probablePitcher from the Stats API monthly schedule JSON.
--          Populated 1–3 days before game time once the rotation is announced.
--          probable_pitcher_id is null when the field is absent (rotation not
--          yet set or game too far in the future). No rows are dropped.
--          Join to stg_statsapi_games on game_pk for full game context.
-- =============================================================================

{{
    config(
        materialized = 'table'
    )
}}

with source as (

    select json_field, ingestion_ts
    from {{ source('statsapi', 'monthly_schedule') }}

),

dates_flattened as (

    select d.value as date_obj, ingestion_ts
    from source,
    lateral flatten(input => json_field:dates) d

),

games_flattened as (

    select g.value as game, ingestion_ts
    from dates_flattened,
    lateral flatten(input => date_obj:games) g

),

home_side as (

    select
        game:gamePk::integer                                        as game_pk,
        game:officialDate::date                                     as game_date,
        'home'                                                      as side,
        game:teams:home:probablePitcher:id::integer                 as probable_pitcher_id,
        game:teams:home:probablePitcher:fullName::varchar           as probable_pitcher_name,
        ingestion_ts
    from games_flattened

),

away_side as (

    select
        game:gamePk::integer                                        as game_pk,
        game:officialDate::date                                     as game_date,
        'away'                                                      as side,
        game:teams:away:probablePitcher:id::integer                 as probable_pitcher_id,
        game:teams:away:probablePitcher:fullName::varchar           as probable_pitcher_name,
        ingestion_ts
    from games_flattened

),

all_sides as (

    select * from home_side
    union all
    select * from away_side

)

select *
from all_sides
qualify row_number() over (
    partition by game_pk, side
    order by ingestion_ts desc nulls last
) = 1
