"""rookie_publish_policy.py — NF-D21: the RECORDED PM DECISION to publish NF-D16's rookie-point
level recalibration at a board-blind global shrink λ = 0.5.

════════════════════════════════════════════════════════════════════════════════════════════════
🚨 READ THIS FIRST: THIS FILE IS A DECISION RECORD, NOT A SELECTION RESULT
════════════════════════════════════════════════════════════════════════════════════════════════
λ = 0.5 was NOT selected. No search produced it, no metric ranked it first, and no fold chose it.
It is the MIDPOINT of the shrink family's own declared interval — a number available before any
result existed — applied by an explicit PM decision (operator, 2026-08-04) after NF-D20 closed the
only statistically legitimate selection path.

The distinction is the entire point of the file, so it is worth stating precisely why it matters
here rather than leaving it to a changelog line:

  · NF-D16 RATIFIED a per-position affine level recalibration of the rookie point (pooled
    draftable-tier MAE 1.0738 → 0.9407 over seven held-out draft classes, 7/7 positive, PBO 0.029,
    DSR 0.996, p 0.0033, pooled bias −20.87 → −5.41 PPR). It was HELD from publish because at
    λ = 1 it lifts the top rookie RB to overall rank 6, breaching NF1.4's placement clause.
  · NF-D18 tried four differently-SHAPED attenuations. All four failed; three placed the top rookie
    WORSE. Its load-bearing finding: **the constraint was never the binding problem, the SHAPES
    were** — a plain global shrink clears the cap at λ = 0.75, retaining 81.5% of the gain.
  · ⛔ BUT 0.75 WAS FITTED TO THE 2026 BOARD WITH THE ANSWER IN VIEW. Pre-registering it would be
    the E2.1-r inversion wearing a successor's badge, which is why `NF_D20_FRONTIER_LAMBDA` below
    is recorded as a value this policy MAY NOT USE, and a guard test enforces that.
  · NF-D20 then ran the legitimate version — select the shrink IN-FOLD under a per-fold whole-board
    placement constraint — and it came back **`CONSTRAINT_REFUSED`**: every recalibrating arm beat
    the incumbent on the metric and every one was refused by the constraint out of sample, while a
    BLIND constant satisfied the constraint on every board. Its own §6a disclosure states the
    verdict rests on one arm's ELIGIBILITY, not on any gate level.

⇒ The honest options NF-D20 left were (i) a PM decision to publish a fixed conservative shrink,
owning that the constant came from judgement, (ii) a board-free shrink ESTIMATOR, or (iii) accept
the null. **The operator chose (i).** This file is that choice, written down, with the property
that makes it defensible baked into the artifact rather than into prose:
`statistically_selected = False`.

⚠️ WHAT MAY AND MAY NOT BE SAID ABOUT THIS PUBLISH
  ✅ "a board-BLIND CONSERVATIVE rookie-point recalibration chosen by JUDGMENT, evidenced accurate
      and cap-respecting OUT-OF-SAMPLE on every held-out board"
  ⛔ "selected", "optimised", "the best shrink", or any framing implying a search produced 0.5.
  ⛔ any market/edge claim. `best_alpha = 0`; this is a projection product.

════════════════════════════════════════════════════════════════════════════════════════════════
CURRENT STATE (NF-D21-PUBLISH, 2026-08-20): SERVING — `DISPOSITION = "SHIP"`, λ = 0.5
════════════════════════════════════════════════════════════════════════════════════════════════
The flip is ON. It spent 2026-08-05 → 2026-08-20 held `False` after the `interval_floors` gate
refused it, and it moved only because NF-D22 REPLACED that gate's rule — a power-derived floor
derived from n and NF1.8's own pre-registered false-reject target, with no coverage argument to
tune. ⛔ The floor was not moved to clear this: read the full sequence, the prohibitions NF-D22 was
held to, and the rollback contract at `DISPOSITION` and `SERVING_ENABLED` below — in that order,
which is the order it happened in.

════════════════════════════════════════════════════════════════════════════════════════════════
THE EVIDENCE BASE (NF-D20-measured — cited as evidence, never as a selection)
════════════════════════════════════════════════════════════════════════════════════════════════
At λ = 0.5, over the seven held-out draft classes 2019–2025:
  · pooled draftable-tier MAE 1.0738 → 0.9949 (Δ −0.0789, ~59% of NF-D16's full-λ gain)
  · pooled universe bias −20.87 → −13.14 PPR (toward zero — the signature a genuine LEVEL
    correction produces, and a per-player one does not)
  · the per-fold whole-board placement constraint is satisfied on EVERY held-out board
  · on the 2026 serving board the best rookie sits at overall rank 12 (λ = 1 would put him at 6)

⚠️ AND THE HONEST CAVEAT ON THAT LAST NUMBER: NF-D20 measured the constraint as INACTIVE on 4 of 8
boards, because the best rookie there is a QB — the one position this correction may not touch. The
2026 board is one of them (its best rookie is a rookie QB at rank 12). So "rank 12 at λ = 0.5" is a
NON-BREACH, and part of why it does not breach is that the correction cannot reach the player
holding the rank. Reporting it as a tight clearance would overstate what was demonstrated.
"""
from __future__ import annotations

