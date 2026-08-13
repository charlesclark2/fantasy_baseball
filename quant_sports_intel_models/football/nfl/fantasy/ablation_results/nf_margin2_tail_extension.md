# NF-MARGIN2 — tail-extension-ONLY recalibration vs the champion (§0.5, 1-arm family)

**Generated:** 2026-08-13T03:21:59+00:00 · **folds:** 8 half-season blocks (2022H1…2025H2, the NF-W1 axis on the NF-W2d two-era matrix) · **player-weeks:** 34552

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (a clearing arm's serving path — attach the per-position tail betas to the served bank, no refit — is blocked on NF-C6 Ph2 + NF-G0). The MH2.2-legitimate successor to NF-MARGIN1: a FRESH registration of the single demonstrated contrast, on a construction NF-MARGIN1 never scored. Selection metric `crps_q199`; PIT accounting on the 199-level bank (the 39-level instrument is structurally blind to this arm). PBO UNDEFINED by design; DSR = PSR at a 1-arm field. Every direction word below is three-way and derived at report time, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-MARGIN2):** 532 game-groups / 183314 records checked; 0 rows dropped fail-closed.

**Verdict:** QB[CONSTRAINT_REFUSED] RB[SHIP] WR[CONSTRAINT_REFUSED] TE[SHIP]

## Construction facts (declared structurally INACTIVE — never counted as evidence)

Within-grid identity asserted every fold: Winkler-80, coverage(50/80/95) deltas vs the incumbent are IDENTICALLY ZERO by construction; only 8 of 199 eval columns (4/side beyond the champion grid) can differ. The coverage floor therefore cannot newly fire (NF-D20 (g⁗) — the active-clause count is what the gate's evidence rests on).

## Team-total re-check (independence copula, report-only — the NF-W5 loop)

| label     |    n |   coverage_80 |   share_below_q10 |   share_above_q90 |   binomial_se |
|:----------|-----:|--------------:|------------------:|------------------:|--------------:|
| tail_ext  | 2174 |        0.7052 |            0.1385 |            0.1564 |        0.0086 |
| incumbent | 2174 |        0.6794 |            0.1403 |            0.1803 |        0.0086 |

Reproduction anchor (report-only): incumbent team-total coverage(80) measured 0.6794 vs NF-MARGIN1's 0.6794 — REPRODUCED (tol 0.005).

## QB — **CONSTRAINT_REFUSED**

`tail_ext` BEATS `incumbent` by +0.0040 CRPS (CI95 [+0.0032, +0.0048] excludes zero)

| label               |   mean_crps_q199 |
|:--------------------|-----------------:|
| permuted_tail       |          2.40973 |
| over_ext            |          2.40996 |
| oracle__tail_ext    |          2.41007 |
| pooled_tail         |          2.41012 |
| tail_ext            |          2.41015 |
| matched_n__tail_ext |          2.41016 |
| incumbent           |          2.41416 |
| zero_width          |          3.24795 |
| max_width           |          3.25964 |

- fold wins 8/8 (clause requires 6) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) 1.0 · p 0.0 · BH True
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side): dev 0.08298 → 0.01024 (delta +0.07274) · p_below_eval/p_above_eval incumbent 0.03993/0.05305 → winner 0.00766/0.01258 · beyond-CHAMPION-grid mass (arm-invariant diagnostic, nominal 0.025/side) 0.05871/0.0536
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.825, 'n_rows': 5485, 'binomial_se': 0.0054, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'tail_ext': 0.825, 'incumbent': 0.825, 'over_ext': 0.825, 'max_width': 0.9441}, 'coverage_95': {'tail_ext': 0.911, 'incumbent': 0.911, 'over_ext': 0.911, 'max_width': 0.9809}, 'coverage_99': {'tail_ext': 0.9798, 'incumbent': 0.911, 'over_ext': 0.9996, 'max_width': 0.9809}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'marginal_share': {'mean_delta': 0.00443, 'ci95': [0.0032, 0.00565], 'fold_wins': 8, 'p_one_sided': 0.0}, 'alignment_share': {'mean_delta': -0.00042, 'ci95': [-0.00093, 0.0001], 'fold_wins': 2, 'p_one_sided': 0.9512}, 'conditioning_margin': {'mean_delta': -3e-05, 'ci95': [-9e-05, 3e-05], 'fold_wins': 2, 'p_one_sided': 0.877}, 'note': "marginal_share = incumbent − permuted_tail (the shuffle-surviving channel; EXPECTED positive — NF-D16 (2)); alignment_share = permuted_tail − tail_ext; conditioning_margin = pooled_tail − tail_ext (per-position conditioning's earn in the tail; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_loses': False, 'winner_beats_permuted': False, 'permuted_not_significantly_better': False, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- ⚠️ **REFUTED MAGNITUDE HYPOTHESIS (NF-D20):** `over_ext` (betas × 3.0, registered to lose) BEAT the fitted arm — the mean-excess fit UNDER-extends and the metric optimum lies beyond the fitted magnitude. Recorded as a decomposed refutation; the anchor stays an anchor (⛔ never re-labelled).
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 2.41015, 'own_form_oracle': 2.41007, 'matched_n': 2.41016, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': 0.00042, 'permuted_better_p_one_sided': 0.0488} · thin tail cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0043, 'legacy_mean_delta': 0.0039, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_champion': True, 'fold_consistency': True, 'dsr_ok': True, 'fdr_ok': True, 'coverage_floor_ok': True, 'degenerates_lose': False, 'permutation_not_better': False, 'oracle_floor_respected': True, 'tail_mass_toward_nominal': True}

