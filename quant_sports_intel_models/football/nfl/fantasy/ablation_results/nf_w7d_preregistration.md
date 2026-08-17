# NF-W7d pre-registration — an explicit AVAILABILITY MIXTURE for the assembled QB fantasy-point distribution

**Committed BEFORE any full-run scoring** (the §0.5 discipline). Everything below lives as
constants in `fp_availability_mixture.py`; the runner `run_nf_w7d_qb_availability.py` READS them
(NF-D16). A smoke run (1 fold, QB only, 300 draws, artifacts suffixed `_smoke`) may be used to
prove the code path — no verdict, and **no constant may change in response to a smoke score after
this file is committed** except as an explicitly recorded SMOKE AMENDMENT (§11).

⚖️ Edge-independent projection product — `best_alpha = 0`, **deploy-held**, NF-G0 challenger.
Research-only: no changelog entry. Every emitted string is a calibrated RANGE, never an edge /
ROI / win-rate claim.

---

## 0. The thesis under test (not assumed)

NF-W7c certified the arbitrary-league fantasy-point assembly at TE and was refused at QB by **one
clause** — randomized-PIT decile flatness, 0.0888 against a 0.05 bar. Its §11.1 post-run finding
measured *why*, and the measurement is unusually specific:

| pos | all-zero rows | ρ̄ all rows | ρ̄ played-only | ratio | PIT (`joint_rank`) |
|---|---|---|---|---|---|
| **QB** | **53.9%** | 0.239 | 0.127 | **1.88×** | 0.065 ✗ |
| RB | 35.2% | 0.189 | 0.143 | 1.32× | 0.025 ✓ |
| WR | 32.9% | 0.126 | 0.102 | 1.23× | 0.017 ✓ |
| TE | 42.4% | 0.127 | 0.111 | 1.14× | 0.020 ✓ |

