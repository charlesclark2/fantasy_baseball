-- fct_nfl_team_game — the team-game fact (NFL-N1.0). The workhorse the game-line vertical is built
-- on: every rollup aggregates it, and the opponent-adjustment joins it to itself.
--
-- GRAIN: one row per (game_id, team) — TWO rows per game, each from THAT team's perspective.
--
-- It conforms three sources onto one grain:
--   • the GAME context + result   (dim_nfl_game — opponent, home/away, environment, margin, win)
--   • pbp EFFICIENCY              (stg_nfl_pbp — off/def EPA·success·explosiveness, garbage-excluded)
--   • the conventional BOX line   (stg_nfl_team_week — yards, first downs, turnovers, penalties)
--
-- ⭐ off_* = this team's OFFENSE (its posteam plays); def_* = what its DEFENSE allowed (its defteam
--   plays). Both EPA-higher-is-better for offense, EPA-LOWER-is-better for defense (def_epa is
--   points allowed per play) — the sign convention every consumer inherits.
-- ⭐ `_clean` columns exclude garbage time (wp outside [0.05, 0.95]); the plain columns are the
--   full game. The rollups read the clean columns for the strength signal.
--
-- ⚠️ EVERY COLUMN HERE IS POST-KICKOFF — an OUTCOME fact. Nothing may feed a pregame row for the
--   SAME game; the as-of rollups (week < W) are the sanctioned pregame path.
-- The box line LEFT-joins (stats_team_week can lag pbp for the newest slate) → `has_box_line`
--   flags absence rather than letting a NULL read as 0.
{{ config(materialized='table') }}

with games as (
    select * from {{ ref('dim_nfl_game') }}
),

-- two sides per game, each from that team's perspective
sides as (
    select
        game_id, season, week, season_type, is_postseason, game_date, game_datetime,
        home_team as team, away_team as opponent, true as is_home,
        is_neutral_site, is_div_game, is_dome, surface, temperature_f, wind_mph,
        home_rest_days as rest_days, away_travel_km as opponent_travel_km,
        is_completed, home_score as points_for, away_score as points_against,
        home_margin as margin, home_win as team_won_home_side
    from games
    union all
    select
        game_id, season, week, season_type, is_postseason, game_date, game_datetime,
        away_team as team, home_team as opponent, false as is_home,
        is_neutral_site, is_div_game, is_dome, surface, temperature_f, wind_mph,
        away_rest_days as rest_days, away_travel_km as opponent_travel_km,
        is_completed, away_score as points_for, home_score as points_against,
        -home_margin as margin, home_win as team_won_home_side
    from games
),

