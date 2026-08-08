# NF-RECAL1 — recalibrating the fastpath VETERAN point LEVEL
_generated 2026-08-08T08:36:29.228019+00:00_ · `best_alpha = 0` · model `nfl_fantasy_nf_recal1_veteran_level_v1` · recalibrates `nfl_fantasy_fastpath_v1`
## Verdict: **RECORDED NULL — CONSTRAINT_REFUSED**
On the pre-registered population — the veteran leg's draftable tier, fixed by the INCUMBENT's own projection — the measured level bias is **-12.85 PPR** over n = 2028, against the motivating **−37.7** over n = 1165. The unconditional universe reading is **0.84** and the same tier anchored on the REALIZED outcome is **-64.8** — the spread across those three readings is the whole methodological point, and it is why the anchor is pre-registered rather than chosen.

Best recalibrating arm: `pos_affine · unconstrained` at CRPS 50.6773 vs the incumbent's 53.04 (6/7 folds). Matched-foil reading: **mixed**. Null state: **CONSTRAINT_REFUSED**.
## 0. PREMISE CHECK — does the motivating defect reproduce in this population?
⭐ A recalibration is a correction fitted to a measured defect, so the defect is re-measured in the population this story fits on **before** anything is fitted. The tier is fixed by the INCUMBENT's own projection (`TIER_ANCHOR`), identically for every arm.
| reading | n | mean_bias | median_bias | ours_over_actual | pct_zero_outcome |
|---|---|---|---|---|---|
| universe (unconditional) | 8099 | 0.84 | 13.84 | 1.013 | 0.324 |
| draftable tier, INCUMBENT anchor (top 156/season) ⭐ PRE-REGISTERED | 2028 | -12.85 | -14.35 | 0.919 | 0.075 |
| draftable tier, REALIZED anchor (top 156/season) ⛔ forbidden | 2028 | -64.8 | -65.53 | 0.661 | 0.0 |
| played ≥6 games ⛔ outcome-conditioned | 4708 | -23.83 | -11.04 | 0.773 | 0.024 |

Motivating figure (NF-TR1): n **1165**, mean **−37.7**, median **−34.5**, our/actual QB 0.923 · RB 0.693 · WR 0.778 · TE 0.816.
| position | n | mean_bias (measured) | our/actual (measured) | our/actual (motivating) | sign agrees |
|---|---|---|---|---|---|
| QB | 465 | -0.57 | 0.997 | 0.923 | True |
| RB | 490 | -21.54 | 0.859 | 0.693 | True |
| WR | 822 | -15.78 | 0.897 | 0.778 | True |
| TE | 251 | -9.05 | 0.93 | 0.816 | True |

`premise_confirmed` = **True** · `reproduces_motivating_magnitude` = **False**
## 1. The field, and where each arm landed
| arm | form | rule | λ (final fold) | CRPS | MAE | bias | cov80 | universe CRPS | universe bias | eligible |
|---|---|---|---|---|---|---|---|---|---|---|
| pos_affine · unconstrained | pos_affine | unconstrained | 1.0 | 50.6773 | 68.3632 | -3.2728 | 0.5733 | 28.0973 | 1.3763 | False |
| pos_const · unconstrained | pos_const | unconstrained | 1.0 | 51.6904 | 68.6812 | -0.0041 | 0.5238 | 29.2768 | 5.9916 | False |
| pos_offset · unconstrained | pos_offset | unconstrained | 1.0 | 52.1666 | 68.6086 | -3.9162 | 0.4954 | 30.4638 | 7.0759 | False |
| global_const · unconstrained | global_const | unconstrained | 1.0 | 52.2005 | 69.3639 | 0.5142 | 0.5229 | 29.3962 | 6.0767 | False |
| avail_cond · unconstrained | avail_cond | unconstrained | 0.75 | 52.2834 | 69.3647 | -5.6426 | 0.5211 | 29.5576 | 5.4547 | False |
| incumbent (NULL) | incumbent | None | 0.0 | 53.04 | 69.8654 | -12.586 | 0.5046 | 29.2373 | 0.8243 | True |
| global_const · infold | global_const | infold | 0.0 | 53.04 | 69.8654 | -12.586 | 0.5046 | 29.2373 | 0.8243 | False |
| pos_const · infold | pos_const | infold | 0.0 | 53.04 | 69.8654 | -12.586 | 0.5046 | 29.2373 | 0.8243 | False |
| pos_offset · infold | pos_offset | infold | 0.0 | 53.04 | 69.8654 | -12.586 | 0.5046 | 29.2373 | 0.8243 | False |
| pos_affine · infold | pos_affine | infold | 0.0 | 53.04 | 69.8654 | -12.586 | 0.5046 | 29.2373 | 0.8243 | False |
| avail_cond · infold | avail_cond | infold | 0.0 | 53.04 | 69.8654 | -12.586 | 0.5046 | 29.2373 | 0.8243 | False |

