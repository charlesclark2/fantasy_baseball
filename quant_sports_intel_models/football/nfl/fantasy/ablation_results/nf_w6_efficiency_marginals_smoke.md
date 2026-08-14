# NF-W6 — efficiency + yards + touchdowns as distributional targets: THE ORACLE GATE

**Generated:** 2026-08-14T19:36:01+00:00 · **folds:** 2 half-season blocks (2025H1…2025H2, the NF-W1 axis verbatim) · **rows:** 84553 player-weeks · **cells:** 12

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** (research-only, no changelog). ⭐ This is the DECISION GATE, not a bake-off: after three component nulls (NF-W3/W4/W5) nothing is built unless a per-cell realized-efficiency ceiling is demonstrably large. Selection metric `crps_q199` (the NF-MARGIN1 dense grid); TD cells are zero-heavy ⇒ CRPS, never MAE (NF-D11/D14), with the all-zero degenerate SCORED every cell. Every direction word is three-way and derived at report time, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a `assert_point_in_time`):** 175 weeks / 84553 records checked; 0 rows dropped.

## Verdict: **CEILING-GATE[NULL] yes=0 marginal=0 no=12 of 12 cells**

no cell clears the YES band — the champion's per-stat marginals are already near their ceiling; the null is recorded and NOTHING is built (the story card's likely outcome, and a legitimate one)

## Per-cell ceilings (vs the BINDING incumbent; max over per-form block-peeking oracles)

| cell | binding incumbent | inc CRPS | best form | ceiling Δ | ceiling % | CI95 | wins | p | BH | decision |
|---|---|---|---|---|---|---|---|---|---|---|
| QB|passing_tds | inc_head_bank | 0.38807 | cand_lgbm_quantile | 0.06027 | 15.531 | n/a | 2/2 | None | False | **NO** |
| QB|passing_yards | inc_head_bank | 35.86554 | cand_lgbm_quantile | 3.94835 | 11.009 | n/a | 2/2 | None | False | **NO** |
| QB|rushing_tds | inc_climatology | 0.07487 | inc_climatology | 6e-05 | 0.076 | n/a | 2/2 | None | False | **NO** |
| QB|rushing_yards | inc_head_bank | 5.61108 | cand_lgbm_quantile | 0.76608 | 13.653 | n/a | 2/2 | None | False | **NO** |
| RB|receiving_tds | inc_climatology | 0.04713 | inc_climatology | 2e-05 | 0.052 | n/a | 1/2 | None | False | **NO** |
| RB|receiving_yards | inc_head_bank | 5.80145 | cand_lgbm_quantile | 0.63567 | 10.957 | n/a | 2/2 | None | False | **NO** |
| RB|rushing_tds | inc_climatology | 0.15764 | cand_lgbm_quantile | 0.00313 | 1.987 | n/a | 2/2 | None | False | **NO** |
| RB|rushing_yards | inc_head_bank | 12.15342 | cand_lgbm_quantile | 0.85102 | 7.002 | n/a | 2/2 | None | False | **NO** |
| TE|receiving_tds | inc_climatology | 0.10844 | cand_lgbm_quantile | 0.0017 | 1.564 | n/a | 2/2 | None | False | **NO** |
| TE|receiving_yards | inc_head_bank | 8.69088 | cand_lgbm_quantile | 0.88183 | 10.147 | n/a | 2/2 | None | False | **NO** |
| WR|receiving_tds | inc_climatology | 0.12954 | inc_climatology | 0.00013 | 0.1 | n/a | 2/2 | None | False | **NO** |
| WR|receiving_yards | inc_head_bank | 13.31589 | cand_lgbm_quantile | 0.88084 | 6.615 | n/a | 2/2 | None | False | **NO** |

## Per-form detail (oracle vs matched-n — NF1.9 (f): a peek is informative only if it beats its own form at matched n)

### QB|passing_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 0.45391 | 0.45567 | True | -0.06585 | n/a | 0/2 |
| inc_head_bank | 0.40924 | 0.42984 | True | -0.02117 | n/a | 0/2 |
| cand_lgbm_quantile | 0.3278 | 0.33127 | True | 0.06027 | n/a | 2/2 |

