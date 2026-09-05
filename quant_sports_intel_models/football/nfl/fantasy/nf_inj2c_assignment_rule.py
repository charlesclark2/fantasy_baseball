"""nf_inj2c_assignment_rule.py — NF-INJ2c: the STRICT-DOMINANCE registration, as code.

⭐ READ `ablation_results/nf_inj2c_preregistration.md` FIRST, and `nf_inj2c_margin_construction_rule.md`
(node 3a) beside it. 3a is **BINDING** and was committed BEFORE the node-3b re-measure ran; this
module is a TRANSCRIPTION of those two documents into checkable constants, ⛔ never a second place
where a band or a field may be decided. A value here that disagrees with either document is a defect
in this file.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT THIS MODULE IS, AND WHAT IT DELIBERATELY IS NOT
────────────────────────────────────────────────────────────────────────────────────────────────
It is the REGISTRATION: the declared field, the deflation conventions, the six measures with their
tie-band rules, the injection-sensitive/invariant partition, and the folds.

It is **NOT** an assignment kernel. Every arm NF-INJ2c scores already exists in NF-INJ2b's kernel,
so this module DISPATCHES into `nf_inj2b_rate_ordering` and implements no assignment rule of its
own — the NF-W6c drift-proofing shape. A second implementation of `stratified` would be two code
paths for one certified mechanism (NF-C0e "wired != invoked", and the E9.61 two-renderers class);
`assert_coherent()` proves the dispatch rather than trusting this paragraph.

It is **NOT** a serving-policy owner. `nf_inj2b_rate_ordering.resolve_served_arm()` is THE SINGLE
AUTHORITY and this module deliberately defines no `SERVED_ARM` — a third owner for one logical thing
is exactly the INC-30 / INC-36 / INC-38 class, and `assert_coherent()` refuses one appearing here.

────────────────────────────────────────────────────────────────────────────────────────────────
THE FIELD, AND WHY IT IS FIVE ARMS
────────────────────────────────────────────────────────────────────────────────────────────────
PM ruling 2026-09-01, transcribed: the deflation gates' BINDING field is this story's own coherent
family, declared on MECHANISM before any deflation statistic was computed — point-space assignment
rules only. The four rate-space arms are excluded as a DIFFERENT MECHANISM already refused on the
ordering gate (NF-INJ2's `CONSTRAINT_REFUSED`, which stands and is ⛔ not re-read); carrying a refused
mechanism's arms in `V` would tax this contest for a search it is not running — the MH2.5 /
NF-W6b-C V-inflation class.

⚠️ THREE CONSEQUENCES, declared in the pre-registration §2.3 and repeated here because each is
knowable before a single arm is scored and none may be discovered afterwards:

  (a) `V` HAS EXACTLY TWO MEMBERS — a 1-df variance estimate, itself a high-variance quantity. It
      can land small (a generous bar) or large (a punishing one) for reasons that are noise. That is
      a REAL fragility of the declared design. ⛔ It is not a licence to change the field later.
  (b) THE FIELD-TRIM READING IS INADMISSIBLE BY CONSTRUCTION (NF-W7h). With two contributors, the
      "drop `V`'s largest contributor" diagnostic can only delete the arm under test (inadmissible
      outright) or leave `V` undefined at one point. A refusal is stated A FORTIORI on the design,
      ⛔ never as a trimmed number.
  (c) DSR-CONV'S EXCLUSION IS NON-MONOTONE, SO IT IS NOT A LEVER. Dropping a far-out designed loser
      lowers the bar; dropping one near the field mean WIDENS `V` and raises it. Both figures are
      computed and published — degenerate-excluded (BINDING) and degenerate-included (sensitivity).
      This is the same field under two conventions the program already owns, ⛔ not a third field.
"""
from __future__ import annotations

from typing import Mapping

from quant_sports_intel_models.football.nfl.fantasy import nf_inj2b_rate_ordering as B

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered field (nf_inj2c_preregistration.md §2.2) — DECLARED FORWARD
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: H1's arm: the assignment rule in POINT space. ⛔ Not "the CRPS winner" — this story's disposition
#: is STRICT DOMINANCE of a NAMED arm against the served incumbent, so the arm under test is fixed
#: by the registration and cannot be chosen once the scores are visible (E2.1-r).
PRIMARY_ARM = "stratified"

INCUMBENT_ARM = B.INCUMBENT_ARM

