# NF-TR2b — season-projection LEVEL recalibration (draft-board credibility) · trailing window 5 seasons
_generated 2026-08-15T21:49:09.213387+00:00_ · `best_alpha = 0` · model `nfl_fantasy_nf_tr2b_veteran_level_v1` · recalibrates `nfl_fantasy_fastpath_v1` · wall 22.1s
## Verdict: **SHIP**
Winner `pos_const · λ=1 · mean-match` · tier CRPS **49.3394** vs incumbent 49.9214 · pooled tier bias 1.4117258361110376 vs -12.850295382832726 · PBO(elig) 0.0 · DSR(declared 3-trial field) **0.9995** · DSR under NF-B3's field 0.999 · p 0.0002

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
| pos_affine · λ=1 · OLS [refit band DISCLOSURE] | refit | False | False | 49.0722 | 70.1733 | -1.1961 | 1.5242 | -7.0176 | -0.4180 | 2.5808 | 0.8284 | 29.1847 | 2.3824 |
| pos_affine · λ=1 · OLS | fixed | True | False | 49.1812 | 70.1733 | -1.1961 | 1.5242 | -7.0176 | -0.4180 | 2.5808 | 0.8348 | 28.9621 | 2.3824 |
| pos_const · λ=1 · mean-match [refit band DISCLOSURE] | refit | False | False | 49.2529 | 70.4922 | 1.4117 | 7.6239 | -5.3152 | 1.3793 | 3.1418 | 0.8304 | 29.7621 | 7.4872 |
| pos_const · λ=1 · mean-match | fixed | True | True | 49.3394 | 70.4922 | 1.4117 | 7.6239 | -5.3152 | 1.3793 | 3.1418 | 0.8343 | 29.7379 | 7.4872 |
| pos_const · λ=1 · mean-match [scaled band DISCLOSURE] | scaled | False | False | 49.5789 | 70.4922 | 1.4117 | 7.6239 | -5.3152 | 1.3793 | 3.1418 | 0.8812 | 30.0695 | 7.4872 |
| incumbent (NULL) | served | True | True | 49.9214 | 71.7011 | -12.8503 | -0.5654 | -21.5386 | -15.7798 | -9.0540 | 0.8333 | 29.3817 | 0.8286 |
| pos_affine · λ=1 · OLS [scaled band DISCLOSURE] | scaled | False | False | 50.2806 | 70.1733 | -1.1961 | 1.5242 | -7.0176 | -0.4180 | 2.5808 | 0.9093 | 29.7787 | 2.3824 |

Fitted params (final fold 2025): `{'pos_const': '{"QB": 0.9418470646368412, "RB": 1.1909543087655077, "TE": 1.0839139129853799, "WR": 1.1148363612759715}', 'pos_affine': '{"QB": [-1.7490995583955915, 1.0398471547798434], "RB": [1.7776948404144688, 1.019070048254655], "TE": [0.7578553804506298, 0.9909906599661684], "WR": [-2.21734298335545, 1.332281059825699]}'}`

