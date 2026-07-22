-- rollup_nfl_team_season — the season-final team rollup (NFL-N1.0).
--
-- GRAIN: one row per (season, team). The team's COMPLETE season: record, scoring, pbp efficiency
--   (garbage-time-excluded), pace, box.
--
-- ⛔⛔ NOT PREGAME-SAFE FOR ITS OWN SEASON. It includes every game the team played, including games
--   that had not happened yet at any point in that season. Joining it to a game in season S by
--   (S, team) leaks the future — the classic way to build a backtest that wins on paper and loses
--   money.
--     ✅ Correct: season-over-season priors (join season S−1 to a game in season S); reporting.
--     ❌ Wrong:   any feature for a game IN this season.
--     ⭐ For a pregame row in-season, use rollup_nfl_team_week_asof.
--
-- Efficiency EXCLUDES garbage time; advanced metrics are PLAY-WEIGHTED (a 70-play game should not
-- count the same as a 45-play one).
{{ config(materialized='table') }}

with team_game as (
    select * from {{ ref('fct_nfl_team_game') }}
    where is_completed
)

select
    'nfl'                                                     as sport,
    season,
    team,
    season || '-' || team                                    as team_season_key,

    count(*)                                                 as games_played,
    sum(is_win::int)                                         as wins,
    sum((not is_win)::int)                                   as losses,
    avg(is_win::int)                                         as win_pct,

    avg(points_for)                                          as points_for_per_game,
    avg(points_against)                                      as points_against_per_game,
    avg(margin)                                              as margin_per_game,

    -- pbp efficiency (garbage-time-excluded, play-weighted)
    sum(off_clean_epa_per_play * off_clean_plays) / nullif(sum(off_clean_plays), 0) as off_epa_per_play,
    sum(def_clean_epa_per_play * def_clean_plays) / nullif(sum(def_clean_plays), 0) as def_epa_per_play,
    sum(off_clean_success_rate * off_clean_plays) / nullif(sum(off_clean_plays), 0) as off_success_rate,
    sum(def_clean_success_rate * def_clean_plays) / nullif(sum(def_clean_plays), 0) as def_success_rate,
    sum(off_clean_explosive_rate * off_clean_plays) / nullif(sum(off_clean_plays), 0) as off_explosive_rate,
    sum(def_clean_explosive_rate * def_clean_plays) / nullif(sum(def_clean_plays), 0) as def_explosive_rate,
    (sum(off_clean_epa_per_play * off_clean_plays) / nullif(sum(off_clean_plays), 0))
      - (sum(def_clean_epa_per_play * def_clean_plays) / nullif(sum(def_clean_plays), 0)) as net_epa_per_play,
    sum(off_pass_epa_per_play * off_pass_plays) / nullif(sum(off_pass_plays), 0)    as off_pass_epa_per_play,
    sum(off_rush_epa_per_play * off_rush_plays) / nullif(sum(off_rush_plays), 0)    as off_rush_epa_per_play,

    -- pace / box
    avg(off_plays)                                           as off_plays_per_game,
    avg(off_pass_rate)                                       as off_pass_rate,
    avg(total_yards)                                         as total_yards_per_game,
    avg(passing_yards)                                       as passing_yards_per_game,
    avg(rushing_yards)                                       as rushing_yards_per_game,
    avg(turnovers)                                           as turnovers_per_game,
    avg(penalty_yards)                                       as penalty_yards_per_game
from team_game
group by 1, 2, 3
