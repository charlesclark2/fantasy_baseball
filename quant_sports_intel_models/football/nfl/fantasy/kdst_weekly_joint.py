"""kdst_weekly_joint.py — NF-W7b: the DST DEPENDENCE successor (pure constants + assembly glue).

THE STORY IN ONE PARAGRAPH. NF-W7's assembled `dst_points` distribution BEAT all three foils on
`crps_q199` (+0.0338 vs the best, CI95 excludes zero, DSR 0.961, 7/8 folds) and was
**CONSTRAINT_REFUSED** by the pre-registered coverage(80) floor alone: 0.7603 vs 0.80 at n=2,174
(≈4.6 binomial SE). Mechanism = the DECLARED independence simplification firing — the component
banks (sacks / INT / FR / rares / PA-bucket) co-move, so an independent draw under-disperses the
assembled sum. Per NF-D18 the floor is untouchable and has NO data trigger; the only remedy is a
DIFFERENT MECHANISM. This story adds exactly one thing: a pre-registered JOINT (Gaussian-copula)
draw over the component legs. ⛔ The component marginals are NOT refit — they won their score
contest in NF-W7 and are consumed VERBATIM (`FROZEN_DST_WINNERS`, asserted against the committed
NF-W7 record at load); the copula layer changes only the joint law, provably (a Σ=I draw is
byte-identical to the independent draw under common random numbers).

⭐ ARM-MOVABILITY (NF-MARGIN2 / NF-D20 — a statistic the arm cannot move is décor, not a gate):
the dependence knob provably moves the gated statistic. Analytic half: Var(Σ wᵢXᵢ) =
(w∘σ)ᵀΣ(w∘σ) is strictly increasing in every off-diagonal with a positive weight product, so the
assembled sum's dispersion — hence its central-interval coverage — moves with Σ. Measured half:
the smoke run must show cov80(comonotone) > cov80(indep) before the full run, and the full run
records `dependence_moves_coverage` as a gate clause.

Everything decidable in advance is a CONSTANT here; the runner READS it (NF-D16). The narrative
pre-registration is committed at `ablation_results/nf_w7b_preregistration.md` BEFORE the full run.

⚖️ EDGE-INDEPENDENT (best_alpha N/A) · DEPLOY-HELD · research-only (no changelog).
"""
from __future__ import annotations

import numpy as np

from quant_sports_intel_models.football.nfl.fantasy import joint_draw as JD
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
STORY = "NF-W7b"
TARGET = "dst_points"
SELECTION_METRIC = "crps_q199"                  # unchanged from NF-W7 — the dense grid
_SEED = 20260814

#: ⛔ FROZEN — NF-W7's Layer-A score-best DST arms, consumed verbatim (the card's binding
#: constraint: this story adds ONLY the dependence structure). The runner ASSERTS these against
#: the committed NF-W7 record (`ablation_results/nf_w7_kdst_weekly.json`) before any scoring.
FROZEN_DST_WINNERS: dict[str, str] = {
    "def_sacks": "negbin_glm",
    "def_int": "negbin_glm",
    "def_fumble_rec": "negbin_glm",
    "dst_td": "eb_pois",
    "def_safety": "hurdle_pois",
    "def_blocked_kick": "eb_pois",
    "pa_bucket": "ordered_logit",
}

#: The copula leg ORDER (fixed; the six linear count legs in NF-W7's scoring order, PA last).
COMPONENT_LEGS: tuple[str, ...] = (
    "def_sacks", "def_int", "def_fumble_rec", "dst_td", "def_safety", "def_blocked_kick",
    "pa_bucket",
)
#: The comonotone degenerate co-moves every leg in the POINTS direction: tier points DECREASE in
#: the PA bucket, so the PA leg takes 1−u (a great defensive day = many sacks AND few points
#: allowed). Only the PA leg flips.
COMONOTONE_FLIP: tuple[bool, ...] = (False, False, False, False, False, False, True)

