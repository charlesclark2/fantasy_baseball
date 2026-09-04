# NF-INJ4 — closeout: `CONSTRAINT_REFUSED`. Nothing ships.

**`best_alpha = 0`. DEPLOY-HELD. The served availability discount for a weekly Questionable /
Doubtful / Out designation remains EXACTLY ZERO.** The gap NF-C8 traced is still open, and this
record says precisely how far the fix got and what stands between it and a ship.

| record | what it is |
|---|---|
| `nf_inj4_data_census.md` | node 1 — the data census, run BEFORE the registration |
| `nf_inj4_preregistration.md` | the registration, committed before any scoring |
| `nf_inj4_designation_duration.{json,md}` | the decisive run |
| this file | the verdict, the findings, and what a successor should do |

---

## 1. The verdict in one paragraph

A weekly designation carries real, large, honestly-measurable duration signal. Fitted as an
empirical conditional distribution and scored against a matched status-blind foil, the winner
(`desig_x_practice`) is **+0.1408 CRPS on 10 of 10 folds, one-sided p = 0.0**, clearing both the
binding single-hypothesis cutoff and the conservative arm-corrected one. PBO is **0.000** over the
declared field *and* the eligible set, Bailey performance degradation **0.000**, the
leave-one-fold-out flip distribution puts **10/10** on one arm, DSR-CONV is **0.9999**, the
permutation anchor is beaten and both degenerates lose. **Seven of the eight registered gates
pass.** The study is refused by the eighth — a pre-registered ANCHOR clause — and the refusal is a
statement about how that anchor was built, not about the mechanism.

---

## 2. What refused it, decomposed rather than re-labelled

`oracle_respected`, as registered, reads *"no arm beats its OWN-FORM oracle"*. It **FAILS on all
three shippable arms**. Per NF-D20 a failing pre-registered anchor is left failing and decomposed:

| clause | result |
|---|---|
| naive: `arm_crps ≥ own_form_oracle_crps` | **FAILS** 3/3 |
| NF1.9 (f): `own_form_oracle_crps ≤ matched_n_control_crps` — the floor at equal family **and equal resolution** | **PASSES** on every active pair |

The peek is a genuine peek — it beats an honest fit at its own `n` — but it is fitted on a **~131-row
test fold against arms trained on ~1,178 rows (a 9.0× resolution ratio)**, and `MIN_CELL_N = 30`
collapses most of its conditioning to the pooled distribution at that size. So the naive clause is
measuring **the oracle's sample size**, not any property of an arm: the NF-W7i
capacity-starved-ceiling shape. An arm beating a label-seeing oracle here can only be **capacity**,
never leakage — the arms are fitted strictly on training rows disjoint by player.

**⛔ The remedy is an ANCHOR DESIGN, not data.** That ratio is fixed by the CV design, so no fold
count and no season count moves it. The null is classified `CONSTRAINT_REFUSED` with
`binding_half = "anchor"` and **no data re-test trigger** — publishing "come back with more seasons"
here would be exactly the misleading direction NF-D18 exists to stop. `classify_null` has no state
for a deterministic-constraint refusal, so its own output is preserved verbatim beside the verdict
rather than overwritten.

**⛔ The clause was not re-read after it failed.** The registration is unedited. The decomposition is
reported and rescues nothing — re-reading the gate against its NF1.9 (f) half now would be the
E2.1-r inversion in its most literal form.

---

## 3. The positive control, and the badge that would mislead a reader

`injected_effect_positive_control` returned **`BLIND`** — "a null from this family is free" — with
`partition_source = "gate_classes"` and `partition_verified = true` (the explicit declaration, not
the name heuristic; this registration is one of the two named triggers for retiring it, and it
exercised the declared path). The blocking gate, for every arm, is `oracle_respected` alone.

That badge is correct as returned and **misleading in substance**, so the claim behind it was
MEASURED rather than argued: across a ladder of planted effects (0, 0.5, 1, 2, 4 games)
`oracle_respected` is **FALSE at every rung**. It cannot be made to fire by the injection, so an arm
blocked by it alone cleared everything the control could move — the substance of
`CONSTRAINT_BLOCKED`.

