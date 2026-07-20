-- rollup_ncaaf_team_week_asof — the POINT-IN-TIME team rollup (NCAAF-P1.1).
--
-- ⭐⭐ THIS IS THE PREGAME-SAFE SURFACE. Every in-season team feature must come from here (or
-- from the opponent-adjusted model built on top of it), never from rollup_ncaaf_team_season.
--
-- GRAIN: one row per (season, team_id, as_of_week).
--   The row answers: "everything we knew about this team BEFORE week `as_of_week` kicked off."
--
-- ⚠️ `as_of_week` IS `season_order_week`, NOT CFBD's raw `week` — postseason restarts at 1, so
-- a raw-`week` spine folds December bowl and CFP games into September (2024 Ohio State had FIVE
-- games at `week <= 1`). See dim_ncaaf_game's header; that ordering bug is invisible to a
-- `week < W` filter because the filter is right and the ordering is wrong.
--
-- ⭐ THE LEAKAGE CONTRACT — one line, and it is the whole model:
--        a row for as_of_week = W aggregates ONLY games with season_order_week < W.
--   Strictly less-than. Not ≤. A team's week-6 pregame row must not contain the week-6 game it
--   is about to play — that game's result is the thing being predicted. This is enforced
--   structurally by the join below (`g.season_order_week < s.as_of_week`) and by the data test
--   `assert_asof_week_has_no_future_games` in _ncaaf_marts.yml, which fails the build if any row
--   can be traced to a game at or after its own as_of_week.
--
-- ⚠️ WEEK 1 IS AN HONEST EMPTY ROW. At as_of_week = 1 nothing has been played, so
-- games_played = 0 and every metric is NULL. That is CORRECT and must stay NULL — coalescing it
-- to 0 would tell a model "this team scores 0 points per game," which is worse than "unknown."
-- `has_sufficient_sample` marks rows with a usable base (≥3 games); small-sample rows are kept
-- (they are real) but flagged so a consumer can shrink toward a prior instead of trusting n=1.
--
-- ⚠️ Bye weeks: the spine is (every FBS week in the season) × (every team active that season), so
-- a team on bye still gets a row. Its metrics simply do not advance — which is the truth.
--
-- Sources are pre-aggregated to the team-GAME grain first (drive quality, garbage-time-excluded
-- play efficiency), so the as-of self-join runs over ~18k rows, not 1.5M.
{{ config(materialized='table') }}

with team_game as (
    select * from {{ ref('fact_ncaaf_team_game') }}
    where is_completed
),

-- ── per team-GAME drive quality (offense's own drives) ─────────────────────────────────
drive_game as (
    select
        game_id,
        offense_team_id                                  as team_id,
        count(*)                                         as drives,
        sum(points_scored)                               as drive_points,
        sum(is_scoring_opportunity::int)                 as scoring_opportunities,
        sum(is_three_and_out::int)                       as three_and_outs,
        sum(is_explosive_drive::int)                     as explosive_drives,
        sum(start_yards_to_goal)                         as start_yards_to_goal_sum
    from {{ ref('fact_ncaaf_drive') }}
    group by 1, 2
),

-- ── ⭐ per team-GAME play efficiency, GARBAGE TIME EXCLUDED ────────────────────────────
play_game_off as (
    select
        game_id, offense_team_id as team_id,
        count(*)                     as off_clean_plays,
        sum(ppa)                     as off_clean_ppa_sum,
        count(ppa)                   as off_clean_ppa_n,
        sum(is_successful_play::int) as off_clean_successes,
        count(is_successful_play)    as off_clean_success_n
    from {{ ref('fact_ncaaf_play') }}
    where is_scrimmage_play and not is_garbage_time
    group by 1, 2
),

play_game_def as (
    select
        game_id, defense_team_id as team_id,
        count(*)                     as def_clean_plays,
        sum(ppa)                     as def_clean_ppa_sum,
        count(ppa)                   as def_clean_ppa_n,
        sum(is_successful_play::int) as def_clean_successes,
        count(is_successful_play)    as def_clean_success_n
    from {{ ref('fact_ncaaf_play') }}
    where is_scrimmage_play and not is_garbage_time
    group by 1, 2
),

-- one enriched row per team-game — the unit the as-of window sums over
game_base as (
    select
        tg.*,
        d.drives, d.drive_points, d.scoring_opportunities, d.three_and_outs,
        d.explosive_drives, d.start_yards_to_goal_sum,
        po.off_clean_plays, po.off_clean_ppa_sum, po.off_clean_ppa_n,
        po.off_clean_successes, po.off_clean_success_n,
        pdf.def_clean_plays, pdf.def_clean_ppa_sum, pdf.def_clean_ppa_n,
        pdf.def_clean_successes, pdf.def_clean_success_n
    from team_game tg
    left join drive_game   d   on d.game_id   = tg.game_id and d.team_id   = tg.team_id
    left join play_game_off po on po.game_id  = tg.game_id and po.team_id  = tg.team_id
    left join play_game_def pdf on pdf.game_id = tg.game_id and pdf.team_id = tg.team_id
),

-- ── the spine: every (season, week) × every team active that season ────────────────────
season_weeks as (
    -- ⭐ season_order_week, NOT week — postseason restarts at week 1, so a raw-`week` spine
    -- would collapse December bowls onto September's week 1 (see dim_ncaaf_game's header).
    select distinct season, season_order_week as as_of_week
    from {{ ref('dim_ncaaf_game') }}
    where is_fbs_matchup and season_order_week is not null
),

