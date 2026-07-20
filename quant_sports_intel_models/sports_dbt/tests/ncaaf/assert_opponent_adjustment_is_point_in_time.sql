-- ⭐⭐ THE LEAKAGE GATE for rollup_ncaaf_team_week_opponent_adjusted (NCAAF-P1.1).
--
-- Asserts: each opponent's strength rating was read AS OF THE SAME WEEK, not at season's end.
--
-- ⚠️ WHY THIS NEEDS ITS OWN TEST. Opponent adjustment has a leak the as-of test cannot see. You
-- can filter the opponent LIST perfectly — only teams actually played before week W — and still
-- leak badly, by rating each of those opponents using their FULL-SEASON numbers. It feels
-- innocent ("the opponent's later games aren't about us") but it is not: at week 6 you would be
-- crediting a team for beating an opponent who turned out to be good in November. That
-- information did not exist at kickoff. It is the single most common way a published
-- opponent-adjusted rating backtests far better than it can possibly perform live.
--
-- THE MECHANISM OF THE TEST: `min_opponent_games` is the minimum games-played among the
-- opponents faced, as recorded when their ratings were read. Recompute it independently from the
-- as-of rollup pinned to the SAME as_of_week. If the model read opponents at their season-final
-- state, its `min_opponent_games` would reflect final game counts (~11–13) and diverge from this
-- point-in-time recomputation immediately. Any mismatch is returned and fails the build.
--
-- Rows where no opponent rating was resolvable (min_opponent_games IS NULL — nothing was read)
-- are excluded: there is nothing to verify, and `adjustment_applied` already reports it honestly.

with opponents_faced as (
    select
        a.season,
        a.team_id,
        a.as_of_week,
        g.opponent_team_id
    from {{ ref('rollup_ncaaf_team_week_opponent_adjusted') }} a
    join {{ ref('fact_ncaaf_team_game') }} g
      on g.season = a.season
     and g.team_id = a.team_id
     and g.season_order_week < a.as_of_week
     and g.is_completed
),

-- the independent recomputation: opponent state pinned to THE SAME as_of_week
expected as (
    select
        o.season,
        o.team_id,
        o.as_of_week,
        min(w.games_played) as expected_min_opponent_games
    from opponents_faced o
    join {{ ref('rollup_ncaaf_team_week_asof') }} w
      on w.season     = o.season
     and w.team_id    = o.opponent_team_id
     and w.as_of_week = o.as_of_week      -- ⭐ the pinning under test
    where w.games_played > 0
    group by 1, 2, 3
)

select
    a.season,
    a.team_id,
    a.team,
    a.as_of_week,
    a.min_opponent_games,
    e.expected_min_opponent_games
from {{ ref('rollup_ncaaf_team_week_opponent_adjusted') }} a
join expected e
  on e.season = a.season
 and e.team_id = a.team_id
 and e.as_of_week = a.as_of_week
where a.min_opponent_games is not null
  and a.min_opponent_games is distinct from e.expected_min_opponent_games
