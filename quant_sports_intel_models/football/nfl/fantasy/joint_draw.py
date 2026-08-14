"""joint_draw.py — reusable cross-component JOINT-DRAW machinery (NF-W7b; the NF-W10 substrate).

WHY THIS EXISTS. NF-W7's assembled DST distribution won the score contest against every foil and
was CONSTRAINT_REFUSED by the pre-registered coverage(80) floor: the component banks were drawn
INDEPENDENTLY, but DST legs co-move, so the assembled sum under-disperses (cov 0.7603 vs 0.80 at
n=2,174, ≈4.6 SE — the DECLARED independence-simplification check firing). The remedy is a
dependence STRUCTURE over the existing marginals, never a refit of the marginals themselves.

THE MECHANISM. A Gaussian copula separates "what each component's distribution is" (the marginal
quantile banks — frozen, they won their contest) from "how the components co-move" (a correlation
matrix over the latent normals whose probability transforms drive each component's inverse-CDF
draw). With Σ = I the draw is EXACTLY the independent draw; any Σ changes only the JOINT law —
each leg's marginal is untouched by construction, because leg i's values are still produced by
inverse-CDF of a U(0,1) variate (Φ of a standard normal marginal of the MVN).

⭐ COMMON RANDOM NUMBERS: every arm transforms the SAME base normals (one `standard_normal`
block per fold), so arm-vs-arm score differences are dependence-structure differences, not
Monte-Carlo noise.

GENERALITY. Nothing in this module knows about DST: it takes correlation matrices, base normals
and per-leg PIT inputs. The same layer is what any future same-game / team-total / stack
construction (NF-W10) needs — a joint draw over legs whose marginals are separately certified.

⚖️ Research substrate — promotes nothing, publishes nothing, retrains nothing.
"""
from __future__ import annotations

import numpy as np

#: Below this many complete estimation rows the dependence estimate is REFUSED (raised), never
#: silently replaced by identity — an unevaluable estimate must not masquerade as "independent"
#: (NF1.7 (a): a check that did not run is not a pass).
MIN_ESTIMATION_ROWS = 50

#: Off-diagonal clip applied before any PSD repair — a scaled correlation may not demand |ρ| ≥ 1.
MAX_ABS_OFFDIAG = 0.99


# ── Correlation-matrix hygiene ──────────────────────────────────────────────────────────────────
def psd_clamp(corr: np.ndarray, floor: float = 1e-6) -> np.ndarray:
    """Nearest-PSD repair by eigenvalue flooring + renormalization to a unit diagonal. Idempotent
    (up to float noise) on a matrix that is already a valid correlation matrix."""
    c = np.asarray(corr, dtype=float)
    c = (c + c.T) / 2.0
    w, v = np.linalg.eigh(c)
    w = np.clip(w, floor, None)
    out = (v * w) @ v.T
    d = np.sqrt(np.diag(out))
    out = out / np.outer(d, d)
    np.fill_diagonal(out, 1.0)
    return out


def scale_offdiagonal(corr: np.ndarray, k: float) -> np.ndarray:
    """Every off-diagonal scaled by `k` (clipped to ±MAX_ABS_OFFDIAG), then PSD-repaired — the
    attenuation-probe transform (randomized PITs on zero-heavy discrete margins bias the
    estimated ρ toward 0; a pre-registered scale probes the magnitude axis)."""
    c = np.asarray(corr, dtype=float) * float(k)
    mask = ~np.eye(c.shape[0], dtype=bool)
    c[mask] = np.clip(c[mask], -MAX_ABS_OFFDIAG, MAX_ABS_OFFDIAG)
    np.fill_diagonal(c, 1.0)
    return psd_clamp(c)


def one_factor_corr(corr: np.ndarray, n_iter: int = 200) -> tuple[np.ndarray, np.ndarray]:
    """The nearest ONE-FACTOR structure Σ = λλᵀ + diag(1−λ²) — the shared-latent "game state"
    reading (opponent quality / script / pace as the single common factor every leg loads on,
    with its sign free so a leg may load negatively). Loadings by PRINCIPAL-AXIS iteration on
    communalities (⚠️ the raw principal eigenvector of Σ is NOT proportional to λ — the
    heterogeneous unique-variance diagonal shifts it; the iteration removes that diagonal, and
    on a true one-factor matrix it recovers λ exactly). Returns (Σ_factor, λ)."""
    c = psd_clamp(corr)
    w, v = np.linalg.eigh(c)
    lam = np.sqrt(max(float(w[-1]), 0.0)) * v[:, -1]
    lam = np.clip(lam, -MAX_ABS_OFFDIAG, MAX_ABS_OFFDIAG)
    for _ in range(n_iter):
        reduced = c.copy()
        np.fill_diagonal(reduced, lam ** 2)
        w, v = np.linalg.eigh(reduced)
        new = np.sqrt(max(float(w[-1]), 0.0)) * v[:, -1]
        if float(new @ lam) < 0:            # eigenvector sign is arbitrary — keep continuity
            new = -new
        new = np.clip(new, -MAX_ABS_OFFDIAG, MAX_ABS_OFFDIAG)
        if float(np.max(np.abs(new - lam))) < 1e-10:
            lam = new
            break
        lam = new
    out = np.outer(lam, lam)
    np.fill_diagonal(out, 1.0)
    return out, lam


