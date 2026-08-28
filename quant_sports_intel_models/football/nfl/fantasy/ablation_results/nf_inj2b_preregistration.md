# NF-INJ2b — PRE-REGISTRATION: re-fit the ordering learner on a per-game RATE target

**Committed BEFORE any arm is scored.** Spec `plan_specs/nfl_fantasy/nf-inj2b.yaml` (PM-authored
2026-08-25). ⛔ This document is not edited by the decisive run. Anything the run overturns is left
here VERBATIM under a `SUPERSEDED` marker in the REPORT, never rewritten here (E2.1-r / NF-W7f).

`best_alpha = 0`. Nothing in this story serves without the gated ship path **and** an operator
disposition; `nf_inj2b_rate_ordering.SERVED_ARM` stays `"incumbent"` and `assert_coherent()` refuses
a flag flip the record does not support (NF-D21 / NF-D22 governance shape).

---

## 0. Baseline — the CURRENT served vintage, verified before anything was designed

The spec makes the flip board the baseline and binds the SHIP lesson: **verify input freshness from
inside the artifact before any board-vintage measurement.** Read from the live prod api-cache
(`s3://credence-prod-s3-api-cache/fantasy/nfl/2026/`) at the start of this session:

| read | value | reading |
|---|---|---|
| `manifest.injuryGamesStamp.verdict` | `FLIPPED_AND_MOVED` (`passed=true`) | the NF-INJ3b fitted RES/PUP caps ARE live |
| `injuryGamesStamp` counts | `n_certified=25, n_fitted=25, n_moved=25`, max move 4.00 games | nothing reverted |
| `manifest.coherence.injury_input` | `OK`, lag **0.8h** against a 72h bar | the feed is fresh — no stale-feed poisoning |
| `projections.json` — Alec Pierce | **g = 3.7** | the operator's §5 morning check reads CLEAN |
| `projections.json` — "AJ Dillon" present | yes (the 32 all-caps names are D/ST, correct) | names repaired |
| `manifest.coherence.violating_players` | **11** | the NF-INJ1 give-back's live, user-visible expressions |
| `manifest.reportedAbsenceCount` | **0** | no NF-INJ-NEWS-1 override adopted — matches the stamped D10 state |
| board `generated_at` | 2026-08-27T14:18:54Z | republished twice since the flip, flip intact each time |

⇒ **The precondition holds: nothing was reversed on 2026-08-25, and the flip board is the baseline.**
The combined read's PASS is the one recorded in `plan_specs/nfl_fantasy/nf-inj3b-ship.yaml` node 5;
this session did not re-run it and does not claim to have.

---

## 1. The hypothesis, and the mechanism it rests on

NF-INJ2 (`ablation_results/nf_inj2_rate_permutation.md`, `CONSTRAINT_REFUSED`) established both
halves of the problem on the served board:

* `rate_permute` **works on what it targets** — veteran impossible rows 10 → 0 attributable, injury
  give-back +33.96% → −11.99%, CRPS +0.3126 over 7 folds (5/7), PBO 0.0286, and the matched foil
  attributes the win to the per-player availability channel from both directions.
* It **breaches the pre-registered ORDERING constraint at QB** — draftable-tier ρ 0.481 → 0.350,
  BH-significant — and its own §6b decomposition names why: NF1.5's ordering learner is fitted on
  `real_fp_ppr`, a season TOTAL, so it was selected to order POINTS. The damage ranks exactly with
  the games signal's per-position deficit (worst at QB, where expected games is the weakest ordering
  signal; TE, where it is relatively strongest, actually gains).

**H1 (this story).** The ordering score and the permuted multiset must be in the SAME unit. Re-fitting
the ordering learner on a per-game RATE target makes the score rank the quantity `rate_permute`
actually hands out, so coherence and ordering can hold together.

**The mechanism, stated so it can be refuted.** Under `rate_permute` the served point is
`rate_{σ(i)} × games_i`, where σ ranks by the learned score. A points-fitted score already prices
availability (through `mvp1_fp`, `expected_games`, `base_games`), so availability is priced TWICE —
once in deciding which rate a row receives, once in the multiply. A rate-fitted score is asked only
to rank rates, so availability enters exactly once, at the multiply. That predicts the repair is
largest where the games spread is widest, i.e. at QB.

