-- =============================================================================
-- mart_team_schedule_context.sql
-- Grain: one row per team_abbrev × game_pk (regular season only)
-- Purpose: Schedule fatigue context features (days rest, recent game frequency,
--          home/away streak length, timezone/travel signal). Join target for
--          feature_pregame_team_features on team_abbrev + game_pk. No leakage:
--          all values computed from games strictly before the current game_date.
--
-- DuckDB branch (E11.1-W6): reads the migrated mart_game_spine (W5) +
-- stg_statsapi_venues (W6). Snowflake (else) branch is a thin view over the
-- lakehouse_ext external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

with

team_spine as (

    select
        game_pk,
        game_date::date         as game_date,
        game_year::integer      as game_year,
        home_team               as team_abbrev,
        'home'                  as side,
        venue_id
    from mart_game_spine
    where game_type = 'R'

    union all

    select
        game_pk,
        game_date::date,
        game_year::integer,
        away_team,
        'away',
        venue_id
    from mart_game_spine
    where game_type = 'R'

),

venue_tz as (

    select
        venue_id,
        timezone_id,
        timezone_utc_offset,
        latitude,
        longitude
    from stg_statsapi_venues
    qualify row_number() over (partition by venue_id order by ingest_date desc) = 1

),

team_games as (

    select
        ts.game_pk,
        ts.game_date,
        ts.game_year,
        ts.team_abbrev,
        ts.side,
        v.timezone_id,
        v.timezone_utc_offset,
        v.latitude,
        v.longitude
    from team_spine ts
    left join venue_tz v on v.venue_id = ts.venue_id

),

rest_and_frequency as (

    select
        game_pk,
        game_date,
        game_year,
        team_abbrev,
        side,
        timezone_id,
        timezone_utc_offset,
        latitude,
        longitude,

        datediff(
            'day',
            lag(game_date) over (
                partition by team_abbrev, game_year
                order by game_date, game_pk
            ),
            game_date
        )                               as days_rest,

        count(*) over (
            partition by team_abbrev
            order by game_date
            range between interval '7 days' preceding and interval '1 day' preceding
        )                               as games_last_7d,

        count(*) over (
            partition by team_abbrev
            order by game_date
            range between interval '14 days' preceding and interval '1 day' preceding
        )                               as games_last_14d,

        lag(timezone_id) over (
            partition by team_abbrev, game_year
            order by game_date, game_pk
        )                               as prev_timezone_id,

        lag(timezone_utc_offset) over (
            partition by team_abbrev, game_year
            order by game_date, game_pk
        )                               as prev_timezone_utc_offset,

        lag(latitude) over (
            partition by team_abbrev, game_year
            order by game_date, game_pk
        )                               as prev_latitude,

        lag(longitude) over (
            partition by team_abbrev, game_year
            order by game_date, game_pk
        )                               as prev_longitude

    from team_games

),

streak_grouped as (

    select
        *,
        row_number() over (
            partition by team_abbrev, game_year
            order by game_date, game_pk
        )
        - row_number() over (
            partition by team_abbrev, game_year, side
            order by game_date, game_pk
        )                               as streak_group

    from rest_and_frequency

),

getaway_flagged as (

    select
        *,
        coalesce(
            lead(streak_group) over (
                partition by team_abbrev, game_year
                order by game_date, game_pk
            ) != streak_group,
            false
        )::boolean                      as is_getaway_day

    from streak_grouped

),

final as (

    select
        game_pk,
        game_date,
        game_year,
        team_abbrev,
        side,

        days_rest,
        games_last_7d,
        games_last_14d,

        (side = 'home')::boolean        as is_home_game,

        case when side = 'home'
            then row_number() over (
                     partition by team_abbrev, game_year, streak_group
                     order by game_date, game_pk
                 )
        end                             as consecutive_home_games,

        case when side = 'away'
            then row_number() over (
                     partition by team_abbrev, game_year, streak_group
                     order by game_date, game_pk
                 )
        end                             as consecutive_away_games,

        coalesce(
            (prev_timezone_id is not null
             and prev_timezone_id != timezone_id)::boolean,
            false
        )                               as tz_changed_from_last_game,

        case
            when prev_latitude  is not null
             and prev_longitude is not null
             and latitude       is not null
             and longitude      is not null
            then
                2 * 3958.8 * asin(sqrt(
                    pow(sin(radians(latitude  - prev_latitude)  / 2), 2)
                    + cos(radians(prev_latitude)) * cos(radians(latitude))
                    * pow(sin(radians(longitude - prev_longitude) / 2), 2)
                ))
        end                             as travel_distance_miles,

        coalesce(
            abs(timezone_utc_offset - prev_timezone_utc_offset),
            0
        )                               as tz_delta_hours,

        coalesce(
            case when side = 'away'
                then row_number() over (
                         partition by team_abbrev, game_year, streak_group
                         order by game_date, game_pk
                     ) >= 3
            end,
            false
        )::boolean                      as is_3rd_consecutive_road_game,

        is_getaway_day

    from getaway_flagged

)

select * from final

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.mart_team_schedule_context

{% endif %}
