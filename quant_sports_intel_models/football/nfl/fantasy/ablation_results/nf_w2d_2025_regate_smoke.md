# NF-W2d — the injury-availability family re-gated with 2025 in the fold set (§0.5 bake-off)

**Generated:** 2026-08-09T22:20:12+00:00 · **gated folds:** 4 (2024H1…2025H2) · **modeled rows:** 84553 · **label:** `v1.nflverse.stats_player_week` / `ppr`

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim, **deploy-held**: this story validates a TRAINING ERA and promotes, publishes and retrains nothing. Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects (inverted at QB/TE on this frame). ONLY the fold set changed vs NF-W2b — 2025H1/2025H2 leave SHADOW and join the gated set; the reproduction control below measures that claim.

## Reproduction control — **PASS**

the 12 NF-W2b folds reproduce exactly ⇒ the 2025 plumbing did not perturb the inherited harness, so every difference below is an ERA effect (80 legacy (fold, arm, position) cells compared at tolerance 1e-09; max |Δ| 0.0).

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

### QB — **NULL (POWER_LIMITED)**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__inj  |      2.1118 |
| oracle_avail__base |      2.1143 |
| inj_both           |      2.5377 |
| inj_zero_leg       |      2.5429 |
| inj_override       |      2.5662 |
| base_rate          |      2.6523 |
| inj_permuted       |      2.6583 |
| base_noRate        |      2.6683 |
| pos_marginal       |      4.7852 |
| nihilist_zero      |      6.6483 |

- winner `inj_both` vs rate foil `base_rate`: mean lift +0.1146 CRPS, fold wins 4/4 (clause requires 4) · PBO 0.1667 · DSR 0.9186 · p 0.0532 · FDR pass True
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.1146, 'fold_wins': 4}, 'inj_zero_leg': {'mean': 0.1094, 'fold_wins': 4}, 'inj_override': {'mean': 0.0861, 'fold_wins': 4}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.1307, 'winner_vs_production_fold_wins': 4, 'marginal_channel_mean': 0.0161, 'marginal_channel_p_one_sided': 0.1113, 'player_content_mean': 0.1146}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': -0.006, 'permuted_lift_p_one_sided': 0.6705, 'winner_vs_permuted_mean': 0.1206} · coverage(80) {'winner_coverage_80': 0.8171, 'n_rows': 2733, 'binomial_se': 0.0077, 'blocking_shortfall': False}
- MAE (report-only, never selects): {'inj_both': 3.3689, 'base_rate': 3.4968, 'base_noRate': 3.5201, 'nihilist_zero': 6.6483}
- ERA DELTA (diagnostic): {'arm': 'inj_both', 'full_14': {'n_folds': 4, 'mean_lift_vs_foil': 0.1146, 'fold_wins': 4, 'mean_lift_vs_production': 0.1307}, 'legacy_12': {'n_folds': 2, 'mean_lift_vs_foil': 0.1072, 'fold_wins': 2, 'mean_lift_vs_production': 0.1371}, 'new_2025': {'n_folds': 2, 'mean_lift_vs_foil': 0.122, 'fold_wins': 2, 'mean_lift_vs_production': 0.1242}}
- ERA RANK (post-hoc diagnostic): {'arm': 'inj_both', 'new_lifts': [0.2119, 0.0321], 'legacy_min': 0.0241, 'legacy_max': 0.1902, 'legacy_median': 0.1072, 'below_legacy_pairs': 1, 'of_pairs': 4, 'exact_one_sided_p': 0.8333, 'relative_lift_legacy_pct': 4.113, 'relative_lift_new_pct': 4.52}

### RB — **SHIP**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__inj  |      2.1751 |
| oracle_avail__base |      2.1764 |
| inj_both           |      2.4005 |
| inj_zero_leg       |      2.4020 |
| inj_override       |      2.4211 |
| inj_permuted       |      2.4950 |
| base_noRate        |      2.4954 |
| base_rate          |      2.4971 |
| pos_marginal       |      3.8900 |
| nihilist_zero      |      5.6859 |

