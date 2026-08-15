# NF-W6 — efficiency + yards + touchdowns as distributional targets: THE ORACLE GATE

**Generated:** 2026-08-14T20:52:23+00:00 · **folds:** 8 half-season blocks (2022H1…2025H2, the NF-W1 axis verbatim) · **rows:** 84553 player-weeks · **cells:** 12

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** (research-only, no changelog). ⭐ This is the DECISION GATE, not a bake-off: after three component nulls (NF-W3/W4/W5) nothing is built unless a per-cell realized-efficiency ceiling is demonstrably large. Selection metric `crps_q199` (the NF-MARGIN1 dense grid); TD cells are zero-heavy ⇒ CRPS, never MAE (NF-D11/D14), with the all-zero degenerate SCORED every cell. Every direction word is three-way and derived at report time, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a `assert_point_in_time`):** 175 weeks / 84553 records checked; 0 rows dropped.

## Verdict: **CEILING-GATE[BUILD] yes=7 marginal=1 no=4 of 12 cells**

7 cell(s) clear the YES band with stat_ok — the §0.5 bake-off is licensed for: ['QB|passing_tds', 'QB|passing_yards', 'QB|rushing_yards', 'RB|receiving_yards', 'RB|rushing_yards', 'TE|receiving_yards', 'WR|receiving_yards']

## Per-cell ceilings (vs the BINDING incumbent; max over per-form block-peeking oracles)

| cell | binding incumbent | inc CRPS | best form | ceiling Δ | ceiling % | CI95 | wins | p | BH | decision |
|---|---|---|---|---|---|---|---|---|---|---|
| QB|passing_tds | inc_head_bank | 0.382 | cand_lgbm_quantile | 0.06528 | 17.088 | [0.06248, 0.06807] | 8/8 | 0.0 | True | **YES** |
| QB|passing_yards | inc_head_bank | 36.96636 | cand_lgbm_quantile | 2.94074 | 7.955 | [1.63014, 4.25134] | 8/8 | 0.0006 | True | **YES** |
| QB|rushing_tds | inc_climatology | 0.0746 | inc_climatology | 0.00012 | 0.156 | [4e-05, 0.00019] | 8/8 | 0.0044 | True | **NO** |
| QB|rushing_yards | inc_head_bank | 5.67586 | cand_lgbm_quantile | 0.67978 | 11.977 | [0.55923, 0.80033] | 8/8 | 0.0 | True | **YES** |
| RB|receiving_tds | inc_climatology | 0.04281 | inc_climatology | 3e-05 | 0.073 | [-0.0, 6e-05] | 6/8 | 0.0282 | True | **NO** |
| RB|receiving_yards | inc_head_bank | 6.14589 | cand_lgbm_quantile | 0.53271 | 8.668 | [0.44155, 0.62386] | 8/8 | 0.0 | True | **YES** |
| RB|rushing_tds | inc_climatology | 0.14964 | cand_lgbm_quantile | 0.00611 | 4.084 | [0.00246, 0.00976] | 8/8 | 0.0027 | True | **MARGINAL** |
| RB|rushing_yards | inc_head_bank | 12.46804 | cand_lgbm_quantile | 1.07109 | 8.591 | [0.82575, 1.31642] | 8/8 | 0.0 | True | **YES** |
| TE|receiving_tds | inc_climatology | 0.09416 | inc_climatology | 0.00029 | 0.31 | [0.00012, 0.00046] | 8/8 | 0.0025 | True | **NO** |
| TE|receiving_yards | inc_head_bank | 8.69139 | cand_lgbm_quantile | 0.85828 | 9.875 | [0.75642, 0.96015] | 8/8 | 0.0 | True | **YES** |
| WR|receiving_tds | inc_climatology | 0.13454 | cand_lgbm_quantile | 0.00051 | 0.38 | [-0.0007, 0.00173] | 5/8 | 0.1765 | False | **NO** |
| WR|receiving_yards | inc_head_bank | 13.73854 | cand_lgbm_quantile | 0.92137 | 6.706 | [0.77868, 1.06407] | 8/8 | 0.0 | True | **YES** |

## Per-form detail (oracle vs matched-n — NF1.9 (f): a peek is informative only if it beats its own form at matched n)

### QB|passing_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 0.43677 | 0.43771 | True | -0.05477 | [-0.06627, -0.04327] | 0/8 |
| inc_head_bank | 0.39207 | 0.41153 | True | -0.01007 | [-0.01681, -0.00332] | 0/8 |
| cand_lgbm_quantile | 0.31673 | 0.32273 | True | 0.06528 | [0.06248, 0.06807] | 8/8 |

