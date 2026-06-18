-- =============================================================================
-- feature_edge_sharp_anchor_backtest.sql   (Edge Program — Story E4.3)
-- Grain: one row per (game_pk, market_type, soft_book),
--        market_type ∈ {h2h, totals}, soft_book ∈ {bovada, caesars, fanduel}.
--
-- NAME NOTE: Edge-scoped relation (feature_edge_) — never collides with a product
-- model (same convention as feature_pregame_edge_market / _era_quality).
--
-- Purpose (E4.3): the leakage-safe backtest frame for "bet the soft book toward
-- Pinnacle when they diverge." Per game/market/soft-book it captures, at the SOFT
-- BOOK'S OPEN (the decision time):
--   • the de-vigged soft open price/line + the soft CLOSE (for CLV)
--   • the contemporaneous PINNACLE anchor — its latest snapshot AT OR BEFORE the
--     soft open (point-in-time; never the close → no anchor leakage)
--   • the divergence: h2h edge_signed (prob units) / totals line_gap_runs (runs)
--   • the bet side the divergence implies, and the entry American price
--   • CLV_signed: did the soft book's OWN line move toward Pinnacle by close
--   • the realized outcome + bet_won + profit_units (ROI net of vig at the soft
--     open entry price) from mart_game_results
--   • the E3.0b recency_quality_weight for that (book, market, season)
--
-- The Python backtest (purged walk-forward CV + corrected PBO/DSR) reads THIS frame;
-- it selects the |edge| tail, weights by recency_quality_weight, and measures CLV +
-- ROI per era — 2026 forward is the decisive gate, not the easy 2021–2023 era.
--
-- Leakage guards (both enforced here, validated 2026-06-18, 0 violations):
--   • every snapshot_ts < commence_time
--   • the Pinnacle anchor snapshot_ts ≤ the soft book's open_ts (decision time)
--
-- Advisory/analysis only — no column asserts a +EV bet (honest-framing rule). This is
-- a BACKTEST artifact, not a serving feature; nothing here surfaces to users.
--
-- Sources:
--   oddsapi.odds_snapshots_historical  — per-book per-snapshot prices (de-vig inputs)
--   stg_statsapi_games                 — commence_time (leakage clock) + season
--   mart_game_results                  — realized outcomes (h2h winner, total runs)
--   feature_edge_book_market_era_quality — E3.0b recency-quality weight
-- =============================================================================

{{ config(materialized='table') }}

with

game_times as (
    select game_pk, game_date as commence_time, year(game_date) as season
    from {{ ref('stg_statsapi_games') }}
),

results as (
    select
        game_pk,
        iff(home_team_won, 1, 0)              as home_won,
        (home_final_score + away_final_score) as total_runs
    from {{ ref('mart_game_results') }}
),