## RB — **SHIP**

`tail_ext` BEATS `incumbent` by +0.0028 CRPS (CI95 [+0.0021, +0.0035] excludes zero)

| label               |   mean_crps_q199 |
|:--------------------|-----------------:|
| tail_ext            |          2.35729 |
| permuted_tail       |          2.35729 |
| oracle__tail_ext    |          2.35731 |
| matched_n__tail_ext |          2.35735 |
| pooled_tail         |          2.35738 |
| over_ext            |          2.35805 |
| incumbent           |          2.36012 |
| zero_width          |          3.23657 |
| max_width           |          3.32154 |

- fold wins 8/8 (clause requires 6) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) 1.0 · p 0.0 · BH True
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side): dev 0.06112 → 0.00362 (delta +0.0575) · p_below_eval/p_above_eval incumbent 0.02677/0.04435 → winner 0.00559/0.00803 · beyond-CHAMPION-grid mass (arm-invariant diagnostic, nominal 0.025/side) 0.04156/0.04516
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.845, 'n_rows': 8591, 'binomial_se': 0.0043, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'tail_ext': 0.8452, 'incumbent': 0.8452, 'over_ext': 0.8452, 'max_width': 0.9847}, 'coverage_95': {'tail_ext': 0.9335, 'incumbent': 0.9335, 'over_ext': 0.9335, 'max_width': 0.9958}, 'coverage_99': {'tail_ext': 0.9864, 'incumbent': 0.9335, 'over_ext': 0.9994, 'max_width': 0.9958}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'marginal_share': {'mean_delta': 0.00283, 'ci95': [0.00193, 0.00372], 'fold_wins': 8, 'p_one_sided': 0.0001}, 'alignment_share': {'mean_delta': 0.0, 'ci95': [-0.00021, 0.00022], 'fold_wins': 4, 'p_one_sided': 0.4884}, 'conditioning_margin': {'mean_delta': 8e-05, 'ci95': [4e-05, 0.00013], 'fold_wins': 8, 'p_one_sided': 0.0023}, 'note': "marginal_share = incumbent − permuted_tail (the shuffle-surviving channel; EXPECTED positive — NF-D16 (2)); alignment_share = permuted_tail − tail_ext; conditioning_margin = pooled_tail − tail_ext (per-position conditioning's earn in the tail; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_loses': True, 'winner_beats_permuted': True, 'permuted_not_significantly_better': True, 'no_arm_beats_own_oracle': False, 'oracle_floor_respected_at_matched_n': True}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 2.35729, 'own_form_oracle': 2.35731, 'matched_n': 2.35735, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': -0.0, 'permuted_better_p_one_sided': 0.5116} · thin tail cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0035, 'legacy_mean_delta': 0.0026, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_champion': True, 'fold_consistency': True, 'dsr_ok': True, 'fdr_ok': True, 'coverage_floor_ok': True, 'degenerates_lose': True, 'permutation_not_better': True, 'oracle_floor_respected': True, 'tail_mass_toward_nominal': True}

