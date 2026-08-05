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
#: 🚨 **HELD `False` — BLOCKED BY THE INTERVAL-FLOOR GATE, NOT ABANDONED (NF-D21, 2026-08-04).**
#: The publish was built, stamped and routed through the NF-G0 pipeline, and the pipeline REFUSED it
#: at the `interval_floors` gate. Measured on the seven held-out draft classes (n = 148 rookie-RB
#: seasons), the rookie **RB** 80% coverage floor reads:
#:
#:     λ:        0.00    0.25    0.50    0.75    1.00
#:     RB cov  0.8041  0.8041  0.7905  0.8041  0.8041      (floor 0.80; 119 covered rows required)
#:     covered   119     119     117     119     119
#:
#: λ = 0.5 lands **2 covered rows short**, and it is the ONLY point on NF-D16's own grid that does.
#: ⛔ NEITHER available "fix" is admissible, and both are worth naming because both are tempting:
#:   · MOVING λ off 0.5 would be selecting the shrink on the CONSTRAINT'S OWN HEADROOM — NF1.8's
#:     explicit prohibition — and the nearest passing grid value is **0.75**, precisely the
#:     board-fitted frontier NF-D18/NF-D20 ruled un-publishable. The trap closes on itself.
#:   · MOVING THE FLOOR is E2.1-r's cardinal error: a floor that moves until something clears it is
#:     not a floor (NF1.8 §1), and `run_interval_revalidation` exits non-zero precisely so this is a
#:     RE-SELECTION trigger rather than a log line.
#: ⇒ the flip stays `False` (ZERO regression — users keep exactly the projection they have) until a
#: PM decision resolves it. See `ablation_results/nf_g0_d21_governance_publish.md` §4 for the full
#: measurement, including why the RB floor has zero slack by construction and what that implies.
SERVING_ENABLED: bool = False

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


def serving_lambda() -> float:
    """The λ the SERVED board is built at — 0.0 when the flip is off.

    Every caller reads λ through here rather than from `SHRINK_LAMBDA` directly, so "serving is off"
    and "serving is on at 0.5" are one switch. The interval re-validation reads it too, which is how
    the standing coverage check stays anchored to the point the product actually serves."""
    return float(SHRINK_LAMBDA) if SERVING_ENABLED else 0.0
