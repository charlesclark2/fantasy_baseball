# NF-W6 — Pre-registration: per-stat distributional targets, THE ORACLE DECISION GATE

**Committed BEFORE the full run** (the §0.5 discipline). Every constant named here lives in
`efficiency_marginals.py` and the runner READS it (NF-D16). `best_alpha` N/A · **deploy-held** ·
research-only, no changelog entry.

## 0. Framing (two corrections baked into the story card)

- **NOT a simulator component.** NF-W8's §9 allocation-correlation premise is measured-dead
  (NF-W5: ceiling ≤ 0.5%, non-demonstrable). Nothing here feeds a simulator decision.
- **NOT a marginal point-forecast improvement in the W3/W4/W5 sense.** Those channels all
  nulled — the champion absorbs environment, availability and correlation. NF-W6 asks the
  narrower question: can the champion's **per-stat distributional targets** — receiving /
  rushing / passing **yards + TDs** — be improved **as marginals**?
- ⭐ **ORACLE FIRST — the decision gate, not a warm-up.** Given three consecutive component
  nulls, the story does NOT open with a bake-off. It measures the per-cell improvement CEILING
  via realized-efficiency oracles and **builds nothing unless the ceiling is demonstrably
  large**. A small ceiling → record the null and STOP: "the champion's per-stat marginals are
  already near the ceiling" is a complete, valuable result (the likely outcome, and a legitimate
  one).

## 1. The incumbent — what "the champion's per-stat predictive" is, stated plainly

The NF-W1 champion emits raw stat-line components as **point means only**
(`WP.fit_component_head`: pooled LGBM regression over the champion feature set, position code,
predictions clipped at 0 — "advisory raw lines beside the gated points distribution"). **No
per-stat distribution is served today.** The incumbent distributional forms are therefore the two
minimal champion-faithful constructions, built ONLY from champion machinery:

- `inc_head_bank` — the champion component-head mean (full-train fit, byte-identical learner
  construction to `fit_component_head`) + a per-position empirical residual bank on the dense
  grid, with the bank fit on a **purged calibration slice** (`MC.calibration_split`) — in-sample
  residuals of a boosted model are optimistically sharp (NF-MARGIN1), and an artificially sharp
  incumbent would inflate the ceiling toward BUILD.
- `inc_climatology` — per-position train empirical marginal of the stat. For the zero-heavy TD
  targets this is the honest discrete null and may legitimately be the better incumbent.

The ceiling is measured against the **BINDING incumbent** (better mean fold CRPS of the two):
you would not build a bake-off to beat the worse of two trivial forms. Bias directions declared:
the incumbent-side min LOWERS the ceiling (favors NO); the oracle-side max RAISES it (favors
YES). Net: the NF-W5 rule — **the estimator's bias favors a BUILD, so a NO is conservative.**

## 2. The cells

| position | stats |
|---|---|
| QB | passing_yards, passing_tds, rushing_yards, rushing_tds |
| RB | rushing_yards, rushing_tds, receiving_yards, receiving_tds |
| WR | receiving_yards, receiving_tds |
| TE | receiving_yards, receiving_tds |

12 cells. Scope declared: QB rushing is a real fantasy channel and is in; WR/TE rushing and
non-QB passing are excluded as minor channels. Scoring population = the NF-W1 modeled population
(ex-bye, retained zeros — availability risk is priced in the marginal, exactly as the points
champion prices it).

**Labels.** Yards labels ride the NF-W1 certified matrix (the same `stats_player_week` feed as
the points label). TD labels are attached at (season, week, gsis_id) with the frame's
retained-zero convention — a LABEL-side fill on rows the certified frame already carries,
identical to the existing yards/receptions attach; ⛔ NOT a `fillna(0)` on a NULL-bearing FEATURE
(NF-W0b constraint (9) is about features; no new features exist in this story). The attach
REFUSES duplicate feed keys (grain guard) and REFUSES on a TD-conservation mismatch (the NF-W3
row-conservation rule). No pbp source is read → the NF-W3 franchise-code/era traps are honored
by absence.

## 3. The oracles — "peek realized yards/TD per position", made precise

A ROW-level peek is a zero-CRPS degenerate, not a ceiling. Each oracle peeks the **BLOCK**: the
declared form re-fit on the test block itself (NF-W1 `anchor_oracle_marginal` semantics, per
stat), with conditional forms **cross-fit within the block (K = 3)** so no row's own label
reaches its own prediction. The peek is the block's realized efficiency REGIME — its conditional
structure and its residual distribution — not the answers row by row.

Three declared forms (NF-D16 (g‴): per-form ceilings), each with a **matched-n control**
(NF1.9 (f): the same form fit honestly on the block-sized most-recent train window; a peek is
INFORMATIVE only if it beats its own form at matched n — reported per form):

1. `oracle__inc_climatology` — the block's per-position empirical marginal (the story card's
   phrase, literally).
