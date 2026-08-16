# NF-W6d Phase A — the ceiling gate over every remaining optimizer-input stat cell

**Generated:** 2026-08-15T21:20:27+00:00 · **folds:** 8 half-season blocks (2022H1…2025H2, the NF-W1 axis verbatim) · **rows:** 84553 player-weeks · **cells:** 22

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** (research-only, no changelog). THE DECISION GATE, not a bake-off: per-form block-peeking oracles floored at matched-n controls sized to the peek's effective n (NF-W6b-C). A cell with no ceiling is a recorded finding — its point mean is already near-optimal — and gets a calibrated Phase-C default. Metric `crps_q199`; the nihilist is SCORED every cell (NF-D11). Every direction word is three-way and derived at report time (NF-W2e).

**PIT gate (NF-W0a `assert_point_in_time`):** 175 weeks / 84553 records checked; 0 rows dropped. Label attach: {'cache': 'hit'}

## Verdict: **CEILING-GATE yes=10 marginal=4 no=8 of 22 cells → 14 licensed for the bake-off; 8 point-only (Phase-C default)**

- LICENSED for the Phase-B bake-off (YES or MARGINAL ∧ stat_ok): ['QB|attempts', 'QB|carries', 'QB|fumbles_lost', 'QB|passing_interceptions', 'QB|rushing_tds', 'RB|carries', 'RB|receptions', 'RB|targets', 'TE|receiving_tds', 'TE|receptions', 'TE|targets', 'WR|receiving_tds', 'WR|receptions', 'WR|targets']
- YES: ['QB|attempts', 'QB|carries', 'QB|passing_interceptions', 'RB|carries', 'RB|receptions', 'RB|targets', 'TE|receptions', 'TE|targets', 'WR|receiving_tds', 'WR|receptions'] · MARGINAL: ['QB|fumbles_lost', 'QB|rushing_tds', 'TE|receiving_tds', 'WR|targets'] · NO (point-only → Phase-C default): ['QB|two_pt', 'RB|fumbles_lost', 'RB|receiving_tds', 'RB|two_pt', 'TE|fumbles_lost', 'TE|two_pt', 'WR|fumbles_lost', 'WR|two_pt']

## Per-cell ceilings (vs the BINDING incumbent; max over per-form block-peeking oracles)

