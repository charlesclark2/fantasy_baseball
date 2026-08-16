# NF-W6d Phase B — the §0.5 bake-off over the Phase-A-licensed cells

**Generated:** 2026-08-16T01:02:38+00:00 · **folds:** 8 half-season blocks (2022H1…2025H2) · **rows:** 84553 · **cells:** 14 · cell source: Phase-A record nf_w6d_ceiling_gate.json licensed_cells

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held**, NF-G0 staged. FRESH registration (seed 20260817). Per-class atom-aware families (⛔ no linear-residual / plain-quantile arm and no head+bank foil on the EVENT class — the NF-W6b-C field-inflation lesson). Coverage is a one-sided FLOOR (NF1.9 (e)); a distribution here is a calibrated RANGE, never an edge or win-rate claim.

## Reproduction control (NF-W2d): **ALL FOLDS REPRODUCE — run VALID**

| fold | all 7 reproduce | worst |abs diff| | seconds |
|---|---|---|---|
| 2022H1 | True | 0.0 | 163.7 |
| 2022H2 | True | 0.0 | 163.9 |
| 2023H1 | True | 0.0 | 157.8 |
| 2023H2 | True | 0.0 | 172.1 |
| 2024H1 | True | 0.0 | 168.5 |
| 2024H2 | True | 0.0 | 164.7 |
| 2025H1 | True | 0.0 | 169.9 |
| 2025H2 | True | 0.0 | 179.4 |

## Verdict: **PERSTAT-BAKEOFF-D ship=9 null=5 of 14 cells**

per-cell verdicts (no story-level gate): SHIP ['QB|passing_interceptions', 'QB|rushing_tds', 'RB|carries', 'RB|receptions', 'TE|receptions', 'TE|targets', 'WR|receiving_tds', 'WR|receptions', 'WR|targets']; nulls ['QB|attempts', 'QB|carries', 'QB|fumbles_lost', 'RB|targets', 'TE|receiving_tds']

## Per-cell contests (winner vs the BINDING foil)

| cell | class | winner | foil | foil CRPS | Δ | Δ% | CI95 | wins | p | PBO | DSR | SR0 | BH | cov80 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| QB|attempts | count | lgbm_hurdle_tail | inc_head_bank | 4.98797 | 0.86829 | 17.408 | [0.78878, 0.94779] | 8/8 | 0.0 | 0.0 | 0.8061 | 7.3187 | True | 0.8171 | **POWER_LIMITED** |
| QB|carries | count | lgbm_hurdle_tail | inc_head_bank | 0.97039 | 0.15529 | 16.003 | [0.14177, 0.16882] | 8/8 | 0.0 | 0.0 | 0.9981 | 3.7305 | True | 0.8713 | **CONSTRAINT_REFUSED** |
| QB|fumbles_lost | event | knn_quantile | inc_climatology | 0.081 | 0.00416 | 5.137 | [0.00283, 0.00549] | 8/8 | 0.0001 | 0.0 | 0.998 | 1.0278 | True | 0.9756 | **CONSTRAINT_REFUSED** |
| QB|passing_interceptions | event | knn_quantile | inc_climatology | 0.24589 | 0.03661 | 14.887 | [0.02968, 0.04353] | 8/8 | 0.0 | 0.0 | 0.9998 | 0.7065 | True | 0.9531 | **SHIP** |
| QB|rushing_tds | event | count_negbin | inc_climatology | 0.0746 | 0.00644 | 8.629 | [0.00432, 0.00855] | 8/8 | 0.0001 | 0.0714 | 0.9998 | 1.0634 | True | 0.9703 | **SHIP** |
| RB|carries | count | lgbm_hurdle_tail | inc_head_bank | 2.27926 | 0.26939 | 11.819 | [0.24884, 0.28995] | 8/8 | 0.0 | 0.0 | 0.9796 | 5.4527 | True | 0.8483 | **SHIP** |
| RB|receptions | count | lgbm_hurdle_tail | inc_head_bank | 0.67957 | 0.09182 | 13.512 | [0.08247, 0.10117] | 8/8 | 0.0 | 0.0 | 1.0 | 2.16 | True | 0.9039 | **SHIP** |
| RB|targets | count | lgbm_hurdle_tail | inc_head_bank | 0.81154 | 0.09977 | 12.294 | [0.09082, 0.10872] | 8/8 | 0.0 | 0.0 | 1.0 | 2.7664 | True | 0.8965 | **CONSTRAINT_REFUSED** |
| TE|receiving_tds | event | knn_quantile | inc_climatology | 0.09416 | 0.00655 | 6.956 | [0.00461, 0.00849] | 8/8 | 0.0 | 0.5286 | 1.0 | 0.296 | True | 0.9596 | **POWER_LIMITED** |
| TE|receptions | count | lgbm_hurdle_tail | inc_head_bank | 0.75304 | 0.09375 | 12.449 | [0.08379, 0.10371] | 8/8 | 0.0 | 0.0 | 0.9987 | 2.5182 | True | 0.8886 | **SHIP** |
| TE|targets | count | lgbm_hurdle_tail | inc_head_bank | 0.95166 | 0.11232 | 11.803 | [0.1048, 0.11984] | 8/8 | 0.0 | 0.0 | 1.0 | 3.1391 | True | 0.8869 | **SHIP** |
| WR|receiving_tds | event | knn_quantile | inc_climatology | 0.13454 | 0.01225 | 9.102 | [0.0105, 0.01399] | 8/8 | 0.0 | 0.0 | 1.0 | 0.519 | True | 0.9634 | **SHIP** |
| WR|receptions | count | lgbm_hurdle_tail | inc_head_bank | 0.95146 | 0.09861 | 10.364 | [0.09212, 0.10511] | 8/8 | 0.0 | 0.0 | 0.9999 | 4.7998 | True | 0.8711 | **SHIP** |
| WR|targets | count | lgbm_hurdle_tail | inc_head_bank | 1.31395 | 0.11417 | 8.689 | [0.10537, 0.12297] | 8/8 | 0.0 | 0.0 | 1.0 | 2.8714 | True | 0.8582 | **SHIP** |

