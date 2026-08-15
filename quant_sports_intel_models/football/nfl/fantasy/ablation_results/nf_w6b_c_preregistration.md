# NF-W6b-C — Pre-registration: RB rushing_tds fresh-family successor (atom-aware family only)

**Committed BEFORE the full run** (the §0.5 discipline). Every constant named here lives in
`stat_distributions_c.py` and the runner READS it (NF-D16). `best_alpha` N/A · **deploy-held** ·
research-only, no changelog entry. **This is a FRESH REGISTRATION** (MH2.2/E2.1-r): a NEW field
with a NEW seed (20260816), ⛔ not a re-score and not a trim of NF-W6b's field — the W6b record
stands untouched, and nothing is promoted from it into this field.

## 0. Why this field exists (PM Decision C, 2026-08-15)

NF-W6b found a REAL winner on RB|rushing_tds — `knn_quantile` beat the discrete climatology by
+13.0% CRPS (Δ +0.0194, CI95 [+0.0169, +0.0219]), 8/8 folds — that could never clear DSR **in
that field**: the pre-registered linear-residual arm (`enet_residual`, trial Sharpe **−9.199**
on an 86%-zero cell) lost enormously and consistently, inflating the cross-trial dispersion DSR
deflates against (**sr0 ≈ 7.32 > the winner's per-fold Sharpe 6.47**). ⛔ MH2.2 forbids trimming
a field after seeing results — the W6b DSR verdict is not revisited. The admissible successor is
a fresh registration whose declared family is **coherent and atom-aware only**, which also
removes the actual cause: a position-constant residual bank around a linear mean cannot express
an 86% atom, and its guaranteed huge loss re-inflates the very deflation bar that refused the
cell. With the incoherent class excluded **up front on mechanistic grounds**, DSR becomes
honestly evaluable — the field's dispersion measures how REAL candidates disperse.

**Scope: ONE cell — RB|rushing_tds.** ⛔ The four TD-NO cells (QB rushing_tds, RB/WR/TE
receiving_tds) stay closed — NF-W6 measured a discrete climatology near-optimal there
(0.07–0.38% ceiling); they need a different MECHANISM, not this. The other seven W6b cells are
decided and untouched. Guards pin both.

## 1. The declared field (before any scoring)

**Real arms — 3 classes, EVERY one atom-aware by construction (the coherence requirement):**

- `lgbm_hurdle_tail` — the W6b pinned code path, **imported by identity** (`SD.arm_lgbm_hurdle_tail`):
  champion-construction LGBM P(y=0) classifier × conditional-on-nonzero 9-knot quantile bank +
  purged-calibration exponential tails, mixed exactly. Prices the atom directly.
- `knn_quantile` — the W6b pinned code path, **imported by identity** (`SD.arm_knn_quantile`):
  per-position standardized kNN (k=300), empirical 199-level quantiles of the neighbors'
  realized stat. Prices the atom and the conditional spread nonparametrically. ⭐ It NESTS the
  foil (k → n reproduces the per-position climatology) — see the tie guard and per-form
  ceilings below.
- `count_negbin` — the discrete-count class the PM ruling names (NEW, this story): champion-head
  LGBM mean (`EM.fit_head_mean`, verbatim construction) + per-position NB2 dispersion
  (Var = μ + α·μ²) fit by bounded MLE **on the purged calibration slice** (the NF-MARGIN1
  lesson applied to a variance parameter), predictive = the NB2 quantile function on the dense
  grid. α at the floor ⇒ the Poisson special case (nested, declared, visible in the recorded α).
  Prices the atom parametrically: P(0) = NB2(0; μᵢ, α) moves row-by-row with the mean signal.

**Foil (never shippable; sets the bar):** `inc_climatology` — the per-position empirical
discrete climatology, the BINDING W6b incumbent on this cell (0.14964; it beat the
champion-faithful head-bank by 27% here). Atom-aware by construction.

⛔ **Excluded classes, on the record** (`BANNED_ARM_CLASSES`, guard-pinned): `enet_residual`
(the field-inflating defect itself) and `inc_head_bank` (the same non-atom-aware
residual-bank class in the incumbent costume; its W6b score on this cell, 0.18987, is already
on the record — nothing is lost by not re-scoring it).

**`DECLARED_FIELD_SIZE` = 3** (the real arms). This is the smallest field pre-registered for
this mechanism and is passed to `cv_power.classify_null(declared_field_size=…)`; the record
reads the machine flag `field_remedy_admissible`, never the prose (MH2.7; guide §0.5.4 rules
5/5b). The NF-W3 (c) hand-derivation exception is RETIRED for this story: the n_arms=1
mis-render is fixed (MH2.7, PR #791) and this is a 3-arm field.

**Diagnostic anchors — scored every run, never trials (MH2.1 (a)):**

- `nihilist_zero` (all-zero; must LOSE — the CRPS-soundness proof on an 86%-atom cell, NF-D11).
- `zero_width` + `max_width` — the two-sided sharpness degenerates, derived from the foil bank
  (the field's only foil). ⚠️ Declared numerical coincidence: on this cell the climatology's
  median is 0, so `zero_width` coincides with the nihilist — a property of the atom, recorded,
  not a defect; both must still lose.
- `permuted_knn` — the kNN form's full code path on labels permuted within (position, global
  week), seeded from THIS story's seed. Must lose; its lift vs the foil must not be
  significant (unevaluable p failing closed).
- **Per-form peeking oracles floored at matched-n (NF-D16 (g‴)/NF1.9 (f)) — one
  ceiling-plus-control pair PER candidate form, not one for the field**, because `knn_quantile`
  (and in the mixture limit the hurdle) NESTS the marginal: a single marginal ceiling would
  falsely veto a legitimately-better nested form. Pairs: (`oracle_marginal`,
  `matched_marginal`) — the foil's own form, the W6b machinery imported; (`oracle_knn`,
  `matched_knn`); (`oracle_hurdle`, `matched_hurdle`); (`oracle_negbin`, `matched_negbin`).
  Oracles cross-fit within the test block (no row sees its own label; K=3); matched-n controls
  fit on the block-sized recent train window with WINDOW-IN-SAMPLE calibration (the
  `EM.matched_cand_quantile` declared bias: optimism favors matched_n, making
  `oracle_beats_matched` HARDER — conservative; the purged split cannot run on a block-sized
  window and would refuse). The **winner's own-form pair gates** (`winner_own_form_floor`:
  the winner's form's peek must beat that form's matched-n control — the instrument-soundness
  clause); the other pairs are REPORTED, and a candidate beating a DIFFERENT form's oracle is
  legitimate cross-form capacity (the NF-W1 stance), never a veto.