## WR — **CONSTRAINT_REFUSED**

`tail_ext` BEATS `incumbent` by +0.0032 CRPS (CI95 [+0.0027, +0.0038] excludes zero)

| label               |   mean_crps_q199 |
|:--------------------|-----------------:|
| permuted_tail       |          2.51083 |
| oracle__tail_ext    |          2.51092 |
| tail_ext            |          2.51102 |
| matched_n__tail_ext |          2.51104 |
| pooled_tail         |          2.51105 |
| over_ext            |          2.51159 |
| incumbent           |          2.51426 |
| zero_width          |          3.46621 |
| max_width           |          3.56004 |

- fold wins 8/8 (clause requires 6) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) 1.0 · p 0.0 · BH True
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side): dev 0.05736 → 0.00522 (delta +0.05214) · p_below_eval/p_above_eval incumbent 0.0216/0.04576 → winner 0.00437/0.00959 · beyond-CHAMPION-grid mass (arm-invariant diagnostic, nominal 0.025/side) 0.04155/0.04678
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.8541, 'n_rows': 12827, 'binomial_se': 0.0035, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'tail_ext': 0.854, 'incumbent': 0.854, 'over_ext': 0.854, 'max_width': 0.9891}, 'coverage_95': {'tail_ext': 0.9371, 'incumbent': 0.9371, 'over_ext': 0.9371, 'max_width': 0.9978}, 'coverage_99': {'tail_ext': 0.986, 'incumbent': 0.9371, 'over_ext': 0.9995, 'max_width': 0.9978}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'marginal_share': {'mean_delta': 0.00343, 'ci95': [0.00268, 0.00418], 'fold_wins': 8, 'p_one_sided': 0.0}, 'alignment_share': {'mean_delta': -0.00019, 'ci95': [-0.00037, -0.0], 'fold_wins': 2, 'p_one_sided': 0.9759}, 'conditioning_margin': {'mean_delta': 3e-05, 'ci95': [-3e-05, 9e-05], 'fold_wins': 5, 'p_one_sided': 0.1412}, 'note': "marginal_share = incumbent − permuted_tail (the shuffle-surviving channel; EXPECTED positive — NF-D16 (2)); alignment_share = permuted_tail − tail_ext; conditioning_margin = pooled_tail − tail_ext (per-position conditioning's earn in the tail; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_loses': True, 'winner_beats_permuted': False, 'permuted_not_significantly_better': False, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 2.51102, 'own_form_oracle': 2.51092, 'matched_n': 2.51104, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': 0.00019, 'permuted_better_p_one_sided': 0.0241} · thin tail cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0027, 'legacy_mean_delta': 0.0034, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_champion': True, 'fold_consistency': True, 'dsr_ok': True, 'fdr_ok': True, 'coverage_floor_ok': True, 'degenerates_lose': True, 'permutation_not_better': False, 'oracle_floor_respected': True, 'tail_mass_toward_nominal': True}

## TE — **SHIP**

`tail_ext` BEATS `incumbent` by +0.0015 CRPS (CI95 [+0.0013, +0.0018] excludes zero)

| label               |   mean_crps_q199 |
|:--------------------|-----------------:|
| oracle__tail_ext    |          1.72779 |
| matched_n__tail_ext |          1.72794 |
| pooled_tail         |          1.72805 |
| tail_ext            |          1.72813 |
| permuted_tail       |          1.72846 |
| over_ext            |          1.72937 |
| incumbent           |          1.72963 |
| zero_width          |          2.36975 |
| max_width           |          2.48597 |

