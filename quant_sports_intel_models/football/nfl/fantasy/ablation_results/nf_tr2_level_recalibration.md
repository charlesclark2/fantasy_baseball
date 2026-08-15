# NF-TR2 — season-projection LEVEL recalibration (draft-board credibility) · full-history mean-match
_generated 2026-08-15T21:49:32.031574+00:00_ · `best_alpha = 0` · model `nfl_fantasy_nf_tr2_veteran_level_v1` · recalibrates `nfl_fantasy_fastpath_v1` · wall 22.3s
## Verdict: **RECORDED NULL — CONSTRAINT_REFUSED**
Winner `pos_const · λ=1 · mean-match` · tier CRPS **49.4173** vs incumbent 49.9214 · pooled tier bias 7.881152519454248 vs -12.850295382832726 · PBO(elig) 0.0 · DSR(declared 3-trial field) **0.9911** · DSR under NF-B3's field 0.9744 · p 0.0014

## 0. Pre-registration + provenance
- Declared field: **3 trials** — NF-TR2 brief (2026-08-15): "Pre-register the recalibration forms against matched foils, selected in-fold: per-position constant vs per-position affine (slope) vs a no-op foil."
- Forms `['pos_const', 'pos_affine']` + no-op · estimator `mean_match` · λ fixed 1.0 · band treatment PRIMARY `fixed` (disclosed: ['fixed', 'refit', 'scaled']) · space `per_game` · tier top 156/season by the INCUMBENT anchor · folds 2013–2025
- Served band held through the model path: universe IS80 160.888 (Δ 0.0%), tier cov 2019–25 0.8452. Structurally rookie-less boards: [2013, 2014, 2015].

## 1. Decomposition — availability vs per-game rate (tier, pooled over the 13 folds)
| position | n | bias | availability_part | rate_part | our_over_actual | games_ratio | rate_ratio_pooled | mean_match_k | zero_outcome_frac |
|---|---|---|---|---|---|---|---|---|---|
| QB | 465 | -0.5650 | -1.5220 | 0.9570 | 0.9970 | 1.0120 | 0.9850 | 1.0030 | 0.0750 |
| RB | 490 | -21.5390 | -1.1350 | -20.4040 | 0.8590 | 0.9940 | 0.8640 | 1.1640 | 0.0590 |
| TE | 251 | -9.0540 | 12.3610 | -21.4150 | 0.9300 | 1.1110 | 0.8370 | 1.0750 | 0.0640 |
| WR | 822 | -15.7800 | 6.9770 | -22.7570 | 0.8970 | 1.0590 | 0.8480 | 1.1140 | 0.0770 |
| POOLED | 2028 | -12.8500 | 3.7340 | -16.5850 | 0.9190 | 1.0400 | 0.8830 | 1.0890 | 0.0710 |

