# NF-W7h — the RB MARGINAL-layer zero-mass recalibration (NULL)

Generated 2026-08-18T03:14:59.402248+00:00 · gate position **RB** · gate league **full_ppr** · 8 folds · target `league_fantasy_points` · ranked on `crps_q199` · gated on `randomized_pit_max_decile_dev`

⚖️ `best_alpha = 0` · **DEPLOY-HELD** · NF-G0 challenger. Joint construction held FIXED at `mix_played` (NF-W7d's registered primary — RB's CRPS-best construction on record, ⛔ NOT NF-W7e's `mixall_learned`, which NF-W7e measured as BEATEN at RB) — the declared family varies the per-leg zero-mass TARGET and nothing else.

> ⛔ RB ONLY — QB/WR/TE were NOT scored here and this record certifies nothing about them (NF1.7 (a)). NF-W8's four-position optimizer input is a CROSS-POSITION ranking, so an RB certificate alone does not unblock it (NF-W7c §4).

> ⭐ **RB IS NOT A RE-RUN OF NF-W7f.** NF-W7e recorded RB's assembled PIT at **0.0242** against the 0.05 bar — it ALREADY CLEARS, where QB's 0.0640 did not. So the registered question is not *does the recalibration repair RB's calibration* (there is nothing to repair) but *does removing the marginal-admissibility constraint improve RB's PROPER SCORE while HOLDING that calibration*. The verdict rule below has five states, including `RB_CALIBRATION_DAMAGED`, which QB's rule structurally cannot express.

## RB verdict

**`RB_RECALIBRATION_PAYS`** — the cap was lifted, RB's assembled PIT still clears the bar, and the winner beats BOTH contest foils — the marginal layer was a live constraint on RB's proper score (deploy-held, NF-G0 challenger)

> **Certified for NF-W8: NO** — certified for NF-W8 ONLY on RB_RECALIBRATION_PAYS with the FULL gate green (prereg §7); the state alone is a mechanism reading, never a certificate. This run's full gate: NOT green.

| quantity | value |
|---|---|
| atom cap, SERVED marginals (NF-W7e recorded, RB) | 0.3018 |
| atom cap, RECALIBRATED | 0.4182 |
| cap lift (required ≥ 0.0341) | 0.1164 |
| — the floor's derivation | realized all-zero rate 0.3359 − NF-W7e's recorded RB atom cap 0.3018: the recalibration has turned the knob iff the recalibrated cap reaches the atom the population actually exhibits |
| installed atom | 0.3286 |
| realized all-zero rate | 0.3359 |
| shortfall (realized − installed) | 0.0073 |
| clamp binding SHARE (was 0.4184) | 0.4184 ⚠️ a share is not a magnitude — see the next row |
| clamp mean UPWARD MOVE on π̂ (the magnitude) | 0.00103 |
| PIT: best arm | `zm_floor` 0.0245 vs bar 0.05 |
| PIT: matched foil (`mix_played`) | 0.0242 |
| PIT: already cleared BEFORE this story (NF-W7e) | 0.0242 |
| PIT moved by the recalibration | 0.0099 |
| winner beats BOTH contest foils | True |

**Which NF-W6d cell caps the atom** (share of rows attaining the row-wise `min_j P̂_j(0)`):

- SERVED: `{'carries': 0.3986, 'receiving_yards': 0.3025, 'receptions': 0.0094, 'rushing_yards': 0.155, 'targets': 0.1345}`

## RB — winner `zm_floor` vs best contest foil `mix_played`

Δ`crps_q199` **0.0218** (CI95 [0.0152, 0.0283], 8/8 folds) · PBO 0.0 · DSR 0.0 · p 0.0001 · coverage(80) 0.8679 (floor 0.8) · PIT 0.0245 (bar 0.05)

**Gate: NO** — beats_foil ✅, fold_consistency ✅, pbo_ok ✅, dsr_ok ❌, fdr_ok ✅, coverage_floor_ok ✅, pit_flat_ok ✅, degenerates_lose ✅, permutation_behaves ✅, oracle_floors_respected ✅, mixture_is_active ✅, mixture_preserves_marginals ✅, incumbent_reproduces ✅, predecessor_reproduces ✅, zero_mass_hits_target ✅, positive_law_preserved ✅, matched_foil_identity ✅, cap_was_lifted ✅, per_leg_calibration_not_degraded ✅, independence_under_disperses ✅, dependence_moves_coverage ✅, beats_indep_on_coverage ✅

### Attribution (the reported 2×2: marginals × availability split)

| contrast | Δ |
|---|---|
| recalibration_with_split | 0.0218 |
| recalibration_without_split | -0.1085 |
| recalibration_with_split__PRIMARY_ARM_MATCHED | -0.1087 |
| recalibration_with_split__ARM | zm_floor |
| recalibration_without_split__ARM | zm_conditional |
| split_at_fixed_sigma_played | 0.0161 |
| vs_incumbent_construction_BUNDLED | 0.0117 |
| vs_incumbent | 0.0335 |
| delta_vs_indep | 0.1059 |
| beats_direct_points_REPORT_ONLY | False |
| delta_vs_direct_points_REPORT_ONLY | -0.0263 |

> ⚠️ `vs_incumbent_construction_BUNDLED` differs in the SPLIT **and** the Σ population, because RB's pinned construction estimates Σ on ACTIVE rows while the incumbent uses all rows. `split_at_fixed_sigma_played` is the clean split channel here (the §12 pre-score amendment).

> ⛔ **`recalibration_with_split` and `recalibration_without_split` are NOT a matched pair** — the first is measured on the SELECTED arm (`zm_floor`), the second only on the PRIMARY arm (`zm_conditional`), so differencing them attributes to the SPLIT what belongs to the TARGET. Matched on the primary target, the recalibration channel is **-0.1087** WITH the split against **-0.1085** without it — i.e. essentially unchanged, so the split does NOT modulate the recalibration; the TARGET does.

### Mean CRPS by label

| label | crps_q199 | PIT |
|---|---|---|
| `oracle__foil_direct_points` | 1.4933 | — |
| `oracle__zm_floor` | 2.2403 | — |
| `oracle__zm_over` | 2.355 | — |
| `oracle__zm_conditional` | 2.3599 | — |
| `foil_direct_points` | 2.4692 | 0.1222 |
| `zm_floor` | 2.4956 | 0.0245 |
| `mix_played` | 2.5173 | 0.0242 |
| `matched_n__zm_floor` | 2.5176 | — |
| `single_copula` | 2.529 | 0.0257 |
| `mix_off` | 2.5335 | 0.03 |
| `assembled_indep` | 2.6015 | 0.0862 |
| `zm_conditional` | 2.626 | 0.0341 |
| `zm_cond_copula` | 2.6375 | 0.0308 |
| `assembled_comonotone` | 2.6442 | 0.0363 |
| `matched_n__zm_conditional` | 2.6449 | — |
| `zm_over` | 2.6679 | 0.0901 |
| `matched_n__zm_over` | 2.6957 | — |
| `oracle__zm_climatology` | 2.9584 | — |
| `matched_n__zm_climatology` | 2.9954 | — |
| `zm_climatology` | 3.0244 | 0.0456 |
| `zm_permuted` | 3.2723 | 0.079 |
| `permuted_direct` | 3.801 | — |
| `nihilist_zero` | 5.5948 | 0.5724 |
| `zero_width` | 5.8589 | 0.5465 |
| `max_width` | 7.1397 | 0.3228 |

### The transform's measured identities

- `zero_mass_hits_target`: max gap 0.0 (tol 1e-12)
- `positive_law_preserved`: max drift / resolution bound 0.914573 (tol ≤ 1.0; evaluated True) — {'max_probability_drift': 0.080402, 'mean_probability_drift': 0.00261, 'max_resolution_bound': 0.181818, 'max_drift_over_bound': 0.819095, 'evaluable_cell_share': 0.4625, 'min_conditional_knots': 10, 'tolerance_ratio': 1.0, 'evaluated': True, 'holds': True}
- `matched_foil_identity` (re-splice to own atom is a no-op through `draw_legs`): max draw gap 0.0
- resplice edges (last fold): {'zm_conditional': {'share_no_atom_in_source': 0.0, 'share_target_below_source_ignored': 0.3733, 'share_target_clipped': 0.3354, 'mean_target': 0.7805, 'mean_source_zero_mass': 0.7829}, 'zm_floor': {'share_no_atom_in_source': 0.0, 'share_target_below_source_ignored': 0.0, 'share_target_clipped': 0.0, 'mean_target': 0.7899, 'mean_source_zero_mass': 0.7829}, 'zm_climatology': {'share_no_atom_in_source': 0.0, 'share_target_below_source_ignored': 0.3489, 'share_target_clipped': 0.3077, 'mean_target': 0.7852, 'mean_source_zero_mass': 0.7829}, 'zm_over': {'share_no_atom_in_source': 0.0, 'share_target_below_source_ignored': 0.2129, 'share_target_clipped': 0.4949, 'mean_target': 0.8196, 'mean_source_zero_mass': 0.7829}}

### Per-leg calibration — the FORWARD-decided materiality clause

> The gating question was resolved FIRST (prereg §6.1): the served paid stat line does **not** derive from these cells — every consumer of the W6d substrate is a research runner or a test, and the board's `STAT_FIELD` payload comes from `season_projection.py`. So the clause cannot be defended as protecting a served surface; it stays a HARD GATE for its scientific job (a story may not buy the assembled atom by wrecking the parts), with a MATERIALITY threshold from a design quantity. ⭐ Applied to NF-W7f's own recorded QB numbers the relaxed rule STILL REFUSES QB (0.3866% observed against a 0.0712% bar), so it rescues nothing.

- priced legs ['passing_yards', 'passing_tds', 'passing_interceptions', 'rushing_yards', 'rushing_tds', 'receptions', 'receiving_yards', 'receiving_tds', 'fumbles_lost', 'two_pt']
- read for the SELECTED arm `zm_floor`: summed CRPS served 18.03311 → recalibrated 17.72818 (relative change -0.016909)
- the arm's own claimed effect, relative: 0.00864577 ⇒ materiality bar 0.00086458 (0.1 × the claimed effect)
- degraded on 0/8 folds [-0.016295, -0.01361, -0.016779, -0.018969, -0.01584, -0.013328, -0.019707, -0.021059]
- **verdict `IMPROVED`** (holds=True, evaluated=True) — the priced legs' summed CRPS IMPROVED by 0.016909 relative — the recalibration did not buy the atom by wrecking the parts
- by arm: {'zm_conditional': -0.013101, 'zm_floor': -0.016948, 'zm_climatology': 0.118378, 'zm_over': -0.004235}

### ⭐ Where the per-leg effect lands — the availability decomposition (arm `zm_floor`)

**`NON_MONOTONE`** — 4 sign changes — the effect is not a single crossover in availability, so a successor conditioning on a single π̂ threshold would be mis-specified

> positive = the recalibration IMPROVED that availability bucket. Buckets are FIXED absolute π̂ edges (never per-fold quantiles), pooled as Σsums/Σcounts so the 8-fold figure is a row-pooled mean (NF1.8). A bucket below 30 rows reports None and can never supply a crossover.

| π̂ bucket | rows | pooled Δ (priced legs, per row) |
|---|---|---|
| 0.0–0.1 | 169 | 1.72206 |
| 0.1–0.2 | 697 | 1.59555 |
| 0.2–0.3 | 722 | 1.14101 |
| 0.3–0.4 | 682 | 0.52097 |
| 0.4–0.5 | 546 | 0.06403 |
| 0.5–0.6 | 528 | -0.03184 |
| 0.6–0.7 | 547 | 0.03674 |
| 0.7–0.8 | 547 | -0.04626 |
| 0.8–0.9 | 846 | 0.02592 |
| 0.9–1.0 | 3307 | 0.00071 |

- crossovers: [{'between_buckets': [0.4, 0.6], 'pi_hat': 0.5168, 'direction': 'helps_below_hurts_above', 'delta_below': 0.06403, 'delta_above': -0.03184}, {'between_buckets': [0.5, 0.7], 'pi_hat': 0.5964, 'direction': 'hurts_below_helps_above', 'delta_below': -0.03184, 'delta_above': 0.03674}, {'between_buckets': [0.6, 0.8], 'pi_hat': 0.6943, 'direction': 'helps_below_hurts_above', 'delta_below': 0.03674, 'delta_above': -0.04626}, {'between_buckets': [0.7, 0.9], 'pi_hat': 0.8141, 'direction': 'hurts_below_helps_above', 'delta_below': -0.04626, 'delta_above': 0.02592}]
- pooled Δ over all buckets: 0.30491
- state by arm: {'zm_conditional': 'NON_MONOTONE', 'zm_floor': 'NON_MONOTONE', 'zm_climatology': 'NON_MONOTONE', 'zm_over': 'CROSSES'}
- state by priced leg: {'passing_yards': 'UNDEFINED', 'passing_tds': 'UNDEFINED', 'passing_interceptions': 'UNDEFINED', 'rushing_yards': 'NON_MONOTONE', 'rushing_tds': 'ALL_POSITIVE', 'receptions': 'NON_MONOTONE', 'receiving_yards': 'ALL_POSITIVE', 'receiving_tds': 'UNDEFINED', 'fumbles_lost': 'UNDEFINED', 'two_pt': 'UNDEFINED'}

### ⭐ Channel attribution (paired per-fold deltas, not ranks)

> each entry is (foil − arm) per fold, so POSITIVE means the arm is better. A channel whose paired delta is indistinguishable from zero did not act, regardless of where either arm ranks (NF-D20 — count whether the mechanism could act before crediting it).

| channel | foil | Δ (foil − arm) | CI95 | folds | p |
|---|---|---|---|---|---|
| `recalibration_channel` | `mix_played` | 0.02176 | [0.01519, 0.02834] | 8/8 | 0.0001 |
| `availability_derived_target_channel` | `zm_climatology` | 0.52881 | [0.48352, 0.5741] | 8/8 | 0.0 |
| `split_channel_at_fixed_sigma_played` | `mix_off` | 0.01613 | [0.01372, 0.01854] | 8/8 | 0.0 |

### ⭐ Per-fold series (the anchors are scored on every fold)

| fold | `zm_floor` | `mix_played` | `single_copula` | `nihilist_zero` | `zero_width` | `max_width` | `assembled_comonotone` | `permuted_direct` | `zm_permuted` | `oracle__zm_floor` | `matched_n__zm_floor` |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022H1 | 2.6091 | 2.6314 | 2.6399 | 5.5725 | 5.9474 | 7.1794 | 2.7432 | 3.8177 | 3.2622 | 2.3249 | 2.642 |
| 2022H2 | 2.4346 | 2.4495 | 2.4593 | 5.362 | 5.6493 | 7.0356 | 2.5778 | 3.6586 | 3.1798 | 2.1801 | 2.4602 |
| 2023H1 | 2.4759 | 2.492 | 2.5057 | 5.4307 | 5.6065 | 7.0779 | 2.6141 | 3.6424 | 3.3065 | 2.2072 | 2.5063 |
| 2023H2 | 2.4701 | 2.5002 | 2.5132 | 5.6838 | 5.8947 | 7.1421 | 2.6377 | 3.8348 | 3.224 | 2.1924 | 2.469 |
| 2024H1 | 2.6213 | 2.6434 | 2.655 | 5.8326 | 6.1094 | 7.2111 | 2.7768 | 3.9112 | 3.4702 | 2.3608 | 2.6453 |
| 2024H2 | 2.4885 | 2.4978 | 2.5087 | 5.6164 | 5.8165 | 7.1286 | 2.6282 | 3.8526 | 3.2622 | 2.2083 | 2.5144 |
| 2025H1 | 2.4153 | 2.4463 | 2.4597 | 5.5386 | 5.9262 | 7.1415 | 2.5644 | 3.802 | 3.2004 | 2.2021 | 2.4531 |
| 2025H2 | 2.4498 | 2.4782 | 2.4908 | 5.7222 | 5.9211 | 7.2013 | 2.6117 | 3.8887 | 3.2731 | 2.2466 | 2.4504 |

PIT (max-decile deviation) per fold — bar 0.05:

| fold | `zm_floor` | `mix_played` | `single_copula` | `nihilist_zero` | `zero_width` | `max_width` | `assembled_comonotone` |
|---|---|---|---|---|---|---|---|
| 2022H1 | 0.0236 | 0.027 | 0.0323 | 0.5385 | 0.5377 | 0.3529 | 0.0243 |
| 2022H2 | 0.0199 | 0.0215 | 0.0197 | 0.5895 | 0.5571 | 0.3221 | 0.0298 |
| 2023H1 | 0.023 | 0.0177 | 0.0243 | 0.5831 | 0.5528 | 0.3078 | 0.0466 |
| 2023H2 | 0.0208 | 0.021 | 0.0182 | 0.5736 | 0.5356 | 0.3167 | 0.038 |
| 2024H1 | 0.0328 | 0.0229 | 0.0248 | 0.5667 | 0.5397 | 0.3262 | 0.0337 |
| 2024H2 | 0.0171 | 0.018 | 0.0239 | 0.5868 | 0.5624 | 0.3078 | 0.0424 |
| 2025H1 | 0.0209 | 0.0379 | 0.0313 | 0.5638 | 0.5554 | 0.3256 | 0.0299 |
| 2025H2 | 0.0381 | 0.0279 | 0.0312 | 0.5774 | 0.5312 | 0.3233 | 0.0455 |

- winner clears the PIT bar on 8/8 folds ([True, True, True, True, True, True, True, True])
- ⭐ the MATCHED FOIL (what RB already had) clears it on 8/8 ([True, True, True, True, True, True, True, True]) — at RB the question is whether the recalibration KEEPS this, not whether it wins it
- the reproduced incumbent clears it on 8/8 ([True, True, True, True, True, True, True, True])
- priced-leg relative change by fold: [-0.016295, -0.01361, -0.016779, -0.018969, -0.01584, -0.013328, -0.019707, -0.021059]
- atom cap by fold — served [0.2982, 0.3116, 0.304, 0.2946, 0.2955, 0.3005, 0.3038, 0.3058] → recalibrated [0.4161, 0.4273, 0.4234, 0.4067, 0.4174, 0.4105, 0.4194, 0.4248]

### The premise, measured — per-leg predicted vs realized zero mass (last fold)

> §0.2 of the pre-registration predicted, off a 126-row serving proof, that RB's CONTINUOUS cells OVER-price their zero (gap < 0) and that the RAISE-ONLY splice therefore cannot reach them. This is the same table at FOLD SCALE — it is free to overturn that prediction, and what it says is the finding.

| leg | predicted P(0) | realized P(0) | gap | AFTER re-splice | gap after |
|---|---|---|---|---|---|
| `attempts` | 0.995 | 0.9972 | 0.0022 | 0.995 | 0.0022 |
| `passing_yards` | 0.995 | 1.0 | 0.005 | 0.995 | 0.005 |
| `passing_tds` | 0.995 | 1.0 | 0.005 | 0.995 | 0.005 |
| `passing_interceptions` | 0.995 | 1.0 | 0.005 | 0.995 | 0.005 |
| `carries` | 0.42 | 0.3928 | -0.0272 | 0.4542 | -0.0614 |
| `rushing_yards` | 0.4327 | 0.4113 | -0.0214 | 0.4776 | -0.0663 |
| `rushing_tds` | 0.8622 | 0.8494 | -0.0128 | 0.8995 | -0.0502 |
| `targets` | 0.4585 | 0.5065 | 0.048 | 0.5163 | -0.0098 |
| `receptions` | 0.5481 | 0.5518 | 0.0037 | 0.5945 | -0.0427 |
| `receiving_yards` | 0.56 | 0.5786 | 0.0186 | 0.6523 | -0.0737 |
| `receiving_tds` | 0.9599 | 0.9584 | -0.0015 | 0.9688 | -0.0104 |
| `fumbles_lost` | 0.9681 | 0.976 | 0.0079 | 0.9767 | -0.0008 |
| `two_pt` | 0.9888 | 0.9898 | 0.001 | 0.9924 | -0.0026 |

- binding-leg share, SERVED: {'carries': 0.3986, 'receiving_yards': 0.3025, 'receptions': 0.0094, 'rushing_yards': 0.155, 'targets': 0.1345}
- binding-leg share, RECALIBRATED: {'carries': 0.7148, 'receiving_yards': 0.0465, 'receptions': 0.0019, 'rushing_yards': 0.0739, 'targets': 0.163}

### Anchors

- degenerates (CRPS): {'nihilist_zero': 5.5948, 'zero_width': 5.8589, 'max_width': 7.1397, 'assembled_comonotone': 2.6442}
- degenerates (PIT — printed every run so the bar can never become a selection criterion, NF1.8): {'nihilist_zero': 0.5724, 'zero_width': 0.5465, 'max_width': 0.3228, 'assembled_comonotone': 0.0363}
- oracle states (one per FORM, at matched n — NF-D16 (g‴)): {'zm_conditional': 'RESPECTED', 'zm_floor': 'RESPECTED', 'zm_climatology': 'RESPECTED', 'zm_over': 'RESPECTED'}
- permutations: {'permuted_direct_lift_vs_foil_mean': -1.2837, 'permuted_direct_lift_p_one_sided': 1.0, 'zm_permuted_lift_vs_foil_mean': -0.755, 'zm_permuted_lift_p_one_sided': 1.0}
- reproduction — incumbent {'reproduces': True, 'n_folds_compared': 8, 'max_abs_gap': 0.0, 'tolerance': 1e-09, 'per_fold_abs_gap': {'2022H1': 0.0, '2022H2': 0.0, '2023H1': 0.0, '2023H2': 0.0, '2024H1': 0.0, '2024H2': 0.0, '2025H1': 0.0, '2025H2': 0.0}}
- reproduction — predecessor {'mix_played': {'reproduces': True, 'n_folds_compared': 8, 'max_abs_gap': 0.0, 'tolerance': 1e-09, 'per_fold_abs_gap': {'2022H1': 0.0, '2022H2': 0.0, '2023H1': 0.0, '2023H2': 0.0, '2024H1': 0.0, '2024H2': 0.0, '2025H1': 0.0, '2025H2': 0.0}}}

### Null state: `DSR_UNREACHABLE`

`nf_w7h_rb_marginal|RB`: the winner's per-fold Sharpe 2.768 sits at or BELOW the 4-arm field's deflated benchmark SR0 5.837, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, PRE-REGISTERED field, not more seasons — and ⛔ only if such a field was pre-registered; this is NOT a licence to re-cut a field you have already scored (MH2.7). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.

- failing anchor/registration clauses: None
- failing statistical checks: None
- binding half: None
- instrument's own reading (kept verbatim for audit): {'state': 'DSR_UNREACHABLE', 'reason': "`nf_w7h_rb_marginal|RB`: the winner's per-fold Sharpe 2.768 sits at or BELOW the 4-arm field's deflated benchmark SR0 5.837, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, PRE-REGISTERED field, not more seasons — and ⛔ only if such a field was pre-registered; this is NOT a licence to re-cut a field you have already scored (MH2.7). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.", 'retest_trigger': 'field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)'}
- retest trigger: field size is NOT a lever here — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)
- `field_remedy_admissible`: None — ⚠️ `None` here does NOT mean unmeasured: it means field size is NO LEVER AT ALL (`max_field < 2`, i.e. not even a 2-arm field clears), so there is nothing to be admissible about and ⛔ no field remedy may be read from this record
- declared field size source: fp_rb_marginal_calibration.REAL_ARMS, committed in ablation_results/nf_w7h_preregistration.md §3 before any score