from typing import Any

# ── identity ───────────────────────────────────────────────────────────────────────────────────
POLICY_VERSION = "nf_d21_rookie_pm_judgment_v1"
SOURCE_MODEL = "NF-D16"
DECISION_STORY = "NF-D21"
DECIDED_ON = "2026-08-04"
DECIDED_BY = "operator (PM)"

# ── the DISPOSITION — the PM's ANSWER, now a PUBLISH (2026-08-20) ───────────────────────────────
#: ⭐ **`SHIP` — NF-D21 IS PUBLISHED at λ = 0.5** (the vocabulary is `veteran_level_policy`'s, so the
#: two level policies read the same way). The gate that refused it in August has been REPLACED, not
#: relaxed, and the sequence is what makes this admissible rather than a floor moved until something
#: cleared it:
#:
#:   1. 2026-08-05 — the publish was REFUSED by `interval_floors` (rookie RB, 2 covered rows short at
#:      λ=0.5) and the PM CLOSED the story rather than parking it, *specifically* so no follow-on
#:      could feel pressure to fix the floor on NF-D21's behalf. That refusal is preserved verbatim
#:      below as `PREDECESSOR_DISPOSITION` / `PREDECESSOR_RATIONALE` — it is history, not a mistake.
#:   2. NF-D22 then landed the power-derived floor ON ITS OWN MERITS, derived from n and
#:      NF1.8's own PRE-REGISTERED false-reject target (`Φ⁻¹(0.95)`, recorded before any of these
#:      results existed), applied uniformly to every constrained group, with a TWO-SIDED validation
#:      (a truly-nominal band clears at ≥ the target rate AND a materially-short band still fails).
#:      It replaced a rule that rejected a perfectly-calibrated band **0.393–0.500 of the time at
#:      every size** — i.e. the defect was that the old refusals carried almost no information while
#:      still reading as evidence.
#:   3. 2026-08-20 — the PM re-read NF-D16 against the floor now in force and recorded THIS
#:      disposition. λ is UNCHANGED at the board-blind midpoint; nothing was re-selected.
#:
#: ⛔ THE ONE THING THIS MUST NOT BE READ AS: NF-D22 was not motivated by, and may not be justified
#: by, the breach recorded here. NF-D16 clearing at λ=0.5 is a CONSEQUENCE of the new floor, stated
#: as such in NF-D22's own §3 preamble, and it is the reason NF-D22's prohibitions were written down
#: before it ran rather than after.
DISPOSITION = "SHIP"
DISPOSITION_DECIDED_ON = "2026-08-20"
DISPOSITION_REVIEWED_BY = "Charlie (operator/PM)"