2. `oracle__inc_head_bank` — cross-fit head mean on the block + the block's residual bank.
3. `oracle__cand_lgbm_quantile` — the form a bake-off arm would take: cross-fit 9-knot pooled
   LGBM quantile bank + ⭐ the **NF-MARGIN1 exponential mean-excess tail** beyond the knots
   (inherited from day one; a knot form with flat extension has no tails). ⭐ Required because
   the two incumbent-form oracles carry position-CONSTANT banks — structurally blind to
   conditional heteroscedasticity (a 12-target week is wider than a 2-target week), which is
   precisely where per-stat headroom would live; without this form the gate could return a
   FALSE NO.

Matched-n controls use window-in-sample banks/tails — any optimism there favors matched_n, i.e.
makes `oracle_beats_matched_n` HARDER to claim (conservative; declared).

## 4. Metric + anchors

- **Primary: `crps_q199`** (the NF-MARGIN1 dense grid, imported from `margin_calibration`).
  The native 39-level grid is structurally blind to beyond-grid tail work; a build's arms would
  carry tail models, so the ORACLE stage must already score on the grid that can see them.
- **TD cells are zero-heavy → CRPS, never MAE** (NF-D11/D14: MAE inverts at the conditional
  median). MAE is not computed anywhere in this story.
- **Degenerate anchors, scored every cell, never reasoned about** (NF-D14): `nihilist_zero`
  (all-zero — its LOSING on a TD cell is the metric-soundness proof), `zero_width` (point mass
  at the conditional incumbent's median), `max_width` (×3 spread — satisfies any coverage floor
  and must still lose CRPS; NF1.8's floor-is-a-constraint proof). Coverage(80) of the binding
  incumbent + its zero-atom calibration (pred P(0) vs realized) are REPORTED diagnostics — no
  coverage target exists anywhere (E2.1-r).
- The one reducer REFUSES non-finite predictives (NF-W3 (b): an arm silently scored on a smaller
  population is not in the same contest) and non-finite labels.

## 5. The decision rule (pre-registered; fails closed)

Per cell: `ceiling_pct` = 100 · (binding incumbent − best per-form oracle CRPS) / binding
incumbent CRPS, paired over the **8 NF-W1 folds** (2022H1…2025H2, expanding window,
purge = 2 weeks — the axis verbatim).

- `stat_ok` = CI95 excludes zero (lo > 0) ∧ `cv_power.fold_consistency_clause(8)` ∧ **BH
  binding** at q = 0.10 over TWO pre-registered families — the 6 yards cells and the 6 TD
  cells — own-family AND pooled computed, a YES must survive BOTH (MH2 (a)).
- Bands on `ceiling_pct` (the NF-W5 precedent bands, calibrated against this vertical's own
  history — NF-W3's 2–3% recorded as "cannot justify the chain"; the shipped NF-MARGIN wins
  live well below 2%): **< 2% → NO · 2–5% → MARGINAL (PM decision; nothing built in-session) ·
  ≥ 5% → YES** (a §0.5 bake-off on that cell's family is licensed). Not `stat_ok` → NO
  regardless of magnitude. Unevaluable pct/CI → NO (fails closed).
- **Story verdict: BUILD iff any cell is YES; else RECORDED NULL** with MARGINAL cells named.
- **PBO: UNDEFINED** at this stage — the ceiling is a pre-registered anchor contrast, not a
  searched field (the NF-W5 ceiling rule verbatim). **DSR: does not arise** (no arm is
  selected). **`cv_power.classify_null` is NOT invoked** — the n_arms=1 fold-shortage
  mis-render is a known instrument bug (NF-W3 (c), 4× hand-corrected in this vertical); the
  decision object here is bands, not a null state.
- Era split (capture folds 2025H1/2025H2 vs legacy) REPORT-ONLY (NF-W2d/W2e); forward-looking
  sizing quotes the capture era.

## 6. Instrument validation (before the full run is trusted)

- **Positive control (MH2.1 (d), NF-W7b smoke-movability):** in `--smoke`, the block's realized
  QB passing yards are scaled ×1.3 and the climatology ceiling re-measured — the instrument MUST
  see the shift (hard assert; a blind instrument refuses the smoke).
- The guards RED-prove: the CI clause and bands are load-bearing (in-process mutations asserted
  to LAND — E11.24 #682); the reducer's finite refusal; the attach's grain + conservation
  refusals; tail monotonicity + the beta-0 flat (as-served) behavior; one isolating fixture per
  `stat_ok` clause (NF-D17).

## 7. If the gate says BUILD (not run in this story's session)

The licensed successor is a per-cell-family §0.5 bake-off: ≥3 learner classes (lgbm_quantile +
tail, per-stat hurdle + tail, enet_residual, knn) + a direct-learned foil, on these folds, on
`crps_q199`, coverage as a two-sided FLOOR, deflation (PBO < 0.2 / DSR ≥ 0.95 / BH), under a
FRESH registration. ⛔ Nothing from this stage's oracle field may be promoted into that field
post-hoc (MH2.2: you may pre-register a family, you may not discover one).

## 8. What this story cannot ship

Deploy-held: promotes nothing, publishes nothing, retrains nothing, writes no registry/S3/
serving surface (guard-scanned). The only outputs are `ablation_results/` artifacts and the
catalog record.