---

## 1b. TWO STRUCTURAL MEASUREMENTS TAKEN BEFORE ANY SCORING — they bound what H1 can achieve

These are properties of the learner FORM, not scores of any arm against realized outcomes. They are
recorded here, in advance, so that if the primary arm underperforms the record already says why and
it cannot read as a post-hoc excuse (NF1.7 (a): measure whether the mechanism CAN act, do not
reason about it — NF-D20).

**(a) The re-fit is STRUCTURALLY INACTIVE at RB.** NF1.5's per-position selections are
`{QB: pos_learned_adaptive_blend, RB: pos_blend_flat, WR: pos_learned_blend, TE: pos_learned_blend}`.
`PosRefinedBlend` scores `(1−w)·z(anchor) + w·z(market_score)`, and the fit target `y` reaches the
score ONLY through the inner model, which exists only when `anchor == "learned"`. RB's
`pos_blend_flat` anchors on `mvp1_fp`, so **`y` never touches RB's score at all**. Measured on the
pooled training frame (fit points vs fit rate, 200 held rows per position):

| position | selected class | anchor | max &#124;Δscore&#124; | ρ(points-fit, rate-fit) | mechanism can act |
|---|---|---|---|---|---|
| QB | `pos_learned_adaptive_blend` | learned | 1.230e+00 | 0.9918 | **True** |
| RB | `pos_blend_flat` | mvp1 | **0.000e+00** | 1.000000 | **False — structurally inactive** |
| WR | `pos_learned_blend` | learned | 3.217e-01 | 0.9989 | **True** |
| TE | `pos_learned_blend` | learned | 3.690e-01 | 0.9959 | **True** |

⇒ At RB, `rate_refit` is **byte-identical** to `points_rate_permute` by construction. An RB result
under the primary is therefore UNINFORMATIVE about H1 and must never be counted as a pass (NF-D20:
count the cells the mechanism can act on, and report the active count beside the pass count). This
does **not** threaten the joint success criterion — RB was not the breached position (Δ tier-ρ
−0.0079, not significant) — but it must be reported, not discovered.

**(b) Even where ACTIVE, the re-fit moves the ordering only slightly** — ρ(points-fit, rate-fit)
≥ 0.9918 at every active position. The score is a z-blend whose market axis (`market_score`, an
ADP/ECR SEASON-TOTAL consensus) is **target-invariant**, and whose learned anchor keeps
availability-bearing features. So a target swap alone cannot make the score availability-neutral.
⇒ **We register in advance the expectation that `rate_refit` alone is unlikely to recover the full
0.13 tier-ρ at QB**, because the QB damage is produced by the `× games` multiply and not by the
score. If that is what the run shows, it is a CONFIRMED prediction, not a rescue — and it is exactly
why the field below also registers an arm that acts on the multiply.

---

## 2. Arms — DECLARED FORWARD; this IS the field for PBO/DSR

The family is declared on MECHANISM before anything is scored (MH2.2 — you get to pre-register a
family, you do not get to discover one). It is a **2×2 over the two factors the diagnosis names**,
plus the two NF-INJ2 members the spec carries by name, plus two degenerates.

