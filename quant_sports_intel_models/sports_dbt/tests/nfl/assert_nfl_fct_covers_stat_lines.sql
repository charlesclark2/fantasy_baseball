-- COVERAGE GUARD (2026-07-24): every player with a box-score line in a season MUST appear in
-- fct_player_week that season. This catches the "missing rookie class" corruption — when the fact
-- was anchored on the depth-chart-derived role dimension and `depth_charts` lagged a season, the
-- entire rookie class (present in the box score) was silently dropped. Fails (rows > 0) if any
-- season has stat-line players absent from the fact.
with stat_players as (
    select distinct season, player_id from {{ ref('stg_nfl_weekly_data') }}
),
fct_players as (
    select distinct season, player_id from {{ ref('fct_player_week') }}
)
select s.season, count(*) as stat_players_missing_from_fct
from stat_players s
left join fct_players f on f.season = s.season and f.player_id = s.player_id
where f.player_id is null
group by 1
