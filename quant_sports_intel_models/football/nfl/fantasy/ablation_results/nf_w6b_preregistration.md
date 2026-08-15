# NF-W6b — Pre-registration: the per-stat distributional successor (the CEILING-GATE[BUILD] license)

**Committed BEFORE the full run** (the §0.5 discipline). Every constant named here lives in
`stat_distributions.py` and the runner READS it (NF-D16). `best_alpha` N/A · **deploy-held** ·
research-only, no changelog entry. **This is a FRESH REGISTRATION** — ⛔ nothing from NF-W6's
oracle field is promoted into this field (MH2.2: you may pre-register a family, you may not
discover one; the oracle/matched-n labels of NF-W6 appear here only as newly-registered
DIAGNOSTIC anchors, never as trials).

## 0. The license and the scope

NF-W6's oracle gate returned **CEILING-GATE[BUILD]**: 7 cells clear the YES band (ceiling
6.7–17.1% of binding-incumbent CRPS) and the matched-n controls attributed the headroom to
**FORM, not information** — the champion's per-stat emission (LGBM mean + position-constant
residual bank) under-prices the zero atom (pred P(0) 0.23–0.32 vs realized 0.40–0.69 on yards
cells) and expresses no conditional spread. This story is the licensed successor: a
per-cell-family §0.5 bake-off of distributional FORMS that price the atom and the conditional
spread.

**The 8 cells** (7 YES + 1 by PM ruling, carrying the multiplicity):

| position | stats |
|---|---|
| QB | passing_yards, passing_tds, rushing_yards |
| RB | rushing_yards, rushing_tds ⭐(PM ruling: RB rushing_tds — MARGINAL 4.08% — admitted as an 8th cell), receiving_yards |
| WR | receiving_yards |
| TE | receiving_yards |

⛔ **The 4 TD-NO cells stay closed** — QB rushing_tds, RB/WR/TE receiving_tds. NF-W6 measured a
discrete climatology near-optimal there (0.07–0.38% ceiling); re-opening them needs a different
MECHANISM, not more data. A guard fails if any of them enters this field.

**Mechanism constraint (the whole point of the matched-n attribution):** the arms price the
zero atom and the conditional spread — hurdle / quantile-type forms over the champion feature
set. ⛔ No exotic features (the bar to clear is the FORM change itself); ⛔ nothing re-opens the
dead W3/W4/W5 environment/availability/correlation channels; the NF-MARGIN1 exponential
mean-excess tail is carried from day one (a fresh knot-quantile distributional target has
truncated tails). No pbp source is read (the NF-W3 franchise-code traps honored by absence);
the matrix is the NF-W6 certified build (NF-W1 matrix + conservation-guarded TD labels, PIT
gate on every load), so no `fillna(0)` on any NULL-bearing feature arises.

## 1. The field (per cell; pooled fits, per-cell scoring)

**Real arms — 4 learner classes**, each an (n, 199)-quantile bank on the NF-MARGIN1 dense grid:

- `lgbm_quantile_tail` — the champion representation a build would inherit: pooled 9-knot LGBM
  quantile bank per stat (champion `_lgbm` construction, position code appended) + per-position
  exponential mean-excess tails beyond the end knots, **fit on a purged calibration slice**
  (`MC.calibration_split`; NF-MARGIN1: in-sample tails of a boosted model are optimistically
  sharp).
- `lgbm_hurdle_tail` — the per-stat hurdle: champion-construction LGBM P(y=0) classifier ×
  conditional-on-nonzero 9-knot quantile bank + calibration-slice tails, mixed exactly
  (`p0·δ0 + (1−p0)·F_cond`, negative conditional mass handled — yards can be negative). The
  form that prices the atom DIRECTLY.
