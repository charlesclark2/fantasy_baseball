-- =============================================================================
-- mart_odds_line_movement.sql
-- Grain: one row per game_pk
-- Purpose: Opening and pre-game implied probabilities per game, computed from
--          intraday odds snapshots. Exposes h2h and totals line movement as
--          signed deltas (pregame − open).
--
-- Data sources by era:
--   2021–2025  baseball_data.oddsapi.odds_snapshots_historical  (Card 7.P2 backfill)
--   2026+      mart_odds_outcomes (Parlay API hourly snapshots via odds_snapshot.yml,
--              ~15 captures/game-day) filtered to ingestion_ts < commence_time
--
-- Bookmaker: bovada (hardcoded). The Card 7.P2 historical backfill used bovada;
--   Parlay API also carries bovada, ensuring consistent implied-prob scale across
--   eras. Future enhancement: make bookmaker configurable.
--
-- Leakage guard: all snapshots must have snapshot_ts < game commence_time.
--   For historical rows the guard uses stg_statsapi_games.game_date (TIMESTAMP_TZ).
--   For live rows the guard uses the real commence_time from
--   stg_parlayapi_canonical_events, with fallback to mart_odds_outcomes.commence_time
--   (the 19:00:00Z placeholder) when canonical data is absent for an event.
--
-- Null handling:
--   h2h_line_movement / total_line_movement are NULL when snapshot_count = 1
--   (open = close, no detectable movement). Imputation to 0.0 happens downstream
--   in feature_pregame_game_features. open_home_win_prob and open_total_line are
--   left NULL when no data exists; imputing 0.0 for a probability is meaningless.
-- =============================================================================

{{ config(materialized='table') }}

with

game_times as (
    -- Game start timestamp (UTC) for leakage guard on historical snapshots
    select
        game_pk,
        game_date   as commence_time   -- TIMESTAMP_TZ from Stats API gameDate
    from {{ ref('stg_statsapi_games') }}
),

-- ── Historical snapshots (2021–2025) ──────────────────────────────────────────
-- odds_snapshots_historical is pre-pivoted: one row per (game_pk, snapshot_ts,
-- bookmaker) with home_win_prob and total_line already computed.
historical as (
    select
        h.game_pk,
        h.game_date,
        h.snapshot_ts,
        h.home_team,
        h.away_team,
        h.home_win_prob,
        h.total_line,
        h.bookmaker,
        'historical'    as data_source,
        gt.commence_time
    from {{ source('oddsapi', 'odds_snapshots_historical') }} h
    left join game_times gt
        on  gt.game_pk = h.game_pk
    where h.bookmaker = 'bovada'
      and h.game_pk is not null
      -- Leakage guard: drop any snapshot after first pitch
      and (gt.commence_time is null or h.snapshot_ts < gt.commence_time)
),

-- ── Real game start times (Story 0.10) ───────────────────────────────────────
-- Parlay API /events and /odds return 19:00:00Z as a placeholder for all games.
-- /events/canonical is the only endpoint with real per-game start times, but it
-- exposes only canonical_event_id (no ephemeral event_id).
--
-- Bridge: stg_parlayapi_odds maps event_id ↔ canonical_event_id for Parlay rows.
-- canonical_times resolves to one real commence_time per event_id.
-- Left-joined in live_raw so the mart degrades gracefully when canonical data is
-- absent (falls back to the 19:00:00Z placeholder).
event_canonical_bridge as (
    select distinct
        event_id,
        canonical_event_id
    from {{ ref('stg_parlayapi_odds') }}
    where source_system = 'parlay_api'
      and canonical_event_id is not null
),

canonical_times as (
    select
        b.event_id,
        c.commence_time
    from {{ ref('stg_parlayapi_canonical_events') }} c
    inner join event_canonical_bridge b
        on  b.canonical_event_id = c.canonical_event_id
    qualify row_number() over (
        partition by b.event_id
        order by c.ingestion_ts desc
    ) = 1
),

