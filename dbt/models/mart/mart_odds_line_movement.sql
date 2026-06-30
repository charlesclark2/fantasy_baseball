-- =============================================================================
-- mart_odds_line_movement.sql
-- Grain: one row per game_pk
-- Purpose: Opening and pre-game implied probabilities per game, computed from
--          intraday odds snapshots. Exposes h2h and totals line movement as
--          signed deltas (pregame − open).
--
-- Data sources (priority order, deduped per game_pk):
--   1. oddsapi.odds_snapshots_historical (Odds API backfill) — AUTHORITATIVE.
--   2. mart_odds_outcomes (Odds API intraday) — FALLBACK for game_pks not yet
--      in the backfill (today's games).
-- Bookmaker: bovada (hardcoded). Leakage guard: snapshot_ts < commence_time.
--
-- DuckDB branch (E11.1-W6): odds_snapshots_historical is registered as a TYPED view
-- over its S3 parquet by run_w1_lakehouse.py (_build_w6); the other reads are migrated
-- W3pre/W6 marts. The Snowflake (else) branch is a thin view over the lakehouse_ext
-- external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

with

game_times as (
    select
        game_pk,
        game_date::timestamptz   as commence_time   -- TIMESTAMP_TZ from Stats API gameDate
    from stg_statsapi_games
),

-- ── Historical snapshots (2021–2025) ──────────────────────────────────────────
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
      and (gt.commence_time is null or h.snapshot_ts < gt.commence_time)
),

-- ── Live snapshots (2026+) ────────────────────────────────────────────────────
live_raw as (
    select
        o.ingestion_ts                                              as snapshot_ts,
        o.event_id,
        o.commence_time,
        o.home_team,
        o.away_team,
        o.bookmaker_key                                             as bookmaker,
        case
            when o.market_key = 'h2h' and o.is_home_outcome
            then o.outcome_price_american
        end                                                         as home_price,
        case
            when o.market_key = 'totals'
            then o.outcome_point
        end                                                         as total_line_val
    from mart_odds_outcomes o
    where o.bookmaker_key = 'bovada'
      and o.market_key in ('h2h', 'totals')
      and o.ingestion_ts < o.commence_time
),

live_pivoted as (
    select
        snapshot_ts,
        event_id,
        commence_time,
        home_team,
        away_team,
        bookmaker,
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
    inner join mart_game_odds_bridge b
        on  b.event_id = p.event_id
),

-- ── Pool both eras ────────────────────────────────────────────────────────────
all_snapshots as (
    select * from historical
    union all
    select * from live l
    where not exists (
        select 1 from historical h where h.game_pk = l.game_pk
    )
),

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
        o.open_home_win_prob,
        c.pregame_home_win_prob,
        case when c.snapshot_count > 1
             then c.pregame_home_win_prob - o.open_home_win_prob
        end                                                         as h2h_line_movement,
        o.open_total_line,
        c.pregame_total_line,
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

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.mart_odds_line_movement

{% endif %}
