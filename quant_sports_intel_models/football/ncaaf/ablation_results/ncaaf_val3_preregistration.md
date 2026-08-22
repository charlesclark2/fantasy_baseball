# NCAAF-VAL3 — pre-registration (written BEFORE any arm was scored)

**Story.** An in-fold-selected **cold-start μ_total correction, weeks 1–3 only**. Model / §0.5 /
market-blind / `best_alpha = 0`. Query + eval only: **no serving write, no registry edit, no refit
of a served artifact, no bet.**

Handed down by **NCAAF-VAL2** (`HAND_TO_VAL3_SCOPED`, target cell `wk1-3`) and unblocked by
**NCAAF-CLV-repair**. Everything in §1–§7 below was fixed before a single arm was scored; §0 was
executed first and its numbers are inputs, not results.

---

## 0. Data prep, executed first (the card's step 0)

The CLV-repair PM decision (§6a-2) left the repair's levels on the 2026-07-22 vintage and made
"re-quote on current data" VAL3's first step. Done, in this order:

1. `cp` the only working cache to `/tmp` **before** anything (a failing odds join still WRITES the
   cache with `has_close = False` on every row). ⭐ This worktree's `_PROJECT_ROOT` is the worktree,
   so `--assemble` writes a worktree-local cache and cannot reach the main checkout's copy at all —
   the backup is belt-and-braces, not the only guard.
2. `--assemble --matrix-source s3` → **2026-08-22**, 8,325 completed games, **4,187 closes** (the
   odds join was smoke-tested on its own first, 5,062 closes 2020+, so a silent close-less write
   could not happen).
3. **S1-serve re-run BEFORE VAL1**, eval-only: `--stage finalize --contract strength_pace --form
   strength_posterior --calib-out …ncaaf_val3_s1_serve_reanchor.json`. ⚠️ `--form` is load-bearing —
   `stage_finalize` defaults to the P1.4 REFERENCE form (`gaussian`), not the served
   `strength_posterior`; omitting it re-anchors the pin onto the wrong model.
   ⭐ `--calib-out` means **no served artifact is written and S1-serve's own decided record is not
   rewritten** (NF-W7f: a decided story's record is not rewritten after its result).
4. **VAL1's §2a pin re-anchored from THAT output** (⛔ never from VAL1's own). The pin HALTed on the
   population legs exactly as its docstring predicts; the HALT was the instruction.
5. VAL1 + VAL2 re-run on the new vintage.

**Result of step 0 — the inputs this pre-registration is written against:**

| | 2026-07-22 (recorded) | **2026-08-22 (this study)** |
|---|---|---|
| closes | 4,182 | **4,187** |
| VAL2 verdict | `HAND_TO_VAL3_SCOPED`, `wk1-3` | **identical** |
| `wk1-3` μ−y (clustered) | +2.322 [+0.88, +3.76] | **+2.311 [+0.89, +3.74]**, 6/6 seasons |
| cold-start contrast Δ | +2.118 [+0.42, +3.81] | **+2.101 [+0.39, +3.81]**, t +3.16 |
| `wk4-6` μ−y | −0.626 | **−0.626** |
| pooled μ−y | +0.548 [−0.66, +1.76] | **+0.554 [−0.63, +1.73]** |
| by week (μ−y) wk1/2/3 | +4.83 / +2.88 / +0.28 | **+4.77 / +2.88 / +0.28** |
| VAL1 `wk1-3` model→over / over hit | — | **0.608 / 0.463** |
| VAL1 verdict | `ALL_BUCKETS_NULL` | **identical** (0 of 6 cells clear) |

The lead VAL3 consumes is therefore unchanged and current: **the served μ_total runs ≈ +2.5 pts hot
in the cold-start weeks, decaying to ~0 by week 3.**

---

## 1. The three constraints inherited from VAL2 §9, and how each is honoured mechanically

