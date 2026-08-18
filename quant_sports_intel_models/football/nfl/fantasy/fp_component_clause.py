"""fp_component_clause.py — NF-W7j: the COMPONENT-CLAUSE decision, as constants.

NF-W7f refused a QB ship on two of its 22 gate clauses and deferred ONE of them to a successor's
forward registration (NF-W7f §11.2 / §12.5b(3)): whether *"components must not degrade"* should be a
HARD GATE at tolerance 0.0 or a REPORTED DIAGNOSTIC. This module is that decision, committed as
constants BEFORE any clause was re-scored; `run_nf_w7j_component_clause.py` READS them (NF-D16) and
adds no threshold of its own.

⚖️ `best_alpha = 0` · DEPLOY-HELD · research-only. Nothing here promotes, publishes or serves.

⭐ THE DECISION (prereg §2) — `per_leg_calibration_not_materially_degraded` REFUSES iff ALL FOUR:

  A. the SERVED-CELL AUDIT passes — the degraded NF-W6d cells reach no serving surface. This is a
     PRECONDITION for relaxing at all, it is re-measured on EVERY invocation, and the clause FAILS
     CLOSED to the raw 0.0 tolerance when it does not hold. A future story that wires the cells into
     a served surface therefore re-arms the hard gate automatically (prereg §1.3).
  B. DEMONSTRABLE — the per-fold priced-leg relative-change series is significantly positive at
     `ALPHA_DEMONSTRABLE`, one-sided paired, through the harness's OWN instrument.
  C. MATERIAL — the point estimate is ≥ `MATERIALITY_FRACTION` of the arm's claimed effect.
  D. the claimed effect is well-defined (a positive assembled delta), else C's ratio is meaningless.

⛔ NO threshold here is derived from NF-W7f's observed +0.3866%. `MATERIALITY_FRACTION` is NF-W7c's
convention, named by NF-W7f §12.5b(3) BEFORE this story existed; `ALPHA_DEMONSTRABLE` is the
conventional 0.05 the harness already applies to `beats_foil`. Reverse-engineering either from the
observed value is the E2.1-r inversion (prereg §0.2).

⚠️ THE DECIDED CLAUSE IS STRICTLY WEAKER than the raw one and cannot catch a degradation this design
is underpowered to demonstrate. Condition A is what pays for that residual risk — which is why the
clause is a CONJUNCTION and why A fails closed. Neither half justifies the relaxation alone.
"""
from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The decided clause's thresholds (prereg §2) — DESIGN quantities, never observed ones
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: NF-W7c's convention, named by NF-W7f §12.5b(3): a component cost is MATERIAL at one tenth of the
#: arm's claimed effect. ⛔ Not derived from NF-W7f's +0.3866%.
MATERIALITY_FRACTION: float = 0.10

#: One-sided paired significance level for the DEMONSTRABLE half — the same 0.05 the harness applies
#: to `beats_foil`. The TEST is `nf1_1_model.onesided_paired_pvalue` BY IDENTITY (prereg §2 row B):
#: reusing the story's own instrument is what stops a new test being chosen to suit the answer.
ALPHA_DEMONSTRABLE: float = 0.05

#: The raw clause NF-W7f registered, retained so both readings are reported every run (NF-D20).
RAW_TOLERANCE: float = 0.0

#: The clause names.
DECIDED_CLAUSE = "per_leg_calibration_not_materially_degraded"
RAW_CLAUSE = "per_leg_calibration_not_degraded"

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The served-cell audit (prereg §1) — the PM's condition, made CHECKABLE and EXPIRING
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: The five entry points that between them PRODUCE and SERVE the paid stat line. An import-closure
#: walk over these is the measurement; ⛔ a grep over one file is not (INC-27).
SERVING_PLANE_SEEDS: tuple[str, ...] = (
    # the exporter that WRITES passYds/passTd/… into the published board
    "quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json",
    # the model that COMPUTES the proj_* columns the exporter reads
    "quant_sports_intel_models.football.nfl.fantasy.season_projection",
    # the whole API surface
    "app.backend.main",
    # the entitled /fantasy/nfl/projections-full + league-board routes
    "app.backend.routers.fantasy",
    # the scoring authority (NF-EPIC 1)
    "quant_sports_intel_models.fantasy_engine.scoring",
)

#: ⭐ THE POSITIVE CONTROL (NF1.7 (a) / INC-38). A closure walker that resolves nothing returns an
#: empty hit set for EVERY seed, so a PASS would be indistinguishable from a broken walker. These two
#: are KNOWN consumers; the audit RAISES rather than passing if either comes back empty.
POSITIVE_CONTROL_SEEDS: tuple[str, ...] = (
    "quant_sports_intel_models.football.nfl.fantasy.run_nf_w7f_qb_marginal",
    "quant_sports_intel_models.football.nfl.fantasy.fp_assembly",
)

#: Any module whose dotted name carries one of these is a per-stat-cell consumer.
FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "stat_distribution_serving", "stat_distributions", "fp_assembly", "fp_qb_marginal",
)

