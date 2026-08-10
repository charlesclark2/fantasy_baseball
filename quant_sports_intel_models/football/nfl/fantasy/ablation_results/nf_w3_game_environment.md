# NF-W3 — game environment: team play-volume + pass/rush allocation (§0.5 bake-off)

**Generated:** 2026-08-10T03:17:40+00:00 · **folds:** 8 half-season blocks (2022H1…2025H2, the NF-W1 axis verbatim) · **team-games:** 5278 · **player-weeks:** 84553

> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (serving is NF-W8 / NF-C6 Ph2). Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects. Every direction word below is three-way and **derived from the interval at report time**, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a `assert_point_in_time`):** 175 weeks / 5278 team-game records checked; 0 rows in 0 weeks dropped fail-closed.

## ⭐ Headline

- **Layer A (does the component beat its own baseline?)** — off_plays: **DSR_UNREACHABLE** · pass_share: **POWER_LIMITED**
- **Layer B (does it improve the ASSEMBLED player projection vs the NF-W1 champion?)** — QB: **POWER_LIMITED** · RB: **POWER_LIMITED** · WR: **POWER_LIMITED** · TE: **GENUINE_ABSENCE**

## Layer A — the component bake-offs

### `off_plays` — **DSR_UNREACHABLE**

`negbin_glm` TIES `foil_team_eb` by +0.0367 CRPS (CI95 [-0.0155, +0.0889] spans zero)

| label                        |   mean_crps |
|:-----------------------------|------------:|
| oracle__lgbm_quantile        |      2.8662 |
| oracle__negbin_glm           |      4.4466 |
| oracle__pois_glm             |      4.4467 |
| oracle__knn_quantile         |      4.7890 |
| negbin_glm                   |      4.8185 |
| pois_glm                     |      4.8231 |
| oracle__foil_team_eb         |      4.8357 |
| matched_n__knn_quantile      |      4.8457 |
| knn_quantile                 |      4.8474 |
| foil_team_eb                 |      4.8552 |
| marginal_train               |      4.8681 |
| lgbm_quantile                |      4.9496 |
| permuted_within_week         |      4.9530 |
| matched_n__lgbm_quantile     |      5.1892 |
| oracle__foil_team_eb_matchup |      5.2019 |
| foil_team_eb_matchup         |      5.2213 |
| matched_n__negbin_glm        |      6.6200 |
| matched_n__pois_glm          |      6.6214 |
| zero_width                   |      6.7066 |
| max_width                    |      7.1041 |
| nihilist_zero                |     61.7013 |

- fold wins 6/8 (clause requires 6) · PBO 0.1429 · DSR 0.2993 · p 0.0702 · BH own-family True / pooled False (binding False)
- anchors: {'nihilist_loses': True, 'marginal_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) + matched-n capacity control (NF1.9 (f)): {'pois_glm': {'arm': 4.8231, 'own_form_oracle': 4.4467, 'matched_n': 6.6214, 'oracle_beats_matched_n': True}, 'negbin_glm': {'arm': 4.8185, 'own_form_oracle': 4.4466, 'matched_n': 6.62, 'oracle_beats_matched_n': True}, 'lgbm_quantile': {'arm': 4.9496, 'own_form_oracle': 2.8662, 'matched_n': 5.1892, 'oracle_beats_matched_n': True}, 'knn_quantile': {'arm': 4.8474, 'own_form_oracle': 4.789, 'matched_n': 4.8457, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_foil_mean': -0.0978, 'permuted_lift_p_one_sided': 0.9597} · coverage(80) {'winner_coverage_80': 0.8091, 'n_rows': 2174, 'binomial_se': 0.0086, 'blocking_shortfall': False}
- MAE (report-only, never selects): {'negbin_glm': 6.6606, 'foil_team_eb': 6.7025, 'nihilist_zero': 61.7013, 'marginal_train': 6.7547}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True}
- ⚠️ **field-shrink remedy is SUSPECT — NOT ADVICE** — the instrument suggests a smaller field, but this story's family of 4 arms was PRE-REGISTERED as the minimum §0.5 field (≥3 classes + a direct-learned foil). ⛔ Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one.

