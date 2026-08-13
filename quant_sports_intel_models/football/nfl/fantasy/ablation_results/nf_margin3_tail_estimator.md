# NF-MARGIN3 — a better QB/WR tail-magnitude estimator vs `tail_ext` (§0.5, 1-arm family)

**Generated:** 2026-08-13T04:51:56+00:00 · **folds:** 8 half-season blocks (2022H1…2025H2, the NF-W1 axis on the NF-W2d two-era matrix) · **player-weeks:** 34552

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (a clearing arm's serving path — attach the QB/WR tail offsets to the served bank, no refit, completing the tail fix at all four positions — is blocked on NF-C6 Ph2 + NF-G0). The successor NF-MARGIN2 named: a FRESH registration of a magnitude estimator that targets the refuted quantity directly (per-side empirical-quantile offsets calibrated on eval-end exceedance rates = the pooled pinball optimum per level). ⭐ THE BAR IS `tail_ext`, not the incumbent. Selection metric `crps_q199`; PIT accounting on the 199-level bank. PBO UNDEFINED by design; DSR = PSR at a 1-arm field. FAMILY = QB + WR; RB/TE report-only (registered non-shippable — `tail_ext` stands). Every direction word below is three-way and derived at report time, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-MARGIN3):** 532 game-groups / 183314 records checked; 0 rows dropped fail-closed.

**Verdict:** QB[SHIP] WR[SHIP] · RB/TE report-only (tail_ext stands)

## Construction facts (declared structurally INACTIVE — never counted as evidence)

Within-grid identity asserted every fold for BOTH arm and foil: Winkler-80, coverage(50/80/95) deltas vs the incumbent are IDENTICALLY ZERO by construction; only 8 of 199 eval columns (4/side beyond the champion grid) can differ between `eq_tail` and `tail_ext` — the contrast isolates the magnitude estimator and nothing else (NF-D20 (g⁗)).

## Team-total re-check (independence copula, report-only — the NF-W5 loop)

| label     |    n |   coverage_80 |   share_below_q10 |   share_above_q90 |   binomial_se |
|:----------|-----:|--------------:|------------------:|------------------:|--------------:|
| eq_tail   | 2174 |        0.724  |            0.1403 |            0.1357 |        0.0086 |
| tail_ext  | 2174 |        0.7052 |            0.1385 |            0.1564 |        0.0086 |
| incumbent | 2174 |        0.6794 |            0.1403 |            0.1803 |        0.0086 |

Reproduction anchor (report-only): incumbent team-total coverage(80) measured 0.6794 vs NF-MARGIN2's 0.6794 — REPRODUCED (tol 0.005).
Reproduction anchor (report-only): tail_ext team-total coverage(80) measured 0.7052 vs NF-MARGIN2's 0.7052 — REPRODUCED (tol 0.005).

Per-position mean-CRPS reproduction anchors vs the NF-MARGIN2 record (tol 0.002, report-only): 8/8 reproduced.

## QB — **SHIP**

`eq_tail` BEATS `tail_ext` by +0.0009 CRPS (CI95 [+0.0004, +0.0014] excludes zero)

| label              |   mean_crps_q199 |
|:-------------------|-----------------:|
| oracle__eq_tail    |          2.40898 |
| eq_tail            |          2.40920 |
| matched_n__eq_tail |          2.40928 |
| pooled_eq          |          2.40937 |
| tail_ext           |          2.41015 |
| over_ext_eq        |          2.41387 |
| incumbent          |          2.41416 |
| permuted_eq        |          2.41709 |
| zero_width         |          3.24795 |
| max_width          |          3.25964 |

- fold wins 8/8 (clause requires 6) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) 1.0 · p 0.0014 · BH True
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side, ⭐ vs the FOIL): dev foil 0.01024 → winner 0.00219 (delta +0.00805) · incumbent dev 0.08316 (continuity, report-only) · p_below_eval/p_above_eval foil 0.00766/0.01258 → winner 0.00474/0.00693
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.825, 'n_rows': 5485, 'binomial_se': 0.0054, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'eq_tail': 0.825, 'tail_ext': 0.825, 'incumbent': 0.825, 'over_ext_eq': 0.825, 'max_width': 0.9441}, 'coverage_95': {'eq_tail': 0.911, 'tail_ext': 0.911, 'incumbent': 0.911, 'over_ext_eq': 0.911, 'max_width': 0.9809}, 'coverage_99': {'eq_tail': 0.9883, 'tail_ext': 0.9798, 'incumbent': 0.911, 'over_ext_eq': 1.0, 'max_width': 0.9809}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'vs_incumbent_total': {'mean_delta': 0.00496, 'ci95': [0.00372, 0.00621], 'fold_wins': 8, 'p_one_sided': 0.0}, 'magnitude_channel': {'mean_delta': 0.00095, 'ci95': [0.00045, 0.00145], 'fold_wins': 8, 'p_one_sided': 0.0014}, 'conditioning_margin': {'mean_delta': 0.00017, 'ci95': [-0.0001, 0.00043], 'fold_wins': 7, 'p_one_sided': 0.0882}, 'note': "vs_incumbent_total = incumbent − eq_tail (cross-story continuity: the whole tail win); magnitude_channel = tail_ext − eq_tail (THE story contrast — what the successor estimator adds over the shipped exponential); conditioning_margin = pooled_eq − eq_tail (per-position conditioning's earn; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_eq_loses': True, 'winner_beats_permuted': True, 'permuted_not_significantly_better': True, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 2.4092, 'own_form_oracle': 2.40898, 'matched_n': 2.40928, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': -0.00789, 'permuted_better_p_one_sided': 1.0} · thin/clamped cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0, 'n_fold_levels_clamped_hi': 0, 'n_fold_levels_clamped_lo': 0}
- offsets vs the exponential (report-only, §8): [{'t_hi_995': 10.863, 'exp_hi_995': 7.768, 'ratio_hi_995': 1.398, 't_lo_005': 3.723, 'exp_lo_005': 2.663, 'ratio_lo_005': 1.398}, {'t_hi_995': 10.193, 'exp_hi_995': 7.3, 'ratio_hi_995': 1.396, 't_lo_005': 3.454, 'exp_lo_005': 2.683, 'ratio_lo_005': 1.287}, {'t_hi_995': 10.596, 'exp_hi_995': 6.637, 'ratio_hi_995': 1.596, 't_lo_005': 3.383, 'exp_lo_005': 2.723, 'ratio_lo_005': 1.243}, {'t_hi_995': 9.478, 'exp_hi_995': 6.596, 'ratio_hi_995': 1.437, 't_lo_005': 3.0, 'exp_lo_005': 2.488, 'ratio_lo_005': 1.206}, {'t_hi_995': 10.604, 'exp_hi_995': 6.833, 'ratio_hi_995': 1.552, 't_lo_005': 2.862, 'exp_lo_005': 2.173, 'ratio_lo_005': 1.317}, {'t_hi_995': 10.341, 'exp_hi_995': 7.251, 'ratio_hi_995': 1.426, 't_lo_005': 3.265, 'exp_lo_005': 2.173, 'ratio_lo_005': 1.502}, {'t_hi_995': 9.355, 'exp_hi_995': 7.228, 'ratio_hi_995': 1.294, 't_lo_005': 2.852, 'exp_lo_005': 2.343, 'ratio_lo_005': 1.218}, {'t_hi_995': 10.873, 'exp_hi_995': 7.137, 'ratio_hi_995': 1.523, 't_lo_005': 3.124, 'exp_lo_005': 2.079, 'ratio_lo_005': 1.502}]
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0011, 'legacy_mean_delta': 0.0009, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_tail_ext': True, 'fold_consistency': True, 'dsr_ok': True, 'fdr_ok': True, 'coverage_floor_ok': True, 'degenerates_lose': True, 'permutation_not_better': True, 'oracle_floor_respected': True, 'tail_mass_toward_nominal': True}

