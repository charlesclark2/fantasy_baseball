"""level_recalibration.py — NF-RECAL1 pure model logic + PRE-REGISTRATION: can the fastpath's
VETERAN point LEVEL be recalibrated in-fold, under the product's own placement, ordering and
interval-coverage constraints?

⚠️ THIS FILE IS THE PRE-REGISTRATION. Everything that could otherwise be chosen after seeing a result
— the population, the tier ANCHOR, the forms, the two spaces, the λ grid and its selection rule, the
three constraints, the metric, the framing, the deflation reading and its level, the anchor set and
the empty-evidence default — is a CONSTANT here, written before the run. The runner READS these
rather than restating them, so "what was pre-registered" has exactly one owner.

════════════════════════════════════════════════════════════════════════════════════════════════════
0. ⭐ THE PREMISE CHECK COMES FIRST, AND IT IS NOT A FORMALITY
════════════════════════════════════════════════════════════════════════════════════════════════════
The motivating finding (`production_model_state/nfl_season_fantasy.md`, "MEASURED LEVEL BIAS",
NF-TR1 2026-08-07) reports a pooled −37.7 PPR level shift over 1,165 player-seasons 2019–2025, with
per-position our/actual QB 0.923 · RB 0.693 · WR 0.778 · TE 0.816, and states the figures are
"unconditional per-position means — ⛔ NOT conditioned on the outcome".

⭐ **A RECALIBRATION IS A CORRECTION FITTED TO A MEASURED DEFECT, SO THE DEFECT MUST FIRST BE
CONFIRMED IN THE POPULATION BEING FITTED** (NF-D10's `cache_is_current` lesson, one axis over: a
number carried forward from a differently-scoped run is not comparable, and a correction fitted to an
un-reproduced defect is a correction to nothing). `POPULATION_READINGS` names the readings the runner
computes so the premise is a MEASUREMENT rather than an inheritance, and `TIER_ANCHOR` /
`FORBIDDEN_TIER_ANCHORS` record the choice that decides the answer.

⚠️ **THE HAZARD IS SPECIFIC AND THE PROGRAM HAS ALREADY NAMED IT TWICE.** NF-D17 measured that a
ONE-SIDED top-N truncation manufactures an arbitrary gap ("state which side defined the N or the
comparison is uninterpretable"), and this very document's own caution 1 forbids citing the
outcome-BUCKETED decile table because "sorting on the REALIZED outcome selects for positive noise; it
cannot distinguish bias from correct shrinkage". A LEVEL statistic inherits both hazards: conditioning
the population on the realized outcome — by realized rank, or merely by "the player actually played" —
selects the rows on which any honest projection looks cold, and a correction fitted there would lift
the whole board to cure an artifact of the slice.

⇒ **`TIER_ANCHOR = "incumbent_projection"`** — NF1.1's fixed-anchor rule, inherited: the tier is fixed
by the INCUMBENT'S OWN projection, identically for every arm, so no candidate (and no anchor) can buy
a friendlier subset. The outcome-conditioned readings are COMPUTED AND REPORTED as disclosures — that
is how "which reading you take decides the answer" becomes a number rather than an argument — but
⛔ nothing is fitted, selected, or gated on them.

════════════════════════════════════════════════════════════════════════════════════════════════════
1. SCOPE — THE VETERAN LEG ONLY, AND THE ROOKIE EXCLUSION IS INHERITED RATHER THAN RE-DECIDED
════════════════════════════════════════════════════════════════════════════════════════════════════
⛔ **THE ROOKIE LEVEL IS OUT OF SCOPE AND MAY NOT BE RE-OPENED HERE.** NF-D16 ratified a rookie point
recalibration; NF-D18 and NF-D20 both recorded `CONSTRAINT_REFUSED`; NF-D21 routed it through the
governance pipeline at λ = 0.5 and **the pipeline refused it on the rookie-RB interval floor**, after
which the PM CLOSED it (2026-08-05) — explicitly *closed rather than parked*, because "a story left
open pending a floor fix is exactly the pressure that would bias that floor toward clearing λ = 0.5".

Re-opening the rookie level inside a *differently named* story would re-apply that exact pressure
while wearing a new badge. So the exclusion is INHERITED BY IMPORT from `rookie_publish_policy` (whose
`assert_coherent()` already refuses a serving flip that contradicts its own disposition), and
`assert_rookie_leg_untouched` is the single gate every arm — candidate, foil, degenerate and oracle
alike — must pass through. That makes "rookies are untouched" a property of the CODE rather than of
every arm remembering to honour it.

⚠️ UPDATE 2026-08-20 (NF-D21-PUBLISH) — the rookie leg is no longer closed; it now SERVES a level
correction at λ = 0.5, after NF-D22 replaced the interval-floor RULE (a power-derived floor derived
from n and NF1.8's pre-registered false-reject target, with NF-D21 explicitly out of its scope) and
NF-D16 was re-gated against it. ⭐ That does NOT relax this story's scope, it hardens the reason for
it: a rookie row reaching this population would now be level-corrected TWICE. The re-read is recorded
in `REVIEWED_ROOKIE_DISPOSITIONS`, which is what the gate checks — a rookie disposition nobody has
re-read this scope against still raises.

⭐ It is also where the mass is: 703 of the 784 served skill players are veterans, and the veteran
level has never had a recalibration story at all, while the rookie level has had four.

QB is IN SCOPE here, and that is a deliberate difference from NF-D16/D18/D20 (which exclude it). Their
exclusion is specific to the rookie leg — NF-D14 MEASURED a rookie-QB double-pricing. No such finding
exists for veteran QBs, and the motivating table names a QB bias, so excluding QB would be inheriting
a reason that does not apply. ⚠️ The premise check reads QB in BOTH directions precisely because this
is the position where the motivating figure and an unconditional read are most likely to disagree.

════════════════════════════════════════════════════════════════════════════════════════════════════
2. ⭐ THE PRIMARY HYPOTHESIS — THE CORRECTION'S INTERCEPT SCALES WITH EXPECTED GAMES
════════════════════════════════════════════════════════════════════════════════════════════════════
The served point is `rate × expected_games`, and the motivating analysis attributes MOST of the level
gap to the availability (expected-games) discount. If that is right, a correction fitted in
SEASON-TOTAL space double-counts it: a flat per-season offset gives the 8-game player and the 17-game
player the same lift, so it over-corrects the players whose projection was low *because we expect them
to miss time* — which is the one part of the level that is deliberate and honest.

**PER-GAME (PRIMARY):** the correction is parameterised on the per-game rate and re-expanded by
expected games, so an intercept enters the season total as `c · g`.
**SEASON-TOTAL (REGISTERED FOIL):** the identical form with a FLAT intercept.

⭐ **THE TWO SPACES ARE A MATCHED FOIL IN THE NF-D15 (g′) SENSE — IDENTICAL IN EVERY RESPECT EXCEPT
THE ONE CLAIMED CHANNEL.** `pos_offset` per-game emits `point + c·g`; season-total emits `point + c`.
Same family, same fit population, same λ machinery, same metric — only whether the intercept scales
with expected games. The PAIRED delta is therefore attributable to the availability channel and
nothing else, which is exactly the control NF-D15 showed is required before a win may be credited to
its stated mechanism.

⚠️⚠️ **AND THE SPACE DISTINCTION IS A MATHEMATICAL NO-OP FOR THREE OF THE FIVE FORMS — PRE-REGISTERED
AS AN EXPECTED TIE, TO BE PROVEN RATHER THAN DISCOVERED.** Any purely MULTIPLICATIVE correction
satisfies `k · (point/g) · g ≡ k · point`, so `global_const`, `pos_const` and `avail_cond` emit
BYTE-IDENTICAL projections in both spaces. That is NF1.9's "a mechanism that cannot act is a finding,
not an omission", and NF-D16 (2)'s rule that a near-tie must be REGISTERED IN ADVANCE and MEASURED
rather than presented as a passed test: `SPACE_INVARIANT_FORMS` names them, and
`test_space_invariance_is_exact` proves max |Δ| = 0. ⇒ the per-game hypothesis is testable ONLY on
`pos_offset` and `pos_affine`, and a report that claimed otherwise would be claiming a mechanism acted
where it structurally cannot.

════════════════════════════════════════════════════════════════════════════════════════════════════
3. THE FIVE PRE-REGISTERED FORMS (≥3 classes + a direct-learned foil + the incumbent NULL, per §0.5)
════════════════════════════════════════════════════════════════════════════════════════════════════
  • `incumbent`     — THE NULL. The shipped veteran point, untouched. In the field, and it can win.
  • `global_const`  — ONE multiplicative constant for the whole board. ⭐ THE STRUCTURALLY SAFE ARM:
                      a single positive constant is a monotone transform of the ENTIRE board, so it
                      moves NO rank anywhere — not within a position and not across positions. It is
                      also the only arm that cannot fix the per-position SHAPE (RB 0.693 vs QB 0.923),
                      and that tension is the story's core: the safe arm and the corrective arm are
                      different arms.
  • `pos_const`     — per-position multiplicative constant. Monotone WITHIN position ⇒ zero
                      within-position movement; ACROSS positions it reorders the shared board, which
                      is precisely the NF-D16 (g‴) hazard and why C2 exists.
  • `pos_offset`    — per-position additive offset. A different SHAPE, not a reparametrisation: an
                      offset moves the bottom of a position's board as much as the top, a
                      multiplicative constant moves the top most.
  • `pos_affine`    — THE DIRECT-LEARNED FOIL: per-position intercept AND slope, fitted. It differs
                      from the prescribed forms ONLY in that the correction's shape is learned, so a
                      win is attributable to the learning and — more usefully — a LOSS is the
                      strongest available evidence that a prescribed constant is the right shape,
                      since the foil was free to discover any affine including both constants.
                      ⚠️ CONDITIONALLY monotone: a negative fitted slope inverts a position's whole
                      board, so "does no ordering harm" is MEASURED here, never asserted (NF-D16 (2)).
  • `avail_cond`    — per-position × AVAILABILITY-BUCKET multiplicative constant. ⭐ THE DIRECT TEST
                      OF THE MOTIVATING EXPLANATION: if the level gap is carried by the availability
                      discount, the fitted constant must differ sharply across expected-games buckets.
                      If it does not, the stated mechanism is refuted whatever the metric says.
                      Reorders WITHIN position (two players in different buckets can swap), so C1
                      genuinely binds on it — which is what stops the ordering constraint from passing
                      having examined nothing (NF1.7 (a) in an eligibility rule's clothing).

════════════════════════════════════════════════════════════════════════════════════════════════════
4. 📏 SELECTION METRIC — CRPS, AND MAE IS FORBIDDEN AS THE PRIMARY
════════════════════════════════════════════════════════════════════════════════════════════════════
`SELECTION_METRIC = "crps"`. ⛔ NOT MAE, and the reason is measured rather than stylistic: MAE is
minimised at the CONDITIONAL MEDIAN, so on a right-skewed, zero-heavy target it PAYS FOR PESSIMISM —
NF-D11 measured an all-zero degenerate WINNING MAE on a 43%-zero cohort, and NF-D15 measured pooled
bias moving FURTHER from zero while MAE improved. The veteran population is 31–35% zero-outcome. A
level story graded on MAE would therefore be graded on the very statistic that CAUSED the residual it
is trying to remove, which is metric-shopping in the most self-defeating direction available.

CRPS is proper and grades the point AND the spread jointly, so neither pessimism nor a widened band
can win it. It is computed from the SERVED 80% band via the quantile identity
`CRPS(F,y) = 2∫₀¹ ρ_τ(y − Q(τ))dτ` over a split-normal quantile function CLIPPED AT ZERO — the clip is
not a convenience, it is the correct representation of a population with a genuine point mass at zero
(NF1.9 measured 31%), and it is what lets the score see a projection that is impossible rather than
merely wrong.

⚠️ MAE, RMSE, pooled BIAS, 80% COVERAGE and the Winkler interval score are all computed and reported
as DISCLOSURES. Two of them are load-bearing without gating:
  · **BIAS is the ATTRIBUTION SIGNATURE** (NF-D15 (g′)). A genuine LEVEL fix moves pooled bias TOWARD
    zero while accuracy improves. Bias moving AWAY from zero while the metric improves is the
    signature of a PER-PLAYER effect wearing a level story's clothes, and NF-D15 caught exactly that.
  · **MAE is the INVERSION DETECTOR.** `pos_median` — the arm that throws away every per-player
    distinction — is scored every run. If it WINS MAE and LOSES CRPS, that is the inversion this
    story's metric choice exists to avoid, MEASURED on this population rather than argued from
    precedent (E2.1-r (b)/(c): sanity-check the metric against an oracle floor and a degenerate
    ceiling, and READ them rather than reasoning about them).

════════════════════════════════════════════════════════════════════════════════════════════════════
5. THE THREE CONSTRAINTS — ALL INHERITED, NONE INVENTED
════════════════════════════════════════════════════════════════════════════════════════════════════
  C1 · DO NO ORDERING HARM (WITHIN position) — NF1.4's `ORDERING_DO_NO_HARM = 0.02` on the
       within-position rank correlation against the incumbent, checked PER POSITION and never as a
       pooled mean (a pooled ρ can sit flat while one position's ordering collapses). Inherited
       verbatim by import.

  C2 · THE PER-FOLD WHOLE-BOARD PLACEMENT CONSTRAINT — NF-D17's threshold-invariant rookie placement
       cap, evaluated OUT-OF-SAMPLE on each held-out season's own merged board, DELEGATED to
       `rookie_top_attenuation.placement_clearance` (which delegates to `season_projection`). This
       story introduces NO new threshold and NO new reference: clearing only at a cap one would pick
       after seeing the result is the E2.1-r inversion.

       ⭐⭐ **AND ITS DIRECTION IS INVERTED HERE, WHICH IS WHY ITS ACTIVITY MUST BE COUNTED BEFORE ITS
       PASSES ARE CREDITED (NF-D20 (g⁗)).** NF-D16/D18/D20 lifted ROOKIES through a fixed veteran
       field, so the clause was the binding veto. NF-RECAL1 lifts VETERANS through a fixed rookie
       field: a LIFT pushes the best rookie DOWN the board (a larger rank = further from the cap), so
       the clause is satisfied *more* easily and a recorded "C2 held on 7 of 7 folds" may mean the
       constraint could not act at all. `constraint_activity` COUNTS the folds on which any λ moves
       the constrained rank, and an inactive fold is reported UNINFORMATIVE, never as a pass. The
       clause still has teeth in the other direction (an arm that SHRINKS a position lifts rookies),
       which is exactly what `over_scale` and the shrinking degenerates are scored to demonstrate.

  C3 · ⭐ THE INTERVAL COVERAGE FLOORS AFTER THE SHIFT — the gate that ACTUALLY refused NF-D21, and
       the one a level story is most likely to forget. A level recalibration moves the band's CENTRE,
       so the served 80% coverage moves with it; NF-D21's λ = 0.5 missed the rookie-RB floor by two
       covered rows and was closed on it. Floor `0.80`, checked PER POSITION and pooled over ROWS
       (NF1.8's rule: a per-group floor may not be a mean of per-class means).
       ⛔ THE FLOOR IS A CONSTRAINT AND MAY NEVER BECOME A TARGET (NF1.8): no arm is selected on
       coverage headroom — that criterion is monotone in widening and the `wide_band` degenerate wins
       it outright, which is precisely why `wide_band` is scored every run.
       ⛔ AND THE FLOOR MAY NOT BE MOVED (E2.1-r's cardinal error). A breach is a refusal.

════════════════════════════════════════════════════════════════════════════════════════════════════
6. λ IS NEVER A KNOB — THE FIELD IS RULES, NOT VALUES (NF-D20, inherited)
════════════════════════════════════════════════════════════════════════════════════════════════════
A field of fixed λ values makes λ a knob and the winner a re-pick. Every candidate here is a
deterministic RULE whose λ is computed from folds strictly BEFORE the one it is scored on:

  • `infold`        — λ is the in-fold-CRPS argmin among the values ADMISSIBLE under C1∧C2∧C3 on EVERY
                      prior fold. Ties break toward the SMALLER λ: a tie means the data cannot tell
                      them apart, and the conservative side of "how much correction do we apply" is
                      less of it.
  • `unconstrained` — λ = 1, the constraints REMOVED. Carried SHIPPABLE so the constraints have
                      something to REFUSE; a field of only constrained arms leaves them passing having
                      examined nothing.

`LAMBDA_GRID` is INHERITED BY IMPORT from `rookie_point_recalibration.SHRINK_GRID` — a grid written
before any constraint result in this programme existed. Inheriting is what stops the grid from
becoming a place to hide a choice. `EMPTY_EVIDENCE_LAMBDA = 0.0`: with no prior fold to verify
against, a rule applies NO correction, because a check that did not run is not a check that passed.

════════════════════════════════════════════════════════════════════════════════════════════════════
7. FRAMING · DEFLATION · THE DECLARED FIELD
════════════════════════════════════════════════════════════════════════════════════════════════════
  · FRAMING — POOLED, pre-registered, with the same reason NF-D16 gave and NF-D18/D20 inherited: the
              ship UNIT is ONE change to the veteran level that applies at all four positions together
              or not at all. There is no product in which the correction ships at TE alone. The
              per-position reading is computed as a DISCLOSURE and does not gate.
  · DSR     — WHOLE-FIELD reading BINDS at 0.95; PBO < 0.2; α = 0.10 single-hypothesis. All inherited
              BY IMPORT from `rookie_point_recalibration` so the bar cannot drift between the stories.
              Contender-set DSR, the DSR CEILING at this fold count, and the sensitivities at DSR ≥ 0
              and with DSR removed are all reported (MH2: name which binds in advance, report both).
  · FIELD   — ⭐ THE DECLARED FAMILY IS THE 5 FORMS × 2 λ-RULES + THE NULL = 11 TRIALS, fixed here.
              MH2 (a) is two-sided: a family gets its own PRE-REGISTERED field, and ⛔ trimming one
              after the fact under-taxes it because the arm you drop is chosen because it LOST. The
              MATCHED FOILS (the season-total twins) and every ANCHOR are excluded from the trial
              field and from PBO's search, because a diagnostic is never a trial — and the EXPANDED
              reading that counts every constant-λ point as its own trial is reported as the
              conservative sensitivity so the exclusion is visible rather than assumed.

════════════════════════════════════════════════════════════════════════════════════════════════════
8. ⚠️ TWO-SIDED ANCHORS, SCORED AND READ EVERY RUN
════════════════════════════════════════════════════════════════════════════════════════════════════
  · `oracle_perplayer` — the ORACLE FLOOR at full resolution (per-player `realized/point`). Nothing
                         may beat it; a violation means the metric is inverted, not that an arm is good.
  · a PEEKING CEILING **PER FORM** (`FAMILY_CEILING`) — each form's OWN parameters fitted on the
                         HELD-OUT fold. ⭐ ONE CEILING FOR THE WHOLE FIELD WOULD BE MIS-SPECIFIED
                         (NF-D16 (g‴)): the forms NEST — `pos_affine` contains `pos_offset` (slope 1)
                         and `pos_const` (intercept 0), which contains `global_const` — so a richer
                         family can legitimately beat a coarser family's ceiling, a CAPACITY effect,
                         and a single ceiling would veto the real winner as a metric inversion. The
                         per-form ceilings are expected to ORDER BY CAPACITY, which is an
                         internal-consistency signal a single ceiling structurally cannot produce.
  · `permuted_across`  — constants estimated from outcomes shuffled ACROSS positions. Must LOSE.
  · `permuted_within`  — shuffled WITHIN position. ⭐ PRE-REGISTERED TO **TIE** for the pure LEVEL
                         forms and to BE BEATEN for the slope-carrying ones, and saying which in
                         advance is the point: a within-position shuffle preserves that position's
                         MARGINAL exactly, and a level is a marginal statistic, so the permutation is
                         near-VACUOUS against a level form (NF-D16 measured max |Δ| 7e-15 for exactly
                         this reason) and genuinely BITES against `pos_affine`.

                         ⭐⭐ **AND THE MEASUREMENT REFINED THAT EXPECTATION IN A WAY WORTH CARRYING:
                         THE VACUITY IS A PROPERTY OF THE *SPACE*, NOT ONLY OF THE FORM.** Measured
                         on the additive form, max |Δparam| under a within-position shuffle is
                         **1.4e-14 in SEASON-TOTAL space** (reproducing NF-D16's 7.1e-15 on a
                         different population) and **1.03 in PER-GAME space**. The reason is exact:
                         season-total fits `c = mean(y − p)`, which a within-position shuffle cannot
                         move, whereas per-game fits `c = Σg(y − p)/Σg²`, which RE-PAIRS each outcome
                         with a different expected-games value. ⇒ **the per-game parameterisation
                         makes a level correction stop being a pure MARGINAL statistic** — it draws
                         on a within-position covariate — so "the permutation is vacuous against a
                         level" is true only with the SPACE named. That is also why the per-game
                         hypothesis is testable at all, and it is measured (`permutation_vacuity`)
                         rather than asserted (NF-D16 (2)).
  · `zero_project`     — DEGENERATE: project nothing for anyone. Must LOSE the metric; satisfies C2
                         trivially. NF1.8's rule read in both directions — a CONSTRAINT a degenerate
                         satisfies is fine (the metric eliminates it); a CRITERION a degenerate WINS
                         is fatal. Scoring it is the proof C2/C3 were not quietly promoted into
                         selection criteria.
  · `pos_median`       — DEGENERATE: the in-fold position median for everyone. The MAE-collapse tell,
                         and the arm whose MAE-vs-CRPS split MEASURES the inversion §4 asserts.
  · `over_scale`       — THE DEGENERATE ON THE OTHER SIDE: λ = 2, twice the fitted correction. It must
                         LOSE. ⭐ If it WINS, that is NOT a metric inversion (the do-nothing
                         degenerates still lose): it is a REFUTED MAGNITUDE HYPOTHESIS — the fit
                         UNDER-corrects and the metric optimum lies outside the registered interval
                         (NF-D20). A pre-registered anchor that fails is left FAILING and DECOMPOSED,
                         never re-labelled.
  · `wide_band`        — the SHARPNESS degenerate: the band inflated ×3 at an unchanged centre. It
                         SATISFIES every coverage floor and must LOSE CRPS. Without it, C3 would be a
                         constraint nothing is ever measured winning from, and NF1.7 (d) (3) is
                         explicit that sharpness needs two degenerates, not one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy.nf1_4_rookie import ORDERING_DO_NO_HARM
# ⭐ The gates are INHERITED BY IMPORT so the bar cannot drift between the story that ratified a level
#    correction (NF-D16) and the story asking the same question of a different leg.
from quant_sports_intel_models.football.nfl.fantasy.rookie_point_recalibration import (
    ALPHA,
    DSR_MIN,
    MULT_CLIP,
    OFFSET_CLIP,
    PBO_MAX,
    SHRINK_GRID,
    blend_toward_incumbent,
    family_ceiling_check,
)
# ⛔ The rookie leg's DISPOSITION is imported, never restated. It was CONSTRAINT_REFUSED at
#    pre-registration and is SHIP (serving, λ=0.5) since NF-D21-PUBLISH; this story re-opens it under
#    neither. The re-read of each is recorded in `REVIEWED_ROOKIE_DISPOSITIONS`. See §1.
from quant_sports_intel_models.football.nfl.fantasy import rookie_publish_policy as RPP
from quant_sports_intel_models.football.nfl.fantasy.rookie_top_attenuation import (
    board_placement,
    placement_clearance,
)

MODEL_VERSION = "nfl_fantasy_nf_recal1_veteran_level_v1"
RECALIBRATES = "nfl_fantasy_fastpath_v1"          # the LEVEL model; ⛔ NOT the NF1.5 ordering layer

# ══════════════════════════════════════════════════════════════════════════════════════════════
# SCOPE (§1)
# ══════════════════════════════════════════════════════════════════════════════════════════════
RECALIBRATED_POSITIONS = ("QB", "RB", "WR", "TE")
RECALIBRATED_LEG = "veteran"
EXCLUDED_LEGS = ("rookie", "K", "DST")
ROOKIE_EXCLUSION_REASON = (
    "The rookie LEVEL is governed by the NF-D16 → NF-D18 → NF-D20 → NF-D21 → NF-D22 chain, not by "
    "this story. At pre-registration (2026-08-05) that chain was CLOSED as CONSTRAINT_REFUSED and "
    "the PM's reason for closing rather than parking it — a story left open pending a floor fix is "
    "exactly the pressure that would bias that floor toward clearing — is why re-opening the rookie "
    "level inside a differently-named story would have re-applied that pressure wearing a new badge. "
    "Since 2026-08-20 (NF-D21-PUBLISH) that chain SERVES a rookie-level correction at λ=0.5, which "
    "makes the exclusion STRONGER rather than moot: a rookie row in this population would be "
    "level-corrected twice, once by the rookie policy at build time and again by a veteran constant "
    "fitted over rows that should never have been in it. The exclusion is INHERITED BY IMPORT from "
    "`rookie_publish_policy`, not re-decided here."
)
QB_INCLUSION_REASON = (
    "QB is IN scope, unlike NF-D16/D18/D20. Their exclusion rests on NF-D14's MEASURED rookie-QB "
    "double-pricing — a finding about the ROOKIE slot curve. No equivalent finding exists for the "
    "veteran leg, and the motivating table names a QB level gap, so excluding QB would be inheriting "
    "a reason that does not apply to this population."
)

# ══════════════════════════════════════════════════════════════════════════════════════════════
# POPULATION + THE TIER ANCHOR (§0) — the choice that decides the answer
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: The folds. 2019–2025 is the INTERSECTION of the veteran walk-forward panel and the per-season
#: merged boards C2 needs; it is a DATA-AVAILABILITY fact, not a preference.
PANEL_SEASONS = tuple(range(2019, 2026))
#: MH2's rule — a fold ceiling that is a WINDOW choice must say so, and say whether widening is
#: reachable NOW. The veteran panel reaches back to target season 2007. The METRIC is therefore
#: recomputable on 13 folds today; ⛔ C2 is NOT, because the merged boards begin at 2019, and an
#: unevaluable constraint is never a pass (NF1.7 (a)). Reported as a metric-only sensitivity, and the
#: board rebuild is named as the re-test trigger if this null is power-limited.
WIDE_WINDOW_SEASONS = tuple(range(2013, 2026))

#: ⭐ THE DRAFTABLE TIER IS A PRODUCT QUANTITY, DERIVED — NOT A NUMBER SOMEBODY PICKED. It is the
#: count of SKILL roster spots a 12-team league of the shipped standard preset actually fills:
#: (1 QB + 2 RB + 2 WR + 1 TE + 1 FLEX + 6 BN) × 12 = 156. Deriving it from `league_presets` rather
#: than typing it means a preset change has one owner, and it means the tier cannot be tuned.
DRAFT_TEAMS = 12
TIER_PRESET = "standard"

#: ⛔ THE ANCHOR THE TIER IS FIXED BY — NF1.1's fixed-anchor rule, and §0's whole point.
TIER_ANCHOR = "incumbent_projection"
FORBIDDEN_TIER_ANCHORS = ("realized_outcome", "realized_participation", "benchmark_rank")
TIER_ANCHOR_REASON = (
    "The tier is fixed by the INCUMBENT'S OWN projection, identically for every arm, so no candidate "
    "or anchor can buy a friendlier subset. Anchoring on the REALIZED outcome (or merely on 'the "
    "player played') selects the rows on which any honest projection looks cold — NF-D17 measured a "
    "one-sided truncation manufacturing an arbitrary gap, and this product's own documentation "
    "forbids citing its outcome-bucketed decile table for the same reason. The outcome-conditioned "
    "readings are COMPUTED AND REPORTED as disclosures; nothing is fitted, selected or gated on them."
)
#: The readings the runner must compute for the premise check (§0). Naming them here means the
#: premise is a measurement with a fixed shape, not whichever slice happened to be convenient.
POPULATION_READINGS = ("universe", "draftable_tier_incumbent_anchor",
                       "draftable_tier_realized_anchor", "played_at_least_6_games")

# ══════════════════════════════════════════════════════════════════════════════════════════════
# METRIC (§4)
# ══════════════════════════════════════════════════════════════════════════════════════════════
SELECTION_METRIC = "crps"
DISCLOSED_METRICS = ("mae", "rmse", "bias", "coverage80", "interval_score80")
FORBIDDEN_SELECTION_METRICS = ("mae", "rmse")
METRIC_REASON = (
    "CRPS is proper and grades point AND spread jointly. MAE is minimised at the CONDITIONAL MEDIAN, "
    "so on this 31–35%-zero right-skewed target it PAYS FOR PESSIMISM — the very effect NF-D11 "
    "measured (an all-zero degenerate WINNING MAE at 43% zeros) and NF-D15 measured again (bias "
    "moving away from zero while MAE improved). Selecting a LEVEL correction on MAE would grade it on "
    "the statistic that caused the residual it exists to remove."
)
#: The nominal band and its FLOOR (C3). Inherited: 80% is the served band, 0.80 the standing floor.
BAND_NOMINAL = 0.80
COVERAGE_FLOOR = 0.80
#: Number of quantile knots in the CRPS integration. Fixed in advance, and its sufficiency is
#: MEASURED rather than assumed — `test_crps_matches_the_closed_form_normal` scores it against the
#: analytic Gaussian CRPS.
#:
#: ⚠️ THE TOLERANCE IS RELATIVE, AND THAT IS THE HONEST FORM RATHER THAN A WEAKENING. CRPS carries
#: the units of the target, so an absolute bound means something different at a 5-PPR outcome and a
#: 400-PPR one. Measured worst-case relative error over y ∈ [0, 400] against a Normal(100, 25):
#: **1.0e-4 at 512 knots**, 4.6e-5 at 1024, 2.0e-5 at 2048 — i.e. O(1/n), because the pinball
#: integrand has a KINK at the τ where Q(τ) = y and midpoint quadrature is only first-order there.
#: Doubling the knots halves an error that is already ~400× smaller than the gap between the arms
#: this metric has to separate (the field spans ~4.5% of the incumbent's CRPS), so 512 buys the
#: resolution the decision needs and nothing is bought by more.
CRPS_TAU_KNOTS = 512
#: The worst-case RELATIVE accuracy the knot count is proven to deliver — recorded as data so the
#: guard cannot quietly drift to a looser bar than the one this constant was chosen against.
CRPS_RELATIVE_TOLERANCE = 2e-4
_Z80 = 1.2815515655446004                          # Phi^{-1}(0.9)

# ══════════════════════════════════════════════════════════════════════════════════════════════
# FORMS + SPACES (§2, §3)
# ══════════════════════════════════════════════════════════════════════════════════════════════
FORMS = ("global_const", "pos_const", "pos_offset", "pos_affine", "avail_cond")
LEARNED_FOIL = "pos_affine"
SPACES = ("per_game", "season_total")
PRIMARY_SPACE = "per_game"
FOIL_SPACE = "season_total"
#: ⭐ PRE-REGISTERED EXPECTED TIE (§2). Purely multiplicative forms satisfy k·(p/g)·g ≡ k·p, so the
#: space distinction CANNOT ACT on them. Proven, not assumed, by `test_space_invariance_is_exact`.
SPACE_INVARIANT_FORMS = ("global_const", "pos_const", "avail_cond")
SPACE_ACTING_FORMS = ("pos_offset", "pos_affine")

#: Ordering classes — three, not two, and the middle one is why the claim is MEASURED every run.
#: ⚠️⚠️ `LEG_MONOTONE_FORMS` IS NAMED FOR ITS SCOPE BECAUSE THE FIRST CUT OF THIS FILE CALLED IT
#: `GLOBAL_MONOTONE` AND CLAIMED "monotone across the WHOLE board: no rank moves" — WHICH IS FALSE,
#: AND THE MEASUREMENT CAUGHT IT. A single positive constant is monotone over the rows it TOUCHES,
#: and this story touches VETERANS ONLY (the rookie leg is CLOSED, §1). The served board holds both,
#: so lifting every veteran past a fixed rookie field reorders the board: measured at median 2 /
#: max 35 places over 786 rows at λ = 1, with the top-100 membership and the top-10 order intact.
#: That is NF-D16 (g‴) exactly — a "moves no ranks" claim is scoped, and asserting it unscoped is the
#: error — and it is why `cross_position_movement` measures rather than the constant declaring.
LEG_MONOTONE_FORMS = ("global_const",)             # monotone within the RECALIBRATED LEG only
WITHIN_POSITION_MONOTONE_FORMS = ("pos_const", "pos_offset")
CONDITIONALLY_MONOTONE_FORMS = ("pos_affine",)     # monotone iff the fitted slope is positive
REORDERING_FORMS = ("avail_cond",)                 # two players in different games-buckets can swap

#: ⭐ ONE PEEKING CEILING PER FORM (§8, NF-D16 (g‴)). The forms NEST, so a single ceiling would veto a
#: legitimately-better richer family as a metric inversion.
FAMILY_CEILING = {f: f"oracle_{f}" for f in FORMS}
#: The nesting itself, recorded so the run can ASSERT the ceilings order by capacity rather than
#: hoping they do. `a ⊂ b` means every `a` is a special case of `b`.
FORM_NESTING = (("global_const", "pos_const"), ("pos_const", "pos_affine"),
                ("pos_offset", "pos_affine"), ("pos_const", "avail_cond"))

#: Availability buckets for `avail_cond`. FIXED and PHYSICAL (part-season / most-of-season /
#: full-season against a 17-game year), never fitted — a fitted boundary is a knob, and a knob chosen
#: on this population is the E2.1-r move.
AVAIL_BUCKETS = ((0.0, 8.0), (8.0, 13.0), (13.0, 99.0))
AVAIL_BUCKET_LABELS = ("part", "most", "full")

# Physical bounds, not tuning knobs — a level correction that halves or doubles a whole position's
# board is not a recalibration, it is a different projection. Inherited by import from NF-D16.
MIN_POINT = 5.0            # a ratio needs a denominator with signal in it (floor on the DENOMINATOR)
MIN_GAMES = 1.0            # per-game space: guard the divisor, never the target
MIN_CELL = 25              # rows required before a (position × availability bucket) cell fits its own

# ══════════════════════════════════════════════════════════════════════════════════════════════
# λ (§6) — inherited by import; the field is RULES, never values
# ══════════════════════════════════════════════════════════════════════════════════════════════
LAMBDA_GRID = (0.0,) + tuple(SHRINK_GRID)          # (0, 0.25, 0.5, 0.75, 1.0)
SELECTION_RULES = ("infold", "unconstrained")
RULE_CONSTRAINED = {"infold": True, "unconstrained": False}
EMPTY_EVIDENCE_LAMBDA = 0.0
OVER_SCALE_LAMBDA = 2.0
WIDE_BAND_FACTOR = 3.0
LAMBDA_PROVENANCE = (
    "λ is never a knob. Every candidate is a deterministic RULE whose λ is computed from folds "
    "strictly BEFORE the one it is scored on; the grid is `rookie_point_recalibration.SHRINK_GRID`, "
    "imported, written before any constraint result in this programme existed. No arm is fitted, "
    "filtered or selected on the 2026 serving board."
)

# ══════════════════════════════════════════════════════════════════════════════════════════════
# FRAMING + DEFLATION (§7) — recorded as DATA so the report cannot quietly disagree with it
# ══════════════════════════════════════════════════════════════════════════════════════════════
PREREGISTERED_FRAMING = "pooled"
PREREGISTERED_DSR_READING = "whole_field"
FRAMING_REASON = (
    "The ship UNIT is ONE change to the veteran level that applies at all four positions together or "
    "not at all — there is no product in which the correction ships at TE alone. Splitting one "
    "hypothesis into four tests pays a multiplicity penalty for a decomposition the hypothesis does "
    "not require (NF-D15 was blocked by exactly that framing; NF-D16 pre-registered pooled for this "
    "reason and NF-D18/NF-D20 inherited it). The per-position reading is a DISCLOSURE and does not gate."
)
FIELD_REASON = (
    "The DECLARED family is the 5 forms × 2 λ-rules + the NULL = 11 trials, fixed before the run. "
    "MH2 (a) is two-sided: you get to PRE-REGISTER a family, you do NOT get to DISCOVER one — and "
    "trimming a field after the fact under-taxes it, because the arm you drop is dropped for LOSING. "
    "The season-total matched foils and every anchor are excluded from the trial field because a "
    "diagnostic is never a trial; the EXPANDED reading counting every constant-λ point is reported as "
    "the conservative sensitivity so that exclusion is visible rather than assumed."
)
FDR_Q = ALPHA

NON_SHIPPABLE = ("zero_project", "pos_median", "over_scale", "wide_band",
                 "oracle_perplayer", "permuted_across", "permuted_within") + tuple(
                     FAMILY_CEILING.values())
_REQUIRED_ANCHORS = ("oracle_perplayer", "permuted_across", "permuted_within",
                     "zero_project", "pos_median", "over_scale", "wide_band"
                     ) + tuple(FAMILY_CEILING.values())

__all__ = [
    "MODEL_VERSION", "RECALIBRATES", "RECALIBRATED_POSITIONS", "RECALIBRATED_LEG", "EXCLUDED_LEGS",
    "ROOKIE_EXCLUSION_REASON", "QB_INCLUSION_REASON",
    "PANEL_SEASONS", "WIDE_WINDOW_SEASONS", "DRAFT_TEAMS", "TIER_PRESET", "TIER_ANCHOR",
    "FORBIDDEN_TIER_ANCHORS", "TIER_ANCHOR_REASON", "POPULATION_READINGS",
    "SELECTION_METRIC", "DISCLOSED_METRICS", "FORBIDDEN_SELECTION_METRICS", "METRIC_REASON",
    "BAND_NOMINAL", "COVERAGE_FLOOR", "CRPS_TAU_KNOTS",
    "FORMS", "LEARNED_FOIL", "SPACES", "PRIMARY_SPACE", "FOIL_SPACE",
    "SPACE_INVARIANT_FORMS", "SPACE_ACTING_FORMS", "LEG_MONOTONE_FORMS",
    "WITHIN_POSITION_MONOTONE_FORMS", "CONDITIONALLY_MONOTONE_FORMS", "REORDERING_FORMS",
    "FAMILY_CEILING", "FORM_NESTING", "AVAIL_BUCKETS", "AVAIL_BUCKET_LABELS",
    "MIN_POINT", "MIN_GAMES", "MIN_CELL",
    "LAMBDA_GRID", "SELECTION_RULES", "RULE_CONSTRAINED", "EMPTY_EVIDENCE_LAMBDA",
    "OVER_SCALE_LAMBDA", "WIDE_BAND_FACTOR", "LAMBDA_PROVENANCE",
    "PREREGISTERED_FRAMING", "PREREGISTERED_DSR_READING", "FRAMING_REASON", "FIELD_REASON",
    "PBO_MAX", "DSR_MIN", "ALPHA", "FDR_Q", "ORDERING_DO_NO_HARM", "NON_SHIPPABLE",
    "draftable_tier_size", "assert_rookie_leg_untouched", "REVIEWED_ROOKIE_DISPOSITIONS",
    "avail_bucket",
    "crps_from_band", "interval_score80", "band_metrics",
    "fit_form", "fit_form_peeking_on_metric", "predict_form", "apply_to_band",
    "blend_band_toward_incumbent", "per_position_coverage",
    "blend_toward_incumbent", "family_ceiling_check", "board_placement", "placement_clearance",
    "coverage_floor_check", "ordering_movement", "cross_position_movement",
    "candidate_configs", "config_key", "require_anchors", "select_lambda", "aggregate_admissible",
    "pooled_ship", "level_verdict", "attribution_signature",
]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scope gates
# ══════════════════════════════════════════════════════════════════════════════════════════════
def draftable_tier_size(*, teams: int = DRAFT_TEAMS, preset: str = TIER_PRESET) -> int:
    """The draftable SKILL tier, DERIVED from the shipped league preset rather than chosen (§0).

    Counts every roster slot of the named preset that a QB/RB/WR/TE can occupy — starters, FLEX and
    bench — and multiplies by the league size. K and DST slots are excluded because they are a
    separate model (`nfl_fantasy_kdst_base_v1`) with its own selection story and are out of this
    story's scope.

    ⭐ Deriving it means a preset change has ONE owner and the tier cannot be tuned. A tier that could
    be tuned is a tier that would be tuned, and it sits directly upstream of every number here."""
    from quant_sports_intel_models.football.nfl.fantasy import league_presets as LP

    cfg = LP.get_preset(preset, n_teams=int(teams))
    roster = getattr(cfg, "roster", None)
    if not roster:                                  # pragma: no cover - defended, see the raise below
        raise SystemExit(
            f"could not resolve the '{preset}' preset's roster from league_presets — the draftable "
            "tier is a DERIVED product quantity and must never be hard-coded (NF-RECAL1 §0).")
    skill = set(RECALIBRATED_POSITIONS)
    n = sum(int(s.count) for s in roster if skill.intersection(set(s.eligible)))
    return int(n * int(teams))


#: The rookie dispositions NF-RECAL1's SCOPE has been re-read against by a human, with the date of
#: the read. A disposition outside this set trips the gate below — which is the gate WORKING, not a
#: bug: it exists precisely so a change to the rookie leg cannot silently widen this story's scope.
#:
#:   · `CONSTRAINT_REFUSED` (2026-08-05, the pre-registration) — the rookie leg was CLOSED, and
#:     re-opening it inside a differently-named story would re-apply the pressure the PM closed it
#:     to remove.
#:   · `SHIP` (re-read 2026-08-20, NF-D21-PUBLISH) — the rookie leg is now SERVED at λ=0.5 by its
#:     OWN chain (NF-D16 → NF-D22's floor → the recorded PM disposition). ⭐ THE SCOPE CONCLUSION IS
#:     UNCHANGED AND THE REASON IS NOW STRONGER, not weaker: a correction is live on that leg, so a
#:     rookie row reaching THIS story's population would be recalibrated TWICE — once by the rookie
#:     policy at build time and again by a veteran-level constant fitted over a population that
#:     should never have contained it. "Governed elsewhere" and "governed elsewhere AND already
#:     corrected" both mean the same thing here: out of scope.
REVIEWED_ROOKIE_DISPOSITIONS: tuple[str, ...] = ("CONSTRAINT_REFUSED", "SHIP")


def assert_rookie_leg_untouched(frame: pd.DataFrame, *, col: str = "is_rookie") -> None:
    """⛔ THE SINGLE GATE THAT KEEPS THE OUT-OF-SCOPE ROOKIE LEG OUT (§1).

    Raises if a rookie row reaches this story's fit or scoring population. It also re-asserts the
    imported disposition, so a change to `rookie_publish_policy` that no human has re-read this
    story's scope against fails here rather than silently widening it.

    ⚠️ IT NO LONGER PINS ONE LITERAL DISPOSITION, and the difference matters. The original form
    demanded `CONSTRAINT_REFUSED` exactly — correct while that was the only state the rookie leg had
    ever had, but it made the gate fire on ANY rookie decision, including one that STRENGTHENS the
    exclusion (see `REVIEWED_ROOKIE_DISPOSITIONS`). A gate that cannot distinguish "the premise
    broke" from "the premise was reconfirmed" forces the next session to either re-read it properly
    or delete it, and under time pressure that is a coin flip. The reviewed set records the re-read
    instead, so the tripwire keeps its teeth for an UNreviewed change.

    ⛔ ADDING A DISPOSITION TO THAT SET IS THE RE-READ — never a way around this raise. And the
    rookie policy's own coherence (serving must not contradict its disposition) is delegated to
    `RPP.assert_coherent()` rather than re-implemented here, so there is one owner of that rule.

    This is a function rather than an inline filter because "rookies are untouched" is the claim the
    PM's close depends on, and a claim that important must be independently testable."""
    RPP.assert_coherent()
    if RPP.DISPOSITION not in REVIEWED_ROOKIE_DISPOSITIONS:
        raise SystemExit(
            "the rookie recalibration's disposition has changed to a value NF-RECAL1's scope has "
            f"never been re-read against (DISPOSITION={RPP.DISPOSITION!r}, "
            f"SERVING_ENABLED={RPP.SERVING_ENABLED!r}; re-read: {REVIEWED_ROOKIE_DISPOSITIONS}). "
            "NF-RECAL1 scopes itself to the VETERAN leg on the premise that the rookie leg is "
            "governed by its own chain; that premise must be re-read by a human, and the re-read "
            "RECORDED in REVIEWED_ROOKIE_DISPOSITIONS, before this story runs again.")
    if col in frame.columns and bool(pd.Series(frame[col]).fillna(False).astype(bool).any()):
        raise SystemExit(
            f"{int(pd.Series(frame[col]).fillna(False).astype(bool).sum())} rookie row(s) reached the "
            "NF-RECAL1 population. The rookie LEVEL is governed by the CLOSED NF-D16→D21 chain and is "
            "out of scope: " + ROOKIE_EXCLUSION_REASON)