### `pass_share` — **POWER_LIMITED**

`betabinom` BEATS `foil_team_eb` by +0.0014 CRPS (CI95 [+0.0006, +0.0022] excludes zero)

| label                        |   mean_crps |
|:-----------------------------|------------:|
| oracle__lgbm_quantile        |      0.0336 |
| oracle__betabinom            |      0.0533 |
| oracle__binom_glm            |      0.0551 |
| betabinom                    |      0.0575 |
| oracle__foil_team_eb         |      0.0585 |
| knn_quantile                 |      0.0585 |
| lgbm_quantile                |      0.0588 |
| foil_team_eb                 |      0.0589 |
| oracle__knn_quantile         |      0.0593 |
| binom_glm                    |      0.0600 |
| matched_n__knn_quantile      |      0.0604 |
| oracle__foil_team_eb_matchup |      0.0605 |
| foil_team_eb_matchup         |      0.0607 |
| marginal_train               |      0.0614 |
| matched_n__lgbm_quantile     |      0.0622 |
| permuted_within_week         |      0.0626 |
| zero_width                   |      0.0817 |
| matched_n__betabinom         |      0.0874 |
| max_width                    |      0.0880 |
| matched_n__binom_glm         |      0.0909 |
| nihilist_zero                |      0.5737 |

- fold wins 8/8 (clause requires 6) · PBO 0.0 · DSR 0.8812 · p 0.0018 · BH own-family True / pooled True (binding True)
- anchors: {'nihilist_loses': True, 'marginal_loses': True, 'zero_width_loses': True, 'max_width_loses': True, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': False, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- per-form oracle floors (NF-D16 (g‴)) + matched-n capacity control (NF1.9 (f)): {'binom_glm': {'arm': 0.06, 'own_form_oracle': 0.0551, 'matched_n': 0.0909, 'oracle_beats_matched_n': True}, 'betabinom': {'arm': 0.0575, 'own_form_oracle': 0.0533, 'matched_n': 0.0874, 'oracle_beats_matched_n': True}, 'lgbm_quantile': {'arm': 0.0588, 'own_form_oracle': 0.0336, 'matched_n': 0.0622, 'oracle_beats_matched_n': True}, 'knn_quantile': {'arm': 0.0585, 'own_form_oracle': 0.0593, 'matched_n': 0.0604, 'oracle_beats_matched_n': True}}
- permutation: {'permuted_lift_vs_foil_mean': -0.0037, 'permuted_lift_p_one_sided': 0.9995} · coverage(80) {'winner_coverage_80': 0.8017, 'n_rows': 2174, 'binomial_se': 0.0086, 'blocking_shortfall': False}
- MAE (report-only, never selects): {'betabinom': 0.0799, 'foil_team_eb': 0.0817, 'nihilist_zero': 0.5737, 'marginal_train': 0.0855}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True}
- ⚠️ **field-shrink remedy is SUSPECT — NOT ADVICE** — the instrument suggests a smaller field, but this story's family of 4 arms was PRE-REGISTERED as the minimum §0.5 field (≥3 classes + a direct-learned foil). ⛔ Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one.

## ⭐ Layer B — the gate: does the environment layer move the PLAYER projection?

Env forms carried into Layer B (the Layer-A winners): `{'off_plays': 'negbin_glm', 'pass_share': 'betabinom'}`.

### QB — **POWER_LIMITED**

`champion_env` TIES `champion` by +0.0014 CRPS (CI95 [-0.0107, +0.0135] spans zero)

| label                 |   mean_crps |
|:----------------------|------------:|
| champion_env_oracle   |      2.5218 |
| champion_env          |      2.5868 |
| champion              |      2.5882 |
| champion_env_foil     |      2.5919 |
| champion_env_shuffled |      2.5922 |

