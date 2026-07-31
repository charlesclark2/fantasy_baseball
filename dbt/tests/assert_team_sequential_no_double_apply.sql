-- 🚨 2026-07-31 — regression guard for a NON-IDEMPOTENT backfill double-applying a season.
--
-- THE DEFECT: update_team_posteriors.py::run_backfill replays a whole season on top of whatever
-- state already exists (`_load_current_seq` loads the existing posterior as the PRIOR; `_prep`
-- only ensures DDL — no truncate, no check). So every `--backfill` against a POPULATED table
-- applies an ENTIRE EXTRA SEASON of observations to the same chains. Three replays had
-- accumulated on season 2026 before this was found (2026-06-03 correct on an empty table, an
-- undetected re-run 2026-06-04, and one 2026-07-31).
--
-- ⭐ WHY IT HID FOR TWO MONTHS, AND WHY THIS TEST COUNTS INSTEAD OF COMPARING VALUES:
-- the duplicates are replays of the SAME games, so `posterior_mu` stays ≈ the true record — the
-- MEAN looks perfect and every value-based sanity check passes. Only the second moment is wrong:
-- `posterior_sigma2 ∝ 1/(param_a + param_b)`, so the served belief was ~2.7× OVERCONFIDENT. That
-- feeds feature_pregame_game_features_raw's unconditional-core discriminative team_sequential_*
-- family, i.e. it is a serving-path CALIBRATION defect that no mean-based check can detect.
-- WHEN A REPLAY CORRUPTS ONLY THE SECOND MOMENT, ASSERT ON A COUNT, NOT ON A VALUE.
--
-- THE INVARIANT: `win_prob` is Beta-Binomial and absorbs exactly ONE observation per team per
-- completed game (`n_obs = 1` in update_team_posteriors._collect_observations), so
--     n_cumulative == games played
-- is an EXACT identity for every (season, team) — not a heuristic. It is also the ONLY reason the
-- inflation was findable at all. off_xwoba / bullpen_xwoba accumulate PA counts and have no such
-- clean identity, but they are written in the same pass, so guarding win_prob guards all three.
--
-- TOLERANCE: 1.02 (2%). A genuine double-apply is ~2×, so this is nowhere near it; the headroom
-- absorbs the handful of team-alias rows that make a couple of historical seasons report 32
-- "teams" and a 0.994 ratio (verified 2026-07-31: seasons 2021-2025 all sit at ratio 1.000).
--
-- CURE when this fires: the chain is non-idempotent, so a clean rebuild is the only correct fix —
--   DELETE FROM baseball_data.betting.team_sequential_posteriors WHERE season = <yr>;
--   uv run python betting_ml/scripts/sequential_bayes/update_team_posteriors.py \
--       --backfill --season <yr> --reset
-- `--reset` does the DELETE for you and is now REQUIRED to backfill a populated season
-- (catchup.guard_or_reset_backfill), so this should only ever fire on pre-guard data.

with played as (
    select game_year as season, team, count(*) as games
    from (
        select game_year, home_team as team
        from {{ ref('mart_game_results') }}
        where game_type = 'R' and home_team_won is not null
        union all
        select game_year, away_team
        from {{ ref('mart_game_results') }}
        where game_type = 'R' and home_team_won is not null
    )
    group by 1, 2
),

current_win_prob as (
    select season, team, n_cumulative, param_a, param_b
    from {{ source('betting', 'team_sequential_posteriors') }}
    where is_current = TRUE
      and metric = 'win_prob'
)

select
    p.season,
    p.team,
    pl.games,
    p.n_cumulative,
    p.n_cumulative / nullif(pl.games, 0) as observations_per_game,
    p.param_a,
    p.param_b
from current_win_prob p
join played pl
  on pl.team = p.team
 and pl.season = p.season
where pl.games > 0
  and p.n_cumulative > 1.02 * pl.games