def avail_bucket(proj_games) -> np.ndarray:
    """Fixed, physical availability buckets for `avail_cond` — never fitted (see `AVAIL_BUCKETS`)."""
    g = pd.to_numeric(pd.Series(proj_games), errors="coerce").to_numpy(dtype=float)
    out = np.array([AVAIL_BUCKET_LABELS[-1]] * len(g), dtype=object)
    for (lo, hi), lab in zip(AVAIL_BUCKETS, AVAIL_BUCKET_LABELS):
        out[(g >= lo) & (g < hi)] = lab
    out[~np.isfinite(g)] = AVAIL_BUCKET_LABELS[0]   # unknown availability is the conservative bucket
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE METRIC — CRPS from the served 80% band (§4)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _tau_knots(n: int = CRPS_TAU_KNOTS) -> np.ndarray:
    """Midpoint knots on (0,1). Midpoints rather than endpoints because the split-normal quantile
    function diverges at τ ∈ {0,1}, and a rule that evaluates its integrand at a pole is a rule that
    silently returns inf."""
    return (np.arange(n, dtype=float) + 0.5) / float(n)


def _band_quantiles(point, p10, p90, taus: np.ndarray) -> np.ndarray:
    """The predictive quantile function implied by a served (p10, point, p90) triple.

    A TWO-PIECE (split) normal — a different σ either side of the centre — because the served bands
    are deliberately ASYMMETRIC (NF1.9's per-player neighbourhood quantiles; the engine's own
    `league_p10 = base_p10 × ratio` rescale is documented to preserve that asymmetry), and forcing a
    symmetric normal through them would score a distribution the product does not serve.

    ⭐ CLIPPED AT ZERO, AND THE CLIP IS SUBSTANTIVE RATHER THAN COSMETIC. A fantasy season cannot be
    negative, and this population has a genuine point mass at zero (NF1.9 measured 31%). Clipping the
    QUANTILE function puts mass `P(Q(τ) < 0)` exactly on the atom at 0, which is the correct
    representation of that population — and it is what lets the score see a projection that is
    IMPOSSIBLE rather than merely wrong.

    A degenerate triple (p10 = point = p90) collapses to a point mass, for which CRPS reduces to
    |y − point|. That is the right limit and it is asserted in the tests."""
    p = np.asarray(point, dtype=float)[:, None]
    lo = np.asarray(p10, dtype=float)[:, None]
    hi = np.asarray(p90, dtype=float)[:, None]
    # A non-monotone triple (which a negative fitted slope can produce) is SORTED rather than
    # silently mis-ordered: an inverted band is a real defect that the ordering measurement reports,
    # and a quantile function must still be non-decreasing for the score to mean anything.
    lo = np.minimum(lo, hi)
    hi = np.maximum(np.asarray(p10, dtype=float)[:, None], np.asarray(p90, dtype=float)[:, None])
    p = np.clip(p, lo, hi)
    s_lo = np.maximum((p - lo) / _Z80, 1e-9)
    s_hi = np.maximum((hi - p) / _Z80, 1e-9)
    from scipy.stats import norm
    z = norm.ppf(taus)[None, :]
    q = p + np.where(z < 0.0, s_lo, s_hi) * z
    return np.clip(q, 0.0, None)


