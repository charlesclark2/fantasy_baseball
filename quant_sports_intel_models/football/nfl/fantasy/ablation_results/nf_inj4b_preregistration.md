# NF-INJ4b — PRE-REGISTRATION

**Committed before any arm was scored.** ⛔ Editing this document after a result is not a
pre-registration (E2.1-r). Everything decidable in advance is a CONSTANT in
`nf_inj4b_designation_duration.py`; this document is the reasoning, and the runner restates neither.

`best_alpha = 0`. **DEPLOY-HELD** — the served Questionable / Doubtful / Out availability discount
stays EXACTLY ZERO until the gated ship path (§7) and explicit operator approval.

---

## 0. ⛔ THE HONESTY CLAUSE — read this before any number in this study

This is the FIFTH fix-the-spec successor (MARGIN2→3, W7→W7b, VAL3→VAL3b, NF-INJ2b→2c). It changes
**one pre-registered anchor clause and nothing else.**

NF-INJ4 measured the mechanism and published it: `desig_x_practice` **+0.1408 CRPS** over its
matched status-blind foil, **10 of 10 folds**, one-sided **p = 0.0**, PBO **0.000** over both the
declared field and the eligible set, DSR-CONV **0.9999**, permutation beaten, both degenerates
losing. **Seven of eight gates passed.** It was `CONSTRAINT_REFUSED` by the eighth — an oracle
anchor fitted at 9.0× coarser resolution than the arms, which measured the oracle's sample size
rather than any property of an arm.

⇒ **With the field, the folds and the data unchanged, every number this study reports is ALREADY
KNOWN, and only the gate flips.** What is bought here is a **properly-registered record of an
already-measured result** — ⛔ **not new evidence, and never to be presented as fresh
confirmation.** A re-run that reproduces a known number confirms the pipeline, not the hypothesis.

**"Unchanged" is a MEASUREMENT here, not an assumption, in two independent ways:**

1. **By construction.** `nf_inj4b_designation_duration` IMPORTS the field, the folds, the seed, the
   metric, the BH family, `V`'s membership, the injection and the application constants from
   `nf_inj4_designation_duration`. There is no second place for them to drift.
2. **By the substrate vintage check.** NF-INJ4's frame artifact is gitignored and was absent from
   this worktree (the NF-INFRA1 class), so it was rebuilt — through NF-INJ4's own census loaders and
   `build()`, unchanged — and then CHECKED against NF-INJ4's committed census, every expectation
   read out of that record rather than hardcoded. Result, `nf_inj4b_substrate_vintage.json`:
   **1,309 rows / 398 players / weeks 1–18**, per-designation cells `questionable 842 · none_listed
   239 · out 199 · doubtful 29`, PIT gate **1,309 checked, 0 dropped** — **identical on every
   field**. ⭐ The rebuild wrote ONLY the parquet: `run_nf_inj4_census.main()` writes its census
   report at FIXED PATHS and running it would have OVERWRITTEN a decided story's audit trail (the
   NCAAF-P2.1 S1-serve defect), which E2.1-r forbids.

⚠️ Had the append-only store moved, that would have been a FORCED change, every deflation statistic
would recompute from scratch, and this document would have had to say the result was new evidence.
The check is what makes the claim above admissible; it is not a formality.

**The ONE genuinely new thing** is the PLAT-CVP2 positive control's **verdict**, because the control
drives the study's own gate function and this registration changes that function. That, and nothing
else, is reported as new.

---

## 1. What is being corrected, and why it is not a re-read

`oracle_respected`, as NF-INJ4 registered it, reads *"no arm beats its OWN-FORM oracle"* —
`arm_crps ≥ own_form_oracle_crps`. It failed on all three shippable arms.

Per NF-D20, NF-INJ4 left that clause failing and DECOMPOSED it rather than re-labelling it. The
decomposition measured that the oracle is fitted on a **~131-row test fold** against arms trained on
**~1,178 rows** — a **9.0× resolution ratio fixed by the CV design** — with `MIN_CELL_N = 30`
collapsing most of the peek's conditioning to the pooled distribution at that size. The clause was
measuring the ORACLE'S SAMPLE SIZE (the NF-W7i capacity-starved-ceiling shape).

**NF1.9 (f) is explicit that a peeking oracle is a floor ONLY at matched `n`**, and enforces it by
gating the ORACLE against a matched-n control of equal family and equal resolution. In this design
an arm beating its own peeking oracle can only be **capacity, never leakage**: the arms are fitted
strictly on training rows disjoint **by player** (`FOLD_UNIT = gsis_id`), so the leakage the naive
clause exists to catch is excluded by the **fold construction**, not by the anchor.

