# MLB Edge-E7.9 — train/serve exposure audit (BATTER + STARTER MiLB-MLE priors)

> ⚠️ **Not an edge result.** This scopes a retrain; `best_alpha = 0`.

## Which SERVED contracts does the MLE actually touch?

| model / tier | features | E7.5/E7.5p columns in contract | train-serve skew |
|---|---:|---|---|
| total_runs/post_lineup | 13 | — | no |
| total_runs/pre_lineup | 14 | — | no |
| run_diff/post_lineup | 13 | — | no |
| run_diff/pre_lineup | 124 | `away_starter_eb_k_pct`, `home_starter_eb_k_pct`, `away_starter_eb_bb_pct` | **YES** |
| home_win/post_lineup | 19 | — | no |
| home_win/pre_lineup | 36 | — | no |

**Skewed contracts: run_diff/pre_lineup.** Every other served contract is UNAFFECTED — the MLE-moved columns are simply not in it, so for those models E7.9 is a new-feature question (`eb_gb_pct`) and not a skew repair.

## How much does the pitcher MLE move the served starter population?

- Starter rows (season ≥ 2021): **27,534**
- Cold-start (`age_band='u25'`): **5,991**
- Cold-start WITH an MLE prior (the rows whose `eb_k_pct`/`eb_bb_pct` actually change): **5,579** = 20.3% of starter rows (≈36.4% of games touch ≥1 moved starter)

Magnitude vs the generic experience-band prior mean — EXACT for `prior_only`, an UPPER BOUND for `full_eb` (the generic path would already have shrunk toward the observed line):

| eb_data_source | n | mean abs K% shift | p90 | mean abs BB% shift |
|---|---:|---:|---:|---:|
| full_eb | 4,681 | 0.0298 | 0.0624 | 0.0150 |
| prior_only | 898 | 0.0220 | 0.0481 | 0.0128 |

`eb_gb_pct` (the E7.5p column E7.9 joins through): 48,629/48,629 non-null, range 0.261–0.716.

## Leakage posture

- **mle_map** — leakage-safe by construction — emit_projections refits per debut cohort on STRICTLY-PRIOR cohorts; the minor line is strictly pre-debut. No as-of rebuild is needed for the historical backfill.
- **residual_full_sample_quantity** — the recalibrated kappa (one scalar per metric, from mle_prior.recalibrate) is fit on all graduates; it carries no player-specific information.

