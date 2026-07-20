-- =============================================================================
-- mart_pitch_play_event.sql  (E11.1-W1d decommission)
-- Grain: one row per pitch
-- Purpose: What happened on the pitch and resulting plate appearance outcome.
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

        (pitch_description = 'called_strike')::boolean          as is_called_strike,
        (pitch_description in ('ball', 'blocked_ball',
            'pitchout', 'intent_ball'))::boolean                as is_called_ball,

        -- ── Terminal PA event flags ───────────────────────────────────────────────
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
        coalesce(
            lower(plate_appearance_description) like '%error%', false
        )                                                       as error_on_play,

        case
            when lower(plate_appearance_description) like '%throwing error%'   then 'throwing'
            when lower(plate_appearance_description) like '%fielding error%'   then 'fielding'
            when lower(plate_appearance_description) like '%error%'            then 'unknown'
        end                                                     as error_type,

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

        -- ── Run / win expectancy impact ───────────────────────────────────────────
        delta_run_exp,
        delta_pitcher_run_exp,
        delta_home_win_exp,

        -- ── wOBA (PA outcome; non-null only on the terminal pitch of each PA) ──────
        -- E11.1-W3pre woba-DDL fix: these three columns were DROPPED from this
        -- branch at W1d (2026-06-25) but were still DECLARED in the lakehouse_ext
        -- external-table DDL (scripts/ddl/w1_external_tables.sql) → the Snowflake
        -- view read NULL for them, zeroing every downstream reader of
        -- ppe.woba_value / ppe.woba_denom / ppe.xwoba:
        --   mart_batter_woba_vs_cluster, mart_batter_archetype_vs_pitcher_cluster,
        --   mart_batter_profile_summary  (mart_pitcher_batter_history was repointed
        --   to stg_batter_pitches in W2 and is unaffected).
        -- Re-emitting them from the source (stg_batter_pitches carries real woba)
        -- makes the DDL columns correct again with NO reader or DDL change. Summing
        -- across pitch rows == summing across PAs (non-terminal pitches are NULL).
        woba_value,
        woba_denom,
        xwoba

    from source

)

select * from final

{% else %}

select * from baseball_data.lakehouse_ext.mart_pitch_play_event

{% endif %}