| cell | class | binding incumbent | inc CRPS | best form | ceiling Δ | ceiling % | CI95 | wins | p | BH | peek>matched | inapplicable | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| QB|attempts | count | inc_head_bank | 4.98797 | cand_quantile | 0.45216 | 9.065 | [0.32794, 0.57639] | 8/8 | 0.0 | True | True | — | **YES** → BAKE-OFF |
| QB|carries | count | inc_head_bank | 0.97039 | cand_quantile | 0.06349 | 6.543 | [0.04845, 0.07854] | 8/8 | 0.0 | True | True | — | **YES** → BAKE-OFF |
| RB|carries | count | inc_head_bank | 2.27926 | cand_quantile | 0.13355 | 5.859 | [0.0926, 0.1745] | 8/8 | 0.0001 | True | True | — | **YES** → BAKE-OFF |
| RB|receptions | count | inc_head_bank | 0.67957 | cand_quantile | 0.04994 | 7.349 | [0.04037, 0.05952] | 8/8 | 0.0 | True | True | — | **YES** → BAKE-OFF |
| RB|targets | count | inc_head_bank | 0.81154 | cand_quantile | 0.04581 | 5.645 | [0.03502, 0.05661] | 8/8 | 0.0 | True | True | — | **YES** → BAKE-OFF |
| TE|receptions | count | inc_head_bank | 0.75304 | cand_quantile | 0.05401 | 7.172 | [0.04509, 0.06292] | 8/8 | 0.0 | True | True | — | **YES** → BAKE-OFF |
| TE|targets | count | inc_head_bank | 0.95166 | cand_quantile | 0.06078 | 6.387 | [0.04711, 0.07445] | 8/8 | 0.0 | True | True | — | **YES** → BAKE-OFF |
| WR|receptions | count | inc_head_bank | 0.95146 | cand_quantile | 0.04793 | 5.037 | [0.03483, 0.06103] | 8/8 | 0.0 | True | True | — | **YES** → BAKE-OFF |
| WR|targets | count | inc_head_bank | 1.31395 | cand_quantile | 0.04595 | 3.497 | [0.03101, 0.06089] | 8/8 | 0.0001 | True | True | — | **MARGINAL** → BAKE-OFF |
| QB|fumbles_lost | event | inc_climatology | 0.081 | knn | 0.00246 | 3.035 | [0.00178, 0.00314] | 8/8 | 0.0 | True | False | — | **MARGINAL** → BAKE-OFF |
| QB|passing_interceptions | event | inc_climatology | 0.24589 | knn | 0.02211 | 8.991 | [0.01873, 0.02548] | 8/8 | 0.0 | True | True | — | **YES** → BAKE-OFF |
| QB|rushing_tds | event | inc_climatology | 0.0746 | negbin | 0.00354 | 4.744 | [0.00129, 0.00579] | 8/8 | 0.0037 | True | True | — | **MARGINAL** → BAKE-OFF |
| QB|two_pt | event | inc_climatology | 0.03288 | knn | 0.00055 | 1.665 | [0.00032, 0.00077] | 8/8 | 0.0003 | True | False | hurdle | **NO** → default |
| RB|fumbles_lost | event | inc_climatology | 0.02937 | knn | 0.00051 | 1.729 | [0.00021, 0.0008] | 8/8 | 0.0023 | True | True | — | **NO** → default |
| RB|receiving_tds | event | inc_climatology | 0.04281 | knn | 0.00084 | 1.971 | [0.00048, 0.00121] | 8/8 | 0.0005 | True | False | — | **NO** → default |
| RB|two_pt | event | inc_climatology | 0.00814 | knn | 1e-05 | 0.093 | [-2e-05, 3e-05] | 5/8 | 0.2415 | False | False | hurdle | **NO** → default |
| TE|fumbles_lost | event | inc_climatology | 0.00794 | marginal | 0.0 | 0.022 | [-0.0, 0.0] | 3/8 | 0.0904 | False | True | — | **NO** → default |
| TE|receiving_tds | event | inc_climatology | 0.09416 | knn | 0.00412 | 4.38 | [0.00294, 0.00531] | 8/8 | 0.0 | True | True | — | **MARGINAL** → BAKE-OFF |
| TE|two_pt | event | inc_climatology | 0.00536 | knn | 1e-05 | 0.102 | [-1e-05, 2e-05] | 5/8 | 0.2214 | False | False | hurdle | **NO** → default |
| WR|fumbles_lost | event | inc_climatology | 0.01215 | knn | 5e-05 | 0.432 | [2e-05, 8e-05] | 7/8 | 0.0033 | True | True | — | **NO** → default |
| WR|receiving_tds | event | inc_climatology | 0.13454 | knn | 0.01047 | 7.784 | [0.00865, 0.0123] | 8/8 | 0.0 | True | True | — | **YES** → BAKE-OFF |
| WR|two_pt | event | inc_climatology | 0.00776 | knn | 1e-05 | 0.073 | [-0.0, 1e-05] | 5/8 | 0.0717 | True | False | hurdle | **NO** → default |

## Per-form detail (oracle vs matched-n — NF1.9 (f); conditional controls at (K−1)/K)

### QB|attempts

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 8.49107 | 8.50407 | True | -3.50309 | [-3.80793, -3.19826] | 0/8 |
| head_bank | 5.46632 | 5.8525 | True | -0.47835 | [-0.65028, -0.30641] | 0/8 |
| cand_quantile | 4.53581 | 4.7381 | True | 0.45216 | [0.32794, 0.57639] | 8/8 |
| knn | 5.9389 | 6.05993 | True | -0.95093 | [-1.12867, -0.77319] | 0/8 |
| hurdle | 4.76274 | 4.79609 | True | 0.22523 | [0.04955, 0.40092] | 7/8 |
| negbin | 8.52675 | 5.92426 | False | -3.53878 | [-4.40405, -2.6735] | 0/8 |

