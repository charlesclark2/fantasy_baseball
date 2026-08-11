# NF-MARGIN1 — per-player interval/tail calibration of the hurdle champion (§0.5 bake-off)

**Generated:** 2026-08-11T05:22:50+00:00 · **folds:** 2 half-season blocks (2025H1…2025H2, the NF-W1 axis on the NF-W2d two-era matrix) · **player-weeks:** 8688

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (a clearing arm's retrain/promote path is blocked on NF-C6 Ph2 + NF-G0). Selection metric is `crps_q199` (199-level pinball CRPS — the grid the tail fix is VISIBLE on); Winkler-80 + randomized-PIT flatness form the story's two-sided calibration gate; coverage stays a FLOOR (NF1.8). Every direction word below is three-way and **derived from the interval at report time**, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-MARGIN1):** 532 game-groups / 183314 records checked; 0 rows dropped fail-closed.

**Verdict:** QB[UNDEFINED] RB[UNDEFINED] WR[UNDEFINED] TE[UNDEFINED]

## The diagnosis (motivating measurement: NF-W5 team-total coverage(80) 0.706, ~11 SE below the floor)

| position   |    n |   p_below_grid |   p_above_grid |   max_decile_dev |   var_z |   cov_50 |   cov_80 |   cov_95 |   cov_99 |   pred_p0 |   zero_share |
|:-----------|-----:|---------------:|---------------:|-----------------:|--------:|---------:|---------:|---------:|---------:|----------:|-------------:|
| QB         | 1372 |        0.06487 |        0.05248 |          0.02974 |  1.3189 |   0.6822 |   0.8112 |   0.9009 |   0.9009 |    0.5143 |       0.5189 |
| RB         | 2144 |        0.03871 |        0.04944 |          0.01884 |  1.1148 |   0.6409 |   0.8424 |   0.93   |   0.93   |    0.3638 |       0.3544 |
| WR         | 3231 |        0.03838 |        0.03962 |          0.01854 |  1.1344 |   0.6472 |   0.8567 |   0.9461 |   0.9461 |    0.3862 |       0.4048 |
| TE         | 1941 |        0.02524 |        0.04379 |          0.01396 |  1.0523 |   0.6996 |   0.8774 |   0.9541 |   0.9541 |    0.4763 |       0.4729 |

## Team-total re-check (independence copula, report-only — the loop closed)

| label            |   n |   coverage_80 |   share_below_q10 |   share_above_q90 |   binomial_se |
|:-----------------|----:|--------------:|------------------:|------------------:|--------------:|
| pit_recal_pos    | 544 |        0.6691 |            0.1673 |            0.1636 |        0.0171 |
| pit_recal_tail   | 544 |        0.7243 |            0.1673 |            0.1085 |        0.0171 |
| level_widen      | 544 |        0.6636 |            0.1728 |            0.1636 |        0.0171 |
| zscore_affine    | 544 |        0.6728 |            0.171  |            0.1562 |        0.0171 |
| incumbent        | 544 |        0.6618 |            0.171  |            0.1673 |        0.0171 |
| pit_recal_global | 544 |        0.6654 |            0.1728 |            0.1618 |        0.0171 |

## QB — **UNDEFINED**

`pit_recal_tail` TIES `pit_recal_global` by +0.0084 CRPS (interval unevaluable)

| label                     |   mean_crps_q199 |
|:--------------------------|-----------------:|
| oracle__pit_recal_tail    |          2.51994 |
| oracle__zscore_affine     |          2.52574 |
| oracle__pit_recal_pos     |          2.52607 |
| pit_recal_tail            |          2.52646 |
| oracle__pit_recal_global  |          2.53129 |
| zscore_affine             |          2.53136 |
| matched_n__pit_recal_tail |          2.53247 |
| pit_recal_pos             |          2.53274 |
| level_widen               |          2.53306 |
| oracle__level_widen       |          2.53306 |
| matched_n__level_widen    |          2.53447 |
| pit_recal_global          |          2.53492 |
| matched_n__zscore_affine  |          2.53575 |
| incumbent                 |          2.53763 |
| matched_n__pit_recal_pos  |          2.53789 |
| permuted_recal            |          2.80375 |
| max_width                 |          3.36064 |
| zero_width                |          3.44817 |

- fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · BH binding False
- calibration gate: Winkler-80 delta vs incumbent +0.2225 (incumbent 17.05954 → winner 16.83706) · PIT max-decile-dev 0.03557 → 0.01837
- coverage (floor 0.8, never a target): {'coverage_80': 0.8418, 'n_rows': 1372, 'binomial_se': 0.0108, 'blocking_shortfall': False} · map {'coverage_50': {'pit_recal_tail': 0.6991, 'incumbent': 0.6824, 'max_width': 0.8761}, 'coverage_80': {'pit_recal_tail': 0.8418, 'incumbent': 0.8111, 'max_width': 0.938}, 'coverage_95': {'pit_recal_tail': 0.9527, 'incumbent': 0.9009, 'max_width': 0.9773}, 'coverage_99': {'pit_recal_tail': 0.9877, 'incumbent': 0.9009, 'max_width': 0.9773}}
- tail channel (`pit_recal_tail` − `pit_recal_pos`, pre-registered contrast): {'mean_delta': 0.00628, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None} · BH binding False
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': False, 'oracle_floors_respected_at_matched_n': True, 'foil_respects_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'pit_recal_pos': {'arm': 2.53274, 'own_form_oracle': 2.52607, 'matched_n': 2.53789, 'oracle_beats_matched_n': True}, 'pit_recal_tail': {'arm': 2.52646, 'own_form_oracle': 2.51994, 'matched_n': 2.53247, 'oracle_beats_matched_n': True}, 'level_widen': {'arm': 2.53306, 'own_form_oracle': 2.53306, 'matched_n': 2.53447, 'oracle_beats_matched_n': True}, 'zscore_affine': {'arm': 2.53136, 'own_form_oracle': 2.52574, 'matched_n': 2.53575, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_incumbent_mean': -0.26613, 'permuted_lift_p_one_sided': None}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0085, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True, 'interval_score_improves': True, 'pit_flatness_improves': True}

## RB — **UNDEFINED**

`pit_recal_tail` TIES `pit_recal_global` by +0.0036 CRPS (interval unevaluable)

| label                     |   mean_crps_q199 |
|:--------------------------|-----------------:|
| oracle__pit_recal_tail    |          2.35873 |
| pit_recal_tail            |          2.36179 |
| matched_n__pit_recal_tail |          2.36352 |
| oracle__pit_recal_pos     |          2.36354 |
| matched_n__zscore_affine  |          2.36451 |
| oracle__pit_recal_global  |          2.36465 |
| oracle__zscore_affine     |          2.36485 |
| pit_recal_global          |          2.36537 |
| zscore_affine             |          2.36545 |
| oracle__level_widen       |          2.36551 |
| level_widen               |          2.36566 |
| incumbent                 |          2.36566 |
| matched_n__level_widen    |          2.36566 |
| pit_recal_pos             |          2.36648 |
| matched_n__pit_recal_pos  |          2.36796 |
| permuted_recal            |          2.59627 |
| zero_width                |          3.23177 |
| max_width                 |          3.28400 |

- fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · BH binding False
- calibration gate: Winkler-80 delta vs incumbent +0.0529 (incumbent 15.59021 → winner 15.53726) · PIT max-decile-dev 0.01894 → 0.01558
- coverage (floor 0.8, never a target): {'coverage_80': 0.8503, 'n_rows': 2144, 'binomial_se': 0.0086, 'blocking_shortfall': False} · map {'coverage_50': {'pit_recal_tail': 0.6471, 'incumbent': 0.6411, 'max_width': 0.9012}, 'coverage_80': {'pit_recal_tail': 0.8502, 'incumbent': 0.8423, 'max_width': 0.9818}, 'coverage_95': {'pit_recal_tail': 0.957, 'incumbent': 0.93, 'max_width': 0.9967}, 'coverage_99': {'pit_recal_tail': 0.9879, 'incumbent': 0.93, 'max_width': 0.9967}}
- tail channel (`pit_recal_tail` − `pit_recal_pos`, pre-registered contrast): {'mean_delta': 0.00468, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None} · BH binding False
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foil_respects_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'pit_recal_pos': {'arm': 2.36648, 'own_form_oracle': 2.36354, 'matched_n': 2.36796, 'oracle_beats_matched_n': True}, 'pit_recal_tail': {'arm': 2.36179, 'own_form_oracle': 2.35873, 'matched_n': 2.36352, 'oracle_beats_matched_n': True}, 'level_widen': {'arm': 2.36566, 'own_form_oracle': 2.36551, 'matched_n': 2.36566, 'oracle_beats_matched_n': True}, 'zscore_affine': {'arm': 2.36545, 'own_form_oracle': 2.36485, 'matched_n': 2.36451, 'oracle_beats_matched_n': False}}
- permutation: {'permuted_lift_vs_incumbent_mean': -0.23061, 'permuted_lift_p_one_sided': None}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0036, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True, 'interval_score_improves': True, 'pit_flatness_improves': True}

