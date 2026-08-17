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

- **NO CONSTANT, GATE, ARM, BAR OR TOLERANCE CHANGED.** One HARNESS FIX is recorded in §11.3 below;
  it changes which arm two clauses READ, never what they require.

### 11.2 Smoke OBSERVATIONS — operator run, 2026-08-17, 1 fold (2025H2), 300 draws, 409 s

*(⛔ **NOT a verdict.** One fold cannot select: `select_position` requires ≥2, so the runner correctly
produced no selection and the marginal-cap layer correctly returned `UNDEFINED` — that is the harness
refusing to read a verdict from one fold, NOT the `CAP_NOT_LIFTED` state. Magnitudes at 300 draws are
not evidence. Recorded so a reader knows what was seen when the registration was frozen.)*

- ✅ **All three transform identities hold on REAL banks**: `zero_mass_hits_target` max gap **0.0**;
  `matched_foil_no_op` max draw gap **0.0** on 701 QB rows; `positive_law` ratio **0.864** against a
  bar of 1.0 (raw drift 0.090 against a resolution bound 0.182, 45.1% of cells evaluable).
- ✅ **The mechanism ACTS, and the §6 pre-declared prediction landed to three decimals.** §6
  predicted the installed atom would move "0.267 → ≈0.514 against a realized 0.5162". Measured:
  atom cap **0.2658 → 0.5431**, installed atom **0.2641 → 0.5142** against a realized **0.5093**,
  clamp binding share **0.9215 → 0.0728**, π̂ 0.4857 dragged to 0.7359 by the clamp → used at 0.4858
  (essentially unclamped). Marginal drift 0.0012 vs the 0.01 tolerance.
- ✅ **THE PREMISE IS CONFIRMED ON REAL DATA, and refined.** `QB|passing_yards` under-prices its own
  zero by **+0.2581** (predicted 0.2983 vs realized 0.5563) and binds the row-wise minimum on
  **72.2%** of rows — the hypothesised cell, and its gap is essentially the whole cap shortfall
  (0.5093 − 0.2658 = 0.2435). Every other leg sits within ±0.05. ⭐ NOT predicted: `QB|attempts` is a
  SECOND binding cell (25.1% of rows served, and the dominant one at 57.9% AFTER recalibration,
  because raise-only cannot lower its slightly-over-priced 0.5500 vs 0.5378).
- 📋 **The PIT direction, on one fold at 300 draws** (⛔ not evidence): `zm_conditional` **0.0312** ·
  `zm_floor` 0.0341 · `zm_climatology` 0.0569 · `zm_over` 0.0826, against `mixall_learned` **0.0854**
  and `single_copula` 0.0812. The under-priced-atom signature is gone from the first decile
  (0.185 → 0.117). `assembled_comonotone` posts 0.0669 and loses CRPS by 0.07 — §4's discipline again.
- ⚠️⚠️ **THE OBSERVATION THE DECISIVE RUN MUST BE READ AGAINST: every one of the four arms FAILS
  `per_leg_calibration_not_degraded` on this fold.** Summed PRICED-leg CRPS vs served:
  `zm_floor` **+0.60%** · `zm_conditional` **+1.35%** · `zm_over` **+5.21%** · `zm_climatology`
  **+48.56%**. The damage is almost entirely `QB|passing_yards`, and the availability decomposition
  says the effect's SIGN FLIPS with π̂ — mean Δ by π̂ quartile (positive = improved) for
  `zm_conditional`: **+0.58 · −0.30 · −1.95 · −0.19**. Reading: raising a leg's atom helps where
  availability is confidently LOW and hurts where the player probably PLAYED, because
  `QB|passing_yards` is an LGBM on the champion feature set and already encodes availability
  partially — so adding `q̂` on top **double-prices availability in the MARGINAL** (NF-W7e §12.2's
  "the joint layer prices availability twice", one layer down).
- ⛔ **THE BAR IS NOT MOVED.** §5 registered a tolerance of 0.0 AND the reading *"if the diagnosis is
  right the legs IMPROVE; if it is wrong, this is where it shows."* The legs do not improve.
  Re-reading either the tolerance or that sentence now would be the E2.1-r inversion in its most
  literal form. On this evidence the LIKELY decisive outcome is `CONSTRAINT_REFUSED` on
  `per_leg_calibration_not_degraded`, with `QB_STILL_BLOCKED_WITH_THE_CAP_LIFTED` — and §8 already
  says what that means. What the decisive run buys is the 8-fold measurement, the reproduction
  controls at 4,000 draws, and an ATTRIBUTED residual: the cap IS the blocker and lifting it DOES fix
  the assembled calibration, but no registered target installs the atom without damaging the parts on
  high-availability rows. That names where a successor must aim (a target conditioned on availability
  CONFIDENCE, not on `q̂` alone) rather than closing a door.