#### ⭐ The DSR 2×2 — which lever actually binds

**`VARIANCE`** — removing the most extreme trial Sharpe collapses V but DSR still does not clear ⇒ the binding quantity is PER-FOLD NOISE in the delta, not multiplicity (NF-W7f measured exactly this: V fell 8.8× and DSR reached only 0.174). The honest lever is a LOWER-VARIANCE design — more assembly draws / a sharper metric — ⛔ NOT more seasons and ⛔ NOT a field trim. ⚠️ AND THE TRIMMED ARM IS THE WINNER ITSELF (`zm_floor`): the sub-field scored here is the declared family MINUS THE ARM UNDER TEST, which no pre-registration could ever declare, so this row is a SENSITIVITY OF V, not a registrable alternative field. ⇒ the VARIANCE reading is A FORTIORI: even after deleting V's single largest contributor — a deletion no admissible registration could make — the bar is still not reached.

- DSR on the DECLARED 4-arm field: 0.0 (bar 0.95)
- DSR on a ⛔ NON-REGISTRABLE sub-field — a V-SENSITIVITY, it deletes the arm under test (dropping the most extreme trial Sharpe, `zm_floor`): 0.9093 (moved 0.9093)
- cross-trial dispersion V: 30.775029 → 4.818793 (ratio 6.386×)
- observed SR 2.768; trial SRs [-6.243, 2.768, -10.253, -6.7]
- REPORTED as a diagnostic. The gate binds on the DECLARED 4-arm field; this row exists so the record names WHICH lever binds rather than prescribing a reflex.

