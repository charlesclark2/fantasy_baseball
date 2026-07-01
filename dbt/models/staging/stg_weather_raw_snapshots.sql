-- =============================================================================
-- stg_weather_raw_snapshots.sql
-- Grain: one row per (game_pk, loaded_at) for forecast_pregame observations.
-- Purpose: Feed SCD-2 change detection in feature_pregame_weather_status.
--          Retains ALL ingestion snapshots so weather changes (forecast updates)
--          can be tracked temporally.
--
-- Scope: forecast_pregame only. forecast_intraday and observed_at_first_pitch
--        are excluded here because the downstream feature model was trained
--        exclusively on forecast_pregame data — mixing types creates a
--        train/inference distribution mismatch.
--
-- Coverage: Epic T.2 conversion date (2026-05-01) onward. Pre-T weather
--           history is permanently unrecoverable.
--
-- wind_component_mph computed here (positive = blowing out toward CF,
-- negative = in toward home plate) so the SCD-2 table carries the final
-- feature value and does not require a downstream ref_venues join.
--
-- E11.1-W11 Tier-C lakehouse migration. DuckDB branch reads the weather_raw S3 raw mirror and joins
-- the ref_venues seed (registered as a DuckDB view by run_w1_lakehouse._build_w11c). The Snowflake
-- (else) branch is a thin view over the lakehouse_ext external table (rollback path). ref_venues is
-- referenced by BARE NAME (not a Jinja ref call) in the DuckDB branch because run_w1_lakehouse's
-- Layout-A extractor does not resolve ref() for stg_ models -- the view is pre-registered instead.
-- (Do NOT write an empty ref() with Jinja braces even in a comment: dbt-fusion's lexer evaluates it
--  BEFORE the SQL comment strips, and a zero-arg ref() panics the codegen -- index out of bounds.)
-- loaded_at is read via try_cast(... as timestamp) (INC-23 use-site cast for the mixed bridge/live union).
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w11c_lakehouse']) }}

with source as (

    select
        game_pk::integer                        as game_pk,
        venue_id::integer                       as venue_id,
        try_cast(temp_f as double)              as temp_f,
        try_cast(wind_speed_mph as double)      as wind_speed_mph,
        try_cast(wind_direction_deg as integer) as wind_direction_deg,
        try_cast(humidity_pct as integer)       as humidity_pct,
        condition_text::varchar                 as condition_text,
        try_cast(loaded_at as timestamp)        as loaded_at
    from read_parquet('{{ lakehouse_raw_loc("weather_raw") }}**/*.parquet', union_by_name=true)
    where weather_observation_type = 'forecast_pregame'

),

with_venue as (

    select
        s.*,
        case
            when rv.roof_type in ('open', 'convertible')
                and rv.park_facing_degrees is not null
                then round(
                    s.wind_speed_mph * cos(
                        (s.wind_direction_deg - rv.park_facing_degrees) * pi() / 180
                    ), 2)
            else null
        end                                                 as wind_component_mph,
        case when rv.roof_type = 'fixed' then true else false end as is_dome
    from source s
    left join ref_venues rv using (venue_id)

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
    md5(
        coalesce(cast(temp_f as varchar), '')           || '|' ||
        coalesce(cast(wind_component_mph as varchar), '') || '|' ||
        coalesce(cast(humidity_pct as varchar), '')     || '|' ||
        coalesce(condition_text, '')
    )                                                   as record_hash,
    loaded_at
from with_venue
qualify row_number() over (
    partition by game_pk, loaded_at
    order by temp_f nulls last
) = 1

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.stg_weather_raw_snapshots

{% endif %}
