-- mart_opportunity_player_week — usage/volume driver per player-week (N0.3 port of jaffle
-- `mart_opportunity_player_week`). The opportunity side of fantasy value: target/air-yards/carry
-- shares, dropback share, snap share, pressure context, and starter/WR1/TE1/feature-back flags.
-- Joins fct + PFR advanced + the NGS satellites. Snowflake `iff` → DuckDB `case when`; PFR staging
-- repointed to stg_nfl_*. ⭐ sport-tagged. Excludes kickers.
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
        -- team totals
        max(case when f.offense_pct = 1.0 and f.is_bye = false then coalesce(f.offense_snaps, 0) else 0 end)
            over (partition by f.season, f.week, f.team_id) as team_snaps,
        coalesce(f.team_pass_attempts, 0) as team_pass_attempts,
        coalesce(f.team_rush_attempts, 0) as team_rush_attempts,
        coalesce(f.team_targets, 0) as team_targets,
        case when team_snaps > 0 then round(team_pass_attempts / team_snaps, 2) else 0.0 end as team_passing_pct,
        case when team_snaps > 0 then round(team_rush_attempts / team_snaps, 2) else 0.0 end as team_rushing_pct,
        -- receiving raw opportunity
        f.receiving_targets,
        f.target_share,
        f.receiving_air_yards,
        f.air_yards_share,
        coalesce(rn.avg_intended_air_yards, 0.0) as avg_intended_air_yards,
        coalesce(rn.percent_share_of_intended_air_yards, 0.0) as pct_share_intended_air_yards,
        coalesce(rn.avg_cushion, 0.0) as avg_cushion,
        coalesce(rn.avg_separation, 0.0) as avg_separation,
        coalesce(rn.avg_yards_after_catch, 0.0) as avg_yards_after_catch,
        coalesce(rn.avg_expected_yards_after_catch, 0.0) as avg_expected_yards_after_catch,
        coalesce(rn.avg_yards_after_catch_above_expectation, 0.0) as avg_yards_after_catch_above_expectation,
        coalesce(rp.receiving_drop, 0) as receiving_drops,
        coalesce(rp.receiving_drop_pct, 0.0) as receiving_drop_pct,
        coalesce(rp.receiving_broken_tackles, 0) as receiving_broken_tackles,
        coalesce(rp.receiving_interceptions, 0) as receiving_interceptions,
        coalesce(rp.receiving_rating, 0.0) as receiving_rating,
        -- rushing raw opportunity
        f.rushing_carries,
        f.carry_share,
        f.rushing_yards,
        f.rushing_touchdowns,
        f.rushing_first_downs,
        coalesce(rngs.avg_time_to_line_of_scrimmage, 0.0) as avg_time_to_line_of_scrimmage,
        coalesce(rngs.efficiency, 0.0) as ngs_rush_efficiency,
        coalesce(rngs.percent_attempts_gte_eight_defenders, 0.0) as ngs_box_8plus_pct,
        coalesce(rngs.expected_rushing_yards, 0.0) as ngs_expected_rushing_yards,
        coalesce(rngs.rushing_yards_over_expected, 0.0) as ngs_rushing_yards_over_expected,
        coalesce(rngs.rush_percentage_over_expected, 0.0) as ngs_rush_pct_over_expected,
        coalesce(rushp.rushing_broken_tackles, 0.0) as rushing_broken_tackles,
        -- qb specific
        f.pass_attempts,
        f.pass_completions,
        f.sacks_taken,
        f.sacks_taken::int + f.pass_attempts::int + f.rushing_carries::int as qb_dropbacks,
        sum(qb_dropbacks) over (partition by f.season, f.week, f.team_id) as team_dropbacks,
        case when qb_dropbacks > 0 then round(qb_dropbacks / team_dropbacks, 2) else 0.0 end as dropback_share,
        case when pp.times_pressured > 0 then round(f.sacks_taken / pp.times_pressured, 2) else 0.0 end as pressure_to_sack,
        coalesce(pp.times_blitzed, 0) as times_blitzed,
        coalesce(pp.times_hurried, 0) as times_hurried,
        coalesce(pp.times_hit, 0) as times_hit,
        coalesce(pp.times_pressured_pct, 0.0) as times_pressured_pct,
        coalesce(pn.avg_time_to_throw, 0.0) as avg_time_to_throw,
        coalesce(pn.aggressiveness, 0.0) as qb_aggressiveness,
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
