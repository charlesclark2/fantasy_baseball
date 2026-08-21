# NF-W8-0e — the QB | `passing_yards` CELL, zero-mass × conditional-level (**CELL_NOT_CORRECTED**)

Generated 2026-08-21T04:06:30.323373+00:00 · gate league **full_ppr** · 8 folds · cell **QB|passing_yards** · ranked on `crps_q199`

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing, publishes nothing, re-serves NO NF-W6d cell and writes NO optimizer input.

## Verdict

- state: **CELL_NOT_CORRECTED**
- winner: `zm_only` · **`cross_rankable`: False**
- the best cell arm `zm_only` does not clear the registered battery (['beats_foil', 'not_a_foil_tie', 'fold_consistency', 'dsr_ok', 'fdr_ok', 'cell_pit_not_degraded']) — the served `QB|passing_yards` cell STANDS and the NF-W8-0c reading is unchanged

## Harness controls (a control that did not run is never a pass — NF1.7 (a))

| control | holds |
|---|---|
| `identity_matches_certified` | ✅ |
| `transform_identities` | ✅ |
| `permutation_is_inactive` | ✅ |
| pin `qb_assembly_matches_w7f` | ✅ — {"n_folds_compared": 8, "max_abs_crps_gap": 0.0, "max_abs_pit_gap": 0.0} |
| pin `non_qb_bias_matches_w8_0b` | ✅ — {"n_folds_compared": 8, "max_abs_gap_by_position": {"QB": 0.0, "RB": 0.0, "WR": 0.0, "TE": 0.0}} |
| pin `w8_0c_leg_contribution` | ✅ — {"comparable": true, "recorded_contribution_ppr": -0.3975331334769923, "recomputed_contribution_ppr": -0.3975331334769923, "abs_gap_contribution": 0.0, "recorded_conditional_ppr":  |
| pin `incumbent_cell_is_the_served_cell` | ✅ — {"note": "the identity assembly reproduces the certified `zm_floor` exactly, which is only possible if the identity CELL is the served cell"} |

## ⭐ Family B — the 2×2 (the read this story exists for)

> `Δ` positive = the arm IMPROVES the metric. `interaction = Δ_joint − (Δ_Z + Δ_C)`. A SUB_ADDITIVE interaction means the halves OVERLAP — together they buy less than the sum of their separate effects, which is the NF-W7e shape and exactly why fixing one then the other would mis-price both.

### primary (shift) · CRPS — **SUPER_ADDITIVE**

| quantity | mean | CI95 | folds won | p |
|---|---|---|---|---|
| Δ_Z (zero-mass alone) | -0.15482 | [-0.46137, 0.15174] | 3/8 | 0.8643 |
| Δ_C (conditional level alone) | -13.23693 | [-17.87689, -8.59698] | 0/8 | 0.9999 |
| Δ_joint (both) | -0.97468 | [-1.53138, -0.41798] | 0/8 | 0.9978 |
| **interaction** | **12.41707** | [8.02400, 16.81013] | — | — |
| Δ_Z + Δ_C (the sum of the halves) | -13.39175 | — | — | — |
| joint ÷ sum-of-halves | 0.0728 | — | — | — |

### alternative (scale) · CRPS — **SUPER_ADDITIVE**

| quantity | mean | CI95 | folds won | p |
|---|---|---|---|---|
| Δ_Z (zero-mass alone) | -0.15482 | [-0.46137, 0.15174] | 3/8 | 0.8643 |
| Δ_C (conditional level alone) | -12.90661 | [-17.89258, -7.92064] | 0/8 | 0.9998 |
| Δ_joint (both) | -1.45192 | [-2.30294, -0.60090] | 0/8 | 0.9975 |
| **interaction** | **11.60951** | [7.24085, 15.97816] | — | — |
| Δ_Z + Δ_C (the sum of the halves) | -13.06143 | — | — | — |
| joint ÷ sum-of-halves | 0.1112 | — | — | — |

### primary (shift) · |level bias| — **SUPER_ADDITIVE**

| quantity | mean | CI95 | folds won | p |
|---|---|---|---|---|
| Δ_Z (zero-mass alone) | -8.05094 | [-9.96305, -6.13882] | 0/8 | 1.0000 |
| Δ_C (conditional level alone) | -40.80805 | [-55.06458, -26.55151] | 0/8 | 0.9999 |
| Δ_joint (both) | -0.76884 | [-5.16934, 3.63166] | 4/8 | 0.6541 |
| **interaction** | **48.09014** | [34.43430, 61.74599] | — | — |
| Δ_Z + Δ_C (the sum of the halves) | -48.85898 | — | — | — |
| joint ÷ sum-of-halves | 0.0157 | — | — | — |

### alternative (scale) · |level bias| — **SUPER_ADDITIVE**

| quantity | mean | CI95 | folds won | p |
|---|---|---|---|---|
| Δ_Z (zero-mass alone) | -8.05094 | [-9.96305, -6.13882] | 0/8 | 1.0000 |
| Δ_C (conditional level alone) | -39.57867 | [-53.99090, -25.16643] | 0/8 | 0.9998 |
| Δ_joint (both) | -0.84179 | [-5.15636, 3.47277] | 4/8 | 0.6707 |
| **interaction** | **46.78781** | [33.82328, 59.75234] | — | — |
| Δ_Z + Δ_C (the sum of the halves) | -47.62960 | — | — | — |
| joint ÷ sum-of-halves | 0.0177 | — | — | — |

## Family A — the cell contest

- winner `zm_only` vs the SERVED cell (`identity`): Δ`crps_q199` **-0.15482** (CI95 [-0.46137, 0.15174], 3/8 folds) · lift -0.504% · PBO 0.0000 · DSR 0.0002 · p 0.8643

| arm | cell CRPS | cell PIT | cell level bias | pred P(0) | assembled CRPS | assembled PIT | assembled bias |
|---|---|---|---|---|---|---|---|
| `identity` | 30.69922 | 0.0569 | -1.510 | 0.3100 | 2.56449 | 0.0281 | -0.4233 |
| `zm_only` | 30.85404 | 0.0643 | -11.061 | 0.5235 | 2.56449 | 0.0281 | -0.4233 |
| `cond_shift` | 43.93616 | 0.0826 | 43.633 | 0.3083 | 2.62382 | 0.0377 | 0.8253 |
| `joint_shift` | 31.67391 | 0.0389 | 3.523 | 0.4955 | 2.56401 | 0.0255 | 0.1179 |
| `cond_scale` | 43.60583 | 0.0857 | 42.403 | 0.3099 | 2.72084 | 0.0333 | 1.1526 |
| `joint_scale` | 32.15114 | 0.0434 | 2.970 | 0.4960 | 2.56521 | 0.0239 | 0.0971 |
| `oracle_zm_only` | 24.67692 | 0.0875 | -15.722 | 0.5749 | — | — | — |
| `oracle_cond_shift` | 45.27687 | 0.0847 | 48.613 | 0.3082 | — | — | — |
| `oracle_joint_shift` | 31.80090 | 0.0303 | 4.965 | 0.5231 | — | — | — |
| `oracle_cond_scale` | 45.40306 | 0.0912 | 48.451 | 0.3099 | — | — | — |
| `oracle_joint_scale` | 32.51376 | 0.0358 | 4.979 | 0.5235 | — | — | — |
| `matched_n_zm_only` | 30.85404 | 0.0643 | -11.061 | 0.5235 | — | — | — |
| `matched_n_cond_shift` | 43.64995 | 0.0833 | 42.841 | 0.3083 | — | — | — |
| `matched_n_joint_shift` | 31.88031 | 0.0386 | 4.202 | 0.4955 | — | — | — |
| `matched_n_cond_scale` | 43.67821 | 0.0883 | 42.278 | 0.3099 | — | — | — |
| `matched_n_joint_scale` | 32.60064 | 0.0416 | 4.141 | 0.4960 | — | — | — |
| `over_joint_shift` | 34.81189 | 0.0369 | 17.032 | 0.4955 | — | — | — |
| `reverse_joint_shift` | 32.74284 | 0.1336 | -21.696 | 0.5717 | — | — | — |
| `permuted_shift` | 31.67391 | 0.0389 | 3.523 | 0.4955 | — | — | — |
| `nihilist_zero` | 91.94152 | 0.4028 | -91.935 | 1.0000 | — | — | — |
| `zero_width` | 40.52615 | 0.2911 | -7.764 | 0.3898 | — | — | — |
| `max_width` | 40.18796 | 0.2094 | 10.996 | 0.4224 | — | — | — |
| `climatology_bank` | 57.11215 | 0.0264 | 0.867 | 0.5250 | — | — | — |

- realized cell `P(0)` (pooled): 0.5497 · NF-W7f recorded 0.5563 against a served 0.2983

### The registered clause battery

| clause | class | verdict |
|---|---|---|
| `beats_foil` | statistical | ❌ |
| `not_a_foil_tie` | anchor | ❌ |
| `fold_consistency` | statistical | ❌ |
| `pbo_ok` | statistical | ✅ |
| `dsr_ok` | statistical | ❌ |
| `fdr_ok` | statistical | ❌ |
| `coverage_floor_ok` | constraint | ✅ |
| `assembled_pit_preserved` | constraint | ✅ |
| `assembled_crps_no_harm` | constraint | ✅ |
| `cell_pit_not_degraded` | anchor | ❌ |
| `degenerates_lose` | anchor | ✅ |
| `magnitude_anchors_lose` | anchor | ✅ |
| `winner_own_form_floor` | anchor | ✅ |
| `transform_identities_hold` | anchor | ✅ |
| `incumbent_reproduces` | anchor | ✅ |

- coverage: {"coverage_80": 0.8086, "n_rows": 5485, "binomial_se": 0.0054, "floor": 0.8, "blocking_shortfall": false}
- assembled PIT (bar 0.05): {"bar": 0.05, "per_fold": [0.01721068249258159, 0.034306569343065696, 0.024450951683748168, 0.03380281690140843, 0.02262773722627738, 0.03165680473372781, 0.03114754098360656, 0.02981455064194008], "n_folds": 8, "n_evaluable": 8, "n_unreadable": 0, "n_clearing": 8, "worst": 0.034306569343065696, "mean": 0.028127206750794463, "passes": true}
- cell PIT: {"winner": 0.06427143828657703, "incumbent": 0.05686554031941053, "w6d_default_bar_disclosure": 0.03, "note": "a NO-HARM clause against the served cell; the 0.03 figure is NF-W6d's Phase-C DEFAULT bar, disclosed and NEVER a gate here (E2.1-r)"}
- per-form oracle pairs (a TIE is INACTIVE, never a refusal — NF-W6d/NF-D20): {"zm_only": {"state": "ACTIVE_AND_RESPECTED", "passes": true, "inactive": false, "gap": 6.177122951353461}, "cond_shift": {"state": "ACTIVE_AND_VIOLATED", "passes": false, "inactive": false, "gap": -1.62692279439338}, "joint_shift": {"state": "ACTIVE_AND_RESPECTED", "passes": true, "inactive": false, "gap": 0.07941703105935005}, "cond_scale": {"state": "ACTIVE_AND_VIOLATED", "passes": false, "inactive": false, "gap": -1.7248542537400553}, "joint_scale": {"state": "ACTIVE_AND_RESPECTED", "passes": true, "inactive": false, "gap": 0.08687573486837152}}
- degenerates lose: {"nihilist_zero": true, "zero_width": true, "max_width": true, "climatology_bank": true} · magnitude bracket loses: {"over_joint_shift": true, "reverse_joint_shift": true}
- BH (§12A A2, over all five real arms): {"pvals": {"zm_only": 0.8643, "cond_shift": 0.9999, "joint_shift": 0.9978, "cond_scale": 0.9998, "joint_scale": 0.9975}, "rejected": {"zm_only": false, "cond_shift": false, "joint_shift": false, "cond_scale": false, "joint_scale": false}, "q": 0.1, "note": "prereg \u00a712A A2 \u2014 BH over ALL FIVE real arms (stricter than the two registered contrasts; it can only prevent a false ADD)"}

## Family C — the assembled QB read, and the §8.1 measured Z-column activity

> ⭐ The consumed QB generator is `zm_floor`, which ALREADY re-splices all thirteen legs, and the re-splice is idempotent under the RAISE-ONLY rule — so the Z column was PREDICTED (before the run) to be a structural no-op at the ASSEMBLED layer. Measured, never assumed; an inactive arm is UNINFORMATIVE, never a pass (NF-D20).

| comparison | active folds / folds | max abs CRPS gap | inactive |
|---|---|---|---|
| `identity_vs_zm_only` | 0/8 | 0.000000000 | ✅ |
| `cond_shift_vs_joint_shift` | 7/8 | 0.104592280 | ❌ |
| `cond_scale_vs_joint_scale` | 7/8 | 0.272309096 | ❌ |

### ⭐ The cell's own channel, before and after

> NF-W8-0c recorded `passing_yards` at -0.3975 PPR (conditional -0.3878) under `identity`; a row-pooled read (NF1.8), never a mean of fold means

| arm | `passing_yards` contribution (PPR) | its conditional part (PPR) |
|---|---|---|
| `identity` | -0.3975 | -0.3878 |
| `zm_only` | -0.3975 | -0.3878 |
| `cond_shift` | 0.8543 | 0.8711 |
| `joint_shift` | 0.1443 | 0.1567 |
| `cond_scale` | 1.1798 | 1.1986 |
| `joint_scale` | 0.1234 | 0.1357 |

## Family D — the DOWNSTREAM cross-position verification

> ⭐ Every arm's row is REPORT-ONLY (prereg §12A A8). The verdict reads the closure of the §7 winner and nothing else — an arm that lost the registered contest can never be promoted on this table (E2.1-r).

### under `identity` — `gap_detected` **True** · QB pooled bias -0.4233 PPR

| pair | gap (PPR) | SE | MDE | below MDE | BH rejected |
|---|---|---|---|---|---|
| QB|RB | -0.2032 | 0.1174 | 0.3288 | — | ❌ |
| QB|WR | -0.3621 | 0.0727 | 0.2036 | ❌ | ✅ |
| QB|TE | -0.3106 | 0.0679 | 0.1903 | ❌ | ✅ |
| RB|WR | -0.1589 | 0.0908 | 0.2543 | — | ❌ |
| RB|TE | -0.1074 | 0.0619 | 0.1733 | — | ❌ |
| WR|TE | 0.0515 | 0.0660 | 0.1850 | — | ❌ |

- QB pairs all below their MDEs: ❌ · none BH rejected: ❌

### under `zm_only` — `gap_detected` **True** · QB pooled bias -0.4233 PPR

| pair | gap (PPR) | SE | MDE | below MDE | BH rejected |
|---|---|---|---|---|---|
| QB|RB | -0.2032 | 0.1174 | 0.3288 | — | ❌ |
| QB|WR | -0.3621 | 0.0727 | 0.2036 | ❌ | ✅ |
| QB|TE | -0.3106 | 0.0679 | 0.1903 | ❌ | ✅ |
| RB|WR | -0.1589 | 0.0908 | 0.2543 | — | ❌ |
| RB|TE | -0.1074 | 0.0619 | 0.1733 | — | ❌ |
| WR|TE | 0.0515 | 0.0660 | 0.1850 | — | ❌ |

- QB pairs all below their MDEs: ❌ · none BH rejected: ❌

### under `cond_shift` — `gap_detected` **True** · QB pooled bias 0.8253 PPR

| pair | gap (PPR) | SE | MDE | below MDE | BH rejected |
|---|---|---|---|---|---|
| QB|RB | 1.0454 | 0.1787 | 0.5007 | — | ✅ |
| QB|WR | 0.8865 | 0.1752 | 0.4908 | ❌ | ✅ |
| QB|TE | 0.9380 | 0.1824 | 0.5109 | ❌ | ✅ |
| RB|WR | -0.1589 | 0.0908 | 0.2543 | — | ❌ |
| RB|TE | -0.1074 | 0.0619 | 0.1733 | — | ❌ |
| WR|TE | 0.0515 | 0.0660 | 0.1850 | — | ❌ |

- QB pairs all below their MDEs: ❌ · none BH rejected: ❌

### under `joint_shift` — `gap_detected` **False** · QB pooled bias 0.1179 PPR

| pair | gap (PPR) | SE | MDE | below MDE | BH rejected |
|---|---|---|---|---|---|
| QB|RB | 0.3380 | 0.1223 | 0.3426 | — | ❌ |
| QB|WR | 0.1790 | 0.0888 | 0.2487 | ✅ | ❌ |
| QB|TE | 0.2305 | 0.0991 | 0.2776 | ✅ | ❌ |
| RB|WR | -0.1589 | 0.0908 | 0.2543 | — | ❌ |
| RB|TE | -0.1074 | 0.0619 | 0.1733 | — | ❌ |
| WR|TE | 0.0515 | 0.0660 | 0.1850 | — | ❌ |

- QB pairs all below their MDEs: ✅ · none BH rejected: ✅

### under `cond_scale` — `gap_detected` **True** · QB pooled bias 1.1526 PPR

| pair | gap (PPR) | SE | MDE | below MDE | BH rejected |
|---|---|---|---|---|---|
| QB|RB | 1.3727 | 0.2281 | 0.6390 | — | ✅ |
| QB|WR | 1.2138 | 0.2261 | 0.6335 | ❌ | ✅ |
| QB|TE | 1.2652 | 0.2345 | 0.6569 | ❌ | ✅ |
| RB|WR | -0.1589 | 0.0908 | 0.2543 | — | ❌ |
| RB|TE | -0.1074 | 0.0619 | 0.1733 | — | ❌ |
| WR|TE | 0.0515 | 0.0660 | 0.1850 | — | ❌ |

- QB pairs all below their MDEs: ❌ · none BH rejected: ❌

### under `joint_scale` — `gap_detected` **False** · QB pooled bias 0.0971 PPR

| pair | gap (PPR) | SE | MDE | below MDE | BH rejected |
|---|---|---|---|---|---|
| QB|RB | 0.3172 | 0.1276 | 0.3573 | — | ❌ |
| QB|WR | 0.1583 | 0.0919 | 0.2574 | ✅ | ❌ |
| QB|TE | 0.2098 | 0.1029 | 0.2882 | ✅ | ❌ |
| RB|WR | -0.1589 | 0.0908 | 0.2543 | — | ❌ |
| RB|TE | -0.1074 | 0.0619 | 0.1733 | — | ❌ |
| WR|TE | 0.0515 | 0.0660 | 0.1850 | — | ❌ |

- QB pairs all below their MDEs: ✅ · none BH rejected: ✅

## Null classification

```
{
  "state": "GENUINE_ABSENCE",
  "reason": "`crps_q199|QB|passing_yards`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a negative point estimate and no field size changes its sign \u2014 do NOT re-test.",
  "retest_trigger": null,
  "folds_have": 8,
  "folds_needed": null,
  "extra_seasons": null,
  "max_field_size": null,
  "detail": {
    "n_folds": 8,
    "n_arms": 5
  },
  "field_remedy_admissible": null,
  "failing_checks": [
    "beats_foil",
    "fold_consistency",
    "dsr_ok",
    "fdr_ok",
    "not_a_foil_tie",
    "cell_pit_not_degraded"
  ],
  "binding_half": "mixed",
  "lockstep": {
    "evaluable": true,
    "sr0": 0.9173,
    "observed_sr": -0.42220560498615817,
    "sr_minus_sr0": -1.3395056049861582,
    "variance_lever_closed": true,
    "most_dispersing_trial": "cond_shift",
    "reading": "`SR \u2264 SR0` \u21d2 a SHARED proportional variance lever cannot flip the sign, at any row, fold or draw count \u2014 do NOT publish a 'lower-variance design' trigger (NF-W8-0d \u00a71). `SR > SR0` \u21d2 the fold-count lever has a real sign and the shortfall is a power statement."
  },
  "mechanism_reading": "\u26d4 The instrument's 'lower-variance design' remedy is VOID here: `SR \u2264 SR0`, and a shared proportional variance lever maps `SR \u2212 SR0 \u21a6 (SR \u2212 SR0)/c` with its SIGN invariant (NF-W8-0d \u00a71). No row, fold or draw count clears it, so no data trigger is published (NF-D18). The admissible remedy is a fresh, coherently pre-registered family \u2014 \u26d4 never a post-hoc trim of these five declared arms (MH2.2).",
  "classifier": "cv_power.classify_null (declared_field_size stated \u2014 MH2.7; read field_remedy_admissible, never the prose)"
}
```

⚠️ The classification describes **family A** — the FITTED cell contest. Family B is a deterministic decomposition of stored per-fold scores and family D's bar is INHERITED; reading a fold trigger onto either would be the NF-D18 misleading-trigger class.

## Promote blockers

- NF-W8-0 is DEPLOY-HELD: the cross-position input is an NF-G0 challenger consumed by nothing until governance promotes it
- every QB row carries the §1 Option-B caveat: calibrated + best-on-record, consumed under a registered-forward PM decision — NOT certification-equivalent to WR/TE/RB, and the ship bar was never relaxed (E2.1-r)
- NF-W7c's promote blockers are INHERITED in full: an assembled row whose source is not `bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league prices (`calibration_warning`), and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap
- K/DST are OUT OF SCOPE — the input is declared 4-position; the NF-W7 K/DST weekly models join in a successor's registration, never by silent extension
- the layer corrects LEVEL (and uniform affine scale) only; a rank-dependent generator artifact is a successor's fresh registration
- the tail completion is a DETERMINISTIC read of the certified bank — it re-certifies NO position: NF-W7f's QB Option-B caveat, NF-W7c's calibrated-default disclosure and every per-position certification scope are inherited UNCHANGED
- `cross_rankable: true` licenses the RAW-POINT cross-position surfaces and a superflex board at the stated MDE only; it is not a claim about a rank-dependent (within-position non-uniform) generator artifact, which stays out of scope for a successor's registration
- NF-W8-0e re-serves NOTHING: a SHIP verdict says a corrected `QB|passing_yards` cell EXISTS and is certified on this axis — re-serving a NF-W6d cell changes the certified substrate every assembled position reads and is a SUCCESSOR's registration, never a side effect
- the correction is ROW-BLIND (a pooled scalar per fold): the cell's LEVEL is corrected, not its per-player resolution — which is also why this story's permutation anchor is registered INACTIVE rather than presented as a passed test (prereg §5.2)
- the layer corrects a LEVEL (or a uniform conditional scale) only; a rank-dependent, covariate-dependent or shape-dependent cell artifact stays a successor's fresh registration
- `cond_scale` / `joint_scale` re-level a CERTIFIED per-stat marginal multiplicatively — their measured marginal drift is disclosed, and an admissible win under the scale form trades a per-stat certification scope for an assembled level
- the gate league is `full_ppr` (`passing_yards` at +0.04); a league pricing it differently scales every PPR figure here and is not separately certified
- family D is a VERIFICATION at ~0.19-0.20 PPR MDEs — 'below the MDE' means 'no artifact larger than X', never 'no artifact' (MH2.6)

_runtime 3182.1s_
