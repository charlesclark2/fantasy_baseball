# NF-W1 — the lean weekly per-game distributional fantasy projection (§0.5 bake-off)

**Generated:** 2026-08-07T03:54:58+00:00 · **folds:** 2 half-season blocks over weeks (2025H1…2025H2) · **modeled rows:** 84553 (byes excluded by pre-registration) · **label:** `v1.nflverse.stats_player_week` / `ppr`

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects — it is inverted at QB/TE on this frame (conditional median 0.0, NF-W0 §2.3).

**PIT gate (NF-W0a `assert_point_in_time` — first real caller):** 175 weeks / 84553 records checked; 0 rows in 0 weeks dropped fail-closed (the un-provable-window class).

## Per-position verdicts

### QB — **NULL (UNDEFINED)**

| arm             |   mean_crps |
|:----------------|------------:|
| lgbm_hurdle     |      2.6912 |
| lgbm_quantile   |      2.7349 |
| knn_quantile    |      2.7852 |
| enet_residual   |      3.4438 |
| foil_flat       |      3.7977 |
| foil_matchup    |      3.8084 |
| oracle_marginal |      4.7324 |
| pos_marginal    |      4.7415 |
| permuted_within |      4.7687 |
| zero_width      |      5.2071 |
| max_width       |      5.2502 |
| nihilist_zero   |      6.5468 |

- winner `lgbm_hurdle` vs best foil `foil_flat`: mean lift +1.1065 CRPS, fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · FDR pass False
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'permuted_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'oracle_marginal_beaten_by_winner': True} · coverage(80) {'winner_coverage_80': 0.8047, 'n_rows': 1372, 'binomial_se': 0.0108, 'blocking_shortfall': False}
- MAE (report-only): {'lgbm_hurdle': 3.5911, 'foil_flat': 4.7531, 'nihilist_zero': 6.5468}

### RB — **NULL (UNDEFINED)**

| arm             |   mean_crps |
|:----------------|------------:|
| lgbm_hurdle     |      2.4417 |
| lgbm_quantile   |      2.4590 |
| knn_quantile    |      2.5530 |
| enet_residual   |      2.8518 |
| foil_flat       |      2.9768 |
| foil_matchup    |      3.0357 |
| oracle_marginal |      3.8805 |
| pos_marginal    |      3.8821 |
| permuted_within |      3.9293 |
| zero_width      |      4.0984 |
| max_width       |      4.5142 |
| nihilist_zero   |      5.6416 |

- winner `lgbm_hurdle` vs best foil `foil_flat`: mean lift +0.5351 CRPS, fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · FDR pass False
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'permuted_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'oracle_marginal_beaten_by_winner': True} · coverage(80) {'winner_coverage_80': 0.8577, 'n_rows': 2144, 'binomial_se': 0.0086, 'blocking_shortfall': False}
- MAE (report-only): {'lgbm_hurdle': 3.2707, 'foil_flat': 3.7268, 'nihilist_zero': 5.6416}

### WR — **NULL (UNDEFINED)**

| arm             |   mean_crps |
|:----------------|------------:|
| lgbm_quantile   |      2.5650 |
| lgbm_hurdle     |      2.5717 |
| knn_quantile    |      2.6113 |
| enet_residual   |      2.9280 |
| foil_flat       |      3.0364 |
| foil_matchup    |      3.0702 |
| oracle_marginal |      3.5350 |
| pos_marginal    |      3.5539 |
| permuted_within |      3.5692 |
| zero_width      |      4.3357 |
| max_width       |      4.7187 |
| nihilist_zero   |      5.1960 |

- winner `lgbm_quantile` vs best foil `foil_flat`: mean lift +0.4714 CRPS, fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · FDR pass False
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'permuted_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'oracle_marginal_beaten_by_winner': True} · coverage(80) {'winner_coverage_80': 0.8279, 'n_rows': 3231, 'binomial_se': 0.007, 'blocking_shortfall': False}
- MAE (report-only): {'lgbm_quantile': 3.4793, 'foil_flat': 3.8565, 'nihilist_zero': 5.196}

### TE — **NULL (UNDEFINED)**

| arm             |   mean_crps |
|:----------------|------------:|
| lgbm_hurdle     |      1.8676 |
| lgbm_quantile   |      1.8780 |
| knn_quantile    |      1.9333 |
| enet_residual   |      2.2024 |
| foil_flat       |      2.2655 |
| foil_matchup    |      2.2924 |
| oracle_marginal |      2.6830 |
| pos_marginal    |      2.6858 |
| permuted_within |      2.6909 |
| zero_width      |      3.0544 |
| max_width       |      3.3282 |
| nihilist_zero   |      3.7087 |

- winner `lgbm_hurdle` vs best foil `foil_flat`: mean lift +0.3979 CRPS, fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · FDR pass False
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'permuted_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'oracle_marginal_beaten_by_winner': True} · coverage(80) {'winner_coverage_80': 0.8779, 'n_rows': 1941, 'binomial_se': 0.0091, 'blocking_shortfall': False}
- MAE (report-only): {'lgbm_hurdle': 2.5105, 'foil_flat': 2.8177, 'nihilist_zero': 3.7087}

## Gate detail

```json
{
  "QB": {
    "checks": {
      "beats_foil": true,
      "fold_consistency": false,
      "pbo_ok": false,
      "dsr_ok": false,
      "fdr_ok": false,
      "degenerates_lose": true,
      "permutation_beaten": true,
      "coverage_floor_ok": true
    },
    "ship": false
  },
  "RB": {
    "checks": {
      "beats_foil": true,
      "fold_consistency": false,
      "pbo_ok": false,
      "dsr_ok": false,
      "fdr_ok": false,
      "degenerates_lose": true,
      "permutation_beaten": true,
      "coverage_floor_ok": true
    },
    "ship": false
  },
  "WR": {
    "checks": {
      "beats_foil": true,
      "fold_consistency": false,
      "pbo_ok": false,
      "dsr_ok": false,
      "fdr_ok": false,
      "degenerates_lose": true,
      "permutation_beaten": true,
      "coverage_floor_ok": true
    },
    "ship": false
  },
  "TE": {
    "checks": {
      "beats_foil": true,
      "fold_consistency": false,
      "pbo_ok": false,
      "dsr_ok": false,
      "fdr_ok": false,
      "degenerates_lose": true,
      "permutation_beaten": true,
      "coverage_floor_ok": true
    },
    "ship": false
  }
}
```

## Null-state classification (failing positions)

```json
{
  "QB": {
    "state": "UNDEFINED",
    "reason": "`nf_w1_weekly_crps_QB`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "RB": {
    "state": "UNDEFINED",
    "reason": "`nf_w1_weekly_crps_RB`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "WR": {
    "state": "UNDEFINED",
    "reason": "`nf_w1_weekly_crps_WR`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "TE": {
    "state": "UNDEFINED",
    "reason": "`nf_w1_weekly_crps_TE`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  }
}
```

## With-bye sensitivity (analytic)

A bye row's honest projection is the identity point-mass at 0 (CRPS 0 for every arm that emits it, including the nihilist). Including byes therefore multiplies every arm's mean CRPS by the same factor n/(n+n_bye) and CANNOT reorder arms — which is why the scoring population excludes them.