#: pre-registered DEGENERATES — they MUST lose. ∈ `n_trials`, ∉ `V` (DSR-CONV, opted into here,
#: FORWARD). ⛔ Declaring an arm degenerate after seeing it lose is laundering.
DEGENERATE_ARMS: tuple[str, ...] = ("mvp1_null", "random_order")

#: the REFERENCE arm, whose lift series is identically ZERO by construction. ∈ `n_trials`, ∉ `V`
#: (MH2.1 (a)): a structural 0.0 inflates a small family's cross-trial dispersion exactly as a
#: diagnostic anchor does.
REFERENCE_ARMS: tuple[str, ...] = (INCUMBENT_ARM,)

#: the five declared arms — the BINDING field for every deflation gate.
ARMS: tuple[str, ...] = (
    "incumbent",           # point-by-score              — REFERENCE, today's served board, the bar
    "stratified",          # point-within-strata         — PRIMARY, H1
    "feasibility_clamp",   # point-by-score, clamped     — the point-space alternative, by name
    "mvp1_null",           # no re-order at all          — DEGENERATE, must LOSE
    "random_order",        # seeded within-position perm — DEGENERATE, must LOSE
)
DECLARED_FIELD_SIZE = len(ARMS)

#: the rate-space arms, EXCLUDED. ⛔ Out because they belong to a different mechanism whose refusal
#: stands — NOT because of anything they scored. Enumerated so the exclusion is auditable against
#: NF-INJ2b's field rather than asserted.
EXCLUDED_RATE_SPACE_ARMS: tuple[str, ...] = (
    "points_rate_permute", "rate_refit", "points_rate_stratified",
    "rate_refit_stratified", "rate_refit_reselect",
)

#: the inherited NF-INJ2b 10-arm field, whose DSR is ALSO computed and published beside the binding
#: figure as a NON-BINDING DIAGNOSTIC (NF-D14's two-sided rule), declared as such IN ADVANCE. It
#: publishes whichever way it comes out, ⛔ cannot rescue a binding refusal, and no disposition reads
#: it. ⛔ No third field is ever computed.
DIAGNOSTIC_FIELD: tuple[str, ...] = tuple(B.ARMS)
DIAGNOSTIC_LABEL = "NON-BINDING DIAGNOSTIC (inherited NF-INJ2b 10-arm field)"

# ══════════════════════════════════════════════════════════════════════════════════════════════
# Folds and metric (pre-registration §3)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: SEVEN folds, INHERITED from NF1.5's own `score_from` at the shipped `base_from` — ⭐ the window's
#: authority is that it was inherited, not chosen. Re-cutting it is refused (PM ruling 2026-09-01);
#: node 3c settled 2018 as not data-honest on three independent legs.
FOLDS: tuple[int, ...] = (2019, 2020, 2021, 2022, 2023, 2024, 2025)
BASE_FROM = 2017

#: the 8th fold is CALENDAR-BOUND (the realized 2026 season) and publishable as a re-test trigger —
#: ⚠️ but ONLY when `SR > SR0`. Under `DSR_UNREACHABLE`, `n` enters through `√(n−1)` and can scale a
#: positive gap but never create one (NF-W8-0d), so the trigger is WITHHELD with that reason stated
#: rather than published — publishing it would be the NF-D18 misleading direction.
CALENDAR_BOUND_NEXT_FOLD = 2026

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The six measures and their TIE BANDS (node 3a §1–§2 — BINDING, transcribed)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: 3a §1: every band is one of exactly three things, and ⛔ no band may be derived from an observed
#: arm-vs-incumbent gap.
BAND_RULES: Mapping[str, str] = {
    "R1": "an estimator's own STANDARD ERROR — the per-fold SE of that measure's own series",
    "R2": "the measurement's RECORDED PRECISION — a board-level figure has no sampling to average",
    "R3": "an EXISTING pre-registered gate, reused VERBATIM at the same bar",
}

