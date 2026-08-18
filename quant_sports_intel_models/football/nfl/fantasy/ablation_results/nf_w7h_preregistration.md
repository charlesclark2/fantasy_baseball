# NF-W7h pre-registration — the RB MARGINAL-layer zero-mass recalibration on the 52-cell substrate

**Committed BEFORE any full-run scoring** (the §0.5 discipline). Everything decidable in advance
lives as a constant in `fp_rb_marginal_calibration.py`; the runner `run_nf_w7h_rb_marginal.py`
READS them (NF-D16). A smoke run (1 fold, 300 draws, artifacts suffixed `_smoke`) may be used to
prove the code path — no verdict, and **no constant may change in response to a smoke score after
this file is committed** except as an explicitly recorded SMOKE AMENDMENT (§12).

⚖️ Edge-independent projection product — `best_alpha = 0`, **deploy-held**, NF-G0 challenger.
Research-only: no changelog entry. Every emitted string is a calibrated RANGE, never an edge / ROI /
win-rate claim.

---

## 0. Why RB is NOT a re-run of NF-W7f — the two structural differences, measured before any score

NF-W7f took the QB substrate defect and cleared QB's assembled calibration: PIT 0.0648 → 0.0281,
8/8 folds where the reproduced incumbent clears 0/8. The card that opened THIS story reads RB as
"the other NF-W8 blocker … the same defect plausibly hits rushing_yards/receiving_yards."

Two quantities, **both read off COMMITTED records before this story scores anything**, say RB is a
materially different question. Recording them here is the whole point of a pre-registration: if
they are not stated in advance, a null at RB reads as a refutation of the mechanism when it is
really a statement about how little room the mechanism had.

### 0.1 RB's assembled calibration ALREADY CLEARS — so the QB verdict rule would be VACUOUS here

| quantity (NF-W7e, 8 folds, decisive run) | QB | **RB** |
|---|---|---|
| assembled PIT max-decile deviation, best construction | 0.0640 | **0.0242** (`mix_played`) |
| PIT bar | 0.05 | 0.05 |
| clears? | **NO** | **YES, already** |
| atom CAP — what the marginals admit (`mean_i min_j P̂_j(0)`) | 0.2687 | **0.3018** |
| realized all-zero rate | 0.5162 | **0.3359** |
| shortfall (realized − cap) | **0.2475** | **0.0341** (7.3× smaller) |
| marginal-admissible clamp binding share | **91.7%** | **41.8%** |
| coverage(80) | 0.8314 | 0.8901 |

⭐ **CONSEQUENCE, DECIDED HERE AND NOT LATER.** NF-W7f's headline rule `marginal_cap_verdict`
returns `CLEARS` when *the cap lifted AND some real arm's PIT clears the bar*. At RB the second
conjunct is **true before the story runs**, so that rule would return `RB_CLEARS…` for any arm that
moved the cap by a hair — a verdict satisfied by a mechanism that did nothing (the NF1.7 (a)
vacuous-anchor class, and the NF-D20 "count whether the mechanism could ACT" lesson). RB therefore
gets its **own** verdict rule (§7), whose states are about the PROPER SCORE while HOLDING the
calibration RB already has — including a state QB's rule structurally cannot express,
`RB_CALIBRATION_DAMAGED`.

### 0.2 RB's continuous cells OVER-price their zero — and the transform is RAISE-ONLY

The story's premise is that a continuous cell under-prices its own zero. NF-W6d's committed
serving record (`nf_w6d_served_stat_distributions.json`, the 126-row RB serving proof) measures
`gap = realized P(0) − predicted P(0)`; **positive = the cell UNDER-prices its zero and is
repairable by a raise-only re-splice**:

| RB cell | predicted P(0) | realized P(0) | gap | repairable by a RAISE? |
|---|---|---|---|---|
| `receptions` | 0.5685 | 0.4762 | **−0.0923** | ⛔ no — over-prices |
| `receiving_yards` | 0.5628 | 0.4921 | **−0.0707** | ⛔ no — over-prices |
| `rushing_yards` | 0.4218 | 0.3571 | **−0.0647** | ⛔ no — over-prices |
| `carries` | 0.4080 | 0.3492 | **−0.0588** | ⛔ no — over-prices |
| `receiving_tds` | 0.9641 | 0.9444 | −0.0197 | no |
| `two_pt` | 0.9937 | 0.9841 | −0.0096 | no |
| `fumbles_lost` | 0.9715 | 0.9762 | +0.0047 | yes (negligible) |
| `targets` | 0.4519 | 0.4603 | +0.0084 | yes (negligible) |
| `rushing_tds` | 0.8591 | 0.9048 | **+0.0457** | ✅ yes — the one real offender |
| `attempts`, `passing_*` | 1.0 | 1.0 | 0.0 | degenerate |
| *(for contrast)* `QB\|passing_yards` | 0.3295 | 0.5506 | **+0.2211** | ✅ the NF-W7f defect |

