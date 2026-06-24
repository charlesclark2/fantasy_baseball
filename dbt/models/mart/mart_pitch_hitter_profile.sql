-- =============================================================================
-- mart_pitch_hitter_profile.sql
-- Grain: one row per pitch
-- Purpose: Batter identity and at-bat context at the time of each pitch.
--          Name resolved via ref_players join on batter_id.
--          Runner IDs included for baserunning context. Join key: pitch_sk.
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
    from {{ ref('stg_ref_players') }}

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

        -- ── Batter identity ──────────────────────────────────────────────────────
        p.batter_id,
        r.first_name                                            as batter_first_name,
        r.last_name                                             as batter_last_name,
        r.player_name                                           as batter_name,
            -- Display name from ref_players; falls back to null if ID not found

        p.batter_hand,
        p.batter_age,
        p.batter_age_legacy,

        -- ── Matchup handedness ───────────────────────────────────────────────────
        p.pitcher_hand,
        case
            when p.batter_hand = p.pitcher_hand then 'same_hand'
            else 'opposite_hand'
        end                                                     as matchup_handedness,
            -- Same-hand (e.g. RHP vs RHB) vs opposite-hand matchup

        -- ── Batter in-game context ───────────────────────────────────────────────
        p.batter_prior_pas_this_game,
        p.batter_days_since_prev_game,
        p.batter_days_until_next_game,

        -- ── Baserunners at time of pitch ─────────────────────────────────────────
        -- IDs included for potential downstream join to a players dim
        p.runner_on_1b_id,
        p.runner_on_2b_id,
        p.runner_on_3b_id

    from pitches     p
    left join players r
        on p.batter_id = r.mlb_bam_id

)

select * from final