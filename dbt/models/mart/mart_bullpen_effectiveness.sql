-- =============================================================================
-- mart_bullpen_effectiveness.sql
-- Grain: one row per team_abbrev per game_pk (games where the team used
--        at least one reliever)
-- Purpose: Rolling bullpen quality metrics (K%, BB%, xwOBA against,
--          hard-hit %, whiff rate, innings pitched) over the 14- and 30-day
--          windows preceding each game. All windows exclude the current game
--          to prevent data leakage. Use as a pre-game feature capturing
--          bullpen effectiveness entering a given game.
--
-- Reliever definition: any pitcher who is NOT the qualifying starter per
--   mart_starting_pitcher_game_log (first pitcher with >= 20 pitches or
--   >= 3 distinct innings). Identical to the definition in mart_bullpen_workload.
--
-- Rolling window upper bound: interval '1 day' preceding (same-day games
--   excluded). Both games of a doubleheader carry the same prior-day values.
--
-- Companion model: mart_bullpen_workload (availability / fatigue metrics).
--   Join both on pitching_team + game_pk for a complete pre-game bullpen view.
-- =============================================================================

-- E11.1-W5 dual-branch lakehouse model (W4-deferred Group B; was incremental). DuckDB
-- branch reads the W1 stg_batter_pitches + the W2 mart_starting_pitcher_game_log
-- (registered as DuckDB views) + the eb_bullpen_team_posteriors S3 parquet (exported by
-- scripts/export_w5_raw_to_s3.py); Snowflake branch is a thin view over the lakehouse_ext
-- external table. The eb_bullpen_team_posteriors dbt model KEEPS its Snowflake write — this
-- reads the one-time/opt-in S3 mirror. Full rebuild (incremental WHERE arms dropped).
-- game_date is cast ::date in the pitches CTE for the RANGE-interval rolling windows
-- (stg_batter_pitches stores it VARCHAR).

{{
    config(
        materialized = 'view',
        tags         = ['w5_lakehouse']
    )
}}

{% if target.name == 'duckdb' %}

with pitches as (

    select
        game_pk,
        game_date::date as game_date,
        game_year,
        at_bat_number,
        pitch_number,
        pitcher_id,
        home_team,
        away_team,
        inning_half,
        plate_appearance_event,
        pitch_result_code,
        pitch_description,
        exit_velocity_mph,
        xwoba,
        woba_value,
        woba_denom
    from stg_batter_pitches
    where game_type = 'R'

),

pitches_tagged as (

    select
        *,
        case when inning_half = 'Top' then home_team else away_team end
            as pitching_team
    from pitches

),

starters as (

    select game_pk, pitcher_id, pitching_team
    from mart_starting_pitcher_game_log

),

-- All pitches thrown by non-starters
reliever_pitches as (

    select pt.*
    from pitches_tagged pt
    left join starters s
        on  pt.game_pk       = s.game_pk
        and pt.pitcher_id    = s.pitcher_id
        and pt.pitching_team = s.pitching_team
    where s.pitcher_id is null

),

