-- ⭐⭐ THE LEAKAGE GATE for rollup_nfl_team_week_asof (NFL-N1.0).
--
-- Asserts: no as-of-week row can be traced to a game that had not yet kicked off.
--
-- ⚠️ THIS TEST IS DELIBERATELY DATE-BASED, NOT WEEK-BASED. The obvious test — "recompute
-- games_played with `week < as_of_week` and compare" — is worthless: it re-uses the very ordering
-- the model used, so if the ordering were ever wrong the filter is still satisfied and the test
-- passes green (exactly the NCAAF P1.1 postseason-week-1 failure mode). NFL `week` is verified
-- monotone today, but this test defends the invariant against a future regression regardless of
-- the ordering, by going around it and using the CLOCK:
--   for each as-of row, take the FIRST KICKOFF DATE of its own as_of_week, then assert every game
--   contributing to that row was played STRICTLY BEFORE it.
--
-- game_date is an ISO VARCHAR in the lake (INC-23) → cast ::date at the use-site. Returns
-- violating rows; dbt fails the build if any are returned.

with week_start as (
    select season, week as as_of_week, min(game_date::date) as first_kickoff
    from {{ ref('dim_nfl_game') }}
    where week is not null
    group by 1, 2
)

select
    r.season,
    r.team,
    r.as_of_week,
    w.first_kickoff,
    g.game_id           as leaking_game_id,
    g.game_date         as leaking_game_date,
    g.week              as leaking_game_week
from {{ ref('rollup_nfl_team_week_asof') }} r
join week_start w
  on w.season = r.season and w.as_of_week = r.as_of_week
join {{ ref('fct_nfl_team_game') }} g
  on g.season = r.season
 and g.team   = r.team
 and g.is_completed
 and g.week   < r.as_of_week          -- the games the rollup actually aggregated…
where g.game_date::date >= w.first_kickoff   -- …any played on/after its own week's first kickoff is a leak