* **F1 — the score's fit target:** `points` (season total, today) | `rate` (per-game).
* **F2 — the multiset and its assignment:** `point-by-score` (today's form) | `rate-by-score`
  (NF-INJ2's coherent form) | `rate-within-availability-strata` | `point-within-strata`.

| # | arm | F1 | F2 | role |
|---|---|---|---|---|
| 1 | `incumbent` | points | point-by-score | **reference** — today's served board; the ordering bar |
| 2 | `points_rate_permute` | points | rate-by-score | NF-INJ2's refused arm, carried by name — **the matched TARGET foil** |
| 3 | `rate_refit` | **rate** | rate-by-score | **PRIMARY** — the spec's rate-target re-fit |
| 4 | `points_rate_stratified` | points | rate-within-strata | the 2×2's fourth cell (NF-W7e: two halves are not additive) |
| 5 | `rate_refit_stratified` | **rate** | rate-within-strata | acts on the MULTIPLY: rates are exchanged only between rows of comparable games |
| 6 | `rate_refit_reselect` | **rate**, class chosen IN-FOLD | rate-by-score | the "re-select" half of the story's own title |
| 7 | `stratified` | points | point-within-strata | carried by name (NF-INJ2's named fallback: CRPS 7/7, give-back +6.88%, 7 impossible rows left) |
| 8 | `feasibility_clamp` | points | point-by-score, envelope-bounded rescale | carried by name (removes impossible rows at ~0 ordering cost, does NOTHING to the give-back) |
| 9 | `mvp1_null` | — | no re-order at all | pre-registered **DEGENERATE** — must LOSE |
| 10 | `random_order` | — | seeded within-position random | pre-registered **DEGENERATE** — must LOSE |

**`declared_field_size = 10`**, passed to `cv_power.classify_null(declared_field_size=10)`. Read
`field_remedy_admissible`, ⛔ never the prose (MH2.7). ⛔ **No post-hoc trim** (MH2.2).

### Matched pairs, declared now (NF-D15 g′ / NF-W7e)

| channel | pair | reads |
|---|---|---|
| **TARGET** | `rate_refit` − `points_rate_permute` | identical machinery, the fit target is the ONLY difference ⇒ isolates H1 |
| **ASSIGNMENT** | `rate_refit_stratified` − `rate_refit` | identical machinery, the stratification is the ONLY difference |
| **2×2 interaction** | (3−2) vs (5−4) | NF-W7e: two mechanism halves are NOT additive. Every parameter is re-fit WITHIN each cell; ⛔ no channel is recombined from separate conditional measurements |
| **point-space control** | `stratified` − `incumbent` | the same stratification in POINT space, so "stratification helps" cannot be confused with "rate space helps" |

### The in-fold re-selection, specified now so it cannot be tuned later

`rate_refit_reselect` chooses its class from `nf1_5_model.STAGE1_CANDIDATES` — the SAME four-variant
family NF1.5's own stage-1 searched, no expansion. Hyperparameters are NOT re-tuned (this is a
target re-fit, not a new Optuna search): each candidate takes the position's NF1.5-selected `hp`
restricted to the parameters that variant accepts. Selection is **strictly in-fold**: fit each
candidate on pool seasons ≤ `fold − 2`, rank by Spearman(score, realized per-game rate) on pool
season `fold − 1`, then re-fit the argmax on the full training pool. The evaluation fold is never
touched. Ties break by `STAGE1_CANDIDATES` order (deterministic).

---

## 3. Metric, gates and conventions — SAME BARS, NOT RELAXED

The ordering constraint is **the exact gate NF-INJ2 breached, at the same bar**. This story
supersedes the LEARNER; it does not relax the gate (E2.1-r).

* **Primary metric:** CRPS on realized season PPR (`level_recalibration.SELECTION_METRIC`),
  walk-forward over NF1.5's OWN stage-1 window — **folds 2019–2025, inherited from
  `score_from`, not chosen here**, so the window cannot have been tuned to this result.
* ⛔ **MAE never selects** (NF-D11 / NF-D14: the target is skewed and the low-availability cohort sits
  near the conditional median). Reported, never used.
* **Calibration (E2.1-r hygiene):** `coverage80` is a **FLOOR**, never a target to minimise distance
  to; the interval score is reported beside it. Degenerates are SCORED every run and their numbers
  READ, not reasoned about — and the `max_width`-style degenerate check applies: a CONSTRAINT a
  degenerate satisfies is fine, a CRITERION a degenerate wins is fatal (NF1.8).
* **ORDERING CONSTRAINT (binding):** draftable-tier Spearman ρ per position (`top_tier_rho`, anchored
  on the FIXED incumbent `mvp1_fp` tier so every arm grades on the identical subset). The binding
  reading is NF-INJ2's, verbatim: **no position shows a regression distinguishable from noise**,
  one-sided paired t on the per-fold (incumbent − arm) tier-ρ deltas, BH-corrected across the four
  positions at `q = 0.10`. The STRICT point-estimate reading and the full-population reading are both
  reported beside it (NF-D22: a strict point-floor at nominal is a coin flip at any n; and the two
  readings disagreed in NF-INJ2, so both must be shown).
  ⚠️ This BH protects against a false REFUSAL, i.e. it is directionally generous to the arm. Stated
  now, so the generosity is on the record rather than discovered by a reader.
* **COHERENCE:** violating players against `projection_coherence.REALIZED_MAX_PER_GAME` must be **0
  attributable**. Reported for EVERY arm including degenerates. `rate_*` arms satisfy it by
  construction ⇒ it is a **PRECONDITION, ⛔ never a discriminator** between arms.
* **Deflation gates:** PBO < 0.2 (CSCV, over the ELIGIBLE declared field), DSR ≥ 0.95, BH-FDR, and the
  fold-consistency clause via the calibrated `cv_power.fold_consistency_clause(n_folds=…)` — ⛔ never
  the raw 0.60 rate (MH2 H8).

### THE DEFLATION CONVENTIONS, NAMED UP FRONT (the NF-INJ3 lesson, binding here)

NF-INJ3's null rested on two specification details its pre-registration left open. They are fixed
**now**, before any score:

1. **`V`'s membership.** `var_trials_sr` is measured EXCLUDING the two pre-registered
   lose-by-construction degenerates (DSR-CONV) **AND** excluding `incumbent`, the REFERENCE arm,
   whose lift series is identically zero by construction — a structural 0.0 inflates a small family's
   `V` exactly as a diagnostic anchor does (MH2.1 (a)). `n_trials` stays at the FULL declared field of
   10, so multiplicity is not reduced. Both figures — reference-excluded and reference-included — are
   reported; **the reference-excluded one BINDS.** (NF-INJ2's harness left `incumbent` in `V`; that is
   a convention defect this registration fixes forward, not a re-read of NF-INJ2's number.)
2. **The BH family.** The mechanism is ONE hypothesis over ONE population and no per-position axis is
   registered for the SELECTION metric, so the CRPS leg is a **SINGLE hypothesis** — the per-position
   CRPS split is a DIAGNOSTIC, not a family. The ORDERING constraint keeps its own 4-position BH
   family (that axis IS registered: the constraint must hold at every position). Both are stated so a
   reader can check which multiplicity applies where.
3. **`pbo_application="field"`** is passed to `classify_null`. CSCV/PBO is ONE number about the
   SEARCH; it does not vary across arms, and reading it per-arm converts "the search was unstable"
   into "this arm failed" — a statement the statistic does not make (PLAT-CVP1 defect 4(a)).

### THE INJECTED-EFFECT POSITIVE CONTROL — APPLICABLE, and here is why

The spec requires this question answered in the prereg. **It applies, and it is required**, because
arms 2–6 all share the rate-multiset assignment and differ only in the score or the stratification —
they are **near-clones on the assignment axis**. That is precisely the shape MLB-HV2-1 measured: a
uniform planted effect makes near-clones simultaneously strong, which drives PBO UP (NF1.8 — a high
PBO over near-clones is a TIE, not overfitting) and collapses DSR by inflating cross-trial dispersion
(MH2.5 / NF-W6b-C). Without the control, a deflation-gate refusal here cannot be distinguished from
a gate family that would refuse a real, large effect.

Run via `cv_power.injected_effect_positive_control(inject=…, run_gates=…)` — with **this study's own
registered gate function**, not a re-implementation (the NF-C0e "a test that reads a value back under
the key the code wrote" class). The two-sided leg (`check_null_control=True`, `inject(0.0)` = the
real payload) runs. Readings recorded verbatim: `verdict`, `blocking_gates`, and
`field_level_gates_applied_per_arm`.

* `VACUOUS` ⇒ the family certifies noise; **no reading of this study means anything** and the run is
  reported as such.
* `DETECTED` ⇒ the family can certify an effect of this size over this field.
* `DEFLATION_BLOCKED` ⇒ the metric half fires and the deflation half cannot certify an effect of this
  size over THIS field. That BOUNDS what a survivor would have meant; ⛔ it does not by itself rescue
  or refuse anything.
* `BLIND` ⇒ a null from this family is free.

The injected effect is **+0.75 CRPS** per fold on every non-degenerate, non-reference arm — declared
now. It is ~2.4× the lift NF-INJ2 measured (0.3126), i.e. an effect nobody would call marginal, and it
is applied uniformly so the near-clone geometry is preserved.

> #### ⚠️ AMENDMENT 1 — 2026-08-27, filed BEFORE ANY SCORING (nothing had been run when this was written)
>
> **The injection also plants +0.05 draftable-tier ρ per fold, per position, on the same arms.**
>
> The clause above plants a SELECTING-METRIC effect only. Writing the control revealed that this
> would not answer the question the control is registered to ask. `injected_effect_positive_control`
> partitions the registered gates into DEFLATION-class and METRIC, and returns `BLIND` when not even
> the metric gates fire. This study's registered gate table contains the ORDERING CONSTRAINT, which
> is held at its REAL value by a CRPS-only injection — so on any run where the constraint legitimately
> fails, the control would return `BLIND`, whose documented meaning is *"a null from this family is
> free"*. That would be flatly wrong, and it would be a label attached to the study's headline.
>
> A planted TRUE POSITIVE for THIS study is an arm that is better on the selecting metric **and**
> does not regress the ordering constraint. The injection must therefore reach both, and +0.05 tier-ρ
> per fold per position is enough to make the one-sided paired regression test unambiguously
> non-significant in the "arm is worse" direction for a planted arm.
>
> ⛔ This changes NO bar, NO arm, NO gate and NO reading of the study. It changes only what the
> DIAGNOSTIC control plants, it is filed before a single arm was scored, and the original clause is
> left above VERBATIM (E2.1-r / NF-W7f: a pre-registration is not edited, it is amended on the
> record). The MLB-TV2-0 node-2 amendment is the precedent for the shape.
>
> One consequence, stated now so it is a prediction and not a post-hoc reading: because the
> registered per-arm gate table deliberately **excludes** `pbo` (a FIELD-level statistic must not be
> carried as a per-arm pass/fail — PLAT-CVP1 defect 4(a)), the control's
> `field_level_gates_applied_per_arm` is expected to come back **EMPTY**. That emptiness is the
> affirmative finding, not an absence of one. The field-level PBO's behaviour under injection is
> reported BESIDE the control as a labelled diagnostic, because it is the MLB-HV2-1 mechanism and
> would otherwise be invisible.

### Anchors

* Every degenerate scored every run and its number READ (NF-D14).
* **One peeking ceiling PER FORM** (NF-D16 g‴ — the forms nest, so a single field-wide ceiling would
  veto a legitimately better nested form), built same-form AND same-sample by ordering that form with
  the realized outcome (NF1.7 (b) / NF1.9 (f)).
* **NF-D20 activity is COUNTED, never assumed**: the per-position structural-activity table of §1b is
  recomputed by the run, and an INACTIVE cell is reported as uninformative, ⛔ never as a pass.

---

## 4. Level-adjacency — the gates a ship must clear (inherited from NF-INJ2 §4, unrelaxed)

Every `rate_*` arm changes the served point distribution (the per-position POINT multiset is no
longer preserved), so it is **level-adjacent** and must clear, before any publish:

1. **Whole-board cross-position placement read** against the PUBLISHED artifact, per config.
   ⚠️ The NF-W8-0 VOR "shield" is **ADDITIVE-only**; this correction re-levels by a RATIO, so the
   shield does not excuse the read — and it does not hold at all under the two **superflex** configs,
   where QB is cross-pooled, and QB is the position this family moves most (NF-TR2b).
2. **Interval revalidation** — the NF1.9 per-player band is priced off the point and must follow it.
   Per-group coverage floors use **`power_floor()`** derived from each group's n and the
   pre-registered false-reject target — ⛔ never a flat nominal point-floor (NF-D22).
3. **Rookie placement cap** (NF-D18 / NF-D20), read against the published artifact per config.
4. **Population-scoped material diff at 1e-9, ⛔ NEVER bitwise**; rookie-band motion read against a
   **≥5-draw same-commit control envelope** (card QkpAHBYa — one draw cannot establish that a column
   is deterministic).
5. **Reproduction pin:** the `incumbent` arm rebuilt through this story's code must match the SERVED
   2026 artifact to **1e-9**. If it does not, every arm delta is measured against a board nobody is
   served, and the run is void.

---

## 5. Explicitly OUT OF SCOPE (kept separable — NF-W7d)

* **The feature space.** The re-fit changes the TARGET only. NF1.5's stage-2 six-class null over
  season-level features is a recorded null and is not re-opened; no feature is added or removed.
* **Hyperparameter re-tuning.** `blend_w` / `disp_slope` keep NF1.5's selected values. A new Optuna
  search would be a different (and much larger) intervention with its own deflation cost.
* **A per-position family.** ⛔ **A QB-ONLY application is NOT admissible** — adopting one after
  seeing NF-INJ2's per-position damage is discovering a family after scoring. No per-position family
  is registered here, so none may be adopted from this run.
* **The injury cap constants** (NF-INJ3b, now live) and the **rookie `fp_target` ↔ slot-bucket-games
  decoupling** (NF-INJ3c) — different code paths, their own registrations.
* **The NF-INJ1-C suppression** — the symptom patch this story aims to make unnecessary. Its guards
  must stay green on any counterfactual board; nothing here changes it.

---

## 6. Pre-committed reading of the outcomes

Written now so no branch can be chosen after the numbers are visible.

1. **An arm wins or TIES on CRPS, holds the ordering constraint at every position, restores
   coherence, and its matched TARGET foil does not** → SHIP, subject to §4, deploy-held for the
   operator. A **TIE still ships**: coherence is a correctness constraint the INCUMBENT FAILS on 11
   live rows, and a tie on the selecting metric is not a reason to keep serving a physically
   impossible stat line. This is the pricing-vs-discrimination family rule, ⛔ NOT the E2.1-r
   inversion — and it is written down here, in advance, precisely so it cannot look like a rescue.
2. **The ordering constraint is breached at a named position by a margin distinguishable from noise**
   → `CONSTRAINT_REFUSED`. ⛔ **No "more seasons" trigger** — more folds make a real regression MORE
   significant, not less (NF-D18).
3. **No arm restores coherence** → the story's own premise failed; record it.
4. **The best arm loses CRPS on average** → `GENUINE_ABSENCE`; no n and no field size rescues a
   negative point estimate.
5. **A deflation gate is EVALUATED and FAILS while the metric and constraint gates pass** →
   `DEFLATION_REFUSED`, read against the positive control's verdict. Compute the DSR 2×2
   (series × field) as a **labelled diagnostic BEFORE naming any remedy** (NF-W7f), and check the
   **lockstep invariant**: a shared-variance lever (more rows / folds / draws) is DETERMINISTICALLY
   VOID for `dsr_ok` when `SR ≤ SR0` (NF-W8-0d), so ⛔ publish no season/fold trigger for it. ⛔ If the
   winner is `V`'s largest contributor, the field-trim reading is **INADMISSIBLE** (NF-W7h) — say so
   a fortiori rather than quoting a trimmed number.
6. **A null (no arm clears all three legs of the joint criterion)** is a VALID outcome. Classify it,
   name which leg binds, and hand the **stratified fallback question** to the operator with the
   measured numbers for `stratified` (the named fallback) and `feasibility_clamp` beside it.

### The JOINT success criterion (the spec's, verbatim in structure)

A winning arm must do all three:

* **(a)** hold the ORDERING constraint at **every** position's draftable tier;
* **(b)** remove — or at minimum not reintroduce — the give-back, measured as the
  availability-discount retention on the flagged cohort of the served board;
* **(c)** drive the NF-INJ1 violation count on its counterfactual board toward **zero**.

⛔ A run that clears (a) only at positions where the mechanism is INACTIVE has not cleared (a); the
active-cell count is reported beside the pass count (NF-D20).

---

## 7. Runtime + provenance

Fold capture is measured at **~15 s warm per fold** (191.7 s on the first, cold), so the decisive
7-fold run plus the 2026 application is expected **> 2 min** and is handed to the operator
paste-ready. A ≤2-fold `--smoke` runs in-session as a code-path proof only, and a smoke is NEVER a
gate (its artifacts are written to `*_smoke.{json,md}`).

The learner scores are computed from the SAME `feats` frame the shipped build used (captured as an
OUT-param, the INC-41 `run_ref` pattern), so the arm the bake-off scores and the arm the board would
serve cannot drift (NF-C0e).
