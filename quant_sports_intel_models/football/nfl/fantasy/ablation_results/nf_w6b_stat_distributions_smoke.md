# NF-W6b — the per-stat distributional successor (§0.5 bake-off; the CEILING-GATE[BUILD] license)

**Generated:** 2026-08-14T22:54:15+00:00 · **folds:** 2 half-season blocks (2025H1…2025H2, the NF-W1 axis verbatim) · **rows:** 84553 player-weeks · **cells:** 8

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** (research-only, no changelog). FRESH registration (MH2.2) licensed by NF-W6's CEILING-GATE[BUILD]. DoD = per-stat marginal CRPS (`crps_q199`); the assembled-PPR effect is REPORT-ONLY (PM ruling). Coverage is a FLOOR, one-sided by pre-registration (NF1.9 (e) — the zero atom makes an upper coverage gate structurally inverted); the two-sidedness lives in the sharpness degenerates. Every direction word is three-way and derived at report time, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a `assert_point_in_time`):** 175 weeks / 84553 records checked; 0 rows dropped.

## Verdict: **PERSTAT-BAKEOFF ship=0 null=8 of 8 cells**

per-cell verdicts (no story-level aggregation gate): SHIP —; recorded nulls ['QB|passing_tds', 'QB|passing_yards', 'QB|rushing_yards', 'RB|receiving_yards', 'RB|rushing_tds', 'RB|rushing_yards', 'TE|receiving_yards', 'WR|receiving_yards']

## Per-cell contests (winner vs the BINDING champion-faithful incumbent)

| cell | winner | foil | foil CRPS | Δ | Δ% | CI95 | wins | p | PBO | DSR | BH | cov80 (floor 0.80) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| QB|passing_tds | knn_quantile | inc_head_bank | 0.38807 | 0.08107 | 20.89 | n/a | 2/2 | None | None | None | False | 0.9461 | **POWER_LIMITED** |
| QB|passing_yards | lgbm_quantile_tail | inc_head_bank | 35.86554 | 5.94052 | 16.563 | n/a | 2/2 | None | None | None | False | 0.7988 | **POWER_LIMITED** |
| QB|rushing_yards | lgbm_hurdle_tail | inc_head_bank | 5.61108 | 1.11144 | 19.808 | n/a | 2/2 | None | None | None | False | 0.8324 | **POWER_LIMITED** |
| RB|receiving_yards | lgbm_hurdle_tail | inc_head_bank | 5.80145 | 0.89946 | 15.504 | n/a | 2/2 | None | None | None | False | 0.8937 | **POWER_LIMITED** |
| RB|rushing_tds | knn_quantile | inc_climatology | 0.15764 | 0.01809 | 11.474 | n/a | 2/2 | None | None | None | False | 0.9473 | **POWER_LIMITED** |
| RB|rushing_yards | lgbm_hurdle_tail | inc_head_bank | 12.15342 | 1.66738 | 13.719 | n/a | 2/2 | None | None | None | False | 0.8475 | **POWER_LIMITED** |
| TE|receiving_yards | lgbm_hurdle_tail | inc_head_bank | 8.69088 | 1.27319 | 14.65 | n/a | 2/2 | None | None | None | False | 0.8918 | **POWER_LIMITED** |
| WR|receiving_yards | lgbm_quantile_tail | inc_head_bank | 13.31589 | 1.59166 | 11.953 | n/a | 2/2 | None | None | None | False | 0.8338 | **POWER_LIMITED** |

## Per-cell detail

### QB|passing_tds

| label              |   mean_crps |
|:-------------------|------------:|
| knn_quantile       |     0.30700 |
| lgbm_hurdle_tail   |     0.31347 |
| lgbm_quantile_tail |     0.31842 |
| inc_head_bank      |     0.38807 |
| enet_residual      |     0.40034 |
| oracle_marginal    |     0.45391 |
| inc_climatology    |     0.45464 |
| matched_marginal   |     0.45567 |
| zero_width         |     0.45871 |
| max_width          |     0.46108 |
| permuted_quantile  |     0.48368 |
| nihilist_zero      |     0.58854 |

