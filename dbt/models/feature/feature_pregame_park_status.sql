{{ config(materialized='table') }}

-- SCD-2 for park factors. Grain: one row per (venue_id, season).
-- Natural key: (venue_id, season) — park factors update once per season.
-- valid_from  = first regular-season game at this venue for the season.
-- valid_to    = first game of next season at this venue (contiguous intervals);
--              NULL for venues active in the current season (is_current = true).
--              Retired venues (last_season < current): valid_to = season_close + 1 day
--              so they are never mis-flagged as is_current.
-- Change-detection hash: eb_park_run_factor, elevation_ft, center_ft, roof_type.
-- No snapshot staging needed — source mart_eb_park_factors is already at annual grain.
-- feature_pregame_park_features NOT re-pointed — game_year-1 leakage guard is correct.

with

-- Season dates per venue from regular-season games
season_dates as (
    select
        venue_id,
        game_year::integer   as season,
        min(game_date::date) as season_open,
        max(game_date::date) as season_close
    from {{ ref('mart_game_results') }}
    where game_type = 'R'
      and venue_id is not null
    group by venue_id, game_year
),

max_season as (
    select max(game_year::integer) as max_season
    from {{ ref('mart_game_results') }}
    where game_type = 'R'
),

-- Most recent physical dimensions per venue (static attributes)
venue_latest as (
    select
        venue_id,
        elevation_ft,
        center_ft,
        roof_type,
        row_number() over (
            partition by venue_id
            order by ingest_date desc
        ) as rn
    from {{ ref('stg_statsapi_venues') }}
),

venues as (
    select * from venue_latest where rn = 1
),

combined as (
    select
        eb.venue_id,
        eb.season,
        eb.eb_park_run_factor,
        eb.shrinkage_factor,
        v.elevation_ft,
        v.center_ft,
        v.roof_type,
        sd.season_open,
        sd.season_close,
        md5(
            coalesce(cast(eb.eb_park_run_factor as varchar), '') || '|' ||
            coalesce(cast(v.elevation_ft        as varchar), '') || '|' ||
            coalesce(cast(v.center_ft           as varchar), '') || '|' ||
            coalesce(cast(v.roof_type           as varchar), '')
        )                   as record_hash,
        sysdate()           as computed_at
    from {{ ref('mart_eb_park_factors') }} eb
    left join venues v
        on  v.venue_id = eb.venue_id
    left join season_dates sd
        on  sd.venue_id = eb.venue_id
        and sd.season   = eb.season
),

with_lead as (
    select
        *,
        lead(season_open) over (
            partition by venue_id
            order by season
        ) as valid_to_lead
    from combined
),

with_valid_to as (
    select
        *,
        case
            -- Next season exists for this venue → use its open date
            when valid_to_lead is not null
                then valid_to_lead
            -- No next season and this is not the current season → retired venue;
            -- close the interval at season end + 1 day so is_current stays false
            when season < (select max_season from max_season)
                then dateadd('day', 1, season_close)
            -- Current season, still active → open-ended (is_current = true)
            else null
        end as valid_to
    from with_lead
)

select
    venue_id,
    season,
    eb_park_run_factor,
    shrinkage_factor,
    elevation_ft,
    center_ft,
    roof_type,
    season_open      as valid_from,
    valid_to,
    record_hash,
    computed_at,
    (valid_to is null) as is_current
from with_valid_to
