# NF-W6d Phase A — the ceiling gate over every remaining optimizer-input stat cell

**Generated:** 2026-08-15T19:42:33+00:00 · **folds:** 2 half-season blocks (2025H1…2025H2, the NF-W1 axis verbatim) · **rows:** 84553 player-weeks · **cells:** 22

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** (research-only, no changelog). THE DECISION GATE, not a bake-off: per-form block-peeking oracles floored at matched-n controls sized to the peek's effective n (NF-W6b-C). A cell with no ceiling is a recorded finding — its point mean is already near-optimal — and gets a calibrated Phase-C default. Metric `crps_q199`; the nihilist is SCORED every cell (NF-D11). Every direction word is three-way and derived at report time (NF-W2e).

**PIT gate (NF-W0a `assert_point_in_time`):** 175 weeks / 84553 records checked; 0 rows dropped. Label attach: {'cache': 'hit'}

## Verdict: **CEILING-GATE yes=0 marginal=0 no=22 of 22 cells → 0 licensed for the bake-off; 22 point-only (Phase-C default)**

- LICENSED for the Phase-B bake-off (YES or MARGINAL ∧ stat_ok): []
- YES: [] · MARGINAL: [] · NO (point-only → Phase-C default): ['QB|attempts', 'QB|carries', 'QB|fumbles_lost', 'QB|passing_interceptions', 'QB|rushing_tds', 'QB|two_pt', 'RB|carries', 'RB|fumbles_lost', 'RB|receiving_tds', 'RB|receptions', 'RB|targets', 'RB|two_pt', 'TE|fumbles_lost', 'TE|receiving_tds', 'TE|receptions', 'TE|targets', 'TE|two_pt', 'WR|fumbles_lost', 'WR|receiving_tds', 'WR|receptions', 'WR|targets', 'WR|two_pt']

## Per-cell ceilings (vs the BINDING incumbent; max over per-form block-peeking oracles)

| cell | class | binding incumbent | inc CRPS | best form | ceiling Δ | ceiling % | CI95 | wins | p | BH | peek>matched | inapplicable | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| QB|attempts | count | inc_head_bank | 4.85183 | cand_quantile | 0.48212 | 9.937 | n/a | 2/2 | None | False | True | — | **NO** → default |
| QB|carries | count | inc_head_bank | 0.97592 | cand_quantile | 0.05226 | 5.355 | n/a | 2/2 | None | False | False | — | **NO** → default |
| RB|carries | count | inc_head_bank | 2.15367 | cand_quantile | 0.12684 | 5.89 | n/a | 2/2 | None | False | True | — | **NO** → default |
| RB|receptions | count | inc_head_bank | 0.63258 | negbin | 0.06299 | 9.958 | n/a | 2/2 | None | False | True | — | **NO** → default |
| RB|targets | count | inc_head_bank | 0.74351 | cand_quantile | 0.05515 | 7.418 | n/a | 2/2 | None | False | True | — | **NO** → default |
| TE|receptions | count | inc_head_bank | 0.74984 | cand_quantile | 0.05238 | 6.986 | n/a | 2/2 | None | False | True | — | **NO** → default |
| TE|targets | count | inc_head_bank | 0.93861 | cand_quantile | 0.06322 | 6.735 | n/a | 2/2 | None | False | True | — | **NO** → default |
| WR|receptions | count | inc_head_bank | 0.91084 | cand_quantile | 0.04524 | 4.967 | n/a | 2/2 | None | False | True | — | **NO** → default |
| WR|targets | count | inc_head_bank | 1.28417 | cand_quantile | 0.03652 | 2.844 | n/a | 2/2 | None | False | True | — | **NO** → default |
| QB|fumbles_lost | event | inc_climatology | 0.07385 | knn | 0.00209 | 2.833 | n/a | 2/2 | None | False | False | — | **NO** → default |
| QB|passing_interceptions | event | inc_climatology | 0.23218 | negbin | 0.02456 | 10.576 | n/a | 2/2 | None | False | True | — | **NO** → default |
| QB|rushing_tds | event | inc_climatology | 0.07487 | negbin | 0.00309 | 4.122 | n/a | 2/2 | None | False | True | — | **NO** → default |
| QB|two_pt | event | inc_climatology | 0.03354 | knn | 0.00049 | 1.467 | n/a | 2/2 | None | False | False | hurdle | **NO** → default |
| RB|fumbles_lost | event | inc_climatology | 0.02786 | knn | 0.00043 | 1.54 | n/a | 2/2 | None | False | False | — | **NO** → default |
| RB|receiving_tds | event | inc_climatology | 0.04713 | knn | 0.00129 | 2.727 | n/a | 2/2 | None | False | True | — | **NO** → default |
| RB|two_pt | event | inc_climatology | 0.00741 | knn | 2e-05 | 0.204 | n/a | 2/2 | None | False | True | hurdle | **NO** → default |
| TE|fumbles_lost | event | inc_climatology | 0.00821 | knn | 1e-05 | 0.13 | n/a | 1/2 | None | False | False | — | **NO** → default |
| TE|receiving_tds | event | inc_climatology | 0.10844 | knn | 0.00533 | 4.92 | n/a | 2/2 | None | False | True | — | **NO** → default |
| TE|two_pt | event | inc_climatology | 0.00516 | marginal | 0.0 | 0.087 | n/a | 1/2 | None | False | True | hurdle | **NO** → default |
| WR|fumbles_lost | event | inc_climatology | 0.00865 | knn | 3e-05 | 0.369 | n/a | 2/2 | None | False | True | — | **NO** → default |
| WR|receiving_tds | event | inc_climatology | 0.12954 | knn | 0.0091 | 7.028 | n/a | 2/2 | None | False | False | — | **NO** → default |
| WR|two_pt | event | inc_climatology | 0.00863 | marginal | 0.0 | 0.0 | n/a | 0/2 | None | False | True | hurdle | **NO** → default |