⭐ **The RATIO orders the failure; the SIZE of the zero atom does not** — RB carries the larger
joint-zero excess (17.6× vs QB's 11.0×) and passes comfortably. One Gaussian copula is being asked
to carry a binary AVAILABILITY factor and a within-game co-movement at once and fits a compromise
between them; and a Gaussian copula has **zero tail dependence by construction**, so at ρ̂ ≈ 0.24 it
cannot reproduce a 53.9% joint-zero atom at all. The tell that the defect belongs to the TARGET and
not to the assembly: **every representation fails PIT at QB, including `foil_direct_points`, which
contains no copula whatsoever** (0.0959 — the worst in the field).

**The thesis.** Separating the two things the single copula conflates —

```
F_total(t) = (1 − π) · 1{t ≥ 0}  +  π · F_played(t)
```

a Bernoulli availability draw times a conditional-on-playing joint draw, with **Σ estimated on
active rows only** — produces an assembled QB fantasy-point distribution that clears the PIT bar
*and* beats both the NF-W7c incumbent and a matched foil on the proper score. A null is a
legitimate published outcome, naming exactly which of the mixture's two halves fell short.

---

## 1. ⚠️ This must beat NF-W4's null ×4 — the distinction, registered

NF-W4 tested an availability mixture and returned four nulls. This story is not entitled to ignore
that, and it is not a free win. NF-W4's own record says which claim each null is about:

| | NF-W4 | NF-W7d |
|---|---|---|
| what availability IS | the roster **`played` label** | ⭐ the **all-zero stat-line** event — the atom §11.1 measures at 53.9% |
| how it is CONSUMED | a **FEATURE** injected into the point/quantile champion | a **COMPONENT OF THE PREDICTIVE'S DRAW LAW** |
| what is GATED | Layer A: the availability model's own CRPS · Layer B: the champion's CRPS | the assembled total's **randomized-PIT flatness** + CRPS |
| result | **Layer A SHIPPED** (`lgbm_binary`, +0.0220, 8/8, DSR 0.995) · Layer B GENUINE_ABSENCE ×3 + POWER_LIMITED | *this run* |

- NF-W4 **Layer A** settled that availability is MODELABLE. This story **CONSUMES** that — it
  imports NF-W4's certified learner spec and EB constants rather than re-deriving them — and does
  not re-litigate it.
- NF-W4 **Layer B** is the null, and it says: *a learner already given lagged usage cannot be told
  anything new by an availability COLUMN.* That is a statement about FEATURES.
- **A feature cannot put an atom in a distribution.** Only a mixture can. NF-W7d is gated on a
  statistic NF-W4 never scored.
- ⛔ **A null here does NOT re-decide NF-W4; a ship here does NOT re-open its Layer B.**

⭐ **Why the ACTIVITY indicator and not the roster label**, declared before any score: it is the
event §11.1 actually measures; it is the event that makes the conditional-marginal decomposition
EXACT (all-zero ⟹ every leg's zero mass is at least the atom, so the uniform shift can never remove
positive mass); and it needs no new source, no new feature family and no new provenance gate — it is
read off the same realized stat lines the assembly is already scored against. A QB who dressed, took
two snaps and threw an incompletion is "not active" here, and that is the intended reading: he is
part of the atom the gate is failing on. (Guarded: the source may not read `label`, `status` or
`offense_pct` — NF-W4's own target-leak tokens.)

---

## 2. Binding constraints

- ⛔ **The per-stat marginals are NOT refit or re-selected.** The assembly consumes the NF-W6d
  SERVED MAP through the SERVING DISPATCH (`SDSD.serve_banks`), exactly as NF-W7c did. This story
  adds ONLY the availability mixture over the joint law.
- ⭐⭐ **THE MIXTURE IS MARGINAL-PRESERVING BY CONSTRUCTION, AND THAT IS NOT OPTIONAL.** A naive
  mixture draws the Bernoulli and then draws each leg from its UNCONDITIONAL bank — double-counting
  the zero atom and silently under-stating every stat. Since not-active ⟹ every leg is zero, the
  unconditional law decomposes exactly, `F_i(t) = (1−π) + π·F_i(t | played)`, so the conditional
  bank is the unconditional bank read at a **shifted uniform**, `u ↦ (1−π) + π·u`. The leg marginals
  are then untouched by algebra rather than by hope, and `assemble_mixture_bank` at π ≡ 1 is
  **BYTE-IDENTICAL** to `fp_assembly.assemble_fp_bank` — which is what makes "the availability term
  off" a genuinely MATCHED foil.
- **The exactness condition is CLAMPED and COUNTED.** The identity holds while `1 − π ≤ min_i
  P̂_i(0)`; true at the population level, not guaranteed for an ESTIMATE, so π is raised to the
  marginal-admissible floor and the binding rate is recorded. A clamp that bound everywhere would
  make the mixture its own matched foil — see the activity clause in §6.
- ⛔ **Every gate constant is INHERITED BY REFERENCE** — the PIT bar (0.05), the coverage(80) floor,
  PBO/DSR/FDR, the gate league, the oracle α and materiality fraction. Re-setting a bar a
  predecessor FAILED, inside the story written to clear it, is the E2.1-r inversion in its most
  literal form. Guard-tested by identity, not by value.
- **Frames, folds, PIT gate**: NF-W6d's matrix builder + the NF-W1 8-fold axis (2022H1…2025H2,
  purge 2) + the fail-closed per-week PIT gate, all reused unchanged. NF-W0 constraints are
  inherited through the reused frame builder.
- **Σ and π are always estimated on TRAIN**, never on the slate being scored; the oracle and
  matched-n contexts are the only exceptions and are labelled as such.

### ⭐ The draw seed is DELIBERATELY INHERITED, and that is the opposite of seed shopping

Every fresh registration in this vertical re-seeds. This one does not, because the contest foil
`single_copula` IS NF-W7c's pre-registered primary construction, and the harness proves it by
**reproducing NF-W7c's recorded per-fold scores EXACTLY** (`incumbent_reproduces`, tolerance 1e-9).
A fresh seed would move the common-random-number blocks, make that reproduction approximate, and
force a tolerance knob — a knob chosen after seeing the gap. Nothing can be shopped by keeping it:
the three mixture arms are NEW constructions that did not exist under this seed, so there is no
prior score for them to have been selected against. The availability Bernoulli draws from an
INDEPENDENT stream at a fixed offset so the 13 copula columns stay byte-identical.

---

## 3. The declared field (⛔ never trimmed or grown after a score — MH2 (a) / MH2.2)

**Three real arms, a COHERENT family**: they differ ONLY in how π is estimated, over identical
mixture machinery and an identical active-rows-only Σ. Bundling unrelated mechanisms over-taxes DSR
through the cross-trial dispersion channel (MH2.5 / NF-W6b-C); these three sit close by design.

| arm | π̂ estimator | the hypothesis |
|---|---|---|
| `mix_learned` ⭐ PRIMARY | the NF-W4 certified binary-learner SPEC on the champion feature set | per-row availability is learnable and is what the atom needs |
| `mix_clim` | the player's own EB-shrunk lagged availability | an honest climatology is enough |
| `mix_const` | the position's TRAIN activity rate — per-row **BLIND** | ⭐ the STRUCTURE alone pays; the per-row signal is inert |

⭐ **`mix_const` is registered SHIPPABLE on purpose.** NF-D20's lesson is that a blind arm
registered NON-shippable produces a null resting on a REGISTRATION CHOICE rather than on the
evidence — its blind constant "would have shipped had it been registered shippable". If the per-row
signal is inert and only the structural atom pays, `mix_const` wins, ships, and the record says
exactly that.

**CONTEST FOILS (`beats_foil` binds against these and only these):**

- `single_copula` — **THE INCUMBENT**: NF-W7c's pre-registered primary (`joint_rank`), one Gaussian
  copula with Σ on ALL train rows. Reproduced byte-for-byte.
- `mix_off` — ⭐ **THE MATCHED FOIL**: this story's own active-rows-only Σ in a single copula with
  the availability term OFF. So `mixture − mix_off` isolates **the split**, holding the conditional
  Σ fixed, and `mix_off − single_copula` isolates **the Σ-estimation population**. A two-step
  attribution rather than one bundled claim (NF-D10 / NF-D15 (g′)).

**REFERENCE FOILS (SCORED and REPORTED; they do NOT bind `beats_foil`, declared here with the
reason):** `assembled_indep`, `foil_direct_points`.

⛔ NF-W7c §11.4 is explicit that **`classify_null` names the FOIL, not the hypothesis**: its QB
`GENUINE_ABSENCE` answered *"does assembling from per-stat parts beat modelling the total
directly?"* — an ARCHITECTURE question §11.3 cards as its own successor hypothesis, and not the
question this story asks. Gating NF-W7d on `foil_direct_points` would re-run that architecture
verdict under a mixture badge and would say nothing about availability. Both references are still
scored; `beats_direct_points` is REPORTED on every position; `assembled_indep` carries the three
inherited dependence clauses. They are excluded from the PBO/DSR trial field for the MH2.1 (a)
reason — a diagnostic far from the contest inflates the cross-trial dispersion `V` and over-taxes a
real finding.

**DEGENERATES (registered to LOSE the selection metric):** `nihilist_zero`, `zero_width` (at the
train MEAN — NF-W7c measured a median-located point mass collapsing onto `nihilist_zero` on this
zero-heavy cohort), `max_width`, `assembled_comonotone`.

**ANCHORS:** `permuted_direct`; ⭐ `pi_permuted` (the primary arm's own π shuffled across players
within a global week — same π marginal, the wrong players, aimed directly at the availability
SIGNAL channel, NF-D10); and **per-form** oracle + matched-n controls for every real arm, plus an
own-form oracle for `foil_direct_points` as the ACTIVITY POSITIVE CONTROL. ⛔ `assembled_indep` and
`mix_off` deliberately carry **NO** oracle — an anchor that cannot differ from what it anchors is
décor (NF1.7 (a)). The three-state oracle evaluator (RESPECTED / VIOLATED / INACTIVE) is imported
from NF-W7c unchanged, including its materiality clause: an inversion counts only if it is BOTH
significant at α = 0.05 AND at least one tenth of the arm's own claimed effect.

---

## 4. ⭐⭐ PIT GATES BUT DOES NOT SELECT — the single most important decision here

The card names PIT flatness as the primary metric, and it IS the statistic this story is gated on.
It may **not** be the statistic that RANKS the arms, and the reason is already in NF-W7c's
committed record rather than in anything this run will produce:

> `assembled_comonotone` — the over-correlated **degenerate** — posts the **BEST PIT in the entire
> QB field (0.0563)** while posting the **WORST CRPS (2.6954)**. Perfect dependence is a crude
> availability factor: every leg goes to zero together.

**A criterion a degenerate WINS is fatal** (NF1.8); a CONSTRAINT a degenerate satisfies is fine,
because the metric then eliminates it. So:

- arms are **RANKED on `crps_q199`** among the real arms;
- the **SELECTED** arm must then clear the PIT bar — a hard gate clause, never a ranking key;
- the degenerates are **scored on PIT every run and the table is printed**, which is what PROVES
  the bar was not quietly promoted into a selection criterion (NF-D18's discipline, applied to PIT
  rather than to coverage).

⛔ Reading this as "the story moved its own primary metric" inverts it: the gate statistic is
unchanged and the bar is unchanged; only the RANKING key is named, and it is named precisely to
keep a degenerate from winning it.

**Both pooling conventions are reported; the INHERITED one binds.** NF-W7c's convention is the mean
of per-fold max-decile deviations, and that is what gates. The row-POOLED figure (NF1.8: pool over
ROWS for any per-group statistic) is reported beside it — swapping conventions in the story written
to clear a bar the predecessor failed would be the E2.1-r inversion.

**A calibrated null is REPORTED, and it does not move the bar** (MH2.6). A bootstrap describes a
statistic's spread; only a calibrated null answers *"would a perfectly calibrated model produce a
window this rough?"*. At n ≈ 690 a perfect model posts a median max-decile deviation of ~0.020 and
essentially never exceeds 0.05 — independently re-derived here, and the agreement with §11.1's
figure is itself a cross-check on the instrument.

**§11.2's carded instrumentation gap is CLOSED.** NF-W7c stored only `max_decile_dev`, so *which*
decile was off — the DIRECTION of the miscalibration — was not recoverable without another run. This
story stores the decile COUNTS per label per fold (which pool exactly, at no storage cost) and the
worst decile.

---

## 5. Scope: ONE gated position

**QB gates.** It is the position NF-W7c refused and the only one whose PIT fails. RB/WR/TE are
scored **REPORT-ONLY** — the diagnostic question is *does the mixture HARM a position that already
passed?* — which means the BH family carries exactly one member and the report buys no multiplicity
penalty for itself.

⛔ **A report-only position is never promotable from this record.** A position that would have
passed every clause is a hypothesis for a successor to register FORWARD; re-classifying a result
into shippability after seeing it is the E2.1-r inversion. Stated on the verdict object itself.

---

## 6. Gate (all clauses must pass; declared here, composed in code)

`crps_q199` vs the best CONTEST foil ∧ the calibrated fold-consistency clause (`cv_power`) ∧
PBO < 0.20 over the 5-config eligible field ∧ DSR ≥ 0.95 over the 3-arm declared family (anchors,
degenerates and the two REFERENCE foils never enter `V` — MH2.1 (a) / DSR-CONV) ∧ BH-FDR at q = 0.10
over the single gated hypothesis ∧ the **coverage(80) floor** ∧ ⭐ **randomized-PIT decile flatness
≤ 0.05** ∧ degenerates lose ∧ permutation behaves (BOTH the label permutation and the π permutation)
∧ per-form oracle floors respected at matched n ∧ the three inherited DEPENDENCE clauses
(`independence_under_disperses` / `dependence_moves_coverage` / `beats_indep_on_coverage`) ∧ the
three clauses this story ADDS:

- ⭐ **`mixture_is_active`** — the mean per-row atom the mixture actually installs must exceed 0.01.
  The clamp can in principle return π ≈ 1 on every row, at which point the mixture IS its own
  matched foil and the whole contest is an arm against itself, passing on nothing. *A mechanism that
  cannot act is a FINDING, never a pass* (NF1.9 / NF-D20), so it is MEASURED before it is credited.
- ⭐ **`mixture_preserves_marginals`** — the sup distance (in PROBABILITY units) between the
  mixture's realized leg distributions and the availability-off construction's must be ≤ 0.01,
  derived from the diagnostic's own Monte-Carlo floor (≈2× it) and an order of magnitude below the
  ~26% of mass a double-counted atom would move. The clause is proven non-vacuous by scoring the
  naive double-counting mixture against it, which drifts ~0.17 and is REFUSED.
- ⭐ **`incumbent_reproduces`** — `single_copula` must reproduce NF-W7c's recorded per-fold scores
  to 1e-9. Every comparison in this story is "the mixture against the incumbent"; if the marginals,
  folds, draws or scoring had drifted by any amount, the contest would be measuring the drift and
  would still look perfectly plausible.

⭐ E2.1-r: on these atom-bearing discrete legs, coverage is a **FLOOR** and PIT flatness is the
calibration **TARGET** — never the other way round.

`cv_power.classify_null(declared_field_size=3)` classifies any null, read through
`field_remedy_admissible` (MH2.7) so the instrument REFUSES to prescribe a field smaller than the
pre-registered one; the source of the declared size is recorded on the verdict for a reviewer to
check against this document.

---

## 7. Pre-declared arm-movability (a statistic the arm cannot move is décor)

- **The availability knob provably moves the gate statistic.** The mixture places an explicit,
  per-row point mass at 0; PIT reads the CDF at the realized outcome, and ~54% of QB rows realize
  exactly the atom, so a change in π moves those rows' PIT directly. `mixture_is_active` measures
  that the knob was actually turned.
- **The dependence knob provably moves coverage** (inherited): `sd(Σ wᵢXᵢ) = √((w∘σ)ᵀ Σ (w∘σ))` is
  strictly increasing in every off-diagonal with a positive weight product.
- **The measured half** is the three dependence clauses, carried unchanged from NF-W7c.

---

## 8. What a null would mean

- **Beaten by `mix_off`** ⇒ the SPLIT does not pay; the active-rows-only Σ (if it beats
  `single_copula`) is the part that mattered, and the availability factor is a decomposition
  without a lift. A real, publishable finding, and a much sharper one than "availability is dead".
- **Beaten by `single_copula`** ⇒ neither half pays: the compromise the single copula fits is
  better than either component estimated separately at this n. Registered as possible.
- **PIT-only refusal** ⇒ `CONSTRAINT_REFUSED` with **NO data trigger**. A max-decile deviation
  against a FIXED bar accumulates no sampling error that more folds can remove, so a "+N folds"
  trigger would be the misleading direction NF-D18 forbids. The remedy is a DIFFERENT MECHANISM
  under a FRESH registration (the NF-MARGIN2→3 / NF-W6b-C successor pattern — a tail-dependent or
  atom-aware conditional copula, or a sharper availability probability), or a PM decision.
- **`mixture_is_active` refusal** ⇒ the marginals did not admit an atom; the mechanism could not
  act. A SCOPE finding, and the remedy is a different population, never more seasons.
- **DSR failure** ⇒ read for its MECHANISM (observed SR vs the field's SR0, and which trial arm
  inflates `V`) BEFORE filing POWER_LIMITED. NF-W6b-C: "≈0 more folds" is a misleading trigger when
  the mechanism is field dispersion — and the remedy is a fresh coherent registration, ⛔ never a
  post-hoc trim of this field (MH2.2).
- ⭐ **Whatever the state, read WHICH FOIL it is against** before repeating it (NF-W7c §11.4, the
  sixth hand-correction of this classifier's phrasing in the vertical).

---

## 9. Deploy hold

Nothing here promotes, publishes or retrains. NF-W7c's serving path stays fail-closed on ITS
record; this story writes no serving path of its own, and `PROMOTE_BLOCKERS` are carried onto the
artifact and into the report. NF-W7c's promote blockers are inherited in full.

---

## 10. Power, checked in advance

At 8 folds the calibrated fold clause is attainable and PBO is evaluable over the 5-config eligible
field; the sign floor `2⁻⁸ = 0.0039` sits below the 0.10 BH cutoff; `dsr_ceiling(8) ≈ 0.9999`
against a 0.95 gate. The PIT bar's own power is quantified rather than assumed: at n ≈ 690 per fold
a perfectly calibrated predictive essentially never exceeds 0.05, so the bar is not one this design
could fail by accident — which is what makes NF-W7c's 0.0888 a real defect and not a small-sample
artifact.

---

## 11. Smoke amendments

*(A path-proof smoke — 1 fold, QB only, 300 draws — may be run to prove the code path. Any constant
changed in response to it is recorded HERE, before the decisive run, and never silently.)*

- **None.** The path proof exercised the full field, every anchor and both new clauses without a
  constant change. Two defects were found and fixed BEFORE this file was committed, both by
  deliberate-break RED proofs rather than by a green suite, and both are CODE fixes rather than
  registration changes:
  1. `mixture_marginal_drift` validated its OWN copy of the conditional uniform shift rather than
     the path the assembly scores — so deleting the shift from the assembly (i.e. shipping the
     double-counted-atom defect the clause exists to catch) left the entire suite green. Both now
     route through one `mixture_leg_draws`, and the clause's reference side deliberately runs the
     *other* real path (`mix_off`'s) so a defect cannot cancel on both sides.
  2. The drift metric was expressed in units of each leg's inter-decile RANGE and read 10.0 on a
     construction that is exact by algebra — a mostly-zero integer leg has an inter-decile range of
     0 or 1, so one unit of discretization divides by nothing. The claim under test is "no
     probability mass moved", so the metric is now a Kolmogorov distance in probability units, with
     its tolerance derived from the diagnostic's Monte-Carlo floor.

### 11.1 Smoke OBSERVATIONS — ⛔ no constant, gate, arm or bar changed

*(1 fold — 2025H2 — QB only, 300 draws. **NOT a verdict**: one fold cannot select, and the runner
correctly produced no selection. Recorded here, before the decisive run, because a reader is
entitled to know what was seen at the moment the registration was frozen — and because one of these
observations is a structural finding the decisive run should be read against.)*

- ✅ **The mechanism ACTS and the algebra holds.** Installed atom 0.264; marginal drift 0.0027
  against a 0.01 tolerance; ρ̄ all-rows 0.247 vs active-rows 0.137 — a **1.80× ratio**, reproducing
  §11.1's independently-measured 1.88× at QB on this fold's own train rows.
- ✅ **The oracle ceiling is EVALUATED here, unlike NF-W7c.** Every dependence oracle in NF-W7c went
  INACTIVE (a 13×13 correlation peeked on ~700 test rows could not beat one estimated on ~12,600
  train rows). π is a far lower-dimensional quantity, so its peek ACTS — `oracle__mix_learned`
  2.6458 against its arm's 2.6580. The floor this story is judged under is therefore a real
  ceiling, not an unevaluated one.
- ⭐⭐ **THE STRUCTURAL OBSERVATION, and the one to read the decisive run against: the SUBSTRATE'S
  OWN MARGINALS BOUND HOW MUCH ATOM THE MIXTURE MAY INSTALL, and on this fold that bound BINDS on
  92–97% of rows.** The learned π̂ averaged 0.486 against an observed all-zero rate of 0.51 — i.e.
  the availability model wants an atom the size of the one §11.1 measured — but the
  marginal-admissible floor raised it to 0.736, so only ~0.26 of atom could be installed. Nothing is
  wrong: the clamp is the exactness condition doing exactly its job, and installing the atom the
  model wants would have removed genuine positive mass from the leg with the least zero mass. The
  consequence is worth stating plainly: **each row's per-leg banks already encode a per-row
  availability belief, and this mixture can only price the atom those banks already carry.** If the
  decisive run returns a null, that bound — not the availability model — is the first place to look,
  and the lever it points at is the MARGINAL layer (a W6d cell whose own zero mass is smaller than
  the realized all-zero rate), which is a different story under a fresh registration. ⛔ It is NOT
  a licence to relax the clamp: a mixture that installs more atom than its marginals admit is the
  double-counting defect this registration exists to refuse.
- 📋 Also observed, and deliberately NOT acted on: on this single fold at 300 draws the mixture arms
  beat the matched foil `mix_off` (2.658 vs 2.670) but lose to the incumbent `single_copula`
  (2.643); mixture PIT is 0.0598 against the incumbent's 0.0812 — a real move in the gated
  direction that still does not clear 0.05; and the mixture beats even the over-correlated
  degenerate on PIT (0.0669), which is the mechanism claim showing up exactly where it should. One
  fold is not evidence, `incumbent_reproduces` cannot pass at 300 draws by construction, and ⛔
  nothing here may be tuned in response (E2.1-r).

---

## 12. POST-RUN FINDINGS (added AFTER the decisive run — 2026-08-17)

⛔ **Nothing in this section changes a gate, a threshold, an arm, or a verdict.** The run's result
stands exactly as §§0–11 defined it: **QB NULL — `GENUINE_ABSENCE`**, winner `mix_learned`, best
contest foil `single_copula`, Δ **−0.0031** CRPS (CI95 [−0.0066, +0.0005]), **1/8** folds, PIT
0.0595 against the 0.05 bar. This records what the completed record explains and what it hands the
next story.

### 12.1 ⭐⭐ The null is about the BUNDLE; its two halves point in OPPOSITE directions

The registered arm changes TWO things at once, and the matched foil separates them:

| channel | measured by | QB | RB | WR | TE |
|---|---|---|---|---|---|
| the availability **SPLIT** | `mixture − mix_off` | **+0.0149** | **+0.0161** | **+0.0058** | **+0.0036** |
| the **Σ POPULATION** (active-rows-only) | `mix_off − single_copula` | **−0.0180** | −0.0044 | −0.0042 | −0.0015 |
| net vs the incumbent | | −0.0031 | +0.0117 | +0.0016 | +0.0021 |

⭐ **The split is POSITIVE at all four positions; the Σ population is NEGATIVE at all four.** The
bundle nets negative at QB only because QB's Σ penalty is ~4× any other position's — which is the
§11.1 mechanism reappearing from the other side: QB has by far the largest gap between marginal and
conditional dependence (ρ̄ ratio re-measured here at **1.79–1.85× across all 8 folds**), so
restricting Σ to active rows is where QB loses the most information.

⚠️ **Without `mix_off` in the field this story would have recorded a flat null and been WRONG about
it.** The bundled Δ against the incumbent alone is −0.0031 — indistinguishable from "the mixture is
inert" — when in fact one half is a clean, consistently-signed gain. This is NF-D15 (g′) paying for
itself: a win (or a loss) must be attributed to its claimed channel, not to the bundle.

⛔ **What this does NOT license.** `mixture with the ALL-ROWS Σ` was **not in the declared field**
and is not measured here; the split's +0.0149 is measured *conditional on* Σ_played. Asserting that
combination would win is exactly the post-hoc field construction MH2.2 forbids. It is a
**successor**, registered forward.

⚠️ And the report-only positions are DIAGNOSTIC: RB/WR/TE each beat the incumbent 8/8, but this
record cannot ship them (§5), and at **n = 4 positions** the sign pattern is *consistent and
suggestive*, not a fifth fold (NF-W7c §11.3's own caution, inherited).

### 12.2 The null names the BUNDLE, not the channel — and this time the foil IS the hypothesis

NF-W7c §11.4 warned that `classify_null` names the FOIL. Here the binding foil is
`single_copula` — **the incumbent**, i.e. this story's own comparison — so unlike NF-W7c's QB null
(which was against a direct-points learner and therefore an *architecture* verdict) this
`GENUINE_ABSENCE` is genuinely on-hypothesis. It says: *the availability mixture AS REGISTERED does
not beat the NF-W7c incumbent on average, and no sample size rescues a negative point estimate.*
That is correct and the `retest_trigger: None` is correct.

⛔ It does **not** say "availability separation is inert" — §12.1 measures that channel at +0.0149.
The refinement this run adds to §11.4: a null can name the FOIL correctly and still be read wrongly
if the ARM bundles two mechanisms. Read the attribution before repeating the state.

### 12.3 ⭐ The PIT bar was never approachable — and the DECILE VECTOR says why

- The mixture improved calibration in the gated direction, **like-for-like**: `single_copula`
  0.0646 → `mix_learned` 0.0595. (⚠️ NF-W7c's headline 0.0888 is its *selected* arm `joint_double`;
  comparing against it would overstate the gain. `single_copula` reproduces NF-W7c's `joint_rank`
  to **0.0 across all 8 folds**.)
- **No arm in the field could have cleared 0.05** — the best PIT anywhere is
  `assembled_comonotone` at **0.0563**, and it is a DEGENERATE that loses CRPS by 0.106. ⭐ That is
  the second run in a row in which the over-correlated degenerate wins the PIT table, and it is the
  measured vindication of §4: had PIT been allowed to RANK, this story would have selected a
  construction registered to lose.
- The defect is real, not sampling noise: at n = 685/fold a perfectly calibrated predictive posts a
  median max-decile deviation of 0.0212 and exceeds the bar with probability **0.0003**; the
  observed value's calibrated-null p is **0.00025**. Both pooling conventions agree (per-fold mean
  0.0595, row-pooled 0.0568), so nothing turns on the convention choice.
- ⭐⭐ **§11.2's carded instrumentation gap paid off immediately.** The stored decile vector is
  `[0.136, 0.157, 0.121, 0.110, 0.104, 0.085, 0.066, 0.065, 0.062, 0.093]` — **excess mass in the
  LOW deciles, depletion through the upper-middle**, which is the signature of an **UNDER-PRICED
  ZERO ATOM** (a realized zero draws its randomized PIT from U(0, P̂(0)), so too small a P̂(0)
  compresses that mass toward 0). The ordering across the whole field tracks installed atom exactly
  — low-3 mass 0.469 (`assembled_indep`, no atom) > 0.438 (`mix_off`) > 0.425 (`single_copula`) >
  0.414 (`mix_learned`) > 0.383 (`assembled_comonotone`, the crudest and largest atom). NF-W7c had
  to INFER this from arm ordering; here it is read off the statistic.
  ⚠️ **Direction only.** A pooled simulation of "realized atom 0.516 against installed atom 0.267"
  reproduces the SHAPE but over-states the magnitude (max dev 0.094 vs the observed 0.057), because
  it ignores the per-row heterogeneity of the atom (a starter's bank carries almost none, a
  backup's carries a lot). This is a direction finding, not a quantitative decomposition.

### 12.4 ⭐⭐ Where the answer lives: the MARGINALS bound the mixture, and that is now measured

The §11.1 smoke observation reproduced at full scale and is the most transferable thing here:

- realized all-zero rate **0.516**; learned π̂ mean **0.486** (the availability model wants an atom
  the right size);
- the marginal-admissible floor clamps it, binding on **91.7%** of rows, so the atom actually
  installed is **0.267** — barely half of what the target carries.

⭐ **Each row's per-leg W6d banks already encode a per-row availability belief, and this mixture can
only price the atom those banks already carry.** The mixture is not failing to model availability;
it is being *capped* by the marginals it is contractually forbidden to refit. Combined with §12.3's
decile signature — the residual defect IS under-priced zero mass — the two findings agree on where
the lever is, and it is **not** in the joint layer this story owns.

⛔ **This is not a licence to relax the clamp.** A mixture that installs more atom than its
marginals admit is precisely the double-counting defect this registration exists to refuse, and the
clause that refuses it was proven non-vacuous against a deliberately-built naive mixture.

### 12.5 What the successors are (registered FORWARD, never selected here)

1. ⭐ **The availability split over the ALL-ROWS Σ** — keep the channel that is positive 4/4, drop
   the one that is negative 4/4. Not in this field, not measured, and it must be a FRESH coherent
   registration (MH2.2), scored against this same reproduced incumbent.
2. ⭐ **A MARGINAL-layer story**: a W6d cell whose own zero mass is smaller than the realized
   all-zero rate is what caps every downstream atom. That is a different substrate and a different
   registration — and §12.3/§12.4 now name it with a measured statistic rather than a hunch.
3. **A conditional dependence shape with tail dependence.** A Gaussian copula has none by
   construction; §11.1's original diagnosis survives this run untouched for the *conditional* half.

### 12.6 Anchors and controls, all green — what the null can be trusted against

`incumbent_reproduces` **exact (0.0, 8/8 folds)** · all four degenerates lose (nearest is
`assembled_comonotone` at 2.6954 vs the winner's 2.5924) · the label permutation loses (4.7437) ·
⭐ the **π permutation** loses (2.5970 vs 2.5924), so the per-row availability signal is doing real
work even where the bundle nets negative · all three per-form oracle floors **RESPECTED and
ACTIVE** (unlike NF-W7c, where every dependence oracle went INACTIVE — π is low-dimensional enough
for a peek to act) · the activity positive control peeks 0.8618 · all three inherited dependence
clauses pass · `mixture_is_active` and `mixture_preserves_marginals` both pass on measurement
(atom 0.267, drift 0.00495 against a 0.01 tolerance). ⇒ the null is a measurement, not an artifact
of a harness that could not have seen the effect.
