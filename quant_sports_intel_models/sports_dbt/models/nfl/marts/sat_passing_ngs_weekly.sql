-- sat_passing_ngs_weekly — QB NGS satellite on the fct spine (N0.3 port of jaffle
-- `sat_passing_ngs_weekly`). Left-joins Next Gen passing metrics onto every fct player-week row
-- (QBs, 2016+). ⭐ sport-tagged.
with base as (
    select * from {{ ref('stg_nfl_passing_ngs_weekly') }}
),
fct_player_week as (
    select * from {{ ref('fct_player_week') }}
),
joined as (
    select
        'nfl' as sport,
        b.season, b.week, b.player_id, b.pfr_id, b.gsis_it_id, b.player_name, b.team_id,
        b.position, b.status, b.depth_chart_position_rank, b.is_bye, b.week_start_et, b.week_end_et,
        f.avg_time_to_throw,
        f.avg_completed_air_yards,
        f.avg_intended_air_yards,
        f.avg_air_yards_differential,
        f.aggressiveness,
        f.max_completed_air_distance,
        f.avg_air_yards_to_sticks,
        f.attempts,
        f.completions,
        f.passing_yards,
        f.passing_touchdowns,
        f.interceptions,
        f.passer_rating,
        f.completion_percentage,
        f.expected_completion_percentage,
        f.completion_percentage_above_expectation
    from fct_player_week b
    left join base f
        on b.player_id = f.player_id and b.season = f.season and b.week = f.week
    where b.season is not null
      and b.week is not null
      and b.player_id is not null
      and b.season >= 2016
      and b.position = 'QB'
)
select *
from joined