⭐ **The card's stated premise is CONTRADICTED on the committed record.** `rushing_yards` and
`receiving_yards` — the two cells the card names — are among the cells that most OVER-price their
zero at RB, and `resplice_zero_mass` is **RAISE-ONLY by construction** (NF1.7 (d) (4): lowering an
atom would require inventing positive mass the source never expressed, and because the cap is a
row-wise MIN only raising can lift it). The transform therefore **cannot touch them**. The only RB
cell that materially under-prices its zero is `rushing_tds`, a low-weight touchdown leg — not a
continuous one.

⛔ **This is a HYPOTHESIS, not a finding, and it is registered as such.** It is read off a
126-row single-week serving proof, exactly as NF-W7f treated the analogous 89-row QB reading
("that is a HYPOTHESIS read off an 89-row serving proof, not a finding"). The runner MEASURES the
per-leg predicted-vs-realized zero mass, the row-wise argmin (which cell actually caps the atom)
and the cap before/after **on every fold at fold scale (~1,073 RB test rows/fold, 8.5× the proof)**,
and the record reports what bound the cap rather than what was expected to. A fold-scale
measurement is free to overturn this table, and the arms are unchanged either way.

### 0.3 What the story is therefore testing

Not "does the QB repair work at RB" — RB has no calibration defect to repair. The registered
question is: **with the marginal-admissibility constraint removed at RB, does the assembled RB
predictive get BETTER on the proper score without losing the calibration it already has?** A NO is
a real result: it says RB's residual (NF-W7e's `GENUINE_ABSENCE` against `mix_played`) is not a
marginal-layer question, which is exactly what NF-W8 needs to know before it spends another story
on RB.

---

## 1. Scope

**RB ONLY.** ⛔ QB/WR/TE are NOT scored here and NOT reported — a position this story does not run
cannot be read as evidence in either direction (NF1.7 (a)), and a report-only result may never be
re-classified into shippability (E2.1-r). The BH family carries ONE member; that is the declared
scope, not a multiplicity dodge, and it is stated on the verdict so a reader prices it.

Target `league_fantasy_points` under NF-W7c's declared gate league (`full_ppr`), NF-W7c's fold axis
(8 folds), ranked on `crps_q199`, gated on `randomized_pit_max_decile_dev`. Every one of those is
INHERITED by reference from the predecessor modules — ⛔ none is re-chosen here (E2.1-r).

## 2. The held-fixed joint construction — `mix_played`, NOT `mixall_learned`

NF-W7f held the joint construction fixed at NF-W7e's registered arm `mixall_learned`, because at QB
that arm is *also* the CRPS-best construction on record. **At RB it is not.** NF-W7e measured
(8 folds, decisive):

| RB construction | mean `crps_q199` | what it is |
|---|---|---|
| **`mix_played`** | **2.5173** | NF-W7d's registered primary: learned π̂ + Σ on ACTIVE rows |
| `mixall_learned` | 2.5212 | NF-W7e's registered arm: learned π̂ + Σ on ALL rows |
| `single_copula` | 2.5290 | NF-W7c's incumbent (`joint_rank`) |

so NF-W7e's own RB verdict was `GENUINE_ABSENCE` — `mixall_learned` LOST to `mix_played` by
−0.0039 CRPS (CI95 [−0.0065, −0.0013], 1/8 folds).

⇒ **`JOINT_CONSTRUCTION = "mix_played"`** for every real arm, and **`MATCHED_FOIL = "mix_played"`**.
The rule this follows is NF-W7f's own, applied to RB's facts rather than copied from QB's
conclusion: *the arm must beat the best thing that EXISTS, not merely the thing that shipped.*
Holding the construction at `mixall_learned` would have handed this story a foil already known to
be beaten and made a "win" un-attributable to the recalibration.

