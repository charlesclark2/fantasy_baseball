# NF-MARGIN3 pre-registration — a better QB/WR tail-magnitude estimator vs `tail_ext`

**Committed BEFORE the bake-off run.** Constants live in `margin3_tail_estimator.py`; the runner
(`run_nf_margin3_tail_estimator.py`) reads them (NF-D16 discipline). This file is the narrative
copy.

> ⚖️ Edge-independent projection product — `best_alpha = 0`, **deploy-held**: this story promotes
> nothing, publishes nothing, retrains nothing. If the arm clears at QB/WR, the serving change is
> attaching the QB/WR tail offsets to the champion's served quantile bank (serving-side, no
> refit) — completing the tail fix at all four positions — and it stays blocked on NF-C6 Ph2 +
> NF-G0 as an operator decision.

## 1. Why this story — the NF-MARGIN2 refusal, decomposed and answered

NF-MARGIN2 proved the tail channel real and statistically clean at ALL FOUR positions
(+0.0040/+0.0028/+0.0032/+0.0015 CRPS/wk QB/RB/WR/TE, 8/8 folds each, p≈0, DSR(=PSR) 1.0,
BH-binding) and SHIPPED `tail_ext` at RB/TE. QB/WR were **CONSTRAINT_REFUSED by the anchors, not
the statistics**: `over_ext` (the arm's own betas × 3, registered to lose) beat the QB arm by
0.0002, and `permuted_tail` (misalignment-inflated betas) edged the arm at QB/WR (one-sided p
0.0488/0.0241). Two costumes, one finding: **the exponential mean-excess fit slightly
UNDER-extends at QB/WR — the CRPS-optimal tail magnitude lies beyond the mean-excess MLE.**
⛔ Per NF-D18/MH2.7 no sample-size trigger was published — more folds cannot fix a magnitude
estimator; the remedy is a SUCCESSOR estimator under a fresh registration. This is that
registration (MH2.2: a new pre-registration, never a post-hoc rescue of NF-MARGIN2's field).

**Candor about the evidence base:** the fold axis is the same 8 half-season blocks — a re-test
on overlapping data, not independent replication. What keeps it honest: (a) the arm is an
ESTIMATOR NF-MARGIN2 never scored, answering the specific quantity its anchors refuted; (b) the
family is declared at 1 arm × 2 live positions BEFORE the run, with the foil, gates, and anchors
fixed here; (c) the anchors can still refuse it — in particular `over_ext_eq` (×3 of offsets that
now sit AT the calibration pinball optimum) is a sharper refutation probe than NF-MARGIN2's,
because a win for it can no longer be explained by a biased base estimator. The first genuinely
out-of-sample read is a 2026H1 fold when that data exists (§9).

## 2. The single arm, and why this estimator

`eq_tail` — per-position, per-side **empirical-quantile tail offsets calibrated on the eval-end
exceedance rates** of the purged calibration slice (`MC.calibration_split`, honest OOS
exceedances, unchanged). For each beyond-grid eval level u ∈ {0.98, 0.985, 0.99, 0.995} the hi
offset is t_hi(u) = max(0, Q̂_D(u)) with D = y − q975(row) over ALL calibration rows of the
position; x(u) = q975(row) + t_hi(u). The low side mirrors it (t_lo(u) = max(0, Q̂_{q025−y}(1−u)),
x(u) = q025(row) − t_lo(u)). Identity map within the grid — byte-identical to the incumbent on
every eval level in [0.025, 0.975], asserted at runtime (the NF-MARGIN2 invariant verbatim).

**Why this is the right estimator for the refuted quantity:** the pooled pinball optimum at
level u for the shared-offset family x = q975(row) + t is exactly the t at which
P̂(y > q975 + t) = 1 − u — i.e. the empirical u-quantile of D. The estimator therefore targets
the METRIC OPTIMUM directly (the quantity `over_ext`/`permuted_tail` proved the mean-excess
proxy under-estimates), with no distributional form to mis-specify. It is the story card's
"beta calibrated on eval-end exceedances," generalized from one scale to the four gated levels
per side; where the exceedance law is heavier than exponential it extends further at the far
levels — subsuming, WITHIN the eval grid, what a shape-index fit would buy.

**Why not GPD (the named alternative, decided at design time, before any scoring):** (a) a GPD
MLE is still a FORM fit — a likelihood proxy for the metric optimum, which is the exact bias
class the NF-MARGIN2 anchors refused (the CRPS optimum of a mis-specified family ≠ its MLE);
(b) the shape parameter ξ at the ~40–80 exceedances a (fold, position, side) cell carries is
unstable; (c) the eval grid ends at 0.995, so the metric only probes the exceedance law to
conditional level ~0.9, where nonparametric quantiles are well-posed — parametric extrapolation
pays off only beyond the grid, which `crps_q199` cannot see.

**Declared two-sided:** relative to the exponential the estimator may extend LESS where the
exponential over-extends (WR's low side already sits slightly past nominal: p_below_eval 0.00437
vs 0.005), with a hard floor at the flat clamp (offsets ≥ 0 — the arm can never touch
within-grid columns). No widen-only clamp is declared (the `zscore_affine` precedent: two-sided
BY DECLARATION). A side with < MIN_TAIL_N (10) exceedances collapses loudly to the clamp; a
level whose raw quantile is ≤ 0 clamps to 0 and is COUNTED (`clamped_*`) — degradation is loud,
never silent (NF1.7 (a)).

**Foil: `tail_ext`** — ⭐ the standing object at every position (shipped at RB/TE), rebuilt
byte-identically to NF-MARGIN2's construction (the builder DELEGATES to `M2.build_bank_m2`).
⛔ NOT the flat-tail incumbent — that contest is already won; the incumbent enters only as a
REFERENCE (within-grid identity base, tail-mass continuity, reproduction anchors) and is
excluded from the eligible field.

## 3. Family, metrics, instrument

- **FAMILY = QB + WR** (the two refused positions), 1 arm each. **RB/TE are computed and
  REPORTED but registered NON-SHIPPABLE**: `tail_ext` stands there regardless of how `eq_tail`
  scores; a win at RB/TE is an out-of-family observation for a future registration, never a ship
  (NF-D20 decision-shape — eligibility, not a threshold, separates that null from a ship, and
  saying so here is what makes the record honest). RB/TE p-values do NOT enter the BH family.
- **PRIMARY (selects + gates): `crps_q199`**, deltas vs `tail_ext` per fold. Only the 8
  beyond-grid eval columns can differ between arm and foil — the contrast isolates the magnitude
  estimator and nothing else.
- **PIT accounting on the 199-level bank** (`randomized_pit_levels` — the NF-MARGIN2 instrument
  verbatim; the 39-level PIT is guard-proved blind to any tail-only construction).
- **Declared structurally INACTIVE (facts, never gates):** Winkler-80, coverage(50/80/95) —
  identical to the incumbent's for BOTH arm and foil by construction (asserted every fold; a
  nonzero delta is a harness bug). Coverage_99 is the only coverage the contrast can move
  (co-reported). The coverage floor stays in the statistical set and is declared inactive
  exactly as in NF-MARGIN2 (it can only fire on a harness defect; passing it is NOT evidence).

## 4. The tail-mass gate — proved arm-MOVABLE at design time (the story card's ⭐ clause)

- The gate statistic is NF-MARGIN2's: pooled beyond-EVAL-grid randomized-PIT deviation
  D = |P(u<0.005) − 0.005| + |P(u>0.995) − 0.005|, two-sided (an over-extended arm raises its
  own deviation from the other side).
- **`tail_mass_toward_nominal` (gate): D(eq_tail) must strictly UNDERCUT D(tail_ext)** — the
  bar is the foil, matching the primary contrast. D vs the incumbent is co-reported for
  cross-story continuity, never gated (that fall is already NF-MARGIN2's result).
- ⭐ **Design-time movability check (NF-D20 (g⁗)/NF-MARGIN2 §4, applied BEFORE registration):**
  beyond-CHAMPION-grid mass is arm-invariant for any tail-only construction (recorded again —
  diagnostic only). The beyond-EVAL-grid statistic IS movable by this arm relative to the foil:
  `eq_tail` places the 0.98…0.995 / 0.005…0.02 columns at different x than `tail_ext` whenever
  the exceedance law is not exactly exponential-at-assumed-mass, so P(u<0.005)/P(u>0.995) move.
  Guard-tested (`test_the_tail_mass_gate_is_arm_movable_vs_the_foil`): on a fat-tailed synthetic
  the two constructions produce different deviations and the calibrated arm's is smaller. A
  statistic the arm could not move would be décor, not a gate.
- ⚠️ Recorded risk, not smoothed over: at WR the foil's deviation is already small (0.00522),
  so the strict-fall clause is a tight bar; the per-side two-sided design (the low side may
  extend LESS) is what gives the arm a channel on both sides there. At QB the foil's deviation
  is 0.01024 with both sides still above nominal — headroom on both sides.

## 5. Anchors (excluded from the DSR trial field; PBO see §6)

- `zero_width` + `max_width` — the two-sided sharpness degenerates (NF1.7 (c)); `max_width`
  must SATISFY the coverage floor while losing the primary (NF1.8's floor-is-a-constraint
  proof, re-run every story).
- `over_ext_eq` — the arm's own offsets × 3.0 (**the magnitude degenerate, registered to
  LOSE**). Sharper than NF-MARGIN2's probe: the offsets sit AT the calibration pinball optimum,
  so a win for ×3 can no longer be explained by a biased base estimator — it would refute the
  calibrated-optimum hypothesis itself (recorded decomposed, never re-labelled).
- `permuted_eq` — offsets fit by the same estimator on within-(position, week) permuted
  outcomes. **Registered expectation:** in NF-MARGIN2 the misalignment-INFLATED permuted betas
  accidentally compensated for under-extension and won at QB/WR; a calibrated arm removes that
  headroom, so `permuted_eq` (inflated PAST the optimum) is expected to tie-or-lose. Gate
  clause `permutation_not_better`: it must not significantly BEAT the arm (one-sided p ≥ 0.05;
  an unevaluable p with a positive mean fails CLOSED, NF1.7 (a)). Attribution decomposition
  co-reported as in NF-MARGIN2.
- `pooled_eq` — offsets fit position-POOLED (report-only; informs whether the serving object is
  per-position or pooled).
- `oracle__eq_tail` — offsets fit on the TEST fold's own exceedances (peeking, same form),
  floored AT MATCHED n via `matched_n__eq_tail` (NF1.9 (f) — refit on the most recent
  min(n_test, n_cal) calibration rows).

## 6. Deflation — the honest 1-arm reading (NF-MARGIN2 §6 verbatim)

- **PBO: UNDEFINED BY DESIGN** (`GE.pbo_is_evaluable(1)` False — one pre-registered contrast
  has no search to overfit). Declared before the run; deliberately NOT a gate.
- **DSR ≥ 0.95 with n_trials = 1** ⇒ DSR reduces to the PSR of the contrast (per-fold Sharpe
  ≥ ~0.62 at 8 folds). Anchors and the incumbent reference never enter the trial field
  (MH2.1 (a)). DSR-CONV is MOOT at n=1; no opt-in declared.
- Fold clause: `cv_power.fold_consistency_clause(8)` → 6/8 wins required (MH2 H8).
- **FDR: ONE pre-registered family** `{margin3_tail_QB, margin3_tail_WR}`, BH at q = 0.10.
  Own-family IS the pooled correction; RB/TE contribute no hypotheses.
- Null classification: 1-arm family ⇒ hand classification per `GE.classify_layer_b` (the
  `classify_null` n_arms=1 "+N folds" mis-render is the known instrument bug; the instrument's
  verdict is recorded alongside, never discarded). Anchor/calibration-only refusals →
  CONSTRAINT_REFUSED, no sample-size trigger (NF-D18/MH2.7).

## 7. The gate (per LIVE position; SHIP = all clauses)

`beats_tail_ext` (crps_q199) ∧ `fold_consistency` ∧ `dsr_ok` ∧ `fdr_ok` ∧ `coverage_floor_ok`
(declared inactive — §3) ∧ `degenerates_lose` (zero_width, max_width, over_ext_eq) ∧
`permutation_not_better` ∧ `oracle_floor_respected` (at matched n) ∧ `tail_mass_toward_nominal`
(vs the FOIL — §4). PBO deliberately absent (§6).

## 8. Expectations fixed in advance (attributable, falsifiable)

- The headroom NF-MARGIN2's anchors exposed is SMALL: `permuted_tail` beat the arm by 0.00042
  (QB) / 0.00019 (WR) and `over_ext` by 0.0002 (QB) — so the expected arm-over-foil margin is of
  order +0.0002…+0.0008 CRPS/wk, an order of magnitude below the tail channel itself. The
  per-fold consistency question is whether a margin that small is stable across folds; the
  design accepts that a real-but-fold-inconsistent margin fails the gate honestly.
- `eq_tail`'s far-level offsets are expected ABOVE the exponential's implied t_exp(u) =
  beta·ln(0.025/(1−u)) at QB (both sides) and at WR's hi side; at-or-below on WR's lo side (the
  side already past nominal). The offsets-vs-implied ratio is co-reported per fold.
- `over_ext_eq` expected to LOSE everywhere; `permuted_eq` expected to tie-or-lose (the
  NF-MARGIN2 accident cannot recur for a calibrated arm unless cal→test drift is real, in which
  case the refusal is earned).
- Tail-mass deviation expected to fall vs the foil at QB (0.01024 → toward the randomized-PIT
  resolution floor) and at WR (0.00522 → smaller, via both sides).
- RB/TE (report-only): expected ≈ tie with `tail_ext` (mean-excess was already adequate there —
  `over_ext` lost at both). A small loss is also unremarkable (a quantile estimator pays
  variance for unbiasedness at n≈50–80 exceedances). Either way `tail_ext` stands by
  registration.
- Team-total re-check (report-only, NF-W5 CRN machinery verbatim): the incumbent row must
  reproduce 0.6794 and the `tail_ext` row 0.7052 (both from NF-MARGIN2; tolerance 0.005 —
  LightGBM thread scheduling is the only admissible wiggle). Per-position mean crps_q199 for
  `tail_ext` and `incumbent` must reproduce NF-MARGIN2's table (tol 0.002, report-only — the
  cross-story comparability anchors).