- verdict: `oracle__cand_quantile` BEATS `inc_head_bank` by +0.4522 CRPS (CI95 [+0.3279, +0.5764] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.8022, "pred_p0_mean": 0.2424, "real_p0": 0.54}
- era (report-only): capture Δ 0.48212 vs legacy Δ 0.44218
- decision: ceiling 9.06% ≥ 5.0% — a §0.5 bake-off on this cell's family is licensed

### QB|carries

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 1.25523 | 1.2586 | True | -0.28484 | [-0.3531, -0.21658] | 0/8 |
| head_bank | 1.11655 | 1.20014 | True | -0.14616 | [-0.17689, -0.11542] | 0/8 |
| cand_quantile | 0.9069 | 0.91737 | True | 0.06349 | [0.04845, 0.07854] | 8/8 |
| knn | 1.05802 | 1.0684 | True | -0.08763 | [-0.14177, -0.03349] | 0/8 |
| hurdle | 0.94132 | 0.93982 | False | 0.02907 | [0.00288, 0.05526] | 7/8 |
| negbin | 0.97555 | 1.03731 | True | -0.00516 | [-0.02522, 0.01489] | 4/8 |

- verdict: `oracle__cand_quantile` BEATS `inc_head_bank` by +0.0635 CRPS (CI95 [+0.0485, +0.0785] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.7942, "pred_p0_mean": 0.2592, "real_p0": 0.5741}
- era (report-only): capture Δ 0.05226 vs legacy Δ 0.06724
- decision: ceiling 6.54% ≥ 5.0% — a §0.5 bake-off on this cell's family is licensed

### QB|fumbles_lost

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.08094 | 0.08113 | True | 6e-05 | [-2e-05, 0.00014] | 6/8 |
| knn | 0.07854 | 0.0785 | False | 0.00246 | [0.00178, 0.00314] | 8/8 |
| hurdle | 0.08851 | 0.08755 | False | -0.00752 | [-0.00952, -0.00551] | 0/8 |
| negbin | 0.082 | 0.08215 | True | -0.00101 | [-0.00268, 0.00066] | 1/8 |

- verdict: `oracle__knn` BEATS `inc_climatology` by +0.0025 CRPS (CI95 [+0.0018, +0.0031] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9207, "pred_p0_mean": 0.9234, "real_p0": 0.9207}
- era (report-only): capture Δ 0.00209 vs legacy Δ 0.00258
- decision: ceiling 3.04% sits in the 2.0–5.0% band — a PM decision; nothing is built in-session

### QB|passing_interceptions

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.24568 | 0.24603 | True | 0.00021 | [5e-05, 0.00037] | 8/8 |
| knn | 0.22378 | 0.2241 | True | 0.02211 | [0.01873, 0.02548] | 8/8 |
| hurdle | 0.26649 | 0.27359 | True | -0.0206 | [-0.03107, -0.01012] | 1/8 |
| negbin | 0.2258 | 0.23045 | True | 0.0201 | [0.01449, 0.0257] | 8/8 |

- verdict: `oracle__knn` BEATS `inc_climatology` by +0.0221 CRPS (CI95 [+0.0187, +0.0255] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9333, "pred_p0_mean": 0.7889, "real_p0": 0.7917}
- era (report-only): capture Δ 0.02274 vs legacy Δ 0.0219
- decision: ceiling 8.99% ≥ 5.0% — a §0.5 bake-off on this cell's family is licensed

