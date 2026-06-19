-- E1.8 (§7.3) — regression guard for the team sequential-posterior producer chain.
--
-- feature_pregame_game_features reads `team_sequential_posteriors.prior_mu` as the PRE-game
-- (entering-G) belief. That is leakage-safe ONLY because of the producer invariant
-- (update_team_posteriors.py): the chain is ordered by (game_date, game_pk) and
--     prior_mu[N] == posterior_mu[N-1]   per (team, metric, season).
-- posterior_mu is the THROUGH-game value (includes game-G's own observation) and must never
-- be the basis of the chain. This guard fails if the producer regresses (e.g. reverts to the
-- documented WRONG pattern "prior_mu = current EB every game"), which shifts prior_mu far from
-- the prior posterior. See ablation_results/feature_leakage_audit.md §4 (sequential) + §7.3.
--
-- TOLERANCE — why this is not `> 1e-6` (verified against prod 2026-06-18):
--   The table is re-backfillable and carries up to 3 `update_ts` versions per grain. Picking
--   the latest version per grain to RE-RECONSTRUCT the chain post-hoc introduces a small
--   version-/doubleheader-alignment noise floor: 405/78,735 comparable rows (0.5%, all in one
--   re-backfilled season, all doubleheader-adjacent) differ by at most 0.0092 — these are
--   reconstruction artifacts, NOT leakage (the live consumer reads prior_mu per game_pk and
--   never reconstructs the chain). The 0.02 threshold (≈2× the observed artifact ceiling)
--   passes that noise while still failing on any gross chain break (which is an order of
--   magnitude larger). If this ever fires, inspect the magnitude: < ~0.01 = re-backfill
--   reconstruction noise (raise tolerance / dedup by batch); >> 0.02 = a real producer break.

with deduped as (
    -- collapse to one row per grain (latest version), defending against re-backfill duplicates
    select team, metric, season, game_pk, game_date, prior_mu, posterior_mu
    from {{ source('betting', 'team_sequential_posteriors') }}
    qualify row_number() over (
        partition by team, metric, season, game_pk
        order by update_ts desc
    ) = 1
),

chained as (
    select
        team, metric, season, game_pk, game_date,
        prior_mu,
        lag(posterior_mu) over (
            partition by team, metric, season
            order by game_date, game_pk
        ) as prev_posterior_mu
    from deduped
)

select team, metric, season, game_pk, game_date, prior_mu, prev_posterior_mu
from chained
where prev_posterior_mu is not null               -- exclude the season anchor (first game)
  and abs(prior_mu - prev_posterior_mu) > 0.02     -- > re-backfill reconstruction-noise floor (max observed 0.0092)
