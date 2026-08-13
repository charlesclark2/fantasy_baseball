# NF-MARGIN2 pre-registration — tail-extension-ONLY recalibration vs the champion

**Committed BEFORE the bake-off run.** Constants live in `margin2_tail_extension.py`; the runner
(`run_nf_margin2_tail_extension.py`) reads them (NF-D16 discipline). This file is the narrative
copy.

> ⚖️ Edge-independent projection product — `best_alpha = 0`, **deploy-held**: this story promotes
> nothing, publishes nothing, retrains nothing. A clearing arm's serving path (attach the
> per-position tail model to the served quantile bank — serving-side, no refit) is blocked on
> NF-C6 Ph2 + NF-G0 and is an operator decision.

## 1. Why this story — the MH2.2-legitimate successor, stated candidly

NF-MARGIN1 demonstrated the TAIL CHANNEL at all four positions (`pit_recal_tail` −
`pit_recal_pos`: +0.0054/+0.0031/+0.0039/+0.0017 CRPS/wk QB/RB/WR/TE, 8/8 fold wins each, every
CI95 excluding zero, BH-binding own-family AND pooled) while its ARM verdicts were refused at the
ship bar by DSR (0.51–0.61 vs 0.95) — the field-composition tax of a 6-config eligible set that
deliberately carried the diagnosis-priced weak arms. MH2.2 forbids the shortcut: ⛔ NF-MARGIN1's
field may NOT be shrunk post hoc to rescue its winner. The legitimate path is THIS: a **fresh
pre-registration of the single demonstrated contrast**, as a NEW construction, with the full gate
battery.

**Candor about the evidence base (recorded so nobody has to discover it):** the fold axis is the
same 8 half-season blocks NF-MARGIN1 used — this is a re-test on overlapping data, not
independent replication. Three things keep it from being selection laundering: (a) the arm is a
construction NF-MARGIN1 **never scored** — tail extension on the RAW champion shoulders
(`tail_ext`), not the recorded `pit_recal_tail` (tail on recalibrated shoulders) — and it is the
exact serving-shaped object; (b) the family is declared at n=1 BEFORE the run, with the
contrast, gates, and anchors fixed here; (c) the anchors (peeking oracle at matched n, magnitude
degenerate, permutation decomposition) can each still refuse it. A future truly-out-of-sample
fold (2026H1) is the independent replication; it is named in §9.

## 2. The single arm

`tail_ext` — the champion's served 39-level bank, evaluated on the 199-level grid with the
**per-position exponential mean-excess tail model** beyond the grid ends (`MC.fit_tail_betas`:
beta_hi = mean excess above q975, beta_lo below q025, exponential MLE; a side with < 10
exceedances collapses loudly to the clamp). **Identity map within the grid** — every eval level
in [0.025, 0.975] is byte-identical to the incumbent bank (asserted at runtime, guard-tested).
Fit on the purged calibration slice (`MC.calibration_split`: most recent train weeks totaling
≥ max(6000, 20%·train) rows, champion refit on the remaining core with the PURGE_WEEKS gap —
honest OOS exceedances; in-sample exceedances of a boosted model under-fit the betas).

**Foil:** `incumbent` — the champion as served (flat tails). The contrast IS the story.

## 3. Metrics + the instrument change the arm forces

