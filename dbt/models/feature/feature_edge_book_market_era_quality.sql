-- =============================================================================
-- feature_edge_book_market_era_quality.sql   (Edge Program — Story E3.0b)
-- Grain: one row per (book, market_type, season), book ∈ {pinnacle,bovada,caesars,
--        fanduel}, market_type ∈ {h2h, totals}.
--
-- NAME NOTE: Edge-scoped relation (prefix feature_edge_) so it can never collide
-- with a pre-existing product model — same convention as feature_pregame_edge_market.
--
-- Purpose (E3.0b): bookmaker line-quality DRIFT over time + a RECENCY-QUALITY weight.
--   Books keep sharpening their own lines, so an old soft-era line is a weaker
--   benchmark than a recent one. Treating all historical odds as equally informative
--   biases every market backtest (E3/E4) — the E4 sharp-anchor CLV signal is strong
--   in 2021–2023 but DECAYS in 2025 as soft books got sharper. This model surfaces
--   that trend (the report) and emits a per-(book,market,era) sample weight that
--   DOWN-WEIGHTS stale eras so the E4.3 backtest leans on the current regime, not the
--   easy early years.
--
-- Metrics per (book, market, season), all on the CLOSE (last pre-game snapshot):
--   n_games                 — games with a usable close + outcome
--   closing_brier           — mean (fair_prob − outcome)^2  (lower = sharper)
--   closing_log_loss        — mean −[y·ln p + (1−y)·ln(1−p)] (lower = sharper)
--   mean_vig                — mean two-way overround at close (lower = sharper)
--   mean_abs_dist_to_sharp  — mean |book_fair − pinnacle_fair| at close (vs the sharp
--                             consensus; 0 for pinnacle itself by construction)
--   recency_quality_weight  — exp(−λ·(max_season − season)) ∈ (0,1]; newest era = 1.0.
--                             λ = var('edge_recency_lambda', default 0.35).
--
-- Reference side: h2h = home; totals = over. Outcomes: h2h home win; totals
-- (home+away runs) vs the book's OWN close line (pushes excluded).
--
-- Leakage note: this is an EVAL/weighting artifact (per-era summary stats), not a
-- per-game serving feature. Every snapshot is still guarded < commence_time. The
-- weight is a function of season only → parity-safe, no game-level leakage.
--
-- Advisory/transparency only — no column asserts a +EV bet (honest-framing rule).
--
-- Sources:
--   oddsapi.odds_snapshots_historical — per-book per-snapshot prices (de-vig inputs)
--   stg_statsapi_games                — commence_time (leakage clock) + season
--   mart_game_results                 — realized outcomes
-- =============================================================================

{{ config(materialized='table') }}

{% set lam = var('edge_recency_lambda', 0.35) %}

with

game_times as (
    select
        game_pk,
        game_date                 as commence_time,
        year(game_date)           as season
    from {{ ref('stg_statsapi_games') }}
),

results as (
    select
        game_pk,
        iff(home_team_won, 1, 0)                       as home_won,
        (home_final_score + away_final_score)          as total_runs
    from {{ ref('mart_game_results') }}
),

-- Canonical-book, leakage-guarded raw snapshots (one row carries BOTH markets).
snaps as (
    select
        gt.season,
        gt.commence_time,
        s.game_pk,
        case when lower(s.bookmaker) = 'williamhill_us' then 'caesars'
             else lower(s.bookmaker) end                          as book,
        s.snapshot_ts,
        -- h2h: home_win_prob/away_win_prob are RAW implied already
        s.home_win_prob                                            as raw_home,
        s.away_win_prob                                            as raw_away,
        -- totals: convert American over/under → implied (vig-included)
        {{ american_to_implied_sql('s.over_price') }}             as impl_over,
        {{ american_to_implied_sql('s.under_price') }}            as impl_under,
        s.total_line
    from {{ source('oddsapi', 'odds_snapshots_historical') }} s
    inner join game_times gt on gt.game_pk = s.game_pk
    where lower(s.bookmaker) in ('pinnacle', 'bovada', 'caesars', 'fanduel', 'williamhill_us')
      and s.snapshot_ts < gt.commence_time          -- leakage guard
),

