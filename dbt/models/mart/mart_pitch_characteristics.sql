-- =============================================================================
-- mart_pitch_characteristics.sql  (E11.1-W1d decommission)
-- Grain: one row per pitch
-- Purpose: Physical characteristics of the pitch itself — velocity, movement,
--          spin, release mechanics, and zone location.
-- DuckDB branch: used by run_w1_lakehouse.py to build the S3 parquet.
-- Snowflake branch: thin view over baseball_data.lakehouse_ext external table.
-- =============================================================================

{{
    config(
        materialized = 'view',
        enabled      = (target.name == 'duckdb'),
        tags         = ['w1_lakehouse']
    )
}}
-- E11.20 phase 1.5 (2026-07-20): SF side RETIRED via enabled=(target.name=='duckdb') —
-- the SF thin view over lakehouse_ext is dropped (zero readers since 7/13; stragglers
-- repointed in a0). The duckdb branch stays: run_w1_lakehouse.py extracts it for the
-- Delta build (it strips the config call, so the flag is invisible to the box build).

{% if target.name == 'duckdb' %}

with

source as (

    select * from stg_batter_pitches

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

        -- ── Velocity ─────────────────────────────────────────────────────────────
        release_speed_mph,
        effective_speed_mph,
        release_speed_mph - effective_speed_mph                 as speed_vs_perceived_diff,

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

        case
            when pitcher_hand = 'R' and plate_x_ft > 0  then 'arm_side'
            when pitcher_hand = 'R' and plate_x_ft <= 0 then 'glove_side'
            when pitcher_hand = 'L' and plate_x_ft < 0  then 'arm_side'
            when pitcher_hand = 'L' and plate_x_ft >= 0 then 'glove_side'
        end                                                     as pitch_side

    from source

)

select * from final

{% else %}

select * from baseball_data.lakehouse_ext.mart_pitch_characteristics

{% endif %}