## Per-form detail (oracle vs matched-n — NF1.9 (f); conditional controls at (K−1)/K)

### QB|attempts

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 8.30024 | 8.31277 | True | -3.44841 | [None, None] | 0/2 |
| head_bank | 5.28583 | 5.5733 | True | -0.43401 | [None, None] | 0/2 |
| cand_quantile | 4.36971 | 4.55193 | True | 0.48212 | [None, None] | 2/2 |
| knn | 5.75998 | 5.85613 | True | -0.90815 | [None, None] | 0/2 |
| hurdle | 4.62178 | 4.7227 | True | 0.23004 | [None, None] | 2/2 |
| negbin | 7.4832 | 5.44586 | False | -2.63138 | [None, None] | 0/2 |

- verdict: `oracle__cand_quantile` TIES `inc_head_bank` by +0.4821 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.801, "pred_p0_mean": 0.259, "real_p0": 0.5386}
- era (report-only): capture Δ 0.48212 vs legacy Δ None
- decision: ceiling 9.94% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### QB|carries

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 1.20286 | 1.2047 | True | -0.22694 | [None, None] | 0/2 |
| head_bank | 1.10143 | 1.14157 | True | -0.12552 | [None, None] | 0/2 |
| cand_quantile | 0.92366 | 0.91274 | False | 0.05226 | [None, None] | 2/2 |
| knn | 1.00942 | 1.0131 | True | -0.03351 | [None, None] | 0/2 |
| hurdle | 0.95616 | 0.9605 | True | 0.01976 | [None, None] | 2/2 |
| negbin | 0.9595 | 0.98443 | True | 0.01642 | [None, None] | 2/2 |

- verdict: `oracle__cand_quantile` TIES `inc_head_bank` by +0.0523 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.7813, "pred_p0_mean": 0.2589, "real_p0": 0.5656}
- era (report-only): capture Δ 0.05226 vs legacy Δ None
- decision: ceiling 5.36% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### QB|fumbles_lost

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.07377 | 0.07393 | True | 7e-05 | [None, None] | 2/2 |
| knn | 0.07176 | 0.07149 | False | 0.00209 | [None, None] | 2/2 |
| hurdle | 0.08164 | 0.08127 | False | -0.00779 | [None, None] | 0/2 |
| negbin | 0.07519 | 0.07544 | True | -0.00134 | [None, None] | 0/2 |

