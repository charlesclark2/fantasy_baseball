-- =============================================================================
-- mart_game_results.sql
-- Grain: one row per game (game_pk)
-- Purpose: Final result, score, teams, and context for every game.
--          Covers all game types (R=Regular Season, S=Spring, F/D/L/W=Playoffs).
--          Join key: game_pk.
-- =============================================================================

-- E11.1-W5 dual-branch lakehouse model. The DuckDB branch (built by
-- run_w1_lakehouse.py → S3 parquet) reads the W1 stg_batter_pitches + the W3pre
-- stg_statsapi_games + the ref_teams seed (all registered as DuckDB views). The
-- Snowflake branch is a thin view over the lakehouse_ext external table. This was
-- an `incremental`/merge table pre-W5; the lakehouse build is a full rebuild each
-- run. game_date is cast ::date so the parquet carries DATE (matching the retired
-- Snowflake mart_game_results.GAME_DATE DATE type) — the spine + every team/game
-- mart inherits a real DATE for its RANGE-interval windows.

{{
    config(
        materialized = 'view',
        tags         = ['w5_lakehouse']
    )
}}

{% if target.name == 'duckdb' %}

with

source as (

    select * from stg_batter_pitches

),

-- Collapse pitch-level data to one row per game.
-- Final score = max post-pitch score (the score that persists after the last pitch).
-- Total innings = max inning reached.
game_level as (

    select
        game_pk,
        max(game_date::date)         as game_date,
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

team_ref as (

    select * from ref_teams

),

venue_lookup as (

    select
        game_pk,
        venue_id,
        venue_name
    from stg_statsapi_games

),

final as (

    select

        -- ── Keys ────────────────────────────────────────────────────────────────
        gl.game_pk,

        -- ── Game identifiers ─────────────────────────────────────────────────────
        gl.game_date,
        gl.game_year,
        gl.game_type,

        -- ── Venue ─────────────────────────────────────────────────────────────────
        vl.venue_id,
        vl.venue_name,

        -- ── Home team ────────────────────────────────────────────────────────────
        gl.home_team,
        ht.team_id                   as home_team_id,
        ht.team_name                 as home_team_name,
        ht.league                    as home_league,
        ht.division                  as home_division,
        ht.league_division           as home_league_division,

        -- ── Away team ────────────────────────────────────────────────────────────
        gl.away_team,
        at_.team_id                   as away_team_id,
        at_.team_name                 as away_team_name,
        at_.league                    as away_league,
        at_.division                  as away_division,
        at_.league_division           as away_league_division,

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
        (ht.league != at_.league)::boolean          as is_interleague

    from game_level gl
    left join venue_lookup vl on gl.game_pk = vl.game_pk
    left join team_ref ht on gl.home_team = ht.team_abbrev
    left join team_ref at_ on gl.away_team = at_.team_abbrev

)

select * from final

{% else %}

select * from baseball_data.lakehouse_ext.mart_game_results

{% endif %}