-- Canonical-book, leakage-guarded snapshots (one row carries both markets' prices).
snaps as (
    select
        gt.season,
        s.game_pk,
        case when lower(s.bookmaker) = 'williamhill_us' then 'caesars'
             else lower(s.bookmaker) end                       as book,
        s.snapshot_ts,
        s.home_price, s.away_price,
        s.home_win_prob                                        as raw_home,
        s.away_win_prob                                        as raw_away,
        s.over_price, s.under_price, s.total_line,
        {{ american_to_implied_sql('s.over_price') }}          as impl_over,
        {{ american_to_implied_sql('s.under_price') }}         as impl_under
    from {{ source('oddsapi', 'odds_snapshots_historical') }} s
    inner join game_times gt on gt.game_pk = s.game_pk
    where lower(s.bookmaker) in ('pinnacle','bovada','caesars','fanduel','williamhill_us')
      and s.snapshot_ts < gt.commence_time
),

-- ── H2H branch ───────────────────────────────────────────────────────────────
h2h_snaps as (
    select season, game_pk, book, snapshot_ts, home_price, away_price,
           raw_home / nullif(raw_home + raw_away, 0) as vf_home
    from snaps
    where raw_home is not null and raw_away is not null
),
h2h_soft_open as (
    select game_pk, season, book, snapshot_ts as open_ts, home_price, away_price,
           vf_home as soft_open_vf
    from h2h_snaps
    where book in ('bovada','caesars','fanduel') and vf_home is not null
    qualify row_number() over (partition by game_pk, book order by snapshot_ts asc) = 1
),
h2h_soft_close as (
    select game_pk, book, vf_home as soft_close_vf
    from h2h_snaps
    where book in ('bovada','caesars','fanduel') and vf_home is not null
    qualify row_number() over (partition by game_pk, book order by snapshot_ts desc) = 1
),
h2h_pinn as (
    select game_pk, snapshot_ts as pinn_ts, vf_home as pinn_vf
    from h2h_snaps where book = 'pinnacle' and vf_home is not null
),
h2h_decision as (
    select so.game_pk, so.season, so.book, so.open_ts, so.home_price, so.away_price,
           so.soft_open_vf, p.pinn_vf as pinn_decision_vf
    from h2h_soft_open so
    inner join h2h_pinn p
        on p.game_pk = so.game_pk and p.pinn_ts <= so.open_ts   -- decision-time anchor
    qualify row_number() over (partition by so.game_pk, so.book order by p.pinn_ts desc) = 1
),
h2h_rows as (
    select
        d.game_pk, d.season, 'h2h' as market_type, d.book as soft_book,
        d.soft_open_vf, sc.soft_close_vf, d.pinn_decision_vf,
        (d.pinn_decision_vf - d.soft_open_vf)                  as edge_signed,
        cast(null as float)                                    as line_gap_runs,
        iff(d.pinn_decision_vf - d.soft_open_vf > 0, 'home', 'away') as bet_side,
        (sc.soft_close_vf - d.soft_open_vf)
            * sign(d.pinn_decision_vf - d.soft_open_vf)        as clv_signed,
        iff(d.pinn_decision_vf - d.soft_open_vf > 0, d.home_price, d.away_price) as entry_american,
        r.home_won                                             as ref_outcome,
        case when r.home_won is null then null
             when d.pinn_decision_vf - d.soft_open_vf > 0 then r.home_won  -- bet home
             else 1 - r.home_won end                           as bet_won      -- bet away
    from h2h_decision d
    inner join h2h_soft_close sc on sc.game_pk = d.game_pk and sc.book = d.book
    inner join results r         on r.game_pk = d.game_pk
    where d.pinn_decision_vf <> d.soft_open_vf                 -- drop exact ties (no side)
),

-- ── Totals branch (bet at the SOFT OPEN line; gap drives the side) ────────────
tot_snaps as (
    select season, game_pk, book, snapshot_ts, over_price, under_price, total_line,
           impl_over / nullif(impl_over + impl_under, 0) as vf_over
    from snaps
    where impl_over is not null and impl_under is not null and total_line is not null
),
tot_soft_open as (
    select game_pk, season, book, snapshot_ts as open_ts, over_price, under_price,
           total_line as soft_open_line, vf_over as soft_open_vf
    from tot_snaps
    where book in ('bovada','caesars','fanduel')
    qualify row_number() over (partition by game_pk, book order by snapshot_ts asc) = 1
),
tot_soft_close as (
    select game_pk, book, total_line as soft_close_line
    from tot_snaps
    where book in ('bovada','caesars','fanduel')
    qualify row_number() over (partition by game_pk, book order by snapshot_ts desc) = 1
),
tot_pinn as (
    select game_pk, snapshot_ts as pinn_ts, total_line as pinn_line
    from tot_snaps where book = 'pinnacle'
),
tot_decision as (
    select so.game_pk, so.season, so.book, so.open_ts, so.over_price, so.under_price,
           so.soft_open_line, so.soft_open_vf, p.pinn_line as pinn_decision_line
    from tot_soft_open so
    inner join tot_pinn p
        on p.game_pk = so.game_pk and p.pinn_ts <= so.open_ts
    qualify row_number() over (partition by so.game_pk, so.book order by p.pinn_ts desc) = 1
),
tot_rows as (
    select
        d.game_pk, d.season, 'totals' as market_type, d.book as soft_book,
        d.soft_open_vf, cast(null as float) as soft_close_vf, cast(null as float) as pinn_decision_vf,
        cast(null as float)                                    as edge_signed,
        (d.pinn_decision_line - d.soft_open_line)             as line_gap_runs,
        iff(d.pinn_decision_line - d.soft_open_line > 0, 'over', 'under') as bet_side,
        (sc.soft_close_line - d.soft_open_line)
            * sign(d.pinn_decision_line - d.soft_open_line)    as clv_signed,
        iff(d.pinn_decision_line - d.soft_open_line > 0, d.over_price, d.under_price) as entry_american,
        case when r.total_runs > d.soft_open_line then 1
             when r.total_runs < d.soft_open_line then 0 else null end as ref_outcome,
        case when r.total_runs = d.soft_open_line then null               -- push
             when d.pinn_decision_line - d.soft_open_line > 0
                  then iff(r.total_runs > d.soft_open_line, 1, 0)         -- bet over
             else iff(r.total_runs < d.soft_open_line, 1, 0) end as bet_won  -- bet under
    from tot_decision d
    inner join tot_soft_close sc on sc.game_pk = d.game_pk and sc.book = d.book
    inner join results r         on r.game_pk = d.game_pk
    where d.pinn_decision_line <> d.soft_open_line             -- drop exact ties (no side)
),

unioned as (
    select game_pk, season, market_type, soft_book, soft_open_vf, soft_close_vf,
           pinn_decision_vf, edge_signed, line_gap_runs, bet_side, clv_signed,
           entry_american, ref_outcome, bet_won
    from h2h_rows
    union all
    select game_pk, season, market_type, soft_book, soft_open_vf, soft_close_vf,
           pinn_decision_vf, edge_signed, line_gap_runs, bet_side, clv_signed,
           entry_american, ref_outcome, bet_won
    from tot_rows
),

final as (
    select
        u.*,
        -- Decimal odds at the soft-open entry price.
        case when u.entry_american > 0 then u.entry_american/100.0 + 1
             else 100.0/abs(u.entry_american) + 1 end          as entry_decimal,
        -- ROI net of vig: +profit on win (decimal−1), −1 on loss, null on push/unknown.
        case when u.bet_won is null then null
             when u.bet_won = 1 then
                 (case when u.entry_american > 0 then u.entry_american/100.0
                       else 100.0/abs(u.entry_american) end)
             else -1.0 end                                     as profit_units,
        -- Selection magnitudes (different units per market — keep both).
        coalesce(abs(u.edge_signed), 0)                        as edge_mag_prob,
        coalesce(abs(u.line_gap_runs), 0)                      as line_gap_mag_runs,
        q.recency_quality_weight,
        current_timestamp()::timestamp_ntz                     as computed_at
    from unioned u
    left join {{ ref('feature_edge_book_market_era_quality') }} q
        on q.book = u.soft_book and q.market_type = u.market_type and q.season = u.season
)

select * from final
