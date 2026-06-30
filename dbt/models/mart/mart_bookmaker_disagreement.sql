-- =============================================================================
-- mart_bookmaker_disagreement.sql
-- Grain: one row per game_pk (games with at least one pre-game odds snapshot)
-- Purpose: Bookmaker disagreement features for pre-game ML (dispersion of implied
--          probabilities across books before game time). Card 8.T.
--
-- Two-source union:
--   Historical (2021–2025): from oddsapi.mlb_odds_raw JSON. bookmaker.last_update
--     (inside the JSON) is the authoritative pre-game timestamp.
--   Live (2026+): from mart_odds_outcomes, morning-window ingestion_ts.
-- Tiers — sharp: lowvig, betonlineag, bovada; soft: williamhill_us, betmgm,
--   caesars, fanduel.
--
-- DuckDB branch (E11.1-W6): the historical path re-flattens the RAW JSON parquet
-- (lakehouse_raw/mlb_odds_raw/, same blob stg_oddsapi_odds flattens) since the
-- export carries raw_json (home_team/away_team are read from inside it, identical
-- to the Snowflake columns); the live path reads the migrated mart_odds_outcomes +
-- mart_game_odds_bridge. iff()/count_if()/convert_timezone()/dateadd() →
-- CASE / count(*) FILTER / AT TIME ZONE / interval. Snowflake (else) branch is a
-- thin view over the lakehouse_ext external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

with

bridge as (
    select event_id, odds_api_event_id, game_pk, game_date
    from mart_game_odds_bridge
    where event_id is not null
),

-- ─── Historical path (2021–2025): flatten mlb_odds_raw RAW JSON ──────────────
hist_src as (
    select raw_json
    from read_parquet('{{ lakehouse_raw_loc("mlb_odds_raw") }}**/*.parquet', union_by_name=true)
    where raw_json is not null
      and json_extract_string(raw_json, '$.id') is not null
      and json_extract(raw_json, '$.bookmakers') is not null
),

hist_bk as (
    select
        json_extract_string(raw_json, '$.id')                       as event_id,
        json_extract_string(raw_json, '$.commence_time')::timestamp as commence_ts,
        json_extract_string(raw_json, '$.home_team')                as home_team,
        json_extract_string(raw_json, '$.away_team')                as away_team,
        unnest(from_json(json_extract(raw_json, '$.bookmakers'), '["JSON"]')) as bk
    from hist_src
),

hist_mkt as (
    select
        event_id, commence_ts, home_team, away_team,
        json_extract_string(bk, '$.key')                            as bookmaker_key,
        json_extract_string(bk, '$.last_update')::timestamp         as last_update,
        unnest(from_json(json_extract(bk, '$.markets'), '["JSON"]')) as m
    from hist_bk
),

hist_flat as (
    select
        event_id, commence_ts, home_team, away_team, bookmaker_key, last_update,
        json_extract_string(m, '$.key')                             as market_key,
        unnest(from_json(json_extract(m, '$.outcomes'), '["JSON"]')) as o
    from hist_mkt
),

hist_outcomes as (
    select
        event_id, commence_ts, home_team, away_team, bookmaker_key, last_update, market_key,
        json_extract_string(o, '$.name')                            as outcome_name,
        json_extract_string(o, '$.price')::integer                  as outcome_price,
        json_extract_string(o, '$.point')::double                   as outcome_point
    from hist_flat
),

hist_h2h_agg as (
    select
        event_id, commence_ts, bookmaker_key, last_update,
        max(case when outcome_name = home_team then outcome_price end) as home_price,
        max(case when outcome_name = away_team then outcome_price end) as away_price
    from hist_outcomes
    where year(commence_ts) between 2021 and 2025
      and market_key = 'h2h'
      and last_update < commence_ts
    group by 1, 2, 3, 4
),

hist_h2h_raw as (
    select event_id, commence_ts, bookmaker_key, last_update, home_price, away_price
    from hist_h2h_agg
    qualify row_number() over (
        partition by event_id, bookmaker_key
        order by last_update desc
    ) = 1
),

hist_totals_agg as (
    select
        event_id, bookmaker_key, last_update,
        max(case when outcome_name = 'Over' then outcome_point end) as total_line
    from hist_outcomes
    where year(commence_ts) between 2021 and 2025
      and market_key = 'totals'
      and last_update < commence_ts
    group by 1, 2, 3
),

hist_totals_raw as (
    select event_id, bookmaker_key, last_update, total_line
    from hist_totals_agg
    qualify row_number() over (
        partition by event_id, bookmaker_key
        order by last_update desc
    ) = 1
),

-- ─── Live path (2026+): pre-game snapshots from mart_odds_outcomes ────────────
live_h2h_raw as (
    select
        b.game_pk,
        b.game_date,
        o.bookmaker_key,
        o.ingestion_ts,
        max(case when o.is_home_outcome then o.outcome_price_american end) as home_price,
        max(case when o.is_away_outcome then o.outcome_price_american end) as away_price
    from mart_odds_outcomes o
    inner join bridge b
        on  b.event_id = o.event_id
        or (b.odds_api_event_id is not null and b.odds_api_event_id = o.event_id)
    where o.market_key = 'h2h'
      -- INC-23: b.game_date is parquet-VARCHAR here. mart_game_spine emits game_date
      -- as ::timestamp (its ext-table contract), and the W8a binary-timestamp cure
      -- (_string_timestamp_wrap) stores every TIMESTAMP output as ISO VARCHAR in the
      -- parquet → mart_game_odds_bridge inherits VARCHAR game_date → year(VARCHAR) and
      -- VARCHAR ± interval are rejected by the DuckDB binder. Cast ::date before any
      -- date function / arithmetic (DuckDB-compat rule). Output game_date stays VARCHAR.
      and year(b.game_date::date) >= 2026
      and o.ingestion_ts::date in (b.game_date::date, b.game_date::date - interval 1 day)
      and (o.ingestion_ts::timestamp at time zone 'UTC' at time zone 'America/New_York')
          <= b.game_date::timestamp + interval 720 minute
    group by b.game_pk, b.game_date, o.bookmaker_key, o.ingestion_ts
    qualify row_number() over (
        partition by game_pk, bookmaker_key
        order by ingestion_ts asc
    ) = 1
),

