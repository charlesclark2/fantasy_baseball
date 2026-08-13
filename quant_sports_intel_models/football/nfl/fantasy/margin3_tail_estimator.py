"""margin3_tail_estimator.py — NF-MARGIN3: a better QB/WR tail-magnitude estimator vs
`tail_ext` (pure).

THE STORY IN ONE PARAGRAPH. NF-MARGIN2 proved the tail channel is real and statistically clean
at all four positions and SHIPPED `tail_ext` (exponential mean-excess tails) at RB/TE — but QB/WR
were CONSTRAINT_REFUSED by the anchors, not the statistics: `over_ext` (the arm's own betas × 3,
registered to lose) beat the QB arm by 0.0002, and `permuted_tail` (misalignment-inflated betas)
edged the arm at QB/WR (p 0.0488/0.0241). One finding in two costumes: the CRPS/pinball-optimal
tail magnitude lies BEYOND the exponential mean-excess MLE there — the estimator under-extends.
⛔ Not a sample-size problem; more folds cannot fix a magnitude estimator. NF-MARGIN3 is the
pre-registered successor: a single fresh arm (`eq_tail`) whose per-side offsets ESTIMATE THE
REFUTED QUANTITY DIRECTLY, priced against `tail_ext` — the standing object at every position,
⛔ NOT against the flat-tail incumbent (that contest is already won).

THE ARM, AND WHY THIS ESTIMATOR. `eq_tail` = per-position, per-side EMPIRICAL-QUANTILE tail
offsets calibrated on the eval-end exceedance rates of the purged calibration slice. For each
beyond-grid eval level u the offset is the empirical u-quantile of D = y − q975 (hi side; the
mirror below), clamped at 0 — which is EXACTLY the pooled pinball (= per-level CRPS-term)
optimizer for the shared-offset family: the pinball optimum at level u for x = q975(row) + t is
the t at which P̂(y > q975 + t) = 1 − u. So the estimator targets the metric optimum that
`over_ext`/`permuted_tail` proved the mean-excess proxy under-estimates, with no distributional
form to mis-specify. ⭐ WHY NOT GPD (the named alternative, recorded so nobody re-litigates):
(a) a GPD MLE is still a FORM fit — a likelihood proxy for the metric optimum, the exact bias
class the anchors refused (the CRPS optimum of a mis-specified family ≠ its MLE); (b) ξ at the
~40–80 exceedances a (fold, position, side) cell carries is unstable; (c) the eval grid ends at
0.995, so it only probes the exceedance law to conditional level ~0.9 — where nonparametric
quantiles are well-posed; the extrapolation a parametric tail buys is beyond the grid, which the
metric cannot see. The estimator is TWO-SIDED BY DECLARATION relative to the exponential (it may
extend LESS where the exponential over-extends — WR's low side is already slightly past nominal)
with a hard floor at the flat clamp (offsets ≥ 0: it can never touch within-grid columns).

⭐ THE BAR IS `tail_ext`, NOT THE INCUMBENT: `tail_ext` shipped at RB/TE, so it is the standing
object at every position. The foil is `tail_ext`; the incumbent is a REFERENCE only (the
within-grid identity base, tail-mass continuity, and the cross-story reproduction anchors).
FAMILY = QB + WR only (the two refused positions). RB/TE are computed and REPORTED but are
registered NON-SHIPPABLE in this story — `tail_ext` stands there; a win at RB/TE is an
out-of-family observation for a future registration, never a ship (NF-D20 decision-shape:
eligibility, not a threshold, separates that null from a ship).

⚠️ THE INSTRUMENT (inherited from NF-MARGIN2, NF-D20 (g⁗)): within-grid columns are
byte-identical to the incumbent's for every tail-family construction (asserted at runtime), so
Winkler-80 / coverage(50/80/95) are structurally INACTIVE facts, and the tail-mass gate reads the
beyond-EVAL-grid ends via `randomized_pit_levels`. ⭐ ARM-MOVABILITY of the gate statistic was
proved at design time (guard-tested): `eq_tail` places the beyond-grid eval columns at different
x than `tail_ext` whenever the exceedance law is not exactly exponential-at-assumed-mass, so
P(u < 0.005) + P(u > 0.995) moves — the gate compares the arm's deviation against THE FOIL's,
and a statistic the arm could not move would be décor, not a gate.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: this module promotes nothing and serves
nothing; a clearing arm's serving path (attach the QB/WR offsets to the served quantile bank —
serving-side, no refit — completing the tail fix at all four positions) is blocked on NF-C6 Ph2
+ NF-G0.

Pure module — no lake IO. The runner is `run_nf_margin3_tail_estimator.py`; the narrative
pre-registration is `ablation_results/nf_margin3_preregistration.md`, committed BEFORE the run.
"""
from __future__ import annotations

