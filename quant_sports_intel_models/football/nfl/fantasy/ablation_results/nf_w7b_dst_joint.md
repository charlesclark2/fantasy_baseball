# NF-W7b — DST dependence successor: joint/copula draw over the co-moving component legs (§0.5)

**Generated:** 2026-08-14T18:07:28+00:00 · **folds:** 8 (2022H1…2025H2, the NF-W1 axis verbatim) · **team-weeks:** 5278 · marginals FROZEN to NF-W7's Layer-A winners (asserted against the committed record)

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held**. This story adds ONLY a dependence structure over NF-W7's frozen component marginals; the coverage(80) floor and the three foils are NF-W7's verbatim (⛔ the floor may not move — NF-D18/E2.1-r). Every direction word is derived at report time, failing closed to `TIES` (NF-W2e).

**PIT gate (dst):** 175 weeks / 5278 records; 0 rows dropped fail-closed.

## ⭐ Headline

- **`dst_points` (joint draw): SHIP** — winner `joint_raw`
- coverage(80): winner **0.8298** vs floor 0.8 (n=2174, blocking_shortfall=False) · independent draw 0.7562 (NF-W7 recorded 0.7603) · comonotone 0.9457

`joint_raw` BEATS `foil_direct` by +0.0613 CRPS (CI95 [+0.0362, +0.0864] excludes zero)

| label                     |   mean_crps_q199 |
|:--------------------------|-----------------:|
| oracle__foil_direct       |           1.6870 |
| oracle__joint_raw         |           2.4880 |
| oracle__joint_factor      |           2.4893 |
| oracle__joint_rankcorr    |           2.4898 |
| oracle__joint_double      |           2.4939 |
| joint_raw                 |           2.6700 |
| joint_double              |           2.6721 |
| joint_rankcorr            |           2.6730 |
| joint_factor              |           2.6733 |
| assembled_indep           |           2.6973 |
| oracle__foil_climatology  |           2.7252 |
| oracle__foil_board_eb     |           2.7301 |
| foil_direct               |           2.7313 |
| foil_climatology          |           2.7390 |
| foil_board_eb             |           2.7450 |
| permuted_direct           |           2.8281 |
| assembled_comonotone      |           2.9247 |
| zero_width                |           3.8158 |
| max_width                 |           4.0852 |
| nihilist_zero             |           6.2188 |
| matched_n__joint_double   |           9.0141 |
| matched_n__joint_raw      |           9.0262 |
| matched_n__joint_rankcorr |           9.0336 |
| matched_n__joint_factor   |           9.0362 |

- fold wins 8/8 (clause requires 6) · PBO 0.0 (7-config eligible field) · DSR 0.997 (4-arm declared family) · p 0.0003 · BH True
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 6.2188, 'zero_width': 3.8158, 'max_width': 4.0852, 'assembled_comonotone': 2.9247}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'joint_rankcorr': {'arm': 2.673, 'own_form_oracle': 2.4898, 'matched_n': 9.0336}, 'joint_factor': {'arm': 2.6733, 'own_form_oracle': 2.4893, 'matched_n': 9.0362}, 'joint_raw': {'arm': 2.67, 'own_form_oracle': 2.488, 'matched_n': 9.0262}, 'joint_double': {'arm': 2.6721, 'own_form_oracle': 2.4939, 'matched_n': 9.0141}}
- permutation: {'permuted_lift_vs_foil_mean': -0.0969, 'permuted_lift_p_one_sided': 0.9998}
- coverage by label: {'joint_rankcorr': {'coverage': 0.8155, 'n_rows': 2174, 'binomial_se': 0.0086, 'blocking_shortfall': False}, 'joint_factor': {'coverage': 0.8169, 'n_rows': 2174, 'binomial_se': 0.0086, 'blocking_shortfall': False}, 'joint_raw': {'coverage': 0.8298, 'n_rows': 2174, 'binomial_se': 0.0086, 'blocking_shortfall': False}, 'joint_double': {'coverage': 0.8597, 'n_rows': 2174, 'binomial_se': 0.0086, 'blocking_shortfall': False}, 'assembled_indep': {'coverage': 0.7562, 'n_rows': 2174, 'binomial_se': 0.0086, 'blocking_shortfall': True}, 'assembled_comonotone': {'coverage': 0.9457, 'n_rows': 2174, 'binomial_se': 0.0086, 'blocking_shortfall': False}}
- ⭐ dependence clauses: {'incumbent_refusal_reproduces': True, 'dependence_moves_coverage': True, 'beats_indep_on_coverage': True}
- Δcrps vs the refused independent draw: +0.0273 (winner minus-side positive = the joint draw also SCORES better than indep)
- NF-W7 reproduction (report-only): {'recorded_indep_crps': 2.6975, 'measured_indep_crps': 2.6973, 'recorded_indep_cov80': 0.7603, 'measured_indep_cov80': 0.7562}
- capture-era (2025) fold deltas, report-only (NF-W2d): {'2025H1': 0.0974, '2025H2': 0.0716}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': True, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True, 'incumbent_refusal_reproduces': True, 'dependence_moves_coverage': True, 'beats_indep_on_coverage': True}

