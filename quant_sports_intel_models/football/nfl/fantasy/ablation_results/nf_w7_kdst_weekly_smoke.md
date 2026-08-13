# NF-W7 — weekly Kicker + DST projections, exact tier scoring as bucket probabilities (§0.5 bake-off)

**Generated:** 2026-08-13T05:59:42+00:00 · **folds:** 2 (2025H1…2025H2, the NF-W1 axis verbatim) · **kicker-weeks:** 5318 · **team-weeks:** 5278 · **FG attempts:** 10277

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** (serving is the weekly path / NF-C6, an operator decision). Selection is `crps_q199` on the dense grid for banks, log-loss / RPS for the categorical legs; MAE never selects. Every direction word is three-way and derived at report time, failing closed to `TIES` (NF-W2e).

**PIT gate (dst):** 175 weeks / 5278 records; 0 rows dropped fail-closed.
**PIT gate (kicker):** 175 weeks / 5318 records; 0 rows dropped fail-closed.
**PIT gate (attempt):** 175 weeks / 10277 records; 0 rows dropped fail-closed.

## ⭐ Headline

- **Layer B (the gate — does the component chain beat the climatology null, the board-EB read and the direct-points foil?)** — k_points: **POWER_LIMITED** · dst_points: **POWER_LIMITED**
- **Layer A (components)** — fg_att: **UNDEFINED** · xp_att: **UNDEFINED** · def_sacks: **UNDEFINED** · def_int: **UNDEFINED** · def_fumble_rec: **UNDEFINED** · fg_make: **UNDEFINED** · fg_band: **UNDEFINED** · dst_td: **UNDEFINED** · def_safety: **UNDEFINED** · def_blocked_kick: **UNDEFINED** · pa_bucket: **UNDEFINED** · ya_bucket: **UNDEFINED**

## ⭐ Layer B — the assembled fantasy-point distributions

### `k_points` — **POWER_LIMITED**

`assembled` TIES `foil_climatology` by +0.0410 CRPS (interval unevaluable)

| label                    |   mean_crps_q199 |
|:-------------------------|-----------------:|
| oracle__foil_direct      |           1.6606 |
| oracle__assembled        |           2.4743 |
| assembled                |           2.6313 |
| oracle__foil_climatology |           2.6483 |
| oracle__foil_board_eb    |           2.6593 |
| foil_climatology         |           2.6723 |
| foil_board_eb            |           2.6850 |
| foil_direct              |           2.7037 |
| permuted_direct          |           2.7275 |
| matched_n__assembled     |           2.9461 |
| zero_width               |           3.7433 |
| max_width                |           3.9299 |
| nihilist_zero            |           8.5167 |

