-- =============================================================================
-- mart_pitch_fielding.sql
-- Grain: one row per pitch
-- Purpose: Defensive alignment and fielder identity at the time of each pitch.
--          Separated from pitcher profile to allow independent fielding analysis
--          without pulling pitch physics or pitcher usage context.
--          Join key: pitch_sk.
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

        -- ── Fielding alignment ────────────────────────────────────────────────────
        -- Known if_fielding_alignment values: Standard, Infield shade,
        --   Infield shift, Strategic
        -- Known of_fielding_alignment values: Standard, Strategic,
        --   Extreme outfield shift, 4th outfielder
        if_fielding_alignment,
        of_fielding_alignment,

        -- Infield flags
        coalesce(
            (if_fielding_alignment = 'Infield shift')::boolean, false
        )                                                       as is_infield_shift,
            -- True when if_fielding_alignment = 'Infield shift'. False when alignment
            -- not tracked by Statcast (70,778 regular-season pitches across all years).

        coalesce(
            (if_fielding_alignment = 'Infield shade')::boolean, false
        )                                                       as is_infield_shade,
            -- True when if_fielding_alignment = 'Infield shade'. False when not tracked.

        coalesce(
            (if_fielding_alignment = 'Strategic')::boolean, false
        )                                                       as is_infield_strategic,
            -- True when if_fielding_alignment = 'Strategic'. False when not tracked.

        coalesce(
            (if_fielding_alignment in (
                'Infield shift', 'Infield shade', 'Strategic'
            ))::boolean, false
        )                                                       as is_infield_non_standard,
            -- True when infield is non-standard. False when alignment not tracked.

        -- Outfield flags
        coalesce(
            (of_fielding_alignment = 'Extreme outfield shift')::boolean, false
        )                                                       as is_outfield_extreme_shift,
            -- True when of_fielding_alignment = 'Extreme outfield shift'. False when not tracked.

        coalesce(
            (of_fielding_alignment = '4th outfielder')::boolean, false
        )                                                       as is_fourth_outfielder,
            -- True when of_fielding_alignment = '4th outfielder'. False when not tracked.

        coalesce(
            (of_fielding_alignment = 'Strategic')::boolean, false
        )                                                       as is_outfield_strategic,
            -- True when of_fielding_alignment = 'Strategic'. False when not tracked.

        coalesce(
            (of_fielding_alignment in (
                'Extreme outfield shift', '4th outfielder', 'Strategic'
            ))::boolean, false
        )                                                       as is_outfield_non_standard,
            -- True when outfield is non-standard. False when alignment not tracked.

        -- Combined shade/shift indicator
        coalesce(
            (
                if_fielding_alignment in ('Infield shift', 'Infield shade')
                or of_fielding_alignment in ('Extreme outfield shift', '4th outfielder')
            )::boolean, false
        )                                                       as is_any_shade_or_shift,
            -- True when either infield or outfield is in a positional shade or shift.
            -- Excludes "Strategic" since that covers situational depth adjustments
            -- rather than lateral overloading. False when alignment not tracked.

        -- ── Fielder IDs by position ───────────────────────────────────────────────
        -- IDs reflect who was playing each position at the time of this pitch.
        -- Join to ref_players on mlb_bam_id for names.
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