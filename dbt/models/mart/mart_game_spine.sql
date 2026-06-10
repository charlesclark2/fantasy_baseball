-- =============================================================================
-- mart_game_spine.sql   (Epic A1.11)
-- Grain: one row per game_pk (regular + all game types from the two sources).
-- Purpose: the single forward-looking game spine for the pregame feature
--          pipeline. UNION of
--            (1) COMPLETED games — pass-through of mart_game_results (pitch-
--                derived; the authoritative historical record), and
--            (2) SCHEDULED-not-yet-played games — from stg_statsapi_games
--                (forward-looking schedule), for game_pks not yet in results.
--
--          mart_game_results only ever contains games that have been played
--          (its source is pitch-by-pitch data), so feature marts that spine on
--          it never see today's games and live predictions fall back to the
--          intraday assembly (Epic A1.8). Spining on THIS model instead lets the
--          feature store hold today's not-yet-played games with full features.
--
-- NON-DESTRUCTIVE CONTRACT:
--   * The completed branch selects mart_game_results columns unchanged, so any
--     consumer that swaps `mart_game_results` → `mart_game_spine` produces
--     byte-for-byte identical rows for every historical game.
--   * The scheduled branch only ADDS game_pks absent from mart_game_results.
--     Once a scheduled game is played its pitches land in mart_game_results and
--     the NOT IN filter moves it to the completed branch automatically — so a
--     game is never double-counted.
--   * Outcome columns (scores) are NULL for scheduled games; downstream label
--     joins therefore yield NULL labels for today (correct — no result yet).
--
-- Team abbreviations for scheduled games are resolved through the canonical
-- dim_team_name_lookup (Epic A1.9), so the A's / relocated-franchise name drift
-- is handled the same way everywhere.
-- =============================================================================

{{ config(materialized='view') }}

with team_lookup as (

    select name_lower, team_id, canonical_abbrev
    from {{ ref('dim_team_name_lookup') }}

),

completed as (

    -- Pass-through of the authoritative completed-game record. Column list is
    -- the spine contract; values are unchanged from mart_game_results.
    select
        game_pk,
        game_date,
        game_year,
        game_type,
        home_team,
        away_team,
        home_team_id,
        away_team_id,
        home_team_name,
        away_team_name,
        venue_id,
        venue_name,
        home_final_score,
        away_final_score,
        false                              as is_scheduled
    from {{ ref('mart_game_results') }}

),

scheduled as (

    -- Forward-looking games not yet in the completed record. Abbreviations
    -- resolved to the canonical form via the A1.9 team dimension.
    select
        g.game_pk,
        g.official_date::timestamp_ntz     as game_date,
        year(g.official_date)::integer     as game_year,
        g.game_type,
        h.canonical_abbrev                 as home_team,
        a.canonical_abbrev                 as away_team,
        g.home_team_id,
        g.away_team_id,
        g.home_team_name,
        g.away_team_name,
        g.venue_id,
        g.venue_name,
        cast(null as integer)              as home_final_score,
        cast(null as integer)              as away_final_score,
        true                               as is_scheduled
    from {{ ref('stg_statsapi_games') }} g
    left join team_lookup h
        on h.name_lower = lower(regexp_replace(trim(g.home_team_name), '^G[12] ', ''))
    left join team_lookup a
        on a.name_lower = lower(regexp_replace(trim(g.away_team_name), '^G[12] ', ''))
    where g.game_type = 'R'
      and g.game_pk not in (select game_pk from {{ ref('mart_game_results') }})
      -- Tight forward window: today (with a 1-day back/2-day fwd cushion for
      -- timezones + next-day pre-scoring). This keeps the spine lean AND means
      -- the scheduled branch NEVER adds a row for a historical date, so every
      -- past game's output is byte-for-byte identical to the old mart_game_results
      -- spine. (A postponed/cancelled game that was never played simply ages out
      -- of the window instead of lingering as a phantom "scheduled" row.)
      and g.official_date >= dateadd('day', -1, current_date)
      and g.official_date <= dateadd('day',  2, current_date)
      -- Exclude games the schedule already marks finished (results lag only).
      and coalesce(g.abstract_game_state, '') not in ('Final', 'Completed Early')

)

select * from completed
union all
select * from scheduled
