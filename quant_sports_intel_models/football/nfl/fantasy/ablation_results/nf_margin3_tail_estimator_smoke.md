# NF-MARGIN3 — a better QB/WR tail-magnitude estimator vs `tail_ext` (§0.5, 1-arm family)

**Generated:** 2026-08-13T04:30:12+00:00 · **folds:** 2 half-season blocks (2025H1…2025H2, the NF-W1 axis on the NF-W2d two-era matrix) · **player-weeks:** 8688

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (a clearing arm's serving path — attach the QB/WR tail offsets to the served bank, no refit, completing the tail fix at all four positions — is blocked on NF-C6 Ph2 + NF-G0). The successor NF-MARGIN2 named: a FRESH registration of a magnitude estimator that targets the refuted quantity directly (per-side empirical-quantile offsets calibrated on eval-end exceedance rates = the pooled pinball optimum per level). ⭐ THE BAR IS `tail_ext`, not the incumbent. Selection metric `crps_q199`; PIT accounting on the 199-level bank. PBO UNDEFINED by design; DSR = PSR at a 1-arm field. FAMILY = QB + WR; RB/TE report-only (registered non-shippable — `tail_ext` stands). Every direction word below is three-way and derived at report time, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-MARGIN3):** 532 game-groups / 183314 records checked; 0 rows dropped fail-closed.

**Verdict:** QB[POWER_LIMITED] WR[POWER_LIMITED] · RB/TE report-only (tail_ext stands)

## Construction facts (declared structurally INACTIVE — never counted as evidence)

Within-grid identity asserted every fold for BOTH arm and foil: Winkler-80, coverage(50/80/95) deltas vs the incumbent are IDENTICALLY ZERO by construction; only 8 of 199 eval columns (4/side beyond the champion grid) can differ between `eq_tail` and `tail_ext` — the contrast isolates the magnitude estimator and nothing else (NF-D20 (g⁗)).

## Team-total re-check (independence copula, report-only — the NF-W5 loop)

| label     |   n |   coverage_80 |   share_below_q10 |   share_above_q90 |   binomial_se |
|:----------|----:|--------------:|------------------:|------------------:|--------------:|
| eq_tail   | 544 |        0.693  |            0.1728 |            0.1342 |        0.0171 |
| tail_ext  | 544 |        0.6801 |            0.1673 |            0.1526 |        0.0171 |
| incumbent | 544 |        0.6618 |            0.171  |            0.1673 |        0.0171 |

Reproduction anchor (report-only): incumbent team-total coverage(80) measured 0.6618 vs NF-MARGIN2's 0.6794 — n/a on a partial run (anchors are valid only on the full 8-fold pooling) (tol 0.005).
Reproduction anchor (report-only): tail_ext team-total coverage(80) measured 0.6801 vs NF-MARGIN2's 0.7052 — n/a on a partial run (anchors are valid only on the full 8-fold pooling) (tol 0.005).

## QB — **POWER_LIMITED**

`eq_tail` TIES `tail_ext` by +0.0011 CRPS (interval unevaluable)

| label              |   mean_crps_q199 |
|:-------------------|-----------------:|
| oracle__eq_tail    |          2.53204 |
| eq_tail            |          2.53227 |
| matched_n__eq_tail |          2.53239 |
| pooled_eq          |          2.53269 |
| tail_ext           |          2.53337 |
| over_ext_eq        |          2.53729 |
| incumbent          |          2.53763 |
| permuted_eq        |          2.53992 |
| max_width          |          3.36064 |
| zero_width         |          3.44817 |

- fold wins 2/2 (clause requires None) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) None · p None · BH False
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side, ⭐ vs the FOIL): dev foil 0.01187 → winner 0.00385 (delta +0.00802) · incumbent dev 0.09423 (continuity, report-only) · p_below_eval/p_above_eval foil 0.00875/0.01312 → winner 0.00583/0.00802
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.8112, 'n_rows': 1372, 'binomial_se': 0.0108, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'eq_tail': 0.8111, 'tail_ext': 0.8111, 'incumbent': 0.8111, 'over_ext_eq': 0.8111, 'max_width': 0.938}, 'coverage_95': {'eq_tail': 0.9009, 'tail_ext': 0.9009, 'incumbent': 0.9009, 'over_ext_eq': 0.9009, 'max_width': 0.9773}, 'coverage_99': {'eq_tail': 0.9862, 'tail_ext': 0.9783, 'incumbent': 0.9009, 'over_ext_eq': 1.0, 'max_width': 0.9773}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'vs_incumbent_total': {'mean_delta': 0.00535, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'magnitude_channel': {'mean_delta': 0.00109, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'conditioning_margin': {'mean_delta': 0.00042, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'note': "vs_incumbent_total = incumbent − eq_tail (cross-story continuity: the whole tail win); magnitude_channel = tail_ext − eq_tail (THE story contrast — what the successor estimator adds over the shipped exponential); conditioning_margin = pooled_eq − eq_tail (per-position conditioning's earn; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_eq_loses': True, 'winner_beats_permuted': True, 'permuted_not_significantly_better': True, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 2.53227, 'own_form_oracle': 2.53204, 'matched_n': 2.53239, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': -0.00764, 'permuted_better_p_one_sided': None} · thin/clamped cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0, 'n_fold_levels_clamped_hi': 0, 'n_fold_levels_clamped_lo': 0}
- offsets vs the exponential (report-only, §8): [{'t_hi_995': 9.355, 'exp_hi_995': 7.228, 'ratio_hi_995': 1.294, 't_lo_005': 2.852, 'exp_lo_005': 2.343, 'ratio_lo_005': 1.218}, {'t_hi_995': 10.873, 'exp_hi_995': 7.137, 'ratio_hi_995': 1.523, 't_lo_005': 3.124, 'exp_lo_005': 2.079, 'ratio_lo_005': 1.502}]
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0011, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_tail_ext': True, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'coverage_floor_ok': True, 'degenerates_lose': True, 'permutation_not_better': True, 'oracle_floor_respected': True, 'tail_mass_toward_nominal': True}

## RB — **REPORT_ONLY** (registered non-shippable — `tail_ext` stands here)

`eq_tail` TIES `tail_ext` by +0.0007 CRPS (interval unevaluable)

| label              |   mean_crps_q199 |
|:-------------------|-----------------:|
| oracle__eq_tail    |          2.36138 |
| pooled_eq          |          2.36144 |
| eq_tail            |          2.36149 |
| matched_n__eq_tail |          2.36170 |
| tail_ext           |          2.36220 |
| over_ext_eq        |          2.36408 |
| incumbent          |          2.36566 |
| permuted_eq        |          2.36709 |
| zero_width         |          3.23177 |
| max_width          |          3.28400 |

- fold wins 2/2 (clause requires None) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) None · p None · BH n/a (out of family)
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side, ⭐ vs the FOIL): dev foil 0.00539 → winner 0.00166 (delta +0.00373) · incumbent dev 0.06649 (continuity, report-only) · p_below_eval/p_above_eval foil 0.00606/0.00933 → winner 0.00606/0.0056
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.8424, 'n_rows': 2144, 'binomial_se': 0.0086, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'eq_tail': 0.8423, 'tail_ext': 0.8423, 'incumbent': 0.8423, 'over_ext_eq': 0.8423, 'max_width': 0.9818}, 'coverage_95': {'eq_tail': 0.93, 'tail_ext': 0.93, 'incumbent': 0.93, 'over_ext_eq': 0.93, 'max_width': 0.9967}, 'coverage_99': {'eq_tail': 0.9884, 'tail_ext': 0.9846, 'incumbent': 0.93, 'over_ext_eq': 0.9991, 'max_width': 0.9967}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'vs_incumbent_total': {'mean_delta': 0.00417, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'magnitude_channel': {'mean_delta': 0.0007, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'conditioning_margin': {'mean_delta': -6e-05, 'ci95': [None, None], 'fold_wins': 0, 'p_one_sided': None}, 'note': "vs_incumbent_total = incumbent − eq_tail (cross-story continuity: the whole tail win); magnitude_channel = tail_ext − eq_tail (THE story contrast — what the successor estimator adds over the shipped exponential); conditioning_margin = pooled_eq − eq_tail (per-position conditioning's earn; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_eq_loses': True, 'winner_beats_permuted': True, 'permuted_not_significantly_better': True, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 2.36149, 'own_form_oracle': 2.36138, 'matched_n': 2.3617, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': -0.0056, 'permuted_better_p_one_sided': None} · thin/clamped cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0, 'n_fold_levels_clamped_hi': 0, 'n_fold_levels_clamped_lo': 0}
- offsets vs the exponential (report-only, §8): [{'t_hi_995': 10.737, 'exp_hi_995': 7.559, 'ratio_hi_995': 1.42, 't_lo_005': 1.221, 'exp_lo_005': 1.4, 'ratio_lo_005': 0.872}, {'t_hi_995': 10.353, 'exp_hi_995': 7.224, 'ratio_hi_995': 1.433, 't_lo_005': 1.528, 'exp_lo_005': 1.517, 'ratio_lo_005': 1.007}]
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0007, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: NOT COMPOSED — registered non-shippable (NF-D20 decision-shape: eligibility, not a threshold, separates this null from a ship; a win here is an out-of-family observation for a future registration).

## WR — **POWER_LIMITED**

`eq_tail` TIES `tail_ext` by +0.0004 CRPS (interval unevaluable)

| label              |   mean_crps_q199 |
|:-------------------|-----------------:|
| oracle__eq_tail    |          2.44107 |
| pooled_eq          |          2.44116 |
| eq_tail            |          2.44118 |
| matched_n__eq_tail |          2.44123 |
| tail_ext           |          2.44158 |
| incumbent          |          2.44431 |
| over_ext_eq        |          2.44609 |
| permuted_eq        |          2.44688 |
| zero_width         |          3.36273 |
| max_width          |          3.50078 |

- fold wins 2/2 (clause requires None) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) None · p None · BH False
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side, ⭐ vs the FOIL): dev foil 0.00372 → winner 0.00226 (delta +0.00146) · incumbent dev 0.04695 (continuity, report-only) · p_below_eval/p_above_eval foil 0.00402/0.00774 → winner 0.00464/0.0031
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.8567, 'n_rows': 3231, 'binomial_se': 0.007, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'eq_tail': 0.8567, 'tail_ext': 0.8567, 'incumbent': 0.8567, 'over_ext_eq': 0.8567, 'max_width': 0.9861}, 'coverage_95': {'eq_tail': 0.9461, 'tail_ext': 0.9461, 'incumbent': 0.9461, 'over_ext_eq': 0.9461, 'max_width': 0.9978}, 'coverage_99': {'eq_tail': 0.9923, 'tail_ext': 0.9882, 'incumbent': 0.9461, 'over_ext_eq': 0.9997, 'max_width': 0.9978}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'vs_incumbent_total': {'mean_delta': 0.00312, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'magnitude_channel': {'mean_delta': 0.0004, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'conditioning_margin': {'mean_delta': -2e-05, 'ci95': [None, None], 'fold_wins': 1, 'p_one_sided': None}, 'note': "vs_incumbent_total = incumbent − eq_tail (cross-story continuity: the whole tail win); magnitude_channel = tail_ext − eq_tail (THE story contrast — what the successor estimator adds over the shipped exponential); conditioning_margin = pooled_eq − eq_tail (per-position conditioning's earn; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_eq_loses': True, 'winner_beats_permuted': True, 'permuted_not_significantly_better': True, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 2.44118, 'own_form_oracle': 2.44107, 'matched_n': 2.44123, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': -0.0057, 'permuted_better_p_one_sided': None} · thin/clamped cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0, 'n_fold_levels_clamped_hi': 0, 'n_fold_levels_clamped_lo': 2}
- offsets vs the exponential (report-only, §8): [{'t_hi_995': 11.565, 'exp_hi_995': 8.005, 'ratio_hi_995': 1.445, 't_lo_005': 2.303, 'exp_lo_005': 2.64, 'ratio_lo_005': 0.872}, {'t_hi_995': 10.119, 'exp_hi_995': 7.54, 'ratio_hi_995': 1.342, 't_lo_005': 2.407, 'exp_lo_005': 2.832, 'ratio_lo_005': 0.85}]
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0004, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_tail_ext': True, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'coverage_floor_ok': True, 'degenerates_lose': True, 'permutation_not_better': True, 'oracle_floor_respected': True, 'tail_mass_toward_nominal': True}

## TE — **REPORT_ONLY** (registered non-shippable — `tail_ext` stands here)

`eq_tail` TIES `tail_ext` by +0.0006 CRPS (interval unevaluable)

| label              |   mean_crps_q199 |
|:-------------------|-----------------:|
| oracle__eq_tail    |          1.78412 |
| matched_n__eq_tail |          1.78422 |
| eq_tail            |          1.78423 |
| pooled_eq          |          1.78435 |
| tail_ext           |          1.78479 |
| over_ext_eq        |          1.78567 |
| incumbent          |          1.78641 |
| permuted_eq        |          1.78758 |
| zero_width         |          2.44472 |
| max_width          |          2.55497 |

- fold wins 2/2 (clause requires None) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) None · p None · BH n/a (out of family)
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side, ⭐ vs the FOIL): dev foil 0.00979 → winner 0.00494 (delta +0.00485) · incumbent dev 0.03997 (continuity, report-only) · p_below_eval/p_above_eval foil 0.00103/0.01082 → winner 0.00567/0.00927
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.8774, 'n_rows': 1941, 'binomial_se': 0.0091, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'eq_tail': 0.8774, 'tail_ext': 0.8774, 'incumbent': 0.8774, 'over_ext_eq': 0.8774, 'max_width': 0.984}, 'coverage_95': {'eq_tail': 0.9541, 'tail_ext': 0.9541, 'incumbent': 0.9541, 'over_ext_eq': 0.9541, 'max_width': 0.9974}, 'coverage_99': {'eq_tail': 0.9876, 'tail_ext': 0.9881, 'incumbent': 0.9541, 'over_ext_eq': 0.9959, 'max_width': 0.9974}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'vs_incumbent_total': {'mean_delta': 0.00218, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'magnitude_channel': {'mean_delta': 0.00056, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'conditioning_margin': {'mean_delta': 0.00012, 'ci95': [None, None], 'fold_wins': 1, 'p_one_sided': None}, 'note': "vs_incumbent_total = incumbent − eq_tail (cross-story continuity: the whole tail win); magnitude_channel = tail_ext − eq_tail (THE story contrast — what the successor estimator adds over the shipped exponential); conditioning_margin = pooled_eq − eq_tail (per-position conditioning's earn; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_eq_loses': True, 'winner_beats_permuted': True, 'permuted_not_significantly_better': True, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 1.78423, 'own_form_oracle': 1.78412, 'matched_n': 1.78422, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': -0.00335, 'permuted_better_p_one_sided': None} · thin/clamped cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0, 'n_fold_levels_clamped_hi': 0, 'n_fold_levels_clamped_lo': 7}
- offsets vs the exponential (report-only, §8): [{'t_hi_995': 6.308, 'exp_hi_995': 5.596, 'ratio_hi_995': 1.127, 't_lo_005': 0.32, 'exp_lo_005': 2.514, 'ratio_lo_005': 0.128}, {'t_hi_995': 7.201, 'exp_hi_995': 5.696, 'ratio_hi_995': 1.264, 't_lo_005': 0.0, 'exp_lo_005': 1.952, 'ratio_lo_005': 0.0}]
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0006, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: NOT COMPOSED — registered non-shippable (NF-D20 decision-shape: eligibility, not a threshold, separates this null from a ship; a win here is an out-of-family observation for a future registration).

## Null-state classification

```json
{
  "QB": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_margin3_QB_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0011 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 2/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~2 half-season folds (\u22481 seasons) for the DSR gate at the observed per-fold Sharpe 28.232 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test."
  },
  "WR": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_margin3_WR_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0004 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 2/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~4 half-season folds (\u22482 seasons) for the DSR gate at the observed per-fold Sharpe 1.066 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test."
  }
}
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