- verdict: `oracle__knn` TIES `inc_climatology` by +0.0021 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9278, "pred_p0_mean": 0.9221, "real_p0": 0.9279}
- era (report-only): capture Δ 0.00209 vs legacy Δ None
- decision: ceiling 2.83% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### QB|passing_interceptions

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.23171 | 0.23233 | True | 0.00047 | [None, None] | 2/2 |
| knn | 0.20943 | 0.21157 | True | 0.02274 | [None, None] | 2/2 |
| hurdle | 0.25207 | 0.25786 | True | -0.01989 | [None, None] | 0/2 |
| negbin | 0.20762 | 0.21302 | True | 0.02456 | [None, None] | 2/2 |

- verdict: `oracle__negbin` TIES `inc_climatology` by +0.0246 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9431, "pred_p0_mean": 0.7889, "real_p0": 0.7969}
- era (report-only): capture Δ 0.02456 vs legacy Δ None
- decision: ceiling 10.58% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### QB|rushing_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.07481 | 0.07486 | True | 6e-05 | [None, None] | 2/2 |
| knn | 0.0727 | 0.0726 | False | 0.00217 | [None, None] | 2/2 |
| hurdle | 0.07797 | 0.07893 | True | -0.0031 | [None, None] | 0/2 |
| negbin | 0.07178 | 0.0756 | True | 0.00309 | [None, None] | 2/2 |

- verdict: `oracle__negbin` TIES `inc_climatology` by +0.0031 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9359, "pred_p0_mean": 0.9397, "real_p0": 0.9358}
- era (report-only): capture Δ 0.00309 vs legacy Δ None
- decision: ceiling 4.12% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### QB|two_pt

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.03353 | 0.03354 | True | 2e-05 | [None, None] | 2/2 |
| knn | 0.03305 | 0.03282 | False | 0.00049 | [None, None] | 2/2 |
| negbin | 0.03355 | 0.03725 | True | -1e-05 | [None, None] | 1/2 |
| hurdle | INAPPLICABLE | — | — | — | — | 2 oracle / 1 matched folds inapplicable |

- verdict: `oracle__knn` TIES `inc_climatology` by +0.0005 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9687, "pred_p0_mean": 0.9698, "real_p0": 0.9686}
- era (report-only): capture Δ 0.00049 vs legacy Δ None
- decision: ceiling 1.47% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### RB|carries

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 3.55997 | 3.56583 | True | -1.4063 | [None, None] | 0/2 |
| head_bank | 2.34479 | 2.34677 | True | -0.19113 | [None, None] | 0/2 |
| cand_quantile | 2.02683 | 2.0713 | True | 0.12684 | [None, None] | 2/2 |
| knn | 2.40843 | 2.55091 | True | -0.25476 | [None, None] | 0/2 |
| hurdle | 2.07757 | 2.08192 | True | 0.07609 | [None, None] | 2/2 |
| negbin | 2.34018 | 2.18083 | False | -0.18651 | [None, None] | 0/2 |

- verdict: `oracle__cand_quantile` TIES `inc_head_bank` by +0.1268 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.8176, "pred_p0_mean": 0.2147, "real_p0": 0.396}
- era (report-only): capture Δ 0.12684 vs legacy Δ None
- decision: ceiling 5.89% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### RB|fumbles_lost

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.02782 | 0.02783 | True | 3e-05 | [None, None] | 1/2 |
| knn | 0.02743 | 0.0272 | False | 0.00043 | [None, None] | 2/2 |
| hurdle | 0.02864 | 0.02867 | True | -0.00078 | [None, None] | 0/2 |
| negbin | 0.02851 | 0.03004 | True | -0.00066 | [None, None] | 0/2 |

- verdict: `oracle__knn` TIES `inc_climatology` by +0.0004 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.972, "pred_p0_mean": 0.9698, "real_p0": 0.972}
- era (report-only): capture Δ 0.00043 vs legacy Δ None
- decision: ceiling 1.54% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### RB|receiving_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.04711 | 0.04711 | False | 2e-05 | [None, None] | 1/2 |
| knn | 0.04585 | 0.04594 | True | 0.00129 | [None, None] | 2/2 |
| hurdle | 0.04877 | 0.04834 | False | -0.00164 | [None, None] | 0/2 |
| negbin | 0.04801 | 0.04811 | True | -0.00088 | [None, None] | 0/2 |

