-- 🚨 E11.24 target 6 (2026-07-31) — the third and MOST CONSEQUENTIAL of the sequential-store
-- double-apply guards. See assert_player_sequential_no_double_apply.sql for the shared mechanism
-- (the pre-`--catchup` `statcast_catchup_job` hourly re-fire, closed 2026-07-19) and the
-- conservation identity this reuses.
--
-- AUDITED 2026-07-31: DIRTY. **All 25 current cells inflated**, ratio 1.158 avg / 1.188 max;
-- 598 of 3,556 season-2026 rows are extra versions of an already-written (cell, game_pk).
--
-- ⭐ WHY THIS ONE IS WORSE THAN ITS TWO SIBLINGS — THE CORRUPTED QUANTITY IS ACTUALLY SERVED.
--
-- The E9.53 team finding and the player finding both landed on "the store is wrong but the
-- consumed quantity is not": every consumer reads posterior_mu only, so a ~2.7× (team) or ~1.15×
-- (player) inflation of the observation count never reaches serving. THAT ARGUMENT DOES NOT HOLD
-- HERE. betting_ml/scripts/eb_priors/generate_matchup_signals.py::_load_seq_cell_posteriors
-- selects posterior_mu, **posterior_sigma AND n_pa_cumulative**, and assigns
--     active_cell_sigmas[bi, pi] = float(row["posterior_sigma"])
-- directly into the matchup signal's uncertainty. Since sigma ∝ 1/sqrt(n), a 1.158× inflation of
-- n_pa_cumulative makes the served cell sigma ~7.1% TOO SMALL — i.e. the matchup signal is
-- published as more certain than the data supports. So this is a serving-path calibration defect,
-- not merely a store defect, and it should be repaired rather than just noted.
--
-- The identity is the same conservation form (no external truth table needed):
--     n_pa_cumulative (at is_current) == Σ n_pa_observed over DISTINCT (cell, game_pk)
--
-- CURE when this fires:
--   uv run python betting_ml/scripts/sequential_bayes/update_matchup_cell_posteriors.py \
--       --backfill --season <yr> --reset

with truth as (
    select season, batter_archetype, pitcher_archetype, sum(n_pa_observed) as true_pa
    from (
        select distinct season, batter_archetype, pitcher_archetype, game_pk, n_pa_observed
        from {{ source('betting', 'matchup_cell_sequential_posteriors') }}
    )
    group by 1, 2, 3
),

current_cell as (
    select season, batter_archetype, pitcher_archetype, n_pa_cumulative, posterior_sigma
    from {{ source('betting', 'matchup_cell_sequential_posteriors') }}
    where is_current = TRUE
)

select
    c.season,
    c.batter_archetype,
    c.pitcher_archetype,
    t.true_pa,
    c.n_pa_cumulative,
    c.n_pa_cumulative / nullif(t.true_pa, 0) as pa_per_true_pa,
    c.posterior_sigma
from current_cell c
join truth t
  on  t.season            = c.season
 and  t.batter_archetype  = c.batter_archetype
 and  t.pitcher_archetype = c.pitcher_archetype
where t.true_pa > 0
  and c.n_pa_cumulative > 1.02 * t.true_pa
