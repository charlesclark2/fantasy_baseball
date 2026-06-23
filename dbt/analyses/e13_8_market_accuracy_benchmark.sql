-- =============================================================================
-- e13_8_market_accuracy_benchmark.sql   (Edge Program — Story E13.8)
-- Grain: one row per (book, market_type, season) for EVERY oddsapi book that
--        carries the market (market_type ∈ {h2h, totals}).
--
-- Analysis (NOT materialized): compiled by `dbtf compile` for CI/parity but never
-- run on a schedule — zero warehouse cost. Reproduces & WIDENS E3.0b's
-- feature_edge_book_market_era_quality (which hard-codes 4 books) to the full book
-- set, and ADDS the line-accuracy / hit-rate / push-rate extensions the Brier alone
-- can't capture. Operator runs it ad-hoc to refresh the E13.8 benchmark report.
--
-- "What are we targeting?" — the sharpest book's accuracy is the practical CEILING
-- our model must MATCH (the H2H edge is dead; product goal is calibration-parity
-- with the close), the cross-book spread is where any residual edge could live, and
-- the year trend says whether books are sharpening.
--
-- Metrics per (book, market, season), all on the CLOSE:
--   n_games_brier           — games with a usable close + non-push outcome
--   closing_brier           — mean (fair_prob − outcome)^2   (lower = sharper)
--   closing_log_loss        — mean −[y·ln p + (1−y)·ln(1−p)]  (lower = sharper)
--   mean_vig                — mean two-way overround at close (lower = better price)
--   mean_abs_dist_to_sharp  — mean |book_fair − pinnacle_fair| (0 for pinnacle)
--   h2h_fav_hit_rate        — share of games the de-vigged favorite won  (h2h only)
--   line_mae / line_rmse    — mean/RMS |total_line − actual_runs|        (totals only)
--   push_rate               — share of priced games where runs == line   (totals only)
--
-- Reference side: h2h = home; totals = over. Outcome: h2h home win; totals
-- (home+away runs) vs the book's OWN close line (pushes excluded from Brier,
-- counted for push_rate). De-vig via american_to_implied_sql for exact parity with
-- the warehouse + Python serve-time de-vig.
--
-- ⚠️ "CLOSE" CAVEAT (inherited from E3.0b/E4.3, preserved deliberately): the leakage
-- guard is `snapshot_ts < game_date`, i.e. the last snapshot strictly before
-- game-day 00:00 UTC — roughly 18–24h before first pitch, NOT the minutes-before-
-- pitch close. So every accuracy number here is a CONSERVATIVE LOWER BOUND on true
-- closing-line sharpness; the real close would be modestly sharper.
--
-- Advisory/transparency only — no column asserts a +EV bet (honest-framing rule).
--
-- Sources:
--   oddsapi.odds_snapshots_historical — per-book per-snapshot prices (de-vig inputs)
--   mart_game_results                 — realized outcomes (h2h winner, total runs)
-- =============================================================================

with

results as (
    select
        game_pk,
        iff(home_team_won, 1, 0)              as home_won,
        (home_final_score + away_final_score) as total_runs
    from {{ ref('mart_game_results') }}
),