## The estimated dependence structure (train-side Σ̂, per fold)

Named pairs are latent-scale correlations under the frozen marginals (model-residual scale for `joint_rankcorr`, raw-outcome Spearman→Gaussian for `joint_raw`). A NEGATIVE sacks~PA / int~PA correlation is the co-movement the independent draw ignored: a dominant defensive day produces counting stats AND a low PA tier together.

### `joint_rankcorr`

|        |   def_sacks~pa_bucket |   def_int~pa_bucket |   def_sacks~def_int |   def_int~def_fumble_rec |   dst_td~def_int |   mean_abs_offdiag |
|:-------|----------------------:|--------------------:|--------------------:|-------------------------:|-----------------:|-------------------:|
| 2022H1 |                -0.297 |              -0.235 |               0.049 |                    0.023 |            0.166 |              0.060 |
| 2022H2 |                -0.298 |              -0.238 |               0.058 |                    0.030 |            0.161 |              0.059 |
| 2023H1 |                -0.291 |              -0.228 |               0.058 |                    0.026 |            0.165 |              0.059 |
| 2023H2 |                -0.294 |              -0.230 |               0.068 |                    0.029 |            0.166 |              0.060 |
| 2024H1 |                -0.298 |              -0.230 |               0.069 |                    0.023 |            0.169 |              0.060 |
| 2024H2 |                -0.301 |              -0.224 |               0.068 |                    0.019 |            0.169 |              0.060 |
| 2025H1 |                -0.302 |              -0.221 |               0.065 |                    0.017 |            0.163 |              0.059 |
| 2025H2 |                -0.305 |              -0.219 |               0.064 |                    0.022 |            0.165 |              0.059 |

### `joint_factor`

|        |   def_sacks~pa_bucket |   def_int~pa_bucket |   def_sacks~def_int |   def_int~def_fumble_rec |   dst_td~def_int |   mean_abs_offdiag |
|:-------|----------------------:|--------------------:|--------------------:|-------------------------:|-----------------:|-------------------:|
| 2022H1 |                -0.294 |              -0.211 |               0.106 |                    0.054 |            0.020 |              0.055 |
| 2022H2 |                -0.296 |              -0.215 |               0.110 |                    0.057 |            0.018 |              0.054 |
| 2023H1 |                -0.287 |              -0.207 |               0.110 |                    0.054 |            0.021 |              0.053 |
| 2023H2 |                -0.286 |              -0.212 |               0.118 |                    0.056 |            0.027 |              0.055 |
| 2024H1 |                -0.292 |              -0.211 |               0.116 |                    0.054 |            0.026 |              0.054 |
| 2024H2 |                -0.296 |              -0.205 |               0.114 |                    0.055 |            0.024 |              0.054 |
| 2025H1 |                -0.298 |              -0.199 |               0.112 |                    0.053 |            0.022 |              0.053 |
| 2025H2 |                -0.300 |              -0.198 |               0.112 |                    0.054 |            0.023 |              0.054 |