- verdict: `oracle__knn` TIES `inc_climatology` by +0.0013 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9543, "pred_p0_mean": 0.9598, "real_p0": 0.9543}
- era (report-only): capture Δ 0.00129 vs legacy Δ None
- decision: ceiling 2.73% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### RB|receptions

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.76977 | 0.77032 | True | -0.13719 | [None, None] | 0/2 |
| head_bank | 0.66221 | 0.72063 | True | -0.02963 | [None, None] | 0/2 |
| cand_quantile | 0.57342 | 0.5854 | True | 0.05916 | [None, None] | 2/2 |
| knn | 0.62034 | 0.62824 | True | 0.01223 | [None, None] | 2/2 |
| hurdle | 0.58429 | 0.59013 | True | 0.04829 | [None, None] | 2/2 |
| negbin | 0.56958 | 0.59917 | True | 0.06299 | [None, None] | 2/2 |

- verdict: `oracle__negbin` TIES `inc_head_bank` by +0.0630 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.8223, "pred_p0_mean": 0.2615, "real_p0": 0.5452}
- era (report-only): capture Δ 0.06299 vs legacy Δ None
- decision: ceiling 9.96% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### RB|targets

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.95595 | 0.95729 | True | -0.21245 | [None, None] | 0/2 |
| head_bank | 0.8128 | 0.86859 | True | -0.06929 | [None, None] | 0/2 |
| cand_quantile | 0.68836 | 0.70597 | True | 0.05515 | [None, None] | 2/2 |
| knn | 0.75842 | 0.76989 | True | -0.01491 | [None, None] | 0/2 |
| hurdle | 0.69811 | 0.71958 | True | 0.0454 | [None, None] | 2/2 |
| negbin | 0.70066 | 0.72162 | True | 0.04284 | [None, None] | 2/2 |

- verdict: `oracle__cand_quantile` TIES `inc_head_bank` by +0.0551 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.8251, "pred_p0_mean": 0.2548, "real_p0": 0.4981}
- era (report-only): capture Δ 0.05515 vs legacy Δ None
- decision: ceiling 7.42% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### RB|two_pt

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.00741 | 0.00744 | True | 0.0 | [None, None] | 2/2 |
| knn | 0.0074 | 0.0074 | True | 2e-05 | [None, None] | 2/2 |
| negbin | 0.00754 | 0.00827 | True | -0.00013 | [None, None] | 0/2 |
| hurdle | INAPPLICABLE | — | — | — | — | 2 oracle / 1 matched folds inapplicable |

- verdict: `oracle__knn` TIES `inc_climatology` by +0.0000 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9925, "pred_p0_mean": 0.995, "real_p0": 0.9926}
- era (report-only): capture Δ 2e-05 vs legacy Δ None
- decision: ceiling 0.20% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### TE|fumbles_lost

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.00821 | 0.00821 | True | 0.0 | [None, None] | 0/2 |
| knn | 0.0082 | 0.00819 | False | 1e-05 | [None, None] | 1/2 |
| hurdle | 0.00824 | 0.00824 | False | -3e-05 | [None, None] | 0/2 |
| negbin | 0.00831 | 0.00897 | True | -0.0001 | [None, None] | 0/2 |

- verdict: `oracle__knn` TIES `inc_climatology` by +0.0000 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9918, "pred_p0_mean": 0.995, "real_p0": 0.9918}
- era (report-only): capture Δ 1e-05 vs legacy Δ None
- decision: ceiling 0.13% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### TE|receiving_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.10824 | 0.10882 | True | 0.0002 | [None, None] | 2/2 |
| knn | 0.1031 | 0.10336 | True | 0.00533 | [None, None] | 2/2 |
| hurdle | 0.1126 | 0.11293 | True | -0.00417 | [None, None] | 0/2 |
| negbin | 0.1052 | 0.10712 | True | 0.00324 | [None, None] | 2/2 |