- If the statistics clear and only the anchors refuse again, the state is CONSTRAINT_REFUSED
  and the finding is that the pinball-optimum family itself (shared per-position offsets above
  per-row grid ends) is the wrong FORM at QB/WR — the next registration would need row-varying
  tail structure, not another magnitude estimator. Recorded in advance so the successor story
  starts from the right place.

## 9. Folds / constants / constraints

The NF-W1 axis verbatim: 8 expanding-window half-season blocks 2022H1…2025H2, PURGE_WEEKS = 2,
DSR ≥ 0.95, FDR q = 0.10, coverage floor 0.80 (3-SE blocking), seed **20260815** (fresh; the
primary metric is deterministic — the seed touches only PIT randomization and the permutation
draw). Capture-era folds (2025H1, 2025H2) reported separately (report-only, NF-W2d/W2e). Matrix
= `build_matrix_w2d` verbatim; NF-W0 constraints inherited — NF-MARGIN3 introduces NO new
source, NO new features, NO new joins; its only inputs are the champion's own predictive
quantiles and the realized `fantasy_points` label. Reducers refuse non-finite predictives;
verdict words three-way and derived at report time (NF-W2e); `--rewrite-report` re-derives the
verdict layer with zero refit. **Independent replication:** the first genuinely out-of-sample
read is a 2026H1 fold when that data exists — named here so the re-test is a calendar fact, not
a post-hoc choice.
