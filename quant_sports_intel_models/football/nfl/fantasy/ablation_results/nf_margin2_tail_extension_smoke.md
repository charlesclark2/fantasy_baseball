# NF-MARGIN2 — tail-extension-ONLY recalibration vs the champion (§0.5, 1-arm family)

**Generated:** 2026-08-13T02:52:25+00:00 · **folds:** 2 half-season blocks (2025H1…2025H2, the NF-W1 axis on the NF-W2d two-era matrix) · **player-weeks:** 8688

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (a clearing arm's serving path — attach the per-position tail betas to the served bank, no refit — is blocked on NF-C6 Ph2 + NF-G0). The MH2.2-legitimate successor to NF-MARGIN1: a FRESH registration of the single demonstrated contrast, on a construction NF-MARGIN1 never scored. Selection metric `crps_q199`; PIT accounting on the 199-level bank (the 39-level instrument is structurally blind to this arm). PBO UNDEFINED by design; DSR = PSR at a 1-arm field. Every direction word below is three-way and derived at report time, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-MARGIN2):** 532 game-groups / 183314 records checked; 0 rows dropped fail-closed.

**Verdict:** QB[POWER_LIMITED] RB[POWER_LIMITED] WR[POWER_LIMITED] TE[POWER_LIMITED]

## Construction facts (declared structurally INACTIVE — never counted as evidence)

Within-grid identity asserted every fold: Winkler-80, coverage(50/80/95) deltas vs the incumbent are IDENTICALLY ZERO by construction; only 8 of 199 eval columns (4/side beyond the champion grid) can differ. The coverage floor therefore cannot newly fire (NF-D20 (g⁗) — the active-clause count is what the gate's evidence rests on).

## Team-total re-check (independence copula, report-only — the NF-W5 loop)

| label     |   n |   coverage_80 |   share_below_q10 |   share_above_q90 |   binomial_se |
|:----------|----:|--------------:|------------------:|------------------:|--------------:|
| tail_ext  | 544 |        0.6801 |            0.1673 |            0.1526 |        0.0171 |
| incumbent | 544 |        0.6618 |            0.171  |            0.1673 |        0.0171 |

Reproduction anchor (report-only): incumbent team-total coverage(80) measured 0.6618 vs NF-MARGIN1's 0.6794 — ⚠️ NOT reproduced (investigate before trusting cross-story comparability) (tol 0.005).

## QB — **POWER_LIMITED**

`tail_ext` TIES `incumbent` by +0.0043 CRPS (interval unevaluable)

| label               |   mean_crps_q199 |
|:--------------------|-----------------:|
| permuted_tail       |          2.53277 |
| over_ext            |          2.53299 |
| oracle__tail_ext    |          2.53325 |
| pooled_tail         |          2.53335 |
| tail_ext            |          2.53337 |
| matched_n__tail_ext |          2.53338 |
| incumbent           |          2.53763 |
| max_width           |          3.36064 |
| zero_width          |          3.44817 |

- fold wins 2/2 (clause requires None) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) None · p None · BH False
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side): dev 0.0935 → 0.01187 (delta +0.08163) · p_below_eval/p_above_eval incumbent 0.05102/0.05248 → winner 0.00875/0.01312 · beyond-CHAMPION-grid mass (arm-invariant diagnostic, nominal 0.025/side) 0.06706/0.05321
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.8112, 'n_rows': 1372, 'binomial_se': 0.0108, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'tail_ext': 0.8111, 'incumbent': 0.8111, 'over_ext': 0.8111, 'max_width': 0.938}, 'coverage_95': {'tail_ext': 0.9009, 'incumbent': 0.9009, 'over_ext': 0.9009, 'max_width': 0.9773}, 'coverage_99': {'tail_ext': 0.9783, 'incumbent': 0.9009, 'over_ext': 1.0, 'max_width': 0.9773}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'marginal_share': {'mean_delta': 0.00485, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'alignment_share': {'mean_delta': -0.00059, 'ci95': [None, None], 'fold_wins': 0, 'p_one_sided': None}, 'conditioning_margin': {'mean_delta': -1e-05, 'ci95': [None, None], 'fold_wins': 0, 'p_one_sided': None}, 'note': "marginal_share = incumbent − permuted_tail (the shuffle-surviving channel; EXPECTED positive — NF-D16 (2)); alignment_share = permuted_tail − tail_ext; conditioning_margin = pooled_tail − tail_ext (per-position conditioning's earn in the tail; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_loses': False, 'winner_beats_permuted': False, 'permuted_not_significantly_better': False, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- ⚠️ **REFUTED MAGNITUDE HYPOTHESIS (NF-D20):** `over_ext` (betas × 3.0, registered to lose) BEAT the fitted arm — the mean-excess fit UNDER-extends and the metric optimum lies beyond the fitted magnitude. Recorded as a decomposed refutation; the anchor stays an anchor (⛔ never re-labelled).
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 2.53337, 'own_form_oracle': 2.53325, 'matched_n': 2.53338, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': 0.00059, 'permuted_better_p_one_sided': None} · thin tail cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0043, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_champion': True, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'coverage_floor_ok': True, 'degenerates_lose': False, 'permutation_not_better': False, 'oracle_floor_respected': True, 'tail_mass_toward_nominal': True}