- verdict: `oracle__knn` TIES `inc_climatology` by +0.0053 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.8949, "pred_p0_mean": 0.9045, "real_p0": 0.8948}
- era (report-only): capture Δ 0.00533 vs legacy Δ None
- decision: ceiling 4.92% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### TE|receptions

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.99504 | 0.99627 | True | -0.2452 | [None, None] | 0/2 |
| head_bank | 0.78098 | 0.87651 | True | -0.03115 | [None, None] | 0/2 |
| cand_quantile | 0.69745 | 0.71906 | True | 0.05238 | [None, None] | 2/2 |
| knn | 0.78658 | 0.80796 | True | -0.03674 | [None, None] | 0/2 |
| hurdle | 0.71509 | 0.72682 | True | 0.03475 | [None, None] | 2/2 |
| negbin | 0.70652 | 0.74104 | True | 0.04332 | [None, None] | 2/2 |

- verdict: `oracle__cand_quantile` TIES `inc_head_bank` by +0.0524 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.7898, "pred_p0_mean": 0.2176, "real_p0": 0.4797}
- era (report-only): capture Δ 0.05238 vs legacy Δ None
- decision: ceiling 6.99% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### TE|targets

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 1.33064 | 1.33334 | True | -0.39203 | [None, None] | 0/2 |
| head_bank | 0.98163 | 1.12034 | True | -0.04302 | [None, None] | 0/2 |
| cand_quantile | 0.8754 | 0.90801 | True | 0.06322 | [None, None] | 2/2 |
| knn | 1.02751 | 1.06331 | True | -0.0889 | [None, None] | 0/2 |
| hurdle | 0.88696 | 0.9246 | True | 0.05165 | [None, None] | 2/2 |
| negbin | 0.89226 | 0.95184 | True | 0.04635 | [None, None] | 2/2 |

- verdict: `oracle__cand_quantile` TIES `inc_head_bank` by +0.0632 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.7867, "pred_p0_mean": 0.2126, "real_p0": 0.4272}
- era (report-only): capture Δ 0.06322 vs legacy Δ None
- decision: ceiling 6.74% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### TE|two_pt

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.00515 | 0.00516 | True | 0.0 | [None, None] | 1/2 |
| knn | 0.00516 | 0.00513 | False | -1e-05 | [None, None] | 1/2 |
| negbin | 0.00522 | 0.00676 | True | -7e-05 | [None, None] | 0/2 |
| hurdle | INAPPLICABLE | — | — | — | — | 2 oracle / 1 matched folds inapplicable |

- verdict: `oracle__marginal` TIES `inc_climatology` by +0.0000 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9948, "pred_p0_mean": 0.995, "real_p0": 0.9948}
- era (report-only): capture Δ 0.0 vs legacy Δ None
- decision: ceiling 0.09% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### WR|fumbles_lost

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.00863 | 0.00863 | False | 1e-05 | [None, None] | 2/2 |
| knn | 0.00862 | 0.00865 | True | 3e-05 | [None, None] | 2/2 |
| hurdle | 0.00868 | 0.00867 | False | -4e-05 | [None, None] | 1/2 |
| negbin | 0.0088 | 0.00954 | True | -0.00015 | [None, None] | 0/2 |

- verdict: `oracle__knn` TIES `inc_climatology` by +0.0000 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9913, "pred_p0_mean": 0.9899, "real_p0": 0.9913}
- era (report-only): capture Δ 3e-05 vs legacy Δ None
- decision: ceiling 0.37% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### WR|receiving_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.12941 | 0.12966 | True | 0.00013 | [None, None] | 2/2 |
| knn | 0.12044 | 0.11988 | False | 0.0091 | [None, None] | 2/2 |
| hurdle | 0.14006 | 0.1384 | False | -0.01052 | [None, None] | 0/2 |
| negbin | 0.12843 | 0.12937 | True | 0.00111 | [None, None] | 1/2 |

- verdict: `oracle__knn` TIES `inc_climatology` by +0.0091 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9842, "pred_p0_mean": 0.8643, "real_p0": 0.8718}
- era (report-only): capture Δ 0.0091 vs legacy Δ None
- decision: ceiling 7.03% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### WR|receptions

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 1.18105 | 1.18542 | True | -0.27021 | [None, None] | 0/2 |
| head_bank | 0.95114 | 1.04055 | True | -0.04029 | [None, None] | 0/2 |
| cand_quantile | 0.8656 | 0.87494 | True | 0.04524 | [None, None] | 2/2 |
| knn | 0.88272 | 0.90203 | True | 0.02812 | [None, None] | 2/2 |
| hurdle | 0.89166 | 0.8907 | False | 0.01919 | [None, None] | 2/2 |
| negbin | 0.87193 | 0.88944 | True | 0.03891 | [None, None] | 2/2 |