#: The rationale as the PM wrote it. Carried VERBATIM into the registry's `validation_report`, which
#: is the named authority for why the served board is what it is — so the reason a user sees the
#: recalibrated rookie point is recorded beside the thing that serves it, not only in a story doc.
DISPOSITION_RATIONALE = (
    "Publish at lambda=0.5: NF-D22 replaced the hard point-estimate coverage floor with a "
    "power-derived one, derived on its own merits from n and NF1.8's pre-registered false-reject "
    "target and validated two-sided — the rule it replaced rejected a perfectly calibrated band "
    "0.393-0.500 of the time at every size. Against the floor now in force NF-D16's ratified lift "
    "(pooled draftable-tier MAE 1.0738 -> 0.9407 over seven held-out draft classes, 7/7 positive, "
    "PBO 0.029, DSR 0.996) clears every per-group coverage floor and all ten NF-G0 gates at "
    "lambda=0.5. lambda is UNCHANGED at the board-blind midpoint: nothing was re-selected, and "
    "NF-D16 clearing is a consequence of the new floor, never its motivation."
)

#: The refused predecessor state, preserved rather than overwritten. A decision record that deletes
#: the refusal it reversed reads as if the gate had always passed, which is precisely the history a
#: future reader needs in order to judge whether this publish was earned or engineered.
PREDECESSOR_DISPOSITION = "CONSTRAINT_REFUSED"
PREDECESSOR_DECIDED_ON = "2026-08-05"
PREDECESSOR_RATIONALE = (
    "Held at incumbent: the rookie-RB interval-floor breach is a coin-flip at n=148 (a perfectly "
    "calibrated band fails this floor 50% of the time), so the honest remedy is a power-derived "
    "floor for structurally-thin groups — carded independently — not moving λ or the floor. "
    "NF-D16's lift is deferred, not abandoned."
)

#: ⛔ STILL `True`, and the reason has MOVED rather than lapsed. It originally recorded that NF-D21
#: was CLOSED rather than "open pending the floor fix" — because a dangling dependency is exactly
#: the pressure that would have biased NF-D22 toward clearing λ=0.5. That worked: NF-D22 was derived
#: and reviewed with NF-D21 explicitly out of scope. The flag now records the mirror-image property —
#: this publish is DECIDED, not provisional-pending-a-rebuild. Either way the field means one thing:
#: **no other story owes this one an output.**
DISPOSITION_IS_NOT_PENDING: bool = True

#: The follow-on, and the discipline that made it admissible. ✅ **LANDED — and it HONOURED every
#: prohibition below, which is the reason this policy was allowed to move at all.** Kept in full
#: rather than summarised: these are the terms the publish above must be audited against, and a
#: reader deciding whether the flip was earned or engineered needs the terms, not a verdict.
#:
#: ⛔ THE PROHIBITIONS WERE THE POINT, NOT THE TASK — and each is checkable in NF-D22's own record:
#:   · derive the floor from **n and a PRE-STATED false-reject target ONLY** — ⛔ ZERO reference to
#:     the 0.7905 measured here. It must be written, reviewed and defensible on that basis alone.
#:     ✅ `coverage_power_floor.power_floor` takes no coverage argument and a guard asserts its
#:     signature never gains one; the target is NF1.8's own pre-registered `Φ⁻¹(0.95)`, recorded
#:     before any of these results existed. NF-D22 §1's claim is that its table could have been
#:     published before any band was ever scored.
#:   · apply it to **ALL structurally-thin groups**, not just the one that failed. ✅ no thin-group
#:     list exists — the floor self-attenuates toward nominal as n grows, so nothing had to decide
#:     where to stop applying it (NF-D22 §1/§1b: the veteran population gets the identical rule).
#:   · **NF-D21 is explicitly OUT OF SCOPE** of that story, and it lands POST-LAUNCH — temporally
#:     separated from this breach so it cannot read as a floor reverse-engineered from the answer.
#:     ✅ NF-D22 published with `SERVING_ENABLED` untouched at `False` and NF-D21 still CLOSED.
#:   · re-gating NF-D21 against whatever floor it produces is a DOWNSTREAM CONSEQUENCE, never the
#:     story's motivation. (It will likely clear at λ=0.5 then — which is precisely why the
#:     motivation has to be independent of that fact.) ✅ it did clear; NF-D22 §3 states the
#:     consequence-not-motivation reading in its own preamble, before the sweep.
#:
#: ⚠️ THE PREDICTION IN THAT LAST PARENTHESIS CAME TRUE, and that is uncomfortable rather than
#: reassuring: it means the only defence against this having been engineered is that the floor is
#: derivable WITHOUT the answer — which is exactly the property NF-D22 made mechanically checkable.
#: Read it there, not here.
FOLLOW_ON_STORY = "NF-D22"  # power-derived fallback floor for structurally-thin groups (post-launch)
FOLLOW_ON_STATUS = "LANDED"  # 2026-08-21 — `nf_d22_exact_binomial_power_floor_v1` is the floor in force

