-- =============================================================================
-- feature_pregame_park_features.sql
-- Grain: one row per game_pk (regular season games only)
-- Purpose: Pre-game park context features for ML. Joins physical park
--          characteristics (dimensions, elevation, surface, roof) from
--          stg_statsapi_venues and empirical run factors from
--          mart_park_run_factors.
--
-- LEAKAGE GUARD: park run factors join on game_year - 1 (prior season only)
-- so no current-season game results appear in the feature. Physical dimensions
-- from stg_statsapi_venues are static attributes — no leakage risk.
--
-- Nulls: park_run_factor_3yr is null for 2015 games (no 2014 data) and for
-- venues with fewer than 10 games in the prior season (filtered in the mart).
-- venue_id is null for a small number of games with missing venue data.
-- =============================================================================

{{ config(materialized='table') }}

with

games as (
    select
        game_pk,
        game_date,
        game_year::integer  as game_year,
        venue_id
    from {{ ref('mart_game_results') }}
    where game_type = 'R'
),

-- Most recent ingested record per venue (dimensions are static)
venue_latest as (
    select
        venue_id,
        venue_name,
        elevation_ft,
        turf_type,
        roof_type,
        left_line_ft,
        left_ft,
        left_center_ft,
        center_ft,
        right_center_ft,
        right_line_ft,
        row_number() over (
            partition by venue_id
            order by ingest_date desc
        ) as rn
    from {{ ref('stg_statsapi_venues') }}
),

venues as (
    select * from venue_latest where rn = 1
),

-- Prior-season run factors (game_year - 1) — prevents in-season leakage
park_factors as (
    select
        g.game_pk,
        prf.runs_per_game_at_park,
        prf.park_run_factor_3yr
    from games g
    left join {{ ref('mart_park_run_factors') }} prf
        on  prf.venue_id        = g.venue_id
        and prf.game_year       = g.game_year - 1
),

final as (
    select
        g.game_pk,
        g.game_date::date           as game_date,
        g.game_year,
        g.venue_id,
        v.venue_name,

        -- ── Physical park characteristics ─────────────────────────────────────
        v.elevation_ft,
        v.turf_type,
        v.roof_type,
        v.left_line_ft,
        v.left_ft,
        v.left_center_ft,
        v.center_ft,
        v.right_center_ft,
        v.right_line_ft,

        -- ── Prior-season empirical run environment ────────────────────────────
        pf.runs_per_game_at_park,
        pf.park_run_factor_3yr

    from games g
    left join venues v
        on  v.venue_id = g.venue_id
    left join park_factors pf
        on  pf.game_pk = g.game_pk
)

select * from final