- winner `inj_both` vs rate foil `base_rate`: mean lift +0.0966 CRPS, fold wins 4/4 (clause requires 4) · PBO 0.0 · DSR 0.9938 · p 0.029 · FDR pass True
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.0966, 'fold_wins': 4}, 'inj_zero_leg': {'mean': 0.0951, 'fold_wins': 4}, 'inj_override': {'mean': 0.076, 'fold_wins': 4}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.0948, 'winner_vs_production_fold_wins': 4, 'marginal_channel_mean': -0.0018, 'marginal_channel_p_one_sided': 0.6387, 'player_content_mean': 0.0966}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': 0.0021, 'permuted_lift_p_one_sided': 0.2088, 'winner_vs_permuted_mean': 0.0945} · coverage(80) {'winner_coverage_80': 0.8446, 'n_rows': 4246, 'binomial_se': 0.0061, 'blocking_shortfall': False}
- MAE (report-only, never selects): {'inj_both': 3.2345, 'base_rate': 3.358, 'base_noRate': 3.3562, 'nihilist_zero': 5.6859}
- ERA DELTA (diagnostic): {'arm': 'inj_both', 'full_14': {'n_folds': 4, 'mean_lift_vs_foil': 0.0966, 'fold_wins': 4, 'mean_lift_vs_production': 0.0948}, 'legacy_12': {'n_folds': 2, 'mean_lift_vs_foil': 0.151, 'fold_wins': 2, 'mean_lift_vs_production': 0.1568}, 'new_2025': {'n_folds': 2, 'mean_lift_vs_foil': 0.0422, 'fold_wins': 2, 'mean_lift_vs_production': 0.0329}}
- ERA RANK (post-hoc diagnostic): {'arm': 'inj_both', 'new_lifts': [0.0421, 0.0424], 'legacy_min': 0.1328, 'legacy_max': 0.1692, 'legacy_median': 0.151, 'below_legacy_pairs': 4, 'of_pairs': 4, 'exact_one_sided_p': 0.1667, 'relative_lift_legacy_pct': 5.933, 'relative_lift_new_pct': 1.723}

### WR — **SHIP**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__base |      2.0585 |
| oracle_avail__inj  |      2.0604 |
| inj_zero_leg       |      2.5410 |
| inj_both           |      2.5428 |
| inj_override       |      2.5609 |
| base_noRate        |      2.6398 |
| base_rate          |      2.6440 |
| inj_permuted       |      2.6460 |
| pos_marginal       |      3.7053 |
| nihilist_zero      |      5.4612 |

- winner `inj_zero_leg` vs rate foil `base_rate`: mean lift +0.1029 CRPS, fold wins 4/4 (clause requires 4) · PBO 0.0 · DSR 0.9753 · p 0.0046 · FDR pass True
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.1011, 'fold_wins': 4}, 'inj_zero_leg': {'mean': 0.1029, 'fold_wins': 4}, 'inj_override': {'mean': 0.083, 'fold_wins': 4}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.0988, 'winner_vs_production_fold_wins': 4, 'marginal_channel_mean': -0.0042, 'marginal_channel_p_one_sided': 0.8134, 'player_content_mean': 0.1029}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': -0.002, 'permuted_lift_p_one_sided': 0.6896, 'winner_vs_permuted_mean': 0.105} · coverage(80) {'winner_coverage_80': 0.8526, 'n_rows': 6416, 'binomial_se': 0.005, 'blocking_shortfall': False}
- MAE (report-only, never selects): {'inj_zero_leg': 3.4457, 'base_rate': 3.5855, 'base_noRate': 3.5699, 'nihilist_zero': 5.4612}
- ERA DELTA (diagnostic): {'arm': 'inj_zero_leg', 'full_14': {'n_folds': 4, 'mean_lift_vs_foil': 0.1029, 'fold_wins': 4, 'mean_lift_vs_production': 0.0988}, 'legacy_12': {'n_folds': 2, 'mean_lift_vs_foil': 0.1221, 'fold_wins': 2, 'mean_lift_vs_production': 0.1229}, 'new_2025': {'n_folds': 2, 'mean_lift_vs_foil': 0.0838, 'fold_wins': 2, 'mean_lift_vs_production': 0.0746}}
- ERA RANK (post-hoc diagnostic): {'arm': 'inj_zero_leg', 'new_lifts': [0.1144, 0.0531], 'legacy_min': 0.114, 'legacy_max': 0.1302, 'legacy_median': 0.1221, 'below_legacy_pairs': 3, 'of_pairs': 4, 'exact_one_sided_p': 0.3333, 'relative_lift_legacy_pct': 4.497, 'relative_lift_new_pct': 3.256}

