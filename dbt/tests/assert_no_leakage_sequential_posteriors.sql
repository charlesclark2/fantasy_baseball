-- E1.8 (§7.3) — regression guard for the consumer-enforced sequential-posterior leakage barrier.
--
-- feature_pregame_game_features reads `team_sequential_posteriors.prior_mu` as the PRE-game
-- (entering-G) belief. That is leakage-safe ONLY because of the producer invariant
-- (update_team_posteriors.py): the chain is ordered by (game_date, game_pk) and
--     prior_mu[N] == posterior_mu[N-1]   per (team, metric, season).
-- posterior_mu is the THROUGH-game value (includes game-G's own observation) and must never
-- be consumed as a pre-game feature. The first game of a season anchors to a league prior
-- (no lag) and is excluded.
--
-- If anyone repoints a consumer to posterior_mu-by-game_pk, breaks the chain order, or the
-- producer regresses to "prior_mu = current observation every game", prior_mu stops equaling
-- the prior game's posterior and this test returns rows → fail. The barrier can't regress
-- silently. See ablation_results/feature_leakage_audit.md §4 (sequential) + §7.3.

with deduped as (
    -- one row per grain (team, metric, season, game_pk); defends against any historical
    -- duplicate version from the MERGE upsert.
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
  and abs(prior_mu - prev_posterior_mu) > 1e-6     -- producer rounds to 8 dp; 1e-6 is slack
