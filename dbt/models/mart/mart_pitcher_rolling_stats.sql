-- =============================================================================
-- mart_pitcher_rolling_stats.sql
-- Grain: one row per pitcher × game (regular season appearances only)
-- Purpose: Rolling pitcher performance statistics over 7/14/30-day and
--          season-to-date windows. Designed as a primary feature source for
--          game outcome prediction — a starter's recent form (last 2-3 starts)
--          is more predictive than season-line stats, especially after injuries
--          or mechanical changes.
-- Key metrics: K%, BB%, whiff rate, barrel rate allowed, hard-hit rate allowed,
--              xwOBA against, avg fastball velocity, avg release extension,
--              batter chase rate.
-- Join keys: pitcher_id, game_date
-- =============================================================================

-- E11.1-W2: dual-branch lakehouse model (was incremental on Snowflake; the
-- duckdb branch is a full rebuild — the daily run rewrites the parquet, like the
-- W1 marts). Upstream stg_batter_pitches is lakehouse parquet, registered as a
-- view by run_w1_lakehouse.py before this model builds.
{{
    config(
        materialized = 'view',
        tags         = ['w2_lakehouse']
    )
}}

{% if target.name == 'duckdb' %}

with

pitches as (

    select p.*
    from stg_batter_pitches p
    where p.game_type = 'R'

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Annotate every pitch with team context, swing/contact flags, and the
-- identity of the game's starting pitcher for this team.
-- ─────────────────────────────────────────────────────────────────────────────
pitches_tagged as (

    select
        game_pk,
        -- game_date is VARCHAR (ISO) in lakehouse parquet; cast to DATE so the
        -- RANGE … INTERVAL rolling windows bind and the output matches the prior
        -- Snowflake CTAS (DATE). [E11.1-W2]
        game_date::date as game_date,
        game_year,
        at_bat_number,
        pitch_number,
        pitcher_id,
        pitcher_hand,

        case when inning_half = 'Top' then home_team else away_team end  as pitching_team,
        case when inning_half = 'Top' then away_team else home_team end  as facing_team,

        plate_appearance_event,
        pitch_description,
        pitch_type,
        pitch_zone,

        exit_velocity_mph,
        launch_speed_angle_zone,
        xwoba,
        woba_value,
        woba_denom,
        release_speed_mph,
        release_extension_ft,

        -- Swing: batter offered at the pitch
        (pitch_description in (
            'swinging_strike', 'swinging_strike_blocked',
            'foul', 'foul_bunt', 'foul_tip', 'bunt_foul_tip', 'missed_bunt',
            'hit_into_play', 'hit_into_play_score', 'hit_into_play_no_out'
        ))::boolean                                                         as is_swing,

        -- Whiff: swing and complete miss (foul_tip = contact, not a whiff)
        (pitch_description in (
            'swinging_strike', 'swinging_strike_blocked', 'missed_bunt'
        ))::boolean                                                         as is_whiff,

        -- Out-of-zone: zones 11-14 per Statcast zone map
        (pitch_zone between 11 and 14)::boolean                             as is_out_of_zone,

        -- Fastball family: 4-seam (FF), sinker (SI), cutter (FC)
        (pitch_type in ('FF', 'SI', 'FC'))::boolean                         as is_fastball,

        -- Identify the starter: first pitcher_id to appear for this team in the game
        first_value(pitcher_id) over (
            partition by game_pk,
            case when inning_half = 'Top' then home_team else away_team end
            order by at_bat_number, pitch_number
            rows between unbounded preceding and unbounded following
        )                                                                   as starting_pitcher_id

    from pitches

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Plate-appearance level: terminal pitches only, outcome flags
-- ─────────────────────────────────────────────────────────────────────────────
plate_appearances as (

    select
        game_pk,
        game_date,
        game_year,
        pitcher_id,
        pitcher_hand,
        pitching_team,
        facing_team,
        (pitcher_id = starting_pitcher_id)::boolean                         as is_starter,

        woba_value,
        woba_denom,
        xwoba,

        (plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ))::boolean                                                         as is_strikeout,

        (plate_appearance_event in (
            'walk', 'intent_walk'
        ))::boolean                                                         as is_walk,

        (plate_appearance_event in (
            'single', 'double', 'triple', 'home_run'
        ))::boolean                                                         as is_hit,

        (plate_appearance_event = 'home_run')::boolean                      as is_home_run,

        (exit_velocity_mph >= 95)::boolean                                  as is_hard_hit,
        (launch_speed_angle_zone = 6)::boolean                              as is_barrel,
        (exit_velocity_mph is not null)::boolean                            as is_batted_ball

    from pitches_tagged
    where plate_appearance_event is not null
      and plate_appearance_event != 'truncated_pa'

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Pitch-level aggregates per pitcher × game
-- ─────────────────────────────────────────────────────────────────────────────
pitch_game_agg as (

    select
        game_pk,
        pitcher_id,

        count(*)                                                            as pitch_count,
        sum(is_swing::integer)                                              as swings,
        sum(is_whiff::integer)                                              as whiffs,
        sum(is_out_of_zone::integer)                                        as out_of_zone_pitches,
        sum((is_out_of_zone and is_swing)::integer)                         as out_of_zone_swings,

        -- Fastball velocity (only on fastball pitch types with valid readings)
        sum(case when is_fastball and release_speed_mph is not null
                 then release_speed_mph end)                                as fastball_speed_sum,
        count(case when is_fastball and release_speed_mph is not null
                   then 1 end)                                              as fastball_count,

        -- Release extension
        sum(case when release_extension_ft is not null
                 then release_extension_ft end)                             as extension_sum,
        count(case when release_extension_ft is not null
                   then 1 end)                                              as extension_count

    from pitches_tagged
    group by game_pk, pitcher_id

),

-- ─────────────────────────────────────────────────────────────────────────────
-- PA-level aggregates per pitcher × game
-- ─────────────────────────────────────────────────────────────────────────────
pa_game_agg as (

    select
        game_pk,
        game_date,
        game_year,
        pitcher_id,
        pitcher_hand,
        pitching_team,
        facing_team,

        -- Take the starter flag from any row (all rows for the same pitcher × game agree)
        max(is_starter::integer)::boolean                                   as is_starter,

        count(*)                                                            as batters_faced,
        sum(woba_value)                                                     as woba_value_sum,
        sum(woba_denom)                                                     as woba_denom_sum,
        sum(xwoba)                                                          as xwoba_sum,
        count(xwoba)                                                        as xwoba_denom,
        sum(is_strikeout::integer)                                          as strikeouts,
        sum(is_walk::integer)                                               as walks,
        sum(is_hit::integer)                                                as hits_allowed,
        sum(is_home_run::integer)                                           as home_runs_allowed,
        sum(is_hard_hit::integer)                                           as hard_hit_balls,
        sum(is_barrel::integer)                                             as barrels,
        sum(is_batted_ball::integer)                                        as batted_balls

    from plate_appearances
    group by game_pk, game_date, game_year, pitcher_id, pitcher_hand, pitching_team, facing_team

),

-- Combine PA and pitch aggregates into one game-level row per pitcher
game_stats as (

    select
        pa.game_pk,
        pa.game_date,
        pa.game_year,
        pa.pitcher_id,
        pa.pitcher_hand,
        pa.pitching_team,
        pa.facing_team,
        pa.is_starter,
        pa.batters_faced,
        pm.pitch_count,
        pm.swings,
        pm.whiffs,
        pm.out_of_zone_pitches,
        pm.out_of_zone_swings,
        pm.fastball_speed_sum,
        pm.fastball_count,
        pm.extension_sum,
        pm.extension_count,
        pa.woba_value_sum,
        pa.woba_denom_sum,
        pa.xwoba_sum,
        pa.xwoba_denom,
        pa.strikeouts,
        pa.walks,
        pa.hits_allowed,
        pa.home_runs_allowed,
        pa.hard_hit_balls,
        pa.barrels,
        pa.batted_balls

    from pa_game_agg pa
    join pitch_game_agg pm
        on pa.game_pk = pm.game_pk
        and pa.pitcher_id = pm.pitcher_id

),

-- ─────────────────────────────────────────────────────────────────────────────
-- Rolling windows — inline window specs for Snowflake compatibility
-- ─────────────────────────────────────────────────────────────────────────────
rolling as (

    select
        game_pk,
        game_date,
        game_year,
        pitcher_id,
        pitcher_hand,
        pitching_team,
        facing_team,
        is_starter,

        -- ── Single-game actuals ─────────────────────────────────────────────────
        batters_faced,
        pitch_count,
        strikeouts,
        walks,
        hits_allowed,
        home_runs_allowed,

        round(
            case when woba_denom_sum > 0
                 then (woba_value_sum / woba_denom_sum)::numeric else null end, 3
        )                                                                   as woba_against,
        round(
            case when xwoba_denom > 0
                 then (xwoba_sum / xwoba_denom)::numeric else null end, 3
        )                                                                   as xwoba_against,
        round(
            case when batters_faced > 0
                 then (strikeouts::numeric / batters_faced) else null end, 3
        )                                                                   as k_pct,
        round(
            case when batters_faced > 0
                 then (walks::numeric / batters_faced) else null end, 3
        )                                                                   as bb_pct,
        round(
            case when swings > 0
                 then (whiffs::numeric / swings) else null end, 3
        )                                                                   as whiff_rate,
        round(
            case when pitch_count > 0
                 then (whiffs::numeric / pitch_count) else null end, 3
        )                                                                   as swinging_strike_rate,
        round(
            case when out_of_zone_pitches > 0
                 then (out_of_zone_swings::numeric / out_of_zone_pitches) else null end, 3
        )                                                                   as batter_chase_rate,
        round(
            case when batted_balls > 0
                 then (hard_hit_balls::numeric / batted_balls) else null end, 3
        )                                                                   as hard_hit_pct_allowed,
        round(
            case when batted_balls > 0
                 then (barrels::numeric / batted_balls) else null end, 3
        )                                                                   as barrel_pct_allowed,
        round(
            case when fastball_count > 0
                 then (fastball_speed_sum / fastball_count)::numeric else null end, 1
        )                                                                   as avg_fastball_velo,
        round(
            case when extension_count > 0
                 then (extension_sum / extension_count)::numeric else null end, 2
        )                                                                   as avg_release_extension,

        -- ── Rolling 7-day ────────────────────────────────────────────────────────
        count(*) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row) as games_7d,
        sum(batters_faced) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row) as batters_faced_7d,
        sum(pitch_count)   over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row) as pitches_7d,

        round(
            sum(woba_value_sum) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as woba_against_7d,
        round(
            sum(xwoba_sum) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as xwoba_against_7d,
        round(
            sum(strikeouts) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(batters_faced) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as k_pct_7d,
        round(
            sum(walks) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(batters_faced) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as bb_pct_7d,
        round(
            sum(whiffs) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(swings) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as whiff_rate_7d,
        round(
            sum(whiffs) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(pitch_count) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as swinging_strike_rate_7d,
        round(
            sum(out_of_zone_swings) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(out_of_zone_pitches) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as batter_chase_rate_7d,
        round(
            sum(hard_hit_balls) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as hard_hit_pct_7d,
        round(
            sum(barrels) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 3) as barrel_pct_7d,
        round(
            sum(fastball_speed_sum) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(fastball_count) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 1) as avg_fastball_velo_7d,
        round(
            sum(extension_sum) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row)
            / nullif(sum(extension_count) over (partition by pitcher_id order by game_date range between interval '7 days' preceding and current row), 0)
        , 2) as avg_release_extension_7d,

        -- ── Rolling 14-day ───────────────────────────────────────────────────────
        count(*) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row) as games_14d,
        sum(batters_faced) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row) as batters_faced_14d,
        sum(pitch_count)   over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row) as pitches_14d,

        round(
            sum(woba_value_sum) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as woba_against_14d,
        round(
            sum(xwoba_sum) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as xwoba_against_14d,
        round(
            sum(strikeouts) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(batters_faced) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as k_pct_14d,
        round(
            sum(walks) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(batters_faced) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as bb_pct_14d,
        round(
            sum(whiffs) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(swings) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as whiff_rate_14d,
        round(
            sum(whiffs) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(pitch_count) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as swinging_strike_rate_14d,
        round(
            sum(out_of_zone_swings) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(out_of_zone_pitches) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as batter_chase_rate_14d,
        round(
            sum(hard_hit_balls) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as hard_hit_pct_14d,
        round(
            sum(barrels) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 3) as barrel_pct_14d,
        round(
            sum(fastball_speed_sum) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(fastball_count) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 1) as avg_fastball_velo_14d,
        round(
            sum(extension_sum) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row)
            / nullif(sum(extension_count) over (partition by pitcher_id order by game_date range between interval '14 days' preceding and current row), 0)
        , 2) as avg_release_extension_14d,

        -- ── Rolling 30-day ───────────────────────────────────────────────────────
        count(*) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row) as games_30d,
        sum(batters_faced) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row) as batters_faced_30d,
        sum(pitch_count)   over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row) as pitches_30d,

        round(
            sum(woba_value_sum) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as woba_against_30d,
        round(
            sum(xwoba_sum) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as xwoba_against_30d,
        round(
            sum(strikeouts) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(batters_faced) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as k_pct_30d,
        round(
            sum(walks) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(batters_faced) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as bb_pct_30d,
        round(
            sum(whiffs) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(swings) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as whiff_rate_30d,
        round(
            sum(whiffs) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(pitch_count) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as swinging_strike_rate_30d,
        round(
            sum(out_of_zone_swings) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(out_of_zone_pitches) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as batter_chase_rate_30d,
        round(
            sum(hard_hit_balls) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as hard_hit_pct_30d,
        round(
            sum(barrels) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(batted_balls) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 3) as barrel_pct_30d,
        round(
            sum(fastball_speed_sum) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(fastball_count) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 1) as avg_fastball_velo_30d,
        round(
            sum(extension_sum) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row)
            / nullif(sum(extension_count) over (partition by pitcher_id order by game_date range between interval '30 days' preceding and current row), 0)
        , 2) as avg_release_extension_30d,

        -- ── Season-to-date ───────────────────────────────────────────────────────
        count(*) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row) as games_std,
        sum(batters_faced) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row) as batters_faced_std,
        sum(pitch_count)   over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row) as pitches_std,

        round(
            sum(woba_value_sum) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(woba_denom_sum) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as woba_against_std,
        round(
            sum(xwoba_sum) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(xwoba_denom) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as xwoba_against_std,
        round(
            sum(strikeouts) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(batters_faced) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as k_pct_std,
        round(
            sum(walks) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(batters_faced) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as bb_pct_std,
        round(
            sum(whiffs) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(swings) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as whiff_rate_std,
        round(
            sum(whiffs) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(pitch_count) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as swinging_strike_rate_std,
        round(
            sum(out_of_zone_swings) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(out_of_zone_pitches) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as batter_chase_rate_std,
        round(
            sum(hard_hit_balls) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(batted_balls) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as hard_hit_pct_std,
        round(
            sum(barrels) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(batted_balls) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 3) as barrel_pct_std,
        round(
            sum(fastball_speed_sum) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(fastball_count) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 1) as avg_fastball_velo_std,
        round(
            sum(extension_sum) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row)
            / nullif(sum(extension_count) over (partition by pitcher_id, game_year order by game_date rows between unbounded preceding and current row), 0)
        , 2) as avg_release_extension_std

    from game_stats

)

select * from rolling
order by pitcher_id, game_date

{% else %}

select * from baseball_data.lakehouse_ext.mart_pitcher_rolling_stats

{% endif %}
