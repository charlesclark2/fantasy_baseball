# NF-W4 — availability & playing-time: the availability mixture (§0.5 bake-off)

**Generated:** 2026-08-11T03:01:54+00:00 · **folds:** 8 half-season blocks (2022H1…2025H2, the NF-W1 axis on the NF-W2d two-era matrix) · **player-weeks:** 84553

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (serving is NF-W8 / NF-C6 Ph2). Selection metric is CRPS (`crps_q39`; T1 in exact Bernoulli closed form — the dense-grid limit of the same identity); MAE is reported and NEVER selects. Every direction word below is three-way and **derived from the interval at report time**, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-W4):** 532 game-groups / 183314 records (15401 injury, 83360 rate, 9501 wayback-provenance) checked; 0 rows dropped fail-closed.

## ⭐ Oracle first — the realized-availability ceiling

Scored BEFORE any arm is judged (NF-W3's transferable discipline): the peeking substitution of the target week's realized played indicator + measured snap share into the injury-aware champion. This bounds the whole availability channel from above.

| position   |   champion_crps |   oracle_ceiling_delta |   ceiling_pct_of_champion | ceiling_ci95     | fold_wins   |
|:-----------|----------------:|-----------------------:|--------------------------:|:-----------------|:------------|
| QB         |          2.4562 |                 0.6827 |                     27.79 | [0.5864, 0.7791] | 8/8         |
| RB         |          2.4026 |                 0.4851 |                     20.19 | [0.4416, 0.5286] | 8/8         |
| WR         |          2.5592 |                 0.2729 |                     10.66 | [0.23, 0.3158]   | 8/8         |
| TE         |          1.7608 |                 0.1427 |                      8.1  | [0.1115, 0.1738] | 8/8         |

## ⭐ Headline

- **Layer A (does the availability component beat its own climatology?)** — played: **SHIP** · snap_share: **POWER_LIMITED**
- **Layer B (does PROJECTED availability improve the assembled projection vs the INJURY-AWARE champion?)** — QB: **GENUINE_ABSENCE** · RB: **GENUINE_ABSENCE** · WR: **GENUINE_ABSENCE** · TE: **POWER_LIMITED**

## Layer A — the component bake-offs

### `played` — **SHIP** (metric `crps_bernoulli_exact`)

`lgbm_binary` BEATS `foil_clim_inj` by +0.0220 CRPS (CI95 [+0.0208, +0.0232] excludes zero)

| label                  |   mean_crps |
|:-----------------------|------------:|
| oracle__two_stage      |     0.00352 |
| oracle__lgbm_binary    |     0.00562 |
| lgbm_binary            |     0.07758 |
| two_stage              |     0.07978 |
| oracle__logit_glm      |     0.08429 |
| logit_glm              |     0.08621 |
| knn_rate               |     0.08913 |
| matched_n__logit_glm   |     0.09185 |
| matched_n__lgbm_binary |     0.09544 |
| matched_n__two_stage   |     0.09923 |
| foil_clim_inj          |     0.09955 |
| oracle__foil_clim_inj  |     0.11733 |
| oracle__knn_rate       |     0.11863 |
| oracle__foil_clim      |     0.11870 |
| foil_clim              |     0.11926 |
| matched_n__knn_rate    |     0.12119 |
| marginal_train         |     0.14829 |
| permuted_within        |     0.14912 |
| zero_width             |     0.26492 |
| max_width              |     0.33333 |
| nihilist_zero          |     0.79179 |

- fold wins 8/8 (clause requires 6) · PBO 0.0 · DSR 0.995 · p 0.0 · BH own-family True / pooled True (binding True)
- anchors: {'nihilist_loses': True, 'marginal_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': False, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': False}
- per-form oracle floors (NF-D16 (g‴)) + matched-n capacity control (NF1.9 (f)): {'logit_glm': {'arm': 0.08621, 'own_form_oracle': 0.08429, 'matched_n': 0.09185, 'oracle_beats_matched_n': True}, 'lgbm_binary': {'arm': 0.07758, 'own_form_oracle': 0.00562, 'matched_n': 0.09544, 'oracle_beats_matched_n': True}, 'two_stage': {'arm': 0.07978, 'own_form_oracle': 0.00352, 'matched_n': 0.09923, 'oracle_beats_matched_n': True}, 'knn_rate': {'arm': 0.08913, 'own_form_oracle': 0.11863, 'matched_n': 0.12119, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_foil_mean': -0.04957, 'permuted_lift_p_one_sided': 1.0} · coverage(80) {'winner_coverage_80': 0.9828, 'n_rows': 34552, 'binomial_se': 0.0022, 'blocking_shortfall': False, 'structurally_inactive': True} ⚠️ T1's coverage clause is STRUCTURALLY NEAR-INACTIVE (two-point band) — recorded, never credited (NF-D20).
- MAE (report-only, never selects): {'lgbm_binary': 0.10568, 'foil_clim_inj': 0.11999, 'nihilist_zero': 0.79179, 'marginal_train': 0.20698}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': True, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True}

### `snap_share` — **POWER_LIMITED** (metric `crps_q39`)

`lgbm_quantile` BEATS `foil_clim_inj` by +0.0338 CRPS (CI95 [+0.0320, +0.0355] excludes zero)

| label                    |   mean_crps |
|:-------------------------|------------:|
| oracle__lgbm_quantile    |     0.06374 |
| lgbm_quantile            |     0.08663 |
| matched_n__lgbm_quantile |     0.09325 |
| oracle__beta_mom         |     0.09445 |
| beta_mom                 |     0.09546 |
| oracle__frac_logit       |     0.09609 |
| frac_logit               |     0.09678 |
| knn_quantile             |     0.09826 |
| matched_n__beta_mom      |     0.09908 |
| matched_n__frac_logit    |     0.10090 |
| oracle__knn_quantile     |     0.10996 |
| matched_n__knn_quantile  |     0.11390 |
| oracle__foil_clim_inj    |     0.12026 |
| foil_clim_inj            |     0.12042 |
| oracle__foil_clim        |     0.12090 |
| foil_clim                |     0.12098 |
| max_width                |     0.16078 |
| permuted_within          |     0.16739 |
| marginal_train           |     0.16775 |
| zero_width               |     0.17224 |
| nihilist_zero            |     0.47384 |

- fold wins 8/8 (clause requires 6) · PBO 0.0 · DSR 1.0 · p 0.0 · BH own-family True / pooled True (binding True)
- anchors: {'nihilist_loses': True, 'marginal_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': False, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) + matched-n capacity control (NF1.9 (f)): {'frac_logit': {'arm': 0.09678, 'own_form_oracle': 0.09609, 'matched_n': 0.1009, 'oracle_beats_matched_n': True}, 'beta_mom': {'arm': 0.09546, 'own_form_oracle': 0.09445, 'matched_n': 0.09908, 'oracle_beats_matched_n': True}, 'lgbm_quantile': {'arm': 0.08663, 'own_form_oracle': 0.06374, 'matched_n': 0.09325, 'oracle_beats_matched_n': True}, 'knn_quantile': {'arm': 0.09826, 'own_form_oracle': 0.10996, 'matched_n': 0.1139, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_foil_mean': -0.04697, 'permuted_lift_p_one_sided': 1.0} · coverage(80) {'winner_coverage_80': 0.7884, 'n_rows': 27348, 'binomial_se': 0.0024, 'blocking_shortfall': True, 'structurally_inactive': False}
- T2 population (⛔ no fillna(0) — NF-W0b): {'n_rows': 34552, 'n_played': 27355, 'n_scored': 27348, 'n_played_unmeasured_excluded': 7} — played-but-unmeasured rows are EXCLUDED AND COUNTED, never imputed.
- MAE (report-only, never selects): {'lgbm_quantile': 0.1168, 'foil_clim_inj': 0.17014, 'nihilist_zero': 0.47384, 'marginal_train': 0.2446}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': True, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': False}

## ⭐ Layer B — the gate: does projected availability move the PLAYER projection?

Availability forms carried into Layer B (the Layer-A winners): `{'played': 'lgbm_binary', 'snap_share': 'lgbm_quantile'}` · matched-foil forms: `{'played': 'foil_clim_inj', 'snap_share': 'foil_clim_inj'}` · incumbent per position: `{'QB': 'inj_zero_leg', 'RB': 'inj_both', 'WR': 'inj_both', 'TE': 'inj_zero_leg'}` (pinned to the committed NF-W2d artifact).

### QB — **GENUINE_ABSENCE** (incumbent `inj_zero_leg`)

`champion_avail` LOSES TO `champion_inj` by -0.0281 CRPS (CI95 [-0.0440, -0.0122] excludes zero)

| label                   |   mean_crps |
|:------------------------|------------:|
| avail_oracle_zero_leg   |      1.7734 |
| avail_oracle_both       |      1.7735 |
| inj_both                |      2.4549 |
| inj_zero_leg            |      2.4562 |
| avail_shuffled_zero_leg |      2.4599 |
| avail_shuffled_both     |      2.4637 |
| avail_foil_zero_leg     |      2.4644 |
| avail_foil_both         |      2.4649 |
| avail_both              |      2.4832 |
| avail_zero_leg          |      2.4843 |

- ⭐ **realized-availability CEILING** (`champion_avail_oracle`, peeking): `champion_avail_oracle` BEATS `champion_inj` by +0.6827 CRPS (CI95 [+0.5864, +0.7791] excludes zero), 8/8 folds. This bounds what the availability chain can buy at the player level over the injury-aware champion.
- matched foil-availability anchor (block from the climatology+designation foil — attributes any lift to the LEARNED component): `champion_avail_foil` TIES `champion_inj` by -0.0082 CRPS (CI95 [-0.0227, +0.0063] spans zero)
- fold wins 1/8 (clause requires 6) · PBO None (UNDEFINED — CSCV resampl…) · DSR 0.0021 · p 0.998 · BH own-family False / pooled False (binding False)
- anchors {'winner_beats_shuffled': False, 'shuffled_lift_not_significant': True, 'respects_realized_oracle': True} · shuffle {'shuffled_lift_mean': -0.0037, 'shuffled_lift_p_one_sided': 0.8232} · coverage(80) {'winner_coverage_80': 0.8179, 'n_rows': 5485, 'binomial_se': 0.0054, 'blocking_shortfall': False}
- 📅 era note (lift sizing — NF-W2d/W2e): {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': -0.0253, 'legacy_mean_delta': -0.029, 'note': 'REPORT-ONLY (n=2 capture folds — a design quantity, never a gate): forward-looking lift sizing quotes the capture era (NF-W2d/W2e).'}
- gate: {'beats_champion': False, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'permutation_behaves': False, 'oracle_floor_respected': True, 'coverage_floor_ok': True}
- 🩹 **hand-corrected classification** (the classify_null field-size gap, third instance in this vertical): instrument said `UNDEFINED`; corrected state **GENUINE_ABSENCE** — the arm LOSES to the champion on average (-0.0281 CRPS over 8 folds, 1/8 fold wins) — a negative point estimate is not rescued by more folds or a smaller field. Re-test trigger: None

### RB — **GENUINE_ABSENCE** (incumbent `inj_both`)

`champion_avail` TIES `champion_inj` by -0.0067 CRPS (CI95 [-0.0154, +0.0021] spans zero)

| label                   |   mean_crps |
|:------------------------|------------:|
| avail_oracle_both       |      1.9175 |
| avail_oracle_zero_leg   |      1.9210 |
| avail_shuffled_both     |      2.4014 |
| avail_foil_both         |      2.4019 |
| inj_both                |      2.4026 |
| avail_shuffled_zero_leg |      2.4035 |
| inj_zero_leg            |      2.4052 |
| avail_foil_zero_leg     |      2.4061 |
| avail_zero_leg          |      2.4065 |
| avail_both              |      2.4093 |

- ⭐ **realized-availability CEILING** (`champion_avail_oracle`, peeking): `champion_avail_oracle` BEATS `champion_inj` by +0.4851 CRPS (CI95 [+0.4416, +0.5286] excludes zero), 8/8 folds. This bounds what the availability chain can buy at the player level over the injury-aware champion.
- matched foil-availability anchor (block from the climatology+designation foil — attributes any lift to the LEARNED component): `champion_avail_foil` TIES `champion_inj` by +0.0007 CRPS (CI95 [-0.0053, +0.0068] spans zero)
- fold wins 1/8 (clause requires 6) · PBO None (UNDEFINED — CSCV resampl…) · DSR 0.0105 · p 0.9416 · BH own-family False / pooled False (binding False)
- anchors {'winner_beats_shuffled': False, 'shuffled_lift_not_significant': True, 'respects_realized_oracle': True} · shuffle {'shuffled_lift_mean': 0.0012, 'shuffled_lift_p_one_sided': 0.2958} · coverage(80) {'winner_coverage_80': 0.8406, 'n_rows': 8591, 'binomial_se': 0.0043, 'blocking_shortfall': False}
- 📅 era note (lift sizing — NF-W2d/W2e): {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0021, 'legacy_mean_delta': -0.0096, 'note': 'REPORT-ONLY (n=2 capture folds — a design quantity, never a gate): forward-looking lift sizing quotes the capture era (NF-W2d/W2e).'}
- gate: {'beats_champion': False, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'permutation_behaves': False, 'oracle_floor_respected': True, 'coverage_floor_ok': True}
- 🩹 **hand-corrected classification** (the classify_null field-size gap, third instance in this vertical): instrument said `UNDEFINED`; corrected state **GENUINE_ABSENCE** — the arm LOSES to the champion on average (-0.0067 CRPS over 8 folds, 1/8 fold wins) — a negative point estimate is not rescued by more folds or a smaller field. Re-test trigger: None

### WR — **GENUINE_ABSENCE** (incumbent `inj_both`)

`champion_avail` TIES `champion_inj` by -0.0046 CRPS (CI95 [-0.0140, +0.0049] spans zero)

| label                   |   mean_crps |
|:------------------------|------------:|
| avail_oracle_both       |      2.2863 |
| avail_oracle_zero_leg   |      2.2883 |
| inj_zero_leg            |      2.5589 |
| inj_both                |      2.5592 |
| avail_shuffled_both     |      2.5608 |
| avail_foil_zero_leg     |      2.5610 |
| avail_shuffled_zero_leg |      2.5613 |
| avail_both              |      2.5637 |
| avail_zero_leg          |      2.5643 |
| avail_foil_both         |      2.5644 |

- ⭐ **realized-availability CEILING** (`champion_avail_oracle`, peeking): `champion_avail_oracle` BEATS `champion_inj` by +0.2729 CRPS (CI95 [+0.2300, +0.3158] excludes zero), 8/8 folds. This bounds what the availability chain can buy at the player level over the injury-aware champion.
- matched foil-availability anchor (block from the climatology+designation foil — attributes any lift to the LEARNED component): `champion_avail_foil` LOSES TO `champion_inj` by -0.0052 CRPS (CI95 [-0.0083, -0.0021] excludes zero)
- fold wins 2/8 (clause requires 6) · PBO None (UNDEFINED — CSCV resampl…) · DSR 0.1515 · p 0.8547 · BH own-family False / pooled False (binding False)
- anchors {'winner_beats_shuffled': False, 'shuffled_lift_not_significant': True, 'respects_realized_oracle': True} · shuffle {'shuffled_lift_mean': -0.0017, 'shuffled_lift_p_one_sided': 0.715} · coverage(80) {'winner_coverage_80': 0.8548, 'n_rows': 12827, 'binomial_se': 0.0035, 'blocking_shortfall': False}
- 📅 era note (lift sizing — NF-W2d/W2e): {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0018, 'legacy_mean_delta': -0.0067, 'note': 'REPORT-ONLY (n=2 capture folds — a design quantity, never a gate): forward-looking lift sizing quotes the capture era (NF-W2d/W2e).'}
- gate: {'beats_champion': False, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'permutation_behaves': False, 'oracle_floor_respected': True, 'coverage_floor_ok': True}
- 🩹 **hand-corrected classification** (the classify_null field-size gap, third instance in this vertical): instrument said `UNDEFINED`; corrected state **GENUINE_ABSENCE** — the arm LOSES to the champion on average (-0.0046 CRPS over 8 folds, 2/8 fold wins) — a negative point estimate is not rescued by more folds or a smaller field. Re-test trigger: None

### TE — **POWER_LIMITED** (incumbent `inj_zero_leg`)

`champion_avail` TIES `champion_inj` by +0.0007 CRPS (CI95 [-0.0049, +0.0062] spans zero)

| label                   |   mean_crps |
|:------------------------|------------:|
| avail_oracle_both       |      1.6178 |
| avail_oracle_zero_leg   |      1.6181 |
| avail_shuffled_both     |      1.7595 |
| avail_zero_leg          |      1.7601 |
| avail_shuffled_zero_leg |      1.7604 |
| avail_both              |      1.7605 |
| inj_zero_leg            |      1.7608 |
| avail_foil_zero_leg     |      1.7608 |
| avail_foil_both         |      1.7609 |
| inj_both                |      1.7613 |

- ⭐ **realized-availability CEILING** (`champion_avail_oracle`, peeking): `champion_avail_oracle` BEATS `champion_inj` by +0.1427 CRPS (CI95 [+0.1115, +0.1738] excludes zero), 8/8 folds. This bounds what the availability chain can buy at the player level over the injury-aware champion.
- matched foil-availability anchor (block from the climatology+designation foil — attributes any lift to the LEARNED component): `champion_avail_foil` TIES `champion_inj` by -0.0000 CRPS (CI95 [-0.0053, +0.0053] spans zero)
- fold wins 5/8 (clause requires 6) · PBO None (UNDEFINED — CSCV resampl…) · DSR 0.6004 · p 0.3916 · BH own-family False / pooled False (binding False)
- anchors {'winner_beats_shuffled': True, 'shuffled_lift_not_significant': True, 'respects_realized_oracle': True} · shuffle {'shuffled_lift_mean': 0.0004, 'shuffled_lift_p_one_sided': 0.4416} · coverage(80) {'winner_coverage_80': 0.8812, 'n_rows': 7649, 'binomial_se': 0.0046, 'blocking_shortfall': False}
- 📅 era note (lift sizing — NF-W2d/W2e): {'capture_folds': ['2025H1', '2025H2'], 'capture_mean_delta': 0.0003, 'legacy_mean_delta': 0.0008, 'note': 'REPORT-ONLY (n=2 capture folds — a design quantity, never a gate): forward-looking lift sizing quotes the capture era (NF-W2d/W2e).'}
- gate: {'beats_champion': True, 'fold_consistency': False, 'dsr_ok': False, 'fdr_ok': False, 'permutation_behaves': True, 'oracle_floor_respected': True, 'coverage_floor_ok': True}
- 🩹 **hand-corrected classification** (the classify_null field-size gap, third instance in this vertical): instrument said `UNDEFINED`; corrected state **POWER_LIMITED** — the point estimate is positive (+0.0007 CRPS) but the interval spans zero (CI95 [-0.0049, 0.0062]), fold wins are 5/8 against a required 6, and p=0.3916. Every statistical gate except PBO is REACHABLE at this design — the effect is simply smaller than this design can resolve. Re-test trigger: ~267 half-season folds (≈133 seasons) for the DSR gate at the observed per-fold Sharpe 0.101 — i.e. CALENDAR-bound and far beyond any plausible window; ⛔ this is NOT a near-term re-test.

## Null-state classification

```json
{
  "layer_a::snap_share": {
    "state": "POWER_LIMITED",
    "reason": "`nf_w4_snap_share_crps`: insufficient recorded statistics to certify the null as powered. Absent a detectability figure the honest default is POWER-LIMITED \u2014 a null is trustworthy only when something was computed to make it so.",
    "retest_trigger": null
  },
  "layer_b::QB": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w4_downstream_crps_QB`: 8 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "-4 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "GENUINE_ABSENCE",
    "reason": "the arm LOSES to the champion on average (-0.0281 CRPS over 8 folds, 1/8 fold wins) \u2014 a negative point estimate is not rescued by more folds or a smaller field.",
    "retest_trigger": null
  },
  "layer_b::RB": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w4_downstream_crps_RB`: 8 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "-4 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "GENUINE_ABSENCE",
    "reason": "the arm LOSES to the champion on average (-0.0067 CRPS over 8 folds, 1/8 fold wins) \u2014 a negative point estimate is not rescued by more folds or a smaller field.",
    "retest_trigger": null
  },
  "layer_b::WR": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w4_downstream_crps_WR`: 8 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "-4 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "GENUINE_ABSENCE",
    "reason": "the arm LOSES to the champion on average (-0.0046 CRPS over 8 folds, 2/8 fold wins) \u2014 a negative point estimate is not rescued by more folds or a smaller field.",
    "retest_trigger": null
  },
  "layer_b::TE": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w4_downstream_crps_TE`: 8 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "-4 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0007 CRPS) but the interval spans zero (CI95 [-0.0049, 0.0062]), fold wins are 5/8 against a required 6, and p=0.3916. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~267 half-season folds (\u2248133 seasons) for the DSR gate at the observed per-fold Sharpe 0.101 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test."
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