-- ── offense efficiency from pbp (this team's posteam plays) ──────────────────────────
pbp_off as (
    select
        game_id, posteam as team,
        count(*) filter (where is_scrimmage_play)                          as off_plays,
        avg(epa) filter (where is_scrimmage_play)                          as off_epa_per_play,
        avg(is_success::int) filter (where is_scrimmage_play)              as off_success_rate,
        avg(is_explosive::int) filter (where is_scrimmage_play)            as off_explosive_rate,
        avg(epa) filter (where is_pass_play)                               as off_pass_epa_per_play,
        avg(epa) filter (where is_rush_play)                               as off_rush_epa_per_play,
        count(*) filter (where is_pass_play)                               as off_pass_plays,
        count(*) filter (where is_rush_play)                               as off_rush_plays,
        avg(qb_epa) filter (where is_scrimmage_play)                       as off_qb_epa_per_play,
        -- garbage-time-excluded (the strength read)
        count(*) filter (where is_scrimmage_play and not is_garbage_time)  as off_clean_plays,
        avg(epa) filter (where is_scrimmage_play and not is_garbage_time)  as off_clean_epa_per_play,
        avg(is_success::int) filter (where is_scrimmage_play and not is_garbage_time)
                                                                           as off_clean_success_rate,
        avg(is_explosive::int) filter (where is_scrimmage_play and not is_garbage_time)
                                                                           as off_clean_explosive_rate
    from {{ ref('stg_nfl_pbp') }}
    where posteam is not null
    group by 1, 2
),

-- ── defense efficiency from pbp (this team's defteam plays — what it ALLOWED) ─────────
pbp_def as (
    select
        game_id, defteam as team,
        count(*) filter (where is_scrimmage_play)                          as def_plays,
        avg(epa) filter (where is_scrimmage_play)                          as def_epa_per_play,
        avg(is_success::int) filter (where is_scrimmage_play)              as def_success_rate,
        avg(is_explosive::int) filter (where is_scrimmage_play)            as def_explosive_rate,
        count(*) filter (where is_scrimmage_play and not is_garbage_time)  as def_clean_plays,
        avg(epa) filter (where is_scrimmage_play and not is_garbage_time)  as def_clean_epa_per_play,
        avg(is_success::int) filter (where is_scrimmage_play and not is_garbage_time)
                                                                           as def_clean_success_rate,
        avg(is_explosive::int) filter (where is_scrimmage_play and not is_garbage_time)
                                                                           as def_clean_explosive_rate
    from {{ ref('stg_nfl_pbp') }}
    where defteam is not null
    group by 1, 2
),

box as (select * from {{ ref('stg_nfl_team_week') }})

select
    'nfl'                                               as sport,
    s.game_id,
    s.team,
    'nfl-' || s.game_id || '-' || s.team               as team_game_key,
    s.season,
    s.week,
    s.season_type,
    s.is_postseason,
    s.game_date,
    s.game_datetime,

    -- ── side / opponent / environment ───────────────────────────────────────────────
    s.is_home,
    s.opponent,
    s.is_neutral_site,
    s.is_div_game,
    s.is_dome,
    s.surface,
    s.temperature_f,
    s.wind_mph,
    s.rest_days,
    s.opponent_travel_km,

    -- ── ⚠️ RESULT (post-kickoff) ─────────────────────────────────────────────────────
    s.is_completed,
    s.points_for,
    s.points_against,
    s.margin,
    case when not s.is_completed or s.team_won_home_side is null then null
         when s.is_home then s.team_won_home_side
         else not s.team_won_home_side end              as is_win,

    -- ── pbp EFFICIENCY: offense ──────────────────────────────────────────────────────
    po.off_plays,
    po.off_epa_per_play,
    po.off_success_rate,
    po.off_explosive_rate,
    po.off_pass_epa_per_play,
    po.off_rush_epa_per_play,
    po.off_pass_plays,
    po.off_rush_plays,
    po.off_qb_epa_per_play,
    po.off_clean_plays,
    po.off_clean_epa_per_play,
    po.off_clean_success_rate,
    po.off_clean_explosive_rate,
    -- pass rate = a style/pace-adjacent read
    po.off_pass_plays::double / nullif(po.off_pass_plays + po.off_rush_plays, 0) as off_pass_rate,

    -- ── pbp EFFICIENCY: defense (allowed) ────────────────────────────────────────────
    pd.def_plays,
    pd.def_epa_per_play,
    pd.def_success_rate,
    pd.def_explosive_rate,
    pd.def_clean_plays,
    pd.def_clean_epa_per_play,
    pd.def_clean_success_rate,
    pd.def_clean_explosive_rate,

    -- ── conventional BOX line (post-kickoff; LEFT-joined) ────────────────────────────
    (b.game_id is not null)                             as has_box_line,
    b.total_yards,
    b.passing_yards,
    b.rushing_yards,
    b.offensive_first_downs,
    b.pass_attempts,
    b.completions,
    b.rush_attempts,
    b.turnovers,
    b.sacks_suffered,
    b.penalties,
    b.penalty_yards,
    b.def_sacks,
    b.def_interceptions
from sides s
left join pbp_off po on po.game_id = s.game_id and po.team = s.team
left join pbp_def pd on pd.game_id = s.game_id and pd.team = s.team
left join box b      on b.game_id  = s.game_id and b.team  = s.team
