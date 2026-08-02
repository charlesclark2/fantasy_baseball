# E7.13 Phase 2 — comp-based projection: DISPLAY_ONLY

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": "forward, relaxed maturity",
 "gates": null,
 "n_arms": 2,
 "n_folds": 4,
 "per_metric": [
  {
   "metric": "batter",
   "n_arms": null,
   "n_folds": 4,
   "verdict": "BLEND_ELIGIBLE_NOT_WIRED"
  },
  {
   "metric": "pitcher",
   "n_arms": null,
   "n_folds": 4,
   "verdict": "DISPLAY_ONLY"
  }
 ],
 "primary_contrast": "randomized-PIT max decile deviation <= 0.05",
 "reason": null,
 "schema": 1,
 "source_artifact": "e7_13_artifacts/e7_13_comp_validation.json",
 "status": "recovered",
 "verdict": "DISPLAY_ONLY"
}
-->


**Target** — fantasy_points over the 3 seasons after the board (0 for a prospect who never reached MLB)
**Primary metric** — CRPS (proper — the target is 47% exact zeros; MAE inverts here)
**Constraint** — randomized-PIT max decile deviation <= 0.05
**Incumbent** — `fv_bucket`

## ⚠️ Fold ceiling

Strictly-matured folds available: `{'batter': 1, 'pitcher': 1}`.