-- Aggregate effectiveness stats per reliever per game
reliever_pitcher_game as (

    select
        game_pk,
        game_date,
        game_year,
        pitcher_id,
        pitching_team,

        count(*)                                                as pitches_thrown,
        count(distinct at_bat_number)                          as batters_faced,

        sum(case when plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ) then 1 else 0 end)                                   as strikeouts,

        sum(case when plate_appearance_event in (
            'walk', 'intent_walk'
        ) then 1 else 0 end)                                   as walks,

        -- Outs recorded (mirrors mart_starting_pitcher_game_log definition)
        sum(case when plate_appearance_event in (
            'strikeout', 'strikeout_double_play',
            'field_out', 'force_out',
            'grounded_into_double_play', 'double_play', 'triple_play',
            'sac_fly', 'sac_fly_double_play',
            'sac_bunt', 'sac_bunt_double_play',
            'fielders_choice_out',
            'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
            'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
            'other_out'
        ) then 1 else 0 end)                                   as outs_recorded,

        -- xwOBA: use xwoba for in-play events, woba_value for K/BB/HBP
        sum(case when woba_denom = 1
            then coalesce(xwoba, woba_value)
            else 0
        end)                                                   as xwoba_numerator,
        sum(coalesce(woba_denom, 0))                           as xwoba_denom,

        -- Hard-hit: exit velocity >= 95 mph on in-play events
        sum(case when pitch_result_code = 'X' then 1 else 0 end)
                                                               as batted_balls,
        sum(case when pitch_result_code = 'X'
            and exit_velocity_mph >= 95
            then 1 else 0 end)                                 as hard_hit_balls,

        -- Whiff: swing-and-miss pitches
        sum(case when pitch_description in (
            'swinging_strike',
            'swinging_strike_blocked',
            'foul_tip',
            'missed_bunt'
        ) then 1 else 0 end)                                   as swing_and_misses

    from reliever_pitches
    group by game_pk, game_date, game_year, pitcher_id, pitching_team

),

-- Collapse to team × game level
team_game as (

    select
        game_pk,
        game_date,
        game_year,
        pitching_team,
        sum(pitches_thrown)   as pitches_thrown,
        sum(batters_faced)    as batters_faced,
        sum(strikeouts)       as strikeouts,
        sum(walks)            as walks,
        sum(outs_recorded)    as outs_recorded,
        sum(xwoba_numerator)  as xwoba_numerator,
        sum(xwoba_denom)      as xwoba_denom,
        sum(batted_balls)     as batted_balls,
        sum(hard_hit_balls)   as hard_hit_balls,
        sum(swing_and_misses) as swing_and_misses
    from reliever_pitcher_game
    group by game_pk, game_date, game_year, pitching_team

),

-- Collapse to team × date to handle doubleheader accuracy in rolling windows
team_date as (

    select
        game_date,
        game_year,
        pitching_team,
        sum(pitches_thrown)   as pitches_thrown,
        sum(batters_faced)    as batters_faced,
        sum(strikeouts)       as strikeouts,
        sum(walks)            as walks,
        sum(outs_recorded)    as outs_recorded,
        sum(xwoba_numerator)  as xwoba_numerator,
        sum(xwoba_denom)      as xwoba_denom,
        sum(batted_balls)     as batted_balls,
        sum(hard_hit_balls)   as hard_hit_balls,
        sum(swing_and_misses) as swing_and_misses
    from team_game
    group by game_date, game_year, pitching_team

),

