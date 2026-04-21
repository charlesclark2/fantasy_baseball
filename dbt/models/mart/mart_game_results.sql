-- =============================================================================
-- mart_game_results.sql
-- Grain: one row per game (game_pk)
-- Purpose: Final result, score, teams, and context for every game.
--          Covers all game types (R=Regular Season, S=Spring, F/D/L/W=Playoffs).
--          Join key: game_pk.
-- =============================================================================

{{
    config(
        materialized     = 'incremental',
        unique_key       = 'game_pk',
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

-- Collapse pitch-level data to one row per game.
-- Final score = max post-pitch score (the score that persists after the last pitch).
-- Total innings = max inning reached.
game_level as (

    select
        game_pk,
        max(game_date)               as game_date,
        max(game_year)               as game_year,
        max(game_type)               as game_type,
        max(home_team)               as home_team,
        max(away_team)               as away_team,
        max(post_pitch_home_score)   as home_final_score,
        max(post_pitch_away_score)   as away_final_score,
        max(inning)                  as total_innings
    from source
    group by game_pk

),

ref_teams as (

    select * from {{ ref('ref_teams') }}

),

final as (

    select

        -- ── Keys ────────────────────────────────────────────────────────────────
        gl.game_pk,

        -- ── Game identifiers ─────────────────────────────────────────────────────
        gl.game_date,
        gl.game_year,
        gl.game_type,

        -- ── Home team ────────────────────────────────────────────────────────────
        gl.home_team,
        ht.team_id                   as home_team_id,
        ht.team_name                 as home_team_name,
        ht.league                    as home_league,
        ht.division                  as home_division,
        ht.league_division           as home_league_division,

        -- ── Away team ────────────────────────────────────────────────────────────
        gl.away_team,
        at.team_id                   as away_team_id,
        at.team_name                 as away_team_name,
        at.league                    as away_league,
        at.division                  as away_division,
        at.league_division           as away_league_division,

        -- ── Scores ───────────────────────────────────────────────────────────────
        gl.home_final_score,
        gl.away_final_score,
        gl.home_final_score - gl.away_final_score  as run_differential,
            -- Positive = home team advantage; negative = away team advantage

        -- ── Game context ─────────────────────────────────────────────────────────
        gl.total_innings,
        (gl.total_innings > 9)::boolean            as is_extra_innings,
        (gl.home_final_score = gl.away_final_score)::boolean as is_tie,

        -- ── Result ───────────────────────────────────────────────────────────────
        case
            when gl.home_final_score > gl.away_final_score then true
            when gl.home_final_score < gl.away_final_score then false
            else null  -- tie or suspended game
        end::boolean                               as home_team_won,

        case
            when gl.home_final_score > gl.away_final_score then gl.home_team
            when gl.home_final_score < gl.away_final_score then gl.away_team
            else null
        end                                        as winning_team,

        case
            when gl.home_final_score > gl.away_final_score then gl.away_team
            when gl.home_final_score < gl.away_final_score then gl.home_team
            else null
        end                                        as losing_team,

        -- ── Schedule context ─────────────────────────────────────────────────────
        (ht.league != at.league)::boolean          as is_interleague

    from game_level gl
    left join ref_teams ht on gl.home_team = ht.team_abbrev
    left join ref_teams at on gl.away_team = at.team_abbrev

)

select * from final