identity holds: True · the miss is the RATE: **True** (availability +3.73 vs rate -16.58). Universe pooled bias +0.84.
Premise (NF-RECAL1's reading, reproduced): tier bias -12.85 (n 2028), universe 0.84 — premise confirmed: True.

## 2. The field + disclosures
| arm | treatment | trial | eligible | CRPS | MAE | bias (pooled rows) | bias_QB | bias_RB | bias_WR | bias_TE | cov80 | universe CRPS | universe bias |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pos_affine · λ=1 · OLS [refit band DISCLOSURE] | refit | False | False | 49.2818 | 70.7043 | 5.4572 | 10.4941 | -4.7865 | 6.8503 | 11.5613 | 0.8328 | 30.1005 | 9.4163 |
| pos_affine · λ=1 · OLS | fixed | True | False | 49.3354 | 70.7043 | 5.4572 | 10.4941 | -4.7865 | 6.8503 | 11.5613 | 0.8348 | 29.9256 | 9.4163 |
| pos_const · λ=1 · mean-match | fixed | True | True | 49.4173 | 70.8832 | 7.8812 | 12.6152 | -4.2460 | 10.6464 | 13.7296 | 0.8348 | 29.9898 | 10.5143 |
| pos_const · λ=1 · mean-match [refit band DISCLOSURE] | refit | False | False | 49.4340 | 70.8832 | 7.8812 | 12.6152 | -4.2460 | 10.6464 | 13.7296 | 0.8235 | 30.0413 | 10.5143 |
| incumbent (NULL) | served | True | True | 49.9214 | 71.7011 | -12.8503 | -0.5654 | -21.5386 | -15.7798 | -9.0540 | 0.8333 | 29.3817 | 0.8286 |
| pos_const · λ=1 · mean-match [scaled band DISCLOSURE] | scaled | False | False | 50.1813 | 70.8832 | 7.8812 | 12.6152 | -4.2460 | 10.6464 | 13.7296 | 0.8974 | 30.6037 | 10.5143 |
| pos_affine · λ=1 · OLS [scaled band DISCLOSURE] | scaled | False | False | 50.3517 | 70.7043 | 5.4572 | 10.4941 | -4.7865 | 6.8503 | 11.5613 | 0.8817 | 31.1724 | 9.4163 |

Fitted params (final fold 2025): `{'pos_const': '{"QB": 1.0314802526145428, "RB": 1.1497320506124653, "TE": 1.1223898016551492, "WR": 1.159457482661065}', 'pos_affine': '{"QB": [-2.2547103543634055, 1.144284404171156], "RB": [-1.7822454809031953, 1.3076886200072972], "TE": [0.5210901791879506, 1.0461916731678997], "WR": [0.2538561256583392, 1.121342600564867]}'}`

### Anchors (two-sided, scored every run, PRIMARY treatment; ceilings under the FIXED band)
| anchor | role | expected | CRPS | MAE | bias | cov80 | behaves as expected |
|---|---|---|---|---|---|---|---|
| oracle_perplayer | ceiling | beats every real arm | 0.0043 | 0.0043 | 0.0043 | 0.9951 | True |
| zero_project | degenerate | loses to every real arm | 157.9249 | 157.9249 | -157.9163 | 0.0705 | True |
| pos_median | degenerate | loses to every real arm | 81.9364 | 81.9364 | -2.7007 | 0.0000 | True |
| wide_band | degenerate | loses to every real arm | 63.3477 | 71.7011 | -12.8503 | 0.9916 | True |
| permuted_across@pos_const | permutation | loses to every real arm | 49.5638 | 71.5331 | 7.0435 | 0.8358 | True |
| permuted_within@pos_const | permutation | loses to every real arm | 49.4173 | 70.8832 | 7.8812 | 0.8348 | True |
| permuted_across@pos_affine | permutation | loses to every real arm | 54.0266 | 83.3639 | -12.3605 | 0.8338 | True |
| permuted_within@pos_affine | permutation | loses to every real arm | 53.6426 | 82.0080 | -12.3540 | 0.8333 | True |
| over_scale | degenerate | loses to every real arm | 50.4131 | 75.0389 | 28.6126 | 0.8388 | True |
| lambda_sweep@0.25 | degenerate | loses to every real arm | 49.6613 | 71.0600 | -7.6674 | 0.8333 | True |
| lambda_sweep@0.5 | degenerate | loses to every real arm | 49.4830 | 70.7138 | -2.4846 | 0.8333 | True |
| lambda_sweep@0.75 | degenerate | loses to every real arm | 49.4002 | 70.6646 | 2.6983 | 0.8343 | True |
| lambda_sweep@1.25 | degenerate | loses to every real arm | 49.5272 | 71.4396 | 13.0640 | 0.8353 | True |
| lambda_sweep@1.5 | degenerate | loses to every real arm | 49.7307 | 72.2929 | 18.2469 | 0.8358 | True |
| lambda_sweep@2 | degenerate | loses to every real arm | 50.4131 | 75.0389 | 28.6126 | 0.8388 | True |
| window_sensitivity@w3 | degenerate | loses to every real arm | 49.4114 | 70.5991 | -0.0556 | 0.8333 | True |
| window_sensitivity@w8 | degenerate | loses to every real arm | 49.4229 | 70.7580 | 3.8555 | 0.8343 | True |
| window_sensitivity@wNone | degenerate | loses to every real arm | 49.4173 | 70.8832 | 7.8812 | 0.8348 | True |
| oracle_pos_const | ceiling | beats every real arm | 48.8642 | 69.7650 | 4.1225 | 0.8358 | True |
| oracle_pos_affine | ceiling | beats every real arm | 47.8106 | 68.3228 | 0.1508 | 0.8378 | True |

Family ceiling (matched FIXED-band treatment): {'pos_const': True, 'pos_affine': True} · ceilings order by capacity: True · {'pos_const': {'ceiling_crps': 48.8642, 'arm_crps_fixed_band': 49.4173}, 'pos_affine': {'ceiling_crps': 47.8106, 'arm_crps_fixed_band': 49.3354}}

### λ-sweep of the mean-match (the interior-optimum question, MEASURED — anchors, never selected on)
| treatment | λ | CRPS | bias | cov80 | MAE |
|---|---|---|---|---|---|
| fixed | 0.0000 | 49.9214 | -12.8503 | 0.8333 | 71.7011 |
| fixed | 0.2500 | 49.6613 | -7.6674 | 0.8333 | 71.0600 |
| fixed | 0.5000 | 49.4830 | -2.4846 | 0.8333 | 70.7138 |
| fixed | 0.7500 | 49.4002 | 2.6983 | 0.8343 | 70.6646 |
| fixed | 1.0000 | 49.4173 | 7.8812 | 0.8348 | 70.8832 |
| fixed | 1.2500 | 49.5272 | 13.0640 | 0.8353 | 71.4396 |
| fixed | 1.5000 | 49.7307 | 18.2469 | 0.8358 | 72.2929 |
| fixed | 2.0000 | 50.4131 | 28.6126 | 0.8388 | 75.0389 |
| refit | 0.0000 | 49.9214 | -12.8503 | 0.8333 | 71.7011 |
| refit | 0.2500 | 49.6324 | -7.6674 | 0.8329 | 71.0600 |
| refit | 0.5000 | 49.4584 | -2.4846 | 0.8284 | 70.7138 |
| refit | 0.7500 | 49.3951 | 2.6983 | 0.8274 | 70.6646 |
| refit | 1.0000 | 49.4340 | 7.8812 | 0.8235 | 70.8832 |
| refit | 1.2500 | 49.5599 | 13.0640 | 0.8264 | 71.4396 |
| refit | 1.5000 | 49.7396 | 18.2469 | 0.8235 | 72.2929 |
| refit | 2.0000 | 50.4793 | 28.6126 | 0.8215 | 75.0389 |
| scaled | 0.0000 | 49.9214 | -12.8503 | 0.8333 | 71.7011 |
| scaled | 0.2500 | 49.6152 | -7.6674 | 0.8516 | 71.0600 |
| scaled | 0.5000 | 49.5676 | -2.4846 | 0.8698 | 70.7138 |
| scaled | 0.7500 | 49.7625 | 2.6983 | 0.8841 | 70.6646 |
| scaled | 1.0000 | 50.1813 | 7.8812 | 0.8974 | 70.8832 |
| scaled | 1.2500 | 50.8063 | 13.0640 | 0.9024 | 71.4396 |
| scaled | 1.5000 | 51.6214 | 18.2469 | 0.9088 | 72.2929 |
| scaled | 2.0000 | 53.7602 | 28.6126 | 0.9122 | 75.0389 |

### Window sensitivity (anchors, never trials) — the registered window is DERIVED, not tuned
derivation: `{'tier_rows_per_position_per_season': {'QB': 35.77, 'RB': 37.69, 'TE': 19.31, 'WR': 63.23}, 'min_rows': 90, 'derived_window': 5, 'pinned_window': 5}`
| window | is_registered | CRPS | bias | bias_QB | bias_RB | bias_WR | bias_TE | cov80 | MAE |
|---|---|---|---|---|---|---|---|---|---|
| 3 | False | 49.4114 | -0.0556 | 4.8677 | -4.8406 | -0.2699 | 0.8663 | 0.8333 | 70.5991 |
| 8 | False | 49.4229 | 3.8555 | 10.1591 | -5.4608 | 4.7756 | 7.3518 | 0.8343 | 70.7580 |
| full history | True | 49.4173 | 7.8812 | 12.6152 | -4.2460 | 10.6464 | 13.7296 | 0.8348 | 70.8832 |
| full history | True | 49.4173 | 7.8812 | 12.6152 | -4.2460 | 10.6464 | 13.7296 | 0.8348 | 70.8832 |

## 3. Constraints (out-of-sample, every fold)
| arm | holds out (C1∧C2∧C3) | C1 only | C2 only | C3 only | failing folds | C2 active folds | C2 structurally absent |
|---|---|---|---|---|---|---|---|
| incumbent (NULL) | True | True | True | True | [] | None | None |
| pos_const · λ=1 · mean-match | True | True | True | True | [] | [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] | [2013, 2014, 2015] |
| pos_affine · λ=1 · OLS | False | False | True | True | [2013, 2015, 2017] | [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] | [2013, 2014, 2015] |

## 4. Deflation over the DECLARED field
| declared_field_size | n_trial_sharpes | trial_sharpes | sr0_declared_field | dsr_declared_field | b3_field_sr0 | dsr_under_b3_field |
|---|---|---|---|---|---|---|
| 3 | 2 | [1.0414, 1.3284] | 0.1055 | 0.9911 | 0.2710 | 0.9744 |

the SAME winner, the SAME folds: the declared-field DSR is the pre-registered gate; the NF-B3-field DSR is the tax the winner would carry inside NF-B3's 11-arm heterogeneous field. Both are on this page so a narrower family cannot launder a result — whether the brief's 3-trial family is admissible is a fact about the brief (see declared_field_source), not about this run.

NF-B3 recorded: {'story': 'NF-B3', 'winner': 'pos_const · infold λ=0.25', 'dsr_whole_field': 0.8773, 'n_trials_in_field': 8, 'verdict': 'RECORDED NULL — POWER_LIMITED'}

### Gate table (pooled framing)
| ship | framing | has_eligible_winner | recalibrates | beats_incumbent | ordering_ok_every_position | placement_holds_out_every_fold | coverage_floors_hold | pbo_ok | dsr_ok | significant |
|---|---|---|---|---|---|---|---|---|---|---|
| True | pooled | True | True | True | True | True | True | True | True | True |

### Per-position disclosure (computed, never selected on)
```
{
 "per_position": [
  {
   "position": "QB",
   "incumbent_metric": 59.2997,
   "winner": "pos_const \u00b7 \u03bb=1 \u00b7 mean-match",
   "metric": 59.2693,
   "delta": -0.0304,
   "pbo": 0.8829,
   "dsr": 0.3863,
   "pvalue": 0.4441
  },
  {
   "position": "RB",
   "incumbent_metric": 51.7438,
   "winner": "pos_const \u00b7 \u03bb=1 \u00b7 mean-match",
   "metric": 50.9144,
   "delta": -0.8293,
   "pbo": 0.0227,
   "dsr": 0.9888,
   "pvalue": 0.0231
  },
  {
   "position": "WR",
   "incumbent_metric": 47.4356,
   "winner": "pos_const \u00b7 \u03bb=1 \u00b7 mean-match",
   "metric": 46.8278,
   "delta": -0.6078,
   "pbo": 0.014,
   "dsr": 0.9931,
   "pvalue": 0.0189
  },
  {
   "position": "TE",
   "incumbent_metric": 37.4341,
   "winner": "pos_const \u00b7 \u03bb=1 \u00b7 mean-match",
   "metric": 36.7578,
   "delta": -0.6763,
   "pbo": 0.0956,
   "dsr": 0.9023,
   "pvalue": 0.0585
  }
 ],
 "bh_cutoff_unconditional": 0.025,
 "fdr": {
  "QB": false,
  "RB": true,
  "WR": true,
  "TE": true
 }
}
```

## 5. Level gates (L1–L5)
```
{
 "L1_pooled_reduced": false,
 "L1_detail": {
  "incumbent": -12.850295382832726,
  "winner": 7.881152519454248,
  "reduction": 0.3866948358258733
 },
 "L2_per_position": {
  "QB": false,
  "RB": true,
  "WR": false,
  "TE": false
 },
 "L2_all": false,
 "L3_no_inflation": false,
 "L3_detail": {
  "not_significantly_hot": false,
  "over_scale_loses": true,
  "pooled_se": 1.9574161313208067
 },
 "L4_availability_preserved": true,
 "pass": false,
 "se": {
  "QB": 4.871425799779968,
  "RB": 4.068618813320924,
  "WR": 2.862212204740051,
  "TE": 4.026231724009692,
  "pooled": 1.9574161313208067
 }
}
```

L5 rank identity: `{
 "QB": {
  "folds": 13,
  "min_within_position_rho": 0.9999999999999999,
  "delta_rho_identical": true,
  "order_identical": true,
  "max_abs_delta_rho_change": 0.0
 },
 "RB": {
  "folds": 13,
  "min_within_position_rho": 0.9999999999999999,
  "delta_rho_identical": true,
  "order_identical": true,
  "max_abs_delta_rho_change": 0.0
 },
 "WR": {
  "folds": 13,
  "min_within_position_rho": 0.9999999999999998,
  "delta_rho_identical": true,
  "order_identical": true,
  "max_abs_delta_rho_change": 0.0
 },
 "TE": {
  "folds": 13,
  "min_within_position_rho": 0.9999999999999999,
  "delta_rho_identical": true,
  "order_identical": true,
  "max_abs_delta_rho_change": 0.0
 }
}`

## 6. Verdict flags
| ship | level_gate_pass | L5_rank_identity | premise_confirmed | miss_is_rate | sanity_degenerates_lose | oracle_respected | permutation_across_beaten | over_scale_loses | wide_band_loses | family_ceiling_respected_fixed_band | ceilings_order_by_capacity | rookie_leg_untouched |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| False | False | True | True | True | True | True | True | True | True | True | True | True |

### Null classification (declared field)
```
{
 "state": "CONSTRAINT_REFUSED",
 "taxonomy_would_say": "POWER_LIMITED",
 "remedy": null,
 "detail": {
  "n_folds": 13,
  "n_arms": 3,
  "observed_sr": 1.3284,
  "sr0": 0.1731,
  "var_trials_sr": 0.041182890281009084,
  "degenerates_excluded_from_v": null,
  "declared_field_size": 3,
  "declared_field_size_source": "stated",
  "field_remedy_admissible": true
 },
 "field_remedy_admissible": true,
 "refused_by_constraint": true,
 "refused_by_level_gate": true,
 "best_arm": "pos_affine \u00b7 \u03bb=1 \u00b7 OLS",
 "observed_sr": 1.3283597658938822
}
```

## 7. Serving — the fit that would ship + the before/after board diff
form `pos_const` · params 2026 `{'QB': 1.024678076887253, 'RB': 1.1549603674393962, 'WR': 1.1548691370421966, 'TE': 1.127698202419321}` · panel target seasons < 2026, trailing window None (tier top 156/season)
refit-vs-fixed band agreement (winner): {'crps_refit': 49.4173, 'crps_fixed': 49.4173, 'cov80_refit': 0.8348, 'cov80_fixed': 0.8348, 'cov80_incumbent': 0.8333, 'band_fallback_rows_frac': 0.0}

**fastpath 2026 (nfl_fantasy_season_projections_2026)** — n 784 · veterans 703 · rookies untouched True · top-24 membership stable False
| position | n_veterans | mean_before | mean_after | level_shift_pct | spearman_before_after | kendall_before_after | order_identical |
|---|---|---|---|---|---|---|---|
| QB | 95 | 104.7200 | 107.3100 | 2.4700 | 1.0000 | 1.0000 | True |
| RB | 165 | 58.1600 | 67.1800 | 15.5000 | 1.0000 | 1.0000 | True |
| WR | 280 | 50.8700 | 58.7500 | 15.4900 | 1.0000 | 1.0000 | True |
| TE | 147 | 40.1400 | 45.2700 | 12.7700 | 1.0000 | 1.0000 | True |

**NF1.5 served 2026 (nf1_5_season_projections_2026)** — n 794 · veterans 713 · rookies untouched True · top-24 membership stable False
| position | n_veterans | mean_before | mean_after | level_shift_pct | spearman_before_after | kendall_before_after | order_identical |
|---|---|---|---|---|---|---|---|
| QB | 96 | 103.7700 | 106.3400 | 2.4700 | 1.0000 | 1.0000 | True |
| RB | 168 | 57.0400 | 65.8800 | 15.5000 | 1.0000 | 1.0000 | True |
| WR | 285 | 49.8500 | 57.5700 | 15.4900 | 1.0000 | 1.0000 | True |
| TE | 148 | 39.7100 | 44.7800 | 12.7700 | 1.0000 | 1.0000 | True |

## 8. Registry action
{'registry': 'betting_ml/models/model_family_registry.yaml (NF-G0)', 'action': 'NONE — nothing was promoted'}

## 9. Scope + serving
- ⛔ Rookie leg out of scope (NF-D21 CLOSED; inherited).
- ⛔ NF1.5's ORDERING layer untouched — levels only.
- 🔒 CODE-READY, deploy-HELD: the board rebuild + republish + `run_interval_revalidation` re-run are POST-MERGE OPERATOR steps.
