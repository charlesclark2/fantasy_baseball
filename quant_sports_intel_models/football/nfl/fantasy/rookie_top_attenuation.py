"""rookie_top_attenuation.py — NF-D18 pure model logic: does a rookie-point recalibration exist that
fixes the cold LEVEL/SHAPE bias WITHOUT over-placing the single top rookie on the merged draft board?

⚠️ THIS FILE IS THE PRE-REGISTRATION. Everything that could otherwise be chosen after seeing a result
— the forms, the constraint set, the metric, the framing, the deflation reading and its level, the
anchor set, the physical clips — is a CONSTANT here, written before the run. The runner READS these
rather than restating them, so "what was pre-registered" has exactly one owner.

────────────────────────────────────────────────────────────────────────────────────────────────────
WHY THIS STORY EXISTS — AND WHY IT IS A NEW HYPOTHESIS RATHER THAN A RE-READ OF NF-D16
────────────────────────────────────────────────────────────────────────────────────────────────────
NF-D16 pre-registered a per-position LEVEL recalibration of the rookie point and it CLEARED every gate
it registered (pooled draftable-tier MAE 1.0738 → 0.9407 over 7 held-out draft classes, positive in
all 7, PBO 0.029, whole-field DSR 0.996, p 0.0033; pooled bias −20.87 → −5.41, i.e. TOWARD zero — the
signature a genuine level correction produces). The winner was `ols_slope · λ 1`, a per-position
AFFINE. It is RATIFIED and it is NOT in question here.

It was nonetheless HELD from publish. Applied to the 2026 board the correction lifts the top rookie RB
to overall rank 6, and NF1.4's face-validity PLACEMENT clause admits no rookie inside the overall top
10. NF-D17 then re-specified that clause under its own pre-registration and **came back the other
way**: the clause is VALIDATED, not mis-specified (cap Q10 = 8.8 against the incumbent's 10 — about
one board slot — and reality breaches "no rookie in the overall top 10" in 2 of 7 seasons, 29%,
against the corrected LEVEL clause's own 9/28, 32%). Rank 6 sits outside the reference's ENTIRE
observed support (observed minimum 7), so the veto is genuine and threshold-invariant.

⇒ The correction is right ON AVERAGE and over-places at the very TOP. NF-D18 asks — as a NEW
hypothesis, pre-registered before the 2026 board is re-read — whether a correction exists that keeps
the accuracy gain while leaving the top rookie where the placement clause admits.

⛔ **THIS IS NEVER A λ RE-PICK, AND THE FILE ENFORCES THAT STRUCTURALLY.** NF-D16 pre-registered a
shrink grid and SELECTED λ = 1. Re-opening λ after seeing a constraint result is the E2.1-r inversion
(a selection parameter re-picked once its answer is known). So **every candidate in this field runs at
λ = 1** (`FIXED_LAMBDA`); there is no shrink knob in this story at all. The globally-shrunk affine —
the forbidden move — appears ONLY as a NON-SHIPPABLE MATCHED FOIL (below), where its job is to test
this story's own mechanism claim rather than to be selected.

────────────────────────────────────────────────────────────────────────────────────────────────────
🚩 THE A-PRIORI RISK, STATED BEFORE THE RUN — THIS STORY EXPECTS TO FAIL, AND SAYS WHY
────────────────────────────────────────────────────────────────────────────────────────────────────
NF-D16's own fitted parameters say where its lift comes from, and it is NOT a level shift: the served
fit is `RB (a 4.85, b 1.376) · TE (a 3.02, b 1.276) · WR (a 18.44, b 1.002)` — dominated by SLOPE, and
NF-D16's `add_offset` arm (a pure additive level, no slope) scored EXACTLY the incumbent at every λ.
A slope correction lifts the TOP of a position's board MOST and the bottom least. The selection metric
is NF1.4's DRAFTABLE-TIER MAE — the top ~6 RB / 8 WR / 3 TE. **So the region a top-attenuating form
must give up is precisely the region the metric grades and the region the defect lives in.**

That is registered here as the honest prior: the plausible outcome is a NULL in which every form that
clears the placement cap has surrendered the gain. The one structural reason it might not be is that
the two constraints act at different resolutions — the placement clause binds on the SINGLE best
rookie, while the metric grades a TIER of six. A form whose attenuation is concentrated in the extreme
upper tail could in principle satisfy one without paying the other. Whether such a shape is what the
DATA actually supports is the empirical question, and it is answered by fitting every form in-fold and
reading the result, never by choosing an attenuation strength that produces the desired rank.

────────────────────────────────────────────────────────────────────────────────────────────────────
PRE-REGISTERED FORMS (≥3 correction classes + a direct-learned foil + the incumbent NULL, per §0.5)
────────────────────────────────────────────────────────────────────────────────────────────────────
Every form is fitted STRICTLY IN-FOLD, PER POSITION, at λ = 1, and every one of them has **no free
strength dial**: its shape is estimated from the prior draft classes, never chosen to satisfy the 2026
constraint. That property is what separates this story from the reverse-engineering it must not do —
whichever arms clear the placement cap do so as a CONSEQUENCE of a fitted shape.

  • `incumbent`  — THE NULL: the rookie point as SERVED TODAY (NF-D16's flip is off). In the field,
                   and it can win. Its placement is the bar the field has to match: the served board
                   places its top rookie at overall rank 12, which clears the cap threshold-invariantly.
  • `ols_slope`  — ⭐ NF-D16's RATIFIED AFFINE, imported verbatim from `rookie_point_recalibration`.
                   THE REFERENCE ARM — the correction being attenuated, carried at full strength and
                   flagged SHIPPABLE so the placement constraint has something to REFUSE. A field of
                   only attenuated forms would leave that constraint passing having examined nothing,
                   which is the NF1.7 vacuous-anchor class wearing NF-D16's `mult_tier` hat.
  • `power`      — CONCAVE POWER, the canonical top-attenuating shape: `f(x) = s·e^c·(1+x)^γ − 1`,
                   fitted per position by OLS of `log1p(y)` on `log1p(x)`. Strictly increasing for
                   γ > 0 (⇒ zero within-position rank movement) and CONCAVE for γ < 1, so the lift it
                   applies decays with the projection — attenuation by SHAPE, expressed in the one
                   parameter the data estimates.
                   ⭐ `s` is DUAN'S SMEARING ESTIMATOR (`mean(exp(residual))`) and it is not optional:
                   an un-smeared log-scale fit estimates a conditional MEDIAN, which is systematically
                   LOW at every x. Carrying that would confound "attenuates at the top" with
                   "attenuates everywhere" — the exact confound the matched foil exists to separate,
                   so the arm must not import it in the first place.
                   ⚠️ `log1p` rather than `log`: `log(y)` would silently DROP the ~15% of drafted
                   rookies who score zero, making this arm's fit population different from the
                   reference affine's. A form must not win by being graded on a different population.
  • `huber`      — ROBUST AFFINE: the same affine family as the reference, fitted with a Huber loss
                   (ε = 1.35, the literature's 95%-efficiency default, inherited rather than tuned).
                   It attenuates through a DIFFERENT CHANNEL — the ESTIMATOR's sensitivity to the
                   handful of extreme realized outcomes that steepen an OLS slope — rather than
                   through the correction's shape. If the reference's steep slope is driven by a few
                   outlier rookie seasons, this arm finds a gentler one from the same family.
  • `qmap`       — MONOTONE QUANTILE MAPPING: each rookie's within-position PERCENTILE among the
                   in-fold point projections is mapped to that percentile of the in-fold REALIZED
                   distribution. Rank-preserving by construction (a non-decreasing composition), no
                   free parameter at all, and it is the principled answer to "where should the top
                   rookie sit?" — it places him exactly where the realized best-rookie distribution
                   says, which is the same reference NF-D17's placement cap is derived from.
                   ⚠️ It makes the OPPOSITE prediction to `power`: the realized rookie distribution is
                   right-skewed, so quantile matching may EXPAND rather than attenuate the top. It is
                   registered because a field containing only forms expected to help is a field that
                   cannot be surprised.
  • `isotonic`   — ⭐ THE DIRECT-LEARNED FOIL: per-position isotonic (PAV) regression of realized on
                   predicted. The RICHEST monotone family — it CONTAINS the affine (positive slope),
                   the power (γ > 0) and every concave map in this field as special cases — so it is
                   free to discover ANY monotone attenuation the data supports, including none. A LOSS
                   here is the strongest available evidence that no monotone re-shaping helps; a WIN
                   is attributable to the learning rather than to a prescribed shape.
                   ⚠️ Isotonic is WEAKLY monotone: its flat segments create TIES, and a tie IS rank
                   movement. So this arm can genuinely fail do-no-ordering-harm — measured, never
                   assumed.

────────────────────────────────────────────────────────────────────────────────────────────────────
⭐ THE MATCHED GLOBAL FOIL — the control the story's own claim turns on (NF-D10 (g) / NF-D15 (g′))
────────────────────────────────────────────────────────────────────────────────────────────────────
This story's claim, if anything ships, is that a top-attenuating SHAPE buys a placement clearance that
a uniformly weaker correction does not. That claim is refutable and must be refuted or corroborated by
a control, not asserted: NF-D15 shipped a lift explained by a mechanism its own matched foil then
REFUTED, and the lesson is that "my arm won" is not "it won for the reason I said".

So every attenuating arm `A` is paired with `global_match(A)`: the REFERENCE AFFINE shrunk globally to
the SAME mean absolute correction over the held-out draftable tier. Same family, same magnitude,
UNIFORM instead of shaped — everything except the claimed channel.

  · A clears placement and its matched foil does NOT  ⇒ the SHAPE earned it.
  · both clear                                        ⇒ MAGNITUDE is the mechanism, the story's
                                                        premise is refuted, and the honest fix would be
                                                        a global λ — which is exactly what §6 forbids.
  · paired tier-MAE delta (A − foil)                  ⇒ what the shape costs or buys in accuracy.

⛔ The matched foils are NON-SHIPPABLE and are EXCLUDED from the DSR trial field and from the PBO
eligible set. A DIAGNOSTIC ANCHOR IS NEVER A TRIAL (MH2 (a)): NF-D16's sibling programme had an oracle
leak into a DSR trial field and set the gate's own bar arithmetically. These foils exist to police an
attribution, so they must not price the multiplicity of a search nobody ran.

────────────────────────────────────────────────────────────────────────────────────────────────────
THE CONSTRAINT SET — BOTH BINDING ON ELIGIBILITY, BOTH FIXED IN WRITING BEFORE THE RUN
────────────────────────────────────────────────────────────────────────────────────────────────────
  C1 · DO NO ORDERING HARM — NF1.4's `ORDERING_DO_NO_HARM = 0.02` on the within-position rank
       correlation against the incumbent, checked PER POSITION and never as a pooled mean (a pooled ρ
       can sit flat while one position's ordering collapses). Inherited verbatim by import.
  C2 · THE NF-D17 PLACEMENT CAP, THRESHOLD-INVARIANT — on the emitted board the best rookie's OVERALL
       rank must clear the cap at EVERY quantile in NF-D17's own Q05–Q25 band AND against reality's
       observed MINIMUM realized rank. Delegated verbatim to `season_projection.rookie_placement_breach`;
       this story introduces NO new threshold and NO new reference.
       ⭐ THE INVARIANCE REQUIREMENT IS THE WHOLE POINT AND IT MIRRORS THE VETO. NF-D17's veto held
       across the entire band (caps 7.90 / 8.80 / 9.70 / 10.60 / 11.50) and against the observed
       minimum 7. A SHIP must clear on the same terms — clearing only at a cap one would pick after
       seeing the result is the E2.1-r inversion facing the other way. There is therefore no threshold
       left to choose: `rank ≥ 11.5`, i.e. rank 12 or worse, is the whole constraint.
       The other two clauses of NF1.4's advisory gate (the #1 overall slot is not a rookie; no rookie
       inside the overall top 10; and the LEVEL cap) are required to pass alongside it.

⚠️ **PLACEMENT IS AN ELIGIBILITY CONSTRAINT, NOT A POST-HOC VETO, AND THAT CHOICE IS DISCLOSED.**
NF-D16 applied its face-validity check as a veto on the arm the metric had already selected. Doing
that here would make the story VACUOUS: the least-attenuated arm wins the tier metric by construction
and is exactly the arm the cap refuses, so the answer would be fixed before any data was read. The
question this story was asked — does a correction exist that clears BOTH — requires the constraint to
act on the eligible SET, exactly as the ordering constraint already does. The cost is that ONE board
influences which of six discrete forms is selected; the deflation is computed over that eligible set,
no arm's PARAMETERS are ever tuned to the board, and §"limitations" states it plainly. The
ordering-only reading (NF-D16's convention) is COMPUTED AND REPORTED beside the pre-registered one.

────────────────────────────────────────────────────────────────────────────────────────────────────
METRIC · FRAMING · DEFLATION — INHERITED, NOT RE-CHOSEN
────────────────────────────────────────────────────────────────────────────────────────────────────
  · METRIC  — NF1.4's `tier_mae`, imported. The incumbent rookie point was selected on it and NF-D16
              was graded on it; grading the third change to the same product on a new metric is
              metric-shopping.
  · FRAMING — POOLED, inherited from NF-D16 with its reason unchanged: the ship UNIT is one change to
              `project_rookies` that applies at RB/TE/WR together or not at all. The per-position
              reading is computed as a DISCLOSURE and does not gate.
  · DSR     — WHOLE-FIELD reading BINDS, level 0.95; PBO < 0.2; α = 0.10 single-hypothesis. All
              inherited from NF-D16 verbatim. Sensitivities at DSR ≥ 0 and with the DSR removed are
              reported so a reader can see whether a gate level decided the answer.

────────────────────────────────────────────────────────────────────────────────────────────────────
⚠️ TWO-SIDED ANCHORS — AND ONE OF THEM BEHAVES DIFFERENTLY HERE THAN IT DID IN NF-D16
────────────────────────────────────────────────────────────────────────────────────────────────────
  · `oracle_perplayer`  — the ORACLE FLOOR at full resolution. Nothing may beat it.
  · a PEEKING CEILING **PER FORM** — `oracle_ols`, `oracle_power`, `oracle_huber`, `oracle_qmap`,
    `oracle_isotonic`: each form's OWN estimator fitted on the HELD-OUT class. ⭐ ONE CEILING FOR THE
    WHOLE FIELD WOULD BE MIS-SPECIFIED and NF-D16 shipped exactly that bug in its first cut: a peeking
    oracle is a floor only at MATCHED FAMILY *and* MATCHED RESOLUTION (NF1.7 (b) / NF1.9 (f)), and the
    families here NEST — `isotonic` contains every other form in the field — so a richer family can
    legitimately beat a coarser one's ceiling. That is a CAPACITY effect, not a metric inversion, and
    the ceilings are expected to ORDER by capacity (isotonic lowest).
  · `permuted_across`   — corrections estimated from realized outcomes shuffled ACROSS positions. The
                          per-position structure destroyed. Must LOSE.
  · `permuted_within`   — ⭐⭐ **THE ANCHOR THAT WAS VACUOUS IN NF-D16 AND IS PREDICTED TO BITE HERE,
                          AND SAYING SO IN ADVANCE IS THE POINT.** NF-D16 measured its within-position
                          permutation as EXACTLY invariant (max |Δ| 7.1e-15) because a LEVEL is a
                          MARGINAL statistic and a within-position shuffle preserves the marginal.
                          NF-D18's forms are not level statistics — every one of them estimates the
                          SHAPE of realized-given-predicted, which a within-position shuffle
                          DESTROYS while preserving that position's marginal exactly. So the anchor
                          that could not act on NF-D16's hypothesis is a genuine test of NF-D18's, and
                          it is PRE-REGISTERED TO BE BEATEN rather than to tie. If it is not beaten,
                          the shapes carry nothing a shuffled outcome vector would not also give.
  · `zero_scale`        — DEGENERATE CEILING: project nothing.
  · `pos_median`        — DEGENERATE CEILING: NF1.4's MAE-collapse tell (the in-fold position median
                          for everyone) — the arm that WINS an inverted metric.

⭐ AND THE DEGENERATES DO A SECOND JOB IN THIS STORY, WHICH IS WHY THEIR PLACEMENT IS ALSO SCORED.
`zero_scale` SATISFIES the placement cap trivially (a board of zero-projected rookies places none of
them). NF1.8's rule is that a CONSTRAINT a degenerate satisfies is fine — the metric then eliminates
it — while a CRITERION a degenerate WINS is fatal. Reporting that the placement cap is the former is
what proves this story did not quietly promote a constraint into a selection criterion.
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
    apply_position_adjustment,
    blend_toward_incumbent,
    family_ceiling_check,
    fit_ols,
    ordering_check,
    scaled_positions_only,
)
from quant_sports_intel_models.football.nfl.fantasy.rookie_point_scaling import SCALED_TIER_K

MODEL_VERSION = "nfl_fantasy_nf_d18_rookie_top_attenuation_v1"

# ⛔ SCOPE, INHERITED BY IMPORT (through NF-D16, which inherits it from NF-D15) so no story in this
#    chain can drift on which positions may be touched. QB is excluded because NF-D14 MEASURED the
#    rookie-QB double-pricing; NF-D18 does not re-open it, and `apply_position_adjustment` is the
#    single gate every arm — candidate, degenerate, matched foil and oracle alike — passes through.
ATTENUATED_POSITIONS = RECALIBRATED_POSITIONS
EXCLUDED_POSITIONS = ("QB",)

# ── THE PRE-REGISTERED FRAMING AND GATES, RECORDED AS DATA SO THE REPORT CANNOT QUIETLY DISAGREE ──
PREREGISTERED_FRAMING = "pooled"
PREREGISTERED_DSR_READING = "whole_field"
FRAMING_REASON = (
    "INHERITED FROM NF-D16 VERBATIM, and inheriting rather than re-deciding is itself the point: this "
    "is the third pre-registered change asked of ONE product, and a framing re-chosen per story is a "
    "framing chosen for its answer. The ship UNIT is one change to `project_rookies` that applies at "
    "RB/TE/WR together or not at all, so the hypothesis is ONE claim and gets ONE test. The "
    "per-position reading is computed as a DISCLOSURE and does not gate."
)
ELIGIBILITY_REASON = (
    "The PLACEMENT cap acts on ELIGIBILITY, not as a post-hoc veto on an already-selected arm. As a "
    "veto the story would be vacuous — the least-attenuated arm wins the tier metric by construction "
    "and is precisely the arm the cap refuses, so the answer would be fixed before any data was read. "
    "The question asked was whether an arm exists that clears BOTH constraints, which requires the "
    "constraint to act on the eligible SET exactly as do-no-ordering-harm already does. No arm's "
    "PARAMETERS are tuned to the board; only the discrete FORM choice is filtered, deflation is "
    "computed over that eligible set, and the ordering-only reading is reported beside it."
)

# Deflation gates and the significance level — INHERITED FROM NF-D16 BY IMPORT (PBO_MAX, DSR_MIN,
# ALPHA), so a reader checking "did the bar move between the story that shipped and the story that
# wants to publish it" finds one owner rather than two copies that can drift.
FDR_Q = 0.10          # the DISCLOSED per-position reading only — it does not gate

# ⛔ λ IS NOT A KNOB IN THIS STORY. NF-D16 pre-registered a shrink grid and selected λ = 1; re-opening
#    it after seeing a constraint result is the E2.1-r inversion. Every candidate runs here.
FIXED_LAMBDA = 1.0

REFERENCE_FORM = "ols_slope"          # NF-D16's ratified affine — the correction being attenuated
LEARNED_FOIL = "isotonic"             # the richest monotone family; contains every other form
ATTENUATION_FORMS = ("power", "huber", "qmap", "isotonic")
FORMS = (REFERENCE_FORM,) + ATTENUATION_FORMS

# ⭐ THREE ORDERING CLASSES, and the middle one is why the claim is MEASURED on every run rather than
#    asserted from the algebra (NF-D16 method lock 2). NOTHING in this field is monotone for ALL
#    admissible parameter values — an affine inverts a board on a negative slope, a power does on a
#    negative exponent — so the honest classification is that everything here is CONDITIONAL except
#    the quantile map, whose monotonicity is a property of composing two non-decreasing functions.
MONOTONE_FORMS = ("qmap",)
CONDITIONALLY_MONOTONE_FORMS = ("ols_slope", "power", "huber")
REORDERING_FORMS = ("isotonic",)      # weakly monotone: flat segments TIE, and a tie IS rank movement
ORDERING_BINDING_FORMS = CONDITIONALLY_MONOTONE_FORMS + REORDERING_FORMS

# ⭐ EACH FORM'S OWN PEEKING CEILING (NF1.7 (b) / NF1.9 (f)). The families NEST — `isotonic` contains
#    every other form here — so one ceiling for the field would veto a legitimately-better nested form
#    as a false metric inversion, which is the bug NF-D16's first cut shipped.
FAMILY_CEILING = {"ols_slope": "oracle_ols", "power": "oracle_power", "huber": "oracle_huber",
                  "qmap": "oracle_qmap", "isotonic": "oracle_isotonic"}

# The matched global foil's label prefix. One foil per attenuating arm; never shippable, never a trial.
MATCHED_FOIL_PREFIX = "global_match"
# ⚠️ WIDENED PAST 1.0 AFTER THE SMOKE RUN, AND THE REASON IS A DEFECT RATHER THAN A RESULT — DISCLOSED.
# The first cut clipped the foil's λ to [0, 1], i.e. it assumed every attenuating arm applies LESS
# correction than the reference. Two arms apply MORE, so their λ pinned at 1.0 and the "matched foil"
# became the REFERENCE ARM ITSELF, byte-identical — a control that examined NOTHING while reporting a
# clean pairing (the NF1.7 (a) vacuous-check class, in a diagnostic rather than an anchor). The bound
# is physical, not tuned: a uniform correction 4× the reference's is no longer the same mechanism.
# ⭐ THE FIX CANNOT MANUFACTURE A SHIP. The matched foils are non-shippable and are excluded from the
#    eligible set, from PBO's search and from the DSR trial field, so this touches only the ATTRIBUTION
#    disclosure — and it makes it honest in the direction that can only weaken a mechanism claim.
MATCHED_FOIL_LAMBDA_CLIP = (0.0, 4.0)

# Physical bounds, not tuning knobs — each one is there to stop a thin in-fold cell from emitting a
# correction that is a different projection rather than a recalibration.
POWER_GAMMA_CLIP = (0.25, 2.0)     # γ ≤ 0 would invert a position's board; γ > 2 is not an attenuation
POWER_SMEAR_CLIP = (0.5, 2.0)      # Duan's retransformation factor, bounded to a physical range
HUBER_EPSILON = 1.35               # the literature's 95%-efficiency default — inherited, never tuned
MIN_FIT_ROWS = 20                  # per position, matching `fit_ols`'s own floor
MIN_QMAP_ROWS = 30                 # a quantile map needs a distribution, not a handful of points

# Forms that exist to CHARACTERISE the metric, to bound it, or to police an attribution — never to ship.
NON_SHIPPABLE = (("zero_scale", "pos_median", "oracle_perplayer", "permuted_across",
                  "permuted_within") + tuple(FAMILY_CEILING.values()))

_REQUIRED_ANCHORS = (("oracle_perplayer", "permuted_across", "permuted_within",
                      "zero_scale", "pos_median") + tuple(FAMILY_CEILING.values()))

__all__ = [
    "MODEL_VERSION", "ATTENUATED_POSITIONS", "EXCLUDED_POSITIONS", "PREREGISTERED_FRAMING",
    "PREREGISTERED_DSR_READING", "FRAMING_REASON", "ELIGIBILITY_REASON", "PBO_MAX", "DSR_MIN",
    "ALPHA", "FDR_Q", "FIXED_LAMBDA", "REFERENCE_FORM", "LEARNED_FOIL", "ATTENUATION_FORMS", "FORMS",
    "MONOTONE_FORMS", "CONDITIONALLY_MONOTONE_FORMS", "REORDERING_FORMS", "ORDERING_BINDING_FORMS",
    "FAMILY_CEILING", "MATCHED_FOIL_PREFIX", "MATCHED_FOIL_LAMBDA_CLIP",
    "POWER_GAMMA_CLIP", "POWER_SMEAR_CLIP", "HUBER_EPSILON",
    "MIN_FIT_ROWS", "MIN_QMAP_ROWS", "MIN_POINT", "NON_SHIPPABLE",
    "SELECTION_METRIC", "ORDERING_DO_NO_HARM", "TIER_K", "SCALED_TIER_K",
    "apply_position_adjustment", "blend_toward_incumbent", "ordering_check", "scaled_positions_only",
    "family_ceiling_check", "fit_ols",
    "fit_power", "fit_huber", "fit_qmap", "fit_isotonic", "fit_form", "predict_form",
    "candidate_configs", "config_key", "require_anchors", "ordering_is_structural",
    "tier_mask", "matched_global_lambda", "placement_clearance", "board_placement",
    "attenuation_profile", "pooled_ship", "attenuation_verdict",
]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The five pre-registered fits — ALL strictly in-fold, ALL per position
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _clean(point, real, positions) -> tuple:
    p = np.asarray(point, dtype=float)
    y = np.asarray(real, dtype=float)
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    return p, y, pos, np.isfinite(p) & np.isfinite(y)


def fit_power(point, real, positions, *, positions_scope: tuple = ATTENUATED_POSITIONS,
              gamma_clip: tuple = POWER_GAMMA_CLIP, smear_clip: tuple = POWER_SMEAR_CLIP,
              min_n: int = MIN_FIT_ROWS) -> dict:
    """CONCAVE POWER — the canonical top-attenuating shape, `f(x) = s·e^c·(1+x)^γ − 1`.

    Fitted by OLS of `log1p(y)` on `log1p(x)`, which is the one specification in which "the lift
    decays with the projection" is a single estimated parameter (γ) rather than a knob somebody set.
    γ < 1 attenuates the top; γ > 1 would steepen it; γ is free to come back either way and the run
    reports which, because a form pre-registered as an attenuator that the data fits as an amplifier
    is a finding about the data.

    ⭐ `s` IS DUAN'S SMEARING ESTIMATOR — `mean(exp(residual))` on the log1p scale — AND IT IS
    LOAD-BEARING. Without it the arm predicts a conditional MEDIAN and therefore sits systematically
    LOW at every x, which would make it "attenuate everywhere" and confound the SHAPE mechanism this
    story is testing with a plain magnitude reduction. That confound is exactly what the matched global
    foil exists to detect, so the candidate must not carry it built in.

    ⚠️ `log1p` rather than `log`: a log fit drops every rookie who scored zero (~15% of the drafted
    population, 35% at QB), which would grade this arm on a DIFFERENT population than the reference
    affine. An arm must not win by being fitted on an easier subset.

    Both parameters are clipped to physical bounds — γ ≤ 0 would invert a whole position's board, and
    an unbounded smear on a thin cell can emit a multiplier that is a different projection rather than
    a recalibration."""
    p, y, pos, ok = _clean(point, real, positions)
    ok = ok & (p >= float(MIN_POINT)) & (y >= 0.0)
    out: dict[str, tuple] = {}
    for q in positions_scope:
        sel = ok & (pos == q)
        if sel.sum() < min_n:
            continue
        lx, ly = np.log1p(p[sel]), np.log1p(y[sel])
        if float(np.std(lx)) <= 1e-9:
            continue
        gamma, c = np.polyfit(lx, ly, 1)
        gamma = float(np.clip(gamma, gamma_clip[0], gamma_clip[1]))
        c = float(c)
        resid = ly - (c + gamma * lx)
        smear = float(np.clip(np.mean(np.exp(resid)), smear_clip[0], smear_clip[1]))
        out[q] = (c, gamma, smear)
    return out


def fit_huber(point, real, positions, *, positions_scope: tuple = ATTENUATED_POSITIONS,
              epsilon: float = HUBER_EPSILON, min_n: int = MIN_FIT_ROWS) -> dict:
    """ROBUST AFFINE — the reference's own family, fitted with a Huber loss instead of squared error.

    The attenuation channel here is the ESTIMATOR rather than the correction's shape: if the reference
    affine's steep slope is being set by a handful of extreme realized rookie seasons, a robust fit
    recovers a gentler one from the identical family. That makes it the arm that separates "the top
    needs less correction" from "the top few OUTCOMES were driving the estimate of how much correction
    everyone needs" — two different stories about the same number.

    ε = 1.35 is the literature's 95%-efficiency-under-normality default, INHERITED rather than tuned;
    tuning it would turn the robustness into the very strength dial this story forbids itself.
    Returns `(intercept, slope)`, the same shape `fit_ols` returns, so the two are interchangeable
    everywhere downstream and the ONLY difference between the arms is the loss."""
    from sklearn.linear_model import HuberRegressor

    p, y, pos, ok = _clean(point, real, positions)
    out: dict[str, tuple] = {}
    for q in positions_scope:
        sel = ok & (pos == q)
        if sel.sum() < min_n or float(np.std(p[sel])) <= 1e-9:
            continue
        try:
            m = HuberRegressor(epsilon=float(epsilon), max_iter=500).fit(
                p[sel].reshape(-1, 1), y[sel])
        except Exception:                                   # noqa: BLE001 — a failed fit is a SKIP,
            continue                                        # which degrades to the incumbent, never 0
        out[q] = (float(m.intercept_), float(m.coef_[0]))
    return out


def fit_qmap(point, real, positions, *, positions_scope: tuple = ATTENUATED_POSITIONS,
             min_n: int = MIN_QMAP_ROWS) -> dict:
    """MONOTONE QUANTILE MAPPING — place each rookie at the realized distribution's own quantile.

    The map is `x → Q_realized(F_point(x))`, both empirical and both in-fold. It is non-decreasing by
    construction (a composition of two non-decreasing interpolations), so it moves no rank except where
    the realized quantile function is FLAT — which it is at the bottom, where ~15% of drafted rookies
    score exactly zero. Those ties are real and are MEASURED by `ordering_is_structural`; they are the
    honest cost of matching a distribution with an atom in it.

    ⚠️ It is registered knowing it may make the placement WORSE, not better: the realized rookie
    distribution is right-skewed, so matching it can push the top projection UP. A field containing
    only forms expected to help cannot be surprised, and NF1.9's lesson is that a mechanism which
    acts the wrong way is a measurement rather than an omission.

    Stored as the two sorted vectors rather than a fitted parameter, because a quantile map HAS no
    parameters — which is also why it has no strength dial to tune."""
    p, y, pos, ok = _clean(point, real, positions)
    out: dict[str, tuple] = {}
    for q in positions_scope:
        sel = ok & (pos == q)
        if sel.sum() < min_n:
            continue
        out[q] = (np.sort(p[sel]), np.sort(y[sel]))
    return out


def fit_isotonic(point, real, positions, *, positions_scope: tuple = ATTENUATED_POSITIONS,
                 min_n: int = MIN_FIT_ROWS) -> dict:
    """THE DIRECT-LEARNED FOIL — per-position isotonic (PAV) regression of realized on predicted.

    The richest monotone family in this field: it CONTAINS the reference affine (positive slope), the
    power (γ > 0) and the quantile map as special cases, so it is free to discover any monotone
    re-shaping the data supports — including a flat top, including none at all. That is what makes its
    result readable in both directions. A LOSS here is the strongest evidence available that no
    monotone re-shaping of the rookie point helps, because the foil was free to find one; a WIN is
    attributable to learning rather than to a shape somebody prescribed.

    Deliberately unregularised, matching `fit_ols`'s own choice: ~130–200 in-fold rows per position is
    thin for a nonparametric fit and the arm will step, but a regularised foil that has been smoothed
    into the prescribed forms is not a foil. `out_of_bounds="clip"` extends the fitted map flat beyond
    the training range — which is itself a top-attenuation, and one the data chose rather than one this
    story imposed."""
    from sklearn.isotonic import IsotonicRegression

    p, y, pos, ok = _clean(point, real, positions)
    out: dict[str, object] = {}
    for q in positions_scope:
        sel = ok & (pos == q)
        if sel.sum() < min_n or float(np.std(p[sel])) <= 1e-9:
            continue
        out[q] = IsotonicRegression(increasing=True, out_of_bounds="clip").fit(p[sel], y[sel])
    return out


_FITTERS = {"ols_slope": fit_ols, "power": fit_power, "huber": fit_huber,
            "qmap": fit_qmap, "isotonic": fit_isotonic}


def fit_form(form: str, point, real, positions, **kw) -> dict:
    """Fit ONE registered form. A single dispatch point so a candidate, its peeking ceiling and its
    permutation anchor are provably the SAME estimator applied to different rows — the property that
    lets the anchors be read as anchors rather than merely described as such."""
    try:
        fitter = _FITTERS[form]
    except KeyError:                                        # noqa: PERF203
        raise ValueError(f"unknown form {form!r}") from None
    return fitter(point, real, positions, **kw)


def predict_form(form: str, params: dict, point, positions) -> np.ndarray:
    """Apply one fitted form to a held-out class. Returns the ADJUSTED point BEFORE the QB gate, so no
    form owns its own copy of the exclusion.

    A position with no fitted parameter yields NaN, which `apply_position_adjustment` turns back into
    the incumbent. A missing estimate must degrade to 'leave it alone', never to a silent zero."""
    p = np.asarray(point, dtype=float)
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    out = np.full(len(p), np.nan)
    if form in ("ols_slope", "huber"):
        for q, (a, b) in params.items():
            out[pos == q] = float(a) + float(b) * p[pos == q]
    elif form == "power":
        for q, (c, gamma, smear) in params.items():
            sel = pos == q
            out[sel] = float(smear) * np.exp(float(c) + float(gamma) * np.log1p(p[sel])) - 1.0
    elif form == "qmap":
        for q, (sp, sy) in params.items():
            sel = pos == q
            if not sel.any():
                continue
            u = np.linspace(0.0, 1.0, len(sp))
            out[sel] = np.interp(np.interp(p[sel], sp, u), u, sy)
    elif form == "isotonic":
        for q, model in params.items():
            sel = pos == q
            if sel.any():
                out[sel] = np.asarray(model.predict(p[sel]), dtype=float)
    else:
        raise ValueError(f"unknown form {form!r}")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered field (EVERY config counts toward PBO/DSR — §0.5)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def candidate_configs(*, smoke: bool = False) -> list[dict]:
    """The full pre-registered candidate list, fixed before any result was read: the incumbent NULL,
    NF-D16's ratified affine as the REFERENCE, and the four attenuating forms — every one of them at
    λ = 1, because λ is not a knob in this story."""
    cfgs = [{"label": "incumbent (NULL)", "form": "incumbent", "lam": 0.0,
             "recalibrates": False, "shippable": True, "attenuates": False}]
    forms = (REFERENCE_FORM, "power", LEARNED_FOIL) if smoke else FORMS
    for form in forms:
        cfgs.append({"label": form, "form": form, "lam": FIXED_LAMBDA,
                     "recalibrates": True, "shippable": True,
                     "attenuates": form in ATTENUATION_FORMS,
                     "monotone": form in MONOTONE_FORMS,
                     "learned": form == LEARNED_FOIL})
    return cfgs


def config_key(cfg: dict) -> str:
    return f"{cfg['form']}@{float(cfg.get('lam', 0.0)):g}"


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
# Ordering — MEASURED on emitted projections, never asserted from the algebra
# ══════════════════════════════════════════════════════════════════════════════════════════════
def ordering_is_structural(form: str, point, positions, adjusted, *,
                           positions_scope: tuple = ATTENUATED_POSITIONS) -> dict:
    """Max within-position rank movement, per position, on the numbers an arm ACTUALLY EMITS.

    NF-D16's method lock 2, inherited: 'zero ordering movement by construction' is a claim about a
    form's algebra under admissible parameters, and the parameters this run fitted are the only ones
    that matter. An affine inverts a position's board on a negative slope; a power does on a negative
    exponent; an isotonic map TIES wherever it is flat. Only `qmap` is monotone for every attainable
    parameter value, and even it ties at the realized distribution's zero atom.

    `structural_claim_holds` is therefore checked only for the forms registered as MONOTONE_FORMS —
    for everything else the number is reported as the measurement that gives the ordering constraint
    something to refuse."""
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


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE MATCHED GLOBAL FOIL — magnitude held equal, SHAPE removed
# ══════════════════════════════════════════════════════════════════════════════════════════════
def tier_mask(point, positions, *, tier_k: dict = SCALED_TIER_K) -> np.ndarray:
    """The DRAFTABLE TIER on a set of emitted projections — the top `tier_k[pos]` per position by the
    INCUMBENT point, i.e. NF1.1's fixed-anchor rule. Every arm is matched on the identical rows, so a
    foil cannot be matched on a subset its own correction chose."""
    p = np.asarray(point, dtype=float)
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    keep = np.zeros(len(p), dtype=bool)
    for q, k in tier_k.items():
        idx = np.flatnonzero((pos == q) & np.isfinite(p))
        if not len(idx):
            continue
        keep[idx[np.argsort(-p[idx])[:int(k)]]] = True
    return keep


def matched_global_lambda(point, positions, arm_adjusted, reference_adjusted, *,
                          tier_k: dict = SCALED_TIER_K,
                          clip: tuple = MATCHED_FOIL_LAMBDA_CLIP) -> float | None:
    """The λ at which the REFERENCE AFFINE applies the same MEAN ABSOLUTE CORRECTION over the
    draftable tier as `arm_adjusted` does — the matched foil's only parameter.

    ⭐ THIS IS THE STORY'S ATTRIBUTION CONTROL AND IT MUST NOT PEEK. It is computed from the emitted
    POINT PROJECTIONS ONLY — no realized outcome enters it — so the foil is matched on magnitude
    without being told anything about the answer. That is what makes 'A cleared placement and its
    matched foil did not' a statement about SHAPE (NF-D15 (g′): a matched foil keeps everything except
    the claimed channel).

    Returns None when the reference applies no correction on the tier, which would make the ratio
    undefined; a None foil is reported as unscorable rather than silently treated as a pass."""
    keep = tier_mask(point, positions, tier_k=tier_k)
    p = np.asarray(point, dtype=float)
    a = np.asarray(arm_adjusted, dtype=float)
    r = np.asarray(reference_adjusted, dtype=float)
    ok = keep & np.isfinite(a) & np.isfinite(r) & np.isfinite(p)
    if not ok.any():
        return None
    denom = float(np.mean(np.abs(r[ok] - p[ok])))
    if denom <= 1e-9:
        return None
    return float(np.clip(float(np.mean(np.abs(a[ok] - p[ok]))) / denom, clip[0], clip[1]))


def attenuation_profile(point, positions, adjusted, *,
                        positions_scope: tuple = ATTENUATED_POSITIONS,
                        tier_k: dict = SCALED_TIER_K) -> dict:
    """⭐ DOES THIS ARM ACTUALLY ATTENUATE AT THE TOP? — measured, so the field's own labels are not
    taken on trust.

    A form registered as 'top-attenuating' is a HYPOTHESIS about its fitted parameters, not a fact:
    `power` steepens when γ comes back above 1, and `qmap` is registered precisely because it may
    expand the top. So each arm's correction ratio is reported at the TOP of each position's board (the
    single best rookie) against the draftable TIER as a whole. `attenuates_at_top` is true when the
    top rookie's correction ratio is SMALLER than the tier's mean — i.e. the arm is doing the thing its
    registration claims — and it is reported for every arm including the reference, which is the
    comparison that makes the number readable."""
    p = np.asarray(point, dtype=float)
    a = np.asarray(adjusted, dtype=float)
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    keep = tier_mask(point, positions, tier_k=tier_k)
    per: dict[str, dict] = {}
    for q in positions_scope:
        sel = (pos == q) & np.isfinite(p) & np.isfinite(a) & (p > 1e-6)
        if not sel.any():
            continue
        idx = np.flatnonzero(sel)
        top = idx[int(np.argmax(p[idx]))]
        tier = idx[keep[idx]]
        per[q] = {
            "top_ratio": round(float(a[top] / p[top]), 4),
            "tier_mean_ratio": (round(float(np.mean(a[tier] / p[tier])), 4)
                                if len(tier) else None),
            "top_delta_ppr": round(float(a[top] - p[top]), 2),
        }
    tops = [v["top_ratio"] for v in per.values()]
    tiers = [v["tier_mean_ratio"] for v in per.values() if v["tier_mean_ratio"] is not None]
    return {"per_position": per,
            "mean_top_ratio": round(float(np.mean(tops)), 4) if tops else None,
            "mean_tier_ratio": round(float(np.mean(tiers)), 4) if tiers else None,
            "attenuates_at_top": bool(tops and tiers and float(np.mean(tops))
                                      < float(np.mean(tiers)) - 1e-9)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE NF-D17 PLACEMENT CONSTRAINT — inherited verbatim, no new threshold, no new reference
# ══════════════════════════════════════════════════════════════════════════════════════════════
def board_placement(board: pd.DataFrame, adjusted_rookie_fp=None, *,
                    fp_col: str = "proj_fp_ppr") -> dict:
    """Re-rank the emitted (veterans + rookies) board with a candidate's rookie projections and read
    where its best rookie lands overall.

    ⭐ THE CORRECTION IS APPLIED TO THE BOARD'S OWN EMITTED ROOKIE POINTS, not to a re-projection of
    them. That is exactly what serving does (`RookieSlotCurve.recalibrate_fp` acts on the FINAL SCORED
    projection), and it means the incumbent half of this comparison IS the served product rather than
    a reconstruction of it that could drift — the only thing this story contributes to the number is
    the correction map itself.

    ⚠️ Veterans are untouched by construction: a rookie recalibration cannot move a veteran's
    projection, so every rank change on this board is the rookie half moving through a fixed veteran
    field. That is the whole reason a within-position 'moves no ranks' argument does not reach this
    gate (NF-D16's structural finding)."""
    d = board.copy()
    is_rk = (d["is_rookie"].fillna(False).astype(bool) if "is_rookie" in d
             else pd.Series(False, index=d.index))
    if adjusted_rookie_fp is not None:
        vals = pd.to_numeric(pd.Series(np.asarray(adjusted_rookie_fp, dtype=float),
                                       index=d.index[is_rk.to_numpy()]), errors="coerce")
        d.loc[is_rk.to_numpy(), fp_col] = vals
    ranked = d.sort_values(fp_col, ascending=False).reset_index(drop=True)
    rk = ranked[ranked["is_rookie"].fillna(False).astype(bool)] if "is_rookie" in ranked else ranked.iloc[:0]
    return {
        "n_rookies": int(len(rk)),
        "best_rookie_overall_rank": (int(rk.index[0]) + 1) if len(rk) else None,
        "best_rookie": None if rk.empty else str(rk.iloc[0].get("player_name")),
        "best_rookie_position": None if rk.empty else str(rk.iloc[0].get("position")),
        "best_rookie_fp": None if rk.empty else round(float(rk.iloc[0][fp_col]), 2),
        "n_rookies_in_top10": int(ranked["is_rookie"].fillna(False).astype(bool).head(10).sum()),
        "top1_is_rookie": bool(ranked["is_rookie"].fillna(False).astype(bool).iloc[0]),
    }


def placement_clearance(best_rookie_overall_rank, *, q: float = 0.10) -> dict:
    """⭐ C2 — THE NF-D17 PLACEMENT CAP, AND THE CLEARANCE IS REQUIRED TO BE THRESHOLD-INVARIANT.

    Delegates the whole computation to `season_projection.rookie_placement_breach`, which owns the
    reference distribution (the realized per-class BEST rookie's overall finish, 2019–2025) and the
    Q05–Q25 robustness band. NF-D18 introduces NO new threshold and NO new reference — importing the
    validated clause rather than re-deriving it is what stops this story from re-specifying the very
    bar it is trying to clear.

    ⭐ WHY INVARIANCE, AND WHY IT LEAVES NOTHING TO CHOOSE. NF-D17's VETO held at every quantile in
    the band (caps 7.90 / 8.80 / 9.70 / 10.60 / 11.50) and against reality's observed MINIMUM realized
    rank of 7 — that is what made it un-reverse-engineerable given rank 6 was already known. A SHIP
    must clear on the same terms, so `clears` requires no breach at ANY of those caps. In integer ranks
    that is exactly `rank ≥ 12`, and there is no threshold left for anybody to pick.

    An unevaluable rank (no rookie on the board) is NOT a pass — it is reported as unevaluable and
    treated as a failure by the caller, because a check that did not run is not a check that passed
    (NF1.7 anchor lesson (a))."""
    from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP

    if best_rookie_overall_rank is None:
        return {"clears": False, "evaluable": False,
                "note": "no rookie on the board — the placement clause could not be evaluated, "
                        "which is not the same as passing it"}
    br = SP.rookie_placement_breach(best_rookie_overall_rank, q=q)
    caps = list(br["caps_over_q_band"].values()) + [br["observed_minimum"]]
    clears = all(float(best_rookie_overall_rank) >= float(c) for c in caps)
    return {"clears": bool(clears), "evaluable": True,
            "threshold_invariant": bool(br["verdict_is_threshold_invariant"]),
            "strictest_cap": round(float(max(caps)), 2), **br}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The verdict — the PRE-REGISTERED pooled framing, with BOTH constraints on eligibility
# ══════════════════════════════════════════════════════════════════════════════════════════════
def pooled_ship(*, winner: dict | None, incumbent_metric: float | None, ordering: dict,
                placement: dict | None, pbo: float | None, dsr: float | None,
                pvalue: float | None, pbo_max: float = PBO_MAX, dsr_min: float = DSR_MIN,
                alpha: float = ALPHA) -> dict:
    """THE SHIP DECISION under the pre-registered pooled framing — one hypothesis, one test, and the
    ship unit is the whole per-position correction (RB/TE/WR together or not at all).

    Both constraints appear here as CHECKS ON THE SELECTED ARM as well as on eligibility, so a reader
    of the verdict dict can see the constraint state of the thing that was actually chosen rather than
    having to trust that the eligible set was filtered correctly.

    ⚠️ ORDERING is checked PER POSITION even though the decision is pooled — averaging is the exact
    operation that would hide the failure the constraint exists to catch. PLACEMENT is a whole-board
    property and is therefore a single check by construction, which is precisely why NF-D16's
    within-position 'moves no ranks' argument never reached it."""
    beats = bool(winner and incumbent_metric is not None and winner.get("metric") is not None
                 and float(winner["metric"]) < float(incumbent_metric))
    per_pos = (ordering or {}).get("per_position", {})
    checks = {
        "has_eligible_winner": winner is not None,
        "recalibrates": bool(winner and winner.get("recalibrates")),
        "beats_incumbent": beats,
        "ordering_ok_every_position": bool(per_pos) and all(v.get("ok", False)
                                                            for v in per_pos.values()),
        "placement_clears_threshold_invariant": bool((placement or {}).get("clears")),
        "pbo_ok": pbo is not None and pbo < pbo_max,
        "dsr_ok": dsr is not None and dsr >= dsr_min,
        "significant": pvalue is not None and float(pvalue) <= float(alpha),
    }
    return {"ship": all(checks.values()), "framing": PREREGISTERED_FRAMING, **checks}


def attenuation_verdict(*, pooled_ships: bool, degenerates_lose: bool,
                        permutation_across_beaten: bool, permutation_within_beaten: bool,
                        oracle_respected: bool, family_ceiling_respected: bool,
                        qb_untouched: bool) -> dict:
    """The STORY-level decision: the pre-registered pooled gate PLUS the run's global sanity anchors.

    The anchors are STORY-level VETOES on purpose. A degenerate winning the metric, or an arm beating
    its own family's peeking ceiling, does not mean 'this run was unlucky' — it means the measurement
    is not trustworthy anywhere in it and no number computed from it may be shipped.

    ⭐ `permutation_within_beaten` IS NEW HERE AND IS A REAL GATE RATHER THAN A FORMALITY. In NF-D16 the
    within-position permutation was EXACTLY invariant — a LEVEL is a marginal statistic and a
    within-position shuffle preserves the marginal — so it was declared an expected TIE in advance and
    reported as a property of the hypothesis. Every NF-D18 form estimates the SHAPE of realized-given-
    predicted, which that shuffle DESTROYS while preserving the marginal exactly. So the anchor that
    could not act on the previous hypothesis genuinely tests this one, and it is pre-registered as a
    gate: if a shuffled outcome vector produces corrections as good as the real ones, the shapes in
    this field carry nothing."""
    checks = {
        "pooled_gate_passes": bool(pooled_ships),
        "degenerates_lose": bool(degenerates_lose),
        "permutation_across_beaten": bool(permutation_across_beaten),
        "permutation_within_beaten": bool(permutation_within_beaten),
        "oracle_respected": bool(oracle_respected),
        "family_ceiling_respected": bool(family_ceiling_respected),
        "qb_untouched": bool(qb_untouched),
    }
    return {"ship": all(checks.values()), **checks}
