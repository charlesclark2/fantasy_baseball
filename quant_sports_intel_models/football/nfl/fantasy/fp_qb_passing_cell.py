"""fp_qb_passing_cell.py — NF-W8-0e: the QB | `passing_yards` CELL, zero-mass × conditional-level.

THE STORY IN ONE PARAGRAPH. Two unrelated instruments localised QB's defect to ONE NF-W6d per-stat
cell. NF-W8-0c reached it from the LEVEL side — an exact additive identity over the served assembly
puts 93% of the QB model channel in `QB|passing_yards`, and 0.3878 of its 0.3975 PPR in that cell's
CONDITIONAL (played-and-positive) level. NF-W7f reached the same cell from the CALIBRATION side —
its served bank predicts `P(0) = 0.2983` against a realized 0.5563, so it under-prices its own zero
atom, and raising that atom LOWERS the marginal mean. The two corrections plausibly push the cell's
level in OPPOSITE directions. NF-W7e proved that fixing one and then the other is the single most
likely way to burn two stories and land back here, so this module registers BOTH mechanisms JOINTLY
and measures the 2×2 — `{zero-mass recal on/off} × {conditional-level correction none/shift/scale}`
— and the INTERACTION is the read, never the two marginals.

⭐ THE LAYER. This is the MARGINAL / per-stat (NF-W6d) layer: one 199-level cell bank, not the
cross-position assembly layer. NF-W8-0c's / NF-W8-0d's `DSR_UNREACHABLE` reading belongs to THAT
field (4 assembly-layer arms on a paired assembled-level statistic) and is not inherited — a
different field, a different statistic, a different declared family. ⛔ Nor is the reverse claimed:
NF-W8-0d's LOCKSTEP invariant covers ANY common-random-number field, so a `dsr_ok` failure here is
reported WITH its lockstep reading rather than with a void "lower-variance design" trigger.

⛔ NO SECOND IMPLEMENTATION OF THE TRANSFORM. `resplice_zero_mass`, `zero_targets`,
`conditional_quantiles` and `leg_zero_mass` are POINTERS at `fp_qb_marginal_calibration` — the
functions NF-W7f certified — and a guard asserts they are the same objects, not copies (the NF-C0e
wrong-key class). The ONE transform this module introduces is the conditional-level correction.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger. This module serves nothing,
publishes nothing and writes no optimizer input; a SHIP verdict says a corrected cell EXISTS and is
certified on this axis — it is NOT a re-serve of the NF-W6d substrate (prereg §11).

Pure module — no lake IO, no S3, no boto3 (fast-gate import-safe). Runner:
`run_nf_w8_0e_qb_passing_cell.py`. Pre-registration:
`ablation_results/nf_w8_0e_preregistration.md`.
"""
from __future__ import annotations

import numpy as np

from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM
from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import fp_cross_position as XP
from quant_sports_intel_models.football.nfl.fantasy import fp_qb_body as QB
from quant_sports_intel_models.football.nfl.fantasy import fp_qb_marginal_calibration as QM
from quant_sports_intel_models.football.nfl.fantasy import fp_tail_point as TP
from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions_c as SDC
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

# ── Identity ────────────────────────────────────────────────────────────────────────────────────
STORY = "NF-W8-0e"
PREDECESSORS: tuple[str, ...] = ("NF-W7e", "NF-W7f", "NF-W8-0b", "NF-W8-0c")
POSITION = "QB"
#: ⭐ THE ONE CELL. Derived from `FA.LEGS`, never re-typed — a second copy of a key is the NF-C0e
#: wrong-key class, and this key is what every reproduction pin is addressed by.
LEG = "passing_yards"
LEG_INDEX = FA.LEGS.index(LEG)
CELL = f"{POSITION}|{LEG}"
TARGET = FA.TARGET                                  # the ASSEMBLED read's target
CELL_METRIC = "crps_q199"                           # the cell contest's ranking key
PREREGISTRATION_RELPATH = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                           "nf_w8_0e_preregistration.md")

#: NF-W8-0b's DECIDED ranking point + bank reader, imported by reference (⛔ not re-litigated).
POINT_READER = TP.tail_completed_point
BANK_DETAIL = TP.bank_report

LEGS: tuple[str, ...] = FA.LEGS
N_LEGS = FA.N_LEGS
N_LEVELS = FA.N_LEVELS
EVAL_LEVELS: np.ndarray = FA.EVAL_LEVELS
POSITIONS: tuple[str, ...] = XP.POSITIONS

# ── PINS from the decided predecessors (§1 — recorded figures, never re-derived) ────────────────
PRED_QB_TOTAL_BIAS_PPR = -0.4237            # NF-W8-0c family A, row-pooled
PRED_QB_MODEL_CHANNEL_PPR = -0.4276         # NF-W8-0c family A
PRED_LEG_CONTRIBUTION_PPR = -0.3975         # NF-W8-0c family A — `passing_yards`
PRED_LEG_CONDITIONAL_PPR = -0.3878          # NF-W8-0c family A — its conditional part
PRED_LEG_AVAILABILITY_PPR = -0.0097         # NF-W8-0c family A — its availability part
PRED_CELL_PRED_P0 = 0.2983                  # NF-W7f — the SERVED cell's own atom
PRED_CELL_REAL_P0 = 0.5563                  # NF-W7f — realized
PRED_CELL_P0_AFTER_ZM = 0.5461              # NF-W7f — after the `zm_floor` re-splice
PRED_QB_PIT_ZM_FLOOR = 0.0281               # NF-W7f — clears the 0.05 bar 8/8
PRED_PAIR_MDE_PPR: dict[str, float] = {"QB|WR": 0.2036, "QB|TE": 0.1903}
GAP_PAIRS: tuple[str, ...] = ("QB|WR", "QB|TE")

# ── Gate constants — INHERITED BY REFERENCE, un-relaxed (E2.1-r) ────────────────────────────────
ASSEMBLED_PIT_MAX_DECILE_DEV = FA.PIT_MAX_DECILE_DEV        # 0.05
PBO_MAX, DSR_MIN, FDR_Q = WP.PBO_MAX, WP.DSR_MIN, WP.FDR_Q
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = WP.COVERAGE_FLOOR, WP.COVERAGE_BLOCK_SE
BH_Q, ALPHA = XP.BH_Q, XP.ALPHA
MIN_PRIOR_ROWS = XP.MIN_PRIOR_ROWS                          # 50
TIE_EPS_CRPS = SDC.TIE_EPS_CRPS                             # 1e-4
REPRODUCTION_TOLERANCE = XP.REPRODUCTION_TOLERANCE          # 1e-9
MIN_SCALE, MAX_SCALE = QB.MIN_SCALE, QB.MAX_SCALE           # [0.5, 2.0]
OVER_SCALE = QB.OVER_SCALE                                  # 2.0 — the magnitude anchor
#: NF-W6d's Phase-C DEFAULT calibration bar. ⛔ REPORTED as disclosure, NEVER a gate here: it was
#: registered for defaults, and importing it as a bar this certified W6b cell was never held to
#: would be inventing a threshold after the fact (E2.1-r). Clause 8 is a NO-HARM clause instead.
W6D_DEFAULT_PIT_BAR = 0.03
#: identities of the construction; ⛔ none is a knob
COMMUTATION_TOLERANCE = 1e-9
NO_OP_TOLERANCE = 0.0
#: a family-A channel below this is IMMATERIAL — inherited from NF-W8-0c so the two records'
#: materiality reads are the same number wearing the same name
CHANNEL_MATERIAL_PPR = QB.CHANNEL_MATERIAL_PPR

