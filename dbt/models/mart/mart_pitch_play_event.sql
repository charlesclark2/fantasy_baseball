-- =============================================================================
-- mart_pitch_play_event.sql
-- Grain: one row per pitch
-- Purpose: What happened on the pitch and resulting plate appearance outcome.
--          Includes swing/contact flags, terminal PA events, error detection
--          parsed from plate_appearance_description, and run/win impact.
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

        -- ── Raw pitch outcome ────────────────────────────────────────────────────
        pitch_result_code,
        pitch_description,
        plate_appearance_event,
        plate_appearance_description,

        -- ── Pitch-level outcome flags ─────────────────────────────────────────────
        (pitch_result_code = 'S')::boolean                      as is_strike,
        (pitch_result_code = 'B')::boolean                      as is_ball,
        (pitch_result_code = 'X')::boolean                      as is_in_play,

        (pitch_description in (
            'swinging_strike',
            'swinging_strike_blocked',
            'foul_tip',
            'missed_bunt'
        ))::boolean                                             as is_swing_and_miss,
            -- Contact was attempted but missed

        (pitch_description in (
            'swinging_strike',
            'swinging_strike_blocked',
            'foul_tip',
            'missed_bunt',
            'foul',
            'foul_bunt',
            'hit_into_play',
            'hit_into_play_no_out',
            'hit_into_play_score'
        ))::boolean                                             as is_swing,
            -- Any pitch the batter offered at

        (pitch_description = 'called_strike')::boolean          as is_called_strike,
        (pitch_description in ('ball', 'blocked_ball',
            'pitchout', 'intent_ball'))::boolean                as is_called_ball,

        -- ── Terminal PA event flags ───────────────────────────────────────────────
        -- Only populated on the final pitch of a plate appearance
        (plate_appearance_event is not null)::boolean           as is_terminal_pitch,

        coalesce(plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ), false)                                               as is_strikeout,

        coalesce(plate_appearance_event in (
            'walk', 'intent_walk'
        ), false)                                               as is_walk,

        coalesce(
            plate_appearance_event = 'hit_by_pitch', false
        )                                                       as is_hit_by_pitch,

        coalesce(plate_appearance_event in (
            'single', 'double', 'triple', 'home_run'
        ), false)                                               as is_hit,

        coalesce(
            plate_appearance_event = 'home_run', false
        )                                                       as is_home_run,

        coalesce(plate_appearance_event in (
            'single', 'double', 'triple', 'home_run',
            'walk', 'intent_walk', 'hit_by_pitch',
            'sac_fly', 'sac_fly_double_play'
        ), false)                                               as is_on_base_event,

        coalesce(plate_appearance_event in (
            'field_out', 'force_out', 'grounded_into_double_play',
            'double_play', 'triple_play', 'fielders_choice',
            'fielders_choice_out', 'sac_bunt', 'sac_bunt_double_play',
            'sac_fly', 'sac_fly_double_play', 'strikeout',
            'strikeout_double_play'
        ), false)                                               as is_out_event,

        -- ── Error detection from plate_appearance_description ─────────────────────
        -- MLB Gameday descriptions use consistent phrasing for errors.
        -- We detect presence, type, and the position that committed the error.
        (
            lower(plate_appearance_description) like '%error%'
        )::boolean                                              as error_on_play,
            -- True when any error (fielding or throwing) is mentioned

        case
            when lower(plate_appearance_description) like '%throwing error%'   then 'throwing'
            when lower(plate_appearance_description) like '%fielding error%'   then 'fielding'
            when lower(plate_appearance_description) like '%error%'            then 'unknown'
        end                                                     as error_type,
            -- Throwing vs fielding error; unknown when description is ambiguous

        case
            when lower(plate_appearance_description) like '%error by the pitcher%'     then 'pitcher'
            when lower(plate_appearance_description) like '%error by the catcher%'     then 'catcher'
            when lower(plate_appearance_description) like '%error by the first%'       then 'first_base'
            when lower(plate_appearance_description) like '%error by the second%'      then 'second_base'
            when lower(plate_appearance_description) like '%error by the third%'       then 'third_base'
            when lower(plate_appearance_description) like '%error by the shortstop%'   then 'shortstop'
            when lower(plate_appearance_description) like '%error by the left%'        then 'left_field'
            when lower(plate_appearance_description) like '%error by the center%'      then 'center_field'
            when lower(plate_appearance_description) like '%error by the right%'       then 'right_field'
            when lower(plate_appearance_description) like '%error%'                    then 'unknown'
        end                                                     as error_position,
            -- Which defensive position committed the error

        -- ── Run / win expectancy impact ───────────────────────────────────────────
        delta_run_exp,
        delta_pitcher_run_exp,
        delta_home_win_exp

    from source

)

select * from final