### Anchors (two-sided, scored every run) — each with its REQUIRED direction
| anchor | role | expected | CRPS | MAE | bias | cov80 | behaves as expected |
|---|---|---|---|---|---|---|---|
| oracle_perplayer | ceiling | beats every real arm | 0.0026 | 0.0026 | 0.0026 | 0.9945 | True |
| permuted_across@pos_offset | permutation | loses to every real arm | 52.7481 | 69.5562 | -6.4266 | 0.4909 | True |
| permuted_across@pos_const | permutation | loses to every real arm | 51.9322 | 69.6195 | 14.1788 | 0.555 | True |
| permuted_across@pos_affine | permutation | loses to every real arm | 74.7637 | 80.3563 | -8.955 | 0.0962 | True |
| permuted_within@pos_offset | permutation | loses to every real arm | 51.897 | 68.4348 | -6.3202 | 0.5119 | True |
| permuted_within@pos_const | permutation | loses to every real arm | 52.7828 | 70.8057 | 16.4229 | 0.5595 | True |
| permuted_within@pos_affine | permutation | loses to every real arm | 72.4806 | 79.8869 | -9.1651 | 0.1218 | True |
| zero_project | degenerate | loses to every real arm | 162.7957 | 162.7957 | -162.7905 | 0.0549 | True |
| pos_median | degenerate | loses to every real arm | 82.8171 | 82.8171 | 0.8751 | 0.0 | True |
| over_scale | degenerate | loses to every real arm | 50.2491 | 68.9244 | 9.0457 | 0.6868 | False |
| wide_band | degenerate | loses to every real arm | 50.7451 | 69.8654 | -12.586 | 0.9405 | True |
| oracle_global_const | ceiling | beats every real arm | 51.822 | 69.0854 | 2.7845 | 0.5385 | False |
| oracle_pos_const | ceiling | beats every real arm | 50.1788 | 67.1964 | 3.9824 | 0.565 | True |
| oracle_pos_offset | ceiling | beats every real arm | 50.883 | 67.1845 | -2.0603 | 0.5229 | False |
| oracle_pos_affine | ceiling | beats every real arm | 47.8661 | 66.3102 | -4.5068 | 0.7207 | True |
| oracle_avail_cond | ceiling | beats every real arm | 49.3797 | 66.4447 | 5.136 | 0.5696 | True |

### Do the constraints have TEETH? — the degenerates read in both directions (NF1.8)
A CONSTRAINT a do-nothing arm satisfies is fine (the metric eliminates it); a CRITERION a do-nothing arm WINS is fatal. And a gate nothing is ever measured FAILING has examined nothing. Both halves are measured here rather than asserted.
| anchor | satisfies C2 on every fold | satisfies C3 on every fold | breaches C2 somewhere | breaches C3 somewhere |
|---|---|---|---|---|
| zero_project | False | False | True | True |
| over_scale | True | False | False | True |
| wide_band | True | True | False | False |

### Per-form peeking ceilings — must ORDER BY CAPACITY (NF-D16 (g‴))
| form | anchor | ceiling fitted on CRPS ⭐ | ceiling fitted by least squares | LS is not a bound (worse than the CRPS fit) |
|---|---|---|---|---|
| global_const | oracle_global_const | 51.822 | 51.8869 | True |
| pos_const | oracle_pos_const | 50.1788 | 50.6173 | True |
| pos_offset | oracle_pos_offset | 50.883 | 51.0516 | True |
| pos_affine | oracle_pos_affine | 47.8661 | 50.7962 | True |
| avail_cond | oracle_avail_cond | 49.3797 | 50.5359 | True |