def crps_from_band(point, p10, p90, y, *, n_tau: int = CRPS_TAU_KNOTS) -> np.ndarray:
    """Per-row CRPS via the quantile identity `CRPS(F,y) = 2∫₀¹ ρ_τ(y − Q(τ)) dτ`.

    The integral is the average pinball loss over `n_tau` midpoint knots, doubled. `CRPS_TAU_KNOTS` is
    fixed in the pre-registration and `test_crps_matches_the_closed_form_normal` proves this
    resolution reproduces the analytic Gaussian CRPS to 1e-3, so the resolution is a PROVEN
    sufficiency rather than a guess a reader has to take on trust."""
    taus = _tau_knots(n_tau)
    q = _band_quantiles(point, p10, p90, taus)
    yy = np.asarray(y, dtype=float)[:, None]
    u = yy - q
    pin = u * (taus[None, :] - (u < 0.0).astype(float))
    return 2.0 * pin.mean(axis=1)


def interval_score80(p10, p90, y, *, alpha: float = 1.0 - BAND_NOMINAL) -> np.ndarray:
    """Winkler/Gneiting interval score for the 80% band — the DISCLOSED interval metric the interval
    stories (NF1.7/1.8/1.9) were selected on, reported here so a level change is legible against the
    machinery that owns the widths."""
    lo = np.asarray(p10, dtype=float)
    hi = np.asarray(p90, dtype=float)
    yy = np.asarray(y, dtype=float)
    return ((hi - lo)
            + (2.0 / alpha) * np.clip(lo - yy, 0.0, None)
            + (2.0 / alpha) * np.clip(yy - hi, 0.0, None))