- fold wins 2/2 (clause requires None) · PBO None · DSR(=PSR, 1 arm) None · p None · BH own-family False / pooled False (binding False)
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 8.5167, 'zero_width': 3.7433, 'max_width': 3.9299}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- permutation: {'permuted_lift_vs_foil_mean': -0.0552, 'permuted_lift_p_one_sided': None} · coverage(80) {'winner_coverage_80': 0.8548, 'n_rows': 544, 'binomial_se': 0.0171, 'blocking_shortfall': False}
- randomized-PIT flatness by fold (report-only): [{'max_decile_dev': 0.03333333333333334, 'n': 270}, {'max_decile_dev': 0.027737226277372268, 'n': 274}]
- capture-era (2025) fold deltas, report-only (NF-W2d): {'2025H1': 0.0116, '2025H2': 0.0704}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True}
- null state: **POWER_LIMITED** — the point estimate is positive (+0.0410 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 2/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design — the effect is simply smaller than this design can resolve. Re-test: ~4 half-season folds (≈2 seasons) for the DSR gate at the observed per-fold Sharpe 0.987 — i.e. CALENDAR-bound and far beyond any plausible window; ⛔ this is NOT a near-term re-test.
- 🩹 hand-corrected from the instrument verdict {'state': 'UNDEFINED', 'reason': '`nf_w7_downstream_k_points`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.', 'retest_trigger': '2 more fold(s) — i.e. a window of 7 seasons'} (the known classify_null n_arms=1 mis-render).

### `dst_points` — **POWER_LIMITED**

`assembled` TIES `foil_direct` by +0.0588 CRPS (interval unevaluable)

| label                    |   mean_crps_q199 |
|:-------------------------|-----------------:|
| oracle__foil_direct      |           1.6965 |
| oracle__assembled        |           2.4766 |
| assembled                |           2.6587 |
| foil_direct              |           2.7175 |
| oracle__foil_board_eb    |           2.7211 |
| oracle__foil_climatology |           2.7220 |
| foil_board_eb            |           2.7316 |
| foil_climatology         |           2.7363 |
| permuted_direct          |           2.8101 |
| zero_width               |           3.8101 |
| max_width                |           4.0681 |
| nihilist_zero            |           5.9259 |
| matched_n__assembled     |           6.3807 |

- fold wins 2/2 (clause requires None) · PBO None · DSR(=PSR, 1 arm) None · p None · BH own-family False / pooled False (binding False)
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 5.9259, 'zero_width': 3.8101, 'max_width': 4.0681}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- permutation: {'permuted_lift_vs_foil_mean': -0.0926, 'permuted_lift_p_one_sided': None} · coverage(80) {'winner_coverage_80': 0.761, 'n_rows': 544, 'binomial_se': 0.0171, 'blocking_shortfall': False}
- randomized-PIT flatness by fold (report-only): [{'max_decile_dev': 0.07037037037037036, 'n': 270}, {'max_decile_dev': 0.04233576642335765, 'n': 274}]
- capture-era (2025) fold deltas, report-only (NF-W2d): {'2025H1': 0.0608, '2025H2': 0.0567}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True, 'coverage_floor_ok': True}
- null state: **POWER_LIMITED** — the point estimate is positive (+0.0588 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 2/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design — the effect is simply smaller than this design can resolve. Re-test: ~2 half-season folds (≈1 seasons) for the DSR gate at the observed per-fold Sharpe 20.101 — i.e. CALENDAR-bound and far beyond any plausible window; ⛔ this is NOT a near-term re-test.
- 🩹 hand-corrected from the instrument verdict {'state': 'UNDEFINED', 'reason': '`nf_w7_downstream_dst_points`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.', 'retest_trigger': '2 more fold(s) — i.e. a window of 7 seasons'} (the known classify_null n_arms=1 mis-render).

## Layer A — the component legs

### `fg_att` (crps_q199) — **UNDEFINED**

`pois_glm` TIES `foil_climatology` by +0.0009 CRPS (interval unevaluable)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__lgbm_quantile    |       0.4660 |
| oracle__pois_glm         |       0.6676 |
| oracle__negbin_glm       |       0.6677 |
| oracle__foil_climatology |       0.7178 |
| pois_glm                 |       0.7212 |
| negbin_glm               |       0.7212 |
| foil_climatology         |       0.7221 |
| foil_entity_eb           |       0.7261 |
| oracle__foil_entity_eb   |       0.7263 |
| permuted_control         |       0.7567 |
| lgbm_quantile            |       0.7587 |
| matched_n__lgbm_quantile |       0.7796 |
| matched_n__pois_glm      |       0.8298 |
| matched_n__negbin_glm    |       0.8308 |
| zero_width               |       0.9664 |
| max_width                |       1.1704 |
| nihilist_zero            |       2.0001 |

- fold wins 1/2 (requires None) · PBO None · DSR None · p None · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 2.0001, 'zero_width': 0.9664, 'max_width': 1.1704}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': False}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'pois_glm': {'arm': 0.7212, 'own_form_oracle': 0.6676, 'matched_n': 0.8298}, 'negbin_glm': {'arm': 0.7212, 'own_form_oracle': 0.6677, 'matched_n': 0.8308}, 'lgbm_quantile': {'arm': 0.7587, 'own_form_oracle': 0.466, 'matched_n': 0.7796}}
- era deltas (2025, report-only): {'2025H1': -0.0029, '2025H2': 0.0046}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **UNDEFINED** — `nf_w7_fg_att`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.

### `xp_att` (crps_q199) — **UNDEFINED**

`pois_glm` TIES `foil_entity_eb` by +0.0198 CRPS (interval unevaluable)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__lgbm_quantile    |       0.4927 |
| oracle__pois_glm         |       0.7229 |
| oracle__negbin_glm       |       0.7229 |
| pois_glm                 |       0.7723 |
| negbin_glm               |       0.7724 |
| oracle__foil_entity_eb   |       0.7910 |
| foil_entity_eb           |       0.7922 |
| oracle__foil_climatology |       0.8068 |
| foil_climatology         |       0.8088 |
| lgbm_quantile            |       0.8120 |
| matched_n__pois_glm      |       0.8336 |
| matched_n__negbin_glm    |       0.8343 |
| permuted_control         |       0.8410 |
| matched_n__lgbm_quantile |       0.8431 |
| zero_width               |       1.1381 |
| max_width                |       1.2795 |
| nihilist_zero            |       2.3185 |

