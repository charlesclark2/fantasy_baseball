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
    from {{ ref('mart_game_results') }} gr
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

),

-- ── Parlay API events (2026+) ─────────────────────────────────────────────────
-- Sourced directly from stg_parlayapi_odds — every odds row has event_id,
-- game_date, home_team, away_team. No separate events staging model needed.
-- Resolve to team_id via the same canonical lookup.

parlay_events_resolved as (

    select
        po.event_id,
        po.game_date,
        po.commence_time,
        h.team_id as home_team_id,
        a.team_id as away_team_id,
        po.ingestion_ts
    from {{ ref('stg_parlayapi_odds') }} po
    left join team_lookup h
        on h.name_lower = lower(regexp_replace(trim(po.home_team), '^G[12] ', ''))
    left join team_lookup a
        on a.name_lower = lower(regexp_replace(trim(po.away_team), '^G[12] ', ''))

),

-- Deduplicate Parlay API to one canonical event_id per matchup per date.
-- Partition includes date_trunc('hour', commence_time) so both DH game slots
-- survive as distinct rows rather than being collapsed to one.
parlay_events_deduped as (

    select
        event_id,
        game_date,
        commence_time,
        home_team_id,
        away_team_id,
        row_number() over (
            partition by game_date, home_team_id, away_team_id, date_trunc('hour', commence_time)
            order by ingestion_ts desc
        ) as _rn
    from parlay_events_resolved

),

parlay_events as (

    select
        event_id          as parlay_api_event_id,
        game_date,
        commence_time,
        home_team_id,
        away_team_id
    from parlay_events_deduped
    where _rn = 1

),

-- Assign a game_slot rank to each Parlay event within its matchup/date.
-- Non-19:00 UTC events are ranked first by commence_time (these are real DH game
-- starts with suffixed event_ids added by the 2026-05-11 Parlay API fix).
-- 19:00 UTC events (placeholders for non-DH games, or old DH collapse artifacts)
-- rank last. For a single-game matchup only one event exists and gets slot=1.
-- For DH matchups: slot 1 = earliest real start (Game 1), slot 2 = later (Game 2).
parlay_events_ranked as (

    select
        parlay_api_event_id,
        game_date,
        commence_time,
        home_team_id,
        away_team_id,
        row_number() over (
            partition by game_date, home_team_id, away_team_id
            order by
                case when time(commence_time) = '19:00:00'::time then 1 else 0 end asc,
                commence_time asc
        ) as game_slot
    from parlay_events

),

-- Stats API game_number (1 or 2) and double_header flag for DH routing.
-- game_number is reliable even when the scheduled game_date/time is stale
-- (postponed games replayed as DH makeups keep their original scheduled time
-- in the Stats API game_date column, making time-proximity unusable).
game_schedule as (

    select
        game_pk,
        game_number,
        double_header
    from {{ ref('stg_statsapi_games') }}

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
    gr.home_team_id,
    gr.away_team_id,

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
left join game_schedule gs on gs.game_pk = gr.game_pk
left join odds_events oe
    on  gr.game_date    = oe.commence_date
    and gr.home_team_id = oe.home_team_id
    and gr.away_team_id = oe.away_team_id
left join parlay_events_ranked pe
    on  gr.game_date    = pe.game_date
    and gr.home_team_id = pe.home_team_id
    and gr.away_team_id = pe.away_team_id
-- Route each game_pk to its correct Parlay event slot using Stats API game_number.
-- abs(game_number - game_slot) = 0 is a perfect match (Game 1→slot 1, Game 2→slot 2).
-- For non-DH games: game_number=1 and only slot 1 exists → always matches correctly.
-- Null pe.game_slot (no Parlay match) sorts last, preserving one row per game_pk.
qualify row_number() over (
    partition by gr.game_pk
    order by abs(coalesce(gs.game_number, 1) - pe.game_slot) asc nulls last
) = 1