def band_metrics(point, p10, p90, y) -> dict:
    """Every metric this story reports for one arm on one population, from ONE reducer.

    Candidates, matched foils, degenerates and oracles all pass through this function, so "the anchors
    answer the same question as the candidates" is a property of the code rather than a sentence in a
    report."""
    p = np.asarray(point, dtype=float)
    yy = np.asarray(y, dtype=float)
    ok = np.isfinite(p) & np.isfinite(yy)
    if not ok.any():
        return {m: None for m in (SELECTION_METRIC,) + DISCLOSED_METRICS} | {"n": 0}
    p, yy = p[ok], yy[ok]
    lo = np.asarray(p10, dtype=float)[ok]
    hi = np.asarray(p90, dtype=float)[ok]
    d = p - yy
    return {
        "n": int(ok.sum()),
        SELECTION_METRIC: round(float(np.mean(crps_from_band(p, lo, hi, yy))), 4),
        "mae": round(float(np.mean(np.abs(d))), 4),
        "rmse": round(float(np.sqrt(np.mean(d ** 2))), 4),
        "bias": round(float(np.mean(d)), 4),
        "coverage80": round(float(np.mean((yy >= np.minimum(lo, hi)) & (yy <= np.maximum(lo, hi)))), 4),
        "interval_score80": round(float(np.mean(interval_score80(lo, hi, yy))), 4),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE FIVE FITS × TWO SPACES — all strictly in-fold (§2, §3)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pos(positions) -> np.ndarray:
    return np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)


