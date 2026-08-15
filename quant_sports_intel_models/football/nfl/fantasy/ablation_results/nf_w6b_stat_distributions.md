# NF-W6b — the per-stat distributional successor (§0.5 bake-off; the CEILING-GATE[BUILD] license)

**Generated:** 2026-08-15T01:01:21+00:00 · **folds:** 8 half-season blocks (2022H1…2025H2, the NF-W1 axis verbatim) · **rows:** 84553 player-weeks · **cells:** 8

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** (research-only, no changelog). FRESH registration (MH2.2) licensed by NF-W6's CEILING-GATE[BUILD]. DoD = per-stat marginal CRPS (`crps_q199`); the assembled-PPR effect is REPORT-ONLY (PM ruling). Coverage is a FLOOR, one-sided by pre-registration (NF1.9 (e) — the zero atom makes an upper coverage gate structurally inverted); the two-sidedness lives in the sharpness degenerates. Every direction word is three-way and derived at report time, failing closed to `TIES` (NF-W2e).

**PIT gate (NF-W0a `assert_point_in_time`):** 175 weeks / 84553 records checked; 0 rows dropped.

## Verdict: **PERSTAT-BAKEOFF ship=6 null=2 of 8 cells**

per-cell verdicts (no story-level aggregation gate): SHIP ['QB|passing_tds', 'QB|passing_yards', 'QB|rushing_yards', 'RB|rushing_yards', 'TE|receiving_yards', 'WR|receiving_yards']; recorded nulls ['RB|receiving_yards', 'RB|rushing_tds']

## Per-cell contests (winner vs the BINDING champion-faithful incumbent)

| cell | winner | foil | foil CRPS | Δ | Δ% | CI95 | wins | p | PBO | DSR | BH | cov80 (floor 0.80) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| QB|passing_tds | knn_quantile | inc_head_bank | 0.382 | 0.08454 | 22.13 | [0.07955, 0.08952] | 8/8 | 0.0 | 0.0 | 0.9925 | True | 0.9484 | **SHIP** |
| QB|passing_yards | lgbm_quantile_tail | inc_head_bank | 36.96636 | 6.26714 | 16.954 | [5.8411, 6.69317] | 8/8 | 0.0 | 0.0 | 0.9837 | True | 0.7938 | **SHIP** |
| QB|rushing_yards | lgbm_hurdle_tail | inc_head_bank | 5.67586 | 1.07096 | 18.869 | [0.9981, 1.14383] | 8/8 | 0.0 | 0.0 | 0.9692 | True | 0.8268 | **SHIP** |
| RB|receiving_yards | lgbm_hurdle_tail | inc_head_bank | 6.14589 | 0.92374 | 15.03 | [0.87052, 0.97697] | 8/8 | 0.0 | 0.0 | 0.8747 | True | 0.8881 | **POWER_LIMITED** |
| RB|rushing_tds | knn_quantile | inc_climatology | 0.14964 | 0.0194 | 12.966 | [0.0169, 0.02191] | 8/8 | 0.0 | 0.0 | 0.2131 | True | 0.9537 | **POWER_LIMITED** |
| RB|rushing_yards | lgbm_hurdle_tail | inc_head_bank | 12.46804 | 1.67862 | 13.463 | [1.62683, 1.7304] | 8/8 | 0.0 | 0.0 | 1.0 | True | 0.8328 | **SHIP** |
| TE|receiving_yards | lgbm_hurdle_tail | inc_head_bank | 8.69139 | 1.23587 | 14.219 | [1.16472, 1.30702] | 8/8 | 0.0 | 0.0 | 0.9854 | True | 0.8874 | **SHIP** |
| WR|receiving_yards | lgbm_hurdle_tail | inc_head_bank | 13.73854 | 1.5778 | 11.484 | [1.48323, 1.67236] | 8/8 | 0.0 | 0.0 | 1.0 | True | 0.8578 | **SHIP** |

## Per-cell detail

### QB|passing_tds

