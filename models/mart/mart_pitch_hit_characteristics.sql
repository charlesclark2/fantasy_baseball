-- =============================================================================
-- mart_pitch_hit_characteristics.sql
-- Grain: one row per pitch where the ball was put in play (pitch_result_code = 'X')
-- Purpose: Batted ball physics, contact quality, expected outcome metrics,
--          and bat tracking for in-play events. Rows where the ball was not
--          put in play are excluded — this model is intentionally sparse.
--          Join key: pitch_sk.
-- =============================================================================

{{
    config(
        materialized = 'incremental',
        unique_key   = 'pitch_sk',
        incremental_strategy = 'merge'    )
}}

with

source as (

    select * from {{ ref('stg_batter_pitches') }}

    where pitch_result_code = 'X'
        -- Only pitches put in play have meaningful batted ball data

    {% if is_incremental() %}
        and game_date > (select max(game_date) from {{ this }})
    {% endif %}

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
            -- Human-readable label for the launch speed/angle zone

        -- ── Exit conditions ───────────────────────────────────────────────────────
        exit_velocity_mph,
        launch_angle_degrees,
        hit_distance_ft,

        -- ── Derived contact quality flags ─────────────────────────────────────────
        (launch_speed_angle_zone = 6)::boolean                  as is_barrel,
            -- Perfect combination of exit velocity and launch angle

        (exit_velocity_mph >= 95)::boolean                      as is_hard_hit,
            -- Statcast hard-hit threshold: 95+ mph exit velocity

        (
            launch_angle_degrees between 8 and 32
        )::boolean                                              as is_sweet_spot,
            -- Launch angle sweet-spot per Statcast definition

        (
            launch_angle_degrees between 8 and 32
            and exit_velocity_mph >= 95
        )::boolean                                              as is_hard_hit_sweet_spot,
            -- Combined quality flag: sweet-spot LA + hard-hit EV

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
            -- True when bat_speed_mph >= 75. Statcast defines a fast swing as
            -- one with a bat speed of 75 mph or higher. False when bat tracking
            -- data is unavailable (pre-2023) since absence of tracking means
            -- the swing was not fast enough to record, not that it wasn't taken.

        coalesce(
            attack_angle_degrees between 5 and 20, false
        )                                                       as is_ideal_attack_angle
            -- True when attack_angle_degrees is between 5 and 20 degrees
            -- inclusive. Statcast's definition of ideal attack angle for
            -- productive contact. False when bat tracking unavailable (pre-2023).

    from source

)

select * from final