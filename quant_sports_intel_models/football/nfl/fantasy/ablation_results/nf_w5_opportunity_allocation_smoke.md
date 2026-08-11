# NF-W5 — opportunity allocation on the JOINT gate (§0.5 bake-off + the NF-W8 decision)

**Generated:** 2026-08-11T04:01:20+00:00 · **folds:** 2 half-season blocks (2025H1…2025H2, the NF-W1 axis on the NF-W2d two-era matrix) · **player-weeks:** 84553 · **team-weeks scored:** 544

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (serving is NF-W8 / NF-C6 Ph2). Primary metric is sample-based **team-total CRPS** (roster-grain lineup CRPS; S=512, common random numbers); energy + variogram scores are co-reported and never select. Marginals are PINNED to the injury-aware champion — every construction differs ONLY in the copula (the Sklar split), asserted numerically per fold. Every direction word below is three-way and **derived from the interval at report time**, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-W5):** 532 game-groups / 183314 records checked; 0 rows dropped fail-closed.

## ⭐ THE NF-W8 DECISION (the story's deliverable)

# **NO** — the ceiling is not statistically demonstrable at this design (CI95 [None, None], fold wins 2, BH binding False) — and an upward-biased estimator that still cannot demonstrate a ceiling is a conservative NO

- decision rule (pre-registered): stat_ok (CI>0 ∧ fold clause ∧ BH binding) then bands NO < 2.0% ≤ MARGINAL < 5.0% ≤ YES on ceiling_pct.
- context: the NF-W3 environment ceiling was 2.0–3.1% of champion CRPS (recorded as 'cannot justify the chain alone'); the NF-W4 availability ceiling was 8.1–27.8% (largest single error source, forecastable slice already priced).

## ⭐ Oracle first — the joint-allocation ceiling

Best peeking form: `empirical_role_resample` — `oracle__empirical_role_resample` TIES `independence` by +0.1191 CRPS (interval unevaluable) = **0.87%** of the independence team_total_crps (13.68882), fold wins 2/2 (clause requires None), p None, BH binding False.

| form                    |   mean_delta | ci95         |   fold_wins |
|:------------------------|-------------:|:-------------|------------:|
| constant_rho            |      0.06649 | [None, None] |           2 |
| gauss_pos_factor        |      0.08425 | [None, None] |           2 |
| gauss_pos_pairwise      |      0.07705 | [None, None] |           2 |
| dirichlet_alloc         |      0.05395 | [None, None] |           1 |
| empirical_role_resample |      0.11912 | [None, None] |           2 |

- co-metric ceilings (report-only): {'energy_score': {'mean_delta': -0.02726, 'ci95': [None, None], 'pct_of_independence': -0.19}, 'variogram_score': {'mean_delta': -0.88344, 'ci95': [None, None], 'pct_of_independence': -0.52}}
- estimator note: max over the per-form peeking oracles — upward-biased by selection over the declared forms; the bias FAVORS a YES, so a NO is conservative (pre-registered).
- PBO: UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W3/W4 rule).
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.1191, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}

## The mechanism, model-free — realized same-team PIT correlation by position pair

| pair   |   r_pooled |   n_pairs |   n_team_weeks |
|:-------|-----------:|----------:|---------------:|
| QB|QB  |    -0.2148 |      1125 |            544 |
| QB|RB  |     0.0105 |      5419 |            544 |
| QB|TE  |     0.0863 |      4869 |            544 |
| QB|WR  |     0.0754 |      8117 |            544 |
| RB|RB  |    -0.0531 |      3311 |            544 |
| RB|TE  |    -0.0119 |      7560 |            544 |
| RB|WR  |    -0.0024 |     12701 |            544 |
| TE|TE  |     0.0126 |      2609 |            544 |
| TE|WR  |     0.0034 |     11508 |            544 |
| WR|WR  |     0.0187 |      8121 |            544 |

## The arm bake-off (secondary to the decision)

### winner `empirical_role_resample` vs best foil `constant_rho` — **UNDEFINED**

`empirical_role_resample` TIES `constant_rho` by +0.0785 CRPS (interval unevaluable)

| label                              |   mean_team_total_crps |
|:-----------------------------------|-----------------------:|
| matched_n__empirical_role_resample |               13.49492 |
| oracle__empirical_role_resample    |               13.56970 |
| empirical_role_resample            |               13.59711 |
| oracle__gauss_pos_factor           |               13.60458 |
| oracle__gauss_pos_pairwise         |               13.61177 |
| oracle__constant_rho               |               13.62233 |
| oracle__dirichlet_alloc            |               13.63487 |
| matched_n__gauss_pos_factor        |               13.65049 |
| gauss_pos_factor                   |               13.65678 |
| matched_n__gauss_pos_pairwise      |               13.66913 |
| gauss_pos_pairwise                 |               13.67003 |
| constant_rho                       |               13.67558 |
| shuffled_teams                     |               13.68170 |
| independence                       |               13.68882 |
| matched_n__dirichlet_alloc         |               13.88344 |
| dirichlet_alloc                    |               13.97284 |
| comonotonic                        |               18.33628 |

- fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · BH own-family False / pooled False (binding False)
- anchors: {'comonotonic_loses': True, 'winner_beats_shuffled': True, 'shuffled_lift_not_significant': False, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foil_respects_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) + matched-n capacity control (NF1.9 (f)): {'gauss_pos_factor': {'arm': 13.65678, 'own_form_oracle': 13.60458, 'matched_n': 13.65049, 'oracle_beats_matched_n': True}, 'gauss_pos_pairwise': {'arm': 13.67003, 'own_form_oracle': 13.61177, 'matched_n': 13.66913, 'oracle_beats_matched_n': True}, 'dirichlet_alloc': {'arm': 13.97284, 'own_form_oracle': 13.63487, 'matched_n': 13.88344, 'oracle_beats_matched_n': True}, 'empirical_role_resample': {'arm': 13.59711, 'own_form_oracle': 13.5697, 'matched_n': 13.49492, 'oracle_beats_matched_n': False}}
- shuffle: {'shuffled_lift_vs_independence_mean': 0.00713, 'shuffled_lift_p_one_sided': None} · team-total coverage(80) {'winner_coverage_80': 0.6893, 'n_rows': 544, 'binomial_se': 0.0171, 'blocking_shortfall': True}
- co-metrics (never select): {'energy_score': {'empirical_role_resample': 14.39495, 'constant_rho': 14.41165, 'independence': 14.41312, 'comonotonic': 15.72341}, 'variogram_score': {'empirical_role_resample': 168.34104, 'constant_rho': 168.26196, 'independence': 168.27805, 'comonotonic': 194.01667}}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': False, 'oracle_floors_respected': True, 'coverage_floor_ok': False}

## Marginal identity (the Sklar guard, §10.1A made structural)

| fold   |   spread |   tolerance |   exclusions |   team_weeks |
|:-------|---------:|------------:|-------------:|-------------:|
| 2025H1 |  0.00684 |        0.02 |            0 |          270 |
| 2025H2 |  0.00606 |        0.02 |            0 |          274 |

## Null-state classification

```json
{
  "arm": {
    "state": "UNDEFINED",
    "reason": "`nf_w5_joint_alloc_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  }
}
```

## Pre-registration echo

```json
{
  "real_arms": [
    "gauss_pos_factor",
    "gauss_pos_pairwise",
    "dirichlet_alloc",
    "empirical_role_resample"
  ],
  "foils": [
    "independence",
    "constant_rho"
  ],
  "anchors": [
    "comonotonic",
    "shuffled_teams",
    "oracle__constant_rho",
    "oracle__gauss_pos_factor",
    "oracle__gauss_pos_pairwise",
    "oracle__dirichlet_alloc",
    "oracle__empirical_role_resample",
    "matched_n__gauss_pos_factor",
    "matched_n__gauss_pos_pairwise",
    "matched_n__dirichlet_alloc",
    "matched_n__empirical_role_resample"
  ],
  "eligible": [
    "gauss_pos_factor",
    "gauss_pos_pairwise",
    "dirichlet_alloc",
    "empirical_role_resample",
    "independence",
    "constant_rho"
  ],
  "parametrized_forms": [
    "constant_rho",
    "gauss_pos_factor",
    "gauss_pos_pairwise",
    "dirichlet_alloc",
    "empirical_role_resample"
  ],
  "primary_metric": "team_total_crps",
  "co_metrics": [
    "energy_score",
    "variogram_score"
  ],
  "n_samples": 512,
  "variogram_p": 0.5,
  "min_team_k": 2,
  "role_caps": {
    "QB": 2,
    "RB": 4,
    "WR": 5,
    "TE": 3
  },
  "marginal_identity_tol": 0.02,
  "ceiling_bands": [
    2.0,
    5.0
  ],
  "incumbent_of_position": {
    "QB": "inj_zero_leg",
    "RB": "inj_both",
    "WR": "inj_both",
    "TE": "inj_zero_leg"
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
    "arm": [
      "joint_alloc_arm"
    ],
    "ceiling": [
      "joint_alloc_ceiling"
    ]
  },
  "coverage_floor": 0.8,
  "capture_era_folds": [
    "2025H1",
    "2025H2"
  ],
  "seed": 20260811
}
```