1. **Size off `μ − y`, never off the offset.** In `wk1-3` the offset is only ~54 % of our own error
   (the two halves of the identity partially cancel). ⇒ the estimator reads **`mu_total − y_total`
   and nothing else**; a guard asserts the estimator's code path never touches `close_total` /
   `close_home_spread` / `has_close`.
2. **Select the magnitude IN-FOLD.** ⛔ No constant is inherited from VAL2 (that would be the
   NF-D18/NF-D20 inadmissible-λ shape: a magnitude fitted with the answer in view). Every arm's
   magnitude comes from a **nested walk-forward inside the outer fold's own training seasons**.
3. **A level move is not free on a right-skewed target.** Aggregate PIT and the calib floor are
   REFUSAL CONSTRAINTS, not diagnostics (§5 C1–C3).

And VAL2's two ⛔s:

- ⛔ **Not a pooled level correction.** `wk4-6` is *negative*, the pooled CI spans zero and the level
  drifts −0.02 → +2.11 by season. The pooled correction is registered as a **matched foil that must
  LOSE** (§4 `pooled_level`), not excluded by assertion.
- ⛔ **Must not touch the mean-vs-median component.** ~41 % of the *offset* is the market's number
  behaving like a conditional MEDIAN against a right-skewed total (P2.5: fitted skew-normal
  α ≈ +2.12). Sizing off `μ − y` removes that half **by construction** — `y` is the realised total,
  so the correction moves μ toward the realised conditional MEAN and can never chase a median line.
  This is asserted, not argued: constraint C4.

---

## 2. Population, folds and the frozen model

- Cache: the **2026-08-22** assembly (8,325 games, 4,187 closes).
- Config: the **SERVED** one — `ridge` / `strength_pace` / `strength_posterior`, taken from
  `ncaaf_val1_clv_week_strat.PRIMARY`, never restated.
- Folds: `bakeoff_ncaaf_game.build_folds` verbatim — **8 purged season-forward folds, eval 2018–2025**.
- Scored population: the **full OOS frame, 6,024 games** — *not* the close-carrying subset. The
  target `μ − y` needs no market number at all, so restricting to close-carrying rows would discard
  2 seasons and 1,837 games for nothing. This is what makes the study market-blind by construction
  rather than by promise.
- `wk1-3` eval rows per fold (a DESIGN quantity, counted before any scoring):
  143 / 139 / **34 (2020, the COVID staggered start)** / 147 / 150 / 153 / 140 / 145 = **1,051**.
- ⛔ `season_order_week`, never raw `week` (the P1.1 postseason restart).

**FROZEN-σ invariant.** Every arm moves **μ_total only**. The per-game σ (the `strength_posterior`
propagation, σ0/k fitted per fold on the inner holdout) and **μ_margin** are byte-identical across
arms. This is a REFUSAL condition (C6/C7), not a diagnostic — an arm that moved σ would be a
dispersion story wearing a mean costume (the P2.5 frozen-mean invariant, mirrored).

**The in-fold estimator.** For an outer fold with eval season `Y`, an inner purged walk-forward is
run over the rows with `season < Y`, `min_train_seasons = 2`, giving honest in-train OOS
predictions. Every arm's magnitude is a statistic of **those** rows' `mu_total − y_total`.
`min_train_seasons = 2` is a **design quantity, fixed from the fold structure and not from any
result**: at 3, fold 2018 has ZERO inner folds and the estimator is UNDEFINED there — and an
unevaluable fold is never a pass (NF1.7 (a)). At 2 every outer fold has ≥1 inner fold; the in-fold
`wk1-3` sample runs 141 (fold 2018) → 1,047 (fold 2025).

---

## 3. The metric, and why it is a SUBSET metric

**Primary (selection): closed-form Gaussian CRPS of the total, on the `wk1-3` cell, per fold.**

- The served predictive **is** a heteroscedastic Gaussian, so CRPS has an exact closed form
  (`σ·[z(2Φ(z)−1) + 2φ(z) − 1/√π]`). Using it instead of a draw ensemble makes every figure
  **deterministic to 1e-12** and removes the Monte-Carlo-variance question NF-W7k had to spend a
  whole story closing. A sampled-CRPS cross-check is scored anyway, as an instrument control.