- **PRIMARY (selects + gates): `crps_q199`** (NF-MARGIN1's declared reason verbatim: the defect
  lives beyond the champion's grid; `crps_q39` is structurally blind to any tail model). Only 8
  of 199 eval columns can differ from the incumbent (4/side beyond the grid ends) — the channel
  is small BY CONSTRUCTION and the metric sees exactly that channel.
- **PIT accounting runs on the 199-level bank** (`randomized_pit_levels`, the levels-generalized
  `OA.randomized_pit`; guard: byte-identical to `OA.randomized_pit` on a 39-level bank). ⚠️ WHY
  (NF-D20 (g⁗) — the instrument must be able to see the fix): the arm's 39 champion-grid columns
  are byte-identical to the incumbent's, so the 39-level PIT CANNOT move — a flatness or
  tail-mass check computed there would be STRUCTURALLY INACTIVE and read as an uninformative
  pass. The 199-level PIT resolves the extension.
- **Declared structurally INACTIVE for this arm, by construction (reported as facts, never
  gates):** Winkler-80, coverage(50/80/95) — all read within-grid columns only, so their deltas
  vs the incumbent are IDENTICALLY ZERO (the runner asserts this each fold; a nonzero delta is a
  harness bug, not a finding). NF-MARGIN1's `interval_score_improves`/`pit_flatness_improves`
  clauses are therefore NOT carried — carrying a clause the mechanism cannot move would count an
  inactive gate as evidence (NF-D20 (g⁗)).
- Co-reported, never select: coverage_99 (the only coverage the arm can move), the cov95≡cov99
  flat-tail fingerprint (must BREAK under a real tail), Var(z), max-decile-dev, and the
  **team-total re-check** (NF-W5 CRN machinery verbatim; the incumbent row should reproduce
  NF-MARGIN1's 0.6794 — a reproduction anchor, report-only).

## 4. The two-sided calibration gate (the story card's clause, operationalized)

- ⚠️ **A gate the design almost shipped inactive (recorded per NF-D20 (g⁗)):** the natural
  statistic — beyond-CHAMPION-grid PIT mass vs its nominal 0.025/side — is **ARM-INVARIANT**
  for a tail-only construction: the extension redistributes mass WITHIN (0.975, 1) but cannot
  change how often y exceeds q975. A clause on it could never move and would read as an
  uninformative pass/fail. Caught at design time; it is co-reported as an arm-invariant
  diagnostic, never gated.
- **`tail_mass_toward_nominal`** (gate): pooled 199-level randomized-PIT beyond-**EVAL**-grid
  deviation `D = |P(u<0.005) − 0.005| + |P(u>0.995) − 0.005|` must strictly FALL vs the
  incumbent. The flat incumbent piles ALL beyond-champion-grid mass into the end cells
  (u ~ U(0.995, 1) above / U(0, 0.005) below ⇒ ≈0.04 per side vs nominal 0.005); a correct tail
  spreads it to nominal; an OVER-extended tail pushes it BELOW nominal and D rises again — the
  clause fails from either side (E2.1-r: a deviation-from-nominal on a DENSITY account, not a
  |coverage − target| criterion; coverage itself stays a floor).
- **Coverage(80) floor 0.80** (3-SE blocking, pooled per position) stays in the statistical set.
  Declared: it is INACTIVE for this arm by construction (cov80 is identical to the incumbent's,
  which NF-MARGIN1 measured 0.825–0.882, all above the floor) — it can only fire on a harness
  defect, and passing it is NOT evidence (NF-D20 (g⁗) — the active-clause count is stated).

## 5. Anchors (excluded from the DSR trial field; PBO see §6)

- `zero_width` + `max_width` — the two-sided sharpness degenerates (NF1.7 (c)); `max_width` must
  SATISFY the coverage floor while losing the primary (NF1.8's floor-is-a-constraint proof).
- `over_ext` — the arm's own betas × 3.0 (**the magnitude degenerate, registered to LOSE**,
  NF-D20: scored, never reasoned about). If `over_ext` BEATS `tail_ext`, the mean-excess fit
  UNDER-extends and the magnitude hypothesis is refuted — recorded as a decomposed refutation,
  never re-labelled.
- `permuted_tail` — betas fit on within-(position, week) permuted outcomes. ⭐ **Registered
  expectation (NF-D16 (2) — a permutation is near-vacuous against a MARGINAL hypothesis):** the
  tail model is a per-position marginal object, so `permuted_tail` is EXPECTED to also beat the
  incumbent (misalignment inflates betas somewhat but the marginal channel survives a
  within-group shuffle). Its role is ATTRIBUTION, not refutation: `incumbent − permuted_tail` =
  the marginal share, `permuted_tail − tail_ext` = the row-alignment share; expected
  marginal-dominant. The only GATE clause is `permutation_not_better`: `permuted_tail` must not
  significantly BEAT `tail_ext` (one-sided p ≥ 0.05; an unevaluable p with a positive mean fails
  CLOSED, NF1.7 (a)). ⛔ NF-MARGIN1's `winner_beats_permuted`-style clause is NOT carried — for
  a marginal mechanism it would demand the arm beat an anchor that legitimately shares the
  mechanism (an expected-tie mis-registered as a discriminating test).
- `pooled_tail` — betas fit position-POOLED (the NF1.8 pooled-conformal analogue): prices
  whether per-position conditioning earns anything IN THE TAIL. Report-only; informs whether the
  serving object is per-position or pooled betas.
- `oracle__tail_ext` — betas fit on the TEST fold's own exceedances (peeking, same form),
  floored AT MATCHED n via `matched_n__tail_ext` (refit on the most recent min(n_test, n_cal)
  calibration rows — NF1.9 (f)).

## 6. Deflation — the honest 1-arm reading, declared in advance

- **PBO: UNDEFINED BY DESIGN** (`GE.pbo_is_evaluable(1)` is False — CSCV resamples a FIELD; one
  pre-registered contrast has no search to overfit). Declared before the run; deliberately NOT a
  gate (the NF-W4 Layer-B precedent verbatim; NF-W3's mis-specification not repeated).
- **DSR ≥ 0.95 with n_trials = 1**: `deflated_sharpe` at a single trial has SR0 = 0, so DSR
  reduces to the probabilistic Sharpe ratio of the contrast — at 8 folds it needs a per-fold
  Sharpe ≥ ~0.62. That is the point of the fresh registration: a pre-registered single contrast
  carries no search to deflate. Anchors never enter the trial field (MH2.1 (a)) — automatic
  here, the field is the arm alone. The DSR-CONV degenerate-exclusion question is MOOT at n=1
  and no opt-in is declared.
- Fold clause: `cv_power.fold_consistency_clause(8)` → 6/8 wins required (MH2 H8).
- **FDR: ONE pre-registered family** `{margin2_tail_QB, margin2_tail_RB, margin2_tail_WR,
  margin2_tail_TE}`, BH at q = 0.10. There is no second family; own-family is the pooled
  correction.
- Null classification: 1-arm family ⇒ **hand classification per `GE.classify_layer_b`** (the
  `classify_null` n_arms=1 "+N folds" mis-render is the known instrument bug — 4th/5th
  occurrences recorded in NF-W3/NF-W4); the instrument's verdict is recorded alongside, never
  discarded. Anchor/calibration-only refusals → CONSTRAINT_REFUSED (NF-D18/MH2.7), no
  sample-size trigger.

## 7. The gate (per position; SHIP = all clauses)

`beats_champion` (crps_q199) ∧ `fold_consistency` ∧ `dsr_ok` ∧ `fdr_ok` ∧ `coverage_floor_ok`
(declared inactive — see §4) ∧ `degenerates_lose` (zero_width, max_width, over_ext) ∧
`permutation_not_better` ∧ `oracle_floor_respected` (at matched n) ∧ `tail_mass_toward_nominal`.
PBO deliberately absent (§6).

## 8. Expectations fixed by NF-MARGIN1's record (attributable in advance)

- The contrast is expected POSITIVE at every position with QB largest / TE smallest (the
  MARGIN1 tail-channel ordering), of order +0.002…+0.006 CRPS/wk — the tail term transfers onto
  raw shoulders approximately unchanged (shoulder recal and tail extension touched disjoint
  levels there too).
- The per-fold consistency is expected to resemble the MARGIN1 tail-channel contrast (8/8) more
  than its arm contrast (4–7/8): within-grid columns are identical, so per-row CRPS deltas carry
  NO shoulder noise.
- `permuted_tail` expected to beat the incumbent (marginal mechanism) and be ≈ tied-or-slightly
  behind `tail_ext`; `pooled_tail` expected close to `tail_ext` (position tails differ in scale
  — QB betas largest — so per-position should earn a small positive margin).
- Team-total coverage(80) expected to move from ≈0.679 toward ≈0.75 (MARGIN1 measured 0.7511
  under tail-on-recalibrated-shoulders; tail-only should land nearby), with the above-q90 share
  moving toward nominal and the below-q10 residual left standing (the NF-W4-measured
  unforecastable direction).
- If the effect is real but DSR still refuses at PSR — there is no field tax left to blame; the
  verdict is the design's own power and is recorded per §6 classification, with the margin in
  folds.

## 9. Folds / constants / constraints

The NF-W1 axis verbatim: 8 expanding-window half-season blocks 2022H1…2025H2, PURGE_WEEKS = 2,
DSR ≥ 0.95, FDR q = 0.10, coverage floor 0.80 (3-SE blocking), seed **20260813** (fresh; the
primary metric is deterministic — the seed touches only PIT randomization and the permutation
draw, so no verdict can turn on it). Capture-era folds (2025H1, 2025H2) reported separately
(report-only, NF-W2d/W2e). Matrix = `build_matrix_w2d` verbatim; NF-W0 constraints inherited —
NF-MARGIN2 introduces NO new source, NO new features, NO new joins; its only inputs are the
champion's own predictive quantiles and the realized `fantasy_points` label. Reducers refuse
non-finite predictives; verdict words three-way and derived at report time (NF-W2e);
`--rewrite-report` re-derives the verdict layer with zero refit. **Independent replication:**
the first genuinely out-of-sample read is a 2026H1 fold when that data exists — named here so
the re-test is a calendar fact, not a post-hoc choice.