## Per-cell detail

### QB|attempts

| label                       |   mean_crps |
|:----------------------------|------------:|
| lgbm_hurdle_tail            |     4.11969 |
| lgbm_quantile_tail          |     4.12363 |
| knn_quantile                |     4.39646 |
| oracle_cand_quantile        |     4.53581 |
| matched_cand_quantile       |     4.73810 |
| oracle_hurdle               |     4.76274 |
| matched_hurdle              |     4.79609 |
| inc_head_bank               |     4.98797 |
| matched_negbin              |     5.92426 |
| oracle_knn                  |     5.93890 |
| matched_knn                 |     6.05993 |
| max_width                   |     6.12029 |
| zero_width                  |     6.12287 |
| count_negbin                |     7.38808 |
| oracle_marginal             |     8.49107 |
| matched_marginal            |     8.50407 |
| inc_climatology             |     8.50961 |
| oracle_negbin               |     8.52675 |
| permuted_lgbm_quantile_tail |     8.87781 |
| nihilist_zero               |    13.04102 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +0.8683 CRPS (CI95 [+0.7888, +0.9478] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": false, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": true, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 8.49107, "matched_crps": 8.50407, "oracle_beats_matched": true}, "cand_quantile": {"oracle_crps": 4.53581, "matched_crps": 4.7381, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 4.76274, "matched_crps": 4.79609, "oracle_beats_matched": true}, "knn": {"oracle_crps": 5.9389, "matched_crps": 6.05993, "oracle_beats_matched": true}, "negbin": {"oracle_crps": 8.52675, "matched_crps": 5.92426, "oracle_beats_matched": false}}
- DSR mechanism: trial SRs [9.35, 9.131, 3.207, -5.466], {"sr0_this_field": 7.3187, "observed_sr": 9.131, "unreachable_in_field": false, "most_dispersing_arm": "count_negbin", "most_dispersing_arm_sr": -5.466, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.8171, "binding_foil_coverage_80": 0.8022, "structural_expectation": 0.954, "n_rows": 5485, "binomial_se": 0.0054, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.54, "winner_pred_p0": 0.5521, "binding_foil_pred_p0": 0.2423, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| 0.0): 0.0
- null state: {"state": "POWER_LIMITED", "reason": "`crps_q199|QB|attempts`: the effect is positive and every gate is REACHABLE, but this design cannot resolve it \u2014 DSR alone needs 27 folds against 8 (the BH-FDR requirement is separate and may be larger). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.", "retest_trigger": "+19 folds for the DSR gate. On field size \u2014 \u26d4 **NOT A REMEDY \u2014 ARITHMETIC ONLY.** The effect clears only in a field of \u22642 arm(s), which is BELOW the declared family of 4. Shrinking a field below what was pre-registered means dropping arms BECAUSE THEY LOST \u2014 the very selection bias DSR exists to deflate, and on MH2.2's `bb_pct` that move bought its whole apparent gain through a 19,938\u00d7 collapse in the cross-trial dispersion `V`, not through honest multiplicity. A smaller field is a legitimate remedy ONLY if that smaller family was itself declared in advance on MECHANISTIC grounds. \u21d2 the \u22642 figure is reported as a DESIGN QUANTITY, never as advice.", "folds_have": 8, "folds_needed": 27, "extra_seasons": 19, "max_field_size": 2, "detail": {"n_folds": 8, "n_arms": 4, "observed_sr": 9.131, "sr0": 7.3189, "var_trials_sr": 48.390448333333325, "degenerates_excluded_from_v": true, "declared_field_size": 4, "declared_field_size_source": "stated", "field_remedy_admissible": false}, "field_remedy_admissible": false, "failing_checks": ["dsr_ok"], "dsr_mechanism": {"sr0_this_field": 7.3187, "observed_sr": 9.131, "unreachable_in_field": false, "most_dispersing_arm": "count_negbin", "most_dispersing_arm_sr": -5.466, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}, "classifier": "cv_power.classify_null (declared_field_size stated \u2014 MH2.7; read field_remedy_admissible, never the prose)"}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": [], "ships_without_waived_checks": true}

### QB|carries