# ── Uniform generators (the draw layer) ─────────────────────────────────────────────────────────
def independent_uniforms(base_z: np.ndarray) -> np.ndarray:
    """Φ of the untransformed base normals — BYTE-IDENTICAL to the Gaussian copula at Σ = I, which
    is the mechanical statement that the copula layer adds ONLY dependence."""
    from scipy.special import ndtr
    return ndtr(np.asarray(base_z, dtype=float))


def gaussian_copula_uniforms(base_z: np.ndarray, corr: np.ndarray) -> np.ndarray:
    """(…, L) iid N(0,1) base normals → (…, L) uniforms whose joint law is the Gaussian copula
    with correlation `corr`. Each output leg is marginally U(0,1) exactly (Φ of a standard-normal
    marginal), so downstream inverse-CDF draws keep every marginal bank untouched."""
    from scipy.special import ndtr
    chol = np.linalg.cholesky(psd_clamp(corr))
    return ndtr(np.asarray(base_z, dtype=float) @ chol.T)


def comonotone_uniforms(base_z: np.ndarray, flip: tuple[bool, ...]) -> np.ndarray:
    """The perfect-dependence degenerate: ONE shared uniform (leg 0 of the base normals) drives
    every leg; `flip[i]` gives leg i `1−u` so a leg whose POINTS decrease in its own outcome
    (e.g. a points-allowed tier) co-moves in the points direction. The maximal-dispersion
    anchor — registered to LOSE the score contest."""
    from scipy.special import ndtr
    u = ndtr(np.asarray(base_z, dtype=float)[..., 0])
    out = np.empty(np.asarray(base_z).shape[:-1] + (len(flip),))
    for i, fl in enumerate(flip):
        out[..., i] = 1.0 - u if fl else u
    return out


# ── PIT → latent scale (the estimation layer) ───────────────────────────────────────────────────
def zscores_from_uniforms(u: np.ndarray) -> np.ndarray:
    from scipy.special import ndtri
    return ndtri(np.clip(np.asarray(u, dtype=float), 1e-9, 1.0 - 1e-9))


def randomized_pit_categorical(proba: np.ndarray, y: np.ndarray, seed: int) -> np.ndarray:
    """Randomized PIT for an ordinal/categorical leg: u ~ U(F(b−1), F(b)) at the realized
    bucket b — the categorical twin of `randomized_pit_from_bank`."""
    rng = np.random.default_rng(seed)
    p = np.clip(np.asarray(proba, dtype=float), 1e-9, None)
    p = p / p.sum(axis=1, keepdims=True)
    cum = np.cumsum(p, axis=1)
    b = np.asarray(y, dtype=int)
    rows = np.arange(len(b))
    hi = cum[rows, b]
    lo = hi - p[rows, b]
    return lo + rng.uniform(size=len(b)) * (hi - lo)


def estimate_corr_from_z(z: np.ndarray, min_rows: int = MIN_ESTIMATION_ROWS) -> tuple[np.ndarray, int]:
    """Pearson correlation of latent z-scores over COMPLETE rows, PSD-repaired. REFUSES (raises)
    below `min_rows` — an unevaluable dependence estimate must never silently become 'independent'
    (NF1.7 (a)). Returns (Σ̂, n_rows_used)."""
    zz = np.asarray(z, dtype=float)
    ok = np.all(np.isfinite(zz), axis=1)
    zz = zz[ok]
    if zz.shape[0] < min_rows:
        raise ValueError(
            f"dependence estimation refused: {zz.shape[0]} complete rows < {min_rows} — an "
            f"unevaluable estimate must not masquerade as independence")
    return psd_clamp(np.corrcoef(zz.T)), int(zz.shape[0])


def spearman_gauss_corr(mat: np.ndarray, min_rows: int = MIN_ESTIMATION_ROWS) -> tuple[np.ndarray, int]:
    """Spearman rank correlation of RAW outcomes (ties midranked) mapped to the Gaussian-copula
    scale via ρ = 2·sin(π·ρ_s/6) — the unconditional co-movement read (includes the part the
    marginals' features explain; a deliberate second estimator scale)."""
    from scipy.stats import spearmanr
    m = np.asarray(mat, dtype=float)
    ok = np.all(np.isfinite(m), axis=1)
    m = m[ok]
    if m.shape[0] < min_rows:
        raise ValueError(
            f"dependence estimation refused: {m.shape[0]} complete rows < {min_rows} — an "
            f"unevaluable estimate must not masquerade as independence")
    rho = np.asarray(spearmanr(m).statistic, dtype=float)
    if rho.ndim == 0:                       # scipy returns a SCALAR for exactly two columns
        r = float(rho)
        rho = np.array([[1.0, r], [r, 1.0]])
    g = 2.0 * np.sin(np.pi * rho / 6.0)
    np.fill_diagonal(g, 1.0)
    return psd_clamp(g), int(m.shape[0])


# ── The movability analytic (NF-MARGIN2/NF-D20: prove the knob can move the gated statistic) ────
def weighted_sum_variance(corr: np.ndarray, sds: np.ndarray, weights: np.ndarray) -> float:
    """Var(Σ wᵢXᵢ) = (w∘σ)ᵀ Σ (w∘σ) — strictly increasing in any off-diagonal ρᵢⱼ whose
    wᵢσᵢwⱼσⱼ > 0, which is the analytic half of the arm-movability proof: the dependence knob
    changes the assembled sum's dispersion, hence its central-interval coverage."""
    a = np.asarray(weights, dtype=float) * np.asarray(sds, dtype=float)
    return float(a @ np.asarray(corr, dtype=float) @ a)
