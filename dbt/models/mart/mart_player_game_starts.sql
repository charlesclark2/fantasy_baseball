-- =============================================================================
-- mart_player_game_starts.sql   (Story 33.1 Task 1a)
-- Grain: one row per (game_pk, team, side, player_id) — a CONFIRMED STARTER
--        (a player who appeared in the posted batting lineup for that game).
-- Purpose: the leakage-safe START FACT for the playing-time probability model
--          (Story 33.1) and the expected-lineup feature family (33.3). The
--          team-game spine (mart_game_spine, unpivoted home/away) joined to the
--          posted lineups (stg_statsapi_lineups, where one row = one starter).
--
-- This fact is INTENTIONALLY actual-starts-only (no did_start=0 rows). The
-- candidate panel + the did_start∈{0,1} label + rolling start-rates are built
-- downstream in build_playing_time_dataset.py, which applies the strict
--   prior.official_date < game.official_date   (leakage guard)
-- when counting a player's recent starts. `official_date` is the canonical,
-- leakage-safe game date (same key the lineup feature model uses).
--
-- Scheduled (today's) games have no posted lineup yet, so they produce no rows
-- here — that is correct: the serving path predicts today's starters from each
-- team's RECENT starts in this fact, it does not read today's (unknown) lineup.
-- Coverage: 2015+ (Statcast-era lineups).
-- =============================================================================

{{ config(materialized='table') }}

with spine as (

    select
        game_pk,
        game_date::date as game_date,
        game_year,
        home_team,
        away_team
    from {{ ref('mart_game_spine') }}

),

-- one row per (game_pk, team, side) with the opponent team carried for the
-- downstream opponent-starter-handedness join.
team_games as (

    select game_pk, game_date, game_year, home_team as team, away_team as opp_team, 'home' as side from spine
    union all
    select game_pk, game_date, game_year, away_team as team, home_team as opp_team, 'away' as side from spine

),

starters as (

    -- one row per starter (stg_statsapi_lineups is already deduped to the latest
    -- ingest per game_pk × side × batting_order).
    select
        game_pk,
        home_away      as side,
        official_date,
        player_id,
        full_name,
        batting_order,
        position_code
    from {{ ref('stg_statsapi_lineups') }}

)

select
    tg.game_pk,
    s.official_date,
    tg.game_year,
    tg.team,
    tg.opp_team,
    tg.side,
    s.player_id,
    s.full_name,
    s.batting_order,
    s.position_code,
    -- pitchers in the batting order (pre-2022 NL, no-DH) — flagged so the
    -- expected-OFFENSE aggregates (33.3) can down-weight/exclude them.
    (s.position_code = '1')::boolean as is_pitcher_slot
from team_games tg
join starters s
    on s.game_pk = tg.game_pk
   and s.side    = tg.side