### Anchors (two-sided, scored every run, PRIMARY treatment; ceilings under the FIXED band)
| anchor | role | expected | CRPS | MAE | bias | cov80 | behaves as expected |
|---|---|---|---|---|---|---|---|
| oracle_perplayer | ceiling | beats every real arm | 0.0043 | 0.0043 | 0.0043 | 0.9951 | True |
| zero_project | degenerate | loses to every real arm | 157.9249 | 157.9249 | -157.9163 | 0.0705 | True |
| pos_median | degenerate | loses to every real arm | 81.9364 | 81.9364 | -2.7007 | 0.0000 | True |
| wide_band | degenerate | loses to every real arm | 63.3477 | 71.7011 | -12.8503 | 0.9916 | True |
| permuted_across@pos_const | permutation | loses to every real arm | 49.7391 | 72.0656 | 0.9800 | 0.8363 | True |
| permuted_within@pos_const | permutation | loses to every real arm | 49.3394 | 70.4922 | 1.4117 | 0.8343 | True |
| permuted_across@pos_affine | permutation | loses to every real arm | 53.8247 | 82.9071 | -7.2083 | 0.8338 | True |
| permuted_within@pos_affine | permutation | loses to every real arm | 53.3882 | 81.1746 | -7.8947 | 0.8333 | True |
| over_scale | degenerate | loses to every real arm | 49.5944 | 72.0421 | 15.6737 | 0.8358 | True |
| lambda_sweep@0.25 | degenerate | loses to every real arm | 49.7032 | 71.1437 | -9.2848 | 0.8333 | True |
| lambda_sweep@0.5 | degenerate | loses to every real arm | 49.5311 | 70.7598 | -5.7193 | 0.8333 | True |
| lambda_sweep@0.75 | degenerate | loses to every real arm | 49.4063 | 70.5313 | -2.1538 | 0.8343 | True |
| lambda_sweep@1.25 | degenerate | loses to every real arm | 49.3259 | 70.6351 | 4.9772 | 0.8348 | True |
| lambda_sweep@1.5 | degenerate | loses to every real arm | 49.3655 | 70.9595 | 8.5427 | 0.8348 | True |
| lambda_sweep@2 | degenerate | loses to every real arm | 49.5944 | 72.0421 | 15.6737 | 0.8358 | True |
| window_sensitivity@w3 | degenerate | loses to every real arm | 49.4114 | 70.5991 | -0.0556 | 0.8333 | True |
| window_sensitivity@w8 | degenerate | loses to every real arm | 49.4229 | 70.7580 | 3.8555 | 0.8343 | True |
| window_sensitivity@wNone | degenerate | loses to every real arm | 49.4173 | 70.8832 | 7.8812 | 0.8348 | True |
| oracle_pos_const | ceiling | beats every real arm | 48.8642 | 69.7650 | 4.1225 | 0.8358 | True |
| oracle_pos_affine | ceiling | beats every real arm | 47.8106 | 68.3228 | 0.1508 | 0.8378 | True |

Family ceiling (matched FIXED-band treatment): {'pos_const': True, 'pos_affine': True} · ceilings order by capacity: True · {'pos_const': {'ceiling_crps': 48.8642, 'arm_crps_fixed_band': 49.3394}, 'pos_affine': {'ceiling_crps': 47.8106, 'arm_crps_fixed_band': 49.1812}}

### λ-sweep of the mean-match (the interior-optimum question, MEASURED — anchors, never selected on)
| treatment | λ | CRPS | bias | cov80 | MAE |
|---|---|---|---|---|---|
| fixed | 0.0000 | 49.9214 | -12.8503 | 0.8333 | 71.7011 |
| fixed | 0.2500 | 49.7032 | -9.2848 | 0.8333 | 71.1437 |
| fixed | 0.5000 | 49.5311 | -5.7193 | 0.8333 | 70.7598 |
| fixed | 0.7500 | 49.4063 | -2.1538 | 0.8343 | 70.5313 |
| fixed | 1.0000 | 49.3394 | 1.4117 | 0.8343 | 70.4922 |
| fixed | 1.2500 | 49.3259 | 4.9772 | 0.8348 | 70.6351 |
| fixed | 1.5000 | 49.3655 | 8.5427 | 0.8348 | 70.9595 |
| fixed | 2.0000 | 49.5944 | 15.6737 | 0.8358 | 72.0421 |
| refit | 0.0000 | 49.9214 | -12.8503 | 0.8333 | 71.7011 |
| refit | 0.2500 | 49.6655 | -9.2848 | 0.8309 | 71.1437 |
| refit | 0.5000 | 49.4936 | -5.7193 | 0.8319 | 70.7598 |
| refit | 0.7500 | 49.3582 | -2.1538 | 0.8328 | 70.5313 |
| refit | 1.0000 | 49.2529 | 1.4117 | 0.8304 | 70.4922 |
| refit | 1.2500 | 49.3051 | 4.9772 | 0.8264 | 70.6351 |
| refit | 1.5000 | 49.3387 | 8.5427 | 0.8274 | 70.9595 |
| refit | 2.0000 | 49.6078 | 15.6737 | 0.8294 | 72.0421 |
| scaled | 0.0000 | 49.9214 | -12.8503 | 0.8333 | 71.7011 |
| scaled | 0.2500 | 49.6185 | -9.2848 | 0.8491 | 71.1437 |
| scaled | 0.5000 | 49.4643 | -5.7193 | 0.8614 | 70.7598 |
| scaled | 0.7500 | 49.4542 | -2.1538 | 0.8743 | 70.5313 |
| scaled | 1.0000 | 49.5789 | 1.4117 | 0.8812 | 70.4922 |
| scaled | 1.2500 | 49.8296 | 4.9772 | 0.8881 | 70.6351 |
| scaled | 1.5000 | 50.1977 | 8.5427 | 0.8935 | 70.9595 |
| scaled | 2.0000 | 51.2608 | 15.6737 | 0.9019 | 72.0421 |

