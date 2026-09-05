"""nf_inj4b_designation_duration.py — NF-INJ4b: the FRESH registration of NF-INJ4's duration model
with the oracle anchor corrected to MATCHED RESOLUTION.

⭐ READ `ablation_results/nf_inj4b_preregistration.md`. ⛔ Editing it after a result is not a
pre-registration (E2.1-r).

────────────────────────────────────────────────────────────────────────────────────────────────
⛔ THE HONESTY CLAUSE, WHICH IS THIS MODULE'S REASON TO EXIST AND ALSO ITS LIMIT
────────────────────────────────────────────────────────────────────────────────────────────────
NF-INJ4 measured a real, large mechanism (`desig_x_practice` +0.1408 CRPS over its matched
status-blind foil, 10/10 folds, p = 0.0, PBO 0.000, DSR-CONV 0.9999) and was CONSTRAINT_REFUSED by
ONE pre-registered anchor clause. This registration changes THAT CLAUSE AND NOTHING ELSE: the
field, the folds, the seed, the substrate and every arm are IMPORTED from NF-INJ4's own module
rather than restated, so "unchanged" is a mechanical fact about this file's imports, not a claim.

⇒ **Every number this study will report is ALREADY KNOWN from NF-INJ4's record. Only the gate
flips.** What is bought here is a PROPERLY-REGISTERED RECORD of an already-measured result — not
new evidence, and ⛔ never to be presented as fresh confirmation. A re-run that reproduces a known
number confirms the pipeline, not the hypothesis.

⭐ The one place that is genuinely NEW is the PLAT-CVP2 positive control's VERDICT, because the
control drives the study's own gate function and this registration changes that function. That is
stated as new; nothing else is.

`best_alpha = 0`. **DEPLOY-HELD** — the served Questionable/Doubtful/Out availability discount stays
EXACTLY ZERO until the gated ship path and explicit operator approval.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT THIS MODULE IS
────────────────────────────────────────────────────────────────────────────────────────────────
The registration DELTA and nothing more: the corrected anchor clauses, their tolerance, and the
explicit gate partition. The kernel — admissibility, resolution, spells, arms, the exact discrete
CRPS reducer, the fold builders — is `nf_inj4_designation_duration`, imported UNCHANGED. ⛔ That
module is NOT edited: it is the code NF-INJ4's committed record was produced by, and a record whose
generating code has moved is a record that no longer reproduces (the NF-INJ3b-M provenance rule).
"""
from __future__ import annotations

from quant_sports_intel_models.football.nfl.fantasy import nf_inj4_designation_duration as DD

STORY = "NF-INJ4b"
SUPERSEDES = "NF-INJ4 (anchor clause only; its verdict and record stand unedited — E2.1-r)"

# ══════════════════════════════════════════════════════════════════════════════════════════════
# INHERITED UNCHANGED — imported, never restated
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: ⭐ Field, folds, seed, substrate, metric, BH family, `V`'s membership, the injection and the
#: application constants are NF-INJ4's, by IMPORT. Re-declaring any of them here would create a
#: second place for them to drift, and "the field is unchanged" would become a claim a reader has
#: to check by eye instead of a fact the interpreter enforces.
ARMS = DD.ARMS
SHIPPABLE_ARMS = DD.SHIPPABLE_ARMS
DEGENERATE_ARMS = DD.DEGENERATE_ARMS
NON_SHIPPABLE_BY_REGISTRATION = DD.NON_SHIPPABLE_BY_REGISTRATION
PRIMARY_ARM = DD.PRIMARY_ARM
INCUMBENT_ARM = DD.INCUMBENT_ARM
MATCHED_FOIL = DD.MATCHED_FOIL
DECLARED_FIELD_SIZE = DD.DECLARED_FIELD_SIZE
N_FOLDS, FOLD_UNIT, FOLD_SEED = DD.N_FOLDS, DD.FOLD_UNIT, DD.FOLD_SEED
MAX_PBO, MIN_DSR = DD.MAX_PBO, DD.MIN_DSR
BH_FAMILY_SIZE = DD.BH_FAMILY_SIZE
BH_CUTOFF_BINDING = DD.BH_CUTOFF_BINDING
BH_CUTOFF_CONSERVATIVE = DD.BH_CUTOFF_CONSERVATIVE
PBO_APPLICATION = DD.PBO_APPLICATION
DEGENERATES_EXCLUDED_FROM_V = DD.DEGENERATES_EXCLUDED_FROM_V
INJECTION_EFFECT_GAMES = DD.INJECTION_EFFECT_GAMES
INJECTED_DESIGNATIONS = DD.INJECTED_DESIGNATIONS
SEASON_GAMES = DD.SEASON_GAMES

