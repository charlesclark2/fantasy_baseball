# NF-W2d — the injury-availability family re-gated with 2025 in the fold set (§0.5 bake-off)

**Generated:** 2026-08-09T22:51:30+00:00 · **gated folds:** 14 (2019H1…2025H2) · **modeled rows:** 84553 · **label:** `v1.nflverse.stats_player_week` / `ppr`

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim, **deploy-held**: this story validates a TRAINING ERA and promotes, publishes and retrains nothing. Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects (inverted at QB/TE on this frame). ONLY the fold set changed vs NF-W2b — 2025H1/2025H2 leave SHADOW and join the gated set; the reproduction control below measures that claim.

## Reproduction control — **PASS**

the 12 NF-W2b folds reproduce exactly ⇒ the 2025 plumbing did not perturb the inherited harness, so every difference below is an ERA effect (480 legacy (fold, arm, position) cells compared at tolerance 1e-09; max |Δ| 0.0).

## 2025 coverage — the registered design quantities, recomputed at run time

- primary bound **7.0 d** (one NFL game week, registered on sport structure, not tuned): coverage **0.9484** of 8688 modeled 2025 rows · diagnostics-only {'3d': 0.9375, 'unbounded': 1.0}
- by position {'QB': 0.9497, 'RB': 0.9464, 'TE': 0.9485, 'WR': 0.9492} · fully-uncovered weeks **[12]** · capture age (days) {'median': 0.606, 'p75': 1.483, 'p90': 1.74}
- listed share over covered rows **0.163** (the NF-D20 activity count — compare the 2016–2024 fold activity table below)
- ⚠️ per-COLUMN absence over listed 2025 rows (MH2.1 (c) — never a pooled mean): {'injury_report__practice_dnp': 0.3433, 'injury_report__practice_limited': 0.3433, 'injury_report__status_out': 0.0}

|   week |   n |   coverage |   median_capture_age_days |
|-------:|----:|-----------:|--------------------------:|
|      1 | 509 |          1 |                     0.832 |
|      2 | 511 |          1 |                     0.096 |
|      3 | 512 |          1 |                     1.01  |
|      4 | 511 |          1 |                     1.483 |
|      5 | 450 |          1 |                     0.606 |
|      6 | 475 |          1 |                     1.047 |
|      7 | 474 |          1 |                     0.036 |
|      8 | 416 |          1 |                     0.321 |
|      9 | 450 |          1 |                     2.19  |
|     10 | 445 |          1 |                     0.481 |
|     11 | 477 |          1 |                     1.64  |
|     12 | 448 |          0 |                    10.899 |
|     13 | 509 |          1 |                     1.617 |
|     14 | 446 |          1 |                     0.27  |
|     15 | 513 |          1 |                     0.27  |
|     16 | 510 |          1 |                     1.74  |
|     17 | 515 |          1 |                     0.051 |
|     18 | 517 |          1 |                     0.159 |

**Revision-clause activity (NF-D20):** {'store_rows': 2187, 'store_subjects': 2187, 'store_subject_max_captures': 1, 'store_subjects_with_multiple_captures': 0, 'player_weeks_with_multiple_source_captures': 664, 'clause_state': 'INACTIVE — no store subject holds more than one capture, so clause 7 has nothing it could fire on; this is not a pass'}

## Per-position verdicts (14 gated folds)

### QB — **SHIP**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__base |      2.0796 |
| oracle_avail__inj  |      2.0815 |
| inj_zero_leg       |      2.4908 |
| inj_both           |      2.4911 |
| inj_override       |      2.5073 |
| base_rate          |      2.5915 |
| inj_permuted       |      2.5989 |
| base_noRate        |      2.6079 |
| pos_marginal       |      4.8063 |
| nihilist_zero      |      6.6897 |

