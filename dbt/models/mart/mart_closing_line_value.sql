-- =============================================================================
-- mart_closing_line_value.sql
-- Grain: one row per game_pk
-- Purpose: Vig-free opening and closing implied home-win probability and O/U total
--          line, averaged across all bookmakers that have both an opening and
--          closing pre-game snapshot. CLV = close − open (home/over perspective).
--
-- Opening snapshot: first snapshot on game day (ET date = game_date).
-- Closing snapshot: last snapshot strictly before commence_time.
--
-- Sources:
--   Historical (2021-2025): oddsapi.odds_snapshots_historical
--   Live (2026+):           mart_odds_outcomes + mart_game_odds_bridge
--
-- DuckDB branch (E11.1-W6): odds_snapshots_historical is a TYPED view over its S3
-- parquet (registered by run_w1_lakehouse.py); Snowflake convert_timezone(...) →
-- DuckDB AT TIME ZONE. The Snowflake (else) branch is a thin view over the
-- lakehouse_ext external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

with

game_times as (
    select
        game_pk,
        game_date::date                                                 as game_date,
        game_date::timestamptz                                                       as commence_time
    from stg_statsapi_games
),

-- ── Historical snapshots (2021–2025) ─────────────────────────────────────────
historical as (
    select
        h.game_pk,
        coalesce(gt.game_date, h.game_date)                             as game_date,
        h.snapshot_ts,
        h.bookmaker,
        h.home_win_prob                                                 as vf_home,
        h.total_line,
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
live_h2h_pivoted as (
    select
        ingestion_ts,
        event_id,
        commence_time,
        bookmaker_key                                                   as bookmaker,
        max(case when is_home_outcome then outcome_price_decimal end)   as home_decimal,
        max(case when is_away_outcome then outcome_price_decimal end)   as away_decimal
    from mart_odds_outcomes
    where market_key = 'h2h'
      and ingestion_ts < commence_time::timestamp
    group by ingestion_ts, event_id, commence_time, bookmaker_key
),

-- ── Live totals snapshots (2026+) ─────────────────────────────────────────────
live_totals as (
    select
        ingestion_ts,
        event_id,
        bookmaker_key                                                   as bookmaker,
        max(outcome_point)                                              as total_line,
        max(case when outcome_name ilike '%over%'  then outcome_price_decimal end) as over_decimal,
        max(case when outcome_name ilike '%under%' then outcome_price_decimal end) as under_decimal
    from mart_odds_outcomes
    where market_key = 'totals'
      and ingestion_ts < commence_time::timestamp
    group by ingestion_ts, event_id, bookmaker_key
),

live_with_vf as (
    select
        h.ingestion_ts                                                  as snapshot_ts,
        h.event_id,
        h.commence_time,
        h.bookmaker,
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
    inner join mart_game_odds_bridge b
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
opening_candidates as (
    select *
    from all_snapshots
    where
        -- Snowflake convert_timezone('UTC','America/New_York', snapshot_ts::timestamp_ntz)::date
        -- → DuckDB: drop to UTC wall-clock (session tz=UTC), then AT TIME ZONE to ET.
        ((snapshot_ts::timestamp at time zone 'UTC' at time zone 'America/New_York')::date)
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

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.mart_closing_line_value

{% endif %}