- **Subset, registered forward.** The mechanism can only move 17.4 % of rows, so a pooled metric
  dilutes it toward zero by construction (NCAAF-P2.1 (f); E1.13's bounded-by-exposure null). The
  pooled figure is *reported* — as the honest statement of what the correction is worth to the
  whole book — but the *contest* is on the cell.
- CRPS is proper, σ is frozen and only μ moves, so a "predict nothing" pessimism arm cannot win it
  (NF-D11). The two-sided anchors of §4 are scored regardless.

**Reported, never selected on:** pooled CRPS; `wk4+` CRPS (an inertness control — it must not move);
margin CRPS (must be byte-identical); the `wk1-3` model→over share and over-hit rate on the
close-carrying rows (the AC's headline, and the only market-touching number in the study).

---

## 4. The field — ⛔ CLOSED at pre-registration

Let `d̂_bucket(f)`, `d̂_week(f,w)`, `d̂_pooled(f)` be in-fold means of `mu_total − y_total` over the
fold's inner-OOS rows (all weeks ≤3 / week `w` / every week).

**Foil (the do-nothing degenerate + the incumbent, one and the same):**

| arm | δ | registered as |
|---|---|---|
| `none` | 0 | the FOIL. The served model, untouched. Everything is measured against it. |

**Selectable candidates (4):**

| arm | δ on a `wk1-3` row | params |
|---|---|---|
| `bucket_shift` | `d̂_bucket(f)` | 1 |
| `per_week_shift` | `d̂_week(f, w)` | 3 |
| `linear_decay` | in-fold OLS `a + b·w` on the fold's inner `wk1-3` rows | 2 |
| `shrunk_bucket` | positive-part James–Stein shrink of `d̂_bucket` toward 0 by its own in-fold SE | 1 |

**Registered-to-LOSE arms — SCORED, counted in `n_trials`, INELIGIBLE to ship (NF-D20: an anchor
that is reasoned about instead of scored teaches nothing):**

| arm | δ | what its winning would mean |
|---|---|---|
| `pooled_level` | `d̂_pooled(f)` on **every** row | the effect is a season-wide LEVEL, not a cold start — VAL2's ⛔ would be wrong |
| `week_blind` | `d̂_pooled(f)` on `wk1-3` rows only | the SCOPING carries the effect but the MAGNITUDE carries no week information |
| `over_scale` | `2 · d̂_bucket(f)` | the estimator systematically UNDER-corrects (NF-D20's `over_scale`) |

`pooled_level` and `week_blind` are the **matched foils** (NF-D10/NF-D15 g′): each keeps the entire
machinery and removes exactly one claimed channel — the week SCOPING and the week-informed
MAGNITUDE respectively. A win must be attributable to a channel, not merely observed.

**Diagnostic anchors — NOT trials, excluded from `n_trials` AND from `V` (MH2.1 (a): a diagnostic
anchor is never a trial; an anchor that sets the gate's own bar is the defect that rule exists to
prevent):**

| anchor | what it is |
|---|---|
| `oracle_bucket` | δ = the mean `mu_total − y_total` of the **eval fold's own** `wk1-3` rows (peeking). Same FORM as `bucket_shift`. |
| `matched_n_bucket` | `bucket_shift`'s estimator on a random in-fold slice **sized to the eval fold's own `wk1-3` n**. |

⭐ The oracle is a floor **only at matched family AND matched sample** (NF1.7 (b), NF1.9 (f),
NF-W6b-C). Its n is ~145; an honest arm's is up to 1,047, so an honest arm beating the peek is a
CAPACITY effect, not a metric inversion — which is exactly what `matched_n_bucket` is registered to
demonstrate. Per **NF-W6d**: an oracle that merely **TIES** its matched-n control is **INACTIVE, not
a refusal** — a per-form floor whose anchor pair could not act is uninformative (NF-D20), and it is
recorded as `INACTIVE`, never as a pass and never as a fail.

**`DECLARED_FIELD_SIZE = 8`** = the foil + 4 selectable + 3 registered-to-lose. Declared here,
forward, in this document. ⛔ No post-hoc trim (MH2.2): you get to pre-register a family, you do not
get to discover one.

**Not registered, and stated so it is visibly a choice:** a per-fold in-fold arm SELECTOR (pick the
best-scoring arm inside each fold) would need a third nesting level and 8 folds cannot support it.
It is out of scope, not overlooked.

---

## 5. Ship clauses (all must hold) and the deflation gates

| id | clause |
|---|---|
| **C1** | pooled (all-row) total PIT max-decile-dev ≤ the foil's **+ 0.0020** — the AC's "without degrading aggregate PIT" |
| **C2** | pooled total `calib_80` ≥ 0.78 (the P1.4 floor, `_CALIB_TARGET − _CALIB_FLOOR_TOL`) — a FLOOR, never a target (NF1.8) |
| **C3** | `wk1-3` total `calib_80` ≥ 0.78 |
| **C4** | **market-blind estimator** — the correction is computed from `mu_total − y_total` only; no market column is read on the estimator path (VAL2 §9's mean-vs-median ⛔) |
| **C5** | `wk4+` CRPS unchanged to 1e-9 (the correction is week-scoped by construction; asserted, not assumed) |
| **C6** | margin CRPS byte-identical to the foil's (μ_margin frozen) |
| **C7** | per-game σ byte-identical to the foil's (σ frozen) |
| **C8** | own-form peeking-oracle floor: the arm does not BEAT `oracle_bucket`. A **TIE ⇒ INACTIVE**, recorded as such |

**Deflation.** `pbo_cscv` over the per-(fold × slice) bucket matrix of the foil + the 7 arms
(gate < 0.20); `deflated_sharpe` on each arm's per-fold improvement series vs the foil with
`n_trials = 8` and `var_trials_sr` measured over the **7 non-foil, non-diagnostic** arms (gate
≥ 0.95); Benjamini–Hochberg at α = 0.05 over the arms' one-sided paired p-values;
`cv_power.fold_consistency_clause(n_folds = 8)`.

⭐ **Which `V` binds is declared here, forward.** The **full-field** `V` (all 7 arms) **BINDS**. The
DSR-CONV variant (`V` over the 4 selectable arms only, i.e. excluding the three designed losers) is
computed and reported as a labelled diagnostic. Declaring the *generous* reading as non-binding is
the conservative direction, and it forecloses the NF-W7h failure in which a re-read of `V` after a
failed gate deletes the arm under test.

**Null classification.** `cv_power.classify_null(declared_field_size = 8, degenerates_excluded_from_v
= False)`, with the machine flag `field_remedy_admissible` read rather than the prose (MH2.7). If the
refusal is caused by a ship CLAUSE rather than by the statistic, the recorded state is
**`CONSTRAINT_REFUSED`** and ⛔ **no fold/season re-test trigger is published** — no fold count moves
a clause (NF-D18). The instrument's own state is preserved beside it, never replaced.

---

## 6. Reproduction pin (§6a) — vintage-bound on purpose

Pinned from the **PARENT** (`ncaaf_val3_s1_serve_reanchor.json`) and from the cache meta, ⛔ never
from VAL3's own output: cache `assembled_at` = 2026-08-22, `n_with_close` = 4,187,
`n_oos_games` = 6,024, fold years 2018–2025. A re-assemble moves the population and this pin HALTs,
correctly; the remedy is to re-run the parent and re-anchor from ITS output.

## 7. Acceptance

A §0.5-cleared cold-start μ correction that reduces the `wk1-3` over-tilt **without degrading
aggregate PIT** — or a documented null with `classify_null`. Market-blind; `best_alpha = 0`; no
serving change either way. **⛔ Whatever the arms do, no clause, threshold, metric, field or `V`
choice above may be revisited after seeing a score (E2.1-r).**
