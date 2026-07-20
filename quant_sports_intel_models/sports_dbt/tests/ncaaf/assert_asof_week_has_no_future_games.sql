-- ⭐⭐ THE LEAKAGE GATE for rollup_ncaaf_team_week_asof (NCAAF-P1.1).
--
-- Asserts: no as-of-week row can be traced to a game that had not yet kicked off.
--
-- ⚠️ THIS TEST IS DELIBERATELY DATE-BASED, NOT WEEK-BASED. The obvious test — "recompute
-- games_played with `week < as_of_week` and compare" — is worthless, because it re-uses the very
-- ordering the model used: if the ORDERING is wrong the filter is still satisfied and the test
-- passes green. That is not hypothetical. It is exactly what happened during P1.1: CFBD restarts
-- `week` at 1 for the postseason, so 2024 Ohio State had FIVE games at `week <= 1` (its opener
-- plus four CFP games played in December and January), every as-of row from week 2 onward
-- silently absorbed them, and a week-based recomputation test passed anyway.
--
-- So this test goes around the ordering entirely and uses the CLOCK, which cannot be wrong:
--   for each as-of row, take the FIRST KICKOFF DATE of its own as_of_week, then assert that every
--   game contributing to that row was played STRICTLY BEFORE it.
-- A future ordering bug moves a game across a calendar boundary, and this fails.
--
-- Returns violating rows; dbt fails the build if any are returned.

with week_start as (
    select
        season,
        season_order_week as as_of_week,
        min(game_date)    as first_kickoff
    from {{ ref('dim_ncaaf_game') }}
    where is_fbs_matchup
      and season_order_week is not null
    group by 1, 2
)

select
    r.season,
    r.team_id,
    r.team,
    r.as_of_week,
    w.first_kickoff,
    g.game_id           as leaking_game_id,
    g.game_date         as leaking_game_date,
    g.season_order_week as leaking_game_order_week
from {{ ref('rollup_ncaaf_team_week_asof') }} r
join week_start w
  on w.season = r.season
 and w.as_of_week = r.as_of_week
join {{ ref('fact_ncaaf_team_game') }} g
  on g.season = r.season
 and g.team_id = r.team_id
 and g.is_completed
 -- the games the rollup actually aggregated…
 and g.season_order_week < r.as_of_week
-- …any of which played ON or AFTER its own week's first kickoff is a leak
where g.game_date >= w.first_kickoff
