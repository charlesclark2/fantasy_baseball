"""fp_qb_body.py — NF-W8-0c: the QB BODY-level comparison (assembled `zm_floor` vs
`direct_points`) and the declared body re-level field (pure).

THE STORY IN ONE PARAGRAPH. NF-W8-0 measured a cross-position LEVEL gap concentrated at QB
(the assembled ranking point reads −0.42 PPR below realized while WR/TE read −0.06/−0.11), and
NF-W8-0b proved it is neither a calibration defect (QB PIT is flat, 8/8 folds) nor the truncated
tails (the tail mechanism is real and ~19× too small). What NF-W8-0b DID localise is that ~95% of
the −0.3505 PPR `zm_floor`-vs-`direct_points` gap lives in the BODY of the distribution. This
module carries (a) the exact additive decomposition that names WHICH channel loses the level,
(b) the four-arm declared field that tries to restore it WITHOUT moving the calibrated quantiles
the certification rests on, (c) the separate architecture comparison against `direct_points`, and
(d) the verdict rule — all fixed BEFORE any score (the narrative pre-registration is committed at
`ablation_results/nf_w8_0c_preregistration.md`).

⛔ THE TAIL LEVER IS CLOSED. NF-W8-0b bounded the whole tail-completion mechanism at a 0.0193 PPR
cross-position spread against a 0.36 PPR artifact needing to fall under a ~0.20 PPR MDE — a
DETERMINISTIC bound no fold count can widen. Nothing here re-reads it.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 CHALLENGER: this story promotes
nothing, publishes nothing, retrains nothing, and writes NO optimizer input (prereg §9).

Pure module — no lake IO, no S3, no boto3. Runner: `run_nf_w8_0c_qb_body.py`.
"""
from __future__ import annotations

import numpy as np

from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import fp_availability_mixture as MX
from quant_sports_intel_models.football.nfl.fantasy import fp_cross_position as XP
from quant_sports_intel_models.football.nfl.fantasy import fp_qb_marginal_calibration as QM
from quant_sports_intel_models.football.nfl.fantasy import fp_tail_point as TP

# ── Pre-registration constants (the runner READS these — NF-D16) ────────────────────────────────
STORY = "NF-W8-0c"
PREDECESSORS: tuple[str, ...] = ("NF-W8-0", "NF-W8-0b")
POSITION = "QB"
TARGET = XP.TARGET
POSITIONS: tuple[str, ...] = XP.POSITIONS
PREREGISTRATION_RELPATH = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                           "nf_w8_0c_preregistration.md")

#: ⛔ The DECIDED ranking point (NF-W8-0b), imported BY REFERENCE — not re-litigated, not re-read.
POINT_READER = TP.tail_completed_point
BANK_DETAIL = TP.bank_report

N_LEGS, N_LEVELS = FA.N_LEGS, FA.N_LEVELS
LEGS: tuple[str, ...] = FA.LEGS
EVAL_LEVELS: np.ndarray = FA.EVAL_LEVELS
GRID_STEP = 1.0 / float(N_LEVELS)

# ── §1 predecessor PINS — recorded figures, never re-derived here ────────────────────────────────
PRED_QB_BIAS_TAIL_COMPLETED = -0.4237      # NF-W8-0b §12.1, row-pooled
PRED_QB_SWAP_BODY_GAP = -0.3505            # NF-W8-0b §12.2 (zm_floor − direct_points, same rows)
PRED_QB_TAIL_CHANNEL_SHARE = 0.049         # NF-W8-0b §12.2 — the tail is 4.9% of that gap
PRED_TAIL_MECHANISM_BOUND_PPR = 0.0193     # NF-W8-0b §12.1 — deterministic, no fold count widens it
PRED_PAIR_MDE_PPR: dict[str, float] = {"QB|WR": 0.2036, "QB|TE": 0.1903}
PRED_QB_PIT_ZM_FLOOR = 0.0281              # NF-W7f — clears the 0.05 bar 8/8
PRED_QB_PIT_DIRECT_POINTS = 0.0959         # NF-W7f — clears it 0/8
#: the two pairs NF-W8-0b left surviving BH — the pairs family A′ must un-reject to close the gap
GAP_PAIRS: tuple[str, ...] = ("QB|WR", "QB|TE")

# ── §4 the declared field (⛔ never trimmed or grown after a score — MH2/MH2.2) ──────────────────
INCUMBENT = "identity"
#: ⭐ in the registered SIMPLICITY order, which is also the tie-break order (prereg §4)
REAL_ARMS: tuple[str, ...] = ("cond_shift", "cond_scale", "avail_relevel", "leg_scale")
ORACLE_OF: dict[str, str] = {a: f"oracle_{a}" for a in REAL_ARMS}
#: ⭐ ONE ORACLE PER FORM — the forms NEST (`cond_scale` ⊂ `leg_scale`), and a single field-wide
#: ceiling would veto a legitimately-better nested form as a false metric inversion (NF-D16 (g‴)).
ORACLE_ARMS: tuple[str, ...] = tuple(ORACLE_OF[a] for a in REAL_ARMS)
DEGENERATE_ARMS: tuple[str, ...] = ("climatology_bank", "nihilist_zero")
ANCHOR_ARMS: tuple[str, ...] = (*ORACLE_ARMS, "over_cond_shift", "permuted_leg_scale",
                                *DEGENERATE_ARMS)
