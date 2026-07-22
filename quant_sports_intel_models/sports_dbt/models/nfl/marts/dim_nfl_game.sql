-- dim_nfl_game — the NFL game dimension / conformed spine (NFL-N1.0). ONE row per game_id, the
-- spine fct_nfl_team_game and every rollup hang off.
--
-- Built over stg_nfl_schedules (already one-row-per-game, 2020+) — this model ADDS the situational
-- environment the game-line vertical needs and that schedules doesn't compute: travel distance
-- (Haversine from stg_nfl_team_geo), a clean dome flag, and typed rest. It also carries the
-- POST-KICKOFF result, flagged as such.
--
-- ⭐ `week` IS A SAFE SEASON ORDERING FOR NFL. Unlike CFBD (which restarts `week` at 1 for the
--   postseason — the NCAAF P1.1 leak), nflverse numbers the season monotonically: regular 1–18,
--   then WC/DIV/CON/SB continue at 19–22 (2021+; 18–21 in the 17-game 2020 season). VERIFIED
--   monotone-in-kickoff on the real lake for 2020–2024. So the as-of rollups order on `week`
--   directly; the leakage TEST still uses each game's own kickoff DATE (belt-and-suspenders — a
--   future ordering regression moves a game across a calendar boundary and the test catches it).
--
-- ⚠️ OUTCOME COLUMNS ARE POST-KICKOFF (home_score/away_score/result/total_points/home_win). They
--   are correct on a game dimension but must NEVER be folded into a pregame feature row for the
--   same game — the as-of rollups read them only for games with week < the as-of week.
--   `is_completed` distinguishes a real result from a scheduled-but-unplayed game (NULL score,
--   never 0-0).
{{ config(materialized='table') }}

with games as (
    select * from {{ ref('stg_nfl_schedules') }}
    where season >= 2020            -- the N0.4 odds floor; the team-game layer's modelling window
),

-- game venue coordinates = the HOME team's stadium, unless the game is at a neutral site (an
-- international/neutral game has no attributed venue geography → NULL, not a wrong home stadium)
home_geo as (select code, latitude, longitude from {{ ref('stg_nfl_team_geo') }}),
away_geo as (select code, latitude, longitude from {{ ref('stg_nfl_team_geo') }})

select
    'nfl'                                               as sport,
    g.game_id,
    'nfl-' || g.game_id                                 as game_key,
    g.season,
    g.week,                                             -- ⭐ monotone-in-date; safe as-of ordering
    g.season_type,
    (g.season_type <> 'REG')                            as is_postseason,
    g.is_regular_season,
    g.game_date,
    g.game_datetime,
    g.weekday,

    -- ── participants ─────────────────────────────────────────────────────────────────
    g.home_team,
    g.away_team,
    g.div_game                                          as is_div_game,

    -- ── situational environment ──────────────────────────────────────────────────────
    g.location,
    (lower(coalesce(g.location, 'home')) = 'neutral')   as is_neutral_site,
    g.roof,
    -- clean dome flag: a closed/domed roof at kickoff. 'outdoors'/'open' → false; NULL → NULL.
    case when g.roof is null then null
         when lower(g.roof) in ('dome', 'closed', 'retractable') then true
         else false end                                 as is_dome,
    g.surface,
    g.temp                                              as temperature_f,
    g.wind                                              as wind_mph,
    g.home_rest                                         as home_rest_days,
    g.away_rest                                         as away_rest_days,
    (g.home_rest - g.away_rest)                         as rest_days_diff,

    -- ⭐ away-team travel distance (great-circle km) from its own home stadium to the game venue.
    -- Home team travels ~0 at its own stadium; neutral-site venue geography is unattributed → NULL.
    case when lower(coalesce(g.location, 'home')) = 'neutral'
              or ag.latitude is null or hg.latitude is null then null
         else 6371.0 * acos(least(1.0, greatest(-1.0,
                 sin(radians(ag.latitude)) * sin(radians(hg.latitude))
               + cos(radians(ag.latitude)) * cos(radians(hg.latitude))
                 * cos(radians(hg.longitude - ag.longitude)))))
    end                                                 as away_travel_km,

    -- ── QB context (nflverse names the probable/actual starters on the schedule row) ──
    g.home_qb_id,
    g.away_qb_id,
    g.home_qb_name,
    g.away_qb_name,
    g.referee,
    g.stadium_id,
    g.stadium,

    -- ── free nflverse consensus line (a cross-check; the per-book close is mart_nfl_clv_*) ──
    g.spread_line,
    g.total_line,
    g.home_moneyline,
    g.away_moneyline,

    -- ── ⚠️ RESULT — POST-KICKOFF. Never a pregame feature for the same game. ──────────
    (g.home_score is not null and g.away_score is not null) as is_completed,
    g.home_score,
    g.away_score,
    g.result                                            as home_margin,   -- home_score - away_score
    g.total_points,
    case when g.home_score is null or g.away_score is null then null
         when g.home_score = g.away_score then null
         else (g.home_score > g.away_score) end         as home_win
from games g
left join home_geo hg on hg.code = g.home_team
left join away_geo ag on ag.code = g.away_team