- winner `inj_zero_leg` vs rate foil `base_rate`: mean lift +0.1007 CRPS, fold wins 13/14 (clause requires 10) · PBO 0.1559 · DSR 0.9971 · p 0.0 · FDR pass True
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.1004, 'fold_wins': 14}, 'inj_zero_leg': {'mean': 0.1007, 'fold_wins': 13}, 'inj_override': {'mean': 0.0842, 'fold_wins': 14}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.1171, 'winner_vs_production_fold_wins': 13, 'marginal_channel_mean': 0.0164, 'marginal_channel_p_one_sided': 0.0037, 'player_content_mean': 0.1007}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': -0.0074, 'permuted_lift_p_one_sided': 0.9372, 'winner_vs_permuted_mean': 0.1081} · coverage(80) {'winner_coverage_80': 0.8192, 'n_rows': 9483, 'binomial_se': 0.0041, 'blocking_shortfall': False}
- MAE (report-only, never selects): {'inj_zero_leg': 3.2934, 'base_rate': 3.4124, 'base_noRate': 3.43, 'nihilist_zero': 6.6897}
- ERA DELTA (diagnostic): {'arm': 'inj_zero_leg', 'full_14': {'n_folds': 14, 'mean_lift_vs_foil': 0.1007, 'fold_wins': 13, 'mean_lift_vs_production': 0.1171}, 'legacy_12': {'n_folds': 12, 'mean_lift_vs_foil': 0.098, 'fold_wins': 11, 'mean_lift_vs_production': 0.1167}, 'new_2025': {'n_folds': 2, 'mean_lift_vs_foil': 0.1173, 'fold_wins': 2, 'mean_lift_vs_production': 0.1195}}
- ERA RANK (post-hoc diagnostic): {'arm': 'inj_zero_leg', 'new_lifts': [0.2036, 0.0311], 'legacy_min': -0.0055, 'legacy_max': 0.1799, 'legacy_median': 0.1132, 'below_legacy_pairs': 10, 'of_pairs': 24, 'exact_one_sided_p': 0.6703, 'relative_lift_legacy_pct': 3.807, 'relative_lift_new_pct': 4.347}

### RB — **SHIP**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__inj  |      2.1854 |
| oracle_avail__base |      2.1860 |
| inj_both           |      2.4683 |
| inj_zero_leg       |      2.4687 |
| inj_override       |      2.4920 |
| base_rate          |      2.5898 |
| inj_permuted       |      2.5931 |
| base_noRate        |      2.5953 |
| pos_marginal       |      3.8426 |
| nihilist_zero      |      5.5950 |

- winner `inj_both` vs rate foil `base_rate`: mean lift +0.1215 CRPS, fold wins 14/14 (clause requires 10) · PBO 0.0 · DSR 1.0 · p 0.0 · FDR pass True
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.1215, 'fold_wins': 14}, 'inj_zero_leg': {'mean': 0.1211, 'fold_wins': 14}, 'inj_override': {'mean': 0.0978, 'fold_wins': 14}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.127, 'winner_vs_production_fold_wins': 14, 'marginal_channel_mean': 0.0055, 'marginal_channel_p_one_sided': 0.0359, 'player_content_mean': 0.1215}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': -0.0033, 'permuted_lift_p_one_sided': 0.8791, 'winner_vs_permuted_mean': 0.1248} · coverage(80) {'winner_coverage_80': 0.8367, 'n_rows': 15246, 'binomial_se': 0.0032, 'blocking_shortfall': False}
- MAE (report-only, never selects): {'inj_both': 3.3172, 'base_rate': 3.4738, 'base_noRate': 3.4827, 'nihilist_zero': 5.595}
- ERA DELTA (diagnostic): {'arm': 'inj_both', 'full_14': {'n_folds': 14, 'mean_lift_vs_foil': 0.1215, 'fold_wins': 14, 'mean_lift_vs_production': 0.127}, 'legacy_12': {'n_folds': 12, 'mean_lift_vs_foil': 0.1347, 'fold_wins': 12, 'mean_lift_vs_production': 0.1427}, 'new_2025': {'n_folds': 2, 'mean_lift_vs_foil': 0.0422, 'fold_wins': 2, 'mean_lift_vs_production': 0.0329}}
- ERA RANK (post-hoc diagnostic): {'arm': 'inj_both', 'new_lifts': [0.0421, 0.0424], 'legacy_min': 0.076, 'legacy_max': 0.1913, 'legacy_median': 0.1286, 'below_legacy_pairs': 24, 'of_pairs': 24, 'exact_one_sided_p': 0.011, 'relative_lift_legacy_pct': 5.156, 'relative_lift_new_pct': 1.723}

### WR — **SHIP**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__base |      2.1647 |
| oracle_avail__inj  |      2.1647 |
| inj_both           |      2.6471 |
| inj_zero_leg       |      2.6473 |
| inj_override       |      2.6770 |
| base_rate          |      2.7669 |
| inj_permuted       |      2.7689 |
| base_noRate        |      2.7697 |
| pos_marginal       |      3.8400 |
| nihilist_zero      |      5.7197 |

