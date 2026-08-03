"""rookie_point_recalibration.py — NF-D16 pure model logic: a per-position LEVEL recalibration of the
rookie POINT projection for RB/TE/WR.

WHY THIS STORY EXISTS, AND WHY THE MOTIVATION IS NOT THE RESULT.
NF1.4 **documented** a cold rookie-point bias and never corrected it (draftable-tier bias RB −58 /
WR −49 / TE −44 PPR). NF-D14 corroborated that there is something cold to correct. NF-D15 then
separated two effects that had been conflated: its matched foil proved the AVAILABILITY arm's lift is
PER-PLAYER and not a level correction — refuting NF-D14's own stated mechanism — and, independently,
that a per-position CONSTANT recalibration beat the incumbent at all three scaled positions
(pooled tier MAE 1.0301 vs 1.0738, 6/7 classes, p = 0.0052).

⚠️ **THAT NUMBER IS PRIOR MOTIVATION AND IS CITED EXACTLY ONCE — here.** It is the best of 33 arms
chosen AFTER seeing the field, undeflated, and never registered as its own hypothesis. It may not be
cited as this story's result. NF-D16 exists to ask the same question CLEANLY, and if the clean
pre-registration makes the effect shrink, **the shrinkage IS the answer** (E2.1-r: a field re-read
until something in it clears is not a finding).

────────────────────────────────────────────────────────────────────────────────────────────────────
⭐ WHY THIS IS THE LOW-RISK HALF OF NF-D15's TWO LEADS
────────────────────────────────────────────────────────────────────────────────────────────────────
A per-position CONSTANT carries ZERO per-player information and — for the two constant forms — does
ZERO ordering harm **by construction**: a strictly monotone transform of a position's projections moves
no rank at all. And unlike NF-D15's availability half (whose re-validation is data-gated to 2028/2029
by its own power-in-classes computation) this is testable NOW on existing data. So the risk profile is
the opposite of NF-D15's: the question is only whether the level effect is real and estimable in-fold,
never whether correcting it would scramble the draft board.

⛔ **QB IS EXCLUDED, AND THE EXCLUSION IS INHERITED RATHER THAN RE-DECIDED.** NF-D14 MEASURED the
rookie-QB double-pricing and NF-D15 enforced the exclusion in one function, proving it at max drift
0.0. `RECALIBRATED_POSITIONS` is `rookie_point_scaling.SCALED_POSITIONS` **verbatim, by import**, so
the two stories cannot drift apart on scope, and `apply_position_adjustment` is the single gate every
arm — candidate, degenerate and oracle alike — must pass through.

────────────────────────────────────────────────────────────────────────────────────────────────────
🚨 THE FRAMING, PRE-REGISTERED **BEFORE** THE RUN — the single most important decision in this file
────────────────────────────────────────────────────────────────────────────────────────────────────
NF-D15 was blocked by its FRAMING, not by its effect size: it split one question into three
per-position tests and paid a BH multiplicity penalty (pooled single-hypothesis p 0.081 against a
three-test BH cutoff of 0.033). It could only say so honestly because it computed both readings.

**NF-D16 PRE-REGISTERS THE POOLED SINGLE-HYPOTHESIS FRAMING, AND HERE IS THE REASON, IN ADVANCE:**

  1. A LEVEL effect is *a-priori* expected to be COMMON across positions. NF1.4's documented bias is
     the same SIGN and a comparable magnitude at all three scaled positions (RB −58 / WR −49 /
     TE −44 PPR). The hypothesis under test is "the rookie point is systematically COLD", which is ONE
     claim about one product, not three unrelated claims that happen to be tested together.
  2. **The ship UNIT is the whole per-position constant vector.** A level recalibration is a single
     change to `project_rookies`: it either applies at RB/TE/WR together or not at all. There is no
     product in which the correction ships at TE alone. A multiplicity correction prices the risk of
     cherry-picking WHICH of three findings to report — and this framing cannot cherry-pick, because
     it reports one.
  3. Paying a 3× multiplicity penalty for a decomposition the hypothesis does not require is not
     conservatism, it is a worse test of the same thing.

⚠️ **THE PER-POSITION READING IS COMPUTED AND REPORTED BESIDE IT AS A DISCLOSURE** — the exact mirror
of NF-D15, which pre-registered per-position and disclosed pooled. The pre-registered framing GOVERNS.
If the two disagree, that is a disclosure, never a licence to take the other one.

**AND THE DSR READING IS PRE-REGISTERED TOO** (`PREREGISTERED_DSR_READING`): the **WHOLE-FIELD** DSR
binds, with the contender-set reading reported for distinguishability. NF-D14 and NF-D15 were both
bitten by a deflation statistic computed over a field containing its own weak arms; naming which one
binds in advance is what stops that from becoming a choice made after seeing the answer.

**AND THE DSR LEVEL IS THE STRICTER OF THE TWO AVAILABLE BARS** (`DSR_MIN = 0.95`, NF-D14/NF-D15's,
rather than NF1.4's own 0.0). The reason is specific to how this hypothesis was born: it was surfaced
by re-reading NF-D15's field, and a story born that way must not ALSO be granted a looser bar than the
field it was born in. The sensitivity at NF1.4's 0.0 and with the DSR dropped entirely is reported, so
a reader can see whether the choice decided the outcome.

────────────────────────────────────────────────────────────────────────────────────────────────────
PRE-REGISTERED CORRECTION FORMS (≥3 classes + a direct-learned foil + the incumbent NULL, per §0.5)
────────────────────────────────────────────────────────────────────────────────────────────────────
  • `incumbent`   — THE NULL. The shipped rookie point, untouched. In the field, and it can win.
  • `mult_const`  — per-position MULTIPLICATIVE constant, the in-fold mean of `realized / point`.
                    ⭐ Registered as the CLEAN statement of the hypothesis rather than inherited from
                    NF-D15's `mean_ratio` foil — that arm was a per-position mean of a DEPTH-derived
                    availability ratio, so registering it here would needlessly drag NF-D14's
                    week-1-vs-August depth provenance caveat into a story that touches no depth
                    feature at all. Monotone ⇒ ZERO ordering movement by construction.
  • `add_offset`  — per-position ADDITIVE offset, the in-fold mean of `realized − point`. Monotone
                    (up to the physical floor at 0) ⇒ ZERO ordering movement by construction. It is a
                    genuinely different shape from `mult_const`: an additive offset moves the bottom
                    of a position's board as much as the top, a multiplicative one moves the top most.
  • `mult_tier`   — per-position × DRAFT-TIER multiplicative constant. NF1.4's own diagnosis is that
                    the defect lives at the TOP of the board, so a correction that is uniform across
                    draft slot may simply be the wrong SHAPE. ⚠️ This form CAN reorder (two rookies in
                    different tiers can swap), so the ordering constraint genuinely binds on it.
  • `ols_slope`   — THE DIRECT-LEARNED FOIL: per-position OLS of realized on predicted, i.e. an
                    intercept AND a slope learned from the data rather than a prescribed constant. It
                    differs from the prescribed forms ONLY in that the correction's shape is fitted,
                    so a win is attributable to the learning. Also reorders (a slope ≠ 1 with a
                    non-zero intercept is still monotone, but the CLIP at zero and cross-tier
                    interaction are not) — the constraint binds here too.

⭐ **CARRYING THE TWO ORDERING-BINDING FORMS IS SUBSTANTIVE, NOT DECORATIVE.** The do-no-ordering-harm
constraint is NON-BINDING for `mult_const`/`add_offset` by construction and BINDING for
`mult_tier`/`ols_slope`. A field of only the constant forms would make the constraint vacuous — it
would pass having examined nothing, which is the NF1.7 anchor lesson wearing a different hat. The
slot-varying and slope forms are what give the constraint something to refuse.

Each non-null form × a SHRINK grid λ, blended in the OUTPUT space:
`pred(λ) = point + λ · (adjusted − point)`, so **λ = 0 reproduces the incumbent EXACTLY** for EVERY
form. (NF-D15 shrank geometrically in the scale, which is only defined for a multiplicative arm; an
output-space blend is the one convention that means the same thing for a multiplicative, an additive
and an affine form, so no form gets a differently-shaped knob than its rivals.)

────────────────────────────────────────────────────────────────────────────────────────────────────
📏 SELECTION METRIC — NF1.4's `tier_mae`, INHERITED RATHER THAN CHOSEN
────────────────────────────────────────────────────────────────────────────────────────────────────
The incumbent rookie point was selected on NF1.4's draftable-tier MAE, on a tier FIXED by the
incumbent's own projection (NF1.1's fixed-anchor rule, so no candidate can buy a friendlier subset).
NF-D16 changes that same product, so it is graded on that same metric. Grading a change to an
already-selected product on a NEW metric is metric-shopping, and it is exactly how a "lift" gets
manufactured.

⚠️ TWO-SIDED ANCHORS, EVERY RUN, SCORED AND READ RATHER THAN REASONED ABOUT (E2.1-r (b)/(c), NF-D11,
NF-D14's refinement):
  · `oracle_perplayer`  — peeks at full resolution (`k = realized/point` per player). Scores ~0;
                          nothing may beat it. A DIRECTION check for an accidentally-inverted metric.
  · A PEEKING CEILING **PER FORM** — `oracle_posconst`, `oracle_addoffset`, `oracle_tierconst`,
                          `oracle_ols`: each form's OWN parameters fitted on the HELD-OUT class.
                          ⭐ ONE CEILING FOR THE WHOLE FIELD WOULD BE MIS-SPECIFIED, AND THE FIRST CUT
                          OF THIS FILE HAD IT THAT WAY. A peeking oracle is a floor only at MATCHED
                          FAMILY **and** MATCHED RESOLUTION (NF1.7 (b) / NF1.9 (f)). `mult_tier` and
                          `ols_slope` are strictly RICHER families than a per-position constant, so
                          either could legitimately beat the best possible constant — a capacity
                          effect, exactly as NF1.9's winner legitimately beat its coarser oracle — and
                          a single constant-family ceiling would have called that a metric inversion.
                          Each arm is floored by the peeking version of **its own** form, where
                          "peeking can only help" genuinely holds, and NOTHING may beat its own
                          family's ceiling.
  · `permuted_across`   — the level constants estimated from training outcomes SHUFFLED ACROSS
                          positions. Same family, same n; only the per-position level structure moves.
                          Must LOSE.
  · `permuted_within`   — ⭐ THE ANCHOR THAT IS EXPECTED TO **TIE**, AND SAYING SO IN ADVANCE IS THE
                          POINT. Training outcomes shuffled WITHIN each position preserve that
                          position's MARGINAL distribution, and a level is a marginal statistic — so
                          for `add_offset` this anchor is EXACTLY the candidate arm (`mean(y) −
                          mean(point)` is invariant under a within-position permutation; asserted in
                          the tests). A permutation test is therefore near-VACUOUS against a level
                          correction, and that is a property of the hypothesis rather than a defect
                          in the anchor. Scoring it is what turns "a permutation anchor would not
                          bite here" from an assertion into a measurement (NF1.9: "a mechanism that
                          cannot act is a finding, not an omission").
  · `zero_scale`        — DEGENERATE CEILING: project nothing for every rookie.
  · `pos_median`        — DEGENERATE CEILING: NF1.4's MAE-collapse tell (the in-fold position median
                          for everyone). MAE is minimised at the conditional median, so this is the
                          arm that WINS an inverted metric — and it is the RIGHT degenerate for a
                          level story specifically, because it is the extreme of "throw away every
                          per-player distinction", which is precisely what a level correction must
                          NOT do.

🚧 DO-NO-ORDERING-HARM — NF1.4's `ORDERING_DO_NO_HARM`, inherited verbatim, checked PER POSITION and
never as a pooled mean (a pooled ρ can sit flat while one position's ordering collapses). Reused from
`rookie_point_scaling.ordering_check` rather than re-implemented.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy.nf1_4_rookie import (
    ORDERING_DO_NO_HARM,
    SELECTION_METRIC,
    TIER_K,
)
from quant_sports_intel_models.football.nfl.fantasy.rookie_point_scaling import (
    SCALED_POSITIONS,
    SCALED_TIER_K,
    ordering_check,
    scaled_positions_only,
)

MODEL_VERSION = "nfl_fantasy_nf_d16_rookie_point_recalibration_v1"

# ⛔ SCOPE, INHERITED BY IMPORT so the two stories cannot drift apart. QB is excluded because NF-D14
#    MEASURED the double-pricing and NF-D15 enforced the exclusion at max drift 0.0; NF-D16 does not
#    re-open it, and this alias means a future change to the scope has exactly one owner.
RECALIBRATED_POSITIONS = SCALED_POSITIONS
EXCLUDED_POSITIONS = ("QB",)

# ── THE PRE-REGISTERED FRAMING, RECORDED AS DATA SO THE REPORT CANNOT QUIETLY DISAGREE WITH IT ──
# Written before the run (see the module docstring for the three-part reason). The runner reads these
# rather than hard-coding a framing in its prose, so "which framing governs" is one fact in one place.
PREREGISTERED_FRAMING = "pooled"
PREREGISTERED_DSR_READING = "whole_field"
FRAMING_REASON = (
    "A LEVEL effect is a-priori COMMON across positions (NF1.4's documented bias is the same sign and "
    "comparable magnitude at RB/WR/TE), and the ship UNIT is the whole per-position constant vector — "
    "a level recalibration is ONE change to `project_rookies` that applies at RB/TE/WR together or "
    "not at all. Splitting one hypothesis into three tests pays a multiplicity penalty for a "
    "decomposition the hypothesis does not require."
)

# Deflation gates. PBO/α inherited from NF1.1/NF1.4. DSR is the STRICTER of the two available bars
# (NF-D14/NF-D15's 0.95 rather than NF1.4's 0.0) because this hypothesis was surfaced by re-reading
# NF-D15's field — a story born that way must not also be granted a looser bar than the field it was
# born in. The sensitivity at 0.0 and with the DSR dropped entirely is reported.
PBO_MAX = 0.2
DSR_MIN = 0.95
ALPHA = 0.10          # the single-hypothesis level under the PRE-REGISTERED pooled framing
FDR_Q = 0.10          # for the DISCLOSED per-position reading only — it does not gate

# The shrink grid, blended in OUTPUT space so λ = 0 IS the incumbent exactly for every form.
SHRINK_GRID = (0.25, 0.5, 0.75, 1.0)
FORMS = ("mult_const", "add_offset", "mult_tier", "ols_slope")
# ⭐ THREE ORDERING CLASSES, NOT TWO — and the middle one is why the claim is MEASURED every run.
#   · MONOTONE_FORMS       — strictly monotone within a position for ANY admissible parameter value
#                            (a positive constant; any additive offset) ⇒ ZERO rank movement BY
#                            CONSTRUCTION. The ordering constraint is non-binding for these.
#   · CONDITIONALLY_MONOTONE — monotone IFF the fitted parameters come back the right way round. An
#                            affine `a + b·point` moves no rank when `b > 0` and INVERTS a position's
#                            entire board when `b < 0`. So "the learned foil does no ordering harm" is
#                            a MEASUREMENT (`slope_signs`, `ordering_is_structural`), never a
#                            property of the form — and calling it "by construction" would be exactly
#                            the vacuous-check class this program keeps closing.
#   · REORDERING_FORMS     — genuinely reorder (two rookies in different draft tiers can swap). These
#                            are what give the ordering constraint something to refuse instead of
#                            passing having examined nothing.
MONOTONE_FORMS = ("mult_const", "add_offset")
CONDITIONALLY_MONOTONE_FORMS = ("ols_slope",)
REORDERING_FORMS = ("mult_tier",)
ORDERING_BINDING_FORMS = CONDITIONALLY_MONOTONE_FORMS + REORDERING_FORMS
LEARNED_FOIL = "ols_slope"

# ⭐ EACH FORM'S OWN PEEKING CEILING (NF1.7 (b) / NF1.9 (f): a peeking oracle is a floor only at
#    MATCHED FAMILY *and* MATCHED RESOLUTION). Flooring a richer family on the constant family's
#    ceiling would call a legitimate capacity effect a metric inversion.
FAMILY_CEILING = {"mult_const": "oracle_posconst", "add_offset": "oracle_addoffset",
                  "mult_tier": "oracle_tierconst", "ols_slope": "oracle_ols"}

# Physical bounds, not tuning knobs. A level correction that doubles or halves a whole position's
# board is not a recalibration, it is a different projection — and the UPPER bound is what stops one
# thin in-fold cell (a draft tier can hold a handful of rookies) from emitting a constant that
# single-handedly decides a position's MAE.
MULT_CLIP = (0.5, 2.5)
OFFSET_CLIP = (-60.0, 60.0)
# A ratio needs a denominator with signal in it: a rookie projected at 0.4 PPR contributes a ratio of
# 200 to a mean that is supposed to describe the board's level. The floor is on the DENOMINATOR only.
MIN_POINT = 5.0
MIN_CELL = 12          # rows required before a (position × tier) cell gets its own constant

# Forms that exist to CHARACTERISE the metric or to bound it — never to ship.
NON_SHIPPABLE = ("zero_scale", "pos_median", "oracle_perplayer", "permuted_across",
                 "permuted_within") + tuple(FAMILY_CEILING.values())

_REQUIRED_ANCHORS = (("oracle_perplayer", "permuted_across", "permuted_within",
                      "zero_scale", "pos_median") + tuple(FAMILY_CEILING.values()))

__all__ = [
    "MODEL_VERSION", "RECALIBRATED_POSITIONS", "EXCLUDED_POSITIONS", "PREREGISTERED_FRAMING",
    "PREREGISTERED_DSR_READING", "FRAMING_REASON", "PBO_MAX", "DSR_MIN", "ALPHA", "FDR_Q",
    "SHRINK_GRID", "FORMS", "MONOTONE_FORMS", "CONDITIONALLY_MONOTONE_FORMS", "REORDERING_FORMS",
    "ORDERING_BINDING_FORMS", "LEARNED_FOIL", "FAMILY_CEILING",
    "MULT_CLIP", "OFFSET_CLIP", "MIN_POINT", "MIN_CELL", "NON_SHIPPABLE",
    "SELECTION_METRIC", "ORDERING_DO_NO_HARM", "TIER_K", "SCALED_TIER_K",
    "apply_position_adjustment", "blend_toward_incumbent", "slot_tier",
    "fit_mult_const", "fit_add_offset", "fit_mult_tier", "fit_ols",
    "predict_form", "candidate_configs", "config_key", "require_anchors",
    "ordering_check", "ordering_is_structural", "scaled_positions_only",
    "family_ceiling_check", "pooled_ship", "recalibration_verdict", "read_the_ceiling_gap",
]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The primitives
# ══════════════════════════════════════════════════════════════════════════════════════════════
def apply_position_adjustment(point, positions, adjusted, *,
                              recalibrated_positions: tuple = RECALIBRATED_POSITIONS
                              ) -> np.ndarray:
    """⛔ THE SINGLE GATE BETWEEN A RECALIBRATION AND A POINT PROJECTION — and the ONLY place the QB
    exclusion lives in this story.

    Any position outside `recalibrated_positions` is returned UNCHANGED, whatever the arm computed.
    That makes "QB is excluded" a property of the code rather than of every arm remembering to honour
    it, which matters because the anchors (`zero_scale`, the oracles) are exactly the arms most likely
    to be written without the exclusion in mind — and an oracle that silently recalibrated QB would be
    scoring a different question than every candidate it is compared against.

    A non-finite adjustment falls back to the incumbent point. That is the honest degradation of "I
    have no level read for this position": leave the projection alone, never blank a rookie off the
    board. The output is floored at 0 because a fantasy projection cannot be negative — physical, and
    the one place an ADDITIVE form could otherwise emit an impossible number."""
    p = np.asarray(point, dtype=float)
    a = np.asarray(adjusted, dtype=float)
    out = np.where(np.isfinite(a), a, p)
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    out = np.where(np.isin(pos, tuple(recalibrated_positions)), out, p)
    return np.clip(out, 0.0, None)


def blend_toward_incumbent(point, adjusted, lam: float) -> np.ndarray:
    """The SHRINK, in OUTPUT space: `point + λ · (adjusted − point)`.

    ⭐ `λ = 0` reproduces the incumbent EXACTLY for EVERY form, which is what makes the grid an honest
    shrink toward "no recalibration" rather than a knob that quietly changes shape at its zero end.

    Output-space rather than parameter-space on purpose. NF-D15 shrank GEOMETRICALLY in the scale
    (`k**λ`), which is only defined for a multiplicative arm. This field holds a multiplicative, an
    additive and an affine form, and a knob that meant three different things across them would make
    the λ grid an uncontrolled difference between arms rather than the controlled one it is for."""
    lam = float(lam)
    p = np.asarray(point, dtype=float)
    a = np.asarray(adjusted, dtype=float)
    if lam == 0.0:
        return p.copy()
    return p + lam * (np.where(np.isfinite(a), a, p) - p)


def slot_tier(overall) -> np.ndarray:
    """Draft-slot buckets for the `mult_tier` form — `season_projection._slot_bucket`'s own boundaries,
    reused rather than re-chosen so the tier form is expressed in the same slot geometry the served
    point projection is built on. A missing pick lands in the last bucket, exactly as the served curve
    does its own fallback."""
    from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP
    o = pd.to_numeric(pd.Series(overall), errors="coerce").to_numpy(dtype=float)
    return np.array([SP._slot_bucket(x) if np.isfinite(x) else "101+" for x in o], dtype=object)


def _usable(point: np.ndarray, real: np.ndarray, *, min_point: float = MIN_POINT) -> np.ndarray:
    return np.isfinite(point) & np.isfinite(real) & (point >= float(min_point))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The four pre-registered fits — ALL strictly in-fold
# ══════════════════════════════════════════════════════════════════════════════════════════════
def fit_mult_const(point, real, positions, *, positions_scope: tuple = RECALIBRATED_POSITIONS,
                   clip: tuple = MULT_CLIP, min_point: float = MIN_POINT) -> dict:
    """Per-position MULTIPLICATIVE constant: the in-fold MEAN of `realized / point`.

    ⭐ This is the CLEAN statement of the hypothesis, deliberately not inherited from NF-D15's
    `mean_ratio` arm. That arm was the per-position mean of a DEPTH-derived availability ratio, so
    reusing it would drag NF-D14's week-1-vs-August depth provenance caveat into a story that reads no
    depth feature at all. Estimating the constant directly from `realized / point` keeps NF-D16's
    inputs to two quantities the board already owns.

    The mean of per-player RATIOS (not the ratio of means) because the hypothesis is about the level of
    a per-player projection; the denominator floor is what keeps a rookie projected at 0.4 PPR from
    contributing a ratio of 200 to a statistic meant to describe the board."""
    p = np.asarray(point, dtype=float)
    y = np.asarray(real, dtype=float)
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    ok = _usable(p, y, min_point=min_point)
    out: dict[str, float] = {}
    for q in positions_scope:
        sel = ok & (pos == q)
        if sel.sum() >= 3:
            out[q] = float(np.clip(np.mean(y[sel] / p[sel]), clip[0], clip[1]))
    return out


def fit_add_offset(point, real, positions, *, positions_scope: tuple = RECALIBRATED_POSITIONS,
                   clip: tuple = OFFSET_CLIP) -> dict:
    """Per-position ADDITIVE offset: the in-fold MEAN of `realized − point`.

    A genuinely different SHAPE from `mult_const`, not a reparametrisation of it: an additive offset
    moves the bottom of a position's board by exactly as much as the top, while a multiplicative one
    moves the top most. NF1.4's diagnosis places the defect at the TOP of the board, so the two forms
    make opposite predictions about where the correction should land — which is why both are
    registered rather than one standing in for the other.

    ⭐ No denominator floor is needed here: an additive statistic has no denominator, so unlike
    `mult_const` this form uses the FULL in-fold population. That is a real difference between the
    arms and it is stated rather than hidden."""
    p = np.asarray(point, dtype=float)
    y = np.asarray(real, dtype=float)
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    ok = np.isfinite(p) & np.isfinite(y)
    out: dict[str, float] = {}
    for q in positions_scope:
        sel = ok & (pos == q)
        if sel.sum() >= 3:
            out[q] = float(np.clip(np.mean(y[sel] - p[sel]), clip[0], clip[1]))
    return out


def fit_mult_tier(point, real, positions, tiers, *,
                  positions_scope: tuple = RECALIBRATED_POSITIONS, clip: tuple = MULT_CLIP,
                  min_point: float = MIN_POINT, min_cell: int = MIN_CELL) -> dict:
    """Per-position × DRAFT-TIER multiplicative constant, falling back to the position's own constant
    for a thin cell.

    NF1.4's own diagnosis is that the cold bias lives at the TOP of the rookie board, so a correction
    that is UNIFORM across draft slot may simply be the wrong shape — this form is what tests that,
    and it is the reason "a per-position constant" is not the only prescribed arm in the field.

    ⚠️ The fallback is what keeps a 4-rookie cell from emitting its own constant, and it is a FALLBACK
    rather than a skip: a cell with no estimate inherits the position's level, so the form degrades
    into `mult_const` locally instead of leaving those rookies uncorrected while their neighbours move
    (which would be an ordering artefact manufactured by the estimator's thinness)."""
    p = np.asarray(point, dtype=float)
    y = np.asarray(real, dtype=float)
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    tie = np.asarray([str(t) for t in np.asarray(tiers, dtype=object)], dtype=object)
    ok = _usable(p, y, min_point=min_point)
    base = fit_mult_const(point, real, positions, positions_scope=positions_scope, clip=clip,
                          min_point=min_point)
    out: dict[tuple, float] = {}
    for q in positions_scope:
        for t in np.unique(tie):
            sel = ok & (pos == q) & (tie == t)
            out[(q, str(t))] = (float(np.clip(np.mean(y[sel] / p[sel]), clip[0], clip[1]))
                                if sel.sum() >= min_cell else base.get(q, np.nan))
    return out


def fit_ols(point, real, positions, *, positions_scope: tuple = RECALIBRATED_POSITIONS,
            min_n: int = 20) -> dict:
    """THE DIRECT-LEARNED FOIL — per-position OLS of realized on predicted, `(intercept, slope)`.

    It differs from the prescribed forms ONLY in that the SHAPE of the correction is learned rather
    than prescribed: `mult_const` is this fit with the intercept forced to 0, `add_offset` is it with
    the slope forced to 1. So a win here is attributable to the learning, and — more usefully — a LOSS
    here is the strongest available evidence that the prescribed constant is the right shape, since
    the foil was free to discover any affine correction including both constants.

    Deliberately no regularisation and no higher-order terms: ~400 in-fold rows across three positions
    is enough for two parameters per position and nowhere near enough for more, and an over-fitted foil
    makes for a dishonest bake-off in the direction that flatters the prescribed arms."""
    p = np.asarray(point, dtype=float)
    y = np.asarray(real, dtype=float)
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    ok = np.isfinite(p) & np.isfinite(y)
    out: dict[str, tuple] = {}
    for q in positions_scope:
        sel = ok & (pos == q)
        if sel.sum() >= min_n and float(np.std(p[sel])) > 1e-9:
            b, a = np.polyfit(p[sel], y[sel], 1)
            out[q] = (float(a), float(b))
    return out


def predict_form(form: str, params: dict, point, positions, tiers=None) -> np.ndarray:
    """Apply one fitted form to a held-out class. Returns the ADJUSTED point BEFORE the λ blend and
    before `apply_position_adjustment` — the two are separate steps so the QB gate and the shrink can
    each be unit-tested without the other, and so no form can accidentally own its own copy of either.

    A position with no fitted parameter yields NaN, which `apply_position_adjustment` turns back into
    the incumbent. A missing estimate must degrade to "leave it alone", never to a silent zero."""
    p = np.asarray(point, dtype=float)
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    out = np.full(len(p), np.nan)
    if form == "mult_const":
        for q, k in params.items():
            out[pos == q] = p[pos == q] * float(k)
    elif form == "add_offset":
        for q, c in params.items():
            out[pos == q] = p[pos == q] + float(c)
    elif form == "mult_tier":
        tie = np.asarray([str(t) for t in np.asarray(tiers, dtype=object)], dtype=object)
        for (q, t), k in params.items():
            sel = (pos == q) & (tie == t)
            if sel.any() and np.isfinite(k):
                out[sel] = p[sel] * float(k)
    elif form == "ols_slope":
        for q, (a, b) in params.items():
            out[pos == q] = float(a) + float(b) * p[pos == q]
    else:
        raise ValueError(f"unknown form {form!r}")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered grid (EVERY config counts toward PBO/DSR — §0.5)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def candidate_configs(*, smoke: bool = False) -> list[dict]:
    """The full pre-registered candidate list, fixed before any result was read: the incumbent NULL
    plus four correction FORMS across the shrink grid."""
    cfgs = [{"label": "incumbent (NULL)", "form": "incumbent", "lam": 0.0,
             "recalibrates": False, "shippable": True}]
    lams = (1.0,) if smoke else SHRINK_GRID
    forms = FORMS[:2] + (LEARNED_FOIL,) if smoke else FORMS
    for form in forms:
        for lam in lams:
            cfgs.append({"label": f"{form} · λ {lam:g}", "form": form, "lam": float(lam),
                         "recalibrates": True, "shippable": True,
                         "monotone": form in MONOTONE_FORMS,
                         "learned": form == LEARNED_FOIL})
    return cfgs


def config_key(cfg: dict) -> str:
    return f"{cfg['form']}@{float(cfg.get('lam', 0.0)):g}"


def require_anchors(scored: dict, required: tuple = _REQUIRED_ANCHORS) -> None:
    """⭐ A MISSING ANCHOR IS A HARD FAILURE, NEVER A PASS (NF1.7 anchor lesson (a)).

    An anchor that fails to fit makes its own check VACUOUSLY TRUE — `winner < anchor` against an
    absent anchor compares nothing and reports green. NF1.7 shipped exactly that bug once; every
    anchored story since carries this guard, and it is a function rather than an inline `if` so it can
    be unit-tested without running the bake-off."""
    missing = [k for k in required
               if k not in scored or scored[k].get(SELECTION_METRIC) is None]
    if missing:
        raise SystemExit(
            f"the anchor(s) {missing} did not score — their checks would pass on NOTHING. Fix the "
            "anchor before reading any selection (NF1.7 anchor-set lesson 1).")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Ordering — the constraint, and the proof that it is non-vacuous
# ══════════════════════════════════════════════════════════════════════════════════════════════
def ordering_is_structural(form: str, point, positions, adjusted, *,
                           positions_scope: tuple = RECALIBRATED_POSITIONS) -> dict:
    """⭐ MEASURE the "zero ordering movement BY CONSTRUCTION" claim on real emitted projections rather
    than asserting it from the form's algebra.

    `mult_const` and `add_offset` are strictly monotone within a position, so the within-position rank
    vector must be BYTE-IDENTICAL to the incumbent's — max rank movement exactly 0. Two things can
    break that in practice and neither is visible in the algebra: a multiplicative constant that
    clipped to a different value in different cells, and the physical floor at 0 creating TIES among
    rookies an additive offset pushed below zero. So the claim is checked, per position, on the
    numbers the arm actually emits.

    Returns the max within-position rank movement per position and whether the structural claim holds
    for this form. A form that is NOT expected to be monotone reports its movement too — that number
    is the reason the ordering constraint has something to refuse."""
    p = np.asarray(point, dtype=float)
    a = np.asarray(adjusted, dtype=float)
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    per: dict[str, float] = {}
    for q in positions_scope:
        sel = pos == q
        if sel.sum() < 2:
            continue
        rb = pd.Series(p[sel]).rank(ascending=False, method="average").to_numpy()
        rc = pd.Series(a[sel]).rank(ascending=False, method="average").to_numpy()
        per[q] = float(np.max(np.abs(rb - rc)))
    worst = max(per.values()) if per else 0.0
    expected = form in MONOTONE_FORMS
    return {"form": form, "expected_monotone": expected, "max_rank_move_by_pos": per,
            "worst_rank_move": worst,
            "structural_claim_holds": (not expected) or worst == 0.0}


def family_ceiling_check(arms: list[dict], anchors: dict, *, metric: str = SELECTION_METRIC,
                         tol: float = 1e-9, family_ceiling: dict | None = None) -> dict:
    """⭐ EVERY ARM AGAINST **ITS OWN** FORM'S PEEKING CEILING — the NF1.7 (b) / NF1.9 (f) rule
    (matched family AND matched resolution) turned into a runnable check over the whole field.

    ⚠️ THE FIRST CUT OF THIS STORY FLOORED THE ENTIRE FIELD ON THE PER-POSITION CONSTANT CEILING, AND
    THAT WAS WRONG in a way that happened to pass. `mult_tier` (per position × draft tier) and
    `ols_slope` (per-position affine) are strictly RICHER families than a per-position constant: each
    of them CONTAINS the constant as a special case, so either can legitimately score better than the
    best possible constant. That is a capacity effect — the same one NF1.9 documented when its winner
    beat a coarser peeking oracle — and a single constant-family ceiling would have reported it as a
    metric inversion, i.e. it would have vetoed a real result for the wrong reason.

    Against its OWN form's peeking parameters, though, "peeking can only help" genuinely holds: the
    peeking fit minimises the same objective over the same parameter space on the very rows it is
    scored on. So an in-fold arm beating it IS a metric inversion, and this is the check that says so.

    A form with no registered ceiling, or a ceiling that failed to score, is a HARD FAILURE rather
    than a skip — an absent anchor passes on nothing (NF1.7 lesson (a)).

    ⭐ `family_ceiling` (added by NF-D18) lets a LATER story reuse this check with its OWN form → anchor
    map. It defaults to NF-D16's, so nothing here changes. The parameter exists because NF-D18's first
    run reported a hard failure on two arms whose ceilings had in fact been computed and scored: the
    check was reading NF-D16's dict, which does not contain NF-D18's forms, so every one of them
    resolved to `None`. That the failure surfaced as a LOUD refusal rather than a silent skip is the
    NF1.7 (a) rule working exactly as intended — but the correct cure is to let the check be told which
    map to use, not to let a story quietly re-implement it."""
    ceilings = FAMILY_CEILING if family_ceiling is None else dict(family_ceiling)
    per: list[dict] = []
    ok = True
    for r in arms:
        form = r.get("form")
        if not r.get("recalibrates") or form == "incumbent":
            continue
        tag = ceilings.get(form)
        ceiling = (anchors.get(tag) or {}).get(metric) if tag else None
        value = r.get(metric)
        if ceiling is None or value is None:
            per.append({"arm": r.get("label"), "form": form, "ceiling_anchor": tag,
                        "ceiling": ceiling, "arm_metric": value, "ok": False,
                        "note": "no scorable matched-family ceiling — the check would pass on NOTHING"})
            ok = False
            continue
        good = float(value) >= float(ceiling) - tol
        per.append({"arm": r.get("label"), "form": form, "ceiling_anchor": tag,
                    "ceiling": round(float(ceiling), 4), "arm_metric": round(float(value), 4),
                    "margin": round(float(value) - float(ceiling), 4), "ok": bool(good)})
        ok = ok and good
    return {"ok": bool(ok), "n_checked": len(per),
            "violations": [v for v in per if not v["ok"]], "per_arm": per}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The verdict — the PRE-REGISTERED pooled framing
# ══════════════════════════════════════════════════════════════════════════════════════════════
def pooled_ship(*, winner: dict | None, incumbent_metric: float | None, ordering: dict,
                pbo: float | None, dsr: float | None, pvalue: float | None,
                pbo_max: float = PBO_MAX, dsr_min: float = DSR_MIN,
                alpha: float = ALPHA) -> dict:
    """⭐ THE SHIP DECISION UNDER THE PRE-REGISTERED POOLED FRAMING — one hypothesis, one decision, and
    the ship unit is the WHOLE per-position constant vector (RB/TE/WR together or not at all).

    `pvalue` is the one-sided paired p over held-out draft classes on the pooled scale-free tier MAE,
    tested at `alpha` with NO multiplicity correction, because there is exactly one test. That is the
    substance of the pre-registration: NF-D15 paid a 3× BH penalty for a decomposition its hypothesis
    did not require, and this story decided in advance not to.

    ⚠️ The ORDERING constraint is still checked PER POSITION even though the decision is pooled — a
    pooled ρ can sit flat while one position's ordering collapses, and averaging is the exact operation
    that would hide the failure the constraint exists to catch (NF1.8, one axis over). A pooled
    hypothesis about the LEVEL does not license a pooled reading of the ORDER."""
    beats = bool(winner and incumbent_metric is not None and winner.get("metric") is not None
                 and float(winner["metric"]) < float(incumbent_metric))
    per_pos = (ordering or {}).get("per_position", {})
    checks = {
        "has_eligible_winner": winner is not None,
        "recalibrates": bool(winner and winner.get("recalibrates")),
        "beats_incumbent": beats,
        "ordering_ok_every_position": bool(per_pos) and all(v.get("ok", False)
                                                            for v in per_pos.values()),
        "pbo_ok": pbo is not None and pbo < pbo_max,
        "dsr_ok": dsr is not None and dsr >= dsr_min,
        "significant": pvalue is not None and float(pvalue) <= float(alpha),
    }
    return {"ship": all(checks.values()), "framing": PREREGISTERED_FRAMING, **checks}


def recalibration_verdict(*, pooled_ships: bool, degenerates_lose: bool,
                          permutation_across_beaten: bool, oracle_respected: bool,
                          family_ceiling_respected: bool, qb_untouched: bool) -> dict:
    """The STORY-level decision: the pre-registered pooled gate PLUS the run's global sanity anchors.

    ⚠️ The anchors are STORY-level VETOES on purpose. A degenerate winning the metric, or a constant
    arm beating the best possible constant, does not mean "this run was unlucky" — it means the
    measurement is not trustworthy anywhere in it, and no number computed from it may be shipped.

    ⭐ `family_ceiling_respected` is the anchor this story adds over NF-D15's set, and it is checked
    PER FORM against that form's OWN peeking ceiling (`family_ceiling_check`). NF-D15's single
    `oracle_posconst` was a floor at a COARSER resolution than its per-player candidates, so an honest
    arm could legitimately beat it (NF1.7 (b) / NF1.9 (f)); the same asymmetry exists INSIDE this
    field, since `mult_tier` and `ols_slope` each CONTAIN the per-position constant as a special case.
    Against its own form's peeking parameters, though, an in-fold arm cannot legitimately win — so a
    violation there is a metric inversion, and this veto says so."""
    checks = {
        "pooled_gate_passes": bool(pooled_ships),
        "degenerates_lose": bool(degenerates_lose),
        "permutation_across_beaten": bool(permutation_across_beaten),
        "oracle_respected": bool(oracle_respected),
        "family_ceiling_respected": bool(family_ceiling_respected),
        "qb_untouched": bool(qb_untouched),
    }
    return {"ship": all(checks.values()), **checks}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE CEILING GAP — the story's own scoping question, answered by computation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def read_the_ceiling_gap(*, incumbent: float | None, best_candidate: float | None,
                         ceiling: float | None, constant_stability: dict,
                         ceiling_anchor: str | None = None, constant_ceiling: float | None = None,
                         tol: float = 0.15) -> dict:
    """⭐ WHICH READING OF THE CEILING GAP DOES THE RUN SUPPORT? — decided by a measurement, not by
    prose.

    `ceiling` is the peeking version of the WINNER'S OWN form (`ceiling_anchor` names it), because that
    is the ceiling the winner is actually chasing; `constant_ceiling` is the per-position CONSTANT
    family's, reported beside it because the story's scoping question was posed on the constant. Using
    one family's ceiling to judge another's headroom is the same matched-family error
    `family_ceiling_check` exists to prevent, one statistic over.

    NF-D15 measured the constant ceiling at pooled tier MAE 0.9091 against the incumbent's 1.0738,
    while its best in-fold constant reached only 1.0301 — roughly a QUARTER of the available level
    headroom.

    That gap has two legitimate readings and they imply opposite next steps:
      (A) **ESTIMABLE** — there is real room for a BETTER-ESTIMATED constant, and a cleaner estimator
          closes more of it. ⇒ this story should find a bigger effect than its motivation did.
      (B) **CLASS-VARIABLE** — the correct constant swings strongly from draft class to draft class, so
          it is not learnable in-fold at all and the ceiling is unreachable in principle. ⇒ a NULL,
          and a null that no amount of further estimator work would overturn.

    The discriminator is `constant_stability`: whether the in-fold estimate PREDICTS the held-out
    class's own constant better than the incumbent's implicit constant of 1.0 does. If it does not,
    the truth is moving faster than any in-fold estimator can follow, which is reading (B) — and the
    strength of that reading is `skill_vs_null`, the fraction of the "predict 1.0" error the in-fold
    estimate removes.

    `tol` is the share of the headroom a candidate must capture before the run is called (A). It is a
    reporting threshold on a diagnostic, never a gate on the ship decision — no product outcome turns
    on it."""
    out = {"incumbent": incumbent, "best_candidate": best_candidate, "ceiling": ceiling,
           "ceiling_anchor": ceiling_anchor, "constant_family_ceiling": constant_ceiling,
           "headroom": None, "captured": None, "captured_share": None,
           "skill_vs_null": constant_stability.get("skill_vs_null"),
           "reading": "indeterminate"}
    if None in (incumbent, best_candidate, ceiling):
        return out
    headroom = float(incumbent) - float(ceiling)
    captured = float(incumbent) - float(best_candidate)
    out["headroom"] = round(headroom, 4)
    out["captured"] = round(captured, 4)
    out["captured_share"] = round(captured / headroom, 4) if abs(headroom) > 1e-9 else None
    skill = constant_stability.get("skill_vs_null")
    if out["captured_share"] is not None and out["captured_share"] >= tol and (skill or 0) > 0:
        out["reading"] = "A_estimable"
    elif skill is not None and skill <= 0:
        out["reading"] = "B_class_variable"
    elif out["captured_share"] is not None and out["captured_share"] < tol:
        out["reading"] = "B_class_variable"
    return out