- ⭐ **realized-environment CEILING** (`champion_env_oracle`, peeking): `champion_env_oracle` BEATS `champion` by +0.0664 CRPS (CI95 [+0.0393, +0.0935] excludes zero), 8/8 folds. This bounds what the ENTIRE environment chain (NF-W3→W5→W8) can buy at the player level.
- matched foil-env anchor (env from the team-EB foil, attributing any lift to the LEARNED component rather than to team context in any form): `champion_env_foil` TIES `champion` by -0.0037 CRPS (CI95 [-0.0155, +0.0081] spans zero)
- fold wins 5/8 (clause requires 6) · PBO 0.7714 · DSR 0.5996 · p 0.3972 · BH own-family False / pooled False (binding False)
- anchors {'winner_beats_shuffled': True, 'shuffled_lift_not_significant': True, 'respects_realized_oracle': True} · shuffle {'shuffled_lift_mean': -0.004, 'shuffled_lift_p_one_sided': 0.7858} · coverage(80) {'winner_coverage_80': 0.8162, 'n_rows': 5485, 'binomial_se': 0.0054, 'blocking_shortfall': False}
- gate: {'beats_champion': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'permutation_behaves': True, 'oracle_floor_respected': True, 'coverage_floor_ok': True}
- ⚠️ **PBO is UNDEFINED — CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.** Registering `pbo_ok` as a Layer-B gate was a MIS-SPECIFICATION; it is left in the gate as pre-registered (⛔ a gate is not dropped after seeing it fail) and reported as undefined rather than failed.
- ⭐ **the null does not rest on that gate** (NF-D15 (g″), measured): waiving `['pbo_ok']` leaves **['fold_consistency', 'dsr_ok', 'fdr_ok']** still refusing ⇒ ships without the waived checks: False.
- 🩹 **hand-corrected classification.** The instrument said `UNDEFINED` — "`nf_w3_downstream_crps_QB`: 8 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do." with trigger "-4 more fold(s) — i.e. a window of 7 seasons". That is wrong on its face at 8 folds: the undefined-ness comes from the FIELD SIZE (one pre-registered contrast), not the fold count, and the trigger is negative. Corrected state **POWER_LIMITED** — the point estimate is positive (+0.0014 CRPS) but the interval spans zero (CI95 [-0.0107, 0.0135]), fold wins are 5/8 against a required 6, and p=0.3972. Every statistical gate except PBO is REACHABLE at this design — the effect is simply smaller than this design can resolve. Re-test trigger: ~295 half-season folds (≈147 seasons) for the DSR gate at the observed per-fold Sharpe 0.096 — i.e. CALENDAR-bound and far beyond any plausible window; ⛔ this is NOT a near-term re-test.

### RB — **POWER_LIMITED**

`champion_env` TIES `champion` by +0.0027 CRPS (CI95 [-0.0053, +0.0107] spans zero)

| label                 |   mean_crps |
|:----------------------|------------:|
| champion_env_oracle   |      2.4264 |
| champion_env          |      2.5019 |
| champion              |      2.5046 |
| champion_env_foil     |      2.5063 |
| champion_env_shuffled |      2.5128 |

- ⭐ **realized-environment CEILING** (`champion_env_oracle`, peeking): `champion_env_oracle` BEATS `champion` by +0.0781 CRPS (CI95 [+0.0574, +0.0989] excludes zero), 8/8 folds. This bounds what the ENTIRE environment chain (NF-W3→W5→W8) can buy at the player level.
- matched foil-env anchor (env from the team-EB foil, attributing any lift to the LEARNED component rather than to team context in any form): `champion_env_foil` TIES `champion` by -0.0018 CRPS (CI95 [-0.0072, +0.0037] spans zero)
- fold wins 5/8 (clause requires 6) · PBO 0.6286 · DSR 0.8243 · p 0.2273 · BH own-family False / pooled False (binding False)
- anchors {'winner_beats_shuffled': True, 'shuffled_lift_not_significant': True, 'respects_realized_oracle': True} · shuffle {'shuffled_lift_mean': -0.0082, 'shuffled_lift_p_one_sided': 0.9944} · coverage(80) {'winner_coverage_80': 0.8475, 'n_rows': 8591, 'binomial_se': 0.0043, 'blocking_shortfall': False}
- gate: {'beats_champion': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'permutation_behaves': True, 'oracle_floor_respected': True, 'coverage_floor_ok': True}
- ⚠️ **PBO is UNDEFINED — CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.** Registering `pbo_ok` as a Layer-B gate was a MIS-SPECIFICATION; it is left in the gate as pre-registered (⛔ a gate is not dropped after seeing it fail) and reported as undefined rather than failed.
- ⭐ **the null does not rest on that gate** (NF-D15 (g″), measured): waiving `['pbo_ok']` leaves **['fold_consistency', 'dsr_ok', 'fdr_ok']** still refusing ⇒ ships without the waived checks: False.
- 🩹 **hand-corrected classification.** The instrument said `UNDEFINED` — "`nf_w3_downstream_crps_RB`: 8 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do." with trigger "-4 more fold(s) — i.e. a window of 7 seasons". That is wrong on its face at 8 folds: the undefined-ness comes from the FIELD SIZE (one pre-registered contrast), not the fold count, and the trigger is negative. Corrected state **POWER_LIMITED** — the point estimate is positive (+0.0027 CRPS) but the interval spans zero (CI95 [-0.0053, 0.0107]), fold wins are 5/8 against a required 6, and p=0.2273. Every statistical gate except PBO is REACHABLE at this design — the effect is simply smaller than this design can resolve. Re-test trigger: ~36 half-season folds (≈18 seasons) for the DSR gate at the observed per-fold Sharpe 0.28 — i.e. CALENDAR-bound and far beyond any plausible window; ⛔ this is NOT a near-term re-test.

