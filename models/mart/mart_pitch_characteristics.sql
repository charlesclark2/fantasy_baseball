-- =============================================================================
-- mart_pitch_characteristics.sql
-- Grain: one row per pitch
-- Purpose: Physical characteristics of the pitch itself — velocity, movement,
--          spin, release mechanics, and zone location. All rows populated
--          regardless of pitch outcome. Join key: pitch_sk.
-- =============================================================================

{{
    config(
        materialized = 'incremental',
        unique_key   = 'pitch_sk',
        incremental_strategy = 'merge'
    )
}}

with

source as (

    select * from {{ ref('stg_batter_pitches') }}

    {% if is_incremental() %}
        where game_date > (select max(game_date) from {{ this }})
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

        -- ── Pitch classification ─────────────────────────────────────────────────
        pitch_type,
        pitch_name,

        case
            when pitch_type in ('FF', 'SI', 'FC')       then 'fastball'
            when pitch_type in ('SL', 'ST', 'SV')       then 'breaking'
            when pitch_type in ('CU', 'KC', 'CS', 'EP') then 'breaking'
            when pitch_type in ('CH', 'FS', 'FO', 'SC') then 'offspeed'
            when pitch_type = 'KN'                       then 'knuckleball'
            else 'other'
        end                                                     as pitch_category,
            -- Broad pitch family grouping for aggregation

        -- ── Velocity ─────────────────────────────────────────────────────────────
        release_speed_mph,
        effective_speed_mph,
        release_speed_mph - effective_speed_mph                 as speed_vs_perceived_diff,
            -- Positive = batter perceives pitch as slower than release speed

        -- ── Spin ─────────────────────────────────────────────────────────────────
        release_spin_rate_rpm,
        spin_axis_degrees,

        -- ── Release mechanics ────────────────────────────────────────────────────
        release_pos_x_ft,
        release_pos_y_ft,
        release_pos_z_ft,
        release_extension_ft,
        pitcher_arm_angle_degrees,

        -- ── Movement (Statcast pfx) ───────────────────────────────────────────────
        pitch_movement_x_ft,
        pitch_movement_z_ft,

        -- ── Movement (API physics-based) ──────────────────────────────────────────
        api_break_z_with_gravity_in,
        api_break_x_arm_in,
        api_break_x_batter_in,

        -- ── Kinematics at y=50ft reference plane ─────────────────────────────────
        vx0_fps,
        vy0_fps,
        vz0_fps,
        ax_fps2,
        ay_fps2,
        az_fps2,

        -- ── Plate location ───────────────────────────────────────────────────────
        plate_x_ft,
        plate_z_ft,
        strike_zone_top_ft,
        strike_zone_bot_ft,
        pitch_zone,

        -- ── Derived location flags ───────────────────────────────────────────────
        coalesce(
            plate_x_ft between -0.8333 and 0.8333
            and plate_z_ft between strike_zone_bot_ft and strike_zone_top_ft,
            false
        )                                                       as is_in_zone,
            -- True if ball crosses within the rulebook strike zone.
            -- Horizontal bounds ≈ ±10 inches (half of 17-inch plate).
            -- False when plate location data is unavailable.

        case
            when pitcher_hand = 'R' and plate_x_ft > 0  then 'arm_side'
            when pitcher_hand = 'R' and plate_x_ft <= 0 then 'glove_side'
            when pitcher_hand = 'L' and plate_x_ft < 0  then 'arm_side'
            when pitcher_hand = 'L' and plate_x_ft >= 0 then 'glove_side'
        end                                                     as pitch_side
            -- Arm-side vs glove-side horizontal location from pitcher's POV

    from source

)

select * from final