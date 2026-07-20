-- =============================================================================
-- mart_pitch_game_context.sql  (E11.1-W1d decommission)
-- Grain: one row per pitch
-- Purpose: Game-level and situational context at the time of each pitch.
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
        at_bat_number,
        pitch_number,
        batter_id,
        pitcher_id,

        -- ── Game identifiers ─────────────────────────────────────────────────────
        game_date,
        game_year,
        game_type,
        home_team,
        away_team,

        -- ── Inning & outs ────────────────────────────────────────────────────────
        inning,
        inning_half,
        outs_when_up,

        -- ── Count state ──────────────────────────────────────────────────────────
        balls,
        strikes,
        balls::varchar || '-' || strikes::varchar               as count_state,

        case
            when balls = 3 and strikes = 2 then 'full'
            when balls = 3               then 'hitters'
            when strikes = 2             then 'pitchers'
            else 'neutral'
        end                                                     as count_leverage,

        -- ── Base state ───────────────────────────────────────────────────────────
        case when runner_on_1b_id is not null then '1' else '-' end
            || case when runner_on_2b_id is not null then '2' else '-' end
            || case when runner_on_3b_id is not null then '3' else '-' end
                                                                as base_state,

        (runner_on_1b_id is not null)::boolean                  as runner_on_1b,
        (runner_on_2b_id is not null)::boolean                  as runner_on_2b,
        (runner_on_3b_id is not null)::boolean                  as runner_on_3b,

        case
            when runner_on_1b_id is not null
              or runner_on_2b_id is not null
              or runner_on_3b_id is not null
            then true else false
        end                                                     as runners_on_base,

        -- ── Score context ─────────────────────────────────────────────────────────
        pre_pitch_home_score,
        pre_pitch_away_score,
        pre_pitch_bat_score,
        pre_pitch_fld_score,
        post_pitch_home_score,
        post_pitch_away_score,
        post_pitch_bat_score,
        post_pitch_fld_score,
        home_score_diff,
        bat_score_diff,

        -- ── Win / run expectancy ─────────────────────────────────────────────────
        pre_pitch_home_win_exp,
        pre_pitch_bat_win_exp,
        delta_home_win_exp,
        delta_run_exp,
        delta_pitcher_run_exp

    from source

)

select * from final

{% else %}

select * from baseball_data.lakehouse_ext.mart_pitch_game_context

{% endif %}
