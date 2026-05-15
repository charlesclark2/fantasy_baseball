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
--            game_date      = commence_date (UTC date for Odds API; ET-corrected
--                             date from stg_parlayapi_odds for Parlay API)
--            home_team_name = odds home_team (after normalization)
--            away_team_name = odds away_team (after normalization)
--            For DH games, QUALIFY on time-proximity against Stats API scheduled
--            start distinguishes Game 1 from Game 2.
--
--          Team name normalization applied to both sources:
--            "Cleveland Indians"  → "Cleveland Guardians"  (2021 Odds API name)
--            "Oakland Athletics"  → "Athletics"            (Odds API 2021-2025 name)
--          Parlay API live data (2026+) should already use current names, but
--          the mapping is applied defensively to both sides.
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
        commence_time,
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
-- Partition includes date_trunc('hour', commence_time) so both DH game slots
-- survive as distinct rows rather than being collapsed to one.
parlay_events_deduped as (

    select
        event_id,
        game_date,
        commence_time,
        home_team,
        away_team,
        row_number() over (
            partition by game_date, home_team, away_team, date_trunc('hour', commence_time)
            order by ingestion_ts desc
        ) as _rn
    from parlay_events_normalized

),

parlay_events as (

    select
        event_id          as parlay_api_event_id,
        game_date,
        commence_time,
        home_team,
        away_team
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
        home_team,
        away_team,
        row_number() over (
            partition by game_date, home_team, away_team
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
    on  gr.game_date      = oe.commence_date
    and gr.home_team_name = oe.home_team
    and gr.away_team_name = oe.away_team
left join parlay_events_ranked pe
    on  gr.game_date      = pe.game_date
    and gr.home_team_name = pe.home_team
    and gr.away_team_name = pe.away_team
-- Route each game_pk to its correct Parlay event slot using Stats API game_number.
-- abs(game_number - game_slot) = 0 is a perfect match (Game 1→slot 1, Game 2→slot 2).
-- For non-DH games: game_number=1 and only slot 1 exists → always matches correctly.
-- Null pe.game_slot (no Parlay match) sorts last, preserving one row per game_pk.
qualify row_number() over (
    partition by gr.game_pk
    order by abs(coalesce(gs.game_number, 1) - pe.game_slot) asc nulls last
) = 1