import numpy as np

from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import margin2_tail_extension as M2
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
STORY = "NF-MARGIN3"
PRIMARY_METRIC = MC.PRIMARY_METRIC          # crps_q199 — MARGIN1's declared reason verbatim
EVAL_LEVELS = MC.EVAL_LEVELS
IDX_Q39 = MC.IDX_Q39
_SEED = 20260815  # fresh (MARGIN1 20260812, MARGIN2 20260813); the primary metric is
#                   deterministic — the seed touches only PIT randomization + the permutation.

#: ONE real arm — the pre-registered successor magnitude estimator.
REAL_ARMS: tuple[str, ...] = ("eq_tail",)
#: ONE foil — ⭐ `tail_ext`, the standing object (shipped at RB/TE), NOT the incumbent.
FOILS: tuple[str, ...] = ("tail_ext",)
#: Reference constructions (report-only, never in the field): the incumbent is the within-grid
#: identity base + the cross-story reproduction anchor; it is NOT a foil — that contest is won.
REFERENCE: tuple[str, ...] = ("incumbent",)
#: Anchors (excluded from the DSR trial field — automatic at a 1-arm family, MH2.1 (a)):
#:   `zero_width`/`max_width` — the two-sided sharpness degenerates (NF1.7 (c));
#:   `over_ext_eq`  — the arm's offsets × OVER_SCALE, the MAGNITUDE degenerate registered to
#:                    LOSE (NF-D20). The arm's offsets sit at the calibration pinball optimum,
#:                    so ×3 must overshoot OOS; if it wins anyway, the calibrated-optimum
#:                    hypothesis itself is refuted — decomposed, never re-labelled;
#:   `permuted_eq`  — offsets fit on within-(position, week) permuted outcomes. In NF-MARGIN2
#:                    the inflated permuted betas accidentally compensated for under-extension;
#:                    a calibrated arm removes that headroom, so the permuted anchor is expected
#:                    to tie-or-lose. Gate clause: it must not significantly BEAT the arm;
#:   `pooled_eq`    — offsets fit position-POOLED (prices per-position conditioning in the
#:                    tail; report-only, informs the serving object).
BASE_ANCHORS: tuple[str, ...] = ("zero_width", "max_width", "over_ext_eq", "permuted_eq",
                                 "pooled_eq")
#: Same magnitude-degenerate scale as NF-MARGIN2 (comparability of the refutation probe).
OVER_SCALE = M2.OVER_SCALE

TEST_BLOCKS = MC.TEST_BLOCKS                # the NF-W1 axis, verbatim
PURGE_WEEKS = MC.PURGE_WEEKS
DSR_MIN, FDR_Q = MC.DSR_MIN, MC.FDR_Q
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = MC.COVERAGE_FLOOR, MC.COVERAGE_BLOCK_SE
POSITIONS = MC.POSITIONS
MIN_TAIL_N = MC.MIN_TAIL_N

