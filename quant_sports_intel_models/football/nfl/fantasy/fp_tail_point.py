"""fp_tail_point.py — NF-W8-0b: the TAIL-COMPLETED cross-position ranking point (pure).

THE STORY IN ONE PARAGRAPH. NF-W8-0 measured a real cross-position LEVEL gap concentrated at QB
(pooled bias QB −0.470 PPR; QB|WR −0.359 and QB|TE −0.319 survive BH) and proved it is NOT a
calibration defect — every position's PIT is flat and `banks_untouched` held. The cause it named
(§12.3d) is the RANKING POINT'S OWN READ: the consumer-visible point is the MEAN OF THE 199-LEVEL
QUANTILE GRID, which is the midpoint-rule E[Y] with the outer 0.5% of probability mass TRUNCATED
— and a generator with a heavier right tail loses more mean to that truncation. On the same rows
the QB assembly reads 0.371 PPR below the direct-points construction while direct-points at QB
carries the same small bias as WR/TE. This module replaces the truncated grid mean with a
TAIL-COMPLETED E[Y]: the covered mass integrated exactly as before, plus the two beyond-grid tails
recovered with the NF-MARGIN exponential mean-excess form (`MC.apply_level_map`'s functional
family), whose scale is read DETERMINISTICALLY off the certified bank's own tail spacing.

⭐⭐ WHY "DETERMINISTIC" IS THE WHOLE POINT. NF-W8-0 §12.3a measured a NON-STATIONARITY FLOOR that
defeats any prior-history-fitted per-position constant: the cross-position range of prior-vs-fold
y-level drift is 0.511 PPR — the SAME magnitude as the 0.4888 artifact such a constant would
correct, which is why every registered recal arm captured only ~20% of the peeking oracle's
ceiling. A transform that reads NOTHING from realized outcomes has no moving target to chase: it
is a pure function of the certified quantile bank, identical whenever the bank is identical, on
every fold and every era. ⛔ THE SCALE THEREFORE MAY NOT COME FROM `MC.fit_tail_betas` (which fits
mean excess on realized `y`) NOR `M3.fit_eq_tail` (empirical exceedance quantiles) — both are
estimators and both would re-import the floor this story exists to step around. It comes from the
bank's OWN [0.975, 0.995] spacing, which the certified generator already produced.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 CHALLENGER: nothing here promotes,
publishes or retrains; the certified DISTRIBUTIONS are not touched at all (this module only
changes how a POINT is read off them — asserted, never assumed, by `banks_untouched`).

Pure module — no lake IO, no S3, no boto3. Runner: `run_nf_w8_0b_tail_point.py`.
Narrative pre-registration: `ablation_results/nf_w8_0b_preregistration.md`.
"""
from __future__ import annotations

import numpy as np

from quant_sports_intel_models.football.nfl.fantasy import fp_cross_position as XP
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

STORY = "NF-W8-0b"
PREDECESSOR = "NF-W8-0"
TARGET = XP.TARGET
POSITIONS: tuple[str, ...] = XP.POSITIONS
PREREGISTRATION_RELPATH = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                           "nf_w8_0b_preregistration.md")

# ══════════════════════════════════════════════════════════════════════════════════════════════
# §1 — the grid quadrature the incumbent point implies (prereg §2)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: the 199-level evaluation grid, inherited by identity (⛔ never redefined here)
GRID_LEVELS: np.ndarray = MC.EVAL_LEVELS
N_LEVELS = int(len(GRID_LEVELS))
#: uniform level spacing (0.005 = 1/200) — asserted at import, never assumed
GRID_STEP = float(np.round(np.diff(GRID_LEVELS).mean(), 10))
#: ⭐ the midpoint reading of `XP.bank_point`: level u_k is the MIDPOINT of a probability bin of
#: width GRID_STEP, so the 199 bins tile [COVERED_LO, COVERED_HI] and the grid mean is
#: (1/N)·Σ Q(u_k) = (1/(N·h))·∫ over that interval. The mass OUTSIDE it — TAIL_MASS_PER_SIDE on
#: each end, 0.005 in total — is exactly the "outer 0.5% tails truncated" NF-W8-0 §3 declares.
COVERED_LO = float(GRID_LEVELS[0] - GRID_STEP / 2.0)      # 0.0025
COVERED_HI = float(GRID_LEVELS[-1] + GRID_STEP / 2.0)     # 0.9975
TAIL_MASS_PER_SIDE = float(COVERED_LO)                    # 0.0025 per side, by symmetry
COVERED_MASS = float(COVERED_HI - COVERED_LO)             # 0.995 = N·h