#: (measure, better-is, band rule, where it is measured). ⭐ `where` is load-bearing: M2/M3/M4 are
#: BOARD measures taken on the node-3b capture and are READ from that report, ⛔ never recomputed
#: here — a second computation of a committed baseline is a second answer to one question.
MEASURES: Mapping[str, Mapping[str, str]] = {
    "M1": {"what": "CRPS mean lift vs incumbent over the registered folds",
           "better": "higher", "band": "R1", "where": "folds"},
    "M2": {"what": "coherence violating players per fold (attribution-controlled)",
           "better": "lower", "band": "R1", "where": "board"},
    "M3": {"what": "worst breach as a multiple of the envelope (max times_over)",
           "better": "lower", "band": "R2", "where": "board"},
    "M4": {"what": "injury give-back as max(give_back_pct, 0)",
           "better": "lower", "band": "R2", "where": "board"},
    "M5": {"what": "draftable-tier Spearman rho, per position",
           "better": "higher", "band": "R3", "where": "folds"},
    "M6": {"what": "per-group interval coverage against its NF-D22 power floor",
           "better": "clears", "band": "R3", "where": "folds"},
}

#: 3a §2 recorded precision, used as the R2 band. ⛔ These are the precisions the quantities are
#: RECORDED at, read off node 3b's report format — not tolerances chosen to reach a verdict.
M3_RECORDED_PRECISION = 0.01      # `times_over`
M4_RECORDED_PRECISION = 0.01      # `giveback_pct`, in percentage points

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The injected-effect positive control's partition (pre-registration §7) — DECLARED FORWARD
# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ NF-INJ2b's control returned `BLIND` and that badge was WRONG AS A READING: arms were stopped
# under injection by a gate an injected CRPS effect CANNOT MOVE. PLAT-CVP2 (the `CONSTRAINT_BLOCKED`
# instrument fix) has not landed, so the 2b annotation pattern is carried and the partition is
# declared HERE, before the control runs.
#
# The control is evaluated over the INJECTION-SENSITIVE half ONLY, and `blocking_gates` is read
# against this table. If `BLIND` fires and every blocker is on the invariant side, the honest
# statement is: the family's statistical half demonstrably fires; the verdict was decided by measures
# no injection can reach — ⛔ neither a rescue nor a condemnation. ⛔ The control is NEVER re-run with
# a constraint removed to obtain a nicer badge (E2.1-r).
INJECTION_SENSITIVE_GATES: tuple[str, ...] = (
    "m1_crps_lift", "m5_tier_rho", "fold_consistency", "dsr", "bh_fdr",
)
INJECTION_INVARIANT_GATES: tuple[str, ...] = (
    "m2_coherence", "m3_worst_times_over", "m4_giveback", "m6_interval_floor",
)

#: ⭐ THE SAME PARTITION, in `cv_power`'s own vocabulary, so the control is DRIVEN by the declared
#: table rather than by the instrument's NAME HEURISTIC over its default vocabulary — which, in the
#: instrument's own words, is "a fact about this repo's harness names, not about what your clauses
#: measure". It must classify EVERY gate the study scores.
#:
#: ⚠️ THE PRE-REGISTRATION §7's PREMISE IS MEASURED FALSE AT THIS COMMIT, and that is recorded here
#: rather than quietly worked around. §7 states PLAT-CVP2 "has not landed: verified at this commit,
#: `cv_power` exposes no `CONSTRAINT_BLOCKED` verdict and no injection-invariant-gate parameter."
#: It now exposes BOTH (`gate_classes=` / `invariant_gates=`, and `CONSTRAINT_BLOCKED` as a
#: verdict). §7's TEXT stays VERBATIM AND UNEDITED in the pre-registration — a premise a later
#: measurement refutes is itself part of the record (NF-W7f) — and the decisive run reports the
#: refutation under a SUPERSEDED marker.
#:
#: ⛔ Using the parameter is NOT a relaxation: §7's annotation pattern was a WORKAROUND for a
#: missing parameter, and the partition it declares is unchanged. The instrument is explicit that
#: `invariant_gates` "is DECLARED FORWARD by the registration, which is what keeps it from
#: laundering: a gate cannot be reclassified as injection-invariant after seeing that it blocked" —
#: this table was declared before the control ran, which is precisely that condition.
#:
#: `fold_consistency` is METRIC, ⛔ not deflation: the program convention (CLAUDE.md) is
#: deflation-class = {pbo, cscv, dsr, deflated_sharpe}, with `bh_fdr` and `fold_consistency` as
#: MULTIPLICITY / STABILITY gates. Mis-filing one silently converts a `DEFLATION_BLOCKED` reading
#: into a `BLIND` one, which mean opposite things.
GATE_CLASSES: Mapping[str, str] = {
    "m1_crps_lift": "metric",
    "m5_tier_rho": "metric",
    "fold_consistency": "metric",
    "dsr": "deflation",
    "m2_coherence": "invariant",
    "m3_worst_times_over": "invariant",
    "m4_giveback": "invariant",
    "m6_interval_floor": "invariant",
}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The §0.5 outcome — pinned to the committed report, ⛔ never maintained by hand
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: One of "UNRUN" | "DOMINATES" | "NULL" | "VOID" | "DEFLATION_REFUSED". A guard fails if this and
#: `ablation_results/nf_inj2c_decisive.json`'s verdict disagree, so a re-run that changes the verdict
#: must change this in the SAME commit (NF-INJ2's module shipped "UNRUN" after its decisive run had
#: landed and been refused — the policy module claimed the study had never run).
GATE_STATUS = "UNRUN"