-- Leakage-guarded raw snapshots, williamhill_us folded into caesars (canonical map).
-- NO book whitelist (vs the mart's 4) — that's the E13.8 widening. game_date is the
-- leakage clock exactly as E3.0b/E4.3 use it.
snaps as (
    select
        year(s.game_date)                                          as season,
        s.game_pk,
        case when lower(s.bookmaker) = 'williamhill_us' then 'caesars'
             else lower(s.bookmaker) end                           as book,
        s.snapshot_ts,
        s.home_win_prob                                            as raw_home,
        s.away_win_prob                                            as raw_away,
        {{ american_to_implied_sql('s.over_price') }}              as impl_over,
        {{ american_to_implied_sql('s.under_price') }}             as impl_under,
        s.total_line
    from {{ source('oddsapi', 'odds_snapshots_historical') }} s
    where s.snapshot_ts < s.game_date                              -- leakage guard
),

-- Last pre-game snapshot per (game_pk, book) = the (conservative) close.
close_snap as (
    select
        season, game_pk, book, total_line,
        raw_home / nullif(raw_home + raw_away, 0)                  as vf_home,
        (raw_home + raw_away) - 1.0                                as h2h_vig,
        impl_over / nullif(impl_over + impl_under, 0)              as vf_over,
        (impl_over + impl_under) - 1.0                             as totals_vig
    from snaps
    qualify row_number() over (partition by game_pk, book
                               order by snapshot_ts desc) = 1
),

pinn_close as (
    select game_pk, vf_home as pinn_vf_home, vf_over as pinn_vf_over
    from close_snap
    where book = 'pinnacle'
),

-- ── H2H per-game rows ─────────────────────────────────────────────────────────
h2h_games as (
    select
        c.season, c.book, c.vf_home, c.h2h_vig as vig,
        r.home_won                              as outcome,
        abs(c.vf_home - p.pinn_vf_home)         as dist_to_sharp
    from close_snap c
    inner join results r    on r.game_pk = c.game_pk
    left  join pinn_close p on p.game_pk = c.game_pk
    where c.vf_home is not null
),

h2h_metrics as (
    select
        book,
        'h2h'                                                      as market_type,
        season,
        count_if(outcome is not null)                             as n_games_brier,
        count(*)                                                  as n_games_priced,
        avg(pow(vf_home - outcome, 2))                            as closing_brier,
        avg(-( outcome      * ln(greatest(least(vf_home, 1 - 1e-6), 1e-6))
             + (1 - outcome) * ln(greatest(least(1 - vf_home, 1 - 1e-6), 1e-6)) )) as closing_log_loss,
        avg(vig)                                                  as mean_vig,
        avg(dist_to_sharp)                                        as mean_abs_dist_to_sharp,
        -- de-vigged favorite hit-rate (drops exact pick-em rows from the numerator)
        avg(case when abs(vf_home - 0.5) < 1e-9 then null
                 when vf_home > 0.5 then outcome
                 else 1 - outcome end)                            as h2h_fav_hit_rate,
        cast(null as float)                                       as line_mae,
        cast(null as float)                                       as line_rmse,
        cast(null as float)                                       as push_rate
    from h2h_games
    where outcome is not null
    group by book, season
),

-- ── Totals per-game rows (vs the book's OWN close line) ───────────────────────
totals_games as (
    select
        c.season, c.book, c.vf_over, c.totals_vig as vig, c.total_line,
        r.total_runs,
        case when r.total_runs > c.total_line then 1
             when r.total_runs < c.total_line then 0
             else null end                                        as outcome,   -- push → null
        abs(c.vf_over - p.pinn_vf_over)                          as dist_to_sharp
    from close_snap c
    inner join results r    on r.game_pk = c.game_pk
    left  join pinn_close p on p.game_pk = c.game_pk
    where c.vf_over is not null
      and c.total_line is not null
),

totals_metrics as (
    select
        book,
        'totals'                                                  as market_type,
        season,
        count_if(outcome is not null)                             as n_games_brier,
        count(*)                                                  as n_games_priced,
        avg(case when outcome is not null then pow(vf_over - outcome, 2) end) as closing_brier,
        avg(case when outcome is not null then
             -( outcome      * ln(greatest(least(vf_over, 1 - 1e-6), 1e-6))
              + (1 - outcome) * ln(greatest(least(1 - vf_over, 1 - 1e-6), 1e-6)) ) end) as closing_log_loss,
        avg(vig)                                                  as mean_vig,
        avg(dist_to_sharp)                                        as mean_abs_dist_to_sharp,
        cast(null as float)                                       as h2h_fav_hit_rate,
        -- line accuracy: how close is the posted NUMBER to realized runs
        avg(abs(total_line - total_runs))                        as line_mae,
        sqrt(avg(pow(total_line - total_runs, 2)))               as line_rmse,
        avg(iff(total_runs = total_line, 1, 0))                  as push_rate
    from totals_games
    group by book, season
)

select * from h2h_metrics
union all
select * from totals_metrics
-- Filter thin cells in the report layer (e.g. n_games_priced >= 150); kept here so
-- the analysis stays a complete per-(book,market,season) census.
order by market_type, book, season