`ceilings_order_by_capacity` = **True** (CRPS-fitted) vs **False** (least-squares-fitted).

⭐ **A THIRD REQUIREMENT ON A PEEKING CEILING, MEASURED HERE: MATCHED OBJECTIVE.** NF1.7 (b) / NF1.9 (f) / NF-D16 (g‴) require matched FAMILY and matched SAMPLE. This run's first cut fitted each ceiling by least squares — the candidates' own estimator — and scored it on CRPS, and the ceilings did not order by capacity even though the families strictly nest. "Peeking can only help" holds only when the peeking fit minimises the objective the arm is SCORED on; an LS-fitted ceiling is not a bound on a CRPS-scored arm, it is just another arm. Fitting each ceiling on CRPS restores the ordering and makes `family_ceiling_check` a real inversion detector rather than a coin flip. One shared ceiling would separately have vetoed a legitimately-better nested form as an inversion.
## 2. Matched foil — did the PER-GAME channel earn it? (NF-D15 (g′))
| arm | form | per_game_crps | season_total_crps | paired_delta | space_invariant_by_construction | expected_tie_holds |
|---|---|---|---|---|---|---|
| global_const · infold | global_const | 53.04 | 53.04 | 0.0 | True | True |
| global_const · unconstrained | global_const | 52.2005 | 52.2005 | 0.0 | True | True |
| pos_const · infold | pos_const | 53.04 | 53.04 | 0.0 | True | True |
| pos_const · unconstrained | pos_const | 51.6904 | 51.6904 | 0.0 | True | True |
| pos_offset · infold | pos_offset | 53.04 | 53.04 | 0.0 | False | None |
| pos_offset · unconstrained | pos_offset | 52.1666 | 52.4 | -0.2334 | False | None |
| pos_affine · infold | pos_affine | 53.04 | 53.04 | 0.0 | False | None |
| pos_affine · unconstrained | pos_affine | 50.6773 | 52.9064 | -2.229157 | False | None |
| avail_cond · infold | avail_cond | 53.04 | 53.04 | 0.0 | True | True |
| avail_cond · unconstrained | avail_cond | 52.2834 | 52.2834 | 0.0 | True | True |

reading = **mixed** · `space_invariance_proven` = **True** (a purely multiplicative correction satisfies `k·(p/g)·g ≡ k·p`, so the per-game channel CANNOT act on three of the five forms — pre-registered as an expected tie and proven, not discovered).

### Permutation vacuity — pre-registered as a TIE, and the SPACE is what decides it
A within-position shuffle preserves that position's MARGINAL exactly, so it cannot move a SEASON-TOTAL additive level (`c = mean(y − p)`). It DOES move the per-game one (`c = Σg(y − p)/Σg²`), which re-pairs each outcome with a different expected-games value. ⇒ the per-game parameterisation makes a level correction stop being a pure marginal statistic — which is also why the per-game hypothesis is testable at all. Measured, not asserted.
| space | max |Δ param| across folds | verdict |
|---|---|---|
| per_game | 1.0083765152297028 | ACTS — the fit re-pairs each outcome with a different expected-games value, so the correction is NOT purely marginal |
| season_total | 5.329070518200751e-15 | VACUOUS — a pure marginal statistic the shuffle cannot move |

### Attribution signature (a level fix moves bias TOWARD zero while accuracy improves)
| incumbent_bias | winner_bias | incumbent_metric | winner_metric | verdict | accuracy_improved | bias_moved_toward_zero | abs_bias_delta |
|---|---|---|---|---|---|---|---|
| -12.586 | -12.586 | 53.04 | 53.04 | no_lift | False | False | 0.0 |
## 3. Constraints
### C2 activity — how many folds can the placement clause even act on? (NF-D20 (g⁗))
| form | n_folds | folds_c2_can_act | active_folds | c2_inactive_everywhere | why_inactive |
|---|---|---|---|---|---|
| global_const | 7 | 7 | [2019, 2020, 2021, 2022, 2023, 2024, 2025] | False | None |
| pos_const | 7 | 7 | [2019, 2020, 2021, 2022, 2023, 2024, 2025] | False | None |
| pos_offset | 7 | 7 | [2019, 2020, 2021, 2022, 2023, 2024, 2025] | False | None |
| pos_affine | 7 | 7 | [2019, 2020, 2021, 2022, 2023, 2024, 2025] | False | None |
| avail_cond | 7 | 7 | [2019, 2020, 2021, 2022, 2023, 2024, 2025] | False | None |