### QB|rushing_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.07448 | 0.07462 | True | 0.00012 | [4e-05, 0.00019] | 8/8 |
| knn | 0.07216 | 0.07188 | False | 0.00244 | [0.00201, 0.00287] | 8/8 |
| hurdle | 0.0774 | 0.07623 | False | -0.0028 | [-0.00683, 0.00122] | 2/8 |
| negbin | 0.07106 | 0.07261 | True | 0.00354 | [0.00129, 0.00579] | 8/8 |

- verdict: `oracle__negbin` BEATS `inc_climatology` by +0.0035 CRPS (CI95 [+0.0013, +0.0058] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9329, "pred_p0_mean": 0.9435, "real_p0": 0.9329}
- era (report-only): capture Δ 0.00309 vs legacy Δ 0.00369
- decision: ceiling 4.74% sits in the 2.0–5.0% band — a PM decision; nothing is built in-session

### QB|two_pt

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.03286 | 0.03294 | True | 2e-05 | [-1e-05, 5e-05] | 6/8 |
| knn | 0.03233 | 0.0323 | False | 0.00055 | [0.00032, 0.00077] | 8/8 |
| negbin | 0.03292 | 0.03462 | True | -4e-05 | [-0.00067, 0.0006] | 3/8 |
| hurdle | INAPPLICABLE | — | — | — | — | 8 oracle / 6 matched folds inapplicable |

- verdict: `oracle__knn` BEATS `inc_climatology` by +0.0006 CRPS (CI95 [+0.0003, +0.0008] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9679, "pred_p0_mean": 0.9698, "real_p0": 0.9679}
- era (report-only): capture Δ 0.00049 vs legacy Δ 0.00057
- decision: ceiling 1.67% < the 2.0% band — the champion's per-stat marginal is already near its ceiling on this cell

### RB|carries

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 3.55479 | 3.5582 | True | -1.27553 | [-1.36351, -1.18755] | 0/8 |
| head_bank | 2.41474 | 2.57595 | True | -0.13548 | [-0.19148, -0.07949] | 0/8 |
| cand_quantile | 2.14571 | 2.18044 | True | 0.13355 | [0.0926, 0.1745] | 8/8 |
| knn | 2.51023 | 2.62749 | True | -0.23097 | [-0.265, -0.19695] | 0/8 |
| hurdle | 2.19322 | 2.23341 | True | 0.08603 | [0.05731, 0.11476] | 8/8 |
| negbin | 2.41257 | 2.39209 | False | -0.13331 | [-0.19499, -0.07162] | 0/8 |

- verdict: `oracle__cand_quantile` BEATS `inc_head_bank` by +0.1336 CRPS (CI95 [+0.0926, +0.1745] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.8135, "pred_p0_mean": 0.2123, "real_p0": 0.3896}
- era (report-only): capture Δ 0.12684 vs legacy Δ 0.13579
- decision: ceiling 5.86% ≥ 5.0% — a §0.5 bake-off on this cell's family is licensed

### RB|fumbles_lost

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.02933 | 0.02937 | True | 4e-05 | [0.0, 8e-05] | 5/8 |
| knn | 0.02886 | 0.02892 | True | 0.00051 | [0.00021, 0.0008] | 8/8 |
| hurdle | 0.03017 | 0.03021 | True | -0.0008 | [-0.00135, -0.00024] | 1/8 |
| negbin | 0.02991 | 0.03153 | True | -0.00054 | [-0.00081, -0.00028] | 0/8 |

- verdict: `oracle__knn` BEATS `inc_climatology` by +0.0005 CRPS (CI95 [+0.0002, +0.0008] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9707, "pred_p0_mean": 0.9711, "real_p0": 0.9706}
- era (report-only): capture Δ 0.00043 vs legacy Δ 0.00053
- decision: ceiling 1.73% < the 2.0% band — the champion's per-stat marginal is already near its ceiling on this cell