### Window sensitivity (anchors, never trials) — the registered window is DERIVED, not tuned
derivation: `{'tier_rows_per_position_per_season': {'QB': 35.77, 'RB': 37.69, 'TE': 19.31, 'WR': 63.23}, 'min_rows': 90, 'derived_window': 5, 'pinned_window': 5}`
| window | is_registered | CRPS | bias | bias_QB | bias_RB | bias_WR | bias_TE | cov80 | MAE |
|---|---|---|---|---|---|---|---|---|---|
| 3 | False | 49.4114 | -0.0556 | 4.8677 | -4.8406 | -0.2699 | 0.8663 | 0.8333 | 70.5991 |
| 8 | False | 49.4229 | 3.8555 | 10.1591 | -5.4608 | 4.7756 | 7.3518 | 0.8343 | 70.7580 |
| full history | False | 49.4173 | 7.8812 | 12.6152 | -4.2460 | 10.6464 | 13.7296 | 0.8348 | 70.8832 |
| 5 | True | 49.3394 | 1.4117 | 7.6239 | -5.3152 | 1.3793 | 3.1418 | 0.8343 | 70.4922 |

Predecessor: `{'story': 'NF-TR2', 'record': 'ablation_results/nf_tr2_level_recalibration.md', 'why_a_successor': "NF-TR2's full-history mean-match passed every inherited gate and was REFUSED by its own level gates (over-correction out of fold from a non-stationary level — see season_level_recalibration.py, the TR2b block); the successor is the same family with the trailing window DERIVED from the tier's thinnest position, declared before this run"}`

## 3. Constraints (out-of-sample, every fold)
| arm | holds out (C1∧C2∧C3) | C1 only | C2 only | C3 only | failing folds | C2 active folds | C2 structurally absent |
|---|---|---|---|---|---|---|---|
| incumbent (NULL) | True | True | True | True | [] | None | None |
| pos_const · λ=1 · mean-match | True | True | True | True | [] | [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] | [2013, 2014, 2015] |
| pos_affine · λ=1 · OLS | False | False | True | True | [2013, 2015, 2016, 2017, 2019, 2021] | [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] | [2013, 2014, 2015] |