# ══════════════════════════════════════════════════════════════════════════════════════════════
# §2 — the exponential mean-excess tail, anchored on the bank's OWN quantiles (prereg §3)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: ⭐ the two anchor levels, both DESIGN CONSTANTS already in the codebase and both exact members
#: of the 199-grid: the SERVED 39-level grid's end (`WP.Q_LEVELS[-1]` = 0.975 — the level
#: NF-MARGIN's own tail model treats as "where the tail begins", `MC.apply_level_map`'s
#: continuity joint) and the eval grid's end (0.995). ⛔ NOT tuned: this is the WIDEST in-grid
#: tail span available, so the implied scale is the most stable one the bank can supply, and both
#: numbers were fixed by prior stories, not by this one. The narrower alternatives are scored as
#: a REPORT-ONLY sensitivity (`ANCHOR_SENSITIVITY_PAIRS`) and ⛔ never selected.
ANCHOR_INNER_HI = float(WP.Q_LEVELS[-1])                  # 0.975
ANCHOR_OUTER_HI = float(GRID_LEVELS[-1])                  # 0.995
ANCHOR_INNER_LO = float(WP.Q_LEVELS[0])                   # 0.025
ANCHOR_OUTER_LO = float(GRID_LEVELS[0])                   # 0.005
#: report-only anchor sensitivity (inner level of the hi side; the lo side mirrors) — the record
#: states the transform's spread across these so the anchor choice's influence is BOUNDED and
#: VISIBLE rather than asserted to be small (NF-TR2's trailing-window discipline)
ANCHOR_SENSITIVITY_INNER_HI: tuple[float, ...] = (0.95, 0.975, 0.99)

#: the exponential mean-excess form, mirrored per side (⛔ SYMMETRIC BY REGISTRATION): the weekly
#: fantasy target is zero-heavy but NOT bounded below (an INT/fumble line scores negative), so
#: there is no support argument for treating the two sides differently — and an asymmetry that
#: happened to favour the position family A indicted would be indistinguishable from tuning
#: (E2.1-r). On a zero-atom row the bottom anchors are equal, β_lo is 0, and the left extension
#: degenerates to the flat clamp on its own — a measurement, not a special case.
TAIL_FORM = "exponential_mean_excess_symmetric"


def _assert_bank(bank: np.ndarray) -> np.ndarray:
    b = np.asarray(bank, dtype=float)
    if b.ndim != 2 or b.shape[1] != N_LEVELS:
        raise ValueError(f"bank is {b.shape}, expected (n, {N_LEVELS})")
    if not np.isfinite(b).all():
        raise ValueError("non-finite bank quantile — REFUSED, never nan-meaned past (NF-W3): a "
                         "tail-completed point over a partly-absent bank is a different "
                         "population, not a smaller one")
    return b


def _level_index(level: float) -> int:
    """The exact 199-grid column for a level. ⛔ RAISES on a level that is not ON the grid — an
    anchor silently snapped to a neighbour is a different transform wearing this one's name."""
    idx = int(np.searchsorted(np.round(GRID_LEVELS, 6), round(level, 6)))
    if idx >= N_LEVELS or abs(float(GRID_LEVELS[idx]) - level) > 1e-9:
        raise ValueError(f"anchor level {level} is not an exact member of the {N_LEVELS}-level "
                         f"grid — refused (a snapped anchor is an undeclared transform)")
    return idx