- ⚠️ `incumbent_reproduces` / `predecessor_reproduces` cannot pass at 300 draws by construction (as
  in NF-W7d's and NF-W7e's smokes); both are checked at 4,000 draws in the decisive run.

### 11.3 Recorded HARNESS FIX (⛔ not a constant, gate, arm, bar or tolerance change)

The smoke exposed a real defect in the RUNNER, not in the registration: the per-leg table and the two
TARGET-DEPENDENT identities (`zero_mass_hits_target`, `positive_law`) were computed for the PRIMARY
arm only, while the gate reads them for the **WINNER**. With the four arms moving the per-leg CRPS by
+0.60% to +48.56%, which arm the clause reads is decisive — a clause describing something other than
what it anchors is the NF1.7 (a) defect. Fixed: both are now computed **per real arm** and the
selection reads the winner's (`per_leg_detail.arm_read` / `transform_detail.identity_arm_read` are
carried on the record so the attribution is auditable). The target-independent no-op identity is still
measured once. Two guards now RED-prove the attribution in both directions, and the availability
decomposition is carried as a REPORTED field (never gated) so a refusal can name WHERE the per-leg
effect lands. ⛔ No clause's requirement changed; no threshold moved.

### 11.4 In-session PATH PROOF — synthetic frames, no lake, no dispatch

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

### 11.5 PM-mandated captures for the decisive run (2026-08-17, POST-smoke, **REPORTED-ONLY**)

The PM decided **A — run the decisive 8-fold**, recorded the story as a *measured, attributed null*
rather than unresolved-by-choice, and asked for five things captured in the SAME run (it is one shot
at this cost). ⛔ **Every one is a REPORT computed from the arms already declared in §3.** Nothing
below adds an arm, a foil, a clause or a threshold: a new arm would change the field PBO and DSR
deflate over (MH2 (a) / MH2.2) and a new clause would change what `ship` means, so the additions are
confined to what the record PRINTS. `test_none_of_the_new_captures_reached_the_gate` pins that: the
gate's key set must remain a subset of the §5 checks, and the field sizes are pinned as counts.

| # | capture | where it lands | how it is computed |
|---|---|---|---|
| 1 | component-error decomposition **by availability**, with the crossover located | `availability_decomposition` (per arm, per priced leg) | `QM.bucket_by_availability` + `QM.pool_availability_buckets` |
| 2 | per-stat **cap contributions** across every QB leg, before *and* after | `premise_detail.leg_zero_mass_table[_recalibrated]_last_fold` + pooled `binding_leg_share_*` | `QM.leg_zero_mass_table` on served and re-spliced banks |
| 3 | assembled **PIT + CRPS every fold** vs the reproduced incumbent | `per_fold_series` | the per-fold `scores` / `pit_flatness` already recorded |
| 4 | a **matched foil per channel**, as a paired delta | `channel_attribution` | `mat[foil] − mat[winner]` per fold + CI95 + one-sided p |
| 5 | **degenerates + oracle scored every fold** | `per_fold_series.crps` / `.pit_max_decile_dev` | ditto |

Two defects were found while wiring them, both of which would have made a capture unusable:

- ⭐ **capture 1 was NOT poolable across folds.** The smoke's decomposition bucketed by π̂
  **quartiles computed per fold**, so "bucket k" described a different population on every fold and
  an 8-fold pool would have measured the movement of the edges as much as the effect — and the PM's
  premise is explicitly an 8-fold claim. It also pooled a mean-of-means, which re-weights a thin
  fold equal to a fat one (**NF1.8**: pool over ROWS). Now: **fixed absolute** π̂ edges
  (`PI_BUCKET_EDGES`, 10 bins), each fold contributing raw **sums and counts** so the pool is exactly
  `Σsums/Σcounts`; a bucket below `MIN_BUCKET_ROWS = 30` reports `None` and can never supply a
  crossover (**NF1.7 (a)**); fewer than two signed buckets is `UNDEFINED`, ⛔ never "no crossover".
  A fold whose bucketing disagrees **raises** rather than being averaged in.
- **the sign walk treated an exact-zero bucket as a wall**, so a textbook single crossing landing on
  a bucket centre reported `NON_MONOTONE`/`MIXED`. Zero-valued buckets are dropped from the sign
  walk (still reported), which makes such a crossover locatable. Caught by its own guard.

