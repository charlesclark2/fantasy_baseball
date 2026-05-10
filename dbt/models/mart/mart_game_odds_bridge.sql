-- =============================================================================
-- mart_game_odds_bridge.sql
-- Grain: one row per game_pk
-- Purpose: Bridge table linking every game in mart_game_results to its
--          corresponding odds event_id(s) from The Odds API and/or Parlay API.
--          Enables downstream models to join game outcomes with pre-game odds.
--
--          Two source-specific columns preserve full audit trail:
--            odds_api_event_id   — from mart_odds_events (Odds API; 2021–2025)
--            parlay_api_event_id — from stg_parlayapi_odds (Parlay API; 2026+)
--          The coalesced event_id column (Parlay API preferred) provides a
--          single join key for all downstream models, automatically routing to
--          Parlay API data for 2026 games and Odds API data for historical games.
--
--          Priority by era:
--            2021–2025 historical:  odds_api_event_id only
--            2026 overlap period:   both present; event_id = parlay_api_event_id
--            2026 post-cutover:     parlay_api_event_id only
--
--          Join logic (both sources):
--            game_date      = commence_date (UTC date for Odds API; UTC date
--                             from 19:00:00Z placeholder for Parlay API)
--            home_team_name = odds home_team (after normalization)
--            away_team_name = odds away_team (after normalization)
--
--          Team name normalization applied to both sources:
--            "Cleveland Indians"  → "Cleveland Guardians"  (2021 Odds API name)
--            "Oakland Athletics"  → "Athletics"            (Odds API 2021-2025 name)
--          Parlay API live data (2026+) should already use current names, but
--          the mapping is applied defensively to both sides.
--
--          Doubleheader limitation: Parlay API collapses both games of a DH
--          into one event_id. The bridge maps that event_id to whichever
--          game_pk matches first; the second DH game_pk will have
--          parlay_api_event_id = null. See stg_parlayapi_odds.doubleheader_ambiguous.
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

-- ── Odds API events (2021–2025 historical) ────────────────────────────────────
-- Normalize historical franchise names to match Stats API canonical names.

odds_events_normalized as (

    select
        event_id,
        commence_date,
        case home_team
            when 'Cleveland Indians' then 'Cleveland Guardians'
            when 'Oakland Athletics' then 'Athletics'
            else home_team
        end as home_team,
        case away_team
            when 'Cleveland Indians' then 'Cleveland Guardians'
            when 'Oakland Athletics' then 'Athletics'
            else away_team
        end as away_team,
        ingestion_ts
    from {{ ref('mart_odds_events') }}

),

-- Deduplicate Odds API to one canonical event_id per matchup per date.
-- The API occasionally returns different event_ids for the same game
-- across separate ingestion runs; pick the most recently ingested one.
odds_events_deduped as (

    select
        event_id,
        commence_date,
        home_team,
        away_team,
        row_number() over (
            partition by commence_date, home_team, away_team
            order by ingestion_ts desc
        ) as _rn
    from odds_events_normalized

),

odds_events as (

    select
        event_id          as odds_api_event_id,
        commence_date,
        home_team,
        away_team
    from odds_events_deduped
    where _rn = 1

),

-- ── Parlay API events (2026+) ─────────────────────────────────────────────────
-- Sourced directly from stg_parlayapi_odds — every odds row has event_id,
-- game_date, home_team, away_team. No separate events staging model needed.
-- Apply same franchise-name normalization defensively.

parlay_events_normalized as (

    select
        event_id,
        game_date,
        case home_team
            when 'Cleveland Indians' then 'Cleveland Guardians'
            when 'Oakland Athletics' then 'Athletics'
            else home_team
        end as home_team,
        case away_team
            when 'Cleveland Indians' then 'Cleveland Guardians'
            when 'Oakland Athletics' then 'Athletics'
            else away_team
        end as away_team,
        ingestion_ts
    from {{ ref('stg_parlayapi_odds') }}

),

-- Deduplicate Parlay API to one canonical event_id per matchup per date.
parlay_events_deduped as (

    select
        event_id,
        game_date,
        home_team,
        away_team,
        row_number() over (
            partition by game_date, home_team, away_team
            order by ingestion_ts desc
        ) as _rn
    from parlay_events_normalized

),

parlay_events as (

    select
        event_id          as parlay_api_event_id,
        game_date,
        home_team,
        away_team
    from parlay_events_deduped
    where _rn = 1

)

select

    -- ── Game keys ─────────────────────────────────────────────────────────────
    gr.game_pk,
    gr.game_date,
    gr.game_type,

    -- ── Teams (from game results; authoritative abbreviation + full name) ─────
    gr.home_team                                                    as home_team_abbrev,
    gr.home_team_name,
    gr.away_team                                                    as away_team_abbrev,
    gr.away_team_name,

    -- ── Source-specific event keys ────────────────────────────────────────────
    oe.odds_api_event_id,
    pe.parlay_api_event_id,

    -- ── Coalesced event key: Parlay API preferred, Odds API as fallback ───────
    -- Use this column for all downstream joins to mart_odds_outcomes.
    -- Routes automatically: Parlay API for 2026+ games, Odds API for 2021–2025.
    coalesce(pe.parlay_api_event_id, oe.odds_api_event_id)         as event_id,

    -- ── Match quality ─────────────────────────────────────────────────────────
    (coalesce(pe.parlay_api_event_id, oe.odds_api_event_id)
     is not null)::boolean                                          as has_odds

from game_results gr
left join odds_events oe
    on  gr.game_date      = oe.commence_date
    and gr.home_team_name = oe.home_team
    and gr.away_team_name = oe.away_team
left join parlay_events pe
    on  gr.game_date      = pe.game_date
    and gr.home_team_name = pe.home_team
    and gr.away_team_name = pe.away_team