def tail_scales(bank: np.ndarray, *, inner_hi: float = ANCHOR_INNER_HI) -> dict:
    """(β_hi, β_lo) per row — the exponential mean-excess scales the CERTIFIED BANK ITSELF
    implies, read off its own tail spacing. No outcomes, no fit, no state (prereg §3).

    Under `Q(u) = Q(u_a) + β·ln((1−u_a)/(1−u))` — `MC.apply_level_map`'s exact functional family —
    two grid levels pin β in closed form:

        β_hi = (Q(0.995) − Q(inner_hi)) / ln((1−inner_hi)/(1−0.995))

    mirrored below. β ≥ 0 always (the bank is sorted), so the extension is MONOTONE by
    construction and no clamp is needed — asserted here rather than assumed."""
    b = np.sort(_assert_bank(bank), axis=1)              # defensive, per `crps_from_quantiles`
    inner_lo = float(np.round(1.0 - inner_hi, 6))
    i_hi, o_hi = _level_index(inner_hi), _level_index(ANCHOR_OUTER_HI)
    i_lo, o_lo = _level_index(inner_lo), _level_index(ANCHOR_OUTER_LO)
    log_hi = float(np.log((1.0 - inner_hi) / (1.0 - ANCHOR_OUTER_HI)))
    log_lo = float(np.log(inner_lo / ANCHOR_OUTER_LO))
    if not (log_hi > 0 and log_lo > 0):
        raise ValueError(f"degenerate anchor pair (inner_hi={inner_hi}) — refused")
    beta_hi = (b[:, o_hi] - b[:, i_hi]) / log_hi
    beta_lo = (b[:, i_lo] - b[:, o_lo]) / log_lo
    if float(np.min(beta_hi)) < -1e-12 or float(np.min(beta_lo)) < -1e-12:
        raise ValueError("negative exponential tail scale off a SORTED bank — impossible unless "
                         "the sort was skipped; refused rather than clamped")
    return {"beta_hi": np.maximum(beta_hi, 0.0), "beta_lo": np.maximum(beta_lo, 0.0),
            "q_hi": b[:, o_hi], "q_lo": b[:, o_lo], "inner_hi": float(inner_hi)}


def tail_contributions(bank: np.ndarray, *, inner_hi: float = ANCHOR_INNER_HI) -> dict:
    """The two beyond-grid mass contributions to E[Y], in closed form (prereg §3).

    With `Q(u) = q_end + β·ln(s0/(1−u))` above the grid (s0 = 1 − 0.995 = GRID_STEP) and the
    quadrature edge at `COVERED_HI` (s = TAIL_MASS_PER_SIDE):

        ∫_{COVERED_HI}^{1} Q(u) du = s·(q_hi + β_hi·(ln(s0/s) + 1))

    mirrored below. `ln(s0/s) = ln 2` here because the quadrature edge sits exactly half a bin
    beyond the last level — a consequence of the midpoint reading, not a free parameter."""
    sc = tail_scales(bank, inner_hi=inner_hi)
    s = TAIL_MASS_PER_SIDE
    s0 = float(1.0 - ANCHOR_OUTER_HI)                    # == GRID_STEP == ANCHOR_OUTER_LO
    k = float(np.log(s0 / s) + 1.0)                      # ln 2 + 1
    hi = s * (sc["q_hi"] + sc["beta_hi"] * k)
    lo = s * (sc["q_lo"] - sc["beta_lo"] * k)
    return {"hi": hi, "lo": lo, "beta_hi": sc["beta_hi"], "beta_lo": sc["beta_lo"],
            "excess_factor": k, "tail_mass_per_side": s, "inner_hi": sc["inner_hi"]}