#: ⭐ AMENDED BEFORE ANY VERDICT (prereg §7 SMOKE AMENDMENT) — a HARNESS fix, not a threshold that
#: moves a verdict. The first cut applied a minimum closure SIZE to every serving-plane seed, which
#: `quant_sports_intel_models.fantasy_engine.scoring` legitimately trips: it is a small PURE module
#: whose whole closure is 2. The audit correctly REFUSED to run rather than scoring it clean, which
#: is the floor working — but the floor was aimed at a PROXY. The real vacuity condition is "the
#: walker resolved NOTHING", so it is now asserted directly: every seed must resolve to a real
#: module file, and the SIZE floor applies to the POSITIVE CONTROLS, where a large closure is what
#: makes an empty hit set diagnostic. Strictly better targeted, and it cannot be satisfied by a
#: broken walker.
MIN_CLOSURE_MODULES: int = 5

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The reproduction pin (prereg §3) — the decision must be measured against the object W7f scored
# ══════════════════════════════════════════════════════════════════════════════════════════════

W7F_RECORD = "nf_w7f_qb_marginal.json"
W7F_POSITION = "QB"
W7F_WINNER = "zm_floor"
W7F_MATCHED_FOIL = "mixall_learned"
W7F_N_FOLDS = 8
W7F_DECLARED_FIELD_SIZE = 4  # fp_qb_marginal_calibration.REAL_ARMS, committed in W7f's prereg §3

#: Exact values the decision consumes. A mismatch RAISES (exit 2) rather than deciding about a
#: different object than NF-W7f scored.
#: ⭐ NF-W7f's component figure exists in TWO forms and they are NOT the same statistic — the pin
#: caught this before any clause was evaluated (prereg §3 doing its job). `relative_change` is the
#: POOLED ratio-of-sums `(Σ recal − Σ served) / Σ served` = +0.3866%; the per-fold series is a set of
#: per-fold ratios whose MEAN is +0.3748% (= `relative_change_by_arm[winner]`). They differ by ~3%
#: relative (NF1.8: a ratio of sums is not a mean of per-fold ratios). Both are pinned, both are
#: reported, and the decision states which half uses which: the MAGNITUDE half reads the POOLED
#: figure (NF1.8 — pool, never a mean of means), the SIGNIFICANCE half necessarily reads the
#: per-fold series, because a paired test has no per-fold units otherwise.
W7F_PINS: dict[str, float] = {
    "per_leg_relative_change": 0.003866,
    "per_leg_relative_change_winner_by_fold_mean": 0.003748,
    "per_leg_tolerance": 0.0,
    "mean_delta": 0.0184,
    "ci95_lo": 0.0032,
    "ci95_hi": 0.0336,
    "matched_foil_mean_crps": 2.5829,
}
PIN_TOLERANCE: float = 1e-9

#: The two clauses NF-W7f's gate failed, and the count of clauses it passed. Pinned so a re-scored
#: gate that differs anywhere else is caught rather than absorbed.
W7F_FAILING_CLAUSES: tuple[str, ...] = ("dsr_ok", RAW_CLAUSE)
W7F_N_GATE_CLAUSES: int = 22

# ══════════════════════════════════════════════════════════════════════════════════════════════
# Band states for the materiality read (prereg §2.2) — the NF-W7i lesson
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: ⛔ `UNDECIDED_MAGNITUDE` is NOT `POWER_LIMITED`. A band decision is not a power verdict, and
#: reporting one as the other is the hand-correction NF-W7i had to make to `cv_power`.
BAND_STATES: tuple[str, ...] = ("MEASURED_IMMATERIAL", "MEASURED_MATERIAL", "UNDECIDED_MAGNITUDE")

#: The certification bar (prereg §4) — the FULL gate green, the identical bar NF-W7h pre-registered
#: for RB and the one WR (NF-W7e, DSR 0.9852) and TE (NF-W7c, DSR 0.9822) actually cleared.
#: ⛔ This story does not lower it: a "PIT + component + beats incumbent" reading omits `dsr_ok`, and
#: adopting it after seeing `dsr_ok` fail is the E2.1-r inversion.
CERTIFICATION_REQUIRES_FULL_GATE: bool = True

PROMOTE_BLOCKERS: tuple[str, ...] = (
    "NF-W7j decides ONE clause and audits ONE condition; it re-scores nothing and refits nothing — "
    "NF-W7f's scores stand byte-identical",
    "the component-clause decision CANNOT certify QB on its own: `dsr_ok` is a second, independent "
    "refusal, out of scope here (prereg §0.1)",
    "the served-cell audit licenses the relaxation for the SERVING plane only — the NF-W6/W7 "
    "research line consumes the cells and NF-W8 intends to (prereg §1.3)",
    "NF-W7f's and NF-W7c's promote blockers are inherited in full, including NF-W7c §4's rule that "
    "a per-position-certified distribution may not feed a CROSS-POSITION ranking",
)