### RB|receiving_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.04277 | 0.04282 | True | 3e-05 | [-0.0, 6e-05] | 6/8 |
| knn | 0.04196 | 0.04195 | False | 0.00084 | [0.00048, 0.00121] | 8/8 |
| hurdle | 0.04438 | 0.04406 | False | -0.00157 | [-0.00302, -0.00012] | 2/8 |
| negbin | 0.04356 | 0.04459 | True | -0.00075 | [-0.00126, -0.00025] | 1/8 |

- verdict: `oracle__knn` BEATS `inc_climatology` by +0.0008 CRPS (CI95 [+0.0005, +0.0012] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9584, "pred_p0_mean": 0.9585, "real_p0": 0.9584}
- era (report-only): capture Δ 0.00129 vs legacy Δ 0.0007
- decision: ceiling 1.97% < the 2.0% band — the champion's per-stat marginal is already near its ceiling on this cell

### RB|receptions

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.79557 | 0.79656 | True | -0.116 | [-0.13603, -0.09597] | 0/8 |
| head_bank | 0.72366 | 0.78207 | True | -0.04409 | [-0.05485, -0.03334] | 0/8 |
| cand_quantile | 0.62962 | 0.63607 | True | 0.04994 | [0.04037, 0.05952] | 8/8 |
| knn | 0.65358 | 0.66459 | True | 0.02599 | [0.01497, 0.03701] | 8/8 |
| hurdle | 0.65137 | 0.65673 | True | 0.0282 | [0.01304, 0.04335] | 8/8 |
| negbin | 0.63122 | 0.65136 | True | 0.04834 | [0.03509, 0.0616] | 8/8 |

- verdict: `oracle__cand_quantile` BEATS `inc_head_bank` by +0.0499 CRPS (CI95 [+0.0404, +0.0595] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.8154, "pred_p0_mean": 0.2538, "real_p0": 0.5362}
- era (report-only): capture Δ 0.05916 vs legacy Δ 0.04687
- decision: ceiling 7.35% ≥ 5.0% — a §0.5 bake-off on this cell's family is licensed

### RB|targets

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.99021 | 0.99172 | True | -0.17868 | [-0.20038, -0.15697] | 0/8 |
| head_bank | 0.87616 | 0.94643 | True | -0.06462 | [-0.07837, -0.05088] | 0/8 |
| cand_quantile | 0.76572 | 0.77074 | True | 0.04581 | [0.03502, 0.05661] | 8/8 |
| knn | 0.79932 | 0.81529 | True | 0.01221 | [-0.00419, 0.02861] | 6/8 |
| hurdle | 0.79083 | 0.79019 | False | 0.02071 | [0.00542, 0.03599] | 8/8 |
| negbin | 0.77342 | 0.80126 | True | 0.03811 | [0.02819, 0.04803] | 8/8 |

- verdict: `oracle__cand_quantile` BEATS `inc_head_bank` by +0.0458 CRPS (CI95 [+0.0350, +0.0566] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.8141, "pred_p0_mean": 0.2453, "real_p0": 0.4897}
- era (report-only): capture Δ 0.05515 vs legacy Δ 0.0427
- decision: ceiling 5.64% ≥ 5.0% — a §0.5 bake-off on this cell's family is licensed

### RB|two_pt

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.00813 | 0.00815 | True | 0.0 | [-0.0, 1e-05] | 4/8 |
| knn | 0.00813 | 0.00812 | False | 1e-05 | [-2e-05, 3e-05] | 5/8 |
| negbin | 0.00823 | 0.00872 | True | -0.0001 | [-0.00014, -6e-05] | 0/8 |
| hurdle | INAPPLICABLE | — | — | — | — | 8 oracle / 6 matched folds inapplicable |

