-- ⭐⭐ THE LEAKAGE GATE for feature_ncaaf_pregame_matrix (NCAAF-P1.3).
--
-- This is THE matrix every downstream P1.4 model trains on, so a silent leak here contaminates
-- everything. The gate audits, for BOTH sides of every matchup, that the team's pregame feature
-- snapshot could only have seen games that had already kicked off — measured against THIS game's
-- own kickoff, which is the true per-matchup leakage boundary.
--
-- ⚠️ DELIBERATELY DATE-BASED, per the P1.1 lesson (and verified to FAIL on a tampered row by the
-- fast-gate test test_ncaaf_feature_matrix.py). A pure "recount with season_order_week < W" test
-- re-uses the very ordering the matrix used: if the ORDERING is wrong the filter is still
-- satisfied and the test passes green — exactly the P1.1 postseason-week=1 collision. So this
-- asserts two INDEPENDENT things per side:
--
--   (A) COUNT PARITY  — the matrix's `{home,away}_games_played` (what the joined rollup claims was
--       in scope) equals an independent recount of the team's completed games with
--       season_order_week < the game's own season_order_week. Catches a snapshot joined at the
--       WRONG week (e.g. W+1, which would pull the game's own result in).
--   (B) CLOCK SANITY  — no game inside that window was played ON OR AFTER this specific game's
--       kickoff date. Catches an ordering bug that (A), which re-uses the ordering, is blind to.
--
-- NULL games_played (a week-1 / no-coverage row) is exempt from (A): the matrix legitimately has
-- no rollup there, so there is nothing to recount — the clock check (B) still applies vacuously
-- (an empty window cannot contain a future game). Returns violating rows; dbt fails on any.

with sides as (
    select game_id, season, home_team_id as team_id, season_order_week, game_date,
           home_games_played as claimed_games
    from {{ ref('feature_ncaaf_pregame_matrix') }}
    union all
    select game_id, season, away_team_id as team_id, season_order_week, game_date,
           away_games_played as claimed_games
    from {{ ref('feature_ncaaf_pregame_matrix') }}
),

recount as (
    select
        s.game_id,
        s.season,
        s.team_id,
        s.season_order_week,
        s.game_date                                              as kickoff_date,
        s.claimed_games,
        count(g.game_id)                                         as recounted_games,
        max(g.game_date)                                         as latest_game_in_window
    from sides s
    left join {{ ref('fact_ncaaf_team_game') }} g
      on g.season = s.season
     and g.team_id = s.team_id
     and g.is_completed
     and g.season_order_week < s.season_order_week
    group by 1, 2, 3, 4, 5, 6
)

select
    game_id,
    season,
    team_id,
    season_order_week,
    kickoff_date,
    claimed_games,
    recounted_games,
    latest_game_in_window,
    case
        when claimed_games is not null and claimed_games <> recounted_games then 'count parity'
        when latest_game_in_window >= kickoff_date                          then 'clock sanity'
    end                                                          as violation
from recount
where (claimed_games is not null and claimed_games <> recounted_games)
   or latest_game_in_window >= kickoff_date
