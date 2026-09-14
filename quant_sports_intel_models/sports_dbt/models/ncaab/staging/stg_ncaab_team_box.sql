-- stg_ncaab_team_box — one row per (game, team): the box line tempo x efficiency needs.
--
-- ⭐ POSSESSIONS are computed HERE, once, from the standard identity
--       poss ≈ FGA − ORB + TO + 0.475·FTA
-- so that every downstream consumer shares one definition. Two models each computing "pace"
-- their own way is how two surfaces end up disagreeing about the same game (the
-- two-renderers-of-one-field class), and pace is the spine of the whole NCAAB model.
--
-- ⚠️ `turnovers` and `total_turnovers` BOTH exist in the source and are NOT interchangeable
-- (`team_turnovers` is a third). `turnovers` is the team's own giveaways, which is the term
-- the possession identity wants; the identity is stated above the code so a future editor
-- can check the column against the formula rather than against their memory.
with box as (
    select * from {{ ncaab_delta('team_box') }}
)
select
    'ncaab'                                         as sport,
    game_id::bigint                                 as game_id,
    season::int                                     as season,
    season_type::int                                as season_type,
    game_date::date                                 as game_date,
    team_id::bigint                                 as team_id,
    team_display_name                               as team,
    opponent_team_id::bigint                        as opponent_team_id,
    (team_home_away = 'home')                       as is_home,
    team_score::int                                 as points,
    opponent_team_score::int                        as opponent_points,
    coalesce(team_winner, false)                    as won,
    field_goals_made::int                           as fgm,
    field_goals_attempted::int                      as fga,
    three_point_field_goals_made::int               as fg3m,
    three_point_field_goals_attempted::int          as fg3a,
    free_throws_made::int                           as ftm,
    free_throws_attempted::int                      as fta,
    offensive_rebounds::int                         as oreb,
    defensive_rebounds::int                         as dreb,
    total_rebounds::int                             as reb,
    assists::int                                    as ast,
    steals::int                                     as stl,
    blocks::int                                     as blk,
    turnovers::int                                  as tov,
    fouls::int                                      as pf,
    -- the shared possession definition (see header). NULL in, NULL out — an estimate built on
    -- a missing operand would be a fabricated number wearing a real one's units.
    (field_goals_attempted - offensive_rebounds + turnovers
        + 0.475 * free_throws_attempted)::double    as possessions_est,
    capture_timestamp
from box
where game_id is not null and team_id is not null