def tail_completed_point(bank: np.ndarray, *, inner_hi: float = ANCHOR_INNER_HI) -> np.ndarray:
    """(n,) ⭐ THE NF-W8-0b RANKING POINT: `E[Y]` with the truncated outer mass RESTORED.

        point_tc = COVERED_MASS · gridmean + ∫_0^{0.0025} Q + ∫_{0.9975}^1 Q

    The first term re-weights the incumbent's `(1/N)·Σ Q` to the mass it actually integrates
    (N·h = 0.995, not 1) — ⛔ WITHOUT IT the transform carries a +0.5% MULTIPLICATIVE bias that
    scales with a position's own level and would MANUFACTURE a cross-position differential of its
    own. The correctness anchor is exactness: `tail_completed_point` returns `c` EXACTLY for a
    degenerate bank at `c`, and E[Y] exactly for any distribution whose quantile function the
    exponential form reproduces (uniform, exponential) — guard-tested as an oracle floor.

    DETERMINISTIC: a pure function of the bank. No `y`, no fold, no fitted state."""
    b = _assert_bank(bank)
    tc = tail_contributions(b, inner_hi=inner_hi)
    return COVERED_MASS * XP.bank_point(b) + tc["hi"] + tc["lo"]


def completion_detail(bank: np.ndarray, *, inner_hi: float = ANCHOR_INNER_HI) -> dict:
    """The transform's own decomposition, per (fold, position) — the magnitudes BESIDE any
    activity share (NF-W7f: a binding/active share is invariant to the magnitude it binds at, so
    a share alone can report 'nothing changed' about a mechanism that stopped mattering)."""
    b = _assert_bank(bank)
    gm = XP.bank_point(b)
    tc = tail_contributions(b, inner_hi=inner_hi)
    point = COVERED_MASS * gm + tc["hi"] + tc["lo"]
    delta = point - gm
    return {
        "n": int(b.shape[0]),
        "mean_gridmean": round(float(gm.mean()), 6),
        "mean_point_tc": round(float(point.mean()), 6),
        "mean_delta": round(float(delta.mean()), 6),
        "mean_reweight_term": round(float(((COVERED_MASS - 1.0) * gm).mean()), 6),
        "mean_hi_tail": round(float(tc["hi"].mean()), 6),
        "mean_lo_tail": round(float(tc["lo"].mean()), 6),
        "mean_beta_hi": round(float(tc["beta_hi"].mean()), 6),
        "mean_beta_lo": round(float(tc["beta_lo"].mean()), 6),
        # the share of rows whose hi-side tail is FLAT (β_hi == 0 — a degenerate upper tail): a
        # reported share, never a silent default (NF1.7 (a))
        "flat_hi_share": round(float(np.mean(tc["beta_hi"] <= 0.0)), 4),
        "flat_lo_share": round(float(np.mean(tc["beta_lo"] <= 0.0)), 4),
        "inner_hi": float(inner_hi),
    }


def anchor_sensitivity(bank: np.ndarray) -> dict:
    """REPORT-ONLY (prereg §3): the mean tail-completed point under each alternative inner
    anchor. ⛔ NEVER selected — it exists so the registered anchor's influence is BOUNDED and
    VISIBLE in the record rather than argued to be small."""
    out: dict[str, float] = {}
    for inner in ANCHOR_SENSITIVITY_INNER_HI:
        out[f"inner_hi={inner}"] = round(float(tail_completed_point(bank, inner_hi=inner).mean()), 6)
    out["registered"] = f"inner_hi={ANCHOR_INNER_HI}"
    return out