live_totals_raw as (
    select
        b.game_pk,
        o.bookmaker_key,
        o.ingestion_ts,
        max(o.outcome_point) as total_line
    from mart_odds_outcomes o
    inner join bridge b
        on  b.event_id = o.event_id
        or (b.odds_api_event_id is not null and b.odds_api_event_id = o.event_id)
    where o.market_key = 'totals'
      and o.outcome_point is not null
      -- INC-23: cast parquet-VARCHAR game_date ::date before year()/interval (see live_h2h_raw).
      and year(b.game_date::date) >= 2026
      and o.ingestion_ts::date in (b.game_date::date, b.game_date::date - interval 1 day)
      and (o.ingestion_ts::timestamp at time zone 'UTC' at time zone 'America/New_York')
          <= b.game_date::timestamp + interval 720 minute
    group by b.game_pk, o.bookmaker_key, o.ingestion_ts
    qualify row_number() over (
        partition by game_pk, bookmaker_key
        order by ingestion_ts asc
    ) = 1
),

-- ─── Unified book-level prices ──────────────────────────────────────────────
all_h2h_book_prices as (
    select
        b.game_pk,
        b.game_date,
        h.bookmaker_key,
        h.home_price,
        h.away_price
    from hist_h2h_raw h
    inner join bridge b on b.event_id = h.event_id
    where h.home_price is not null
      and h.away_price is not null

    union all

    select game_pk, game_date, bookmaker_key, home_price, away_price
    from live_h2h_raw
    where home_price is not null
      and away_price is not null
),

all_totals_book_prices as (
    select
        b.game_pk,
        h.bookmaker_key,
        h.total_line
    from hist_totals_raw h
    inner join bridge b on b.event_id = h.event_id
    where h.total_line is not null

    union all

    select game_pk, bookmaker_key, total_line
    from live_totals_raw
    where total_line is not null
),

-- ─── Garbage-price guard ────────────────────────────────────────────────────
valid_h2h_book_prices as (
    select game_pk, game_date, bookmaker_key, home_price, away_price
    from all_h2h_book_prices
    where (
        (case when home_price < 0 then abs(home_price) / (abs(home_price) + 100.0)
              else 100.0 / (home_price + 100.0) end)
      + (case when away_price < 0 then abs(away_price) / (abs(away_price) + 100.0)
              else 100.0 / (away_price + 100.0) end)
    ) between 1.00 and 1.40
),

-- ─── Vig-free implied probabilities ────────────────────────────────────────
h2h_vig_free as (
    select
        game_pk,
        game_date,
        bookmaker_key,
        (case when home_price < 0
              then abs(home_price) / (abs(home_price) + 100.0)
              else 100.0 / (home_price + 100.0)
         end)
        / nullif(
            (case when home_price < 0
                  then abs(home_price) / (abs(home_price) + 100.0)
                  else 100.0 / (home_price + 100.0)
             end)
            +
            (case when away_price < 0
                  then abs(away_price) / (abs(away_price) + 100.0)
                  else 100.0 / (away_price + 100.0)
             end)
        , 0)::double                                             as vf_home,
        case bookmaker_key
            when 'lowvig'         then 'sharp'
            when 'betonlineag'    then 'sharp'
            when 'bovada'         then 'sharp'
            when 'williamhill_us' then 'soft'
            when 'betmgm'         then 'soft'
            when 'caesars'        then 'soft'
            when 'fanduel'        then 'soft'
            else                       'neutral'
        end                                                     as tier
    from valid_h2h_book_prices
),

-- ─── Game-level aggregations ────────────────────────────────────────────────
h2h_agg as (
    select
        game_pk,
        game_date,
        stddev(vf_home)::double                                  as ml_implied_prob_std,
        (max(vf_home) - min(vf_home))::double                   as ml_implied_prob_range,
        case
            when count(*) filter (where tier = 'sharp') >= 1
             and count(*) filter (where tier = 'soft')  >= 1
            then (avg(case when tier = 'sharp' then vf_home end)
                  - avg(case when tier = 'soft'  then vf_home end))::double
            else null
        end                                                     as sharp_soft_ml_spread,
        count(distinct bookmaker_key)::integer                  as n_books_available,
        0::integer                                              as stale_book_flag
    from h2h_vig_free
    group by game_pk, game_date
),

totals_agg as (
    select
        game_pk,
        count(distinct bookmaker_key)                           as n_totals_books,
        stddev(total_line)::double                               as totals_line_std,
        (max(total_line) - min(total_line))::double              as totals_line_range
    from all_totals_book_prices
    group by game_pk
)

select
    h.game_pk,
    h.game_date,

    h.ml_implied_prob_std,
    case when h.n_books_available >= 2 then h.ml_implied_prob_range
         else null
    end                                                         as ml_implied_prob_range,
    t.totals_line_std,
    case when coalesce(t.n_totals_books, 0) >= 2 then t.totals_line_range
         else null
    end                                                         as totals_line_range,
    h.sharp_soft_ml_spread,
    h.n_books_available,
    h.stale_book_flag

from h2h_agg h
left join totals_agg t on t.game_pk = h.game_pk

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.mart_bookmaker_disagreement

{% endif %}