- verdict: `oracle__knn` TIES `inc_climatology` by +0.0000 CRPS (CI95 [-0.0000, +0.0000] spans zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.992, "pred_p0_mean": 0.995, "real_p0": 0.992}
- era (report-only): capture Δ 2e-05 vs legacy Δ 1e-05
- decision: ceiling 0.09% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### TE|fumbles_lost

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.00794 | 0.00795 | True | 0.0 | [-0.0, 0.0] | 3/8 |
| knn | 0.00795 | 0.00793 | False | -1e-05 | [-3e-05, 1e-05] | 4/8 |
| hurdle | 0.00797 | 0.00798 | True | -3e-05 | [-5e-05, -1e-05] | 1/8 |
| negbin | 0.00804 | 0.0089 | True | -0.0001 | [-0.00015, -5e-05] | 1/8 |

- verdict: `oracle__marginal` TIES `inc_climatology` by +0.0000 CRPS (CI95 [-0.0000, +0.0000] spans zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.992, "pred_p0_mean": 0.995, "real_p0": 0.992}
- era (report-only): capture Δ 0.0 vs legacy Δ 0.0
- decision: ceiling 0.02% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### TE|receiving_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.09387 | 0.09426 | True | 0.00029 | [0.00012, 0.00046] | 8/8 |
| knn | 0.09003 | 0.09052 | True | 0.00412 | [0.00294, 0.00531] | 8/8 |
| hurdle | 0.09932 | 0.09884 | False | -0.00517 | [-0.00747, -0.00286] | 0/8 |
| negbin | 0.09341 | 0.09447 | True | 0.00075 | [-0.00084, 0.00233] | 5/8 |

- verdict: `oracle__knn` BEATS `inc_climatology` by +0.0041 CRPS (CI95 [+0.0029, +0.0053] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9464, "pred_p0_mean": 0.902, "real_p0": 0.9098}
- era (report-only): capture Δ 0.00533 vs legacy Δ 0.00372
- decision: ceiling 4.38% sits in the 2.0–5.0% band — a PM decision; nothing is built in-session

### TE|receptions

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.9704 | 0.97221 | True | -0.21736 | [-0.2499, -0.18483] | 0/8 |
| head_bank | 0.79444 | 0.87168 | True | -0.0414 | [-0.04971, -0.03309] | 0/8 |
| cand_quantile | 0.69903 | 0.71633 | True | 0.05401 | [0.04509, 0.06292] | 8/8 |
| knn | 0.778 | 0.8014 | True | -0.02496 | [-0.04139, -0.00854] | 1/8 |
| hurdle | 0.71533 | 0.73137 | True | 0.03771 | [0.02026, 0.05516] | 8/8 |
| negbin | 0.70485 | 0.73309 | True | 0.04819 | [0.03306, 0.06332] | 8/8 |

- verdict: `oracle__cand_quantile` BEATS `inc_head_bank` by +0.0540 CRPS (CI95 [+0.0451, +0.0629] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.7981, "pred_p0_mean": 0.2285, "real_p0": 0.4946}
- era (report-only): capture Δ 0.05238 vs legacy Δ 0.05455
- decision: ceiling 7.17% ≥ 5.0% — a §0.5 bake-off on this cell's family is licensed

### TE|targets

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 1.31662 | 1.31991 | True | -0.36496 | [-0.40465, -0.32527] | 0/8 |
| head_bank | 0.99824 | 1.11352 | True | -0.04657 | [-0.05992, -0.03323] | 0/8 |
| cand_quantile | 0.89088 | 0.91056 | True | 0.06078 | [0.04711, 0.07445] | 8/8 |
| knn | 1.03193 | 1.06325 | True | -0.08027 | [-0.09792, -0.06262] | 0/8 |
| hurdle | 0.90806 | 0.92832 | True | 0.0436 | [0.03014, 0.05706] | 8/8 |
| negbin | 0.90592 | 0.95228 | True | 0.04574 | [0.03221, 0.05927] | 8/8 |

- verdict: `oracle__cand_quantile` BEATS `inc_head_bank` by +0.0608 CRPS (CI95 [+0.0471, +0.0745] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.7974, "pred_p0_mean": 0.2198, "real_p0": 0.4318}
- era (report-only): capture Δ 0.06322 vs legacy Δ 0.05997
- decision: ceiling 6.39% ≥ 5.0% — a §0.5 bake-off on this cell's family is licensed