**One genuine classifier defect, fixed (no bar moved).** `per_leg_calibration_not_degraded` is an
`ANCHOR_CHECK`, so the *expected* shape (all statistical gates green, that clause red) already routed
to `CONSTRAINT_REFUSED` with `retest_trigger: None` — the PM's requirement, satisfied by
construction. But a **MIXED** failure (a statistical gate red *and* an anchor red) fell through to
`cv_power.classify_null`, which could publish a "+N folds" trigger while a non-rescuable anchor
refusal was still standing — exactly the misleading direction **NF-D18** names. A mixed failure now
classifies `CONSTRAINT_REFUSED` with `binding_half: "anchor"` (the anchor half binds: more folds
could clear the statistical half and the ship would *still* be refused), `retest_trigger: None`, the
statistical shortfall **reported** in `failing_statistical_checks` rather than hidden, and the
instrument's own reading kept verbatim in `instrument_verdict` for audit.

⛔ **The failed clause stays a hard gate at tolerance 0.0** (E2.1-r). Whether "components must not
degrade" should be a gate or a diagnostic is the **successor's** forward registration to decide, not
this story's to re-read; the PM's lean is recorded there (keep it a hard gate unless the specific
degraded component is shown not to be independently served/consumed).

**Guards:** section 8 of `betting_ml/tests/test_nf_w7f_qb_marginal.py` — 9 new tests, 65 total,
each with an isolating fixture (NF-D17) and each RED-proved against a deliberately broken source
(12 further breaks, all 12 RED; every mutation asserted uniquely-anchored, landed, and — for a
replacement — token-removed, with an insertion instead asserted to APPEAR: #682 / #815 / #885).

⭐ **The RED proof found one real coverage hole and three defects in its own breaks** — worth recording
because every one is the "a RED proof lies" family and none was visible from a green suite:
- **the hole:** `test_the_recalibrated_leg_table_*` read the key out of the TEST FIXTURE, which
  supplies it — so deleting the emission from `run_position` left the test GREEN. `run_position`
  needs the lake, so the emission is now pinned by SOURCE inspection with comment lines stripped
  (INC-38, so prose cannot satisfy it).
- **a break that wrote without moving the asserted predicate** (#815): dividing sums AND counts by
  the fold count leaves `Σsums/Σcounts` unchanged, so the "mean of fold means" break was a no-op. A
  real mean-of-means break was needed.
- **a break aimed at a clause that cannot fire:** the zero-bucket handling has ONE live mechanism
  (the `ev_signed` filter); the zero tests inside the `continue` are unreachable once zeros are
  filtered, so patching them was inert. The pre-fix behaviour needs BOTH lines reverted as a block.
- **the harness itself hung** on an unbounded "walk up to `pyproject.toml`" from a scratchpad path
  (`Path("/").parent` is `/`): 100% CPU, no children, no output — indistinguishable from a hanging
  test, and it meant the first two runs proved NOTHING. A per-break `timeout` that reports `HUNG`
  (⛔ never counted as RED) and a bounded root lookup are now part of the harness.

---

## 12. POST-RUN FINDINGS

*Decisive run 2026-08-17, 8 folds × 4,000 draws, 3,365.9 s. ⛔ Nothing here changed a gate, a
threshold, an arm or a verdict; the only post-run code change is a REPORTED field (§12.7).*

**VERDICT: `NULL` / `CONSTRAINT_REFUSED` · `marginal_cap = QB_CLEARS_AT_THE_MARGINAL_LAYER` ·
`retest_trigger = None` · `binding_half = anchor`.** Refused by exactly two clauses:
`per_leg_calibration_not_degraded` (anchor) and `dsr_ok` (statistical). The other **15** anchors pass,
all four per-form oracle floors are `RESPECTED`, and reproduction is **exact** — max abs gap `0.0` on
8/8 folds for both the incumbent (`single_copula`) and NF-W7e's arm (`mixall_learned`), so every
comparison below is on identical common random numbers.

### 12.1 The thesis is VINDICATED — the marginal layer was QB's binding constraint

| quantity | NF-W7e (served) | NF-W7f (winner `zm_floor`) |
|---|---|---|
| marginal-admissible atom cap | 0.2687 | **0.5481** (lift **+0.2794**, floor 0.012) |
| installed Bernoulli atom | 0.2776 | **0.5176** vs realized **0.5162** |
| clamp mean upward move on π̂ | 0.25271 | **0.00225** (**112×** smaller) |
| clamp binding *share* | 0.917 | 0.917 ⚠️ see §12.7 |
| assembled QB PIT (max-decile dev) | **0.0648** | **0.0281** |
| folds clearing the 0.05 PIT bar | **0/8** (0.0489–0.0897) | **8/8** (0.0172–0.0343) |

**A calibrated assembled QB distribution exists.** After three joint-layer stories could not get QB
below 0.064, recalibrating one number per (row, leg) clears the bar on **every fold**, and the
incumbent clears on **none**. The atom lands within **0.0014** of the realized all-zero rate.

And it is not bought with the proper score: `zm_floor` **2.5645** beats the matched foil
`mixall_learned` **2.5829** by **+0.0184 CRPS**, CI95 **[0.0032, 0.0336]** (excludes zero), **6/8**
folds, **p = 0.0121**, with **PBO 0.0**, out-of-sample gap **0.0%**, contender spread 2.54%, and
**100% of flip mass on the winner** (70/70 IS halves) — the most stable selection this line has
produced. Coverage(80) **0.8299** clears its 0.80 floor. Degenerates lose by a mile on CRPS
(6.54 / 7.84 / 10.44) *and* on PIT (0.40 / 0.54 / 0.76), which is what proves the PIT bar never
became a selection criterion (NF1.8).

### 12.2 ⭐ THE PRE-COMMITTED MECHANISM IS REFUTED BY THIS STORY'S OWN CAPTURES

The decision to run recorded the headline as: *"no target derived from the availability ESTIMATE
alone can do it without degrading the components, because `passing_yards` already prices availability
internally — so it prices availability twice, and the sign flips with P(played)."* **Both halves of
that clause are contradicted by the measurements taken to test them.**

- **"Double-prices availability" — REFUTED.** The matched foil for that channel is `zm_climatology`,
  the ROW-BLIND arm: identical re-splice machinery, availability content removed. The winner beats it
  by **+1.1871 CRPS, 8/8 folds, p = 0.0** — the **largest positive channel in the story**. Removing
  the availability content from the target is catastrophic, not corrective. (Channel table: the
  recalibration channel is +0.0184 at p=0.0121; NF-W7e's own split channel reproduces at +0.0064,
  8/8, p=0.0.)
- **"The sign flips with P(played)" — REFUTED as stated.** Pooled over 8 folds and rows on fixed π̂
  edges (all 10 buckets evaluable, 5,485 QB rows) the winner's decomposition is **`NON_MONOTONE`
  with 6 sign changes**. The two buckets holding **57%** of all rows show almost nothing
  (π̂ 0.0–0.1: 1,324 rows, **−0.16**; π̂ 0.9–1.0: 1,799 rows, **−0.03**); every large swing lives in
  buckets of **102–176 rows** and alternates sign (+3.07 then −2.62 then −2.18). That is the
  signature of thin-support noise, not an availability gradient. The one-fold quartile view that
  produced the original claim had forced equal *counts* per bucket and lumped a nearly-empty middle
  in with the top — the defect §11.5 removed, showing up in the conclusion it had produced.

⇒ **The refusal is real; the stated reason for it was wrong.** This is the NF-D15 (g′) lesson in the
null direction: a matched foil refutes a *stated mechanism*, not only a null.

### 12.3 What the component damage actually is

`per_leg_calibration_not_degraded` fails at **+0.3866%** against a tolerance of 0.0. Decomposed:

- **It is one leg.** `passing_yards` pools **−0.1587**; every other priced leg is **≤ +0.0026** or
  exactly **0.0** (`receptions`, `receiving_*`, `two_pt`, `rushing_tds` are untouched — their
  buckets read `UNDEFINED` because the transform never moved them, which is the correct reading).
- **It is sign-inconsistent across folds:** per-fold relative change
  **[−1.25, −0.35, +0.74, +1.81, +0.32, +1.42, −0.29, +0.60] %** → degraded on **5 of 8** folds,
  improved on 3, mean **+0.375%**, range −1.25% to +1.81%.

⛔ **The bar STAYS at 0.0 and the refusal STANDS** (E2.1-r — the tolerance was registered *alongside*
"if the diagnosis is right the legs IMPROVE", and the legs did not improve). Stating the measured
shape of the refusing quantity is not re-reading the bar; it is the input the successor's forward
registration needs, and it bears directly on the PM's open gate-vs-diagnostic question: a clause
refusing a ship on a **+0.375% point estimate that is positive on 5 of 8 folds** is refusing on
something not distinguishable from noise. That is a decision to make FORWARD, in NF-W7g's
registration — never here.

### 12.4 The DSR failure — and why field coherence is NOT the lever (measured, not asserted)

`DSR = 0.0` at `observed_sr = 1.013`, from trial Sharpes **[−1.347, 1.013, −10.934, −2.408]** giving
cross-trial dispersion **V = 27.147**: `zm_climatology`'s −10.934 dominates the deflation bar. That is
the MH2.5 / NF-W6b-C / NCAAF-P2.1-S1 heterogeneous-field mechanism, and `PBO 0.0` with 100% flip mass
on the winner says the *selection* is maximally stable — so DSR here is a statement about the FIELD.

The obvious move is therefore a fresh registration over a coherent family (the three ROW-CONDITIONAL
arms, excluding the row-blind one as a mechanistically different hypothesis). **Measured as a
post-verdict DIAGNOSTIC (⛔ not a re-score; the shipped verdict is the 4-arm one):**

| field | V | DSR |
|---|---|---|
| declared 4-arm (**the verdict**) | 27.147 | **0.0000** |
| row-conditional 3-arm (diagnostic) | 3.066 | **0.1741** |

**Coherence is not enough here.** V falls **8.8×** and DSR reaches only 0.174 against a 0.95 bar, so
this case is *unlike* MARGIN2→3 / W7→W7b / W6b-C, where a coherent re-registration converted the
refusal into a ship. The instrument's own reading agrees and is more informative than the field story:
`DSR_UNREACHABLE` — *"field size is NOT a lever here — even a 2-arm field does not clear at this fold
count and dispersion, so the only lever left is a lower-variance design."* The binding quantity is the
per-fold noise in the delta (mean 0.0184, sd ≈ 0.0182, two negative folds). **A candidate
variance-reduction lever exists and is neither more data nor a smaller field: more DRAWS**, since part
of the per-fold spread is Monte-Carlo error in the CRPS estimates at 4,000 draws. ⛔ That must be
registered FORWARD and is not a claim that it would clear.

### 12.5 What the run tells the successor (correcting NF-W7g's carded premise)

NF-W7g is carded as *"condition the zero target on availability CONFIDENCE, not the estimate"*. **That
premise rests on the mechanism §12.2 refutes** — the availability content is worth +1.19 CRPS, and the
residual damage is not availability-structured. Two measured targets replace it:

1. ⭐ **The binding cell MOVED, and raise-only cannot reach it.** Pooled binding-leg share went
   `passing_yards` 0.7091 / `attempts` 0.2634 (served) → **`attempts` 0.5724** / `passing_yards`
   0.4245 (recalibrated). `attempts` already carries **more** zero mass than its realized rate, so no
   raise-only target in this family can correct it — it is now the majority binding cell and it is
   structurally out of reach of the whole NF-W7f mechanism. A successor that wants the cap higher must
   be able to LOWER an over-priced atom, which is a different (and monotonicity-breaking) transform.
2. **The residual `passing_yards` damage is thin-support noise, not a gradient** — concentrated in
   ~7% of rows at intermediate π̂ with alternating sign. Chasing it with a π̂-threshold rule would be
   mis-specified; the honest question is whether it is an effect at all.

### 12.6 What this certifies, and what it does not

QB now has a **calibrated** assembled distribution that also **beats** the incumbent and NF-W7e's arm
on the proper score — but it is **NOT certified** and **NOT shippable**: the ship was refused, and a
report-only result may never be re-classified into shippability (E2.1-r). ⛔ **NF-W8's four-position
optimizer input remains blocked** — QB is uncertified here and RB is a separate story. `best_alpha = 0`,
deploy-held; nothing serves either way. Per NF-W7c §4, a per-position-certified distribution must not
feed a CROSS-POSITION ranking regardless.

### 12.7 The one post-run code change (REPORTED-ONLY)

⭐ **The clamp's binding SHARE is invariant to the level it binds at, and alone it is actively
misleading.** The share reads **0.917 → 0.917** — identical to NF-W7e's — while the clamp's mean
upward move on π̂ collapsed **0.25271 → 0.00225 (112×)** and the installed atom nearly doubled. Read
alone, the headline row says "the clamp still binds on 91.7% of rows", i.e. *nothing changed*, when the
constraint had effectively stopped mattering. The magnitude is now reported beside the share
(`clamp_mean_upward_move_{served,winner}`), populated by `--rewrite-report` from the stored fold
results — no re-run, and the verdict, gates, null state and every score are byte-identical after the
re-render. This is the NF-D20 lesson one level over: **an ACTIVITY count is not a MAGNITUDE, and when
a constraint moves, the share can stay fixed while the constraint stops binding in any way that
matters.**