- verdict: `oracle__cand_lgbm_quantile` BEATS `inc_head_bank` by +0.0653 CRPS (CI95 [+0.0625, +0.0681] excludes zero)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.8044 · pred P(0) 0.3081 vs realized 0.6852
- era (report-only): capture Δ 0.06027 vs legacy Δ 0.06694
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### QB|passing_yards

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 61.42626 | 61.51719 | True | -24.4599 | [-26.38198, -22.53782] | 0/8 |
| inc_head_bank | 40.23588 | 43.71938 | True | -3.26952 | [-4.71607, -1.82298] | 0/8 |
| cand_lgbm_quantile | 34.02562 | 34.84965 | True | 2.94074 | [1.63014, 4.25134] | 8/8 |

- verdict: `oracle__cand_lgbm_quantile` BEATS `inc_head_bank` by +2.9407 CRPS (CI95 [+1.6301, +4.2513] excludes zero)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.8005 · pred P(0) 0.2519 vs realized 0.5497
- era (report-only): capture Δ 3.94835 vs legacy Δ 2.60487
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### QB|rushing_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 0.07448 | 0.07462 | True | 0.00012 | [4e-05, 0.00019] | 8/8 |
| inc_head_bank | 0.11392 | 0.12085 | True | -0.03932 | [-0.04283, -0.0358] | 0/8 |
| cand_lgbm_quantile | 0.07467 | 0.07475 | True | -7e-05 | [-0.00243, 0.00228] | 5/8 |

- verdict: `oracle__inc_climatology` BEATS `inc_climatology` by +0.0001 CRPS (CI95 [+0.0000, +0.0002] excludes zero)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.9329 · pred P(0) 0.9435 vs realized 0.9329
- era (report-only): capture Δ 6e-05 vs legacy Δ 0.00014
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### QB|rushing_yards

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 6.39378 | 6.40997 | True | -0.71792 | [-1.06802, -0.36782] | 0/8 |
| inc_head_bank | 6.40148 | 6.69933 | True | -0.72562 | [-0.82052, -0.63072] | 0/8 |
| cand_lgbm_quantile | 4.99608 | 4.94929 | False | 0.67978 | [0.55923, 0.80033] | 8/8 |

- verdict: `oracle__cand_lgbm_quantile` BEATS `inc_head_bank` by +0.6798 CRPS (CI95 [+0.5592, +0.8003] excludes zero)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.7916 · pred P(0) 0.3154 vs realized 0.5892
- era (report-only): capture Δ 0.76608 vs legacy Δ 0.65101
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### RB|receiving_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 0.04277 | 0.04282 | True | 3e-05 | [-0.0, 6e-05] | 6/8 |
| inc_head_bank | 0.07658 | 0.07901 | True | -0.03377 | [-0.03618, -0.03137] | 0/8 |
| cand_lgbm_quantile | 0.04653 | 0.04646 | False | -0.00372 | [-0.00454, -0.00291] | 0/8 |

- verdict: `oracle__inc_climatology` TIES `inc_climatology` by +0.0000 CRPS (CI95 [-0.0000, +0.0001] spans zero)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.9584 · pred P(0) 0.9585 vs realized 0.9584
- era (report-only): capture Δ 2e-05 vs legacy Δ 3e-05
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### RB|receiving_yards

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 6.50715 | 6.51433 | True | -0.36126 | [-0.50289, -0.21963] | 0/8 |
| inc_head_bank | 6.74638 | 7.17094 | True | -0.60048 | [-0.66043, -0.54054] | 0/8 |
| cand_lgbm_quantile | 5.61319 | 5.57418 | False | 0.53271 | [0.44155, 0.62386] | 8/8 |

- verdict: `oracle__cand_lgbm_quantile` BEATS `inc_head_bank` by +0.5327 CRPS (CI95 [+0.4415, +0.6239] excludes zero)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.8122 · pred P(0) 0.2971 vs realized 0.5457
- era (report-only): capture Δ 0.63567 vs legacy Δ 0.49838
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### RB|rushing_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 0.14949 | 0.14969 | True | 0.00015 | [-0.0, 0.00031] | 7/8 |
| inc_head_bank | 0.1981 | 0.20443 | True | -0.04847 | [-0.05276, -0.04418] | 0/8 |
| cand_lgbm_quantile | 0.14353 | 0.14299 | False | 0.00611 | [0.00246, 0.00976] | 8/8 |

- verdict: `oracle__cand_lgbm_quantile` BEATS `inc_climatology` by +0.0061 CRPS (CI95 [+0.0025, +0.0098] excludes zero)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.9738 · pred P(0) 0.8693 vs realized 0.8606
- era (report-only): capture Δ 0.00313 vs legacy Δ 0.0071
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### RB|rushing_yards

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 16.51909 | 16.54454 | True | -4.05104 | [-4.42845, -3.67364] | 0/8 |
| inc_head_bank | 13.13062 | 14.01982 | True | -0.66258 | [-1.04155, -0.28361] | 1/8 |
| cand_lgbm_quantile | 11.39696 | 11.50317 | True | 1.07109 | [0.82575, 1.31642] | 8/8 |

