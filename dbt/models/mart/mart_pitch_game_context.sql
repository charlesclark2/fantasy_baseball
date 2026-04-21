-- =============================================================================
-- mart_pitch_game_context.sql
-- Grain: one row per pitch
-- Purpose: Game-level and situational context at the time of each pitch.
--          Covers game identifiers, score state, count/base state, and
--          win/run expectancy. Join key: pitch_sk.
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
            -- e.g. "1-2", "3-0" — pre-pitch count as a readable label

        case
            when balls = 3 and strikes = 2 then 'full'
            when balls = 3               then 'hitters'
            when strikes = 2             then 'pitchers'
            else 'neutral'
        end                                                     as count_leverage,
            -- Broad categorization of count advantage

        -- ── Base state ───────────────────────────────────────────────────────────
        case when runner_on_1b_id is not null then '1' else '-' end
            || case when runner_on_2b_id is not null then '2' else '-' end
            || case when runner_on_3b_id is not null then '3' else '-' end
                                                                as base_state,
            -- e.g. "1--" = runner on 1st only, "123" = bases loaded

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