- verdict: `knn_quantile` TIES `inc_head_bank` by +0.0811 CRPS (interval unevaluable)
- gates: {"beats_foil": true, "fold_consistency": false, "pbo_ok": false, "dsr_ok": false, "fdr_ok": false, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.9461, "binding_foil_coverage_80": 0.7959, "structural_expectation": 0.9685, "n_rows": 1372, "binomial_se": 0.0108, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.6851, "winner_pred_p0": 0.6798, "binding_foil_pred_p0": 0.3184, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 0.08107 vs legacy Δ None
- null state: {"state": "POWER_LIMITED", "reason": "the point estimate is positive (0.08107 CRPS) and the interval is unevaluable (CI95 [None, None]); fold wins 2/2 vs required None; failing statistical gates: ['fold_consistency', 'pbo_ok', 'dsr_ok', 'fdr_ok'] \u2014 the effect is smaller than this design resolves.", "retest_trigger": "\u22652 half-season folds (\u22480 more than the current 2) at the observed per-fold Sharpe 35.22 \u2014 a LOWER bound (the deflation term is ignored); calendar-bound.", "failing_checks": ["fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok"]}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": ["fold_consistency", "pbo_ok", "fdr_ok"], "ships_without_waived_checks": false}

### QB|passing_yards

| label              |   mean_crps |
|:-------------------|------------:|
| lgbm_quantile_tail |    29.92501 |
| lgbm_hurdle_tail   |    30.35285 |
| knn_quantile       |    31.37033 |
| inc_head_bank      |    35.86554 |
| enet_residual      |    39.02711 |
| zero_width         |    43.58644 |
| max_width          |    44.41928 |
| oracle_marginal    |    59.81115 |
| matched_marginal   |    59.95849 |
| inc_climatology    |    60.04877 |
| permuted_quantile  |    61.05359 |
| nihilist_zero      |    89.20971 |

- verdict: `lgbm_quantile_tail` TIES `inc_head_bank` by +5.9405 CRPS (interval unevaluable)
- gates: {"beats_foil": true, "fold_consistency": false, "pbo_ok": false, "dsr_ok": false, "fdr_ok": false, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.7988, "binding_foil_coverage_80": 0.8017, "structural_expectation": 0.9553, "n_rows": 1372, "binomial_se": 0.0108, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.5532, "winner_pred_p0": 0.3093, "binding_foil_pred_p0": 0.2614, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 5.94052 vs legacy Δ None
- null state: {"state": "POWER_LIMITED", "reason": "the point estimate is positive (5.94052 CRPS) and the interval is unevaluable (CI95 [None, None]); fold wins 2/2 vs required None; failing statistical gates: ['fold_consistency', 'pbo_ok', 'dsr_ok', 'fdr_ok'] \u2014 the effect is smaller than this design resolves.", "retest_trigger": "\u22652 half-season folds (\u22480 more than the current 2) at the observed per-fold Sharpe 12.381 \u2014 a LOWER bound (the deflation term is ignored); calendar-bound.", "failing_checks": ["fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok"]}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": ["fold_consistency", "pbo_ok", "fdr_ok"], "ships_without_waived_checks": false}

### QB|rushing_yards

| label              |   mean_crps |
|:-------------------|------------:|
| lgbm_hurdle_tail   |     4.49964 |
| lgbm_quantile_tail |     4.52121 |
| knn_quantile       |     4.64786 |
| inc_head_bank      |     5.61108 |
| enet_residual      |     5.68583 |
| permuted_quantile  |     6.03063 |
| oracle_marginal    |     6.03393 |
| matched_marginal   |     6.04303 |
| inc_climatology    |     6.06008 |
| max_width          |     6.55711 |
| zero_width         |     6.65655 |
| nihilist_zero      |     7.40836 |

- verdict: `lgbm_hurdle_tail` TIES `inc_head_bank` by +1.1114 CRPS (interval unevaluable)
- gates: {"beats_foil": true, "fold_consistency": false, "pbo_ok": false, "dsr_ok": false, "fdr_ok": false, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.8324, "binding_foil_coverage_80": 0.8054, "structural_expectation": 0.9582, "n_rows": 1372, "binomial_se": 0.0108, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.5824, "winner_pred_p0": 0.622, "binding_foil_pred_p0": 0.3198, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 1.11144 vs legacy Δ None
- null state: {"state": "POWER_LIMITED", "reason": "the point estimate is positive (1.11144 CRPS) and the interval is unevaluable (CI95 [None, None]); fold wins 2/2 vs required None; failing statistical gates: ['fold_consistency', 'pbo_ok', 'dsr_ok', 'fdr_ok'] \u2014 the effect is smaller than this design resolves.", "retest_trigger": "\u22652 half-season folds (\u22480 more than the current 2) at the observed per-fold Sharpe 33.724 \u2014 a LOWER bound (the deflation term is ignored); calendar-bound.", "failing_checks": ["fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok"]}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": ["fold_consistency", "pbo_ok", "fdr_ok"], "ships_without_waived_checks": false}

### RB|receiving_yards

| label              |   mean_crps |
|:-------------------|------------:|
| lgbm_hurdle_tail   |     4.90199 |
| lgbm_quantile_tail |     4.91544 |
| knn_quantile       |     5.05099 |
| inc_head_bank      |     5.80145 |
| enet_residual      |     6.19979 |
| oracle_marginal    |     6.37273 |
| matched_marginal   |     6.38223 |
| inc_climatology    |     6.39264 |
| permuted_quantile  |     6.50142 |
| zero_width         |     7.13776 |
| max_width          |     7.42832 |
| nihilist_zero      |     8.17212 |

- verdict: `lgbm_hurdle_tail` TIES `inc_head_bank` by +0.8995 CRPS (interval unevaluable)
- gates: {"beats_foil": true, "fold_consistency": false, "pbo_ok": false, "dsr_ok": false, "fdr_ok": false, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.8937, "binding_foil_coverage_80": 0.8153, "structural_expectation": 0.9557, "n_rows": 2144, "binomial_se": 0.0086, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.5569, "winner_pred_p0": 0.5599, "binding_foil_pred_p0": 0.2989, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 0.89946 vs legacy Δ None
- null state: {"state": "POWER_LIMITED", "reason": "the point estimate is positive (0.89946 CRPS) and the interval is unevaluable (CI95 [None, None]); fold wins 2/2 vs required None; failing statistical gates: ['fold_consistency', 'pbo_ok', 'dsr_ok', 'fdr_ok'] \u2014 the effect is smaller than this design resolves.", "retest_trigger": "\u22652 half-season folds (\u22480 more than the current 2) at the observed per-fold Sharpe 85.647 \u2014 a LOWER bound (the deflation term is ignored); calendar-bound.", "failing_checks": ["fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok"]}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": ["fold_consistency", "pbo_ok", "fdr_ok"], "ships_without_waived_checks": false}

### RB|rushing_tds

| label              |   mean_crps |
|:-------------------|------------:|
| knn_quantile       |     0.13955 |
| lgbm_hurdle_tail   |     0.14222 |
| lgbm_quantile_tail |     0.14639 |
| oracle_marginal    |     0.15746 |
| inc_climatology    |     0.15764 |
| matched_marginal   |     0.15786 |
| permuted_quantile  |     0.16760 |
| nihilist_zero      |     0.17809 |
| enet_residual      |     0.19547 |
| inc_head_bank      |     0.20183 |
| max_width          |     0.24026 |
| zero_width         |     0.24149 |

- verdict: `knn_quantile` TIES `inc_climatology` by +0.0181 CRPS (interval unevaluable)
- gates: {"beats_foil": true, "fold_consistency": false, "pbo_ok": false, "dsr_ok": false, "fdr_ok": false, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.9473, "binding_foil_coverage_80": 0.9688, "structural_expectation": 0.9857, "n_rows": 2144, "binomial_se": 0.0086, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.8573, "winner_pred_p0": 0.8693, "binding_foil_pred_p0": 0.8693, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 0.01809 vs legacy Δ None
- null state: {"state": "POWER_LIMITED", "reason": "the point estimate is positive (0.01809 CRPS) and the interval is unevaluable (CI95 [None, None]); fold wins 2/2 vs required None; failing statistical gates: ['fold_consistency', 'pbo_ok', 'dsr_ok', 'fdr_ok'] \u2014 the effect is smaller than this design resolves.", "retest_trigger": "\u22652 half-season folds (\u22480 more than the current 2) at the observed per-fold Sharpe 8.543 \u2014 a LOWER bound (the deflation term is ignored); calendar-bound.", "failing_checks": ["fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok"]}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": ["fold_consistency", "pbo_ok", "fdr_ok"], "ships_without_waived_checks": false}

### RB|rushing_yards

| label              |   mean_crps |
|:-------------------|------------:|
| lgbm_hurdle_tail   |    10.48604 |
| lgbm_quantile_tail |    10.61810 |
| knn_quantile       |    11.00162 |
| inc_head_bank      |    12.15342 |
| enet_residual      |    12.42464 |
| zero_width         |    14.95278 |
| max_width          |    15.32526 |
| permuted_quantile  |    16.64853 |
| oracle_marginal    |    16.73197 |
| matched_marginal   |    16.76330 |
| inc_climatology    |    16.77475 |
| nihilist_zero      |    24.12683 |

- verdict: `lgbm_hurdle_tail` TIES `inc_head_bank` by +1.6674 CRPS (interval unevaluable)
- gates: {"beats_foil": true, "fold_consistency": false, "pbo_ok": false, "dsr_ok": false, "fdr_ok": false, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.8475, "binding_foil_coverage_80": 0.8064, "structural_expectation": 0.9406, "n_rows": 2144, "binomial_se": 0.0086, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.4058, "winner_pred_p0": 0.4314, "binding_foil_pred_p0": 0.2512, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 1.66738 vs legacy Δ None
- null state: {"state": "POWER_LIMITED", "reason": "the point estimate is positive (1.66738 CRPS) and the interval is unevaluable (CI95 [None, None]); fold wins 2/2 vs required None; failing statistical gates: ['fold_consistency', 'pbo_ok', 'dsr_ok', 'fdr_ok'] \u2014 the effect is smaller than this design resolves.", "retest_trigger": "\u22652 half-season folds (\u22480 more than the current 2) at the observed per-fold Sharpe 16.185 \u2014 a LOWER bound (the deflation term is ignored); calendar-bound.", "failing_checks": ["fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok"]}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": ["fold_consistency", "pbo_ok", "fdr_ok"], "ships_without_waived_checks": false}

### TE|receiving_yards

| label              |   mean_crps |
|:-------------------|------------:|
| lgbm_hurdle_tail   |     7.41769 |
| lgbm_quantile_tail |     7.44557 |
| knn_quantile       |     7.74936 |
| inc_head_bank      |     8.69088 |
| enet_residual      |     8.93882 |
| max_width          |    10.68802 |
| oracle_marginal    |    10.77190 |
| inc_climatology    |    10.77708 |
| matched_marginal   |    10.77922 |
| zero_width         |    10.80858 |
| permuted_quantile  |    10.82816 |
| nihilist_zero      |    14.96055 |

- verdict: `lgbm_hurdle_tail` TIES `inc_head_bank` by +1.2732 CRPS (interval unevaluable)
- gates: {"beats_foil": true, "fold_consistency": false, "pbo_ok": false, "dsr_ok": false, "fdr_ok": false, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.8918, "binding_foil_coverage_80": 0.7944, "structural_expectation": 0.9485, "n_rows": 1941, "binomial_se": 0.0091, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.4848, "winner_pred_p0": 0.4984, "binding_foil_pred_p0": 0.2491, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 1.27319 vs legacy Δ None
- null state: {"state": "POWER_LIMITED", "reason": "the point estimate is positive (1.27319 CRPS) and the interval is unevaluable (CI95 [None, None]); fold wins 2/2 vs required None; failing statistical gates: ['fold_consistency', 'pbo_ok', 'dsr_ok', 'fdr_ok'] \u2014 the effect is smaller than this design resolves.", "retest_trigger": "\u22652 half-season folds (\u22480 more than the current 2) at the observed per-fold Sharpe 16.656 \u2014 a LOWER bound (the deflation term is ignored); calendar-bound.", "failing_checks": ["fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok"]}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": ["fold_consistency", "pbo_ok", "fdr_ok"], "ships_without_waived_checks": false}

### WR|receiving_yards

| label              |   mean_crps |
|:-------------------|------------:|
| lgbm_quantile_tail |    11.72423 |
| lgbm_hurdle_tail   |    11.73721 |
| knn_quantile       |    11.88657 |
| inc_head_bank      |    13.31589 |
| enet_residual      |    13.43193 |
| oracle_marginal    |    16.01009 |
| matched_marginal   |    16.05170 |
| permuted_quantile  |    16.06427 |
| inc_climatology    |    16.09573 |
| zero_width         |    17.00024 |
| max_width          |    17.04032 |
| nihilist_zero      |    23.50866 |

- verdict: `lgbm_quantile_tail` TIES `inc_head_bank` by +1.5917 CRPS (interval unevaluable)
- gates: {"beats_foil": true, "fold_consistency": false, "pbo_ok": false, "dsr_ok": false, "fdr_ok": false, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.8338, "binding_foil_coverage_80": 0.8025, "structural_expectation": 0.9425, "n_rows": 3231, "binomial_se": 0.007, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.4249, "winner_pred_p0": 0.1972, "binding_foil_pred_p0": 0.2359, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 1.59166 vs legacy Δ None
- null state: {"state": "POWER_LIMITED", "reason": "the point estimate is positive (1.59166 CRPS) and the interval is unevaluable (CI95 [None, None]); fold wins 2/2 vs required None; failing statistical gates: ['fold_consistency', 'pbo_ok', 'dsr_ok', 'fdr_ok'] \u2014 the effect is smaller than this design resolves.", "retest_trigger": "\u22652 half-season folds (\u22480 more than the current 2) at the observed per-fold Sharpe 6.548 \u2014 a LOWER bound (the deflation term is ignored); calendar-bound.", "failing_checks": ["fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok"]}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": ["fold_consistency", "pbo_ok", "fdr_ok"], "ships_without_waived_checks": false}

## Assembled-PPR effect — REPORT-ONLY (PM ruling; never a gate)

```json
{
  "per_cell_points_units": {
    "QB|passing_tds": 0.3243,
    "QB|passing_yards": 0.2376,
    "QB|rushing_yards": 0.1111,
    "RB|receiving_yards": 0.0899,
    "RB|rushing_tds": 0.1085,
    "RB|rushing_yards": 0.1667,
    "TE|receiving_yards": 0.1273,
    "WR|receiving_yards": 0.1592
  },
  "per_position_sum_points_units": {
    "QB": 0.673,
    "RB": 0.3651,
    "TE": 0.1273,
    "WR": 0.1592
  },
  "note": "REPORT-ONLY (PM ruling): winner-vs-binding-incumbent CRPS lift \u00d7 PPR weight, summed per position \u2014 a sum of MARGINAL contributions in points units, NOT an assembled joint-points claim; a per-stat win need not move assembled points."
}
```

## Pre-registration

- cells: ['QB|passing_yards', 'QB|passing_tds', 'QB|rushing_yards', 'RB|rushing_yards', 'RB|rushing_tds', 'RB|receiving_yards', 'WR|receiving_yards', 'TE|receiving_yards'] (⛔ closed: ['QB|rushing_tds', 'RB|receiving_tds', 'WR|receiving_tds', 'TE|receiving_tds']); arms: ['lgbm_quantile_tail', 'lgbm_hurdle_tail', 'enet_residual', 'knn_quantile']; foils: ['inc_head_bank', 'inc_climatology'] (binding sets the bar); anchors: ['nihilist_zero', 'zero_width', 'max_width', 'permuted_quantile', 'oracle_marginal', 'matched_marginal'].
- gates: paired lift vs binding foil ∧ `fold_consistency_clause(2)` ∧ PBO<0.2 over the eligible field ∧ DSR≥0.95 ∧ BH q=0.1 (two families, own AND pooled) ∧ coverage floor (one-sided, prereg §2) ∧ degenerates lose ∧ permutation behaves. Fails closed.
- FDR families: yards=6 cells, tds=2 cells.
- null classification is HAND-derived (GENUINE_ABSENCE / POWER_LIMITED / CONSTRAINT_REFUSED); `classify_null` is NOT invoked (the n_arms mis-render — NF-W3 (c)).

_Runtime: 2047.3s · seed 20260815 · matrix cache key 57c4cf96bb3c3570_