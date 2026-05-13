{{
    config(
        materialized='table'
    )
}}

with source as (
    select json_field, ingestion_ts
    from {{ source('statsapi', 'monthly_schedule') }}
),

dates_flattened as (
    select
        d.value as date_obj,
        ingestion_ts
    from source,
    lateral flatten(input => json_field:dates) d
),

games_flattened as (
    select
        g.value as game,
        ingestion_ts
    from dates_flattened,
    lateral flatten(input => date_obj:games) g
),

home_players as (
    select
        game:gamePk::integer                    as game_pk,
        game:officialDate::date                 as official_date,
        'home'                                  as home_away,
        p.index + 1                             as batting_order,
        p.value                                 as player,
        ingestion_ts
    from games_flattened,
    lateral flatten(input => game:lineups:homePlayers) p
),

away_players as (
    select
        game:gamePk::integer                    as game_pk,
        game:officialDate::date                 as official_date,
        'away'                                  as home_away,
        p.index + 1                             as batting_order,
        p.value                                 as player,
        ingestion_ts
    from games_flattened,
    lateral flatten(input => game:lineups:awayPlayers) p
),

all_players as (
    select * from home_players
    union all
    select * from away_players
)

select
    game_pk,
    official_date,
    home_away,
    batting_order,

    player:id::integer                          as player_id,
    player:fullName::varchar                    as full_name,
    player:firstName::varchar                   as first_name,
    player:lastName::varchar                    as last_name,
    player:useName::varchar                     as use_name,

    player:primaryPosition:code::varchar        as position_code,
    player:primaryPosition:name::varchar        as position_name,
    player:primaryPosition:type::varchar        as position_type,
    player:primaryPosition:abbreviation::varchar as position_abbreviation,

    ingestion_ts

from all_players
qualify row_number() over (
    partition by game_pk, home_away, batting_order
    order by ingestion_ts desc nulls last
) = 1
