-- =============================================================================
-- feature_pregame_starter_status.sql
-- Grain: one row per (game_pk, side, valid_from) — one SCD-2 row per distinct
--        projected starter per team per game.
-- Source: stg_statsapi_starter_snapshots
-- Epic 15, Story 15.4 — Projected starter SCD-2
-- =============================================================================
-- Tracks changes to the projected starting pitcher between ingestion snapshots.
-- A new SCD-2 row is created each time probable_pitcher_id changes for a given
-- (game_pk, side). Unchanged snapshots between changes are collapsed.
--
-- Point-in-time join pattern (use is_current = false for historical replay):
--   ON  ss.game_pk    = game_pk
--   AND ss.side       = side
--   AND ss.valid_from <= :prediction_ts
--   AND (ss.valid_to  >  :prediction_ts OR ss.valid_to IS NULL)
--
-- Coverage: full history from monthly_schedule inception.
-- SCD-2 temporal resolution only available post-Epic-T (2026-05-12). Pre-Epic-T
-- rows carry sentinel valid_from = 1970-01-01 and represent a single "first
-- known state" snapshot with no change history.
-- =============================================================================

{{ config(materialized='table') }}

with

snapshots as (
    select * from {{ ref('stg_statsapi_starter_snapshots') }}
),

-- Compare each pitcher to the prior ingestion for the same (game_pk, side).
-- Rows where the pitcher is unchanged are skipped; only boundaries matter.
with_lag as (
    select
        game_pk,
        game_date,
        side,
        probable_pitcher_id,
        probable_pitcher_name,
        ingestion_ts,
        lag(probable_pitcher_id) over (
            partition by game_pk, side
            order by ingestion_ts
        ) as prev_pitcher_id
    from snapshots
),

-- First snapshot per (game_pk, side) always opens a row; subsequent rows only
-- when probable_pitcher_id actually changed (IS DISTINCT FROM handles NULLs).
change_boundaries as (
    select *
    from with_lag
    where prev_pitcher_id is distinct from probable_pitcher_id
),

-- LEAD gives the next change timestamp for the same (game_pk, side); NULL = still current.
with_scd2 as (
    select
        game_pk,
        game_date,
        side,
        probable_pitcher_id                                             as starter_player_id,
        probable_pitcher_name                                           as starter_player_name,
        ingestion_ts                                                    as valid_from,
        lead(ingestion_ts) over (
            partition by game_pk, side
            order by ingestion_ts
        )                                                               as valid_to,
        md5(coalesce(cast(probable_pitcher_id as varchar), ''))         as record_hash,
        sysdate()                                                       as computed_at
    from change_boundaries
)

select
    game_pk,
    game_date,
    side,
    starter_player_id,
    starter_player_name,
    valid_from,
    valid_to,
    (valid_to is null)  as is_current,
    record_hash,
    computed_at
from with_scd2
