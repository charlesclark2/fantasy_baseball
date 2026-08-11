# NF-W4 — availability & playing-time: the availability mixture (§0.5 bake-off)

**Generated:** 2026-08-11T01:53:22+00:00 · **folds:** 2 half-season blocks (2025H1…2025H2, the NF-W1 axis on the NF-W2d two-era matrix) · **player-weeks:** 84553

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (serving is NF-W8 / NF-C6 Ph2). Selection metric is CRPS (`crps_q39`; T1 in exact Bernoulli closed form — the dense-grid limit of the same identity); MAE is reported and NEVER selects. Every direction word below is three-way and **derived from the interval at report time**, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-W4):** 532 game-groups / 183314 records (15401 injury, 83360 rate, 9501 wayback-provenance) checked; 0 rows dropped fail-closed.

## ⭐ Oracle first — the realized-availability ceiling

Scored BEFORE any arm is judged (NF-W3's transferable discipline): the peeking substitution of the target week's realized played indicator + measured snap share into the injury-aware champion. This bounds the whole availability channel from above.

| position   |   champion_crps |   oracle_ceiling_delta |   ceiling_pct_of_champion | ceiling_ci95   | fold_wins   |
|:-----------|----------------:|-----------------------:|--------------------------:|:---------------|:------------|
| QB         |          2.5819 |                 0.7031 |                     27.23 | [None, None]   | 2/2         |
| RB         |          2.4076 |                 0.4488 |                     18.64 | [None, None]   | 2/2         |
| WR         |          2.4885 |                 0.307  |                     12.34 | [None, None]   | 2/2         |
| TE         |          1.8182 |                 0.1368 |                      7.52 | [None, None]   | 2/2         |

## ⭐ Headline

- **Layer A (does the availability component beat its own climatology?)** — played: **UNDEFINED** · snap_share: **UNDEFINED**
- **Layer B (does PROJECTED availability improve the assembled projection vs the INJURY-AWARE champion?)** — QB: **GENUINE_ABSENCE** · RB: **POWER_LIMITED** · WR: **POWER_LIMITED** · TE: **POWER_LIMITED**

## Layer A — the component bake-offs

### `played` — **UNDEFINED** (metric `crps_bernoulli_exact`)

`lgbm_binary` TIES `foil_clim_inj` by +0.0227 CRPS (interval unevaluable)

| label                  |   mean_crps |
|:-----------------------|------------:|
| oracle__two_stage      |     0.00316 |
| oracle__lgbm_binary    |     0.00532 |
| lgbm_binary            |     0.08348 |
| two_stage              |     0.08674 |
| oracle__logit_glm      |     0.08991 |
| logit_glm              |     0.09271 |
| knn_rate               |     0.09574 |
| matched_n__logit_glm   |     0.09924 |
| matched_n__lgbm_binary |     0.10353 |
| foil_clim_inj          |     0.10619 |
| matched_n__two_stage   |     0.10642 |
| oracle__foil_clim_inj  |     0.11780 |
| oracle__foil_clim      |     0.11815 |
| foil_clim              |     0.11848 |
| oracle__knn_rate       |     0.11975 |
| matched_n__knn_rate    |     0.12371 |
| marginal_train         |     0.14940 |
| permuted_within        |     0.15260 |
| zero_width             |     0.26339 |
| max_width              |     0.33333 |
| nihilist_zero          |     0.79123 |

- fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · BH own-family False / pooled False (binding False)
- anchors: {'nihilist_loses': True, 'marginal_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': False, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': False}
- per-form oracle floors (NF-D16 (g‴)) + matched-n capacity control (NF1.9 (f)): {'logit_glm': {'arm': 0.09271, 'own_form_oracle': 0.08991, 'matched_n': 0.09924, 'oracle_beats_matched_n': True}, 'lgbm_binary': {'arm': 0.08348, 'own_form_oracle': 0.00532, 'matched_n': 0.10353, 'oracle_beats_matched_n': True}, 'two_stage': {'arm': 0.08674, 'own_form_oracle': 0.00316, 'matched_n': 0.10642, 'oracle_beats_matched_n': True}, 'knn_rate': {'arm': 0.09574, 'own_form_oracle': 0.11975, 'matched_n': 0.12371, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_foil_mean': -0.04641, 'permuted_lift_p_one_sided': None} · coverage(80) {'winner_coverage_80': 0.9777, 'n_rows': 8688, 'binomial_se': 0.0043, 'blocking_shortfall': False, 'structurally_inactive': True} ⚠️ T1's coverage clause is STRUCTURALLY NEAR-INACTIVE (two-point band) — recorded, never credited (NF-D20).
- MAE (report-only, never selects): {'lgbm_binary': 0.11034, 'foil_clim_inj': 0.12703, 'nihilist_zero': 0.79123, 'marginal_train': 0.209}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True}

### `snap_share` — **UNDEFINED** (metric `crps_q39`)

`lgbm_quantile` TIES `foil_clim_inj` by +0.0333 CRPS (interval unevaluable)

| label                    |   mean_crps |
|:-------------------------|------------:|
| oracle__lgbm_quantile    |     0.06428 |
| lgbm_quantile            |     0.08686 |
| matched_n__lgbm_quantile |     0.09376 |
| oracle__beta_mom         |     0.09555 |
| beta_mom                 |     0.09658 |
| oracle__frac_logit       |     0.09713 |
| frac_logit               |     0.09777 |
| knn_quantile             |     0.09899 |
| matched_n__beta_mom      |     0.10086 |
| matched_n__frac_logit    |     0.10247 |
| oracle__knn_quantile     |     0.11282 |
| matched_n__knn_quantile  |     0.11465 |
| oracle__foil_clim_inj    |     0.12002 |
| foil_clim_inj            |     0.12018 |
| oracle__foil_clim        |     0.12026 |
| foil_clim                |     0.12039 |
| max_width                |     0.16070 |
| permuted_within          |     0.16706 |
| marginal_train           |     0.16737 |
| zero_width               |     0.17088 |
| nihilist_zero            |     0.47030 |

- fold wins 2/2 (clause requires None) · PBO None · DSR None · p None · BH own-family False / pooled False (binding False)
- anchors: {'nihilist_loses': True, 'marginal_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': False, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) + matched-n capacity control (NF1.9 (f)): {'frac_logit': {'arm': 0.09777, 'own_form_oracle': 0.09713, 'matched_n': 0.10247, 'oracle_beats_matched_n': True}, 'beta_mom': {'arm': 0.09658, 'own_form_oracle': 0.09555, 'matched_n': 0.10086, 'oracle_beats_matched_n': True}, 'lgbm_quantile': {'arm': 0.08686, 'own_form_oracle': 0.06428, 'matched_n': 0.09376, 'oracle_beats_matched_n': True}, 'knn_quantile': {'arm': 0.09899, 'own_form_oracle': 0.11282, 'matched_n': 0.11465, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_foil_mean': -0.04687, 'permuted_lift_p_one_sided': None} · coverage(80) {'winner_coverage_80': 0.7758, 'n_rows': 6870, 'binomial_se': 0.0048, 'blocking_shortfall': True, 'structurally_inactive': False}
- T2 population (⛔ no fillna(0) — NF-W0b): {'n_rows': 8688, 'n_played': 6874, 'n_scored': 6870, 'n_played_unmeasured_excluded': 4} — played-but-unmeasured rows are EXCLUDED AND COUNTED, never imputed.
- MAE (report-only, never selects): {'lgbm_quantile': 0.11738, 'foil_clim_inj': 0.16988, 'nihilist_zero': 0.4703, 'marginal_train': 0.24265}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': False}

## ⭐ Layer B — the gate: does projected availability move the PLAYER projection?

Availability forms carried into Layer B (the Layer-A winners): `{'played': 'lgbm_binary', 'snap_share': 'lgbm_quantile'}` · matched-foil forms: `{'played': 'foil_clim_inj', 'snap_share': 'foil_clim_inj'}` · incumbent per position: `{'QB': 'inj_zero_leg', 'RB': 'inj_both', 'WR': 'inj_both', 'TE': 'inj_zero_leg'}` (pinned to the committed NF-W2d artifact).

### QB — **GENUINE_ABSENCE** (incumbent `inj_zero_leg`)

`champion_avail` TIES `champion_inj` by -0.0253 CRPS (interval unevaluable)

| label                   |   mean_crps |
|:------------------------|------------:|
| avail_oracle_both       |      1.8763 |
| avail_oracle_zero_leg   |      1.8788 |
| avail_foil_zero_leg     |      2.5734 |
| inj_both                |      2.5772 |
| avail_shuffled_both     |      2.5805 |
| inj_zero_leg            |      2.5819 |
| avail_shuffled_zero_leg |      2.5822 |
| avail_foil_both         |      2.5849 |
| avail_zero_leg          |      2.6072 |
| avail_both              |      2.6080 |

- ⭐ **realized-availability CEILING** (`champion_avail_oracle`, peeking): `champion_avail_oracle` TIES `champion_inj` by +0.7031 CRPS (interval unevaluable), 2/2 folds. This bounds what the availability chain can buy at the player level over the injury-aware champion.
- matched foil-availability anchor (block from the climatology+designation foil — attributes any lift to the LEARNED component): `champion_avail_foil` TIES `champion_inj` by +0.0085 CRPS (interval unevaluable)
- fold wins 0/2 (clause requires None) · PBO None (UNDEFINED — CSCV resampl…) · DSR None · p None · BH own-family False / pooled False (binding False)
- anchors {'winner_beats_shuffled': False, 'shuffled_lift_not_significant': True, 'respects_realized_oracle': True} · shuffle {'shuffled_lift_mean': -0.0003, 'shuffled_lift_p_one_sided': None} · coverage(80) {'winner_coverage_80': 0.7996, 'n_rows': 1372, 'binomial_se': 0.0108, 'blocking_shortfall': False}
- 📅 era note (lift sizing — NF-W2d/W2e): {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': -0.0253, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (n=2 capture folds — a design quantity, never a gate): forward-looking lift sizing quotes the capture era (NF-W2d/W2e).'}
- gate: {'beats_champion': False, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'permutation_behaves': False, 'oracle_floor_respected': True, 'coverage_floor_ok': True}
- 🩹 **hand-corrected classification** (the classify_null field-size gap, third instance in this vertical): instrument said `UNDEFINED`; corrected state **GENUINE_ABSENCE** — the arm LOSES to the champion on average (-0.0253 CRPS over 2 folds, 0/2 fold wins) — a negative point estimate is not rescued by more folds or a smaller field. Re-test trigger: None

### RB — **POWER_LIMITED** (incumbent `inj_both`)

`champion_avail` TIES `champion_inj` by +0.0021 CRPS (interval unevaluable)

| label                   |   mean_crps |
|:------------------------|------------:|
| avail_oracle_both       |      1.9588 |
| avail_oracle_zero_leg   |      1.9605 |
| avail_zero_leg          |      2.3986 |
| avail_shuffled_both     |      2.4025 |
| avail_shuffled_zero_leg |      2.4042 |
| avail_both              |      2.4055 |
| inj_both                |      2.4076 |
| inj_zero_leg            |      2.4079 |
| avail_foil_both         |      2.4086 |
| avail_foil_zero_leg     |      2.4090 |

- ⭐ **realized-availability CEILING** (`champion_avail_oracle`, peeking): `champion_avail_oracle` TIES `champion_inj` by +0.4488 CRPS (interval unevaluable), 2/2 folds. This bounds what the availability chain can buy at the player level over the injury-aware champion.
- matched foil-availability anchor (block from the climatology+designation foil — attributes any lift to the LEARNED component): `champion_avail_foil` TIES `champion_inj` by -0.0010 CRPS (interval unevaluable)
- fold wins 1/2 (clause requires None) · PBO None (UNDEFINED — CSCV resampl…) · DSR None · p None · BH own-family False / pooled False (binding False)
- anchors {'winner_beats_shuffled': False, 'shuffled_lift_not_significant': False, 'respects_realized_oracle': True} · shuffle {'shuffled_lift_mean': 0.0051, 'shuffled_lift_p_one_sided': None} · coverage(80) {'winner_coverage_80': 0.8414, 'n_rows': 2144, 'binomial_se': 0.0086, 'blocking_shortfall': False}
- 📅 era note (lift sizing — NF-W2d/W2e): {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0021, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (n=2 capture folds — a design quantity, never a gate): forward-looking lift sizing quotes the capture era (NF-W2d/W2e).'}
- gate: {'beats_champion': True, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'permutation_behaves': False, 'oracle_floor_respected': True, 'coverage_floor_ok': True}
- 🩹 **hand-corrected classification** (the classify_null field-size gap, third instance in this vertical): instrument said `UNDEFINED`; corrected state **POWER_LIMITED** — the point estimate is positive (+0.0021 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 1/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design — the effect is simply smaller than this design can resolve. Re-test trigger: ~27 half-season folds (≈13 seasons) for the DSR gate at the observed per-fold Sharpe 0.324 — i.e. CALENDAR-bound and far beyond any plausible window; ⛔ this is NOT a near-term re-test.

### WR — **POWER_LIMITED** (incumbent `inj_both`)

`champion_avail` TIES `champion_inj` by +0.0018 CRPS (interval unevaluable)

| label                   |   mean_crps |
|:------------------------|------------:|
| avail_oracle_zero_leg   |      2.1808 |
| avail_oracle_both       |      2.1816 |
| avail_shuffled_zero_leg |      2.4839 |
| avail_shuffled_both     |      2.4866 |
| avail_both              |      2.4867 |
| avail_zero_leg          |      2.4883 |
| inj_both                |      2.4885 |
| inj_zero_leg            |      2.4888 |
| avail_foil_both         |      2.4938 |
| avail_foil_zero_leg     |      2.4947 |

- ⭐ **realized-availability CEILING** (`champion_avail_oracle`, peeking): `champion_avail_oracle` TIES `champion_inj` by +0.3070 CRPS (interval unevaluable), 2/2 folds. This bounds what the availability chain can buy at the player level over the injury-aware champion.
- matched foil-availability anchor (block from the climatology+designation foil — attributes any lift to the LEARNED component): `champion_avail_foil` TIES `champion_inj` by -0.0052 CRPS (interval unevaluable)
- fold wins 1/2 (clause requires None) · PBO None (UNDEFINED — CSCV resampl…) · DSR None · p None · BH own-family False / pooled False (binding False)
- anchors {'winner_beats_shuffled': False, 'shuffled_lift_not_significant': False, 'respects_realized_oracle': True} · shuffle {'shuffled_lift_mean': 0.0019, 'shuffled_lift_p_one_sided': None} · coverage(80) {'winner_coverage_80': 0.8576, 'n_rows': 3231, 'binomial_se': 0.007, 'blocking_shortfall': False}
- 📅 era note (lift sizing — NF-W2d/W2e): {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0018, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (n=2 capture folds — a design quantity, never a gate): forward-looking lift sizing quotes the capture era (NF-W2d/W2e).'}
- gate: {'beats_champion': True, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'permutation_behaves': False, 'oracle_floor_respected': True, 'coverage_floor_ok': True}
- 🩹 **hand-corrected classification** (the classify_null field-size gap, third instance in this vertical): instrument said `UNDEFINED`; corrected state **POWER_LIMITED** — the point estimate is positive (+0.0018 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 1/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design — the effect is simply smaller than this design can resolve. Re-test trigger: ~36 half-season folds (≈18 seasons) for the DSR gate at the observed per-fold Sharpe 0.282 — i.e. CALENDAR-bound and far beyond any plausible window; ⛔ this is NOT a near-term re-test.

### TE — **POWER_LIMITED** (incumbent `inj_zero_leg`)

`champion_avail` TIES `champion_inj` by +0.0003 CRPS (interval unevaluable)

| label                   |   mean_crps |
|:------------------------|------------:|
| avail_oracle_zero_leg   |      1.6814 |
| avail_oracle_both       |      1.6820 |
| avail_both              |      1.8179 |
| avail_zero_leg          |      1.8179 |
| inj_zero_leg            |      1.8182 |
| inj_both                |      1.8186 |
| avail_shuffled_both     |      1.8188 |
| avail_shuffled_zero_leg |      1.8215 |
| avail_foil_both         |      1.8218 |
| avail_foil_zero_leg     |      1.8237 |

- ⭐ **realized-availability CEILING** (`champion_avail_oracle`, peeking): `champion_avail_oracle` TIES `champion_inj` by +0.1368 CRPS (interval unevaluable), 2/2 folds. This bounds what the availability chain can buy at the player level over the injury-aware champion.
- matched foil-availability anchor (block from the climatology+designation foil — attributes any lift to the LEARNED component): `champion_avail_foil` TIES `champion_inj` by -0.0055 CRPS (interval unevaluable)
- fold wins 1/2 (clause requires None) · PBO None (UNDEFINED — CSCV resampl…) · DSR None · p None · BH own-family False / pooled False (binding False)
- anchors {'winner_beats_shuffled': True, 'shuffled_lift_not_significant': True, 'respects_realized_oracle': True} · shuffle {'shuffled_lift_mean': -0.0033, 'shuffled_lift_p_one_sided': None} · coverage(80) {'winner_coverage_80': 0.8784, 'n_rows': 1941, 'binomial_se': 0.0091, 'blocking_shortfall': False}
- 📅 era note (lift sizing — NF-W2d/W2e): {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0003, 'legacy_mean_delta': None, 'note': 'REPORT-ONLY (n=2 capture folds — a design quantity, never a gate): forward-looking lift sizing quotes the capture era (NF-W2d/W2e).'}
- gate: {'beats_champion': True, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'permutation_behaves': True, 'oracle_floor_respected': True, 'coverage_floor_ok': True}
- 🩹 **hand-corrected classification** (the classify_null field-size gap, third instance in this vertical): instrument said `UNDEFINED`; corrected state **POWER_LIMITED** — the point estimate is positive (+0.0003 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 1/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design — the effect is simply smaller than this design can resolve. Re-test trigger: ~1978 half-season folds (≈989 seasons) for the DSR gate at the observed per-fold Sharpe 0.037 — i.e. CALENDAR-bound and far beyond any plausible window; ⛔ this is NOT a near-term re-test.

## Null-state classification

```json
{
  "layer_a::played": {
    "state": "UNDEFINED",
    "reason": "`nf_w4_played_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_a::snap_share": {
    "state": "UNDEFINED",
    "reason": "`nf_w4_snap_share_crps`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_b::QB": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w4_downstream_crps_QB`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "GENUINE_ABSENCE",
    "reason": "the arm LOSES to the champion on average (-0.0253 CRPS over 2 folds, 0/2 fold wins) \u2014 a negative point estimate is not rescued by more folds or a smaller field.",
    "retest_trigger": null
  },
  "layer_b::RB": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w4_downstream_crps_RB`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0021 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 1/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~27 half-season folds (\u224813 seasons) for the DSR gate at the observed per-fold Sharpe 0.324 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test."
  },
  "layer_b::WR": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w4_downstream_crps_WR`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0018 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 1/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~36 half-season folds (\u224818 seasons) for the DSR gate at the observed per-fold Sharpe 0.282 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test."
  },
  "layer_b::TE": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w4_downstream_crps_TE`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0003 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 1/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~1978 half-season folds (\u2248989 seasons) for the DSR gate at the observed per-fold Sharpe 0.037 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test."
  }
}
```

## Pre-registration echo

```json
{
  "real_arms": {
    "played": [
      "logit_glm",
      "lgbm_binary",
      "two_stage",
      "knn_rate"
    ],
    "snap_share": [
      "frac_logit",
      "beta_mom",
      "lgbm_quantile",
      "knn_quantile"
    ]
  },
  "foils": [
    "foil_clim",
    "foil_clim_inj"
  ],
  "anchors": {
    "played": [
      "nihilist_zero",
      "marginal_train",
      "zero_width",
      "max_width",
      "permuted_within",
      "oracle__logit_glm",
      "oracle__lgbm_binary",
      "oracle__two_stage",
      "oracle__knn_rate",
      "oracle__foil_clim",
      "oracle__foil_clim_inj",
      "matched_n__logit_glm",
      "matched_n__lgbm_binary",
      "matched_n__two_stage",
      "matched_n__knn_rate"
    ],
    "snap_share": [
      "nihilist_zero",
      "marginal_train",
      "zero_width",
      "max_width",
      "permuted_within",
      "oracle__frac_logit",
      "oracle__beta_mom",
      "oracle__lgbm_quantile",
      "oracle__knn_quantile",
      "oracle__foil_clim",
      "oracle__foil_clim_inj",
      "matched_n__frac_logit",
      "matched_n__beta_mom",
      "matched_n__lgbm_quantile",
      "matched_n__knn_quantile"
    ]
  },
  "eligible": {
    "played": [
      "logit_glm",
      "lgbm_binary",
      "two_stage",
      "knn_rate",
      "foil_clim",
      "foil_clim_inj"
    ],
    "snap_share": [
      "frac_logit",
      "beta_mom",
      "lgbm_quantile",
      "knn_quantile",
      "foil_clim",
      "foil_clim_inj"
    ]
  },
  "layer_b_eligible": [
    "champion_inj",
    "champion_avail"
  ],
  "layer_b_anchors": [
    "champion_avail_foil",
    "champion_avail_shuffled",
    "champion_avail_oracle"
  ],
  "incumbent_of_position": {
    "QB": "inj_zero_leg",
    "RB": "inj_both",
    "WR": "inj_both",
    "TE": "inj_zero_leg"
  },
  "foil_forms": {
    "played": "foil_clim_inj",
    "snap_share": "foil_clim_inj"
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
    "component": [
      "played",
      "snap_share"
    ],
    "downstream": [
      "QB",
      "RB",
      "WR",
      "TE"
    ]
  },
  "coverage_floor": 0.8,
  "eb_kappa_avail": 4.0,
  "min_cell": 200,
  "inj_gate_classes_t1": [
    "out",
    "doubtful",
    "questionable",
    "listed_no_designation"
  ],
  "inj_mult_classes_t2": [
    "questionable",
    "listed_no_designation"
  ],
  "share_mult_clip": [
    0.25,
    1.5
  ],
  "avail_features": [
    "game_context__is_home",
    "game_context__week_index",
    "game_context__days_since_last_game",
    "prior_week_box__played_share_l4",
    "prior_week_box__games_s2d",
    "prior_week_box__ppr_l1",
    "prior_week_box__ppr_l4_mean",
    "prior_week_box__ppr_s2d_mean",
    "prior_week_box__targets_l4",
    "prior_week_box__carries_l4",
    "snap_share__l1",
    "snap_share__l4_mean",
    "snap_share__observed_l4",
    "prior_season_priors__games_prior",
    "prior_season_priors__ppg_prior",
    "prior_season_priors__rookie_flag",
    "injury_report__listed",
    "injury_report__status_out",
    "injury_report__status_doubtful",
    "injury_report__status_questionable",
    "injury_report__practice_dnp",
    "injury_report__practice_limited",
    "injury_report__observed",
    "injury_rate__listed",
    "injury_rate__status_out",
    "injury_rate__status_doubtful",
    "injury_rate__status_questionable",
    "injury_rate__practice_dnp",
    "injury_rate__practice_limited",
    "injury_rate__observed"
  ],
  "avail_proj_features": [
    "availability_projection__p_played",
    "availability_projection__snap_share",
    "availability_projection__expected_avail",
    "availability_projection__share_sd"
  ],
  "oracle_substituted": [
    "availability_projection__p_played",
    "availability_projection__snap_share",
    "availability_projection__expected_avail"
  ],
  "banned_feature_tokens": [
    "spread_line",
    "total_line",
    "vegas",
    "moneyline",
    "depth_chart",
    "depth_team",
    "gameday_inactive",
    "weather"
  ],
  "target_leak_tokens": [
    "offense_pct",
    "_t_played",
    "_t_share",
    "label",
    "status"
  ],
  "capture_era_folds": [
    "2025H1",
    "2025H2"
  ]
}
```