A strictly-matured backtest (production's rule) admits at most ONE fold at this archive depth — see comp_validation's FOLD CEILING section. The primary run therefore relaxes the pool to 'any strictly earlier board season', which grants historical queries hindsight. Every arm reads the identical pool, so the HEAD-TO-HEAD stays fair while the LEVELS are optimistic. Re-opens mechanically: 2 strictly-matured folds in 2027, 4 in 2029.

## Batters — BLEND_ELIGIBLE_NOT_WIRED

Pool 2597 rows, non-debut share **0.6088** (the busts are IN the pool). 1777/2229 rows scoreable by every contender.

| arm | kind | CRPS | PIT max-decile-dev | p10–p90 coverage |
|---|---|---|---|---|
| `oracle_k15` 🎯 floor | anchor | 9.27 | 0.1515 | 0.948 |
| `comp_gower_k25` | comp | 64.81 | 0.0261 | 0.849 |
| `comp_gower_k15` | comp | 65.27 | 0.0398 | 0.831 |
| `comp_gower_k10` | comp | 66.64 | 0.0863 | 0.876 |
| `comp_mahalanobis_k15` | comp | 66.73 | 0.0403 | 0.836 |
| `blend_comp_fv` | blend | 67.14 | 0.0266 | 0.842 |
| `comp_gower_k15_simweighted` | comp | 69.03 | 0.0739 | 0.764 |
| `comp_no_fv_k15` | comp | 70.04 | 0.0342 | 0.838 |
| `fv_bucket` | bucket | 73.44 | 0.0615 | 0.804 |
| `comp_components_only_k15` | comp | 74.00 | 0.0494 | 0.835 |
| `marginal` 🚧 ceiling | degenerate | 79.17 | 0.0266 | 0.845 |
| `random_k15` 🎲 placebo | placebo | 83.16 | 0.0465 | 0.844 |
| `all_zero` 🚧 ceiling | degenerate | 105.99 | 0.5151 | 0.391 |

**Best contender** — `comp_gower_k25`

### Two-sided anchors

* `oracle_is_the_floor` = **True**
* `oracle_crps` = **9.271**
* `all_zero_loses` = **True**
* `all_zero_crps` = **105.992**
* `marginal_loses` = **True**
* `marginal_crps` = **79.167**
* `placebo_loses` = **True**
* `placebo_crps` = **83.163**
* `all_pass` = **True**

### Matched foils (paired ΔCRPS, negative = the arm is better)

| comparison | arm | foil | ΔCRPS | 95% CI | p | arm better |
|---|---|---|---|---|---|---|
| selected_vs_incumbent | `comp_gower_k25` | `fv_bucket` | -8.63 | [-11.00, -6.54] | 0.0000 | True |
| comp_vs_incumbent | `comp_gower_k15` | `fv_bucket` | -8.17 | [-10.73, -5.82] | 0.0000 | True |
| blend_vs_incumbent | `blend_comp_fv` | `fv_bucket` | -6.31 | [-7.73, -5.05] | 0.0000 | True |
| blend_vs_comp | `blend_comp_fv` | `comp_gower_k15` | +1.87 | [+0.73, +3.05] | 0.0005 | False |
| fv_channel | `comp_gower_k15` | `comp_no_fv_k15` | -4.77 | [-7.14, -2.46] | 0.0000 | True |
| structural_channel | `comp_gower_k15` | `comp_components_only_k15` | -8.73 | [-11.18, -6.15] | 0.0000 | True |
| similarity_channel | `comp_gower_k15` | `random_k15` | -17.89 | [-20.93, -14.77] | 0.0000 | True |
| kernel_channel | `comp_gower_k15` | `comp_gower_k15_simweighted` | -3.76 | [-5.18, -2.44] | 0.0000 | True |

### Deflation

* PBO (contender set) — `0.0` over 6 splits; whole field `0.0`
* Performance degradation — `0.0`
* Flip distribution — `{'comp_gower_k15': 1, 'comp_gower_k25': 5}`
* DSR — contender set `1.0`, whole field `1.0` (n = 919 CLUSTERS, not 1777 rows)
* Spread — contender 14.18%, whole field 1043.24%
* BH-FDR — cutoff `0.05`, rejects `[True, True, True, True, True, True, True]`

### Gates

* `anchors_pass` — **PASS**
* `beats_incumbent` — **PASS**
* `pbo_lt_0_2` — **PASS**
* `dsr_contender_ge_0_95` — **PASS**
* `pit_flat` — **PASS**
* `fdr_survives` — **PASS**

## Pitchers — DISPLAY_ONLY

Pool 2648 rows, non-debut share **0.6148** (the busts are IN the pool). 2015/2297 rows scoreable by every contender.

| arm | kind | CRPS | PIT max-decile-dev | p10–p90 coverage |
|---|---|---|---|---|
| `oracle_k15` 🎯 floor | anchor | 7.21 | 0.1541 | 0.975 |
| `comp_gower_k25` | comp | 97.90 | 0.0350 | 0.847 |
| `blend_comp_fv` | blend | 98.34 | 0.0315 | 0.846 |
| `comp_mahalanobis_k15` | comp | 99.87 | 0.0484 | 0.827 |
| `comp_gower_k15` | comp | 99.88 | 0.0419 | 0.834 |
| `fv_bucket` | bucket | 101.15 | 0.0409 | 0.838 |
| `comp_gower_k10` | comp | 102.37 | 0.0935 | 0.870 |
| `comp_no_fv_k15` | comp | 104.94 | 0.0459 | 0.845 |
| `comp_gower_k15_simweighted` | comp | 106.98 | 0.0663 | 0.763 |
| `marginal` 🚧 ceiling | degenerate | 107.58 | 0.0191 | 0.860 |
| `comp_components_only_k15` | comp | 110.54 | 0.0479 | 0.840 |
| `random_k15` 🎲 placebo | placebo | 115.14 | 0.0474 | 0.842 |
| `all_zero` 🚧 ceiling | degenerate | 146.01 | 0.5203 | 0.401 |

**Best contender** — `comp_gower_k25`

### Two-sided anchors

* `oracle_is_the_floor` = **True**
* `oracle_crps` = **7.21**
* `all_zero_loses` = **True**
* `all_zero_crps` = **146.012**
* `marginal_loses` = **True**
* `marginal_crps` = **107.577**
* `placebo_loses` = **True**
* `placebo_crps` = **115.141**
* `all_pass` = **True**

### Matched foils (paired ΔCRPS, negative = the arm is better)

| comparison | arm | foil | ΔCRPS | 95% CI | p | arm better |
|---|---|---|---|---|---|---|
| selected_vs_incumbent | `comp_gower_k25` | `fv_bucket` | -3.25 | [-5.19, -1.41] | 0.0010 | True |
| comp_vs_incumbent | `comp_gower_k15` | `fv_bucket` | -1.27 | [-3.64, +0.88] | 0.2755 | True |
| blend_vs_incumbent | `blend_comp_fv` | `fv_bucket` | -2.81 | [-4.02, -1.71] | 0.0000 | True |
| blend_vs_comp | `blend_comp_fv` | `comp_gower_k15` | -1.54 | [-2.63, -0.37] | 0.0055 | True |
| fv_channel | `comp_gower_k15` | `comp_no_fv_k15` | -5.06 | [-7.52, -2.43] | 0.0000 | True |
| structural_channel | `comp_gower_k15` | `comp_components_only_k15` | -10.66 | [-13.44, -7.92] | 0.0000 | True |
| similarity_channel | `comp_gower_k15` | `random_k15` | -15.26 | [-18.70, -12.02] | 0.0000 | True |
| kernel_channel | `comp_gower_k15` | `comp_gower_k15_simweighted` | -7.10 | [-8.97, -5.26] | 0.0000 | True |

### Deflation

* PBO (contender set) — `0.0` over 6 splits; whole field `0.0`
* Performance degradation — `0.0`
* Flip distribution — `{'comp_gower_k25': 5, 'blend_comp_fv': 1}`
* DSR — contender set `0.9448`, whole field `0.9197` (n = 1075 CLUSTERS, not 2015 rows)
* Spread — contender 12.9%, whole field 1925.21%
* BH-FDR — cutoff `0.04285714285714286`, rejects `[True, False, True, True, True, True, True]`

### Gates

* `anchors_pass` — **PASS**
* `beats_incumbent` — **PASS**
* `pbo_lt_0_2` — **PASS**
* `dsr_contender_ge_0_95` — **FAIL**
* `pit_flat` — **PASS**
* `fdr_survives` — **PASS**

## Ordering study — may a comp term touch the board's RANKING?

CRPS grades a distribution; a draft board is purely ordinal. This is the statistic that governs `blend_score` / `model_score`. Incumbent = the board's own formula (`board_proxy`, reconstructed from `board_assembly`'s constants).

