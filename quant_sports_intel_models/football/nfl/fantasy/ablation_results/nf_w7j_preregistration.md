# NF-W7j pre-registration — the COMPONENT-CLAUSE decision + the served-cell audit

**Committed BEFORE any clause is re-scored** (the §0.5 discipline). Every threshold, unit, test and
fail-closed condition below lives as a constant in `fp_component_clause.py`; the runner
`run_nf_w7j_component_clause.py` READS them (NF-D16).

⚖️ `best_alpha = 0` · **DEPLOY-HELD** · research-only · no changelog. Nothing here promotes,
publishes, serves or retrains, and nothing re-opens QB's calibration (NF-W7f settled it).

---

## 0. What this story is, and what it is NOT

NF-W7f produced a QB assembled distribution that **clears the PIT bar on 8/8 folds where the
incumbent clears 0/8** and **beats the matched foil on the proper score** (+0.0184 CRPS, CI95
[0.0032, 0.0336], 6/8, p = 0.0121, PBO 0.0, coverage(80) 0.8299). Its ship was refused by **exactly
two** of 22 gate clauses:

| clause | kind | measured |
|---|---|---|
| `per_leg_calibration_not_degraded` | ANCHOR / registration | +0.3866% summed priced-leg CRPS against a tolerance of **0.0** |
| `dsr_ok` | STATISTICAL | DSR 0.0 at observed SR 1.013 against SR0 5.482 |

NF-W7f §11.2 and §12.5b(3) explicitly deferred ONE of those to a successor's forward registration:
whether *"components must not degrade"* should be a **hard gate** or a **reported diagnostic**, with
the PM's lean recorded as *"keep it a hard gate **unless** the specific degraded component is shown
not to be independently served/consumed."*

**This story decides that one clause, forward, and audits that one condition.** It does not decide
`dsr_ok`.

### 0.1 ⭐ THE STRUCTURAL FACT THAT MAKES THIS NOT A BAR-MOVING EXERCISE

**The component-clause decision cannot, by itself, certify QB or license a ship, because `dsr_ok` is
a second and independent refusal.** Whatever this registration decides, the gate's verdict remains
`NO` unless `dsr_ok` also clears, and `dsr_ok` is out of scope here (NF-W7f measured its remedy as a
lower-variance design, and this story adds no data, no folds and no draws).

This is stated FIRST and on purpose. The E2.1-r hazard in a clause-relaxation story is that the bar
is re-read to buy the answer. Here the answer is not for sale: the most this decision can achieve is
to reduce a **two-clause** refusal to a **one-clause** refusal and to re-classify the null from an
opaque mixed `CONSTRAINT_REFUSED` into a named, mechanism-attributed statistical state with a
registered remedy. That is the whole deliverable, and it is worth having — but it is not a ship.

### 0.2 ⭐ MANDATORY DISCLOSURE — this decision is NOT made blind

NF-W7f **already published** the full shape of the refusing quantity, in §12.3 of its own
pre-registration and in its record:

> *"per-fold relative change **[−1.25, −0.35, +0.74, +1.81, +0.32, +1.42, −0.29, +0.60] %** → degraded
> on **5 of 8** folds, improved on 3, mean **+0.375%**, range −1.25% to +1.81%"*, confined to ONE leg
> (`passing_yards`).

⛔ **So this registration is made with the answer in view, and pretending otherwise would be the
selection bias the §0.5 discipline exists to prevent** (the MH2.2 / NCAAF-S1 disclosure precedent).
Three structural protections replace the blindness that is not available:

1. **The rule SHAPE is inherited, not chosen here.** *Significant AND ≥ 1/10 of the arm's claimed
   effect* is NF-W7c's convention, and NF-W7f §12.5b(3) **prescribed it by name as the replacement**
   before this story existed. ⛔ No threshold is derived from the observed +0.3866% (E2.1-r).
2. **The decision cannot buy a ship** (§0.1).
3. **Both readings are reported, always** — the raw 0.0-tolerance clause stays scored and printed on
   the artifact beside the decided one, and the verdict names which of them binds (NF-D20: a
   pre-registered anchor that fails is left FAILING and DECOMPOSED, never re-labelled).

---

## 1. The served-cell audit (the PM's condition, made CHECKABLE)

NF-W7f §12.5b(3) established that every consumer of `stat_distribution_serving{,_d}` is an
NF-W6/W7 research runner, and left **one question explicitly unresolved**:

> *"(b) whether the served paid **stat line** is derived from these same cells was NOT established
> here and must be resolved before relying on this."*

**That is the question this audit answers**, and it is answered by MEASUREMENT — a transitive
import-closure walk over the actual serving plane — not by grep and not by argument (INC-27: a
consumer list built from one file's imports is not a consumer list; NF-C0e: a claim about what the
product does must be read off the thing that produces it).

### 1.1 The audit, specified in advance

`SERVING_PLANE_SEEDS` (declared constant): the five entry points that between them produce and serve
the paid stat line —

- `…fantasy.export_draft_board_json` — the exporter that WRITES `passYds`/`passTd`/… into the
  published board
- `…fantasy.season_projection` — the model that COMPUTES the `proj_*` columns the exporter reads
- `app.backend.main` — the whole API surface
- `app.backend.routers.fantasy` — the entitled `/fantasy/nfl/projections-full` + `league-board`
  routes
- `quant_sports_intel_models.fantasy_engine.scoring` — the scoring authority (NF-EPIC 1)

`FORBIDDEN_SUBSTRINGS` (declared constant): `stat_distribution_serving`, `stat_distributions`,
`fp_assembly`, `fp_qb_marginal`.

**PASS** iff the transitive import closure of every seed contains **zero** module whose dotted name
carries a forbidden substring.

### 1.2 ⭐ The audit is TWO-SIDED and must prove it is not vacuous (NF1.7 (a) / INC-38)

A closure walker that silently resolves nothing returns an empty hit set for every seed, so a PASS is
indistinguishable from a broken walker. The audit therefore ALSO runs a **positive control**:

`POSITIVE_CONTROL_SEEDS` = `…fantasy.run_nf_w7f_qb_marginal` and `…fantasy.fp_assembly`, which are
KNOWN to consume the cells. The audit **RAISES** — never returns PASS — if either control yields an
empty hit set, and it RAISES if any seed's closure is implausibly small (`MIN_CLOSURE_MODULES`).

### 1.3 What the audit licenses, and its expiry

A PASS establishes exactly one fact: **the NF-W6d per-stat cells that NF-W7f's recalibration
degrades reach no serving surface** — not the published board, not the entitled stat line, not the
scorer. It licenses the clause relaxation of §2 and **nothing else**.

⚠️ Two limits, stated in advance:
- It is true of the **SERVING plane only**. The NF-W6/W7 research line consumes the cells, and NF-W8
  intends to.
- ⭐ **It EXPIRES the moment it stops being true, and the expiry is MECHANICAL, not a promise.** The
  audit is re-run on every invocation of the decided clause, and the clause **FAILS CLOSED to the
  raw 0.0 tolerance** if the audit does not pass. A future story that wires the cells into a served
  surface therefore re-arms the hard gate automatically, with no one having to remember.

---

## 2. THE DECISION — `per_leg_calibration_not_materially_degraded`

**DECIDED FORWARD: the clause becomes a MATERIALITY gate, not a zero-tolerance gate, and it remains
a GATE (it is not demoted to a bare diagnostic).**

It **REFUSES** the ship iff **ALL FOUR** hold:

| # | condition | threshold source |
|---|---|---|
| A | the served-cell audit **PASSES** (§1) — else fail closed to the raw 0.0 tolerance | the PM's own stated condition |
| B | **DEMONSTRABLE** — the per-fold priced-leg relative-change series is significantly positive, one-sided paired test, **α = 0.05** | the harness's own `MC.onesided_paired_pvalue`, the identical instrument `beats_foil` uses |
| C | **MATERIAL** — the degradation's point estimate is **≥ 1/10 of the arm's claimed effect** | NF-W7c's convention, named by NF-W7f §12.5b(3) |
| D | the arm's claimed effect is itself well-defined (a positive assembled Δ) | else the ratio in C is meaningless |

Condition A is inverted relative to B–D: A is a **precondition for relaxing at all**, B–D are the
**refusal test**. In one sentence: *with the harm demonstrably absent from a surface nobody is
served, we do not refuse a ship on it — and if either half of that changes, we do.*

### 2.1 The units, fixed in advance (⛔ not after seeing which one is convenient)

The component quantity is a **sum over 10 priced legs**; the claimed effect is **one assembled
number**. A raw absolute ratio is dimensionally incoherent (10 legs vs 1 total), so:

- **PRIMARY unit — RELATIVE.** `component_relative_change` (served → recalibrated, as a fraction) vs
  `assembled_relative_effect` = `mean_delta / foil_mean_crps`. Both dimensionless, both the same
  model's effect on the same object class. Materiality band = `MATERIALITY_FRACTION` (= 0.10) ×
  `assembled_relative_effect`.
- **REPORTED SENSITIVITY — ABSOLUTE.** `component_absolute_change` (CRPS units, summed legs) vs
  `mean_delta` (CRPS units). Recorded every run.

⭐ **The verdict must state whether the two units AGREE**, and if they disagree the PRIMARY binds and
the disagreement is reported in the headline. (Declared now so a later reader cannot suspect the unit
was picked to fit.)

### 2.2 The materiality read is reported in BAND UNITS (the NF-W7i lesson)

The materiality half is reported as NF-W7i reported its ceiling: the point estimate **and its CI95**
expressed as a **multiple of the materiality band**, with one of three states —

| state | rule |
|---|---|
| `MEASURED_IMMATERIAL` | the CI95 **upper** bound sits BELOW the band ⇒ the evidence RULES OUT a material degradation |
| `MEASURED_MATERIAL` | the CI95 **lower** bound sits ABOVE the band ⇒ the evidence ESTABLISHES one |
| `UNDECIDED_MAGNITUDE` | the CI95 spans the band ⇒ the design does not resolve the magnitude |

⛔ **`UNDECIDED_MAGNITUDE` must NOT be reported as `POWER_LIMITED`** and must not be silently read as
either of the decided states (the NF-W7i cv_power hand-correction: a band decision is not a power
verdict, and a power verdict is not a band decision).

### 2.3 ⭐ Why "not demonstrable" is allowed to decide a REFUSAL — and what it costs

The burden of proof for a **refusal** sits with the refusing evidence. NF-W6 refused a ceiling that
was statistically demonstrable but immaterial (*demonstrable ≠ material*); this is the same principle
facing the other way: a clause refusing a ship on a **sign that is not established** (5 of 8 folds,
a CI spanning zero) is refusing on something not distinguishable from noise. E2.1-r cuts both ways —
a bar must not be re-read to PERMIT a ship, and equally must not REFUSE on an unmeasured quantity.

⚠️ **The cost, stated plainly rather than hidden:** the decided clause is strictly WEAKER than the
raw one, and it cannot catch a real degradation this design is underpowered to demonstrate. That
residual risk is what condition **A** pays for — an undetectable degradation in cells that reach no
served surface cannot reach the product. **Neither half would justify the relaxation alone**, which
is exactly why the clause is a conjunction and why A fails closed.

### 2.4 What is NOT decided here

- ⛔ `dsr_ok` — untouched. NF-W7f measured field coherence as NOT the lever (V falls 8.8×, DSR reaches
  0.174 against a 0.95 bar) and the instrument reads `DSR_UNREACHABLE`. ⛔ No post-hoc field trim
  (MH2.2). The declared field stays 4.
- ⛔ QB's calibration — settled by NF-W7f, not re-opened.
- ⛔ Any change to NF-W7f's scores. This story re-derives a CLAUSE from NF-W7f's **stored per-fold
  results**; it refits nothing.
- ⛔ Whether NF-W8 may consume an uncertified QB distribution — a governance call for the 2nd reader
  (§5).

---

## 3. Reproduction pin (the decision is measured against the object NF-W7f scored)

Before any clause is evaluated the runner asserts, against `nf_w7f_qb_marginal.json`, that every
quantity the decision consumes reproduces NF-W7f's record EXACTLY:

| pinned | expected |
|---|---|
| `smoke` | `False` |
| `n_folds` | 8 |
| winner / matched foil | `zm_floor` / `mixall_learned` |
| `per_leg_detail.relative_change` | 0.003866 |
| `per_leg_detail.tolerance` | 0.0 |
| `per_fold_series.priced_leg_relative_change_by_fold` | 8 values, mean 0.003866 to 1e-6 |
| `mean_delta` / `ci95` | 0.0184 / [0.0032, 0.0336] |
| `mean_crps[matched foil]` | 2.5829 |
| gate `dsr_ok` / `per_leg_calibration_not_degraded` | `False` / `False`; all other 20 clauses `True` |