#: ⭐ The declared real-arm family — a hypothesis-driven magnitude/structure grid over the
#: dependence axis, bracketed by the anchors (indep = 0×, comonotone = 1.0):
#:   joint_rankcorr — full Gaussian copula, Σ̂ from latent z-scores of randomized PITs under the
#:                    FROZEN marginals' in-sample train predictions (the model-RESIDUAL scale —
#:                    the co-movement the marginals' features do NOT already explain);
#:   joint_factor   — the nearest ONE-FACTOR structure of that Σ̂ (shared latent game state);
#:   joint_raw      — Σ̂ from Spearman rank correlation of the RAW outcomes, 2·sin(π·ρ_s/6)
#:                    (the unconditional scale — an upper read that includes feature-explained
#:                    co-movement);
#:   joint_double   — Σ̂ off-diagonals ×2, PSD-repaired (the attenuation probe: randomized PITs
#:                    on zero-heavy discrete margins bias ρ̂ toward 0 by a factor with no closed
#:                    form — NF-D20's magnitude axis, registered as a REAL arm so an
#:                    under-correcting estimator cannot hide behind an anchor's ineligibility).
REAL_ARMS: tuple[str, ...] = ("joint_rankcorr", "joint_factor", "joint_raw", "joint_double")
DOUBLE_SCALE = 2.0

#: The same three foils as NF-W7's Layer B — the joint arm must keep the score win against them.
FOILS: tuple[str, ...] = KW.LAYER_B_FOILS
#: The eligible field — declared here, never trimmed or grown after a score (MH2 (a)).
ELIGIBLE: tuple[str, ...] = (*REAL_ARMS, *FOILS)

#: Degenerates — all SCORED, all registered to LOSE the metric (NF1.8/NF-D14). The comonotone
#: arm is the over-correlated degenerate of the card: it will trivially SATISFY the coverage
#: floor (a constraint a degenerate satisfies is fine — the metric eliminates it), and it must
#: LOSE the score contest.
DEGENERATES: tuple[str, ...] = ("nihilist_zero", "zero_width", "max_width",
                                "assembled_comonotone")
ANCHORS: tuple[str, ...] = (
    *DEGENERATES, "assembled_indep", "permuted_direct",
    *(f"oracle__{a}" for a in REAL_ARMS), *(f"matched_n__{a}" for a in REAL_ARMS),
    *(f"oracle__{f}" for f in FOILS),
)

#: One downstream family, one member — BH-FDR at q=0.10 over it (declared; trivially p < q).
FDR_FAMILIES: dict[str, tuple[str, ...]] = {"downstream": ("dst_points_joint",)}

#: Inherited gate constants — identical to NF-W7 (⛔ the floor may not move: NF-D18/E2.1-r).
COVERAGE_FLOOR = KW.COVERAGE_FLOOR
COVERAGE_BLOCK_SE = KW.COVERAGE_BLOCK_SE
PBO_MAX, DSR_MIN, FDR_Q = KW.PBO_MAX, KW.DSR_MIN, KW.FDR_Q
ASSEMBLY_DRAWS = KW.ASSEMBLY_DRAWS
MIN_ESTIMATION_ROWS = JD.MIN_ESTIMATION_ROWS

#: NF-W7's recorded incumbent figures — REPRODUCTION references only (report-only tolerance
#: checks; the harness re-scores indep itself, these never gate).
NF_W7_RECORDED = {"assembled_crps": 2.6975, "assembled_cov80": 0.7603, "n_rows": 2174}

#: The gate's clause partition (GE.hand_classify_refusal semantics, W7b's clause set).
STATISTICAL_CHECKS: tuple[str, ...] = (
    "beats_foil", "fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok", "coverage_floor_ok",
)
ANCHOR_CHECKS: tuple[str, ...] = (
    "degenerates_lose", "permutation_behaves", "oracle_floors_respected",
    "incumbent_refusal_reproduces", "dependence_moves_coverage", "beats_indep_on_coverage",
)

#: The CONSTRAINT_REFUSED prose for THIS story's mechanism (NF-W7's text says "independence-
#: simplification firing", which would be FALSE here — the arms are not independent draws).
REFUSAL_MECHANISM = (
    ". The mechanism: the registered dependence structures UNDER-CORRECT — the joint draw moves "
    "coverage toward nominal but not far enough, so the residual co-movement (or a non-Gaussian "
    "dependence shape) is still unpriced.")
REFUSAL_REMEDY = (
    "NONE — a constraint refusal is not rescuable by data (NF-D18): more folds make the refusal "
    "MORE certain. The remedy is a BETTER dependence estimator/shape under a FRESH registration "
    "(NF-MARGIN3's successor pattern — e.g. a less attenuated latent-scale estimator or a "
    "non-Gaussian copula), or a PM decision; ⛔ never a post-hoc floor change (E2.1-r/NF1.8).")


