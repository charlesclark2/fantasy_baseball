# NF-W2b — the injury family re-registered against a marginal-rate-carrying foil (§0.5 bake-off)

**Generated:** 2026-08-09T03:39:45+00:00 · **gated folds:** 2 half-season blocks (2024H1…2024H2; family ACTIVE on all) · **shadow folds:** 2025H2 (2025 — both families structurally unmeasured, never gated) · **modeled rows:** 84553 · **label:** `v1.nflverse.stats_player_week` / `ppr`

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects. The matched foil is `base_rate` (NF-W1 champion + pre-registered week×position listing-rate features): each arm is the identical bundle plus the PLAYER-level `injury_report` family, so the paired delta vs `base_rate` IS the pure player-level attribution (NF-D10). `base_noRate` (the production incumbent) anchors the deployment bar.

**PIT gate (per-game as-of instants; window + injury + rate records):** 532 game-groups / 173813 records (14058 injury, 75202 rate) checked; 0 rows in 0 groups dropped fail-closed.

## Per-position verdicts (gated folds)

### QB — **NULL (UNDEFINED)**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__inj  |      2.0628 |
| oracle_avail__base |      2.0668 |
| inj_both           |      2.4981 |
| inj_zero_leg       |      2.5039 |
| inj_override       |      2.5360 |
| base_rate          |      2.6053 |
| inj_permuted       |      2.6082 |
| base_noRate        |      2.6353 |
| pos_marginal       |      4.8288 |
| nihilist_zero      |      6.7498 |

- winner `inj_both` vs rate foil `base_rate`: mean lift +0.1072 CRPS, fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · FDR pass False
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.1072, 'fold_wins': 2}, 'inj_zero_leg': {'mean': 0.1014, 'fold_wins': 2}, 'inj_override': {'mean': 0.0693, 'fold_wins': 2}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.1371, 'winner_vs_production_fold_wins': 2, 'marginal_channel_mean': 0.03, 'marginal_channel_p_one_sided': None, 'player_content_mean': 0.1072}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': -0.0029, 'permuted_lift_p_one_sided': None, 'winner_vs_permuted_mean': 0.11} · coverage(80) {'winner_coverage_80': 0.8259, 'n_rows': 1361, 'binomial_se': 0.0108, 'blocking_shortfall': False}
- MAE (report-only): {'inj_both': 3.3053, 'base_rate': 3.4022, 'base_noRate': 3.4479, 'nihilist_zero': 6.7498}

### RB — **NULL (UNDEFINED)**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__inj  |      2.1735 |
| oracle_avail__base |      2.1755 |
| inj_both           |      2.3935 |
| inj_zero_leg       |      2.3961 |
| inj_override       |      2.4324 |
| inj_permuted       |      2.5434 |
| base_rate          |      2.5445 |
| base_noRate        |      2.5502 |
| pos_marginal       |      3.8978 |
| nihilist_zero      |      5.7302 |

- winner `inj_both` vs rate foil `base_rate`: mean lift +0.1510 CRPS, fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · FDR pass False
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.151, 'fold_wins': 2}, 'inj_zero_leg': {'mean': 0.1483, 'fold_wins': 2}, 'inj_override': {'mean': 0.112, 'fold_wins': 2}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.1568, 'winner_vs_production_fold_wins': 2, 'marginal_channel_mean': 0.0058, 'marginal_channel_p_one_sided': None, 'player_content_mean': 0.151}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': False, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': 0.0011, 'permuted_lift_p_one_sided': None, 'winner_vs_permuted_mean': 0.1499} · coverage(80) {'winner_coverage_80': 0.8468, 'n_rows': 2102, 'binomial_se': 0.0087, 'blocking_shortfall': False}
- MAE (report-only): {'inj_both': 3.2372, 'base_rate': 3.4295, 'base_noRate': 3.4391, 'nihilist_zero': 5.7302}

### WR — **NULL (UNDEFINED)**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__base |      2.1439 |
| oracle_avail__inj  |      2.1485 |
| inj_zero_leg       |      2.5933 |
| inj_both           |      2.5971 |
| inj_override       |      2.6158 |
| base_rate          |      2.7154 |
| base_noRate        |      2.7162 |
| inj_permuted       |      2.7228 |
| pos_marginal       |      3.8567 |
| nihilist_zero      |      5.7263 |

- winner `inj_zero_leg` vs rate foil `base_rate`: mean lift +0.1221 CRPS, fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · FDR pass False
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.1183, 'fold_wins': 2}, 'inj_zero_leg': {'mean': 0.1221, 'fold_wins': 2}, 'inj_override': {'mean': 0.0996, 'fold_wins': 2}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.1229, 'winner_vs_production_fold_wins': 2, 'marginal_channel_mean': 0.0008, 'marginal_channel_p_one_sided': None, 'player_content_mean': 0.1221}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': -0.0074, 'permuted_lift_p_one_sided': None, 'winner_vs_permuted_mean': 0.1295} · coverage(80) {'winner_coverage_80': 0.8502, 'n_rows': 3185, 'binomial_se': 0.0071, 'blocking_shortfall': False}
- MAE (report-only): {'inj_zero_leg': 3.5138, 'base_rate': 3.6737, 'base_noRate': 3.6657, 'nihilist_zero': 5.7263}