# ── The declared field (prereg §5) ⛔ never trimmed or grown after a score (MH2/MH2.2) ───────────
INCUMBENT = "identity"
#: arm → (Z on?, C form) — the 2 × 3 grid, minus the incumbent cell.
ARM_GRID: dict[str, tuple[bool, str | None]] = {
    "zm_only": (True, None),
    "cond_shift": (False, "shift"),
    "joint_shift": (True, "shift"),
    "cond_scale": (False, "scale"),
    "joint_scale": (True, "scale"),
}
REAL_ARMS: tuple[str, ...] = tuple(ARM_GRID)
DECLARED_FIELD_SIZE = len(REAL_ARMS)                 # 5 — passed to classify_null (MH2.7)
ELIGIBLE: tuple[str, ...] = (INCUMBENT, *REAL_ARMS)  # the PBO field; trials = the 5 real arms
#: the 2×2 the story is registered on — the PRIMARY (shift) square. `scale` is the declared
#: alternative FORM and gets its own square, read separately (prereg §6).
PRIMARY_SQUARE: dict[str, str] = {"z": "zm_only", "c": "cond_shift", "joint": "joint_shift"}
ALT_SQUARE: dict[str, str] = {"z": "zm_only", "c": "cond_scale", "joint": "joint_scale"}

#: FORM → the arm whose peeking oracle / matched-n control gates it (NF-D16 (g‴) / NF1.9 (f)).
ORACLE_OF: dict[str, str] = {a: f"oracle_{a}" for a in REAL_ARMS}
MATCHED_OF: dict[str, str] = {a: f"matched_n_{a}" for a in REAL_ARMS}
ORACLE_ARMS: tuple[str, ...] = tuple(ORACLE_OF[a] for a in REAL_ARMS)
MATCHED_ARMS: tuple[str, ...] = tuple(MATCHED_OF[a] for a in REAL_ARMS)
#: the two-sided MAGNITUDE bracket — both registered to LOSE (NF-D20: scored, never reasoned about)
MAGNITUDE_ANCHORS: tuple[str, ...] = ("over_joint_shift", "reverse_joint_shift")
#: ⭐ registered FORWARD as an EXPECTED EXACT TIE (prereg §5.2) — a pooled scalar has no per-row
#: content for a within-fold permutation to destroy, so this anchor CANNOT act. It is scored and
#: its tie asserted; it does NOT enter any gate clause (NF-D16 sibling (1) / NF-D20).
PERMUTED_ANCHOR = "permuted_shift"
DEGENERATE_ARMS: tuple[str, ...] = ("nihilist_zero", "zero_width", "max_width", "climatology_bank")
ANCHOR_ARMS: tuple[str, ...] = (*ORACLE_ARMS, *MATCHED_ARMS, *MAGNITUDE_ANCHORS,
                                PERMUTED_ANCHOR, *DEGENERATE_ARMS)
ALL_ARMS: tuple[str, ...] = (INCUMBENT, *REAL_ARMS, *ANCHOR_ARMS)

# ── Clause classes (prereg §7) ──────────────────────────────────────────────────────────────────
STATISTICAL_CLAUSES: tuple[str, ...] = ("beats_foil", "fold_consistency", "pbo_ok", "dsr_ok",
                                        "fdr_ok")
CONSTRAINT_CLAUSES: tuple[str, ...] = ("coverage_floor_ok", "assembled_pit_preserved",
                                       "assembled_crps_no_harm")
ANCHOR_CLAUSES: tuple[str, ...] = ("not_a_foil_tie", "cell_pit_not_degraded", "degenerates_lose",
                                   "magnitude_anchors_lose", "winner_own_form_floor",
                                   "transform_identities_hold", "incumbent_reproduces")
ALL_CLAUSES: tuple[str, ...] = (*STATISTICAL_CLAUSES, *CONSTRAINT_CLAUSES, *ANCHOR_CLAUSES)

# ── Verdict states (prereg §8, fixed in advance) ────────────────────────────────────────────────
V_CLOSED = "CELL_CORRECTED_GAP_CLOSED"
V_PERSISTS = "CELL_CORRECTED_GAP_PERSISTS"
V_NOT_CORRECTED = "CELL_NOT_CORRECTED"
V_UNDEFINED = "UNDEFINED"
VERDICT_STATES: tuple[str, ...] = (V_CLOSED, V_PERSISTS, V_NOT_CORRECTED, V_UNDEFINED)

I_ADDITIVE = "ADDITIVE"
I_SUB = "SUB_ADDITIVE"
I_SUPER = "SUPER_ADDITIVE"
I_UNDEFINED = "UNDEFINED"
INTERACTION_STATES: tuple[str, ...] = (I_ADDITIVE, I_SUB, I_SUPER, I_UNDEFINED)

PROMOTE_BLOCKERS: tuple[str, ...] = TP.PROMOTE_BLOCKERS + (
    "NF-W8-0e re-serves NOTHING: a SHIP verdict says a corrected `QB|passing_yards` cell EXISTS "
    "and is certified on this axis — re-serving a NF-W6d cell changes the certified substrate "
    "every assembled position reads and is a SUCCESSOR's registration, never a side effect",
    "the correction is ROW-BLIND (a pooled scalar per fold): the cell's LEVEL is corrected, not "
    "its per-player resolution — which is also why this story's permutation anchor is registered "
    "INACTIVE rather than presented as a passed test (prereg §5.2)",
    "the layer corrects a LEVEL (or a uniform conditional scale) only; a rank-dependent, "
    "covariate-dependent or shape-dependent cell artifact stays a successor's fresh registration",
    "`cond_scale` / `joint_scale` re-level a CERTIFIED per-stat marginal multiplicatively — their "
    "measured marginal drift is disclosed, and an admissible win under the scale form trades a "
    "per-stat certification scope for an assembled level",
    "the gate league is `full_ppr` (`passing_yards` at +0.04); a league pricing it differently "
    "scales every PPR figure here and is not separately certified",
    "family D is a VERIFICATION at ~0.19-0.20 PPR MDEs — 'below the MDE' means 'no artifact "
    "larger than X', never 'no artifact' (MH2.6)",
)

