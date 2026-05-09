-- =============================================================================
-- mart_bookmaker_disagreement.sql
-- Grain: one row per game_pk (games with at least one pre-game odds snapshot)
-- Purpose: Bookmaker disagreement features for pre-game ML. Captures the
--          dispersion of implied probabilities across books before game time —
--          high disagreement indicates price discovery in progress.
--          Card 8.T.
--
-- Two-source union:
--   Historical (2021–2025): from baseball_data.oddsapi.mlb_odds_raw JSON.
--     ingestion_ts reflects batch-load time, NOT price capture time.
--     bookmaker.last_update (inside the JSON) is the authoritative timestamp.
--     Filter: last_update < commence_time (pre-game only).
--     Effective snapshot: ~noon–1 PM ET on game day (historical API query point).
--
--   Live (2026+): from mart_odds_outcomes, morning-window ingestion_ts.
--     Filter: ingestion_ts between 6:00 AM–8:30 AM ET on game_date.
--     Effective snapshot: true morning consensus before sharp action.
--
-- Bookmaker tier classification (unchanged from original):
--   Sharp-leaning: lowvig, betonlineag, bovada
--   Soft/recreational: williamhill_us, betmgm, caesars, fanduel
--   Neutral: all other bookmakers
--
-- stale_book_flag: only meaningful for 2026+ live path (multiple intraday
--   snapshots exist). For historical rows, set to 0 (not computable from a
--   single pre-game snapshot). The column is preserved for backward compat.
--
-- Null handling (unchanged):
--   ml_implied_prob_std   — NULL when only 1 book
--   ml_implied_prob_range — NULL-guarded when only 1 book
--   sharp_soft_ml_spread  — NULL when fewer than 1 sharp OR 1 soft book
--   totals_line_std       — NULL when only 1 book
--   totals_line_range     — NULL-guarded when only 1 book
--   All features NULL-imputed in preprocessing.py.
-- =============================================================================

{{ config(materialized='table') }}

with

-- Bridge provides game_pk and game_date for each odds event_id
bridge as (
    select event_id, game_pk, game_date
    from {{ ref('mart_game_odds_bridge') }}
    where event_id is not null
),

-- ─── Historical path (2021–2025): from mlb_odds_raw JSON ───────────────────
-- Flatten bookmakers → markets → outcomes. Use bookmaker.last_update as the
-- effective timestamp. Two-step dedup: _agg aggregates outcomes per
-- (event_id, bookmaker_key); _raw then QUALIFY-deduplicates the two identical
-- rows per event that exist in mlb_odds_raw. Splitting into two CTEs avoids
-- Snowflake's restriction on QUALIFY over VARIANT-derived GROUP BY expressions.