### TE|two_pt

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.00535 | 0.00536 | True | 0.0 | [-0.0, 1e-05] | 3/8 |
| knn | 0.00535 | 0.00534 | False | 1e-05 | [-1e-05, 2e-05] | 5/8 |
| negbin | 0.00542 | 0.00597 | True | -6e-05 | [-8e-05, -4e-05] | 0/8 |
| hurdle | INAPPLICABLE | — | — | — | — | 8 oracle / 6 matched folds inapplicable |

- verdict: `oracle__knn` TIES `inc_climatology` by +0.0000 CRPS (CI95 [-0.0000, +0.0000] spans zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9946, "pred_p0_mean": 0.995, "real_p0": 0.9946}
- era (report-only): capture Δ -1e-05 vs legacy Δ 1e-05
- decision: ceiling 0.10% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### WR|fumbles_lost

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.01214 | 0.01215 | True | 1e-05 | [0.0, 2e-05] | 6/8 |
| knn | 0.0121 | 0.01211 | True | 5e-05 | [2e-05, 8e-05] | 7/8 |
| hurdle | 0.01235 | 0.01227 | False | -0.0002 | [-0.00037, -2e-05] | 1/8 |
| negbin | 0.01237 | 0.01322 | True | -0.00022 | [-0.00029, -0.00014] | 0/8 |

- verdict: `oracle__knn` BEATS `inc_climatology` by +0.0001 CRPS (CI95 [+0.0000, +0.0001] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9878, "pred_p0_mean": 0.9899, "real_p0": 0.9878}
- era (report-only): capture Δ 3e-05 vs legacy Δ 6e-05
- decision: ceiling 0.43% < the 2.0% band — the champion's per-stat marginal is already near its ceiling on this cell

### WR|receiving_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.13439 | 0.13451 | True | 0.00016 | [2e-05, 0.00029] | 7/8 |
| knn | 0.12407 | 0.12494 | True | 0.01047 | [0.00865, 0.0123] | 8/8 |
| hurdle | 0.14505 | 0.14371 | False | -0.01051 | [-0.01293, -0.0081] | 0/8 |
| negbin | 0.13199 | 0.13313 | True | 0.00255 | [0.00022, 0.00487] | 6/8 |

- verdict: `oracle__knn` BEATS `inc_climatology` by +0.0105 CRPS (CI95 [+0.0086, +0.0123] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9828, "pred_p0_mean": 0.8624, "real_p0": 0.8669}
- era (report-only): capture Δ 0.0091 vs legacy Δ 0.01093
- decision: ceiling 7.78% ≥ 5.0% — a §0.5 bake-off on this cell's family is licensed

### WR|receptions

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 1.26123 | 1.26369 | True | -0.30976 | [-0.35153, -0.26799] | 0/8 |
| head_bank | 1.00007 | 1.10101 | True | -0.04861 | [-0.06446, -0.03276] | 0/8 |
| cand_quantile | 0.90354 | 0.93628 | True | 0.04793 | [0.03483, 0.06103] | 8/8 |
| knn | 0.93134 | 0.96439 | True | 0.02013 | [0.00431, 0.03595] | 7/8 |
| hurdle | 0.9254 | 0.95251 | True | 0.02606 | [0.00703, 0.04509] | 8/8 |
| negbin | 0.90804 | 0.95261 | True | 0.04342 | [0.0325, 0.05434] | 8/8 |

- verdict: `oracle__cand_quantile` BEATS `inc_head_bank` by +0.0479 CRPS (CI95 [+0.0348, +0.0610] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.8053, "pred_p0_mean": 0.2059, "real_p0": 0.4089}
- era (report-only): capture Δ 0.04524 vs legacy Δ 0.04882
- decision: ceiling 5.04% ≥ 5.0% — a §0.5 bake-off on this cell's family is licensed