### Out-of-sample constraint state per arm
| arm | holds out (C1∧C2∧C3) | C2 only | C3 only | failing folds |
|---|---|---|---|---|
| incumbent (NULL) | True | True | True | [] |
| global_const · infold | False | True | False | [2019, 2020, 2021, 2022, 2024, 2025] |
| global_const · unconstrained | False | True | False | [2019, 2020, 2021, 2022, 2024, 2025] |
| pos_const · infold | False | True | False | [2019, 2020, 2021, 2022, 2024, 2025] |
| pos_const · unconstrained | False | True | False | [2019, 2020, 2021, 2022, 2024, 2025] |
| pos_offset · infold | False | True | False | [2019, 2020, 2021, 2022, 2024, 2025] |
| pos_offset · unconstrained | False | True | False | [2019, 2020, 2021, 2022, 2024, 2025] |
| pos_affine · infold | False | True | False | [2019, 2020, 2021, 2022, 2024, 2025] |
| pos_affine · unconstrained | False | True | False | [2019, 2021, 2022, 2025] |
| avail_cond · infold | False | True | False | [2019, 2020, 2021, 2022, 2024, 2025] |
| avail_cond · unconstrained | False | False | False | [2019, 2020, 2021, 2022, 2023, 2024, 2025] |

### Whole-board CROSS-POSITION movement — MEASURED, gated on by NOTHING
⛔ NF-D17 validated a placement clause for the ROOKIE leg; this programme owns **no validated bar** for whole-board veteran churn, and inventing one on the population whose answer is already in view is the E2.1-r move. The number is handed to the PM instead.
| arm | λ | n_board | median_abs_rank_move | p90_abs_rank_move | max_abs_rank_move | n_moved | top100_churn | top100_membership_stable | top10_order_stable |
|---|---|---|---|---|---|---|---|---|---|
| global_const · infold | 0.0 | 786 | 0.0 | 0.0 | 0.0 | 0 | 0 | True | True |
| global_const · unconstrained | 1.0 | 786 | 2.0 | 12.0 | 35.0 | 585 | 0 | True | True |
| pos_const · infold | 0.0 | 786 | 0.0 | 0.0 | 0.0 | 0 | 0 | True | True |
| pos_const · unconstrained | 1.0 | 786 | 7.0 | 22.0 | 39.0 | 737 | 2 | False | False |
| pos_offset · infold | 0.0 | 786 | 0.0 | 0.0 | 0.0 | 0 | 0 | True | True |
| pos_offset · unconstrained | 1.0 | 786 | 16.0 | 71.0 | 136.0 | 760 | 3 | False | False |
| pos_affine · infold | 0.0 | 786 | 0.0 | 0.0 | 0.0 | 0 | 0 | True | True |
| pos_affine · unconstrained | 1.0 | 786 | 13.0 | 47.0 | 156.0 | 769 | 3 | False | False |
| avail_cond · infold | 0.0 | 786 | 0.0 | 0.0 | 0.0 | 0 | 0 | True | True |
| avail_cond · unconstrained | 0.75 | 786 | 7.0 | 20.0 | 35.0 | 731 | 2 | False | False |
## 4. Deflation + the pre-registered gate
| ship | framing | has_eligible_winner | recalibrates | beats_incumbent | ordering_ok_every_position | placement_holds_out_every_fold | coverage_floors_hold | pbo_ok | dsr_ok | significant |
|---|---|---|---|---|---|---|---|---|---|---|
| False | pooled | True | False | False | True | True | False | False | False | False |