### WR — **POWER_LIMITED**

`champion_env` TIES `champion` by +0.0019 CRPS (CI95 [-0.0057, +0.0094] spans zero)

| label                 |   mean_crps |
|:----------------------|------------:|
| champion_env_oracle   |      2.6198 |
| champion_env_shuffled |      2.6704 |
| champion_env          |      2.6708 |
| champion              |      2.6726 |
| champion_env_foil     |      2.6729 |

- ⭐ **realized-environment CEILING** (`champion_env_oracle`, peeking): `champion_env_oracle` BEATS `champion` by +0.0528 CRPS (CI95 [+0.0391, +0.0665] excludes zero), 8/8 folds. This bounds what the ENTIRE environment chain (NF-W3→W5→W8) can buy at the player level.
- matched foil-env anchor (env from the team-EB foil, attributing any lift to the LEARNED component rather than to team context in any form): `champion_env_foil` TIES `champion` by -0.0002 CRPS (CI95 [-0.0115, +0.0111] spans zero)
- fold wins 5/8 (clause requires 6) · PBO 0.6286 · DSR 0.6911 · p 0.29 · BH own-family False / pooled False (binding False)
- anchors {'winner_beats_shuffled': False, 'shuffled_lift_not_significant': True, 'respects_realized_oracle': True} · shuffle {'shuffled_lift_mean': 0.0022, 'shuffled_lift_p_one_sided': 0.2365} · coverage(80) {'winner_coverage_80': 0.8528, 'n_rows': 12827, 'binomial_se': 0.0035, 'blocking_shortfall': False}
- gate: {'beats_champion': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'permutation_behaves': False, 'oracle_floor_respected': True, 'coverage_floor_ok': True}
- ⚠️ **PBO is UNDEFINED — CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.** Registering `pbo_ok` as a Layer-B gate was a MIS-SPECIFICATION; it is left in the gate as pre-registered (⛔ a gate is not dropped after seeing it fail) and reported as undefined rather than failed.
- ⭐ **the null does not rest on that gate** (NF-D15 (g″), measured): waiving `['pbo_ok']` leaves **['fold_consistency', 'dsr_ok', 'fdr_ok', 'permutation_behaves']** still refusing ⇒ ships without the waived checks: False.
- 🩹 **hand-corrected classification.** The instrument said `UNDEFINED` — "`nf_w3_downstream_crps_WR`: 8 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do." with trigger "-4 more fold(s) — i.e. a window of 7 seasons". That is wrong on its face at 8 folds: the undefined-ness comes from the FIELD SIZE (one pre-registered contrast), not the fold count, and the trigger is negative. Corrected state **POWER_LIMITED** — the point estimate is positive (+0.0019 CRPS) but the interval spans zero (CI95 [-0.0057, 0.0094]), fold wins are 5/8 against a required 6, and p=0.29. Every statistical gate except PBO is REACHABLE at this design — the effect is simply smaller than this design can resolve. Re-test trigger: ~66 half-season folds (≈33 seasons) for the DSR gate at the observed per-fold Sharpe 0.205 — i.e. CALENDAR-bound and far beyond any plausible window; ⛔ this is NOT a near-term re-test.

