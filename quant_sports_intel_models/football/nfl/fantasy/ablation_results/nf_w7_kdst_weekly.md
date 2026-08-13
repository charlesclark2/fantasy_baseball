# NF-W7 — weekly Kicker + DST projections, exact tier scoring as bucket probabilities (§0.5 bake-off)

**Generated:** 2026-08-13T19:56:35+00:00 · **folds:** 8 (2022H1…2025H2, the NF-W1 axis verbatim) · **kicker-weeks:** 5318 · **team-weeks:** 5278 · **FG attempts:** 10277

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** (serving is the weekly path / NF-C6, an operator decision). Selection is `crps_q199` on the dense grid for banks, log-loss / RPS for the categorical legs; MAE never selects. Every direction word is three-way and derived at report time, failing closed to `TIES` (NF-W2e).

**PIT gate (dst):** 175 weeks / 5278 records; 0 rows dropped fail-closed.
**PIT gate (kicker):** 175 weeks / 5318 records; 0 rows dropped fail-closed.
**PIT gate (attempt):** 175 weeks / 10277 records; 0 rows dropped fail-closed.

## ⭐ Headline

- **Layer B (the gate — does the component chain beat the climatology null, the board-EB read and the direct-points foil?)** — k_points: **SHIP** · dst_points: **CONSTRAINT_REFUSED**
- **Layer A (components)** — fg_att: **DSR_UNREACHABLE** · xp_att: **POWER_LIMITED** · def_sacks: **POWER_LIMITED** · def_int: **DSR_UNREACHABLE** · def_fumble_rec: **GENUINE_ABSENCE** · fg_make: **DSR_UNREACHABLE** · fg_band: **DSR_UNREACHABLE** · dst_td: **GENUINE_ABSENCE** · def_safety: **GENUINE_ABSENCE** · def_blocked_kick: **GENUINE_ABSENCE** · pa_bucket: **SHIP** · ya_bucket: **SHIP**

## ⭐ Layer B — the assembled fantasy-point distributions

### `k_points` — **SHIP**

`assembled` BEATS `foil_climatology` by +0.0261 CRPS (CI95 [+0.0036, +0.0487] excludes zero)

| label                    |   mean_crps_q199 |
|:-------------------------|-----------------:|
| oracle__foil_direct      |           1.6111 |
| oracle__assembled        |           2.4162 |
| assembled                |           2.5745 |
| oracle__foil_climatology |           2.5838 |
| oracle__foil_board_eb    |           2.6000 |
| foil_climatology         |           2.6006 |
| foil_board_eb            |           2.6051 |
| foil_direct              |           2.6467 |
| permuted_direct          |           2.6844 |
| matched_n__assembled     |           2.7600 |
| zero_width               |           3.6794 |
| max_width                |           3.8519 |
| nihilist_zero            |           8.2696 |

- fold wins 7/8 (clause requires 6) · PBO 0.0 · DSR(=PSR, 1 arm) 0.9991 · p 0.0145 · BH own-family True / pooled True (binding True)
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 8.2696, 'zero_width': 3.6794, 'max_width': 3.8519}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- permutation: {'permuted_lift_vs_foil_mean': -0.0838, 'permuted_lift_p_one_sided': 0.9998} · coverage(80) {'winner_coverage_80': 0.8668, 'n_rows': 2162, 'binomial_se': 0.0086, 'blocking_shortfall': False}
- randomized-PIT flatness by fold (report-only): [{'max_decile_dev': 0.04391143911439113, 'n': 271}, {'max_decile_dev': 0.04716981132075472, 'n': 265}, {'max_decile_dev': 0.05112781954887219, 'n': 266}, {'max_decile_dev': 0.02647058823529412, 'n': 272}, {'max_decile_dev': 0.030434782608695643, 'n': 276}, {'max_decile_dev': 0.03805970149253732, 'n': 268}, {'max_decile_dev': 0.040740740740740744, 'n': 270}, {'max_decile_dev': 0.031386861313868614, 'n': 274}]
- capture-era (2025) fold deltas, report-only (NF-W2d): {'2025H1': 0.0197, '2025H2': 0.0773}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': True, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True}

### `dst_points` — **CONSTRAINT_REFUSED**

`assembled` BEATS `foil_direct` by +0.0338 CRPS (CI95 [+0.0094, +0.0582] excludes zero)

| label                    |   mean_crps_q199 |
|:-------------------------|-----------------:|
| oracle__foil_direct      |           1.6870 |
| oracle__assembled        |           2.5058 |
| assembled                |           2.6975 |
| oracle__foil_climatology |           2.7252 |
| oracle__foil_board_eb    |           2.7301 |
| foil_direct              |           2.7313 |
| foil_climatology         |           2.7390 |
| foil_board_eb            |           2.7450 |
| permuted_direct          |           2.8281 |
| zero_width               |           3.8158 |
| max_width                |           4.0852 |
| nihilist_zero            |           6.2188 |
| matched_n__assembled     |           9.0771 |

