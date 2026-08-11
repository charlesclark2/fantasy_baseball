# NF-W5 — opportunity allocation on the JOINT gate (§0.5 bake-off + the NF-W8 decision)

**Generated:** 2026-08-11T04:30:07+00:00 · **folds:** 8 half-season blocks (2022H1…2025H2, the NF-W1 axis on the NF-W2d two-era matrix) · **player-weeks:** 84553 · **team-weeks scored:** 2174

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (serving is NF-W8 / NF-C6 Ph2). Primary metric is sample-based **team-total CRPS** (roster-grain lineup CRPS; S=512, common random numbers); energy + variogram scores are co-reported and never select. Marginals are PINNED to the injury-aware champion — every construction differs ONLY in the copula (the Sklar split), asserted numerically per fold. Every direction word below is three-way and **derived from the interval at report time**, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-W5):** 532 game-groups / 183314 records checked; 0 rows dropped fail-closed.

## ⭐ THE NF-W8 DECISION (the story's deliverable)

# **NO** — the ceiling is not statistically demonstrable at this design (CI95 [-0.00597, 0.14846], fold wins 6, BH binding True) — and an upward-biased estimator that still cannot demonstrate a ceiling is a conservative NO

- decision rule (pre-registered): stat_ok (CI>0 ∧ fold clause ∧ BH binding) then bands NO < 2.0% ≤ MARGINAL < 5.0% ≤ YES on ceiling_pct.
- context: the NF-W3 environment ceiling was 2.0–3.1% of champion CRPS (recorded as 'cannot justify the chain alone'); the NF-W4 availability ceiling was 8.1–27.8% (largest single error source, forecastable slice already priced).

## ⭐ Oracle first — the joint-allocation ceiling

Best peeking form: `empirical_role_resample` — `oracle__empirical_role_resample` TIES `independence` by +0.0712 CRPS (CI95 [-0.0060, +0.1485] spans zero) = **0.543%** of the independence team_total_crps (13.11105), fold wins 6/8 (clause requires 6), p 0.0327, BH binding True.

| form                    |   mean_delta | ci95                |   fold_wins |
|:------------------------|-------------:|:--------------------|------------:|
| constant_rho            |      0.04938 | [0.0102, 0.08856]   |           6 |
| gauss_pos_factor        |      0.06043 | [0.0191, 0.10175]   |           7 |
| gauss_pos_pairwise      |      0.06189 | [0.01613, 0.10765]  |           7 |
| dirichlet_alloc         |     -0.02516 | [-0.18569, 0.13537] |           2 |
| empirical_role_resample |      0.07124 | [-0.00597, 0.14846] |           6 |

- co-metric ceilings (report-only): {'energy_score': {'mean_delta': -0.03829, 'ci95': [-0.05554, -0.02103], 'pct_of_independence': -0.27}, 'variogram_score': {'mean_delta': -0.6699, 'ci95': [-0.91241, -0.42739], 'pct_of_independence': -0.4}}
- estimator note: max over the per-form peeking oracles — upward-biased by selection over the declared forms; the bias FAVORS a YES, so a NO is conservative (pre-registered).
- PBO: UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched field; declared before the run (the NF-W3/W4 rule).
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.1191, 'legacy_mean_delta': 0.0553, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}

## The mechanism, model-free — realized same-team PIT correlation by position pair

| pair   |   r_pooled |   n_pairs |   n_team_weeks |
|:-------|-----------:|----------:|---------------:|
| QB|QB  |    -0.1677 |      4492 |           2174 |
| QB|RB  |     0.0127 |     21692 |           2174 |
| QB|TE  |     0.0565 |     19231 |           2174 |
| QB|WR  |     0.0726 |     32335 |           2174 |
| RB|RB  |    -0.0376 |     13352 |           2174 |
| RB|TE  |    -0.0018 |     30001 |           2174 |
| RB|WR  |    -0.0027 |     50412 |           2174 |
| TE|TE  |    -0.0041 |     10088 |           2174 |
| TE|WR  |     0.0038 |     45026 |           2174 |
| WR|WR  |    -0.0002 |     32096 |           2174 |

## The arm bake-off (secondary to the decision)

### winner `empirical_role_resample` vs best foil `constant_rho` — **POWER_LIMITED**

`empirical_role_resample` BEATS `constant_rho` by +0.0812 CRPS (CI95 [+0.0500, +0.1125] excludes zero)