⚠️ **That is a statement about THIS design and does not generalise.** In a design where an arm could
see its own test rows, the naive clause is exactly the thing that catches it. So the naive
comparison is still **COMPUTED AND REPORTED per arm as a diagnostic** — it will read FALSE, exactly
as NF-INJ4 measured. Retiring a clause from the gate table is not a reason to stop showing its
number.

⛔ **This is not a re-read of NF-INJ4's refusal.** NF-INJ4's registration, verdict and record stand
UNEDITED. This is a FRESH FORWARD registration that supersedes one clause going forward, decided and
committed before this study scored anything (E2.1-r).

---

## 2. ⭐ THE TWO GUARDS, NAMED SEPARATELY

The standing convention NF-INJ4 produced (`plan_specs/plan_spec_process.md`, "Oracle-anchor
resolution matching"): **the NF-W6d inactive-pair reading and the NF1.9 (f) capacity reading are
DIFFERENT clauses — registering one does not give you the other.** NF-INJ4 registered the first and
not the second, and that is precisely the gap this story closes. Both are named here explicitly;
neither is implied by the other.

One measured pair per arm — `own_form_oracle` vs `matched_n_control` — carries **three** states,
separated by a SYMMETRIC tie band `ANCHOR_TIE_TOL = 1e-6`:

| state | condition | meaning |
|---|---|---|
| **ACTIVE** | `oracle < control − TOL` | the peek genuinely helps at matched `n`; the floor holds and is informative |
| **INACTIVE** | `\|oracle − control\| ≤ TOL` | the pair had nothing to act on — UNINFORMATIVE |
| **VIOLATED** | `oracle > control + TOL` | an HONEST matched-n fit BEATS the peek — the floor is breached |

**Clause A — `anchor_pair_informative` (the NF-W6d inactive-pair reading).**
PASSES when **at least one SHIPPABLE arm's pair is ACTIVE**. An inactive pair is neither a refusal
(NF-W6d lost three shippable arms to reading a tie as "this form has no headroom") nor a pass
(NF1.7 (a): a check that could not run is not a check that ran). An anchor family in which NOTHING
could act certified nothing, and must not be scored as though it had.

**Clause B — `oracle_floor_matched_resolution` (the NF1.9 (f) capacity reading).**
PASSES when **no evaluable arm's pair is VIOLATED** — the floor enforced at equal family AND equal
resolution.

⚠️ **B is VACUOUSLY satisfied on an INACTIVE pair.** So B's pass count is reported BESIDE A's active
count and never on its own (NF-D20: count what the mechanism could ACT on before crediting "the
constraint held N of M"). ⭐ And because an activity classification is not a magnitude (NF-W7f), the
per-arm margin `|oracle − control|` is REPORTED, so a reader can see whether the 1e-6 tolerance is
load-bearing rather than take the classification on trust.

**`ANCHOR_TIE_TOL = 1e-6` is NF-INJ4's own activity tolerance, adopted VERBATIM**, so the
ACTIVE/INACTIVE partition is identical to the one it measured. Choosing a different tolerance would
move the partition and quietly break the honesty clause's "unchanged" precondition.

**The anchor construction is self-checked, not assumed.** `matched_n_control` is only "matched" if
it is genuinely fitted at the peek's resolution; if it silently fitted at full resolution the whole
matched reading would be vacuous. The control's training size is `min(n_test, n_train)` by
construction, and the run ASSERTS per fold that it equals the peek's row count. A control that is
not at matched resolution makes both clauses UNEVALUABLE — a hard failure, never a pass (NF1.7 (a)).

**A missing or unfittable anchor RAISES.** Carried over from NF-INJ4 verbatim.

---

## 3. Field, folds, data — inherited UNCHANGED

**Nothing in this section is a decision this study made.** It is NF-INJ4's registration, imported.
It is restated only so a reader need not hold two documents open.

| | |
|---|---|
| Substrate | the landed NF-W2c / NF-W2c-CBS capture store, 2025 — **1,309 (player, week) rows / 398 players / 18 weeks** |
| Sources | `nfl`, `cbs`; **ESPN excluded on ADMISSIBILITY** (a one-week-late attribution leaves its rows with no admissible week) |
| Target | `spell` — consecutive own-team games missed from the designation week; right-censoring OBSERVED, never imputed (77 rows, 5.88%) |
| Metric | exact discrete CRPS, per-row truncated to `{0..games_remaining}`. ⛔ Never a point MAE (65.6% zeros, conditional median 0 — NF-D11's inversion is measurably present) |
| Field | 7 arms; `DECLARED_FIELD_SIZE = 7`; shippable = `desig_empirical`, `desig_x_posgroup`, `desig_x_practice` |
| Design | grouped **10-fold by player**, `FOLD_SEED = 20260903` |
| `V` | measured over the five NON-degenerate arms; degenerates RETAINED in `n_trials = 7` (DSR-CONV, opted into explicitly and forward) |
| BH family | **ONE mechanism, ONE population, NO position axis ⇒ a single hypothesis**, so `0.05` BINDS; the arm-corrected `0.00714` is REPORTED beside it |
| PBO | FIELD-level (`pbo_application = "field"`), declared + eligible sets, eligible binding |

⛔ **No membership change of any kind.** Had one been forced, every deflation statistic would
recompute from scratch and **no DSR or PBO figure would be inherited across it** — `V` is a sample
variance over the field's trial Sharpes and moves NON-MONOTONICALLY with membership (MH2.2 /
NF-INJ3 §0a). ⛔ No post-hoc trim, and no menu of per-candidate-family DSRs.

**The ESPN exclusion stands as an ADMISSIBILITY ruling and is not re-litigated here.** Card
`yjZo7pk9` owns the fix. **`assert_point_in_time` is wired AND invoked** on the re-assembled frame:
**1,309 records checked, 0 dropped, no findings**; the store's revision clause is reported INACTIVE
(no subject holds more than one capture), which is not a pass (NF-D20).

**Sign certifiability, computed at REGISTRATION time** (`cv_power.validate_sign_certifiability`,
the PLAT-CVP2 discipline — a refusal re-shapes the design BEFORE scoring, never after):

| cutoff | sign floor at 10 folds | floor / cutoff | certifiable |
|---|---|---|---|
| 0.05 (binding) | 0.00098 | 0.0195 | ✅ with margin (≤ ½) |
| 0.00714 (conservative, reported) | 0.00098 | 0.1367 | ✅ with margin (≤ ½) |

`cv_power.fold_consistency_clause(10)` requires **7 of 10** wins (attained false-fire 0.1719 against
the legacy clause's 0.3770).

⛔ **`MIN_CELL_N = 30` IS UNTOUCHED, and the 29-row near-miss is restated here as a NON-REASON.**
`doubtful` holds 29 rows, so it can never populate its own in-fold cell and ALWAYS backs off to the
pooled distribution — the model treats a Doubtful player as an average injury-report player, which
is the backoff doing exactly what it was registered to do. Moving the threshold to 29 *because 29 is
the number that would unlock it* is reverse-engineering a design constant from the answer (MH2.2).
It is REPORTED, never acted on.

---

## 4. Gates, in the order they are read

Every gate is classified EXPLICITLY. ⛔ This registration declares `gate_classes=`; it does not fall
back on the instrument's name heuristic (PLAT-CVP2 defect 2). It is the **second** registration
consuming the explicit declaration, which is the trigger for retiring that heuristic.

| gate | class | passes when |
|---|---|---|
| `beats_incumbent` | metric | winner's pooled CRPS < `always_zero`'s |
| `beats_foil` | metric | winner's pooled CRPS < `status_blind_foil`'s |
| `fold_consistency` | metric | ≥ 7 of 10 fold wins |
| `bh_ok` | metric | one-sided paired p ≤ 0.05 |
| `anchor_pair_informative` | **invariant** | ≥ 1 shippable arm's oracle/control pair is ACTIVE (§2 A) |
| `oracle_floor_matched_resolution` | **invariant** | no evaluable arm's pair is VIOLATED (§2 B) |
| `beats_permutation` | metric | winner beats its designation-shuffled self |
| `dsr_ok` | **deflation** | DSR-CONV ≥ 0.95 |
| `degenerates_lose` | **invariant** | both degenerates lose to the winner |

PM convention: deflation-class = `{pbo, cscv, dsr, deflated_sharpe}`; `bh_ok` and `fold_consistency`
are MULTIPLICITY / STABILITY gates, not deflation-class.

### ⭐ The injection-invariance declarations, made FORWARD

`degenerates_lose` is carried over verbatim. **BOTH anchor clauses are declared INJECTION-INVARIANT
here** — the declaration NF-INJ4 said belonged to its successor, made before any arm is scored.

**Why they are invariant, mechanistically:** each compares TWO ANCHORS (`own_form_oracle` vs
`matched_n_control`) fitted on the SAME injected data by the SAME form at two sample sizes. An
injection that strengthens the designation → duration link strengthens both together. What the pair
measures is the PEEK'S CAPACITY — a property of the fold sizes and `MIN_CELL_N`, not of the effect's
magnitude.

**Corroboration, cited honestly:** NF-INJ4's post-hoc ladder measured the NAIVE clause FALSE at
every rung (0, 0.5, 1, 2, 4 games). ⚠️ That is evidence about a **DIFFERENT clause**, so it is cited
as corroboration and never as proof of the matched form's invariance.

⭐ **THE DECLARATION IS EXPECTED TO BE INERT FOR THIS VERDICT, and that is said plainly rather than
left for a reader to notice.** These clauses are expected to PASS, and a passing gate appears in no
blocking set, so the declaration **cannot rescue this study from anything.** It is registered
because it is true and falsifiable, so that a FUTURE run in which an anchor clause DOES block is
read as `CONSTRAINT_BLOCKED` rather than `BLIND` — and because declaring it now, before the result,
is the only moment at which declaring it is honest.

⛔ **It is not asserted.** This study runs its own gate ladder and REPORTS whether each
declared-invariant clause actually holds still across it. **A clause that MOVES refutes this
declaration, and that refutation will be reported as a defect in THIS registration** — the way
NF-INJ4 reported its own PBO prediction.

### The positive control (PLAT-CVP2), declared forward

`cv_power.injected_effect_positive_control` runs against this study's **own** registered gate
function. `inject(effect)` adds `effect` extra missed games to rows designated `out`/`doubtful`
(clipped to `games_remaining`); `inject(0.0)` returns the unmodified payload, so the two-sided
null-control leg genuinely runs. Declared effect: **1.0 game**. `gate_classes`, `invariant_gates`
and the null-control leg are all passed explicitly.

⚠️ **Declared in advance, and this is the one prediction that can be wrong:** the injection is a
UNIFORM additive shift on the treated rows, so it may make the designation-aware arms simultaneously
strong NEAR-CLONES. Under MLB-HV2-1's mechanism that raises PBO and inflates `V`. `pbo` is not in
the per-arm table, so the control's field-level-gate detector should report nothing there; if it
does, that is a defect in this registration and will be reported as one.

⚠️ **A uniform additive injection is a structural NO-OP on a rank-based field statistic** (NF-INJ2b):
CSCV/PBO ranks arms within each in-sample half, so adding the same constant to every treated arm
cannot re-order them among themselves. That is stated forward so the control's PBO leg is read as
INERT rather than as a passed check.

---

## 5. What the expected result is, said in advance

⭐ **Stating the expected outcome forward is what makes it unable to function as a discovery.**

Under the honesty clause, the expected result is: the seven statistical gates reproduce NF-INJ4's
figures **exactly** (same field, same folds, same seed, same substrate), and the two anchor clauses
**PASS** — Clause A because NF-INJ4 measured four pairs ACTIVE, Clause B because it measured
`oracle ≤ control` on every one of them, with three pairs INACTIVE and therefore uninformative.
**Nine of nine gates pass and the study SHIPS**, subject to the deploy-held gated path in §7.

⛔ **If that is what happens, the record says exactly that and no more.** It is not a confirmation,
a replication, or independent evidence. The mechanism's evidence is NF-INJ4's; this study's
contribution is that the evidence is now held under a registration whose anchor clause measures an
arm property instead of a fold size.

**What would make it a real finding rather than a formality:** the run failing to reproduce, or an
anchor clause failing, or the invariance declaration being refuted by the ladder. Any of those would
be genuinely new, and each is reported as such.

---

## 6. What a null means here, and the re-test

`cv_power.classify_null` is called in the registered order with `declared_field_size = 7`,
`pbo_application = "field"` and `degenerates_excluded_from_v = True`.

**The named re-test is the 2026 season** — designations accrue weekly from Week 1 (2026-09-09), so a
second season roughly doubles the depth and makes season-transfer measurable for the first time.
(This design certifies "does the population distribution generalise to unseen PLAYERS", never "to an
unseen SEASON"; grouped-by-player folds also share weeks between train and test. Both limitations
are NF-INJ4's, restated, and neither is fixable at this depth.)

⚠️⚠️ **THE DEPENDENCY, NAMED AND MEASURED AT REGISTRATION TIME RATHER THAN INHERITED.** The 2026
re-test and every downstream monitoring use of this model require the **NF-W0a weekly injuries
capture to be RUNNING on a weekly cadence**. Measured today (`nf_inj4b_substrate_vintage.json`,
2026-09-04): `nfl/pit/injuries` holds **12,136 rows, ALL season 2025, from exactly ONE capture date
(2026-08-05), and ZERO rows for 2026** — a post-season backfill, unchanged since NF-INJ4 measured
it. **The capture has fired once, ever.** Operator enablement is flagged on the PIT-capture Sprint
card; it is an operator lane, not a modelling assumption, and stating it is what keeps the re-test
trigger from being the actively-misleading kind (NF-D18).

---

## 7. Application semantics and the gated ship path — all deploy-held

**Registered forward, unchanged from NF-INJ4 §7, and restated only where this story acts on it.**

`compose_availability_caps` is IMPLEMENTED and ASSERTED but **deliberately NOT WIRED**: NF-INJ4
landed it with a guard PINNING its absence, because putting an uncertified branch into the shipped
availability owner is the wired-not-invoked hazard. **Wiring it is a ONE-LINE change, and the
absence guard flips to a PRESENCE guard in the SAME COMMIT that wires it — never before, and never
after.**

- **One owner, no second discount path.** `new_games = min(current, current × (SEASON_GAMES −
  E[spell]) / SEASON_GAMES)`, reusing the SAME remaining-season rate the shipped reported-absence
  cap already uses.
- **DISJOINTNESS — the single strongest applicable discount, NEVER a stacked one.** Three channels
  can touch `proj_games` (formal roster-status cap, this designation cap, curated news cap); exactly
  one is recorded as the applied owner. The invariant is re-asserted on a CONSTRUCTED both-channels
  row: the composed answer is **9.06** where the stacked one would be **7.83** — the stacking the
  NEWS-1 rule exists to prevent, arriving through a third channel that rule predates.
- ⛔ **SCOPE: REGULAR-SEASON designations only.** The fitted population is 2025 REG weeks 1–18; a
  PRESEASON tag is out-of-population and gets nothing. **A counterfactual board built before Week 1
  may move almost nothing** — the value arrives with the Week-1 report (2026-09-09). The
  counterfactual is MEASURED, not asserted.

**The gated ship path, fired only if §4 clears, in this order** — the publish decision is the
operator's:

1. Counterfactual board rebuild against a **capture-pinned** baseline, using NF-INJ2c's
   representation-tolerant pin semantics (`≤` evaluated with an explicit epsilon `1e-9`, strictly
   below the artifact's quantum and strictly above accumulated ULP) and its **vintage-match
   preconditions** — a pin whose market inputs are a different day is not a pin.
2. **Population-scoped material diff at 1e-9, NEVER bitwise** — the rookie band is not bitwise
   reproducible at the same commit, so rookie-band motion is read against the ≥5-draw envelope.
3. Whole-board placement read + interval revalidation via `--out` stems.
4. Operator packet: **top-25 moves per config INCLUDING superflex** (a per-position level change is
   NOT shielded there — NF-TR2b), plus the per-designation magnitude table.
5. Combined read on the EXACT publish-candidate board.

**If it ships**, `test_nf_c9_designation_disclosure.py` needs a DELIBERATE amendment — it pins that
the model's availability path never reads the weekly designation, which is exactly the property this
story changes. It is re-anchored onto the new implementation, ⛔ never weakened or deleted (MH2.7).
And **NF-C9's user-facing copy is a NAMED follow-up**: "we hold the designation and do not price it"
becomes FALSE the moment the discount is live.

---

## 8. Disclosure — what had been run when this document was committed

**The substrate rebuild and its vintage check (§0), and `validate_sign_certifiability` (§3).**
Neither scores an arm: the first assembles the frame and proves it is NF-INJ4's, the second is a
design check on fold counts that consumes no outcome. The registration module imports cleanly and
its self-assertions pass.

⛔ **No arm, anchor, gate, deflation statistic or positive control had been run under this
registration when this document was committed.** ⚠️ And it must be said plainly that this study's
disclosure burden is unusual and LOWER than a normal one in a way that does not flatter it: the
numbers are already public in NF-INJ4's record, so there is nothing here a pre-registration could
protect against. **That is exactly why §5 states the expected result forward** — where a
registration cannot prevent foreknowledge, the honest substitute is to write the expectation down
where it can be checked against what happens.