Any mismatch **RAISES** (`exit 2`, `invalid: true`). ⛔ A decision measured against a different object
than the one NF-W7f scored is not a decision about NF-W7f.

---

## 4. Re-scored verdict + null classification

With the decided clause substituted for the raw one, the runner re-derives the 22-clause gate and
classifies:

- If the gate goes **fully green** ⇒ `QB_CERTIFIED`.
- If the ONLY remaining failure is `dsr_ok` ⇒ the refusal becomes **purely statistical**, so
  `cv_power.classify_null(declared_field_size=4, degenerates_excluded_from_v=True)` classifies it —
  the call NF-W7f's mixed-refusal path bypassed — and `field_remedy_admissible` is read (MH2.7)
  rather than the prose.
- If any anchor clause still fails ⇒ `CONSTRAINT_REFUSED`, `binding_half: anchor`, `retest_trigger:
  None` (NF-D18), unchanged.

**Pre-declared certification rule.** `QB_CERTIFIED_FOR_NF_W8` requires the **FULL gate green** — the
identical bar NF-W7h pre-registered for RB (*"certified for NF-W8 ONLY … with the FULL gate green;
the state alone is a mechanism reading, never a certificate"*) and the bar WR and TE actually cleared
(NF-W7c TE DSR 0.9822; NF-W7e WR DSR 0.9852, both green on `dsr_ok`).

⛔ **This story does not lower that bar.** A three-part *"PIT + component rule + beats the incumbent"*
reading omits `dsr_ok`, and adopting it after seeing `dsr_ok` fail would be the E2.1-r inversion in
its most literal form — and would certify QB on a bar the other three positions were never held to.
If the PM intends a distinct, lower **consumption** bar for NF-W8 (as against a **ship** bar), that
is a governance decision to register FORWARD in NF-W8, not to infer here (§5).

---

## 5. ⭐ FLAGGED FOR A 2ND READER (governance)

Two items, neither of which this story resolves unilaterally:

1. **The clause decision itself** (§2) — a pre-registered gate is being replaced by a materiality
   gate. The audit that licenses it is mechanical and fails closed, the raw clause stays reported,
   and the decision cannot buy a ship; a 2nd reader should nevertheless confirm the conjunction in
   §2 and the disclosure in §0.2. (NF-W7i flagged its own amendment the same way.)
2. **The certification bar for NF-W8 consumption.** §4 holds QB to the full-gate bar WR/TE cleared
   and RB was registered against. If NF-W8 is to consume a distribution that is calibrated and
   score-beating but `dsr_ok`-refused, that is a **PM decision about what "certified" means for a
   consumer**, and it must be registered forward in NF-W8 — with the consequence stated that QB
   would then enter the optimizer on a weaker footing than WR/TE, which NF-W7c §4's cross-position
   scope rule already forbids ranking against them.

---

## 6. Deploy hold

`best_alpha = 0`. Nothing here promotes, publishes, serves, retrains or writes a serving path. No
`--publish`, no `deploy.sh`, no Dagster op, no S3 write, no dbt model — the runner reads a committed
JSON and writes local artifacts. NF-W7f's and NF-W7c's promote blockers are inherited in full. No
changelog (not user-visible).

---

## 7. RECORDED AMENDMENTS + POST-RUN FINDINGS

⛔ **Nothing below changed a threshold, a unit, a clause or a verdict.** Two are HARNESS fixes made
BEFORE any clause was evaluated (the audit and the pin both REFUSED to run, which is the floor
working); two are findings the run produced. The decided clause's four conditions, `α = 0.05` and
`MATERIALITY_FRACTION = 0.10` are exactly as committed in §2.

### 7.1 HARNESS FIX — the audit's vacuity floor was aimed at a proxy (before any verdict)

§1.2 applied a minimum closure SIZE to every serving-plane seed. `fantasy_engine.scoring`
legitimately trips it — it is a small PURE module whose entire closure is **2**. The audit correctly
**RAISED rather than scoring it clean**, which is the NF1.7 (a) floor doing its job, but the floor was
a PROXY for the real condition.

Fixed to assert the real condition directly: **every seed must RESOLVE to a module file** (an
unresolvable seed yields an empty closure, which has no hits and would read as a clean PASS), and the
SIZE floor moved to the **positive controls**, where a large closure is what makes an empty hit set
diagnostic. Strictly better targeted; it cannot be satisfied by a broken walker. RED-proved by
`unresolvable_seed_accepted` and `positive_control_check_removed`.

### 7.2 ⭐ FINDING — the component figure exists in TWO forms and they are NOT the same statistic

The pin caught this before any clause was evaluated (§3 doing its job). NF-W7f's headline
**+0.3866%** is the **POOLED ratio-of-sums** `(Σ recal − Σ served)/Σ served`; the per-fold series
whose significance the decision tests has a **mean of +0.3748%** (= NF-W7f's own stored
`relative_change_by_arm['zm_floor']`). They differ by ~3% relative — the NF1.8 distinction between a
pooled quantity and a mean of per-fold ratios.

Both are now pinned and both are reported, and the decision states which half reads which: the
**MAGNITUDE** half reads the POOLED figure (NF1.8 — pool, never a mean of means), the
**SIGNIFICANCE** half necessarily reads the per-fold series, because a paired test has no per-fold
units otherwise. ⭐ The gap is immaterial to the verdict — both figures sit ~5× above the band, and
the decision turns entirely on the significance half.

### 7.3 ⭐⭐ FINDING — the fail-closed path was written FAIL-OPEN, and a green suite could not see it

The first cut expressed condition A as `refuses = audit_ok and demonstrable and material and …`.
That reads exactly like a precondition and is **the opposite of what A is for**: with the audit
FAILING it returns "does not refuse", i.e. an expired or broken audit **silently REMOVES the gate**
rather than reverting to NF-W7f's raw 0.0 tolerance. Every test was green, because no fixture had yet
exercised a failing audit against a raw-refusing series. Found while writing the isolating fixture
for A, and now pinned two-sided: fail-closed must REFUSE where the raw clause refuses
(`test_condition_A_FAILS_CLOSED…`) and must still PASS where the raw clause passes
(`test_fail_closed_still_tracks_the_raw_verdict…`) — because "fail closed" means *the raw clause
governs*, not *always refuse*.

### 7.4 ⭐⭐ FINDING — the conjunction contained a VACUOUS clause, and only the RED proof saw it

`material_primary` was written `effect_well_defined and pooled_rel >= band_rel` — so condition **C
re-tested D**. Deleting **D** from the conjunction therefore left its isolating guard **GREEN**: C was
already refusing D's fixture. This is NF-D17's lesson *inside the guard written to honour it*, and it
was invisible to a green suite — the RED proof reported it as `effect_well_defined_dropped → GREEN`.
C is now the magnitude comparison ALONE and D is load-bearing (a non-positive claimed effect
collapses the band to ≤ 0, against which any degradation is trivially "material"). Re-proved RED.

### 7.5 The measured result (recorded here so the registration and the answer sit together)

| | value |
|---|---|
| served-cell audit | **PASS** — 5 serving-plane seeds, **0** per-stat-cell hits; positive controls 10 and 6 hits |
| RAW clause (tolerance 0.0) | **REFUSES** at +0.3866% |
| A · audit passes | **True** |
| B · demonstrable | **False** — p = **0.1611** vs α = 0.05; 5/8 folds; CI95 [−0.4575%, +1.2070%] |
| C · material (primary, relative) | **True** — **5.43×** the band; ABSOLUTE unit agrees |
| D · claimed effect well-defined | **True** |
| DECIDED clause | **does NOT refuse** |
| band state | `UNDECIDED_MAGNITUDE` — CI in band units [−6.42, +16.94] |
| re-scored gate | **21 of 22 green**; `dsr_ok` alone red |
| null state | `DSR_UNREACHABLE` · `field_remedy_admissible` **None** (field size is no lever at all) |
| re-test trigger | ⛔ no season/fold trigger — the lever is a LOWER-VARIANCE design |
| **certified for NF-W8** | **NO** |

⭐ **The decision turns entirely on the SIGNIFICANCE half, and the unit question is moot** — both the
relative and the absolute unit call the component cost material, so §2.1's choice of primary unit
does not touch the verdict. That is the robustness statement the two-unit reporting was registered to
make available, and it lands on the side that makes the decision *less* convenient to doubt.

⚠️ **`UNDECIDED_MAGNITUDE` is the honest read and it is not flattering to either side**: this design
does not resolve whether the component cost is material. The clause declines to refuse because the
harm is **not demonstrable**, and because condition A establishes that the harmed object reaches no
served surface — ⛔ **not** because the harm was measured to be small.
