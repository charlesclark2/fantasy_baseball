# NF-MARGIN1 — per-player interval/tail calibration of the hurdle champion (§0.5 bake-off)

**Generated:** 2026-08-11T05:44:43+00:00 · **folds:** 8 half-season blocks (2022H1…2025H2, the NF-W1 axis on the NF-W2d two-era matrix) · **player-weeks:** 34552

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (a clearing arm's retrain/promote path is blocked on NF-C6 Ph2 + NF-G0). Selection metric is `crps_q199` (199-level pinball CRPS — the grid the tail fix is VISIBLE on); Winkler-80 + randomized-PIT flatness form the story's two-sided calibration gate; coverage stays a FLOOR (NF1.8). Every direction word below is three-way and **derived from the interval at report time**, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-MARGIN1):** 532 game-groups / 183314 records checked; 0 rows dropped fail-closed.

**Verdict:** QB[POWER_LIMITED] RB[POWER_LIMITED] WR[POWER_LIMITED] TE[POWER_LIMITED]

## The diagnosis (motivating measurement: NF-W5 team-total coverage(80) 0.706, ~11 SE below the floor)

| position   |     n |   p_below_grid |   p_above_grid |   max_decile_dev |   var_z |   cov_50 |   cov_80 |   cov_95 |   cov_99 |   pred_p0 |   zero_share |
|:-----------|------:|---------------:|---------------:|-----------------:|--------:|---------:|---------:|---------:|---------:|----------:|-------------:|
| QB         |  5485 |        0.05287 |        0.05324 |          0.02416 |  1.2645 |   0.6862 |   0.825  |   0.9108 |   0.9108 |    0.5185 |       0.5232 |
| RB         |  8591 |        0.04097 |        0.04458 |          0.01116 |  1.137  |   0.6264 |   0.845  |   0.9334 |   0.9334 |    0.3544 |       0.3505 |
| WR         | 12827 |        0.03898 |        0.04701 |          0.01187 |  1.1509 |   0.6525 |   0.8541 |   0.9372 |   0.9372 |    0.3734 |       0.3907 |
| TE         |  7649 |        0.02536 |        0.03922 |          0.00404 |  1.036  |   0.7079 |   0.8821 |   0.9576 |   0.9576 |    0.4802 |       0.4903 |

## Team-total re-check (independence copula, report-only — the loop closed)

| label            |    n |   coverage_80 |   share_below_q10 |   share_above_q90 |   binomial_se |
|:-----------------|-----:|--------------:|------------------:|------------------:|--------------:|
| pit_recal_pos    | 2174 |        0.6914 |            0.1325 |            0.1762 |        0.0086 |
| pit_recal_tail   | 2174 |        0.7511 |            0.1293 |            0.1196 |        0.0086 |
| level_widen      | 2174 |        0.6923 |            0.144  |            0.1638 |        0.0086 |
| zscore_affine    | 2174 |        0.6964 |            0.1352 |            0.1684 |        0.0086 |
| incumbent        | 2174 |        0.6794 |            0.1403 |            0.1803 |        0.0086 |
| pit_recal_global | 2174 |        0.6914 |            0.1343 |            0.1743 |        0.0086 |

## QB — **POWER_LIMITED**

`pit_recal_tail` TIES `incumbent` by +0.0033 CRPS (CI95 [-0.0032, +0.0097] spans zero)

| label                     |   mean_crps_q199 |
|:--------------------------|-----------------:|
| oracle__pit_recal_tail    |          2.40320 |
| oracle__pit_recal_pos     |          2.40905 |
| oracle__zscore_affine     |          2.40945 |
| pit_recal_tail            |          2.41090 |
| oracle__pit_recal_global  |          2.41124 |
| oracle__level_widen       |          2.41146 |
| incumbent                 |          2.41416 |
| level_widen               |          2.41421 |
| pit_recal_global          |          2.41448 |
| zscore_affine             |          2.41514 |
| matched_n__level_widen    |          2.41537 |
| matched_n__pit_recal_tail |          2.41614 |
| pit_recal_pos             |          2.41630 |
| matched_n__zscore_affine  |          2.41898 |
| matched_n__pit_recal_pos  |          2.42110 |
| permuted_recal            |          2.71155 |
| zero_width                |          3.24795 |
| max_width                 |          3.25964 |