### TE — **GENUINE_ABSENCE**

`champion_env` TIES `champion` by -0.0017 CRPS (CI95 [-0.0078, +0.0043] spans zero)

| label                 |   mean_crps |
|:----------------------|------------:|
| champion_env_oracle   |      1.7803 |
| champion_env_foil     |      1.8162 |
| champion_env_shuffled |      1.8182 |
| champion              |      1.8197 |
| champion_env          |      1.8214 |

- ⭐ **realized-environment CEILING** (`champion_env_oracle`, peeking): `champion_env_oracle` BEATS `champion` by +0.0394 CRPS (CI95 [+0.0233, +0.0555] excludes zero), 8/8 folds. This bounds what the ENTIRE environment chain (NF-W3→W5→W8) can buy at the player level.
- matched foil-env anchor (env from the team-EB foil, attributing any lift to the LEARNED component rather than to team context in any form): `champion_env_foil` TIES `champion` by +0.0034 CRPS (CI95 [-0.0041, +0.0110] spans zero)
- fold wins 2/8 (clause requires 6) · PBO 0.6 · DSR 0.2786 · p 0.7401 · BH own-family False / pooled False (binding False)
- anchors {'winner_beats_shuffled': False, 'shuffled_lift_not_significant': True, 'respects_realized_oracle': True} · shuffle {'shuffled_lift_mean': 0.0015, 'shuffled_lift_p_one_sided': 0.3062} · coverage(80) {'winner_coverage_80': 0.883, 'n_rows': 7649, 'binomial_se': 0.0046, 'blocking_shortfall': False}
- gate: {'beats_champion': False, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'permutation_behaves': False, 'oracle_floor_respected': True, 'coverage_floor_ok': True}
- ⚠️ **PBO is UNDEFINED — CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.** Registering `pbo_ok` as a Layer-B gate was a MIS-SPECIFICATION; it is left in the gate as pre-registered (⛔ a gate is not dropped after seeing it fail) and reported as undefined rather than failed.
- ⭐ **the null does not rest on that gate** (NF-D15 (g″), measured): waiving `['pbo_ok']` leaves **['beats_champion', 'fold_consistency', 'dsr_ok', 'fdr_ok', 'permutation_behaves']** still refusing ⇒ ships without the waived checks: False.
- 🩹 **hand-corrected classification.** The instrument said `UNDEFINED` — "`nf_w3_downstream_crps_TE`: 8 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do." with trigger "-4 more fold(s) — i.e. a window of 7 seasons". That is wrong on its face at 8 folds: the undefined-ness comes from the FIELD SIZE (one pre-registered contrast), not the fold count, and the trigger is negative. Corrected state **GENUINE_ABSENCE** — the arm LOSES to the champion on average (-0.0017 CRPS over 8 folds, 2/8 fold wins) — a negative point estimate is not rescued by more folds or a smaller field. Re-test trigger: None

## Null-state classification

