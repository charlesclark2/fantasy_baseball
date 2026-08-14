# NF-W7b — DST dependence successor: joint/copula draw over the co-moving component legs (§0.5)

**Generated:** 2026-08-14T18:00:20+00:00 · **folds:** 2 (2025H1…2025H2, the NF-W1 axis verbatim) · **team-weeks:** 5278 · marginals FROZEN to NF-W7's Layer-A winners (asserted against the committed record)

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held**. This story adds ONLY a dependence structure over NF-W7's frozen component marginals; the coverage(80) floor and the three foils are NF-W7's verbatim (⛔ the floor may not move — NF-D18/E2.1-r). Every direction word is derived at report time, failing closed to `TIES` (NF-W2e).

**PIT gate (dst):** 175 weeks / 5278 records; 0 rows dropped fail-closed.

## ⭐ Headline

- **`dst_points` (joint draw): UNDEFINED** — winner `joint_raw`
- coverage(80): winner **0.8217** vs floor 0.8 (n=544, blocking_shortfall=False) · independent draw 0.7629 (NF-W7 recorded 0.7603) · comonotone 0.9467

`joint_raw` TIES `foil_direct` by +0.0845 CRPS (interval unevaluable)

| label                     |   mean_crps_q199 |
|:--------------------------|-----------------:|
| oracle__foil_direct       |           1.6965 |
| oracle__joint_raw         |           2.4600 |
| oracle__joint_factor      |           2.4607 |
| oracle__joint_rankcorr    |           2.4617 |
| oracle__joint_double      |           2.4691 |
| joint_raw                 |           2.6329 |
| joint_double              |           2.6351 |
| joint_rankcorr            |           2.6355 |
| joint_factor              |           2.6361 |
| assembled_indep           |           2.6593 |
| foil_direct               |           2.7175 |
| oracle__foil_board_eb     |           2.7211 |
| oracle__foil_climatology  |           2.7220 |
| foil_board_eb             |           2.7316 |
| foil_climatology          |           2.7363 |
| permuted_direct           |           2.8101 |
| assembled_comonotone      |           2.8834 |
| zero_width                |           3.8101 |
| max_width                 |           4.0681 |
| nihilist_zero             |           5.9259 |
| matched_n__joint_double   |           6.3149 |
| matched_n__joint_raw      |           6.3273 |
| matched_n__joint_rankcorr |           6.3339 |
| matched_n__joint_factor   |           6.3359 |

- fold wins 2/2 (clause requires None) · PBO None (7-config eligible field) · DSR None (4-arm declared family) · p None · BH False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 5.9259, 'zero_width': 3.8101, 'max_width': 4.0681, 'assembled_comonotone': 2.8834}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'joint_rankcorr': {'arm': 2.6355, 'own_form_oracle': 2.4617, 'matched_n': 6.3339}, 'joint_factor': {'arm': 2.6361, 'own_form_oracle': 2.4607, 'matched_n': 6.3359}, 'joint_raw': {'arm': 2.6329, 'own_form_oracle': 2.46, 'matched_n': 6.3273}, 'joint_double': {'arm': 2.6351, 'own_form_oracle': 2.4691, 'matched_n': 6.3149}}
- permutation: {'permuted_lift_vs_foil_mean': -0.0926, 'permuted_lift_p_one_sided': None}
- coverage by label: {'joint_rankcorr': {'coverage': 0.8125, 'n_rows': 544, 'binomial_se': 0.0171, 'blocking_shortfall': False}, 'joint_factor': {'coverage': 0.8107, 'n_rows': 544, 'binomial_se': 0.0171, 'blocking_shortfall': False}, 'joint_raw': {'coverage': 0.8217, 'n_rows': 544, 'binomial_se': 0.0171, 'blocking_shortfall': False}, 'joint_double': {'coverage': 0.8548, 'n_rows': 544, 'binomial_se': 0.0171, 'blocking_shortfall': False}, 'assembled_indep': {'coverage': 0.7629, 'n_rows': 544, 'binomial_se': 0.0171, 'blocking_shortfall': False}, 'assembled_comonotone': {'coverage': 0.9467, 'n_rows': 544, 'binomial_se': 0.0171, 'blocking_shortfall': False}}
- ⭐ dependence clauses: {'incumbent_refusal_reproduces': False, 'dependence_moves_coverage': True, 'beats_indep_on_coverage': True}
- Δcrps vs the refused independent draw: +0.0263 (winner minus-side positive = the joint draw also SCORES better than indep)
- NF-W7 reproduction (report-only): {'recorded_indep_crps': 2.6975, 'measured_indep_crps': 2.6593, 'recorded_indep_cov80': 0.7603, 'measured_indep_cov80': 0.7629}
- capture-era (2025) fold deltas, report-only (NF-W2d): {'2025H1': 0.0974, '2025H2': 0.0716}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True, 'incumbent_refusal_reproduces': False, 'dependence_moves_coverage': True, 'beats_indep_on_coverage': True}
- null state: **UNDEFINED** — `nf_w7b_dst_points_joint`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do. Re-test: 2 more fold(s) — i.e. a window of 7 seasons
- instrument verdict recorded beside: {'state': 'UNDEFINED', 'reason': '`nf_w7b_dst_points_joint`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.', 'retest_trigger': '2 more fold(s) — i.e. a window of 7 seasons'}
- gate sensitivity (NF-D15 (g″)): {'waived': [], 'still_refusing': ['fold_consistency', 'pbo_ok', 'dsr_ok', 'fdr_ok', 'incumbent_refusal_reproduces'], 'ships_without_waived_checks': False}

## The estimated dependence structure (train-side Σ̂, per fold)

