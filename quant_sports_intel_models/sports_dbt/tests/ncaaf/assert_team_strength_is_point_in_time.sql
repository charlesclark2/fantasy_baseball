-- ⭐⭐ THE LEAKAGE GATE for ncaaf_team_strength_week (NCAAF-P1.2).
--
-- The P1.2 posterior is fit OUTSIDE dbt (an iterative mixed-effects fit in
-- models/run_team_strength.py), so dbt cannot inspect the fit itself. What it CAN do is
-- audit the fit's own account of what it saw: `games_in_window` is the model's claim about
-- how many of a team's games were in scope for that as-of row. This test recomputes that
-- claim from the fact table and fails if it does not match — and then, crucially, checks
-- the claim against the CLOCK.
--
-- ⚠️ DELIBERATELY DATE-BASED, same reasoning as assert_asof_week_has_no_future_games. A
-- pure "recount with `season_order_week < as_of_week`" test re-uses the very ordering the
-- model used: if the ORDERING is wrong the count still matches and the test passes green.
-- That is not hypothetical — it is exactly the P1.1 failure (CFBD restarts `week` at 1 for
-- the postseason; 2024 Ohio State had five games at `week <= 1`). So this test asserts two
-- independent things:
--
--   (A) COUNT PARITY  — the model's `games_in_window` equals an independent recount of the
--       team's completed games strictly before its as-of week. Catches a window that
--       silently included or dropped games.
--   (B) CLOCK SANITY  — no game inside that window was played on or after the first kickoff
--       of the as-of week itself. Catches an ordering bug that (A) is blind to.
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
),

-- (A) independent recount of what the window SHOULD have contained
recount as (
    select
        s.season,
        s.team_id,
        s.as_of_week,
        s.games_in_window                                        as claimed_games,
        count(g.game_id)                                         as recounted_games,
        max(g.game_date)                                         as latest_game_in_window
    from {{ ref('ncaaf_team_strength_week') }} s
    left join {{ ref('fact_ncaaf_team_game') }} g
      on g.season = s.season
     and g.team_id = s.team_id
     and g.is_completed
     and g.season_order_week < s.as_of_week
    group by 1, 2, 3, 4
)

select
    r.season,
    r.team_id,
    r.as_of_week,
    r.claimed_games,
    r.recounted_games,
    r.latest_game_in_window,
    w.first_kickoff,
    case
        when r.claimed_games <> r.recounted_games              then 'count parity'
        when r.latest_game_in_window >= w.first_kickoff        then 'clock sanity'
    end                                                        as violation
from recount r
join week_start w
  on w.season = r.season
 and w.as_of_week = r.as_of_week
where r.claimed_games <> r.recounted_games
   or r.latest_game_in_window >= w.first_kickoff