# ── The certified transform — POINTERS, never copies (guard-tested by identity) ─────────────────
resplice_zero_mass = QM.resplice_zero_mass
zero_targets = QM.zero_targets
conditional_quantiles = QM.conditional_quantiles
leg_zero_mass = QM.leg_zero_mass
zero_mass_hits_target = QM.zero_mass_hits_target
positive_law_drift = QM.positive_law_drift
matched_foil_identity = QM.matched_foil_identity
resplice_edges = QM.resplice_edges
ZERO_THRESHOLD = QM.ZERO_THRESHOLD
#: shared readers, imported (NF-W2d discipline: shared machinery is imported, never re-typed)
score_bank = EM.score_bank                       # ONE cell reducer; refuses non-finite (NF-W3 (b))
anchor_nihilist = EM.anchor_nihilist
anchor_zero_width = EM.anchor_zero_width
anchor_max_width = EM.anchor_max_width
paired_ci95 = GE.paired_ci95
direction_word = GE.direction_word
verdict_sentence = GE.verdict_sentence
benchmark_sr0 = SDC.benchmark_sr0
onesided_paired_pvalue = M14.onesided_paired_pvalue
deflated_sharpe = M14.deflated_sharpe
bias_detail = XP.bias_detail
pairwise_gap_tests = XP.pairwise_gap_tests
bh_reject = XP.bh_reject


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §4 — Z, the zero-mass recalibration, LEG-SCOPED
# ══════════════════════════════════════════════════════════════════════════════════════════════
def leg_scoped_targets(banks: np.ndarray, full_targets: np.ndarray,
                       leg_index: int = LEG_INDEX) -> np.ndarray:
    """(n, 13) targets that reproduce `full_targets` on ONE leg and are a NO-OP on the other twelve.

    The no-op is not "leave the leg alone" by omission — it is the target `leg_zero_mass(bank)`,
    which `resplice_zero_mass`'s RAISE-ONLY rule maps to the identity BYTE-FOR-BYTE (its docstring
    proves `u(v) = v` there and the sub-threshold knots are left at their original values). So the
    scoped call goes through the SAME certified transform as the unscoped one and the twelve other
    legs come back unchanged — a property this module MEASURES (`other_legs_untouched`) rather than
    assuming (NF1.7 (a))."""
    b = np.asarray(banks, dtype=float)
    if b.ndim != 3 or b.shape[1] != N_LEGS or b.shape[2] != N_LEVELS:
        raise ValueError(f"banks are {b.shape}, expected (n, {N_LEGS}, {N_LEVELS})")
    t = np.asarray(full_targets, dtype=float)
    if t.shape != b.shape[:2]:
        raise ValueError(f"targets are {t.shape}, expected {b.shape[:2]}")
    if not 0 <= int(leg_index) < N_LEGS:
        raise ValueError(f"leg_index {leg_index} is outside 0..{N_LEGS - 1}")
    out = leg_zero_mass(b)
    out[:, int(leg_index)] = t[:, int(leg_index)]
    return out