- winner `inj_both` vs rate foil `base_rate`: mean lift +0.1198 CRPS, fold wins 14/14 (clause requires 10) · PBO 0.0 · DSR 1.0 · p 0.0 · FDR pass True
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.1198, 'fold_wins': 14}, 'inj_zero_leg': {'mean': 0.1195, 'fold_wins': 14}, 'inj_override': {'mean': 0.0899, 'fold_wins': 14}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.1226, 'winner_vs_production_fold_wins': 14, 'marginal_channel_mean': 0.0029, 'marginal_channel_p_one_sided': 0.1422, 'player_content_mean': 0.1198}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': -0.002, 'permuted_lift_p_one_sided': 0.8924, 'winner_vs_permuted_mean': 0.1218} · coverage(80) {'winner_coverage_80': 0.8397, 'n_rows': 22104, 'binomial_se': 0.0027, 'blocking_shortfall': False}
- MAE (report-only, never selects): {'inj_both': 3.5845, 'base_rate': 3.7395, 'base_noRate': 3.7444, 'nihilist_zero': 5.7197}
- ERA DELTA (diagnostic): {'arm': 'inj_both', 'full_14': {'n_folds': 14, 'mean_lift_vs_foil': 0.1198, 'fold_wins': 14, 'mean_lift_vs_production': 0.1226}, 'legacy_12': {'n_folds': 12, 'mean_lift_vs_foil': 0.1257, 'fold_wins': 12, 'mean_lift_vs_production': 0.1306}, 'new_2025': {'n_folds': 2, 'mean_lift_vs_foil': 0.084, 'fold_wins': 2, 'mean_lift_vs_production': 0.0749}}
- ERA RANK (post-hoc diagnostic): {'arm': 'inj_both', 'new_lifts': [0.1149, 0.0531], 'legacy_min': 0.0807, 'legacy_max': 0.1858, 'legacy_median': 0.1231, 'below_legacy_pairs': 20, 'of_pairs': 24, 'exact_one_sided_p': 0.0989, 'relative_lift_legacy_pct': 4.492, 'relative_lift_new_pct': 3.264}

### TE — **SHIP**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__base |      1.3693 |
| oracle_avail__inj  |      1.3718 |
| inj_zero_leg       |      1.8002 |
| inj_both           |      1.8016 |
| inj_override       |      1.8140 |
| base_rate          |      1.8567 |
| base_noRate        |      1.8584 |
| inj_permuted       |      1.8600 |
| pos_marginal       |      2.5985 |
| nihilist_zero      |      3.5586 |

- winner `inj_zero_leg` vs rate foil `base_rate`: mean lift +0.0564 CRPS, fold wins 14/14 (clause requires 10) · PBO 0.0 · DSR 1.0 · p 0.0 · FDR pass True
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.0551, 'fold_wins': 14}, 'inj_zero_leg': {'mean': 0.0565, 'fold_wins': 14}, 'inj_override': {'mean': 0.0427, 'fold_wins': 14}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.0582, 'winner_vs_production_fold_wins': 14, 'marginal_channel_mean': 0.0018, 'marginal_channel_p_one_sided': 0.1731, 'player_content_mean': 0.0565}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': -0.0033, 'permuted_lift_p_one_sided': 0.937, 'winner_vs_permuted_mean': 0.0598} · coverage(80) {'winner_coverage_80': 0.8805, 'n_rows': 12947, 'binomial_se': 0.0035, 'blocking_shortfall': False}
- MAE (report-only, never selects): {'inj_zero_leg': 2.4228, 'base_rate': 2.4984, 'base_noRate': 2.4963, 'nihilist_zero': 3.5586}
- ERA DELTA (diagnostic): {'arm': 'inj_zero_leg', 'full_14': {'n_folds': 14, 'mean_lift_vs_foil': 0.0565, 'fold_wins': 14, 'mean_lift_vs_production': 0.0582}, 'legacy_12': {'n_folds': 12, 'mean_lift_vs_foil': 0.0589, 'fold_wins': 12, 'mean_lift_vs_production': 0.0606}, 'new_2025': {'n_folds': 2, 'mean_lift_vs_foil': 0.042, 'fold_wins': 2, 'mean_lift_vs_production': 0.0439}}
- ERA RANK (post-hoc diagnostic): {'arm': 'inj_zero_leg', 'new_lifts': [0.0491, 0.035], 'legacy_min': 0.0319, 'legacy_max': 0.0939, 'legacy_median': 0.0554, 'below_legacy_pairs': 19, 'of_pairs': 24, 'exact_one_sided_p': 0.1319, 'relative_lift_legacy_pct': 3.171, 'relative_lift_new_pct': 2.26}