- verdict: `oracle__cand_lgbm_quantile` TIES `inc_head_bank` by +0.0603 CRPS (interval unevaluable)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.7959 · pred P(0) 0.3186 vs realized 0.6848
- era (report-only): capture Δ 0.06027 vs legacy Δ None
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### QB|passing_yards

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 59.81115 | 59.95849 | True | -23.94562 | n/a | 0/2 |
| inc_head_bank | 38.19229 | 42.37902 | True | -2.32676 | n/a | 0/2 |
| cand_lgbm_quantile | 31.91719 | 33.72847 | True | 3.94835 | n/a | 2/2 |

- verdict: `oracle__cand_lgbm_quantile` TIES `inc_head_bank` by +3.9484 CRPS (interval unevaluable)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.8017 · pred P(0) 0.2616 vs realized 0.5532
- era (report-only): capture Δ 3.94835 vs legacy Δ None
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### QB|rushing_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 0.07481 | 0.07486 | True | 6e-05 | n/a | 2/2 |
| inc_head_bank | 0.118 | 0.11572 | False | -0.04313 | n/a | 0/2 |
| cand_lgbm_quantile | 0.07786 | 0.07673 | False | -0.00298 | n/a | 1/2 |

- verdict: `oracle__inc_climatology` TIES `inc_climatology` by +0.0001 CRPS (interval unevaluable)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.9359 · pred P(0) 0.9397 vs realized 0.9358
- era (report-only): capture Δ 6e-05 vs legacy Δ None
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### QB|rushing_yards

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 6.03393 | 6.04303 | True | -0.42285 | n/a | 0/2 |
| inc_head_bank | 6.24607 | 6.3811 | True | -0.63499 | n/a | 0/2 |
| cand_lgbm_quantile | 4.845 | 4.7937 | False | 0.76608 | n/a | 2/2 |

- verdict: `oracle__cand_lgbm_quantile` TIES `inc_head_bank` by +0.7661 CRPS (interval unevaluable)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.8054 · pred P(0) 0.3196 vs realized 0.5822
- era (report-only): capture Δ 0.76608 vs legacy Δ None
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### RB|receiving_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 0.04711 | 0.04711 | False | 2e-05 | n/a | 1/2 |
| inc_head_bank | 0.08211 | 0.08516 | True | -0.03498 | n/a | 0/2 |
| cand_lgbm_quantile | 0.04988 | 0.04944 | False | -0.00275 | n/a | 0/2 |

- verdict: `oracle__inc_climatology` TIES `inc_climatology` by +0.0000 CRPS (interval unevaluable)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.9543 · pred P(0) 0.9598 vs realized 0.9543
- era (report-only): capture Δ 2e-05 vs legacy Δ None
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### RB|receiving_yards

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 6.37273 | 6.38223 | True | -0.57129 | n/a | 0/2 |
| inc_head_bank | 6.41957 | 6.98371 | True | -0.61812 | n/a | 0/2 |
| cand_lgbm_quantile | 5.16577 | 5.28036 | True | 0.63567 | n/a | 2/2 |

- verdict: `oracle__cand_lgbm_quantile` TIES `inc_head_bank` by +0.6357 CRPS (interval unevaluable)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.8153 · pred P(0) 0.2987 vs realized 0.5568
- era (report-only): capture Δ 0.63567 vs legacy Δ None
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### RB|rushing_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 0.15746 | 0.15786 | True | 0.00018 | n/a | 2/2 |
| inc_head_bank | 0.21053 | 0.2121 | True | -0.05289 | n/a | 0/2 |
| cand_lgbm_quantile | 0.15451 | 0.15381 | False | 0.00313 | n/a | 2/2 |

- verdict: `oracle__cand_lgbm_quantile` TIES `inc_climatology` by +0.0031 CRPS (interval unevaluable)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.9688 · pred P(0) 0.8693 vs realized 0.8574
- era (report-only): capture Δ 0.00313 vs legacy Δ None
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### RB|rushing_yards

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 16.73197 | 16.7633 | True | -4.57855 | n/a | 0/2 |
| inc_head_bank | 13.37607 | 13.61272 | True | -1.22265 | n/a | 0/2 |
| cand_lgbm_quantile | 11.30239 | 11.23139 | False | 0.85102 | n/a | 2/2 |

- verdict: `oracle__cand_lgbm_quantile` TIES `inc_head_bank` by +0.8510 CRPS (interval unevaluable)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.8064 · pred P(0) 0.2511 vs realized 0.4059
- era (report-only): capture Δ 0.85102 vs legacy Δ None
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### TE|receiving_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 0.10824 | 0.10882 | True | 0.0002 | n/a | 2/2 |
| inc_head_bank | 0.15477 | 0.16573 | True | -0.04634 | n/a | 0/2 |
| cand_lgbm_quantile | 0.10674 | 0.10818 | True | 0.0017 | n/a | 2/2 |