- fold wins 7/8 (clause requires 6) · PBO 0.0 · DSR(=PSR, 1 arm) 0.961 · p 0.0067 · BH own-family True / pooled True (binding True)
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 6.2188, 'zero_width': 3.8158, 'max_width': 4.0852}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- permutation: {'permuted_lift_vs_foil_mean': -0.0969, 'permuted_lift_p_one_sided': 0.9998} · coverage(80) {'winner_coverage_80': 0.7603, 'n_rows': 2174, 'binomial_se': 0.0086, 'blocking_shortfall': True}
- randomized-PIT flatness by fold (report-only): [{'max_decile_dev': 0.032352941176470584, 'n': 272}, {'max_decile_dev': 0.033333333333333326, 'n': 270}, {'max_decile_dev': 0.07647058823529412, 'n': 272}, {'max_decile_dev': 0.09117647058823528, 'n': 272}, {'max_decile_dev': 0.06666666666666665, 'n': 276}, {'max_decile_dev': 0.09029850746268656, 'n': 268}, {'max_decile_dev': 0.07037037037037036, 'n': 270}, {'max_decile_dev': 0.04233576642335765, 'n': 274}]
- capture-era (2025) fold deltas, report-only (NF-W2d): {'2025H1': 0.0608, '2025H2': 0.0565}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': True, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': False}
- null state: **CONSTRAINT_REFUSED** — every statistical gate is GREEN — the assembled arm beats the best foil by +0.0338 CRPS (CI95 [0.0094, 0.0582] excludes zero), fold wins 7 against a required 6, p=0.0067, PBO/DSR/FDR all pass — and the ship is refused by the pre-registered coverage(80) FLOOR alone: 0.7603 against 0.80 at n=2174 (≈4.6 binomial SE below nominal — decisive under-coverage, not sampling noise). The mechanism is the DECLARED independence-simplification check firing: component banks drawn independently under-disperse the assembled sum wherever the components co-move. Re-test: NONE — a constraint refusal is not rescuable by data (NF-D18): more folds make the refusal MORE certain. The remedy is a DIFFERENT MECHANISM (a successor modeling cross-component dependence — e.g. a joint/copula draw over the component legs) or a PM decision; ⛔ never a post-hoc floor change (a floor re-set after seeing the result is the E2.1-r inversion — NF1.8).
- 🩹 hand-corrected from the instrument verdict {'state': 'UNDEFINED', 'reason': '`nf_w7_downstream_dst_points`: 8 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.', 'retest_trigger': '-4 more fold(s) — i.e. a window of 7 seasons'} (the known classify_null n_arms=1 mis-render).

## Layer A — the component legs

### `fg_att` (crps_q199) — **DSR_UNREACHABLE**

`pois_glm` TIES `foil_climatology` by +0.0007 CRPS (CI95 [-0.0028, +0.0043] spans zero)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__lgbm_quantile    |       0.4567 |
| oracle__pois_glm         |       0.6663 |
| oracle__negbin_glm       |       0.6663 |
| oracle__foil_climatology |       0.7141 |
| pois_glm                 |       0.7175 |
| negbin_glm               |       0.7175 |
| foil_climatology         |       0.7182 |
| oracle__foil_entity_eb   |       0.7229 |
| foil_entity_eb           |       0.7237 |
| lgbm_quantile            |       0.7550 |
| permuted_control         |       0.7612 |
| matched_n__pois_glm      |       0.7845 |
| matched_n__negbin_glm    |       0.7850 |
| matched_n__lgbm_quantile |       0.7878 |
| zero_width               |       0.9884 |
| max_width                |       1.1805 |
| nihilist_zero            |       1.9849 |

