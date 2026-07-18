-- stg_nfl_depth_charts — weekly depth chart (N0.3 port of jaffle `stg_depth_charts`).
--
-- Feeds dim_player_role (position rank + the SCD-2 change signal). Lake asset: `depth_charts`.
-- ⚠️ `depth_team` is VARCHAR in the lake (dirty/format-shifting across the 1999–2025 span);
-- newer seasons populate the typed `pos_rank` instead → the rank is `try_cast(depth_team)`
-- coalesced to `pos_rank` (the INC-23 use-site-cast discipline). `club_code` is coalesced to
-- `team` so the format-shift rows are not dropped. Offensive skill positions only (the fantasy
-- universe). ⭐ sport-tagged.
with base as (
    select *
    from {{ nfl_delta('depth_charts') }}
),
transformed as (
    select
        'nfl'                                         as sport,
        trim(gsis_id)                                 as player_id,
        season,
        week,
        case when full_name is null then trim(concat(first_name, ' ', last_name)) else trim(full_name) end as player_name,
        case
            when coalesce(club_code, team) in ('SD', 'LAC')  then 'LAC'
            when coalesce(club_code, team) in ('STL', 'LA')  then 'LAR'
            when coalesce(club_code, team) in ('OAK', 'LV')  then 'LV'
            else coalesce(club_code, team)
        end                                           as player_team,
        position,
        coalesce(try_cast(depth_team as integer), pos_rank) as depth_chart_position_rank,
        case
            when position in ('QB', 'WR', 'RB', 'TE', 'FB') and formation ilike 'offense' then 1
            when position ilike 'k' then 1
            else 0
        end                                           as is_offensive_player
    from base
    where game_type ilike 'reg'
      and coalesce(club_code, team) is not null
      and position in ('QB', 'WR', 'K', 'RB', 'TE', 'FB')
)
select * exclude(is_offensive_player)
from transformed
where is_offensive_player = 1
