# NF-B3 — JOINT level+band selection under the corrected C3 (13 folds)
_generated 2026-08-09T00:32:08.128852+00:00_ · `best_alpha = 0` · model `nfl_fantasy_nf_b3_joint_level_band_v1` · recalibrates `nfl_fantasy_fastpath_v1` · wall 12.3s
## Verdict: **RECORDED NULL — POWER_LIMITED**
On the 13-fold wide window (2013–2025), tier bias **-12.85 PPR** (n = 2028). Best recalibrating arm: `avail_cond · unconstrained` at CRPS 49.5122 vs the incumbent's 49.9214 (9/13 folds). Whole-field DSR `0.8773` (gate ≥ 0.95) · PBO(eligible) `0.039` · p `0.0119`. Matched-foil reading: **mixed** · attribution signature: **level_fix** · null state: **POWER_LIMITED**.

## 0. Provenance (every clause a RAISE)
- Served band held through the model path: universe IS80 `160.888` (recorded 160.888, Δ 0.0%), tier coverage 2019–2025 `0.8452` (recorded 0.8452); the panel columns' 0.5046 reproduced beside it (`0.5046`) — the trap exists and this run is not in it.
- Boards 2013–2025 walk-forward with rookie legs from 2016; structurally rookie-less (NCAAF substrate starts 2016): [2013, 2014, 2015] — C2 there is INACTIVE (vacuous, uninformative), never refused, never credited (NF-D20 (g⁗)).
- C3 equality boundary: `need = ceil(bind·n − 1e-9)` on the UNROUNDED incumbent (the NF-C3-REREAD harness finding, canonical here) — λ=0 is admissible by construction.

## 1. The field
| arm | form | rule | λ (final fold) | CRPS | MAE | bias | cov80 | universe CRPS | universe bias | eligible |
|---|---|---|---|---|---|---|---|---|---|---|
| avail_cond · unconstrained | avail_cond | unconstrained | 0.5 | 49.5122 | 70.4379 | -4.871 | 0.859 | 30.0889 | 6.2466 | False |
| pos_offset · unconstrained | pos_offset | unconstrained | 0.5 | 49.6423 | 71.0207 | -6.2117 | 0.8028 | 30.3375 | 5.6821 | False |
| pos_affine · unconstrained | pos_affine | unconstrained | 0.5 | 49.6665 | 71.0416 | -8.0403 | 0.8432 | 29.6227 | 2.9898 | False |
| pos_const · infold | pos_const | infold | 0.25 | 49.6817 | 71.0498 | -7.0769 | 0.8521 | 29.59 | 3.4921 | True |
| pos_const · unconstrained | pos_const | unconstrained | 0.25 | 49.6817 | 71.0498 | -7.0769 | 0.8521 | 29.59 | 3.4921 | True |
| global_const · infold | global_const | infold | 0.25 | 49.7402 | 71.1031 | -5.3809 | 0.8585 | 29.6746 | 4.1808 | True |
| global_const · unconstrained | global_const | unconstrained | 0.25 | 49.7402 | 71.1031 | -5.3809 | 0.8585 | 29.6746 | 4.1808 | True |
| avail_cond · infold | avail_cond | infold | 0.0 | 49.8164 | 71.4303 | -11.1722 | 0.8378 | 29.5087 | 1.9235 | False |
| incumbent (NULL) | incumbent | None | 0.0 | 49.9214 | 71.7011 | -12.8503 | 0.8333 | 29.3817 | 0.8286 | True |
| pos_offset · infold | pos_offset | infold | 0.0 | 49.9214 | 71.7011 | -12.8503 | 0.8333 | 29.3817 | 0.8286 | True |
| pos_affine · infold | pos_affine | infold | 0.0 | 49.9214 | 71.7011 | -12.8503 | 0.8333 | 29.3817 | 0.8286 | True |