- `enet_residual` — the linear class: ElasticNet mean (median-imputed, standardized) + a
  per-position empirical residual bank fit on the SAME purged calibration slice (honest OOS
  residuals — structurally the incumbent wrapper with a linear head, the "is LGBM earning
  anything" control).
- `knn_quantile` — the neighborhood class (the NF1.9 winner's shape): per-position standardized
  kNN (k=300), empirical 199-level quantiles of the neighbors' realized stat. Prices atom and
  conditional spread nonparametrically.

**Foils (never shippable; the BINDING one — better mean fold CRPS per cell — sets the bar):**
`inc_head_bank` (the champion-faithful incumbent wrapper: full-train champion component-head
mean + purged-calibration per-position residual bank — NF-W6's incumbent, verbatim, via the
same code) and `inc_climatology` (per-position train marginal). `inc_head_bank` is the
"direct-learned foil" of the story card: the champion's own direct-learned mean wrapped in the
minimal distributional costume. The DoD contest is winner vs the BINDING incumbent.

**Diagnostic anchors — scored every cell, never trials (MH2.1 (a): excluded from PBO's field
and from the DSR trial set):** `nihilist_zero` (all-zero; must LOSE — the CRPS-soundness proof
on atom-heavy cells, NF-D11), `zero_width` (point mass at the incumbent conditional median) +
`max_width` (×3 spread) — the two-sided sharpness degenerates (NF1.7 (c); `max_width` satisfies
any coverage floor and must still lose CRPS, the NF1.8 floor-is-a-constraint proof),
`permuted_quantile` (the full `lgbm_quantile_tail` construction — identical code path,
calibration split and tails included — on labels permuted within (position, global week); must
lose, and its lift vs the binding foil must not be significant), `oracle_marginal` (the
block-peeking per-position marginal) + `matched_marginal` (the same form at matched n — NF1.9
(f)). ⭐ The conditional winner beating `oracle_marginal` is legitimate cross-form capacity and
is REPORTED, never a veto (the NF-W1 stance); the matched pair is what makes that reading
attributable.

## 2. Metric, folds, and the coverage clause

- **Primary: `crps_q199`** (the NF-MARGIN1 dense grid, imported) — the 39-level grid is blind
  to beyond-knot tail work. TD cells are zero-heavy ⇒ CRPS, never MAE (NF-D11/D14; an AST guard
  bans MAE from the module and runner). One reducer for every construction; it REFUSES
  non-finite predictives and labels (NF-W3 (b)).
- **Folds:** the 8 NF-W1 expanding half-season blocks (2022H1…2025H2), purge 2 weeks — the axis
  verbatim. Era split (capture 2025H1/H2 vs legacy) REPORT-ONLY (NF-W2d/W2e); forward sizing
  quotes the capture era.
- **Coverage(80) is a FLOOR, never a target** (E2.1-r/NF1.8): the winner's pooled coverage may
  not fall below 0.80 by more than 3 binomial SE (`coverage_floor_ok`, gated). ⭐ **Why the
  floor is deliberately ONE-SIDED on this population (pre-registered, with the vertical's own
  precedent):** these targets carry a 0.40–0.69 zero atom, and an HONEST atom-pricing
  predictive has q10 = 0 on most rows, so the inclusive central interval structurally covers
  the whole atom — coverage(80) ≈ P(y ≤ q90) ≈ atom + 0.9·(1−atom) ≫ 0.80 for a CORRECTLY
  calibrated arm (NF1.9 (e): on a zero-atom population a two-sided coverage TARGET is
  structurally inverted — hitting 0.80 would require deliberately under-covering the right
  tail; E2.1-r (a): inclusive discrete bounds inflate coverage). An upper-side coverage gate
  would therefore refuse every honest winner on exactly the cells this story exists to fix.
  The TWO-SIDEDNESS the DoD demands is carried instead by the sharpness degenerates, both
  scored every cell: `zero_width` (maximally sharp) and `max_width` (maximally wide, floor-
  satisfying) must BOTH lose the primary metric — the NF1.7 (c)/NF1.8 two-sided bracket. The
  winner's coverage, the binding incumbent's coverage, and the structural expectation are all
  REPORTED per cell so an over-wide arm is visible, and the `max_width` anchor proves the
  metric eliminates that direction.
- **Zero-atom calibration** (pred P(0) vs realized, winner vs incumbent) is REPORTED per cell —
  the licensed mechanism made visible — never a selection criterion.

## 3. Deflation + multiplicity (full §0.5)

- **PBO < 0.20** over the ELIGIBLE field per cell = the 4 real arms + the 2 foils (the search
  the selection actually runs — NF1.8), via the NF18 CSCV `deflate` (flip distribution,
  Bailey's os-gap, contender spread reported beside it).
- **DSR ≥ 0.95** — deltas = winner vs binding foil per fold; trial Sharpe field = the 4 real
  arms' per-fold lifts vs the binding foil (anchors excluded — MH2.1 (a)). The vertical's
  direct `M14.deflated_sharpe` convention (DSR-CONV does not reach this vertical by
  declaration).
- **Fold clause:** `cv_power.fold_consistency_clause(8)` (calibrated, MH2 H8).
- **BH-FDR q=0.10 over TWO pre-registered families** — the 6 yards cells and the 2 TD cells —
  own-family AND pooled computed, a SHIP must survive BOTH (MH2 (a); the NF-W6 composer
  reused).

## 4. The decision rule (per cell; fails closed)

`SHIP` iff ALL of: `beats_foil` (paired mean lift > 0 vs the binding incumbent) ∧
`fold_consistency` ∧ `pbo_ok` ∧ `dsr_ok` ∧ `fdr_ok` (own AND pooled) ∧ `coverage_floor_ok` ∧
`degenerates_lose` (nihilist + zero_width + max_width) ∧ `permutation_behaves` (winner beats
the permuted arm AND the permuted lift vs the foil is not significant, unevaluable p failing
closed). Else a RECORDED per-cell null, hand-classified (⛔ `cv_power.classify_null` is never
invoked — the n_arms mis-render, 4× hand-corrected in this vertical):

- any statistical gate fails with the winner LOSING on average → **GENUINE_ABSENCE** (no
  re-test trigger);
- statistical gates fail with a positive point estimate → **POWER_LIMITED** (margin stated in
  folds; `flag_unsafe_field_shrink` applied to any remedy text);
- every statistical gate green, the null resting only on coverage/anchor clauses →
  **CONSTRAINT_REFUSED** (NF-D18/NF-W7: more data cannot change it; no sample-size trigger).

**Story verdict:** `PERSTAT[BUILD-k]` — per-cell SHIP/null, no story-level aggregation gate.

## 5. The assembled-PPR effect — REPORT-ONLY, not a gate (PM ruling)

The DoD is judged on **per-stat marginal CRPS** — the product-facing raw-line question; honest
per-stat distributions do not exist today and are the arbitrary-league re-scoring substrate.
The assembled-points effect is reported as each cell's CRPS lift × its PPR weight
(0.04/pt passing yards, 4 passing TDs, 0.1 rushing/receiving yards, 6 rushing TDs), summed per
position — a sum of MARGINAL contributions in points units, ⛔ NOT an assembled joint-points
CRPS claim (the champion's points hurdle already conditions on usage — NF-W1; the correlation
channel is measured-dead — NF-W5). A per-stat win need not move assembled points, and the
deliverable does not depend on it.

## 6. Instrument validation (before the full run is trusted)

- The smoke HARD-asserts, per scored cell, that all three degenerates LOSE to the winner — the
  two-sided known-defect movability control (MH2.1 (d): `zero_width` is a known under-dispersion
  defect, `max_width` a known over-dispersion defect; an instrument that cannot see either
  refuses the smoke).
- Guards RED-prove every gate clause with one ISOLATING fixture per clause (NF-D17), assert
  mutations LAND (E11.24 #682), assert non-vacuity of every iterating check, ban MAE by AST,
  pin the closed cells out of the field, pin anchors out of the PBO/DSR fields (MH2.1 (a)/
  MH2.2), and scan the modules deploy-held (no registry/S3/serving writes).

## 7. What this story cannot ship

Deploy-held: promotes nothing, publishes nothing, retrains nothing, writes no registry/S3/
serving surface. The only outputs are `ablation_results/` artifacts and the catalog record.
A SHIP verdict licenses a wiring/promotion story under NF-G0 governance; it does not execute one.

_Seed 20260815 · folds/purge/features/PBO/DSR/FDR constants imported from `weekly_projection`
(never re-typed) · matrix = the NF-W6 certified build (`nf_w6_stat_matrix_*`, PIT-gated on
every load)._