-- ── Live snapshots (2026+) ────────────────────────────────────────────────────
-- mart_odds_outcomes has one row per (ingestion_ts, event_id, bookmaker_key,
-- market_key, outcome_name). Pivot to game-level row with home_win_prob + total_line.
live_raw as (
    select
        o.ingestion_ts                                              as snapshot_ts,
        o.event_id,
        -- Use real game start time from canonical events; fall back to placeholder.
        coalesce(ct.commence_time, o.commence_time)                 as commence_time,
        o.home_team,
        o.away_team,
        o.bookmaker_key                                             as bookmaker,
        -- h2h home-win price (American odds); null for all other outcome rows
        case
            when o.market_key = 'h2h' and o.is_home_outcome
            then o.outcome_price_american
        end                                                         as home_price,
        -- O/U line; same value on Over and Under rows, null for h2h rows
        case
            when o.market_key = 'totals'
            then o.outcome_point
        end                                                         as total_line_val
    from {{ ref('mart_odds_outcomes') }} o
    left join canonical_times ct
        on  ct.event_id = o.event_id
    where o.bookmaker_key = 'bovada'
      and o.market_key in ('h2h', 'totals')
      and o.ingestion_ts < coalesce(ct.commence_time, o.commence_time)
),

live_pivoted as (
    select
        snapshot_ts,
        event_id,
        commence_time,
        home_team,
        away_team,
        bookmaker,
        -- Convert American odds to raw implied probability (with vig)
        max(
            case when home_price is not null then
                case when home_price < 0
                     then abs(home_price) / (abs(home_price) + 100.0)
                     else 100.0 / (home_price + 100.0)
                end
            end
        )                                                           as home_win_prob,
        max(total_line_val)                                         as total_line
    from live_raw
    group by snapshot_ts, event_id, commence_time, home_team, away_team, bookmaker
),

-- Join live pivoted snapshots to game_pk via mart_game_odds_bridge (event_id key).
-- Note: mart_game_odds_bridge stores one canonical event_id per game_pk (the most
-- recently ingested). Snapshots associated with superseded event_ids are excluded.
live as (
    select
        b.game_pk,
        b.game_date,
        p.snapshot_ts,
        p.home_team,
        p.away_team,
        p.home_win_prob,
        p.total_line,
        p.bookmaker,
        'live'          as data_source,
        p.commence_time
    from live_pivoted p
    inner join {{ ref('mart_game_odds_bridge') }} b
        on  b.event_id = p.event_id
),

-- ── Pool both eras ────────────────────────────────────────────────────────────
all_snapshots as (
    select * from historical
    union all
    select * from live
),

-- ── Rank snapshots within each game to identify open (earliest) and
--    pregame (latest, already leakage-guarded) ─────────────────────────────────
ranked as (
    select
        *,
        row_number() over (
            partition by game_pk, bookmaker
            order by snapshot_ts asc
        )                                                           as rn_open,
        row_number() over (
            partition by game_pk, bookmaker
            order by snapshot_ts desc
        )                                                           as rn_close,
        count(*) over (
            partition by game_pk, bookmaker
        )                                                           as snapshot_count
    from all_snapshots
),

open_snap as (
    select
        game_pk,
        home_win_prob   as open_home_win_prob,
        total_line      as open_total_line
    from ranked
    where rn_open = 1
),

close_snap as (
    select
        game_pk,
        game_date,
        home_team,
        away_team,
        home_win_prob   as pregame_home_win_prob,
        total_line      as pregame_total_line,
        snapshot_count,
        data_source,
        bookmaker
    from ranked
    where rn_close = 1
),

final as (
    select
        c.game_pk,
        c.game_date,
        c.home_team,
        c.away_team,

        -- Opening-line implied probabilities (earliest pre-game snapshot)
        o.open_home_win_prob,

        -- Pre-game implied probabilities (latest pre-game snapshot)
        c.pregame_home_win_prob,

        -- h2h line movement: NULL when only 1 snapshot (open = close, no detectable movement)
        -- Positive = line moved toward home team winning
        case when c.snapshot_count > 1
             then c.pregame_home_win_prob - o.open_home_win_prob
        end                                                         as h2h_line_movement,

        -- Opening O/U total
        o.open_total_line,

        -- Pre-game O/U total
        c.pregame_total_line,

        -- Totals movement: NULL when only 1 snapshot or totals absent for game
        -- Positive = total moved up (more runs expected)
        case when c.snapshot_count > 1
             then c.pregame_total_line - o.open_total_line
        end                                                         as total_line_movement,

        c.snapshot_count,
        c.data_source,
        c.bookmaker

    from close_snap c
    inner join open_snap o
        on  o.game_pk = c.game_pk
)

select * from final