### TE — **SHIP**

| arm                |   mean_crps |
|:-------------------|------------:|
| oracle_avail__base |      1.3693 |
| oracle_avail__inj  |      1.3701 |
| inj_both           |      1.7727 |
| inj_zero_leg       |      1.7733 |
| inj_override       |      1.7923 |
| base_rate          |      1.8313 |
| base_noRate        |      1.8315 |
| inj_permuted       |      1.8329 |
| pos_marginal       |      2.6260 |
| nihilist_zero      |      3.5850 |

- winner `inj_both` vs rate foil `base_rate`: mean lift +0.0586 CRPS, fold wins 4/4 (clause requires 4) · PBO 0.0 · DSR 0.9994 · p 0.0068 · FDR pass True
- pure player-level attribution (vs `base_rate`): {'inj_both': {'mean': 0.0586, 'fold_wins': 4}, 'inj_zero_leg': {'mean': 0.058, 'fold_wins': 4}, 'inj_override': {'mean': 0.0391, 'fold_wins': 4}}
- decomposition (vs production `base_noRate`): {'winner_vs_production_mean': 0.0588, 'winner_vs_production_fold_wins': 4, 'marginal_channel_mean': 0.0002, 'marginal_channel_p_one_sided': 0.4829, 'player_content_mean': 0.0586}
- anchors: {'nihilist_loses': True, 'pos_marginal_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'foil_respects_oracle': True} · permutation detail {'permuted_lift_vs_base_rate_mean': -0.0016, 'permuted_lift_p_one_sided': 0.7127, 'winner_vs_permuted_mean': 0.0602} · coverage(80) {'winner_coverage_80': 0.8829, 'n_rows': 3870, 'binomial_se': 0.0064, 'blocking_shortfall': False}
- MAE (report-only, never selects): {'inj_both': 2.3895, 'base_rate': 2.4674, 'base_noRate': 2.469, 'nihilist_zero': 3.585}
- ERA DELTA (diagnostic): {'arm': 'inj_both', 'full_14': {'n_folds': 4, 'mean_lift_vs_foil': 0.0586, 'fold_wins': 4, 'mean_lift_vs_production': 0.0588}, 'legacy_12': {'n_folds': 2, 'mean_lift_vs_foil': 0.0755, 'fold_wins': 2, 'mean_lift_vs_production': 0.074}, 'new_2025': {'n_folds': 2, 'mean_lift_vs_foil': 0.0417, 'fold_wins': 2, 'mean_lift_vs_production': 0.0435}}
- ERA RANK (post-hoc diagnostic): {'arm': 'inj_both', 'new_lifts': [0.0484, 0.0349], 'legacy_min': 0.0639, 'legacy_max': 0.0872, 'legacy_median': 0.0755, 'below_legacy_pairs': 4, 'of_pairs': 4, 'exact_one_sided_p': 0.1667, 'relative_lift_legacy_pct': 4.191, 'relative_lift_new_pct': 2.24}

## Per-fold family activity (the NF-D20 discipline)

| fold   |   n_test |   listed_share |   out_doubtful_share |   observed_share | override                                                          |
|:-------|---------:|---------------:|---------------------:|-----------------:|:------------------------------------------------------------------|
| 2024H1 |     4365 |         0.1805 |               0.0323 |           1      | {'p_emp': 0.9984, 'n_train_cell': 2526, 'n_test_overridden': 141} |
| 2024H2 |     4212 |         0.194  |               0.0332 |           1      | {'p_emp': 0.9985, 'n_train_cell': 2676, 'n_test_overridden': 140} |
| 2025H1 |     4308 |         0.1585 |               0.0416 |           1      | {'p_emp': 0.9986, 'n_train_cell': 2807, 'n_test_overridden': 179} |
| 2025H2 |     4380 |         0.1679 |               0.0226 |           0.8977 | {'p_emp': 0.9967, 'n_train_cell': 3008, 'n_test_overridden': 99}  |

## Covered-subset diagnostic (where the mechanism can act) — never gated

| fold   |   n_test |   observed_rows |   observed_share |   listed_share_over_observed | weeks_fully_uncovered   |
|:-------|---------:|----------------:|-----------------:|-----------------------------:|:------------------------|
| 2024H1 |     4365 |            4365 |           1      |                       0.1805 | []                      |
| 2024H2 |     4212 |            4212 |           1      |                       0.194  | []                      |
| 2025H1 |     4308 |            4308 |           1      |                       0.1585 | []                      |
| 2025H2 |     4380 |            3932 |           0.8977 |                       0.1679 | [12]                    |

## Era attenuation — is it the ARM or the POSITION? (post-hoc, never gated)

**the era ratio is essentially ARM-INVARIANT (max |inj_both − inj_zero_leg| = 0.024) ⇒ any attenuation is a property of the POSITION, not of how much of the family an arm consumes — which REFUTES the practice-line-absence mechanism as the explanation for the position pattern**

| position   | arm          |   legacy_lift |   new_lift |   era_ratio |
|:-----------|:-------------|--------------:|-----------:|------------:|
| QB         | inj_both     |        0.1072 |     0.122  |       1.139 |
| QB         | inj_zero_leg |        0.1014 |     0.1173 |       1.157 |
| QB         | inj_override |        0.0693 |     0.1029 |       1.485 |
| RB         | inj_both     |        0.151  |     0.0422 |       0.28  |
| RB         | inj_zero_leg |        0.1483 |     0.0419 |       0.283 |
| RB         | inj_override |        0.112  |     0.04   |       0.357 |
| WR         | inj_both     |        0.1183 |     0.084  |       0.71  |
| WR         | inj_zero_leg |        0.1221 |     0.0838 |       0.686 |
| WR         | inj_override |        0.0996 |     0.0664 |       0.667 |
| TE         | inj_both     |        0.0755 |     0.0417 |       0.552 |
| TE         | inj_zero_leg |        0.074  |     0.042  |       0.568 |
| TE         | inj_override |        0.0535 |     0.0247 |       0.461 |

BH q=0.10 cutoffs over the four positions: {'RB': 0.025, 'TE': 0.05, 'WR': 0.075, 'QB': 0.1} · survives: {'RB': False, 'TE': False, 'WR': False, 'QB': False}

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
      "dsr_ok": false,
      "fdr_ok": true,
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
{
  "QB": {
    "state": "POWER_LIMITED",
    "reason": "`nf_w2d_injury_crps_QB`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it \u2014 DSR alone needs 8 folds against 4 (the BH-FDR requirement is separate and may be larger). \u26a0\ufe0f The provenance of `V` was NOT stated (`degenerates_excluded_from_v=None`), so this classifier cannot tell a DSR-CONV-correct dispersion from one inflated by pre-registered degenerates. Treat the field-size reading as UNVERIFIED \u2014 establish the provenance and re-classify rather than acting on it.",
    "retest_trigger": "+4 folds for the DSR gate \u2014 field size alone cannot rescue it at this dispersion \u2014 \u26a0\ufe0f BUT FIRST: \u26a0\ufe0f The provenance of `V` was NOT stated (`degenerates_excluded_from_v=None`), so this classifier cannot tell a DSR-CONV-correct dispersion from one inflated by pre-registered degenerates. Treat the field-size reading as UNVERIFIED \u2014 establish the provenance and re-classify rather than acting on it."
  }
}
```