#: Re-selecting the rookie BAND at the λ=0.5 centre (a fresh NF1.8-style §0.5 bake-off) was the other
#: admissible remedy and was REJECTED as dominated: at n=148 with a 50% false-reject rate it can null
#: even when the band is correct, it is the most expensive path, and it buys exactly ONE λ point. It
#: becomes a LAST RESORT only if NF-D22 lands and a breach still stands — never a now-choice.
REJECTED_REMEDY = "re-select the rookie band at the λ=0.5 centre (NF1.8-style §0.5 bake-off)"

# ── the shrink ─────────────────────────────────────────────────────────────────────────────────
#: The shrink family's declared interval. λ = 0 reproduces the incumbent EXACTLY for every form
#: (`rookie_point_recalibration.blend_toward_incumbent`); λ = 1 is NF-D16's ratified affine.
SHRINK_LAMBDA_INTERVAL: tuple[float, float] = (0.0, 1.0)

#: ⭐ COMPUTED FROM THE INTERVAL, NOT TYPED AS A LITERAL. "Board-blind midpoint" is then a property
#: of the code rather than an assertion about a number someone chose — a reader can see that no
#: board, fold or metric could have produced it.
SHRINK_LAMBDA: float = (SHRINK_LAMBDA_INTERVAL[0] + SHRINK_LAMBDA_INTERVAL[1]) / 2.0

#: The value NF-D18 MEASURED on the 2026 board as the frontier. Recorded so the prohibition is
#: explicit and testable: it was fitted with the answer in view and is therefore NOT publishable,
#: however attractive its 81.5%-of-the-gain retention looks.
NF_D20_FRONTIER_LAMBDA: float = 0.75

# ── the stamp ──────────────────────────────────────────────────────────────────────────────────
SELECTION_STATUS = "PM_JUDGMENT"
STATISTICALLY_SELECTED = False

#: Positions the correction may touch. Imported (not re-typed) so this policy cannot drift from the
#: exclusion NF-D14 measured and NF-D15/NF-D16 enforce: ⛔ QB is never recalibrated.
def recalibrated_positions() -> tuple[str, ...]:
    from quant_sports_intel_models.football.nfl.fantasy import rookie_point_recalibration as RC
    return tuple(RC.RECALIBRATED_POSITIONS)


def excluded_positions() -> tuple[str, ...]:
    from quant_sports_intel_models.football.nfl.fantasy import rookie_point_recalibration as RC
    return tuple(RC.EXCLUDED_POSITIONS)