## RB — **REPORT_ONLY** (registered non-shippable — `tail_ext` stands here)

`eq_tail` TIES `tail_ext` by +0.0003 CRPS (CI95 [-0.0000, +0.0006] spans zero)

| label              |   mean_crps_q199 |
|:-------------------|-----------------:|
| oracle__eq_tail    |          2.35684 |
| pooled_eq          |          2.35694 |
| eq_tail            |          2.35700 |
| matched_n__eq_tail |          2.35705 |
| tail_ext           |          2.35729 |
| incumbent          |          2.36012 |
| over_ext_eq        |          2.36082 |
| permuted_eq        |          2.36264 |
| zero_width         |          3.23657 |
| max_width          |          3.32154 |

- fold wins 6/8 (clause requires 6) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) 0.958 · p 0.0321 · BH n/a (out of family)
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side, ⭐ vs the FOIL): dev foil 0.00362 → winner 0.00081 (delta +0.00281) · incumbent dev 0.06089 (continuity, report-only) · p_below_eval/p_above_eval foil 0.00559/0.00803 → winner 0.00535/0.00454
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.845, 'n_rows': 8591, 'binomial_se': 0.0043, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'eq_tail': 0.8452, 'tail_ext': 0.8452, 'incumbent': 0.8452, 'over_ext_eq': 0.8452, 'max_width': 0.9847}, 'coverage_95': {'eq_tail': 0.9335, 'tail_ext': 0.9335, 'incumbent': 0.9335, 'over_ext_eq': 0.9335, 'max_width': 0.9958}, 'coverage_99': {'eq_tail': 0.9901, 'tail_ext': 0.9864, 'incumbent': 0.9335, 'over_ext_eq': 0.9996, 'max_width': 0.9958}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'vs_incumbent_total': {'mean_delta': 0.00312, 'ci95': [0.00214, 0.0041], 'fold_wins': 8, 'p_one_sided': 0.0001}, 'magnitude_channel': {'mean_delta': 0.00029, 'ci95': [-2e-05, 0.00061], 'fold_wins': 6, 'p_one_sided': 0.0321}, 'conditioning_margin': {'mean_delta': -6e-05, 'ci95': [-0.00011, -1e-05], 'fold_wins': 1, 'p_one_sided': 0.986}, 'note': "vs_incumbent_total = incumbent − eq_tail (cross-story continuity: the whole tail win); magnitude_channel = tail_ext − eq_tail (THE story contrast — what the successor estimator adds over the shipped exponential); conditioning_margin = pooled_eq − eq_tail (per-position conditioning's earn; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_eq_loses': True, 'winner_beats_permuted': True, 'permuted_not_significantly_better': True, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 2.357, 'own_form_oracle': 2.35684, 'matched_n': 2.35705, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': -0.00564, 'permuted_better_p_one_sided': 1.0} · thin/clamped cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0, 'n_fold_levels_clamped_hi': 0, 'n_fold_levels_clamped_lo': 0}
- offsets vs the exponential (report-only, §8): [{'t_hi_995': 11.519, 'exp_hi_995': 8.111, 'ratio_hi_995': 1.42, 't_lo_005': 1.75, 'exp_lo_005': 1.631, 'ratio_lo_005': 1.073}, {'t_hi_995': 9.808, 'exp_hi_995': 7.762, 'ratio_hi_995': 1.264, 't_lo_005': 2.342, 'exp_lo_005': 1.929, 'ratio_lo_005': 1.214}, {'t_hi_995': 11.923, 'exp_hi_995': 7.916, 'ratio_hi_995': 1.506, 't_lo_005': 2.119, 'exp_lo_005': 1.87, 'ratio_lo_005': 1.133}, {'t_hi_995': 11.009, 'exp_hi_995': 7.405, 'ratio_hi_995': 1.487, 't_lo_005': 1.941, 'exp_lo_005': 1.875, 'ratio_lo_005': 1.035}, {'t_hi_995': 10.815, 'exp_hi_995': 8.14, 'ratio_hi_995': 1.329, 't_lo_005': 1.861, 'exp_lo_005': 1.697, 'ratio_lo_005': 1.097}, {'t_hi_995': 10.418, 'exp_hi_995': 7.754, 'ratio_hi_995': 1.343, 't_lo_005': 1.854, 'exp_lo_005': 1.795, 'ratio_lo_005': 1.033}, {'t_hi_995': 10.737, 'exp_hi_995': 7.559, 'ratio_hi_995': 1.42, 't_lo_005': 1.221, 'exp_lo_005': 1.4, 'ratio_lo_005': 0.872}, {'t_hi_995': 10.353, 'exp_hi_995': 7.224, 'ratio_hi_995': 1.433, 't_lo_005': 1.528, 'exp_lo_005': 1.517, 'ratio_lo_005': 1.007}]
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0007, 'legacy_mean_delta': 0.0002, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: NOT COMPOSED — registered non-shippable (NF-D20 decision-shape: eligibility, not a threshold, separates this null from a ship; a win here is an out-of-family observation for a future registration).

