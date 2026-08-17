# NF-W7f pre-registration — the QB MARGINAL-layer zero-mass recalibration on the 52-cell substrate

**Committed BEFORE any full-run scoring** (the §0.5 discipline). Everything below lives as constants
in `fp_qb_marginal_calibration.py`; the runner `run_nf_w7f_qb_marginal.py` READS them (NF-D16). A
smoke run (1 fold, 300 draws, artifacts suffixed `_smoke`) may be used to prove the code path — no
verdict, and **no constant may change in response to a smoke score after this file is committed**
except as an explicitly recorded SMOKE AMENDMENT (§11).

⚖️ Edge-independent projection product — `best_alpha = 0`, **deploy-held**, NF-G0 challenger.
Research-only: no changelog entry. Every emitted string is a calibrated RANGE, never an edge / ROI /
win-rate claim.

---

## 0. The thesis under test (not assumed)

NF-W7e §12.2 CONFIRMED, by measurement rather than inference, that QB's PIT ceiling is set by the
**MARGINAL** layer:

| measured (NF-W7e, 8 folds, decisive run) | value |
|---|---|
| installed Bernoulli atom under Σ_all / under Σ_played | **0.267125 / 0.267125** (max fold gap **0.0**) |
| what the marginals ADMIT — `mean_i min_j P̂_j(0)` | **0.2687** |
| realized QB all-zero rate | **0.5162** |
| the marginal-admissible clamp's binding share | **91.7%** of QB rows |
| best PIT any real arm posts at QB (three stories of joint-layer knobs) | **0.064** vs a **0.05** bar |

The atom is Σ-invariant to the last digit — Σ never enters `clamp_pi` — so with split on/off ×
Σ_all/Σ_played all measured across NF-W7c/W7d/W7e, plus the comonotone ceiling, **no joint-layer
construction can install mass its marginals forbid.** NF-W7e §12.5 names the only remaining route:
*"the cells that bind it are identifiable from the served map (the leg with the least zero mass on
each row). This is the ONLY route to a calibrated assembled QB distribution."*

**This story takes that route. The thesis:** the QB per-stat cells under-price their own zero mass;
recalibrating that one number per (row, leg) lifts the atom cap above what π̂ asks, un-clamps the
availability split, installs an atom on the realized all-zero rate, and carries the assembled QB
distribution across the PIT bar — while beating BOTH the incumbent and NF-W7e's own arm on
`crps_q199`. A null is a legitimate published outcome; §8 says what each null would mean, and §7's
rule distinguishes "the marginal layer was not the whole ceiling" from "the knob never turned".

### 0.1 Why a marginal can under-price its own zero — and which cell is suspected

The all-zero event has a **COMMON CAUSE**: a player who did not take a snap has every leg at zero.
But the 52 substrate cells are fitted **INDEPENDENTLY** and none of them knows about the others, so a
cell whose form places little mass at exactly zero caps `min_j P̂_j(0)` for the whole row — and the
assembled atom with it.

Read off the COMMITTED records before this run scores anything (NF-W6c serving record `cell_summary`,
NF-W6d Phase-B/C `real_p0` / `pred_p0`):

| QB leg | served form | priced by the gate league | bank's `p_zero` | realized |
|---|---|---|---|---|
| **`passing_yards`** | `nf_w6b` winner | **yes** | **0.3295** ⬅ the suspect | — |
| `attempts` | W6d-C `climatology` | no | 0.5559 | 0.54 |
| `carries` | W6d-C `count_negbin` | no | 0.5344 | 0.5741 |
| `passing_tds` | `nf_w6b` winner | yes | 0.6992 | — |
| `rushing_yards` | `nf_w6b` winner | yes | 0.6602 | — |
| `passing_interceptions` | W6d-B `knn_quantile` | yes | 0.7979 | 0.7916 |
| `fumbles_lost` / `two_pt` / `rushing_tds` | W6d defaults | yes | 0.9267 / 0.9721 / 0.939 | 0.9207 / 0.9679 / 0.9329 |
| `targets` / `receptions` / `receiving_*` | W6d-C `climatology` | mixed | ≥0.9899 | ≥0.9898 |