def other_legs_untouched(before: np.ndarray, after: np.ndarray,
                         leg_index: int = LEG_INDEX) -> dict:
    """The twelve legs this story does not touch must be BYTE-identical. Measured, not assumed."""
    a, b = np.asarray(before, dtype=float), np.asarray(after, dtype=float)
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch {a.shape} vs {b.shape}")
    idx = [i for i in range(N_LEGS) if i != int(leg_index)]
    gap = float(np.max(np.abs(a[:, idx, :] - b[:, idx, :]))) if idx else 0.0
    return {"max_abs_gap": gap, "holds": bool(gap <= NO_OP_TOLERANCE), "n_other_legs": len(idx)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §4 — C, the conditional-level correction (the ONE transform this story introduces)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def apply_conditional_correction(banks: np.ndarray, form: str, value: float,
                                 leg_index: int = LEG_INDEX) -> np.ndarray:
    """(n, 13, 199) banks → banks whose ONE leg's CONDITIONAL-ON-POSITIVE law is level-corrected.

    `form` is `shift` (`Q_cond ↦ max(Q_cond + value, 0)`) or `scale`
    (`Q_cond ↦ max(value · Q_cond, 0)`).

    ⭐ THE SUB-THRESHOLD KNOTS ARE LEFT AT THEIR ORIGINAL VALUES — the identical rule
    `resplice_zero_mass` documents, for the identical reason: `sample_from_bank` INTERPOLATES, so
    overwriting the last sub-threshold knot changes the ramp into the first positive knot and flips
    a draw just above the atom from 1 to 0. Only the levels ABOVE the bank's own measured atom move.

    ⭐ AND THE ATOM CANNOT MOVE. `passing_yards` is a CONTINUOUS leg (`ZERO_THRESHOLD` 0.0), so a
    positive knot stays positive under `+δ` with `δ ≥ 0` or `×κ` with `κ > 0`; the `max(·, 0)` floor
    is what makes that true for a NEGATIVE shift too (the `reverse_joint_shift` anchor), at the cost
    of clipping — the clipped SHARE is reported (`correction_edges`), never absorbed. That the atom
    is unmoved is MEASURED (`atom_unmoved`), because it is the property that makes Z and C
    commute and the property a wrong implementation would break silently."""
    if form not in ("shift", "scale"):
        raise KeyError(f"unknown conditional-correction form `{form}` — the declared forms are "
                       f"`shift` and `scale` (prereg §4)")
    b = np.asarray(banks, dtype=float)
    if b.ndim != 3 or b.shape[1] != N_LEGS or b.shape[2] != N_LEVELS:
        raise ValueError(f"banks are {b.shape}, expected (n, {N_LEGS}, {N_LEVELS})")
    v = float(value)
    if not np.isfinite(v):
        raise ValueError("a non-finite correction is a coding defect, not an arm")
    if form == "scale" and v <= 0.0:
        raise ValueError(f"κ {v} ≤ 0 inverts the leg — INELIGIBLE outright (NF-D16), never applied")
    j = int(leg_index)
    out = b.copy()
    leg = b[:, j, :]
    p_hat = leg_zero_mass(b)[:, j]                       # the PUBLIC reader, by identity
    above = EVAL_LEVELS[None, :] > p_hat[:, None]
    moved = (leg + v) if form == "shift" else (leg * v)
    out[:, j, :] = np.where(above, np.maximum(moved, 0.0), leg)
    # a correction must leave a MONOTONE bank; the sort is a no-op for a monotone input and is
    # what keeps a clipped negative shift admissible rather than silently non-monotone
    out[:, j, :] = np.sort(out[:, j, :], axis=1)
    return out


def correction_edges(banks: np.ndarray, form: str, value: float,
                     leg_index: int = LEG_INDEX) -> dict:
    """The share of (row, level) cells the `max(·, 0)` floor CLIPPED — reported, never absorbed."""
    b = np.asarray(banks, dtype=float)
    j = int(leg_index)
    leg = b[:, j, :]
    p_hat = leg_zero_mass(b)[:, j]
    above = EVAL_LEVELS[None, :] > p_hat[:, None]
    moved = (leg + float(value)) if form == "shift" else (leg * float(value))
    n = float(above.sum()) or 1.0
    return {"share_clipped_at_zero": round(float(((moved < 0.0) & above).sum()) / n, 6),
            "n_positive_cells": int(above.sum()),
            "mean_source_atom": round(float(p_hat.mean()), 6)}


def atom_unmoved(before: np.ndarray, after: np.ndarray, leg_index: int = LEG_INDEX) -> dict:
    """C must not move the leg's own atom — re-read through the PUBLIC reader, not the internals."""
    p0 = leg_zero_mass(np.asarray(before, dtype=float))[:, int(leg_index)]
    p1 = leg_zero_mass(np.asarray(after, dtype=float))[:, int(leg_index)]
    gap = float(np.max(np.abs(p1 - p0))) if p0.size else 0.0
    return {"max_abs_gap": gap, "holds": bool(gap <= NO_OP_TOLERANCE),
            "mean_atom_before": round(float(p0.mean()), 6) if p0.size else None,
            "mean_atom_after": round(float(p1.mean()), 6) if p1.size else None}


def commutation_gap(banks: np.ndarray, targets: np.ndarray, form: str, value: float,
                    leg_index: int = LEG_INDEX) -> dict:
    """⭐ Registered FORWARD as an EXPECTED TIE (prereg §4): Z-then-C vs C-then-Z on the BANK.

    Stated in advance so a near-tie is not presented as a passed test (NF-D16 sibling (1)), and
    MEASURED so the ordering choice is a recorded fact rather than an assumption. ⛔ Commuting on
    the OBJECT does not make the mechanisms additive on the METRIC — CRPS is not linear in the
    bank, and the fitted magnitude of C depends on whether Z is on. That is §6's question."""
    zc = apply_conditional_correction(resplice_zero_mass(banks, targets), form, value, leg_index)
    cz = resplice_zero_mass(apply_conditional_correction(banks, form, value, leg_index), targets)
    gap = float(np.max(np.abs(zc - cz)))
    return {"max_abs_gap": gap, "commutes": bool(gap <= COMMUTATION_TOLERANCE),
            "tolerance": COMMUTATION_TOLERANCE,
            "registered_expectation": "an EXPECTED TIE, declared before the run (prereg §4)"}


def build_arm(banks: np.ndarray, targets: np.ndarray, *, z_on: bool, form: str | None,
              value: float | None, leg_index: int = LEG_INDEX) -> np.ndarray:
    """One 2×3 cell's bank tensor: Z first (when on), then C (when a form is named)."""
    out = resplice_zero_mass(banks, targets) if z_on else np.asarray(banks, dtype=float).copy()
    if form is not None:
        if value is None:
            raise ValueError(f"form `{form}` was named with no fitted value — an arm built on a "
                             f"missing parameter is not the declared arm (NF1.7 (a))")
        out = apply_conditional_correction(out, form, float(value), leg_index)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §4.1 — the OOF ledger and the per-column fits
# ══════════════════════════════════════════════════════════════════════════════════════════════
def conditional_bank(banks: np.ndarray, leg_index: int = LEG_INDEX) -> np.ndarray:
    """(n, 199) the one leg's CONDITIONAL-ON-POSITIVE quantile function.

    Read through `QM.conditional_quantiles` — the PUBLIC reader on the PUBLIC atom, the same two
    steps the draw path uses — so no estimator here consults a transform's internals (the NF-C0e
    "a test that reads a value back under the key the code writes" class)."""
    cq = conditional_quantiles(np.asarray(banks, dtype=float), EVAL_LEVELS)
    return np.ascontiguousarray(cq[:, int(leg_index), :])


def conditional_grid_mean(banks: np.ndarray, leg_index: int = LEG_INDEX) -> np.ndarray:
    """(n,) the TRUNCATED 199-level grid mean of the conditional law — REPORTED for disclosure.

    ⛔ NOT the estimator (see `conditional_point_mean`): NF-W8-0b decided that a grid mean is not
    `E[Y]` — it integrates 0.995 of the mass and drops the outer 0.5% — and on a right-skewed
    yardage law that under-states the model's conditional mean, which would inflate δ."""
    return conditional_bank(banks, leg_index).mean(axis=1)


def conditional_point_mean(banks: np.ndarray, leg_index: int = LEG_INDEX) -> np.ndarray:
    """(n,) ⭐ THE ESTIMATOR'S MODEL SIDE: the conditional law's `E[Y]`, read through NF-W8-0b's
    DECIDED `tail_completed_point` (prereg §12A A4).

    Why this reader and not the grid mean: the −0.3878 PPR conditional channel this story is
    correcting is stated by NF-W8-0c on the TAIL-COMPLETED point, so an estimator built on the
    truncated grid mean would target a slightly DIFFERENT quantity than the one the record
    localised — the NF-W8-0b "a grid mean is not E[Y]" lesson, one layer down. Both readings are
    carried in the ledger so the choice is auditable rather than asserted."""
    return POINT_READER(conditional_bank(banks, leg_index))


def cell_ledger(*, banks_by_column: dict[str, np.ndarray], realized_leg: np.ndarray,
                leg_index: int = LEG_INDEX) -> dict:
    """One fold's OOF SUMS, per Z column — sums, never means (a mean of fold means is a different
    estimator, NF1.8). `banks_by_column` is `{"z_off": …, "z_on": …}`.

    ⭐ THE MODEL SIDE IS PROBABILITY-WEIGHTED (prereg §12A A6). The realized side averages over the
    rows that WERE positive — disproportionately starters — so an UNWEIGHTED mean of per-row model
    conditional means (which includes every backup's much lower conditional law at full weight)
    compares two different populations and inflates δ by a SELECTION effect, not a level defect.
    The model's own `E[Y | Y > 0]` is by definition

        Σ_i P̂_i(Y > 0)·m_i / Σ_i P̂_i(Y > 0)   with   P̂_i(Y > 0) = 1 − p̂_i,

    so the ledger stores that numerator and denominator as SUMS and the fit divides them. Caught by
    this story's own path proof: the unweighted estimator over-shot the cell's marginal level by
    ~3.5× and drove every C arm's assembled bias positive."""
    y = np.asarray(realized_leg, dtype=float)
    if y.ndim != 1:
        raise ValueError(f"realized leg is {y.shape}, expected (n,)")
    pos = y > float(ZERO_THRESHOLD[int(leg_index)])
    out = {"n": int(len(y)), "n_positive": int(pos.sum()),
           "sum_y_positive": float(y[pos].sum()) if pos.any() else 0.0,
           "sum_y": float(y.sum()), "columns": {}}
    for col, banks in banks_by_column.items():
        cm = conditional_point_mean(banks, leg_index)
        gm = conditional_grid_mean(banks, leg_index)
        if len(cm) != len(y):
            raise ValueError(f"column `{col}`: {len(cm)} bank rows vs {len(y)} realized rows")
        w = 1.0 - leg_zero_mass(np.asarray(banks, dtype=float))[:, int(leg_index)]
        out["columns"][col] = {
            # A6: the WEIGHTED numerator + denominator — the estimator reads these
            "sum_weighted_cond": float((w * cm).sum()), "sum_positive_weight": float(w.sum()),
            # the UNWEIGHTED and TRUNCATED readings, carried BESIDE so the A4/A6 choices are
            # auditable rather than asserted (⛔ never the estimator)
            "sum_cond_mean": float(cm.sum()), "sum_cond_gridmean": float(gm.sum())}
    return out


def _accumulate(ledgers: list[dict], column: str) -> dict | None:
    usable = [l for l in ledgers if l and l.get("n") and column in l.get("columns", {})]
    if not usable:
        return None
    n = sum(l["n"] for l in usable)
    n_pos = sum(l["n_positive"] for l in usable)
    if n < MIN_PRIOR_ROWS or n_pos < 1:
        return None
    wsum = sum(l["columns"][column]["sum_positive_weight"] for l in usable)
    if wsum <= 0.0:
        return None
    return {"n": n, "n_positive": n_pos, "positive_weight": wsum,
            "mean_y_positive": sum(l["sum_y_positive"] for l in usable) / n_pos,
            # ⭐ A6: the model's own E[Y | Y>0] — Σ P̂(Y>0)·m / Σ P̂(Y>0), NOT an unweighted mean
            "mean_cond_model": sum(l["columns"][column]["sum_weighted_cond"]
                                   for l in usable) / wsum,
            "mean_cond_model_unweighted": (
                sum(l["columns"][column]["sum_cond_mean"] for l in usable) / n),
            "mean_cond_model_gridmean": (
                sum(l["columns"][column].get("sum_cond_gridmean", np.nan) for l in usable) / n)}


def fit_cell_params(arm: str, ledgers: list[dict]) -> dict:
    """One arm's parameters from the pooled PRIOR-fold OOF ledger of ITS OWN Z column.

    ⭐ The column matters and is the point: δ and κ are refitted separately in the Z-on and Z-off
    columns, each against the bank that column actually produces, because raising the atom lowers
    the marginal mean and so changes the conditional correction the cell needs. A single δ carried
    across the columns would measure the ORDERING, not the mechanisms (prereg §4.1).

    Returns `{"eligible": bool, …}`; an INELIGIBLE fold keeps identity and is RECORDED — never
    silently clipped or defaulted (NF1.7 (a))."""
    if arm not in REAL_ARMS:
        raise KeyError(f"unknown arm `{arm}` — not in the declared field {REAL_ARMS}")
    z_on, form = ARM_GRID[arm]
    column = "z_on" if z_on else "z_off"
    if form is None:
        # `zm_only` has no fitted scalar of its own: its target is the certified NF-W7f `zm_floor`
        # rule computed from TRAIN (π̂ + the train realized rates), so it is eligible whenever the
        # runner could form that target at all.
        return {"eligible": True, "form": None, "column": column,
                "note": "no fitted scalar — the certified `zm_floor` target rule (NF-W7f)"}
    acc = _accumulate(ledgers, column)
    if acc is None:
        return {"eligible": False, "form": form, "column": column,
                "reason": (f"fewer than {MIN_PRIOR_ROWS} prior OOF rows (or no positive row) in "
                           f"column `{column}` — identity by construction (prereg §4.1)")}
    if acc["mean_cond_model"] <= 0.0:
        return {"eligible": False, "form": form, "column": column,
                "n_prior": acc["n"],
                "reason": (f"the prior-OOF model conditional mean is {acc['mean_cond_model']:.6f} "
                           f"≤ 0 — neither a shift nor a ratio is defined; identity, flagged")}
    delta = float(acc["mean_y_positive"] - acc["mean_cond_model"])
    kappa = float(acc["mean_y_positive"] / acc["mean_cond_model"])
    base = {"form": form, "column": column, "n_prior": acc["n"],
            "n_prior_positive": acc["n_positive"],
            "mean_y_positive_prior": round(acc["mean_y_positive"], 6),
            "mean_cond_model_prior": round(acc["mean_cond_model"], 6),
            "mean_cond_model_prior_unweighted": round(acc["mean_cond_model_unweighted"], 6),
            "mean_cond_model_prior_gridmean": (
                None if not np.isfinite(acc["mean_cond_model_gridmean"])
                else round(acc["mean_cond_model_gridmean"], 6)),
            "positive_weight_prior": round(acc["positive_weight"], 4),
            "reader": ("fp_tail_point.tail_completed_point on the conditional law, "
                       "PROBABILITY-WEIGHTED (prereg A4 + A6)")}
    if form == "shift":
        return {"eligible": True, **base, "value": delta, "delta": delta}
    if not (MIN_SCALE <= kappa <= MAX_SCALE):
        return {"eligible": False, **base, "value": kappa, "kappa": kappa,
                "reason": (f"κ {kappa:.4f} outside the registered band [{MIN_SCALE}, {MAX_SCALE}] "
                           f"— INELIGIBLE for this fold")}
    return {"eligible": True, **base, "value": kappa, "kappa": kappa}


def permuted_ledgers(ledgers: list[dict], rng: np.random.Generator) -> list[dict]:
    """⭐ The §5.2 anchor, built so its INACTIVITY is demonstrable rather than argued.

    A within-fold permutation of the realized labels leaves every pooled moment in the ledger
    unchanged — the ledger stores SUMS — so this returns the ledger unmodified and the runner
    asserts the resulting arm is byte-identical to `joint_shift`. Registering a permutation that
    cannot act as a PASSED test would be exactly the NF-D16 sibling defect; registering it as an
    expected TIE and proving the tie is the honest form. `rng` is accepted so the call site reads
    like every other anchor and so a future per-row correction would have somewhere to draw from."""
    _ = rng                                              # deliberately unused — see the docstring
    return [dict(l) for l in ledgers]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §6 — the 2×2 read (the story's primary deliverable)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _paired(a: np.ndarray, b: np.ndarray) -> dict:
    d = np.asarray(a, float) - np.asarray(b, float)
    d = d[np.isfinite(d)]
    m, lo, hi = paired_ci95(d)
    return {"mean": None if m is None else float(m),
            "ci95": [None if lo is None else float(lo), None if hi is None else float(hi)],
            "n_folds": int(len(d)), "fold_wins": int((d > 0).sum()),
            "p_one_sided": onesided_paired_pvalue(d) if len(d) >= 2 else None,
            "per_fold": [float(v) for v in d]}


def interaction_read(by_arm: dict[str, np.ndarray], square: dict[str, str], *,
                     incumbent: str = INCUMBENT) -> dict:
    """The 2×2 on ONE metric vector per arm (per fold), paired.

    `Δ_Z = M(incumbent) − M(z)`, `Δ_C = M(incumbent) − M(c)`,
    `Δ_joint = M(incumbent) − M(joint)`, `interaction = Δ_joint − (Δ_Z + Δ_C)`.
    Positive `Δ` = the arm IMPROVES the metric (the metric is a loss).

    ⛔ A MEASUREMENT; it gates nothing (prereg §6). The state is read off the interaction's CI95:
    a CI that covers 0 is ADDITIVE, wholly below 0 is SUB_ADDITIVE, wholly above is SUPER_ADDITIVE,
    and fewer than 2 evaluable folds (or any missing cell) is UNDEFINED — never a clean 'they add'
    (NF1.7 (a))."""
    need = [incumbent, square["z"], square["c"], square["joint"]]
    missing = [k for k in need if k not in by_arm]
    if missing:
        return {"state": I_UNDEFINED, "reason": f"square incomplete: missing {missing} — "
                                                f"UNDEFINED, never a clean reading (NF1.7 (a))"}
    inc = np.asarray(by_arm[incumbent], float)
    d_z = inc - np.asarray(by_arm[square["z"]], float)
    d_c = inc - np.asarray(by_arm[square["c"]], float)
    d_j = inc - np.asarray(by_arm[square["joint"]], float)
    inter = d_j - (d_z + d_c)
    ok = np.isfinite(inter)
    if int(ok.sum()) < 2:
        return {"state": I_UNDEFINED,
                "reason": f"{int(ok.sum())} evaluable folds — UNDEFINED (NF1.7 (a))"}
    m, lo, hi = paired_ci95(inter[ok])
    if lo is None or hi is None:
        state = I_UNDEFINED
    elif lo > 0.0:
        state = I_SUPER
    elif hi < 0.0:
        state = I_SUB
    else:
        state = I_ADDITIVE
    return {
        "state": state, "arms": dict(square),
        "delta_z": _paired(inc, np.asarray(by_arm[square["z"]], float)),
        "delta_c": _paired(inc, np.asarray(by_arm[square["c"]], float)),
        "delta_joint": _paired(inc, np.asarray(by_arm[square["joint"]], float)),
        "sum_of_halves": float(np.nanmean(d_z + d_c)),
        "interaction": {"mean": None if m is None else float(m),
                        "ci95": [None if lo is None else float(lo),
                                 None if hi is None else float(hi)],
                        "per_fold": [float(v) for v in inter[ok]],
                        "n_folds": int(ok.sum())},
        # ⭐ the NF-W7e ratio, reported in the same shape that story used: what fraction of the
        # halves' SUM the joint arm actually delivers. Undefined (never 0) at a zero denominator.
        "joint_over_sum_ratio": (None if abs(float(np.nanmean(d_z + d_c))) <= 1e-12
                                 else float(np.nanmean(d_j) / np.nanmean(d_z + d_c))),
        "reading": ("Δ positive = the arm improves the metric. A SUB_ADDITIVE interaction means "
                    "the halves OVERLAP — together they buy less than the sum of their separate "
                    "effects, which is the NF-W7e shape and the reason fixing one then the other "
                    "would mis-price both."),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §7 — selection and the clause battery
# ══════════════════════════════════════════════════════════════════════════════════════════════
def select_winner(mean_cell_crps: dict[str, float]) -> str | None:
    """Ranked on the cell's `crps_q199` among the FIVE declared real arms. ⛔ PIT never ranks
    (NF-W7c measured a degenerate posting the best PIT and the worst CRPS — a criterion a
    degenerate wins is fatal, NF1.8)."""
    scored = {a: mean_cell_crps[a] for a in REAL_ARMS
              if a in mean_cell_crps and np.isfinite(mean_cell_crps[a])}
    if not scored:
        return None
    return min(scored, key=lambda a: scored[a])


def coverage_verdict(cov: float | None, n_rows: int) -> dict:
    """The cell's coverage(80) against the FLOOR — a CONSTRAINT, never a target (NF1.8), blocking
    only beyond `COVERAGE_BLOCK_SE` binomial SE. An unevaluable read is never a pass."""
    if cov is None or not n_rows:
        return {"coverage_80": None, "n_rows": int(n_rows or 0), "binomial_se": None,
                "blocking_shortfall": True,
                "note": "unevaluable — a coverage read that did not happen is not a pass "
                        "(NF1.7 (a))"}
    se = float(np.sqrt(COVERAGE_FLOOR * (1.0 - COVERAGE_FLOOR) / n_rows))
    return {"coverage_80": round(float(cov), 4), "n_rows": int(n_rows),
            "binomial_se": round(se, 4), "floor": COVERAGE_FLOOR,
            "blocking_shortfall": bool((COVERAGE_FLOOR - float(cov)) > COVERAGE_BLOCK_SE * se)}


def oracle_pair_state(oracle_crps: float | None, matched_crps: float | None) -> dict:
    """⭐ NF-D16 (g‴) / NF1.9 (f), with NF-W6d's refinement: a per-form peeking oracle that TIES its
    matched-n control is INACTIVE, not a refusal — the peek had nothing to act on at this cell, and
    an inactive anchor is UNINFORMATIVE, never a pass AND never a fail (NF-D20).

    States: `ACTIVE_AND_RESPECTED` (oracle beats its control) · `INACTIVE` (a tie within
    `TIE_EPS_CRPS`) · `ACTIVE_AND_VIOLATED` (the control beats the peek — the floor is broken) ·
    `UNDEFINED` (either read absent)."""
    if oracle_crps is None or matched_crps is None:
        return {"state": "UNDEFINED", "passes": False, "inactive": False,
                "note": "an absent anchor read is never a pass (NF1.7 (a))"}
    gap = float(matched_crps) - float(oracle_crps)
    if abs(gap) <= TIE_EPS_CRPS:
        # ⭐ prereg §12A A7 / NF-W6d: an INACTIVE pair does NOT refuse — NF-W6d recorded three
        # shippable arms killed by exactly this reading. It is not a clean pass either: the verdict
        # NAMES it, so the record says the floor could not act rather than that it held.
        return {"state": "INACTIVE", "passes": True, "inactive": True, "gap": gap,
                "note": ("the peek TIES its matched-n control — the anchor pair could not ACT at "
                         "this cell, so it is UNINFORMATIVE: it does not refuse (NF-W6d/NF-D20) "
                         "and it does not certify the floor either")}
    if gap > 0.0:
        return {"state": "ACTIVE_AND_RESPECTED", "passes": True, "inactive": False, "gap": gap}
    return {"state": "ACTIVE_AND_VIOLATED", "passes": False, "inactive": False, "gap": gap}


def assembled_pit_verdict(pit_by_fold: list[float | None]) -> dict:
    """The assembled QB distribution must clear `FA.PIT_MAX_DECILE_DEV` on EVERY evaluable fold —
    the same 8/8 basis NF-W7f's `zm_floor` clears it on, INHERITED and un-relaxed (E2.1-r).

    ⛔ A fold whose PIT could not be read is NOT a pass: it makes the clause UNDEFINED, which fails
    closed (NF1.7 (a)). The assembly is the only PIT-clearing QB distribution on record."""
    vals = [None if v is None else float(v) for v in pit_by_fold]
    evaluable = [v for v in vals if v is not None]
    n_missing = len(vals) - len(evaluable)
    clears = [v for v in evaluable if v <= ASSEMBLED_PIT_MAX_DECILE_DEV]
    return {"bar": ASSEMBLED_PIT_MAX_DECILE_DEV, "per_fold": vals,
            "n_folds": len(vals), "n_evaluable": len(evaluable), "n_unreadable": n_missing,
            "n_clearing": len(clears),
            "worst": (max(evaluable) if evaluable else None),
            "mean": (float(np.mean(evaluable)) if evaluable else None),
            "passes": bool(evaluable and n_missing == 0 and len(clears) == len(evaluable))}


def compose_gate(*, beats_foil: bool, mean_delta: float | None, fold_clause_passes: bool,
                 pbo: float | None, dsr: float | None, fdr_pass: bool,
                 coverage: dict, assembled_pit: dict, assembled_crps_delta: float | None,
                 cell_pit_winner: float | None, cell_pit_incumbent: float | None,
                 degenerate_losses: dict, magnitude_losses: dict,
                 own_form_pair: dict, identities: dict, incumbent_reproduces: bool) -> dict:
    """The fifteen named clauses of prereg §7, in one place. Every unevaluable read fails CLOSED."""
    checks = {
        "beats_foil": bool(beats_foil),
        "not_a_foil_tie": bool(mean_delta is not None and mean_delta > TIE_EPS_CRPS),
        "fold_consistency": bool(fold_clause_passes),
        "pbo_ok": bool(pbo is not None and pbo < PBO_MAX),
        "dsr_ok": bool(dsr is not None and dsr >= DSR_MIN),
        "fdr_ok": bool(fdr_pass),
        "coverage_floor_ok": bool(not coverage.get("blocking_shortfall", True)),
        "assembled_pit_preserved": bool(assembled_pit.get("passes", False)),
        "assembled_crps_no_harm": bool(assembled_crps_delta is not None
                                       and assembled_crps_delta >= 0.0),
        "cell_pit_not_degraded": bool(cell_pit_winner is not None
                                      and cell_pit_incumbent is not None
                                      and cell_pit_winner <= cell_pit_incumbent),
        "degenerates_lose": bool(degenerate_losses
                                 and all(bool(v) for v in degenerate_losses.values())),
        "magnitude_anchors_lose": bool(magnitude_losses
                                       and all(bool(v) for v in magnitude_losses.values())),
        # A7: ACTIVE_AND_RESPECTED or INACTIVE pass; ACTIVE_AND_VIOLATED and UNDEFINED (an absent
        # read) both FAIL CLOSED — an anchor that did not run is never a pass (NF1.7 (a))
        "winner_own_form_floor": bool(own_form_pair.get("passes", False)),
        "transform_identities_hold": bool(identities
                                          and all(bool(v) for v in identities.values())),
        "incumbent_reproduces": bool(incumbent_reproduces),
    }
    missing = [c for c in ALL_CLAUSES if c not in checks]
    if missing:
        raise ValueError(f"the clause battery is incomplete: {missing} — a gate that silently "
                         f"drops a registered clause is not the registered gate")
    return {"checks": checks, "ship": all(checks.values())}


def lockstep_reading(observed_sr: float | None, trial_srs: list[float]) -> dict:
    """⭐ NF-W8-0d §1 / R2. `deflated_sharpe` reads BOTH the winner's Sharpe `SR` and the field's
    benchmark `SR0 = std(trial Sharpes)·z(N)`, and the winner is one of those trials. A design
    change that multiplies EVERY arm's per-fold dispersion by a common `c` (the generic case under
    common random numbers) maps `SR − SR0 ↦ (SR − SR0)/c` — its SIGN is invariant. So when
    `SR ≤ SR0`, a sharper design cannot flip the refusal and a "lower-variance design" trigger is
    VOID; it is computed here so it is never published (three consecutive records were sent at that
    wall)."""
    srs = np.asarray(trial_srs, dtype=float)
    sr0 = benchmark_sr0(srs)
    if observed_sr is None or sr0 is None:
        return {"evaluable": False, "sr0": sr0, "observed_sr": observed_sr,
                "note": "unevaluable — reported as such, never as a clean reading (NF1.7 (a))"}
    gap = float(observed_sr) - float(sr0)
    worst = int(np.argmin(srs)) if srs.size else None
    return {
        "evaluable": True, "sr0": float(sr0), "observed_sr": float(observed_sr),
        "sr_minus_sr0": gap,
        "variance_lever_closed": bool(gap <= 0.0),
        "most_dispersing_trial": (REAL_ARMS[worst] if worst is not None
                                  and worst < len(REAL_ARMS) else None),
        "reading": ("`SR ≤ SR0` ⇒ a SHARED proportional variance lever cannot flip the sign, at "
                    "any row, fold or draw count — do NOT publish a 'lower-variance design' "
                    "trigger (NF-W8-0d §1). `SR > SR0` ⇒ the fold-count lever has a real sign and "
                    "the shortfall is a power statement." if gap <= 0.0 else
                    "`SR > SR0` — the deflation gap is positive, so `√(T−1)` is a real lever and "
                    "the shortfall is a POWER statement, not a structural one."),
    }


def classify_null(checks: dict, *, sel: dict, n_folds: int, cv_power) -> dict | None:
    """SHIP → None. A null resting ONLY on constraint/anchor clauses → `CONSTRAINT_REFUSED` by hand
    (`cv_power` has no such state, and a sample-size trigger for a directional refusal is the
    NF-D18 actively-misleading direction). A STATISTICAL null → `cv_power.classify_null` with
    `declared_field_size` STATED (MH2.7), read through the machine flag `field_remedy_admissible`
    — never the prose (guide §0.5.4 rules 5/5b) — and WITH the NF-W8-0d lockstep reading attached
    whenever `dsr_ok` fails."""
    if all(checks.values()):
        return None
    from dataclasses import asdict

    from scipy.stats import kurtosis, skew

    stat_fail = [c for c in STATISTICAL_CLAUSES if not checks[c]]
    other_fail = [c for c in (*CONSTRAINT_CLAUSES, *ANCHOR_CLAUSES) if not checks[c]]
    if not stat_fail:
        return {
            "state": "CONSTRAINT_REFUSED",
            "reason": (f"every statistical gate passed; the null rests on constraint/anchor "
                       f"clauses {other_fail}. More data cannot change a directional refusal, so "
                       f"NO fold/season trigger is published (NF-D18)."),
            "retest_trigger": None, "failing_checks": other_fail, "binding_half": "anchor",
            "classifier": "hand (the cv_power CONSTRAINT_REFUSED gap)",
        }
    d = np.asarray(sel.get("deltas_by_fold") or [], dtype=float)
    trial_srs = np.asarray(sel.get("trial_srs") or [], dtype=float)
    var_trials = float(np.var(trial_srs, ddof=1)) if len(trial_srs) >= 2 else None
    v = cv_power.classify_null(
        metric=f"{CELL_METRIC}|{CELL}", n_folds=int(n_folds), n_arms=DECLARED_FIELD_SIZE,
        beats_foil=bool(sel.get("beats_foil")), observed_sr=sel.get("observed_sr"),
        var_trials_sr=var_trials, fold_wins=sel.get("fold_wins"),
        p_one_sided=sel.get("p_one_sided"), bh_cutoff=FDR_Q,
        skew=float(skew(d)) if len(d) >= 3 else 0.0,
        kurt=float(kurtosis(d, fisher=False)) if len(d) >= 3 else 3.0,
        # DSR-CONV provenance: no degenerate and no anchor is ever a TRIAL here (MH2.1 (a)) —
        # structural, pre-registered FORWARD in §5.1, not discovered after a score.
        degenerates_excluded_from_v=True,
        declared_field_size=DECLARED_FIELD_SIZE,
    )
    out = asdict(v)
    out["failing_checks"] = stat_fail + other_fail
    out["binding_half"] = "statistical" if not other_fail else "mixed"
    if "dsr_ok" in stat_fail:
        ls = lockstep_reading(sel.get("observed_sr"), list(trial_srs))
        out["lockstep"] = ls
        if ls.get("variance_lever_closed"):
            out["retest_trigger"] = None
            out["mechanism_reading"] = (
                "⛔ The instrument's 'lower-variance design' remedy is VOID here: `SR ≤ SR0`, and "
                "a shared proportional variance lever maps `SR − SR0 ↦ (SR − SR0)/c` with its SIGN "
                "invariant (NF-W8-0d §1). No row, fold or draw count clears it, so no data trigger "
                "is published (NF-D18). The admissible remedy is a fresh, coherently pre-registered "
                "family — ⛔ never a post-hoc trim of these five declared arms (MH2.2).")
    out["classifier"] = ("cv_power.classify_null (declared_field_size stated — MH2.7; read "
                         "field_remedy_admissible, never the prose)")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §8 — the downstream verification, and §8.1's measured structural fact
# ══════════════════════════════════════════════════════════════════════════════════════════════
def gap_closed(gap_tests: dict, pairs: tuple[str, ...] = GAP_PAIRS) -> dict:
    """Do the QB contrasts fall BELOW their own MDEs, and does BH still reject them?

    ⭐ Both readings are reported. BH rejection is the family's registered verdict; the MDE
    comparison is what makes a null a bounded statement ('no artifact larger than X') rather than
    'no artifact' (MH2.6). An unevaluable pair is UNDEFINED, never a clean close."""
    out: dict[str, dict] = {}
    for name in pairs:
        p = (gap_tests.get("pairs") or {}).get(name)
        if not p or p.get("gap") is None or p.get("mde_ppr") is None:
            out[name] = {"evaluable": False, "below_mde": None, "bh_rejected": None,
                         "note": "unevaluable pair — UNDEFINED, never a clean close (NF1.7 (a))"}
            continue
        out[name] = {"evaluable": True, "gap": float(p["gap"]), "mde_ppr": float(p["mde_ppr"]),
                     "below_mde": bool(abs(float(p["gap"])) < float(p["mde_ppr"])),
                     "bh_rejected": bool(p.get("bh_rejected"))}
    evaluable = [v for v in out.values() if v["evaluable"]]
    return {
        "pairs": out, "n_evaluable": len(evaluable),
        "all_below_mde": (None if len(evaluable) != len(pairs)
                          else bool(all(v["below_mde"] for v in evaluable))),
        "none_bh_rejected": (None if len(evaluable) != len(pairs)
                             else bool(not any(v["bh_rejected"] for v in evaluable))),
        "gap_detected_family_wide": gap_tests.get("gap_detected"),
        "max_mde_ppr": gap_tests.get("max_mde_ppr"),
    }


def assembly_activity(per_fold_gap: list[float], *, tolerance: float = REPRODUCTION_TOLERANCE
                      ) -> dict:
    """⭐ prereg §8.1 — MEASURED, not assumed. The consumed QB generator is `zm_floor`, which
    ALREADY re-splices all thirteen legs, and the re-splice is idempotent under the RAISE-ONLY
    rule — so at the ASSEMBLED layer the Z column is PREDICTED to be a structural no-op and the
    propagation is predicted to depend on C alone.

    The prediction is registered forward and read here off the per-fold gaps. The ACTIVE-fold count
    is reported beside every assembled comparison because an inactive arm is UNINFORMATIVE and
    never a pass (NF-D20)."""
    g = [float(v) for v in per_fold_gap if v is not None and np.isfinite(v)]
    active = [v for v in g if abs(v) > tolerance]
    return {"n_folds": len(g), "n_active_folds": len(active),
            "max_abs_gap": (max(abs(v) for v in g) if g else None),
            "inactive": bool(g and not active), "tolerance": tolerance,
            "registered_prediction": "a structural NO-OP (the re-splice is idempotent) — "
                                     "measured, never assumed (prereg §8.1)"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §8 — the verdict rule (fixed in advance)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def cell_verdict(*, harness_ok: bool, winner: str | None, checks: dict | None,
                 closure: dict | None, own_form_pair: dict | None = None) -> dict:
    """Four pre-registered states. ⛔ No state is reachable by a post-run reading of a gate.

    ⭐ `own_form_pair` is carried so an INACTIVE own-form oracle floor is NAMED in the verdict
    (prereg §12A A7): it does not refuse, and it does not certify the floor either — the record
    must say which of the two happened rather than letting a pass stand for both."""
    if not harness_ok or winner is None or checks is None:
        return {"state": V_UNDEFINED, "winner": winner, "cross_rankable": False,
                "reason": ("the harness controls did not all hold, or no arm could be selected — "
                           "UNDEFINED, never a clean null (NF1.7 (a))")}
    if not all(checks.values()):
        failing = [c for c, ok in checks.items() if not ok]
        return {"state": V_NOT_CORRECTED, "winner": winner, "cross_rankable": False,
                "failing_clauses": failing,
                "reason": (f"the best cell arm `{winner}` does not clear the registered battery "
                           f"({failing}) — the served `QB|passing_yards` cell STANDS and the "
                           f"NF-W8-0c reading is unchanged")}
    if closure is None or closure.get("all_below_mde") is None:
        return {"state": V_UNDEFINED, "winner": winner, "cross_rankable": False,
                "reason": ("the cell cleared the battery but the downstream cross-position read "
                           "is unevaluable — UNDEFINED, never a claimed close (NF1.7 (a))")}
    inactive = bool((own_form_pair or {}).get("inactive"))
    caveat = ("" if not inactive else
              " ⚠️ the winner's own-form oracle floor is INACTIVE (the peek ties its matched-n "
              "control): the floor did not refuse and did not certify either (NF-W6d / A7).")
    if closure["all_below_mde"] and closure.get("none_bh_rejected"):
        return {
            "state": V_CLOSED, "winner": winner, "cross_rankable": True,
            "own_form_floor_inactive": inactive,
            "reason": (f"`{winner}` corrects the cell (level AND atom) while preserving its CRPS "
                       f"and PIT and the ASSEMBLED QB calibration, and the cross-position read "
                       f"puts QB|WR and QB|TE below their MDEs with no BH rejection — the path to "
                       f"`cross_rankable: true` (raw-point + superflex) is OPEN for governance. "
                       f"⛔ This record still ships nothing (prereg §11).{caveat}"),
        }
    return {
        "state": V_PERSISTS, "winner": winner, "cross_rankable": False,
        "own_form_floor_inactive": inactive,
        "reason": (f"`{winner}` corrects the cell and clears the battery, but the QB "
                   f"cross-position gap SURVIVES it — a classified null on the DOWNSTREAM "
                   f"question: the cell was the largest single channel, not the whole "
                   f"artifact.{caveat}"),
    }