- verdict: `oracle__cand_quantile` TIES `inc_head_bank` by +0.0452 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.796, "pred_p0_mean": 0.2107, "real_p0": 0.4227}
- era (report-only): capture Δ 0.04524 vs legacy Δ None
- decision: ceiling 4.97% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### WR|targets

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 1.80546 | 1.81055 | True | -0.52129 | [None, None] | 0/2 |
| head_bank | 1.36377 | 1.48309 | True | -0.0796 | [None, None] | 0/2 |
| cand_quantile | 1.24765 | 1.25698 | True | 0.03652 | [None, None] | 2/2 |
| knn | 1.29768 | 1.33804 | True | -0.0135 | [None, None] | 1/2 |
| hurdle | 1.26765 | 1.28535 | True | 0.01653 | [None, None] | 1/2 |
| negbin | 1.26837 | 1.29776 | True | 0.0158 | [None, None] | 2/2 |

- verdict: `oracle__cand_quantile` TIES `inc_head_bank` by +0.0365 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.7905, "pred_p0_mean": 0.189, "real_p0": 0.3525}
- era (report-only): capture Δ 0.03652 vs legacy Δ None
- decision: ceiling 2.84% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

### WR|two_pt

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| marginal | 0.00863 | 0.00863 | True | 0.0 | [None, None] | 0/2 |
| knn | 0.00863 | 0.00861 | False | 0.0 | [None, None] | 1/2 |
| negbin | 0.00872 | 0.01085 | True | -8e-05 | [None, None] | 0/2 |
| hurdle | INAPPLICABLE | — | — | — | — | 2 oracle / 1 matched folds inapplicable |

- verdict: `oracle__marginal` TIES `inc_climatology` by +0.0000 CRPS (interval unevaluable)
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true}
- incumbent calibration: {"coverage_80": 0.9913, "pred_p0_mean": 0.995, "real_p0": 0.9913}
- era (report-only): capture Δ 0.0 vs legacy Δ None
- decision: ceiling 0.00% is not statistically demonstrable (CI-excludes-zero False, fold clause False, BH binding False) — NO regardless of magnitude

## Pre-registration

- cells: ['QB|attempts', 'QB|passing_interceptions', 'QB|carries', 'QB|rushing_tds', 'QB|fumbles_lost', 'QB|two_pt', 'RB|carries', 'RB|targets', 'RB|receptions', 'RB|receiving_tds', 'RB|fumbles_lost', 'RB|two_pt', 'WR|targets', 'WR|receptions', 'WR|receiving_tds', 'WR|fumbles_lost', 'WR|two_pt', 'TE|targets', 'TE|receptions', 'TE|receiving_tds', 'TE|fumbles_lost', 'TE|two_pt']; classes: count=['attempts', 'carries', 'targets', 'receptions'] event=['receiving_tds', 'rushing_tds', 'passing_interceptions', 'fumbles_lost', 'two_pt']; forms per class: {'count': ['marginal', 'head_bank', 'cand_quantile', 'knn', 'hurdle', 'negbin'], 'event': ['marginal', 'knn', 'hurdle', 'negbin']}; incumbents per class: {'count': ['inc_head_bank', 'inc_climatology'], 'event': ['inc_climatology']}.
- decision: bands [2.0, 5.0] on ceiling_pct ∧ stat_ok (CI excludes 0 ∧ calibrated fold clause ∧ BH q=0.1 binding own AND pooled over two families); LICENSE rule: ['YES', 'MARGINAL'] ∧ stat_ok → Phase B; NO → Phase-C default. PBO UNDEFINED (anchor contrast); no arm is selected.
- matched-n sizing: marginal = full block (W6); conditional forms = (K−1)/K of the block (K=3, the NF-W6b-C refinement). MIN_COND_ROWS=40 (a hurdle form below it is INAPPLICABLE, recorded, never scored on a constant).

_Runtime: 1363.6s · seed 20260817 · matrix cache key 26c34fbe778c9d87_