# Matchup Model Design

**Epic 8 — Bayesian Archetype × Archetype Interaction Matrix**

---

## Problem Statement

A raw 5×5 archetype interaction matrix has 25 cells with very different effective sample sizes even after soft-assignment weighting. Cells representing common matchup types (e.g., high-whiff batter vs. power pitcher) accumulate far more PA-weight than rare combinations. Raw rates from thin cells are noisy; fitting a standard model on them leads to overfitting. Hierarchical shrinkage degrades thin cells gracefully toward the additive combination of marginal effects, preserving signal where data is abundant and borrowing strength across cells where it is not.

---

## Archetype Definitions

**Batter archetypes (5):** `groundball_speed`, `high_whiff`, `contact_spray`, `patient_obp`, `power_pull`

**Pitcher archetypes (5):** `changeup_deceptive`, `multi_pitch_mix`, `power_swing_and_miss`, `contact_sinker_ball`, `soft_command`

Cluster assignments: `baseball_data.statsapi.batter_clusters` / `pitcher_clusters` (2015+, hard MAP).

Soft posteriors: `baseball_data.betting.mart_player_archetype_posteriors` (2016+ as of 2026-06-02 backfill).

---

## Additive Decomposition Model

For each metric (xwOBA primary; wOBA, K%, BB%, hard-hit% as secondaries), each cell mean is decomposed as:

```
μ_cell(b, p) = grand_mean
             + batter_archetype_effect[b]
             + pitcher_archetype_effect[p]
             + interaction_term[b, p]
```

Where:
- **`grand_mean`** — league-wide mean of the metric over the calibration window
- **`batter_archetype_effect[b]`** — how batter archetype `b` tends to outperform or underperform the grand mean, estimated from all PA involving that archetype regardless of pitcher
- **`pitcher_archetype_effect[p]`** — how pitcher archetype `p` tends to suppress or allow relative to grand mean, estimated from all PA regardless of batter
- **`interaction_term[b, p]`** — the residual after removing both marginal effects; the true matchup-specific departure from the additive prediction

The additive model without interactions (setting all interaction terms to zero) is the fallback for cells with insufficient data.

---

## Shrinkage on Interaction Terms

Each interaction term receives a `Normal(0, σ_interaction)` prior. The empirical Bayes shrinkage formula:

```
shrunk_interaction[b, p] = raw_interaction[b, p]
                         × n_cell / (n_cell + σ²_noise / σ²_interaction)
```

Where:
- `n_cell` — soft-weighted PA count for the cell in the estimation window
- `σ²_noise` — per-PA variance of the outcome metric (xwOBA ≈ 0.43² = 0.185)
- `σ²_interaction` — empirically estimated variance of raw interaction residuals across cells with sufficient data (≥ 200 soft-weighted PA)

The **shrinkage factor** `n_cell / (n_cell + σ²_noise / σ²_interaction)` is bounded [0, 1]:
- Approaches 1 for data-rich cells → interaction term trusted as estimated
- Approaches 0 for data-poor cells → interaction term zeroed toward 0 (additive model only)

---

## Cell Data Source Classification

| Condition | `cell_data_source` | Meaning |
|---|---|---|
| `total_pa_weight ≥ 50` | `full_eb` | Enough data to update the prior; EB shrinkage applied |
| `total_pa_weight < 50` | `marginals_only` | Prior dominates; interaction term set to 0; use additive prediction only |

With soft-assignment posteriors and the 2016–2020 calibration window, all 25 cells are expected to be `full_eb`.

---

## Data Windows

| Window | Seasons | Purpose |
|---|---|---|
| EB calibration (pre-training) | 2016–2020 | Estimates grand_mean, batter_effects, pitcher_effects, σ_interaction |
| Training / evaluation | 2021–2025 | Model training for Stories 8.1 and 8.2 |
| Live inference | Current season | Sequential posterior updates (Story 8.5) |

The 2016–2020 / 2021+ split avoids using training data to set the prior, preventing mild information leakage in the EB estimation.

**Soft posteriors methodology:** All PA in both windows use soft cluster probabilities from `mart_player_archetype_posteriors`. The same KMeans model (fit on 2015+ pooled data) underlies both windows. Posteriors for 2016–2020 were backfilled 2026-06-02 using `compute_archetype_posteriors.py --mode backfill --season {year}`.

**Rolling window in the mart:** `mart_batter_archetype_vs_pitcher_cluster` uses a 180-day rolling window. For EB calibration, end-of-season snapshots (last game_date per season per cell) are used to avoid double-counting across overlapping windows.

---

## Phase 1 — Empirical Bayes (Current)

Script: `betting_ml/scripts/eb_priors/fit_matchup_cell_priors.py`
Output: `betting_ml/models/eb_priors/matchup_cell_priors.json`

Algorithm:
1. Pull end-of-season snapshots from `mart_batter_archetype_vs_pitcher_cluster` for 2016–2020 (QUALIFY window = last game_date per cell per season)
2. Aggregate per cell: `total_pa_weight = SUM(pa_weight)`, `cell_mean_xwoba = weighted_avg(raw_xwoba, pa_weight)`
3. `grand_mean` = total-PA-weight-weighted average of all cell means
4. `batter_effect[b]` = weighted average across all pitcher archetypes for batter `b` − grand_mean
5. `pitcher_effect[p]` = weighted average across all batter archetypes for pitcher `p` − grand_mean
6. `raw_interaction[b, p]` = `cell_mean[b, p] − grand_mean − batter_effect[b] − pitcher_effect[p]`
7. Fit `Normal(0, σ_interaction)` to residuals from cells with `total_pa_weight ≥ 200`; estimate `σ_interaction = std(raw_interactions)`
8. Apply shrinkage formula per cell
9. Validate: skewness and kurtosis of raw residuals; directional sense checks; AC verification
10. Write JSON output