#: family C — a DIFFERENT ARCHITECTURE, deliberately NOT in family B's trial field (MH2 (a))
COMPARATOR = "direct_points"
ALL_ARMS: tuple[str, ...] = (INCUMBENT, *REAL_ARMS, *ANCHOR_ARMS, COMPARATOR)
ELIGIBLE: tuple[str, ...] = (INCUMBENT, *REAL_ARMS)     # the PBO field; trials = the 4 real arms
DECLARED_FIELD_SIZE = len(REAL_ARMS)

# ── Gate constants — ⛔ every one INHERITED BY REFERENCE, un-relaxed (E2.1-r) ─────────────────────
PIT_MAX_DECILE_DEV = FA.PIT_MAX_DECILE_DEV              # 0.05
BH_Q = XP.BH_Q                                          # 0.10
ALPHA = XP.ALPHA                                        # 0.05
PBO_MAX = XP.PBO_MAX
DSR_MIN = XP.DSR_MIN
OS_GAP_TIE_PCT = XP.OS_GAP_TIE_PCT
TIE_SE_MULT = XP.TIE_SE_MULT
MIN_PRIOR_ROWS = XP.MIN_PRIOR_ROWS
REPRODUCTION_TOLERANCE = XP.REPRODUCTION_TOLERANCE      # 1e-9

# ── This story's OWN design quantities (fixed here, before any score) ────────────────────────────
#: κ admissibility band. A κ ≤ 0 is INELIGIBLE outright (a negative scale inverts a leg — NF-D16).
MIN_SCALE, MAX_SCALE = 0.5, 2.0
#: the magnitude anchor, registered to LOSE (NF-D20 — scored, never reasoned about)
OVER_SCALE = 2.0
#: a leg contributing less than this in prior-OOF PPR keeps κ = 1: it cannot materially move the
#: level and its ratio is noise (the NF-W6 "demonstrable ≠ material" lesson, at the parameter level)
MIN_LEG_CONTRIB_PPR = 0.01
#: `leg_scale` is INELIGIBLE for a fold once more than this share of PRICED legs is out of band
MAX_OUT_OF_BAND_SHARE = 1.0 / 3.0
#: a family-A channel below this is reported IMMATERIAL — ≈ NF-W8-0b's whole measured tail mechanism
CHANNEL_MATERIAL_PPR = 0.05
#: the §3.1 identity is exact up to float accumulation; a residual above this is a coding defect
IDENTITY_TOLERANCE = 1e-8
#: the band decomposition's contiguous level bands
N_BANDS = 10

# ── Verdict states (prereg §6) ──────────────────────────────────────────────────────────────────
V_CLOSED = "QB_BODY_GAP_CLOSED"
V_HYBRID = "QB_HYBRID_INDICATED"
V_PERSISTS = "QB_BODY_GAP_PERSISTS"
V_UNDEFINED = "UNDEFINED"
VERDICT_STATES: tuple[str, ...] = (V_CLOSED, V_HYBRID, V_PERSISTS, V_UNDEFINED)

# ── Family C states (prereg §5) ─────────────────────────────────────────────────────────────────
A_ASSEMBLY = "ASSEMBLY_DOMINATES"
A_DIRECT = "DIRECT_POINTS_DOMINATES"
A_UNRESOLVED = "ARCHITECTURE_DISAGREEMENT_UNRESOLVED"
ARCHITECTURE_STATES: tuple[str, ...] = (A_ASSEMBLY, A_DIRECT, A_UNRESOLVED)

ARM_CLAUSES: tuple[str, ...] = (
    "pit_preserved", "no_crps_harm", "reduces_bias", "beats_permuted", "degenerates_lose",
    "banks_move_deliberately", "pbo_ok", "dsr_ok",
)
#: an anchor/constraint refusal publishes NO data trigger (NF-D18); a statistical one is classified
ANCHOR_CLAUSES: tuple[str, ...] = ("pit_preserved", "no_crps_harm", "beats_permuted",
                                   "degenerates_lose", "banks_move_deliberately")
STATISTICAL_CLAUSES: tuple[str, ...] = ("reduces_bias", "pbo_ok", "dsr_ok")

PROMOTE_BLOCKERS: tuple[str, ...] = TP.PROMOTE_BLOCKERS + (
    "NF-W8-0c writes NO optimizer input — NF-W8-0b's shipped input stands untouched; regenerating "
    "it under a repaired QB generator is a SUCCESSOR's step, never a side effect of this run",
    "`leg_scale` and `cond_scale` re-level a CERTIFIED per-stat marginal (NF-W6d): their per-leg "
    "marginal drift is measured and disclosed, and an admissible win under either form trades a "
    "per-stat certification scope for an assembled level",
    "family C is a CONSUMPTION comparison, never a re-certification: `direct_points` at QB is not "
    "a certified QB distribution and this story does not make it one",
    "the four arms correct a LEVEL (and a uniform per-leg scale); a rank-dependent or "
    "covariate-dependent generator artifact stays out of scope for a successor's registration",
)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The assembly wrapper — ⭐ ONE LEG-DRAW CODE PATH, shared with the scored certified assembly
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _alive_mask(pi_block: np.ndarray, shape: tuple[int, int], *, seed: int,
                block_start: int) -> np.ndarray:
    """The mixture's availability draw for one row block, at the SAME stream `mixture_leg_draws`
    uses. ⚠️ This is the one quantity the shared path does not return, so `assemble_qb` VERIFIES
    it against the scored draws (every not-alive draw must carry all-zero legs) rather than
    trusting a second copy of the logic (NF-W7d)."""
    arng = np.random.default_rng(seed + MX.AVAIL_STREAM_OFFSET + block_start)
    return arng.random(shape) < np.asarray(pi_block, float)[:, None]