#: ⭐ The registered family = the two positions NF-MARGIN2 refused. RB/TE run and are REPORTED
#: (continuity + the pooled-vs-per-position serving question) but are NON-SHIPPABLE by
#: registration — `tail_ext` stands there regardless of how `eq_tail` scores (NF-D20
#: decision-shape: an arm registered non-shippable separates its null from a ship by
#: ELIGIBILITY, not by any threshold; re-classifying post hoc is the E2.1-r inversion).
LIVE_POSITIONS: tuple[str, ...] = ("QB", "WR")
REPORT_ONLY_POSITIONS: tuple[str, ...] = tuple(p for p in POSITIONS
                                               if p not in LIVE_POSITIONS)
#: ONE pre-registered BH family over the LIVE positions. RB/TE contribute no hypotheses.
FDR_FAMILY: tuple[str, ...] = tuple(f"margin3_tail_{p}" for p in LIVE_POSITIONS)

#: The beyond-grid eval levels each side's offsets are calibrated at (4/side — the only eval
#: columns a tail-only construction can move; everything else is byte-identity).
HI_MASK: np.ndarray = EVAL_LEVELS > WP.Q_LEVELS[-1]
LO_MASK: np.ndarray = EVAL_LEVELS < WP.Q_LEVELS[0]
HI_LEVELS: np.ndarray = EVAL_LEVELS[HI_MASK]
LO_LEVELS: np.ndarray = EVAL_LEVELS[LO_MASK]

NOMINAL_TAIL = M2.NOMINAL_TAIL              # 0.025/side — ARM-INVARIANT diagnostic, never gated
NOMINAL_EXTREME = M2.NOMINAL_EXTREME        # 0.005/side — the gate statistic's nominal
WITHIN_GRID = M2.WITHIN_GRID

oracle_of = GE.oracle_of
matched_n_of = GE.matched_n_of
form_of = MC.form_of
pbo_is_evaluable = GE.pbo_is_evaluable
classify_layer_b = GE.classify_layer_b

# Shared machinery — IMPORTED, never re-typed (NF-W2d discipline).
direction_word = GE.direction_word
verdict_sentence = GE.verdict_sentence
paired_ci95 = GE.paired_ci95
calibration_split = MC.calibration_split
permute_within_pos_week = MC.permute_within_pos_week
score_bank = MC.score_bank
pit_stats_m2 = M2.pit_stats_m2
pool_pit_stats_m2 = M2.pool_pit_stats_m2
randomized_pit_levels = M2.randomized_pit_levels
tail_mass_deviation = M2.tail_mass_deviation
permuted_not_significantly_better = M2.permuted_not_significantly_better
assert_within_grid_identity = M2.assert_within_grid_identity
team_total_check = MC.team_total_check
pool_team_total = MC.pool_team_total
TEAM_TOTAL_SAMPLES = MC.TEAM_TOTAL_SAMPLES
MIN_TEAM_K = MC.MIN_TEAM_K


def anchors() -> tuple[str, ...]:
    return (*BASE_ANCHORS, oracle_of("eq_tail"), matched_n_of("eq_tail"))


def all_labels() -> tuple[str, ...]:
    return (*REAL_ARMS, *FOILS, *REFERENCE, *anchors())


def eligible_labels() -> list[str]:
    """The declared field — the arm and THE FOIL `tail_ext`, nothing else. ⛔ The incumbent is
    NOT eligible: the story's bar is the standing object, and a field padded with an
    already-beaten reference would re-import the NF-MARGIN1 field-composition tax."""
    return [*REAL_ARMS, *FOILS]