| label                       |   mean_crps |
|:----------------------------|------------:|
| lgbm_hurdle_tail            |     0.81509 |
| lgbm_quantile_tail          |     0.82647 |
| count_negbin                |     0.86836 |
| knn_quantile                |     0.88680 |
| oracle_cand_quantile        |     0.90690 |
| matched_cand_quantile       |     0.91737 |
| matched_hurdle              |     0.93982 |
| oracle_hurdle               |     0.94132 |
| inc_head_bank               |     0.97039 |
| oracle_negbin               |     0.97555 |
| matched_negbin              |     1.03731 |
| oracle_knn                  |     1.05802 |
| matched_knn                 |     1.06840 |
| max_width                   |     1.17030 |
| zero_width                  |     1.17869 |
| oracle_marginal             |     1.25523 |
| matched_marginal            |     1.25860 |
| inc_climatology             |     1.26281 |
| permuted_lgbm_quantile_tail |     1.27006 |
| nihilist_zero               |     1.69921 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +0.1553 CRPS (CI95 [+0.1418, +0.1688] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": false}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": false, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 1.25523, "matched_crps": 1.2586, "oracle_beats_matched": true}, "cand_quantile": {"oracle_crps": 0.9069, "matched_crps": 0.91737, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 0.94132, "matched_crps": 0.93982, "oracle_beats_matched": false}, "knn": {"oracle_crps": 1.05802, "matched_crps": 1.0684, "oracle_beats_matched": true}, "negbin": {"oracle_crps": 0.97555, "matched_crps": 1.03731, "oracle_beats_matched": true}}
- DSR mechanism: trial SRs [9.431, 9.602, 2.536, 4.552], {"sr0_this_field": 3.7305, "observed_sr": 9.602, "unreachable_in_field": false, "most_dispersing_arm": "knn_quantile", "most_dispersing_arm_sr": 2.536, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.8713, "binding_foil_coverage_80": 0.7942, "structural_expectation": 0.9574, "n_rows": 5485, "binomial_se": 0.0054, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.5741, "winner_pred_p0": 0.5837, "binding_foil_pred_p0": 0.2591, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| 0.0): 0.0
- null state: {"state": "CONSTRAINT_REFUSED", "reason": "every statistical gate passed; the null rests on constraint/anchor clauses ['winner_own_form_floor'] \u2014 more data cannot change a directional refusal (NF-D18/NF-W7).", "retest_trigger": null, "failing_checks": ["winner_own_form_floor"], "classifier": "hand (the cv_power CONSTRAINT_REFUSED gap)"}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": ["winner_own_form_floor"], "ships_without_waived_checks": false}

### QB|fumbles_lost

| label                 |   mean_crps |
|:----------------------|------------:|
| knn_quantile          |     0.07684 |
| matched_knn           |     0.07850 |
| oracle_knn            |     0.07854 |
| count_negbin          |     0.07933 |
| lgbm_hurdle_tail      |     0.08028 |
| oracle_marginal       |     0.08094 |
| inc_climatology       |     0.08100 |
| matched_marginal      |     0.08113 |
| permuted_knn_quantile |     0.08144 |
| oracle_negbin         |     0.08200 |
| matched_negbin        |     0.08215 |
| nihilist_zero         |     0.08693 |
| zero_width            |     0.08693 |
| matched_hurdle        |     0.08755 |
| oracle_hurdle         |     0.08851 |
| max_width             |     0.09249 |

- verdict: `knn_quantile` BEATS `inc_climatology` by +0.0042 CRPS (CI95 [+0.0028, +0.0055] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": false}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": false, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 0.08094, "matched_crps": 0.08113, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 0.08851, "matched_crps": 0.08755, "oracle_beats_matched": false}, "knn": {"oracle_crps": 0.07854, "matched_crps": 0.0785, "oracle_beats_matched": false}, "negbin": {"oracle_crps": 0.082, "matched_crps": 0.08215, "oracle_beats_matched": true}}
- DSR mechanism: trial SRs [0.301, 2.616, 0.876], {"sr0_this_field": 1.0278, "observed_sr": 2.616, "unreachable_in_field": false, "most_dispersing_arm": "lgbm_hurdle_tail", "most_dispersing_arm_sr": 0.301, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.9756, "binding_foil_coverage_80": 0.9207, "structural_expectation": 0.9921, "n_rows": 5485, "binomial_se": 0.0054, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.9207, "winner_pred_p0": 0.9231, "binding_foil_pred_p0": 0.9234, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| -2.0): 0.0083
- null state: {"state": "CONSTRAINT_REFUSED", "reason": "every statistical gate passed; the null rests on constraint/anchor clauses ['winner_own_form_floor'] \u2014 more data cannot change a directional refusal (NF-D18/NF-W7).", "retest_trigger": null, "failing_checks": ["winner_own_form_floor"], "classifier": "hand (the cv_power CONSTRAINT_REFUSED gap)"}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": ["winner_own_form_floor"], "ships_without_waived_checks": false}

### QB|passing_interceptions

