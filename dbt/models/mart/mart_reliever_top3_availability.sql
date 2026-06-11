{{
    config(
        materialized='table'
    )
}}

-- Grain: pitching_team × game_pk (same as mart_bullpen_workload).
-- Pre-game availability of the three highest-leverage relievers for each team.
--
-- "Availability" is defined per-arm, not at the team aggregate level.
-- The top-3 arms are ranked by their rolling 30-day leverage workload
-- (sum of |delta_home_win_exp|) using only appearances strictly before
-- this game (leakage guard).
--
-- Role labels:
--   closer  — rank-1 leverage arm (trailing 30d)
--   setup1  — rank-2 leverage arm
--   setup2  — rank-3 leverage arm
--
-- Output columns per arm:
--   {role}_available   — 1 if arm did NOT pitch yesterday (rest_days >= 2);
--                        defaults to 1 (fully rested) when no prior 30-day data
--   {role}_rest_days   — days since last outing (NULL when arm hasn't pitched
--                        in the prior 30 days)
--
-- Leakage guards:
--   Rolling window uses strictly-prior appearances (game_date < this game's date).
--   Rest-days computed as datediff(last_appearance_date, this_game_date).
--
-- Doubleheader handling: appearances are collapsed to the date level before
-- ranking, so both games of a doubleheader see the same trailing workload.
--
-- NULL handling: *_available columns default to 1 (rested) via COALESCE when no
-- prior 30-day appearances exist (season openers). *_rest_days stays NULL.
-- This guarantees ≥95% non-null coverage for *_available across all
-- completed regular-season game-sides.
--
-- Companion models (join on team_abbrev + game_pk):
--   mart_bullpen_workload  — aggregate fatigue/availability
--   mart_bullpen_leverage  — aggregate leverage workload
-- Story: 6.6 — Reliever top-3 leverage availability vector

with

-- ── Raw pitch data for reliever appearances ───────────────────────────────────
pitches as (

    select
        bp.pitch_sk,
        bp.game_pk,
        bp.game_date,
        bp.game_year,
        bp.pitcher_id,
        case when bp.inning_half = 'Top' then bp.home_team else bp.away_team end
            as pitching_team,
        ppe.delta_home_win_exp
    from {{ ref('stg_batter_pitches') }} bp
    join {{ ref('mart_pitch_play_event') }} ppe
        on  ppe.pitch_sk = bp.pitch_sk
    where bp.game_type = 'R'
      and ppe.delta_home_win_exp is not null

),

-- ── Exclude starters ─────────────────────────────────────────────────────────
starters as (

    select game_pk, pitcher_id, pitching_team
    from {{ ref('mart_starting_pitcher_game_log') }}

),

reliever_pitches as (

    select p.*
    from pitches p
    left join starters s
        on  s.game_pk       = p.game_pk
        and s.pitcher_id    = p.pitcher_id
        and s.pitching_team = p.pitching_team
    where s.pitcher_id is null

),

-- ── Per pitcher × game leverage total ────────────────────────────────────────
reliever_game_leverage as (

    select
        game_pk,
        game_date,
        pitching_team,
        pitcher_id,
        sum(abs(delta_home_win_exp)) as game_leverage
    from reliever_pitches
    group by game_pk, game_date, pitching_team, pitcher_id

),

-- ── Collapse to pitcher × date level (doubleheader-safe) ─────────────────────
reliever_date_leverage as (

    select
        game_date,
        pitching_team,
        pitcher_id,
        sum(game_leverage)  as day_leverage
    from reliever_game_leverage
    group by game_date, pitching_team, pitcher_id

),

-- ── Game spine: one row per game_pk × pitching_team ──────────────────────────
-- Reuse the same game-level grains as mart_bullpen_workload (completed games only)
game_spine as (

    select distinct game_pk, game_date, pitching_team
    from reliever_game_leverage

),

-- ── Rolling 30-day leverage and last appearance per pitcher × game ────────────
-- Leakage: reliever appearance date STRICTLY < this game's date.
-- Window: prior 30 calendar days (inclusive on lower bound).
rolling as (

    select
        gs.game_pk,
        gs.game_date,
        gs.pitching_team,
        rdl.pitcher_id,
        sum(rdl.day_leverage)                                   as rolling_leverage_30d,
        max(rdl.game_date)                                      as last_appearance_date,
        datediff(
            'day',
            max(rdl.game_date),
            gs.game_date
        )                                                       as rest_days
    from game_spine gs
    join reliever_date_leverage rdl
        on  rdl.pitching_team = gs.pitching_team
        and rdl.game_date < gs.game_date                        -- leakage guard
        and rdl.game_date >= dateadd('day', -30, gs.game_date)  -- 30-day window
    group by gs.game_pk, gs.game_date, gs.pitching_team, rdl.pitcher_id

),

-- ── Rank pitchers by trailing 30-day leverage (highest = closer) ──────────────
ranked as (

    select
        game_pk,
        game_date,
        pitching_team,
        pitcher_id,
        rolling_leverage_30d,
        last_appearance_date,
        rest_days,
        row_number() over (
            partition by game_pk, pitching_team
            order by rolling_leverage_30d desc nulls last
        ) as leverage_rank
    from rolling

),

-- ── Pivot: closer (rank 1), setup1 (rank 2), setup2 (rank 3) ─────────────────
-- "available" = 1 when rest_days >= 2 (did not pitch yesterday)
-- rest_days = NULL means arm hasn't appeared in trailing 30 days → fully rested
pivoted as (

    select
        game_pk,
        game_date,
        pitching_team,

        -- Closer (highest leverage arm)
        max(case when leverage_rank = 1 then
            case
                when rest_days is null or rest_days >= 2 then 1
                else 0
            end
        end)                                        as closer_available,
        max(case when leverage_rank = 1 then rest_days end) as closer_rest_days,

        -- Setup 1 (second-highest leverage arm)
        max(case when leverage_rank = 2 then
            case
                when rest_days is null or rest_days >= 2 then 1
                else 0
            end
        end)                                        as setup1_available,
        max(case when leverage_rank = 2 then rest_days end) as setup1_rest_days,

        -- Setup 2 (third-highest leverage arm)
        max(case when leverage_rank = 3 then
            case
                when rest_days is null or rest_days >= 2 then 1
                else 0
            end
        end)                                        as setup2_available,
        max(case when leverage_rank = 3 then rest_days end) as setup2_rest_days

    from ranked
    where leverage_rank <= 3
    group by game_pk, game_date, pitching_team

)

-- ── Final: join back to game spine; default unavailable arms to 1 (rested) ────
-- COALESCE on *_available: when no pitcher in top-3 exists (season openers with
-- no trailing 30-day data), the team's arms are implicitly fully rested.
select
    gs.game_pk,
    gs.game_date,
    gs.pitching_team                                as team_abbrev,

    coalesce(p.closer_available,  1)                as closer_available,
    p.closer_rest_days,

    coalesce(p.setup1_available,  1)                as setup1_available,
    p.setup1_rest_days,

    coalesce(p.setup2_available,  1)                as setup2_available,
    p.setup2_rest_days

from game_spine gs
left join pivoted p
    on  p.game_pk       = gs.game_pk
    and p.pitching_team = gs.pitching_team
