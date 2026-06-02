-- =============================================================================
-- feature_pregame_meta_model_features.sql
-- Grain: one row per (game_pk, market_type) where market_type ∈ {h2h, totals}
--
-- Purpose: Training-ready feature mart for the Epic 12 CLV meta-model.
--          Base rows come from mart_clv_labeled_games; this model enriches each
--          labeled game with all seven feature groups the meta-model will consume.
--          Building the feature pipeline ahead of the training gates ensures it
--          is production-ready when sufficient labels accumulate.
--
-- Feature groups:
--   1. Model signal         — h2h_edge_home, totals_edge, game_conviction_score,
--                             win_prob_ci_width*, totals_p_over_ci_width*
--   2. Signal completeness  — gate_signals_met, signal_completeness_score*
--   3. Line movement        — bovada open/close devig probs, line_movement_devig,
--                             h2h_line_movement, totals_line_movement, snapshot_count
--   4. Bookmaker disagreement — ml_implied_prob_std/range, sharp_soft_ml_spread,
--                             bovada_vs_consensus_h2h, bovada_vs_pinnacle_h2h*,
--                             pinnacle_coverage_flag*
--   5. Timing               — hours_to_first_pitch_at_prediction,
--                             lineup_confirmed_hours_before, prior_age_days*
--   6. Public betting       — over_money_pct, home_ml_money_pct, home_ml_ticket_pct,
--                             ml_sharp_signal, total_sharp_signal
--   7. Sequential posterior — posterior_source*, cell_posterior_source*
--
--   * Columns marked with * are NULL for current data. They will be populated
--     when the upstream source is available (see inline comments).
--
-- Incremental strategy: append + merge by (game_pk, market_type). New game-days
-- are added as CLV label conditions are met. Historical rows are never rebuilt
-- after finalization (all four CLV label conditions met + result available).
--
-- Leakage guard: hours_to_first_pitch_at_prediction must be > 0 for all rows.
-- Enforced by a dbt singular test in dbt/tests/assert_no_leakage_meta_model_features.sql.
-- Post-game labeled rows (predicted_at >= stg_statsapi_games.game_date) are
-- filtered at the labeled CTE level and never enter this table.
--
-- Coverage score denominator: 6 active groups (sequential posterior excluded
-- until Epic 16 ships); update denominator to 7 when posterior_available goes live.
--
-- Sources:
--   mart_clv_labeled_games           — base rows (game_pk, market_type, labels)
--   stg_statsapi_games               — authoritative game start timestamp
--   betting_ml.daily_model_predictions — model signal features
--   mart_odds_line_movement          — line movement, snapshot_count
--   mart_bookmaker_disagreement      — cross-book disagreement metrics
--   mart_game_odds_bridge            — game_pk → event_id mapping
--   mart_odds_consensus              — consensus market probabilities
--   feature_pregame_public_betting_features — public betting pcts
--   stg_statsapi_lineups             — lineup confirmation timing
-- =============================================================================

{{ config(
    materialized='incremental',
    unique_key=['game_pk', 'market_type'],
    incremental_strategy='merge'
) }}

with

-- Authoritative game start timestamp. Used for leakage guard and timing features.
-- Avoids relying on daily_model_predictions.game_datetime which can be NULL.
game_schedule as (
    select
        game_pk,
        game_date as game_datetime
    from {{ ref('stg_statsapi_games') }}
),

labeled as (
    select l.*
    from {{ ref('mart_clv_labeled_games') }} l
    inner join game_schedule gs on gs.game_pk = l.game_pk
    -- Only include rows where the canonical prediction was genuinely pre-game.
    -- Post-game reruns produce negative hours_to_first_pitch and should not
    -- be used as training observations.
    where l.predicted_at < gs.game_datetime
    {% if is_incremental() %}
    and l.game_date >= (select max(game_date) from {{ this }}) - interval '7 days'
    {% endif %}
),