- verdict: `oracle__cand_lgbm_quantile` BEATS `inc_head_bank` by +1.0711 CRPS (CI95 [+0.8257, +1.3164] excludes zero)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.8057 · pred P(0) 0.2456 vs realized 0.3999
- era (report-only): capture Δ 0.85102 vs legacy Δ 1.14444
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### TE|receiving_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 0.09387 | 0.09426 | True | 0.00029 | [0.00012, 0.00046] | 8/8 |
| inc_head_bank | 0.14105 | 0.14829 | True | -0.04689 | [-0.04964, -0.04414] | 0/8 |
| cand_lgbm_quantile | 0.09571 | 0.09637 | True | -0.00155 | [-0.00347, 0.00037] | 2/8 |

- verdict: `oracle__inc_climatology` BEATS `inc_climatology` by +0.0003 CRPS (CI95 [+0.0001, +0.0005] excludes zero)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.9464 · pred P(0) 0.902 vs realized 0.9098
- era (report-only): capture Δ 0.0002 vs legacy Δ 0.00032
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### TE|receiving_yards

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 10.53348 | 10.54661 | True | -1.84208 | [-2.12257, -1.5616] | 0/8 |
| inc_head_bank | 9.36664 | 10.11647 | True | -0.67525 | [-0.75279, -0.5977] | 0/8 |
| cand_lgbm_quantile | 7.83311 | 7.91071 | True | 0.85828 | [0.75642, 0.96015] | 8/8 |

- verdict: `oracle__cand_lgbm_quantile` BEATS `inc_head_bank` by +0.8583 CRPS (CI95 [+0.7564, +0.9601] excludes zero)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.8026 · pred P(0) 0.2656 vs realized 0.4976
- era (report-only): capture Δ 0.88183 vs legacy Δ 0.85043
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### WR|receiving_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 0.13439 | 0.13451 | True | 0.00016 | [2e-05, 0.00029] | 7/8 |
| inc_head_bank | 0.18803 | 0.19865 | True | -0.05349 | [-0.05547, -0.05151] | 0/8 |
| cand_lgbm_quantile | 0.13403 | 0.13497 | True | 0.00051 | [-0.0007, 0.00173] | 5/8 |

- verdict: `oracle__cand_lgbm_quantile` TIES `inc_climatology` by +0.0005 CRPS (CI95 [-0.0007, +0.0017] spans zero)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.9828 · pred P(0) 0.8624 vs realized 0.8669
- era (report-only): capture Δ -0.0003 vs legacy Δ 0.00078
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### WR|receiving_yards

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 16.97976 | 17.00569 | True | -3.24122 | [-3.79109, -2.69135] | 0/8 |
| inc_head_bank | 14.49971 | 15.41208 | True | -0.76117 | [-1.03981, -0.48253] | 0/8 |
| cand_lgbm_quantile | 12.81717 | 12.94037 | True | 0.92137 | [0.77868, 1.06407] | 8/8 |

- verdict: `oracle__cand_lgbm_quantile` BEATS `inc_head_bank` by +0.9214 CRPS (CI95 [+0.7787, +1.0641] excludes zero)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.8056 · pred P(0) 0.2325 vs realized 0.4116
- era (report-only): capture Δ 0.88084 vs legacy Δ 0.93488
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

## Pre-registration

- decision bands: NO < 2.0% ≤ MARGINAL < 5.0% ≤ YES on ceiling_pct; `stat_ok` = CI95 excludes zero ∧ calibrated fold clause ∧ BH binding (own family AND pooled). Not stat_ok → NO.
- incumbent forms: ['inc_head_bank', 'inc_climatology'] (the BINDING one sets the bar); oracle forms: ['inc_climatology', 'inc_head_bank', 'cand_lgbm_quantile'] (block-peeking, conditional forms cross-fit K=3); anchors: ['nihilist_zero', 'zero_width', 'max_width', 'oracle__inc_climatology', 'oracle__inc_head_bank', 'oracle__cand_lgbm_quantile', 'matched_n__inc_climatology', 'matched_n__inc_head_bank', 'matched_n__cand_lgbm_quantile'].
- FDR families (own + pooled, stricter binds — MH2 (a)): yards=6 cells, tds=6 cells.
- PBO: UNDEFINED at this stage (pre-registered anchor contrast, not a searched field — the NF-W5 ceiling rule). DSR: does not arise (no arm is selected). `classify_null` is NOT invoked (the n_arms=1 fold-shortage mis-render — NF-W3 (c)).
- estimator bias: max over the per-form block-peeking oracles vs the BINDING (better) incumbent — the oracle-side max is upward-biased by selection over the declared forms and the peek favors YES, so a NO is conservative (pre-registered; the NF-W5 rule).

_Runtime: 4130.5s · seed 20260814 · matrix cache key 57c4cf96bb3c3570_