Σ is `MX.sigma_played` (active rows) on TRAIN, for every arm and every estimation context; π̂ is
NF-W7d's `mix_learned` estimator, imported. ⛔ NOTHING about the copula, the Σ population or the
availability estimator is re-opened here — NF-W7e closed the joint line and this story does not
re-litigate it. The ONLY thing the declared family varies is **the per-leg zero-mass TARGET of the
RB marginals**.

## 3. The declared field (⛔ never trimmed or grown after a score — MH2 (a) / MH2.2)

Four arms, differing ONLY in the per-(row, leg) zero-mass target, over an IDENTICAL joint
construction, identical marginals-before-recalibration, identical mixture machinery and identical
draw stream. The target functions are **imported from `fp_qb_marginal_calibration.zero_targets` by
identity** — a second implementation of a shared rule is the NF-C0e wrong-key class.

| arm | target `t(row, leg)` | role |
|---|---|---|
| `zm_conditional` | `q̂ + (1 − q̂)·p̂₊` | ⭐ **PRIMARY** — the two-part reconstruction |
| `zm_floor` | `max(P̂(0), q̂)` | the MINIMAL intervention (NF-W7f's QB winner) |
| `zm_climatology` | the leg's TRAIN realized zero rate, row-BLIND | registered **SHIPPABLE** (NF-D20) |
| `zm_over` | primary with `q̂′ = min(1, 1.5·q̂)` | the MAGNITUDE probe — a REAL, SHIPPABLE arm |

`q̂ = 1 − π̂` is the estimated inactivity probability. `zm_over` is **expected to lose** and is
registered as a real arm rather than an anchor: an anchor registered to lose that then BEATS the
field produces a null while the answer sits in an ineligible cell (NF-D20 / NF-W7b). If it wins,
the magnitude hypothesis is REFUTED and the record says so rather than re-labelling it.

`PRIMARY_ARM = "zm_conditional"`. `DECLARED_FIELD_SIZE = len(REAL_ARMS) = 4`, and it is what is
passed to `cv_power.classify_null(declared_field_size=…)` (§10).

**Contest foils** — `beats_foil` binds against these and ONLY these:
- `mix_played` — ⭐ the MATCHED foil: the identical joint construction on the SERVED marginals,
  reproduced to 1e-9 against NF-W7d's `mix_learned`. `mix_played − zm_*` is the marginal
  recalibration channel with the copula, the Σ, the π̂ fit and the draw stream all held fixed; the
  no-op identity (§5.3) is what earns that claim.
- `single_copula` — THE INCUMBENT (NF-W7c's `joint_rank`), reproduced to 1e-9. Keeping it binding
  makes this story's margin comparable to NF-W7c/W7d/W7e's on the same folds and the same seed.

**Reference foils** — SCORED and REPORTED; they do NOT bind `beats_foil` and are EXCLUDED from the
PBO/DSR trial field (MH2.1 (a) — a diagnostic anchor that joins the trial field sets the gate's own
bar): `zm_cond_copula` (the primary's marginals under the incumbent's copula — the recalibration
with the availability split OFF), `assembled_indep` (carries the three inherited dependence
clauses), `foil_direct_points` (the ARCHITECTURE question, §11 — never this story's gate).

**Anchors**: the inherited degenerates (`nihilist_zero`, `zero_width`, `max_width`,
`assembled_comonotone`), `permuted_direct`, `zm_permuted` (the primary's per-row `q̂` shuffled
within a global week — preserves the population LEVEL of the atom, destroys only its per-ROW
assignment, so it separates "found the right rows" from "raised the average", NF-D15 (g′)), and a
**per-form** peeking oracle + matched-n control for EVERY real arm (NF-D16 (g‴): one ceiling per
form, because the forms nest; NF1.9 (f): the floor is enforced at equal family AND equal
resolution). Every degenerate's PIT is printed every run, which is what PROVES the bar was never
promoted into a selection criterion (NF1.8).

The draw seed and the availability-stream offset are INHERITED from NF-W7c→W7d→W7e→W7f, so
`single_copula` reproduces NF-W7c and `mix_played` reproduces NF-W7d, per fold to 1e-9, and every
arm, foil and anchor of a fold transforms the SAME base normals (common random numbers). Nothing
can be shopped by keeping it: no recalibrated RB arm has ever been scored under this seed.

## 4. The mechanism-activity floor — `MIN_CAP_LIFT = 0.0341`, DERIVED

NF-D20: before crediting a result, count whether the mechanism could ACT. The recalibration acts
through exactly ONE channel — it raises the marginal-admissible atom cap `mean_i min_j P̂_j(0)` so
the mixture's clamp stops binding. If the cap does not move, every arm is its own matched foil and
the contest passes on nothing.

**The floor is derived from RECORDED design quantities known before this run, never from anything
this run measures (E2.1-r):**

> The recalibration's entire purpose is to stop the marginals from FORBIDDING the atom the
> population actually exhibits. It has turned the knob iff the recalibrated cap reaches RB's
> realized all-zero rate. NF-W7e RECORDED RB's cap at **0.3018** and RB's realized all-zero rate at
> **0.3359** ⇒ `MIN_CAP_LIFT = 0.3359 − 0.3018 = 0.0341`.

This is the RB analogue of NF-W7f's QB floor (0.012 of probability mass, derived from the 0.05 bar
and QB's recorded first decile of 0.162). It is a target stated in advance, not a level read off a
result — and NF-W7f's own decisive run SATISFIES the same rule at QB (cap 0.2687 → 0.5481 = a lift
of 0.2794 against a QB shortfall of 0.2475), so the rule is not tuned to make RB pass or fail.

⭐ **An activity SHARE is not a MAGNITUDE (NF-W7f).** NF-W7f measured a clamp binding share that was
**byte-identical before and after** (0.917 → 0.917) while the clamp's mean upward move on π̂
collapsed 112× (0.2527 → 0.0023) — a headline quoting the share alone would have said *nothing
changed* about a constraint that had stopped mattering. This run therefore reports, per fold and
pooled: the cap before/after, the clamp's binding SHARE **and** its mean upward move on π̂, and the
installed atom against the realized rate.

The baseline is READ FROM the committed NF-W7e record at run time (`predecessor_cap_baseline`),
never trusted from a constant — a cap lift measured against a hard-coded number could not notice
that the predecessor's record had been regenerated (the NF1.9-R `served_*`-column lesson: never
trust a name for a measurement). If the record is absent, a path proof, or carries no RB
`atom_cap_detail.cap_mean`, `cap_was_lifted` is **UNEVALUABLE and never a pass** (NF1.7 (a)).

## 5. Gate clauses

Statistical clauses (`beats_foil`, `fold_consistency`, `pbo_ok`, `dsr_ok`, `fdr_ok`,
`coverage_floor_ok`, `pit_flat_ok`) and their constants are INHERITED BY REFERENCE from
NF-W7e/NF-W7c — ⛔ not one is re-chosen here (E2.1-r / NF1.8 / NF-D18). Coverage(80) stays a
FLOOR, never a target (NF1.8); PIT flatness GATES and never RANKS (NF-W7c measured the
over-correlated degenerate posting the best PIT while posting the worst CRPS — a criterion a
degenerate wins is fatal).

Anchor / registration clauses: `degenerates_lose`, `permutation_behaves`,
`oracle_floors_respected`, `mixture_is_active`, `mixture_preserves_marginals`,
`incumbent_reproduces`, `predecessor_reproduces`, plus the five this family adds:

**5.1 `zero_mass_hits_target`** — the recalibrated bank, RE-READ through the public atom reader
`MX.leg_zero_mass`, carries exactly the atom the raise-only rule asked for (tol 1e-12).

**5.2 `positive_law_preserved`** — the conditional-on-positive law moved by no more than the
resolution a raised atom necessarily costs: a COUNTING Kolmogorov distance against a DERIVED bound
(`2 × grid_step / (1 − t)`), ratio ≤ 1.0. Cells whose conditional law either bank cannot resolve
(< 10 positive knots, or flat) are UNEVALUABLE and excluded with the share reported — never a pass.

**5.3 `matched_foil_identity`** — re-splicing a bank to its OWN measured zero mass is BYTE-IDENTICAL
through `FA.draw_legs` (tol 0.0). This is what makes `mix_played` the EXACT matched foil rather
than a differently-implemented one, and it is MEASURED per fold, never assumed.

**5.4 `cap_was_lifted`** — §4.

**5.5 `per_leg_calibration_not_degraded`** — ⭐ **THE CLAUSE THIS STORY DECIDES FORWARD.** See §6.

## 6. The component-degradation clause — decided FORWARD, with the gating question resolved first

### 6.1 The gating question: does the SERVED paid stat line derive from these cells? **NO.**

Resolved before the clause was written, by reading the running system (not a docstring):

- **Every** consumer of `stat_distribution_serving{,_d}` / `stat_distributions_{c,d}` in the repo is
  a research runner (`run_nf_w6*`, `run_nf_w7*`) or a test. There is no `app/backend`, `frontend/`
  or exporter consumer.
- `export_draft_board_json.py` contains **zero** references to `stat_distribution*`, `fp_assembly`
  or the W6d cells.
- The served paid stat line is the `STAT_FIELD` payload map
  (`app/backend/services/projection_fields.py`), scored server-side by
  `league_scoring.build_board`. Its values are the board's `proj_pass_yds` / `proj_rush_yds` /
  `proj_rec_yds` … columns, which are produced by **`season_projection.py`** — the SEASONAL point
  projection path, a different model from the W6d weekly distributional substrate.

⇒ A per-leg CRPS change in the recalibrated weekly cells **damages no served surface**. The clause
cannot be defended as protecting the paid stat line, because the paid stat line does not come from
here.

### 6.2 What the clause is still for, and why it stays a HARD GATE

It has a scientific job independent of serving: it refuses a story that buys the assembled atom by
**wrecking the parts** — a refit wearing a recalibration's badge. `positive_law_preserved` (§5.2)
guards *reshape vs re-weight* structurally; the per-leg CRPS clause guards the softer question of
whether the parts got worse. ⇒ **the clause REMAINS A HARD GATE.** It is not demoted to a
diagnostic.

### 6.3 The threshold — MATERIALITY, from a DESIGN quantity

NF-W7f set `MAX_PER_LEG_CRPS_DEGRADATION = 0.0` — any degradation, however small, refuses. That is
the "demonstrable ≠ material" defect NF-W6 names, facing the refusal direction: it makes the clause
fire on a rounding artefact. NF-W7c's rule (adopted verbatim as a DESIGN quantity, never from an
observed value) is that a violation must be **significant AND material**:

> A per-leg degradation REFUSES the story iff it is (a) **demonstrable** — the summed priced-leg
> CRPS is worse on a MAJORITY of folds (≥ 5 of 8), so a single fold's noise cannot refuse — AND
> (b) **material** — its RELATIVE magnitude is at least **1/10 of the arm's own claimed effect**,
> where both are expressed as relative changes on their own scales:
> `rel_degradation = (Σ recalibrated − Σ served) / Σ served` over the priced legs, and
> `rel_claimed_effect = Δcrps_q199(matched foil − arm) / crps_q199(matched foil)`.

⭐ **PROOF THAT THIS IS NOT A RESCUE OF ANYTHING.** Applied to NF-W7f's OWN recorded QB numbers, the
relaxed rule **still REFUSES QB**: the claimed effect is 0.0184 / 2.5829 = 0.712% relative, so the
materiality bar is 0.0712% — and QB's observed per-leg degradation was **0.3866%**, 5.4× above it.
The threshold was chosen before any RB score, and it does not retroactively flip the one recorded
result it could have flipped. Both the raw sums and the two relative figures are reported so a
reader can re-derive under another rule (NF-D14).

⚠️ Registered in advance: `rel_claimed_effect ≤ 0` (the arm does not beat its matched foil) makes
the materiality bar non-positive, in which case the clause is **UNEVALUABLE and the gate is
already lost on `beats_foil`** — it is reported as such, never as a pass (NF1.7 (a)).

