-- 🚨 E11.24 target 6 (2026-07-31) — the sibling of assert_team_sequential_no_double_apply.
--
-- THE AUDIT THAT PRODUCED THIS. E9.53 fixed team_sequential_posteriors and flagged the two
-- siblings as "guarded but UNAUDITED". Audited 2026-07-31: **both are DIRTY on season 2026.**
--   player_sequential_posteriors : 1,010 of 1,513 current chains inflated, median ratio 1.147,
--                                  max 4.0 (5,627 (key, game_pk) pairs carry ≥2 versions).
--   seasons 2021-2025            : EXACTLY 1.0000 on every chain, 0 violations.
--
-- ⭐ A DIFFERENT MECHANISM FROM THE TEAM STORE, AND A DIFFERENT CHECK.
--
-- MECHANISM — not a backfill. Read straight off the SCD-2 history, player 679358 / xwoba_against
-- / game_pk 823692 was written THREE TIMES on 2026-06-23 (10:21, 12:13, 13:52 UTC), each write
-- re-absorbing the same game's 3 PA: n_cumulative 182 → 185 → 188. That is the hourly re-fire of
-- `statcast_catchup_job` (the E11.24 lever-1b finding) hitting a writer that then ran
-- `--date yesterday` UNCONDITIONALLY. It stops at 2026-07-19, when the `--catchup` frontier
-- (betting_ml/scripts/sequential_bayes/catchup.py) landed and made re-processing impossible — so
-- the ONGOING defect is already closed; what remains is the corrupted 2026 state.
--
-- CHECK — the team store's identity does NOT transfer. `win_prob` absorbs exactly one observation
-- per team per game, so `n_cumulative == games played` works there. A player's observations are
-- PA counts, so there is no games-based identity. What IS exact is a CONSERVATION identity that
-- needs no external truth table at all:
--
--     n_cumulative (at is_current)  ==  Σ n_obs over DISTINCT (chain, game_pk)
--
-- A replay re-applies an already-counted game, so n_cumulative grows while the DISTINCT-game_pk
-- sum does not. Validated two-sided before shipping (the oracle-floor discipline): the ratio is
-- EXACTLY 1.0000 on all five clean seasons and reaches 4.0 on the dirty one — so the check is
-- neither vacuous nor over-sensitive. `<` is legal and not flagged: a chain whose is_current row
-- predates its last game legitimately sits below the total.
--
-- SERVING IMPACT — SCOPE IT BEFORE ESCALATING (the E9.53 lesson). eb_batter_posteriors_raw and
-- eb_starter_posteriors are the only consumers and both select `sp.posterior_mu` ONLY; neither
-- reads posterior_sigma2 or n_cumulative. So, as with the team store, the corrupted SECOND MOMENT
-- is never served. UNLIKE the team store the MEAN does move here — a Normal-Normal update pulled
-- toward an already-absorbed observation drifts — but only slightly: median |Δposterior_mu| across
-- duplicated versions is 0.0022 xwoba (max 0.0436) on a ~0.31 scale.
--
-- CURE when this fires (the chain is non-idempotent — replay-once is the only correct repair):
--   uv run python betting_ml/scripts/sequential_bayes/update_player_posteriors.py \
--       --backfill --season <yr> --reset
-- `--reset` does the DELETE itself and is REQUIRED to backfill a populated season
-- (catchup.guard_or_reset_backfill).

with truth as (
    select season, player_id, player_type, metric, sum(n_obs) as true_obs
    from (
        select distinct season, player_id, player_type, metric, game_pk, n_obs
        from {{ source('betting', 'player_sequential_posteriors') }}
    )
    group by 1, 2, 3, 4
),

current_chain as (
    select season, player_id, player_type, metric, n_cumulative, posterior_mu
    from {{ source('betting', 'player_sequential_posteriors') }}
    where is_current = TRUE
)

select
    c.season,
    c.player_id,
    c.player_type,
    c.metric,
    t.true_obs,
    c.n_cumulative,
    c.n_cumulative / nullif(t.true_obs, 0) as observations_per_true_observation
from current_chain c
join truth t
  on  t.season      = c.season
 and  t.player_id   = c.player_id
 and  t.player_type = c.player_type
 and  t.metric      = c.metric
where t.true_obs > 0
  and c.n_cumulative > 1.02 * t.true_obs
