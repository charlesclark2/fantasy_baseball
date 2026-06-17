-- =============================================================================
-- mart_closing_line_value.sql
-- Grain: one row per game_pk
-- Purpose: Vig-free opening and closing implied home-win probability and
--          O/U total line, averaged across all bookmakers that have both
--          an opening and closing pre-game snapshot.
--
--          CLV (Closing Line Value) is the gold standard for measuring model
--          edge: clv_home_ml > 0 means the market moved toward home team
--          winning by close. When combined with model predictions this shows
--          whether the model was ahead of market consensus at prediction time.
--
-- Opening snapshot: first snapshot on game day (ET date = game_date) to
--          align with the 08:00 EDT daily prediction run.
--
-- Closing snapshot: last snapshot strictly before commence_time. Typically
--          the 23:30 UTC (19:30 EDT) or 03:00 UTC (23:00 EDT) odds_snapshot
--          run, depending on game start time.
--
-- Vig-free implied probability (additive method, live data only):
--          raw_home = 1 / home_decimal_price
--          raw_away = 1 / away_decimal_price
--          vf_home  = raw_home / (raw_home + raw_away)
--
--          Historical data (2021-2025): home_win_prob from odds_snapshots_historical
--          is already the raw implied probability (close to vig-free within ~2-3%).
--
-- Sources:
--   Historical (2021-2025): baseball_data.oddsapi.odds_snapshots_historical
--   Live (2026+):           mart_odds_outcomes + mart_game_odds_bridge
-- =============================================================================

{{ config(materialized='table') }}

with

game_times as (
    select
        game_pk,
        game_date::date                                                 as game_date,
        game_date                                                       as commence_time
    from {{ ref('stg_statsapi_games') }}
),

-- ── Historical snapshots (2021–2025) ─────────────────────────────────────────
-- odds_snapshots_historical: one row per (game_pk, snapshot_ts, bookmaker).
-- home_win_prob is raw implied probability; used as vig-free approximation.
-- Three snapshots per game day: 12:00, 17:00, 23:00 UTC (08:00, 13:00, 19:00 EDT).
historical as (
    select
        h.game_pk,
        coalesce(gt.game_date, h.game_date)                             as game_date,
        h.snapshot_ts,
        h.bookmaker,
        h.home_win_prob                                                 as vf_home,
        h.total_line,
        -- Convert American odds → decimal, then derive vig-free over probability.
        -- vf_over = (1/over_dec) / (1/over_dec + 1/under_dec)
        case
            when h.over_price is not null and h.under_price is not null
            then (
                case when h.over_price > 0  then h.over_price / 100.0 + 1.0
                     when h.over_price < 0  then 100.0 / abs(h.over_price) + 1.0
                end
            )
        end                                                             as _over_dec,
        case
            when h.over_price is not null and h.under_price is not null
            then (
                case when h.under_price > 0 then h.under_price / 100.0 + 1.0
                     when h.under_price < 0 then 100.0 / abs(h.under_price) + 1.0
                end
            )
        end                                                             as _under_dec,
        'historical'                                                    as data_source,
        gt.commence_time
    from {{ source('oddsapi', 'odds_snapshots_historical') }} h
    left join game_times gt
        on  gt.game_pk = h.game_pk
    where h.game_pk is not null
      and h.home_win_prob is not null
      and h.bookmaker is not null
      -- Leakage guard: exclude snapshots at or after game start
      and (gt.commence_time is null or h.snapshot_ts < gt.commence_time)
),

historical_with_vf_over as (
    select
        game_pk,
        game_date,
        snapshot_ts,
        bookmaker,
        vf_home,
        total_line,
        case
            when _over_dec > 1.0 and _under_dec > 1.0
            then (1.0 / _over_dec) / (1.0 / _over_dec + 1.0 / _under_dec)
        end                                                             as vf_over,
        data_source,
        commence_time
    from historical
),

-- ── Live h2h snapshots (2026+) ────────────────────────────────────────────────
-- Pivot to get home and away decimal prices in the same row per (snapshot, book).
live_h2h_pivoted as (
    select
        ingestion_ts,
        event_id,
        commence_time,
        bookmaker_key                                                   as bookmaker,
        max(case when is_home_outcome then outcome_price_decimal end)   as home_decimal,
        max(case when is_away_outcome then outcome_price_decimal end)   as away_decimal
    from {{ ref('mart_odds_outcomes') }}
    where market_key = 'h2h'
      and ingestion_ts < commence_time   -- leakage guard
    group by ingestion_ts, event_id, commence_time, bookmaker_key
),

-- ── Live totals snapshots (2026+) ─────────────────────────────────────────────
-- Pivot to get over/under decimal prices in the same row per (snapshot, book),
-- so we can compute a vig-free over probability for closing-line totals CLV.
live_totals as (
    select
        ingestion_ts,
        event_id,
        bookmaker_key                                                   as bookmaker,
        max(outcome_point)                                              as total_line,
        max(case when outcome_name ilike '%over%'  then outcome_price_decimal end) as over_decimal,
        max(case when outcome_name ilike '%under%' then outcome_price_decimal end) as under_decimal
    from {{ ref('mart_odds_outcomes') }}
    where market_key = 'totals'
      and ingestion_ts < commence_time   -- leakage guard
    group by ingestion_ts, event_id, bookmaker_key
),