## WR — **SHIP**

`eq_tail` BEATS `tail_ext` by +0.0007 CRPS (CI95 [+0.0004, +0.0010] excludes zero)

| label              |   mean_crps_q199 |
|:-------------------|-----------------:|
| oracle__eq_tail    |          2.51019 |
| eq_tail            |          2.51030 |
| pooled_eq          |          2.51033 |
| matched_n__eq_tail |          2.51034 |
| tail_ext           |          2.51102 |
| incumbent          |          2.51426 |
| over_ext_eq        |          2.51446 |
| permuted_eq        |          2.51556 |
| zero_width         |          3.46621 |
| max_width          |          3.56004 |

- fold wins 8/8 (clause requires 6) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) 0.9991 · p 0.0007 · BH True
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side, ⭐ vs the FOIL): dev foil 0.00522 → winner 0.0007 (delta +0.00452) · incumbent dev 0.05666 (continuity, report-only) · p_below_eval/p_above_eval foil 0.00437/0.00959 → winner 0.00476/0.00546
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.8541, 'n_rows': 12827, 'binomial_se': 0.0035, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'eq_tail': 0.854, 'tail_ext': 0.854, 'incumbent': 0.854, 'over_ext_eq': 0.854, 'max_width': 0.9891}, 'coverage_95': {'eq_tail': 0.9371, 'tail_ext': 0.9371, 'incumbent': 0.9371, 'over_ext_eq': 0.9371, 'max_width': 0.9978}, 'coverage_99': {'eq_tail': 0.9897, 'tail_ext': 0.986, 'incumbent': 0.9371, 'over_ext_eq': 0.9999, 'max_width': 0.9978}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'vs_incumbent_total': {'mean_delta': 0.00396, 'ci95': [0.00305, 0.00487], 'fold_wins': 8, 'p_one_sided': 0.0}, 'magnitude_channel': {'mean_delta': 0.00072, 'ci95': [0.00038, 0.00105], 'fold_wins': 8, 'p_one_sided': 0.0007}, 'conditioning_margin': {'mean_delta': 3e-05, 'ci95': [-2e-05, 8e-05], 'fold_wins': 5, 'p_one_sided': 0.1275}, 'note': "vs_incumbent_total = incumbent − eq_tail (cross-story continuity: the whole tail win); magnitude_channel = tail_ext − eq_tail (THE story contrast — what the successor estimator adds over the shipped exponential); conditioning_margin = pooled_eq − eq_tail (per-position conditioning's earn; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_eq_loses': True, 'winner_beats_permuted': True, 'permuted_not_significantly_better': True, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 2.5103, 'own_form_oracle': 2.51019, 'matched_n': 2.51034, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': -0.00526, 'permuted_better_p_one_sided': 1.0} · thin/clamped cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0, 'n_fold_levels_clamped_hi': 0, 'n_fold_levels_clamped_lo': 3}
- offsets vs the exponential (report-only, §8): [{'t_hi_995': 10.496, 'exp_hi_995': 7.12, 'ratio_hi_995': 1.474, 't_lo_005': 2.766, 'exp_lo_005': 2.75, 'ratio_lo_005': 1.006}, {'t_hi_995': 9.904, 'exp_hi_995': 7.071, 'ratio_hi_995': 1.401, 't_lo_005': 2.659, 'exp_lo_005': 2.55, 'ratio_lo_005': 1.043}, {'t_hi_995': 10.346, 'exp_hi_995': 6.956, 'ratio_hi_995': 1.487, 't_lo_005': 2.597, 'exp_lo_005': 2.69, 'ratio_lo_005': 0.965}, {'t_hi_995': 10.611, 'exp_hi_995': 7.413, 'ratio_hi_995': 1.431, 't_lo_005': 2.78, 'exp_lo_005': 2.968, 'ratio_lo_005': 0.937}, {'t_hi_995': 10.734, 'exp_hi_995': 7.48, 'ratio_hi_995': 1.435, 't_lo_005': 2.802, 'exp_lo_005': 3.04, 'ratio_lo_005': 0.922}, {'t_hi_995': 10.756, 'exp_hi_995': 8.2, 'ratio_hi_995': 1.312, 't_lo_005': 2.67, 'exp_lo_005': 2.718, 'ratio_lo_005': 0.982}, {'t_hi_995': 11.565, 'exp_hi_995': 8.005, 'ratio_hi_995': 1.445, 't_lo_005': 2.303, 'exp_lo_005': 2.64, 'ratio_lo_005': 0.872}, {'t_hi_995': 10.119, 'exp_hi_995': 7.54, 'ratio_hi_995': 1.342, 't_lo_005': 2.407, 'exp_lo_005': 2.832, 'ratio_lo_005': 0.85}]
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0004, 'legacy_mean_delta': 0.0008, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_tail_ext': True, 'fold_consistency': True, 'dsr_ok': True, 'fdr_ok': True, 'coverage_floor_ok': True, 'degenerates_lose': True, 'permutation_not_better': True, 'oracle_floor_respected': True, 'tail_mass_toward_nominal': True}

