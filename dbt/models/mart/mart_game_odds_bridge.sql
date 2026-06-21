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
--          Join logic (both sources) — A1.9:
--            game_date    = commence_date / game_date
--            home_team_id = odds home_team resolved via dim_team_name_lookup
--            away_team_id = odds away_team resolved via dim_team_name_lookup
--          Every name (Stats API, Odds API, Parlay API) is resolved to a team_id
--          through the canonical team dimension, so the join is immune to feed
--          name drift (e.g. Stats API "Athletics" vs Odds API "Oakland
--          Athletics", "Cleveland Indians" → Guardians). New variants are handled
--          by adding a row to the ref_team_aliases seed — no model change.
--          For DH games, QUALIFY on Stats API game_number distinguishes G1 from G2.
--
--          Doubleheader handling: Parlay API fixed the DH collapse bug (2026-05-11).
--          Both DH games now return distinct events with real commence_time values.
--          The dedup partitions on date_trunc('hour', commence_time) to keep both
--          DH game slots separate. QUALIFY routes each game_pk to the correct slot
--          using Stats API game_number: game_number=1 → earliest non-placeholder event
--          (game_slot=1); game_number=2 → next event (game_slot=2). Time-proximity
--          cannot be used because Stats API scheduled times for DH Game 2 game_pks
--          reflect the original postponement time, not the actual DH start time.
-- =============================================================================

{{
    config(
        materialized = 'table'
    )
}}

with team_lookup as (

    -- A1.9 canonical resolver: any feed/Stats API name -> team_id.
    -- Consumer contract: lower(regexp_replace(trim(name), '^G[12] ', '')).
    select name_lower, team_id
    from {{ ref('dim_team_name_lookup') }}

),

game_results as (

    select
        gr.game_pk,
        gr.game_date,
        gr.game_type,
        gr.home_team,
        gr.home_team_name,
        gr.away_team,
        gr.away_team_name,
        h.team_id as home_team_id,
        a.team_id as away_team_id
    -- A1.11 — spine on mart_game_spine so today's scheduled games get an odds
    -- bridge row too (mart_game_results is completed-games only). Historical
    -- rows are unchanged.
    from {{ ref('mart_game_spine') }} gr
    left join team_lookup h
        on h.name_lower = lower(regexp_replace(trim(gr.home_team_name), '^G[12] ', ''))
    left join team_lookup a
        on a.name_lower = lower(regexp_replace(trim(gr.away_team_name), '^G[12] ', ''))

),

-- ── Odds API events (2021–2025 historical) ────────────────────────────────────
-- Resolve historical franchise names to team_id via the canonical lookup
-- (handles "Cleveland Indians" → Guardians, "Oakland Athletics" → Athletics).

odds_events_resolved as (

    select
        oe.event_id,
        oe.commence_date,
        h.team_id as home_team_id,
        a.team_id as away_team_id,
        oe.ingestion_ts
    from {{ ref('mart_odds_events') }} oe
    left join team_lookup h
        on h.name_lower = lower(regexp_replace(trim(oe.home_team), '^G[12] ', ''))
    left join team_lookup a
        on a.name_lower = lower(regexp_replace(trim(oe.away_team), '^G[12] ', ''))

),

-- Deduplicate Odds API to one canonical event_id per matchup per date.
-- The API occasionally returns different event_ids for the same game
-- across separate ingestion runs; pick the most recently ingested one.
odds_events_deduped as (

    select
        event_id,
        commence_date,
        home_team_id,
        away_team_id,
        row_number() over (
            partition by commence_date, home_team_id, away_team_id
            order by ingestion_ts desc
        ) as _rn
    from odds_events_resolved

),

odds_events as (

    select
        event_id          as odds_api_event_id,
        commence_date,
        home_team_id,
        away_team_id
    from odds_events_deduped
    where _rn = 1

)

-- E11.6 (2026-06-21): Parlay API permanently decommissioned. parlay_api_event_id
-- is preserved as a NULL column so downstream consumers (mart_derivative_closes)
-- compile without changes; their OR join branch simply never matches.

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
    gr.home_team_id,
    gr.away_team_id,

    -- ── Source-specific event keys ────────────────────────────────────────────
    oe.odds_api_event_id,
    -- parlay_api_event_id: NULL since E11.6 decommission (2026-06-21); preserved for
    -- schema compatibility with mart_derivative_closes (OR join branch never fires).
    null::varchar                                                   as parlay_api_event_id,

    -- ── Coalesced event key: Odds API only post-E11.6 ────────────────────────
    oe.odds_api_event_id                                            as event_id,

    -- ── Match quality ─────────────────────────────────────────────────────────
    (oe.odds_api_event_id is not null)::boolean                     as has_odds

from game_results gr
left join odds_events oe
    on  gr.game_date    = oe.commence_date
    and gr.home_team_id = oe.home_team_id
    and gr.away_team_id = oe.away_team_id