hist_h2h_agg as (
    select
        r.raw_json:id::varchar                                  as event_id,
        r.raw_json:commence_time::timestamp_tz                  as commence_ts,
        bk.value:key::varchar                                   as bookmaker_key,
        bk.value:last_update::timestamp_tz                      as last_update,
        max(case when o.value:name::varchar = r.home_team
                 then o.value:price::integer end)               as home_price,
        max(case when o.value:name::varchar = r.away_team
                 then o.value:price::integer end)               as away_price
    from baseball_data.oddsapi.mlb_odds_raw r,
         lateral flatten(input => r.raw_json:bookmakers) bk,
         lateral flatten(input => bk.value:markets) m,
         lateral flatten(input => m.value:outcomes) o
    where year(to_date(r.raw_json:commence_time::varchar)) between 2021 and 2025
      and m.value:key::varchar = 'h2h'
      -- pre-game only: bookmaker last updated before game start
      and bk.value:last_update::timestamp_tz < r.raw_json:commence_time::timestamp_tz
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
        r.raw_json:id::varchar                                  as event_id,
        bk.value:key::varchar                                   as bookmaker_key,
        bk.value:last_update::timestamp_tz                      as last_update,
        max(case when o.value:name::varchar = 'Over'
                 then o.value:point::float end)                 as total_line
    from baseball_data.oddsapi.mlb_odds_raw r,
         lateral flatten(input => r.raw_json:bookmakers) bk,
         lateral flatten(input => bk.value:markets) m,
         lateral flatten(input => m.value:outcomes) o
    where year(to_date(r.raw_json:commence_time::varchar)) between 2021 and 2025
      and m.value:key::varchar = 'totals'
      and bk.value:last_update::timestamp_tz < r.raw_json:commence_time::timestamp_tz
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

-- ─── Live path (2026+): morning-window snapshots from mart_odds_outcomes ───

live_h2h_raw as (
    select
        b.game_pk,
        b.game_date,
        o.bookmaker_key,
        o.ingestion_ts,
        max(case when o.is_home_outcome then o.outcome_price_american end) as home_price,
        max(case when o.is_away_outcome then o.outcome_price_american end) as away_price
    from {{ ref('mart_odds_outcomes') }} o
    inner join bridge b on b.event_id = o.event_id
    where o.market_key = 'h2h'
      and year(b.game_date) >= 2026
      -- Morning window: 6:00 AM–8:30 AM ET on game_date
      and convert_timezone('UTC', 'America/New_York', o.ingestion_ts)
          between dateadd('minute', 360, b.game_date::timestamp)
              and dateadd('minute', 510, b.game_date::timestamp)
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
    from {{ ref('mart_odds_outcomes') }} o
    inner join bridge b on b.event_id = o.event_id
    where o.market_key = 'totals'
      and o.outcome_point is not null
      and year(b.game_date) >= 2026
      and convert_timezone('UTC', 'America/New_York', o.ingestion_ts)
          between dateadd('minute', 360, b.game_date::timestamp)
              and dateadd('minute', 510, b.game_date::timestamp)
    group by b.game_pk, o.bookmaker_key, o.ingestion_ts
    qualify row_number() over (
        partition by game_pk, bookmaker_key
        order by ingestion_ts asc
    ) = 1
),

-- ─── Unified book-level prices ──────────────────────────────────────────────

all_h2h_book_prices as (
    -- Historical (2021–2025): bridge to game_pk
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

    -- Live (2026+)
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

-- ─── Vig-free implied probabilities ────────────────────────────────────────

h2h_vig_free as (
    select
        game_pk,
        game_date,
        bookmaker_key,
        -- vig-free: raw_home / (raw_home + raw_away)
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
        , 0)::float                                             as vf_home,
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
    from all_h2h_book_prices
),

-- ─── Game-level aggregations ────────────────────────────────────────────────

h2h_agg as (
    select
        game_pk,
        game_date,
        -- stddev naturally NULL when n=1
        stddev(vf_home)::float                                  as ml_implied_prob_std,
        -- range is 0 for n=1; null-guarded in final SELECT when n_books < 2
        (max(vf_home) - min(vf_home))::float                   as ml_implied_prob_range,
        -- sharp_soft_ml_spread: NULL unless both tiers present
        iff(
            count_if(tier = 'sharp') >= 1 and count_if(tier = 'soft') >= 1,
            (avg(case when tier = 'sharp' then vf_home end)
             - avg(case when tier = 'soft'  then vf_home end))::float,
            null
        )                                                       as sharp_soft_ml_spread,
        count(distinct bookmaker_key)::integer                  as n_books_available,
        -- stale_book_flag: meaningful only for 2026+ live path where multiple
        -- intraday snapshots exist. Historical rows have a single pre-game
        -- snapshot; flag is 0 (not stale by definition).
        0::integer                                              as stale_book_flag
    from h2h_vig_free
    group by game_pk, game_date
),

totals_agg as (
    select
        game_pk,
        count(distinct bookmaker_key)                           as n_totals_books,
        stddev(total_line)::float                               as totals_line_std,
        (max(total_line) - min(total_line))::float              as totals_line_range
    from all_totals_book_prices
    group by game_pk
)

select
    h.game_pk,
    h.game_date,

    -- Null-guard range columns for single-book case (std is naturally null)
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