-- Canonical pre-game prediction matched by exact inserted_at to the row
-- mart_clv_labeled_games selected. Joining against distinct (game_pk, predicted_at)
-- prevents fanout when labeled has two market_type rows per game_pk.
-- Dedup handles the edge case where morning + post_lineup share a batch timestamp.
raw_prediction as (
    select
        p.*,
        row_number() over (
            partition by p.game_pk
            order by
                case when p.prediction_type = 'post_lineup' then 1 else 2 end
        ) as _rn
    from {{ source('betting_ml', 'daily_model_predictions') }} as p
    inner join (
        select distinct game_pk, predicted_at
        from labeled
    ) as l
        on  l.game_pk = p.game_pk
        and p.inserted_at = l.predicted_at
    where p.prediction_type in ('morning', 'post_lineup')
),

prediction as (
    select
        game_pk,
        h2h_edge                    as h2h_edge_home,
        totals_edge,
        game_conviction_score,
        gate_signals_met,
        -- win_prob_ci_width and totals_p_over_ci_width are not yet columns in
        -- daily_model_predictions; will be added in a future model update.
        null::float                 as win_prob_ci_width,
        null::float                 as totals_p_over_ci_width,
        -- signal_completeness_score not yet in daily_model_predictions.
        null::float                 as signal_completeness_score
    from raw_prediction
    where _rn = 1
),

-- Line movement for Bovada (currently the only bookmaker in this mart).
line_movement as (
    select
        game_pk,
        h2h_line_movement,
        total_line_movement         as totals_line_movement,
        snapshot_count
    from {{ ref('mart_odds_line_movement') }}
    where bookmaker = 'bovada'
),