- fold wins 2/2 (requires None) · PBO None · DSR None · p None · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 2.3185, 'zero_width': 1.1381, 'max_width': 1.2795}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'pois_glm': {'arm': 0.7723, 'own_form_oracle': 0.7229, 'matched_n': 0.8336}, 'negbin_glm': {'arm': 0.7724, 'own_form_oracle': 0.7229, 'matched_n': 0.8343}, 'lgbm_quantile': {'arm': 0.812, 'own_form_oracle': 0.4927, 'matched_n': 0.8431}}
- era deltas (2025, report-only): {'2025H1': 0.0109, '2025H2': 0.0288}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **UNDEFINED** — `nf_w7_xp_att`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.

### `def_sacks` (crps_q199) — **UNDEFINED**

`negbin_glm` TIES `foil_entity_eb` by +0.0252 CRPS (interval unevaluable)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__lgbm_quantile    |       0.6023 |
| oracle__negbin_glm       |       0.8700 |
| oracle__pois_glm         |       0.8707 |
| negbin_glm               |       0.9469 |
| pois_glm                 |       0.9507 |
| oracle__foil_entity_eb   |       0.9717 |
| oracle__foil_climatology |       0.9720 |
| foil_entity_eb           |       0.9721 |
| foil_climatology         |       0.9737 |
| lgbm_quantile            |       0.9938 |
| permuted_control         |       1.0204 |
| matched_n__negbin_glm    |       1.0403 |
| matched_n__lgbm_quantile |       1.0427 |
| matched_n__pois_glm      |       1.0499 |
| zero_width               |       1.3603 |
| max_width                |       1.4733 |
| nihilist_zero            |       2.3497 |

- fold wins 2/2 (requires None) · PBO None · DSR None · p None · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 2.3497, 'zero_width': 1.3603, 'max_width': 1.4733}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'pois_glm': {'arm': 0.9507, 'own_form_oracle': 0.8707, 'matched_n': 1.0499}, 'negbin_glm': {'arm': 0.9469, 'own_form_oracle': 0.87, 'matched_n': 1.0403}, 'lgbm_quantile': {'arm': 0.9938, 'own_form_oracle': 0.6023, 'matched_n': 1.0427}}
- era deltas (2025, report-only): {'2025H1': 0.0103, '2025H2': 0.0402}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **UNDEFINED** — `nf_w7_def_sacks`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.

### `def_int` (crps_q199) — **UNDEFINED**

`negbin_glm` TIES `foil_entity_eb` by +0.0009 CRPS (interval unevaluable)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__lgbm_quantile    |       0.2883 |
| oracle__pois_glm         |       0.3839 |
| oracle__negbin_glm       |       0.3839 |
| negbin_glm               |       0.4203 |
| pois_glm                 |       0.4204 |
| oracle__foil_entity_eb   |       0.4209 |
| foil_entity_eb           |       0.4212 |
| oracle__foil_climatology |       0.4229 |
| foil_climatology         |       0.4260 |
| lgbm_quantile            |       0.4549 |
| matched_n__lgbm_quantile |       0.4563 |
| permuted_control         |       0.4636 |
| zero_width               |       0.6951 |
| nihilist_zero            |       0.6984 |
| max_width                |       0.9427 |
| matched_n__pois_glm      |       2.2508 |
| matched_n__negbin_glm    |       2.2520 |

- fold wins 1/2 (requires None) · PBO None · DSR None · p None · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 0.6984, 'zero_width': 0.6951, 'max_width': 0.9427}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'pois_glm': {'arm': 0.4204, 'own_form_oracle': 0.3839, 'matched_n': 2.2508}, 'negbin_glm': {'arm': 0.4203, 'own_form_oracle': 0.3839, 'matched_n': 2.252}, 'lgbm_quantile': {'arm': 0.4549, 'own_form_oracle': 0.2883, 'matched_n': 0.4563}}
- era deltas (2025, report-only): {'2025H1': 0.01, '2025H2': -0.0083}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **UNDEFINED** — `nf_w7_def_int`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.