### TE — **NULL (UNDEFINED) — consistency check; the NF-W2 TE ship stands regardless**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__inj  |      1.3248 |
| oracle_avail__base |      1.3260 |
| inj_both           |      1.7269 |
| inj_zero_leg       |      1.7284 |
| inj_override       |      1.7490 |
| base_noRate        |      1.8009 |
| inj_permuted       |      1.8013 |
| base_rate          |      1.8025 |
| pos_marginal       |      2.5662 |
| nihilist_zero      |      3.4613 |

- winner `inj_both` vs rate foil `base_rate`: mean lift +0.0756 CRPS, fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · FDR pass False
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.0755, 'fold_wins': 2}, 'inj_zero_leg': {'mean': 0.074, 'fold_wins': 2}, 'inj_override': {'mean': 0.0535, 'fold_wins': 2}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.074, 'winner_vs_production_fold_wins': 2, 'marginal_channel_mean': -0.0015, 'marginal_channel_p_one_sided': None, 'player_content_mean': 0.0755}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': False, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': 0.0012, 'permuted_lift_p_one_sided': None, 'winner_vs_permuted_mean': 0.0743} · coverage(80) {'winner_coverage_80': 0.8885, 'n_rows': 1929, 'binomial_se': 0.0091, 'blocking_shortfall': False}
- MAE (report-only): {'inj_both': 2.3356, 'base_rate': 2.4275, 'base_noRate': 2.4355, 'nihilist_zero': 3.4613}

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
      "vs": "base_rate",
      "mean_delta": -0.0277,
      "max_abs_delta": 0.0277
    },
    "inj_zero_leg": {
      "vs": "base_rate",
      "mean_delta": -0.0298,
      "max_abs_delta": 0.0298
    },
    "inj_override": {
      "vs": "base_rate",
      "mean_delta": 0.0,
      "max_abs_delta": 0.0
    },
    "base_rate": {
      "vs": "base_noRate",
      "mean_delta": -0.0145,
      "max_abs_delta": 0.0145
    }
  },
  "RB": {
    "inj_both": {
      "vs": "base_rate",
      "mean_delta": -0.0036,
      "max_abs_delta": 0.0036
    },
    "inj_zero_leg": {
      "vs": "base_rate",
      "mean_delta": -0.0069,
      "max_abs_delta": 0.0069
    },
    "inj_override": {
      "vs": "base_rate",
      "mean_delta": 0.0,
      "max_abs_delta": 0.0
    },
    "base_rate": {
      "vs": "base_noRate",
      "mean_delta": -0.0156,
      "max_abs_delta": 0.0156
    }
  },
  "WR": {
    "inj_both": {
      "vs": "base_rate",
      "mean_delta": -0.0058,
      "max_abs_delta": 0.0058
    },
    "inj_zero_leg": {
      "vs": "base_rate",
      "mean_delta": -0.0013,
      "max_abs_delta": 0.0013
    },
    "inj_override": {
      "vs": "base_rate",
      "mean_delta": 0.0,
      "max_abs_delta": 0.0
    },
    "base_rate": {
      "vs": "base_noRate",
      "mean_delta": -0.0081,
      "max_abs_delta": 0.0081
    }
  },
  "TE": {
    "inj_both": {
      "vs": "base_rate",
      "mean_delta": -0.0125,
      "max_abs_delta": 0.0125
    },
    "inj_zero_leg": {
      "vs": "base_rate",
      "mean_delta": -0.0085,
      "max_abs_delta": 0.0085
    },
    "inj_override": {
      "vs": "base_rate",
      "mean_delta": 0.0,
      "max_abs_delta": 0.0
    },
    "base_rate": {
      "vs": "base_noRate",
      "mean_delta": -0.0054,
      "max_abs_delta": 0.0054
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
      "beats_production": true,
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
  },
  "RB": {
    "checks": {
      "beats_foil": true,
      "beats_production": true,
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
      "beats_production": true,
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
  },
  "TE": {
    "checks": {
      "beats_foil": true,
      "beats_production": true,
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
  }
}
```

## Null-state classification (failing positions)

```json
{
  "QB": {
    "state": "UNDEFINED",
    "reason": "`nf_w2b_injury_crps_QB`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "RB": {
    "state": "UNDEFINED",
    "reason": "`nf_w2b_injury_crps_RB`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "WR": {
    "state": "UNDEFINED",
    "reason": "`nf_w2b_injury_crps_WR`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "TE": {
    "state": "UNDEFINED",
    "reason": "`nf_w2b_injury_crps_TE`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  }
}
```
