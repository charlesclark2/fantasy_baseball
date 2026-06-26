-- =============================================================================
-- mart_pitch_fielding.sql  (E11.1-W1d decommission)
-- Grain: one row per pitch
-- Purpose: Defensive alignment and fielder identity at the time of each pitch.
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

        -- ── Fielding alignment ────────────────────────────────────────────────────
        if_fielding_alignment,
        of_fielding_alignment,

        (if_fielding_alignment = 'Infield shift')::boolean      as is_infield_shift,
        (if_fielding_alignment = 'Infield shade')::boolean      as is_infield_shade,
        (if_fielding_alignment = 'Strategic')::boolean          as is_infield_strategic,

        (if_fielding_alignment in (
            'Infield shift', 'Infield shade', 'Strategic'
        ))::boolean                                             as is_infield_non_standard,

        (of_fielding_alignment = 'Extreme outfield shift')::boolean
                                                                as is_outfield_extreme_shift,

        (of_fielding_alignment = '4th outfielder')::boolean     as is_fourth_outfielder,
        (of_fielding_alignment = 'Strategic')::boolean          as is_outfield_strategic,

        (of_fielding_alignment in (
            'Extreme outfield shift', '4th outfielder', 'Strategic'
        ))::boolean                                             as is_outfield_non_standard,

        (
            if_fielding_alignment in ('Infield shift', 'Infield shade')
            or of_fielding_alignment in ('Extreme outfield shift', '4th outfielder')
        )::boolean                                             as is_any_shade_or_shift,

        -- ── Fielder IDs by position ───────────────────────────────────────────────
        catcher_id,
        first_base_id,
        second_base_id,
        third_base_id,
        shortstop_id,
        left_field_id,
        center_field_id,
        right_field_id

    from source

)

select * from final

{% else %}

select * from baseball_data.lakehouse_ext.mart_pitch_fielding

{% endif %}