Named pairs are latent-scale correlations under the frozen marginals (model-residual scale for `joint_rankcorr`, raw-outcome Spearman→Gaussian for `joint_raw`). A NEGATIVE sacks~PA / int~PA correlation is the co-movement the independent draw ignored: a dominant defensive day produces counting stats AND a low PA tier together.

### `joint_rankcorr`

|        |   def_sacks~pa_bucket |   def_int~pa_bucket |   def_sacks~def_int |   def_int~def_fumble_rec |   dst_td~def_int |   mean_abs_offdiag |
|:-------|----------------------:|--------------------:|--------------------:|-------------------------:|-----------------:|-------------------:|
| 2025H1 |                -0.302 |              -0.221 |               0.065 |                    0.017 |            0.163 |              0.059 |
| 2025H2 |                -0.305 |              -0.219 |               0.064 |                    0.022 |            0.165 |              0.059 |

### `joint_factor`

|        |   def_sacks~pa_bucket |   def_int~pa_bucket |   def_sacks~def_int |   def_int~def_fumble_rec |   dst_td~def_int |   mean_abs_offdiag |
|:-------|----------------------:|--------------------:|--------------------:|-------------------------:|-----------------:|-------------------:|
| 2025H1 |                -0.298 |              -0.199 |               0.112 |                    0.053 |            0.022 |              0.053 |
| 2025H2 |                -0.300 |              -0.198 |               0.112 |                    0.054 |            0.023 |              0.054 |

### `joint_raw`

|        |   def_sacks~pa_bucket |   def_int~pa_bucket |   def_sacks~def_int |   def_int~def_fumble_rec |   dst_td~def_int |   mean_abs_offdiag |
|:-------|----------------------:|--------------------:|--------------------:|-------------------------:|-----------------:|-------------------:|
| 2025H1 |                -0.348 |              -0.260 |               0.082 |                    0.036 |            0.283 |              0.082 |
| 2025H2 |                -0.350 |              -0.263 |               0.085 |                    0.042 |            0.280 |              0.082 |

### `joint_double`

|        |   def_sacks~pa_bucket |   def_int~pa_bucket |   def_sacks~def_int |   def_int~def_fumble_rec |   dst_td~def_int |   mean_abs_offdiag |
|:-------|----------------------:|--------------------:|--------------------:|-------------------------:|-----------------:|-------------------:|
| 2025H1 |                -0.604 |              -0.441 |               0.130 |                    0.034 |            0.326 |              0.118 |
| 2025H2 |                -0.609 |              -0.438 |               0.127 |                    0.044 |            0.330 |              0.118 |

- randomized-PIT flatness by fold (report-only, winner + indep): {'joint_raw': [{'max_decile_dev': 0.02962962962962963, 'n': 270}, {'max_decile_dev': 0.020437956204379562, 'n': 274}], 'assembled_indep': [{'max_decile_dev': 0.07407407407407407, 'n': 270}, {'max_decile_dev': 0.038686131386861305, 'n': 274}]}

## Pre-registration echo

```json
{
  "story": "NF-W7b",
  "target": "dst_points",
  "real_arms": [
    "joint_rankcorr",
    "joint_factor",
    "joint_raw",
    "joint_double"
  ],
  "foils": [
    "foil_climatology",
    "foil_board_eb",
    "foil_direct"
  ],
  "eligible": [
    "joint_rankcorr",
    "joint_factor",
    "joint_raw",
    "joint_double",
    "foil_climatology",
    "foil_board_eb",
    "foil_direct"
  ],
  "anchors": [
    "nihilist_zero",
    "zero_width",
    "max_width",
    "assembled_comonotone",
    "assembled_indep",
    "permuted_direct",
    "oracle__joint_rankcorr",
    "oracle__joint_factor",
    "oracle__joint_raw",
    "oracle__joint_double",
    "matched_n__joint_rankcorr",
    "matched_n__joint_factor",
    "matched_n__joint_raw",
    "matched_n__joint_double",
    "oracle__foil_climatology",
    "oracle__foil_board_eb",
    "oracle__foil_direct"
  ],
  "degenerates": [
    "nihilist_zero",
    "zero_width",
    "max_width",
    "assembled_comonotone"
  ],
  "component_legs": [
    "def_sacks",
    "def_int",
    "def_fumble_rec",
    "dst_td",
    "def_safety",
    "def_blocked_kick",
    "pa_bucket"
  ],
  "comonotone_flip": [
    false,
    false,
    false,
    false,
    false,
    false,
    true
  ],
  "double_scale": 2.0,
  "frozen_marginals": {
    "def_sacks": "negbin_glm",
    "def_int": "negbin_glm",
    "def_fumble_rec": "negbin_glm",
    "dst_td": "eb_pois",
    "def_safety": "hurdle_pois",
    "def_blocked_kick": "eb_pois",
    "pa_bucket": "ordered_logit"
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
  "purge_weeks": 2,
  "pbo_max": 0.2,
  "dsr_min": 0.95,
  "fdr_q": 0.1,
  "fdr_families": {
    "downstream": [
      "dst_points_joint"
    ]
  },
  "coverage_floor": 0.8,
  "coverage_block_se": 3.0,
  "assembly_draws": 4000,
  "statistical_checks": [
    "beats_foil",
    "fold_consistency",
    "pbo_ok",
    "dsr_ok",
    "fdr_ok",
    "coverage_floor_ok"
  ],
  "anchor_checks": [
    "degenerates_lose",
    "permutation_behaves",
    "oracle_floors_respected",
    "incumbent_refusal_reproduces",
    "dependence_moves_coverage",
    "beats_indep_on_coverage"
  ],
  "min_estimation_rows": 50
}
```