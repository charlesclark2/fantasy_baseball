# NF-W6d Phase A — the ceiling gate over every remaining optimizer-input stat cell

**Generated:** 2026-08-15T19:19:00+00:00 · **folds:** 2 half-season blocks (2025H1…2025H2, the NF-W1 axis verbatim) · **rows:** 84553 player-weeks · **cells:** 4

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** (research-only, no changelog). THE DECISION GATE, not a bake-off: per-form block-peeking oracles floored at matched-n controls sized to the peek's effective n (NF-W6b-C). A cell with no ceiling is a recorded finding — its point mean is already near-optimal — and gets a calibrated Phase-C default. Metric `crps_q199`; the nihilist is SCORED every cell (NF-D11). Every direction word is three-way and derived at report time (NF-W2e).

**PIT gate (NF-W0a `assert_point_in_time`):** 175 weeks / 84553 records checked; 0 rows dropped. Label attach: {'n_rows': 84553, 'feed_dup_keys': 0, 'passing_interceptions_total': 4121.0, 'passing_interceptions_filled_zero_rows': 26835, 'fumbles_lost_total': 2383.0, 'fumbles_lost_filled_zero_rows': 26835, 'two_pt_total': 978.0, 'two_pt_filled_zero_rows': 26835}

## Verdict: **CEILING-GATE yes=0 marginal=0 no=4 of 4 cells → 0 licensed for the bake-off; 4 point-only (Phase-C default)**

- LICENSED for the Phase-B bake-off (YES or MARGINAL ∧ stat_ok): []
- YES: [] · MARGINAL: [] · NO (point-only → Phase-C default): ['QB|two_pt', 'RB|two_pt', 'TE|two_pt', 'WR|two_pt']

## Per-cell ceilings (vs the BINDING incumbent; max over per-form block-peeking oracles)

| cell | class | binding incumbent | inc CRPS | best form | ceiling Δ | ceiling % | CI95 | wins | p | BH | peek>matched | inapplicable | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| QB|two_pt | event | inc_climatology | 0.03354 | knn | 0.00049 | 1.467 | n/a | 2/2 | None | False | False | hurdle | **NO** → default |
| RB|two_pt | event | inc_climatology | 0.00741 | knn | 2e-05 | 0.204 | n/a | 2/2 | None | False | True | hurdle | **NO** → default |
| TE|two_pt | event | inc_climatology | 0.00516 | marginal | 0.0 | 0.087 | n/a | 1/2 | None | False | True | hurdle | **NO** → default |
| WR|two_pt | event | inc_climatology | 0.00863 | marginal | 0.0 | 0.0 | n/a | 0/2 | None | False | True | hurdle | **NO** → default |

## Per-form detail (oracle vs matched-n — NF1.9 (f); conditional controls at (K−1)/K)

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

_Runtime: 38.5s · seed 20260817 · matrix cache key 26c34fbe778c9d87_