season_teams as (
    select distinct season, team_id, team, conference
    from team_game
),

spine as (
    select st.season, st.team_id, st.team, st.conference, sw.as_of_week
    from season_teams st
    join season_weeks sw on sw.season = st.season
)

select
    'ncaaf'                                                   as sport,
    s.season,
    s.team_id,
    s.team,
    s.conference,
    s.as_of_week,
    s.season || '-' || s.team_id || '-w' || s.as_of_week      as team_week_key,

    -- ── sample size ───────────────────────────────────────────────────────────────────
    count(g.game_id)                                          as games_played,
    (count(g.game_id) >= 3)                                   as has_sufficient_sample,
    max(g.season_order_week)                                  as last_game_order_week,

    -- ── record + scoring (NULL, not 0, when nothing has been played) ──────────────────
    sum(g.is_win::int)                                        as wins,
    sum((not g.is_win)::int)                                  as losses,
    avg(g.is_win::int)                                        as win_pct,
    avg(g.points_for)                                         as points_for_per_game,
    avg(g.points_against)                                     as points_against_per_game,
    avg(g.margin)                                             as margin_per_game,

    -- ── box efficiency ────────────────────────────────────────────────────────────────
    avg(g.total_yards)                                        as total_yards_per_game,
    avg(g.rushing_yards)                                      as rushing_yards_per_game,
    avg(g.net_passing_yards)                                  as passing_yards_per_game,
    avg(g.turnovers)                                          as turnovers_per_game,
    sum(g.third_down_conversions)::double
        / nullif(sum(g.third_down_attempts), 0)               as third_down_rate,
    sum(g.completions)::double
        / nullif(sum(g.pass_attempts), 0)                     as completion_rate,
    avg(g.possession_seconds)                                 as possession_seconds_per_game,
    avg(g.penalty_yards)                                      as penalty_yards_per_game,

    -- ── CFBD advanced, play-weighted ──────────────────────────────────────────────────
    sum(g.off_ppa * g.off_plays) / nullif(sum(g.off_plays), 0)           as off_ppa,
    sum(g.off_success_rate * g.off_plays) / nullif(sum(g.off_plays), 0)  as off_success_rate,
    sum(g.off_explosiveness * g.off_plays) / nullif(sum(g.off_plays), 0) as off_explosiveness,
    sum(g.off_line_yards * g.off_plays) / nullif(sum(g.off_plays), 0)    as off_line_yards,
    sum(g.off_stuff_rate * g.off_plays) / nullif(sum(g.off_plays), 0)    as off_stuff_rate,
    sum(g.def_ppa * g.def_plays) / nullif(sum(g.def_plays), 0)           as def_ppa,
    sum(g.def_success_rate * g.def_plays) / nullif(sum(g.def_plays), 0)  as def_success_rate,
    sum(g.def_explosiveness * g.def_plays) / nullif(sum(g.def_plays), 0) as def_explosiveness,
    sum(g.def_line_yards * g.def_plays) / nullif(sum(g.def_plays), 0)    as def_line_yards,
    sum(g.def_stuff_rate * g.def_plays) / nullif(sum(g.def_plays), 0)    as def_stuff_rate,
    avg(g.off_plays)                                                     as off_plays_per_game,

    -- ── drive quality ─────────────────────────────────────────────────────────────────
    sum(g.drives)                                             as drives,
    sum(g.drive_points)::double / nullif(sum(g.drives), 0)    as points_per_drive,
    sum(g.scoring_opportunities)::double
        / nullif(sum(g.drives), 0)                            as scoring_opportunity_rate,
    sum(g.three_and_outs)::double / nullif(sum(g.drives), 0)  as three_and_out_rate,
    sum(g.explosive_drives)::double / nullif(sum(g.drives), 0) as explosive_drive_rate,
    sum(g.start_yards_to_goal_sum)::double
        / nullif(sum(g.drives), 0)                            as avg_start_yards_to_goal,

    -- ── ⭐ garbage-time-excluded play efficiency (the cleanest strength read) ──────────
    sum(g.off_clean_plays)                                    as off_clean_plays,
    sum(g.off_clean_ppa_sum) / nullif(sum(g.off_clean_ppa_n), 0)         as off_clean_ppa,
    sum(g.off_clean_successes)::double
        / nullif(sum(g.off_clean_success_n), 0)                          as off_clean_success_rate,
    sum(g.def_clean_plays)                                    as def_clean_plays,
    sum(g.def_clean_ppa_sum) / nullif(sum(g.def_clean_ppa_n), 0)         as def_clean_ppa,
    sum(g.def_clean_successes)::double
        / nullif(sum(g.def_clean_success_n), 0)                          as def_clean_success_rate

from spine s
-- ⭐⭐ THE LEAKAGE CONTRACT: strictly BEFORE the as-of week. Do not relax this to <=.
left join game_base g
       on g.season  = s.season
      and g.team_id = s.team_id
      and g.season_order_week < s.as_of_week
group by 1, 2, 3, 4, 5, 6, 7
