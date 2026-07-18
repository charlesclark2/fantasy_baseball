-- mart_efficiency_player_week — per-play efficiency per player-week (N0.3 port of jaffle
-- `mart_efficiency_player_week`). The efficiency side: completion%/YPA/TD-rate/CPOE/sack-rate
-- (QB), YPC/EPA-per-rush/RYOE (RB), catch-rate/YPT/YAC-OE (WR/TE). Joins fct + PFR advanced +
-- NGS satellites. Snowflake `iff` → DuckDB `case when`; PFR staging repointed to stg_nfl_*.
-- ⭐ sport-tagged. Excludes kickers.
with fct_player_week as (
    select *
    from {{ ref('fct_player_week') }}
    qualify row_number() over (partition by player_id, season, week, team_id order by week_start_et desc) = 1
),
pass_pfr as (
    select * from {{ ref('stg_nfl_passing_pfr') }}
),
receiving_pfr as (
    select * from {{ ref('stg_nfl_receiving_pfr') }}
),
rushing_pfr as (
    select * from {{ ref('stg_nfl_rushing_pfr') }}
),
passing_ngs as (
    select * from {{ ref('sat_passing_ngs_weekly') }}
),
receiving_ngs as (
    select * from {{ ref('sat_receiving_ngs_weekly') }}
),
rushing_ngs as (
    select * from {{ ref('sat_rushing_ngs_weekly') }}
),
base as (
    select
        'nfl' as sport,
        f.season,
        f.week,
        f.player_name,
        f.player_id,
        f.team_id,
        f.opponent_id,
        f.is_bye,
        f.week_start_et,
        f.week_end_et,
        f.position,
        f.status,
        f.depth_chart_position_rank,
        -- QB specifics
        f.pass_attempts,
        f.pass_completions,
        f.passing_yards,
        f.passing_touchdowns,
        case when f.pass_attempts > 0 then round(f.pass_completions / f.pass_attempts, 4) else 0.0 end as completion_pct,
        case when f.pass_attempts > 0 and f.passing_yards > 0 then round(f.passing_yards / f.pass_attempts, 4) else 0.0 end as yards_per_pass_attempt,
        case when f.pass_attempts > 0 then round(f.passing_touchdowns / f.pass_attempts, 4) else 0.0 end as passing_td_rate,
        case when f.pass_attempts > 0 then round(f.passing_expected_points_added / f.pass_attempts, 4) else 0.0 end as expected_points_per_dropback,
        f.qb_efficiency_index,
        coalesce(pn.completion_percentage_above_expectation, 0.0) as completion_percentage_above_expectation,
        coalesce(pn.avg_completed_air_yards, 0.0) as avg_completed_air_yards,
        coalesce(pn.avg_intended_air_yards, 0.0) as avg_intended_air_yards,
        coalesce(pn.avg_air_yards_differential, 0.0) as avg_air_yards_differential,
        coalesce(pn.avg_time_to_throw, 0.0) as avg_time_to_throw,
        coalesce(pn.aggressiveness, 0.0) as qb_aggressiveness,
        coalesce(pp.passing_bad_throws_pct, 0.0) as passing_bad_throw_pct,
        coalesce(pp.times_pressured_pct, 0.0) as times_pressured_pct,
        f.sacks_taken::int + f.pass_attempts::int + f.rushing_carries::int as qb_dropbacks,
        case when qb_dropbacks > 0 then round(f.sacks_taken / qb_dropbacks::float, 4) else 0.0 end as sack_rate,
        -- rushing data
        f.rushing_carries,
        f.rushing_yards,
        f.rushing_touchdowns,
        case when f.rushing_carries > 0 then round(f.rushing_yards / f.rushing_carries, 4) else 0.0 end as yards_per_carry,
        case when f.rushing_carries > 0 then round(f.rushing_touchdowns / f.rushing_carries, 4) else 0.0 end as rush_touchdown_rate,
        case when f.rushing_carries > 0 then round(f.rushing_expected_points_added / f.rushing_carries, 4) else 0.0 end as expected_points_added_per_rush,
        case when f.rushing_carries > 0 then round(f.rushing_first_downs / f.rushing_carries, 4) else 0.0 end as rush_success_rate,
        coalesce(rngs.rushing_yards_over_expected_per_attempt, 0.0) as rushing_yards_over_expected_per_attempt,
        coalesce(rngs.rush_percentage_over_expected, 0.0) as rush_percentage_over_expected,
        coalesce(rngs.avg_time_to_line_of_scrimmage, 0.0) as avg_time_to_line_of_scrimmage,
        coalesce(rngs.efficiency, 0.0) as rush_efficiency,
        coalesce(rngs.percent_attempts_gte_eight_defenders, 0.0) as rush_box_rate,
        case when f.rushing_carries > 0 then round(rushp.rushing_broken_tackles / f.rushing_carries, 4) else 0.0 end as rushing_broken_tackle_rate,
        -- receiving stats
        f.receiving_targets,
        f.receptions,
        f.receiving_yards,
        f.receiving_touchdowns,
        case when f.receiving_targets > 0 then round(f.receptions / f.receiving_targets, 4) else 0.0 end as rec_catch_rate,
        case when f.receiving_targets > 0 then round(f.receiving_yards / f.receiving_targets, 4) else 0.0 end as yards_per_target,
        case when f.receiving_targets > 0 then round(f.receiving_touchdowns / f.receiving_targets, 4) else 0.0 end as reception_touchdown_rate,
        case when f.receiving_targets > 0 then round(f.receiving_first_downs / f.receiving_targets, 4) else 0.0 end as receiving_first_down_rate,
        case when f.receiving_targets > 0 then round(f.receiving_expected_points_added / f.receiving_targets, 4) else 0.0 end as rec_expected_points_added_per_target,
        f.receiving_air_conversion_ratio,
        coalesce(rn.avg_separation, 0.0) as avg_separation,
        coalesce(rn.avg_cushion, 0.0) as avg_cushion,
        coalesce(rn.avg_yards_after_catch, 0.0) as avg_yards_after_catch,
        coalesce(rn.avg_expected_yards_after_catch, 0.0) as avg_expected_yards_after_catch,
        coalesce(rn.avg_yards_after_catch_above_expectation, 0.0) as avg_yards_after_catch_above_expectation,
        coalesce(rn.avg_intended_air_yards, 0.0) as avg_intended_yards,
        coalesce(rp.receiving_drop_pct, 0.0) as receiving_drop_pct,
        case when f.receptions > 0 then round(rp.receiving_broken_tackles / f.receptions, 4) else 0.0 end as receiving_broken_tackle_rate,
        -- snaps
        f.offense_snaps,
        f.offense_pct,
        f.weighted_opportunity_rating,
        -- starter flags
        case
            when f.depth_chart_position_rank = 1 or f.offense_pct > 0.5 then 1
            when (f.depth_chart_position_rank in (1, 2) and f.position != 'QB') or f.offense_pct > 0.5 then 1
            else 0
        end as is_starter,
        case when f.position = 'WR' and f.depth_chart_position_rank = 1 then 1 else 0 end as is_wr1,
        case when f.position = 'TE' and f.depth_chart_position_rank = 1 then 1 else 0 end as is_te1,
        case when f.position in ('FB', 'RB') and f.offense_pct > 0.6 then 1 else 0 end as is_feature_back
    from fct_player_week f
    left join pass_pfr pp
        on f.pfr_id = pp.player_id and f.season = pp.season and f.week = pp.week
    left join receiving_pfr rp
        on f.pfr_id = rp.player_id and f.season = rp.season and f.week = rp.week
    left join rushing_pfr rushp
        on f.pfr_id = rushp.player_id and f.season = rushp.season and f.week = rushp.week
    left join passing_ngs pn
        on f.player_id = pn.player_id and f.season = pn.season and f.week = pn.week
    left join receiving_ngs rn
        on f.player_id = rn.player_id and f.season = rn.season and f.week = rn.week
    left join rushing_ngs rngs
        on f.player_id = rngs.player_id and f.season = rngs.season and f.week = rngs.week
    where f.position != 'K'
)
select *
from base