| return series | declared field | ⛔ NON-REGISTRABLE sub-field — a V-SENSITIVITY, it deletes the arm under test |
|---|---|---|
| **per fold** (BINDS) | 0.0 | 0.9093 |
| per CSCV split (70 splits, REPORT-ONLY) | 0.0 | 1.0 |

> the per-FOLD series binds by pre-registration; CSCV half-splits reuse folds, so the per-SPLIT row is dependent-by-construction and INFLATED — it says whether the series DEFINITION matters (NCAAF-P2.1 measured a ~3× gap on identical folds), never what the gate decides

## Promote blockers

- NF-W7h is DEPLOY-HELD: the RB marginal recalibration is an NF-G0 challenger and is served by nothing until governance promotes it
- ⛔ RB ONLY. This record certifies NOTHING about QB/WR/TE — they were not scored (NF1.7 (a))
- ⛔ A per-position-certified distribution may NOT feed a CROSS-POSITION ranking until every compared position is on the same generator AND the same level recalibration (NF-W7c §4). NF-W8's four-position optimizer input IS a ranking, so an RB certificate alone does not unblock it — QB is calibrated but CONSTRAINT_REFUSED and TE is a GENUINE_ABSENCE
- the recalibration CHANGES NF-W6d certified cells' marginals — a consumer reading the 52-cell substrate directly is reading the SERVED cells, not these; nothing here re-serves W6d
- NF-W7c's promote blockers are INHERITED in full, and RB's labelling is materially WEAKER than QB's: NF-W7e recorded RB as `partial_default` with 7 of 10 priced stats using a NF-W6d calibrated DEFAULT — a calibrated range, not a conditional projection
- a ship here does NOT re-open NF-W4's Layer B: availability enters as a component of the predictive's draw law and of its marginals' atom, never as a feature injected into a point/quantile learner
- the recalibration is certified on the NF-W7c fold axis under the declared gate league — a league or a position outside that certification is not covered by this record