`QB|passing_yards` is the lowest QB leg by a wide margin, it is a **continuous** leg (a quantile bank
places no atom at exactly zero unless the form models one), and the gate league **prices** it.

⛔ **That is a HYPOTHESIS read off an 89-row serving proof, not a finding.** So the runner MEASURES,
per fold and as a first-class output: each leg's predicted zero mass vs its realized zero rate
(`leg_zero_mass_table`), and **which leg ATTAINS the row-wise minimum** (`binding_leg_share`, before
and after). The record reports what actually bound the cap, not what was expected to. If the binding
cell is not `passing_yards`, that is a finding and the record says so.

---

## 1. Binding constraints

- ⛔ **NO joint-layer knob is opened.** Σ is the incumbent's `FA.position_sigma` on ALL train rows;
  the mixture machinery, the clamp and π̂ are NF-W7d's BY IDENTITY; the draw seed and availability
  stream offset are inherited. NF-W7e closed the joint line and this story does not re-litigate it.
- ⛔ **The per-stat cells are NOT refit or re-selected.** The marginals come through the NF-W6d
  SERVING DISPATCH exactly as NF-W7c/W7d/W7e's did. The ONE thing that varies is a **single number
  per (row, leg): the zero-mass TARGET.** A transform that RESHAPED a marginal would be a refit
  wearing a recalibration's badge, and it is REFUSED by a measured clause (§5).
- ⭐ **THE TRANSFORM IS RAISE-ONLY, and provably monotone** (NF1.7 (d) (4)). Lowering an atom would
  require inventing positive mass the source never expressed; and because the cap is a row-wise MIN,
  only raising can lift it. A target below a leg's own atom is a NO-OP, the share is reported, and
  **the cap can never move backwards.**
- ⭐ **NF-W7e'S OWN ARM IS THE MATCHED FOIL — by identity, guard-tested.** Re-splicing a bank to its
  OWN measured atom is BYTE-IDENTICAL through `FA.draw_legs`, so `mixall_learned − zm_*` is the
  marginal recalibration with the joint construction, the π̂ fit and the draw stream all held fixed.
- ⛔ **Every gate constant is INHERITED BY REFERENCE** — the PIT bar (0.05), the coverage(80) floor,
  PBO/DSR/FDR, the gate league, the oracle α and materiality fraction, the mixture-activity floor and
  the marginal-drift tolerance. Guard-tested by identity, not by value.
- **Frames, folds, PIT gate**: NF-W6d's matrix builder + the NF-W1 8-fold axis (2022H1…2025H2, purge
  2) + the fail-closed per-week PIT gate, all reused unchanged.
- **Every estimate is on TRAIN**, never on the slate being scored; the oracle and matched-n contexts
  are the only exceptions and are labelled as such.
- **The per-fold marginal banks are read from NF-W7e's OWN cache directory**
  (`artifacts/nf_w7e_bank_cache/`, gitignored) with NF-W7e's key function by identity — the banks are
  literally the same object, and this story transforms them rather than refitting them.

### 1.1 What the oracle peeks at, and why only that

The per-form oracle peeks at **exactly what this story ESTIMATES** — π̂ and the two TRAIN realized
zero rates — used consistently in both the marginal target and the mixture, **and at nothing else.**
Σ stays on TRAIN in every context. Two reasons, both pre-registered: peeking Σ would move a factor
the family holds fixed (so the "floor" would bound a different arm — NF1.7 (b)); and NF-W7e MEASURED
that a Σ peeked on a ~700-row test block LOSES more to sample size than the peek gains, which is how
a per-form floor goes INACTIVE rather than binding (NF-W6d lost three cells to exactly that).

---

## 2. Scope: **QB ONLY**, gated and shippable

