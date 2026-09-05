# NF-INJ2c — PRE-REGISTRATION: the assignment-rule fix on the STRICT-DOMINANCE route

**Committed BEFORE any arm is scored, and BEFORE the node-3b re-measure has been run** — so nothing
in this document can have been shaped by a number this session has seen. That is stated as a
checkable provenance fact, not a claim of virtue: node 3b is an operator run that has not happened,
its report does not exist, and the guard suite pins that it did not exist at this commit.

`best_alpha = 0`. Nothing here serves. `SERVED_ARM` stays `None`; `assert_coherent()` refuses a flag
flip the record does not support. DEPLOY-HELD throughout.

> **AMENDMENT LOG — this document has been amended. ⛔ No section below is edited.**
>
> | # | date | authority | what it declares | where |
> |---|---|---|---|---|
> | 1 | 2026-09-05 | PM ruling, decision request #6 (D1) | how §7's positive control is READ: the null leg's `VACUOUS` is declared INAPPLICABLE to this family on a source-measured entailment, the INJECTED leg becomes the control's binding substance, and a degenerate surviving EITHER leg is a control failure the declaration does not cover | `nf_inj2c_preregistration_amendment_1.md` |
>
> ⭐ The pointer is here so no reader can reach §7 without learning the amendment exists. Every
> amendment in this log is **REFUSE-ONLY**: it may block a disposition, ⛔ never make one easier to
> reach than this registration made it.

---

## 0. What this registration rests on, and what it is not allowed to touch

| document | node | what it fixes | status here |
|---|---|---|---|
| `nf_inj2c_coherence_diagnosis.md` | 1 | the games-floor hypothesis, REFUTED; the §4 per-stat bound | evidence, ⛔ never re-read as a result |
| `nf_inj2c_margin_construction_rule.md` | 3a | **every tie band**, the six measures, the pre-committed outcomes | **BINDING; ⛔ not edited by this document** |
| `nf_inj2c_fold_fidelity_finding.md` | 3c | the +1 fold is not reachable | settled by PM ruling 2026-09-01 |
| PM re-scope, 2026-08-31 | — | the ship route; coherence measured, never gated | verbatim in the spec |
| PM ruling, 2026-09-01 | — | **seven folds; the binding deflation field** | verbatim in the spec, quoted in §2/§3 |

⛔ **This document declares; it does not measure.** The served incumbent's coherence and give-back
BASELINE is whatever node 3b's capture-pinned run records, and it lives in **that** report — it is
⛔ never copied into this one. That is deliberate: a pre-registration that has to be re-opened to
paste numbers in is a pre-registration with an edit path, and the margin rule (3a) already fixes
every band, so the baseline cannot move a single decision boundary. §5's verdict rule reads the
baseline THROUGH 3a's already-committed bands, from `nf_inj2c_dominance_baseline.md`.

---

## 1. The hypothesis, and the honesty clause it inherits

**H1 — the ASSIGNMENT RULE, in point space.** `stratified` — the arm that permutes the fantasy-point
multiset **within availability strata** rather than across the whole position — improves the board on
every registered dimension against the SERVED incumbent, and regresses none.

NF-INJ2b already isolated the mechanism: +0.4452 CRPS, 7/7 folds, p = 0.0009, ordering held at all
four positions, with the matched TARGET foil showing the *rate* fit target mildly harmful. What that
story could not do was clear its coherence clause, because the clause demanded `= 0` of a per-fold
mean. Node 1 then established WHY no arm in this family can reach zero — the envelope is a per-STAT
ceiling and every assignment rule permutes a per-PLAYER aggregate (**the §4 bound**). The PM retired
the full-coherence disposition on that evidence and routed it to NF-COH2.

**The honesty clause, carried verbatim from the spec:** *"the assignment-rule result is settled; what
is NOT settled is whether that arm can clear a correctly-specified coherence clause at all — 8.57
violations/fold is not an edge case a tolerance absorbs, and this story may buy a properly-specified
record of a second refusal."* Both outcomes close the question honestly and the story is funded for
either.