```json
{
  "layer_a::off_plays": {
    "state": "DSR_UNREACHABLE",
    "reason": "`nf_w3_off_plays_crps`: the winner's per-fold Sharpe 0.588 sits at or BELOW the 4-arm field's deflated benchmark SR0 0.837, so DSR is unreachable at ANY fold count \u2014 `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, pre-registered field, not more seasons. `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
    "retest_trigger": "NOT rescuable by field size either \u2014 even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)",
    "field_shrink_flag": {
      "proposed_field_size": null,
      "declared_family_size": 4,
      "status": "SUSPECT \u2014 NOT ADVICE",
      "note": "the instrument suggests a smaller field, but this story's family of 4 arms was PRE-REGISTERED as the minimum \u00a70.5 field (\u22653 classes + a direct-learned foil). \u26d4 Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one."
    }
  },
  "layer_a::pass_share": {
    "state": "POWER_LIMITED",
    "reason": "`nf_w3_pass_share_crps`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it \u2014 DSR alone needs 44 folds against 8 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
    "retest_trigger": "+36 folds for the DSR gate, OR a field of \u22642 arms at the CURRENT fold count",
    "field_shrink_flag": {
      "proposed_field_size": 2,
      "declared_family_size": 4,
      "status": "SUSPECT \u2014 NOT ADVICE",
      "note": "the instrument suggests a smaller field, but this story's family of 4 arms was PRE-REGISTERED as the minimum \u00a70.5 field (\u22653 classes + a direct-learned foil). \u26d4 Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one."
    }
  },
  "layer_b::QB": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w3_downstream_crps_QB`: 8 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "-4 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0014 CRPS) but the interval spans zero (CI95 [-0.0107, 0.0135]), fold wins are 5/8 against a required 6, and p=0.3972. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~295 half-season folds (\u2248147 seasons) for the DSR gate at the observed per-fold Sharpe 0.096 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test.",
    "gate_sensitivity": {
      "waived": [
        "pbo_ok"
      ],
      "still_refusing": [
        "fold_consistency",
        "dsr_ok",
        "fdr_ok"
      ],
      "ships_without_waived_checks": false
    }
  },
  "layer_b::RB": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w3_downstream_crps_RB`: 8 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "-4 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0027 CRPS) but the interval spans zero (CI95 [-0.0053, 0.0107]), fold wins are 5/8 against a required 6, and p=0.2273. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~36 half-season folds (\u224818 seasons) for the DSR gate at the observed per-fold Sharpe 0.28 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test.",
    "gate_sensitivity": {
      "waived": [
        "pbo_ok"
      ],
      "still_refusing": [
        "fold_consistency",
        "dsr_ok",
        "fdr_ok"
      ],
      "ships_without_waived_checks": false
    }
  },
  "layer_b::WR": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w3_downstream_crps_WR`: 8 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "-4 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0019 CRPS) but the interval spans zero (CI95 [-0.0057, 0.0094]), fold wins are 5/8 against a required 6, and p=0.29. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~66 half-season folds (\u224833 seasons) for the DSR gate at the observed per-fold Sharpe 0.205 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test.",
    "gate_sensitivity": {
      "waived": [
        "pbo_ok"
      ],
      "still_refusing": [
        "fold_consistency",
        "dsr_ok",
        "fdr_ok",
        "permutation_behaves"
      ],
      "ships_without_waived_checks": false
    }
  },
  "layer_b::TE": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w3_downstream_crps_TE`: 8 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "-4 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "UNDEFINED \u2014 CSCV resamples a FIELD; Layer B fields ONE pre-registered contrast, so there was no search to overfit. Reported as undefined, NOT as a failed deflation gate.",
    "state": "GENUINE_ABSENCE",
    "reason": "the arm LOSES to the champion on average (-0.0017 CRPS over 8 folds, 2/8 fold wins) \u2014 a negative point estimate is not rescued by more folds or a smaller field.",
    "retest_trigger": null,
    "gate_sensitivity": {
      "waived": [
        "pbo_ok"
      ],
      "still_refusing": [
        "beats_champion",
        "fold_consistency",
        "dsr_ok",
        "fdr_ok",
        "permutation_behaves"
      ],
      "ships_without_waived_checks": false
    }
  }
}
```

## Pre-registration echo