- verdict: `oracle__cand_lgbm_quantile` TIES `inc_climatology` by +0.0017 CRPS (interval unevaluable)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.8949 · pred P(0) 0.9045 vs realized 0.8948
- era (report-only): capture Δ 0.0017 vs legacy Δ None
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### TE|receiving_yards

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 10.7719 | 10.77922 | True | -2.08103 | n/a | 0/2 |
| inc_head_bank | 9.40239 | 10.34946 | True | -0.71151 | n/a | 0/2 |
| cand_lgbm_quantile | 7.80904 | 7.94219 | True | 0.88183 | n/a | 2/2 |

- verdict: `oracle__cand_lgbm_quantile` TIES `inc_head_bank` by +0.8818 CRPS (interval unevaluable)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.7944 · pred P(0) 0.2491 vs realized 0.4849
- era (report-only): capture Δ 0.88183 vs legacy Δ None
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### WR|receiving_tds

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 0.12941 | 0.12966 | True | 0.00013 | n/a | 2/2 |
| inc_head_bank | 0.18297 | 0.19988 | True | -0.05343 | n/a | 0/2 |
| cand_lgbm_quantile | 0.12984 | 0.13179 | True | -0.0003 | n/a | 0/2 |

- verdict: `oracle__inc_climatology` TIES `inc_climatology` by +0.0001 CRPS (interval unevaluable)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.9842 · pred P(0) 0.8643 vs realized 0.8718
- era (report-only): capture Δ 0.00013 vs legacy Δ None
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

### WR|receiving_yards

| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | CI95 | wins |
|---|---|---|---|---|---|---|
| inc_climatology | 16.01009 | 16.0517 | True | -2.6942 | n/a | 0/2 |
| inc_head_bank | 13.95079 | 14.94717 | True | -0.6349 | n/a | 0/2 |
| cand_lgbm_quantile | 12.43506 | 12.22005 | False | 0.88084 | n/a | 2/2 |

- verdict: `oracle__cand_lgbm_quantile` TIES `inc_head_bank` by +0.8808 CRPS (interval unevaluable)
- anchors: nihilist_loses=True zero_width_loses=True max_width_loses=True (the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)
- incumbent calibration: coverage(80) 0.8025 · pred P(0) 0.2359 vs realized 0.4249
- era (report-only): capture Δ 0.88084 vs legacy Δ None
- UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W5 ceiling rule).

**Instrument positive control (MH2.1 (d), smoke):** ×1.3 regime shift on QB|passing_yards → ceiling 0.35115 → 0.94046 (instrument_sees_the_shift=True)

## Pre-registration

- decision bands: NO < 2.0% ≤ MARGINAL < 5.0% ≤ YES on ceiling_pct; `stat_ok` = CI95 excludes zero ∧ calibrated fold clause ∧ BH binding (own family AND pooled). Not stat_ok → NO.
- incumbent forms: ['inc_head_bank', 'inc_climatology'] (the BINDING one sets the bar); oracle forms: ['inc_climatology', 'inc_head_bank', 'cand_lgbm_quantile'] (block-peeking, conditional forms cross-fit K=3); anchors: ['nihilist_zero', 'zero_width', 'max_width', 'oracle__inc_climatology', 'oracle__inc_head_bank', 'oracle__cand_lgbm_quantile', 'matched_n__inc_climatology', 'matched_n__inc_head_bank', 'matched_n__cand_lgbm_quantile'].
- FDR families (own + pooled, stricter binds — MH2 (a)): yards=6 cells, tds=6 cells.
- PBO: UNDEFINED at this stage (pre-registered anchor contrast, not a searched field — the NF-W5 ceiling rule). DSR: does not arise (no arm is selected). `classify_null` is NOT invoked (the n_arms=1 fold-shortage mis-render — NF-W3 (c)).
- estimator bias: max over the per-form block-peeking oracles vs the BINDING (better) incumbent — the oracle-side max is upward-biased by selection over the declared forms and the peek favors YES, so a NO is conservative (pre-registered; the NF-W5 rule).

_Runtime: 1024.6s · seed 20260814 · matrix cache key 57c4cf96bb3c3570_