| label                 |   mean_crps |
|:----------------------|------------:|
| knn_quantile          |     0.20929 |
| count_negbin          |     0.21470 |
| lgbm_hurdle_tail      |     0.22016 |
| oracle_knn            |     0.22378 |
| matched_knn           |     0.22410 |
| oracle_negbin         |     0.22580 |
| matched_negbin        |     0.23045 |
| oracle_marginal       |     0.24568 |
| inc_climatology       |     0.24589 |
| matched_marginal      |     0.24603 |
| permuted_knn_quantile |     0.24739 |
| oracle_hurdle         |     0.26649 |
| matched_hurdle        |     0.27359 |
| nihilist_zero         |     0.29273 |
| zero_width            |     0.29273 |
| max_width             |     0.32259 |

- verdict: `knn_quantile` BEATS `inc_climatology` by +0.0366 CRPS (CI95 [+0.0297, +0.0435] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": true, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 0.24568, "matched_crps": 0.24603, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 0.26649, "matched_crps": 0.27359, "oracle_beats_matched": true}, "knn": {"oracle_crps": 0.22378, "matched_crps": 0.2241, "oracle_beats_matched": true}, "negbin": {"oracle_crps": 0.2258, "matched_crps": 0.23045, "oracle_beats_matched": true}}
- DSR mechanism: trial SRs [2.763, 4.42, 3.577], {"sr0_this_field": 0.7065, "observed_sr": 4.42, "unreachable_in_field": false, "most_dispersing_arm": "lgbm_hurdle_tail", "most_dispersing_arm_sr": 2.763, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.9531, "binding_foil_coverage_80": 0.9333, "structural_expectation": 0.9792, "n_rows": 5485, "binomial_se": 0.0054, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.7916, "winner_pred_p0": 0.7935, "binding_foil_pred_p0": 0.7889, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| -2.0): 0.0732

### QB|rushing_tds

| label                 |   mean_crps |
|:----------------------|------------:|
| count_negbin          |     0.06816 |
| knn_quantile          |     0.06838 |
| lgbm_hurdle_tail      |     0.06952 |
| oracle_negbin         |     0.07106 |
| matched_knn           |     0.07188 |
| oracle_knn            |     0.07216 |
| matched_negbin        |     0.07261 |
| oracle_marginal       |     0.07448 |
| permuted_knn_quantile |     0.07458 |
| inc_climatology       |     0.07460 |
| matched_marginal      |     0.07462 |
| matched_hurdle        |     0.07623 |
| oracle_hurdle         |     0.07740 |
| nihilist_zero         |     0.07877 |
| zero_width            |     0.07877 |
| max_width             |     0.08042 |

- verdict: `count_negbin` BEATS `inc_climatology` by +0.0064 CRPS (CI95 [+0.0043, +0.0086] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": true, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 0.07448, "matched_crps": 0.07462, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 0.0774, "matched_crps": 0.07623, "oracle_beats_matched": false}, "knn": {"oracle_crps": 0.07216, "matched_crps": 0.07188, "oracle_beats_matched": false}, "negbin": {"oracle_crps": 0.07106, "matched_crps": 0.07261, "oracle_beats_matched": true}}
- DSR mechanism: trial SRs [1.895, 4.304, 2.541], {"sr0_this_field": 1.0634, "observed_sr": 2.541, "unreachable_in_field": false, "most_dispersing_arm": "lgbm_hurdle_tail", "most_dispersing_arm_sr": 1.895, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.9703, "binding_foil_coverage_80": 0.9329, "structural_expectation": 0.9933, "n_rows": 5485, "binomial_se": 0.0054, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.9329, "winner_pred_p0": 0.939, "binding_foil_pred_p0": 0.9435, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| 6.0): 0.0386

### RB|carries

| label                       |   mean_crps |
|:----------------------------|------------:|
| lgbm_hurdle_tail            |     2.00987 |
| lgbm_quantile_tail          |     2.02813 |
| oracle_cand_quantile        |     2.14571 |
| knn_quantile                |     2.15938 |
| matched_cand_quantile       |     2.18044 |
| oracle_hurdle               |     2.19322 |
| matched_hurdle              |     2.23341 |
| inc_head_bank               |     2.27926 |
| count_negbin                |     2.29942 |
| matched_negbin              |     2.39209 |
| oracle_negbin               |     2.41257 |
| oracle_knn                  |     2.51023 |
| matched_knn                 |     2.62749 |
| zero_width                  |     2.88393 |
| max_width                   |     2.93974 |
| oracle_marginal             |     3.55479 |
| matched_marginal            |     3.55820 |
| inc_climatology             |     3.56436 |
| permuted_lgbm_quantile_tail |     3.56645 |
| nihilist_zero               |     5.50654 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +0.2694 CRPS (CI95 [+0.2488, +0.2899] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": true, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 3.55479, "matched_crps": 3.5582, "oracle_beats_matched": true}, "cand_quantile": {"oracle_crps": 2.14571, "matched_crps": 2.18044, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 2.19322, "matched_crps": 2.23341, "oracle_beats_matched": true}, "knn": {"oracle_crps": 2.51023, "matched_crps": 2.62749, "oracle_beats_matched": true}, "negbin": {"oracle_crps": 2.41257, "matched_crps": 2.39209, "oracle_beats_matched": false}}
- DSR mechanism: trial SRs [9.078, 10.957, 4.704, -0.697], {"sr0_this_field": 5.4527, "observed_sr": 10.957, "unreachable_in_field": false, "most_dispersing_arm": "count_negbin", "most_dispersing_arm_sr": -0.697, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.8483, "binding_foil_coverage_80": 0.8135, "structural_expectation": 0.939, "n_rows": 8591, "binomial_se": 0.0043, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.3898, "winner_pred_p0": 0.406, "binding_foil_pred_p0": 0.2126, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| 0.0): 0.0

### RB|receptions

| label                       |   mean_crps |
|:----------------------------|------------:|
| lgbm_hurdle_tail            |     0.58775 |
| count_negbin                |     0.59338 |
| lgbm_quantile_tail          |     0.59462 |
| knn_quantile                |     0.60470 |
| oracle_cand_quantile        |     0.62962 |
| oracle_negbin               |     0.63122 |
| matched_cand_quantile       |     0.63607 |
| matched_negbin              |     0.65136 |
| oracle_hurdle               |     0.65137 |
| oracle_knn                  |     0.65358 |
| matched_hurdle              |     0.65673 |
| matched_knn                 |     0.66459 |
| inc_head_bank               |     0.67957 |
| oracle_marginal             |     0.79557 |
| matched_marginal            |     0.79656 |
| inc_climatology             |     0.79685 |
| permuted_lgbm_quantile_tail |     0.81266 |
| zero_width                  |     0.86475 |
| max_width                   |     0.88884 |
| nihilist_zero               |     1.13619 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +0.0918 CRPS (CI95 [+0.0825, +0.1012] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": true, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 0.79557, "matched_crps": 0.79656, "oracle_beats_matched": true}, "cand_quantile": {"oracle_crps": 0.62962, "matched_crps": 0.63607, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 0.65137, "matched_crps": 0.65673, "oracle_beats_matched": true}, "knn": {"oracle_crps": 0.65358, "matched_crps": 0.66459, "oracle_beats_matched": true}, "negbin": {"oracle_crps": 0.63122, "matched_crps": 0.65136, "oracle_beats_matched": true}}
- DSR mechanism: trial SRs [7.864, 8.211, 6.212, 11.146], {"sr0_this_field": 2.16, "observed_sr": 8.211, "unreachable_in_field": false, "most_dispersing_arm": "knn_quantile", "most_dispersing_arm_sr": 6.212, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.9039, "binding_foil_coverage_80": 0.8154, "structural_expectation": 0.9536, "n_rows": 8591, "binomial_se": 0.0043, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.5364, "winner_pred_p0": 0.5341, "binding_foil_pred_p0": 0.2539, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| 1.0): 0.0918

### RB|targets

| label                       |   mean_crps |
|:----------------------------|------------:|
| lgbm_hurdle_tail            |     0.71177 |
| lgbm_quantile_tail          |     0.71941 |
| count_negbin                |     0.71948 |
| knn_quantile                |     0.73406 |
| oracle_cand_quantile        |     0.76572 |
| matched_cand_quantile       |     0.77074 |
| oracle_negbin               |     0.77342 |
| matched_hurdle              |     0.79019 |
| oracle_hurdle               |     0.79083 |
| oracle_knn                  |     0.79932 |
| matched_negbin              |     0.80126 |
| inc_head_bank               |     0.81154 |
| matched_knn                 |     0.81529 |
| oracle_marginal             |     0.99021 |
| matched_marginal            |     0.99172 |
| inc_climatology             |     0.99252 |
| permuted_lgbm_quantile_tail |     1.00867 |
| zero_width                  |     1.03840 |
| max_width                   |     1.06718 |
| nihilist_zero               |     1.45732 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +0.0998 CRPS (CI95 [+0.0908, +0.1087] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": false}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": false, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 0.99021, "matched_crps": 0.99172, "oracle_beats_matched": true}, "cand_quantile": {"oracle_crps": 0.76572, "matched_crps": 0.77074, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 0.79083, "matched_crps": 0.79019, "oracle_beats_matched": false}, "knn": {"oracle_crps": 0.79932, "matched_crps": 0.81529, "oracle_beats_matched": true}, "negbin": {"oracle_crps": 0.77342, "matched_crps": 0.80126, "oracle_beats_matched": true}}
- DSR mechanism: trial SRs [9.546, 9.32, 6.337, 12.772], {"sr0_this_field": 2.7664, "observed_sr": 9.32, "unreachable_in_field": false, "most_dispersing_arm": "knn_quantile", "most_dispersing_arm_sr": 6.337, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.8965, "binding_foil_coverage_80": 0.8141, "structural_expectation": 0.949, "n_rows": 8591, "binomial_se": 0.0043, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.4898, "winner_pred_p0": 0.4806, "binding_foil_pred_p0": 0.2452, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| 0.0): 0.0
- null state: {"state": "CONSTRAINT_REFUSED", "reason": "every statistical gate passed; the null rests on constraint/anchor clauses ['winner_own_form_floor'] \u2014 more data cannot change a directional refusal (NF-D18/NF-W7).", "retest_trigger": null, "failing_checks": ["winner_own_form_floor"], "classifier": "hand (the cv_power CONSTRAINT_REFUSED gap)"}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": ["winner_own_form_floor"], "ships_without_waived_checks": false}

### TE|receiving_tds

| label                 |   mean_crps |
|:----------------------|------------:|
| knn_quantile          |     0.08761 |
| count_negbin          |     0.08781 |
| lgbm_hurdle_tail      |     0.08795 |
| oracle_knn            |     0.09003 |
| matched_knn           |     0.09052 |
| oracle_negbin         |     0.09341 |
| oracle_marginal       |     0.09387 |
| inc_climatology       |     0.09416 |
| permuted_knn_quantile |     0.09425 |
| matched_marginal      |     0.09426 |
| matched_negbin        |     0.09447 |
| matched_hurdle        |     0.09884 |
| oracle_hurdle         |     0.09932 |
| nihilist_zero         |     0.10182 |
| zero_width            |     0.10182 |
| max_width             |     0.11251 |

- verdict: `knn_quantile` BEATS `inc_climatology` by +0.0066 CRPS (CI95 [+0.0046, +0.0085] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": false, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": true, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 0.09387, "matched_crps": 0.09426, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 0.09932, "matched_crps": 0.09884, "oracle_beats_matched": false}, "knn": {"oracle_crps": 0.09003, "matched_crps": 0.09052, "oracle_beats_matched": true}, "negbin": {"oracle_crps": 0.09341, "matched_crps": 0.09447, "oracle_beats_matched": true}}
- DSR mechanism: trial SRs [2.133, 2.82, 2.392], {"sr0_this_field": 0.296, "observed_sr": 2.82, "unreachable_in_field": false, "most_dispersing_arm": "lgbm_hurdle_tail", "most_dispersing_arm_sr": 2.133, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.9596, "binding_foil_coverage_80": 0.9464, "structural_expectation": 0.991, "n_rows": 7649, "binomial_se": 0.0046, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.9098, "winner_pred_p0": 0.9064, "binding_foil_pred_p0": 0.902, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| 6.0): 0.0393
- null state: {"state": "POWER_LIMITED", "reason": "`crps_q199|TE|receiving_tds`: insufficient recorded statistics to certify the null as powered. Absent a detectability figure the honest default is POWER-LIMITED \u2014 a null is trustworthy only when something was computed to make it so.", "retest_trigger": null, "folds_have": 8, "folds_needed": null, "extra_seasons": null, "max_field_size": null, "detail": {"n_folds": 8, "n_arms": 3, "observed_sr": 2.82, "sr0": 0.2959, "var_trials_sr": 0.12037233333333328, "degenerates_excluded_from_v": true, "declared_field_size": 3, "declared_field_size_source": "stated", "field_remedy_admissible": true, "sign_floor": 0.00390625, "bh_cutoff": 0.1}, "field_remedy_admissible": null, "failing_checks": ["pbo_ok"], "dsr_mechanism": {"sr0_this_field": 0.296, "observed_sr": 2.82, "unreachable_in_field": false, "most_dispersing_arm": "lgbm_hurdle_tail", "most_dispersing_arm_sr": 2.133, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}, "classifier": "cv_power.classify_null (declared_field_size stated \u2014 MH2.7; read field_remedy_admissible, never the prose)"}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": ["pbo_ok"], "ships_without_waived_checks": false}

### TE|receptions

| label                       |   mean_crps |
|:----------------------------|------------:|
| lgbm_hurdle_tail            |     0.65929 |
| count_negbin                |     0.66427 |
| lgbm_quantile_tail          |     0.66797 |
| knn_quantile                |     0.68123 |
| oracle_cand_quantile        |     0.69903 |
| oracle_negbin               |     0.70485 |
| oracle_hurdle               |     0.71533 |
| matched_cand_quantile       |     0.71633 |
| matched_hurdle              |     0.73137 |
| matched_negbin              |     0.73309 |
| inc_head_bank               |     0.75304 |
| oracle_knn                  |     0.77800 |
| matched_knn                 |     0.80140 |
| max_width                   |     0.95662 |
| zero_width                  |     0.95749 |
| oracle_marginal             |     0.97040 |
| inc_climatology             |     0.97154 |
| matched_marginal            |     0.97221 |
| permuted_lgbm_quantile_tail |     0.98189 |
| nihilist_zero               |     1.41130 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +0.0938 CRPS (CI95 [+0.0838, +0.1037] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": true, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 0.9704, "matched_crps": 0.97221, "oracle_beats_matched": true}, "cand_quantile": {"oracle_crps": 0.69903, "matched_crps": 0.71633, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 0.71533, "matched_crps": 0.73137, "oracle_beats_matched": true}, "knn": {"oracle_crps": 0.778, "matched_crps": 0.8014, "oracle_beats_matched": true}, "negbin": {"oracle_crps": 0.70485, "matched_crps": 0.73309, "oracle_beats_matched": true}}
- DSR mechanism: trial SRs [6.852, 7.87, 4.922, 10.663], {"sr0_this_field": 2.5182, "observed_sr": 7.87, "unreachable_in_field": false, "most_dispersing_arm": "knn_quantile", "most_dispersing_arm_sr": 4.922, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.8886, "binding_foil_coverage_80": 0.7981, "structural_expectation": 0.9495, "n_rows": 7649, "binomial_se": 0.0046, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.4946, "winner_pred_p0": 0.496, "binding_foil_pred_p0": 0.2284, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| 1.0): 0.0937

### TE|targets

| label                       |   mean_crps |
|:----------------------------|------------:|
| lgbm_hurdle_tail            |     0.83934 |
| lgbm_quantile_tail          |     0.84775 |
| count_negbin                |     0.85378 |
| knn_quantile                |     0.87583 |
| oracle_cand_quantile        |     0.89088 |
| oracle_negbin               |     0.90592 |
| oracle_hurdle               |     0.90806 |
| matched_cand_quantile       |     0.91056 |
| matched_hurdle              |     0.92832 |
| inc_head_bank               |     0.95166 |
| matched_negbin              |     0.95228 |
| oracle_knn                  |     1.03193 |
| matched_knn                 |     1.06325 |
| max_width                   |     1.21070 |
| zero_width                  |     1.21133 |
| oracle_marginal             |     1.31662 |
| inc_climatology             |     1.31859 |
| matched_marginal            |     1.31991 |
| permuted_lgbm_quantile_tail |     1.32796 |
| nihilist_zero               |     1.98109 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +0.1123 CRPS (CI95 [+0.1048, +0.1198] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": true, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 1.31662, "matched_crps": 1.31991, "oracle_beats_matched": true}, "cand_quantile": {"oracle_crps": 0.89088, "matched_crps": 0.91056, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 0.90806, "matched_crps": 0.92832, "oracle_beats_matched": true}, "knn": {"oracle_crps": 1.03193, "matched_crps": 1.06325, "oracle_beats_matched": true}, "negbin": {"oracle_crps": 0.90592, "matched_crps": 0.95228, "oracle_beats_matched": true}}
- DSR mechanism: trial SRs [14.42, 12.484, 7.671, 9.68], {"sr0_this_field": 3.1391, "observed_sr": 12.484, "unreachable_in_field": false, "most_dispersing_arm": "knn_quantile", "most_dispersing_arm_sr": 7.671, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.8869, "binding_foil_coverage_80": 0.7974, "structural_expectation": 0.9432, "n_rows": 7649, "binomial_se": 0.0046, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.4318, "winner_pred_p0": 0.4262, "binding_foil_pred_p0": 0.2197, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| 0.0): 0.0

### WR|receiving_tds

| label                 |   mean_crps |
|:----------------------|------------:|
| knn_quantile          |     0.12230 |
| oracle_knn            |     0.12407 |
| count_negbin          |     0.12428 |
| lgbm_hurdle_tail      |     0.12480 |
| matched_knn           |     0.12494 |
| oracle_negbin         |     0.13199 |
| matched_negbin        |     0.13313 |
| oracle_marginal       |     0.13439 |
| matched_marginal      |     0.13451 |
| inc_climatology       |     0.13454 |
| permuted_knn_quantile |     0.13510 |
| matched_hurdle        |     0.14371 |
| oracle_hurdle         |     0.14505 |
| nihilist_zero         |     0.15183 |
| zero_width            |     0.15183 |
| max_width             |     0.16955 |

- verdict: `knn_quantile` BEATS `inc_climatology` by +0.0123 CRPS (CI95 [+0.0105, +0.0140] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": true, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 0.13439, "matched_crps": 0.13451, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 0.14505, "matched_crps": 0.14371, "oracle_beats_matched": false}, "knn": {"oracle_crps": 0.12407, "matched_crps": 0.12494, "oracle_beats_matched": true}, "negbin": {"oracle_crps": 0.13199, "matched_crps": 0.13313, "oracle_beats_matched": true}}
- DSR mechanism: trial SRs [4.997, 5.868, 4.696], {"sr0_this_field": 0.519, "observed_sr": 5.868, "unreachable_in_field": false, "most_dispersing_arm": "count_negbin", "most_dispersing_arm_sr": 4.696, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.9634, "binding_foil_coverage_80": 0.9828, "structural_expectation": 0.9867, "n_rows": 12827, "binomial_se": 0.0035, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.867, "winner_pred_p0": 0.8646, "binding_foil_pred_p0": 0.8625, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| 6.0): 0.0735

### WR|receptions

| label                       |   mean_crps |
|:----------------------------|------------:|
| lgbm_hurdle_tail            |     0.85285 |
| lgbm_quantile_tail          |     0.85860 |
| count_negbin                |     0.86347 |
| knn_quantile                |     0.87522 |
| oracle_cand_quantile        |     0.90354 |
| oracle_negbin               |     0.90804 |
| oracle_hurdle               |     0.92540 |
| oracle_knn                  |     0.93134 |
| matched_cand_quantile       |     0.93628 |
| inc_head_bank               |     0.95146 |
| matched_hurdle              |     0.95251 |
| matched_negbin              |     0.95261 |
| matched_knn                 |     0.96439 |
| zero_width                  |     1.22909 |
| max_width                   |     1.25285 |
| oracle_marginal             |     1.26123 |
| matched_marginal            |     1.26369 |
| inc_climatology             |     1.26409 |
| permuted_lgbm_quantile_tail |     1.27978 |
| nihilist_zero               |     1.99664 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +0.0986 CRPS (CI95 [+0.0921, +0.1051] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": true, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 1.26123, "matched_crps": 1.26369, "oracle_beats_matched": true}, "cand_quantile": {"oracle_crps": 0.90354, "matched_crps": 0.93628, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 0.9254, "matched_crps": 0.95251, "oracle_beats_matched": true}, "knn": {"oracle_crps": 0.93134, "matched_crps": 0.96439, "oracle_beats_matched": true}, "negbin": {"oracle_crps": 0.90804, "matched_crps": 0.95261, "oracle_beats_matched": true}}
- DSR mechanism: trial SRs [9.625, 12.689, 5.518, 16.258], {"sr0_this_field": 4.7998, "observed_sr": 12.689, "unreachable_in_field": false, "most_dispersing_arm": "knn_quantile", "most_dispersing_arm_sr": 5.518, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.8711, "binding_foil_coverage_80": 0.8053, "structural_expectation": 0.9409, "n_rows": 12827, "binomial_se": 0.0035, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.4091, "winner_pred_p0": 0.4023, "binding_foil_pred_p0": 0.2059, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| 1.0): 0.0986

### WR|targets

| label                       |   mean_crps |
|:----------------------------|------------:|
| lgbm_hurdle_tail            |     1.19978 |
| lgbm_quantile_tail          |     1.20444 |
| count_negbin                |     1.23667 |
| knn_quantile                |     1.24056 |
| oracle_cand_quantile        |     1.26800 |
| oracle_hurdle               |     1.29679 |
| oracle_negbin               |     1.30254 |
| inc_head_bank               |     1.31395 |
| matched_cand_quantile       |     1.31494 |
| matched_hurdle              |     1.33330 |
| oracle_knn                  |     1.33621 |
| matched_negbin              |     1.36197 |
| matched_knn                 |     1.39059 |
| zero_width                  |     1.70907 |
| max_width                   |     1.74853 |
| oracle_marginal             |     1.88992 |
| matched_marginal            |     1.89286 |
| inc_climatology             |     1.89546 |
| permuted_lgbm_quantile_tail |     1.91429 |
| nihilist_zero               |     3.16579 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +0.1142 CRPS (CI95 [+0.1054, +0.1230] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true, "not_a_foil_tie": true, "winner_own_form_floor": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_own_form_oracle_beats_matched": true, "winner_beats_own_form_oracle": true}
- per-form oracle/matched pairs: {"marginal": {"oracle_crps": 1.88992, "matched_crps": 1.89286, "oracle_beats_matched": true}, "cand_quantile": {"oracle_crps": 1.268, "matched_crps": 1.31494, "oracle_beats_matched": true}, "hurdle": {"oracle_crps": 1.29679, "matched_crps": 1.3333, "oracle_beats_matched": true}, "knn": {"oracle_crps": 1.33621, "matched_crps": 1.39059, "oracle_beats_matched": true}, "negbin": {"oracle_crps": 1.30254, "matched_crps": 1.36197, "oracle_beats_matched": true}}
- DSR mechanism: trial SRs [7.81, 10.844, 4.658, 5.702], {"sr0_this_field": 2.8714, "observed_sr": 10.844, "unreachable_in_field": false, "most_dispersing_arm": "knn_quantile", "most_dispersing_arm_sr": 4.658, "reading": "if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, not a sample-size one \u2014 more folds scale a positive gap but cannot create one; the admissible remedy is a fresh coherent registration, never a post-hoc trim (MH2.2)."}
- coverage: {"winner_coverage_80": 0.8582, "binding_foil_coverage_80": 0.8036, "structural_expectation": 0.934, "n_rows": 12827, "binomial_se": 0.0035, "blocking_shortfall": false} (one-sided floor — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.3398, "winner_pred_p0": 0.3331, "binding_foil_pred_p0": 0.1838, "note": "REPORT-ONLY \u2014 the mechanism made visible, never a criterion."}
- PPR points-units (report-only, |weight| 0.0): 0.0

## Pre-registration

- families: {'count': ['lgbm_quantile_tail', 'lgbm_hurdle_tail', 'knn_quantile', 'count_negbin'], 'event': ['lgbm_hurdle_tail', 'knn_quantile', 'count_negbin']}; foils: {'count': ['inc_head_bank', 'inc_climatology'], 'event': ['inc_climatology']}; permuted form: {'count': 'lgbm_quantile_tail', 'event': 'knn_quantile'}; banned on EVENT: ['enet_residual', 'inc_head_bank', 'lgbm_quantile_tail']; declared field sizes: {'count': 4, 'event': 3}.
- gates: the W6b-C ten clauses; PBO<0.2; DSR≥0.95 (DSR-CONV forward: anchors never enter trials); BH q=0.1 two families (count/event) own AND pooled; coverage floor one-sided; tie eps 0.0001.
- cell list READ from the Phase-A record (Phase-A record nf_w6d_ceiling_gate.json licensed_cells); reproduction control on 7 served cells, byte-identical or INVALID.

_Runtime: 13132.0s · seed 20260817 · matrix key 26c34fbe778c9d87_