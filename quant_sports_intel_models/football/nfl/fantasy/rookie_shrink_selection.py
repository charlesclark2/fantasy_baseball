"""rookie_shrink_selection.py — NF-D20 pure model logic: can a GLOBAL SHRINK of NF-D16's ratified
rookie-point recalibration be selected IN-FOLD, under a PER-FOLD whole-board placement constraint,
without ever seeing the 2026 board?

⚠️ THIS FILE IS THE PRE-REGISTRATION. Everything that could otherwise be chosen after seeing a result
— the family, the λ grid, the selection RULES, the two constraints, the metric, the framing, the
deflation reading and its level, the anchor set, the empty-evidence default — is a CONSTANT here,
written and COMMITTED before the run. The runner READS these rather than restating them, so "what was
pre-registered" has exactly one owner.

────────────────────────────────────────────────────────────────────────────────────────────────────
WHY THIS STORY EXISTS — AND WHY IT IS THE ONLY LEGITIMATE PUBLISH PATH LEFT FOR NF-D16
────────────────────────────────────────────────────────────────────────────────────────────────────
NF-D16's per-position AFFINE rookie-point recalibration is RATIFIED (pooled draftable-tier MAE
1.0738 → 0.9407 over 7 held-out draft classes, positive in all 7, PBO 0.029, whole-field DSR 0.996,
p 0.0033; pooled bias −20.87 → −5.41, i.e. TOWARD zero) and HELD from publish: on the 2026 board it
lifts the top rookie RB to overall rank 6, and NF-D17 VALIDATED the placement clause that refuses it
(cap Q10 = 8.8; rank 6 is outside reality's ENTIRE observed support, minimum 7).

NF-D18 then asked whether a differently-SHAPED correction could keep the gain and clear the cap. Four
shapes — concave power, robust affine, monotone quantile map, isotonic learned foil — and every one
was refused; three of the four placed the top rookie WORSE than the un-attenuated reference. But its
frontier diagnostic measured the result that outlives the null: **the placement cap admits a plain
GLOBAL SHRINK of the ratified affine up to λ = 0.75, retaining 0.8152 of the tier-MAE gain.** The
constraint was never the binding problem; the SHAPES were.

⛔ **AND NF-D18 WAS RIGHT TO REFUSE TO TAKE THAT NUMBER, WHICH IS EXACTLY WHY THIS FILE EXISTS.**
λ = 0.75 was read off ONE board — the 2026 board — with the answer already in view. Pre-registering it
now that it is known would be reverse-engineering wearing a pre-registration's clothes (the E2.1-r
inversion in a successor's badge). ⇒ **NOTHING IN THIS FILE MAY REFER TO 0.75, AND NO ARM HERE MAY BE
FITTED, TUNED, FILTERED OR SELECTED ON THE 2026 BOARD.** Every λ is selected IN-FOLD from held-out
draft classes and the merged veteran+rookie boards of PRIOR seasons only. The 2026 board appears in
this story exactly once, at the very end, as the serving-time face-validity confirmation NF1.4 applies
to every emitted board — applied to an arm whose λ was already fixed without it.

────────────────────────────────────────────────────────────────────────────────────────────────────
⭐ THE COST NF-D18 NAMED, AND WHAT PAYS IT — THE PER-SEASON MERGED BOARD
────────────────────────────────────────────────────────────────────────────────────────────────────
The placement constraint is a WHOLE-BOARD rank: where the best rookie lands among the VETERANS. It
therefore cannot be evaluated on a rookie-only fold, and NF-D18 recorded that "a legitimate successor
must select the shrink IN-FOLD under a PER-FOLD placement constraint, which requires rebuilding the
merged veteran+rookie board for each held-out season."

That harness turns out to EXIST as a walk-forward artifact rather than needing to be written:
`run_season_projection.py --backtest-from 2019` emits `nfl_fantasy_season_projections_{Y}.parquet` for
every season, each built off `base_season = Y − 1` — the veteran half from season Y−1's realized data,
the rookie half from the incoming class Y priced by a slot curve fitted on classes ≤ Y−1, and with
NF-D16's recalibration OFF (its serving flip is held). So each historical board IS the product as it
would have been served that summer, and its rookie half is the INCUMBENT point. This story READS those
boards; it does not rebuild or re-derive them, and it asserts their walk-forward provenance
(`base_season == Y − 1`) rather than assuming it.

────────────────────────────────────────────────────────────────────────────────────────────────────
THE FAMILY — ONE DECLARED FAMILY, AND THE FIELD IS SELECTION RULES RATHER THAN λ VALUES
────────────────────────────────────────────────────────────────────────────────────────────────────
⚠️ THE DISTINCTION IS LOAD-BEARING. A field of fixed λ values would make λ a KNOB and the winner a
re-pick of NF-D16's selected shrink — the forbidden move. A field of RULES makes each arm a
deterministic function of in-fold data alone: an arm's λ is whatever its rule computes from the draft
classes and boards strictly BEFORE the fold it is scored on, and no human chooses it at any point.

  • `incumbent (NULL)`     — λ ≡ 0, the rookie point AS SERVED TODAY. NF-D16's flip is off, so this is
                             the real product and the real null. It can win.
  • `infold_all_boards`    — ⭐ THE CONSERVATIVE RULE. λ is the in-fold-metric-optimal value among
                             those ADMISSIBLE (C2) on EVERY prior season's merged board. "The shrink
                             must have been admissible on every board we have ever seen."
  • `infold_last_board`    — THE ONE-STEP RULE. Same selection, but admissibility is required only on
                             the MOST RECENT prior board. Registered because the constraint is a
                             property of the board about to be PUBLISHED, and the best available proxy
                             for the next board is the last one. Knob-free, and it is the arm that says
                             whether the conservative aggregation is buying anything.
  • `unconstrained (λ=1)`  — ⭐ NF-D16's RATIFIED AFFINE AT FULL STRENGTH: the in-fold-metric-optimal λ
                             with the placement constraint REMOVED. THE REFERENCE ARM — carried
                             SHIPPABLE so the constraint has something to REFUSE. A field of only
                             constrained arms would leave the constraint passing having examined
                             nothing, which is the NF1.7 (a) vacuous-check class in an eligibility
                             rule's clothing.

⭐ THE MATCHED FOIL (NF-D10 (g) / NF-D15 (g′)) — `blind_half`, a CONSTANT λ = 0.5 chosen with NO board
information at all: the exact midpoint of the registered interval, fixed a priori. Its only job is to
answer the question this story's claim turns on — did the IN-FOLD BOARD EVIDENCE earn the selection,
or would any mid-strength shrink have done the same? "My rule won" is not "it won for the reason I
said". ⛔ NON-SHIPPABLE, and excluded from the eligible set, from PBO's search and from the DSR trial
field: a diagnostic anchor is never a trial (MH2 (a)).

────────────────────────────────────────────────────────────────────────────────────────────────────
THE λ GRID — INHERITED BY IMPORT, NEVER RE-CHOSEN
────────────────────────────────────────────────────────────────────────────────────────────────────
`LAMBDA_GRID = (0.0,) + rookie_point_recalibration.SHRINK_GRID` = (0.0, 0.25, 0.5, 0.75, 1.0).

⭐ THIS IS NF-D16'S OWN PRE-REGISTERED SHRINK GRID, IMPORTED. It was written before any constraint
result existed and NF-D16 scored every point on it and selected λ = 1 on the metric. Inheriting it is
what stops the grid from becoming a place to hide a choice — a successor that invented a new grid
could always place a point wherever it wanted the answer. ⚠️ 0.75 is ON this grid, and it is on it
because NF-D16 put it there in advance, NOT because NF-D18 later measured it: no arm here is fixed at
0.75, no rule may prefer it, and whether any rule lands there is a RESULT.

The finer 0.05 grid is computed as a DISCLOSED SENSITIVITY only (`FINE_GRID`) so a reader can see the
answer is not an artefact of grid coarseness. ⛔ It is never selected on.

────────────────────────────────────────────────────────────────────────────────────────────────────
THE TWO CONSTRAINTS — BOTH BINDING ON ELIGIBILITY, BOTH FIXED IN WRITING BEFORE THE RUN
────────────────────────────────────────────────────────────────────────────────────────────────────
  C1 · DO NO ORDERING HARM — NF1.4's `ORDERING_DO_NO_HARM = 0.02` on the within-position rank
       correlation against the incumbent, checked PER POSITION and never as a pooled mean. Inherited
       verbatim by import. (A global shrink of an affine is affine, so it is CONDITIONALLY monotone —
       a negative effective slope would invert a position's whole board. Measured, never asserted.)

  C2 · THE PER-FOLD PLACEMENT CONSTRAINT — on a merged board S, a shrink λ is ADMISSIBLE iff

           rank_λ(S)  ≥  min( STRICT_CAP , rank_incumbent(S) )

       where `STRICT_CAP` is NF-D17's THRESHOLD-INVARIANT cap: the strictest of the entire Q05–Q25
       band AND reality's observed minimum realized rank, i.e. the same terms on which the VETO held.
       It is DELEGATED to `season_projection.rookie_placement_breach` through NF-D18's
       `placement_clearance` — this story introduces NO new threshold and NO new reference, because
       clearing only at a cap one would pick after seeing the result is the E2.1-r inversion facing
       the other way.

       ⚠️⭐ **WHY THE SECOND TERM IS THERE, AND WHY IT IS NOT A LOOSENING CHOSEN TO GET AN ANSWER.**
       The incumbent's OWN emitted boards do not all clear the cap: the served 2021 board places
       Trevor Lawrence at overall rank 10, inside the band. That is a property of the SHIPPED PRODUCT,
       measured before any candidate in this field was scored, and it is disclosed rather than worked
       around. Without the second term the constraint would refuse EVERY λ on such a board INCLUDING
       λ = 0 — i.e. it would refuse the null itself — and a constraint that refuses everything has
       examined nothing (NF1.7 (a)). The clause as written governs the CHANGE: a recalibration may not
       place the top rookie better than the validated cap admits, and may never make a pre-existing
       breach WORSE. It reduces to the plain NF-D17 cap on every board the incumbent already clears.
       ⭐ The STRICT reading (the bare cap, no second term) is COMPUTED AND REPORTED as a sensitivity
       so a reader can see exactly what the clause decided. It is never selected on.

⚠️ **C2 BINDS ON ELIGIBILITY AND IT IS EVALUATED OUT-OF-SAMPLE.** An arm is eligible only if the λ its
rule chose from data strictly BEFORE each held-out fold ALSO satisfies C2 on that fold's OWN board —
the board the rule never saw. That is the genuine held-out question ("does an in-fold-selected shrink
still clear the cap on the NEXT board?") and it is what makes this story a test rather than a
description. `unconstrained (λ=1)` is expected to fail it, which is precisely why it is in the field.

────────────────────────────────────────────────────────────────────────────────────────────────────
METRIC · FRAMING · DEFLATION — INHERITED, NOT RE-CHOSEN
────────────────────────────────────────────────────────────────────────────────────────────────────
  · METRIC  — NF1.4's `tier_mae`, imported. The incumbent point was selected on it, NF-D16 was graded
              on it and NF-D18 was graded on it; grading the fourth change to ONE product on a new
              metric is metric-shopping.
  · FRAMING — POOLED, inherited from NF-D16/NF-D18 with its reason unchanged: the ship UNIT is one
              change to `project_rookies` applying at RB/TE/WR together or not at all. The
              per-position reading is computed as a DISCLOSURE and does not gate.
  · DSR     — WHOLE-FIELD reading BINDS, level 0.95; PBO < 0.2; α = 0.10 single-hypothesis. All three
              inherited BY IMPORT from `rookie_point_recalibration`, so the bar cannot drift between
              the story that ratified the correction and the story trying to publish it.
              Sensitivities at DSR ≥ 0 and with the DSR removed are reported.

────────────────────────────────────────────────────────────────────────────────────────────────────
⚠️ TWO-SIDED ANCHORS — INCLUDING THE ONE THE STORY BRIEF NAMES EXPLICITLY
────────────────────────────────────────────────────────────────────────────────────────────────────
  · `oracle_perplayer` — the ORACLE FLOOR at full resolution. Nothing may beat it.
  · `oracle_ols`       — THE PEEKING CEILING AT MATCHED FAMILY. Every arm here is a λ-blend of an
                         affine with the identity, which is ITSELF a per-position affine
                         (`λa + (1 + λ(b − 1))·p`), so the whole field lives in ONE family and one
                         ceiling is correct — the opposite of NF-D16's nesting case, and it is stated
                         because "one ceiling per form" (NF-D16 (g‴)) is a rule about NESTING, not a
                         rule that more ceilings are always better.
  · `permuted_across`  — the reference affine fitted on outcomes shuffled ACROSS positions. Must LOSE.
  · `permuted_within`  — shuffled WITHIN position: the marginal preserved EXACTLY, the projection↔
                         outcome relationship destroyed. ⭐ PRE-REGISTERED TO BE BEATEN, not to tie.
                         NF-D16 measured this anchor as provably VACUOUS for a pure LEVEL (max |Δ|
                         7.1e-15) and NF-D18 measured it BITING for a SHAPE. NF-D16's ratified winner
                         is an AFFINE — it carries a slope — so the shuffle genuinely acts here, and
                         saying which in advance is the point.
  · `zero_scale`       — DEGENERATE: project nothing. ⭐ **DOUBLE DUTY, AND THE STORY BRIEF REQUIRES
                         IT.** It must LOSE the selection metric, and its PLACEMENT is scored on every
                         board: it SATISFIES C2 trivially (a board of zero-projected rookies places
                         none of them high). NF1.8's rule is that a CONSTRAINT a degenerate satisfies
                         is fine — the metric eliminates it — whereas a CRITERION a degenerate WINS is
                         fatal. Measuring that is the proof this story did not quietly promote the
                         placement constraint into a selection criterion.
  · `pos_median`       — DEGENERATE: NF1.4's MAE-collapse tell, the arm that WINS an inverted metric.
  · `over_scale`       — ⭐ THE DEGENERATE ON THE OTHER SIDE: λ = 2, twice the ratified correction. It
                         must LOSE the metric AND BREACH C2. A constraint is only shown to have teeth
                         if something is measured failing it, and a one-sided anchor set cannot show
                         that (NF1.7 (d) (3): sharpness needs two degenerates, not one).

────────────────────────────────────────────────────────────────────────────────────────────────────
THE EMPTY-EVIDENCE DEFAULT — REGISTERED IN ADVANCE BECAUSE IT IS DECIDABLE IN ADVANCE
────────────────────────────────────────────────────────────────────────────────────────────────────
The merged boards begin at 2019, so the FIRST held-out class (2019) has NO prior board and its rules
have no constraint evidence at all. `EMPTY_EVIDENCE_LAMBDA = 0.0`: with nothing to verify the
constraint against, a rule applies NO correction. A check that did not run is not a check that passed
(NF1.7 (a)), so the conservative reading is the only admissible one — and registering it here, before
the run, is what stops it from being decided by whichever answer it produces.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy.nf1_4_rookie import (
    ORDERING_DO_NO_HARM,
    SELECTION_METRIC,
    TIER_K,
)
from quant_sports_intel_models.football.nfl.fantasy.rookie_point_recalibration import (
    ALPHA,
    DSR_MIN,
    MIN_POINT,
    PBO_MAX,
    RECALIBRATED_POSITIONS,
    SHRINK_GRID,
    apply_position_adjustment,
    blend_toward_incumbent,
    family_ceiling_check,
    fit_ols,
    ordering_check,
    scaled_positions_only,
)
from quant_sports_intel_models.football.nfl.fantasy.rookie_point_scaling import SCALED_TIER_K
# ⭐ The placement clause is INHERITED, not re-derived: `board_placement` re-ranks a merged board and
#    `placement_clearance` delegates the whole cap computation to `season_projection`. NF-D18 owns
#    them; importing rather than copying is what keeps "the bar this story must clear" one fact.
from quant_sports_intel_models.football.nfl.fantasy.rookie_top_attenuation import (
    board_placement,
    placement_clearance,
)

MODEL_VERSION = "nfl_fantasy_nf_d20_infold_shrink_v1"

# ⛔ SCOPE, INHERITED BY IMPORT (through NF-D16, which inherits it from NF-D15/NF-D14) so no story in
#    this chain can drift on which positions may be touched. QB is excluded because NF-D14 MEASURED
#    the rookie-QB double-pricing; NF-D20 does not re-open it, and `apply_position_adjustment` is the
#    single gate every arm — candidate, degenerate, matched foil and oracle alike — passes through.
SHRINK_POSITIONS = RECALIBRATED_POSITIONS
EXCLUDED_POSITIONS = ("QB",)

# ── THE PRE-REGISTERED FRAMING AND GATES, RECORDED AS DATA SO THE REPORT CANNOT QUIETLY DISAGREE ──
PREREGISTERED_FRAMING = "pooled"
PREREGISTERED_DSR_READING = "whole_field"
FRAMING_REASON = (
    "INHERITED FROM NF-D16 THROUGH NF-D18 VERBATIM, and inheriting rather than re-deciding is itself "
    "the point: this is the FOURTH pre-registered change asked of ONE product, and a framing "
    "re-chosen per story is a framing chosen for its answer. The ship UNIT is one change to "
    "`project_rookies` that applies at RB/TE/WR together or not at all, so the hypothesis is ONE "
    "claim and gets ONE test. The per-position reading is computed as a DISCLOSURE and does not gate."
)
ELIGIBILITY_REASON = (
    "The PER-FOLD placement constraint acts on ELIGIBILITY and is evaluated OUT-OF-SAMPLE: an arm is "
    "eligible only if the λ its rule chose from data strictly BEFORE each held-out fold also "
    "satisfies C2 on that fold's OWN board — the board the rule never saw. As a post-hoc veto the "
    "story would be vacuous (the least-shrunk arm wins the tier metric by construction and is "
    "precisely the arm the cap refuses), and as an IN-SAMPLE filter it would be circular. Only the "
    "held-out reading asks the question that decides a publish: does an in-fold-selected shrink still "
    "clear the cap on the NEXT board?"
)
LAMBDA_PROVENANCE = (
    "λ is NEVER a knob in this story. Every candidate is a deterministic RULE whose λ is computed "
    "from held-out draft classes and prior-season merged boards alone; the grid itself is NF-D16's "
    "own pre-registered SHRINK_GRID, imported. ⛔ NF-D18's frontier value (read off the 2026 board "
    "with the answer in view) is not referenced, defaulted to, or reachable by any rule here, and no "
    "arm is fitted, filtered or selected on the 2026 board."
)

# ⭐ THE λ GRID, INHERITED BY IMPORT. `SHRINK_GRID` is NF-D16's own pre-registered shrink grid; 0.0 is
#    prepended because `blend_toward_incumbent(·, ·, 0)` reproduces the incumbent EXACTLY, which makes
#    the grid an honest shrink toward "no recalibration" with the NULL as one of its own points.
LAMBDA_GRID = (0.0,) + tuple(SHRINK_GRID)
# DISCLOSED SENSITIVITY ONLY — never selected on. Answers "is the verdict an artefact of a coarse
# grid?" with a number instead of a shrug.
FINE_GRID = tuple(round(0.05 * i, 2) for i in range(21))

REFERENCE_FORM = "ols_slope"          # NF-D16's RATIFIED affine — the correction being shrunk
FOIL_LAMBDA = 0.5                     # the blind midpoint of [0, 1]; no board information whatsoever
OVER_SCALE_LAMBDA = 2.0               # the two-sided degenerate: must lose the metric AND breach C2
EMPTY_EVIDENCE_LAMBDA = 0.0           # no board to verify against ⇒ no correction (NF1.7 (a))

# The pre-registered SELECTION RULES. `evidence` names how a rule aggregates the per-board
# admissibility of the boards it is allowed to see; `constrained=False` is the REFERENCE arm.
SELECTION_RULES = ("infold_all_boards", "infold_last_board", "unconstrained")
RULE_EVIDENCE = {"infold_all_boards": "all", "infold_last_board": "last", "unconstrained": "none"}
RULE_LABEL = {"infold_all_boards": "infold_all_boards", "infold_last_board": "infold_last_board",
              "unconstrained": "unconstrained (λ=1)"}

# ⭐ ONE FAMILY, ONE CEILING — and that is a MEASURED property of the family, not a shortcut. A
#    λ-blend of a per-position affine with the identity is `λa + (1 + λ(b − 1))·p`, itself a
#    per-position affine, so every arm in this field lives in the SAME family as `oracle_ols` and the
#    NF-D16 (g‴) "one ceiling per FORM" rule (which is about NESTING families) resolves to one ceiling.
FAMILY_CEILING = {REFERENCE_FORM: "oracle_ols"}

MATCHED_FOIL_PREFIX = "blind"
NON_SHIPPABLE = ("zero_scale", "pos_median", "over_scale", "oracle_perplayer", "permuted_across",
                 "permuted_within", "oracle_ols")
_REQUIRED_ANCHORS = ("oracle_perplayer", "oracle_ols", "permuted_across", "permuted_within",
                     "zero_scale", "pos_median", "over_scale")

__all__ = [
    "MODEL_VERSION", "SHRINK_POSITIONS", "EXCLUDED_POSITIONS", "PREREGISTERED_FRAMING",
    "PREREGISTERED_DSR_READING", "FRAMING_REASON", "ELIGIBILITY_REASON", "LAMBDA_PROVENANCE",
    "LAMBDA_GRID", "FINE_GRID", "REFERENCE_FORM", "FOIL_LAMBDA", "OVER_SCALE_LAMBDA",
    "EMPTY_EVIDENCE_LAMBDA", "SELECTION_RULES", "RULE_EVIDENCE", "RULE_LABEL", "FAMILY_CEILING",
    "MATCHED_FOIL_PREFIX", "NON_SHIPPABLE", "PBO_MAX", "DSR_MIN", "ALPHA", "MIN_POINT",
    "SELECTION_METRIC", "ORDERING_DO_NO_HARM", "TIER_K", "SCALED_TIER_K",
    "apply_position_adjustment", "blend_toward_incumbent", "ordering_check", "scaled_positions_only",
    "family_ceiling_check", "fit_ols", "board_placement", "placement_clearance",
    "strictest_placement_cap", "board_admits", "admissible_lambdas", "aggregate_admissible",
    "held_out_evidence",
    "select_lambda", "monotonicity", "require_anchors", "candidate_configs", "config_key",
    "board_is_walk_forward", "pooled_ship", "shrink_verdict",
]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# C2 — the per-fold placement constraint
# ══════════════════════════════════════════════════════════════════════════════════════════════
def strictest_placement_cap() -> float:
    """NF-D17's THRESHOLD-INVARIANT cap as ONE number — the strictest of the whole Q05–Q25 band and
    reality's observed minimum realized rank.

    ⭐ DERIVED BY DELEGATION, NEVER TRANSCRIBED. `placement_clearance` already requires clearance at
    every cap in the band and against the observed minimum, which is exactly `rank ≥ max(caps)`; this
    reads that maximum out of the same call rather than hard-coding a number that could drift from the
    clause it claims to be. A story that re-types its own bar has two owners for one fact, and the one
    that drifts is always the one nobody re-reads."""
    br = placement_clearance(999)                       # any clearing rank: we want the band itself
    caps = list(br["caps_over_q_band"].values()) + [br["observed_minimum"]]
    return float(max(float(c) for c in caps))


def board_admits(rank_lambda, rank_incumbent, *, cap: float | None = None) -> dict:
    """⭐ C2, THE WHOLE CONSTRAINT, IN ONE INEQUALITY: `rank_λ ≥ min(cap, rank_incumbent)`.

    Two readings are returned and only the first governs:
      · `admits`  — the PRE-REGISTERED clause. It reduces to the plain NF-D17 cap on every board the
                    incumbent already clears, and on a board where the SHIPPED product already breaches
                    it forbids making that breach worse.
      · `admits_strict` — the bare cap with no incumbent term, reported as a SENSITIVITY. On a board
                    the incumbent breaches, this reading refuses λ = 0 — i.e. it refuses the NULL — and
                    a constraint that refuses everything has examined nothing (NF1.7 (a)).

    An unevaluable rank (no rookie on the board) is NOT a pass: it is reported unevaluable and treated
    as a refusal by every caller, because a check that did not run is not a check that passed."""
    cap = strictest_placement_cap() if cap is None else float(cap)
    if rank_lambda is None or rank_incumbent is None:
        return {"admits": False, "admits_strict": False, "evaluable": False,
                "cap": cap, "rank": None, "incumbent_rank": None,
                "note": "no rookie on the board — C2 could not be evaluated, which is not passing it"}
    r, ri = float(rank_lambda), float(rank_incumbent)
    return {"admits": bool(r >= min(cap, ri)), "admits_strict": bool(r >= cap), "evaluable": True,
            "cap": cap, "rank": r, "incumbent_rank": ri,
            "binding_threshold": float(min(cap, ri)),
            "incumbent_itself_breaches": bool(ri < cap)}


def admissible_lambdas(rank_by_lambda: dict, rank_incumbent, *, cap: float | None = None,
                       strict: bool = False) -> tuple:
    """The λ values a SINGLE board admits, given that board's best-rookie overall rank at each λ.

    `strict` switches to the bare-cap sensitivity reading. Returned sorted so downstream code never
    depends on dict insertion order."""
    key = "admits_strict" if strict else "admits"
    return tuple(sorted(
        float(lam) for lam, rank in rank_by_lambda.items()
        if board_admits(rank, rank_incumbent, cap=cap)[key]))


def aggregate_admissible(per_board: dict, evidence: str, *, grid: tuple = LAMBDA_GRID) -> tuple:
    """Aggregate per-board admissible λ sets into the set a RULE may choose from.

    `per_board` maps a board season → the admissible λ tuple for that board; `evidence` is the rule's
    pre-registered aggregation:
      · "all"  — admissible on EVERY board seen (set INTERSECTION)
      · "last" — admissible on the MOST RECENT board only
      · "none" — the REFERENCE arm: no placement evidence enters, the whole grid is available

    ⚠️ AN EMPTY EVIDENCE SET IS NOT AN EMPTY CONSTRAINT. With no board to verify against, the rule
    falls back to `EMPTY_EVIDENCE_LAMBDA` alone (registered in advance) rather than to the full grid —
    the difference between "nothing refused it" and "nothing examined it"."""
    if evidence == "none":
        return tuple(float(x) for x in grid)
    if not per_board:
        return (float(EMPTY_EVIDENCE_LAMBDA),)
    seasons = sorted(per_board)
    if evidence == "last":
        allowed = set(per_board[seasons[-1]])
    elif evidence == "all":
        allowed = set(grid)
        for s in seasons:
            allowed &= set(per_board[s])
    else:
        raise ValueError(f"unknown evidence aggregation {evidence!r}")
    # λ = 0 is the incumbent and is always available: declining to recalibrate cannot be refused by a
    # constraint on recalibration, and a rule with an empty choice set would have no defined answer.
    allowed.add(float(EMPTY_EVIDENCE_LAMBDA))
    return tuple(sorted(float(x) for x in allowed))


def held_out_evidence(evidence_all: dict, serving_season: int) -> dict:
    """⛔ THE SERVING BOARD IS NOT EVIDENCE — the single structural invariant this whole story rests
    on, expressed as a function so it can be TESTED rather than trusted to a comprehension in a
    runner.

    Every aggregation in this story iterates the result of this call, so the board whose placement
    decides the publish is unreachable to every rule by construction. Written as one owner because
    "no arm is selected on the 2026 board" is the claim NF-D18 refused to take on trust, and a claim
    that important must be a function with a guard on it."""
    return {s: v for s, v in evidence_all.items() if int(s) != int(serving_season)}


def select_lambda(allowed: tuple, inner_metric: dict) -> dict:
    """Pick λ from an ALLOWED set by the IN-FOLD metric — `argmin tier_mae`, ties to the SMALLER λ.

    ⭐ THE ARGMIN IS DELIBERATE AND IT IS NOT THE SAME AS "TAKE THE LARGEST ADMISSIBLE λ". The two
    coincide only if the metric is monotone in λ, which is a MEASUREMENT (`monotonicity`) and not a
    property of the family — NF-D16 method lock 2, the same reason "moves no ranks by construction" is
    measured rather than asserted. Registering the argmin means the rule stays correct even where the
    metric is not monotone, and the run reports whether the two readings agreed.

    ⚠️ TIES BREAK TOWARD LESS CORRECTION. A tie means the data cannot tell the two apart, and the
    conservative side of "how much of a held recalibration do we apply" is the smaller one."""
    cands = [(float(inner_metric[lam]), float(lam)) for lam in allowed
             if inner_metric.get(lam) is not None and np.isfinite(inner_metric.get(lam, np.nan))]
    if not cands:
        return {"lam": float(EMPTY_EVIDENCE_LAMBDA), "metric": None, "n_allowed": len(allowed),
                "note": "no scorable in-fold metric over the allowed set — falls back to the "
                        "incumbent rather than to an unverified correction"}
    best = min(cands)                                   # (metric, lam): ties fall to the smaller λ
    return {"lam": best[1], "metric": round(best[0], 4), "n_allowed": len(allowed),
            "allowed": list(allowed)}


def monotonicity(metric_by_lambda: dict, rank_by_lambda: dict | None = None) -> dict:
    """Is the metric monotone DECREASING and the board rank monotone WORSENING in λ? — MEASURED.

    Both are widely assumed and neither is guaranteed. If the metric is monotone, `select_lambda`'s
    argmin coincides with "the largest admissible λ" and the rule has a one-line description; if it is
    not, the argmin is still correct and the difference is a finding. If the RANK is monotone, the
    per-board admissible set is an interval `[0, λ_max]` and the intersection aggregation has a simple
    reading; if it is not, the set can have holes and that too is a finding rather than a bug."""
    lams = sorted(float(x) for x in metric_by_lambda if metric_by_lambda[x] is not None)
    vals = [float(metric_by_lambda[l]) for l in lams]
    mono_metric = all(b <= a + 1e-12 for a, b in zip(vals, vals[1:]))
    out = {"metric_monotone_decreasing": bool(mono_metric),
           "metric_argmin_lambda": (float(lams[int(np.argmin(vals))]) if vals else None),
           "metric_by_lambda": {round(l, 4): round(v, 4) for l, v in zip(lams, vals)}}
    if rank_by_lambda:
        rl = sorted(float(x) for x in rank_by_lambda if rank_by_lambda[x] is not None)
        rv = [float(rank_by_lambda[l]) for l in rl]
        out["rank_monotone_nonincreasing"] = bool(all(b <= a + 1e-12 for a, b in zip(rv, rv[1:])))
        out["rank_by_lambda"] = {round(l, 4): rv[i] for i, l in enumerate(rl)}
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Provenance — the boards this story READS must be walk-forward, and that is asserted
# ══════════════════════════════════════════════════════════════════════════════════════════════
def board_is_walk_forward(board: pd.DataFrame, season: int) -> dict:
    """⭐ THE BOARD'S OWN PROVENANCE, CHECKED RATHER THAN ASSUMED.

    A merged board for season Y is admissible evidence only if it was built off `base_season = Y − 1`
    — the veteran half from Y−1's realized data, the rookie half from the incoming class. If a board
    had been rebuilt with later data (or with NF-D16's recalibration already applied), every placement
    number computed from it would be a number about a different product, and NOTHING downstream would
    notice. This story reads artifacts it did not build, so the check is not optional.

    ⚠️ `has_rookies` is part of the check: a board with no rookie leg makes `board_placement`
    unevaluable, which C2 treats as a refusal — an outcome that must be traceable to the DATA rather
    than looking like a constraint result."""
    base = None
    if "base_season" in board.columns and len(board):
        v = pd.to_numeric(board["base_season"], errors="coerce").dropna()
        base = int(v.iloc[0]) if len(v) else None
    n_rk = int(board["is_rookie"].fillna(False).astype(bool).sum()) if "is_rookie" in board else 0
    return {"season": int(season), "base_season": base, "n_rows": int(len(board)),
            "n_rookies": n_rk,
            "walk_forward": bool(base is not None and int(base) == int(season) - 1),
            "has_rookies": bool(n_rk > 0),
            "ok": bool(base is not None and int(base) == int(season) - 1 and n_rk > 0)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered field (EVERY shippable config counts toward PBO/DSR — §0.5)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def candidate_configs(*, smoke: bool = False) -> list[dict]:
    """The full pre-registered candidate list, fixed before any result was read: the incumbent NULL,
    the two IN-FOLD selection rules, and NF-D16's ratified affine at full strength as the REFERENCE.

    Every one of them carries `form = REFERENCE_FORM` (except the NULL) because they are all the SAME
    per-position affine at different strengths — which is what makes ONE matched-family peeking ceiling
    the correct floor for the whole field."""
    cfgs = [{"label": "incumbent (NULL)", "form": "incumbent", "rule": None,
             "recalibrates": False, "shippable": True, "constrained": False}]
    rules = ("infold_all_boards", "unconstrained") if smoke else SELECTION_RULES
    for rule in rules:
        cfgs.append({"label": RULE_LABEL[rule], "form": REFERENCE_FORM, "rule": rule,
                     "evidence": RULE_EVIDENCE[rule], "recalibrates": True, "shippable": True,
                     "constrained": RULE_EVIDENCE[rule] != "none"})
    return cfgs


def config_key(cfg: dict) -> str:
    return f"{cfg['form']}@{cfg.get('rule') or 'null'}"


def require_anchors(scored: dict, required: tuple = _REQUIRED_ANCHORS) -> None:
    """⭐ A MISSING ANCHOR IS A HARD FAILURE, NEVER A PASS (NF1.7 anchor lesson (a)).

    An anchor that fails to fit makes its own check VACUOUSLY TRUE — `winner < anchor` against an
    absent anchor compares nothing and reports green. Every anchored story in this programme carries
    this guard since NF1.7 shipped that bug once, and it is a function rather than an inline `if` so it
    can be unit-tested without running the bake-off."""
    missing = [k for k in required
               if k not in scored or scored[k].get(SELECTION_METRIC) is None]
    if missing:
        raise SystemExit(
            f"the anchor(s) {missing} did not score — their checks would pass on NOTHING. Fix the "
            "anchor before reading any selection (NF1.7 anchor-set lesson 1).")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The verdict — the PRE-REGISTERED pooled framing, with BOTH constraints on eligibility
# ══════════════════════════════════════════════════════════════════════════════════════════════
def pooled_ship(*, winner: dict | None, incumbent_metric: float | None, ordering: dict,
                placement: dict | None, serving_placement: dict | None,
                pbo: float | None, dsr: float | None, pvalue: float | None,
                pbo_max: float = PBO_MAX, dsr_min: float = DSR_MIN,
                alpha: float = ALPHA) -> dict:
    """THE SHIP DECISION under the pre-registered pooled framing — one hypothesis, one test, and the
    ship unit is the whole per-position correction (RB/TE/WR together or not at all).

    Both constraints appear here as CHECKS ON THE SELECTED ARM as well as on eligibility, so a reader
    of the verdict dict can see the constraint state of the thing that was actually chosen rather than
    having to trust that the eligible set was filtered correctly.

    ⭐ `serving_placement_ok` IS A SEPARATE CLAUSE AND IT IS NOT A SECOND BITE AT SELECTION. λ for the
    served board is fixed by the winning rule from the 2019–2025 evidence with the 2026 board never
    read; this clause then applies NF1.4's ordinary serving-time face-validity check to that already-
    fixed arm. It can only REFUSE a publish, never choose between arms — which is exactly the
    post-selection role NF-D16 used it in, and the only role in which reading the served board cannot
    contaminate a selection."""
    beats = bool(winner and incumbent_metric is not None and winner.get("metric") is not None
                 and float(winner["metric"]) < float(incumbent_metric))
    per_pos = (ordering or {}).get("per_position", {})
    checks = {
        "has_eligible_winner": winner is not None,
        "recalibrates": bool(winner and winner.get("recalibrates")),
        "beats_incumbent": beats,
        "ordering_ok_every_position": bool(per_pos) and all(v.get("ok", False)
                                                            for v in per_pos.values()),
        "per_fold_placement_holds_out": bool((placement or {}).get("holds_out")),
        "serving_placement_ok": bool((serving_placement or {}).get("clears")),
        "pbo_ok": pbo is not None and pbo < pbo_max,
        "dsr_ok": dsr is not None and dsr >= dsr_min,
        "significant": pvalue is not None and float(pvalue) <= float(alpha),
    }
    return {"ship": all(checks.values()), "framing": PREREGISTERED_FRAMING, **checks}


def shrink_verdict(*, pooled_ships: bool, degenerates_lose: bool,
                   permutation_across_beaten: bool, permutation_within_beaten: bool,
                   oracle_respected: bool, family_ceiling_respected: bool,
                   over_scale_breaches: bool, degenerate_satisfies_constraint: bool,
                   boards_walk_forward: bool, qb_untouched: bool) -> dict:
    """The STORY-level decision: the pre-registered pooled gate PLUS the run's global sanity anchors.

    The anchors are STORY-level VETOES on purpose. A degenerate winning the metric, or an arm beating
    its own family's peeking ceiling, does not mean "this run was unlucky" — it means the measurement
    is not trustworthy anywhere in it and no number computed from it may be shipped.

    ⭐ TWO OF THESE ARE ABOUT THE CONSTRAINT RATHER THAN THE METRIC, AND BOTH ARE REQUIRED BY NF1.8's
    degenerate rule read in BOTH directions: `degenerate_satisfies_constraint` proves the placement
    clause is a CONSTRAINT (something a do-nothing arm satisfies while losing the metric) rather than a
    CRITERION that a do-nothing arm could WIN, and `over_scale_breaches` proves the same clause has
    TEETH — a constraint nothing is ever measured failing has examined nothing either.

    `boards_walk_forward` is a data-provenance veto: this story READS merged boards it did not build,
    and a board rebuilt with later data would silently make every placement number a number about a
    different product."""
    checks = {
        "pooled_gate_passes": bool(pooled_ships),
        "degenerates_lose": bool(degenerates_lose),
        "permutation_across_beaten": bool(permutation_across_beaten),
        "permutation_within_beaten": bool(permutation_within_beaten),
        "oracle_respected": bool(oracle_respected),
        "family_ceiling_respected": bool(family_ceiling_respected),
        "over_scale_breaches_the_constraint": bool(over_scale_breaches),
        "degenerate_satisfies_the_constraint": bool(degenerate_satisfies_constraint),
        "boards_are_walk_forward": bool(boards_walk_forward),
        "qb_untouched": bool(qb_untouched),
    }
    return {"ship": all(checks.values()), **checks}
