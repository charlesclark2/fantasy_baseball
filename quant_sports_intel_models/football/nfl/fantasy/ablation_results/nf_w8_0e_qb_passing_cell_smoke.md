# NF-W8-0e — the QB | `passing_yards` CELL, zero-mass × conditional-level (**CELL_NOT_CORRECTED**)

Generated 2026-08-21T02:54:50.581286+00:00 · gate league **full_ppr** · 2 folds · cell **QB|passing_yards** · ranked on `crps_q199` · ⚠️ **PATH PROOF (`--smoke`) — no verdict**

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record promotes nothing, publishes nothing, re-serves NO NF-W6d cell and writes NO optimizer input.

## Verdict

- state: **CELL_NOT_CORRECTED**
- winner: `zm_only` · **`cross_rankable`: False**
- the best cell arm `zm_only` does not clear the registered battery (['beats_foil', 'not_a_foil_tie', 'fold_consistency', 'pbo_ok', 'dsr_ok', 'fdr_ok', 'incumbent_reproduces']) — the served `QB|passing_yards` cell STANDS and the NF-W8-0c reading is unchanged

## Harness controls (a control that did not run is never a pass — NF1.7 (a))

> ⚠️ **PATH PROOF.** Two folds at 300 draws: the reproduction pins compare against records built at 4000 draws, so `qb_assembly_matches_w7f` and `non_qb_bias_matches_w8_0b` CANNOT hit here and their ❌ is the draw count, not a defect. Every C arm is identity on fold 1 BY REGISTRATION (prereg §4.1), so the statistical clauses are structurally unreachable at n=2 and no verdict is claimed.

