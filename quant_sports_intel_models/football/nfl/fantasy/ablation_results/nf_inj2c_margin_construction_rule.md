# NF-INJ2c node 3a — THE MARGIN CONSTRUCTION RULE

**Committed BEFORE the node-3b re-measure runs, and before any arm is scored.** ⛔ Not edited
afterwards; anything the re-measure or the decisive run overturns is left here verbatim under a
`SUPERSEDED` marker in the REPORT (E2.1-r / NF-W7f).

> **WHY THIS DOCUMENT EXISTS, AND WHY IT COMES FIRST.** The PM's re-scope ruling 3 makes the
> give-back re-measure a PREREQUISITE of the pre-registration. That re-measure necessarily shows the
> ARM's numbers. Margins written afterwards would be reverse-engineered from the result — the
> E2.1-r inversion, in the one place this story is most exposed to it, because a "strict dominance"
> claim is exactly a claim about margins. So the RULE by which every forward margin is derived is
> fixed here, in advance; node 3b then fills in the SERVED INCUMBENT's baseline THROUGH this rule.
>
> The PM's own pre-committed branch is what makes the sequencing safe in both directions:
> *"If the re-measured dominance no longer holds on any dimension, that is a NULL, not a margin to
> adjust."*

`best_alpha = 0`. Nothing here serves. `nf_inj2b_rate_ordering.SERVED_ARM` stays `None` and
`assert_coherent()` refuses a flag flip the record does not support.

---

## 0. The disposition being registered

PM ruling 2, verbatim: *"THE REGISTERED SHIP ROUTE is the STRICT-DOMINANCE disposition, alone:
`stratified` vs the SERVED incumbent, forward margins on EVERY measure — violations/fold, worst-×,
give-back %, CRPS, per-position ordering, interval floors — improve-or-tie everywhere, regress
nowhere. Coherence is MEASURED AND REPORTED (both residual populations), never gated at zero."*

⭐ **STRICT DOMINANCE IS THE ONE DISPOSITION SHAPE WITH NO TUNABLE THRESHOLD**, which is why it can
be registered honestly after a node-1 refutation. "Improves or ties on every measure and regresses
on none" needs no bar to be chosen. The ONLY quantity that has to be defined is the **TIE BAND** —
what separates a tie from a regression — and that is what this document fixes.

## 1. THE RULE ITSELF

Every tie band is one of exactly three things. ⛔ Nothing else is admissible, and in particular ⛔ no
band may be derived from an observed arm-vs-incumbent gap:

* **(R1) AN ESTIMATOR'S OWN STANDARD ERROR** — for a measure that is an average over folds, the tie
  band is the standard error of that measure's own per-fold series. This is a dispersion quantity
  fixed by the design (the fold count and the measure), ⛔ not a threshold chosen to reach a
  verdict. It is NF-INJ2b's own convention, adopted verbatim: its ±0.0837 CRPS band is "the per-fold
  SE of the winner's own lift".
* **(R2) THE MEASUREMENT'S RECORDED PRECISION** — for a measure taken on ONE fixed board, where
  there is no sampling to average over, the tie band is the precision at which the quantity is
  recorded. Board-level figures carry no sampling error; their uncertainty is BOARD VINTAGE, and
  that is controlled by the capture-pin (node 3b), not by a band.
* **(R3) AN EXISTING PRE-REGISTERED GATE, REUSED VERBATIM** — where NF-INJ2 or NF-INJ2b already
  registered a test for this exact quantity, that test is reused unchanged, at the same bar. This
  story supersedes no gate and relaxes none (E2.1-r).

**A measure with no admissible band is not a dominance measure**, and must be reported as
DISCLOSED-ONLY rather than folded into the verdict. That is stated now so the choice is not made
later, when it would be visible which side it helps.

## 2. THE MEASURES, EACH WITH ITS RULE AND ITS DIRECTION

Declared before any of them is read on a fresh board.

| # | measure | better is | tie band | rule |
|---|---|---|---|---|
| M1 | CRPS mean lift vs incumbent, over the registered folds | higher | SE of the arm's own per-fold lift series | R1 |
| M2 | coherence violating players per fold (attribution-controlled) | fewer | SE of the per-fold PAIRED difference (arm − incumbent) | R1 |
| M3 | worst breach as a multiple of the envelope (`max times_over`) | lower | 0.01 — the precision `times_over` is recorded at | R2 |
| M4 | injury give-back, as `max(give_back_pct, 0)` (see §3) | lower | 0.01 pp — the precision `giveback_pct` is recorded at | R2 |
| M5 | draftable-tier Spearman ρ, per position | higher | NF-INJ2's registered test, verbatim: one-sided paired t on the per-fold (incumbent − arm) deltas, BH-corrected across the four positions at q = 0.10 | R3 |
| M6 | per-group interval coverage | clears its floor | NF-D22 `power_floor()` from each group's n and the pre-registered false-reject target — ⛔ never a flat nominal point-floor | R3 |