## 7. ⭐ THE RB VERDICT RULE — five states, fixed BEFORE any score

QB's rule cannot be reused (§0.1). `rb_marginal_verdict` reads, in this order:

| state | condition | reading |
|---|---|---|
| `UNDEFINED` | the position was not scored / the cap is not finite | never read as any of the below |
| `CAP_NOT_LIFTED` | cap lift < `MIN_CAP_LIFT` | ⭐ **INACTIVE, not refuted** — every arm is its own matched foil and the contest passed on nothing; the thesis is UNTESTED (NF1.7 (a) / NF-D20) |
| `RB_CALIBRATION_DAMAGED` | cap lifted **AND** the best arm's PIT no longer clears the bar RB already cleared | the recalibration BROKE a calibration RB HAD — a raise-only transform pushed atoms onto cells that already OVER-price their zero (§0.2). ⛔ A state QB's rule cannot express and RB structurally needs |
| `RB_RECALIBRATION_PAYS` | cap lifted **AND** PIT still clears **AND** the winner beats BOTH contest foils | the marginal layer WAS a live constraint on RB's proper score |
| `RB_CAP_LIFTED_NO_SCORE_GAIN` | cap lifted **AND** PIT still clears **AND** no arm beats both foils | the cap was REAL but not RB's binding constraint — NF-W7e's `GENUINE_ABSENCE` stands and RB's residual is elsewhere. ⛔ A CONSTRAINT/absence shape, not a power shortfall |