- fold wins 8/8 (clause requires 6) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) 1.0 · p 0.0 · BH True
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side): dev 0.03694 → 0.00641 (delta +0.03053) · p_below_eval/p_above_eval incumbent 0.00837/0.03857 → winner 0.00196/0.00837 · beyond-CHAMPION-grid mass (arm-invariant diagnostic, nominal 0.025/side) 0.02863/0.03909
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.8821, 'n_rows': 7649, 'binomial_se': 0.0046, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'tail_ext': 0.8821, 'incumbent': 0.8821, 'over_ext': 0.8821, 'max_width': 0.9865}, 'coverage_95': {'tail_ext': 0.9577, 'incumbent': 0.9577, 'over_ext': 0.9577, 'max_width': 0.9988}, 'coverage_99': {'tail_ext': 0.9905, 'incumbent': 0.9577, 'over_ext': 0.9987, 'max_width': 0.9988}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'marginal_share': {'mean_delta': 0.00117, 'ci95': [0.00082, 0.00153], 'fold_wins': 8, 'p_one_sided': 0.0001}, 'alignment_share': {'mean_delta': 0.00034, 'ci95': [0.00017, 0.0005], 'fold_wins': 8, 'p_one_sided': 0.001}, 'conditioning_margin': {'mean_delta': -8e-05, 'ci95': [-0.00021, 5e-05], 'fold_wins': 2, 'p_one_sided': 0.9057}, 'note': "marginal_share = incumbent − permuted_tail (the shuffle-surviving channel; EXPECTED positive — NF-D16 (2)); alignment_share = permuted_tail − tail_ext; conditioning_margin = pooled_tail − tail_ext (per-position conditioning's earn in the tail; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_loses': True, 'winner_beats_permuted': True, 'permuted_not_significantly_better': True, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 1.72813, 'own_form_oracle': 1.72779, 'matched_n': 1.72794, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': -0.00034, 'permuted_better_p_one_sided': 0.999} · thin tail cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 1}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0016, 'legacy_mean_delta': 0.0015, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_champion': True, 'fold_consistency': True, 'dsr_ok': True, 'fdr_ok': True, 'coverage_floor_ok': True, 'degenerates_lose': True, 'permutation_not_better': True, 'oracle_floor_respected': True, 'tail_mass_toward_nominal': True}

## Null-state classification

```json
{
  "QB": {
    "state": "CONSTRAINT_REFUSED",
    "reason": "hand-classified (the NF-D18/MH2.7 classify_null gap): every statistical gate passed and the null rests entirely on anchor/calibration clauses ['degenerates_lose', 'permutation_not_better']. More data cannot change this verdict.",
    "retest_trigger": null,
    "failing_anchor_checks": [
      "degenerates_lose",
      "permutation_not_better"
    ]
  },
  "WR": {
    "state": "CONSTRAINT_REFUSED",
    "reason": "hand-classified (the NF-D18/MH2.7 classify_null gap): every statistical gate passed and the null rests entirely on anchor/calibration clauses ['permutation_not_better']. More data cannot change this verdict.",
    "retest_trigger": null,
    "failing_anchor_checks": [
      "permutation_not_better"
    ]
  }
}
```

## Pre-registration echo

```json
{
  "real_arms": [
    "tail_ext"
  ],
  "foils": [
    "incumbent"
  ],
  "anchors": [
    "zero_width",
    "max_width",
    "over_ext",
    "permuted_tail",
    "pooled_tail",
    "oracle__tail_ext",
    "matched_n__tail_ext"
  ],
  "eligible": [
    "tail_ext",
    "incumbent"
  ],
  "primary_metric": "crps_q199",
  "pit_instrument": "randomized_pit_levels on the 199-level bank (the 39-level PIT is structurally blind to a beyond-grid-only arm)",
  "eval_levels": {
    "n": 199,
    "lo": 0.005,
    "hi": 0.995
  },
  "over_scale": 3.0,
  "min_tail_n": 10,
  "nominal_tail": 0.025,
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
  "pbo": "UNDEFINED by design (1-arm family \u2014 GE.pbo_is_evaluable)",
  "dsr_min": 0.95,
  "fdr_q": 0.1,
  "fdr_family": [
    "margin2_tail_QB",
    "margin2_tail_RB",
    "margin2_tail_WR",
    "margin2_tail_TE"
  ],
  "coverage_floor": 0.8,
  "declared_inactive_clauses": [
    "winkler_80",
    "coverage_50",
    "coverage_80",
    "coverage_95"
  ],
  "team_total_samples": 512,
  "capture_era_folds": [
    "2025H1",
    "2025H2"
  ],
  "seed": 20260813
}
```