PBO over the ELIGIBLE set = `None` · whole-field DSR = `None` (**the pre-registered gate**) · contender-set DSR = `None` · p = `1.0`

PBO over the ELIGIBLE set is `None` — when a constraint refuses every recalibrating arm the eligible set collapses to the NULL alone and the deflation statistics are **UNDEFINED, not failed** (MH2: a stat that was not COMPUTABLE must never be absorbed into a verdict about a mechanism). The unrestricted reading — the search that WOULD have run had the constraints not bound — is PBO `0.0`, OS-degradation `0.0`. ⛔ It gates nothing.

Sensitivities: {"dsr_at_0.0": false, "dsr_removed_would_ship": false, "expanded_field_trials": 36, "note": "the EXPANDED reading counts every constant-\u03bb point as its own trial; the pre-registered field is the RULES (MH2 (a): a family gets its own declared field, and \u26d4 trimming one after the fact under-taxes it)"}

### Per-position disclosure — computed, NEVER selected on
| position | incumbent_metric | winner | metric | delta | pbo | dsr | pvalue |
|---|---|---|---|---|---|---|---|
| QB | 62.2165 | incumbent (NULL) | 62.2165 | 0.0 | None | None | 1.0 |
| RB | 57.0873 | incumbent (NULL) | 57.0873 | 0.0 | None | None | 1.0 |
| WR | 50.4046 | incumbent (NULL) | 50.4046 | 0.0 | None | None | 1.0 |
| TE | 36.0582 | incumbent (NULL) | 36.0582 | 0.0 | None | None | 1.0 |
## 5. Null state
| state | taxonomy_would_say | taxonomy_fits | beats_incumbent_on_accuracy | fold_wins | n_folds | observed_sr |
|---|---|---|---|---|---|---|
| CONSTRAINT_REFUSED | POWER_LIMITED | False | True | 6 | 7 | 1.777 |

**why** — every recalibrating arm BEAT the incumbent on the metric and was removed by a DETERMINISTIC constraint with no sampling error to accumulate, so a statistical state would emit a re-test trigger more folds cannot satisfy

**remedy** — a different MECHANISM or a PM decision — never more folds, which cannot move a deterministic constraint

the veteran panel reaches target season 2013, so the METRIC is recomputable on 13 folds today; ⛔ C2 is NOT, because the merged boards begin at 2019 and an unevaluable constraint is never a pass. Widening the constraint window requires an operator rebuild of the boards (`run_season_projection --backtest-from 2013`).
## 6. Story-level verdict
| ship | pooled_gate_passes | premise_confirmed_in_this_population | sanity_degenerates_lose | permutation_across_beaten | oracle_respected | family_ceiling_respected | ceilings_order_by_capacity | over_scale_loses | wide_band_loses | rookie_leg_untouched | space_invariance_proven |
|---|---|---|---|---|---|---|---|---|---|---|---|
| False | False | True | True | True | True | True | True | False | True | True | True |

## 7. Scope + serving
- ⛔ **Rookie leg out of scope.** The rookie LEVEL is governed by the CLOSED NF-D16 → NF-D18 → NF-D20 → NF-D21 chain. NF-D21 was refused by the interval-floor gate and the PM CLOSED (not parked) it on 2026-08-05, naming the reason: a story left open pending a floor fix is exactly the pressure that would bias that floor toward clearing. Re-opening the rookie level inside a differently-named story would re-apply that pressure wearing a new badge. The exclusion is INHERITED BY IMPORT from `rookie_publish_policy`, not re-decided here.
- **QB in scope.** QB is IN scope, unlike NF-D16/D18/D20. Their exclusion rests on NF-D14's MEASURED rookie-QB double-pricing — a finding about the ROOKIE slot curve. No equivalent finding exists for the veteran leg, and the motivating table names a QB level gap, so excluding QB would be inheriting a reason that does not apply to this population.
- ⛔ **NF1.5's ORDERING layer is untouched.** This story changes LEVELS only.
- 🔒 **CODE-READY, NOT DEPLOYED.** Any serving flip is a POST-LAUNCH operator step with its own soak, and a level shift moves the band centre ⇒ `run_interval_revalidation` is REQUIRED before publish (this is the gate that refused NF-D21).