bk_disagreement as (
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

-- game_pk → event_id bridge for joining mart_odds_consensus
bridge as (
    select game_pk, event_id
    from {{ ref('mart_game_odds_bridge') }}
),

consensus as (
    select
        b.game_pk,
        c.home_win_prob_consensus,
        c.over_prob_consensus,
        c.sharp_soft_ml_delta,
        c.ml_consensus_std
    from bridge b
    inner join {{ ref('mart_odds_consensus') }} c on c.event_id = b.event_id
),

public_betting as (
    select
        game_pk,
        over_money_pct,
        home_ml_money_pct,
        home_ml_ticket_pct,
        ml_sharp_signal,
        total_sharp_signal
    from {{ ref('feature_pregame_public_betting_features') }}
),

-- Lineup confirmation proxy: earliest ingestion timestamp for each game's lineups.
-- lineup_confirmed_hours_before = how many hours before first pitch lineups appeared.
lineup_timing as (
    select
        game_pk,
        min(ingestion_ts) as lineup_first_seen_ts
    from {{ ref('stg_statsapi_lineups') }}
    group by game_pk
),

final as (
    select

        -- ── Grain ────────────────────────────────────────────────────────────────
        l.game_pk,
        l.game_date,
        l.market_type,
        l.predicted_at,

        -- ── CLV label passthrough (from mart_clv_labeled_games) ──────────────────
        l.model_edge,
        l.clv,
        l.clv_positive,
        l.actual_outcome,

        -- ── Group 1: Model signal ─────────────────────────────────────────────────
        p.h2h_edge_home,
        p.totals_edge,
        p.game_conviction_score,
        p.win_prob_ci_width,
        p.totals_p_over_ci_width,
        (p.h2h_edge_home is not null)::boolean                              as model_signal_available,

        -- ── Group 2: Signal completeness ──────────────────────────────────────────
        p.gate_signals_met,
        p.signal_completeness_score,
        (p.gate_signals_met is not null)::boolean                           as signal_completeness_available,

        -- ── Group 3: Line movement ────────────────────────────────────────────────
        l.bovada_open_devig_prob,
        l.bovada_close_devig_prob,
        -- Signed movement: positive = market moved toward reference side (home/over)
        l.bovada_close_devig_prob - l.bovada_open_devig_prob               as line_movement_devig,
        lm.h2h_line_movement,
        lm.totals_line_movement,
        lm.snapshot_count,
        (lm.snapshot_count is not null)::boolean                            as line_movement_available,

        -- ── Group 4: Bookmaker disagreement ──────────────────────────────────────
        bd.ml_implied_prob_std,
        bd.ml_implied_prob_range,
        bd.totals_line_std,
        bd.totals_line_range,
        bd.sharp_soft_ml_spread,
        bd.n_books_available,
        bd.stale_book_flag,
        -- Bovada close devig minus consensus home win prob (h2h rows only)
        case
            when l.market_type = 'h2h'
                then l.bovada_close_devig_prob - con.home_win_prob_consensus
        end                                                                  as bovada_vs_consensus_h2h,
        con.sharp_soft_ml_delta,
        con.ml_consensus_std,
        -- Pinnacle data not yet in a clean mart; populated in a future update
        -- when mlb_matches_raw Pinnacle JSON is extracted into a processed mart.
        null::float                                                          as bovada_vs_pinnacle_h2h,
        false::boolean                                                       as pinnacle_coverage_flag,
        (bd.ml_implied_prob_std is not null)::boolean                       as bookmaker_disagreement_available,

        -- ── Group 5: Timing ───────────────────────────────────────────────────────
        -- Uses stg_statsapi_games.game_date (authoritative) not daily_model_predictions.game_datetime
        -- which can be NULL. l.predicted_at < gs.game_datetime is guaranteed by the
        -- labeled CTE filter, so this value is always >= 0 for non-null rows.
        datediff(hour, l.predicted_at, gs.game_datetime)                    as hours_to_first_pitch_at_prediction,
        datediff(hour, lt.lineup_first_seen_ts, gs.game_datetime)           as lineup_confirmed_hours_before,
        -- prior_age_days: Epic 16 posteriors not yet built
        null::float                                                          as prior_age_days,
        (gs.game_datetime is not null)::boolean                             as timing_available,

        -- ── Group 6: Public betting ───────────────────────────────────────────────
        pb.over_money_pct,
        pb.home_ml_money_pct,
        pb.home_ml_ticket_pct,
        pb.ml_sharp_signal,
        pb.total_sharp_signal,
        (pb.home_ml_money_pct is not null)::boolean                         as public_betting_available,

        -- ── Group 7: Sequential posterior (Epic 16 / Epic 8.5 — not yet built) ───
        null::text                                                           as posterior_source,
        null::text                                                           as cell_posterior_source,
        false::boolean                                                       as posterior_available,

        -- ── Coverage score ────────────────────────────────────────────────────────
        -- Denominator = 6 active groups; update to 7 when posterior_available goes live.
        round(
            (
                (p.h2h_edge_home is not null)::integer
                + (p.gate_signals_met is not null)::integer
                + (lm.snapshot_count is not null)::integer
                + (bd.ml_implied_prob_std is not null)::integer
                + (gs.game_datetime is not null)::integer
                + (pb.home_ml_money_pct is not null)::integer
            ) / 6.0,
            4
        )                                                                    as coverage_score,

        -- ── Training eligibility ──────────────────────────────────────────────────
        -- True when coverage_score ≥ 0.60 AND both primary edges are available.
        (
            (
                (p.h2h_edge_home is not null)::integer
                + (p.gate_signals_met is not null)::integer
                + (lm.snapshot_count is not null)::integer
                + (bd.ml_implied_prob_std is not null)::integer
                + (gs.game_datetime is not null)::integer
                + (pb.home_ml_money_pct is not null)::integer
            ) / 6.0 >= 0.60
            and p.h2h_edge_home is not null
            and p.totals_edge is not null
        )::boolean                                                           as training_eligible

    from labeled l
    inner join game_schedule gs
        on  gs.game_pk = l.game_pk
    left join prediction p
        on  p.game_pk = l.game_pk
    left join line_movement lm
        on  lm.game_pk = l.game_pk
    left join bk_disagreement bd
        on  bd.game_pk = l.game_pk
    left join consensus con
        on  con.game_pk = l.game_pk
    left join public_betting pb
        on  pb.game_pk = l.game_pk
    left join lineup_timing lt
        on  lt.game_pk = l.game_pk
)

select * from final
