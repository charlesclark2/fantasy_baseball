{{
    config(
        materialized='table'
    )
}}

with source as (
    select json_field
    from {{ source('statsapi', 'monthly_schedule') }}
),

dates_flattened as (
    select
        d.value as date_obj
    from source,
    lateral flatten(input => json_field:dates) d
),

games_flattened as (
    select
        g.value as game
    from dates_flattened,
    lateral flatten(input => date_obj:games) g
)

select
    -- Primary identifiers
    game:gamePk::integer                                    as game_pk,
    game:gameGuid::varchar                                  as game_guid,

    -- Game metadata
    game:gameType::varchar                                  as game_type,
    game:season::integer                                    as season,
    game:gameDate::timestamp_tz                             as game_date,
    game:officialDate::date                                 as official_date,
    game:dayNight::varchar                                  as day_night,
    game:doubleHeader::varchar                              as double_header,
    game:gameNumber::integer                                as game_number,
    game:gamesInSeries::integer                             as games_in_series,
    game:seriesGameNumber::integer                          as series_game_number,
    game:seriesDescription::varchar                         as series_description,
    game:scheduledInnings::integer                          as scheduled_innings,
    game:isTie::boolean                                     as is_tie,

    -- Game status
    game:status:abstractGameState::varchar                  as abstract_game_state,
    game:status:detailedState::varchar                      as detailed_state,
    game:status:statusCode::varchar                         as status_code,

    -- Home team
    game:teams:home:team:id::integer                        as home_team_id,
    game:teams:home:team:name::varchar                      as home_team_name,
    game:teams:home:score::integer                          as home_score,
    game:teams:home:isWinner::boolean                       as home_is_winner,
    game:teams:home:leagueRecord:wins::integer              as home_wins,
    game:teams:home:leagueRecord:losses::integer            as home_losses,

    -- Away team
    game:teams:away:team:id::integer                        as away_team_id,
    game:teams:away:team:name::varchar                      as away_team_name,
    game:teams:away:score::integer                          as away_score,
    game:teams:away:isWinner::boolean                       as away_is_winner,
    game:teams:away:leagueRecord:wins::integer              as away_wins,
    game:teams:away:leagueRecord:losses::integer            as away_losses,

    -- Venue
    game:venue:id::integer                                  as venue_id,
    game:venue:name::varchar                                as venue_name

from games_flattened