**⛔ The `BLIND` badge STANDS.** This registration declared only `degenerates_lose` injection-invariant,
and its own §6 says verbatim that a gate may not be reclassified as invariant after seeing that it
blocked. The reclassification is a **finding for the successor**, never applied here.

⚠️ The sweep's own first cut was non-discriminating and is fixed in place: a boolean gate already
`True` at effect 0 has nowhere to move, so "did it change?" reported seven *passing* gates as
"invariant in fact". It now separates `always_passes` / `always_fails` / `moves_with_the_effect`, and
only `always_fails` is read. (NF-D20's "count what the mechanism could act on", applied to the
diagnostic itself.)

---

## 4. Findings the run produced that outlive the verdict

- **The NF-D11 inversion, on live data.** MAE would have selected `fixed_penalty` — the one arm this
  registration forbids — while CRPS selects a real one. The forbidden metric picks the forbidden
  arm; the metric choice is validated rather than assumed.
- **DSR-CONV, worked.** The degenerate `always_max` drives *whole-field* DSR to **0.000** against
  DSR-CONV's **0.9999**, and inflates the whole-field spread to **1558%** against a **3.7%**
  contender spread. NF1.8's "a spread over a field containing its own nulls measures the nulls",
  with numbers. ⚠️ The exclusion remains non-monotone and is not a lever.
- **`doubtful` is structurally unmodelled.** 29 rows against `MIN_CELL_N = 30`, so it *always* backs
  off to the pooled distribution and the model treats a Doubtful player as an average
  injury-report player. The backoff is doing exactly what it was registered to do.
  ⛔ **The 29-vs-30 near-miss must not become a reason to lower the threshold** — that is
  reverse-engineering a design constant from the answer.
- **The resolution sensitivity is INACTIVE**, as the census predicted: all 18 conflicting
  player-weeks resolve identically under both rules, because designations only ever escalate. Its
  agreement carries no information and is not scored as a pass.
- **The revision clause is INACTIVE** — no store subject holds more than one capture, so it had
  nothing to act on. Reported so "it did not fire" is never read as "it passed".

---

## 5. Application semantics — implemented, asserted, deliberately NOT wired

`compose_availability_caps` takes the **single strongest** cap and records exactly one owning
channel; `remaining_season_rate_cap` reuses the shipped news-cap rate verbatim rather than
re-deriving it. The disjointness invariant is asserted on a **constructed both-channels row**: the
composed answer is **9.06** where the stacked one would be **7.83** — a materially different number,
and the stacking the NEWS-1 rule exists to prevent, arriving through a third channel that rule
predates.

**⛔ None of it is wired into `season_projection`.** Putting an uncertified branch into the shipped
availability owner for a refused model is the wired-not-invoked hazard, and a guard pins that
absence. Wiring it is a one-line change made only under the gated ship path.

⚠️ **Scope for whoever does wire it:** the fitted population is REGULAR-SEASON designations. A
preseason tag is out-of-population and gets nothing, so **a counterfactual board built before Week 1
may move almost nothing** — the value arrives with the Week-1 report (2026-09-09).

---

## 6. What a successor should do

1. **Re-register the oracle floor at MATCHED RESOLUTION and re-run.** Every statistical gate already
   passes and the decisive run costs ~1 second, so this is a registration fix, not new modelling.
   ⚠️ It must be a FRESH FORWARD registration, and ⛔ it must not inherit this run's DSR/PBO
   figures — `V` is a sample variance over the field's trial Sharpes and moves non-monotonically
   with membership (MH2.2 / NF-INJ3 §0a).
2. **Declare the anchor-clause family forward**, the way `degenerates_lose` was. This registration
   declared the NF-W6d *inactive-pair* reading forward — and it fired correctly on three arms — but
   not the NF1.9 (f) *capacity* reading. They are two different guards, and registering one does not
   give you the other. That is the transferable lesson.

Findings 3-5 in the spec's `closeout.followUps` (the ESPN one-week-late attribution, the
once-fired forward capture, and the scope/`doubtful` notes) are PM triage, not this story's to card.