### Anchors (two-sided, scored every run)
| anchor | role | expected | CRPS | MAE | bias | cov80 | behaves as expected |
|---|---|---|---|---|---|---|---|
| oracle_perplayer | ceiling | beats every real arm | 0.0043 | 0.0043 | 0.0043 | 0.9951 | True |
| permuted_across@pos_offset | permutation | loses to every real arm | 50.3175 | 71.8257 | -0.9509 | 0.7978 | True |
| permuted_across@pos_const | permutation | loses to every real arm | 52.8248 | 73.9502 | 25.1071 | 0.9097 | True |
| permuted_across@pos_affine | permutation | loses to every real arm | 72.639 | 83.3639 | -12.3605 | 0.1677 | True |
| permuted_within@pos_offset | permutation | loses to every real arm | 49.7173 | 70.8655 | -0.6643 | 0.8141 | True |
| permuted_within@pos_const | permutation | loses to every real arm | 53.2595 | 74.5655 | 26.6296 | 0.9112 | True |
| permuted_within@pos_affine | permutation | loses to every real arm | 70.4098 | 82.008 | -12.354 | 0.1893 | True |
| zero_project | degenerate | loses to every real arm | 157.9249 | 157.9249 | -157.9163 | 0.0705 | True |
| pos_median | degenerate | loses to every real arm | 81.9364 | 81.9364 | -2.7007 | 0.0 | True |
| over_scale | degenerate | loses to every real arm | 54.2873 | 73.8696 | 23.7646 | 0.8856 | True |
| wide_band | degenerate | loses to every real arm | 63.3477 | 71.7011 | -12.8503 | 0.9916 | True |
| oracle_global_const | ceiling | beats every real arm | 49.5452 | 71.0163 | -4.7789 | 0.8619 | False |
| oracle_pos_const | ceiling | beats every real arm | 48.9885 | 70.0068 | -4.7295 | 0.8693 | True |
| oracle_pos_offset | ceiling | beats every real arm | 48.9508 | 70.0349 | -4.2627 | 0.8185 | True |
| oracle_pos_affine | ceiling | beats every real arm | 48.5282 | 69.5391 | -6.1788 | 0.8516 | True |
| oracle_avail_cond | ceiling | beats every real arm | 48.216 | 68.4822 | -4.2865 | 0.8762 | True |

### C3 cannot police magnitude from above (inherited from NF-C3-REREAD) — the metric must
| over_scale_satisfies_c3_everywhere | wide_band_satisfies_c3_everywhere | over_scale_loses_metric | wide_band_loses_metric |
|---|---|---|---|
| False | True | True | True |

### Per-form peeking ceilings (each form floored by the peeking version of its OWN form)
| form | anchor | ceiling fitted on CRPS ⭐ | ceiling fitted by least squares |
|---|---|---|---|
| global_const | oracle_global_const | 49.5452 | 49.7789 |
| pos_const | oracle_pos_const | 48.9885 | 49.3994 |
| pos_offset | oracle_pos_offset | 48.9508 | 49.0773 |
| pos_affine | oracle_pos_affine | 48.5282 | 50.9142 |
| avail_cond | oracle_avail_cond | 48.216 | 49.2782 |

`ceilings_order_by_capacity` = **True** (CRPS-fitted) vs **False** (LS-fitted disclosure).

