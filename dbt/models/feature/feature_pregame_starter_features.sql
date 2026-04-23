-- =============================================================================
-- feature_pregame_starter_features.sql
-- Grain: one row per game_pk × pitcher_id (confirmed probable starters only)
-- Purpose: Pre-game starter features for ML. Provides rolling pitcher stats,
--          days rest, handedness, and prior-season platoon splits.
--
-- LEAKAGE GUARD: all joins use rs.game_date::date < pp.game_date (strictly
-- less than). Platoon splits use prior season (game_year - 1) to avoid
-- in-season leakage from full-season aggregates.
--
-- has_starter_data = false when the pitcher has no prior Statcast history
-- (e.g. MLB debut). Rows with null probable_pitcher_id are excluded — the
-- master assembly (feature_pregame_game_features) LEFT JOINs this model and
-- detects missing starters via null.
-- =============================================================================

{{ config(materialized='table') }}

with

probable_pitchers as (
    select
        game_pk,
        game_date,
        side,
        probable_pitcher_id     as pitcher_id,
        probable_pitcher_name   as pitcher_name
    from {{ ref('stg_statsapi_probable_pitchers') }}
    where probable_pitcher_id is not null
),

-- Most recent pre-game rolling stats row per pitcher (LEAKAGE GUARD applied)
rolling_ranked as (
    select
        pp.game_pk,
        pp.pitcher_id,
        rs.pitcher_hand,
        rs.game_date                        as stats_game_date,

        -- 7-day rolling
        rs.k_pct_7d,
        rs.bb_pct_7d,
        rs.xwoba_against_7d,
        rs.hard_hit_pct_7d,
        rs.barrel_pct_7d,
        rs.whiff_rate_7d,
        rs.batter_chase_rate_7d,
        rs.avg_fastball_velo_7d,

        -- 14-day rolling
        rs.k_pct_14d,
        rs.bb_pct_14d,
        rs.xwoba_against_14d,
        rs.hard_hit_pct_14d,
        rs.barrel_pct_14d,
        rs.whiff_rate_14d,
        rs.batter_chase_rate_14d,
        rs.avg_fastball_velo_14d,

        -- 30-day rolling
        rs.k_pct_30d,
        rs.bb_pct_30d,
        rs.xwoba_against_30d,
        rs.hard_hit_pct_30d,
        rs.barrel_pct_30d,
        rs.whiff_rate_30d,
        rs.batter_chase_rate_30d,
        rs.avg_fastball_velo_30d,

        -- Season-to-date
        rs.k_pct_std,
        rs.bb_pct_std,
        rs.xwoba_against_std,
        rs.hard_hit_pct_std,
        rs.barrel_pct_std,
        rs.whiff_rate_std,
        rs.batter_chase_rate_std,
        rs.avg_fastball_velo_std,

        row_number() over (
            partition by pp.game_pk, pp.pitcher_id
            order by rs.game_date::date desc
        )                                   as rn

    from probable_pitchers pp
    left join {{ ref('mart_pitcher_rolling_stats') }} rs
        on  rs.pitcher_id       = pp.pitcher_id
        and rs.game_date::date  < pp.game_date   -- LEAKAGE GUARD
),

pre_game_rolling as (
    select * from rolling_ranked where rn = 1
),