| control | holds |
|---|---|
| `identity_matches_certified` | ✅ |
| `transform_identities` | ✅ |
| `permutation_is_inactive` | ✅ |
| pin `qb_assembly_matches_w7f` | ❌ — {"n_folds_compared": 2, "max_abs_crps_gap": 0.012522071564870174, "max_abs_pit_gap": 0.004279600570613412} |
| pin `non_qb_bias_matches_w8_0b` | ❌ — {"n_folds_compared": 2, "max_abs_gap_by_position": {"QB": 0.009824730843515317, "RB": 0.0, "WR": 0.015758869119072233, "TE": 0.009998586409554575}} |
| pin `w8_0c_leg_contribution` | ❌ — {"comparable": true, "recorded_contribution_ppr": -0.3975331334769923, "recomputed_contribution_ppr": -0.2832212879599107, "abs_gap_contribution": 0.11431184551708162, "recorded_co |
| pin `incumbent_cell_is_the_served_cell` | ✅ — {"note": "the identity assembly reproduces the certified `zm_floor` exactly, which is only possible if the identity CELL is the served cell"} |

## ⭐ Family B — the 2×2 (the read this story exists for)

> `Δ` positive = the arm IMPROVES the metric. `interaction = Δ_joint − (Δ_Z + Δ_C)`. A SUB_ADDITIVE interaction means the halves OVERLAP — together they buy less than the sum of their separate effects, which is the NF-W7e shape and exactly why fixing one then the other would mis-price both.

### primary (shift) · CRPS — **UNDEFINED**

| quantity | mean | CI95 | folds won | p |
|---|---|---|---|---|
| Δ_Z (zero-mass alone) | -0.06487 | [—, —] | 1/2 | — |
| Δ_C (conditional level alone) | -7.37933 | [—, —] | 0/2 | — |
| Δ_joint (both) | -0.67748 | [—, —] | 0/2 | — |
| **interaction** | **6.76672** | [—, —] | — | — |
| Δ_Z + Δ_C (the sum of the halves) | -7.44421 | — | — | — |
| joint ÷ sum-of-halves | 0.0910 | — | — | — |

### alternative (scale) · CRPS — **UNDEFINED**

| quantity | mean | CI95 | folds won | p |
|---|---|---|---|---|
| Δ_Z (zero-mass alone) | -0.06487 | [—, —] | 1/2 | — |
| Δ_C (conditional level alone) | -5.90720 | [—, —] | 0/2 | — |
| Δ_joint (both) | -0.85356 | [—, —] | 0/2 | — |
| **interaction** | **5.11852** | [—, —] | — | — |
| Δ_Z + Δ_C (the sum of the halves) | -5.97208 | — | — | — |
| joint ÷ sum-of-halves | 0.1429 | — | — | — |

### primary (shift) · |level bias| — **UNDEFINED**

| quantity | mean | CI95 | folds won | p |
|---|---|---|---|---|
| Δ_Z (zero-mass alone) | -6.79370 | [—, —] | 0/2 | — |
| Δ_C (conditional level alone) | -23.65577 | [—, —] | 0/2 | — |
| Δ_joint (both) | -2.74965 | [—, —] | 0/2 | — |
| **interaction** | **27.69982** | [—, —] | — | — |
| Δ_Z + Δ_C (the sum of the halves) | -30.44947 | — | — | — |
| joint ÷ sum-of-halves | 0.0903 | — | — | — |

### alternative (scale) · |level bias| — **UNDEFINED**

| quantity | mean | CI95 | folds won | p |
|---|---|---|---|---|
| Δ_Z (zero-mass alone) | -6.79370 | [—, —] | 0/2 | — |
| Δ_C (conditional level alone) | -21.26234 | [—, —] | 0/2 | — |
| Δ_joint (both) | -2.14818 | [—, —] | 0/2 | — |
| **interaction** | **25.90786** | [—, —] | — | — |
| Δ_Z + Δ_C (the sum of the halves) | -28.05604 | — | — | — |
| joint ÷ sum-of-halves | 0.0766 | — | — | — |

## Family A — the cell contest

- winner `zm_only` vs the SERVED cell (`identity`): Δ`crps_q199` **-0.06487** (CI95 [—, —], 1/2 folds) · lift -0.217% · PBO — · DSR — · p —

| arm | cell CRPS | cell PIT | cell level bias | pred P(0) | assembled CRPS | assembled PIT | assembled bias |
|---|---|---|---|---|---|---|---|
| `identity` | 29.92501 | 0.0595 | 1.337 | 0.3094 | 2.66319 | 0.0334 | -0.4062 |
| `zm_only` | 29.98989 | 0.0509 | -8.131 | 0.5142 | 2.66319 | 0.0334 | -0.4062 |
| `cond_shift` | 37.30435 | 0.0688 | 24.993 | 0.3089 | 2.70503 | 0.0469 | 0.2457 |
| `joint_shift` | 30.60249 | 0.0411 | 4.087 | 0.4178 | 2.67014 | 0.0412 | -0.0991 |
| `cond_scale` | 35.83222 | 0.0774 | 22.600 | 0.3094 | 2.73638 | 0.0398 | 0.3514 |
| `joint_scale` | 30.77858 | 0.0447 | 3.486 | 0.4179 | 2.66882 | 0.0348 | -0.1222 |
| `oracle_zm_only` | 23.89440 | 0.0729 | -12.788 | 0.5722 | — | — | — |
| `oracle_cond_shift` | 44.31547 | 0.0822 | 48.016 | 0.3081 | — | — | — |
| `oracle_joint_shift` | 31.31744 | 0.0293 | 7.326 | 0.5137 | — | — | — |
| `oracle_cond_scale` | 44.25492 | 0.0975 | 47.887 | 0.3094 | — | — | — |
| `oracle_joint_scale` | 32.05027 | 0.0388 | 7.340 | 0.5142 | — | — | — |
| `matched_n_zm_only` | 29.98989 | 0.0509 | -8.131 | 0.5142 | — | — | — |
| `matched_n_cond_shift` | 37.30435 | 0.0688 | 24.993 | 0.3089 | — | — | — |
| `matched_n_joint_shift` | 30.60249 | 0.0411 | 4.087 | 0.4178 | — | — | — |
| `matched_n_cond_scale` | 35.83222 | 0.0774 | 22.600 | 0.3094 | — | — | — |
| `matched_n_joint_scale` | 30.77858 | 0.0447 | 3.486 | 0.4179 | — | — | — |
| `over_joint_shift` | 32.48272 | 0.0504 | 11.763 | 0.4178 | — | — | — |
| `reverse_joint_shift` | 30.89360 | 0.0959 | -10.135 | 0.4659 | — | — | — |
| `permuted_shift` | 30.60249 | 0.0411 | 4.087 | 0.4178 | — | — | — |
| `nihilist_zero` | 89.20971 | 0.3965 | -89.207 | 1.0000 | — | — | — |
| `zero_width` | 39.72442 | 0.3043 | -4.684 | 0.3909 | — | — | — |
| `max_width` | 39.64389 | 0.1955 | 13.380 | 0.4233 | — | — | — |
| `climatology_bank` | 44.41722 | 0.0447 | 3.870 | 0.4354 | — | — | — |

- realized cell `P(0)` (pooled): 0.5532 · NF-W7f recorded 0.5563 against a served 0.2983

### The registered clause battery

| clause | class | verdict |
|---|---|---|
| `beats_foil` | statistical | ❌ |
| `not_a_foil_tie` | anchor | ❌ |
| `fold_consistency` | statistical | ❌ |
| `pbo_ok` | statistical | ❌ |
| `dsr_ok` | statistical | ❌ |
| `fdr_ok` | statistical | ❌ |
| `coverage_floor_ok` | constraint | ✅ |
| `assembled_pit_preserved` | constraint | ✅ |
| `assembled_crps_no_harm` | constraint | ✅ |
| `cell_pit_not_degraded` | anchor | ✅ |
| `degenerates_lose` | anchor | ✅ |
| `magnitude_anchors_lose` | anchor | ✅ |
| `winner_own_form_floor` | anchor | ✅ |
| `transform_identities_hold` | anchor | ✅ |
| `incumbent_reproduces` | anchor | ❌ |

- coverage: {"coverage_80": 0.8156, "n_rows": 1372, "binomial_se": 0.0108, "floor": 0.8, "blocking_shortfall": false}
- assembled PIT (bar 0.05): {"bar": 0.05, "per_fold": [0.03263785394932936, 0.03409415121255349], "n_folds": 2, "n_evaluable": 2, "n_unreadable": 0, "n_clearing": 2, "worst": 0.03409415121255349, "mean": 0.033366002580941426, "passes": true}
- cell PIT: {"winner": 0.05093086095869005, "incumbent": 0.05952195182100936, "w6d_default_bar_disclosure": 0.03, "note": "a NO-HARM clause against the served cell; the 0.03 figure is NF-W6d's Phase-C DEFAULT bar, disclosed and NEVER a gate here (E2.1-r)"}
- per-form oracle pairs (a TIE is INACTIVE, never a refusal — NF-W6d/NF-D20): {"zm_only": {"state": "ACTIVE_AND_RESPECTED", "passes": true, "inactive": false, "gap": 6.095490098830634}, "cond_shift": {"state": "ACTIVE_AND_VIOLATED", "passes": false, "inactive": false, "gap": -7.011126089480896}, "joint_shift": {"state": "ACTIVE_AND_VIOLATED", "passes": false, "inactive": false, "gap": -0.7149414737252364}, "cond_scale": {"state": "ACTIVE_AND_VIOLATED", "passes": false, "inactive": false, "gap": -8.422704914415448}, "joint_scale": {"state": "ACTIVE_AND_VIOLATED", "passes": false, "inactive": false, "gap": -1.2716926421965802}}
- degenerates lose: {"nihilist_zero": true, "zero_width": true, "max_width": true, "climatology_bank": true} · magnitude bracket loses: {"over_joint_shift": true, "reverse_joint_shift": true}
- BH (§12A A2, over all five real arms): {"pvals": {"zm_only": null, "cond_shift": null, "joint_shift": null, "cond_scale": null, "joint_scale": null}, "rejected": {"zm_only": false, "cond_shift": false, "joint_shift": false, "cond_scale": false, "joint_scale": false}, "q": 0.1, "note": "prereg \u00a712A A2 \u2014 BH over ALL FIVE real arms (stricter than the two registered contrasts; it can only prevent a false ADD)"}

## Family C — the assembled QB read, and the §8.1 measured Z-column activity

> ⭐ The consumed QB generator is `zm_floor`, which ALREADY re-splices all thirteen legs, and the re-splice is idempotent under the RAISE-ONLY rule — so the Z column was PREDICTED (before the run) to be a structural no-op at the ASSEMBLED layer. Measured, never assumed; an inactive arm is UNINFORMATIVE, never a pass (NF-D20).

| comparison | active folds / folds | max abs CRPS gap | inactive |
|---|---|---|---|
| `identity_vs_zm_only` | 0/2 | 0.000000000 | ✅ |
| `cond_shift_vs_joint_shift` | 1/2 | 0.069785886 | ❌ |
| `cond_scale_vs_joint_scale` | 1/2 | 0.135130398 | ❌ |

### ⭐ The cell's own channel, before and after

> NF-W8-0c recorded `passing_yards` at -0.3975 PPR (conditional -0.3878) under `identity`; a row-pooled read (NF1.8), never a mean of fold means

| arm | `passing_yards` contribution (PPR) | its conditional part (PPR) |
|---|---|---|
| `identity` | -0.2832 | -0.2861 |
| `zm_only` | -0.2832 | -0.2861 |
| `cond_shift` | 0.3840 | 0.3850 |
| `joint_shift` | 0.0310 | 0.0299 |
| `cond_scale` | 0.4916 | 0.4932 |
| `joint_scale` | 0.0072 | 0.0060 |

## Family D — the DOWNSTREAM cross-position verification

> ⭐ Every arm's row is REPORT-ONLY (prereg §12A A8). The verdict reads the closure of the §7 winner and nothing else — an arm that lost the registered contest can never be promoted on this table (E2.1-r).

### under `identity` — `gap_detected` **False** · QB pooled bias -0.4062 PPR

| pair | gap (PPR) | SE | MDE | below MDE | BH rejected |
|---|---|---|---|---|---|
| QB|RB | -0.1566 | 0.2350 | 0.6584 | — | ❌ |
| QB|WR | -0.5345 | 0.0669 | 0.1874 | ❌ | ❌ |
| QB|TE | -0.2197 | 0.0493 | 0.1382 | ❌ | ❌ |
| RB|WR | -0.3778 | 0.1681 | 0.4709 | — | ❌ |
| RB|TE | -0.0630 | 0.1857 | 0.5202 | — | ❌ |
| WR|TE | 0.3148 | 0.0176 | 0.0492 | — | ❌ |

- QB pairs all below their MDEs: ❌ · none BH rejected: ✅

### under `zm_only` — `gap_detected` **False** · QB pooled bias -0.4062 PPR

| pair | gap (PPR) | SE | MDE | below MDE | BH rejected |
|---|---|---|---|---|---|
| QB|RB | -0.1566 | 0.2350 | 0.6584 | — | ❌ |
| QB|WR | -0.5345 | 0.0669 | 0.1874 | ❌ | ❌ |
| QB|TE | -0.2197 | 0.0493 | 0.1382 | ❌ | ❌ |
| RB|WR | -0.3778 | 0.1681 | 0.4709 | — | ❌ |
| RB|TE | -0.0630 | 0.1857 | 0.5202 | — | ❌ |
| WR|TE | 0.3148 | 0.0176 | 0.0492 | — | ❌ |

- QB pairs all below their MDEs: ❌ · none BH rejected: ✅

### under `cond_shift` — `gap_detected` **False** · QB pooled bias 0.2457 PPR

| pair | gap (PPR) | SE | MDE | below MDE | BH rejected |
|---|---|---|---|---|---|
| QB|RB | 0.4952 | 0.8869 | 2.4847 | — | ❌ |
| QB|WR | 0.1174 | 0.7188 | 2.0137 | ✅ | ❌ |
| QB|TE | 0.4322 | 0.7012 | 1.9645 | ✅ | ❌ |
| RB|WR | -0.3778 | 0.1681 | 0.4709 | — | ❌ |
| RB|TE | -0.0630 | 0.1857 | 0.5202 | — | ❌ |
| WR|TE | 0.3148 | 0.0176 | 0.0492 | — | ❌ |

- QB pairs all below their MDEs: ✅ · none BH rejected: ✅

### under `joint_shift` — `gap_detected` **False** · QB pooled bias -0.0991 PPR

| pair | gap (PPR) | SE | MDE | below MDE | BH rejected |
|---|---|---|---|---|---|
| QB|RB | 0.1505 | 0.5421 | 1.5188 | — | ❌ |
| QB|WR | -0.2273 | 0.3740 | 1.0479 | ✅ | ❌ |
| QB|TE | 0.0875 | 0.3565 | 0.9987 | ✅ | ❌ |
| RB|WR | -0.3778 | 0.1681 | 0.4709 | — | ❌ |
| RB|TE | -0.0630 | 0.1857 | 0.5202 | — | ❌ |
| WR|TE | 0.3148 | 0.0176 | 0.0492 | — | ❌ |

- QB pairs all below their MDEs: ✅ · none BH rejected: ✅

### under `cond_scale` — `gap_detected` **False** · QB pooled bias 0.3514 PPR

| pair | gap (PPR) | SE | MDE | below MDE | BH rejected |
|---|---|---|---|---|---|
| QB|RB | 0.6009 | 0.9926 | 2.7808 | — | ❌ |
| QB|WR | 0.2231 | 0.8245 | 2.3098 | ✅ | ❌ |
| QB|TE | 0.5379 | 0.8069 | 2.2606 | ✅ | ❌ |
| RB|WR | -0.3778 | 0.1681 | 0.4709 | — | ❌ |
| RB|TE | -0.0630 | 0.1857 | 0.5202 | — | ❌ |
| WR|TE | 0.3148 | 0.0176 | 0.0492 | — | ❌ |

- QB pairs all below their MDEs: ✅ · none BH rejected: ✅

### under `joint_scale` — `gap_detected` **False** · QB pooled bias -0.1222 PPR

| pair | gap (PPR) | SE | MDE | below MDE | BH rejected |
|---|---|---|---|---|---|
| QB|RB | 0.1273 | 0.5190 | 1.4539 | — | ❌ |
| QB|WR | -0.2505 | 0.3509 | 0.9830 | ✅ | ❌ |
| QB|TE | 0.0643 | 0.3333 | 0.9338 | ✅ | ❌ |
| RB|WR | -0.3778 | 0.1681 | 0.4709 | — | ❌ |
| RB|TE | -0.0630 | 0.1857 | 0.5202 | — | ❌ |
| WR|TE | 0.3148 | 0.0176 | 0.0492 | — | ❌ |

- QB pairs all below their MDEs: ✅ · none BH rejected: ✅

## Null classification

```
{
  "state": "UNDEFINED",
  "reason": "`crps_q199|QB|passing_yards`: 2 fold(s) < 4 \u2014 CSCV/PBO is UNDEFINED, so the \u00a70.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no gate choice fixes this; only more folds do.",
  "retest_trigger": null,
  "folds_have": 2,
  "folds_needed": 4,
  "extra_seasons": 2,
  "max_field_size": null,
  "detail": {
    "n_folds": 2,
    "n_arms": 5
  },
  "field_remedy_admissible": null,
  "failing_checks": [
    "beats_foil",
    "fold_consistency",
    "pbo_ok",
    "dsr_ok",
    "fdr_ok",
    "not_a_foil_tie",
    "incumbent_reproduces"
  ],
  "binding_half": "mixed",
  "lockstep": {
    "evaluable": true,
    "sr0": 0.2309,
    "observed_sr": -0.2742002927919616,
    "sr_minus_sr0": -0.5051002927919617,
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

_runtime 122.8s_