### `joint_raw`

|        |   def_sacks~pa_bucket |   def_int~pa_bucket |   def_sacks~def_int |   def_int~def_fumble_rec |   dst_td~def_int |   mean_abs_offdiag |
|:-------|----------------------:|--------------------:|--------------------:|-------------------------:|-----------------:|-------------------:|
| 2022H1 |                -0.344 |              -0.273 |               0.075 |                    0.041 |            0.294 |              0.088 |
| 2022H2 |                -0.347 |              -0.275 |               0.084 |                    0.046 |            0.291 |              0.088 |
| 2023H1 |                -0.341 |              -0.264 |               0.081 |                    0.038 |            0.285 |              0.084 |
| 2023H2 |                -0.341 |              -0.268 |               0.085 |                    0.041 |            0.289 |              0.084 |
| 2024H1 |                -0.346 |              -0.267 |               0.085 |                    0.038 |            0.285 |              0.084 |
| 2024H2 |                -0.346 |              -0.262 |               0.083 |                    0.035 |            0.283 |              0.082 |
| 2025H1 |                -0.348 |              -0.260 |               0.082 |                    0.036 |            0.283 |              0.082 |
| 2025H2 |                -0.350 |              -0.263 |               0.085 |                    0.042 |            0.280 |              0.082 |

### `joint_double`

|        |   def_sacks~pa_bucket |   def_int~pa_bucket |   def_sacks~def_int |   def_int~def_fumble_rec |   dst_td~def_int |   mean_abs_offdiag |
|:-------|----------------------:|--------------------:|--------------------:|-------------------------:|-----------------:|-------------------:|
| 2022H1 |                -0.595 |              -0.470 |               0.098 |                    0.046 |            0.333 |              0.120 |
| 2022H2 |                -0.597 |              -0.475 |               0.116 |                    0.060 |            0.322 |              0.118 |
| 2023H1 |                -0.583 |              -0.457 |               0.116 |                    0.052 |            0.331 |              0.118 |
| 2023H2 |                -0.587 |              -0.461 |               0.136 |                    0.057 |            0.333 |              0.120 |
| 2024H1 |                -0.596 |              -0.459 |               0.137 |                    0.046 |            0.338 |              0.120 |
| 2024H2 |                -0.601 |              -0.449 |               0.135 |                    0.039 |            0.338 |              0.119 |
| 2025H1 |                -0.604 |              -0.441 |               0.130 |                    0.034 |            0.326 |              0.118 |
| 2025H2 |                -0.609 |              -0.438 |               0.127 |                    0.044 |            0.330 |              0.118 |

- randomized-PIT flatness by fold (report-only, winner + indep): {'joint_raw': [{'max_decile_dev': 0.028676470588235276, 'n': 272}, {'max_decile_dev': 0.025925925925925908, 'n': 270}, {'max_decile_dev': 0.028676470588235276, 'n': 272}, {'max_decile_dev': 0.03382352941176471, 'n': 272}, {'max_decile_dev': 0.04130434782608694, 'n': 276}, {'max_decile_dev': 0.04179104477611939, 'n': 268}, {'max_decile_dev': 0.02962962962962963, 'n': 270}, {'max_decile_dev': 0.020437956204379562, 'n': 274}], 'assembled_indep': [{'max_decile_dev': 0.028676470588235276, 'n': 272}, {'max_decile_dev': 0.029629629629629617, 'n': 270}, {'max_decile_dev': 0.07279411764705881, 'n': 272}, {'max_decile_dev': 0.09117647058823528, 'n': 272}, {'max_decile_dev': 0.07391304347826086, 'n': 276}, {'max_decile_dev': 0.09029850746268656, 'n': 268}, {'max_decile_dev': 0.07407407407407407, 'n': 270}, {'max_decile_dev': 0.038686131386861305, 'n': 274}]}

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