- fold wins 5/8 (requires 6) · PBO 0.0 · DSR 0.0 · p 0.3233 · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 1.9849, 'zero_width': 0.9884, 'max_width': 1.1805}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'pois_glm': {'arm': 0.7175, 'own_form_oracle': 0.6663, 'matched_n': 0.7845}, 'negbin_glm': {'arm': 0.7175, 'own_form_oracle': 0.6663, 'matched_n': 0.785}, 'lgbm_quantile': {'arm': 0.755, 'own_form_oracle': 0.4567, 'matched_n': 0.7878}}
- era deltas (2025, report-only): {'2025H1': -0.0029, '2025H2': 0.0046}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **DSR_UNREACHABLE** — `nf_w7_fg_att`: the winner's per-fold Sharpe 0.169 sits at or BELOW the 3-arm field's deflated benchmark SR0 3.075, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, pre-registered field, not more seasons. `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.
- ⚠️ field-shrink remedy is SUSPECT — NOT ADVICE — the instrument suggests a smaller field, but this story's family of 3 arms was PRE-REGISTERED as the minimum §0.5 field (≥3 classes + a direct-learned foil). ⛔ Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one.

### `xp_att` (crps_q199) — **POWER_LIMITED**

`pois_glm` BEATS `foil_entity_eb` by +0.0198 CRPS (CI95 [+0.0104, +0.0292] excludes zero)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__lgbm_quantile    |       0.4838 |
| oracle__pois_glm         |       0.7134 |
| oracle__negbin_glm       |       0.7134 |
| pois_glm                 |       0.7604 |
| negbin_glm               |       0.7604 |
| oracle__foil_entity_eb   |       0.7792 |
| foil_entity_eb           |       0.7801 |
| oracle__foil_climatology |       0.7967 |
| foil_climatology         |       0.8020 |
| lgbm_quantile            |       0.8030 |
| matched_n__pois_glm      |       0.8384 |
| matched_n__negbin_glm    |       0.8390 |
| matched_n__lgbm_quantile |       0.8397 |
| permuted_control         |       0.8418 |
| zero_width               |       1.1089 |
| max_width                |       1.2919 |
| nihilist_zero            |       2.2259 |

- fold wins 8/8 (requires 6) · PBO 0.0 · DSR 0.5313 · p 0.0008 · BH own/pooled/binding True/True/True
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 2.2259, 'zero_width': 1.1089, 'max_width': 1.2919}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'pois_glm': {'arm': 0.7604, 'own_form_oracle': 0.7134, 'matched_n': 0.8384}, 'negbin_glm': {'arm': 0.7604, 'own_form_oracle': 0.7134, 'matched_n': 0.839}, 'lgbm_quantile': {'arm': 0.803, 'own_form_oracle': 0.4838, 'matched_n': 0.8397}}
- era deltas (2025, report-only): {'2025H1': 0.0109, '2025H2': 0.0288}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **POWER_LIMITED** — `nf_w7_xp_att`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it — DSR alone needs 5403 folds against 8 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.

### `def_sacks` (crps_q199) — **POWER_LIMITED**

`negbin_glm` BEATS `foil_climatology` by +0.0259 CRPS (CI95 [+0.0131, +0.0387] excludes zero)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__lgbm_quantile    |       0.5963 |
| oracle__negbin_glm       |       0.8803 |
| oracle__pois_glm         |       0.8807 |
| negbin_glm               |       0.9532 |
| pois_glm                 |       0.9565 |
| oracle__foil_climatology |       0.9749 |
| foil_climatology         |       0.9791 |
| oracle__foil_entity_eb   |       0.9863 |
| foil_entity_eb           |       0.9870 |
| lgbm_quantile            |       0.9984 |
| permuted_control         |       1.0226 |
| matched_n__lgbm_quantile |       1.0394 |
| zero_width               |       1.3735 |
| max_width                |       1.4611 |
| matched_n__negbin_glm    |       1.7943 |
| matched_n__pois_glm      |       1.7955 |
| nihilist_zero            |       2.4249 |

- fold wins 8/8 (requires 6) · PBO 0.0 · DSR 0.7118 · p 0.001 · BH own/pooled/binding True/True/True
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 2.4249, 'zero_width': 1.3735, 'max_width': 1.4611}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'pois_glm': {'arm': 0.9565, 'own_form_oracle': 0.8807, 'matched_n': 1.7955}, 'negbin_glm': {'arm': 0.9532, 'own_form_oracle': 0.8803, 'matched_n': 1.7943}, 'lgbm_quantile': {'arm': 0.9984, 'own_form_oracle': 0.5963, 'matched_n': 1.0394}}
- era deltas (2025, report-only): {'2025H1': 0.0217, '2025H2': 0.0319}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **POWER_LIMITED** — `nf_w7_def_sacks`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it — DSR alone needs 172 folds against 8 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.

### `def_int` (crps_q199) — **DSR_UNREACHABLE**

`negbin_glm` TIES `foil_climatology` by +0.0011 CRPS (CI95 [-0.0051, +0.0073] spans zero)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__lgbm_quantile    |       0.2996 |
| oracle__pois_glm         |       0.4081 |
| oracle__negbin_glm       |       0.4081 |
| oracle__foil_climatology |       0.4480 |
| negbin_glm               |       0.4487 |
| pois_glm                 |       0.4489 |
| foil_climatology         |       0.4498 |
| oracle__foil_entity_eb   |       0.4518 |
| foil_entity_eb           |       0.4521 |
| lgbm_quantile            |       0.4860 |
| permuted_control         |       0.4886 |
| matched_n__lgbm_quantile |       0.4982 |
| zero_width               |       0.7191 |
| nihilist_zero            |       0.7429 |
| max_width                |       0.9591 |
| matched_n__pois_glm      |       1.8216 |
| matched_n__negbin_glm    |       1.8225 |

- fold wins 5/8 (requires 6) · PBO 0.2143 · DSR 0.0 · p 0.3389 · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 0.7429, 'zero_width': 0.7191, 'max_width': 0.9591}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'pois_glm': {'arm': 0.4489, 'own_form_oracle': 0.4081, 'matched_n': 1.8216}, 'negbin_glm': {'arm': 0.4487, 'own_form_oracle': 0.4081, 'matched_n': 1.8225}, 'lgbm_quantile': {'arm': 0.486, 'own_form_oracle': 0.2996, 'matched_n': 0.4982}}
- era deltas (2025, report-only): {'2025H1': 0.0092, '2025H2': 0.0021}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **DSR_UNREACHABLE** — `nf_w7_def_int`: the winner's per-fold Sharpe 0.153 sits at or BELOW the 3-arm field's deflated benchmark SR0 3.281, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, pre-registered field, not more seasons. `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.
- ⚠️ field-shrink remedy is SUSPECT — NOT ADVICE — the instrument suggests a smaller field, but this story's family of 3 arms was PRE-REGISTERED as the minimum §0.5 field (≥3 classes + a direct-learned foil). ⛔ Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one.

### `def_fumble_rec` (crps_q199) — **GENUINE_ABSENCE**

`negbin_glm` TIES `foil_climatology` by -0.0002 CRPS (CI95 [-0.0028, +0.0024] spans zero)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__lgbm_quantile    |       0.2362 |
| oracle__negbin_glm       |       0.3085 |
| oracle__pois_glm         |       0.3086 |
| oracle__foil_climatology |       0.3370 |
| foil_climatology         |       0.3394 |
| pois_glm                 |       0.3396 |
| negbin_glm               |       0.3396 |
| oracle__foil_entity_eb   |       0.3430 |
| foil_entity_eb           |       0.3433 |
| lgbm_quantile            |       0.3674 |
| permuted_control         |       0.3713 |
| matched_n__lgbm_quantile |       0.3880 |
| nihilist_zero            |       0.5092 |
| zero_width               |       0.5092 |
| max_width                |       0.6408 |
| matched_n__pois_glm      |       1.7082 |
| matched_n__negbin_glm    |       1.7098 |

