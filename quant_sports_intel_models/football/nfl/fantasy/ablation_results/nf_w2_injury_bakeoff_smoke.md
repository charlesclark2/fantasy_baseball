# NF-W2 — the availability channel: current-week injury-report state (§0.5 bake-off)

**Generated:** 2026-08-09T01:45:05+00:00 · **gated folds:** 2 half-season blocks (2024H1…2024H2; family ACTIVE on all) · **shadow folds:** 2025H2 (2025 — family structurally unmeasured, never gated) · **modeled rows:** 84553 · **label:** `v1.nflverse.stats_player_week` / `ppr`

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects. The incumbent NF-W1 champion (`base_hurdle`) is simultaneously the MATCHED FOIL (NF-D10): each arm is the identical bundle plus the `injury_report` family, so the paired delta IS the attribution.

**PIT gate (per-game as-of instants; injury source records carry `date_modified`):** 532 game-groups / 98611 records (14058 injury) checked; 0 rows in 0 groups dropped fail-closed.

## Per-position verdicts (gated folds)

### QB — **NULL (UNDEFINED)**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__inj  |      2.0753 |
| oracle_avail__base |      2.0772 |
| inj_both           |      2.5270 |
| inj_zero_leg       |      2.5291 |
| inj_override       |      2.5613 |
| inj_permuted       |      2.6213 |
| base_hurdle        |      2.6353 |
| pos_marginal       |      4.8288 |
| nihilist_zero      |      6.7498 |

- winner `inj_both` vs incumbent `base_hurdle`: mean lift +0.1083 CRPS, fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · FDR pass False
- matched-pair deltas vs base (the attribution): {'inj_both': {'mean': 0.1083, 'fold_wins': 2}, 'inj_zero_leg': {'mean': 0.1062, 'fold_wins': 2}, 'inj_override': {'mean': 0.0739, 'fold_wins': 2}}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'inj_permuted_does_not_beat_base': False, 'no_arm_beats_own_oracle': True, 'base_respects_oracle': True} · coverage(80) {'winner_coverage_80': 0.8222, 'n_rows': 1361, 'binomial_se': 0.0108, 'blocking_shortfall': False}
- MAE (report-only): {'inj_both': 3.3375, 'base_hurdle': 3.4479, 'nihilist_zero': 6.7498}

### RB — **NULL (UNDEFINED)**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__inj  |      2.1788 |
| oracle_avail__base |      2.1791 |
| inj_both           |      2.3992 |
| inj_zero_leg       |      2.4010 |
| inj_override       |      2.4360 |
| inj_permuted       |      2.5499 |
| base_hurdle        |      2.5502 |
| pos_marginal       |      3.8978 |
| nihilist_zero      |      5.7302 |

- winner `inj_both` vs incumbent `base_hurdle`: mean lift +0.1511 CRPS, fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · FDR pass False
- matched-pair deltas vs base (the attribution): {'inj_both': {'mean': 0.1511, 'fold_wins': 2}, 'inj_zero_leg': {'mean': 0.1492, 'fold_wins': 2}, 'inj_override': {'mean': 0.1142, 'fold_wins': 2}}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'inj_permuted_does_not_beat_base': False, 'no_arm_beats_own_oracle': True, 'base_respects_oracle': True} · coverage(80) {'winner_coverage_80': 0.8368, 'n_rows': 2102, 'binomial_se': 0.0087, 'blocking_shortfall': False}
- MAE (report-only): {'inj_both': 3.2399, 'base_hurdle': 3.4391, 'nihilist_zero': 5.7302}

### WR — **NULL (UNDEFINED)**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__inj  |      2.1415 |
| oracle_avail__base |      2.1416 |
| inj_zero_leg       |      2.5870 |
| inj_both           |      2.5875 |
| inj_override       |      2.6187 |
| inj_permuted       |      2.7153 |
| base_hurdle        |      2.7162 |
| pos_marginal       |      3.8567 |
| nihilist_zero      |      5.7263 |

- winner `inj_zero_leg` vs incumbent `base_hurdle`: mean lift +0.1291 CRPS, fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · FDR pass False
- matched-pair deltas vs base (the attribution): {'inj_both': {'mean': 0.1287, 'fold_wins': 2}, 'inj_zero_leg': {'mean': 0.1292, 'fold_wins': 2}, 'inj_override': {'mean': 0.0974, 'fold_wins': 2}}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'inj_permuted_does_not_beat_base': False, 'no_arm_beats_own_oracle': True, 'base_respects_oracle': True} · coverage(80) {'winner_coverage_80': 0.8512, 'n_rows': 3185, 'binomial_se': 0.0071, 'blocking_shortfall': False}
- MAE (report-only): {'inj_zero_leg': 3.4862, 'base_hurdle': 3.6657, 'nihilist_zero': 5.7263}

