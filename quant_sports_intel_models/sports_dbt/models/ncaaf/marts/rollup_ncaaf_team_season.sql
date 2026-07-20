-- rollup_ncaaf_team_season — the season-final team rollup (NCAAF-P1.1).
--
-- GRAIN: one row per (season, team_id). The team's COMPLETE season: record, scoring, efficiency,
-- drive quality, and garbage-time-excluded play efficiency.
--
-- ⛔⛔ NOT PREGAME-SAFE FOR ITS OWN SEASON. This rollup includes every game the team played,
-- including games that had not happened yet at any given point in that season. Joining it to a
-- game in season S by (S, team) leaks the future into the past — it is the single most obvious
-- way to build a model that backtests brilliantly and loses money.
--
--   ✅ Correct uses:  season-over-season priors (join season S−1 to a game in season S);
--                     reporting; the denominators for a season-level study.
--   ❌ Wrong use:     any feature for a game IN this season.
--   ⭐ For a pregame row in-season, use `rollup_ncaaf_team_week_asof` — which exists precisely
--      so nobody has to hand-roll this filter and get it wrong.
--
-- ⭐ FBS-filtered + sport-tagged (inherited from the facts, which are already restricted to
-- is_fbs_matchup). Play efficiency EXCLUDES garbage time (see fact_ncaaf_play's header for why
-- that is correctness, not taste).
{{ config(materialized='table') }}

with team_game as (
    select * from {{ ref('fact_ncaaf_team_game') }}
    where is_completed
),

-- drive quality per team-season (offense's own drives)
drive_agg as (
    select
        season,
        offense_team_id                                as team_id,
        count(*)                                       as drives,
        sum(points_scored)::double / nullif(count(*), 0) as points_per_drive,
        avg(is_scoring_opportunity::int)               as scoring_opportunity_rate,
        avg(is_three_and_out::int)                     as three_and_out_rate,
        avg(is_explosive_drive::int)                   as explosive_drive_rate,
        avg(yards_per_play)                            as drive_yards_per_play,
        avg(start_yards_to_goal)                       as avg_start_yards_to_goal
    from {{ ref('fact_ncaaf_drive') }}
    group by 1, 2
),

-- ⭐ play efficiency with GARBAGE TIME EXCLUDED — offense and defense
play_off as (
    select
        season, offense_team_id as team_id,
        count(*)                        as off_clean_plays,
        avg(ppa)                        as off_clean_ppa,
        avg(is_successful_play::int)    as off_clean_success_rate,
        avg(is_successful_play::int) filter (where is_passing_down) as off_clean_passing_down_success_rate,
        avg(ppa) filter (where is_pass_play) as off_clean_pass_ppa,
        avg(ppa) filter (where is_rush_play) as off_clean_rush_ppa
    from {{ ref('fact_ncaaf_play') }}
    where is_scrimmage_play and not is_garbage_time
    group by 1, 2
),

play_def as (
    select
        season, defense_team_id as team_id,
        count(*)                        as def_clean_plays,
        avg(ppa)                        as def_clean_ppa,
        avg(is_successful_play::int)    as def_clean_success_rate,
        avg(is_successful_play::int) filter (where is_passing_down) as def_clean_passing_down_success_rate,
        avg(ppa) filter (where is_pass_play) as def_clean_pass_ppa,
        avg(ppa) filter (where is_rush_play) as def_clean_rush_ppa
    from {{ ref('fact_ncaaf_play') }}
    where is_scrimmage_play and not is_garbage_time
    group by 1, 2
),

base as (
    select
        season,
        team_id,
        any_value(team)         as team,
        any_value(conference)   as conference,
        count(*)                as games_played,
        sum(is_win::int)        as wins,
        sum((not is_win)::int)  as losses,
        avg(is_win::int)        as win_pct,

        avg(points_for)         as points_for_per_game,
        avg(points_against)     as points_against_per_game,
        avg(margin)             as margin_per_game,
        avg(total_yards)        as total_yards_per_game,
        avg(rushing_yards)      as rushing_yards_per_game,
        avg(net_passing_yards)  as passing_yards_per_game,
        avg(turnovers)          as turnovers_per_game,
        avg(third_down_rate)    as third_down_rate,
        avg(fourth_down_rate)   as fourth_down_rate,
        avg(completion_rate)    as completion_rate,
        avg(possession_seconds) as possession_seconds_per_game,
        avg(penalties)          as penalties_per_game,
        avg(penalty_yards)      as penalty_yards_per_game,

        -- CFBD advanced, weighted by plays (a 90-play game should not count the same as a 50)
        sum(off_ppa * off_plays) / nullif(sum(off_plays), 0)                     as off_ppa,
        sum(off_success_rate * off_plays) / nullif(sum(off_plays), 0)            as off_success_rate,
        sum(off_explosiveness * off_plays) / nullif(sum(off_plays), 0)           as off_explosiveness,
        sum(off_line_yards * off_plays) / nullif(sum(off_plays), 0)              as off_line_yards,
        sum(off_stuff_rate * off_plays) / nullif(sum(off_plays), 0)              as off_stuff_rate,
        sum(off_power_success * off_plays) / nullif(sum(off_plays), 0)           as off_power_success,
        sum(def_ppa * def_plays) / nullif(sum(def_plays), 0)                     as def_ppa,
        sum(def_success_rate * def_plays) / nullif(sum(def_plays), 0)            as def_success_rate,
        sum(def_explosiveness * def_plays) / nullif(sum(def_plays), 0)           as def_explosiveness,
        sum(def_line_yards * def_plays) / nullif(sum(def_plays), 0)              as def_line_yards,
        sum(def_stuff_rate * def_plays) / nullif(sum(def_plays), 0)              as def_stuff_rate,
        sum(def_power_success * def_plays) / nullif(sum(def_plays), 0)           as def_power_success,
        avg(off_plays)                                                          as off_plays_per_game,
        sum(off_plays)                                                          as off_plays_total,
        sum(def_plays)                                                          as def_plays_total
    from team_game
    group by 1, 2
)

select
    'ncaaf'                    as sport,
    b.season,
    b.team_id,
    b.team,
    b.conference,
    b.season || '-' || b.team_id as team_season_key,
    b.*  exclude (season, team_id, team, conference),
    -- drive quality
    d.drives,
    d.points_per_drive,
    d.scoring_opportunity_rate,
    d.three_and_out_rate,
    d.explosive_drive_rate,
    d.drive_yards_per_play,
    d.avg_start_yards_to_goal,
    -- ⭐ garbage-time-excluded play efficiency
    po.off_clean_plays,
    po.off_clean_ppa,
    po.off_clean_success_rate,
    po.off_clean_passing_down_success_rate,
    po.off_clean_pass_ppa,
    po.off_clean_rush_ppa,
    pd.def_clean_plays,
    pd.def_clean_ppa,
    pd.def_clean_success_rate,
    pd.def_clean_passing_down_success_rate,
    pd.def_clean_pass_ppa,
    pd.def_clean_rush_ppa
from base b
left join drive_agg d on d.season = b.season and d.team_id = b.team_id
left join play_off  po on po.season = b.season and po.team_id = b.team_id
left join play_def  pd on pd.season = b.season and pd.team_id = b.team_id
