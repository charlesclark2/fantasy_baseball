# NF-W7f — the QB MARGINAL-layer zero-mass recalibration (NULL)

Generated 2026-08-17T23:16:14.801743+00:00 · gate position **QB** · gate league **full_ppr** · 8 folds · target `league_fantasy_points` · ranked on `crps_q199` · gated on `randomized_pit_max_decile_dev`

⚖️ `best_alpha = 0` · **DEPLOY-HELD** · NF-G0 challenger. Joint construction held FIXED at `mixall_learned` (NF-W7e's registered arm) — the declared family varies the per-leg zero-mass TARGET and nothing else.

> ⛔ QB ONLY — RB/WR/TE were NOT scored here and this record certifies nothing about them (NF1.7 (a)); NF-W8's four-position optimizer input additionally requires an RB certificate, a separate story.

## Marginal-cap verdict

**`QB_CLEARS_AT_THE_MARGINAL_LAYER`** — the marginal-admissible atom cap was lifted and a real arm clears the PIT bar — the MARGINAL layer was QB's binding constraint, NF-W7e's confirmation is vindicated, and a calibrated assembled QB distribution exists (deploy-held, NF-G0 challenger)

| quantity | value |
|---|---|
| atom cap, SERVED marginals (NF-W7e recorded) | 0.2687 |
| atom cap, RECALIBRATED | 0.5481 |
| cap lift (required ≥ 0.012) | 0.2794 |
| installed atom | 0.5176 |
| realized all-zero rate | 0.5162 |
| shortfall (realized − installed) | -0.0014 |
| clamp binding SHARE (was 0.917) | 0.917 ⚠️ see below |
| clamp mean upward move on π̂ — SERVED → winner | 0.25271 → 0.00225 |
| PIT: best arm | `zm_floor` 0.0281 vs bar 0.05 |
| PIT: matched foil (`mixall_learned`) | 0.0648 |
| PIT moved by the recalibration | -0.0245 |

**Which NF-W6d cell caps the atom** (share of rows attaining the row-wise `min_j P̂_j(0)`):

- SERVED: `{'attempts': 0.2634, 'carries': 0.022, 'passing_tds': 0.0005, 'passing_yards': 0.7091, 'rushing_yards': 0.0049}`

## QB — winner `zm_floor` vs best contest foil `mixall_learned`

Δ`crps_q199` **0.0184** (CI95 [0.0032, 0.0336], 6/8 folds) · PBO 0.0 · DSR 0.0 · p 0.0121 · coverage(80) 0.8299 (floor 0.8) · PIT 0.0281 (bar 0.05)

**Gate: NO** — beats_foil ✅, fold_consistency ✅, pbo_ok ✅, dsr_ok ❌, fdr_ok ✅, coverage_floor_ok ✅, pit_flat_ok ✅, degenerates_lose ✅, permutation_behaves ✅, oracle_floors_respected ✅, mixture_is_active ✅, mixture_preserves_marginals ✅, incumbent_reproduces ✅, predecessor_reproduces ✅, zero_mass_hits_target ✅, positive_law_preserved ✅, matched_foil_identity ✅, cap_was_lifted ✅, per_leg_calibration_not_degraded ❌, independence_under_disperses ✅, dependence_moves_coverage ✅, beats_indep_on_coverage ✅

### Attribution (the 2×2: marginals × availability split)

| contrast | Δ |
|---|---|
| recalibration_with_split | 0.0184 |
| recalibration_without_split | -0.0407 |
| split_on_served_marginals | 0.0064 |
| vs_incumbent | 0.0248 |
| delta_vs_indep | 0.0953 |
| beats_direct_points_REPORT_ONLY | True |
| delta_vs_direct_points_REPORT_ONLY | 0.0189 |

### Mean CRPS by label

| label | crps_q199 | PIT |
|---|---|---|
| `oracle__foil_direct_points` | 1.7216 | — |
| `oracle__zm_floor` | 2.2276 | — |
| `oracle__zm_conditional` | 2.3195 | — |
| `oracle__zm_over` | 2.3221 | — |
| `zm_floor` | 2.5645 | 0.0281 |
| `mixall_learned` | 2.5829 | 0.0648 |
| `foil_direct_points` | 2.5834 | 0.0959 |
| `single_copula` | 2.5893 | 0.0646 |
| `zm_conditional` | 2.6297 | 0.0403 |
| `zm_cond_copula` | 2.63 | 0.0324 |
| `matched_n__zm_floor` | 2.635 | — |
| `assembled_indep` | 2.6598 | 0.0814 |
| `assembled_comonotone` | 2.6954 | 0.0563 |
| `zm_over` | 2.7017 | 0.0858 |
| `matched_n__zm_conditional` | 2.7288 | — |
| `matched_n__zm_over` | 2.8579 | — |
| `oracle__zm_climatology` | 3.6778 | — |
| `matched_n__zm_climatology` | 3.7029 | — |
| `zm_climatology` | 3.7516 | 0.0695 |
| `zm_permuted` | 4.3983 | 0.1671 |
| `permuted_direct` | 4.7437 | — |
| `nihilist_zero` | 6.5404 | 0.4025 |
| `zero_width` | 7.8446 | 0.5395 |
| `max_width` | 10.4448 | 0.7551 |

### The transform's measured identities

- `zero_mass_hits_target`: max gap 0.0 (tol 1e-12)
- `positive_law_preserved`: max drift / resolution bound 0.894472 (tol ≤ 1.0; evaluated True) — {'max_probability_drift': 0.090452, 'mean_probability_drift': 0.009528, 'max_resolution_bound': 0.181818, 'max_drift_over_bound': 0.819095, 'evaluable_cell_share': 0.4677, 'min_conditional_knots': 10, 'tolerance_ratio': 1.0, 'evaluated': True, 'holds': True}
- `matched_foil_identity` (re-splice to own atom is a no-op through `draw_legs`): max draw gap 0.0
- resplice edges (last fold): {'zm_conditional': {'share_no_atom_in_source': 0.0103, 'share_target_below_source_ignored': 0.4096, 'share_target_clipped': 0.1942, 'mean_target': 0.8129, 'mean_source_zero_mass': 0.7889}, 'zm_floor': {'share_no_atom_in_source': 0.0103, 'share_target_below_source_ignored': 0.0, 'share_target_clipped': 0.0, 'mean_target': 0.826, 'mean_source_zero_mass': 0.7889}, 'zm_climatology': {'share_no_atom_in_source': 0.0103, 'share_target_below_source_ignored': 0.3413, 'share_target_clipped': 0.0769, 'mean_target': 0.8192, 'mean_source_zero_mass': 0.7889}, 'zm_over': {'share_no_atom_in_source': 0.0103, 'share_target_below_source_ignored': 0.219, 'share_target_clipped': 0.5761, 'mean_target': 0.8541, 'mean_source_zero_mass': 0.7889}}

### Per-leg calibration (the story must not buy the atom by wrecking the parts)

- priced legs ['passing_yards', 'passing_tds', 'passing_interceptions', 'rushing_yards', 'rushing_tds', 'receptions', 'receiving_yards', 'receiving_tds', 'fumbles_lost', 'two_pt']
- read for the SELECTED arm `zm_floor`: summed CRPS served 35.98029 → recalibrated 36.11938 (relative change 0.003866, tolerance 0.0)
- by arm: {'zm_conditional': 0.016051, 'zm_floor': 0.003748, 'zm_climatology': 0.540005, 'zm_over': 0.051243}

### ⭐ Where the per-leg effect lands — the availability decomposition (arm `zm_floor`)

**`NON_MONOTONE`** — 6 sign changes — the effect is not a single crossover in availability, so a successor conditioning on a single π̂ threshold would be mis-specified

> positive = the recalibration IMPROVED that availability bucket. Buckets are FIXED absolute π̂ edges (never per-fold quantiles), pooled as Σsums/Σcounts so the 8-fold figure is a row-pooled mean (NF1.8). A bucket below 30 rows reports None and can never supply a crossover.

| π̂ bucket | rows | pooled Δ (priced legs, per row) |
|---|---|---|
| 0.0–0.1 | 1324 | -0.16 |
| 0.1–0.2 | 916 | 0.17667 |
| 0.2–0.3 | 480 | -0.48918 |
| 0.3–0.4 | 264 | 0.26629 |
| 0.4–0.5 | 176 | -0.08543 |
| 0.5–0.6 | 128 | -0.88575 |
| 0.6–0.7 | 102 | 3.07158 |
| 0.7–0.8 | 123 | -2.62092 |
| 0.8–0.9 | 173 | -2.18232 |
| 0.9–1.0 | 1799 | -0.02968 |

- crossovers: [{'between_buckets': [0.0, 0.2], 'pi_hat': 0.0975, 'direction': 'hurts_below_helps_above', 'delta_below': -0.16, 'delta_above': 0.17667}, {'between_buckets': [0.1, 0.3], 'pi_hat': 0.1765, 'direction': 'helps_below_hurts_above', 'delta_below': 0.17667, 'delta_above': -0.48918}, {'between_buckets': [0.2, 0.4], 'pi_hat': 0.3148, 'direction': 'hurts_below_helps_above', 'delta_below': -0.48918, 'delta_above': 0.26629}, {'between_buckets': [0.3, 0.5], 'pi_hat': 0.4257, 'direction': 'helps_below_hurts_above', 'delta_below': 0.26629, 'delta_above': -0.08543}, {'between_buckets': [0.5, 0.7], 'pi_hat': 0.5724, 'direction': 'hurts_below_helps_above', 'delta_below': -0.88575, 'delta_above': 3.07158}, {'between_buckets': [0.6, 0.8], 'pi_hat': 0.704, 'direction': 'helps_below_hurts_above', 'delta_below': 3.07158, 'delta_above': -2.62092}]
- pooled Δ over all buckets: -0.14274
- state by arm: {'zm_conditional': 'NON_MONOTONE', 'zm_floor': 'NON_MONOTONE', 'zm_climatology': 'CROSSES', 'zm_over': 'ALL_NEGATIVE'}
- crossover π̂ by arm: {'zm_conditional': [0.106, 0.1681, 0.3399, 0.3698, 0.5826, 0.6912], 'zm_floor': [0.0975, 0.1765, 0.3148, 0.4257, 0.5724, 0.704], 'zm_climatology': [0.4553], 'zm_over': []}
- state by priced leg: {'passing_yards': 'NON_MONOTONE', 'passing_tds': 'ALL_POSITIVE', 'passing_interceptions': 'CROSSES', 'rushing_yards': 'NON_MONOTONE', 'rushing_tds': 'UNDEFINED', 'receptions': 'UNDEFINED', 'receiving_yards': 'UNDEFINED', 'receiving_tds': 'UNDEFINED', 'fumbles_lost': 'ALL_POSITIVE', 'two_pt': 'UNDEFINED'}

### ⭐ Channel attribution (paired per-fold deltas, not ranks)

> each entry is (foil − winner) per fold, so POSITIVE means the winner is better. A channel whose paired delta is indistinguishable from zero did not act, regardless of where either arm ranks (NF-D20 — count whether the mechanism could act before crediting it).

| channel | foil | Δ (foil − winner) | CI95 | folds | p |
|---|---|---|---|---|---|
| `recalibration_channel` | `mixall_learned` | 0.01839 | [0.00322, 0.03357] | 6/8 | 0.0121 |
| `availability_derived_target_channel` | `zm_climatology` | 1.18708 | [1.09707, 1.2771] | 8/8 | 0.0 |
| `split_channel_on_served_marginals` | `single_copula` | 0.00641 | [0.00554, 0.00727] | 8/8 | 0.0 |

### ⭐ Per-fold series (the anchors are scored on every fold)

| fold | `zm_floor` | `mixall_learned` | `single_copula` | `nihilist_zero` | `zero_width` | `max_width` | `assembled_comonotone` | `permuted_direct` | `zm_permuted` | `oracle__zm_floor` | `matched_n__zm_floor` |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022H1 | 2.4195 | 2.4569 | 2.4629 | 6.613 | 7.8971 | 10.57 | 2.5958 | 4.8341 | 4.67 | 2.1331 | 2.531 |
| 2022H2 | 2.5623 | 2.6005 | 2.6061 | 6.3267 | 7.6154 | 10.4064 | 2.7168 | 4.5991 | 4.2671 | 2.1454 | 2.6622 |
| 2023H1 | 2.4174 | 2.439 | 2.4456 | 6.4948 | 7.743 | 10.4554 | 2.5639 | 4.7064 | 4.2679 | 2.1514 | 2.4803 |
| 2023H2 | 2.5895 | 2.5799 | 2.5854 | 6.2957 | 7.6835 | 10.33 | 2.6663 | 4.5655 | 4.1797 | 2.2442 | 2.6602 |
| 2024H1 | 2.3973 | 2.4245 | 2.4313 | 6.5662 | 7.709 | 10.4029 | 2.5978 | 4.7321 | 4.3552 | 2.062 | 2.4691 |
| 2024H2 | 2.8222 | 2.8152 | 2.8208 | 6.9333 | 8.2279 | 10.5596 | 2.8976 | 5.0393 | 4.5662 | 2.4773 | 2.8258 |
| 2025H1 | 2.6988 | 2.7227 | 2.7295 | 6.9527 | 8.201 | 10.5595 | 2.8315 | 4.9718 | 4.5402 | 2.3364 | 2.7811 |
| 2025H2 | 2.609 | 2.6242 | 2.6327 | 6.1409 | 7.6796 | 10.2751 | 2.694 | 4.5011 | 4.3402 | 2.271 | 2.6705 |

PIT (max-decile deviation) per fold — bar 0.05:

| fold | `zm_floor` | `mixall_learned` | `single_copula` | `nihilist_zero` | `zero_width` | `max_width` | `assembled_comonotone` |
|---|---|---|---|---|---|---|---|
| 2022H1 | 0.0172 | 0.0528 | 0.0558 | 0.4015 | 0.5291 | 0.7724 | 0.0721 |
| 2022H2 | 0.0343 | 0.0562 | 0.0547 | 0.3993 | 0.5438 | 0.7715 | 0.0562 |
| 2023H1 | 0.0245 | 0.0493 | 0.0552 | 0.3993 | 0.5398 | 0.7536 | 0.0479 |
| 2023H2 | 0.0338 | 0.0648 | 0.0662 | 0.4028 | 0.5366 | 0.762 | 0.0563 |
| 2024H1 | 0.0226 | 0.0489 | 0.0518 | 0.4139 | 0.5277 | 0.7555 | 0.046 |
| 2024H2 | 0.0317 | 0.0731 | 0.0672 | 0.4089 | 0.5376 | 0.7402 | 0.0438 |
| 2025H1 | 0.0311 | 0.0833 | 0.0818 | 0.4067 | 0.5379 | 0.7197 | 0.0624 |
| 2025H2 | 0.0298 | 0.0897 | 0.084 | 0.3879 | 0.5633 | 0.7659 | 0.0655 |

- winner clears the PIT bar on 8/8 folds ([True, True, True, True, True, True, True, True])
- the reproduced incumbent clears it on 0/8 ([False, False, False, False, False, False, False, False])
- priced-leg relative change by fold: [-0.01249, -0.003508, 0.007389, 0.018102, 0.003166, 0.01418, -0.002869, 0.006013]
- atom cap by fold — served [0.2789, 0.2736, 0.2717, 0.2684, 0.2638, 0.2621, 0.265, 0.2658] → recalibrated [0.5656, 0.5576, 0.557, 0.5504, 0.544, 0.5328, 0.5346, 0.5431]

### The premise, measured — per-leg predicted vs realized zero mass (last fold)

| leg | predicted P(0) | realized P(0) | gap | AFTER re-splice | gap after |
|---|---|---|---|---|---|
| `attempts` | 0.55 | 0.5378 | -0.0122 | 0.7134 | -0.1756 |
| `passing_yards` | 0.2983 | 0.5563 | 0.2581 | 0.5461 | 0.0102 |
| `passing_tds` | 0.6825 | 0.7019 | 0.0193 | 0.7263 | -0.0245 |
| `passing_interceptions` | 0.7944 | 0.7874 | -0.0069 | 0.8119 | -0.0245 |
| `carries` | 0.517 | 0.5649 | 0.0479 | 0.6142 | -0.0493 |
| `rushing_yards` | 0.6257 | 0.6505 | 0.0248 | 0.6913 | -0.0408 |
| `rushing_tds` | 0.9372 | 0.9401 | 0.0029 | 0.9532 | -0.0131 |
| `targets` | 0.985 | 0.9843 | -0.0007 | 0.9898 | -0.0055 |
| `receptions` | 0.99 | 0.99 | 0.0 | 0.9923 | -0.0023 |
| `receiving_yards` | 0.99 | 0.9943 | 0.0043 | 0.9926 | 0.0017 |
| `receiving_tds` | 0.995 | 0.9986 | 0.0036 | 0.995 | 0.0036 |
| `fumbles_lost` | 0.9233 | 0.9272 | 0.004 | 0.9386 | -0.0114 |
| `two_pt` | 0.9677 | 0.9729 | 0.0052 | 0.9757 | -0.0028 |

- binding-leg share, SERVED: {'attempts': 0.2634, 'carries': 0.022, 'passing_tds': 0.0005, 'passing_yards': 0.7091, 'rushing_yards': 0.0049}
- binding-leg share, RECALIBRATED: {'attempts': 0.5724, 'carries': 0.0031, 'passing_yards': 0.4245}

### Anchors

- degenerates (CRPS): {'nihilist_zero': 6.5404, 'zero_width': 7.8446, 'max_width': 10.4448, 'assembled_comonotone': 2.6954}
- degenerates (PIT — printed every run so the bar can never become a selection criterion, NF1.8): {'nihilist_zero': 0.4025, 'zero_width': 0.5395, 'max_width': 0.7551, 'assembled_comonotone': 0.0563}
- oracle states: {'zm_conditional': 'RESPECTED', 'zm_floor': 'RESPECTED', 'zm_climatology': 'RESPECTED', 'zm_over': 'RESPECTED'}
- permutations: {'permuted_direct_lift_vs_foil_mean': -2.1608, 'permuted_direct_lift_p_one_sided': 1.0, 'zm_permuted_lift_vs_foil_mean': -1.8154, 'zm_permuted_lift_p_one_sided': 1.0}
- reproduction — incumbent {'reproduces': True, 'n_folds_compared': 8, 'max_abs_gap': 0.0, 'tolerance': 1e-09, 'per_fold_abs_gap': {'2022H1': 0.0, '2022H2': 0.0, '2023H1': 0.0, '2023H2': 0.0, '2024H1': 0.0, '2024H2': 0.0, '2025H1': 0.0, '2025H2': 0.0}}
- reproduction — predecessor {'mixall_learned': {'reproduces': True, 'n_folds_compared': 8, 'max_abs_gap': 0.0, 'tolerance': 1e-09, 'per_fold_abs_gap': {'2022H1': 0.0, '2022H2': 0.0, '2023H1': 0.0, '2023H2': 0.0, '2024H1': 0.0, '2024H2': 0.0, '2025H1': 0.0, '2025H2': 0.0}}}

### Null state: `CONSTRAINT_REFUSED`

the null rests on BOTH statistical checks ['dsr_ok'] and anchor/registration clauses ['per_leg_calibration_not_degraded']. The anchor half is not rescuable by data, so it BINDS: more folds could clear the statistical half and the ship would still be refused ⇒ no fold/season trigger is published (NF-D18). The statistical shortfall is recorded below and the instrument's own reading is kept verbatim in `instrument_verdict` for audit. The mechanism: recalibrating the QB legs' zero mass raises the marginal-admissible atom cap and un-clamps the availability split, moving the assembled predictive in the modelled direction — but the residual is no longer the atom the marginals forbid. What remains is either the SHAPE of the conditional-on-playing law (a Gaussian copula still has zero tail dependence among the played rows) or the availability probability's own resolution, and neither is a zero-mass question.

- failing anchor/registration clauses: ['per_leg_calibration_not_degraded']
- failing statistical checks: ['dsr_ok']
- binding half: anchor
- instrument's own reading (kept verbatim for audit): {'state': 'DSR_UNREACHABLE', 'reason': "`nf_w7f_qb_marginal|QB`: the winner's per-fold Sharpe 1.013 sits at or BELOW the 4-arm field's deflated benchmark SR0 5.482, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, PRE-REGISTERED field, not more seasons — and ⛔ only if such a field was pre-registered; this is NOT a licence to re-cut a field you have already scored (MH2.7). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.", 'retest_trigger': 'field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)'}
- retest trigger: None
- `field_remedy_admissible`: None
- declared field size source: fp_qb_marginal_calibration.REAL_ARMS, committed in ablation_results/nf_w7f_preregistration.md §3 before any score

## Promote blockers

- NF-W7f is DEPLOY-HELD: the QB marginal recalibration is an NF-G0 challenger and is served by nothing until governance promotes it
- ⛔ QB ONLY. This record certifies NOTHING about RB/WR/TE — they were not scored. NF-W8's four-position optimizer input additionally requires an RB certificate, which is a separate story; and NF-W7c §4 / NF-W7e's scope rule still binds: a per-position-certified distribution may not feed a CROSS-POSITION ranking until every compared position is on the same generator and the same level recalibration
- the recalibration CHANGES NF-W6d certified cells' marginals — a consumer reading the 52-cell substrate directly is reading the SERVED cells, not these; nothing here re-serves W6d
- NF-W7c's promote blockers are INHERITED in full: an assembled row whose `source` is not `bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league prices, and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap
- a ship here does NOT re-open NF-W4's Layer B: availability enters as a component of the predictive's draw law and of its marginals' atom, never as a feature injected into a point/quantile learner
- the recalibration is certified on the NF-W7c fold axis under the declared gate league — a league or a position outside that certification is not covered by this record