# ── Σ estimation (per fold, train-only — causal) ────────────────────────────────────────────────
def component_zscores(banks: dict[str, np.ndarray], df, seed: int = _SEED) -> np.ndarray:
    """(n, 7) latent z-scores: randomized PIT of each realized component outcome under the FROZEN
    marginal's predictive for that row, Φ⁻¹-mapped. `banks` holds quantile banks for the count
    legs and the (n, 9) bucket-probability matrix for `pa_bucket`."""
    cols = []
    for i, leg in enumerate(COMPONENT_LEGS):
        if leg == "pa_bucket":
            u = JD.randomized_pit_categorical(banks[leg], df[leg].to_numpy(), seed + i)
        else:
            u = KW.randomized_pit_from_bank(banks[leg], df[leg].to_numpy(float), seed + i)
        cols.append(JD.zscores_from_uniforms(u))
    return np.column_stack(cols)


def sigma_for_arm(arm: str, banks: dict[str, np.ndarray], df, seed: int = _SEED) -> np.ndarray:
    """The arm's correlation matrix, from ITS pre-registered estimator. `banks`/`df` are the
    ESTIMATION context (train in the real arms; test in an oracle; the matched slice in a
    matched-n control) — the caller chooses, the transform is fixed here."""
    if arm not in REAL_ARMS:
        raise KeyError(f"unknown dependence arm `{arm}` — not in the pre-registered family")
    if arm == "joint_raw":
        mat = np.column_stack([df[leg].to_numpy(float) for leg in COMPONENT_LEGS])
        return JD.spearman_gauss_corr(mat)[0]
    base, _ = JD.estimate_corr_from_z(component_zscores(banks, df, seed))
    if arm == "joint_rankcorr":
        return base
    if arm == "joint_factor":
        return JD.one_factor_corr(base)[0]
    return JD.scale_offdiagonal(base, DOUBLE_SCALE)  # joint_double


# ── The joint assembly (marginals untouched; only the uniforms' joint law changes) ──────────────
def assemble_dst_bank_from_uniforms(count_banks: dict[str, np.ndarray], pa_proba: np.ndarray,
                                    u_all: np.ndarray) -> np.ndarray:
    """NF-W7's exact DST assembly — inverse-CDF count draws + the EXACT tier draw — fed by an
    externally supplied uniform block `u_all` (n, draws, 7) in COMPONENT_LEGS order. The
    marginal law of each leg is untouched for ANY joint law of `u_all` whose leg marginals are
    U(0,1); the dependence between legs is exactly the dependence of `u_all`."""
    n, draws, n_legs = u_all.shape
    assert n_legs == len(COMPONENT_LEGS)
    pts = np.zeros((n, draws))
    for i, leg in enumerate(COMPONENT_LEGS[:-1]):
        c = np.rint(np.clip(KW.sample_from_bank(count_banks[leg], u_all[:, :, i]), 0, None))
        pts += KW.DST_LINEAR_POINTS[leg] * c
    p = np.clip(np.asarray(pa_proba, dtype=float), 1e-9, None)
    p = p / p.sum(axis=1, keepdims=True)
    cum = np.cumsum(p, axis=1)
    bucket = (u_all[:, :, -1][:, :, None] > cum[:, None, :]).sum(axis=2)
    pts += np.asarray(KW.PA_TIER_POINTS, dtype=float)[bucket]
    return np.quantile(pts, KW.EVAL_LEVELS, axis=1).T


def assembled_bank(count_banks: dict[str, np.ndarray], pa_proba: np.ndarray, *,
                   corr: np.ndarray | None = None, mode: str = "copula",
                   draws: int = ASSEMBLY_DRAWS, seed: int = _SEED) -> np.ndarray:
    """One assembled (n, 199) fantasy-point bank. ⭐ COMMON RANDOM NUMBERS: the base normals
    depend only on (n, draws, seed), so every arm/anchor of a fold transforms the SAME block —
    arm differences are dependence differences, not MC noise — and `mode="indep"` is
    byte-identical to the copula at Σ=I."""
    n = next(iter(count_banks.values())).shape[0]
    rng = np.random.default_rng(seed)
    base_z = rng.standard_normal((n, draws, len(COMPONENT_LEGS)))
    if mode == "comonotone":
        u = JD.comonotone_uniforms(base_z, COMONOTONE_FLIP)
    elif mode == "indep":
        u = JD.independent_uniforms(base_z)
    elif mode == "copula":
        if corr is None:
            raise ValueError("mode='copula' requires corr")
        u = JD.gaussian_copula_uniforms(base_z, corr)
    else:
        raise ValueError(f"unknown assembly mode `{mode}`")
    return assemble_dst_bank_from_uniforms(count_banks, pa_proba, u)