# ── The estimator ───────────────────────────────────────────────────────────────────────────────
def fit_eq_tail(q39_sorted: np.ndarray, y: np.ndarray) -> dict:
    """Per-side empirical-quantile tail offsets, calibrated on the eval-end exceedance rates.

    Hi side: t_hi(u) = max(0, Q̂_D(u)) with D = y − q975(row) over ALL rows — the pooled pinball
    optimum for the shared-offset family at level u (P̂(y > q975 + t) = 1 − u at the optimum).
    Lo side mirrored: t_lo(u) = max(0, Q̂_{q025 − y}(1 − u)); x(u) = q025 − t_lo(u).

    A side with < MIN_TAIL_N exceedances collapses loudly to the clamp (offsets 0, `thin_*`
    counted — the NF-MARGIN2 convention verbatim). A level whose raw quantile is ≤ 0 (the end is
    already calibrated at that level, or the empirical beyond-mass is thinner than 1 − u) clamps
    to 0 and is COUNTED in `clamped_*` — the arm degrades to the flat incumbent there, never
    silently (NF1.7 (a))."""
    q = np.asarray(q39_sorted, dtype=float)
    yv = np.asarray(y, dtype=float)
    d_hi = yv - q[:, -1]
    d_lo = q[:, 0] - yv
    n_hi, n_lo = int((d_hi > 0).sum()), int((d_lo > 0).sum())
    thin_hi, thin_lo = n_hi < MIN_TAIL_N, n_lo < MIN_TAIL_N
    if thin_hi:
        t_hi = np.zeros(len(HI_LEVELS))
        clamped_hi = len(HI_LEVELS)
    else:
        raw = np.quantile(d_hi, HI_LEVELS)
        clamped_hi = int((raw <= 0).sum())
        t_hi = np.maximum.accumulate(np.maximum(raw, 0.0))
    if thin_lo:
        t_lo = np.zeros(len(LO_LEVELS))
        clamped_lo = len(LO_LEVELS)
    else:
        raw = np.quantile(d_lo, 1.0 - LO_LEVELS)
        clamped_lo = int((raw <= 0).sum())
        # LO_LEVELS ascend (.005→.02) ⇒ offsets must be NONINCREASING in u
        t_lo = np.minimum.accumulate(np.maximum(raw, 0.0))
    return {"t_hi": t_hi, "t_lo": t_lo, "n_hi": n_hi, "n_lo": n_lo,
            "m_hi": float(n_hi / max(len(yv), 1)), "m_lo": float(n_lo / max(len(yv), 1)),
            "thin_hi": bool(thin_hi), "thin_lo": bool(thin_lo),
            "clamped_hi": clamped_hi, "clamped_lo": clamped_lo}


def scale_eq(params: dict, scale: float = OVER_SCALE) -> dict:
    """The magnitude degenerate's parameters: the arm's own offsets, scaled. Zero (clamped or
    thin) offsets stay zero — the degenerate cannot invent a tail the fit refused."""
    out = dict(params)
    out["t_hi"] = np.asarray(params["t_hi"], dtype=float) * float(scale)
    out["t_lo"] = np.asarray(params["t_lo"], dtype=float) * float(scale)
    return out


_EQ_FAMILY: tuple[str, ...] = ("eq_tail", "permuted_eq", "pooled_eq")


def apply_eq_tail(q39_sorted: np.ndarray, params: dict) -> np.ndarray:
    """The (n, 199) bank: identity map within the grid, per-side shared offsets beyond it.
    Refuses negative or non-monotone offsets — a crossing predictive is a harness bug."""
    t_hi = np.asarray(params["t_hi"], dtype=float)
    t_lo = np.asarray(params["t_lo"], dtype=float)
    if len(t_hi) != int(HI_MASK.sum()) or len(t_lo) != int(LO_MASK.sum()):
        raise ValueError("eq_tail offsets do not match the beyond-grid eval levels")
    if (t_hi < 0).any() or (t_lo < 0).any():
        raise ValueError("eq_tail offsets must be ≥ 0 — the arm may never touch within-grid "
                         "columns (the tail-only pre-registration)")
    if (np.diff(t_hi) < 0).any() or (np.diff(t_lo) > 0).any():
        raise ValueError("eq_tail offsets are not monotone — refusing to build a crossing "
                         "predictive")
    q = np.asarray(q39_sorted, dtype=float)
    out = MC.apply_level_map(q, EVAL_LEVELS)
    out[:, HI_MASK] = q[:, -1][:, None] + t_hi[None, :]
    out[:, LO_MASK] = q[:, 0][:, None] - t_lo[None, :]
    return out