- fold wins 4/8 (clause requires 6) · PBO 0.1286 · DSR 0.5851 · p 0.1344 · BH binding False
- calibration gate: Winkler-80 delta vs incumbent +0.0895 (incumbent 16.42635 → winner 16.33683) · PIT max-decile-dev 0.02653 → 0.01322
- coverage (floor 0.8, never a target): {'coverage_80': 0.8531, 'n_rows': 5485, 'binomial_se': 0.0054, 'blocking_shortfall': False} · map {'coverage_50': {'pit_recal_tail': 0.7023, 'incumbent': 0.6864, 'max_width': 0.8767}, 'coverage_80': {'pit_recal_tail': 0.8532, 'incumbent': 0.825, 'max_width': 0.9441}, 'coverage_95': {'pit_recal_tail': 0.957, 'incumbent': 0.911, 'max_width': 0.9809}, 'coverage_99': {'pit_recal_tail': 0.9893, 'incumbent': 0.911, 'max_width': 0.9809}}
- tail channel (`pit_recal_tail` − `pit_recal_pos`, pre-registered contrast): {'mean_delta': 0.0054, 'ci95': [0.00367, 0.00713], 'fold_wins': 8, 'p_one_sided': 0.0001} · BH binding True
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foil_respects_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'pit_recal_pos': {'arm': 2.4163, 'own_form_oracle': 2.40905, 'matched_n': 2.4211, 'oracle_beats_matched_n': True}, 'pit_recal_tail': {'arm': 2.4109, 'own_form_oracle': 2.4032, 'matched_n': 2.41614, 'oracle_beats_matched_n': True}, 'level_widen': {'arm': 2.41421, 'own_form_oracle': 2.41146, 'matched_n': 2.41537, 'oracle_beats_matched_n': True}, 'zscore_affine': {'arm': 2.41514, 'own_form_oracle': 2.40945, 'matched_n': 2.41898, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_incumbent_mean': -0.29739, 'permuted_lift_p_one_sided': 1.0}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0112, 'legacy_mean_delta': 0.0006, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True, 'interval_score_improves': True, 'pit_flatness_improves': True}

## RB — **POWER_LIMITED**

`pit_recal_tail` TIES `incumbent` by +0.0022 CRPS (CI95 [-0.0019, +0.0062] spans zero)

| label                     |   mean_crps_q199 |
|:--------------------------|-----------------:|
| oracle__pit_recal_tail    |          2.35517 |
| pit_recal_tail            |          2.35796 |
| matched_n__pit_recal_tail |          2.35848 |
| oracle__pit_recal_pos     |          2.35861 |
| oracle__zscore_affine     |          2.35942 |
| oracle__pit_recal_global  |          2.35950 |
| oracle__level_widen       |          2.35988 |
| matched_n__level_widen    |          2.35992 |
| matched_n__zscore_affine  |          2.36011 |
| incumbent                 |          2.36012 |
| pit_recal_global          |          2.36083 |
| zscore_affine             |          2.36085 |
| level_widen               |          2.36102 |
| pit_recal_pos             |          2.36106 |
| matched_n__pit_recal_pos  |          2.36152 |
| permuted_recal            |          2.57653 |
| zero_width                |          3.23657 |
| max_width                 |          3.32154 |

- fold wins 6/8 (clause requires 6) · PBO 0.1429 · DSR 0.5526 · p 0.1248 · BH binding False
- calibration gate: Winkler-80 delta vs incumbent +0.0466 (incumbent 15.35767 → winner 15.31103) · PIT max-decile-dev 0.01023 → 0.01247
- coverage (floor 0.8, never a target): {'coverage_80': 0.8621, 'n_rows': 8591, 'binomial_se': 0.0043, 'blocking_shortfall': False} · map {'coverage_50': {'pit_recal_tail': 0.6456, 'incumbent': 0.6265, 'max_width': 0.9013}, 'coverage_80': {'pit_recal_tail': 0.8622, 'incumbent': 0.8452, 'max_width': 0.9847}, 'coverage_95': {'pit_recal_tail': 0.9652, 'incumbent': 0.9335, 'max_width': 0.9958}, 'coverage_99': {'pit_recal_tail': 0.9905, 'incumbent': 0.9335, 'max_width': 0.9958}}
- tail channel (`pit_recal_tail` − `pit_recal_pos`, pre-registered contrast): {'mean_delta': 0.00309, 'ci95': [0.00154, 0.00464], 'fold_wins': 8, 'p_one_sided': 0.0011} · BH binding True
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foil_respects_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'pit_recal_pos': {'arm': 2.36106, 'own_form_oracle': 2.35861, 'matched_n': 2.36152, 'oracle_beats_matched_n': True}, 'pit_recal_tail': {'arm': 2.35796, 'own_form_oracle': 2.35517, 'matched_n': 2.35848, 'oracle_beats_matched_n': True}, 'level_widen': {'arm': 2.36102, 'own_form_oracle': 2.35988, 'matched_n': 2.35992, 'oracle_beats_matched_n': True}, 'zscore_affine': {'arm': 2.36085, 'own_form_oracle': 2.35942, 'matched_n': 2.36011, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_incumbent_mean': -0.21641, 'permuted_lift_p_one_sided': 1.0}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0039, 'legacy_mean_delta': 0.0016, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True, 'interval_score_improves': True, 'pit_flatness_improves': False}

## WR — **POWER_LIMITED**

`pit_recal_tail` BEATS `pit_recal_global` by +0.0033 CRPS (CI95 [+0.0008, +0.0059] excludes zero)

| label                     |   mean_crps_q199 |
|:--------------------------|-----------------:|
| oracle__pit_recal_tail    |          2.50527 |
| oracle__pit_recal_pos     |          2.50945 |
| matched_n__pit_recal_tail |          2.50947 |
| pit_recal_tail            |          2.50997 |
| oracle__zscore_affine     |          2.51047 |
| oracle__pit_recal_global  |          2.51172 |
| matched_n__pit_recal_pos  |          2.51328 |
| pit_recal_global          |          2.51331 |
| oracle__level_widen       |          2.51385 |
| pit_recal_pos             |          2.51390 |
| matched_n__zscore_affine  |          2.51390 |
| incumbent                 |          2.51426 |
| zscore_affine             |          2.51493 |
| matched_n__level_widen    |          2.51505 |
| level_widen               |          2.51562 |
| permuted_recal            |          2.70352 |
| zero_width                |          3.46621 |
| max_width                 |          3.56004 |

- fold wins 7/8 (clause requires 6) · PBO 0.0 · DSR 0.6127 · p 0.0079 · BH binding True
- calibration gate: Winkler-80 delta vs incumbent +0.0336 (incumbent 16.26259 → winner 16.22904) · PIT max-decile-dev 0.0139 → 0.00629
- coverage (floor 0.8, never a target): {'coverage_80': 0.8695, 'n_rows': 12827, 'binomial_se': 0.0035, 'blocking_shortfall': False} · map {'coverage_50': {'pit_recal_tail': 0.6613, 'incumbent': 0.6526, 'max_width': 0.9202}, 'coverage_80': {'pit_recal_tail': 0.8695, 'incumbent': 0.854, 'max_width': 0.9891}, 'coverage_95': {'pit_recal_tail': 0.9649, 'incumbent': 0.9371, 'max_width': 0.9978}, 'coverage_99': {'pit_recal_tail': 0.9929, 'incumbent': 0.9371, 'max_width': 0.9978}}
- tail channel (`pit_recal_tail` − `pit_recal_pos`, pre-registered contrast): {'mean_delta': 0.00393, 'ci95': [0.00272, 0.00515], 'fold_wins': 8, 'p_one_sided': 0.0001} · BH binding True
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foil_respects_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'pit_recal_pos': {'arm': 2.5139, 'own_form_oracle': 2.50945, 'matched_n': 2.51328, 'oracle_beats_matched_n': True}, 'pit_recal_tail': {'arm': 2.50997, 'own_form_oracle': 2.50527, 'matched_n': 2.50947, 'oracle_beats_matched_n': True}, 'level_widen': {'arm': 2.51562, 'own_form_oracle': 2.51385, 'matched_n': 2.51505, 'oracle_beats_matched_n': True}, 'zscore_affine': {'arm': 2.51493, 'own_form_oracle': 2.51047, 'matched_n': 2.5139, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_incumbent_mean': -0.18926, 'permuted_lift_p_one_sided': 1.0}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0054, 'legacy_mean_delta': 0.0026, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True, 'interval_score_improves': True, 'pit_flatness_improves': True}

## TE — **POWER_LIMITED**

`pit_recal_tail` TIES `incumbent` by +0.0008 CRPS (CI95 [-0.0018, +0.0034] spans zero)

| label                     |   mean_crps_q199 |
|:--------------------------|-----------------:|
| oracle__pit_recal_tail    |          1.72678 |
| pit_recal_tail            |          1.72881 |
| oracle__pit_recal_pos     |          1.72890 |
| oracle__pit_recal_global  |          1.72902 |
| oracle__level_widen       |          1.72962 |
| level_widen               |          1.72963 |
| incumbent                 |          1.72963 |
| oracle__zscore_affine     |          1.72977 |
| matched_n__pit_recal_tail |          1.72978 |
| zscore_affine             |          1.73007 |
| matched_n__level_widen    |          1.73008 |
| pit_recal_global          |          1.73034 |
| pit_recal_pos             |          1.73051 |
| matched_n__zscore_affine  |          1.73080 |
| matched_n__pit_recal_pos  |          1.73149 |
| permuted_recal            |          1.83858 |
| zero_width                |          2.36975 |
| max_width                 |          2.48597 |

- fold wins 7/8 (clause requires 6) · PBO 0.2429 · DSR 0.5094 · p 0.2368 · BH binding False
- calibration gate: Winkler-80 delta vs incumbent -0.0075 (incumbent 11.42317 → winner 11.43066) · PIT max-decile-dev 0.00613 → 0.00535
- coverage (floor 0.8, never a target): {'coverage_80': 0.8799, 'n_rows': 7649, 'binomial_se': 0.0046, 'blocking_shortfall': False} · map {'coverage_50': {'pit_recal_tail': 0.7028, 'incumbent': 0.708, 'max_width': 0.9192}, 'coverage_80': {'pit_recal_tail': 0.8798, 'incumbent': 0.8821, 'max_width': 0.9865}, 'coverage_95': {'pit_recal_tail': 0.9694, 'incumbent': 0.9577, 'max_width': 0.9988}, 'coverage_99': {'pit_recal_tail': 0.9936, 'incumbent': 0.9577, 'max_width': 0.9988}}
- tail channel (`pit_recal_tail` − `pit_recal_pos`, pre-registered contrast): {'mean_delta': 0.0017, 'ci95': [0.00121, 0.00219], 'fold_wins': 8, 'p_one_sided': 0.0} · BH binding True
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foil_respects_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'pit_recal_pos': {'arm': 1.73051, 'own_form_oracle': 1.7289, 'matched_n': 1.73149, 'oracle_beats_matched_n': True}, 'pit_recal_tail': {'arm': 1.72881, 'own_form_oracle': 1.72678, 'matched_n': 1.72978, 'oracle_beats_matched_n': True}, 'level_widen': {'arm': 1.72963, 'own_form_oracle': 1.72962, 'matched_n': 1.73008, 'oracle_beats_matched_n': True}, 'zscore_affine': {'arm': 1.73007, 'own_form_oracle': 1.72977, 'matched_n': 1.7308, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_incumbent_mean': -0.10895, 'permuted_lift_p_one_sided': 1.0}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0011, 'legacy_mean_delta': 0.0007, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True, 'interval_score_improves': False, 'pit_flatness_improves': True}

## Null-state classification

```json
{
  "QB": {
    "state": "POWER_LIMITED",
    "reason": "`nf_margin1_QB_crps`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it \u2014 DSR alone needs 472 folds against 8 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
    "retest_trigger": "+464 folds for the DSR gate \u2014 field size alone cannot rescue it at this dispersion"
  },
  "RB": {
    "state": "POWER_LIMITED",
    "reason": "`nf_margin1_RB_crps`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it \u2014 DSR alone needs 936 folds against 8 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
    "retest_trigger": "+928 folds for the DSR gate \u2014 field size alone cannot rescue it at this dispersion"
  },
  "WR": {
    "state": "POWER_LIMITED",
    "reason": "`nf_margin1_WR_crps`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it \u2014 DSR alone needs 100 folds against 8 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
    "retest_trigger": "+92 folds for the DSR gate \u2014 field size alone cannot rescue it at this dispersion"
  },
  "TE": {
    "state": "POWER_LIMITED",
    "reason": "`nf_margin1_TE_crps`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it \u2014 DSR alone needs 26067 folds against 8 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
    "retest_trigger": "+26059 folds for the DSR gate \u2014 field size alone cannot rescue it at this dispersion"
  }
}
```

## Pre-registration echo

```json
{
  "real_arms": [
    "pit_recal_pos",
    "pit_recal_tail",
    "level_widen",
    "zscore_affine"
  ],
  "foils": [
    "incumbent",
    "pit_recal_global"
  ],
  "anchors": [
    "zero_width",
    "max_width",
    "permuted_recal",
    "oracle__pit_recal_pos",
    "oracle__pit_recal_tail",
    "oracle__level_widen",
    "oracle__zscore_affine",
    "oracle__pit_recal_global",
    "matched_n__pit_recal_pos",
    "matched_n__pit_recal_tail",
    "matched_n__level_widen",
    "matched_n__zscore_affine"
  ],
  "eligible": [
    "pit_recal_pos",
    "pit_recal_tail",
    "level_widen",
    "zscore_affine",
    "incumbent",
    "pit_recal_global"
  ],
  "parametrized_forms": [
    "pit_recal_pos",
    "pit_recal_tail",
    "level_widen",
    "zscore_affine",
    "pit_recal_global"
  ],
  "primary_metric": "crps_q199",
  "co_metrics": [
    "winkler_80",
    "coverage_80",
    "coverage_95",
    "coverage_99"
  ],
  "eval_levels": {
    "n": 199,
    "lo": 0.005,
    "hi": 0.995
  },
  "widen_grid": [
    1.0,
    1.05,
    1.1,
    1.15,
    1.2,
    1.3,
    1.4,
    1.6
  ],
  "max_width_scale": 3.0,
  "min_tail_n": 10,
  "cal_split": {
    "target_fraction": 0.2,
    "min_rows": 6000,
    "purge_weeks": 2
  },
  "test_blocks": [
    [
      2022,
      1
    ],
    [
      2022,
      2
    ],
    [
      2023,
      1
    ],
    [
      2023,
      2
    ],
    [
      2024,
      1
    ],
    [
      2024,
      2
    ],
    [
      2025,
      1
    ],
    [
      2025,
      2
    ]
  ],
  "pbo_max": 0.2,
  "dsr_min": 0.95,
  "fdr_q": 0.1,
  "fdr_families": {
    "arm": [
      "margin_arm_QB",
      "margin_arm_RB",
      "margin_arm_WR",
      "margin_arm_TE"
    ],
    "tail_channel": [
      "margin_tail_QB",
      "margin_tail_RB",
      "margin_tail_WR",
      "margin_tail_TE"
    ]
  },
  "coverage_floor": 0.8,
  "team_total_samples": 512,
  "capture_era_folds": [
    "2025H1",
    "2025H2"
  ],
  "seed": 20260812
}
```