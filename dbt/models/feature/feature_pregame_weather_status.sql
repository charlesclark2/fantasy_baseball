-- =============================================================================
-- feature_pregame_weather_status.sql
-- Grain: one row per (game_pk, valid_from) — every distinct weather state for
--        a game's pregame forecast. New row only when the forecast changes.
--
-- Observation scope: forecast_pregame only. See stg_weather_raw_snapshots for
-- rationale — mixing observation types creates train/inference distribution
-- mismatch in downstream run_env models.
--
-- Coverage: Epic T.2 conversion date (2026-05-01) onward. Pre-T games have no
-- rows in this table; feature_pregame_weather_features falls back to NULL for
-- those games.
--
-- SCD-2 change detection: md5 hash over (temp_f, wind_component_mph,
-- humidity_pct, condition_text). A new row is only inserted when the hash
-- differs from the previous snapshot — identical re-fetches are collapsed.
--
-- valid_to semantics: NULL means this is the current (latest) forecast.
-- is_current = (valid_to IS NULL).
-- =============================================================================

{{ config(materialized='table') }}

with snapshots as (

    select * from {{ ref('stg_weather_raw_snapshots') }}

),

with_lag as (

    select
        game_pk, venue_id,
        temp_f, wind_speed_mph, wind_direction_deg, humidity_pct,
        condition_text, wind_component_mph, is_dome,
        record_hash, loaded_at,
        lag(record_hash) over (
            partition by game_pk
            order by loaded_at
        ) as prev_hash
    from snapshots

),

change_boundaries as (

    select *
    from with_lag
    where prev_hash is distinct from record_hash

),

with_scd2 as (

    select
        game_pk,
        venue_id,
        temp_f,
        wind_speed_mph,
        wind_direction_deg,
        humidity_pct,
        condition_text,
        wind_component_mph,
        is_dome,
        loaded_at                                           as valid_from,
        lead(loaded_at) over (
            partition by game_pk
            order by loaded_at
        )                                                   as valid_to,
        record_hash,
        sysdate()                                           as computed_at
    from change_boundaries

)

select
    game_pk,
    venue_id,
    temp_f,
    wind_speed_mph,
    wind_direction_deg,
    humidity_pct,
    condition_text,
    wind_component_mph,
    is_dome,
    valid_from,
    valid_to,
    (valid_to is null)  as is_current,
    record_hash,
    computed_at
from with_scd2
