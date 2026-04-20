-- =============================================================================
-- mart_pitch_pitcher_profile.sql
-- Grain: one row per pitch
-- Purpose: Pitcher identity and usage context at the time of each pitch.
--          Name resolved via ref_players join on pitcher_id. Join key: pitch_sk.
-- =============================================================================

{{
    config(
        materialized = 'incremental',
        unique_key   = 'pitch_sk',
        incremental_strategy = 'merge'
    )
}}

with

pitches as (

    select * from {{ ref('stg_batter_pitches') }}

    {% if is_incremental() %}
        where game_date > (select max(game_date) from {{ this }})
    {% endif %}

),

players as (

    select
        mlb_bam_id,
        first_name,
        last_name,
        player_name,
        mlb_played_first::integer   as mlb_played_first,
        mlb_played_last::integer    as mlb_played_last
    from {{ source('savant', 'ref_players') }}

),

final as (

    select

        -- ── Keys ────────────────────────────────────────────────────────────────
        p.pitch_sk,
        p.game_pk,
        p.game_date,
        p.game_year,
        p.at_bat_number,
        p.pitch_number,

        -- ── Pitcher identity ─────────────────────────────────────────────────────
        p.pitcher_id,
        r.first_name                                            as pitcher_first_name,
        r.last_name                                             as pitcher_last_name,
        r.player_name                                           as pitcher_name,
            -- Display name from ref_players; falls back to null if ID not found

        p.pitcher_hand,
        p.pitcher_age,
        p.pitcher_age_legacy,

        -- ── Pitcher usage / fatigue context ──────────────────────────────────────
        p.pitcher_times_thru_order,
        p.pitcher_days_since_prev_game,
        p.pitcher_days_until_next_game,

        case
            when p.pitcher_days_since_prev_game is null then 'unknown'
            when p.pitcher_days_since_prev_game <= 1    then 'back_to_back'
            when p.pitcher_days_since_prev_game <= 4    then 'normal_rest'
            when p.pitcher_days_since_prev_game <= 7    then 'extra_rest'
            else 'extended_rest'
        end                                                     as pitcher_rest_bucket

    from pitches     p
    left join players r
        on p.pitcher_id = r.mlb_bam_id

)

select * from final