{{
    config(
        materialized='table'
    )
}}

with sources as (
    select fg_pitcher_id as fg_player_id, pitcher_name as player_name, mlbam_pitcher_id as mlbam_id, 'pitcher' as player_role
    from {{ ref('stg_fangraphs__zips_pitching') }}
    where fg_pitcher_id is not null and fg_pitcher_id != ''

    union all

    select fg_pitcher_id, pitcher_name, mlbam_pitcher_id, 'pitcher'
    from {{ ref('stg_fangraphs__stuff_plus') }}
    where fg_pitcher_id is not null and fg_pitcher_id != ''

    union all

    select fg_batter_id, batter_name, mlbam_batter_id, 'batter'
    from {{ ref('stg_fangraphs__zips_hitting') }}
    where fg_batter_id is not null and fg_batter_id != ''

    union all

    select fg_batter_id, batter_name, mlbam_batter_id, 'batter'
    from {{ ref('stg_fangraphs__hitting_leaderboard') }}
    where fg_batter_id is not null and fg_batter_id != ''
)

select
    fg_player_id,
    max(player_name)                                                                   as player_name,
    max(mlbam_id)                                                                      as mlbam_id,
    -- Numeric-only IDs are MLB FanGraphs player IDs
    case when regexp_like(fg_player_id, '^[0-9]+$') then fg_player_id end             as fg_mlb_id,
    -- 'sa'-prefixed IDs are FanGraphs minor league player IDs
    case when startswith(fg_player_id, 'sa')         then fg_player_id end             as fg_milb_id,
    startswith(fg_player_id, 'sa')                                                     as is_milb_player,
    boolor_agg(player_role = 'pitcher')                                                as is_pitcher,
    boolor_agg(player_role = 'batter')                                                 as is_batter
from sources
group by fg_player_id