### WR|targets

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 1.88992 | 1.89286 | True | -0.57597 | [-0.64273, -0.50922] | 0/8 |
| head_bank | 1.3809 | 1.52722 | True | -0.06695 | [-0.07747, -0.05643] | 0/8 |
| cand_quantile | 1.268 | 1.31494 | True | 0.04595 | [0.03101, 0.06089] | 8/8 |
| knn | 1.33621 | 1.39059 | True | -0.02226 | [-0.0432, -0.00131] | 2/8 |
| hurdle | 1.29679 | 1.3333 | True | 0.01716 | [0.00247, 0.03186] | 6/8 |
| negbin | 1.30254 | 1.36197 | True | 0.01141 | [-0.00032, 0.02313] | 6/8 |

- verdict: `oracle__cand_quantile` BEATS `inc_head_bank` by +0.0459 CRPS (CI95 [+0.0310, +0.0609] excludes zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.8036, "pred_p0_mean": 0.1838, "real_p0": 0.3396}
- era (report-only): capture Δ 0.03652 vs legacy Δ 0.04909
- decision: ceiling 3.50% sits in the 2.0–5.0% band — a PM decision; nothing is built in-session

### WR|two_pt

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.00776 | 0.00777 | True | 0.0 | [0.0, 0.0] | 0/8 |
| knn | 0.00776 | 0.00774 | False | 1e-05 | [-0.0, 1e-05] | 5/8 |
| negbin | 0.00784 | 0.0087 | True | -7e-05 | [-0.0001, -5e-05] | 0/8 |
| hurdle | INAPPLICABLE | — | — | — | — | 8 oracle / 6 matched folds inapplicable |

- verdict: `oracle__knn` TIES `inc_climatology` by +0.0000 CRPS (CI95 [-0.0000, +0.0000] spans zero)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9922, "pred_p0_mean": 0.995, "real_p0": 0.9922}
- era (report-only): capture Δ 0.0 vs legacy Δ 1e-05
- decision: ceiling 0.07% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding True) — NO regardless of magnitude

## Pre-registration

- cells: ['QB|attempts', 'QB|passing_interceptions', 'QB|carries', 'QB|rushing_tds', 'QB|fumbles_lost', 'QB|two_pt', 'RB|carries', 'RB|targets', 'RB|receptions', 'RB|receiving_tds', 'RB|fumbles_lost', 'RB|two_pt', 'WR|targets', 'WR|receptions', 'WR|receiving_tds', 'WR|fumbles_lost', 'WR|two_pt', 'TE|targets', 'TE|receptions', 'TE|receiving_tds', 'TE|fumbles_lost', 'TE|two_pt']; classes: count=['attempts', 'carries', 'targets', 'receptions'] event=['receiving_tds', 'rushing_tds', 'passing_interceptions', 'fumbles_lost', 'two_pt']; forms per class: {'count': ['marginal', 'head_bank', 'cand_quantile', 'knn', 'hurdle', 'negbin'], 'event': ['marginal', 'knn', 'hurdle', 'negbin']}; incumbents per class: {'count': ['inc_head_bank', 'inc_climatology'], 'event': ['inc_climatology']}.
- decision: bands [2.0, 5.0] on ceiling_pct ∧ stat_ok (CI excludes 0 ∧ calibrated fold clause ∧ BH q=0.1 binding own AND pooled over two families); LICENSE rule: ['YES', 'MARGINAL'] ∧ stat_ok → Phase B; NO → Phase-C default. PBO UNDEFINED (anchor contrast); no arm is selected.
- matched-n sizing: marginal = full block (W6); conditional forms = (K−1)/K of the block (K=3, the NF-W6b-C refinement). MIN_COND_ROWS=40 (a hurdle form below it is INAPPLICABLE, recorded, never scored on a constant).

_Runtime: 5236.3s · seed 20260817 · matrix cache key 26c34fbe778c9d87_