### TE — **NULL (UNDEFINED)**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__base |      1.3244 |
| oracle_avail__inj  |      1.3264 |
| inj_zero_leg       |      1.7246 |
| inj_both           |      1.7257 |
| inj_override       |      1.7479 |
| base_hurdle        |      1.8009 |
| inj_permuted       |      1.8037 |
| pos_marginal       |      2.5662 |
| nihilist_zero      |      3.4613 |

- winner `inj_zero_leg` vs incumbent `base_hurdle`: mean lift +0.0764 CRPS, fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · FDR pass False
- matched-pair deltas vs base (the attribution): {'inj_both': {'mean': 0.0752, 'fold_wins': 2}, 'inj_zero_leg': {'mean': 0.0764, 'fold_wins': 2}, 'inj_override': {'mean': 0.053, 'fold_wins': 2}}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'inj_permuted_does_not_beat_base': True, 'no_arm_beats_own_oracle': True, 'base_respects_oracle': True} · coverage(80) {'winner_coverage_80': 0.8906, 'n_rows': 1929, 'binomial_se': 0.0091, 'blocking_shortfall': False}
- MAE (report-only): {'inj_zero_leg': 2.3355, 'base_hurdle': 2.4355, 'nihilist_zero': 3.4613}

## Per-fold family activity (the NF-D20 discipline)

| fold   |   n_test |   listed_share |   out_doubtful_share |   observed_share | override                                                          |
|:-------|---------:|---------------:|---------------------:|-----------------:|:------------------------------------------------------------------|
| 2024H1 |     4365 |         0.1805 |               0.0323 |                1 | {'p_emp': 0.9984, 'n_train_cell': 2526, 'n_test_overridden': 141} |
| 2024H2 |     4212 |         0.194  |               0.0332 |                1 | {'p_emp': 0.9985, 'n_train_cell': 2676, 'n_test_overridden': 140} |

## Shadow 2025 (mechanism cannot act — registered expectation: near-tie)

```json
{
  "QB": {
    "inj_both": {
      "mean_delta_vs_base": -0.0392,
      "max_abs_delta": 0.0392
    },
    "inj_zero_leg": {
      "mean_delta_vs_base": -0.0381,
      "max_abs_delta": 0.0381
    },
    "inj_override": {
      "mean_delta_vs_base": 0.0,
      "max_abs_delta": 0.0
    }
  },
  "RB": {
    "inj_both": {
      "mean_delta_vs_base": -0.0135,
      "max_abs_delta": 0.0135
    },
    "inj_zero_leg": {
      "mean_delta_vs_base": -0.0154,
      "max_abs_delta": 0.0154
    },
    "inj_override": {
      "mean_delta_vs_base": 0.0,
      "max_abs_delta": 0.0
    }
  },
  "WR": {
    "inj_both": {
      "mean_delta_vs_base": -0.0079,
      "max_abs_delta": 0.0079
    },
    "inj_zero_leg": {
      "mean_delta_vs_base": -0.01,
      "max_abs_delta": 0.01
    },
    "inj_override": {
      "mean_delta_vs_base": 0.0,
      "max_abs_delta": 0.0
    }
  },
  "TE": {
    "inj_both": {
      "mean_delta_vs_base": -0.0148,
      "max_abs_delta": 0.0148
    },
    "inj_zero_leg": {
      "mean_delta_vs_base": -0.0137,
      "max_abs_delta": 0.0137
    },
    "inj_override": {
      "mean_delta_vs_base": 0.0,
      "max_abs_delta": 0.0
    }
  },
  "activity": [
    {
      "fold": "2025H2",
      "n_test": 4380,
      "listed_share": null,
      "out_doubtful_share": 0.0,
      "observed_share": 0.0
    }
  ]
}
```

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
      "permutation_behaves": false,
      "oracle_floors_respected": true,
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
      "permutation_behaves": false,
      "oracle_floors_respected": true,
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
      "permutation_behaves": false,
      "oracle_floors_respected": true,
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
      "permutation_behaves": true,
      "oracle_floors_respected": true,
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
    "reason": "`nf_w2_injury_crps_QB`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "RB": {
    "state": "UNDEFINED",
    "reason": "`nf_w2_injury_crps_RB`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "WR": {
    "state": "UNDEFINED",
    "reason": "`nf_w2_injury_crps_WR`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "TE": {
    "state": "UNDEFINED",
    "reason": "`nf_w2_injury_crps_TE`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  }
}
```
