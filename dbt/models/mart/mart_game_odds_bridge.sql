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
--          Doubleheader handling (restored post-E11.6): The Odds API returns two
--          events for a DH with distinct commence_times. odds_events assigns a
--          game_slot (1=earliest, 2=next) per (date, home, away) ordered by
--          commence_time asc. The final join adds game_number = game_slot so each
--          Stats API game_pk routes to its correct event: game_number=1 → G1 event,
--          game_number=2 → G2 event. For regular games only one event exists so
--          game_slot=1 always matches game_number=1.
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
        a.team_id as away_team_id,
        -- game_number for DH slot routing (1 for G1/regular, 2 for G2).
        -- COALESCE to 1: historical completed games may predate stg_statsapi_games
        -- coverage; all non-DH games have game_number=1 so slot-1 is always correct.
        coalesce(sg.game_number, 1) as game_number
    -- A1.11 — spine on mart_game_spine so today's scheduled games get an odds
    -- bridge row too (mart_game_results is completed-games only). Historical
    -- rows are unchanged.
    from {{ ref('mart_game_spine') }} gr
    left join {{ ref('stg_statsapi_games') }} sg on sg.game_pk = gr.game_pk
    left join team_lookup h
        on h.name_lower = lower(regexp_replace(trim(gr.home_team_name), '^G[12] ', ''))
    left join team_lookup a
        on a.name_lower = lower(regexp_replace(trim(gr.away_team_name), '^G[12] ', ''))

),

-- ── Odds API events (all eras) ────────────────────────────────────────────────
-- INC-2 fix (2026-06-22): resolve events from mart_odds_outcomes (the live /odds
-- feed) instead of mart_odds_events (the /events feed). The /events ingest
-- (stg_oddsapi_events) silently stalled on 2026-06-04, freezing mart_odds_events at
-- commence_date 2026-06-05; every 2026 game after that resolved to a NULL event_id
-- → has_odds=false → null odds throughout feature_pregame_* and the feature_store
-- serving path. mart_odds_outcomes carries the same Odds API event_id + commence_date
-- + team names (all eras), stays live with /odds, and shares the exact event_id space
-- that mart_odds_consensus joins on downstream — so this is both the live fix and a
-- strictly tighter join key. Resolve franchise names to team_id via the canonical
-- lookup (handles "Cleveland Indians" → Guardians, "Oakland Athletics" → Athletics).

odds_events_resolved as (

    -- One row per event_id: collapse multiple ingestion snapshots of the same
    -- event, keeping commence_time (same for all rows of an event_id) and the
    -- most-recent ingestion_ts for dedup ordering below.
    select
        o.event_id,
        o.commence_date,
        o.commence_time,
        h.team_id as home_team_id,
        a.team_id as away_team_id,
        max(o.ingestion_ts) as ingestion_ts
    from {{ ref('mart_odds_outcomes') }} o
    left join team_lookup h
        on h.name_lower = lower(regexp_replace(trim(o.home_team), '^G[12] ', ''))
    left join team_lookup a
        on a.name_lower = lower(regexp_replace(trim(o.away_team), '^G[12] ', ''))
    group by 1, 2, 3, 4, 5

),

-- Assign a game_slot per (date, home_team, away_team) ordered by commence_time.
-- For regular games there is exactly one event → game_slot = 1.
-- For doubleheaders the Odds API returns two events with distinct commence_times:
--   game_slot 1 = earliest event (G1)
--   game_slot 2 = next event     (G2)
-- The final join routes each Stats API game_pk to its correct slot via game_number.
odds_events as (

    select
        event_id          as odds_api_event_id,
        commence_date,
        home_team_id,
        away_team_id,
        row_number() over (
            partition by commence_date, home_team_id, away_team_id
            order by commence_time asc
        ) as game_slot
    from odds_events_resolved

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
    and gr.game_number  = oe.game_slot