def _g(games) -> np.ndarray:
    """The PROJECTED-games divisor for the per-game space, floored.

    ⚠️ PROJECTED, never REALIZED. Dividing by realized games would make the target an
    outcome-conditioned quantity — precisely the artifact §0 exists to keep out of this story — and it
    would be undefined for the ~31% of the population that plays none."""
    g = pd.to_numeric(pd.Series(games), errors="coerce").to_numpy(dtype=float)
    return np.maximum(np.nan_to_num(g, nan=MIN_GAMES), MIN_GAMES)


def fit_form(form: str, space: str, point, real, positions, games) -> dict:
    """Fit ONE form in ONE space, strictly in-fold.

    ⭐ EVERY FORM'S TARGET IS THE REALIZED SEASON TOTAL, IN BOTH SPACES. The "space" changes only how
    the correction is PARAMETERISED, never what it is fitted against — that is what makes the two
    spaces a matched foil differing in exactly one channel (§2), and it is what keeps the realized
    games count out of the fit entirely."""
    p = np.asarray(point, dtype=float)
    y = np.asarray(real, dtype=float)
    pos = _pos(positions)
    g = _g(games)
    fin = np.isfinite(p) & np.isfinite(y)

    if form == "global_const":
        sel = fin & (p >= MIN_POINT)
        return {"k": float(np.clip(np.mean(y[sel] / p[sel]), *MULT_CLIP))} if sel.sum() >= 20 else {}

    if form == "pos_const":
        out = {}
        for q in RECALIBRATED_POSITIONS:
            sel = fin & (pos == q) & (p >= MIN_POINT)
            if sel.sum() >= 20:
                out[q] = float(np.clip(np.mean(y[sel] / p[sel]), *MULT_CLIP))
        return out

    if form == "avail_cond":
        # ⭐ THE DIRECT TEST OF THE MOTIVATING EXPLANATION: a per-position constant that is allowed to
        #   differ by expected-games bucket. A thin cell FALLS BACK to the position's own constant
        #   rather than being skipped — a skipped cell would leave those players uncorrected while
        #   their neighbours moved, which is an ordering artefact manufactured by estimator thinness.
        base = fit_form("pos_const", space, point, real, positions, games)
        buck = avail_bucket(games)
        out = {}
        for q in RECALIBRATED_POSITIONS:
            for b in AVAIL_BUCKET_LABELS:
                sel = fin & (pos == q) & (buck == b) & (p >= MIN_POINT)
                out[(q, b)] = (float(np.clip(np.mean(y[sel] / p[sel]), *MULT_CLIP))
                               if sel.sum() >= MIN_CELL else base.get(q, np.nan))
        return out

    if form == "pos_offset":
        out = {}
        for q in RECALIBRATED_POSITIONS:
            sel = fin & (pos == q)
            if sel.sum() < 20:
                continue
            if space == "season_total":            # total + c
                out[q] = float(np.clip(np.mean(y[sel] - p[sel]), *OFFSET_CLIP))
            else:                                  # PRIMARY: total + c·g  (least squares through 0)
                gg, r = g[sel], y[sel] - p[sel]
                out[q] = float(np.clip(np.dot(gg, r) / max(np.dot(gg, gg), 1e-9),
                                       OFFSET_CLIP[0] / 17.0, OFFSET_CLIP[1] / 17.0))
        return out

    if form == "pos_affine":
        out = {}
        for q in RECALIBRATED_POSITIONS:
            sel = fin & (pos == q)
            if sel.sum() < 30 or float(np.std(p[sel])) <= 1e-9:
                continue
            if space == "season_total":            # a + b·total
                b, a = np.polyfit(p[sel], y[sel], 1)
                out[q] = (float(a), float(b))
            else:                                  # PRIMARY: a·g + b·total
                X = np.column_stack([g[sel], p[sel]])
                coef, *_ = np.linalg.lstsq(X, y[sel], rcond=None)
                out[q] = (float(coef[0]), float(coef[1]))
        return out

    raise ValueError(f"unknown form {form!r}")