#: ⭐ THE SERVING FLIP. `True` turns NF-D16's opt-in recalibration ON at `SHRINK_LAMBDA`.
#: Setting it `False` restores the pre-NF-D16 rookie point BYTE-FOR-BYTE (the recalibration is
#: opt-in by construction — `fit_rookie_slot_curves` fits nothing without `recal_hist`), which is
#: what makes the rollback proof possible without a second code path.
#:
#: ✅ **`True` SINCE 2026-08-20 (NF-D21-PUBLISH) — and the HISTORY below is why it is admissible.**
#:
#: 🚨 IT WAS HELD `False` FROM 2026-08-04, BLOCKED BY THE INTERVAL-FLOOR GATE. The publish was built,
#: stamped and routed through the NF-G0 pipeline, and the pipeline REFUSED it at the `interval_floors`
#: gate. Measured on the seven held-out draft classes (n = 148 rookie-RB seasons), the rookie **RB**
#: 80% coverage floor read:
#:
#:     λ:        0.00    0.25    0.50    0.75    1.00
#:     RB cov  0.8041  0.8041  0.7905  0.8041  0.8041      (floor 0.80; 119 covered rows required)
#:     covered   119     119     117     119     119
#:
#: λ = 0.5 landed **2 covered rows short**, and it was the ONLY point on NF-D16's own grid that did.
#: ⛔ NEITHER available "fix" was admissible, and both are still worth naming because both are still
#: tempting:
#:   · MOVING λ off 0.5 would be selecting the shrink on the CONSTRAINT'S OWN HEADROOM — NF1.8's
#:     explicit prohibition — and the nearest passing grid value is **0.75**, precisely the
#:     board-fitted frontier NF-D18/NF-D20 ruled un-publishable. The trap closes on itself.
#:   · MOVING THE FLOOR is E2.1-r's cardinal error: a floor that moves until something clears it is
#:     not a floor (NF1.8 §1), and `run_interval_revalidation` exits non-zero precisely so this is a
#:     RE-SELECTION trigger rather than a log line.
#: ⇒ 2026-08-05 the PM ACCEPTED THE NULL and CLOSED NF-D21 as `CONSTRAINT_REFUSED`, explicitly so
#: that no follow-on would inherit a dangling dependency on clearing λ=0.5.
#:
#: ✅ **WHAT CHANGED — THE RULE, NOT THE NUMBER.** NF-D22 REPLACED the hard point-estimate floor with
#: an exact-Binomial POWER-DERIVED floor (`nf_d22_exact_binomial_power_floor_v1`) taking **no coverage
#: argument at all** — only n, the nominal level, and NF1.8's own PRE-REGISTERED false-reject target.
#: The rule it replaced rejects a perfectly-calibrated band **0.393–0.500 of the time at every size**,
#: so the 0.7905 refusal above was a coin toss reading as evidence. Under the floor now in force the
#: rookie RB requires 110 covered rows of 148 and has 117 — and EVERY λ on the grid, not only this
#: one, clears. λ is UNCHANGED at the board-blind midpoint. See
#: `ablation_results/nf_d22_power_floor.md` §1–§4 (the derivation, the two-sided validation, the λ
#: sweep under the floor in force, and NF-D16 at λ=0.5 through the ten NF-G0 gates: `ready_to_promote
#: = True`), and `ablation_results/nf_g0_d21_governance_publish.md` §4 for the original refusal.
#:
#: ⛔ **THE ROUTE MATTERS AND MAY NOT BE SHORT-CIRCUITED IN EITHER DIRECTION.** This did not become
#: `True` because a follow-on happened to land: the floor was derived independently (NF-D22 §1's whole
#: claim is that its table could have been published before any band was scored), the gate was
#: RE-RUN against it, and a NEW PM disposition was recorded — all three, in that order.
#: `assert_coherent()` below enforces the last of them mechanically.
#:
#: 🔄 **ROLLBACK IS THIS ONE LINE.** `False` returns λ = 0.0, which folds to the identity affine and
#: restores the pre-NF-D16 rookie point BYTE-FOR-BYTE — the recalibration is opt-in by construction
#: (`fit_rookie_slot_curves` fits nothing without `recal_hist`), so there is no second code path to
#: keep in sync. ⚠️ Flipping it back must also move `DISPOSITION`, or `assert_coherent()` refuses the
#: import — a rollback is a decision too, and an undocumented one is how a served artifact and its
#: own provenance record drift apart.
SERVING_ENABLED: bool = True

#: The single sentence every user-facing record must be able to carry. Kept HERE, beside the
#: decision, so the changelog and the payload quote one string rather than paraphrasing it twice.
HONEST_FRAMING = (
    "A board-blind, conservative rookie-point recalibration chosen by JUDGMENT — evidenced "
    "accurate and placement-respecting out-of-sample on every held-out draft class, but NOT an "
    "optimised in-fold selection, and not a market or edge claim."
)