Beside the state the rule reports the magnitudes a reader needs to CHECK it rather than re-decide
it: the cap before/after, the installed atom against the realized rate, the clamp's binding share
**and** its mean move on π̂, the per-arm PIT, and WHICH LEGS bound the row-wise minimum before and
after.

**CERTIFICATION.** RB is certified for NF-W8 **only** on `RB_RECALIBRATION_PAYS` *with the full gate
green* — i.e. it clears PIT **AND** beats both foils **AND** every statistical and anchor clause
passes. Anything else is a null, classified per §10.

## 8. The availability decomposition — FIXED ABSOLUTE EDGES, raw sums and counts

⛔ **NEVER per-fold quantile / equal-count buckets.** NF-W7f's headline mechanism claim ("the cell
already prices availability internally, so an availability-derived target prices it twice, and the
sign flips with P(played)") was REFUTED by its own decisive run precisely because a π̂-QUARTILE
bucketing on a bimodal covariate fabricated a monotone gradient that did not exist: quartiles read
a tidy sign flip, while the same data on FIXED absolute edges pooled over 8 folds was
`NON_MONOTONE` with six sign changes.

So: `PI_BUCKET_EDGES = (0.0, 0.1, …, 1.0)` — fixed, absolute, identical on every fold, so "bucket
k" is the same population on every fold and the pool is exact. Each fold contributes raw **Σsums
and Σcounts** (never per-bucket means, which could only be pooled as a mean-of-means and would
silently re-weight a thin fold equal to a fat one — NF1.8). A bucket below `MIN_BUCKET_ROWS = 30`
reports `None`, can never supply a crossover, and `< 2` signed buckets reports `UNDEFINED` — never
"no crossover" (NF1.7 (a)). REPORTED only; nothing gates on it.

## 9. DSR — read the 2×2 (field × return-series) FIRST, and do NOT reflexively re-register

The repo now has cases in both directions and the reflex is wrong as often as it is right:

- NF-W6b-C / MARGIN2→3 / W7→W7b / NCAAF-S1: a DSR failure over a HETEROGENEOUS declared field was a
  statement about the FIELD, and a fresh COHERENT registration converted the refusal into a ship.
- **NF-W7f: it was NOT.** Dropping the far-out arm cut cross-trial dispersion `V` **8.8×**
  (27.15 → 3.07) and DSR still reached only **0.174** against a 0.95 bar, because the binding
  quantity was **per-fold NOISE** in the delta (SR ≈ 1.013 at 8 folds), not multiplicity.
  `classify_null`'s own `DSR_UNREACHABLE` text was right and the field instinct was wrong.

⇒ **Registered protocol.** On a DSR failure this run computes and REPORTS the 2×2 as a labelled
DIAGNOSTIC — {declared 4-arm field, coherent sub-field} × {per-fold series, per-bucket series} —
**before** naming any remedy. If `V` falls hard and DSR barely moves, the remedy named is
**VARIANCE** (more assembly draws / a lower-noise design), ⛔ never "more seasons" and ⛔ never a
post-hoc field trim (MH2.2). The instrument is called as
`cv_power.classify_null(declared_field_size=len(REAL_ARMS), …)` and the machine flag
**`field_remedy_admissible` is read, not the prose** (MH2.7): the declared field is 4 arms
committed in this file before any score, and `declared_field_size_source` names this document.

## 10. Null classification

Per `cv_power.classify_null`, with the repo's standing hand-corrections applied at REPORT time and
the instrument's own reading kept VERBATIM beside it for audit (the derive-not-store rule — a
mislabelled state then costs zero refit, NF-W2e/NF-W3):

