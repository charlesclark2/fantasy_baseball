-- =============================================================================
-- mart_pitcher_batted_ball_profile.sql
-- Grain: one row per (pitcher_id, game_year)
-- Purpose: Starter batted-ball profile — GB%, FB%, LD%, Popup% — derived from
--          Statcast pitch data.  Used to construct gb_pct × eb_so_factor and
--          fb_pct × eb_hr_factor interaction terms for Epic 27.5.
--
-- Source: stg_batter_pitches (batted_ball_type column, regular season only).
--
-- Coverage: 2015+ (batted_ball_type populated from Statcast coverage start).
-- Min gate: 50 batters faced — loosely gated so first-year starters and
--   injury-shortened seasons still produce a prior.
--
-- LEAKAGE GUARD: feature consumers join on game_year - 1 so a 2026 game uses
--   season=2025 batted-ball rates — no current-season data crosses the feature
--   boundary.  Do NOT join on game_year directly.
-- =============================================================================

{{ config(materialized='table') }}

with terminal_pa as (
    -- One row per plate appearance (terminal pitch only).
    -- batted_ball_type is non-null only on in-play events; NULL for strikeouts,
    -- walks, HBP, etc. — those count toward BF but not toward batted-ball %.
    select
        pitcher_id,
        game_year,
        batted_ball_type
    from {{ ref('stg_batter_pitches') }}
    where game_type = 'R'
      and game_year >= 2015
      and plate_appearance_event is not null
      and plate_appearance_event != 'truncated_pa'
),

agg as (
    select
        pitcher_id,
        game_year,
        count(*)                                                            as bf_count,
        count(batted_ball_type)                                             as total_batted_balls,
        count(case when batted_ball_type = 'ground_ball' then 1 end)       as gb_count,
        count(case when batted_ball_type = 'fly_ball'    then 1 end)       as fb_count,
        count(case when batted_ball_type = 'line_drive'  then 1 end)       as ld_count,
        count(case when batted_ball_type = 'popup'       then 1 end)       as popup_count
    from terminal_pa
    group by pitcher_id, game_year
    having count(*) >= 50
)

select
    pitcher_id,
    game_year,
    bf_count,
    total_batted_balls,
    gb_count,
    fb_count,
    ld_count,
    popup_count,

    -- GB%: ground balls / total in-play balls (with batted_ball_type)
    round(gb_count::float / nullif(total_batted_balls, 0), 4) as gb_pct,

    -- FB%: fly balls / total in-play balls
    round(fb_count::float / nullif(total_batted_balls, 0), 4) as fb_pct,

    -- LD%: line drives / total in-play balls
    round(ld_count::float / nullif(total_batted_balls, 0), 4) as ld_pct,

    -- Popup%: infield fly balls / total in-play balls
    round(popup_count::float / nullif(total_batted_balls, 0), 4) as popup_pct

from agg