⚠️ **What H1 does NOT claim.** It does not claim the board becomes coherent; node 1 proves it cannot.
It claims **DOMINANCE** — strictly better or tied on every measure. PM ruling 5 makes the
consequence part of the ship: *"this HALVES the incoherence and the give-back, it does not end
them."*

---

## 2. THE FIELD — the PM's declaration, and its consequences named forward

### 2.1 The declaration (PM ruling 2026-09-01, verbatim)

> "the deflation gates' BINDING field is NF-INJ2c's own coherent family, declared on mechanism before
> any deflation statistic is computed: point-space assignment rules only — incumbent (reference),
> stratified, feasibility_clamp, and the two registered degenerates. The four rate-space arms are
> excluded as a DIFFERENT MECHANISM already refused on the ordering gate (NF-INJ2's
> CONSTRAINT_REFUSED — that refusal stands and is not re-read; carrying a refused mechanism's arms in
> V would tax this contest for a search it is not running: the MH2.5/NF-W6b-C V-inflation class).
> Provenance of the narrowing: PM ruling 2 on the 2b closeout framed this story's contest as
> stratified-vs-the-SERVED-incumbent — a point-space question — before any deflation figure at any
> field width existed; the family follows from that ruling, not from 2b's 0.9325. V-membership per
> standing conventions: the incumbent reference arm ∉ V (MH2.1(a)); degenerates ∈ n_trials, ∉ V
> (DSR-CONV, opted into here, forward). Per NF-D14's two-sided rule, the INHERITED 10-arm field's DSR
> is ALSO computed and reported beside the binding figure, labelled NON-BINDING DIAGNOSTIC, declared
> as such here in advance — both numbers publish regardless of which looks better, and no third field
> is ever computed. If the binding family's DSR refuses, that is DEFLATION_REFUSED and the thread
> closes at that specification; the diagnostic does not rescue it."

### 2.2 The binding field, enumerated

| # | arm | F1 target | F2 assignment | role in the binding field |
|---|---|---|---|---|
| 1 | `incumbent` | points | point-by-score | **REFERENCE** — today's served board, the bar. ∈ `n_trials`, **∉ `V`** (MH2.1(a)) |
| 2 | `stratified` | points | point-within-availability-strata | **PRIMARY** — H1 |
| 3 | `feasibility_clamp` | points | point-by-score, envelope-bounded rescale | the point-space alternative, carried by name |
| 4 | `mvp1_null` | — | no re-order at all | **DEGENERATE** — must LOSE. ∈ `n_trials`, **∉ `V`** (DSR-CONV) |
| 5 | `random_order` | — | seeded within-position random | **DEGENERATE** — must LOSE. ∈ `n_trials`, **∉ `V`** (DSR-CONV) |

`declared_field_size = 5`, passed to `cv_power.classify_null(declared_field_size=5)`. Read
`field_remedy_admissible`, ⛔ never the prose (MH2.7). ⛔ **No post-hoc trim, in either direction**
(MH2.2).

**Excluded, and why:** `points_rate_permute`, `rate_refit`, `points_rate_stratified`,
`rate_refit_stratified`, `rate_refit_reselect` — the rate-space mechanism. NF-INJ2's
`CONSTRAINT_REFUSED` **stands and is not re-read**; these arms are out because they belong to a
different mechanism, ⛔ not because of anything they scored.

### 2.3 ⭐ THREE CONSEQUENCES OF THIS FIELD, DECLARED NOW SO NONE IS DISCOVERED LATER

Each follows arithmetically from §2.2 and is knowable before a single arm is scored.