The card gates QB and names an RB certificate as a **separate** prerequisite for NF-W8's
four-position optimizer input. NF-W7e already certified WR; RB and TE returned `GENUINE_ABSENCE`
against NF-W7d's own arm there.

⛔ **RB/WR/TE are NOT scored here and NOT reported.** A position this story does not run may not be
read as evidence in either direction (NF1.7 (a)), and a report-only result may never be
re-classified into shippability (E2.1-r). **The BH family therefore carries ONE member** — that is the
declared scope, not a multiplicity dodge, and it is stated on the verdict (`bh_family_size`) so a
reader prices it.

---

## 3. The declared field (⛔ never trimmed or grown after a score — MH2 (a) / MH2.2)

**Four real arms, a COHERENT family**: they differ ONLY in the per-leg zero-mass TARGET they name,
over an IDENTICAL joint construction (`mixall_learned` = the learned π̂ + the incumbent's all-rows Σ),
identical marginals-before-recalibration, identical mixture machinery and identical draw stream.
`q̂ = 1 − π̂` is the estimated inactivity probability; `p̂₊` is the TRAIN realized `P(leg = 0 | active)`.

| arm | zero-mass target `t` | row-varying? |
|---|---|---|
| `zm_conditional` ⭐ PRIMARY | `q̂ + (1 − q̂)·p̂₊` — the two-part reconstruction | yes |
| `zm_floor` | `max(P̂(0), q̂)` — the minimal intervention: lift only the deficient legs | yes |
| `zm_climatology` | the leg's TRAIN realized zero rate — row-BLIND (shippable per NF-D20) | no |
| `zm_over` | `q̂′ + (1 − q̂′)·p̂₊` with `q̂′ = min(1, 1.5·q̂)` — the MAGNITUDE probe | yes |

⭐ **`zm_over` is a REAL, SHIPPABLE arm, not an anchor** (NF-D20 / NF-W7b): an over-correction
registered to lose that then BEATS the field produces a null while the answer sits in an ineligible
cell. It is **expected to lose** — the primary's predicted installed atom (≈0.514, from NF-W7e's
recorded π̂ mean 0.4857) already lands on the realized rate (0.5162) — and if it wins, the magnitude
hypothesis is REFUTED and the record says so rather than re-labelling it.

**CONTEST FOILS (`beats_foil` binds against these and only these):**

- `mixall_learned` — **NF-W7e's registered QB arm**, reproduced to 1e-9, and ⭐ **THE MATCHED FOIL**:
  the identical joint construction and π̂ fit on the SERVED marginals. It is also the **CRPS-best QB
  construction on record** (NF-W7e beat both its foils 8/8 at QB, DSR 0.9999, refused on the PIT bar
  alone), so the arm must beat the best thing that EXISTS, not merely the thing that shipped.