- fold wins 4/8 (requires 6) · PBO 0.0 · DSR 0.0 · p 0.5752 · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 0.5092, 'zero_width': 0.5092, 'max_width': 0.6408}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'pois_glm': {'arm': 0.3396, 'own_form_oracle': 0.3086, 'matched_n': 1.7082}, 'negbin_glm': {'arm': 0.3396, 'own_form_oracle': 0.3085, 'matched_n': 1.7098}, 'lgbm_quantile': {'arm': 0.3674, 'own_form_oracle': 0.2362, 'matched_n': 0.388}}
- era deltas (2025, report-only): {'2025H1': -0.0059, '2025H2': 0.0029}
- gate: {'beats_foil': False, 'fold_consistency': False, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **GENUINE_ABSENCE** — `nf_w7_def_fumble_rec`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.

### `fg_make` (log_loss) — **DSR_UNREACHABLE**

`logit_distance_glm` BEATS `foil_league_curve` by +0.0037 CRPS (CI95 [+0.0008, +0.0066] excludes zero)

| label                         |   mean_score |
|:------------------------------|-------------:|
| oracle__lgbm_classifier       |       0.1539 |
| oracle__logit_distance_glm    |       0.3595 |
| oracle__foil_league_curve     |       0.3603 |
| logit_distance_glm            |       0.3636 |
| oracle__eb_kicker_curve       |       0.3637 |
| eb_kicker_curve               |       0.3656 |
| matched_n__eb_kicker_curve    |       0.3656 |
| permuted_control              |       0.3659 |
| foil_league_curve             |       0.3673 |
| matched_n__logit_distance_glm |       0.3689 |
| lgbm_classifier               |       0.3769 |
| oracle__foil_constant_rate    |       0.4195 |
| foil_constant_rate            |       0.4206 |
| matched_n__lgbm_classifier    |       0.4637 |
| uniform                       |       0.6931 |
| all_event                     |       1.0275 |

- fold wins 7/8 (requires 6) · PBO 0.0 · DSR 0.3131 · p 0.0101 · BH own/pooled/binding True/True/True
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'all_event': 1.0275, 'uniform': 0.6931}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'eb_kicker_curve': {'arm': 0.3656, 'own_form_oracle': 0.3637, 'matched_n': 0.3656}, 'logit_distance_glm': {'arm': 0.3636, 'own_form_oracle': 0.3595, 'matched_n': 0.3689}, 'lgbm_classifier': {'arm': 0.3769, 'own_form_oracle': 0.1539, 'matched_n': 0.4637}}
- era deltas (2025, report-only): {'2025H1': 0.0033, '2025H2': 0.0043}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **DSR_UNREACHABLE** — `nf_w7_fg_make`: the winner's per-fold Sharpe 1.056 sits at or BELOW the 3-arm field's deflated benchmark SR0 1.246, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, pre-registered field, not more seasons. `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.
- ⚠️ field-shrink remedy is SUSPECT — NOT ADVICE — the instrument suggests a smaller field, but this story's family of 3 arms was PRE-REGISTERED as the minimum §0.5 field (≥3 classes + a direct-learned foil). ⛔ Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one.

### `fg_band` (log_loss_multiclass) — **DSR_UNREACHABLE**

`mnlogit` BEATS `foil_league_mix` by +0.0138 CRPS (CI95 [+0.0053, +0.0222] excludes zero)

| label                          |   mean_score |
|:-------------------------------|-------------:|
| oracle__lgbm_multiclass        |       0.7004 |
| oracle__mnlogit                |       1.0258 |
| mnlogit                        |       1.0390 |
| oracle__foil_league_mix        |       1.0406 |
| permuted_control               |       1.0440 |
| foil_league_mix                |       1.0528 |
| matched_n__mnlogit             |       1.0531 |
| oracle__eb_dirichlet_kicker    |       1.0629 |
| matched_n__eb_dirichlet_kicker |       1.0637 |
| eb_dirichlet_kicker            |       1.0652 |
| lgbm_multiclass                |       1.0749 |
| uniform                        |       1.0986 |
| matched_n__lgbm_multiclass     |       1.2343 |
| point_mass_modal               |       7.0057 |

- fold wins 8/8 (requires 6) · PBO 0.0 · DSR 0.3847 · p 0.0031 · BH own/pooled/binding True/True/True
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'uniform': 1.0986, 'point_mass_modal': 7.0057}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': False, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'mnlogit': {'arm': 1.039, 'own_form_oracle': 1.0258, 'matched_n': 1.0531}, 'eb_dirichlet_kicker': {'arm': 1.0652, 'own_form_oracle': 1.0629, 'matched_n': 1.0637}, 'lgbm_multiclass': {'arm': 1.0749, 'own_form_oracle': 0.7004, 'matched_n': 1.2343}}
- era deltas (2025, report-only): {'2025H1': 0.023, '2025H2': 0.0038}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': False, 'oracle_floors_respected': True}
- null state: **DSR_UNREACHABLE** — `nf_w7_fg_band`: the winner's per-fold Sharpe 1.366 sits at or BELOW the 3-arm field's deflated benchmark SR0 1.460, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, pre-registered field, not more seasons. `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.
- ⚠️ field-shrink remedy is SUSPECT — NOT ADVICE — the instrument suggests a smaller field, but this story's family of 3 arms was PRE-REGISTERED as the minimum §0.5 field (≥3 classes + a direct-learned foil). ⛔ Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one.

### `dst_td` (crps_q199) — **GENUINE_ABSENCE**