def fit_form_peeking_on_metric(form: str, space: str, point, p10, p90, real, positions, games,
                               *, init: dict | None = None) -> dict:
    """⭐⭐ THE PEEKING CEILING, FITTED ON **CRPS** RATHER THAN BY LEAST SQUARES — and this is a
    correction to how this programme has been building ceilings, found by its own consistency check.

    NF1.7 (b) / NF1.9 (f) / NF-D16 (g‴) say a peeking oracle is a floor only at MATCHED FAMILY and
    MATCHED SAMPLE. **THIS RUN MEASURED A THIRD REQUIREMENT: MATCHED OBJECTIVE.** The first cut fitted
    each form's ceiling by least squares (the same estimator the candidates use) and scored it on
    CRPS — and the ceilings DID NOT ORDER BY CAPACITY: `oracle_pos_affine` (50.796) came out WORSE
    than `oracle_pos_const` (50.617) even though the affine family strictly CONTAINS the constant one.
    That is not a paradox and it is not noise. "Peeking can only help" holds only when the peeking fit
    minimises the OBJECTIVE THE ARM IS SCORED ON; a least-squares fit of a richer family can easily
    land further from the CRPS optimum than a coarser family's least-squares fit, so an LS-fitted
    ceiling is not a bound on a CRPS-scored arm at all — it is just another arm.

    ⇒ each form's parameters are optimised HERE to minimise the very CRPS the arms are graded on, on
    the held-out fold. Then the nesting in `FORM_NESTING` genuinely implies the ordering, the check
    `ceilings_order_by_capacity` becomes an internal-consistency signal a single shared ceiling
    structurally cannot produce, and `family_ceiling_check` becomes a real inversion detector instead
    of a coin flip.

    ⭐ THE OPTIMISATION IS SEPARABLE AND THAT IS WHY IT IS AFFORDABLE: CRPS is a sum over rows and a
    per-position (or per-cell) parameter touches only its own rows, so each position is optimised
    independently over 1–2 parameters. Initialised at the least-squares fit so the ceiling can never
    come out WORSE than the LS one — it is a refinement, never a regression.

    ⛔ This is an ANCHOR-ONLY estimator. No candidate may use it: a candidate that fitted on the
    held-out fold would not be a candidate."""
    from scipy.optimize import minimize

    p = np.asarray(point, dtype=float)
    lo = np.asarray(p10, dtype=float)
    hi = np.asarray(p90, dtype=float)
    y = np.asarray(real, dtype=float)
    pos = _pos(positions)
    g = _g(games)
    base = dict(init or {})

    def _score(sel: np.ndarray, params: dict) -> float:
        ap, alo, ahi = apply_to_band(form, space, params, p[sel], lo[sel], hi[sel],
                                     pos[sel], g[sel], 1.0)
        return float(np.mean(crps_from_band(ap, alo, ahi, y[sel])))

    out: dict = {}
    if form == "global_const":
        sel = np.ones(len(p), dtype=bool)
        x0 = [float(base.get("k", 1.0))]
        r = minimize(lambda x: _score(sel, {"k": float(np.clip(x[0], *MULT_CLIP))}), x0,
                     method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 200})
        return {"k": float(np.clip(r.x[0], *MULT_CLIP))}

    for q in RECALIBRATED_POSITIONS:
        sel = pos == q
        if sel.sum() < 5:
            continue
        if form == "pos_const":
            x0 = [float(base.get(q, 1.0))]
            r = minimize(lambda x, s=sel, qq=q: _score(s, {qq: float(np.clip(x[0], *MULT_CLIP))}),
                         x0, method="Nelder-Mead",
                         options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 200})
            out[q] = float(np.clip(r.x[0], *MULT_CLIP))
        elif form == "pos_offset":
            cap = (OFFSET_CLIP[0] / 17.0, OFFSET_CLIP[1] / 17.0) if space == "per_game" \
                else OFFSET_CLIP
            x0 = [float(base.get(q, 0.0))]
            r = minimize(lambda x, s=sel, qq=q, c=cap: _score(s, {qq: float(np.clip(x[0], *c))}),
                         x0, method="Nelder-Mead",
                         options={"xatol": 1e-3, "fatol": 1e-6, "maxiter": 200})
            out[q] = float(np.clip(r.x[0], *cap))
        elif form == "pos_affine":
            a0, b0 = base.get(q, (0.0, 1.0))
            r = minimize(lambda x, s=sel, qq=q: _score(s, {qq: (float(x[0]), float(x[1]))}),
                         [float(a0), float(b0)], method="Nelder-Mead",
                         options={"xatol": 1e-3, "fatol": 1e-6, "maxiter": 400})
            out[q] = (float(r.x[0]), float(r.x[1]))
        elif form == "avail_cond":
            buck = avail_bucket(games)
            for b in AVAIL_BUCKET_LABELS:
                cell = sel & (buck == b)
                if cell.sum() < 5:
                    k0 = base.get((q, b), 1.0)
                    out[(q, b)] = float(k0) if np.isfinite(k0) else 1.0
                    continue
                k0 = base.get((q, b), 1.0)
                k0 = float(k0) if np.isfinite(k0) else 1.0
                r = minimize(lambda x, s=cell, key=(q, b):
                             _score(s, {key: float(np.clip(x[0], *MULT_CLIP))}), [k0],
                             method="Nelder-Mead",
                             options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 200})
                out[(q, b)] = float(np.clip(r.x[0], *MULT_CLIP))
        else:
            raise ValueError(f"unknown form {form!r}")
    return out


def predict_form(form: str, space: str, params: dict, point, positions, games) -> np.ndarray:
    """Apply one fitted form to a held-out fold. Returns the ADJUSTED point BEFORE the λ blend and
    before the scope gate — the three are separate steps so no arm can own a private copy of any of
    them, and so `λ = 0` reproduces the incumbent EXACTLY for every form.

    A position or cell with no fitted parameter yields NaN, which the caller turns back into the
    incumbent. A missing estimate must degrade to 'leave it alone', never to a silent zero."""
    p = np.asarray(point, dtype=float)
    pos = _pos(positions)
    g = _g(games)
    out = np.full(len(p), np.nan)
    if form == "global_const":
        if "k" in params:
            out = p * float(params["k"])
    elif form == "pos_const":
        for q, k in params.items():
            out[pos == q] = p[pos == q] * float(k)
    elif form == "avail_cond":
        buck = avail_bucket(games)
        for (q, b), k in params.items():
            sel = (pos == q) & (buck == b)
            if sel.any() and np.isfinite(k):
                out[sel] = p[sel] * float(k)
    elif form == "pos_offset":
        for q, c in params.items():
            sel = pos == q
            out[sel] = p[sel] + (float(c) * g[sel] if space == "per_game" else float(c))
    elif form == "pos_affine":
        for q, (a, b) in params.items():
            sel = pos == q
            out[sel] = (float(a) * g[sel] if space == "per_game" else float(a)) + float(b) * p[sel]
    else:
        raise ValueError(f"unknown form {form!r}")
    return np.where(np.isfinite(out), out, p)


def apply_to_band(form: str, space: str, params: dict, point, p10, p90, positions, games,
                  lam: float) -> tuple:
    """⭐ THE CORRECTION IS APPLIED TO THE POINT **AND BOTH BAND EDGES**, WITH THE SAME MAP AND THE
    SAME λ — which is what makes this a LEVEL SHIFT rather than a point-only edit.

    That choice is what C3 exists to police and it is the honest one: serving would move the band's
    centre with the point (`run_interval_revalidation` is REQUIRED after any level shift for exactly
    this reason, and NF-D21 was refused on it). Applying the correction to the point alone would leave
    the band anchored to a projection the product no longer makes, quietly inflating coverage and
    turning C3 into a check that cannot fail.

    ⚠️ The band is re-sorted afterwards. A NEGATIVE fitted slope in `pos_affine` inverts the triple,
    and an inverted band is a real defect the ordering measurement reports — but a quantile function
    must remain non-decreasing for any score computed from it to mean anything."""
    args = (form, space, params)
    adj_p = predict_form(*args, point, positions, games)
    adj_lo = predict_form(*args, p10, positions, games)
    adj_hi = predict_form(*args, p90, positions, games)
    p = blend_toward_incumbent(point, adj_p, lam)
    lo = blend_toward_incumbent(p10, adj_lo, lam)
    hi = blend_toward_incumbent(p90, adj_hi, lam)
    p, lo, hi = np.clip(p, 0.0, None), np.clip(lo, 0.0, None), np.clip(hi, 0.0, None)
    return p, np.minimum(lo, hi), np.maximum(lo, hi)


