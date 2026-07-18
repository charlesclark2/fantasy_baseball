-- sat_receiving_ngs_weekly — WR/TE NGS satellite on the fct spine (N0.3 port of jaffle
-- `sat_receiving_ngs_weekly`). Left-joins Next Gen receiving metrics onto every fct player-week
-- row (non-K, 2016+). ⭐ sport-tagged.
with base as (
    select * from {{ ref('stg_nfl_receiving_ngs_weekly') }}
),
fct_player_week as (
    select * from {{ ref('fct_player_week') }}
),
joined as (
    select
        'nfl' as sport,
        f.season, f.week, f.player_id, f.pfr_id, f.gsis_it_id, f.player_name, f.team_id,
        f.position, f.status, f.depth_chart_position_rank, f.is_bye, f.week_start_et, f.week_end_et,
        b.avg_cushion,
        b.avg_separation,
        b.avg_intended_air_yards,
        b.percent_share_of_intended_air_yards,
        b.receptions,
        b.targets,
        b.receiving_yards,
        b.receiving_touchdowns,
        b.catch_percentage,
        b.avg_yards_after_catch,
        b.avg_expected_yards_after_catch,
        b.avg_yards_after_catch_above_expectation
    from fct_player_week f
    left join base b
        on f.player_id = b.player_id and f.season = b.season and f.week = b.week
    where f.season is not null
      and f.week is not null
      and f.player_id is not null
      and f.season >= 2016
      and f.position != 'K'
)
select *
from joined
