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
        (if_fielding_alignment = 'Infield shift')::boolean      as is_infield_shift,
            -- Full infield shift — three infielders on one side of second base

        (if_fielding_alignment = 'Infield shade')::boolean      as is_infield_shade,
            -- Infielders shifted slightly toward pull side without a full shift

        (if_fielding_alignment = 'Strategic')::boolean          as is_infield_strategic,
            -- Situational alignment (e.g. corners in, drawn in)

        (if_fielding_alignment in (
            'Infield shift', 'Infield shade', 'Strategic'
        ))::boolean                                             as is_infield_non_standard,
            -- Any infield alignment that deviates from Standard

        -- Outfield flags
        (of_fielding_alignment = 'Extreme outfield shift')::boolean
                                                                as is_outfield_extreme_shift,
            -- All three outfielders shifted heavily toward one side

        (of_fielding_alignment = '4th outfielder')::boolean     as is_fourth_outfielder,
            -- Four-outfielder alignment; typically vs. pull-heavy power hitters

        (of_fielding_alignment = 'Strategic')::boolean          as is_outfield_strategic,
            -- Situational outfield positioning (e.g. outfield in for shallow play)

        (of_fielding_alignment in (
            'Extreme outfield shift', '4th outfielder', 'Strategic'
        ))::boolean                                             as is_outfield_non_standard,
            -- Any outfield alignment that deviates from Standard

        -- Combined shade/shift indicator
        (
            if_fielding_alignment in ('Infield shift', 'Infield shade')
            or of_fielding_alignment in ('Extreme outfield shift', '4th outfielder')
        )::boolean                                             as is_any_shade_or_shift,
            -- True when either infield or outfield is in a positional shade or shift.
            -- Excludes "Strategic" since that covers situational depth adjustments
            -- rather than lateral overloading.

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