#: ⛔ **`MIN_CELL_N` IS UNTOUCHED AT 30, AND THE 29-ROW NEAR-MISS IS NOT A REASON.** `doubtful`
#: holds 29 rows, so it can never populate its own in-fold cell and ALWAYS backs off to the pooled
#: distribution — the model treats a Doubtful player as an average injury-report player, which is
#: the backoff doing exactly what it was registered to do. Moving the threshold to 29 because 29 is
#: the number that would unlock it is reverse-engineering a design constant from the answer
#: (MH2.2), and it is restated here as a NON-REASON so a future reader cannot mistake the
#: near-miss for an open question. It is REPORTED, never acted on.
MIN_CELL_N = DD.MIN_CELL_N

# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE REGISTRATION DELTA — the oracle anchor, at MATCHED RESOLUTION
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: ⛔ **WHY THE NAIVE CLAUSE IS RETIRED, AND WHAT REPLACES IT.**
#: NF-INJ4 registered `oracle_respected` as "no arm beats its OWN-FORM oracle" — `arm_crps >=
#: own_form_oracle_crps`. It FAILED on all three shippable arms, and the decomposition NF-INJ4
#: published shows why: the oracle is fitted on a ~131-row TEST FOLD against arms trained on ~1,178
#: rows, a **9.0x resolution ratio fixed by the CV design**, with `MIN_CELL_N = 30` collapsing most
#: of the peek's conditioning to the pooled distribution at that size. So the clause measured **the
#: oracle's sample size**, not any property of an arm (the NF-W7i capacity-starved-ceiling shape).
#:
#: ⭐ NF1.9 (f) is explicit that a peeking oracle is a floor **only at matched n**, and enforces it
#: by gating the ORACLE against a matched-n control of equal family and equal resolution. In THIS
#: design an arm beating its own peeking oracle can only be CAPACITY, never leakage — the arms are
#: fitted strictly on training rows disjoint BY PLAYER (`FOLD_UNIT = gsis_id`), so the leakage the
#: naive clause exists to catch is excluded by the FOLD CONSTRUCTION, not by the anchor.
#: ⚠️ That is a statement about THIS design and does not generalise: in a design where an arm could
#: see its own test rows, the naive clause is the thing that catches it. The naive comparison is
#: therefore still COMPUTED AND REPORTED per arm as a diagnostic (it will read FALSE, exactly as
#: NF-INJ4 measured) — retiring a clause from the gate table is not a reason to stop showing its
#: number.
NAIVE_ORACLE_CLAUSE_RETIRED = (
    "arm_crps >= own_form_oracle_crps — REPORTED as a diagnostic, GATES NOTHING in NF-INJ4b")

#: ⭐⭐ **TWO GUARDS, NAMED SEPARATELY, BECAUSE REGISTERING ONE DOES NOT GIVE YOU THE OTHER.**
#: This is the standing convention NF-INJ4 produced (`plan_specs/plan_spec_process.md`, "Oracle-
#: anchor resolution matching"). The single measured pair (`own_form_oracle` vs `matched_n_control`)
#: answers TWO different questions, and a registration that names only one silently inherits the
#: other's failure mode:
#:
#:   A. `anchor_pair_informative`  — the NF-W6d INACTIVE-PAIR reading. Could the anchor family ACT
#:      at all? A pair whose oracle merely TIES its matched-n control had nothing to act on, and is
#:      UNINFORMATIVE: it is neither a refusal (NF-W6d lost three shippable arms to reading a tie
#:      as "this form has no headroom") nor a pass (NF1.7 (a): a check that could not run is not a
#:      check that ran). The clause fails when NO shippable arm's pair is active — an anchor family
#:      that could not act certified nothing and must not be scored as though it had.
#:
#:   B. `oracle_floor_matched_resolution` — the NF1.9 (f) CAPACITY reading. Given that it could
#:      act, does the floor HOLD at equal family and equal resolution? It fails when an HONEST
#:      matched-n fit BEATS the peeking oracle, which would mean the "oracle" is not a floor at
#:      all — the peek is starved past usefulness, or the anchor is mis-built.
#:
#: ⚠️ B is VACUOUSLY satisfied on an INACTIVE pair, so B's pass count is reported BESIDE A's active
#: count and never on its own (NF-D20: count what the mechanism could act on before crediting "the
#: constraint held N of M").
ANCHOR_CLAUSE_INFORMATIVE = "anchor_pair_informative"
ANCHOR_CLAUSE_FLOOR = "oracle_floor_matched_resolution"

