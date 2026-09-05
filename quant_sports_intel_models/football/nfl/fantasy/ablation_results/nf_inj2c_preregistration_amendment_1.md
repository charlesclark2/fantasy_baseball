# NF-INJ2c — PRE-REGISTRATION AMENDMENT 1: the positive control's null leg

**Committed BEFORE PR #1084 merges and BEFORE the decisive run.** Authorised by the PM ruling on
decision request #6 (2026-09-05), D1.

`best_alpha = 0`. Nothing here serves. `SERVED_ARM` stays `None`. DEPLOY-HELD throughout.

---

## 0. WHAT THIS AMENDS, AND WHAT IT DOES NOT TOUCH

| document | status under this amendment |
|---|---|
| `nf_inj2c_margin_construction_rule.md` (node 3a) | ⛔ **UNTOUCHED.** No band, no measure, no direction, no pre-committed outcome is altered. |
| `nf_inj2c_preregistration.md` §7 | ⛔ **VERBATIM AND UNEDITED**, including its measured-false PLAT-CVP2 premise (NF-W7f). This document does not correct it; it declares how §7's control is READ. |
| `nf_inj2c_preregistration.md`, every other section | ⛔ **UNTOUCHED.** |
| the base prereg's header | one **AMENDMENT LOG** pointer added, so no reader can reach §7 without learning this exists. It changes no declaration. |

⛔ **This amendment can only REFUSE, never RESCUE.** Every clause below either leaves the
disposition where it was or blocks it. There is no branch on which this document makes a ship
easier to reach than the base registration made it. That is the property that makes an amendment
written after a measurement admissible at all, and it is checkable rather than asserted: clause (b)
adds a gate, clause (a) removes an *uninformative* badge from the reading without removing any gate,
and clause (a)'s own scope carve-out in §3 adds a second gate.

## 1. THE PROVENANCE CLAIM, STATED NARROWLY BECAUSE IT IS NARROWER THAN THE BASE PREREG'S

The base pre-registration claims it was written blind to node 3b. **This amendment cannot claim
that, and does not.** Node 3b has run; this session has seen its board figures.

What this amendment claims instead, and what is checkable:

1. **It quotes no figure from node 3b**, and a guard extracts that report's distinctive figures and
   asserts none appear here — the same test the base prereg carries.
2. **Its basis is the INSTRUMENT'S SOURCE, not any measured value.** The entailment in §2 is read
   off `cv_power.injected_effect_positive_control` and this study's own `gate_table`. It would hold
   identically if every arm score were different, and it was derivable before node 3b ran.
3. **The decisive run's numbers do not exist.** `nf_inj2c_decisive.{json,md}` is absent at this
   commit, and the guard asserts that absence. That is the blindness that matters here: this
   document fixes how a control verdict is read, and the control verdict has not been computed.

## 2. THE BASIS — A SOURCE-MEASURED ENTAILMENT

`injected_effect_positive_control(check_null_control=True)` runs a null leg at `inject(0.0)`.
This study's injector returns **the real payload unchanged** at zero effect, which is what "no
INJECTED effect" means. The instrument then reads any arm surviving that payload as *the family
certifies noise* and returns **`VACUOUS`**, a verdict with the **highest precedence** of any it
returns and one that is **partition-free** — so nothing §7 declares can reach it.

The gates in this study's `gate_table` are M1–M6 plus `fold_consistency` and `dsr`. Those are
exactly the conditions the SHIP disposition requires of `stratified`. Therefore:

> **the study SHIPS ⟹ `stratified` clears every gate on the real payload ⟹ `stratified` is a
> null-leg survivor ⟹ the control returns `VACUOUS`.**

The badge is not correlated with the ship condition; it is **entailed** by it. A verdict entailed by
the outcome it is supposed to inform carries no information about that outcome.

⭐ The instrument's assumption, once stated, is visible: the null leg is a noise test **only when the
real data is believed to contain no effect**. That holds for a study expecting a null. It cannot
hold for a study whose H1 asserts the real data contains the effect. NF-INJ2b never reached this
branch because `coherence_restored` blocked every arm — the gate PM ruling 2 removed here.

## 3. (a) THE DECLARATION, AND ITS SCOPE

**The null-leg `VACUOUS` verdict is declared INAPPLICABLE to this study's gate family**, on the
basis quoted in §2.

⭐ **SCOPED, ⛔ not a blanket waiver.** The §2 entailment covers a survivor set consisting of the
PRIMARY or other non-degenerate arms — those are the arms H1 predicts will clear. It says **nothing**
about a **DEGENERATE**. `mvp1_null` or `random_order` clearing every gate on the real payload is not
entailed by H1, is not explained by this declaration, and is a genuine alarm about the gate family.

⇒ **The declaration applies only when the null-leg survivor set contains no declared degenerate.**
A degenerate among the null-leg survivors is a control **FAILURE** (§4), and this declaration does
not reach it.

## 4. (b) THE BINDING SUBSTANCE — THE INJECTED LEG, AND IT CUTS BOTH WAYS

**The control's binding substance for this study is the INJECTED leg's recorded content.** PM ruling
D1, verbatim: *"the declaration re-scopes the control, it never waives it."*