## 2. Metric, folds, coverage, tie guard

- **Primary: `crps_q199`** (dense grid, imported). ⛔ Never MAE — an 86%-zero target has its
  conditional median at the floor, exactly where MAE pays for pessimism (NF-D11/D14; AST guard).
  One reducer for every construction; refuses non-finite predictives (NF-W3 (b)).
- **Folds:** the 8 NF-W1 expanding half-season blocks (2022H1…2025H2), purge 2 — the axis
  verbatim. Era split (capture vs legacy) REPORT-ONLY; forward sizing quotes the capture era.
- **Coverage(80) is a one-sided FLOOR, never a target** (E2.1-r/NF1.8/NF1.9 (e)): with an ~86%
  atom an honest predictive has q10 = q90-straddling atom mass and structurally covers ≈
  atom + 0.9·(1−atom) ≈ 0.986 ≫ 0.80 — a two-sided coverage target would be inverted (hitting
  0.80 requires deliberately under-covering the right tail). Blocking only beyond 3 binomial SE
  below 0.80. The two-sidedness lives in the sharpness degenerates (both must lose CRPS;
  `max_width` satisfies any floor and must still lose — the NF1.8 floor-is-a-constraint proof).
- **`tie_with_foil` guard (Batter-Props Ph2), gated:** `not_a_foil_tie` requires the winner's
  mean lift > `TIE_EPS_CRPS = 1e-4` — ~200× below the W6b real effect (0.0194), ~100× above a
  float-precision collapse. A nested form collapsing onto the foil scores a numerical near-tie
  that must classify as a TIE, never a win. (Verdict words are three-way and derived, failing
  closed to TIES — NF-W2e.)

## 3. Deflation + multiplicity (full §0.5)

- **PBO < 0.20** over the ELIGIBLE field = 3 arms + 1 foil (the search the selection actually
  runs — NF1.8), via the NF18 CSCV `deflate` (flip distribution, os-gap, contender spread
  reported beside it).
- **DSR ≥ 0.95** — deltas = winner vs foil per fold; trial-Sharpe field = the 3 declared arms'
  per-fold lifts vs the foil (anchors excluded — MH2.1 (a)). Same instrument as W6b
  (`M14.deflated_sharpe`) so the W6b→W6b-C comparison is like-for-like; the field's sr0 is
  reported beside W6b's (≈7.32) to make the mechanism legible. **DSR-CONV is NOT adopted**: no
  degenerate sits in this trial field at all, so there is nothing to exclude from V —
  `degenerates_excluded_from_v=True` is passed to the classifier as the provenance statement
  of that structural fact (declared forward, before any scoring; nothing here is a
  post-result exclusion).
- **Fold clause:** `cv_power.fold_consistency_clause(8)` (calibrated — MH2 H8; 6 of 8).
- **BH-FDR q=0.10 over a ONE-member family** — this cell is the whole family (m=1 ⇒ the BH
  cutoff is q itself; `fdr_single_cell`). Declared: there is no second member to pool with,
  and borrowing W6b's two-family structure would re-open the retired field.

