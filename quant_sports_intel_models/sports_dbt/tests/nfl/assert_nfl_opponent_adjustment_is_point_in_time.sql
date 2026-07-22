-- ⭐⭐ THE LEAKAGE GATE for rollup_nfl_team_week_opponent_adjusted (NFL-N1.0).
--
-- Asserts: each opponent's strength rating was read AS OF THE SAME WEEK, not at season's end.
--
-- ⚠️ WHY ITS OWN TEST. Opponent adjustment has a leak the as-of test cannot see: you can filter the
-- opponent LIST perfectly (only teams played before week W) and still leak by rating each opponent
-- with their FULL-SEASON numbers — crediting a week-6 team for beating an opponent who turned out
-- good in December, information that did not exist at kickoff. It is the most common way an
-- opponent-adjusted rating backtests better than it can perform live.
--
-- MECHANISM: `min_opponent_games` is the minimum games-played among opponents faced, as recorded
-- when their ratings were read. Recompute it independently from the as-of rollup pinned to the SAME
-- as_of_week. If the model had read opponents at their season-final state, its min_opponent_games
-- would reflect final game counts and diverge immediately. Any mismatch fails the build.
-- Rows where no opponent rating resolved (min_opponent_games IS NULL) are excluded — nothing to
-- verify, and `adjustment_applied` reports it honestly.

with opponents_faced as (
    select a.season, a.team, a.as_of_week, g.opponent
    from {{ ref('rollup_nfl_team_week_opponent_adjusted') }} a
    join {{ ref('fct_nfl_team_game') }} g
      on g.season = a.season
     and g.team   = a.team
     and g.week   < a.as_of_week
     and g.is_completed
),

expected as (
    select o.season, o.team, o.as_of_week, min(w.games_played) as expected_min_opponent_games
    from opponents_faced o
    join {{ ref('rollup_nfl_team_week_asof') }} w
      on w.season     = o.season
     and w.team       = o.opponent
     and w.as_of_week = o.as_of_week       -- ⭐ the pinning under test
    where w.games_played > 0
    group by 1, 2, 3
)

select
    a.season, a.team, a.as_of_week,
    a.min_opponent_games, e.expected_min_opponent_games
from {{ ref('rollup_nfl_team_week_opponent_adjusted') }} a
join expected e
  on e.season = a.season and e.team = a.team and e.as_of_week = a.as_of_week
where a.min_opponent_games is not null
  and a.min_opponent_games is distinct from e.expected_min_opponent_games