def blend_band_toward_incumbent(point, p10, p90, adj, lam: float) -> tuple:
    """The λ blend applied to a pre-computed (point, p10, p90) adjustment triple — used by the anchors,
    which construct their adjustment directly rather than through a fitted form."""
    return (np.clip(blend_toward_incumbent(point, adj[0], lam), 0.0, None),
            np.clip(blend_toward_incumbent(p10, adj[1], lam), 0.0, None),
            np.clip(blend_toward_incumbent(p90, adj[2], lam), 0.0, None))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE THREE CONSTRAINTS (§5)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def coverage_floor_check(y, p10, p90, positions, *, floor: float = COVERAGE_FLOOR,
                         incumbent_coverage: dict | None = None,
                         equality_exact: bool = False) -> dict:
    """C3 — the 80% coverage FLOOR after the level shift, PER POSITION and POOLED OVER ROWS.

    ⭐⭐ **THE CLAUSE GOVERNS THE CHANGE, NOT THE LEVEL: `coverage_λ ≥ min(floor, coverage_incumbent)`
    — AND THE SECOND TERM IS NOT A LOOSENING CHOSEN TO GET AN ANSWER.** It is NF-D20's C2 structure,
    inherited, for the identical reason and after the identical measurement. The FIRST cut of this
    story used the bare floor and it refused **every arm on every fold, including λ = 0** — i.e. it
    refused the NULL — because the served veteran band covers only **0.50** of nominal ON THE
    DRAFTABLE TIER, against the 0.89 NF1.9 validated over the FULL universe. A constraint that
    refuses everything has examined nothing (NF1.7 (a)), and a bake-off run under one would have
    reported a null produced entirely by its own gate.

    ⚠️ **THAT 0.50 IS A REAL FINDING AND IT BELONGS TO THE INTERVAL STORY, NOT THIS ONE.** It is the
    NF1.9 zero-atom mechanism read on a different population: 83% of served lower bounds are 0, so a
    band is near-un-missable on the left tail over a 31%-zero universe and has to actually work on a
    draftable tier where the zeros are rare. It is a RE-SELECTION TRIGGER for the veteran band's
    population, ⛔ not something this story may act on, fit to, or quietly repair — and ⛔ the floor is
    NOT moved (E2.1-r's cardinal error): the clause reduces to the plain floor wherever the incumbent
    already clears it, and elsewhere it forbids making a pre-existing shortfall WORSE.

    `strict_ok` reports the bare-floor reading beside it as a SENSITIVITY so a reader can see exactly
    what the second term decided rather than taking it on trust.

    ⭐ POOLED OVER ROWS, NEVER A MEAN OF PER-FOLD MEANS (NF1.8): a position thin in one fold would be
    silently dropped by a row-count minimum, and the floor would then be evaluated on a quietly
    different population than the one it names.

    ⚠️ THE MARGIN IS REPORTED IN **ROWS**, not in coverage decimals (NF1.8 again). "0.7905 vs 0.80"
    reads like a calibration change; "two covered seasons short of 119 at n = 148" reads like what it
    is — and NF-D21 turned on exactly that distinction.

    ⛔ THIS IS A CONSTRAINT AND NEVER A TARGET. Nothing in this story selects on coverage headroom;
    that criterion is monotone in widening and the `wide_band` degenerate wins it outright.

    ⭐ `equality_exact` — THE NF-B3 HARNESS FIX (flagged by NF-C3-REREAD, made canonical there-after).
    The legacy clause computes `need = ceil(round(inc, 6) · n)` off a 6-dp-ROUNDED incumbent coverage
    (`per_position_coverage`'s default), so whenever the rounding rounds the incumbent's own coverage
    UP, an arm whose coverage EQUALS the incumbent's — including λ = 0, which IS the incumbent — fails
    by exactly one row. A governs-the-change clause's equality boundary must hold: doing nothing must
    always be admissible under a constraint on the CHANGE. With `equality_exact=True` the requirement
    is `need = ceil(bind · n − 1e-9)` and the caller must pass the UNROUNDED incumbent
    (`per_position_coverage(..., rounding=None)`), so `coverage == incumbent` sits exactly ON the
    boundary and passes. ⚠️ The default stays False so the RECORDED NF-RECAL1 / NF-C3-REREAD runs
    (whose reproduction gates require the artifact, ε-sensitivity and all) remain byte-reproducible;
    NF-B3 and every successor pass True."""
    yy = np.asarray(y, dtype=float)
    lo = np.minimum(np.asarray(p10, dtype=float), np.asarray(p90, dtype=float))
    hi = np.maximum(np.asarray(p10, dtype=float), np.asarray(p90, dtype=float))
    pos = _pos(positions)
    covered = (yy >= lo) & (yy <= hi)
    inc = incumbent_coverage or {}
    per: dict[str, dict] = {}
    for q in RECALIBRATED_POSITIONS:
        sel = pos == q
        n = int(sel.sum())
        if n == 0:
            continue
        # The binding level: the floor, or the incumbent's own coverage where the SHIPPED product
        # already falls short of it. Never above the floor — a floor is not a target.
        bind = min(float(floor), float(inc[q])) if q in inc and inc[q] is not None else float(floor)
        eps = 1e-9 if equality_exact else 0.0
        need = int(np.ceil(bind * n - eps))
        need_strict = int(np.ceil(float(floor) * n - eps))
        got = int(covered[sel].sum())
        per[q] = {"n": n, "coverage": round(got / n, 4), "covered_rows": got,
                  "binding_level": round(bind, 4), "rows_required": need,
                  "rows_of_slack": got - need, "ok": bool(got >= need),
                  "rows_of_slack_strict": got - need_strict,
                  "strict_ok": bool(got >= need_strict),
                  "incumbent_coverage": (round(float(inc[q]), 4)
                                         if q in inc and inc[q] is not None else None)}
    n_all = int(len(yy))
    return {
        "ok": bool(per) and all(v["ok"] for v in per.values()),
        "strict_ok": bool(per) and all(v["strict_ok"] for v in per.values()),
        "governs_the_change": bool(inc),
        "floor": float(floor), "per_position": per,
        "pooled_coverage": round(float(covered.mean()), 4) if n_all else None,
        "breaches": [f"{q} {v['coverage']:.4f}<{v['binding_level']:.3f} ({v['rows_of_slack']} rows)"
                     for q, v in per.items() if not v["ok"]],
        "breaches_strict": [f"{q} {v['coverage']:.4f}<{floor:.3f} "
                            f"({v['rows_of_slack_strict']} rows)"
                            for q, v in per.items() if not v["strict_ok"]],
        "evaluable": bool(per),
    }


def per_position_coverage(y, p10, p90, positions, *, rounding: int | None = 6) -> dict:
    """The incumbent's own per-position 80% coverage — the second term C3's clause is built on.

    Computed from the SHIPPED band on the SAME population the constraint is evaluated over, so
    "coverage_incumbent" can never be a number from a different slice than the one it governs.

    ⚠️ `rounding=None` returns the UNROUNDED coverage — REQUIRED whenever the caller evaluates C3
    with `equality_exact=True` (the NF-B3 boundary fix): the 6-dp rounding is exactly what
    manufactures the one-row failure at the equality boundary. The rounded default is kept only so
    the recorded NF-RECAL1 / NF-C3-REREAD artifacts stay byte-reproducible."""
    yy = np.asarray(y, dtype=float)
    lo = np.minimum(np.asarray(p10, dtype=float), np.asarray(p90, dtype=float))
    hi = np.maximum(np.asarray(p10, dtype=float), np.asarray(p90, dtype=float))
    pos = _pos(positions)
    cov = (yy >= lo) & (yy <= hi)
    def _r(v: float) -> float:
        return float(v) if rounding is None else round(float(v), rounding)
    return {q: (_r(cov[pos == q].mean()) if (pos == q).any() else None)
            for q in RECALIBRATED_POSITIONS}


def ordering_movement(point, adjusted, positions) -> dict:
    """C1's INPUT — within-position rank movement, MEASURED on emitted projections (NF-D16 method
    lock 2: 'moves no ranks by construction' is a claim about a form's algebra under ADMISSIBLE
    parameters, and the parameters this run fitted are the only ones that matter)."""
    p = np.asarray(point, dtype=float)
    a = np.asarray(adjusted, dtype=float)
    pos = _pos(positions)
    per, rho = {}, {}
    for q in RECALIBRATED_POSITIONS:
        sel = pos == q
        if sel.sum() < 3:
            continue
        rb = pd.Series(p[sel]).rank(ascending=False, method="average")
        rc = pd.Series(a[sel]).rank(ascending=False, method="average")
        per[q] = float(np.max(np.abs(rb.to_numpy() - rc.to_numpy())))
        rho[q] = float(rb.corr(rc, method="spearman"))
    return {"max_rank_move_by_pos": per, "worst_rank_move": max(per.values()) if per else 0.0,
            "within_position_rho": rho}


def cross_position_movement(point, adjusted, positions, names=None, *, top_n: int = 100) -> dict:
    """⭐ THE MEASUREMENT THE BRIEF ASKS FOR AND FOR WHICH THIS PROGRAMME OWNS **NO VALIDATED BAR** —
    whole-board movement ACROSS positions, reported for PM judgement and gated on by nothing.

    A within-position level shift preserves that position's order by construction; the shared draft
    board is where a per-position correction actually bites (NF-D16 (g‴): a 'moves no ranks' argument
    is a WITHIN-position claim only, and NF-D21 measured 78 QBs changing overall rank while every QB
    projection moved by exactly 0.0).

    ⛔ IT IS DELIBERATELY NOT A GATE. NF-D17 validated a placement clause for the ROOKIE leg; no
    equivalent reference distribution exists for whole-board veteran churn, and inventing a threshold
    here — on the population whose answer is already in view — is the E2.1-r move this programme keeps
    closing. Measuring it and handing the number to the PM is the honest alternative to a bar nobody
    derived."""
    p = np.asarray(point, dtype=float)
    a = np.asarray(adjusted, dtype=float)
    rb = pd.Series(p).rank(ascending=False, method="first").to_numpy()
    rc = pd.Series(a).rank(ascending=False, method="first").to_numpy()
    d = np.abs(rb - rc)
    top_before = set(np.argsort(-p)[:top_n].tolist())
    top_after = set(np.argsort(-a)[:top_n].tolist())
    out = {
        "n_board": int(len(p)),
        "median_abs_rank_move": round(float(np.median(d)), 2),
        "p90_abs_rank_move": round(float(np.percentile(d, 90)), 2),
        "max_abs_rank_move": round(float(d.max()), 2) if len(d) else 0.0,
        "n_moved": int((d > 0).sum()),
        f"top{top_n}_churn": int(len(top_before - top_after)),
        f"top{top_n}_membership_stable": bool(top_before == top_after),
        "top10_order_stable": bool(list(np.argsort(-p)[:10]) == list(np.argsort(-a)[:10])),
    }
    if names is not None:
        nm = np.asarray(names, dtype=object)
        out["top10_before"] = [str(x) for x in nm[np.argsort(-p)[:10]]]
        out["top10_after"] = [str(x) for x in nm[np.argsort(-a)[:10]]]
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE PRE-REGISTERED FIELD + the in-fold λ machinery (§6, §7)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def candidate_configs(*, space: str = PRIMARY_SPACE, smoke: bool = False) -> list[dict]:
    """The DECLARED trial field: the NULL + 5 forms × 2 λ-rules = 11 arms, fixed before the run."""
    cfgs = [{"label": "incumbent (NULL)", "form": "incumbent", "space": space, "rule": None,
             "recalibrates": False, "shippable": True, "constrained": False, "is_foil": False}]
    forms = FORMS[:2] + (LEARNED_FOIL,) if smoke else FORMS
    for form in forms:
        for rule in SELECTION_RULES:
            cfgs.append({
                "label": f"{form} · {rule}", "form": form, "space": space, "rule": rule,
                "recalibrates": True, "shippable": True,
                "constrained": RULE_CONSTRAINED[rule], "is_foil": False,
                "learned": form == LEARNED_FOIL,
                "space_invariant": form in SPACE_INVARIANT_FORMS})
    return cfgs


