-- =============================================================================
-- feature_pregame_edge_market.sql   (Edge Program — Story E3.0)
-- Grain: one row per (game_pk, market_type) where market_type ∈ {h2h, totals}
--
-- NAME NOTE: deliberately NOT named feature_pregame_market_features — that relation
-- is a pre-existing Python-managed SCD-2 SOURCE (sources.yml / scripts/ddl/
-- feature_pregame_market_features.sql) consumed by feature_pregame_odds_features.
-- This Edge model is a DISTINCT relation so the daily build never clobbers it.
--
-- Purpose: the SHARED market-data feature frame for the closing-line model (E3)
--          and the cross-book sharp-anchor (E4). Surfaces, point-in-time:
--            • the de-vigged PINNACLE fair value (the sharp anchor) — open + close
--            • the per-soft-book de-vigged implied price (bovada/caesars/fanduel)
--            • the per-book divergence vs the anchor:
--                - h2h:    edge_<book> = pinnacle_fair − book_implied   (prob units)
--                - totals: <book>_line_gap_runs = pinnacle_line − book_line (run units)
--                          (de-vig over-probs differ across books' own lines, so the
--                           clean totals divergence is the line gap; edge prob kept too)
--            • the open→close line MOVE of the sharp fair value (E3.1 Head-1 target)
--            • cross-book dispersion (mart_bookmaker_disagreement)
--            • point-in-time pre-game change counts for the events that move lines:
--                starter scratches, weather shifts (the spec's named movers)
--            • the freshest pre-game sharp quote timestamp + its lead time to first
--              pitch (the decision-time freshness flag is applied in serving code:
--               betting_ml/utils/market_features.quote_freshness — never anchor to a
--               quote older than a configurable window).
--
-- This is Layer 4: market data is not only allowed but central here. NOT a betting
-- signal on its own — every column is transparency/advisory (honest-framing rule).
--
-- SCOPE (v1, live window): reads the LIVE odds path (mart_odds_outcomes — Parlay +
--   Odds-API `eu` Pinnacle, 2026-05-01+). Historical Pinnacle (oddsapi.
--   odds_snapshots_historical, 2021–2025) is a deferred UNION (Edge spec: extend
--   pre-2024 only if E3.1/E4 are data-starved AFTER E1 says the signal survives PBO).
-- FAST-FOLLOW: lineup-slot deltas (feature_pregame_lineup_state has no dbt model to
--   ref()); incrementalize once the open/close grid stabilises (today's rows must
--   reflect the freshest quote, so v1 is a full `table` like mart_odds_line_movement).
--
-- Leakage guard: every quote/state row is filtered to before first pitch
--   (ingestion_ts / valid_from < commence_time). Enforced by a singular test in
--   dbt/tests/assert_no_leakage_market_features.sql and by validate_scd2_reconstruction.py.
--
-- Sources:
--   stg_statsapi_games            — authoritative commence_time (leakage clock)
--   mart_game_odds_bridge         — game_pk ↔ event_id
--   mart_odds_outcomes            — live per-book per-snapshot prices (de-vig inputs)
--   mart_bookmaker_disagreement   — cross-book dispersion
--   feature_pregame_starter_status / feature_pregame_weather_status — SCD-2 movers
-- =============================================================================

{{ config(materialized='table') }}

with

-- Authoritative game start (UTC). The single leakage clock for every feature below.
game_times as (
    select
        game_pk,
        game_date as commence_time
    from {{ ref('stg_statsapi_games') }}
),

-- game_pk ↔ event_id (one canonical event_id per game_pk; superseded ids excluded).
bridge as (
    select game_pk, event_id
    from {{ ref('mart_game_odds_bridge') }}
    where event_id is not null
),

-- ── Raw pre-game quotes for the anchor + soft books ──────────────────────────
-- One row per outcome; pivoted to a two-way price per snapshot in `snapshots`.
raw_quotes as (
    select
        b.game_pk,
        gt.commence_time,
        o.bookmaker_key                       as book,
        o.market_key                          as market_type,
        o.ingestion_ts,
        -- h2h: home / away American price (null on the other side's row)
        case when o.market_key = 'h2h' and o.is_home_outcome
             then o.outcome_price_american end as h2h_home_px,
        case when o.market_key = 'h2h' and o.is_away_outcome
             then o.outcome_price_american end as h2h_away_px,
        -- totals: over / under American price + the line (same on both rows)
        case when o.market_key = 'totals' and lower(o.outcome_name) = 'over'
             then o.outcome_price_american end as tot_over_px,
        case when o.market_key = 'totals' and lower(o.outcome_name) = 'under'
             then o.outcome_price_american end as tot_under_px,
        case when o.market_key = 'totals' then o.outcome_point end as tot_line
    from {{ ref('mart_odds_outcomes') }} o
    inner join bridge b      on b.event_id = o.event_id
    inner join game_times gt on gt.game_pk = b.game_pk
    where o.bookmaker_key in ('pinnacle', 'bovada', 'caesars', 'fanduel')
      and o.market_key in ('h2h', 'totals')
      -- Leakage guard: only snapshots taken before first pitch.
      and o.ingestion_ts < gt.commence_time
),

-- Collapse the two outcome rows into one two-way snapshot, then de-vig (additive).
-- american_to_implied: a<0 → -a/(-a+100) ; a>=0 → 100/(a+100).
snapshots as (
    select
        game_pk,
        commence_time,
        book,
        market_type,
        ingestion_ts,
        max(tot_line) as line,
        -- de-vigged fair prob of the REFERENCE side: home (h2h) / over (totals)
        case
            when market_type = 'h2h' then
                {{ american_to_implied_sql('max(h2h_home_px)') }}
                / nullif(
                    {{ american_to_implied_sql('max(h2h_home_px)') }}
                    + {{ american_to_implied_sql('max(h2h_away_px)') }}, 0)
            when market_type = 'totals' then
                {{ american_to_implied_sql('max(tot_over_px)') }}
                / nullif(
                    {{ american_to_implied_sql('max(tot_over_px)') }}
                    + {{ american_to_implied_sql('max(tot_under_px)') }}, 0)
        end as fair_prob
    from raw_quotes
    group by game_pk, commence_time, book, market_type, ingestion_ts
),

-- Rank snapshots within (game_pk, book, market) → open (earliest) / close (latest
-- pre-game). Drop snapshots whose de-vig failed (one side missing → fair_prob null).
ranked as (
    select
        *,
        row_number() over (partition by game_pk, book, market_type
                           order by ingestion_ts asc)  as rn_open,
        row_number() over (partition by game_pk, book, market_type
                           order by ingestion_ts desc) as rn_close,
        count(*)     over (partition by game_pk, book, market_type) as snapshot_count
    from snapshots
    where fair_prob is not null
),

close_open as (
    select
        c.game_pk,
        c.commence_time,
        c.book,
        c.market_type,
        c.fair_prob      as close_fair,
        c.line           as close_line,
        c.ingestion_ts   as close_ts,
        c.snapshot_count,
        o.fair_prob      as open_fair,
        o.line           as open_line
    from ranked c
    left join ranked o
        on  o.game_pk = c.game_pk
        and o.book = c.book
        and o.market_type = c.market_type
        and o.rn_open = 1
    where c.rn_close = 1
),

-- Pivot books → columns, one row per (game_pk, market_type).
pivoted as (
    select
        game_pk,
        market_type,
        max(commence_time)                                       as commence_time,
        -- Pinnacle anchor (sharp) ──────────────────────────────────────────────
        max(case when book = 'pinnacle' then close_fair end)     as pinnacle_fair_prob,
        max(case when book = 'pinnacle' then open_fair  end)     as pinnacle_open_prob,
        max(case when book = 'pinnacle' then close_line end)     as pinnacle_line,
        max(case when book = 'pinnacle' then open_line  end)     as pinnacle_open_line,
        max(case when book = 'pinnacle' then close_ts   end)     as pinnacle_quote_ts,
        max(case when book = 'pinnacle' then snapshot_count end) as pinnacle_snapshot_count,
        -- Soft books (user-bettable) ───────────────────────────────────────────
        max(case when book = 'bovada'  then close_fair end)      as bovada_implied_prob,
        max(case when book = 'bovada'  then close_line end)      as bovada_line,
        max(case when book = 'caesars' then close_fair end)      as caesars_implied_prob,
        max(case when book = 'caesars' then close_line end)      as caesars_line,
        max(case when book = 'fanduel' then close_fair end)      as fanduel_implied_prob,
        max(case when book = 'fanduel' then close_line end)      as fanduel_line
    from close_open
    group by game_pk, market_type
),

-- Cross-book dispersion (game-level; same value joined to both market rows).
dispersion as (
    select
        game_pk,
        ml_implied_prob_std,
        ml_implied_prob_range,
        totals_line_std,
        totals_line_range,
        sharp_soft_ml_spread,
        n_books_available,
        stale_book_flag
    from {{ ref('mart_bookmaker_disagreement') }}
),

-- Point-in-time pre-game movers ─────────────────────────────────────────────
-- Starter scratches: # distinct projected starters seen per game before first
-- pitch (>1 distinct on a side ⇒ a scratch/change the market would reprice).
starter_changes as (
    select
        s.game_pk,
        count(distinct case when s.side = 'home' then s.starter_player_id end) as home_starters_seen,
        count(distinct case when s.side = 'away' then s.starter_player_id end) as away_starters_seen
    from {{ ref('feature_pregame_starter_status') }} s
    inner join game_times gt on gt.game_pk = s.game_pk
    where s.valid_from < gt.commence_time
    group by s.game_pk
),

-- Weather shifts: # distinct forecast snapshots before first pitch (>1 ⇒ forecast
-- moved; the latest pre-game temp/wind component is the current state).
weather_changes as (
    select
        w.game_pk,
        count(distinct w.record_hash) as weather_snapshots_seen,
        -- Peak forecast wind component seen across pre-game snapshots (defined
        -- aggregate; a wind-out spike is a classic totals mover).
        max(w.wind_component_mph)     as max_pregame_wind_component
    from {{ ref('feature_pregame_weather_status') }} w
    inner join game_times gt on gt.game_pk = w.game_pk
    where w.valid_from < gt.commence_time
    group by w.game_pk
),

final as (
    select
        p.game_pk,
        p.market_type,
        p.commence_time,

        -- ── Sharp anchor (Pinnacle, de-vigged) ───────────────────────────────
        p.pinnacle_fair_prob,
        p.pinnacle_open_prob,
        p.pinnacle_line,
        p.pinnacle_open_line,
        p.pinnacle_quote_ts,
        p.pinnacle_snapshot_count,
        (p.pinnacle_fair_prob is not null)::boolean                  as pinnacle_available,
        -- Lead time of the freshest pre-game sharp quote to first pitch (minutes).
        -- Decision-time freshness (vs "now") is applied in serving code; this is the
        -- point-in-time lead the batch can know without a wall clock.
        datediff('minute', p.pinnacle_quote_ts, p.commence_time)     as pinnacle_lead_min,

        -- ── Sharp line MOVE (E3.1 Head-1 target) ─────────────────────────────
        -- h2h: Δ fair prob (prob units); totals: Δ fair line (run units).
        case when p.market_type = 'h2h'
             then p.pinnacle_fair_prob - p.pinnacle_open_prob end    as pinnacle_h2h_move_prob,
        case when p.market_type = 'totals'
             then p.pinnacle_line - p.pinnacle_open_line end         as pinnacle_totals_move_runs,

        -- ── Per-book implied price (de-vigged) ───────────────────────────────
        p.bovada_implied_prob,
        p.bovada_line,
        p.caesars_implied_prob,
        p.caesars_line,
        p.fanduel_implied_prob,
        p.fanduel_line,

        -- ── Per-book divergence vs the anchor (E4.1 signal, pre-staged) ───────
        -- h2h: prob-unit edge. Positive ⇒ sharp prices the home side above the book.
        p.pinnacle_fair_prob - p.bovada_implied_prob                 as edge_bovada_prob,
        p.pinnacle_fair_prob - p.caesars_implied_prob                as edge_caesars_prob,
        p.pinnacle_fair_prob - p.fanduel_implied_prob                as edge_fanduel_prob,
        -- totals: run-unit line gap (the clean line-shopping divergence; de-vig
        -- over-probs aren't comparable across different lines). Positive ⇒ sharp
        -- line higher than the book's.
        case when p.market_type = 'totals'
             then p.pinnacle_line - p.bovada_line  end               as bovada_line_gap_runs,
        case when p.market_type = 'totals'
             then p.pinnacle_line - p.caesars_line end               as caesars_line_gap_runs,
        case when p.market_type = 'totals'
             then p.pinnacle_line - p.fanduel_line end               as fanduel_line_gap_runs,

        -- ── Cross-book dispersion ────────────────────────────────────────────
        d.ml_implied_prob_std,
        d.ml_implied_prob_range,
        d.totals_line_std,
        d.totals_line_range,
        d.sharp_soft_ml_spread,
        d.n_books_available,
        d.stale_book_flag,

        -- ── Point-in-time movers (pre-game) ──────────────────────────────────
        coalesce(sc.home_starters_seen, 0)                           as home_starters_seen,
        coalesce(sc.away_starters_seen, 0)                           as away_starters_seen,
        (coalesce(sc.home_starters_seen, 0) > 1
            or coalesce(sc.away_starters_seen, 0) > 1)::boolean      as starter_changed_flag,
        coalesce(wc.weather_snapshots_seen, 0)                       as weather_snapshots_seen,
        (coalesce(wc.weather_snapshots_seen, 0) > 1)::boolean        as weather_changed_flag,
        wc.max_pregame_wind_component,

        current_timestamp()::timestamp_ntz                           as computed_at

    from pivoted p
    left join dispersion d      on d.game_pk = p.game_pk
    left join starter_changes sc on sc.game_pk = p.game_pk
    left join weather_changes wc on wc.game_pk = p.game_pk
)

select * from final