### `def_fumble_rec` (crps_q199) — **UNDEFINED**

`pois_glm` TIES `foil_climatology` by -0.0014 CRPS (interval unevaluable)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__lgbm_quantile    |       0.2257 |
| oracle__negbin_glm       |       0.2861 |
| oracle__pois_glm         |       0.2862 |
| oracle__foil_climatology |       0.3154 |
| foil_climatology         |       0.3198 |
| pois_glm                 |       0.3212 |
| negbin_glm               |       0.3212 |
| oracle__foil_entity_eb   |       0.3254 |
| foil_entity_eb           |       0.3258 |
| lgbm_quantile            |       0.3502 |
| permuted_control         |       0.3535 |
| matched_n__lgbm_quantile |       0.3676 |
| matched_n__pois_glm      |       0.3694 |
| matched_n__negbin_glm    |       0.3697 |
| nihilist_zero            |       0.4521 |
| zero_width               |       0.4521 |
| max_width                |       0.6314 |

- fold wins 1/2 (requires None) · PBO None · DSR None · p None · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 0.4521, 'zero_width': 0.4521, 'max_width': 0.6314}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'pois_glm': {'arm': 0.3212, 'own_form_oracle': 0.2862, 'matched_n': 0.3694}, 'negbin_glm': {'arm': 0.3212, 'own_form_oracle': 0.2861, 'matched_n': 0.3697}, 'lgbm_quantile': {'arm': 0.3502, 'own_form_oracle': 0.2257, 'matched_n': 0.3676}}
- era deltas (2025, report-only): {'2025H1': -0.0057, '2025H2': 0.0028}
- gate: {'beats_foil': False, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **UNDEFINED** — `nf_w7_def_fumble_rec`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.

### `fg_make` (log_loss) — **UNDEFINED**

`eb_kicker_curve` TIES `foil_league_curve` by +0.0046 CRPS (interval unevaluable)

| label                         |   mean_score |
|:------------------------------|-------------:|
| oracle__lgbm_classifier       |       0.1527 |
| oracle__foil_league_curve     |       0.3584 |
| oracle__logit_distance_glm    |       0.3591 |
| oracle__eb_kicker_curve       |       0.3599 |
| matched_n__eb_kicker_curve    |       0.3599 |
| eb_kicker_curve               |       0.3624 |
| logit_distance_glm            |       0.3632 |
| permuted_control              |       0.3646 |
| matched_n__logit_distance_glm |       0.3650 |
| foil_league_curve             |       0.3670 |
| lgbm_classifier               |       0.3819 |
| oracle__foil_constant_rate    |       0.4114 |
| foil_constant_rate            |       0.4131 |
| matched_n__lgbm_classifier    |       0.4594 |
| uniform                       |       0.6931 |
| all_event                     |       0.9974 |

- fold wins 2/2 (requires None) · PBO None · DSR None · p None · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'all_event': 0.9974, 'uniform': 0.6931}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': False, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'eb_kicker_curve': {'arm': 0.3624, 'own_form_oracle': 0.3599, 'matched_n': 0.3599}, 'logit_distance_glm': {'arm': 0.3632, 'own_form_oracle': 0.3591, 'matched_n': 0.365}, 'lgbm_classifier': {'arm': 0.3819, 'own_form_oracle': 0.1527, 'matched_n': 0.4594}}
- era deltas (2025, report-only): {'2025H1': 0.006, '2025H2': 0.0032}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': False, 'oracle_floors_respected': True}
- null state: **UNDEFINED** — `nf_w7_fg_make`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.

### `fg_band` (log_loss_multiclass) — **UNDEFINED**

`mnlogit` TIES `foil_league_mix` by +0.0134 CRPS (interval unevaluable)

| label                          |   mean_score |
|:-------------------------------|-------------:|
| oracle__lgbm_multiclass        |       0.7313 |
| oracle__mnlogit                |       1.0436 |
| mnlogit                        |       1.0566 |
| oracle__foil_league_mix        |       1.0575 |
| permuted_control               |       1.0613 |
| foil_league_mix                |       1.0700 |
| matched_n__mnlogit             |       1.0721 |
| oracle__eb_dirichlet_kicker    |       1.0788 |
| matched_n__eb_dirichlet_kicker |       1.0792 |
| eb_dirichlet_kicker            |       1.0804 |
| lgbm_multiclass                |       1.0858 |
| uniform                        |       1.0986 |
| matched_n__lgbm_multiclass     |       1.2623 |
| point_mass_modal               |       7.3520 |