⚠️ the anchor table's generic 'beats every real arm' expectation is COARSER than the per-form check for the family ceilings: a RICHER real arm can legitimately beat a COARSER family's peeking ceiling (the NF-D16 (g‴) capacity effect — here avail_cond·unconstrained beats oracle_global_const). The binding checks are `family_ceiling_check` (no arm beats its OWN form's ceiling) and `ceilings_order_by_capacity`, both PASS.

## 2. Matched foil + attribution (NF-D15 (g′))
| arm | form | per_game_crps | season_total_crps | paired_delta | space_invariant_by_construction | expected_tie_holds |
|---|---|---|---|---|---|---|
| global_const · infold | global_const | 49.7402 | 49.7402 | 0.0 | True | True |
| global_const · unconstrained | global_const | 49.7402 | 49.7402 | 0.0 | True | True |
| pos_const · infold | pos_const | 49.6817 | 49.6817 | 0.0 | True | True |
| pos_const · unconstrained | pos_const | 49.6817 | 49.6817 | 0.0 | True | True |
| pos_offset · infold | pos_offset | 49.9214 | 49.9214 | 0.0 | False | None |
| pos_offset · unconstrained | pos_offset | 49.6423 | 49.6349 | 0.007469 | False | None |
| pos_affine · infold | pos_affine | 49.9214 | 49.9214 | 0.0 | False | None |
| pos_affine · unconstrained | pos_affine | 49.6665 | 49.7354 | -0.068915 | False | None |
| avail_cond · infold | avail_cond | 49.8164 | 49.8164 | 0.0 | True | True |
| avail_cond · unconstrained | avail_cond | 49.5122 | 49.5122 | 0.0 | True | True |

reading = **mixed** · signature: | incumbent_bias | winner_bias | incumbent_metric | winner_metric | verdict | accuracy_improved | bias_moved_toward_zero | abs_bias_delta |
|---|---|---|---|---|---|---|---|
| -12.8503 | -7.0769 | 49.9214 | 49.6817 | level_fix | True | True | -5.7734 |

## 3. Constraints
### C2 activity (NF-D20 (g⁗)) — inactive folds are uninformative, never passes
| form | n_folds | folds_c2_can_act | active_folds | folds_c2_structurally_absent | c2_inactive_everywhere | why_inactive |
|---|---|---|---|---|---|---|
| global_const | 13 | 9 | [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] | [2013, 2014, 2015] | False | None |
| pos_const | 13 | 9 | [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] | [2013, 2014, 2015] | False | None |
| pos_offset | 13 | 9 | [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] | [2013, 2014, 2015] | False | None |
| pos_affine | 13 | 10 | [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] | [2013, 2014, 2015] | False | None |
| avail_cond | 13 | 9 | [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] | [2013, 2014, 2015] | False | None |

### Out-of-sample constraint state per arm
| arm | holds out (C1∧C2∧C3) | C2 only | C3 only | failing folds |
|---|---|---|---|---|
| incumbent (NULL) | True | True | True | [] |
| global_const · infold | True | True | True | [] |
| global_const · unconstrained | True | True | True | [] |
| pos_const · infold | True | True | True | [] |
| pos_const · unconstrained | True | True | True | [] |
| pos_offset · infold | True | True | True | [] |
| pos_offset · unconstrained | False | True | False | [2014, 2016, 2017, 2018, 2020, 2022, 2025] |
| pos_affine · infold | True | True | True | [] |
| pos_affine · unconstrained | False | True | False | [2014, 2020] |
| avail_cond · infold | False | True | True | [2017] |
| avail_cond · unconstrained | False | False | True | [2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021] |

### Whole-board cross-position movement — measured, gated on by nothing
| arm | λ | n_board | median_abs_rank_move | p90_abs_rank_move | max_abs_rank_move | n_moved | top100_churn | top100_membership_stable | top10_order_stable |
|---|---|---|---|---|---|---|---|---|---|
| global_const · infold | 0.25 | 786 | 0.5 | 4.0 | 15.0 | 393 | 0 | True | True |
| global_const · unconstrained | 0.25 | 786 | 0.5 | 4.0 | 15.0 | 393 | 0 | True | True |
| pos_const · infold | 0.25 | 786 | 2.0 | 7.0 | 16.0 | 632 | 1 | False | False |
| pos_const · unconstrained | 0.25 | 786 | 2.0 | 7.0 | 16.0 | 632 | 1 | False | False |
| pos_offset · infold | 0.0 | 786 | 0.0 | 0.0 | 0.0 | 0 | 0 | True | True |
| pos_offset · unconstrained | 0.5 | 786 | 9.0 | 38.0 | 83.0 | 751 | 1 | False | False |
| pos_affine · infold | 0.0 | 786 | 0.0 | 0.0 | 0.0 | 0 | 0 | True | True |
| pos_affine · unconstrained | 0.5 | 786 | 12.0 | 35.0 | 123.0 | 748 | 1 | False | False |
| avail_cond · infold | 0.0 | 786 | 0.0 | 0.0 | 0.0 | 0 | 0 | True | True |
| avail_cond · unconstrained | 0.5 | 786 | 5.0 | 31.0 | 60.0 | 731 | 1 | False | False |

## 4. Deflation + the pre-registered gate
| ship | framing | has_eligible_winner | recalibrates | beats_incumbent | ordering_ok_every_position | placement_holds_out_every_fold | coverage_floors_hold | pbo_ok | dsr_ok | significant |
|---|---|---|---|---|---|---|---|---|---|---|
| False | pooled | True | True | True | True | True | True | True | False | True |

PBO(eligible) `0.039` · whole-field DSR `0.8773` (**the pre-registered gate**, ≥ 0.95) · contender-set DSR `0.938` · p `0.0119` · per-fold Δ [0.0, 0.5174, 0.6401, -0.4002, -0.3576, 0.483, 0.4943, 0.2196, 0.0605, 0.2437, 0.5302, 0.4357, 0.2494]

### The DSR margin, in the unit that grows (MH2 (b))
| winner_sr | expected_max_sr_under_field_sr0 | sr_exceeds_sr0 | n_trials_in_field | folds_needed_for_dsr_gate | folds_available_today | reading |
|---|---|---|---|---|---|---|
| 0.7172 | 0.271 | True | 8 | 26 | 13 | REACHABLE: at the observed SR (0.717) under the declared field (SR0 0.271), DSR ≥ 0.95 needs ~26 folds vs 13 today. The reachable-now widening (the 2013 board rebuild) is EXHAUSTED; every future season adds one fold, so this is a CALENDAR-bound re-test — and ⛔ the field may not be trimmed to lower SR0 (MH2 (a): a family is pre-registered, never discovered). |

REACHABLE: at the observed SR (0.717) under the declared field (SR0 0.271), DSR ≥ 0.95 needs ~26 folds vs 13 today. The reachable-now widening (the 2013 board rebuild) is EXHAUSTED; every future season adds one fold, so this is a CALENDAR-bound re-test — and ⛔ the field may not be trimmed to lower SR0 (MH2 (a): a family is pre-registered, never discovered).

Sensitivities: {"dsr_at_0.0": true, "dsr_removed_would_ship": true, "expanded_field_trials": 36, "note": "the EXPANDED reading counts every constant-\u03bb point as its own trial; the pre-registered field is the RULES (MH2 (a))"}

### Per-position disclosure (computed, never selected on) + BH-FDR
| position | incumbent_metric | winner | metric | delta | pbo | dsr | pvalue |
|---|---|---|---|---|---|---|---|
| QB | 59.2997 | pos_const · infold | 59.2932 | -0.0065 | 0.7955 | 0.0623 | 0.4793 |
| RB | 51.7438 | pos_const · infold | 51.3073 | -0.4365 | 0.0274 | 0.9699 | 0.0137 |
| WR | 47.4356 | pos_const · infold | 47.2439 | -0.1917 | 0.3258 | 0.5497 | 0.1686 |
| TE | 37.4341 | global_const · infold | 36.8243 | -0.6098 | 0.0012 | 0.9799 | 0.0207 |

BH-FDR: {"QB": false, "RB": true, "WR": false, "TE": true}

## 5. Null state / classification
| state | taxonomy_would_say | taxonomy_fits | beats_incumbent_on_accuracy | fold_wins | n_folds | observed_sr | dsr_ceiling_at_this_fold_count |
|---|---|---|---|---|---|---|---|
| POWER_LIMITED | POWER_LIMITED | True | True | 9 | 13 | 0.6657 | 1.0 |

**why** — at least one recalibrating arm survived the constraints, so whatever refused this story was the METRIC or the deflation gates — the taxonomy applies as written

**remedy** — REACHABLE: at the observed SR (0.717) under the declared field (SR0 0.271), DSR ≥ 0.95 needs ~26 folds vs 13 today. The reachable-now widening (the 2013 board rebuild) is EXHAUSTED; every future season adds one fold, so this is a CALENDAR-bound re-test — and ⛔ the field may not be trimmed to lower SR0 (MH2 (a): a family is pre-registered, never discovered).

NF-B3 IS the wide-window run: 13 folds (2013–2025) is the maximal constraint-evaluable window today — the veteran panel reaches 2007 but merged boards below 2013 do not exist, and the rookie substrate (hence C2's subject) begins at draft class 2016. Any further widening is a new operator precursor, not a property of this data.

## 6. Story-level verdict
| ship | pooled_gate_passes | premise_confirmed_in_this_population | sanity_degenerates_lose | permutation_across_beaten | oracle_respected | family_ceiling_respected | ceilings_order_by_capacity | over_scale_loses | wide_band_loses | rookie_leg_untouched | space_invariance_proven |
|---|---|---|---|---|---|---|---|---|---|---|---|
| False | False | True | True | True | True | True | True | True | True | True | True |

## 6b. Registry action
| registry | action | reason |
|---|---|---|
| betting_ml/models/model_family_registry.yaml (NF-G0) | NONE — nothing was promoted | the pooled gate fails on the whole-field DSR alone, so this is a RECORDED NULL (POWER_LIMITED, calendar-bound re-test). The promotion state machine has no state for a recorded null; a `challenger` entry would misrepresent a non-shipped arm as staged (NF-RECAL1 / NF-D18 / NF-D20 precedent). The record of this story is its ablation memo + the scheduled re-validation trigger in `null.remedy`. |

## 7. Scope + serving
- ⛔ Rookie leg out of scope (closed NF-D16→D21 chain, inherited by import).
- ⛔ NF1.5's ORDERING layer untouched — levels only.
- 🔒 CODE-READY, deploy-HELD. If the verdict ships, the publish of the recalibrated veteran board, a changelog line, and a `run_interval_revalidation` re-run (a level shift moves the band centre) are POST-MERGE OPERATOR steps — nothing serves from this run.