def assemble_qb(banks: np.ndarray, weights: np.ndarray, *, pi: np.ndarray, corr: np.ndarray,
                draws: int = FA.ASSEMBLY_DRAWS, seed: int = QM._SEED,
                row_block: int = FA.ROW_BLOCK,
                played_shift: float = 0.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One assembled QB (n, 199) bank, its (n, 13) MEAN LEG DRAWS, and the (n,) MEAN ASSEMBLED
    TOTAL of the very same draws.

    ⭐ AT `played_shift == 0` THIS IS BYTE-IDENTICAL TO `MX.assemble_mixture_bank` — same block
    loop, same seeds, and the legs come from `MX.mixture_leg_draws`, the function the certified
    assembly itself calls. That is what makes `cond_shift` a MATCHED arm (one code path with the
    shift off) rather than a differently-implemented one, and it is guard-tested + asserted at run
    time against the certified bank (prereg §7).

    ⭐ THE TOTAL MEAN IS RETURNED SEPARATELY AND ON PURPOSE. The §3.1 decomposition needs an
    INDEPENDENT anchor: defining the read channel as `mean(point) − Σ wᵢ·legmeanᵢ` would make the
    identity TAUTOLOGICAL — it would hold for ANY leg means, including wrong ones, so the guard
    would pass on nothing (the "a test that reads a value back under the key the code writes"
    class, NF-C0e). Returning the assembled total's own draw mean gives the decomposition a
    quantity it did not construct, and `Σ wᵢ·legmeanᵢ == mean(total)` is then a REAL identity that
    a wrong leg-mean vector breaks. (Caught by this story's own RED proof at build time.)"""
    b = np.asarray(banks, dtype=float)
    if b.ndim != 3 or b.shape[1] != N_LEGS or b.shape[2] != N_LEVELS:
        raise ValueError(f"banks are {b.shape}, expected (n, {N_LEGS}, {N_LEVELS})")
    w = np.asarray(weights, dtype=float)
    if w.shape != (N_LEGS,):
        raise ValueError(f"weights are {w.shape}, expected ({N_LEGS},)")
    p = np.asarray(pi, dtype=float)
    if p.shape != (b.shape[0],):
        raise ValueError(f"pi is {p.shape}, expected ({b.shape[0]},)")
    if not np.all(np.isfinite(p)) or float(p.min()) < 0.0 or float(p.max()) > 1.0:
        raise ValueError("pi carries non-finite or out-of-[0,1] values — an availability "
                         "probability that is not a probability is a coding defect, not an arm")
    shift = float(played_shift)
    if not np.isfinite(shift):
        raise ValueError("played_shift must be finite")
    n = b.shape[0]
    bank = np.empty((n, N_LEVELS), dtype=float)
    leg_means = np.empty((n, N_LEGS), dtype=float)
    total_mean = np.empty(n, dtype=float)
    for start in range(0, n, row_block):
        stop = min(start + row_block, n)
        rng = np.random.default_rng(seed + start)
        base_z = rng.standard_normal((stop - start, draws, N_LEGS))
        legs = MX.mixture_leg_draws(b[start:stop], base_z, pi=p[start:stop], corr=corr, seed=seed,
                                    block_start=start)
        total = legs @ w
        if shift != 0.0:
            alive = _alive_mask(p[start:stop], base_z.shape[:2], seed=seed, block_start=start)
            if np.any(legs[~alive]):
                raise ValueError("the re-derived availability mask disagrees with the scored leg "
                                 "draws (a not-alive draw carries a non-zero leg) — refused "
                                 "rather than shifting the wrong draws (NF-W7d)")
            total = total + shift * alive
        bank[start:stop] = np.quantile(total, EVAL_LEVELS, axis=1).T
        leg_means[start:stop] = legs.mean(axis=1)
        total_mean[start:stop] = total.mean(axis=1)
    return bank, leg_means, total_mean


def scale_legs(banks: np.ndarray, kappa: np.ndarray) -> np.ndarray:
    """Every leg's bank multiplied by its own κ. A κ > 0 preserves each bank's monotonicity AND
    its zero mass EXACTLY (0·κ = 0), so `MX.pi_floor` — hence the clamp — is unchanged: the scale
    arms move the conditional LEVEL and nothing else about the mixture's admissibility."""
    b = np.asarray(banks, dtype=float)
    k = np.asarray(kappa, dtype=float)
    if k.shape != (N_LEGS,):
        raise ValueError(f"kappa is {k.shape}, expected ({N_LEGS},) in LEGS order")
    if not np.all(np.isfinite(k)) or float(k.min()) <= 0.0:
        raise ValueError("a non-positive or non-finite κ inverts or destroys a leg — INELIGIBLE, "
                         "never clipped silently (NF-D16 / NF1.7 (a))")
    return b * k[None, :, None]


def climatology_bank(prior_y: np.ndarray, n_rows: int) -> np.ndarray:
    """⭐ THE TWO-SIDED ANCHOR (NF1.8): every row gets the PRIOR folds' empirical quantiles of the
    realized target. It achieves ~zero level bias with ZERO skill, so it WINS this story's
    objective and MUST LOSE CRPS — a criterion a degenerate wins is fatal, and scoring it every
    run is what proves the level objective was never promoted into a selection criterion."""
    y = np.asarray(prior_y, dtype=float)
    y = y[np.isfinite(y)]
    if len(y) < 2:
        raise ValueError("the climatology anchor needs at least 2 prior realized rows — an anchor "
                         "that could not be FORMED is a failed control, never a pass (NF1.7 (a))")
    q = np.quantile(y, EVAL_LEVELS)
    return np.repeat(q[None, :], int(n_rows), axis=0)


def nihilist_bank(n_rows: int) -> np.ndarray:
    """The degenerate that predicts identically zero (NF-D11: score it, never reason about it)."""
    return np.zeros((int(n_rows), N_LEVELS), dtype=float)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §3.1 The mechanism decomposition — an EXACT additive identity
# ══════════════════════════════════════════════════════════════════════════════════════════════
def mechanism_decomposition(*, point: np.ndarray, y: np.ndarray, leg_means: np.ndarray,
                            realized: np.ndarray, weights: np.ndarray, pi_used: np.ndarray,
                            active: np.ndarray, total_draw_mean: np.ndarray) -> dict:
    """The exact split of `mean(point) − mean(y)` into the READ channel and a per-leg term.

    Because the assembled total and the realized target are the SAME linear form in the legs
    (`FA.score_realized` is `raw @ w`), the identity

        mean(point) − mean(y) = READ + Σ_i w_i·(legmean_i − realized_i)

    holds to floating-point accumulation with NOTHING estimated. `READ` is NF-W8-0b's ranking-point
    read (truncation + re-weight), carried for continuity and NOT re-opened here.

    ⚠️ `READ` is measured against `total_draw_mean` — the assembled total's OWN draw mean, which
    this function does not construct — and the LINEARITY identity `Σ wᵢ·legmeanᵢ == mean(total)`
    is what `identity_holds` reports. Defining `READ` as the residual instead would make the
    clause vacuously true for ANY leg means. ⛔ It is defined for a shift-0 (incumbent) bank: a
    `played_shift` legitimately moves the total off the leg sum by `shift·P(alive)`.

    Each leg's term splits again, exactly, into an AVAILABILITY part and a CONDITIONAL-LEVEL part
    (prereg §3.1). ⚠️ With `π̄ = 0` or `ā = 0` that split is UNDEFINED and is reported as None —
    never zero-filled (NF1.7 (a))."""
    pt, yv = np.asarray(point, float), np.asarray(y, float)
    lm, rz = np.asarray(leg_means, float), np.asarray(realized, float)
    w = np.asarray(weights, float)
    if lm.shape != rz.shape or lm.shape[1] != N_LEGS or lm.shape[0] != len(pt) != len(yv):
        raise ValueError(f"shape mismatch: point {pt.shape} y {yv.shape} leg_means {lm.shape} "
                         f"realized {rz.shape}")
    for name, arr in (("point", pt), ("y", yv), ("leg_means", lm), ("realized", rz)):
        if not np.isfinite(arr).all():
            raise ValueError(f"non-finite {name} — refused, never nan-meaned (NF-W3)")
    tdm = np.asarray(total_draw_mean, float)
    if tdm.shape != pt.shape:
        raise ValueError(f"total_draw_mean {tdm.shape} vs point {pt.shape}")
    if not np.isfinite(tdm).all():
        raise ValueError("non-finite total_draw_mean — refused, never nan-meaned (NF-W3)")
    leg_sum = float((lm @ w).mean())
    draw_total = float(tdm.mean())
    linearity_residual = float(draw_total - leg_sum)
    total_bias = float(pt.mean() - yv.mean())
    read = float(pt.mean() - draw_total)
    pi_bar = float(np.asarray(pi_used, float).mean())
    a_bar = float(np.asarray(active, float).mean())
    legs: dict[str, dict] = {}
    model_sum = 0.0
    for i, leg in enumerate(LEGS):
        contrib = float(w[i] * (lm[:, i].mean() - rz[:, i].mean()))
        model_sum += contrib
        m_bar = float(lm[:, i].mean() / pi_bar) if pi_bar > 0 else None
        c_bar = float(rz[:, i].mean() / a_bar) if a_bar > 0 else None
        legs[leg] = {
            "weight": float(w[i]),
            "leg_mean": float(lm[:, i].mean()),
            "realized_mean": float(rz[:, i].mean()),
            "contribution_ppr": contrib,
            "availability_part_ppr": (None if m_bar is None else float(w[i] * (pi_bar - a_bar)
                                                                       * m_bar)),
            "conditional_part_ppr": (None if (m_bar is None or c_bar is None)
                                     else float(w[i] * a_bar * (m_bar - c_bar))),
            "priced": bool(w[i] != 0.0),
        }
    residual = float(total_bias - (read + model_sum + linearity_residual))
    return {
        "n": int(len(pt)), "total_bias_ppr": total_bias, "read_channel_ppr": read,
        "model_channel_ppr": float(model_sum),
        "linearity_residual": linearity_residual, "identity_residual": residual,
        # ⭐ BOTH halves must hold: the reconstruction (arithmetic) AND the LINEARITY of the
        # assembled total in its own leg draws — the half a wrong leg-mean vector breaks
        "identity_holds": bool(abs(residual) <= IDENTITY_TOLERANCE
                               and abs(linearity_residual) <= IDENTITY_TOLERANCE),
        "pi_bar": pi_bar, "active_rate": a_bar, "legs": legs,
        "availability_channel_ppr": (None if pi_bar <= 0 or a_bar <= 0 else float(sum(
            d["availability_part_ppr"] for d in legs.values()))),
        "conditional_channel_ppr": (None if pi_bar <= 0 or a_bar <= 0 else float(sum(
            d["conditional_part_ppr"] for d in legs.values()))),
    }


def pool_mechanism(cells: list[dict]) -> dict:
    """Family A pooled over ROWS across folds (NF1.8 — never a mean of fold means), with the
    mean-of-fold-means convention reported BESIDE it because NF-W8-0b's own headline was first
    written the wrong way and a bound stated from the wrong convention is a different number
    wearing the same name (§12.5(e))."""
    usable = [c for c in cells if c and c.get("n")]
    if not usable:
        return {"n": 0, "pooled": None, "note": "no evaluable fold cell — UNDEFINED, not zero"}
    n_tot = sum(c["n"] for c in usable)

    def _pool(key):
        vals = [c.get(key) for c in usable]
        if any(v is None for v in vals):
            return None
        return float(sum(c["n"] * v for c, v in zip(usable, vals)) / n_tot)

    legs_pooled: dict[str, dict] = {}
    for leg in LEGS:
        legs_pooled[leg] = {
            k: (None if any(c["legs"][leg][k] is None for c in usable)
                else float(sum(c["n"] * c["legs"][leg][k] for c in usable) / n_tot))
            for k in ("contribution_ppr", "availability_part_ppr", "conditional_part_ppr")
        } | {"weight": usable[0]["legs"][leg]["weight"],
             "priced": usable[0]["legs"][leg]["priced"]}
        legs_pooled[leg]["material"] = bool(
            legs_pooled[leg]["contribution_ppr"] is not None
            and abs(legs_pooled[leg]["contribution_ppr"]) >= CHANNEL_MATERIAL_PPR)
    return {
        "n": n_tot, "n_folds": len(usable),
        "pooled": {k: _pool(k) for k in ("total_bias_ppr", "read_channel_ppr",
                                         "model_channel_ppr", "availability_channel_ppr",
                                         "conditional_channel_ppr", "linearity_residual")},
        "fold_mean": {k: float(np.mean([c[k] for c in usable]))
                      for k in ("total_bias_ppr", "read_channel_ppr", "model_channel_ppr")},
        "max_abs_identity_residual": float(max(abs(c["identity_residual"]) for c in usable)),
        "max_abs_linearity_residual": float(max(abs(c["linearity_residual"]) for c in usable)),
        "identity_holds": bool(all(c["identity_holds"] for c in usable)),
        "legs": legs_pooled,
        "material_channels": [k for k in ("read_channel_ppr", "availability_channel_ppr",
                                          "conditional_channel_ppr")
                              if (_pool(k) is not None
                                  and abs(_pool(k)) >= CHANNEL_MATERIAL_PPR)],
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §3.2 The band decomposition — where along the quantile function the gap lives
# ══════════════════════════════════════════════════════════════════════════════════════════════
def band_decomposition(bank_a: np.ndarray, bank_b: np.ndarray, *, n_bands: int = N_BANDS) -> dict:
    """The grid-mean gap between two banks on the IDENTICAL rows, split into contiguous level
    bands whose contributions SUM EXACTLY to it (`mean_a − mean_b = h·Σ_ℓ (Q_a(ℓ) − Q_b(ℓ))`).

    This is the direct answer to NF-W8-0b §12.6(1)'s first clause — which quantile ranges carry
    the −0.3505 PPR — and it is deterministic: no fitting, no `y`, no fold."""
    a = np.sort(np.asarray(bank_a, float), axis=1)
    b = np.sort(np.asarray(bank_b, float), axis=1)
    if a.shape != b.shape or a.shape[1] != N_LEVELS:
        raise ValueError(f"banks are {a.shape} vs {b.shape}, expected the same (n, {N_LEVELS})")
    if not (np.isfinite(a).all() and np.isfinite(b).all()):
        raise ValueError("non-finite bank cell — refused (NF-W3)")
    diff = (a - b).mean(axis=0)                       # (199,) mean level-wise gap
    gap = float(diff.sum() * GRID_STEP)
    edges = np.linspace(0, N_LEVELS, int(n_bands) + 1).astype(int)
    bands = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        contrib = float(diff[lo:hi].sum() * GRID_STEP)
        bands.append({
            "level_lo": float(EVAL_LEVELS[lo]), "level_hi": float(EVAL_LEVELS[hi - 1]),
            "n_levels": int(hi - lo), "contribution_ppr": contrib,
            "share": (None if abs(gap) <= 1e-15 else float(contrib / gap)),
        })
    resid = float(gap - sum(x["contribution_ppr"] for x in bands))
    return {"n_rows": int(a.shape[0]), "gridmean_gap_ppr": gap, "bands": bands,
            "band_sum_residual": resid,
            "identity_holds": bool(abs(resid) <= IDENTITY_TOLERANCE)}


def pool_bands(cells: list[dict]) -> dict:
    """Band contributions pooled over ROWS across folds (NF1.8)."""
    usable = [c for c in cells if c and c.get("n_rows")]
    if not usable:
        return {"n_rows": 0, "bands": [], "note": "no evaluable fold cell — UNDEFINED, not zero"}
    n_tot = sum(c["n_rows"] for c in usable)
    gap = float(sum(c["n_rows"] * c["gridmean_gap_ppr"] for c in usable) / n_tot)
    n_bands = len(usable[0]["bands"])
    bands = []
    for j in range(n_bands):
        contrib = float(sum(c["n_rows"] * c["bands"][j]["contribution_ppr"] for c in usable)
                        / n_tot)
        bands.append({"level_lo": usable[0]["bands"][j]["level_lo"],
                      "level_hi": usable[0]["bands"][j]["level_hi"],
                      "contribution_ppr": contrib,
                      "share": (None if abs(gap) <= 1e-15 else float(contrib / gap))})
    return {"n_rows": n_tot, "n_folds": len(usable), "gridmean_gap_ppr": gap, "bands": bands,
            "band_sum_residual": float(gap - sum(x["contribution_ppr"] for x in bands))}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §4 The arm parameters — fit on PRIOR folds' OOF rows only (fold 1 = identity by construction)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def fold_ledger(*, point: np.ndarray, y: np.ndarray, leg_means: np.ndarray,
                realized: np.ndarray, pi_used: np.ndarray, weights: np.ndarray) -> dict:
    """The per-fold OOF sums a LATER fold's arm parameters are fitted from. Sums, never means —
    a mean of fold means is a different estimator (NF1.8)."""
    lm, rz = np.asarray(leg_means, float), np.asarray(realized, float)
    w = np.asarray(weights, float)
    return {
        "n": int(len(point)),
        "sum_point": float(np.asarray(point, float).sum()),
        "sum_y": float(np.asarray(y, float).sum()),
        "sum_pi": float(np.asarray(pi_used, float).sum()),
        "sum_leg_mean": [float(v) for v in lm.sum(axis=0)],
        "sum_realized": [float(v) for v in rz.sum(axis=0)],
        "weights": [float(v) for v in w],
    }


def _accumulate(ledgers: list[dict]) -> dict | None:
    usable = [l for l in ledgers if l and l.get("n")]
    if not usable:
        return None
    n = sum(l["n"] for l in usable)
    if n < MIN_PRIOR_ROWS:
        return None
    return {
        "n": n,
        "mean_point": sum(l["sum_point"] for l in usable) / n,
        "mean_y": sum(l["sum_y"] for l in usable) / n,
        "mean_pi": sum(l["sum_pi"] for l in usable) / n,
        "mean_leg": [sum(l["sum_leg_mean"][i] for l in usable) / n for i in range(N_LEGS)],
        "mean_realized": [sum(l["sum_realized"][i] for l in usable) / n for i in range(N_LEGS)],
        "weights": list(usable[-1]["weights"]),
    }


def fit_arm_params(arm: str, ledgers: list[dict]) -> dict:
    """One arm's parameters from the pooled prior-fold OOF ledger.

    Returns `{"eligible": bool, ...}` — an INELIGIBLE fold keeps identity and is RECORDED; nothing
    is silently clipped or defaulted (NF1.7 (a))."""
    if arm not in REAL_ARMS:
        raise KeyError(f"unknown arm `{arm}` — not in the declared field {REAL_ARMS}")
    acc = _accumulate(ledgers)
    if acc is None:
        return {"eligible": False, "reason": (f"fewer than {MIN_PRIOR_ROWS} prior OOF rows — "
                                              f"identity by construction (prereg §4)")}
    if acc["mean_point"] == 0.0:
        return {"eligible": False, "reason": "prior-OOF mean point is exactly 0 — no ratio form "
                                             "is defined; identity, flagged"}
    ratio = acc["mean_y"] / acc["mean_point"]
    if arm == "cond_shift":
        if acc["mean_pi"] <= 0.0:
            return {"eligible": False, "reason": "prior-OOF mean π is 0 — the shift has no played "
                                                 "mass to act on (INACTIVE, never a pass)"}
        return {"eligible": True, "n_prior": acc["n"],
                "delta": float((acc["mean_y"] - acc["mean_point"]) / acc["mean_pi"]),
                "mean_pi_prior": acc["mean_pi"]}
    if arm == "cond_scale":
        if not (MIN_SCALE <= ratio <= MAX_SCALE):
            return {"eligible": False, "kappa": float(ratio),
                    "reason": (f"κ {ratio:.4f} outside the registered band "
                               f"[{MIN_SCALE}, {MAX_SCALE}] — INELIGIBLE for this fold")}
        return {"eligible": True, "n_prior": acc["n"], "kappa": float(ratio)}
    if arm == "avail_relevel":
        d_pi = float(acc["mean_pi"] * (ratio - 1.0))
        if not (MIN_SCALE <= ratio <= MAX_SCALE):
            return {"eligible": False, "delta_pi": d_pi,
                    "reason": (f"the implied π ratio {ratio:.4f} is outside the registered band "
                               f"[{MIN_SCALE}, {MAX_SCALE}] — INELIGIBLE for this fold")}
        return {"eligible": True, "n_prior": acc["n"], "delta_pi": d_pi,
                "mean_pi_prior": acc["mean_pi"]}
    # leg_scale
    kappa = np.ones(N_LEGS, dtype=float)
    out_of_band: list[str] = []
    immaterial: list[str] = []
    priced = [i for i in range(N_LEGS) if acc["weights"][i] != 0.0]
    for i in priced:
        contrib = abs(acc["weights"][i] * acc["mean_leg"][i])
        if contrib < MIN_LEG_CONTRIB_PPR:
            immaterial.append(LEGS[i])
            continue
        if acc["mean_leg"][i] == 0.0:
            out_of_band.append(LEGS[i])
            continue
        k = acc["mean_realized"][i] / acc["mean_leg"][i]
        if k <= 0.0:
            return {"eligible": False, "reason": (f"leg `{LEGS[i]}` implies κ {k:.4f} ≤ 0 — a "
                                                  f"negative scale inverts a leg; INELIGIBLE "
                                                  f"outright (NF-D16)")}
        if not (MIN_SCALE <= k <= MAX_SCALE):
            out_of_band.append(LEGS[i])
            continue
        kappa[i] = float(k)
    if priced and len(out_of_band) / len(priced) > MAX_OUT_OF_BAND_SHARE:
        return {"eligible": False, "out_of_band_legs": out_of_band,
                "reason": (f"{len(out_of_band)} of {len(priced)} priced legs are out of band "
                           f"(> {MAX_OUT_OF_BAND_SHARE:.3f}) — INELIGIBLE for this fold")}
    return {"eligible": True, "n_prior": acc["n"], "kappa": [float(v) for v in kappa],
            "out_of_band_legs": out_of_band, "immaterial_legs": immaterial,
            "priced_legs": [LEGS[i] for i in priced]}


def permute_kappa(kappa: list[float] | np.ndarray, priced_idx: list[int]) -> np.ndarray:
    """The `permuted_leg_scale` anchor: the fitted κ vector cyclically shifted across the PRICED
    legs, deterministic. It preserves the POPULATION of corrections and destroys their per-leg
    ASSIGNMENT — so it must not beat the real arm (NF-D10's matched-foil discipline)."""
    k = np.asarray(kappa, dtype=float).copy()
    if len(priced_idx) < 2:
        return k
    vals = [k[i] for i in priced_idx]
    rolled = vals[-1:] + vals[:-1]
    for i, v in zip(priced_idx, rolled):
        k[i] = v
    return k


def marginal_drift(banks: np.ndarray, scaled: np.ndarray) -> dict:
    """The per-leg certification-scope disclosure for the scale arms (prereg §10): how far each
    leg's certified NF-W6d marginal was moved. Reported, never gated — but never hidden either."""
    b, s = np.asarray(banks, float), np.asarray(scaled, float)
    if b.shape != s.shape:
        raise ValueError(f"bank shapes differ: {b.shape} vs {s.shape}")
    out: dict[str, float] = {}
    for i, leg in enumerate(LEGS):
        base = float(np.abs(b[:, i, :]).mean())
        out[leg] = float(np.abs(s[:, i, :] - b[:, i, :]).mean() / base) if base > 0 else 0.0
    return {"mean_abs_relative_drift": out,
            "max_leg": max(out, key=out.get) if out else None,
            "max_drift": max(out.values()) if out else 0.0}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §5/§6 The clause + verdict layer
# ══════════════════════════════════════════════════════════════════════════════════════════════
def architecture_state(*, pit_folds_assembly: int, pit_folds_direct: int, n_folds: int,
                       crps_delta: np.ndarray, bias_delta: np.ndarray,
                       alpha: float = ALPHA) -> dict:
    """Family C (prereg §5). `crps_delta` = direct − assembly per fold (positive ⇒ the assembly is
    better); `bias_delta` = |bias_assembly| − |bias_direct| per fold (positive ⇒ direct is better
    LEVELLED). Three registered states; a tie on every axis is UNRESOLVED — a tie is not a win
    (NF1.8)."""
    cd = np.asarray(crps_delta, float)
    bd = np.asarray(bias_delta, float)
    if n_folds < 2 or len(cd) < 2 or len(bd) < 2:
        return {"state": A_UNRESOLVED, "evaluable": False,
                "reason": "fewer than 2 evaluable folds — the comparison DID NOT RUN and is "
                          "never read as a result (NF1.7 (a))"}
    p_assembly_crps = XP.paired_onesided_p(cd)          # small ⇒ assembly reliably better on CRPS
    p_direct_crps = XP.paired_onesided_p(-cd)
    p_direct_bias = XP.paired_onesided_p(bd)            # small ⇒ direct reliably better levelled
    p_assembly_bias = XP.paired_onesided_p(-bd)
    pit_assembly_ok = pit_folds_assembly == n_folds
    pit_direct_ok = pit_folds_direct == n_folds
    wins_a = {"pit": bool(pit_assembly_ok and not pit_direct_ok),
              "crps": bool(p_assembly_crps is not None and p_assembly_crps < alpha),
              "bias": bool(p_assembly_bias is not None and p_assembly_bias < alpha)}
    wins_d = {"pit": bool(pit_direct_ok and not pit_assembly_ok),
              "crps": bool(p_direct_crps is not None and p_direct_crps < alpha),
              "bias": bool(p_direct_bias is not None and p_direct_bias < alpha)}
    a_dominates = any(wins_a.values()) and not any(wins_d.values())
    d_dominates = any(wins_d.values()) and not any(wins_a.values())
    if a_dominates:
        state, reason = A_ASSEMBLY, ("the assembly is no worse on PIT, CRPS or level and strictly "
                                     "better on at least one — it keeps the QB slot")
    elif d_dominates:
        state, reason = A_DIRECT, ("`direct_points` is no worse on PIT, CRPS or level and strictly "
                                   "better on at least one — a PM CONSUMPTION decision is "
                                   "indicated (never a re-certification)")
    else:
        state, reason = A_UNRESOLVED, (
            "each construction wins at least one axis (or neither wins any) — a GENUINE "
            "disagreement NEITHER SIDE CAN CLAIM: the trade is disclosed, not resolved by "
            "preference, and the consumption call is a PM decision")
    return {"state": state, "evaluable": True, "reason": reason,
            "assembly_wins": wins_a, "direct_points_wins": wins_d,
            "pit_folds_clearing": {"assembly": int(pit_folds_assembly),
                                   "direct_points": int(pit_folds_direct), "of": int(n_folds)},
            "p_assembly_better_crps": p_assembly_crps, "p_direct_better_crps": p_direct_crps,
            "p_direct_better_bias": p_direct_bias, "p_assembly_better_bias": p_assembly_bias,
            "mean_crps_delta": float(cd.mean()), "mean_abs_bias_delta": float(bd.mean())}


def banks_move_deliberately(*, arm_acts_by_fold: list[bool],
                            non_qb_identical: bool) -> bool | None:
    """⭐ THE TWO-SIDED BANK CLAUSE: the arm's OWN distribution must have moved (an arm that
    cannot ACT is INACTIVE — a finding, never a pass, NF-D20) **and** every OTHER position's
    certified bank must have passed through BYTE-IDENTICALLY (this story re-levels QB and nothing
    else; a WR or TE bank that moved means the harness changed something it never registered).

    Returns None — never False, never True — when there is no fold to read: a clause that could
    not be evaluated is UNDEFINED (NF1.7 (a))."""
    acts = [bool(a) for a in arm_acts_by_fold]
    if not acts:
        return None
    return bool(all(acts) and non_qb_identical)


def select_arm(bias_by_arm: dict[str, dict], clauses_by_arm: dict[str, dict]) -> str | None:
    """The registered selection (prereg §4): the smallest pooled |bias| among arms that are
    ELIGIBLE and clear BOTH hard constraints; ties within `TIE_SE_MULT` SE break to the registered
    SIMPLICITY order. ⛔ The constraints are FLOORS — an arm is not rewarded for exceeding them."""
    admissible = [a for a in REAL_ARMS
                  if bias_by_arm.get(a, {}).get("abs_pooled") is not None
                  and clauses_by_arm.get(a, {}).get("pit_preserved") is True
                  and clauses_by_arm.get(a, {}).get("no_crps_harm") is True]
    if not admissible:
        return None
    best = min(admissible, key=lambda a: bias_by_arm[a]["abs_pooled"])
    se = bias_by_arm[best].get("se")
    if se:
        tied = [a for a in admissible
                if bias_by_arm[a]["abs_pooled"] <= bias_by_arm[best]["abs_pooled"]
                + TIE_SE_MULT * float(se)]
        if len(tied) > 1:
            return min(tied, key=REAL_ARMS.index)     # the registered simplicity order
    return best


def body_verdict(*, harness_ok: bool, winner: str | None, winner_clauses: dict | None,
                 gap_closed: bool | None, architecture: dict | None,
                 hybrid_closes_gap: bool | None, max_mde_ppr: float | None) -> dict:
    """The four pre-registered states (prereg §6), and the `cross_rankable` flag they license."""
    if not harness_ok:
        return {"state": V_UNDEFINED, "cross_rankable": False,
                "reason": ("a reproduction pin failed, a position was skipped, or fewer than 4 "
                           "evaluable folds — the harness DID NOT RUN and this is never read as "
                           "any verdict (NF1.7 (a))"),
                "max_mde_ppr": max_mde_ppr}
    admissible = bool(winner is not None and winner_clauses
                      and all(winner_clauses.get(c) is True for c in ARM_CLAUSES))
    if admissible and gap_closed:
        return {"state": V_CLOSED, "cross_rankable": True, "winner": winner,
                "reason": (f"`{winner}` closes the QB body gap with every registered clause "
                           f"passing and QB's certified PIT/CRPS preserved — neither "
                           f"{' nor '.join(GAP_PAIRS)} survives BH under it; the hybrid is "
                           f"cross-rankable at the stated MDE"),
                "max_mde_ppr": max_mde_ppr}
    arch = (architecture or {}).get("state")
    if not admissible and arch == A_DIRECT and hybrid_closes_gap:
        return {"state": V_HYBRID, "cross_rankable": False, "winner": None,
                "reason": ("no registered repair arm is admissible, and `direct_points` dominates "
                           "the assembly on every axis while closing the cross-position gap — a "
                           "PM CONSUMPTION decision is indicated. `cross_rankable` stays False "
                           "because this story ships no consumption change (prereg §9)"),
                "architecture_state": arch, "max_mde_ppr": max_mde_ppr}
    return {"state": V_PERSISTS, "cross_rankable": False, "winner": winner,
            "reason": ("the QB body gap survives every registered arm — the hybrid architecture "
                       "stands as-is; the input keeps NF-W8-0b's disclosed per-position gap and "
                       "raw-point cross-position surfaces and superflex stay BLOCKED"),
            "architecture_state": arch, "max_mde_ppr": max_mde_ppr}