def stamp() -> dict[str, Any]:
    """The artifact stamp. Embedded in the built board AND in the published payload.

    ⭐ THE STAMP IS THE HONESTY MECHANISM, NOT THE CHANGELOG. Prose can be paraphrased away by the
    next person who touches the copy; a `statistically_selected: false` field travelling with the
    numbers cannot be. Anyone reading the served artifact — including a future session that has
    never read this file — can see what kind of decision produced it."""
    return {
        "selection_status": SELECTION_STATUS,
        "shrink_lambda": SHRINK_LAMBDA,
        "statistically_selected": STATISTICALLY_SELECTED,
        "source_model": SOURCE_MODEL,
        "decision_story": DECISION_STORY,
        "policy_version": POLICY_VERSION,
        "decided_on": DECIDED_ON,
        "recalibrated_positions": list(recalibrated_positions()),
        "excluded_positions": list(excluded_positions()),
        "framing": HONEST_FRAMING,
    }


#: The dispositions under which this policy may serve. `veteran_level_policy`'s vocabulary, shared so
#: the two level policies read the same way and a reviewer does not have to learn two.
#: ⭐ AN ALLOW-LIST, NOT A DENY-LIST, and that is the substantive choice: the original rule named
#: `CONSTRAINT_REFUSED` as forbidden, which silently permits every OTHER string — including a typo, a
#: half-written `"PENDING"`, or a value invented by a future session that never re-ran the gate.
PUBLISHABLE_DISPOSITIONS: tuple[str, ...] = ("SHIP",)


def assert_coherent() -> None:
    """Refuse an incoherent decision record. Called at IMPORT, so it cannot be skipped.

    ⭐ THE FAILURE THIS EXISTS TO CATCH is the realistic one, not a hypothetical, and it was written
    while the flip was still OFF: a future session reads `SERVING_ENABLED = False`, sees that NF-D22
    has landed, and flips the flip — WITHOUT re-running the gate and without re-deciding the
    disposition. The result is a module that simultaneously serves λ=0.5 and records "we accepted the
    null", i.e. a served artifact whose own provenance record contradicts it. That is the NF-C0e class
    (a declaration outrunning its production) and it is silent: nothing else in the system compares
    these two constants.

    ⭐ IT STILL BINDS NOW THAT THE FLIP IS ON — with the direction reversed. The live incoherence a
    reader should worry about today is a ROLLBACK that moves `SERVING_ENABLED` back to `False` and
    leaves `DISPOSITION = "SHIP"` standing, or a future refusal recorded without turning serving off.
    Both are the same defect wearing the other face, and both trip this check.

    ⛔ The cure for a legitimate future publish or rollback is to change BOTH — re-gate, then
    re-decide — not to weaken this check or to widen `PUBLISHABLE_DISPOSITIONS` to admit whatever
    string is currently in the way.
    """
    if SERVING_ENABLED and DISPOSITION not in PUBLISHABLE_DISPOSITIONS:
        detail = (
            "The flip was turned on without re-deciding the disposition — re-run the interval_floors "
            "gate against the floor in force and record a NEW PM disposition before serving."
            if DISPOSITION == PREDECESSOR_DISPOSITION else
            f"{DISPOSITION!r} is not a disposition this policy may serve under "
            f"(expected one of {PUBLISHABLE_DISPOSITIONS})."
        )
        raise ValueError(
            f"rookie_publish_policy is INCOHERENT: SERVING_ENABLED=True while DISPOSITION is "
            f"{DISPOSITION!r}. " + detail
        )


assert_coherent()


def serving_lambda() -> float:
    """The λ the SERVED board is built at — 0.0 when the flip is off.

    Every caller reads λ through here rather than from `SHRINK_LAMBDA` directly, so "serving is off"
    and "serving is on at 0.5" are one switch. The interval re-validation reads it too, which is how
    the standing coverage check stays anchored to the point the product actually serves."""
    return float(SHRINK_LAMBDA) if SERVING_ENABLED else 0.0