**(a) `V` has exactly TWO members — a 1-df variance estimate.** Excluding the reference and both
degenerates leaves `{stratified, feasibility_clamp}`. `var_trials_sr` is therefore a two-point
sample variance (`ddof=1`), which is itself a high-variance quantity: it can land small (making the
bar generous) or large (making it punishing) for reasons that are noise in a 2-point estimate. This
is a REAL fragility of the declared design and it is stated here, in advance, rather than offered as
an explanation after a number arrives. ⛔ It is not a licence to change the field afterwards.

**(b) THE FIELD-TRIM READING IS INADMISSIBLE BY CONSTRUCTION (NF-W7h).** With two contributors, the
"drop `V`'s largest contributor and re-read DSR" diagnostic can only delete `stratified` (the arm
under test — inadmissible outright) or `feasibility_clamp` (leaving `V` undefined at one point). So
if DSR refuses, the 2×2 is reported as **STRUCTURALLY UNAVAILABLE**, ⛔ never as a trimmed number.
A refusal here is stated *a fortiori* on the design, not rescued by a deletion no registration could
make.

**(c) DSR-CONV'S EXCLUSION IS NON-MONOTONE, SO IT IS NOT A LEVER.** Dropping a *far-out* designed
loser lowers the bar; dropping one near the field mean **widens** `V` and RAISES it. Which happens
here is unknown in advance and ⛔ must not be treated as a knob. Per DSR-CONV's own convention **both
figures are computed and published** — degenerate-excluded (**BINDING**) and degenerate-included
(sensitivity). ⚠️ This is the same field under the two `V` conventions the program already owns; it
is ⛔ **not** a third field, and the PM's "no third field" instruction is honoured.

### 2.4 The NON-BINDING DIAGNOSTIC field (NF-D14's two-sided rule)

The **inherited 10-arm NF-INJ2b field** — all ten arms of `nf_inj2b_rate_ordering.ARMS` — has its
DSR computed and published beside the binding figure, labelled **NON-BINDING DIAGNOSTIC**, declared
as such **here, in advance**. It is published **whichever way it comes out**, including the case
where it is more favourable than the binding number. It ⛔ **cannot rescue a binding refusal** and no
disposition reads it.

---

## 3. Folds, metric, and the calendar-bound trigger

* **Folds: SEVEN — 2019–2025**, inherited from NF1.5's own `score_from`, at the shipped
  `base_from = 2017`. ⭐ The window's authority is that it was **inherited, not chosen**; re-cutting
  it is refused (PM ruling 2026-09-01). Node 3c's three-leg finding settles 2018 as not data-honest.
* **The 8th fold is CALENDAR-BOUND: the realized 2026 season.** The PM has ruled it publishable as a
  re-test trigger — *"the trigger names a date, not a purchase no design can make"*.
  ⚠️ **One standing-rule condition, declared forward:** a fold trigger only means anything when
  `SR > SR0`; if the measured design reads `DSR_UNREACHABLE` (`SR ≤ SR0`), `n` enters only through
  `√(n−1)` and can scale a positive gap but cannot create one (NF-W8-0d), so the trigger is
  **WITHHELD with that reason stated** rather than published — publishing it would be the NF-D18
  misleading direction. The PM's ruling is permissive ("may be published"), so this condition is a
  standing-rule application, ⛔ not a departure; it is flagged in the closeout either way.
* **Primary metric:** CRPS on realized season PPR (`level_recalibration.SELECTION_METRIC`).
* ⛔ **MAE never selects** (NF-D11/NF-D14: skewed target, low-availability cohort near the
  conditional median). Reported, never used.