**The verdict rule.** `stratified` DOMINATES iff, on **every** measure M1–M6, it is better than the
served incumbent by more than that measure's tie band, or within it. A single measure worse than the
incumbent by more than its tie band is a **regression**, and by PM ruling 3 that is a **NULL** —
⛔ never a band to widen, a measure to drop, or a dimension to re-classify as disclosed-only.

## 3. TWO MEASURE DEFINITIONS THAT ARE JUDGMENTS, DECLARED NOW SO THEY ARE REVERSIBLE

Both are choices about what the measure MEANS, not about where a bar sits. They are stated in
advance and flagged for the PM, ⛔ not settled quietly later.

**(a) M4 is `max(give_back_pct, 0)`, not the signed figure.** The defect NF-INJ1 named is injured
players being marked back **UP** — a POSITIVE give-back. A negative give-back means flagged players
project DOWN relative to MVP-1, which NF-INJ2's own record calls "a modelling opinion the board is
entitled to hold", ⛔ not a further improvement on this axis. Scoring the signed value would let an
arm bank credit for over-discounting, which is a different defect wearing this measure's clothes.
⚠️ The SIGNED value is reported beside it on every arm, always.

**(b) M2 is attribution-controlled**, i.e. violations `mvp1_null` also produces are subtracted —
NF-INJ2's convention, because a defect present with the ordering step switched OFF is not caused by
the ordering step. Measured on node 1's populations this subtracts nothing (`mvp1_null` = 0 on all
seven folds), so it is inert here; it is declared because an inert control must be stated, not
discovered (NF-D20).

## 4. WHAT IS MEASURED AND REPORTED BUT ⛔ NOT GATED

PM ruling 2: *"Coherence is MEASURED AND REPORTED (both residual populations), never gated at zero."*

The node-1 residual table — worst ×, min games on a violating row, and the share of violating rows
under 2 expected games, per arm — is reported in full. It carries **no bar**. The reason is node 1's
§4 bound and it is licensing evidence, not an excuse: the envelope is a per-STAT ceiling while every
assignment rule permutes a per-PLAYER aggregate, so no arm in this family can reach zero, and a gate
demanding it would be refusing on a structural impossibility. M2 and M3 are how coherence enters the
verdict — as DOMINANCE against the incumbent, not as a distance from zero.

## 5. PRE-COMMITTED OUTCOMES

Written now so no branch can be chosen once the numbers are visible.

1. **Dominance holds on M1–M6, and the standing deflation gates (PBO, DSR, BH-FDR, fold consistency)
   pass** → SHIP under the dominance disposition, deploy-held for the operator, with the node-6
   disclosure PM ruling 5 requires.
2. **Dominance fails on any one measure by more than its own tie band** → **NULL**. PM ruling 3,
   verbatim: *"that is a NULL, not a margin to adjust."*
3. **The node-3b re-measure cannot be taken** (no capture-pinnable board, or the pin fails) → the
   run is **VOID**, not a null: a dominance claim against a board nobody is served is not a
   measurement (the D3 convention, and the reason ruling 3 exists).
4. **A deflation gate is evaluated and fails while M1–M6 dominate** → `DEFLATION_REFUSED`, read
   against the positive control, with the DSR 2×2 computed as a labelled diagnostic BEFORE any
   remedy is named (NF-W7f), and the lockstep invariant checked (NF-W8-0d). ⛔ If the winner is
   `V`'s largest contributor the field-trim reading is INADMISSIBLE (NF-W7h) — say so a fortiori
   rather than quoting a trimmed number.
5. **DSR at 8 folds does not clear 0.95** → that is branch 4, and PM ruling 4 already says so:
   *"DSR at 8 folds is then a real gate, not a formality — 0.9325 at 7 does not guarantee 0.95 at
   8."* ⛔ No further fold trigger may be published for it without the lockstep check first.

## 6. SEQUENCING, so the record shows the order events actually happened in

1. **This document** — committed. (node 3a)
2. **The capture-pin + re-measure** — a fresh board and its market snapshot captured, pinned, and
   the incumbent's M2/M3/M4 baseline read off it. (node 3b)
3. **The +1 fold data-fidelity finding** — stated either way. (node 3c)
4. **The pre-registration** — quoting the re-measured numbers, with every margin derived through
   §1–§2 above. (node 3)
5. **The decisive run.** (node 4)

⛔ Nothing in steps 2–3 may change §1, §2, §3 or §5. If something there turns out to be
unworkable, it is recorded as a defect in this rule and the story returns to the PM — the rule is
not quietly edited to fit what the re-measure showed.
