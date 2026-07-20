-- =============================================================================
-- mart_pitch_hitter_profile.sql  (E11.1-W1d decommission)
-- Grain: one row per pitch
-- Purpose: Batter identity and at-bat context at the time of each pitch.
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

pitches as (

    select * from stg_batter_pitches

),

players as (

    select
        mlb_bam_id,
        first_name,
        last_name,
        player_name,
        mlb_played_first::integer   as mlb_played_first,
        mlb_played_last::integer    as mlb_played_last
    from stg_ref_players

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

        p.batter_hand,
        p.batter_age,
        p.batter_age_legacy,

        -- ── Matchup handedness ───────────────────────────────────────────────────
        p.pitcher_hand,
        case
            when p.batter_hand = p.pitcher_hand then 'same_hand'
            else 'opposite_hand'
        end                                                     as matchup_handedness,

        -- ── Batter in-game context ───────────────────────────────────────────────
        p.batter_prior_pas_this_game,
        p.batter_days_since_prev_game,
        p.batter_days_until_next_game,

        -- ── Baserunners at time of pitch ─────────────────────────────────────────
        p.runner_on_1b_id,
        p.runner_on_2b_id,
        p.runner_on_3b_id

    from pitches     p
    left join players r
        on p.batter_id = r.mlb_bam_id

)

select * from final

{% else %}

select * from baseball_data.lakehouse_ext.mart_pitch_hitter_profile

{% endif %}