* **Design quantities, computed before any scoring** (they depend only on the fold count):
  * `cv_power.dsr_ceiling(7) = 0.99973` against a 0.95 bar ⇒ **the ceiling does NOT bind at seven
    folds.** A refusal here would be a statement about the evidence, ⛔ not about structural
    impossibility (contrast MH2's 3-fold ceiling of 0.977).
  * `cv_power.fold_consistency_clause(n_folds=7)` ⇒ **6 of 7 wins required**, attained false-fire
    **0.0625**. ⛔ Never the raw 0.60 rate (MH2 H8). Note the calibrated clause is STRICTER than the
    legacy one here (6 vs 5), which is the direction MH2 H8 guarantees.
  * `cv_power.pbo_evaluable(n_folds=7, n_configs=5) = True` ⇒ PBO is computable, not UNDEFINED.

---

## 4. COHERENCE — MEASURED AND REPORTED, ⛔ NEVER GATED AT ZERO

PM ruling 2, verbatim: *"Coherence is MEASURED AND REPORTED (both residual populations, per your §2
table), never gated at zero."*

The licensing evidence is node 1's **§4 bound**: the envelope is a per-STAT ceiling while every
assignment rule permutes a per-PLAYER aggregate, so **no arm in this family can reach zero**, and a
gate demanding it would be refusing on a structural impossibility — the decision-in-a-gate's-clothing
the program forbids.

Reported in full for **every** arm including the degenerates, with **no bar**:

* violating players per fold, raw **and** attribution-controlled;
* worst breach as a multiple of the envelope (`max times_over`);
* min expected games on a violating row, and the share of violating rows under 2 expected games;
* the per-position split.

Coherence enters the **verdict** only through §5's M2 and M3 — as **DOMINANCE against the served
incumbent**, ⛔ never as a distance from zero.

---

## 5. THE VERDICT RULE — strict dominance, through node 3a's already-committed bands

⛔ **Nothing in this section is new.** `nf_inj2c_margin_construction_rule.md` (node 3a) is BINDING and
was committed before the re-measure; this is a pointer, not a restatement with room to drift.

| # | measure | better is | band | rule |
|---|---|---|---|---|
| M1 | CRPS mean lift vs incumbent over the seven folds | higher | SE of the arm's own per-fold lift series | R1 |
| M2 | coherence violating players/fold (attribution-controlled) | fewer | SE of the per-fold PAIRED difference | R1 |
| M3 | worst breach × envelope | lower | 0.01 (recorded precision) | R2 |
| M4 | injury give-back as `max(pct, 0)` | lower | 0.01 pp (recorded precision) | R2 |
| M5 | draftable-tier Spearman ρ per position | higher | NF-INJ2's registered test verbatim: one-sided paired t on per-fold (incumbent − arm) deltas, BH at q = 0.10 across four positions | R3 |
| M6 | per-group interval coverage | clears its floor | NF-D22 `power_floor()` from each group's n + the pre-registered false-reject target — ⛔ never a flat nominal point-floor | R3 |

**`stratified` DOMINATES** iff on **every** measure M1–M6 it beats the served incumbent by more than
that measure's band, or falls within it. **A single measure worse by more than its band is a
regression, and by PM ruling 3 that is a NULL** — ⛔ never a band to widen, a measure to drop, or a
dimension to re-classify as disclosed-only.

Both measure definitions flagged at 3a are **PM-APPROVED as declared** (ruling 2026-09-01): M4 as
`max(pct, 0)` with the signed figure reported beside it always, and M2 attribution-controlled and
carried despite being measured inert — *"an inert declared measure is a finding; an undeclared one is
a hole."*

---

## 6. DEFLATION GATES AND CONVENTIONS

Per the program convention (CLAUDE.md): **deflation-class = `{pbo, cscv, dsr, deflated_sharpe}`**;
**field-level = `{pbo, cscv}`**; `bh_fdr` and `fold_consistency` are **multiplicity/stability, NOT
deflation-class**. The shipped `cv_power` defaults are taken **unchanged** — ⛔ no `deflation_gates=`
override is registered, so none may be passed.

* **PBO < 0.2** (CSCV), computed over the **ELIGIBLE set of the binding field**, with
  `pbo_application="field"` passed to `classify_null`. ⭐ PBO is ONE number about the SEARCH; reading
  it per-arm converts "the search was unstable" into "this arm failed", which the statistic does not
  say. Report the **flip distribution** and the **contender spread** beside it (NF1.8) — a tied field
  with a high PBO is a TIE, not overfitting, and only the spread discriminates.