def matched_foil_configs(*, smoke: bool = False) -> list[dict]:
    """The SEASON-TOTAL twins (§2) — identical in every respect except whether the correction's
    intercept scales with expected games.

    ⛔ NON-SHIPPABLE and excluded from the eligible set, from PBO's search and from the DSR trial
    field: a diagnostic is never a trial (MH2 (a)). Their job is ATTRIBUTION — the paired delta says
    whether the per-game channel earned the result — not to be shipped."""
    out = []
    for cfg in candidate_configs(space=FOIL_SPACE, smoke=smoke):
        if cfg["form"] == "incumbent":
            continue
        out.append({**cfg, "label": f"{cfg['form']} · {cfg['rule']} [season_total FOIL]",
                    "shippable": False, "is_foil": True})
    return out


def config_key(cfg: dict) -> str:
    return f"{cfg['form']}@{cfg.get('space')}@{cfg.get('rule') or 'null'}"


def require_anchors(scored: dict, required: tuple = _REQUIRED_ANCHORS) -> None:
    """⭐ A MISSING ANCHOR IS A HARD FAILURE, NEVER A PASS (NF1.7 anchor lesson (a)).

    An anchor that fails to fit makes its own check VACUOUSLY TRUE — `winner < anchor` against an
    absent anchor compares nothing and reports green. NF1.7 shipped that bug once; every anchored
    story since carries this guard, as a function so it can be tested without running the bake-off."""
    missing = [k for k in required
               if k not in scored or scored[k].get(SELECTION_METRIC) is None]
    if missing:
        raise SystemExit(
            f"the anchor(s) {missing} did not score — their checks would pass on NOTHING. Fix the "
            "anchor before reading any selection (NF1.7 anchor-set lesson 1).")


def aggregate_admissible(per_fold: dict, constrained: bool, *, grid: tuple = LAMBDA_GRID) -> tuple:
    """The λ values a RULE may choose from, given the admissibility of the folds it is allowed to see.

    `constrained=False` is the REFERENCE arm: no constraint evidence enters and the whole grid is
    available. Otherwise the rule takes the INTERSECTION over every prior fold — "the correction must
    have been admissible on every fold we have ever seen".

    ⚠️ AN EMPTY EVIDENCE SET IS NOT AN EMPTY CONSTRAINT. With no prior fold to verify against, the
    rule falls back to `EMPTY_EVIDENCE_LAMBDA` alone rather than to the full grid — the difference
    between "nothing refused it" and "nothing examined it" (NF1.7 (a)). λ = 0 is always available:
    declining to recalibrate cannot be refused by a constraint on recalibration."""
    if not constrained:
        return tuple(float(x) for x in grid)
    if not per_fold:
        return (float(EMPTY_EVIDENCE_LAMBDA),)
    allowed = set(float(x) for x in grid)
    for s in sorted(per_fold):
        allowed &= set(float(x) for x in per_fold[s])
    allowed.add(float(EMPTY_EVIDENCE_LAMBDA))
    return tuple(sorted(allowed))


def select_lambda(allowed: tuple, inner_metric: dict) -> dict:
    """Pick λ from an ALLOWED set by the IN-FOLD metric — `argmin crps`, ties to the SMALLER λ.

    ⭐ THE ARGMIN IS NOT THE SAME AS "TAKE THE LARGEST ADMISSIBLE λ". The two coincide only if the
    metric is monotone in λ, which is a MEASUREMENT and not a property of the family. Registering the
    argmin keeps the rule correct where it is not, and the run reports whether the two agreed."""
    cands = [(float(inner_metric[lam]), float(lam)) for lam in allowed
             if inner_metric.get(lam) is not None and np.isfinite(inner_metric.get(lam, np.nan))]
    if not cands:
        return {"lam": float(EMPTY_EVIDENCE_LAMBDA), "metric": None, "n_allowed": len(allowed),
                "note": "no scorable in-fold metric over the allowed set — falls back to the "
                        "incumbent rather than to an unverified correction"}
    best = min(cands)
    return {"lam": best[1], "metric": round(best[0], 4), "n_allowed": len(allowed),
            "allowed": [round(x, 4) for x in allowed]}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE VERDICT (§5, §7, §8)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def pooled_ship(*, winner: dict | None, incumbent_metric: float | None, ordering: dict,
                placement: dict | None, coverage: dict | None,
                pbo: float | None, dsr: float | None, pvalue: float | None,
                pbo_max: float = PBO_MAX, dsr_min: float = DSR_MIN,
                alpha: float = ALPHA) -> dict:
    """THE SHIP DECISION under the pre-registered POOLED framing — one hypothesis, one test, and the
    ship unit is the whole per-position correction (all four positions together or not at all).

    All three constraints appear here as checks on the SELECTED arm as well as on eligibility, so a
    reader of the verdict can see the constraint state of the thing actually chosen rather than having
    to trust that the eligible set was filtered correctly.

    ⚠️ The ORDERING and COVERAGE constraints are checked PER POSITION even though the decision is
    pooled. A pooled ρ can sit flat while one position's order collapses, and a pooled coverage can
    clear while one position breaches — averaging is the exact operation that hides the failure the
    constraints exist to catch. A pooled hypothesis about the LEVEL does not license a pooled reading
    of the ORDER or of the FLOOR."""
    beats = bool(winner and incumbent_metric is not None and winner.get("metric") is not None
                 and float(winner["metric"]) < float(incumbent_metric))
    per_pos = (ordering or {}).get("per_position", {})
    checks = {
        "has_eligible_winner": winner is not None,
        "recalibrates": bool(winner and winner.get("recalibrates")),
        "beats_incumbent": beats,
        "ordering_ok_every_position": bool(per_pos) and all(v.get("ok", False)
                                                            for v in per_pos.values()),
        "placement_holds_out_every_fold": bool((placement or {}).get("holds_out")),
        "coverage_floors_hold": bool((coverage or {}).get("ok")),
        "pbo_ok": pbo is not None and pbo < pbo_max,
        "dsr_ok": dsr is not None and dsr >= dsr_min,
        "significant": pvalue is not None and float(pvalue) <= float(alpha),
    }
    return {"ship": all(checks.values()), "framing": PREREGISTERED_FRAMING, **checks}


def level_verdict(*, pooled_ships: bool, premise_confirmed: bool,
                  sanity_degenerates_lose: bool,
                  permutation_across_beaten: bool, oracle_respected: bool,
                  family_ceiling_respected: bool, ceilings_order_by_capacity: bool,
                  over_scale_loses: bool, wide_band_loses: bool,
                  rookie_leg_untouched: bool, space_invariance_proven: bool) -> dict:
    """The STORY-level decision: the pre-registered pooled gate PLUS the run's global sanity anchors.

    The anchors are STORY-level VETOES on purpose. A degenerate winning the metric, or an arm beating
    its own family's peeking ceiling, does not mean "this run was unlucky" — it means the measurement
    is not trustworthy ANYWHERE in it and no number computed from it may be shipped.

    ⭐ TWO OF THESE ARE UNIQUE TO THIS STORY AND BOTH ARE LOAD-BEARING:
      · `premise_confirmed` — a recalibration fitted to a defect that does not reproduce in its own
        population is a correction to nothing (§0). This veto is what stops the story from shipping a
        board-wide level shift on the strength of an inherited number.
      · `ceilings_order_by_capacity` — the per-form peeking ceilings must ORDER by how rich each form
        is (`FORM_NESTING`). That is an internal-consistency signal a single shared ceiling
        structurally cannot produce (NF-D16 (g‴)), and its failure means the ceilings are measuring
        something other than capacity."""
    checks = {
        "pooled_gate_passes": bool(pooled_ships),
        "premise_confirmed_in_this_population": bool(premise_confirmed),
        # ⭐ SPLIT FROM `over_scale_loses` ON PURPOSE — a BUNDLED flag mixing a metric-SANITY check
        #   with a MAGNITUDE hypothesis is a liability (NF-D20): a future reader sees one `False` and
        #   concludes the MEASUREMENT is untrustworthy, when in fact the sanity half is fine and only
        #   the registered magnitude was refuted. These are different claims and get different flags.
        "sanity_degenerates_lose": bool(sanity_degenerates_lose),
        "permutation_across_beaten": bool(permutation_across_beaten),
        "oracle_respected": bool(oracle_respected),
        "family_ceiling_respected": bool(family_ceiling_respected),
        "ceilings_order_by_capacity": bool(ceilings_order_by_capacity),
        "over_scale_loses": bool(over_scale_loses),
        "wide_band_loses": bool(wide_band_loses),
        "rookie_leg_untouched": bool(rookie_leg_untouched),
        "space_invariance_proven": bool(space_invariance_proven),
    }
    return {"ship": all(checks.values()), **checks}


def attribution_signature(*, incumbent_bias: float | None, winner_bias: float | None,
                          incumbent_metric: float | None, winner_metric: float | None) -> dict:
    """⭐ NF-D15 (g′) — THE SIGNATURE THAT SEPARATES A LEVEL FIX FROM A PER-PLAYER EFFECT WEARING ONE'S
    CLOTHES.

    A genuine LEVEL correction moves pooled bias TOWARD zero while accuracy improves. NF-D15 measured
    the opposite — bias moving FURTHER from zero (−20.87 → −22.44) while MAE improved — and that is
    what refuted NF-D14's stated level mechanism. So "my arm won" is not "it won for the reason I
    said", and this function computes the corroborating tell rather than leaving it to prose.

    `verdict`:
      · `level_fix`        — accuracy improved AND |bias| moved toward zero. The stated mechanism holds.
      · `per_player_effect` — accuracy improved while |bias| moved AWAY from zero. The lift may be
                              real and the LEVEL story is refuted; report it as a different effect.
      · `no_lift`          — accuracy did not improve; there is nothing to attribute."""
    out = {"incumbent_bias": incumbent_bias, "winner_bias": winner_bias,
           "incumbent_metric": incumbent_metric, "winner_metric": winner_metric,
           "verdict": "indeterminate"}
    if None in (incumbent_bias, winner_bias, incumbent_metric, winner_metric):
        return out
    improved = float(winner_metric) < float(incumbent_metric)
    toward_zero = abs(float(winner_bias)) < abs(float(incumbent_bias))
    out["accuracy_improved"] = bool(improved)
    out["bias_moved_toward_zero"] = bool(toward_zero)
    out["abs_bias_delta"] = round(abs(float(winner_bias)) - abs(float(incumbent_bias)), 4)
    out["verdict"] = ("level_fix" if improved and toward_zero
                      else "per_player_effect" if improved else "no_lift")
    return out