## Per-fold family activity (the NF-D20 discipline)

| fold   |   n_test |   listed_share |   out_doubtful_share |   observed_share | override                                                          |
|:-------|---------:|---------------:|---------------------:|-----------------:|:------------------------------------------------------------------|
| 2019H1 |     4291 |         0.1906 |               0.0506 |           1      | {'p_emp': 0.999, 'n_train_cell': 953, 'n_test_overridden': 217}   |
| 2019H2 |     3833 |         0.1962 |               0.042  |           1      | {'p_emp': 0.9983, 'n_train_cell': 1168, 'n_test_overridden': 161} |
| 2020H1 |     4367 |         0.1802 |               0.036  |           1      | {'p_emp': 0.9985, 'n_train_cell': 1338, 'n_test_overridden': 157} |
| 2020H2 |     4038 |         0.2117 |               0.0332 |           1      | {'p_emp': 0.998, 'n_train_cell': 1483, 'n_test_overridden': 134}  |
| 2021H1 |     4337 |         0.1729 |               0.0327 |           1      | {'p_emp': 0.9981, 'n_train_cell': 1617, 'n_test_overridden': 142} |
| 2021H2 |     4362 |         0.1992 |               0.0353 |           1      | {'p_emp': 0.9983, 'n_train_cell': 1764, 'n_test_overridden': 154} |
| 2022H1 |     4387 |         0.1798 |               0.0429 |           1      | {'p_emp': 0.9984, 'n_train_cell': 1928, 'n_test_overridden': 188} |
| 2022H2 |     4299 |         0.1849 |               0.0354 |           1      | {'p_emp': 0.9986, 'n_train_cell': 2099, 'n_test_overridden': 152} |
| 2023H1 |     4264 |         0.1524 |               0.0237 |           1      | {'p_emp': 0.9987, 'n_train_cell': 2264, 'n_test_overridden': 101} |
| 2023H2 |     4337 |         0.2156 |               0.0399 |           1      | {'p_emp': 0.9987, 'n_train_cell': 2367, 'n_test_overridden': 173} |
| 2024H1 |     4365 |         0.1805 |               0.0323 |           1      | {'p_emp': 0.9984, 'n_train_cell': 2526, 'n_test_overridden': 141} |
| 2024H2 |     4212 |         0.194  |               0.0332 |           1      | {'p_emp': 0.9985, 'n_train_cell': 2676, 'n_test_overridden': 140} |
| 2025H1 |     4308 |         0.1585 |               0.0416 |           1      | {'p_emp': 0.9986, 'n_train_cell': 2807, 'n_test_overridden': 179} |
| 2025H2 |     4380 |         0.1679 |               0.0226 |           0.8977 | {'p_emp': 0.9967, 'n_train_cell': 3008, 'n_test_overridden': 99}  |

## Covered-subset diagnostic (where the mechanism can act) — never gated

| fold   |   n_test |   observed_rows |   observed_share |   listed_share_over_observed | weeks_fully_uncovered   |
|:-------|---------:|----------------:|-----------------:|-----------------------------:|:------------------------|
| 2019H1 |     4291 |            4291 |           1      |                       0.1906 | []                      |
| 2019H2 |     3833 |            3833 |           1      |                       0.1962 | []                      |
| 2020H1 |     4367 |            4367 |           1      |                       0.1802 | []                      |
| 2020H2 |     4038 |            4038 |           1      |                       0.2117 | []                      |
| 2021H1 |     4337 |            4337 |           1      |                       0.1729 | []                      |
| 2021H2 |     4362 |            4362 |           1      |                       0.1992 | []                      |
| 2022H1 |     4387 |            4387 |           1      |                       0.1798 | []                      |
| 2022H2 |     4299 |            4299 |           1      |                       0.1849 | []                      |
| 2023H1 |     4264 |            4264 |           1      |                       0.1524 | []                      |
| 2023H2 |     4337 |            4337 |           1      |                       0.2156 | []                      |
| 2024H1 |     4365 |            4365 |           1      |                       0.1805 | []                      |
| 2024H2 |     4212 |            4212 |           1      |                       0.194  | []                      |
| 2025H1 |     4308 |            4308 |           1      |                       0.1585 | []                      |
| 2025H2 |     4380 |            3932 |           0.8977 |                       0.1679 | [12]                    |

