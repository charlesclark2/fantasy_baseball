-- rollup_nfl_team_week_asof — the POINT-IN-TIME team rollup (NFL-N1.0).
--
-- ⭐⭐ THE PREGAME-SAFE SURFACE. Every in-season team feature must come from here (or the
--   opponent-adjusted model on top), never from rollup_nfl_team_season.
--
-- GRAIN: one row per (season, team, as_of_week). The row answers: "everything we knew about this
--   team BEFORE week `as_of_week` kicked off."
--
-- ⭐ THE LEAKAGE CONTRACT — one line, and it is the whole model:
--        a row for as_of_week = W aggregates ONLY games with week < W.
--   Strictly less-than, not ≤. A team's week-6 pregame row must not contain the week-6 game it is
--   about to play (that result is the prediction target). Enforced by the join
--   (`g.week < s.as_of_week`) and by the kickoff-date test `assert_nfl_asof_week_has_no_future_games`.
--
-- ⭐ `week` IS THE SAFE ORDERING FOR NFL — monotone within a season (no CFBD postseason reset;
--   verified on the real lake). So no season_order_week is needed; `as_of_week` IS `week`.
--
-- ⚠️ WEEK 1 IS AN HONEST EMPTY ROW: games_played = 0, every metric NULL. That is CORRECT and stays
--   NULL — coalescing to 0 would tell a model "this team scores 0 ppg." `has_sufficient_sample`
--   marks rows with a usable base (≥3 games) so a consumer can shrink small samples toward a prior.
-- ⚠️ Bye weeks: the spine is (every week) × (every team active that season), so a team on bye still
--   gets a row — its metrics simply do not advance, which is the truth.
{{ config(materialized='table') }}

with team_game as (
    select * from {{ ref('fct_nfl_team_game') }}
    where is_completed
),

-- the spine: every (season, week) that occurred × every team active that season
season_weeks as (
    select distinct season, week as as_of_week
    from {{ ref('dim_nfl_game') }}
    where week is not null
),
season_teams as (
    select distinct season, team from team_game
),
spine as (
    select st.season, st.team, sw.as_of_week
    from season_teams st
    join season_weeks sw on sw.season = st.season
)

select
    'nfl'                                                     as sport,
    s.season,
    s.team,
    s.as_of_week,
    s.season || '-' || s.team || '-w' || s.as_of_week         as team_week_key,

    -- ── sample size ──────────────────────────────────────────────────────────────────
    count(g.game_id)                                          as games_played,
    (count(g.game_id) >= 3)                                   as has_sufficient_sample,
    max(g.week)                                               as last_game_week,

    -- ── record + scoring (NULL, not 0, when nothing has been played) ─────────────────
    sum(g.is_win::int)                                        as wins,
    sum((not g.is_win)::int)                                  as losses,
    avg(g.is_win::int)                                        as win_pct,
    avg(g.points_for)                                         as points_for_per_game,
    avg(g.points_against)                                     as points_against_per_game,
    avg(g.margin)                                             as margin_per_game,

    -- ── pbp efficiency (garbage-time-excluded, PLAY-WEIGHTED) — the cleanest strength read ──
    sum(g.off_clean_epa_per_play * g.off_clean_plays)
        / nullif(sum(g.off_clean_plays), 0)                   as off_epa_per_play,
    sum(g.def_clean_epa_per_play * g.def_clean_plays)
        / nullif(sum(g.def_clean_plays), 0)                   as def_epa_per_play,
    sum(g.off_clean_success_rate * g.off_clean_plays)
        / nullif(sum(g.off_clean_plays), 0)                   as off_success_rate,
    sum(g.def_clean_success_rate * g.def_clean_plays)
        / nullif(sum(g.def_clean_plays), 0)                   as def_success_rate,
    sum(g.off_clean_explosive_rate * g.off_clean_plays)
        / nullif(sum(g.off_clean_plays), 0)                   as off_explosive_rate,
    sum(g.def_clean_explosive_rate * g.def_clean_plays)
        / nullif(sum(g.def_clean_plays), 0)                   as def_explosive_rate,
    -- net EPA per play (offense − defense) = the single-number team-strength read
    (sum(g.off_clean_epa_per_play * g.off_clean_plays) / nullif(sum(g.off_clean_plays), 0))
      - (sum(g.def_clean_epa_per_play * g.def_clean_plays) / nullif(sum(g.def_clean_plays), 0))
                                                              as net_epa_per_play,
    sum(g.off_pass_epa_per_play * g.off_pass_plays)
        / nullif(sum(g.off_pass_plays), 0)                    as off_pass_epa_per_play,
    sum(g.off_rush_epa_per_play * g.off_rush_plays)
        / nullif(sum(g.off_rush_plays), 0)                    as off_rush_epa_per_play,

    -- ── pace / style ─────────────────────────────────────────────────────────────────
    avg(g.off_plays)                                          as off_plays_per_game,
    avg(g.off_pass_rate)                                      as off_pass_rate,

    -- ── box efficiency ───────────────────────────────────────────────────────────────
    avg(g.total_yards)                                        as total_yards_per_game,
    avg(g.passing_yards)                                      as passing_yards_per_game,
    avg(g.rushing_yards)                                      as rushing_yards_per_game,
    avg(g.turnovers)                                          as turnovers_per_game,
    avg(g.penalty_yards)                                      as penalty_yards_per_game

from spine s
-- ⭐⭐ THE LEAKAGE CONTRACT: strictly BEFORE the as-of week. Do not relax to <=.
left join team_game g
       on g.season = s.season
      and g.team   = s.team
      and g.week   < s.as_of_week
group by 1, 2, 3, 4, 5