* **DSR ≥ 0.95**, computed as in §2: `V` over `{stratified, feasibility_clamp}`, `n_trials = 5`.
  Published four ways, all declared here: binding (degenerate-excluded) · degenerate-included
  sensitivity · the 10-arm NON-BINDING DIAGNOSTIC · and, if it refuses, the lockstep check below.
* **BH-FDR.** The CRPS leg is a **SINGLE hypothesis** — one mechanism, one population, no registered
  per-position axis on the selection metric (the per-position CRPS split is a diagnostic). The
  ORDERING constraint keeps its **own 4-position BH family at q = 0.10**, because that axis IS
  registered. ⚠️ That BH protects against a false REFUSAL, i.e. it is directionally generous to the
  arm — on the record here rather than discovered by a reader.
* **Fold consistency** via `cv_power.fold_consistency_clause(n_folds=7)` ⇒ 6 of 7. ⛔ Never the raw
  0.60 rate.
* **IF DSR REFUSES:** run `cv_power.lockstep_variance_lever` FIRST and report it before naming any
  remedy (NF-W8-0d). If the lever is void, ⛔ publish **no** row/fold/draw trigger. The 2×2 field-trim
  diagnostic is **STRUCTURALLY UNAVAILABLE** here (§2.3(b)) and is reported as such, ⛔ never as a
  trimmed number. Per the PM: *"If the binding family's DSR refuses, that is DEFLATION_REFUSED and
  the thread closes at that specification; the diagnostic does not rescue it."*

---

## 7. THE INJECTED-EFFECT POSITIVE CONTROL — and the partition it needs, declared forward

NF-INJ2b's control returned **`BLIND`**, and that badge was **wrong as a reading**: two arms were
stopped under injection by `coherence_restored` ALONE — a gate an injected CRPS effect **cannot
move**. PLAT-CVP2 (the `CONSTRAINT_BLOCKED` instrument fix) **has not landed**: verified at this
commit, `cv_power` exposes no `CONSTRAINT_BLOCKED` verdict and no injection-invariant-gate parameter.
So the 2b annotation pattern is carried, and the partition is declared **here, before the control
runs**:

| | gates | can an injected CRPS effect move it? |
|---|---|---|
| **INJECTION-SENSITIVE** | M1 (CRPS lift), M5 (tier-ρ), the deflation gates, fold consistency | **yes** — the control is run and read over these |
| **INJECTION-INVARIANT** | M2, M3, M4 (board coherence + give-back), M6 floors | **no** — these are properties of a board an injected effect cannot reach |

⭐ **The control is evaluated over the injection-SENSITIVE half only**, and `blocking_gates` is read
against this declared table. If `BLIND` fires and every blocker is on the invariant side, the honest
statement is: *the family's statistical half demonstrably fires; the verdict was decided by measures
no injection can reach* — ⛔ neither a rescue nor a condemnation. ⛔ **The control is never re-run
with a constraint removed to obtain a nicer badge** (E2.1-r).

⚠️ Note the coherence-as-a-GATE blocker that made 2b's control BLIND is **absent by construction**
here: PM ruling 2 removed coherence from the gate set. That is a consequence of the ruling, ⛔ not a
convenience this registration arranged.

---

## 8. ANCHORS AND DEGENERATES — scored every run, their numbers READ

* **`mvp1_null`** (no re-order) and **`random_order`** (seeded within-position permutation) are
  pre-registered **DEGENERATES**: they **MUST lose**. Their scores are READ, ⛔ never reasoned about
  (NF-D14: "zero-heavy" is not the test for an inversion — score the degenerate and read it).
* A **CONSTRAINT a degenerate satisfies** is fine — the metric eliminates it. A **CRITERION a
  degenerate wins** is **fatal** (NF1.8). Both degenerates are scored against **every** M1–M6 measure
  and the table is published, so a criterion one of them wins is visible rather than inferable.