- fold wins 2/2 (requires None) · PBO None · DSR None · p None · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'uniform': 1.0986, 'point_mass_modal': 7.352}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': False, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'mnlogit': {'arm': 1.0566, 'own_form_oracle': 1.0436, 'matched_n': 1.0721}, 'eb_dirichlet_kicker': {'arm': 1.0804, 'own_form_oracle': 1.0788, 'matched_n': 1.0792}, 'lgbm_multiclass': {'arm': 1.0858, 'own_form_oracle': 0.7313, 'matched_n': 1.2623}}
- era deltas (2025, report-only): {'2025H1': 0.023, '2025H2': 0.0038}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': False, 'oracle_floors_respected': True}
- null state: **UNDEFINED** — `nf_w7_fg_band`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.

### `dst_td` (crps_q199) — **UNDEFINED**

`eb_pois` TIES `foil_climatology` by -0.0010 CRPS (interval unevaluable)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__hurdle_pois      |       0.0847 |
| oracle__foil_climatology |       0.0919 |
| oracle__foil_league_rate |       0.0919 |
| foil_climatology         |       0.0920 |
| foil_league_rate         |       0.0921 |
| eb_pois                  |       0.0930 |
| oracle__eb_pois          |       0.0930 |
| permuted_control         |       0.0930 |
| matched_n__eb_pois       |       0.0931 |
| hurdle_pois              |       0.0942 |
| nihilist_zero            |       0.1010 |
| zero_width               |       0.1010 |
| max_width                |       0.1105 |
| matched_n__hurdle_pois   |       0.1808 |

- fold wins 0/2 (requires None) · PBO None · DSR None · p None · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 0.101, 'zero_width': 0.101, 'max_width': 0.1105}, 'winner_beats_permuted': False, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': False, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'eb_pois': {'arm': 0.093, 'own_form_oracle': 0.093, 'matched_n': 0.0931}, 'hurdle_pois': {'arm': 0.0942, 'own_form_oracle': 0.0847, 'matched_n': 0.1808}}
- era deltas (2025, report-only): {'2025H1': -0.0016, '2025H2': -0.0004}
- gate: {'beats_foil': False, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': False, 'oracle_floors_respected': True}
- null state: **UNDEFINED** — `nf_w7_dst_td`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.

### `def_safety` (crps_q199) — **UNDEFINED**

`hurdle_pois` TIES `foil_climatology` by -0.0006 CRPS (interval unevaluable)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__hurdle_pois      |       0.0187 |
| foil_climatology         |       0.0217 |
| oracle__foil_climatology |       0.0217 |
| foil_league_rate         |       0.0217 |
| oracle__foil_league_rate |       0.0217 |
| nihilist_zero            |       0.0221 |
| zero_width               |       0.0221 |
| hurdle_pois              |       0.0223 |
| oracle__eb_pois          |       0.0224 |
| matched_n__eb_pois       |       0.0224 |
| eb_pois                  |       0.0225 |
| permuted_control         |       0.0225 |
| max_width                |       0.0232 |
| matched_n__hurdle_pois   |       0.0535 |

- fold wins 0/2 (requires None) · PBO None · DSR None · p None · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': False, 'degenerate_detail': {'nihilist_zero': 0.0221, 'zero_width': 0.0221, 'max_width': 0.0232}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'eb_pois': {'arm': 0.0225, 'own_form_oracle': 0.0224, 'matched_n': 0.0224}, 'hurdle_pois': {'arm': 0.0223, 'own_form_oracle': 0.0187, 'matched_n': 0.0535}}
- era deltas (2025, report-only): {'2025H1': -0.0008, '2025H2': -0.0004}
- gate: {'beats_foil': False, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': False, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **UNDEFINED** — `nf_w7_def_safety`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.

### `def_blocked_kick` (crps_q199) — **UNDEFINED**

`eb_pois` TIES `foil_climatology` by +0.0002 CRPS (interval unevaluable)

| label                    |   mean_score |
|:-------------------------|-------------:|
| oracle__hurdle_pois      |       0.0656 |
| oracle__eb_pois          |       0.0748 |
| eb_pois                  |       0.0749 |
| permuted_control         |       0.0749 |
| oracle__foil_climatology |       0.0750 |
| oracle__foil_league_rate |       0.0750 |
| matched_n__eb_pois       |       0.0750 |
| foil_climatology         |       0.0751 |
| foil_league_rate         |       0.0751 |
| hurdle_pois              |       0.0760 |
| nihilist_zero            |       0.0810 |
| zero_width               |       0.0810 |
| max_width                |       0.0854 |
| matched_n__hurdle_pois   |       0.1563 |

- fold wins 1/2 (requires None) · PBO None · DSR None · p None · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'nihilist_zero': 0.081, 'zero_width': 0.081, 'max_width': 0.0854}, 'winner_beats_permuted': False, 'permuted_lift_not_significant': False, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'eb_pois': {'arm': 0.0749, 'own_form_oracle': 0.0748, 'matched_n': 0.075}, 'hurdle_pois': {'arm': 0.076, 'own_form_oracle': 0.0656, 'matched_n': 0.1563}}
- era deltas (2025, report-only): {'2025H1': 0.0016, '2025H2': -0.0011}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': False, 'oracle_floors_respected': True}
- null state: **UNDEFINED** — `nf_w7_def_blocked_kick`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.

