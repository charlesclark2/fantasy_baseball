-- fact_ncaaf_team_game — the team-game fact (NCAAF-P1.1).
--
-- GRAIN: one row per (game_id, team_id) — TWO rows per game, one per side, each from THAT team's
-- perspective. This is the workhorse fact: every season and as-of-week rollup aggregates it, and
-- the opponent-adjustment joins it to itself.
--
-- It conforms three sources onto one grain:
--   • the BOX line          (stg_ncaaf_game_team_stats — yards, downs, turnovers, possession)
--   • CFBD's ADVANCED box   (stg_ncaaf_game_advanced — ppa/success/explosiveness/line-yards)
--   • the GAME context      (dim_ncaaf_game — opponent, venue, home/away, result)
--
-- ⭐ FBS-FILTERED: restricted to `is_fbs_matchup` — both sides FBS. This is the P0.2 flag made
-- structural: without it the fact would carry FCS/D-II opponents whose stats are not comparable
-- and whose presence would distort every opponent-adjusted number computed from it.
-- ⭐ SPORT-TAGGED on every row.
--
-- ⚠️ EVERY COLUMN HERE IS POST-KICKOFF. This is an OUTCOME fact — it describes a game that was
-- played. Nothing in it may be read into a pregame feature row for the SAME game. The as-of-week
-- rollups are the sanctioned pregame path: they aggregate this fact strictly over `week < W`.
--
-- The advanced block joins on (game_id, team NAME) — /stats/game/advanced carries no teamId —
-- so it is a LEFT join: an advanced row can be missing (CFBD's coverage is thinner in the early
-- seasons) and the box line must survive that. `has_advanced_stats` flags it honestly rather
-- than letting a NULL read as a zero downstream.
{{ config(materialized='table') }}

with games as (
    select * from {{ ref('dim_ncaaf_game') }}
    where is_fbs_matchup            -- ⭐ the modelling universe
),

box as (
    select * from {{ ref('stg_ncaaf_game_team_stats') }}
),

adv as (
    select * from {{ ref('stg_ncaaf_game_advanced') }}
)

select
    'ncaaf'                                                      as sport,
    b.game_id,
    b.team_id,
    'ncaaf-' || b.game_id || '-' || b.team_id                    as team_game_key,
    g.season,
    g.week,                          -- ⚠️ CFBD-native; NOT a season ordering
    g.season_order_week,             -- ⭐ the only safe season ordering (see dim_ncaaf_game)
    g.season_type,
    g.game_date,
    b.team,
    b.conference,

    -- ── side / opponent ───────────────────────────────────────────────────────────────
    b.is_home,
    g.is_neutral_site,
    g.is_conference_game,
    g.is_postseason,
    case when b.is_home then g.away_team_id else g.home_team_id end   as opponent_team_id,
    case when b.is_home then g.away_team    else g.home_team    end   as opponent_team,
    case when b.is_home then g.away_conference else g.home_conference end as opponent_conference,

    -- ── ⚠️ RESULT (post-kickoff) ──────────────────────────────────────────────────────
    g.is_completed,
    b.points                                                     as points_for,
    case when b.is_home then g.away_points else g.home_points end as points_against,
    case when b.is_home then g.home_margin else -g.home_margin end as margin,
    case when not g.is_completed or g.is_tie then null
         else (g.winning_team_id = b.team_id) end                as is_win,

    -- ── the BOX line ──────────────────────────────────────────────────────────────────
    b.first_downs,
    b.total_yards,
    b.net_passing_yards,
    b.rushing_yards,
    b.rushing_attempts,
    b.rushing_tds,
    b.passing_tds,
    b.completions,
    b.pass_attempts,
    b.yards_per_pass,
    b.yards_per_rush_attempt,
    b.third_down_conversions,
    b.third_down_attempts,
    b.fourth_down_conversions,
    b.fourth_down_attempts,
    b.turnovers,
    b.fumbles_lost,
    b.interceptions_thrown,
    b.passes_intercepted,
    b.sacks,
    b.tackles_for_loss,
    b.qb_hurries,
    b.passes_deflected,
    b.penalties,
    b.penalty_yards,
    b.possession_seconds,
    b.kicking_points,
    -- derived rates, computed ONCE here so no two consumers can disagree on the definition
    case when b.third_down_attempts > 0
         then b.third_down_conversions::double / b.third_down_attempts end   as third_down_rate,
    case when b.fourth_down_attempts > 0
         then b.fourth_down_conversions::double / b.fourth_down_attempts end as fourth_down_rate,
    case when b.pass_attempts > 0
         then b.completions::double / b.pass_attempts end                    as completion_rate,
    (coalesce(b.rushing_attempts, 0) + coalesce(b.pass_attempts, 0))         as scrimmage_plays_box,

    -- ── CFBD's ADVANCED box (off_* = this team's offense, def_* = what its defense allowed) ─
    (a.game_id is not null)                                      as has_advanced_stats,
    a.off_plays, a.off_drives, a.off_ppa, a.off_total_ppa, a.off_success_rate,
    a.off_explosiveness, a.off_power_success, a.off_stuff_rate, a.off_line_yards,
    a.off_second_level_yards, a.off_open_field_yards,
    a.off_standard_downs_ppa, a.off_standard_downs_success_rate, a.off_standard_downs_explosiveness,
    a.off_passing_downs_ppa,  a.off_passing_downs_success_rate,  a.off_passing_downs_explosiveness,
    a.off_rushing_plays_ppa,  a.off_rushing_plays_success_rate,  a.off_rushing_plays_explosiveness,
    a.off_passing_plays_ppa,  a.off_passing_plays_success_rate,  a.off_passing_plays_explosiveness,
    a.def_plays, a.def_drives, a.def_ppa, a.def_total_ppa, a.def_success_rate,
    a.def_explosiveness, a.def_power_success, a.def_stuff_rate, a.def_line_yards,
    a.def_second_level_yards, a.def_open_field_yards,
    a.def_standard_downs_ppa, a.def_standard_downs_success_rate, a.def_standard_downs_explosiveness,
    a.def_passing_downs_ppa,  a.def_passing_downs_success_rate,  a.def_passing_downs_explosiveness,
    a.def_rushing_plays_ppa,  a.def_rushing_plays_success_rate,  a.def_rushing_plays_explosiveness,
    a.def_passing_plays_ppa,  a.def_passing_plays_success_rate,  a.def_passing_plays_explosiveness

from box b
join games g on g.game_id = b.game_id
left join adv a
    on a.game_id = b.game_id
   and a.team    = b.team