* `mvp1_null` doubles as the **attribution control** for M2 (measured inert on node 1's populations;
  declared anyway).
* Reproduction: every arm is scored under **common random numbers** where draws are involved, and
  the run is pinned against the node-3b capture (§9).

---

## 9. REPRODUCTION AND THE CAPTURE PIN (D3)

* The decisive run pins against the node-3b **capture** — a sha256-stamped published board and its
  market snapshot — ⛔ never a re-pull. A failed pin **exits 2 and reports the run VOID, not a null**
  (3a §5 branch 3): a dominance claim against a board nobody is served is not a measurement.
* ⛔ **No bitwise comparisons.** Population-scoped material tolerance (rtol/atol 1e-9); rookie-band
  motion is read against a ≥5-draw same-commit envelope, because same-commit rebuilds differ there
  by 0–21 material cells.
* This worktree carries neither the gitignored 2026 board parquet nor `sports.duckdb` (NF-INFRA1),
  and a fresh worktree silently REBUILDS the gitignored feature caches from a live upstream — so the
  decisive run states which cache vintage it measured on.

---

## 10. EXPLICITLY OUT OF SCOPE (kept separable — NF-W7d)

* **Full coherence restoration** — retired for this story on the §4 bound; owned by **NF-COH2**.
* **The rate-space mechanism** — NF-INJ2's refusal stands and is ⛔ not re-read.
* **The per-stat envelope's own construction** — NF-COH2.
* **`cv_power`'s `CONSTRAINT_BLOCKED` fix** — PLAT-CVP2; annotated around here (§7), ⛔ not patched.
* **NF-RATE1** — coordination is at the level of confirming its guards stay green on the
  counterfactual (PM ruling 5); ⛔ **no shared files**.

---

## 11. PRE-COMMITTED OUTCOMES

3a §5 governs and is ⛔ not restated with room to drift. Two clarifications the PM ruling adds:

1. **Dominance holds on M1–M6 AND the deflation gates pass** → SHIP under the dominance disposition,
   deploy-held, with PM ruling 5's disclosure (this HALVES the incoherence and the give-back; it does
   not end them; NF-COH2 is the recorded successor).
2. **Dominance fails on any one measure beyond its band** → **NULL**. Verbatim: *"that is a NULL, not
   a margin to adjust."*
3. **The capture cannot be pinned** → **VOID**, not a null.
4. **M1–M6 dominate but the binding DSR refuses** → **`DEFLATION_REFUSED`**, read against §7's
   control, with §6's lockstep check first and §2.3(b)'s structural unavailability stated. The
   diagnostic field publishes beside it and ⛔ does not rescue it.
5. ⚠️ **3a §5 branch 5 refers to "DSR at 8 folds".** That branch is left **VERBATIM and UNEDITED** in
   3a; it is **SUPERSEDED by measurement** — node 3c established there is no 8-fold option and the PM
   settled the registration at seven. The branch's *substance* (a DSR miss is branch 4, and no
   further fold trigger without the lockstep check) is unchanged and binds at seven folds.

---

## 12. PROVENANCE

* Written **before** node 3b ran and **before** any arm was scored under this registration; the
  guard suite pins that `nf_inj2c_dominance_baseline.{json,md}` did not exist at this commit.
* The FIELD was declared by the PM on 2026-09-01 **before any deflation statistic was computed for
  any candidate family** — ⛔ no per-candidate-family DSR was computed, per the NF-INJ3b-M rule.
* The FOLD count was settled by the PM on the same date, on node 3c's data-fidelity finding, whose
  decisive leg runs **against** the arm.
* Sequence, as it actually happened: node 1 (diagnose) → node 2 (carried executions) → **3a (the
  margin rule)** → 3c (the fold finding) → PM ruling → **this registration** → 3b (the re-measure,
  operator) → node 4 (the decisive run).