`eb_pois` LOSES TO `foil_climatology` by -0.0019 CRPS (CI95 [-0.0035, -0.0003] excludes zero)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__hurdle_pois      |       0.0779 |
| oracle__foil_climatology |       0.0897 |
| oracle__foil_league_rate |       0.0898 |
| foil_climatology         |       0.0900 |
| foil_league_rate         |       0.0900 |
| eb_pois                  |       0.0919 |
| oracle__eb_pois          |       0.0919 |
| matched_n__eb_pois       |       0.0919 |
| permuted_control         |       0.0919 |
| hurdle_pois              |       0.0921 |
| nihilist_zero            |       0.0979 |
| zero_width               |       0.0979 |
| max_width                |       0.1095 |
| matched_n__hurdle_pois   |       0.1370 |

- fold wins 1/8 (requires 6) · PBO 0.0 · DSR 0.0004 · p 0.9874 · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 0.0979, 'zero_width': 0.0979, 'max_width': 0.1095}, 'winner_beats_permuted': False, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'eb_pois': {'arm': 0.0919, 'own_form_oracle': 0.0919, 'matched_n': 0.0919}, 'hurdle_pois': {'arm': 0.0921, 'own_form_oracle': 0.0779, 'matched_n': 0.137}}
- era deltas (2025, report-only): {'2025H1': -0.0016, '2025H2': -0.0004}
- gate: {'beats_foil': False, 'fold_consistency': False, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': False, 'oracle_floors_respected': True}
- null state: **GENUINE_ABSENCE** — `nf_w7_dst_td`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.

### `def_safety` (crps_q199) — **GENUINE_ABSENCE**

`hurdle_pois` LOSES TO `foil_climatology` by -0.0005 CRPS (CI95 [-0.0008, -0.0001] excludes zero)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__hurdle_pois      |       0.0194 |
| foil_climatology         |       0.0256 |
| oracle__foil_climatology |       0.0256 |
| foil_league_rate         |       0.0256 |
| oracle__foil_league_rate |       0.0256 |
| hurdle_pois              |       0.0261 |
| nihilist_zero            |       0.0262 |
| zero_width               |       0.0262 |
| eb_pois                  |       0.0263 |
| oracle__eb_pois          |       0.0263 |
| matched_n__eb_pois       |       0.0263 |
| permuted_control         |       0.0263 |
| max_width                |       0.0272 |
| matched_n__hurdle_pois   |       0.0532 |

- fold wins 1/8 (requires 6) · PBO 0.0 · DSR 0.0041 · p 0.9912 · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 0.0262, 'zero_width': 0.0262, 'max_width': 0.0272}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'eb_pois': {'arm': 0.0263, 'own_form_oracle': 0.0263, 'matched_n': 0.0263}, 'hurdle_pois': {'arm': 0.0261, 'own_form_oracle': 0.0194, 'matched_n': 0.0532}}
- era deltas (2025, report-only): {'2025H1': -0.0008, '2025H2': -0.0004}
- gate: {'beats_foil': False, 'fold_consistency': False, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **GENUINE_ABSENCE** — `nf_w7_def_safety`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.

### `def_blocked_kick` (crps_q199) — **GENUINE_ABSENCE**

`eb_pois` TIES `foil_climatology` by -0.0015 CRPS (CI95 [-0.0030, -0.0000] spans zero)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__hurdle_pois      |       0.0610 |
| oracle__foil_climatology |       0.0697 |
| oracle__foil_league_rate |       0.0697 |
| foil_climatology         |       0.0699 |
| foil_league_rate         |       0.0699 |
| oracle__eb_pois          |       0.0713 |
| eb_pois                  |       0.0714 |
| permuted_control         |       0.0714 |
| matched_n__eb_pois       |       0.0715 |
| hurdle_pois              |       0.0717 |
| nihilist_zero            |       0.0750 |
| zero_width               |       0.0750 |
| max_width                |       0.0803 |
| matched_n__hurdle_pois   |       0.1079 |

- fold wins 2/8 (requires 6) · PBO 0.0 · DSR 0.0064 · p 0.9756 · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 0.075, 'zero_width': 0.075, 'max_width': 0.0803}, 'winner_beats_permuted': False, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'eb_pois': {'arm': 0.0714, 'own_form_oracle': 0.0713, 'matched_n': 0.0715}, 'hurdle_pois': {'arm': 0.0717, 'own_form_oracle': 0.061, 'matched_n': 0.1079}}
- era deltas (2025, report-only): {'2025H1': 0.0016, '2025H2': -0.0011}
- gate: {'beats_foil': False, 'fold_consistency': False, 'pbo_ok': True, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': False, 'oracle_floors_respected': True}
- null state: **GENUINE_ABSENCE** — `nf_w7_def_blocked_kick`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign — do NOT re-test.

### `pa_bucket` (rps) — **SHIP**

`ordered_logit` BEATS `foil_entity_eb` by +0.0052 CRPS (CI95 [+0.0030, +0.0074] excludes zero)

| label                        |   mean_score |
|:-----------------------------|-------------:|
| oracle__mnlogit              |       0.0943 |
| oracle__ordered_logit        |       0.1080 |
| oracle__negbin_integrated    |       0.1094 |
| ordered_logit                |       0.1171 |
| negbin_integrated            |       0.1172 |
| mnlogit                      |       0.1176 |
| oracle__foil_entity_eb       |       0.1202 |
| foil_entity_eb               |       0.1223 |
| oracle__foil_climatology     |       0.1224 |
| foil_climatology             |       0.1232 |
| permuted_control             |       0.1240 |
| uniform                      |       0.1368 |
| matched_n__negbin_integrated |       0.1413 |
| matched_n__ordered_logit     |       0.1478 |
| matched_n__mnlogit           |       0.1511 |
| point_mass_modal             |       0.1785 |

- fold wins 8/8 (requires 6) · PBO 0.0 · DSR 0.9956 · p 0.0004 · BH own/pooled/binding True/True/True
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'uniform': 0.1368, 'point_mass_modal': 0.1785}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'ordered_logit': {'arm': 0.1171, 'own_form_oracle': 0.108, 'matched_n': 0.1478}, 'mnlogit': {'arm': 0.1176, 'own_form_oracle': 0.0943, 'matched_n': 0.1511}, 'negbin_integrated': {'arm': 0.1172, 'own_form_oracle': 0.1094, 'matched_n': 0.1413}}
- era deltas (2025, report-only): {'2025H1': 0.0056, '2025H2': 0.0064}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': True, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}