```json
{
  "real_arms": {
    "off_plays": [
      "pois_glm",
      "negbin_glm",
      "lgbm_quantile",
      "knn_quantile"
    ],
    "pass_share": [
      "binom_glm",
      "betabinom",
      "lgbm_quantile",
      "knn_quantile"
    ]
  },
  "foils": [
    "foil_team_eb",
    "foil_team_eb_matchup"
  ],
  "anchors": {
    "off_plays": [
      "nihilist_zero",
      "marginal_train",
      "zero_width",
      "max_width",
      "permuted_within_week",
      "oracle__pois_glm",
      "oracle__negbin_glm",
      "oracle__lgbm_quantile",
      "oracle__knn_quantile",
      "oracle__foil_team_eb",
      "oracle__foil_team_eb_matchup",
      "matched_n__pois_glm",
      "matched_n__negbin_glm",
      "matched_n__lgbm_quantile",
      "matched_n__knn_quantile"
    ],
    "pass_share": [
      "nihilist_zero",
      "marginal_train",
      "zero_width",
      "max_width",
      "permuted_within_week",
      "oracle__binom_glm",
      "oracle__betabinom",
      "oracle__lgbm_quantile",
      "oracle__knn_quantile",
      "oracle__foil_team_eb",
      "oracle__foil_team_eb_matchup",
      "matched_n__binom_glm",
      "matched_n__betabinom",
      "matched_n__lgbm_quantile",
      "matched_n__knn_quantile"
    ]
  },
  "eligible": {
    "off_plays": [
      "pois_glm",
      "negbin_glm",
      "lgbm_quantile",
      "knn_quantile",
      "foil_team_eb",
      "foil_team_eb_matchup"
    ],
    "pass_share": [
      "binom_glm",
      "betabinom",
      "lgbm_quantile",
      "knn_quantile",
      "foil_team_eb",
      "foil_team_eb_matchup"
    ]
  },
  "layer_b_eligible": [
    "champion",
    "champion_env"
  ],
  "layer_b_anchors": [
    "champion_env_shuffled",
    "champion_env_oracle"
  ],
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
      "off_plays",
      "pass_share"
    ],
    "downstream": [
      "QB",
      "RB",
      "WR",
      "TE"
    ]
  },
  "coverage_floor": 0.8,
  "eb_kappa_team": 4.0,
  "matchup_clip": [
    0.9,
    1.1
  ],
  "features": [
    "game_context__is_home",
    "game_context__div_game",
    "game_context__week_index",
    "game_context__days_since_last_game",
    "team_environment__off_plays_l4",
    "team_environment__off_plays_l8",
    "team_environment__off_plays_ewm",
    "team_environment__off_plays_s2d",
    "team_environment__off_plays_prior_season",
    "team_environment__pass_share_l4",
    "team_environment__pass_share_l8",
    "team_environment__pass_share_ewm",
    "team_environment__pass_share_s2d",
    "team_environment__pass_share_prior_season",
    "team_environment__neutral_pass_rate_l4",
    "team_environment__proe_l4",
    "team_environment__no_huddle_l4",
    "team_environment__sec_per_play_l4",
    "team_environment__drives_l4",
    "team_environment__plays_per_drive_l4",
    "team_environment__epa_per_play_l4",
    "team_environment__success_rate_l4",
    "team_environment__points_l4",
    "team_environment__sack_rate_l4",
    "team_environment__games_prior_season",
    "opponent_matchup__def_plays_faced_l4",
    "opponent_matchup__def_pass_share_faced_l4",
    "opponent_matchup__def_epa_allowed_l4",
    "opponent_matchup__def_success_allowed_l4",
    "opponent_matchup__def_sec_per_play_faced_l4",
    "opponent_matchup__def_points_allowed_l4",
    "opponent_matchup__def_drives_faced_l4",
    "opponent_matchup__opp_off_plays_l4",
    "opponent_matchup__opp_off_pass_share_l4",
    "opponent_matchup__opp_off_epa_l4",
    "opponent_matchup__opp_off_sec_per_play_l4"
  ],
  "env_features": [
    "team_environment__proj_off_plays",
    "team_environment__proj_pass_plays",
    "team_environment__proj_rush_plays",
    "team_environment__proj_pass_share",
    "team_environment__proj_off_plays_sd",
    "opponent_matchup__proj_opp_off_plays",
    "opponent_matchup__proj_opp_pass_plays"
  ],
  "era_forbidden_tokens": [
    "pressure",
    "coverage",
    "route",
    "ngs_air_yards"
  ],
  "banned_source_tokens": [
    "spread_line",
    "total_line",
    "vegas_wp",
    "vegas_home_wp",
    "vegas_wpa",
    "vegas_home_wpa",
    "temp",
    "wind",
    "moneyline",
    "depth_team",
    "depth_chart"
  ]
}
```