| label              |   mean_crps |
|:-------------------|------------:|
| knn_quantile       |     0.29747 |
| lgbm_hurdle_tail   |     0.30772 |
| lgbm_quantile_tail |     0.30843 |
| inc_head_bank      |     0.38200 |
| enet_residual      |     0.38855 |
| oracle_marginal    |     0.43677 |
| inc_climatology    |     0.43763 |
| matched_marginal   |     0.43771 |
| zero_width         |     0.45298 |
| max_width          |     0.46356 |
| permuted_quantile  |     0.46752 |
| nihilist_zero      |     0.56634 |

- verdict: `knn_quantile` BEATS `inc_head_bank` by +0.0845 CRPS (CI95 [+0.0795, +0.0895] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.9484, "binding_foil_coverage_80": 0.8044, "structural_expectation": 0.9685, "n_rows": 5485, "binomial_se": 0.0054, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.6853, "winner_pred_p0": 0.6842, "binding_foil_pred_p0": 0.308, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 0.08107 vs legacy Δ 0.0857

### QB|passing_yards

| label              |   mean_crps |
|:-------------------|------------:|
| lgbm_quantile_tail |    30.69922 |
| lgbm_hurdle_tail   |    30.90886 |
| knn_quantile       |    32.43126 |
| inc_head_bank      |    36.96636 |
| enet_residual      |    40.46308 |
| zero_width         |    45.09230 |
| max_width          |    45.44400 |
| oracle_marginal    |    61.42626 |
| matched_marginal   |    61.51719 |
| inc_climatology    |    61.57652 |
| permuted_quantile  |    63.80390 |
| nihilist_zero      |    91.94152 |

- verdict: `lgbm_quantile_tail` BEATS `inc_head_bank` by +6.2671 CRPS (CI95 [+5.8411, +6.6932] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.7938, "binding_foil_coverage_80": 0.8005, "structural_expectation": 0.955, "n_rows": 5485, "binomial_se": 0.0054, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.5497, "winner_pred_p0": 0.3099, "binding_foil_pred_p0": 0.2518, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 5.94052 vs legacy Δ 6.37601

### QB|rushing_yards

| label              |   mean_crps |
|:-------------------|------------:|
| lgbm_hurdle_tail   |     4.60490 |
| lgbm_quantile_tail |     4.62478 |
| knn_quantile       |     4.88534 |
| inc_head_bank      |     5.67586 |
| enet_residual      |     5.80590 |
| oracle_marginal    |     6.39378 |
| permuted_quantile  |     6.40360 |
| matched_marginal   |     6.40997 |
| inc_climatology    |     6.43059 |
| max_width          |     6.54724 |
| zero_width         |     6.66845 |
| nihilist_zero      |     7.74121 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +1.0710 CRPS (CI95 [+0.9981, +1.1438] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.8268, "binding_foil_coverage_80": 0.7916, "structural_expectation": 0.9589, "n_rows": 5485, "binomial_se": 0.0054, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.5892, "winner_pred_p0": 0.6321, "binding_foil_pred_p0": 0.3154, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 1.11144 vs legacy Δ 1.05747

### RB|receiving_yards

| label              |   mean_crps |
|:-------------------|------------:|
| lgbm_hurdle_tail   |     5.22215 |
| lgbm_quantile_tail |     5.24795 |
| knn_quantile       |     5.31544 |
| inc_head_bank      |     6.14589 |
| oracle_marginal    |     6.50715 |
| matched_marginal   |     6.51433 |
| enet_residual      |     6.51584 |
| inc_climatology    |     6.52054 |
| permuted_quantile  |     6.64526 |
| zero_width         |     7.64631 |
| max_width          |     7.77571 |
| nihilist_zero      |     8.47395 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +0.9237 CRPS (CI95 [+0.8705, +0.9770] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": false, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.8881, "binding_foil_coverage_80": 0.8122, "structural_expectation": 0.9546, "n_rows": 8591, "binomial_se": 0.0043, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.5459, "winner_pred_p0": 0.5505, "binding_foil_pred_p0": 0.2971, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 0.89946 vs legacy Δ 0.93184
- null state: {"state": "POWER_LIMITED", "reason": "the point estimate is positive (0.92374 CRPS) and the interval excludes zero (CI95 [0.87052, 0.97697]); fold wins 8/8 vs required 6; failing statistical gates: ['dsr_ok'] \u2014 the effect is smaller than this design resolves.", "retest_trigger": "\u22652 half-season folds (\u22480 more than the current 8) at the observed per-fold Sharpe 14.509 \u2014 a LOWER bound (the deflation term is ignored); calendar-bound.", "failing_checks": ["dsr_ok"]}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": [], "ships_without_waived_checks": true}

### RB|rushing_tds

| label              |   mean_crps |
|:-------------------|------------:|
| knn_quantile       |     0.13023 |
| lgbm_hurdle_tail   |     0.13340 |
| lgbm_quantile_tail |     0.13812 |
| oracle_marginal    |     0.14949 |
| inc_climatology    |     0.14964 |
| matched_marginal   |     0.14969 |
| permuted_quantile  |     0.15992 |
| nihilist_zero      |     0.16898 |
| enet_residual      |     0.18541 |
| inc_head_bank      |     0.18987 |
| zero_width         |     0.22827 |
| max_width          |     0.23025 |

- verdict: `knn_quantile` BEATS `inc_climatology` by +0.0194 CRPS (CI95 [+0.0169, +0.0219] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": false, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.9537, "binding_foil_coverage_80": 0.9738, "structural_expectation": 0.9861, "n_rows": 8591, "binomial_se": 0.0043, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.8607, "winner_pred_p0": 0.8719, "binding_foil_pred_p0": 0.8693, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 0.01809 vs legacy Δ 0.01984
- null state: {"state": "POWER_LIMITED", "reason": "the point estimate is positive (0.0194 CRPS) and the interval excludes zero (CI95 [0.0169, 0.02191]); fold wins 8/8 vs required 6; failing statistical gates: ['dsr_ok'] \u2014 the effect is smaller than this design resolves.", "retest_trigger": "\u22652 half-season folds (\u22480 more than the current 8) at the observed per-fold Sharpe 6.474 \u2014 a LOWER bound (the deflation term is ignored); calendar-bound.", "failing_checks": ["dsr_ok"]}
- gate sensitivity (DSR waived — NF-D15 (g″)): {"waived": ["dsr_ok"], "still_refusing": [], "ships_without_waived_checks": true}

### RB|rushing_yards

| label              |   mean_crps |
|:-------------------|------------:|
| lgbm_hurdle_tail   |    10.78942 |
| lgbm_quantile_tail |    10.83935 |
| knn_quantile       |    11.28625 |
| inc_head_bank      |    12.46804 |
| enet_residual      |    12.72190 |
| zero_width         |    15.49160 |
| max_width          |    15.58349 |
| oracle_marginal    |    16.51909 |
| matched_marginal   |    16.54454 |
| inc_climatology    |    16.56600 |
| permuted_quantile  |    16.67417 |
| nihilist_zero      |    23.80749 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +1.6786 CRPS (CI95 [+1.6268, +1.7304] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.8328, "binding_foil_coverage_80": 0.8057, "structural_expectation": 0.94, "n_rows": 8591, "binomial_se": 0.0043, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.4002, "winner_pred_p0": 0.4254, "binding_foil_pred_p0": 0.2457, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 1.66738 vs legacy Δ 1.68237

### TE|receiving_yards

| label              |   mean_crps |
|:-------------------|------------:|
| lgbm_hurdle_tail   |     7.45552 |
| lgbm_quantile_tail |     7.48540 |
| knn_quantile       |     7.69837 |
| inc_head_bank      |     8.69139 |
| enet_residual      |     8.97332 |
| oracle_marginal    |    10.53348 |
| inc_climatology    |    10.54490 |
| matched_marginal   |    10.54661 |
| permuted_quantile  |    10.60686 |
| zero_width         |    10.84607 |
| max_width          |    10.87189 |
| nihilist_zero      |    14.44599 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +1.2359 CRPS (CI95 [+1.1647, +1.3070] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.8874, "binding_foil_coverage_80": 0.8026, "structural_expectation": 0.9498, "n_rows": 7649, "binomial_se": 0.0046, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.4976, "winner_pred_p0": 0.5051, "binding_foil_pred_p0": 0.2655, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 1.27319 vs legacy Δ 1.22343

### WR|receiving_yards

| label              |   mean_crps |
|:-------------------|------------:|
| lgbm_hurdle_tail   |    12.16074 |
| lgbm_quantile_tail |    12.17838 |
| knn_quantile       |    12.39133 |
| inc_head_bank      |    13.73854 |
| enet_residual      |    14.00494 |
| oracle_marginal    |    16.97976 |
| matched_marginal   |    17.00569 |
| inc_climatology    |    17.01718 |
| permuted_quantile  |    17.10886 |
| zero_width         |    17.49773 |
| max_width          |    17.69794 |
| nihilist_zero      |    25.14389 |

- verdict: `lgbm_hurdle_tail` BEATS `inc_head_bank` by +1.5778 CRPS (CI95 [+1.4832, +1.6724] excludes zero)
- gates: {"beats_foil": true, "fold_consistency": true, "pbo_ok": true, "dsr_ok": true, "fdr_ok": true, "coverage_floor_ok": true, "degenerates_lose": true, "permutation_behaves": true}
- anchors: {"nihilist_loses": true, "zero_width_loses": true, "max_width_loses": true, "winner_beats_permuted": true, "permuted_lift_not_significant": true, "winner_beats_oracle_marginal": true, "oracle_marginal_beats_matched": true}
- coverage: {"winner_coverage_80": 0.8578, "binding_foil_coverage_80": 0.8056, "structural_expectation": 0.9412, "n_rows": 12827, "binomial_se": 0.0035, "blocking_shortfall": false} (floor one-sided by prereg §2; structural expectation shown — NF1.9 (e))
- atom calibration (report-only): {"real_p0": 0.4118, "winner_pred_p0": 0.4119, "binding_foil_pred_p0": 0.2325, "note": "REPORT-ONLY \u2014 the licensed mechanism made visible, never a criterion."}
- era (report-only): capture Δ 1.57868 vs legacy Δ 1.5775

## Assembled-PPR effect — REPORT-ONLY (PM ruling; never a gate)

```json
{
  "per_cell_points_units": {
    "QB|passing_tds": 0.3382,
    "QB|passing_yards": 0.2507,
    "QB|rushing_yards": 0.1071,
    "RB|receiving_yards": 0.0924,
    "RB|rushing_tds": 0.1164,
    "RB|rushing_yards": 0.1679,
    "TE|receiving_yards": 0.1236,
    "WR|receiving_yards": 0.1578
  },
  "per_position_sum_points_units": {
    "QB": 0.696,
    "RB": 0.3767,
    "TE": 0.1236,
    "WR": 0.1578
  },
  "note": "REPORT-ONLY (PM ruling): winner-vs-binding-incumbent CRPS lift \u00d7 PPR weight, summed per position \u2014 a sum of MARGINAL contributions in points units, NOT an assembled joint-points claim; a per-stat win need not move assembled points."
}
```

## PM rulings (2026-08-15) — recorded post-run; preserved by --rewrite-report

### Decision A — YES: wiring carded as NF-W6c (all 6 ship cells)

Card the wiring of ALL SIX winning cells into the served raw-line surface — the substrate is only complete with full raw-line coverage. Substrate first, arbitrary-league re-scoring second (the league-board path is the consumer that follows). ⛔ The points hurdle champion for TOTAL points stays untouched (never beaten; not tested here). NF-W6c ships as its own NF-G0-governed story (NF-W6b promotes nothing), inherits the three-implementations parity tax if any scoring surface consumes it, and stays deploy-held until the weekly serving path opens.

### Decision B — YES: RB receiving_yards re-test scheduled (data-availability trigger)

Re-score on THE SAME harness once the 2026 half-season folds exist (~mid-season; no new modeling): `run_nf_w6b_stat_distributions` with the fold axis extended. ⭐ This is a LEGITIMATE calendar-bound re-test, distinct in kind from the NF-D18/CONSTRAINT_REFUSED no-trigger class: every gate is green except DSR (0.8747 vs 0.95) and the observed per-fold Sharpe (14.509) sits ABOVE the deflation bar (sr0 ≈ 9.97), so n is the binding constraint and n is buyable by the calendar.

### Decision C — carded but DEFERRED as NF-W6b-C (RB rushing_tds fresh-family successor)

The finding is real (knn_quantile beats the discrete climatology by +13.0%, CI excludes zero, 8/8 folds) but DSR is UNREACHABLE in this field: the pre-registered linear arm (`enet_residual`, trial Sharpe −9.199 on an 86%-atom cell) inflates the cross-trial dispersion so sr0 ≈ 7.32 > the winner's sr 6.47, and MH2.2 forbids trimming a field after the fact. ⭐ SUCCESSOR REQUIREMENT (record so the field-inflation lesson is not re-earned): a FRESH registration whose declared family is coherent and atom-aware ONLY — lgbm_hurdle_tail, knn_quantile, and a discrete-count class (e.g. (beta-)binomial / Poisson-mixture) — ⛔ NO linear-residual arm: a position-constant residual bank around a linear mean cannot express an 86% atom, and its guaranteed huge loss re-inflates the very deflation bar that refused this cell. DEFERRED: smallest of the eight (~0.12 pts/wk points-units); may ride NF-W6c's infrastructure later; no dedicated session while fantasy launch is the focus.

### Wiring hand-off pins (Decision A — so NF-W6c is a lift-and-serve, not a re-derivation)

⚠️ NO FITTED PICKLES EXIST — deliberately: the bake-off fits per fold (CV), so what the gate validated is the CONSTRUCTION + SELECTION, not one fitted object. NF-W6c therefore serves a fresh full-train fit produced BY THE IDENTICAL pinned code path below (same functions, same champion features, same calibration-split tail discipline) — the MH2.1 serve-what-was-validated rule applied to a form: re-deriving the form in different code is forbidden.

| cell | winning form | constructing function (the pinned code path) |
|---|---|---|
| QB|passing_tds | knn_quantile | `SD.arm_knn_quantile` — per-position kNN (k=300) over median-imputed (`WP._Imputer`, train medians) standardized champion features; predictive = empirical quantiles of the neighbors' realized stat |
| QB|passing_yards | lgbm_quantile_tail | `SD.arm_lgbm_quantile_tail` — pooled 9-knot LGBM quantile bank (`WP._lgbm` quantile objective at `FIT_LEVELS`, position code appended), sorted + interpolated to the 199 grid, + per-position exponential mean-excess tails fit on the purged `MC.calibration_split` slice |
| QB|rushing_yards | lgbm_hurdle_tail | `SD.arm_lgbm_hurdle_tail` — champion-construction LGBMClassifier P(y=0) (the `WP.fit_lgbm_hurdle` parameter block, verbatim) × conditional-on-nonzero 9-knot LGBM quantile bank (`WP._lgbm` quantile objective at `FIT_LEVELS`, position code appended) + per-position exponential mean-excess tails fit on the purged `MC.calibration_split` slice (beta = mean excess beyond the end knots; 0 if <10 exceedances), mixed exactly by `SD.mixture_quantiles199` (atom at fitted p0; negative conditional mass below the atom) |
| RB|rushing_yards | lgbm_hurdle_tail | `SD.arm_lgbm_hurdle_tail` — champion-construction LGBMClassifier P(y=0) (the `WP.fit_lgbm_hurdle` parameter block, verbatim) × conditional-on-nonzero 9-knot LGBM quantile bank (`WP._lgbm` quantile objective at `FIT_LEVELS`, position code appended) + per-position exponential mean-excess tails fit on the purged `MC.calibration_split` slice (beta = mean excess beyond the end knots; 0 if <10 exceedances), mixed exactly by `SD.mixture_quantiles199` (atom at fitted p0; negative conditional mass below the atom) |
| TE|receiving_yards | lgbm_hurdle_tail | `SD.arm_lgbm_hurdle_tail` — champion-construction LGBMClassifier P(y=0) (the `WP.fit_lgbm_hurdle` parameter block, verbatim) × conditional-on-nonzero 9-knot LGBM quantile bank (`WP._lgbm` quantile objective at `FIT_LEVELS`, position code appended) + per-position exponential mean-excess tails fit on the purged `MC.calibration_split` slice (beta = mean excess beyond the end knots; 0 if <10 exceedances), mixed exactly by `SD.mixture_quantiles199` (atom at fitted p0; negative conditional mass below the atom) |
| WR|receiving_yards | lgbm_hurdle_tail | `SD.arm_lgbm_hurdle_tail` — champion-construction LGBMClassifier P(y=0) (the `WP.fit_lgbm_hurdle` parameter block, verbatim) × conditional-on-nonzero 9-knot LGBM quantile bank (`WP._lgbm` quantile objective at `FIT_LEVELS`, position code appended) + per-position exponential mean-excess tails fit on the purged `MC.calibration_split` slice (beta = mean excess beyond the end knots; 0 if <10 exceedances), mixed exactly by `SD.mixture_quantiles199` (atom at fitted p0; negative conditional mass below the atom) |

- Served-quantile representation: an (n, 199) MONOTONE quantile bank at `MC.EVAL_LEVELS` (0.005…0.995, step 0.005); the zero atom appears as leading quantiles exactly 0.0 — consumers read P(0) as the share of grid levels at 0 and central intervals by level index (q10/q90 at indices 19/179).
- Features: the champion set `WP.FEATURES` (29 columns) + position code — ⛔ no new features (the NF-W6b prereg constraint carries to serving).
- Matrix: the NF-W6 certified build (`build_matrix_w6`, cache key 57c4cf96bb3c3570) — the PIT gate runs on every load; the TD label attach is grain- and conservation-guarded.
- Selection provenance: per-fold scores for every (cell, label) live in THIS json (`fold_results`); the verdict layer re-derives from them at zero refit cost (`--rewrite-report`). Seed 20260815.
- Tail constants: `MIN_TAIL_N=10` (a thinner side gets beta 0 = flat, loud); hurdle classifier params = the champion hurdle block, guard-pinned against `WP.fit_lgbm_hurdle` source.

## Pre-registration

- cells: ['QB|passing_yards', 'QB|passing_tds', 'QB|rushing_yards', 'RB|rushing_yards', 'RB|rushing_tds', 'RB|receiving_yards', 'WR|receiving_yards', 'TE|receiving_yards'] (⛔ closed: ['QB|rushing_tds', 'RB|receiving_tds', 'WR|receiving_tds', 'TE|receiving_tds']); arms: ['lgbm_quantile_tail', 'lgbm_hurdle_tail', 'enet_residual', 'knn_quantile']; foils: ['inc_head_bank', 'inc_climatology'] (binding sets the bar); anchors: ['nihilist_zero', 'zero_width', 'max_width', 'permuted_quantile', 'oracle_marginal', 'matched_marginal'].
- gates: paired lift vs binding foil ∧ `fold_consistency_clause(8)` ∧ PBO<0.2 over the eligible field ∧ DSR≥0.95 ∧ BH q=0.1 (two families, own AND pooled) ∧ coverage floor (one-sided, prereg §2) ∧ degenerates lose ∧ permutation behaves. Fails closed.
- FDR families: yards=6 cells, tds=2 cells.
- null classification is HAND-derived (GENUINE_ABSENCE / POWER_LIMITED / CONSTRAINT_REFUSED); `classify_null` is NOT invoked (the n_arms mis-render — NF-W3 (c)).

_Runtime: 6810.4s · seed 20260815 · matrix cache key 57c4cf96bb3c3570_