### `ya_bucket` (rps) — **SHIP**

`gauss_integrated` BEATS `foil_entity_eb` by +0.0051 CRPS (CI95 [+0.0031, +0.0071] excludes zero)

| label                       |   mean_score |
|:----------------------------|-------------:|
| oracle__mnlogit             |       0.0730 |
| oracle__ordered_logit       |       0.0849 |
| oracle__gauss_integrated    |       0.0859 |
| ordered_logit               |       0.0933 |
| gauss_integrated            |       0.0933 |
| mnlogit                     |       0.0938 |
| oracle__foil_entity_eb      |       0.0962 |
| oracle__foil_climatology    |       0.0982 |
| foil_entity_eb              |       0.0984 |
| permuted_control            |       0.0992 |
| foil_climatology            |       0.0995 |
| matched_n__ordered_logit    |       0.1152 |
| matched_n__gauss_integrated |       0.1168 |
| matched_n__mnlogit          |       0.1240 |
| uniform                     |       0.1269 |
| point_mass_modal            |       0.1824 |

- fold wins 8/8 (requires 6) · PBO 0.0 · DSR 0.9971 · p 0.0003 · BH own/pooled/binding True/True/True
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'uniform': 0.1269, 'point_mass_modal': 0.1824}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'ordered_logit': {'arm': 0.0933, 'own_form_oracle': 0.0849, 'matched_n': 0.1152}, 'mnlogit': {'arm': 0.0938, 'own_form_oracle': 0.073, 'matched_n': 0.124}, 'gauss_integrated': {'arm': 0.0933, 'own_form_oracle': 0.0859, 'matched_n': 0.1168}}
- era deltas (2025, report-only): {'2025H1': 0.0052, '2025H2': 0.0091}
- gate: {'beats_foil': True, 'fold_consistency': True, 'pbo_ok': True, 'dsr_ok': True, 'fdr_ok': True, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}

## Null-state classification

