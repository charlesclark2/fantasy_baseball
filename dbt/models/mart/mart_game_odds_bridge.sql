-- =============================================================================
-- mart_game_odds_bridge.sql
-- Grain: one row per game_pk
-- Purpose: Bridge table linking every game in mart_game_results to its
--          corresponding event in mart_odds_events (if one exists).
--          Enables downstream models and analyses to combine game outcomes
--          with pre-game betting odds.
--
--          Join logic:
--            game_date = commence_date
--            home_team_name = odds home_team  (full team name)
--            away_team_name = odds away_team  (full team name)
--
--          All game_pk rows are preserved; event_id is null when no odds
--          event was ingested for that game (e.g. historical games predating
--          odds ingestion).
--
--          mart_odds_events can carry multiple event_ids for the same
--          matchup when the API returns different IDs across ingestion runs.
--          The odds side is pre-deduplicated to one row per
--          (commence_date, home_team, away_team) — keeping the latest
--          ingestion_ts — before joining, preserving game_pk grain.
-- =============================================================================

{{
    config(
        materialized = 'table'
    )
}}

with game_results as (

    select
        game_pk,
        game_date,
        game_type,
        home_team,
        home_team_name,
        away_team,
        away_team_name
    from {{ ref('mart_game_results') }}

),

-- Deduplicate odds events to one canonical row per matchup per date.
-- The API occasionally returns different event_ids for the same game
-- across separate ingestion runs; pick the most recently ingested one.
odds_events_deduped as (

    select
        event_id,
        commence_date,
        home_team,
        away_team,
        ingestion_ts,
        row_number() over (
            partition by commence_date, home_team, away_team
            order by ingestion_ts desc
        ) as _rn
    from {{ ref('mart_odds_events') }}

),

odds_events as (

    select
        event_id,
        commence_date,
        home_team,
        away_team
    from odds_events_deduped
    where _rn = 1

)

select

    -- ── Game keys ─────────────────────────────────────────────────────────────
    gr.game_pk,
    gr.game_date,
    gr.game_type,

    -- ── Teams (from game results; authoritative abbreviation + full name) ─────
    gr.home_team                                           as home_team_abbrev,
    gr.home_team_name,
    gr.away_team                                           as away_team_abbrev,
    gr.away_team_name,

    -- ── Odds event key (null when no odds exist for this game) ────────────────
    oe.event_id,

    -- ── Match quality ─────────────────────────────────────────────────────────
    (oe.event_id is not null)::boolean                     as has_odds

from game_results gr
left join odds_events oe
    on  gr.game_date      = oe.commence_date
    and gr.home_team_name = oe.home_team
    and gr.away_team_name = oe.away_team