## TE — **REPORT_ONLY** (registered non-shippable — `tail_ext` stands here)

`eq_tail` BEATS `tail_ext` by +0.0005 CRPS (CI95 [+0.0003, +0.0006] excludes zero)

| label              |   mean_crps_q199 |
|:-------------------|-----------------:|
| oracle__eq_tail    |          1.72758 |
| eq_tail            |          1.72765 |
| matched_n__eq_tail |          1.72772 |
| pooled_eq          |          1.72795 |
| tail_ext           |          1.72813 |
| over_ext_eq        |          1.72960 |
| incumbent          |          1.72963 |
| permuted_eq        |          1.73171 |
| zero_width         |          2.36975 |
| max_width          |          2.48597 |

- fold wins 8/8 (clause requires 6) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) 1.0 · p 0.0001 · BH n/a (out of family)
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side, ⭐ vs the FOIL): dev foil 0.00615 → winner 0.00131 (delta +0.00484) · incumbent dev 0.03694 (continuity, report-only) · p_below_eval/p_above_eval foil 0.00222/0.00837 → winner 0.00431/0.00562
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.8821, 'n_rows': 7649, 'binomial_se': 0.0046, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'eq_tail': 0.8821, 'tail_ext': 0.8821, 'incumbent': 0.8821, 'over_ext_eq': 0.8821, 'max_width': 0.9865}, 'coverage_95': {'eq_tail': 0.9577, 'tail_ext': 0.9577, 'incumbent': 0.9577, 'over_ext_eq': 0.9577, 'max_width': 0.9988}, 'coverage_99': {'eq_tail': 0.9913, 'tail_ext': 0.9905, 'incumbent': 0.9577, 'over_ext_eq': 0.9974, 'max_width': 0.9988}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'vs_incumbent_total': {'mean_delta': 0.00198, 'ci95': [0.00165, 0.00232], 'fold_wins': 8, 'p_one_sided': 0.0}, 'magnitude_channel': {'mean_delta': 0.00047, 'ci95': [0.00031, 0.00063], 'fold_wins': 8, 'p_one_sided': 0.0001}, 'conditioning_margin': {'mean_delta': 0.0003, 'ci95': [0.00016, 0.00044], 'fold_wins': 7, 'p_one_sided': 0.0007}, 'note': "vs_incumbent_total = incumbent − eq_tail (cross-story continuity: the whole tail win); magnitude_channel = tail_ext − eq_tail (THE story contrast — what the successor estimator adds over the shipped exponential); conditioning_margin = pooled_eq − eq_tail (per-position conditioning's earn; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_eq_loses': True, 'winner_beats_permuted': True, 'permuted_not_significantly_better': True, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 1.72765, 'own_form_oracle': 1.72758, 'matched_n': 1.72772, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': -0.00405, 'permuted_better_p_one_sided': 1.0} · thin/clamped cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 1, 'n_fold_levels_clamped_hi': 0, 'n_fold_levels_clamped_lo': 26}
- offsets vs the exponential (report-only, §8): [{'t_hi_995': 7.964, 'exp_hi_995': 6.813, 'ratio_hi_995': 1.169, 't_lo_005': 1.22, 'exp_lo_005': 2.779, 'ratio_lo_005': 0.439}, {'t_hi_995': 8.228, 'exp_hi_995': 6.234, 'ratio_hi_995': 1.32, 't_lo_005': 1.598, 'exp_lo_005': 2.949, 'ratio_lo_005': 0.542}, {'t_hi_995': 8.199, 'exp_hi_995': 6.63, 'ratio_hi_995': 1.237, 't_lo_005': 0.253, 'exp_lo_005': 2.554, 'ratio_lo_005': 0.099}, {'t_hi_995': 8.808, 'exp_hi_995': 7.029, 'ratio_hi_995': 1.253, 't_lo_005': 0.159, 'exp_lo_005': 2.12, 'ratio_lo_005': 0.075}, {'t_hi_995': 7.9, 'exp_hi_995': 5.954, 'ratio_hi_995': 1.327, 't_lo_005': 0.0, 'exp_lo_005': 0.0, 'ratio_lo_005': None}, {'t_hi_995': 7.701, 'exp_hi_995': 5.982, 'ratio_hi_995': 1.287, 't_lo_005': 0.3, 'exp_lo_005': 2.501, 'ratio_lo_005': 0.12}, {'t_hi_995': 6.308, 'exp_hi_995': 5.596, 'ratio_hi_995': 1.127, 't_lo_005': 0.32, 'exp_lo_005': 2.514, 'ratio_lo_005': 0.128}, {'t_hi_995': 7.201, 'exp_hi_995': 5.696, 'ratio_hi_995': 1.264, 't_lo_005': 0.0, 'exp_lo_005': 1.952, 'ratio_lo_005': 0.0}]
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0006, 'legacy_mean_delta': 0.0004, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: NOT COMPOSED — registered non-shippable (NF-D20 decision-shape: eligibility, not a threshold, separates this null from a ship; a win here is an out-of-family observation for a future registration).