## WR — **UNDEFINED**

`pit_recal_tail` TIES `pit_recal_global` by +0.0054 CRPS (interval unevaluable)

| label                     |   mean_crps_q199 |
|:--------------------------|-----------------:|
| oracle__pit_recal_tail    |          2.43005 |
| oracle__pit_recal_pos     |          2.43287 |
| oracle__zscore_affine     |          2.43405 |
| matched_n__pit_recal_tail |          2.43619 |
| pit_recal_tail            |          2.43740 |
| matched_n__pit_recal_pos  |          2.43886 |
| oracle__pit_recal_global  |          2.44011 |
| pit_recal_pos             |          2.44024 |
| matched_n__zscore_affine  |          2.44125 |
| pit_recal_global          |          2.44285 |
| zscore_affine             |          2.44320 |
| oracle__level_widen       |          2.44351 |
| incumbent                 |          2.44431 |
| level_widen               |          2.44431 |
| matched_n__level_widen    |          2.44431 |
| permuted_recal            |          2.62793 |
| zero_width                |          3.36273 |
| max_width                 |          3.50078 |

- fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · BH binding False
- calibration gate: Winkler-80 delta vs incumbent +0.0282 (incumbent 15.67734 → winner 15.64915) · PIT max-decile-dev 0.01575 → 0.0121
- coverage (floor 0.8, never a target): {'coverage_80': 0.8682, 'n_rows': 3231, 'binomial_se': 0.007, 'blocking_shortfall': False} · map {'coverage_50': {'pit_recal_tail': 0.6481, 'incumbent': 0.6472, 'max_width': 0.9183}, 'coverage_80': {'pit_recal_tail': 0.8682, 'incumbent': 0.8567, 'max_width': 0.9861}, 'coverage_95': {'pit_recal_tail': 0.9681, 'incumbent': 0.9461, 'max_width': 0.9978}, 'coverage_99': {'pit_recal_tail': 0.9944, 'incumbent': 0.9461, 'max_width': 0.9978}}
- tail channel (`pit_recal_tail` − `pit_recal_pos`, pre-registered contrast): {'mean_delta': 0.00284, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None} · BH binding False
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foil_respects_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'pit_recal_pos': {'arm': 2.44024, 'own_form_oracle': 2.43287, 'matched_n': 2.43886, 'oracle_beats_matched_n': True}, 'pit_recal_tail': {'arm': 2.4374, 'own_form_oracle': 2.43005, 'matched_n': 2.43619, 'oracle_beats_matched_n': True}, 'level_widen': {'arm': 2.44431, 'own_form_oracle': 2.44351, 'matched_n': 2.44431, 'oracle_beats_matched_n': True}, 'zscore_affine': {'arm': 2.4432, 'own_form_oracle': 2.43405, 'matched_n': 2.44125, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_incumbent_mean': -0.18362, 'permuted_lift_p_one_sided': None}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0054, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True, 'interval_score_improves': True, 'pit_flatness_improves': True}

## TE — **UNDEFINED**

`pit_recal_tail` TIES `incumbent` by +0.0011 CRPS (interval unevaluable)

| label                     |   mean_crps_q199 |
|:--------------------------|-----------------:|
| pit_recal_tail            |          1.78529 |
| oracle__pit_recal_tail    |          1.78571 |
| matched_n__pit_recal_tail |          1.78593 |
| level_widen               |          1.78641 |
| incumbent                 |          1.78641 |
| oracle__level_widen       |          1.78641 |
| oracle__pit_recal_global  |          1.78693 |
| pit_recal_global          |          1.78716 |
| pit_recal_pos             |          1.78733 |
| zscore_affine             |          1.78759 |
| oracle__pit_recal_pos     |          1.78813 |
| matched_n__level_widen    |          1.78818 |
| matched_n__pit_recal_pos  |          1.78832 |
| matched_n__zscore_affine  |          1.78877 |
| oracle__zscore_affine     |          1.78988 |
| permuted_recal            |          1.90639 |
| zero_width                |          2.44472 |
| max_width                 |          2.55497 |

- fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · BH binding False
- calibration gate: Winkler-80 delta vs incumbent -0.0109 (incumbent 11.88603 → winner 11.89691) · PIT max-decile-dev 0.01386 → 0.01231
- coverage (floor 0.8, never a target): {'coverage_80': 0.8784, 'n_rows': 1941, 'binomial_se': 0.0091, 'blocking_shortfall': False} · map {'coverage_50': {'pit_recal_tail': 0.7007, 'incumbent': 0.6997, 'max_width': 0.9181}, 'coverage_80': {'pit_recal_tail': 0.8784, 'incumbent': 0.8774, 'max_width': 0.984}, 'coverage_95': {'pit_recal_tail': 0.9696, 'incumbent': 0.9541, 'max_width': 0.9974}, 'coverage_99': {'pit_recal_tail': 0.9897, 'incumbent': 0.9541, 'max_width': 0.9974}}
- tail channel (`pit_recal_tail` − `pit_recal_pos`, pre-registered contrast): {'mean_delta': 0.00204, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None} · BH binding False
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': False, 'oracle_floors_respected_at_matched_n': False, 'foil_respects_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'pit_recal_pos': {'arm': 1.78733, 'own_form_oracle': 1.78813, 'matched_n': 1.78832, 'oracle_beats_matched_n': True}, 'pit_recal_tail': {'arm': 1.78529, 'own_form_oracle': 1.78571, 'matched_n': 1.78593, 'oracle_beats_matched_n': True}, 'level_widen': {'arm': 1.78641, 'own_form_oracle': 1.78641, 'matched_n': 1.78818, 'oracle_beats_matched_n': True}, 'zscore_affine': {'arm': 1.78759, 'own_form_oracle': 1.78988, 'matched_n': 1.78877, 'oracle_beats_matched_n': False}}
- permutation: {'permuted_lift_vs_incumbent_mean': -0.11998, 'permuted_lift_p_one_sided': None}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0011, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': False, 'coverage_floor_ok': True, 'interval_score_improves': False, 'pit_flatness_improves': True}

## Null-state classification

```json
{
  "QB": {
    "state": "UNDEFINED",
    "reason": "`nf_margin1_QB_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "RB": {
    "state": "UNDEFINED",
    "reason": "`nf_margin1_RB_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "WR": {
    "state": "UNDEFINED",
    "reason": "`nf_margin1_WR_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "TE": {
    "state": "UNDEFINED",
    "reason": "`nf_margin1_TE_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
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