-- Last pre-game snapshot per (game_pk, book) = the close.
close_snap as (
    select
        season, game_pk, book, total_line,
        -- de-vigged fair of the reference side
        raw_home / nullif(raw_home + raw_away, 0)                 as vf_home,
        (raw_home + raw_away) - 1.0                               as h2h_vig,
        impl_over / nullif(impl_over + impl_under, 0)             as vf_over,
        (impl_over + impl_under) - 1.0                            as totals_vig
    from snaps
    qualify row_number() over (partition by game_pk, book
                               order by snapshot_ts desc) = 1
),

-- Pinnacle close per game = the sharp consensus benchmark.
pinn_close as (
    select game_pk, vf_home as pinn_vf_home, vf_over as pinn_vf_over
    from close_snap
    where book = 'pinnacle'
),

-- ── Per-game h2h rows (book × game) with outcome + sharp distance ─────────────
h2h_games as (
    select
        c.season,
        c.book,
        c.vf_home,
        c.h2h_vig                                                 as vig,
        r.home_won                                                as outcome,
        abs(c.vf_home - p.pinn_vf_home)                          as dist_to_sharp
    from close_snap c
    inner join results r   on r.game_pk = c.game_pk
    left  join pinn_close p on p.game_pk = c.game_pk
    where c.vf_home is not null
),

-- ── Per-game totals rows (book × game) vs the book's OWN close line ───────────
totals_games as (
    select
        c.season,
        c.book,
        c.vf_over,
        c.totals_vig                                              as vig,
        case when r.total_runs > c.total_line then 1
             when r.total_runs < c.total_line then 0
             else null end                                        as outcome,   -- push → null
        abs(c.vf_over - p.pinn_vf_over)                          as dist_to_sharp
    from close_snap c
    inner join results r   on r.game_pk = c.game_pk
    left  join pinn_close p on p.game_pk = c.game_pk
    where c.vf_over is not null
      and c.total_line is not null
),

-- ── Aggregate to (book, market, season) ──────────────────────────────────────
h2h_metrics as (
    select
        book,
        'h2h'                                                     as market_type,
        season,
        count_if(outcome is not null)                            as n_games,
        avg(pow(vf_home - outcome, 2))                           as closing_brier,
        avg(-( outcome      * ln(greatest(least(vf_home, 1 - 1e-6), 1e-6))
             + (1 - outcome) * ln(greatest(least(1 - vf_home, 1 - 1e-6), 1e-6)) )) as closing_log_loss,
        avg(vig)                                                 as mean_vig,
        avg(dist_to_sharp)                                       as mean_abs_dist_to_sharp
    from h2h_games
    where outcome is not null
    group by book, season
),

totals_metrics as (
    select
        book,
        'totals'                                                 as market_type,
        season,
        count_if(outcome is not null)                            as n_games,
        avg(pow(vf_over - outcome, 2))                           as closing_brier,
        avg(-( outcome      * ln(greatest(least(vf_over, 1 - 1e-6), 1e-6))
             + (1 - outcome) * ln(greatest(least(1 - vf_over, 1 - 1e-6), 1e-6)) )) as closing_log_loss,
        avg(vig)                                                 as mean_vig,
        avg(dist_to_sharp)                                       as mean_abs_dist_to_sharp
    from totals_games
    where outcome is not null
    group by book, season
),

unioned as (
    select * from h2h_metrics
    union all
    select * from totals_metrics
),

max_season as (
    select max(season) as max_season from unioned
)

select
    u.book,
    u.market_type,
    u.season,
    u.n_games,
    u.closing_brier,
    u.closing_log_loss,
    u.mean_vig,
    u.mean_abs_dist_to_sharp,
    -- Recency-quality weight: newest era = 1.0, older eras decay. DOWN-WEIGHTS the
    -- pre-improvement soft era of any book that has since sharpened (E3.0b AC).
    exp(-{{ lam }} * (m.max_season - u.season))                  as recency_quality_weight,
    current_timestamp()::timestamp_ntz                          as computed_at
from unioned u
cross join max_season m
order by u.market_type, u.book, u.season