### Batters — `comp_mean_fp` (comp arm `comp_gower_k25`)

Best contender `board_plus_comp_w40`, ΔIC vs the board's own formula **+0.0817**, improved in 4/4 folds (per fold [0.049, 0.1074, 0.0948, 0.0754]). PBO `0.0`. Anchors: oracle-is-ceiling `True`, placebo IC `0.0155`.

| arm | rank-IC |
|---|---|
| `oracle_order` | +1.0000 |
| `board_plus_comp_w40` | +0.5699 |
| `comp_only` | +0.5661 |
| `board_plus_comp_w30` | +0.5603 |
| `board_plus_comp_w20` | +0.5446 |
| `board_plus_comp_w10` | +0.5205 |
| `board_proxy` | +0.4883 |
| `fv_only` | +0.4050 |
| `random_order` | +0.0155 |

### Batters — `comp_median_fp` (comp arm `comp_gower_k25`)

Best contender `board_plus_comp_w40`, ΔIC vs the board's own formula **+0.0833**, improved in 4/4 folds (per fold [0.044, 0.1087, 0.1023, 0.0781]). PBO `0.0`. Anchors: oracle-is-ceiling `True`, placebo IC `-0.0186`.

| arm | rank-IC |
|---|---|
| `oracle_order` | +1.0000 |
| `board_plus_comp_w40` | +0.5715 |
| `board_plus_comp_w30` | +0.5639 |
| `comp_only` | +0.5631 |
| `board_plus_comp_w20` | +0.5481 |
| `board_plus_comp_w10` | +0.5218 |
| `board_proxy` | +0.4883 |
| `fv_only` | +0.4050 |
| `random_order` | -0.0186 |

### Pitchers — `comp_mean_fp` (comp arm `comp_gower_k25`)

Best contender `board_plus_comp_w40`, ΔIC vs the board's own formula **+0.0410**, improved in 4/4 folds (per fold [0.036, 0.0026, 0.0715, 0.0538]). PBO `0.16666666666666666`. Anchors: oracle-is-ceiling `True`, placebo IC `-0.0017`.

| arm | rank-IC |
|---|---|
| `oracle_order` | +1.0000 |
| `board_plus_comp_w40` | +0.4086 |
| `board_plus_comp_w30` | +0.4050 |
| `comp_only` | +0.3993 |
| `board_plus_comp_w20` | +0.3989 |
| `board_plus_comp_w10` | +0.3884 |
| `board_proxy` | +0.3676 |
| `fv_only` | +0.3671 |
| `random_order` | -0.0017 |

### Pitchers — `comp_median_fp` (comp arm `comp_gower_k25`)

Best contender `board_plus_comp_w40`, ΔIC vs the board's own formula **+0.0448**, improved in 4/4 folds (per fold [0.0395, 0.0149, 0.0732, 0.0517]). PBO `0.5`. Anchors: oracle-is-ceiling `True`, placebo IC `0.0197`.

| arm | rank-IC |
|---|---|
| `oracle_order` | +1.0000 |
| `board_plus_comp_w40` | +0.4124 |
| `board_plus_comp_w30` | +0.4080 |
| `board_plus_comp_w20` | +0.4028 |
| `comp_only` | +0.4002 |
| `board_plus_comp_w10` | +0.3914 |
| `board_proxy` | +0.3676 |
| `fv_only` | +0.3671 |
| `random_order` | +0.0197 |