#: whether a PM has recorded a disposition to serve a non-incumbent arm. Kept SEPARATE from
#: `GATE_STATUS`: clearing the gates and deciding to ship are different facts (NF-D21/NF-D22 were
#: both burned by a record that collapsed them into one flag).
PM_DISPOSITION_RECORDED = False


def resolve_served_arm() -> str:
    """⛔ NOT AN OWNER — delegates to NF-INJ2b, THE SINGLE AUTHORITY.

    Present so a caller reaching for NF-INJ2c's policy gets the one true answer instead of writing
    its own; `assert_coherent()` proves this module declares no `SERVED_ARM` of its own."""
    return B.resolve_served_arm()


def assert_coherent() -> None:
    """Refuse a registration state the documents do not support. Runs at IMPORT.

    ⛔ Every clause below is a claim the pre-registration or node 3a MAKES; this proves it rather
    than trusting the prose above it."""
    # ── the field is a SUBSET of NF-INJ2b's, so every arm routes to an existing kernel ──────────
    unknown = [a for a in ARMS if a not in B.ARMS]
    if unknown:
        raise RuntimeError(
            f"NF-INJ2c declares arm(s) {unknown!r} that NF-INJ2b's kernel does not implement — this "
            "module DISPATCHES and must never define an assignment rule of its own (NF-W6c)")
    if DECLARED_FIELD_SIZE != len(set(ARMS)):
        raise RuntimeError("the declared field contains a duplicate arm")
    if PRIMARY_ARM not in ARMS:
        raise RuntimeError(f"the PRIMARY arm {PRIMARY_ARM!r} is not in the declared field")
    if PRIMARY_ARM in DEGENERATE_ARMS or PRIMARY_ARM in REFERENCE_ARMS:
        raise RuntimeError(f"the PRIMARY arm {PRIMARY_ARM!r} cannot also be a degenerate/reference")
    for name, group in (("degenerate", DEGENERATE_ARMS), ("reference", REFERENCE_ARMS)):
        missing = [a for a in group if a not in ARMS]
        if missing:
            raise RuntimeError(f"{name} arm(s) {missing!r} are not in the declared field")
    if set(DEGENERATE_ARMS) & set(REFERENCE_ARMS):
        raise RuntimeError("an arm cannot be both a degenerate and the reference")

    # ── ⭐ `V` must have EXACTLY the two members §2.3(a) says it has. If this ever stops being 2,
    #    the pre-registration's declared fragility no longer describes the design being run.
    v_members = [a for a in ARMS if a not in set(DEGENERATE_ARMS) | set(REFERENCE_ARMS)]
    if len(v_members) != 2:
        raise RuntimeError(
            f"`V` would have {len(v_members)} member(s) {v_members!r}, but the pre-registration §2.3(a) "
            "declares exactly two and reasons about a 1-df variance estimate on that basis")

    # ── the exclusion is EXACTLY the rate-space mechanism: nothing quietly dropped, nothing kept ──
    accounted = set(ARMS) | set(EXCLUDED_RATE_SPACE_ARMS)
    if accounted != set(B.ARMS):
        raise RuntimeError(
            "the declared field plus the declared exclusions must account for EVERY arm of the "
            f"inherited field exactly once — unaccounted {sorted(set(B.ARMS) - accounted)!r}, "
            f"invented {sorted(accounted - set(B.ARMS))!r}")
    if set(EXCLUDED_RATE_SPACE_ARMS) & set(ARMS):
        raise RuntimeError("an arm cannot be both declared and excluded")

    # ── the diagnostic field is the INHERITED one, not a third field (§2.4) ─────────────────────
    if tuple(DIAGNOSTIC_FIELD) != tuple(B.ARMS):
        raise RuntimeError(
            "the NON-BINDING DIAGNOSTIC field must be the inherited NF-INJ2b field verbatim — the "
            "PM's ruling permits exactly two fields and forbids a third")

    # ── the control's partition covers the gate set once each (§7) ─────────────────────────────
    overlap = set(INJECTION_SENSITIVE_GATES) & set(INJECTION_INVARIANT_GATES)
    if overlap:
        raise RuntimeError(f"gate(s) {sorted(overlap)!r} are declared BOTH injection-sensitive and "
                           "invariant — the control would then be read against an ambiguous table")
    if not INJECTION_SENSITIVE_GATES:
        raise RuntimeError("the injection-SENSITIVE half is empty — the control would be evaluated "
                           "over nothing, which is a vacuous pass (NF1.7 (a))")
    # ── the instrument-vocabulary table is the SAME partition, and covers it exactly ────────────
    if set(GATE_CLASSES) != set(INJECTION_SENSITIVE_GATES) | set(INJECTION_INVARIANT_GATES) - {
            "bh_fdr"}:
        declared = set(INJECTION_SENSITIVE_GATES) | set(INJECTION_INVARIANT_GATES)
        missing = sorted(declared - set(GATE_CLASSES) - {"bh_fdr"})
        extra = sorted(set(GATE_CLASSES) - declared)
        if missing or extra:
            raise RuntimeError(
                f"GATE_CLASSES and the sensitive/invariant halves disagree — missing {missing!r}, "
                f"extra {extra!r}. They are ONE partition in two vocabularies; a disagreement means "
                "the control is driven by a different table than the one the record cites.")
    for g, k in GATE_CLASSES.items():
        if k not in ("metric", "deflation", "invariant"):
            raise RuntimeError(f"gate {g!r} is classed {k!r}, which `cv_power` does not accept")
        want = "invariant" if g in INJECTION_INVARIANT_GATES else None
        if want and k != want:
            raise RuntimeError(
                f"gate {g!r} is declared INJECTION-INVARIANT but classed {k!r} — the two tables "
                "must not be able to disagree about one gate")
    if GATE_CLASSES.get("fold_consistency") == "deflation":
        raise RuntimeError(
            "`fold_consistency` is a MULTIPLICITY/STABILITY gate, ⛔ not deflation-class (CLAUDE.md "
            "program convention) — mis-filing it converts a DEFLATION_BLOCKED reading into a BLIND "
            "one, and those mean opposite things")

    # ── the measures transcribe 3a §2 completely ───────────────────────────────────────────────
    if tuple(MEASURES) != ("M1", "M2", "M3", "M4", "M5", "M6"):
        raise RuntimeError("the measure table must carry exactly M1..M6, in order (node 3a §2)")
    for m, spec in MEASURES.items():
        if spec["band"] not in BAND_RULES:
            raise RuntimeError(f"{m} cites band rule {spec['band']!r}, which node 3a §1 does not "
                               "define — a measure with no admissible band is DISCLOSED-ONLY")
        if spec["where"] not in ("folds", "board"):
            raise RuntimeError(f"{m} must say whether it is measured over FOLDS or on the BOARD")

    # ── ⛔ NOT a serving-policy owner ───────────────────────────────────────────────────────────
    if "SERVED_ARM" in globals():
        raise RuntimeError(
            "NF-INJ2c must NOT declare a SERVED_ARM — `nf_inj2b_rate_ordering.resolve_served_arm()` "
            "is the single authority, and a third owner for one logical thing is the INC-30 / "
            "INC-36 / INC-38 class this repo keeps paying for")
    served = resolve_served_arm()
    if served in DEGENERATE_ARMS:
        raise RuntimeError(f"served arm {served!r} is a pre-registered DEGENERATE — it exists to LOSE")
    if served != INCUMBENT_ARM and GATE_STATUS != "DOMINATES":
        raise RuntimeError(
            f"a non-incumbent arm {served!r} is served while NF-INJ2c's GATE_STATUS={GATE_STATUS!r}")
    if served != INCUMBENT_ARM and not PM_DISPOSITION_RECORDED:
        raise RuntimeError(
            f"a non-incumbent arm {served!r} is served with no PM disposition recorded — clearing "
            "the gates and deciding to ship are different facts")


assert_coherent()
