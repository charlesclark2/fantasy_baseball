-- fact_ncaab_team_game — the team-game fact P1's tempo × efficiency model fits on.
--
-- One row per (game, team) with the box line, the shared possession estimate, and the
-- point-in-time-correct conference resolved through dim_ncaab_team's SCD. Efficiency is
-- per-100-possessions, the standard basketball unit.
--
-- ⚠️ DIVISION GUARD. `possessions_est` can be small or zero for an abandoned/forfeited game,
-- and a per-100 rate divided by ~0 produces a finite, enormous, completely fake efficiency
-- that no NULL check would catch. hoopR's own repo records a model incident caused by exactly
-- one zero-possession box row. So the rate is NULL below a floor rather than computed.
{{ config(materialized='table') }}

with box as (select * from {{ ref('stg_ncaab_team_box') }}),
sched as (select * from {{ ref('stg_ncaab_schedule') }}),
dim as (select * from {{ ref('dim_ncaab_team') }})

select
    b.sport,
    b.game_id,
    b.season,
    b.season_type,
    b.game_date,
    b.team_id,
    b.team,
    b.opponent_team_id,
    b.is_home,
    s.neutral_site,
    s.neutral_site_is_trustworthy,
    s.conference_game,
    s.completed,
    s.is_di_matchup,
    -- PIT-correct conference: the team's conference AS OF THIS SEASON, not today's.
    d.conference_id                                   as team_conference_id,
    do_.conference_id                                 as opponent_conference_id,
    b.points,
    b.opponent_points,
    (b.points - b.opponent_points)                    as margin,
    b.won,
    b.fga, b.fgm, b.fg3a, b.fg3m, b.fta, b.ftm,
    b.oreb, b.dreb, b.reb, b.ast, b.stl, b.blk, b.tov, b.pf,
    b.possessions_est,
    case when b.possessions_est >= 20
         then 100.0 * b.points / b.possessions_est end          as off_rating,
    case when b.possessions_est >= 20
         then 100.0 * b.opponent_points / b.possessions_est end as def_rating,
    -- the floor above is a real filter, so say how often it bites rather than hiding it
    (b.possessions_est is null or b.possessions_est < 20)       as possessions_unusable,
    b.capture_timestamp
from box b
left join sched s  on s.game_id = b.game_id
left join dim d    on d.team_id = b.team_id
                  and b.season between d.valid_from_season and coalesce(d.valid_to_season, 9999)
left join dim do_  on do_.team_id = b.opponent_team_id
                  and b.season between do_.valid_from_season and coalesce(do_.valid_to_season, 9999)