- `single_copula` — **THE INCUMBENT** (NF-W7c's `joint_rank`), reproduced to 1e-9. Keeping it binding
  makes this story's margin comparable to NF-W7c/W7d/W7e's on the same folds and the same seed.

**REFERENCE FOILS (SCORED and REPORTED; they do NOT bind `beats_foil`; excluded from the PBO/DSR
trial field per MH2.1 (a)):** `zm_cond_copula` (the PRIMARY arm's recalibrated marginals under the
INCUMBENT's copula — the availability split OFF; it answers a question the gated cell cannot: does
raising the marginal atom pay when nothing makes that atom COMMON across legs?), `assembled_indep`
(the three inherited dependence clauses), `foil_direct_points` (the ARCHITECTURE question, NF-W7c
§11.4 — never this story's gate).

**The 2×2 the field completes**, every cell on common random numbers:

| | marginals RECALIBRATED | marginals SERVED |
|---|---|---|
| **availability split ON** | `zm_*` (THIS STORY) | `mixall_learned` (NF-W7e — the matched foil) |
| **split OFF** | `zm_cond_copula` (reference) | `single_copula` (NF-W7c — the incumbent) |

**DEGENERATES (registered to LOSE the selection metric):** `nihilist_zero`, `zero_width`,
`max_width`, `assembled_comonotone` — inherited from NF-W7c/W7d/W7e, and all four scored on **PIT
every run** (§4).

**ANCHORS:** `permuted_direct`; `zm_permuted` (the PRIMARY arm's per-row `q̂` shuffled across players
within a global week, used consistently in the marginal target AND the mixture — it preserves the
population LEVEL of the atom and destroys only its per-ROW assignment, so it separates "the
recalibration found the right rows" from "it raised the average"; NF-D15 (g′)); per-form oracle +
matched-n controls for every real arm; an own-form oracle for `foil_direct_points` as the ACTIVITY
positive control. ⛔ `mixall_learned`, `single_copula` and `assembled_indep` carry NO oracle — an
anchor that cannot differ from what it anchors is décor (NF1.7 (a)). The three-state oracle evaluator
(RESPECTED / VIOLATED / **INACTIVE**) is NF-W7c's, imported, with its materiality clause — a per-form
floor that TIES its matched control is INACTIVE, never a refusal (NF-W6d lost three cells to that).

**Eligible set for PBO**: the 4 arms + 2 contest foils (6 configs). **DSR** deflates over the 4-arm
declared family; anchors, degenerates and the three reference foils never enter `V`.

---

## 4. PIT gates but does NOT select (NF-W7d §4 / NF-W7e §4, inherited verbatim)

Arms are RANKED on `crps_q199`; the SELECTED arm must clear the PIT bar (0.05, per-fold mean of
max-decile deviations — NF-W7c's convention, the row-pooled figure reported beside it); **the
degenerates are scored on PIT every run and the table is printed.** `assembled_comonotone` has posted
the best PIT in the QB field for THREE runs running while losing CRPS by ~0.11 — a criterion a
degenerate wins is fatal (NF1.8). The decile VECTOR is stored per label per fold. The calibrated null
(MH2.6) is reported and does not move the bar.

---

## 5. Gate (all clauses must pass; composed in code)

`crps_q199` vs the best CONTEST foil ∧ the calibrated fold-consistency clause (`cv_power`) ∧
PBO < 0.20 over the 6-config eligible field ∧ DSR ≥ 0.95 over the 4-arm declared family ∧ BH-FDR at
q = 0.10 over the ONE gated hypothesis ∧ the coverage(80) floor ∧ randomized-PIT decile flatness
≤ 0.05 ∧ degenerates lose ∧ permutations behave (the label permutation AND the zero-mass
permutation) ∧ per-form oracle floors respected at matched n ∧ the three inherited DEPENDENCE clauses
∧ NF-W7d's two mechanism clauses (`mixture_is_active` ≥ 0.01 installed atom;
`mixture_preserves_marginals` ≤ 0.01 sup drift) ∧ `incumbent_reproduces` (`single_copula` vs NF-W7c,
1e-9) ∧ `predecessor_reproduces` (`mixall_learned` vs NF-W7e, 1e-9) ∧ **the five clauses this story
ADDS**:

- ⭐ **`zero_mass_hits_target`** — the recalibrated bank, RE-READ through `MX.leg_zero_mass` (the very
  function `pi_floor` and the atom cap are built from), carries exactly the atom the raise-only rule
  asked for. Catches a wrong `p̂`, an off-by-one on the grid, or an inverted direction shipping a cap
  the mixture then silently clamps against.
- ⭐ **`positive_law_preserved`** — the conditional-on-positive law moved by no more than the
  RESOLUTION a raised atom necessarily costs. A **counting Kolmogorov distance** (probability units,
  the same units `mixture_marginal_drift` reports) against a **derived** bound `2 × 0.005/(1 − t)` —
  one grid step at each end, because installing an atom of `t` leaves only `(1 − t)·199` knots for
  the positive part. Raw drift, bound and ratio are all reported so a reader can re-derive under
  another rule (NF-D14). ⛔ It stays FALSIFIABLE: a splice that RESHAPED a marginal instead of
  re-weighting its atom is refused (RED-proved against four distinct reshapes and a refit).
  Cells whose conditional law is DEGENERATE (< 10 positive knots) are UNEVALUABLE and reported as
  such — never a pass (NF1.7 (a)).
- ⭐ **`matched_foil_identity`** — re-splicing to a bank's OWN atom is BYTE-IDENTICAL through
  `FA.draw_legs`. This is what earns the claim that `mixall_learned − zm_*` is the recalibration and
  nothing else; without it the contrast would be measuring the transform's own arithmetic.
- ⭐ **`cap_was_lifted`** — the MECHANISM-ACTIVITY floor (NF1.9 / NF1.7 (a) / NF-D20). The measured
  atom cap must exceed NF-W7e's RECORDED 0.2687 by ≥ **0.012**. Derived from design quantities known
  before this run: the bar is a 0.05 max-decile deviation and NF-W7e recorded the QB first decile at
  0.162, so ≥ `0.162 − 0.150 = 0.012` of mass must move out of the bottom decile for ANY arm to clear
  it. The baseline is READ from the committed predecessor record at run time and is **UNEVALUABLE —
  never a pass — if that record is absent or a path proof** (the NF1.9-R lesson: never trust a name
  for a measurement).
- ⭐ **`per_leg_calibration_not_degraded`** — recalibrating a marginal CHANGES a NF-W6d certified
  cell, so the story must show it did not buy the assembled atom by wrecking the parts. The summed
  `crps_q199` of the PRICED QB legs, served vs recalibrated, must not degrade (tolerance 0.0, as a
  fraction). **Two-sided by design**: if the diagnosis is right the legs IMPROVE; if it is wrong, this
  is where it shows.

`cv_power.classify_null(declared_field_size=4)` classifies any null, read through
`field_remedy_admissible` (MH2.7); the source of the declared size is recorded on the verdict. A
PIT-only or anchor-only refusal is `CONSTRAINT_REFUSED` with NO data trigger (NF-D18). ⭐ **And the
mechanism-inactivity read comes FIRST**: if `cap_was_lifted` fails, the state is `UNDEFINED` with the
reason "the knob did not turn" — a HARNESS reading, never a finding about QB.

---

## 6. Pre-declared arm-movability (the mechanism provably moves the gate statistic)

- **The recalibration provably moves the atom cap**: the cap is `mean_i min_j P̂_j(0)`, the transform
  is raise-only, and `zero_mass_hits_target` measures that the requested atom was installed. On
  synthetic banks carrying the measured defect (an atom-free continuous leg) the cap moves
  0.0 → 0.465 and the clamp's binding share 1.00 → 0.00.
- **Quantitatively, in advance**: NF-W7e recorded π̂ mean **0.4857** and a clamp that dragged it to
  **0.7359**, installing **0.2641** of atom instead of **0.5143**. If the recalibration lifts the cap
  above `1 − π̂` on most rows, the installed atom moves **0.267 → ≈0.514** against a realized
  **0.5162**. That is the pre-declared prediction; the run measures it.
- **What the recalibration CANNOT move** — declared so a reader knows in advance: it cannot change Σ,
  the availability estimator, or the conditional-on-positive law of any leg (that last is a gate
  clause, not a hope). If PIT still fails with the cap lifted, the residual is a SHAPE or resolution
  question and §7 says so.

---

## 7. ⭐ The MARGINAL-CAP rule (fixed in advance; read by `QM.marginal_cap_verdict`)

Inputs: the per-arm QB PIT of the four real arms; the measured atom cap and NF-W7e's recorded
baseline; the installed atom and the realized all-zero rate; the clamp's residual binding share; and
the binding-leg shares before and after.

| state | rule | reading |
|---|---|---|
| **`QB_CLEARS_AT_THE_MARGINAL_LAYER`** | cap lifted ≥ 0.012 AND some real arm's QB PIT ≤ 0.05 | the MARGINAL layer WAS QB's binding constraint; NF-W7e's confirmation is vindicated and a calibrated assembled QB distribution exists (deploy-held) |
| **`QB_STILL_BLOCKED_WITH_THE_CAP_LIFTED`** | cap lifted AND no arm clears | the atom cap was REAL but not the whole ceiling; the residual is a SHAPE or resolution question, **not** a zero-mass one, and no fold count moves a fixed bar (NF-D18) |
| **`CAP_NOT_LIFTED`** | the cap did not move by ≥ 0.012 | every arm is its own matched foil and the contest passed on nothing: **the thesis is UNTESTED, not refuted** (NF1.7 (a) / NF-D20). A HARNESS reading, never a finding about QB — and it holds regardless of what the PIT happens to say |
| **`UNDEFINED`** | QB not scored, or the cap unmeasurable | never read as any of the above |

---

## 8. What a null would mean

- **`QB_STILL_BLOCKED_WITH_THE_CAP_LIFTED`** ⇒ the sharpest possible null: the atom cap was real,
  measured, and spent — and QB's remaining PIT excess is NOT a zero-mass question. NF-W7e's "the QB
  roadmap moves to the 52-cell substrate" would then be **half** the answer, and the successor is a
  SHAPE story (the conditional-on-playing law's tail dependence, or the availability probability's
  resolution), registered forward. ⛔ No data trigger.
- **Beaten by `mixall_learned`** ⇒ the recalibration does not pay on the metric even though it lifts
  the cap: raising the marginal atom costs more in conditional sharpness than the common atom buys.
  The 2×2's `zm_cond_copula` cell is what distinguishes "the atom is wrong" from "making it COMMON is
  wrong".
- **Beaten by `single_copula` but not `mixall_learned`** ⇒ read WHICH foil binds before repeating any
  claim (NF-W7c §11.4 / NF-W7d §12.2 / NF-W7c's `beats_foil` names the foil, not the hypothesis).
- **`zm_over` winning** ⇒ the MAGNITUDE hypothesis is refuted, not a metric inversion (the
  degenerates lose by a mile): the two-part reconstruction UNDER-corrects and the metric keeps
  improving past the registered interval. Left FAILING and DECOMPOSED, never re-labelled (NF-D20).
- **`zm_climatology` (blind) winning** ⇒ a finding about the SIGNAL: the per-row availability estimate
  adds nothing over a per-leg population rate. It is registered SHIPPABLE, so this ships rather than
  producing a null in an ineligible cell (NF-D20).
- **DSR failure** ⇒ read for its MECHANISM before filing POWER_LIMITED (MH2.5 / NF-W6b-C): check
  whether `zm_over` (a deliberately-inflated arm) is inflating the cross-trial Sharpe dispersion `V`.
  ⛔ The remedy is a FRESH registration with a coherent narrower family, **never** a post-hoc trim
  (MH2.2); the declared field of 4 admits no trim.
- **`per_leg_calibration_not_degraded` failure** ⇒ the recalibration bought the assembled atom by
  damaging the parts. That is a refusal, and it also refutes the premise: a leg that under-prices its
  own zero should IMPROVE when the zero is priced.
- ⭐ Whatever the state, read WHICH FOIL it is against and which 2×2 cell it names before repeating
  it.

---

## 9. Deploy hold

Nothing here promotes, publishes, serves or retrains. NF-W7c's serving path stays fail-closed on ITS
record; this story writes no serving path of its own and does NOT re-serve the NF-W6d substrate — a
consumer reading the 52 cells is reading the SERVED cells, not these. `PROMOTE_BLOCKERS` are carried
onto the artifact and into the report; NF-W7c's are inherited in full. ⛔ Even a SHIP here does not
license a cross-position ranking: NF-W7c §4 / NF-W7e's scope rule binds until every compared position
is on the same generator and the same level recalibration.

---

## 10. Power, checked in advance

At 8 folds the calibrated fold clause is attainable and PBO is evaluable over the 6-config eligible
field; the sign floor `2⁻⁸ = 0.0039` sits below the 0.10 BH cutoff at family size 1;
`dsr_ceiling(8) ≈ 0.9999` against a 0.95 gate. NF-W7e measured `mixall_learned` beating BOTH its
foils at QB by +0.0064 / +0.0095 with 8/8 folds and DSR 0.9999 — so an effect of that scale is
comfortably inside the design's power, and this story's arm starts from that construction. **The PIT
bar is the binding uncertainty, by design**: it is a CONSTRAINT, §7 is the rule for reading it, and
`cap_was_lifted` is what prevents a run in which the knob never turned from being read as either
verdict.

---

## 11. Smoke amendments

*(A path-proof smoke — 1 fold, 300 draws — may be run to prove the code path. Any constant changed in
response to it is recorded HERE, before the decisive run, and never silently.)*

- **None yet.** The smoke is an OPERATOR run (the >2-minute rule: the NF-W6d marginal dispatch is
  ~370–570 s per fold on a cold cache).

### 11.1 In-session PATH PROOF — synthetic frames, no lake, no dispatch

⛔ **NOT a verdict and not a score**: it exercises the code path on SYNTHETIC banks and frames, so
nothing here is evidence about QB. Recorded because it is what found the transform's four defects.

- The full `run_position` path runs end-to-end (every arm, foil, anchor, all three identities,
  the clamp, the drift diagnostic, the per-leg table and the premise diagnostic) in **13.7 s** on
  900 train / 220 test synthetic QB rows at 300 draws.
- On banks carrying the MEASURED defect (an atom-free continuous `passing_yards`, every other leg an
  unconditional climatology): the binding leg is `passing_yards` on **100%** of rows, the served cap
  is **0.0**, the clamp binds on **1.00** of rows and the mixture installs **0.0** atom. After
  recalibration the cap is **0.4648**, the installed atom **0.4648** against a realized **0.5045**,
  and the assembled PIT moves **0.4364** (`mixall_learned`) → **0.0545** (`zm_conditional`). The
  priced legs' summed CRPS **improves** 103.52 → 75.93, driven by `passing_yards` (98.67 → 70.96).
  ⛔ Synthetic; direction only, magnitude is not evidence.
- ⭐ **FOUR defects were found by the identities going RED, and every fix was to the CONSTRUCTION,
  never to a tolerance (E2.1-r):** (1) zeroing a leg's sub-threshold knots changed an integer leg's
  interpolation ramp and flipped draws 1 → 0 (max draw gap **1.0** on 7 of 13 legs); (2) a target off
  the bank's 199-level grid misaligned the conditional levels (relative deviation **1.04** at the
  first conditional percentile); (3) a target was allowed to LOWER an atom, which the raise-only
  identity caught as a **0.43** gap; (4) the conditional law was measured by INVERTING a staircase,
  which is ill-posed on a count leg and reported a **0.835** tie artifact. The clauses now read
  exact (0.0 / 0.0) and the positive-law ratio sits at **0.47** against a bar of 1.0.
- **RED proof of the guards**: 11 deliberate defects in the source (raise-only clamp removed, grid
  snapping removed, sub-threshold knots zeroed, the exact identity map removed, the positive-law
  clause forced to pass, the cap-lift made to fall through on `nan`, `MIN_CAP_LIFT` zeroed, the
  magnitude probe demoted to an anchor, the scope widened past QB, the PIT bar re-typed instead of
  inherited, the blind arm made row-aware) — **all 11 go RED**, each mutation asserted to be
  uniquely-anchored, to land on disk, and to remove the token it targets (#682 / #815 / #885).
- The positive-law clause is RED-proved against **four distinct reshapes and a refit** (ratios
  8.9–28.5 against a bar of 1.0) and reports NOT-EVALUATED on an all-degenerate comparison.

---

## 12. POST-RUN FINDINGS

*(To be added AFTER the decisive run, by the session that reads it. ⛔ Nothing in that section may
change a gate, a threshold, an arm or a verdict.)*
