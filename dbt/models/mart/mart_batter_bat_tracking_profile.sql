-- =============================================================================
-- mart_batter_bat_tracking_profile.sql   (E11.1-W2 lakehouse decommission)
-- Grain: one row per batter_id × game_date (regular season, 2023-07-14+ only)
-- Purpose: 30-day rolling bat tracking averages per batter from Hawk-Eye bat
--          sensors. bat_speed_30d, swing_length_30d, attack_angle_30d.
--          Only swing events with valid bat tracking are included; pre-2023
--          rows are absent from this mart and will produce NULLs when joined
--          in feature_pregame_lineup_features.
-- Join key: batter_id + game_date (apply game_date < official_date leakage
--           guard in the consuming model)
--
-- E11.1-W2: dual-branch lakehouse model. Upstream stg_batter_pitches is lakehouse
-- parquet (ingest_statcast_to_s3); run_w1_lakehouse.py registers it as a view.
-- =============================================================================

{{
    config(
        materialized = 'view',
        tags         = ['w2_lakehouse']
    )
}}

{% if target.name == 'duckdb' %}

with

swing_events as (
    select
        -- game_date is VARCHAR (ISO) in lakehouse parquet; cast to DATE so the
        -- RANGE … INTERVAL window frames bind and the output type matches the
        -- prior Snowflake CTAS (DATE). [E11.1-W2]
        game_date::date     as game_date,
        batter_id,
        bat_speed_mph,
        swing_length_ft,
        attack_angle_degrees
    from stg_batter_pitches
    where game_type = 'R'
      and bat_speed_mph is not null
      and pitch_description in (
          'swinging_strike', 'swinging_strike_blocked',
          'foul', 'foul_bunt', 'foul_tip', 'bunt_foul_tip',
          'hit_into_play', 'hit_into_play_score', 'hit_into_play_no_out'
      )
),

-- Aggregate to batter × game_date: multiple games on the same date are merged
game_agg as (
    select
        game_date,
        batter_id,
        count(*)                    as swing_count,
        sum(bat_speed_mph)          as bat_speed_sum,
        sum(swing_length_ft)        as swing_length_sum,
        sum(attack_angle_degrees)   as attack_angle_sum
    from swing_events
    group by game_date, batter_id
),

-- 30-day rolling averages weighted by swing count per game-date
rolling as (
    select
        game_date,
        batter_id,

        round(
            sum(bat_speed_sum) over (
                partition by batter_id
                order by game_date
                range between interval '30 days' preceding and current row
            )
            / nullif(
                sum(swing_count) over (
                    partition by batter_id
                    order by game_date
                    range between interval '30 days' preceding and current row
                ), 0
            )
        , 2)                        as bat_speed_30d,

        round(
            sum(swing_length_sum) over (
                partition by batter_id
                order by game_date
                range between interval '30 days' preceding and current row
            )
            / nullif(
                sum(swing_count) over (
                    partition by batter_id
                    order by game_date
                    range between interval '30 days' preceding and current row
                ), 0
            )
        , 2)                        as swing_length_30d,

        round(
            sum(attack_angle_sum) over (
                partition by batter_id
                order by game_date
                range between interval '30 days' preceding and current row
            )
            / nullif(
                sum(swing_count) over (
                    partition by batter_id
                    order by game_date
                    range between interval '30 days' preceding and current row
                ), 0
            )
        , 2)                        as attack_angle_30d

    from game_agg
)

select * from rolling

{% else %}

select * from baseball_data.lakehouse_ext.mart_batter_bat_tracking_profile

{% endif %}