The control **FAILS** — and a failure blocks the disposition regardless of any badge — if **any** of:

| # | condition | why it is a failure |
|---|---|---|
| F1 | no arm clears every **injection-MOVABLE** gate under injection (`metric_survivors` empty) | the planted effect was not detected; a null from this family would be free (BLIND) |
| F2 | a declared **DEGENERATE** is among the injected leg's survivors | the family passes an arm registered to lose |
| F3 | a declared **DEGENERATE** is among the **null** leg's survivors | §3's carve-out — an alarm the declaration does not cover |
| F4 | the control did not run, or its record is missing the keys above | an unevaluable control is ⛔ never a pass (NF1.7 (a)) |

`metric_survivors` — arms stopped by no gate the injection could MOVE — is the right reading and not
a convenience: charging an arm's failure on an INJECTION-INVARIANT gate to the family's *sensitivity*
is PLAT-CVP2 defect 1, the defect NF-INJ2b's `BLIND` badge was earned by.

⭐ **F1 IS *INACTIVE*, ⛔ NOT FAILED, WHEN A GATE IN THE TABLE IS UNDEFINED AT THE FOLD COUNT**
(added 2026-09-05, BEFORE PR #1084 merged and BEFORE the decisive run — found by the 2-fold
code-path smoke, and checkable: §1's guard asserts the decisive artifact does not exist at this
commit). At n ≤ 2 the calibrated fold-consistency clause declares itself UNDEFINED (MH2 H8: `2⁻ⁿ`
already exceeds α), so it is False for **every** arm, `metric_survivors` empties **structurally**,
and F1 fires for a reason with nothing to do with the family's sensitivity. Reporting that as *"the
family did not detect a planted effect"* would be untrue (NF-D20: count the folds the mechanism can
ACT on; NF1.9: a mechanism that cannot act is a finding, not an omission).

⛔ This changes the **REASON**, ⛔ never the **OUTCOME** — an inactive F1 returns `UNEVALUABLE`,
which blocks exactly as `FAILS` does, so the clause stays REFUSE-ONLY. ⛔ And it never reaches
**F2/F3**: a degenerate clearing every gate is an alarm at any fold count and is not a fold-count
artifact, so the carve-out is conditioned on F1 being the *only* failure. The registered **seven**
folds define the clause (6 wins required), so F1 is a real test there.

**The verdict wiring.** A control failure yields the disposition state **`CONTROL_REFUSED`**, which
takes precedence over `DEFLATION_REFUSED` and over `DOMINATES`. A family that cannot certify a
planted effect makes every gate reading downstream of it moot, so the control is read FIRST; the
deflation gate results are recorded in full beside it either way, so the ordering loses nothing.

⚠️ **This is a TIGHTENING of node 3a §5 outcome 1**, which conditions SHIP on M1–M6 plus the
deflation gates and does not mention the control. §5 is not edited, and the added clause can only
refuse — so it is not a change that could benefit the arm, which is the only direction an
after-the-fact edit to a registration could be laundering in.

## 5. (c) THE BADGE IS RECORDED VERBATIM, AND §7's BAN STANDS

1. The instrument's verdict string is recorded **verbatim**, beside this declaration, whatever it is.
   Both readings of a `VACUOUS` badge stay on the record; the declaration says which one BINDS, and
   ⛔ does not delete the other.
2. **§7's ban is untouched**: the control is ⛔ **never** re-run with `check_null_control=False` to
   obtain a nicer badge (E2.1-r). The null leg RUNS, every run, and its survivor set is recorded —
   which is what makes §3's degenerate carve-out enforceable rather than decorative.
3. `null_leg_declaration_applies` is recorded as an explicit boolean, so a reader can see whether
   the declaration reached this run's badge or whether §3's carve-out fired.

## 6. THE LIFECYCLE THIS SITS IN

PM ruling D1, on the record: **(C) — an advantage-removed null construction, plus a declared
study-shape input under which the current leg reports its own `NULL_LEG_INAPPLICABLE` state — is the
true fix and is CARDED as PLAT-CVP3 (defect 5 of the instrument family). This story does not wait
for that build.**

PLAT-CVP2's retirement of the annotate-around rule covered **the four defects it fixed**, not
defects discovered after it shipped. A fifth defect necessarily gets the annotate-with-measurement
treatment until PLAT-CVP3 lands. This annotation is declared **BEFORE the number exists**, which is
strictly stronger than NF-INJ2b's, which was written at the point of reading.

## 7. WHY (A) — "VACUOUS IS DISQUALIFYING" — WAS REJECTED, RECORDED SO THE CHOICE IS AUDITABLE

PM ruling D1, verbatim in substance: a control that **structurally cannot support any shipping study
of this shape** is the unachievable-gate family (E9.61's strict-pin boundary; NF-INJ4's oracle). The
refusal it entails is **vacuity pointed in the punishing direction, not rigor**. The program refuses
gates that cannot FAIL *and* gates that cannot PASS.

⛔ Recorded here rather than left implicit, because "the stricter option" is the one a later reader
will assume was the safe one.