-- Days since most recent start (from game log, not rolling stats — relievers
-- don't reset the rest clock for starters)
prior_start as (
    select
        pp.game_pk,
        pp.pitcher_id,
        max(gl.game_date::date)             as last_start_date
    from probable_pitchers pp
    left join {{ ref('mart_starting_pitcher_game_log') }} gl
        on  gl.pitcher_id       = pp.pitcher_id
        and gl.game_date::date  < pp.game_date
    group by pp.game_pk, pp.pitcher_id
),

-- Prior-season platoon splits vs LHB (game_year - 1 to prevent in-season leakage)
platoon_lhb as (
    select
        pp.game_pk,
        pp.pitcher_id,
        hs.k_pct                            as k_pct_vs_lhb,
        hs.bb_pct                           as bb_pct_vs_lhb,
        hs.xwoba_against                    as xwoba_vs_lhb,
        hs.whiff_rate                       as whiff_rate_vs_lhb
    from probable_pitchers pp
    left join {{ ref('mart_pitcher_vs_handedness_splits') }} hs
        on  hs.pitcher_id   = pp.pitcher_id
        and hs.batter_hand  = 'L'
        and hs.game_year    = year(pp.game_date) - 1
),

-- Prior-season platoon splits vs RHB
platoon_rhb as (
    select
        pp.game_pk,
        pp.pitcher_id,
        hs.k_pct                            as k_pct_vs_rhb,
        hs.bb_pct                           as bb_pct_vs_rhb,
        hs.xwoba_against                    as xwoba_vs_rhb,
        hs.whiff_rate                       as whiff_rate_vs_rhb
    from probable_pitchers pp
    left join {{ ref('mart_pitcher_vs_handedness_splits') }} hs
        on  hs.pitcher_id   = pp.pitcher_id
        and hs.batter_hand  = 'R'
        and hs.game_year    = year(pp.game_date) - 1
),

final as (
    select
        pp.game_pk,
        pp.game_date,
        year(pp.game_date)                  as game_year,
        pp.side,
        pp.pitcher_id,
        pp.pitcher_name,
        pgr.pitcher_hand,

        -- False for debut pitchers with no prior Statcast history
        (pgr.stats_game_date is not null)::boolean  as has_starter_data,

        -- Days since last start (null if no prior starts in the dataset)
        datediff('day', ps.last_start_date, pp.game_date)   as days_rest,

        -- ── 7-day rolling ────────────────────────────────────────────────────
        pgr.k_pct_7d,
        pgr.bb_pct_7d,
        pgr.xwoba_against_7d,
        pgr.hard_hit_pct_7d,
        pgr.barrel_pct_7d,
        pgr.whiff_rate_7d,
        pgr.batter_chase_rate_7d,
        pgr.avg_fastball_velo_7d,

        -- ── 14-day rolling ───────────────────────────────────────────────────
        pgr.k_pct_14d,
        pgr.bb_pct_14d,
        pgr.xwoba_against_14d,
        pgr.hard_hit_pct_14d,
        pgr.barrel_pct_14d,
        pgr.whiff_rate_14d,
        pgr.batter_chase_rate_14d,
        pgr.avg_fastball_velo_14d,

        -- ── 30-day rolling ───────────────────────────────────────────────────
        pgr.k_pct_30d,
        pgr.bb_pct_30d,
        pgr.xwoba_against_30d,
        pgr.hard_hit_pct_30d,
        pgr.barrel_pct_30d,
        pgr.whiff_rate_30d,
        pgr.batter_chase_rate_30d,
        pgr.avg_fastball_velo_30d,

        -- ── Season-to-date ───────────────────────────────────────────────────
        pgr.k_pct_std,
        pgr.bb_pct_std,
        pgr.xwoba_against_std,
        pgr.hard_hit_pct_std,
        pgr.barrel_pct_std,
        pgr.whiff_rate_std,
        pgr.batter_chase_rate_std,
        pgr.avg_fastball_velo_std,

        -- ── Fastball velocity trend (positive = velocity trending up) ────────
        round(pgr.avg_fastball_velo_7d - pgr.avg_fastball_velo_30d, 1) as fastball_velo_trend,

        -- ── Prior-season platoon splits vs LHB ───────────────────────────────
        pl.k_pct_vs_lhb,
        pl.bb_pct_vs_lhb,
        pl.xwoba_vs_lhb,
        pl.whiff_rate_vs_lhb,

        -- ── Prior-season platoon splits vs RHB ───────────────────────────────
        pr.k_pct_vs_rhb,
        pr.bb_pct_vs_rhb,
        pr.xwoba_vs_rhb,
        pr.whiff_rate_vs_rhb

    from probable_pitchers pp
    left join pre_game_rolling pgr
        on  pgr.game_pk     = pp.game_pk
        and pgr.pitcher_id  = pp.pitcher_id
    left join prior_start ps
        on  ps.game_pk      = pp.game_pk
        and ps.pitcher_id   = pp.pitcher_id
    left join platoon_lhb pl
        on  pl.game_pk      = pp.game_pk
        and pl.pitcher_id   = pp.pitcher_id
    left join platoon_rhb pr
        on  pr.game_pk      = pp.game_pk
        and pr.pitcher_id   = pp.pitcher_id
)

select * from final
