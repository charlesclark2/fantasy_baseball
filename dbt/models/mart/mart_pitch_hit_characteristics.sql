-- =============================================================================
-- mart_pitch_hit_characteristics.sql  (E11.1-W1d decommission)
-- Grain: one row per pitch where the ball was put in play (pitch_result_code = 'X')
-- Purpose: Batted ball physics, contact quality, expected outcome metrics,
--          and bat tracking for in-play events.
-- DuckDB branch: used by run_w1_lakehouse.py to build the S3 parquet.
-- Snowflake branch: thin view over baseball_data.lakehouse_ext external table.
-- =============================================================================

{{
    config(
        materialized = 'view',
        tags         = ['w1_lakehouse']
    )
}}

{% if target.name == 'duckdb' %}

with

source as (

    select * from stg_batter_pitches

    where pitch_result_code = 'X'

),

final as (

    select

        -- ── Keys ────────────────────────────────────────────────────────────────
        pitch_sk,
        game_pk,
        game_date,
        game_year,
        at_bat_number,
        pitch_number,
        pitcher_id,
        batter_id,

        -- ── Batted ball classification ────────────────────────────────────────────
        batted_ball_type,
        launch_speed_angle_zone,

        case launch_speed_angle_zone
            when 1 then 'weak'
            when 2 then 'topped'
            when 3 then 'under'
            when 4 then 'flare_burner'
            when 5 then 'solid_contact'
            when 6 then 'barrel'
        end                                                     as contact_quality,

        -- ── Exit conditions ───────────────────────────────────────────────────────
        exit_velocity_mph,
        launch_angle_degrees,
        hit_distance_ft,

        -- ── Derived contact quality flags ─────────────────────────────────────────
        coalesce(launch_speed_angle_zone = 6, false)            as is_barrel,
        coalesce(exit_velocity_mph >= 95, false)                as is_hard_hit,

        coalesce(
            launch_angle_degrees between 8 and 32,
            false
        )                                                       as is_sweet_spot,

        coalesce(
            launch_angle_degrees between 8 and 32
            and exit_velocity_mph >= 95,
            false
        )                                                       as is_hard_hit_sweet_spot,

        -- ── Hit location ─────────────────────────────────────────────────────────
        hit_coord_x,
        hit_coord_y,
        hit_location_fielder,

        -- ── Expected outcome metrics ──────────────────────────────────────────────
        xba,
        xwoba,
        xslg,
        woba_value,
        woba_denom,
        babip_value,
        iso_value,

        -- ── Bat tracking (2023+; null for earlier seasons) ────────────────────────
        bat_speed_mph,
        swing_length_ft,
        attack_angle_degrees,
        attack_direction_degrees,
        swing_path_tilt_degrees,
        hyper_speed,
        intercept_offset_x_inches,
        intercept_offset_y_inches,

        -- ── Derived bat tracking flags ────────────────────────────────────────────
        coalesce(bat_speed_mph >= 75, false)                    as is_fast_swing,

        coalesce(
            attack_angle_degrees between 5 and 20, false
        )                                                       as is_ideal_attack_angle

    from source

)

select * from final

{% else %}

select * from baseball_data.lakehouse_ext.mart_pitch_hit_characteristics

{% endif %}