## 4. Deflation over the DECLARED field
| declared_field_size | n_trial_sharpes | trial_sharpes | sr0_declared_field | dsr_declared_field | b3_field_sr0 | dsr_under_b3_field |
|---|---|---|---|---|---|---|
| 3 | 2 | [1.3261, 1.864] | 0.1977 | 0.9995 | 0.2710 | 0.9990 |

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
   "metric": 59.0474,
   "delta": -0.2523,
   "pbo": 0.2185,
   "dsr": 0.8138,
   "pvalue": 0.1093
  },
  {
   "position": "RB",
   "incumbent_metric": 51.7438,
   "winner": "pos_const \u00b7 \u03bb=1 \u00b7 mean-match",
   "metric": 50.7804,
   "delta": -0.9634,
   "pbo": 0.0058,
   "dsr": 0.9982,
   "pvalue": 0.0208
  },
  {
   "position": "WR",
   "incumbent_metric": 47.4356,
   "winner": "pos_const \u00b7 \u03bb=1 \u00b7 mean-match",
   "metric": 46.8,
   "delta": -0.6356,
   "pbo": 0.0,
   "dsr": 1.0,
   "pvalue": 0.0013
  },
  {
   "position": "TE",
   "incumbent_metric": 37.4341,
   "winner": "pos_const \u00b7 \u03bb=1 \u00b7 mean-match",
   "metric": 37.0027,
   "delta": -0.4314,
   "pbo": 0.0495,
   "dsr": 0.9699,
   "pvalue": 0.0362
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
 "L1_pooled_reduced": true,
 "L1_detail": {
  "incumbent": -12.850295382832726,
  "winner": 1.4117258361110376,
  "reduction": 0.890140592565909
 },
 "L2_per_position": {
  "QB": true,
  "RB": true,
  "WR": true,
  "TE": true
 },
 "L2_all": true,
 "L3_no_inflation": true,
 "L3_detail": {
  "not_significantly_hot": true,
  "over_scale_loses": true,
  "pooled_se": 1.9574161313208067
 },
 "L4_availability_preserved": true,
 "pass": true,
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
| True | True | True | True | True | True | True | True | True | True | True | True | True |

## 7. Serving — the fit that would ship + the before/after board diff
form `pos_const` · params 2026 `{'QB': 0.9287565281164292, 'RB': 1.2479906943402788, 'WR': 1.1003071269200309, 'TE': 1.1115566369997747}` · panel target seasons < 2026, trailing window 5 (tier top 156/season)
refit-vs-fixed band agreement (winner): {'crps_refit': 49.3394, 'crps_fixed': 49.3394, 'cov80_refit': 0.8343, 'cov80_fixed': 0.8343, 'cov80_incumbent': 0.8333, 'band_fallback_rows_frac': 0.0}

**fastpath 2026 (nfl_fantasy_season_projections_2026)** — n 784 · veterans 703 · rookies untouched True · top-24 membership stable False
| position | n_veterans | mean_before | mean_after | level_shift_pct | spearman_before_after | kendall_before_after | order_identical |
|---|---|---|---|---|---|---|---|
| QB | 95 | 104.7200 | 97.2600 | -7.1200 | 1.0000 | 1.0000 | True |
| RB | 165 | 58.1600 | 72.5900 | 24.8000 | 1.0000 | 1.0000 | True |
| WR | 280 | 50.8700 | 55.9800 | 10.0300 | 1.0000 | 1.0000 | True |
| TE | 147 | 40.1400 | 44.6200 | 11.1600 | 1.0000 | 1.0000 | True |

**NF1.5 served 2026 (nf1_5_season_projections_2026)** — n 794 · veterans 713 · rookies untouched True · top-24 membership stable False
| position | n_veterans | mean_before | mean_after | level_shift_pct | spearman_before_after | kendall_before_after | order_identical |
|---|---|---|---|---|---|---|---|
| QB | 96 | 103.7700 | 96.3800 | -7.1200 | 1.0000 | 1.0000 | True |
| RB | 168 | 57.0400 | 71.1900 | 24.8000 | 1.0000 | 1.0000 | True |
| WR | 285 | 49.8500 | 54.8500 | 10.0300 | 1.0000 | 1.0000 | True |
| TE | 148 | 39.7100 | 44.1400 | 11.1600 | 1.0000 | 1.0000 | True |

## 8. Registry action
{'registry': 'betting_ml/models/model_family_registry.yaml (NF-G0)', 'action': 'STAGE a challenger — level_model_version → nfl_fantasy_nf_tr2b_veteran_level_v1 (operator, post-merge, via the NF-G0 publish flow)'}

## 9. Scope + serving
- ⛔ Rookie leg out of scope (NF-D21 CLOSED; inherited).
- ⛔ NF1.5's ORDERING layer untouched — levels only.
- 🔒 CODE-READY, deploy-HELD: the board rebuild + republish + `run_interval_revalidation` re-run are POST-MERGE OPERATOR steps.
