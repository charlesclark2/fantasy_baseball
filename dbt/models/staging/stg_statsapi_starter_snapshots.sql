-- =============================================================================
-- stg_statsapi_starter_snapshots.sql
-- Grain: one row per (game_pk, side, ingestion_ts) — every ingestion snapshot,
--        not just the latest.
-- Purpose: Feed SCD-2 change detection in feature_pregame_starter_status.
--          Unlike stg_statsapi_probable_pitchers, this model retains all
--          ingestion snapshots so that probable starter changes (scratches) can
--          be tracked temporally.
--
-- Pre-Epic-T rows (ingestion_ts IS NULL in source) are assigned the sentinel
-- value 1970-01-01 00:00:00 so they appear as the "first known state" and are
-- not dropped during SCD-2 interval computation.
--
-- Dedup note: the same game can appear in two monthly_schedule rows at the same
-- ingestion_ts (e.g., May and June monthly API fetches run simultaneously).
-- QUALIFY keeps one row per (game_pk, side, ingestion_ts), preferring non-null
-- probable_pitcher_id; when both non-null, picks the lower ID deterministically.
--
-- Coverage: full history from monthly_schedule inception.
-- =============================================================================

{{ config(materialized='table') }}

with source as (

    select json_field, ingestion_ts
    from {{ source('statsapi', 'monthly_schedule') }}

),

dates_flattened as (

    select d.value as date_obj, ingestion_ts
    from source,
    lateral flatten(input => json_field:dates) d

),

games_flattened as (

    select g.value as game, ingestion_ts
    from dates_flattened,
    lateral flatten(input => date_obj:games) g

),

home_side as (

    select
        game:gamePk::integer                                        as game_pk,
        game:officialDate::date                                     as game_date,
        'home'                                                      as side,
        game:teams:home:probablePitcher:id::integer                 as probable_pitcher_id,
        game:teams:home:probablePitcher:fullName::varchar           as probable_pitcher_name,
        coalesce(ingestion_ts, '1970-01-01 00:00:00'::timestamp_ntz) as ingestion_ts
    from games_flattened

),

away_side as (

    select
        game:gamePk::integer                                        as game_pk,
        game:officialDate::date                                     as game_date,
        'away'                                                      as side,
        game:teams:away:probablePitcher:id::integer                 as probable_pitcher_id,
        game:teams:away:probablePitcher:fullName::varchar           as probable_pitcher_name,
        coalesce(ingestion_ts, '1970-01-01 00:00:00'::timestamp_ntz) as ingestion_ts
    from games_flattened

),

combined as (

    select * from home_side
    union all
    select * from away_side

)

select *
from combined
qualify row_number() over (
    partition by game_pk, side, ingestion_ts
    order by probable_pitcher_id nulls last
) = 1
