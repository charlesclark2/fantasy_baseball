-- sat_rushing_ngs_weekly — RB NGS satellite on the fct spine (N0.3 port of jaffle
-- `sat_rushing_ngs_weekly`). Left-joins Next Gen rushing metrics onto every fct player-week row
-- (non-K, 2016+). ⭐ sport-tagged.
with base as (
    select * from {{ ref('stg_nfl_rushing_ngs_weekly') }}
),
fct_player_week as (
    select * from {{ ref('fct_player_week') }}
),
joined as (
    select
        'nfl' as sport,
        f.season, f.week, f.player_id, f.pfr_id, f.gsis_it_id, f.player_name, f.team_id,
        f.position, f.status, f.depth_chart_position_rank, f.is_bye, f.week_start_et, f.week_end_et,
        b.efficiency,
        b.percent_attempts_gte_eight_defenders,
        b.avg_time_to_line_of_scrimmage,
        b.rush_attempts,
        b.rushing_yards,
        b.avg_rushing_yards,
        b.rushing_touchdowns,
        b.expected_rushing_yards,
        b.rushing_yards_over_expected,
        b.rushing_yards_over_expected_per_attempt,
        b.rush_percentage_over_expected
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