### `pa_bucket` (rps) — **UNDEFINED**

`ordered_logit` TIES `foil_entity_eb` by +0.0060 CRPS (interval unevaluable)

| label                        |   mean_score |
|:-----------------------------|-------------:|
| oracle__mnlogit              |       0.0917 |
| oracle__ordered_logit        |       0.1059 |
| oracle__negbin_integrated    |       0.1078 |
| ordered_logit                |       0.1149 |
| negbin_integrated            |       0.1154 |
| mnlogit                      |       0.1155 |
| oracle__foil_entity_eb       |       0.1195 |
| foil_entity_eb               |       0.1209 |
| oracle__foil_climatology     |       0.1227 |
| foil_climatology             |       0.1230 |
| permuted_control             |       0.1240 |
| matched_n__negbin_integrated |       0.1296 |
| matched_n__ordered_logit     |       0.1316 |
| uniform                      |       0.1386 |
| matched_n__mnlogit           |       0.1494 |
| point_mass_modal             |       0.1730 |

- fold wins 2/2 (requires None) · PBO None · DSR None · p None · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'uniform': 0.1386, 'point_mass_modal': 0.173}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': True, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'ordered_logit': {'arm': 0.1149, 'own_form_oracle': 0.1059, 'matched_n': 0.1316}, 'mnlogit': {'arm': 0.1155, 'own_form_oracle': 0.0917, 'matched_n': 0.1494}, 'negbin_integrated': {'arm': 0.1154, 'own_form_oracle': 0.1078, 'matched_n': 0.1296}}
- era deltas (2025, report-only): {'2025H1': 0.0056, '2025H2': 0.0064}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': True, 'oracle_floors_respected': True}
- null state: **UNDEFINED** — `nf_w7_pa_bucket`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.

### `ya_bucket` (rps) — **UNDEFINED**

`gauss_integrated` TIES `foil_entity_eb` by +0.0071 CRPS (interval unevaluable)

| label                       |   mean_score |
|:----------------------------|-------------:|
| oracle__mnlogit             |       0.0721 |
| oracle__ordered_logit       |       0.0841 |
| oracle__gauss_integrated    |       0.0849 |
| gauss_integrated            |       0.0911 |
| ordered_logit               |       0.0912 |
| mnlogit                     |       0.0918 |
| oracle__foil_entity_eb      |       0.0950 |
| oracle__foil_climatology    |       0.0974 |
| permuted_control            |       0.0975 |
| foil_entity_eb              |       0.0982 |
| foil_climatology            |       0.0996 |
| matched_n__gauss_integrated |       0.1075 |
| matched_n__ordered_logit    |       0.1095 |
| uniform                     |       0.1288 |
| matched_n__mnlogit          |       0.1293 |
| point_mass_modal            |       0.1726 |

