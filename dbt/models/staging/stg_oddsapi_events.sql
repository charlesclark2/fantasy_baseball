{{
    config(
        materialized='table'
    )
}}

-- Grain: one row per event_id (latest ingestion snapshot).
-- Source: baseball_data.oddsapi.mlb_events_raw stores the full API response
-- array as a single VARIANT row per ingestion run. Lateral flatten expands
-- that array to one row per event per run; deduplication then collapses to the
-- most recent snapshot per event_id.

with events_flattened as (

    select
        src.ingestion_ts,
        src.load_id,
        src.x_requests_used,
        src.x_requests_remaining,
        evt.value                                       as event
    from {{ source('oddsapi', 'mlb_events_raw') }} src,
    lateral flatten(input => src.raw_json) evt
    where src.raw_json is not null
      and typeof(src.raw_json) = 'ARRAY'
      and array_size(src.raw_json) > 0

),

-- Keep only the most recent ingestion for each event_id. Events are schedule
-- data and stable; the latest snapshot is always the correct one.
deduped as (

    select
        *,
        row_number() over (
            partition by event:id::varchar
            order by ingestion_ts desc
        ) as _rn
    from events_flattened

)

select
    -- Ingestion metadata
    ingestion_ts,
    load_id,
    x_requests_used,
    x_requests_remaining,

    -- Event fields
    event:id::varchar                                   as event_id,
    event:sport_key::varchar                            as sport_key,
    event:sport_title::varchar                          as sport_title,
    event:commence_time::timestamp_ntz                  as commence_time,
    event:home_team::varchar                            as home_team,
    event:away_team::varchar                            as away_team

from deduped
where _rn = 1