-- Rolling effectiveness windows; upper bound = 1 day prior (no leakage)
rolling as (

    select
        game_date,
        pitching_team,

        -- ── 14-day rolling ──────────────────────────────────────────────────────
        round(
            sum(strikeouts) over (
                partition by pitching_team order by game_date
                range between interval '14 days' preceding
                          and interval '1 day'  preceding
            ) / nullif(sum(batters_faced) over (
                partition by pitching_team order by game_date
                range between interval '14 days' preceding
                          and interval '1 day'  preceding
            ), 0),
            4
        )                                                       as k_pct_14d,

        round(
            sum(walks) over (
                partition by pitching_team order by game_date
                range between interval '14 days' preceding
                          and interval '1 day'  preceding
            ) / nullif(sum(batters_faced) over (
                partition by pitching_team order by game_date
                range between interval '14 days' preceding
                          and interval '1 day'  preceding
            ), 0),
            4
        )                                                       as bb_pct_14d,

        round(
            sum(xwoba_numerator) over (
                partition by pitching_team order by game_date
                range between interval '14 days' preceding
                          and interval '1 day'  preceding
            ) / nullif(sum(xwoba_denom) over (
                partition by pitching_team order by game_date
                range between interval '14 days' preceding
                          and interval '1 day'  preceding
            ), 0),
            4
        )                                                       as xwoba_against_14d,

        round(
            sum(hard_hit_balls) over (
                partition by pitching_team order by game_date
                range between interval '14 days' preceding
                          and interval '1 day'  preceding
            ) / nullif(sum(batted_balls) over (
                partition by pitching_team order by game_date
                range between interval '14 days' preceding
                          and interval '1 day'  preceding
            ), 0),
            4
        )                                                       as hard_hit_pct_14d,

        round(
            sum(swing_and_misses) over (
                partition by pitching_team order by game_date
                range between interval '14 days' preceding
                          and interval '1 day'  preceding
            ) / nullif(sum(pitches_thrown) over (
                partition by pitching_team order by game_date
                range between interval '14 days' preceding
                          and interval '1 day'  preceding
            ), 0),
            4
        )                                                       as whiff_rate_14d,

        round(
            coalesce(sum(outs_recorded) over (
                partition by pitching_team order by game_date
                range between interval '14 days' preceding
                          and interval '1 day'  preceding
            ), 0) / 3.0,
            1
        )                                                       as innings_pitched_14d,

        -- ── 30-day rolling ──────────────────────────────────────────────────────
        round(
            sum(strikeouts) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ) / nullif(sum(batters_faced) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ), 0),
            4
        )                                                       as k_pct_30d,

        round(
            sum(walks) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ) / nullif(sum(batters_faced) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ), 0),
            4
        )                                                       as bb_pct_30d,

        round(
            sum(xwoba_numerator) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ) / nullif(sum(xwoba_denom) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ), 0),
            4
        )                                                       as xwoba_against_30d,

        round(
            sum(hard_hit_balls) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ) / nullif(sum(batted_balls) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ), 0),
            4
        )                                                       as hard_hit_pct_30d,

        round(
            sum(swing_and_misses) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ) / nullif(sum(pitches_thrown) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ), 0),
            4
        )                                                       as whiff_rate_30d,

        round(
            coalesce(sum(outs_recorded) over (
                partition by pitching_team order by game_date
                range between interval '30 days' preceding
                          and interval '1 day'  preceding
            ), 0) / 3.0,
            1
        )                                                       as innings_pitched_30d

    from team_date

),

eb_bullpen as (

    select
        game_pk,
        team,
        team_eb_bullpen_xwoba,
        team_eb_bullpen_uncertainty,
        round(
            n_relievers / nullif(n_relievers + n_prior_only, 0),
            4
        )                                                       as eb_bullpen_coverage_pct
    from read_parquet('{{ lakehouse_loc("eb_bullpen_team_posteriors") }}**/*.parquet', union_by_name=true)  -- A2.11 dbt model; W5 reads its S3 mirror

)

-- Join rolling effectiveness back to game_pk grain
select

    tg.game_pk,
    tg.game_date,
    tg.game_year,
    tg.pitching_team                                           as team_abbrev,

    -- ── 14-day rolling effectiveness ──────────────────────────────────────────
    r.k_pct_14d,
    r.bb_pct_14d,
    r.xwoba_against_14d,
    r.hard_hit_pct_14d,
    r.whiff_rate_14d,
    r.innings_pitched_14d,

    -- ── 30-day rolling effectiveness ──────────────────────────────────────────
    r.k_pct_30d,
    r.bb_pct_30d,
    r.xwoba_against_30d,
    r.hard_hit_pct_30d,
    r.whiff_rate_30d,
    r.innings_pitched_30d,

    -- ── Empirical Bayes bullpen estimates ────────────────────────────────────
    eb.team_eb_bullpen_xwoba                                   as eb_bullpen_xwoba,
    eb.team_eb_bullpen_uncertainty                             as eb_bullpen_uncertainty,
    eb.eb_bullpen_coverage_pct

from team_game tg
left join rolling r
    on  tg.game_date     = r.game_date
    and tg.pitching_team = r.pitching_team
left join eb_bullpen eb
    on  cast(tg.game_pk as text) = eb.game_pk
    and tg.pitching_team         = eb.team

{% else %}

select * from baseball_data.lakehouse_ext.mart_bullpen_effectiveness

{% endif %}