-- ── Compute vig-free prob and join totals ─────────────────────────────────────
live_with_vf as (
    select
        h.ingestion_ts                                                  as snapshot_ts,
        h.event_id,
        h.commence_time,
        h.bookmaker,
        -- Additive vig-free method: vf_home = (1/home_dec) / (1/home_dec + 1/away_dec)
        case
            when h.home_decimal > 1.0 and h.away_decimal > 1.0
            then (1.0 / h.home_decimal)
                 / (1.0 / h.home_decimal + 1.0 / h.away_decimal)
        end                                                             as vf_home,
        t.total_line,
        case
            when t.over_decimal > 1.0 and t.under_decimal > 1.0
            then (1.0 / t.over_decimal)
                 / (1.0 / t.over_decimal + 1.0 / t.under_decimal)
        end                                                             as vf_over
    from live_h2h_pivoted h
    left join live_totals t
        on  t.ingestion_ts = h.ingestion_ts
        and t.event_id     = h.event_id
        and t.bookmaker    = h.bookmaker
),

-- ── Join live snapshots to game_pk via bridge ─────────────────────────────────
live as (
    select
        b.game_pk,
        b.game_date                                                     as game_date,
        l.snapshot_ts,
        l.bookmaker,
        l.vf_home,
        l.total_line,
        l.vf_over,
        'live'                                                          as data_source,
        l.commence_time
    from live_with_vf l
    inner join {{ ref('mart_game_odds_bridge') }} b
        on  b.event_id = l.event_id
    where l.vf_home is not null
),

-- ── Pool both eras ────────────────────────────────────────────────────────────
all_snapshots as (
    select game_pk, game_date, snapshot_ts, bookmaker, vf_home, total_line, vf_over, data_source, commence_time
    from historical_with_vf_over
    union all
    select game_pk, game_date, snapshot_ts, bookmaker, vf_home, total_line, vf_over, data_source, commence_time
    from live
),

-- ── Opening snapshot ──────────────────────────────────────────────────────────
-- First snapshot on game day (ET date matches game_date) to capture the
-- morning market state at prediction time (~08:00 EDT / 12:00 UTC).
opening_candidates as (
    select *
    from all_snapshots
    where
        -- Snapshot must be on game day in Eastern time
        convert_timezone('UTC', 'America/New_York', snapshot_ts::timestamp_ntz)::date
            = game_date
),

opening_ranked as (
    select
        *,
        row_number() over (
            partition by game_pk, bookmaker
            order by snapshot_ts asc
        )                                                               as rn
    from opening_candidates
),

opening as (
    select
        game_pk,
        bookmaker,
        vf_home                                                         as open_vf_home,
        total_line                                                      as open_total_line,
        vf_over                                                         as open_vf_over
    from opening_ranked
    where rn = 1
),

-- ── Closing snapshot ──────────────────────────────────────────────────────────
-- Last snapshot before commence_time (leakage guard already applied above).
closing_ranked as (
    select
        *,
        row_number() over (
            partition by game_pk, bookmaker
            order by snapshot_ts desc
        )                                                               as rn
    from all_snapshots
),

closing as (
    select
        game_pk,
        game_date,
        bookmaker,
        data_source,
        vf_home                                                         as close_vf_home,
        total_line                                                      as close_total_line,
        vf_over                                                         as close_vf_over,
        snapshot_ts                                                     as close_snapshot_ts
    from closing_ranked
    where rn = 1
),

-- ── CLV per bookmaker ─────────────────────────────────────────────────────────
per_book as (
    select
        c.game_pk,
        c.game_date,
        c.bookmaker,
        c.data_source,
        o.open_vf_home,
        c.close_vf_home,
        c.close_vf_home - o.open_vf_home                               as clv_home_ml,
        o.open_total_line,
        c.close_total_line,
        case
            when o.open_total_line is not null and c.close_total_line is not null
            then c.close_total_line - o.open_total_line
        end                                                             as clv_total,
        o.open_vf_over,
        c.close_vf_over,
        case
            when o.open_vf_over is not null and c.close_vf_over is not null
            then c.close_vf_over - o.open_vf_over
        end                                                             as clv_over_prob,
        c.close_snapshot_ts
    from closing c
    inner join opening o
        on  o.game_pk    = c.game_pk
        and o.bookmaker  = c.bookmaker
    where o.open_vf_home  is not null
      and c.close_vf_home is not null
),

-- ── Average across bookmakers ─────────────────────────────────────────────────
-- Grain is one row per game_pk (see header). game_date is resolved as MIN across
-- the per-book values: the dense historical-odds backfill grid straddles midnight
-- UTC (00:00/01:00 timestamps), so a night game can be written into
-- odds_snapshots_historical under both its true ET calendar date and the next UTC
-- day. The straddle duplicate is always game_date + 1, so MIN(game_date) recovers
-- the correct ET date and collapses the duplicate back to a single row per game_pk.
final as (
    select
        game_pk,
        min(game_date)                                                 as game_date,
        avg(open_vf_home)                                               as open_vf_home,
        avg(close_vf_home)                                              as close_vf_home,
        avg(clv_home_ml)                                                as clv_home_ml,
        avg(open_total_line)                                            as open_total_line,
        avg(close_total_line)                                           as close_total_line,
        avg(clv_total)                                                  as clv_total,
        avg(open_vf_over)                                               as open_vf_over,
        avg(close_vf_over)                                              as close_vf_over,
        avg(clv_over_prob)                                              as clv_over_prob,
        count(distinct bookmaker)                                       as n_books_with_clv,
        max(data_source)                                                as data_source,
        max(close_snapshot_ts)                                          as close_snapshot_ts
    from per_book
    group by game_pk
)

select * from final