## Null-state classification

```json
{}
```

## Pre-registration echo

```json
{
  "real_arms": [
    "eq_tail"
  ],
  "foils": [
    "tail_ext"
  ],
  "reference": [
    "incumbent"
  ],
  "anchors": [
    "zero_width",
    "max_width",
    "over_ext_eq",
    "permuted_eq",
    "pooled_eq",
    "oracle__eq_tail",
    "matched_n__eq_tail"
  ],
  "eligible": [
    "eq_tail",
    "tail_ext"
  ],
  "live_positions": [
    "QB",
    "WR"
  ],
  "report_only_positions": [
    "RB",
    "TE"
  ],
  "primary_metric": "crps_q199",
  "estimator": "per-side empirical-quantile tail offsets calibrated on the eval-end exceedance rates of the purged calibration slice \u2014 the pooled pinball optimum at each beyond-grid eval level (GPD considered and declined at design time; see the pre-registration \u00a72)",
  "the_bar": "tail_ext (the standing object; the incumbent is reference-only)",
  "pit_instrument": "randomized_pit_levels on the 199-level bank (NF-MARGIN2 verbatim)",
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
    "margin3_tail_QB",
    "margin3_tail_WR"
  ],
  "coverage_floor": 0.8,
  "declared_inactive_clauses": [
    "winkler_80",
    "coverage_50",
    "coverage_80",
    "coverage_95"
  ],
  "tail_mass_gate": "vs the FOIL (tail_ext), beyond-EVAL-grid deviation, strict fall; arm-movability proved at design time (guard-tested)",
  "team_total_samples": 512,
  "capture_era_folds": [
    "2025H1",
    "2025H2"
  ],
  "reproduction_anchors": {
    "team_total": {
      "incumbent": 0.6794,
      "tail_ext": 0.7052
    },
    "mean_crps": {
      "tail_ext": {
        "QB": 2.41015,
        "RB": 2.35729,
        "WR": 2.51102,
        "TE": 1.72813
      },
      "incumbent": {
        "QB": 2.41416,
        "RB": 2.36012,
        "WR": 2.51426,
        "TE": 1.72963
      }
    }
  },
  "seed": 20260815
}
```