def build_bank_m3(label: str, params, q39_sorted: np.ndarray) -> np.ndarray:
    """The evaluation bank for one construction. `incumbent`/`zero_width`/`max_width` and the
    foil `tail_ext` DELEGATE to the NF-MARGIN2 builder — the foil is byte-identical to the
    construction NF-MARGIN2 scored (the reproduction anchor is earned by construction, not by
    tolerance)."""
    form = form_of(label)
    if form in ("incumbent", "zero_width", "max_width", "tail_ext"):
        return M2.build_bank_m2(form, params, q39_sorted)
    if form in _EQ_FAMILY:
        return apply_eq_tail(q39_sorted, params)
    if form == "over_ext_eq":
        return apply_eq_tail(q39_sorted, scale_eq(params))
    raise ValueError(f"unknown construction label: {label}")


# ── Gate composition + refusal classification ───────────────────────────────────────────────────
#: PBO deliberately ABSENT: a 1-arm family has no search to overfit (GE.pbo_is_evaluable —
#: the NF-W4 Layer-B precedent verbatim, carried from NF-MARGIN2).
M3_STATISTICAL_CHECKS: tuple[str, ...] = (
    "beats_tail_ext", "fold_consistency", "dsr_ok", "fdr_ok", "coverage_floor_ok",
)
M3_ANCHOR_CHECKS: tuple[str, ...] = (
    "degenerates_lose", "permutation_not_better", "oracle_floor_respected",
)
#: ⭐ The tail-mass gate is read AGAINST THE FOIL: the arm's beyond-EVAL-grid deviation from
#: nominal must strictly UNDERCUT `tail_ext`'s (two-sided — an over-extended arm raises its own
#: deviation from the other direction). Arm-movability proved at design time (guard-tested).
M3_CALIBRATION_CHECKS: tuple[str, ...] = ("tail_mass_toward_nominal",)


def compose_gate_margin3(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_tail_ext": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
        "degenerates_lose": bool(sel["anchors"]["zero_width_loses"]
                                 and sel["anchors"]["max_width_loses"]
                                 and sel["anchors"]["over_ext_eq_loses"]),
        "permutation_not_better": bool(sel["anchors"]["permuted_not_significantly_better"]),
        "oracle_floor_respected": bool(sel["anchors"]["oracle_floor_respected_at_matched_n"]),
        "tail_mass_toward_nominal": bool(sel["calibration"]["tail_mass_delta_vs_foil"] > 0),
    }
    return {"checks": checks, "ship": all(checks.values())}


def hand_classify_refusal_margin3(checks: dict) -> dict | None:
    """The NF-D18/MH2.7 hand check (carried verbatim from NF-MARGIN2): every statistical gate
    green with the null resting only on anchor/calibration clauses ⇒ CONSTRAINT_REFUSED — more
    data makes a directional anchor refusal fail HARDER, and ⛔ no sample-size re-test trigger
    may be published."""
    stat_fail = [c for c in M3_STATISTICAL_CHECKS if not checks.get(c, True)]
    other_fail = [c for c in (*M3_ANCHOR_CHECKS, *M3_CALIBRATION_CHECKS)
                  if not checks.get(c, True)]
    if stat_fail or not other_fail:
        return None
    return {
        "state": "CONSTRAINT_REFUSED",
        "reason": ("hand-classified (the NF-D18/MH2.7 classify_null gap): every statistical gate "
                   f"passed and the null rests entirely on anchor/calibration clauses "
                   f"{other_fail}. More data cannot change this verdict."),
        "retest_trigger": None,
        "failing_anchor_checks": other_fail,
    }
