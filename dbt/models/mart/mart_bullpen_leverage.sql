{{
    config(
        materialized = 'view',
        tags         = ['w3_lakehouse']
    )
}}

-- E11.1-W3: dual-branch lakehouse model. Upstream stg_batter_pitches (W1),
-- mart_pitch_play_event (W1), and mart_starting_pitcher_game_log (W2) are S3
-- parquet (registered as views by run_w1_lakehouse.py); the Snowflake branch is a
-- thin view over the lakehouse_ext external table. game_date is cast ::date in the
-- pitches CTE so the RANGE-interval rolling windows work on the VARCHAR game_date
-- the parquet carries.
--
-- Grain: team_abbrev × game_pk.
-- Pre-game bullpen leverage exhaustion for each team entering a given game.
-- Designed to join to feature_pregame_game_features on (team_abbrev + game_pk).
--
-- Column definitions:
--   bp_leverage_sum_3d          — sum of |delta_home_win_exp| for all reliever at-bats
--                                 over the trailing 3 calendar days
--   bp_high_lev_appearances_3d  — count of at-bats where at-bat-level |delta_home_win_exp|
--                                 exceeds 0.05 (5pp win-probability swing) over trailing 3 days
--   bp_leverage_sum_1d          — same as bp_leverage_sum_3d but trailing 1 day only
--
-- Leverage proxy: |delta_home_win_exp| per pitch, summed within each plate appearance.
-- A reliever who closed a 1-run game (high |delta|) appears more exhausted than one
-- who mopped up a blowout (low |delta|). This captures situational intensity beyond
-- raw pitch/inning counts from mart_bullpen_workload.
--
-- Leakage guard: rolling window upper bound is interval '1 day' preceding. Only
-- appearances strictly before the game date are included.
--
-- Starter exclusion: any pitcher listed in mart_starting_pitcher_game_log is excluded
-- from reliever calculations for that game.
--
-- Doubleheader handling: stats are aggregated to the calendar-date level before
-- rolling windows are computed. Both games of a doubleheader share the same
-- prior-day leverage values.
--
-- NULL when no reliever data in the trailing window. Impute 0.0 in
-- betting_ml/utils/preprocessing.py.
--
-- Companion models:
--   mart_bullpen_workload           — volume/fatigue metrics (IP, pitchers used)
--   mart_bullpen_effectiveness      — quality metrics (xwOBA, K%, BB%)
--   mart_bullpen_handedness_splits  — L/R split effectiveness
-- Join all four on team_abbrev + game_pk for a complete pre-game bullpen view.

{% if target.name == 'duckdb' %}

with

pitches as (

    select
        bp.pitch_sk,
        bp.game_pk,
        bp.game_date::date as game_date,   -- VARCHAR (ISO) in parquet → DATE for RANGE windows [E11.1-W3]
        bp.game_year,
        bp.at_bat_number,
        bp.pitcher_id,
        case when bp.inning_half = 'Top' then bp.home_team else bp.away_team end
            as pitching_team,
        ppe.delta_home_win_exp
    from stg_batter_pitches bp
    join mart_pitch_play_event ppe
        on ppe.pitch_sk = bp.pitch_sk
    where bp.game_type = 'R'
      and ppe.delta_home_win_exp is not null

),

starters as (

    select game_pk, pitcher_id, pitching_team
    from mart_starting_pitcher_game_log

),

reliever_pitches as (

    select p.*
    from pitches p
    left join starters s
        on  s.game_pk       = p.game_pk
        and s.pitcher_id    = p.pitcher_id
        and s.pitching_team = p.pitching_team
    where s.pitcher_id is null

),

-- At-bat leverage scores: sum |delta_home_win_exp| within each plate appearance
at_bat_leverage as (

    select
        game_pk,
        game_date,
        game_year,
        pitching_team,
        at_bat_number,
        sum(abs(delta_home_win_exp)) as at_bat_leverage_score
    from reliever_pitches
    group by game_pk, game_date, game_year, pitching_team, at_bat_number

),

-- Aggregate to game × team level
game_leverage as (

    select
        game_pk,
        game_date,
        game_year,
        pitching_team,
        sum(at_bat_leverage_score)                                      as game_bp_leverage_sum,
        sum(case when at_bat_leverage_score > 0.05 then 1 else 0 end)  as game_bp_high_lev_appearances
    from at_bat_leverage
    group by game_pk, game_date, game_year, pitching_team

),

-- Collapse to date level for doubleheader-safe rolling windows
date_leverage as (

    select
        game_date,
        game_year,
        pitching_team,
        sum(game_bp_leverage_sum)          as day_bp_leverage_sum,
        sum(game_bp_high_lev_appearances)  as day_bp_high_lev_appearances
    from game_leverage
    group by game_date, game_year, pitching_team

),

-- Rolling window aggregation; leakage guard: upper bound = 1 day prior
rolling as (

    select
        game_date,
        pitching_team,

        sum(day_bp_leverage_sum) over (
            partition by pitching_team order by game_date
            range between interval '3 days' preceding
                      and interval '1 day'  preceding
        )                                       as bp_leverage_sum_3d,

        sum(day_bp_high_lev_appearances) over (
            partition by pitching_team order by game_date
            range between interval '3 days' preceding
                      and interval '1 day'  preceding
        )                                       as bp_high_lev_appearances_3d,

        sum(day_bp_leverage_sum) over (
            partition by pitching_team order by game_date
            range between interval '1 day' preceding
                      and interval '1 day' preceding
        )                                       as bp_leverage_sum_1d

    from date_leverage

),

-- Game spine: one row per game_pk × pitching_team
game_spine as (

    select distinct game_pk, game_date, game_year, pitching_team
    from game_leverage

)

select
    gs.game_pk,
    gs.game_date,
    gs.game_year,
    gs.pitching_team    as team_abbrev,
    r.bp_leverage_sum_3d,
    r.bp_high_lev_appearances_3d,
    r.bp_leverage_sum_1d

from game_spine gs
left join rolling r
    on  r.game_date     = gs.game_date
    and r.pitching_team = gs.pitching_team

{% else %}

select * from baseball_data.lakehouse_ext.mart_bullpen_leverage

{% endif %}