```json
{
  "layer_a::fg_att": {
    "state": "DSR_UNREACHABLE",
    "reason": "`nf_w7_fg_att`: the winner's per-fold Sharpe 0.169 sits at or BELOW the 3-arm field's deflated benchmark SR0 3.075, so DSR is unreachable at ANY fold count \u2014 `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, pre-registered field, not more seasons. `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
    "retest_trigger": "NOT rescuable by field size either \u2014 even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)",
    "field_shrink_flag": {
      "proposed_field_size": null,
      "declared_family_size": 3,
      "status": "SUSPECT \u2014 NOT ADVICE",
      "note": "the instrument suggests a smaller field, but this story's family of 3 arms was PRE-REGISTERED as the minimum \u00a70.5 field (\u22653 classes + a direct-learned foil). \u26d4 Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one."
    }
  },
  "layer_a::xp_att": {
    "state": "POWER_LIMITED",
    "reason": "`nf_w7_xp_att`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it \u2014 DSR alone needs 5403 folds against 8 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
    "retest_trigger": "+5395 folds for the DSR gate \u2014 field size alone cannot rescue it at this dispersion"
  },
  "layer_a::def_sacks": {
    "state": "POWER_LIMITED",
    "reason": "`nf_w7_def_sacks`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it \u2014 DSR alone needs 172 folds against 8 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
    "retest_trigger": "+164 folds for the DSR gate \u2014 field size alone cannot rescue it at this dispersion"
  },
  "layer_a::def_int": {
    "state": "DSR_UNREACHABLE",
    "reason": "`nf_w7_def_int`: the winner's per-fold Sharpe 0.153 sits at or BELOW the 3-arm field's deflated benchmark SR0 3.281, so DSR is unreachable at ANY fold count \u2014 `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, pre-registered field, not more seasons. `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
    "retest_trigger": "NOT rescuable by field size either \u2014 even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)",
    "field_shrink_flag": {
      "proposed_field_size": null,
      "declared_family_size": 3,
      "status": "SUSPECT \u2014 NOT ADVICE",
      "note": "the instrument suggests a smaller field, but this story's family of 3 arms was PRE-REGISTERED as the minimum \u00a70.5 field (\u22653 classes + a direct-learned foil). \u26d4 Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one."
    }
  },
  "layer_a::def_fumble_rec": {
    "state": "GENUINE_ABSENCE",
    "reason": "`nf_w7_def_fumble_rec`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign \u2014 do NOT re-test.",
    "retest_trigger": null
  },
  "layer_a::fg_make": {
    "state": "DSR_UNREACHABLE",
    "reason": "`nf_w7_fg_make`: the winner's per-fold Sharpe 1.056 sits at or BELOW the 3-arm field's deflated benchmark SR0 1.246, so DSR is unreachable at ANY fold count \u2014 `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, pre-registered field, not more seasons. `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
    "retest_trigger": "NOT rescuable by field size either \u2014 even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)",
    "field_shrink_flag": {
      "proposed_field_size": null,
      "declared_family_size": 3,
      "status": "SUSPECT \u2014 NOT ADVICE",
      "note": "the instrument suggests a smaller field, but this story's family of 3 arms was PRE-REGISTERED as the minimum \u00a70.5 field (\u22653 classes + a direct-learned foil). \u26d4 Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one."
    }
  },
  "layer_a::fg_band": {
    "state": "DSR_UNREACHABLE",
    "reason": "`nf_w7_fg_band`: the winner's per-fold Sharpe 1.366 sits at or BELOW the 3-arm field's deflated benchmark SR0 1.460, so DSR is unreachable at ANY fold count \u2014 `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, pre-registered field, not more seasons. `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.",
    "retest_trigger": "NOT rescuable by field size either \u2014 even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)",
    "field_shrink_flag": {
      "proposed_field_size": null,
      "declared_family_size": 3,
      "status": "SUSPECT \u2014 NOT ADVICE",
      "note": "the instrument suggests a smaller field, but this story's family of 3 arms was PRE-REGISTERED as the minimum \u00a70.5 field (\u22653 classes + a direct-learned foil). \u26d4 Shrinking below it would be a POST-HOC field, which is the selection bias DSR exists to deflate (MH2.2). Treat this remedy as SUSPECT, not as advice: you may PRE-REGISTER a family, you may not DISCOVER one."
    }
  },
  "layer_a::dst_td": {
    "state": "GENUINE_ABSENCE",
    "reason": "`nf_w7_dst_td`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign \u2014 do NOT re-test.",
    "retest_trigger": null
  },
  "layer_a::def_safety": {
    "state": "GENUINE_ABSENCE",
    "reason": "`nf_w7_def_safety`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign \u2014 do NOT re-test.",
    "retest_trigger": null
  },
  "layer_a::def_blocked_kick": {
    "state": "GENUINE_ABSENCE",
    "reason": "`nf_w7_def_blocked_kick`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign \u2014 do NOT re-test.",
    "retest_trigger": null
  },
  "layer_b::dst_points": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w7_downstream_dst_points`: 8 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "-4 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "EVALUABLE \u2014 PBO is computed over the 4-config eligible field (assembled + 3 foils); the DSR trial field is the single pre-registered arm (sr0=0, a plain PSR), declared in the pre-registration \u00a77.",
    "state": "CONSTRAINT_REFUSED",
    "reason": "every statistical gate is GREEN \u2014 the assembled arm beats the best foil by +0.0338 CRPS (CI95 [0.0094, 0.0582] excludes zero), fold wins 7 against a required 6, p=0.0067, PBO/DSR/FDR all pass \u2014 and the ship is refused by the pre-registered coverage(80) FLOOR alone: 0.7603 against 0.80 at n=2174 (\u22484.6 binomial SE below nominal \u2014 decisive under-coverage, not sampling noise). The mechanism is the DECLARED independence-simplification check firing: component banks drawn independently under-disperse the assembled sum wherever the components co-move.",
    "retest_trigger": "NONE \u2014 a constraint refusal is not rescuable by data (NF-D18): more folds make the refusal MORE certain. The remedy is a DIFFERENT MECHANISM (a successor modeling cross-component dependence \u2014 e.g. a joint/copula draw over the component legs) or a PM decision; \u26d4 never a post-hoc floor change (a floor re-set after seeing the result is the E2.1-r inversion \u2014 NF1.8).",
    "gate_sensitivity": {
      "waived": [],
      "still_refusing": [
        "coverage_floor_ok"
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
    "fg_att": [
      "pois_glm",
      "negbin_glm",
      "lgbm_quantile"
    ],
    "xp_att": [
      "pois_glm",
      "negbin_glm",
      "lgbm_quantile"
    ],
    "def_sacks": [
      "pois_glm",
      "negbin_glm",
      "lgbm_quantile"
    ],
    "def_int": [
      "pois_glm",
      "negbin_glm",
      "lgbm_quantile"
    ],
    "def_fumble_rec": [
      "pois_glm",
      "negbin_glm",
      "lgbm_quantile"
    ],
    "dst_td": [
      "eb_pois",
      "hurdle_pois"
    ],
    "def_safety": [
      "eb_pois",
      "hurdle_pois"
    ],
    "def_blocked_kick": [
      "eb_pois",
      "hurdle_pois"
    ],
    "fg_make": [
      "eb_kicker_curve",
      "logit_distance_glm",
      "lgbm_classifier"
    ],
    "fg_band": [
      "mnlogit",
      "eb_dirichlet_kicker",
      "lgbm_multiclass"
    ],
    "pa_bucket": [
      "ordered_logit",
      "mnlogit",
      "negbin_integrated"
    ],
    "ya_bucket": [
      "ordered_logit",
      "mnlogit",
      "gauss_integrated"
    ]
  },
  "foils": {
    "fg_att": [
      "foil_climatology",
      "foil_entity_eb"
    ],
    "xp_att": [
      "foil_climatology",
      "foil_entity_eb"
    ],
    "def_sacks": [
      "foil_climatology",
      "foil_entity_eb"
    ],
    "def_int": [
      "foil_climatology",
      "foil_entity_eb"
    ],
    "def_fumble_rec": [
      "foil_climatology",
      "foil_entity_eb"
    ],
    "dst_td": [
      "foil_climatology",
      "foil_league_rate"
    ],
    "def_safety": [
      "foil_climatology",
      "foil_league_rate"
    ],
    "def_blocked_kick": [
      "foil_climatology",
      "foil_league_rate"
    ],
    "fg_make": [
      "foil_league_curve",
      "foil_constant_rate"
    ],
    "fg_band": [
      "foil_league_mix"
    ],
    "pa_bucket": [
      "foil_climatology",
      "foil_entity_eb"
    ],
    "ya_bucket": [
      "foil_climatology",
      "foil_entity_eb"
    ]
  },
  "leg_metrics": {
    "fg_att": "crps_q199",
    "xp_att": "crps_q199",
    "def_sacks": "crps_q199",
    "def_int": "crps_q199",
    "def_fumble_rec": "crps_q199",
    "dst_td": "crps_q199",
    "def_safety": "crps_q199",
    "def_blocked_kick": "crps_q199",
    "fg_make": "log_loss",
    "fg_band": "log_loss_multiclass",
    "pa_bucket": "rps",
    "ya_bucket": "rps"
  },
  "layer_b_eligible": [
    "assembled",
    "foil_climatology",
    "foil_board_eb",
    "foil_direct"
  ],
  "layer_b_anchors": [
    "nihilist_zero",
    "zero_width",
    "max_width",
    "permuted_direct",
    "oracle__assembled",
    "matched_n__assembled",
    "oracle__foil_climatology",
    "oracle__foil_board_eb",
    "oracle__foil_direct"
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
      "fg_att",
      "xp_att",
      "def_sacks",
      "def_int",
      "def_fumble_rec",
      "fg_make",
      "fg_band",
      "dst_td",
      "def_safety",
      "def_blocked_kick",
      "pa_bucket",
      "ya_bucket"
    ],
    "downstream": [
      "k_points",
      "dst_points"
    ]
  },
  "coverage_floor": 0.8,
  "features_k": [
    "game_context__is_home",
    "game_context__div_game",
    "game_context__week_index",
    "game_context__days_since_last_game",
    "game_context__roofed_stadium",
    "prior_week_box__fg_att_l4",
    "prior_week_box__fg_att_l8",
    "prior_week_box__fg_att_ewm",
    "prior_week_box__fg_att_s2d",
    "prior_week_box__fg_att_prior_season",
    "prior_week_box__pat_att_l4",
    "prior_week_box__pat_att_l8",
    "prior_week_box__fg_makerate_prior",
    "prior_week_box__share50_prior",
    "prior_week_box__kicker_games_prior_season",
    "team_environment__points_l4",
    "team_environment__points_l8",
    "team_environment__points_prior_season",
    "team_environment__drives_l4",
    "team_environment__rz_trips_l4",
    "team_environment__rz_tdrate_l4",
    "team_environment__fgrange_trips_l4",
    "team_environment__team_fg_att_l4",
    "team_environment__epa_per_play_l4",
    "team_environment__games_prior_season",
    "opponent_matchup__def_points_allowed_l4",
    "opponent_matchup__def_rz_tdrate_allowed_l4",
    "opponent_matchup__def_fgatt_faced_l4",
    "opponent_matchup__def_epa_allowed_l4",
    "opponent_matchup__def_drives_faced_l4"
  ],
  "features_d": [
    "game_context__is_home",
    "game_context__div_game",
    "game_context__week_index",
    "game_context__days_since_last_game",
    "team_environment__sacks_l4",
    "team_environment__sacks_l8",
    "team_environment__sacks_ewm",
    "team_environment__qb_hits_l4",
    "team_environment__tfl_l4",
    "team_environment__int_l4",
    "team_environment__int_l8",
    "team_environment__fr_l4",
    "team_environment__takeaways_l8",
    "team_environment__dsttd_l16",
    "team_environment__safety_l16",
    "team_environment__block_l16",
    "team_environment__pa_l4",
    "team_environment__pa_l8",
    "team_environment__pa_s2d",
    "team_environment__pa_prior_season",
    "team_environment__ya_l4",
    "team_environment__ya_l8",
    "team_environment__games_prior_season",
    "opponent_matchup__opp_points_l4",
    "opponent_matchup__opp_points_l8",
    "opponent_matchup__opp_points_prior_season",
    "opponent_matchup__opp_sacks_taken_l4",
    "opponent_matchup__opp_sacks_taken_l8",
    "opponent_matchup__opp_giveaways_l4",
    "opponent_matchup__opp_giveaways_l8",
    "opponent_matchup__opp_off_yards_l4",
    "opponent_matchup__opp_pass_yards_l4"
  ],
  "features_make": [
    "game_context__kick_distance",
    "game_context__roofed_stadium",
    "prior_week_box__kicker_prior_makerate_eb",
    "prior_week_box__kicker_prior_att"
  ],
  "features_band": [
    "game_context__roofed_stadium",
    "prior_week_box__kicker_prior_share50_eb",
    "prior_week_box__kicker_prior_share40_eb",
    "prior_week_box__kicker_prior_att"
  ],
  "assembly_draws": 4000,
  "eb_kappa_games": 8.0,
  "pa_edges": [
    0,
    1,
    7,
    14,
    18,
    21,
    28,
    35,
    46
  ],
  "ya_edges": [
    0,
    100,
    200,
    300,
    350,
    400,
    450,
    500,
    550
  ],
  "pa_tier_points": [
    5.0,
    4.0,
    3.0,
    1.0,
    0.0,
    0.0,
    -1.0,
    -3.0,
    -5.0
  ],
  "band_points": [
    3.0,
    4.0,
    5.0
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