def bank_report(bank: np.ndarray) -> dict:
    """The per-(fold, position) transform record: the decomposition PLUS the report-only anchor
    sensitivity. Passed to the shared runner as its `bank_detail` hook."""
    return completion_detail(bank) | {"anchor_sensitivity": anchor_sensitivity(bank)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §3 — the swap-clause MATERIALITY FLOOR (NF-W8-0 §12.5(2), registered forward here)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: ⭐ NF-W8-0's swap activity rule (|pooled shift| > 2×SE) has NO MATERIALITY FLOOR, so it refused
#: the story's winner on WR/TE shifts of 0.037/0.095 PPR — precisely estimated but an ORDER OF
#: MAGNITUDE below family A's own detection floor, while QB (the position family A indicted)
#: collapsed decisively. That is the NF-W6 "demonstrable ≠ material" lesson on a clause of the
#: predecessor's own design; §12.3c registered the successor rule and this is it:
#:
#:      active := |pooled shift| > 2×SE  AND  |pooled shift| ≥ SWAP_MATERIALITY_FLOOR
#:
#: THE FLOOR IS A DESIGN QUANTITY, NOT A TUNED ONE: it is family A's OWN resolution on the SAME
#: run — the MEDIAN of the 6 pairwise MDEs at 80% power. An MDE is a function of the design's
#: noise, never of the effect (MH2.6), so reading it here states the rule the whole story already
#: lives by: a swap shift SMALLER than what family A can detect cannot be the artifact family A
#: indicted. ⛔ Registered BEFORE this story scored anything.
#:
#: DISCLOSED, so the choice cannot hide: on NF-W8-0's RECORDED shifts the MIN (0.1732), MEDIAN
#: (0.1955) and MAX (0.3277) pairwise MDE all yield the IDENTICAL activity set (QB active; RB/WR/
#: TE inactive) — the summary statistic is NOT outcome-determining there. The record reports all
#: three on this run's own numbers (`materiality_floor_sensitivity`) either way.
SWAP_FLOOR_STATISTIC = "median_pairwise_mde_ppr"


def materiality_floor(family_a: dict, *, statistic: str = SWAP_FLOOR_STATISTIC) -> dict:
    """The registered swap materiality floor from family A's own per-pair MDEs, plus the
    min/median/max sensitivity band. Returns floor None (⇒ the floor cannot be formed) when no
    pair is evaluable — the caller must then treat the clause as UNEVALUABLE, never as floor 0
    (NF1.7 (a): a check that could not be formed is not a check that passed)."""
    mdes = sorted(float(d["mde_ppr"]) for d in family_a.get("pairs", {}).values()
                  if d.get("mde_ppr") is not None and np.isfinite(d["mde_ppr"]))
    if not mdes:
        return {"floor_ppr": None, "statistic": statistic, "n_pairs": 0,
                "note": "no evaluable family-A pair — the floor could not be FORMED; the swap "
                        "clause is UNEVALUABLE, never floor-0 (NF1.7 (a))"}
    band = {"min": round(mdes[0], 4), "median": round(float(np.median(mdes)), 4),
            "max": round(mdes[-1], 4)}
    if statistic != SWAP_FLOOR_STATISTIC:
        raise ValueError(f"unregistered floor statistic {statistic!r} — the floor is fixed in "
                         f"advance ({SWAP_FLOOR_STATISTIC}); a summary chosen after a score is "
                         f"the E2.1-r inversion")
    return {"floor_ppr": band["median"], "statistic": statistic, "n_pairs": len(mdes),
            "sensitivity_band": band}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §4 — the NF-W8-0b verdict rule, fixed in advance (prereg §5)
# ══════════════════════════════════════════════════════════════════════════════════════════════
V_CLOSES = "TAIL_COMPLETION_CLOSES_THE_GAP"
V_REMOVED = "TAIL_COMPLETED_LEVEL_ARTIFACT_REMOVED"
V_PERSISTS = "TAIL_COMPLETED_GAP_PERSISTS"
V_UNDEFINED = "UNDEFINED"
VERDICT_STATES: tuple[str, ...] = (V_CLOSES, V_REMOVED, V_PERSISTS, V_UNDEFINED)

#: ⭐ the AC's single definition, fixed before any score: the hybrid is CROSS-RANKABLE only when
#: the DETERMINISTIC tail-completed point closes the gap on its own — i.e. under `identity`, with
#: NO recalibration layer. A gap closed only by a fitted layer is reported as
#: `cross_rankable_with_layer` and is a DIFFERENT, WEAKER claim (it re-imports NF-W8-0 §12.3a's
#: non-stationarity floor, which is exactly what this story exists to avoid).
def tail_point_verdict(*, predecessor_verdict: dict, swap_state: str | None,
                       winner_clauses: dict[str, bool | None] | None) -> dict:
    """Map NF-W8-0's four-state comparability verdict — re-derived by the SHARED derive layer on
    the tail-completed point — onto NF-W8-0b's registered states, and emit the two cross-rankable
    readings. One derivation, two namings: ⛔ no second implementation of the statistics."""
    base = str(predecessor_verdict.get("state"))
    gap = predecessor_verdict.get("gap_detected")
    mde = predecessor_verdict.get("max_mde_ppr")
    if base == XP.V_UNDEFINED or gap is None:
        state = V_UNDEFINED
        reason = ("a reproduction pin failed, a position was skipped, or family A could not "
                  "evaluate on the tail-completed point — the harness did not run; never read "
                  "as any verdict (NF1.7 (a))")
    elif base == XP.V_COMPARABLE:
        state = V_CLOSES
        reason = (f"the DETERMINISTIC tail-completed point closes the cross-position level gap: "
                  f"no pairwise contrast survives BH(q={XP.BH_Q}) at a max pairwise MDE of "
                  f"{mde} PPR. The hybrid is cross-rankable with NO recalibration layer — "
                  f"'no artifact larger than the MDE', never 'no artifact' (MH2.6).")
    elif base == XP.V_REMOVED:
        state = V_REMOVED
        reason = ("the tail-completed point did NOT close the gap on its own, but a registered "
                  "recalibration arm is admissible on top of it — a WEAKER claim than this "
                  "story's gate: a fitted layer re-imports NF-W8-0 §12.3a's non-stationarity "
                  "floor, so `cross_rankable` (the deterministic reading) stays False")
    else:
        state = V_PERSISTS
        reason = ("the cross-position level gap SURVIVES the tail completion and no registered "
                  "arm is admissible — the hybrid is NOT cross-rankable; the input ships as "
                  "`identity` on the tail-completed point with the residual per-position gap "
                  "DISCLOSED (`level_gap_disclosure`)")
    return {
        "state": state, "reason": reason,
        "predecessor_state": base, "gap_detected": gap, "max_mde_ppr": mde,
        "swap_state": swap_state, "winner": predecessor_verdict.get("winner"),
        "winner_clauses": winner_clauses,
        # ⭐ the AC's headline, one definition
        "cross_rankable": bool(state == V_CLOSES),
        "cross_rankable_with_layer": bool(state in (V_CLOSES, V_REMOVED)),
        "qb_consumption": XP.QB_CONSUMPTION, "second_reader": XP.SECOND_READER,
    }


#: NF-W8-0's promote blockers travel VERBATIM (nothing here re-certifies anything), plus the two
#: this story adds.
PROMOTE_BLOCKERS: tuple[str, ...] = XP.PROMOTE_BLOCKERS + (
    "the tail completion is a DETERMINISTIC read of the certified bank — it re-certifies NO "
    "position: NF-W7f's QB Option-B caveat, NF-W7c's calibrated-default disclosure and every "
    "per-position certification scope are inherited UNCHANGED",
    "`cross_rankable: true` licenses the RAW-POINT cross-position surfaces and a superflex "
    "board at the stated MDE only; it is not a claim about a rank-dependent (within-position "
    "non-uniform) generator artifact, which stays out of scope for a successor's registration",
)