## 4. The decision rule (fails closed)

`SHIP` iff ALL of: `beats_foil` ∧ `fold_consistency` ∧ `pbo_ok` ∧ `dsr_ok` ∧ `fdr_ok` ∧
`coverage_floor_ok` ∧ `degenerates_lose` ∧ `permutation_behaves` ∧ `not_a_foil_tie` ∧
`winner_own_form_floor`. Else a RECORDED null:

- every statistical gate green, the null resting only on constraint/anchor clauses →
  **CONSTRAINT_REFUSED** (hand — cv_power has no such state; ⛔ no sample-size trigger, the
  NF-D18 rule);
- any statistical gate failing → **`cv_power.classify_null`** with `n_folds=8, n_arms=3,
  declared_field_size=3, degenerates_excluded_from_v=True, bh_cutoff=0.10` and the empirical
  delta skew/kurtosis; the record carries the returned state (GENUINE_ABSENCE /
  DSR_UNREACHABLE / POWER_LIMITED / …), its reason, its trigger, and the machine flag
  **`field_remedy_admissible`** — a below-declared field prescription is arithmetic, never
  advice. A clean null is a fully acceptable outcome: the W6b ceiling on this cell is ~4.08%
  of foil CRPS ≈ 0.12 pts/wk in points units.

**If it clears:** the winner becomes a follow-on candidate for NF-W6c's dispatch-only serving
wiring under NF-G0 governance. **Today it stays guard-pinned OUT of serving** —
`stat_distribution_serving.WITHHELD_NULL_CELLS` keeps RB|rushing_tds withheld regardless of
this verdict, and a guard test asserts exactly that.

## 5. Instrument validation + guards

- The smoke (2 folds) HARD-asserts all three degenerates lose (the two-sided movability
  control — MH2.1 (d)) before the full run is trusted.
- Guards: one ISOLATING fixture per gate clause (NF-D17) + RED-proof per clause with the
  mutation ASSERTED TO LAND (E11.24 #682); any RED proof wrapping a `pytest.raises` clause
  catches `BaseException` (the NF-W6c pytest-`Failed` lesson); iterating checks assert
  non-vacuity (DSR-CONV #690); MAE banned by AST; the banned arm classes pinned OUT by
  call-site scan on comment-stripped source; anchors pinned out of the PBO/DSR fields;
  deploy-held token scan; the serving pin asserted.

### 5a. Smoke amendment (2026-08-15, recorded BEFORE the full run)

The 2-fold smoke passed its positive control (all three degenerates lose; runtime 203.8s;
kNN +11.5% vs the foil on 2 folds; trial Sharpes [4.1, 8.5, 2.1] ⇒ **sr0 2.79** against
W6b's ≈7.32 — the mechanism is visible before the full run). One INSTRUMENT defect surfaced
and is corrected here, on the smoke's evidence, not on any full-run result: the first cut sized
the per-form matched-n controls with the W6b `GE.matched_n_train` (a FULL block-size window),
while the cross-fit peek trains on only (K−1)/K = ⅔ of the block — so the "matched" control
had ~1.5× the rows of the oracle it was supposed to match (same-family but NOT same-sample,
NF1.7 (b): a peeking kNN's capacity depends on n), and the kNN/hurdle pairs read as near-ties
(0.14419 vs 0.14335; 0.16763 vs 0.16740). ⇒ `matched_window` now sizes every per-form
control to the oracle's effective fit size (`len(test)·(K−1)/K`); the marginal pair keeps
the W6b sizing (climatology is n-insensitive; comparability with the W6b record). The
`winner_own_form_floor` clause is UNCHANGED as a gate — if the winner's own pair still fails
on 8 folds, the record says so as CONSTRAINT_REFUSED. (Smoke artifact:
`nf_w6b_c_rb_rush_tds_smoke.{json,md}`; the smoke was re-run after the amendment.)

## 6. Runtime gate — N/A, stated

🟥 The runtime gate does not apply: **no serving path is touched** — no `--publish`, no
`deploy.sh`, no Dagster op, no S3/registry/dbt write. The outputs are local
`ablation_results/` artifacts read by governance only. CI (fast+slow shards on the PR) is the
whole mechanical gate for this story.

_Seed 20260816 (fresh) · folds/purge/features/PBO/DSR/FDR constants imported from
`weekly_projection` (never re-typed) · matrix = the NF-W6 certified build
(`nf_w6_stat_matrix_*`, PIT-gated on every load) · runner:
`run_nf_w6b_c_rb_rush_tds.py` · artifacts: `nf_w6b_c_rb_rush_tds.{json,md}`._