| label                              |   mean_team_total_crps |
|:-----------------------------------|-----------------------:|
| matched_n__empirical_role_resample |               13.02129 |
| empirical_role_resample            |               13.02604 |
| oracle__empirical_role_resample    |               13.03981 |
| oracle__gauss_pos_pairwise         |               13.04917 |
| oracle__gauss_pos_factor           |               13.05063 |
| oracle__constant_rho               |               13.06168 |
| matched_n__gauss_pos_factor        |               13.08601 |
| gauss_pos_factor                   |               13.09067 |
| matched_n__gauss_pos_pairwise      |               13.09327 |
| gauss_pos_pairwise                 |               13.09755 |
| constant_rho                       |               13.10727 |
| shuffled_teams                     |               13.10753 |
| independence                       |               13.11105 |
| oracle__dirichlet_alloc            |               13.13621 |
| matched_n__dirichlet_alloc         |               13.23821 |
| dirichlet_alloc                    |               13.37847 |
| comonotonic                        |               18.30037 |

- fold wins 8/8 (clause requires 6) · PBO 0.0 · DSR 0.7689 · p 0.0002 · BH own-family True / pooled True (binding True)
- anchors: {'comonotonic_loses': True, 'winner_beats_shuffled': True, 'shuffled_lift_not_significant': True, 'no_arm_beats_own_oracle': False, 'oracle_floors_respected_at_matched_n': False, 'foil_respects_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) + matched-n capacity control (NF1.9 (f)): {'gauss_pos_factor': {'arm': 13.09067, 'own_form_oracle': 13.05063, 'matched_n': 13.08601, 'oracle_beats_matched_n': True}, 'gauss_pos_pairwise': {'arm': 13.09755, 'own_form_oracle': 13.04917, 'matched_n': 13.09327, 'oracle_beats_matched_n': True}, 'dirichlet_alloc': {'arm': 13.37847, 'own_form_oracle': 13.13621, 'matched_n': 13.23821, 'oracle_beats_matched_n': True}, 'empirical_role_resample': {'arm': 13.02604, 'own_form_oracle': 13.03981, 'matched_n': 13.02129, 'oracle_beats_matched_n': False}}
- shuffle: {'shuffled_lift_vs_independence_mean': 0.00352, 'shuffled_lift_p_one_sided': 0.097} · team-total coverage(80) {'winner_coverage_80': 0.7061, 'n_rows': 2174, 'binomial_se': 0.0086, 'blocking_shortfall': True}
- co-metrics (never select): {'energy_score': {'empirical_role_resample': 14.22976, 'constant_rho': 14.24813, 'independence': 14.2484, 'comonotonic': 15.63298}, 'variogram_score': {'empirical_role_resample': 165.39705, 'constant_rho': 165.52846, 'independence': 165.53058, 'comonotonic': 191.56525}}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': False, 'coverage_floor_ok': False}
- ⚠️ **field-shrink remedy is SUSPECT — NOT ADVICE** — the instrument suggests a smaller field, but this story's family of 4 arms was PRE-REGISTERED as the minimum §0.5 field (≥3 classes + a direct-learned foil). ⛔ Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one.

## Marginal identity (the Sklar guard, §10.1A made structural)

| fold   |   spread |   tolerance |   exclusions |   team_weeks |
|:-------|---------:|------------:|-------------:|-------------:|
| 2022H1 |  0.00795 |        0.02 |            0 |          272 |
| 2022H2 |  0.00703 |        0.02 |            0 |          270 |
| 2023H1 |  0.0074  |        0.02 |            0 |          272 |
| 2023H2 |  0.00641 |        0.02 |            0 |          272 |
| 2024H1 |  0.0053  |        0.02 |            0 |          276 |
| 2024H2 |  0.00587 |        0.02 |            0 |          268 |
| 2025H1 |  0.00684 |        0.02 |            0 |          270 |
| 2025H2 |  0.00606 |        0.02 |            0 |          274 |

## Null-state classification

```json
{
  "arm": {
    "state": "POWER_LIMITED",
    "reason": "`nf_w5_joint_alloc_crps`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it \u2014 DSR alone needs 79 folds against 8 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
    "retest_trigger": "+71 folds for the DSR gate, OR a field of \u22642 arms at the CURRENT fold count",
    "field_shrink_flag": {
      "proposed_field_size": 2,
      "declared_family_size": 4,
      "status": "SUSPECT \u2014 NOT ADVICE",
      "note": "the instrument suggests a smaller field, but this story's family of 4 arms was PRE-REGISTERED as the minimum \u00a70.5 field (\u22653 classes + a direct-learned foil). \u26d4 Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one."
    }
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