#: The SYMMETRIC tie band separating the three states of the one measured pair:
#:   ACTIVE    `oracle < control - TOL`  the peek genuinely helps at matched n; the floor holds
#:   INACTIVE  `|oracle - control| <= TOL`  the pair could not act; UNINFORMATIVE
#:   VIOLATED  `oracle > control + TOL`  an honest matched-n fit beats the peek; the floor is BREACHED
#: ⭐ 1e-6 is NF-INJ4's own activity tolerance, adopted VERBATIM so the ACTIVE/INACTIVE partition is
#: identical to the one it measured — changing it would move the partition and quietly break the
#: honesty clause's "unchanged" precondition. ⚠️ Whether the tolerance is LOAD-BEARING is a
#: measurement, not an assertion: the per-arm margin `|oracle - control|` is reported so a reader
#: can see how far each pair sits from the band (NF-W7f: an activity classification is not a
#: magnitude, and a share invariant to the level it binds at hides a constraint that stopped
#: mattering).
ANCHOR_TIE_TOL = 1e-6

# ══════════════════════════════════════════════════════════════════════════════════════════════
# Gates — the explicit partition
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: ⭐ EXPLICIT `gate_classes` (PLAT-CVP2 defect 2), as NF-INJ4 declared: the only input that can
#: affirm "there is no deflation gate here", and it must classify EVERY gate the study scores. ⛔ No
#: fallback to the instrument's name heuristic. This is the SECOND registration consuming the
#: explicit declaration, which is the trigger for retiring that heuristic.
#: PM convention: deflation-class = {pbo, cscv, dsr, deflated_sharpe}; `bh_ok` and
#: `fold_consistency` are MULTIPLICITY / STABILITY gates, not deflation-class.
GATE_CLASSES: dict[str, str] = {
    "beats_incumbent": "metric",
    "beats_foil": "metric",
    "fold_consistency": "metric",
    "bh_ok": "metric",
    ANCHOR_CLAUSE_INFORMATIVE: "invariant",
    ANCHOR_CLAUSE_FLOOR: "invariant",
    "beats_permutation": "metric",
    "dsr_ok": "deflation",
    "degenerates_lose": "invariant",
}

#: ⭐ **DECLARED FORWARD as gates the injection structurally CANNOT move** — and this declaration is
#: the one NF-INJ4 said belonged to its successor, made here BEFORE any arm is scored.
#:
#: · `degenerates_lose` — carried over verbatim: planting a stronger designation → duration
#:   relationship cannot make a point mass at 0 or at `games_remaining` win.
#: · BOTH anchor clauses — because each compares TWO ANCHORS (`own_form_oracle` vs
#:   `matched_n_control`) fitted on the SAME injected data by the SAME form at two sample sizes. An
#:   injection that strengthens the designation → duration link strengthens both together; it is a
#:   statement about the PEEK'S CAPACITY, which is a property of the fold sizes and `MIN_CELL_N`,
#:   not of the effect's magnitude. NF-INJ4's ladder MEASURED the naive form FALSE at every rung
#:   (0, 0.5, 1, 2, 4 games) — related evidence, ⚠️ but about a DIFFERENT clause, so it is cited as
#:   corroboration and never as proof of the matched form's invariance.
#:
#: ⭐ **THE DECLARATION IS EXPECTED TO BE INERT FOR THIS VERDICT, and that is said plainly rather
#: than left for a reader to notice.** These clauses are expected to PASS, and a passing gate
#: appears in no blocking set, so the declaration cannot rescue this study from anything. It is
#: registered because it is TRUE and FALSIFIABLE, so that a FUTURE run in which an anchor clause
#: does block is read as `CONSTRAINT_BLOCKED` rather than `BLIND` — and because declaring it now,
#: before the result, is the only moment at which declaring it is honest (E2.1-r).
#: ⛔ It is not asserted: this study runs its own gate ladder and REPORTS whether each declared-
#: invariant clause actually holds still across it. A clause that MOVES refutes this declaration,
#: and that refutation is reported as a defect in THIS registration.
INVARIANT_GATES: tuple[str, ...] = (
    "degenerates_lose", ANCHOR_CLAUSE_INFORMATIVE, ANCHOR_CLAUSE_FLOOR)
DEFLATION_GATES: tuple[str, ...] = tuple(
    g for g, c in GATE_CLASSES.items() if c == "deflation")

#: ⛔ `pbo` is a FIELD-LEVEL statistic and is NOT in the per-arm gate table (unchanged from NF-INJ4).
assert set(INVARIANT_GATES) <= set(GATE_CLASSES), "an invariant gate must be a declared gate"
assert all(GATE_CLASSES[g] == "invariant" for g in INVARIANT_GATES), \
    "a gate named invariant must be CLASSED invariant — a partition that disagrees with itself is " \
    "the PLAT-CVP2 defect-2 ambiguity in one file instead of two"
assert "oracle_respected" not in GATE_CLASSES, \
    "NF-INJ4's naive clause is RETIRED from the gate table; it survives as a reported diagnostic"