---

## Phase 2 — Full PyMC Hierarchical Model (Epic 17)

```python
with pm.Model() as matchup_hierarchical:
    grand_mean    = pm.Normal("grand_mean", mu=0.315, sigma=0.02)
    σ_batter      = pm.HalfNormal("σ_batter", sigma=0.03)
    batter_effect = pm.Normal("batter_effect", mu=0, sigma=σ_batter,
                               shape=n_batter_archetypes)
    σ_pitcher      = pm.HalfNormal("σ_pitcher", sigma=0.03)
    pitcher_effect = pm.Normal("pitcher_effect", mu=0, sigma=σ_pitcher,
                                shape=n_pitcher_archetypes)
    σ_interaction  = pm.HalfNormal("σ_interaction", sigma=0.015)
    interaction    = pm.Normal("interaction", mu=0, sigma=σ_interaction,
                               shape=(n_batter_archetypes, n_pitcher_archetypes))
    μ      = (grand_mean + batter_effect[batter_idx]
              + pitcher_effect[pitcher_idx] + interaction[batter_idx, pitcher_idx])
    σ_obs  = pm.HalfNormal("σ_obs", sigma=0.05)
    xwoba  = pm.Normal("xwoba", mu=μ, sigma=σ_obs, observed=observed_xwoba)
```

Phase 2 replaces the closed-form EB estimate with full posterior sampling. The Phase 1 EB estimates serve as warm-start priors for Phase 2.

---

## Output Schema — matchup_cell_priors.json

```json
{
  "metadata": {
    "fit_date": "YYYY-MM-DD",
    "calibration_window": [2016, 2020],
    "n_batter_archetypes": 5,
    "n_pitcher_archetypes": 5,
    "n_cells": 25,
    "sigma_noise": 0.43,
    "sigma_noise_squared": 0.1849
  },
  "global": {
    "grand_mean_xwoba": 0.315,
    "sigma_interaction": 0.015,
    "sigma_interaction_squared": 0.000225,
    "residual_skewness": 0.12,
    "residual_kurtosis": 0.45
  },
  "batter_effects": { "power_pull": 0.023, ... },
  "pitcher_effects": { "soft_command": -0.018, ... },
  "cells": {
    "power_pull__soft_command": {
      "batter_archetype": "power_pull",
      "pitcher_archetype": "soft_command",
      "cell_mean_xwoba": 0.338,
      "raw_interaction": 0.010,
      "shrunk_interaction": 0.009,
      "mu_cell": 0.338,
      "cell_n_pa": 18500.0,
      "cell_shrinkage_factor": 0.91,
      "cell_data_source": "full_eb"
    },
    ...
  }
}
```

---

## Story 8.2 — Two-Model Minimum

**Candidate A (baseline):** Gradient boosted or Ridge regression on raw cell features — no explicit shrinkage.

**Candidate B (Bayesian EB):** Uses shrunk interaction terms from this prior as primary features:
- `shrunk_interaction[b, p]`
- `batter_effect[b]`
- `pitcher_effect[p]`
- `cell_shrinkage_factor` (encodes data confidence)
- `cell_sparsity_flag` (boolean)

Expected advantage of Candidate B: meaningfully lower NLL specifically on sparse cells, where shrinkage prevents overfitting to noisy raw rates.

Output signals: `matchup_advantage_mu`, `matchup_advantage_sigma`.

---

---

## Story 8.1 — Training Dataset Sparsity Matrix (2026-06-02)

Hard MAP n_pa totalled across 2021–2025 seasons (prior-season cluster labels, leakage rule applied).

```
                       changeup_deceptive  contact_sinker_ball  multi_pitch_mix  power_swing_and_miss  soft_command
contact_spray                      20,983               28,994           29,290                34,442        18,057
groundball_speed                   10,457               14,534           14,629                16,797         8,563
high_whiff                         15,570               20,994           20,165                24,265        12,495
patient_obp                        15,746               21,671           20,879                25,336        13,752
power_pull                         18,396               24,047           24,198                29,236        17,095
```

All 25 cells dense (> 200 PA threshold). `cell_sparsity_flag = False` for all 125 rows.

Per-season coverage:

| Season | Cells | Min PA | Max PA | Sparse |
|--------|-------|--------|--------|--------|
| 2021   | 25    | 1,420  | 4,592  | 0      |
| 2022   | 25    | 2,208  | 8,497  | 0      |
| 2023   | 25    | 2,065  | 9,393  | 0      |
| 2024   | 25    | 1,534  | 7,389  | 0      |
| 2025   | 25    | 1,306  | 8,560  | 0      |

Dataset summary: 125 rows; `hard_xwoba_mean` range [0.2740, 0.3714]; `raw_interaction_residual` range [−0.0195, +0.0334] (std = 0.0120 — well within EB prior-dominant regime consistent with σ_interaction = 0.0033 from 8.0).

*Last updated: 2026-06-02 (Epic 8.1 training dataset complete)*
