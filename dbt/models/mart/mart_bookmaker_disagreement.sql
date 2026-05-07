-- =============================================================================
-- mart_bookmaker_disagreement.sql
-- Grain: one row per game_pk (games with at least one morning h2h snapshot)
-- Purpose: Bookmaker disagreement features for pre-game ML. Captures the
--          dispersion of implied probabilities across books at morning snapshot
--          time — high disagreement indicates price discovery in progress.
--          Card 8.T.
--
-- Leakage guard: only morning snapshots used — ingestion_ts between 6:00am and
--   8:30am ET on the game_date. This is before the market has moved
--   substantially from sharp action. Row counts per bookmaker_key represent
--   the earliest snapshot in that morning window per game × bookmaker.
--
-- Bookmaker tier classification:
--   Sharp-leaning: lowvig, betonlineag, bovada (tighter vig, faster discovery)
--   Soft/recreational: williamhill_us, betmgm, caesars, fanduel (slower movers)
--   Neutral: all other bookmakers
--
-- Null handling:
--   ml_implied_prob_std   — naturally NULL when only 1 book (STDDEV of 1 value)
--   ml_implied_prob_range — NULL-guarded to NULL when only 1 book
--   sharp_soft_ml_spread  — NULL when fewer than 1 sharp OR 1 soft book present
--   totals_line_std       — naturally NULL when only 1 book
--   totals_line_range     — NULL-guarded to NULL when only 1 book
--   All features are NULL-imputed in preprocessing.py (no COALESCE here).
-- =============================================================================

{{ config(materialized='table') }}

with

-- Bridge provides game_pk and game_date for each odds event_id
bridge as (
    select event_id, game_pk, game_date
    from {{ ref('mart_game_odds_bridge') }}
    where event_id is not null
),

-- Morning h2h snapshots — group (game_pk, bookmaker, ingestion_ts) to pivot
-- home and away prices, then QUALIFY to keep earliest per game × bookmaker
morning_h2h as (
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

-- Vig-free home implied probability and bookmaker tier per book
h2h_vig_free as (
    select
        game_pk,
        game_date,
        bookmaker_key,
        ingestion_ts,
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
    from morning_h2h
    where home_price is not null
      and away_price is not null
),

-- Morning totals snapshots — earliest per game × bookmaker
morning_totals as (
    select
        b.game_pk,
        o.bookmaker_key,
        o.ingestion_ts,
        max(o.outcome_point) as total_line
    from {{ ref('mart_odds_outcomes') }} o
    inner join bridge b on b.event_id = o.event_id
    where o.market_key = 'totals'
      and o.outcome_point is not null
      and convert_timezone('UTC', 'America/New_York', o.ingestion_ts)
          between dateadd('minute', 360, b.game_date::timestamp)
              and dateadd('minute', 510, b.game_date::timestamp)
    group by b.game_pk, o.bookmaker_key, o.ingestion_ts
    qualify row_number() over (
        partition by game_pk, bookmaker_key
        order by ingestion_ts asc
    ) = 1
),

-- Aggregate h2h features to game_pk grain
h2h_agg as (
    select
        game_pk,
        game_date,
        -- stddev naturally NULL when n=1 (Snowflake returns NULL for single-value STDDEV)
        stddev(vf_home)::float                                  as ml_implied_prob_std,
        -- range is 0 for n=1; null-guarded in final SELECT when n_books < 2
        (max(vf_home) - min(vf_home))::float                   as ml_implied_prob_range,
        -- sharp_soft_ml_spread: NULL unless both tiers have >= 1 book
        iff(
            count_if(tier = 'sharp') >= 1 and count_if(tier = 'soft') >= 1,
            (avg(case when tier = 'sharp' then vf_home end)
             - avg(case when tier = 'soft'  then vf_home end))::float,
            null
        )                                                       as sharp_soft_ml_spread,
        count(distinct bookmaker_key)::integer                  as n_books_available,
        -- stale_book_flag: 1 if oldest book's morning snapshot is >60 min
        -- behind the freshest book's morning snapshot
        iff(
            datediff('minute', min(ingestion_ts), max(ingestion_ts)) > 60,
            1, 0
        )::integer                                              as stale_book_flag
    from h2h_vig_free
    group by game_pk, game_date
),

-- Aggregate totals features to game_pk grain
totals_agg as (
    select
        game_pk,
        count(distinct bookmaker_key)                           as n_totals_books,
        stddev(total_line)::float                               as totals_line_std,
        (max(total_line) - min(total_line))::float              as totals_line_range
    from morning_totals
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