## RB — **POWER_LIMITED**

`tail_ext` TIES `incumbent` by +0.0035 CRPS (interval unevaluable)

| label               |   mean_crps_q199 |
|:--------------------|-----------------:|
| permuted_tail       |          2.36197 |
| oracle__tail_ext    |          2.36215 |
| tail_ext            |          2.36220 |
| pooled_tail         |          2.36227 |
| over_ext            |          2.36228 |
| matched_n__tail_ext |          2.36235 |
| incumbent           |          2.36566 |
| zero_width          |          3.23177 |
| max_width           |          3.28400 |

- fold wins 2/2 (clause requires None) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) None · p None · BH False
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side): dev 0.0637 → 0.00539 (delta +0.05831) · p_below_eval/p_above_eval incumbent 0.02519/0.04851 → winner 0.00606/0.00933 · beyond-CHAMPION-grid mass (arm-invariant diagnostic, nominal 0.025/side) 0.03871/0.04991
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.8424, 'n_rows': 2144, 'binomial_se': 0.0086, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'tail_ext': 0.8423, 'incumbent': 0.8423, 'over_ext': 0.8423, 'max_width': 0.9818}, 'coverage_95': {'tail_ext': 0.93, 'incumbent': 0.93, 'over_ext': 0.93, 'max_width': 0.9967}, 'coverage_99': {'tail_ext': 0.9846, 'incumbent': 0.93, 'over_ext': 0.9986, 'max_width': 0.9967}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'marginal_share': {'mean_delta': 0.00369, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'alignment_share': {'mean_delta': -0.00022, 'ci95': [None, None], 'fold_wins': 0, 'p_one_sided': None}, 'conditioning_margin': {'mean_delta': 7e-05, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'note': "marginal_share = incumbent − permuted_tail (the shuffle-surviving channel; EXPECTED positive — NF-D16 (2)); alignment_share = permuted_tail − tail_ext; conditioning_margin = pooled_tail − tail_ext (per-position conditioning's earn in the tail; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_loses': True, 'winner_beats_permuted': False, 'permuted_not_significantly_better': False, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 2.3622, 'own_form_oracle': 2.36215, 'matched_n': 2.36235, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': 0.00022, 'permuted_better_p_one_sided': None} · thin tail cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0035, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_champion': True, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'coverage_floor_ok': True, 'degenerates_lose': True, 'permutation_not_better': False, 'oracle_floor_respected': True, 'tail_mass_toward_nominal': True}

## WR — **POWER_LIMITED**

`tail_ext` TIES `incumbent` by +0.0027 CRPS (interval unevaluable)

| label               |   mean_crps_q199 |
|:--------------------|-----------------:|
| matched_n__tail_ext |          2.44156 |
| tail_ext            |          2.44158 |
| permuted_tail       |          2.44158 |
| oracle__tail_ext    |          2.44158 |
| pooled_tail         |          2.44164 |
| over_ext            |          2.44272 |
| incumbent           |          2.44431 |
| zero_width          |          3.36273 |
| max_width           |          3.50078 |

- fold wins 2/2 (clause requires None) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) None · p None · BH False
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side): dev 0.05128 → 0.00372 (delta +0.04756) · p_below_eval/p_above_eval incumbent 0.02228/0.039 → winner 0.00402/0.00774 · beyond-CHAMPION-grid mass (arm-invariant diagnostic, nominal 0.025/side) 0.04178/0.03931
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.8567, 'n_rows': 3231, 'binomial_se': 0.007, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'tail_ext': 0.8567, 'incumbent': 0.8567, 'over_ext': 0.8567, 'max_width': 0.9861}, 'coverage_95': {'tail_ext': 0.9461, 'incumbent': 0.9461, 'over_ext': 0.9461, 'max_width': 0.9978}, 'coverage_99': {'tail_ext': 0.9882, 'incumbent': 0.9461, 'over_ext': 1.0, 'max_width': 0.9978}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'marginal_share': {'mean_delta': 0.00272, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'alignment_share': {'mean_delta': 1e-05, 'ci95': [None, None], 'fold_wins': 1, 'p_one_sided': None}, 'conditioning_margin': {'mean_delta': 6e-05, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'note': "marginal_share = incumbent − permuted_tail (the shuffle-surviving channel; EXPECTED positive — NF-D16 (2)); alignment_share = permuted_tail − tail_ext; conditioning_margin = pooled_tail − tail_ext (per-position conditioning's earn in the tail; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_loses': True, 'winner_beats_permuted': True, 'permuted_not_significantly_better': True, 'no_arm_beats_own_oracle': False, 'oracle_floor_respected_at_matched_n': False}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 2.44158, 'own_form_oracle': 2.44158, 'matched_n': 2.44156, 'oracle_beats_matched_n': False}
- permutation: {'permuted_better_mean': -1e-05, 'permuted_better_p_one_sided': None} · thin tail cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0027, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_champion': True, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'coverage_floor_ok': True, 'degenerates_lose': True, 'permutation_not_better': True, 'oracle_floor_respected': False, 'tail_mass_toward_nominal': True}

## TE — **POWER_LIMITED**

`tail_ext` TIES `incumbent` by +0.0016 CRPS (interval unevaluable)

| label               |   mean_crps_q199 |
|:--------------------|-----------------:|
| oracle__tail_ext    |          1.78433 |
| matched_n__tail_ext |          1.78443 |
| pooled_tail         |          1.78460 |
| tail_ext            |          1.78479 |
| permuted_tail       |          1.78494 |
| over_ext            |          1.78550 |
| incumbent           |          1.78641 |
| zero_width          |          2.44472 |
| max_width           |          2.55497 |

- fold wins 2/2 (clause requires None) · PBO None (UNDEFINED by design) · DSR(=PSR, 1-arm) None · p None · BH False
- tail-mass gate (two-sided, beyond-EVAL-grid mass, nominal 0.005/side): dev 0.03894 → 0.00979 (delta +0.02915) · p_below_eval/p_above_eval incumbent 0.00618/0.04276 → winner 0.00103/0.01082 · beyond-CHAMPION-grid mass (arm-invariant diagnostic, nominal 0.025/side) 0.02576/0.04328
- coverage (floor 0.8, structurally inactive here): {'coverage_80': 0.8774, 'n_rows': 1941, 'binomial_se': 0.0091, 'blocking_shortfall': False, 'structurally_inactive': True, 'inactive_note': "identical to the incumbent's by construction — passing the floor is NOT evidence (NF-D20 (g⁗))."} · map {'coverage_80': {'tail_ext': 0.8774, 'incumbent': 0.8774, 'over_ext': 0.8774, 'max_width': 0.984}, 'coverage_95': {'tail_ext': 0.9541, 'incumbent': 0.9541, 'over_ext': 0.9541, 'max_width': 0.9974}, 'coverage_99': {'tail_ext': 0.9881, 'incumbent': 0.9541, 'over_ext': 0.9985, 'max_width': 0.9974}} · fingerprint {'incumbent_cov95_equals_cov99': True, 'winner_cov99_exceeds_cov95': True, 'note': 'the flat-tail fingerprint (cov95 ≡ cov99) must hold for the incumbent and BREAK for the winner — a construction sanity read, report-only.'}
- attribution (pre-registered, report-only): {'marginal_share': {'mean_delta': 0.00147, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'alignment_share': {'mean_delta': 0.00016, 'ci95': [None, None], 'fold_wins': 2, 'p_one_sided': None}, 'conditioning_margin': {'mean_delta': -0.00019, 'ci95': [None, None], 'fold_wins': 0, 'p_one_sided': None}, 'note': "marginal_share = incumbent − permuted_tail (the shuffle-surviving channel; EXPECTED positive — NF-D16 (2)); alignment_share = permuted_tail − tail_ext; conditioning_margin = pooled_tail − tail_ext (per-position conditioning's earn in the tail; informs the serving object)."}
- anchors: {'zero_width_loses': True, 'max_width_loses': True, 'max_width_satisfies_floor': True, 'over_ext_loses': True, 'winner_beats_permuted': True, 'permuted_not_significantly_better': True, 'no_arm_beats_own_oracle': True, 'oracle_floor_respected_at_matched_n': True}
- oracle floor (NF-D16 (g‴)) at matched n (NF1.9 (f)): {'arm': 1.78479, 'own_form_oracle': 1.78433, 'matched_n': 1.78443, 'oracle_beats_matched_n': True}
- permutation: {'permuted_better_mean': -0.00016, 'permuted_better_p_one_sided': None} · thin tail cells: {'n_fold_positions_thin_hi': 0, 'n_fold_positions_thin_lo': 0}
- 📅 era note: {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0016, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.'}
- gate: {'beats_champion': True, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'coverage_floor_ok': True, 'degenerates_lose': True, 'permutation_not_better': True, 'oracle_floor_respected': True, 'tail_mass_toward_nominal': True}

## Null-state classification

```json
{
  "QB": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_margin2_QB_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0043 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 2/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~2 half-season folds (\u22481 seasons) for the DSR gate at the observed per-fold Sharpe 12.633 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test."
  },
  "RB": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_margin2_RB_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0035 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 2/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~2 half-season folds (\u22481 seasons) for the DSR gate at the observed per-fold Sharpe 6.086 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test."
  },
  "WR": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_margin2_WR_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0027 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 2/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~2 half-season folds (\u22481 seasons) for the DSR gate at the observed per-fold Sharpe 4.427 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test."
  },
  "TE": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_margin2_TE_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0016 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 2/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~2 half-season folds (\u22481 seasons) for the DSR gate at the observed per-fold Sharpe 10.648 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test."
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