- A null resting on a HARD CONSTRAINT (a fixed PIT bar, a coverage floor, an anchor/registration
  clause) is **`CONSTRAINT_REFUSED`** with `binding_half` named — ⛔ **NO fold/season re-test
  trigger is published** (NF-D18: more folds shrink the SE and make the refusal MORE certain, so a
  "come back with more seasons" trigger is actively misleading).
- When BOTH a statistical gate and a non-rescuable anchor fail, the **ANCHOR BINDS** (more folds
  could clear the statistical half and the ship would still be refused): state
  `CONSTRAINT_REFUSED`, name `binding_half = "anchor"`, and report the statistical shortfall
  anyway rather than hiding it (NF-W7f).
- `CAP_NOT_LIFTED` (§7) is an **INACTIVE** finding — a scope/harness reading, never a finding about
  RB, and it publishes no trigger of any kind.
- `GENUINE_ABSENCE` (the best arm loses ON AVERAGE) publishes **no** re-test trigger: no `n` and no
  field size rescues a negative point estimate.
- Only a genuinely reachable shortfall may be stated as `POWER_LIMITED`, and then the margin is
  stated **in the unit that grows** (folds/seasons/rows), with whether it is reachable NOW.

## 11. Report-only (⛔ never gates, never re-classified into a certificate — E2.1-r)

**The RB vs `foil_direct_points` re-read.** NF-W7c recorded a `GENUINE_ABSENCE` for assembly-from-
parts against a learner pointed straight at league points, at QB and RB. At QB that verdict turned
out to be a MARGINAL-CALIBRATION artefact: NF-W7f's recalibrated arm flipped it
(`beats_direct_points_REPORT_ONLY: True`, Δ +0.0189). RB may be the same — or may not: NF-W7e
recorded RB's gap at **−0.0520** (`foil_direct_points` 2.4692 vs `mix_played` 2.5173), an order of
magnitude wider than QB's, so a flip at RB requires ~7× the movement NF-W7f produced at QB. This
run scores it and reports it. It is a FINDING, not a certificate: `beats_foil` binds against
`mix_played` and `single_copula` only (§3), and the architecture question is NF-W7c §11.4's, not
this story's gate (`classify_null`'s `beats_foil` names the FOIL, not the hypothesis —
NF-W7c's lesson that a null against a stronger different-family foil is an ARCHITECTURE verdict).

## 12. Smoke amendment protocol

A smoke run (`--smoke`: 1 fold, 300 draws, artifacts suffixed `_smoke`) may be used to prove the
code path. It produces **no verdict**. ⛔ No constant in `fp_rb_marginal_calibration.py` may change
in response to a smoke SCORE after this file is committed, except as an explicitly recorded SMOKE
AMENDMENT appended to this section naming the constant, the old and new value, and the reason —
and a reason may be a CONSTRUCTION defect (a code path that raised, an identity that went RED),
⛔ never "the number came out badly" (E2.1-r).

*(no amendments)*

## 13. Promote blockers (inherited in full, plus this story's)

- NF-W7h is **DEPLOY-HELD**: an NF-G0 challenger, served by nothing until governance promotes it.
- ⛔ **RB ONLY.** This record certifies NOTHING about QB/WR/TE.
- ⛔ A per-position-certified distribution may **not** feed a CROSS-POSITION ranking until every
  compared position is on the same generator AND the same level recalibration (NF-W7c §4). NF-W8's
  four-position optimizer input is a ranking, so an RB certificate alone does not unblock it.
- The recalibration CHANGES NF-W6d certified cells' marginals — a consumer reading the 52-cell
  substrate directly is reading the SERVED cells, not these; nothing here re-serves W6d.
- NF-W7c's promote blockers are INHERITED in full (an assembled row whose `source` is not
  `bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league prices;
  a league pricing a `SKILL_UNMODELED_KEYS` term has a real coverage gap). ⚠️ NF-W7e recorded RB as
  `partial_default` — **7 of 10 priced stats use a NF-W6d calibrated DEFAULT** at RB, a materially
  weaker labelling than QB's, and it is reported on the verdict.
- A ship here does NOT re-open NF-W4's Layer B: availability enters as a component of the
  predictive's draw law and of its marginals' atom, never as a feature injected into a
  point/quantile learner.