## Era attenuation — is it the ARM or the POSITION? (post-hoc, never gated)

**the era ratio is essentially ARM-INVARIANT (max |inj_both − inj_zero_leg| = 0.062) ⇒ any attenuation is a property of the POSITION, not of how much of the family an arm consumes — which REFUTES the practice-line-absence mechanism as the explanation for the position pattern**

| position   | arm          |   legacy_lift |   new_lift |   era_ratio |
|:-----------|:-------------|--------------:|-----------:|------------:|
| QB         | inj_both     |        0.0968 |     0.122  |       1.26  |
| QB         | inj_zero_leg |        0.098  |     0.1173 |       1.198 |
| QB         | inj_override |        0.0811 |     0.1029 |       1.269 |
| RB         | inj_both     |        0.1347 |     0.0422 |       0.313 |
| RB         | inj_zero_leg |        0.1343 |     0.0419 |       0.312 |
| RB         | inj_override |        0.1074 |     0.04   |       0.373 |
| WR         | inj_both     |        0.1257 |     0.084  |       0.668 |
| WR         | inj_zero_leg |        0.1255 |     0.0838 |       0.667 |
| WR         | inj_override |        0.0938 |     0.0664 |       0.708 |
| TE         | inj_both     |        0.0573 |     0.0417 |       0.727 |
| TE         | inj_zero_leg |        0.0589 |     0.042  |       0.714 |
| TE         | inj_override |        0.0457 |     0.0247 |       0.54  |

BH q=0.10 cutoffs over the four positions: {'RB': 0.025, 'WR': 0.05, 'TE': 0.075, 'QB': 0.1} · survives: {'RB': True, 'WR': False, 'TE': False, 'QB': False}

## Deflation convention

The fantasy vertical calls `M14.deflated_sharpe` DIRECTLY — the DSR-CONV degenerate-exclusion change reached only the two MLB legs (`e7_9`, `mh2_5`). NF-W2d uses that whole-field call unchanged over the declared 3-arm family, byte-identically the convention NF-W2 and NF-W2b used. No field trim, no convention switch. In this harness anchors and degenerates were never in `trial_srs`, so there is no degenerate-inflated V for DSR-CONV to remove and the question does not arise.

## Gate detail

```json
{
  "QB": {
    "checks": {
      "beats_foil": true,
      "beats_production": true,
      "fold_consistency": true,
      "pbo_ok": true,
      "dsr_ok": true,
      "fdr_ok": true,
      "degenerates_lose": true,
      "permutation_behaves": true,
      "oracle_floors_respected": true,
      "coverage_floor_ok": true
    },
    "ship": true
  },
  "RB": {
    "checks": {
      "beats_foil": true,
      "beats_production": true,
      "fold_consistency": true,
      "pbo_ok": true,
      "dsr_ok": true,
      "fdr_ok": true,
      "degenerates_lose": true,
      "permutation_behaves": true,
      "oracle_floors_respected": true,
      "coverage_floor_ok": true
    },
    "ship": true
  },
  "WR": {
    "checks": {
      "beats_foil": true,
      "beats_production": true,
      "fold_consistency": true,
      "pbo_ok": true,
      "dsr_ok": true,
      "fdr_ok": true,
      "degenerates_lose": true,
      "permutation_behaves": true,
      "oracle_floors_respected": true,
      "coverage_floor_ok": true
    },
    "ship": true
  },
  "TE": {
    "checks": {
      "beats_foil": true,
      "beats_production": true,
      "fold_consistency": true,
      "pbo_ok": true,
      "dsr_ok": true,
      "fdr_ok": true,
      "degenerates_lose": true,
      "permutation_behaves": true,
      "oracle_floors_respected": true,
      "coverage_floor_ok": true
    },
    "ship": true
  }
}
```

## Null-state classification (failing positions)

```json
{}
```