- fold wins 2/2 (requires None) · PBO None · DSR None · p None · BH own/pooled/binding False/False/False
- anchors: {'degenerates_lose': True, 'degenerate_detail': {'uniform': 0.1288, 'point_mass_modal': 0.1726}, 'winner_beats_permuted': True, 'permuted_lift_not_significant': False, 'no_arm_beats_own_oracle': True, 'oracle_floors_respected_at_matched_n': True, 'foils_respect_own_oracle': True}
- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {'ordered_logit': {'arm': 0.0912, 'own_form_oracle': 0.0841, 'matched_n': 0.1095}, 'mnlogit': {'arm': 0.0918, 'own_form_oracle': 0.0721, 'matched_n': 0.1293}, 'gauss_integrated': {'arm': 0.0911, 'own_form_oracle': 0.0849, 'matched_n': 0.1075}}
- era deltas (2025, report-only): {'2025H1': 0.0052, '2025H2': 0.0091}
- gate: {'beats_foil': True, 'fold_consistency': False, 'pbo_ok': False, 'dsr_ok': False, 'fdr_ok': False, 'degenerates_lose': True, 'permutation_behaves': False, 'oracle_floors_respected': True}
- null state: **UNDEFINED** — `nf_w7_ya_bucket`: 2 fold(s) < 4 — CSCV/PBO is UNDEFINED, so the §0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.

## Null-state classification

```json
{
  "layer_a::fg_att": {
    "state": "UNDEFINED",
    "reason": "`nf_w7_fg_att`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_a::xp_att": {
    "state": "UNDEFINED",
    "reason": "`nf_w7_xp_att`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_a::def_sacks": {
    "state": "UNDEFINED",
    "reason": "`nf_w7_def_sacks`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_a::def_int": {
    "state": "UNDEFINED",
    "reason": "`nf_w7_def_int`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_a::def_fumble_rec": {
    "state": "UNDEFINED",
    "reason": "`nf_w7_def_fumble_rec`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_a::fg_make": {
    "state": "UNDEFINED",
    "reason": "`nf_w7_fg_make`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_a::fg_band": {
    "state": "UNDEFINED",
    "reason": "`nf_w7_fg_band`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_a::dst_td": {
    "state": "UNDEFINED",
    "reason": "`nf_w7_dst_td`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_a::def_safety": {
    "state": "UNDEFINED",
    "reason": "`nf_w7_def_safety`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_a::def_blocked_kick": {
    "state": "UNDEFINED",
    "reason": "`nf_w7_def_blocked_kick`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_a::pa_bucket": {
    "state": "UNDEFINED",
    "reason": "`nf_w7_pa_bucket`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_a::ya_bucket": {
    "state": "UNDEFINED",
    "reason": "`nf_w7_ya_bucket`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
    "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
  },
  "layer_b::k_points": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w7_downstream_k_points`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "EVALUABLE \u2014 PBO is computed over the 4-config eligible field (assembled + 3 foils); the DSR trial field is the single pre-registered arm (sr0=0, a plain PSR), declared in the pre-registration \u00a77.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0410 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 2/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~4 half-season folds (\u22482 seasons) for the DSR gate at the observed per-fold Sharpe 0.987 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test.",
    "gate_sensitivity": {
      "waived": [],
      "still_refusing": [
        "fold_consistency",
        "pbo_ok",
        "dsr_ok",
        "fdr_ok"
      ],
      "ships_without_waived_checks": false
    }
  },
  "layer_b::dst_points": {
    "instrument_verdict": {
      "state": "UNDEFINED",
      "reason": "`nf_w7_downstream_dst_points`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
      "retest_trigger": "2 more fold(s) \u2014 i.e. a window of 7 seasons"
    },
    "hand_corrected": true,
    "pbo_state": "EVALUABLE \u2014 PBO is computed over the 4-config eligible field (assembled + 3 foils); the DSR trial field is the single pre-registered arm (sr0=0, a plain PSR), declared in the pre-registration \u00a77.",
    "state": "POWER_LIMITED",
    "reason": "the point estimate is positive (+0.0588 CRPS) but the interval spans zero (CI95 [None, None]), fold wins are 2/2 against a required None, and p=None. Every statistical gate except PBO is REACHABLE at this design \u2014 the effect is simply smaller than this design can resolve.",
    "retest_trigger": "~2 half-season folds (\u22481 seasons) for the DSR gate at the observed per-fold Sharpe 20.101 \u2014 i.e. CALENDAR-bound and far beyond any plausible window; \u26d4 this is NOT a near-term re-test.",
    "gate_sensitivity": {
      "waived": [],
      "still_refusing": [
        "fold_consistency",
        "pbo_ok",
        "dsr_ok",
        "fdr_ok"
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