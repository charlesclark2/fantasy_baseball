"""
MLB Batter Props — PHASE 2 §0.5 pricing bake-off (hits / HR / TB).

Executes `quant_sports_intel_models/baseball/edge_program/MLB_batter_props_phase2_preregistration.md`
EXACTLY — this script does not re-derive the design; every binding choice below cites the section
of the pre-registration that fixed it before the run.

  • Population        : regular-season, market-selected batter-games (prereg §1).
  • Folds             : 6 expanding half-season blocks 2023H2..2026H1, purged + embargoed at the
                        block boundary (prereg §1). 6 is a HARD ceiling (2023-05-03 archive floor,
                        verified on the correct endpoint) — no window widening can buy power.
                        2026H2 rows exist in the substrate (in-progress season) and are used
                        NOWHERE: not a registered eval fold, and expanding training never reaches
                        past the last eval start.
  • Primary metric    : CRPS, exact for discrete counts. ⛔ MAE is FORBIDDEN as primary (§3);
                        it is computed and READ every run so the NF-D11/D14 inversion is measured,
                        never predicted.
  • Market-blind      : book prices are never features (§5). The de-vigged consensus is graded
                        against, with a matched LEVEL-ONLY foil (NF-D15 g′) so any win over the
                        market is attributable. best_alpha = 0 — no edge/ROI claim anywhere.
  • HR constraint     : per-fold de-vigged coverage beside EVERY HR benchmark figure; a pooled HR
                        benchmark number is FORBIDDEN (§9.1) and the report builder RAISES on it.
  • Anchors           : oracle_floor (peeking, per-FORM per NF-D16 g‴; raises on failure per
                        NF1.7 a), degenerate_zero, degenerate_marginal, matched_n_candidate (§4).
                        Anchors are diagnostic and excluded from the DSR trial field (MH2.1 a);
                        the two degenerates are DECLARED FORWARD as DSR-CONV designed losers —
                        they stay in n_trials and are excluded from V (§7).
  • Deflation         : PBO (CSCV over the 5-arm eligible field) with the NF1.8 companions
                        (flip distribution / Bailey degradation / contender spread), DSR ≥ 0.95
                        via dsr_gate (observations = folds, measured trial_sharpes), calibrated
                        fold-consistency clause, BH-FDR across the 3 markets beside the pooled
                        single-hypothesis p (NF-D15 g″).
  • Nulls             : classified via cv_power.classify_null + the CONSTRAINT_REFUSED family
                        (NF-D18) which classify_null cannot represent (§8).

Candidate field (§6 — one configuration per pre-registered class, fixed a priori; no open search,
no post-hoc trimming; every configuration counts toward PBO/DSR):

  glm_poisson   Poisson GLM on the lagged rate features — the DIRECT-LEARNED FOIL.
  glm_nb        the same mean model + an in-fold NB2 dispersion (matched pair vs glm_poisson:
                the paired delta isolates the DISPERSION mechanism — NF-D10 g).
  hurdle_nb     logistic zero-hurdle × zero-truncated NB on the positives (matched pair vs
                glm_nb: the paired delta isolates the ZERO mechanism — registered §6.2 because
                HR is 88.4% zeros).
  lgbm_nb       LightGBM Poisson mean (fixed, pre-registered params — no tuning) + in-fold NB2
                dispersion: the gradient-boosted distributional class (§6.3). LightGBM rather
                than NGBoost avoids the unseeded-base-learner landmine outright; the global RNG
                is seeded anyway.
  pa_structural the PA-decomposition structural model (§6.4): PA-count distribution (empirical
                by batting slot) × per-PA outcome multinomial (binomial GLMs for 1B/2B/3B/HR
                rates) → EXACT compound pmf. This is the analytic form of
                `prop_pricing.draw_batter_bases_hits` — same structure, computed by convolution
                instead of Monte-Carlo, so it is deterministic and cheap.

USAGE
    # Smoke (HR market, last 2 folds, 30% row subsample — proves the path, ~1 min):
    uv run python betting_ml/scripts/batter_props_phase2_bakeoff.py --smoke \
        --substrate <local parquet>

    # Full run (all 3 markets × 6 folds; LAPTOP, ~10 min):
    uv run python betting_ml/scripts/batter_props_phase2_bakeoff.py \
        --substrate <local parquet or s3://...>

Outputs: ablation_results/mlb_batter_props_phase2_bakeoff.{md,json}
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import gammaln
from scipy.stats import ttest_rel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from betting_ml.scripts.e7_9_train_serve_consistency import dsr_gate  # noqa: E402
from betting_ml.utils.cv_power import (  # noqa: E402
    classify_null,
    fold_consistency_clause,
)
from betting_ml.utils.overfitting import pbo_cscv  # noqa: E402

SEED = 20260814

# ── the registered frame (prereg §1) ──────────────────────────────────────────
EVAL_FOLDS = ["2023H2", "2024H1", "2024H2", "2025H1", "2025H2", "2026H1"]
EMBARGO_DAYS = 10
MARKETS = ["batter_hits", "batter_home_runs", "batter_total_bases"]
# grid cap per market: >= max observed y (6 / 4 / 19) + headroom; tail mass folds into the cap bin
GRID_CAP = {"batter_hits": 9, "batter_home_runs": 6, "batter_total_bases": 24}

REAL_ARMS = ["glm_poisson", "glm_nb", "hurdle_nb", "lgbm_nb", "pa_structural"]
FOIL = "glm_poisson"
DEGENERATE_ARMS = ["degenerate_zero", "degenerate_marginal"]  # DSR-CONV: declared forward (§7)

DSR_BAR = 0.95
PBO_BAR = 0.20

# ── the pre-registered feature contract (§6: bounded, hypothesis-driven; no subset search) ────
NUMERIC_FEATURES = [
    "prev_pa_count_7d", "prev_pa_count_30d", "prev_games_30d",
    "prev_avg_30d", "prev_obp_30d", "prev_slg_30d", "prev_ops_30d",
    "prev_woba_30d", "prev_xwoba_30d", "prev_xba_30d", "prev_xslg_30d",
    "prev_k_pct_30d", "prev_bb_pct_30d", "prev_hard_hit_pct_30d", "prev_barrel_pct_30d",
    "prev_woba_7d", "prev_slg_7d", "prev_k_pct_7d",
    "prev_woba_std", "prev_slg_std", "prev_iso_std", "prev_k_pct_std",
    "batting_slot",
    "eb_woba", "eb_k_pct", "eb_bb_pct", "eb_iso", "eb_woba_uncertainty",
    "eb_hr_factor", "eb_singles_factor", "eb_doubles_triples_factor",
    "eb_woba_factor", "eb_so_factor", "eb_bb_factor",
]
# ⛔ MARKET-BLIND (§5): these columns exist on the substrate and MUST NEVER enter a design matrix.
FORBIDDEN_FEATURES = {
    "line_consensus", "line_std", "n_books", "n_books_two_sided",
    "p_over_consensus", "p_over_std", "y_over",
}


# ═══════════════════════════════════════════════════════════════════════════════
# folds
# ═══════════════════════════════════════════════════════════════════════════════

def half_label(dates: pd.Series, seasons: pd.Series) -> pd.Series:
    """'2024H1' style half-season labels (H1 = through June, matching the prereg blocks)."""
    m = pd.to_datetime(dates).dt.month
    return seasons.astype(int).astype(str) + np.where(m <= 6, "H1", "H2")


def make_folds(df: pd.DataFrame) -> list[dict]:
    """Expanding-window half-season folds, purged + embargoed at the block boundary (§1).

    Train = every row strictly before the eval block start, minus the EMBARGO_DAYS window
    immediately before it (the lagged rolling features straddle the boundary; the embargo
    removes the overlap). 2026H2 rows land in no fold on either side.
    """
    dates = pd.to_datetime(df["game_date"])
    halves = half_label(df["game_date"], df["season"])
    folds = []
    for f in EVAL_FOLDS:
        eval_mask = (halves == f).to_numpy()
        if eval_mask.sum() == 0:
            raise RuntimeError(f"registered fold {f} has zero rows — the substrate does not "
                               f"match the registration; refusing to silently skip a fold")
        eval_start = dates[eval_mask].min()
        train_mask = (dates < (eval_start - pd.Timedelta(days=EMBARGO_DAYS))).to_numpy()
        folds.append({"fold": f, "train": train_mask, "eval": eval_mask,
                      "eval_start": eval_start})
    return folds


# ═══════════════════════════════════════════════════════════════════════════════
# scoring — exact discrete CRPS + calibration reads
# ═══════════════════════════════════════════════════════════════════════════════

def crps_discrete(pmf: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Exact CRPS for an integer-count predictive on support 0..K (unit spacing).

    CRPS(F, y) = Σ_k (F(k) − 1[y ≤ k])².  `pmf` is (n, K+1) and each row must sum to ~1
    (tail mass folded into the cap bin by the pmf builders).
    """
    pmf = np.asarray(pmf, float)
    y = np.asarray(y, float)
    if pmf.ndim != 2 or len(y) != pmf.shape[0]:
        raise ValueError("pmf must be (n, K+1) aligned with y")
    rowsum = pmf.sum(axis=1)
    if not np.allclose(rowsum, 1.0, atol=1e-6):
        raise ValueError("pmf rows must sum to 1 — a non-normalized predictive is refused, "
                         "never nan-meaned past (NF-W3)")
    cdf = np.cumsum(pmf, axis=1)
    ks = np.arange(pmf.shape[1])[None, :]
    ind = (y[:, None] <= ks).astype(float)
    return np.sum((cdf - ind) ** 2, axis=1)


def point_median(pmf: np.ndarray) -> np.ndarray:
    """Predictive median (the point MAE actually rewards — the NF-D11 read)."""
    cdf = np.cumsum(np.asarray(pmf, float), axis=1)
    return np.argmax(cdf >= 0.5, axis=1).astype(float)


def randomized_pit(pmf: np.ndarray, y: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Randomized PIT for discrete predictives (E2.1-r): u = F(y−1) + V·p(y), V ~ U(0,1)."""
    pmf = np.asarray(pmf, float)
    y = np.asarray(y, int)
    n, K1 = pmf.shape
    cdf = np.cumsum(pmf, axis=1)
    yc = np.clip(y, 0, K1 - 1)
    f_ym1 = np.where(yc > 0, cdf[np.arange(n), yc - 1], 0.0)
    p_y = pmf[np.arange(n), yc]
    return f_ym1 + rng.uniform(size=n) * p_y


def pit_max_decile_dev(pit: np.ndarray) -> float:
    """Max absolute decile-frequency deviation from 0.1 — the E2.1-r flatness statistic."""
    h, _ = np.histogram(np.clip(pit, 0, 1 - 1e-12), bins=10, range=(0, 1))
    return float(np.max(np.abs(h / len(pit) - 0.1)))


def coverage_80(pmf: np.ndarray, y: np.ndarray) -> float:
    """Empirical coverage of the inclusive [q10, q90] interval — a FLOOR, never a target
    (E2.1-r: inclusive integer bounds inflate a correct model's figure; the gate is PIT flatness)."""
    cdf = np.cumsum(np.asarray(pmf, float), axis=1)
    lo = np.argmax(cdf >= 0.10, axis=1)
    hi = np.argmax(cdf >= 0.90, axis=1)
    y = np.asarray(y, float)
    return float(np.mean((y >= lo) & (y <= hi)))


# ═══════════════════════════════════════════════════════════════════════════════
# predictive-distribution builders
# ═══════════════════════════════════════════════════════════════════════════════

def poisson_pmf_grid(mu: np.ndarray, K: int) -> np.ndarray:
    """Poisson pmf on 0..K with tail mass folded into the cap bin."""
    mu = np.clip(np.asarray(mu, float), 1e-4, None)[:, None]
    ks = np.arange(K + 1)[None, :]
    logp = ks * np.log(mu) - mu - gammaln(ks + 1)
    pmf = np.exp(logp)
    pmf[:, K] = np.clip(1.0 - pmf[:, :K].sum(axis=1), 0.0, 1.0)
    return pmf


def nb_pmf_grid(mu: np.ndarray, alpha: float, K: int) -> np.ndarray:
    """NB2 pmf (Var = μ + α·μ²) on 0..K, tail folded. α → 0 degrades to Poisson."""
    if alpha < 1e-8:
        return poisson_pmf_grid(mu, K)
    mu = np.clip(np.asarray(mu, float), 1e-4, None)[:, None]
    r = 1.0 / alpha
    ks = np.arange(K + 1)[None, :]
    logp = (gammaln(ks + r) - gammaln(r) - gammaln(ks + 1)
            + r * np.log(r / (r + mu)) + ks * np.log(mu / (r + mu)))
    pmf = np.exp(logp)
    pmf[:, K] = np.clip(1.0 - pmf[:, :K].sum(axis=1), 0.0, 1.0)
    return pmf


def _nb2_negloglik(log_alpha: float, y: np.ndarray, mu: np.ndarray) -> float:
    alpha = float(np.exp(log_alpha))
    r = 1.0 / alpha
    ll = (gammaln(y + r) - gammaln(r) - gammaln(y + 1)
          + r * np.log(r / (r + mu)) + y * np.log(np.clip(mu, 1e-10, None) / (r + mu)))
    return -float(np.sum(ll))


def fit_nb_alpha(y: np.ndarray, mu: np.ndarray) -> float:
    """In-fold NB2 dispersion MLE given a fitted mean. Bounded scalar search on log α."""
    y = np.asarray(y, float)
    mu = np.clip(np.asarray(mu, float), 1e-4, None)
    res = minimize_scalar(_nb2_negloglik, bounds=(np.log(1e-6), np.log(50.0)),
                          args=(y, mu), method="bounded")
    if not res.success:  # NF1.7 (a): a fit that fails RAISES, it never returns a silent default
        raise RuntimeError(f"NB dispersion MLE failed: {res.message}")
    alpha = float(np.exp(res.x))
    # a boundary solution at the tiny end = Poisson is adequate; that's a value, not a failure
    return alpha


def _trunc_nb_negloglik(log_alpha: float, y: np.ndarray, mu: np.ndarray) -> float:
    """Zero-truncated NB2 negative loglik (support 1..∞): log pmf(y) − log(1 − pmf(0))."""
    alpha = float(np.exp(log_alpha))
    r = 1.0 / alpha
    logp = (gammaln(y + r) - gammaln(r) - gammaln(y + 1)
            + r * np.log(r / (r + mu)) + y * np.log(np.clip(mu, 1e-10, None) / (r + mu)))
    logp0 = r * np.log(r / (r + mu))
    return -float(np.sum(logp - np.log1p(-np.exp(logp0))))


def fit_trunc_nb_alpha(y_pos: np.ndarray, mu_pos: np.ndarray) -> float:
    y_pos = np.asarray(y_pos, float)
    mu_pos = np.clip(np.asarray(mu_pos, float), 1e-4, None)
    res = minimize_scalar(_trunc_nb_negloglik, bounds=(np.log(1e-6), np.log(50.0)),
                          args=(y_pos, mu_pos), method="bounded")
    if not res.success:
        raise RuntimeError(f"truncated-NB dispersion MLE failed: {res.message}")
    return float(np.exp(res.x))


def hurdle_pmf(p_pos: np.ndarray, mu_pos: np.ndarray, alpha: float, K: int) -> np.ndarray:
    """Hurdle predictive: P(0) = 1−p_pos; positives = zero-truncated NB renormalized × p_pos."""
    base = nb_pmf_grid(mu_pos, alpha, K)
    pos = base[:, 1:]
    denom = np.clip(pos.sum(axis=1, keepdims=True), 1e-12, None)
    pos = pos / denom
    out = np.empty_like(base)
    out[:, 0] = 1.0 - p_pos
    out[:, 1:] = p_pos[:, None] * pos
    return out


def marginal_pmf(y_train: np.ndarray, K: int, n_rows: int) -> np.ndarray:
    """`degenerate_marginal` (§4): the market-wide marginal count distribution, no per-batter
    content. Laplace-smoothed so no support point is exactly zero."""
    counts = np.bincount(np.clip(np.asarray(y_train, int), 0, K), minlength=K + 1) + 1.0
    p = counts / counts.sum()
    return np.tile(p, (n_rows, 1))


def zero_pmf(K: int, n_rows: int) -> np.ndarray:
    """`degenerate_zero` (§4): point mass at 0 — registered to LOSE CRPS and (on HR) WIN MAE."""
    out = np.zeros((n_rows, K + 1))
    out[:, 0] = 1.0
    return out


# ── PA-decomposition structural pmfs (analytic form of draw_batter_bases_hits) ────────────────

def binomial_mixture_pmf(pa_dist: np.ndarray, p_event: np.ndarray, K: int) -> np.ndarray:
    """pmf of Σ Bernoulli(p) over PA ~ pa_dist. pa_dist is (n, P+1) over PA = 0..P."""
    n, P1 = pa_dist.shape
    p = np.clip(np.asarray(p_event, float), 1e-6, 1 - 1e-6)[:, None]
    out = np.zeros((n, K + 1))
    ks = np.arange(K + 1)[None, :]
    for pa in range(P1):
        w = pa_dist[:, pa]
        if not np.any(w > 0):
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            logpmf = (gammaln(pa + 1) - gammaln(ks + 1) - gammaln(pa - ks + 1)
                      + ks * np.log(p) + (pa - ks) * np.log1p(-p))
        pmf_pa = np.where(ks <= pa, np.exp(logpmf), 0.0)
        out += w[:, None] * pmf_pa
    out[:, K] += np.clip(1.0 - out.sum(axis=1), 0.0, 1.0)
    return out


def compound_tb_pmf(pa_dist: np.ndarray, p1: np.ndarray, p2: np.ndarray,
                    p3: np.ndarray, phr: np.ndarray, K: int) -> np.ndarray:
    """Total-bases pmf: per-PA bases ∈ {0,1,2,3,4} with probs (1−Σp, p1, p2, p3, phr), compounded
    over the PA-count distribution by batched convolution (exact; no Monte-Carlo)."""
    n, P1 = pa_dist.shape
    probs = np.stack([np.clip(1 - (p1 + p2 + p3 + phr), 1e-9, 1),
                      np.clip(p1, 1e-9, 1), np.clip(p2, 1e-9, 1),
                      np.clip(p3, 1e-9, 1), np.clip(phr, 1e-9, 1)], axis=1)
    probs = probs / probs.sum(axis=1, keepdims=True)          # (n, 5)

    out = np.zeros((n, K + 1))
    out[:, 0] += pa_dist[:, 0] if P1 > 0 else 0.0
    # iterated batched polynomial multiplication: conv[k] after pa PAs
    conv = np.zeros((n, K + 1))
    conv[:, 0] = 1.0
    for pa in range(1, P1):
        new = np.zeros_like(conv)
        for b in range(5):                                     # kernel is tiny — loop it
            if b == 0:
                new += conv * probs[:, 0:1]
            else:
                new[:, b:] += conv[:, :K + 1 - b] * probs[:, b:b + 1]
                # bases pushed past the cap fold into the cap bin
                new[:, K] += conv[:, K + 1 - b:].sum(axis=1) * probs[:, b]
        conv = new
        out += pa_dist[:, pa][:, None] * conv
    out = out / np.clip(out.sum(axis=1, keepdims=True), 1e-12, None)
    return out


def pa_dist_by_slot(train: pd.DataFrame, max_pa: int = 9) -> dict:
    """Empirical PA-count distribution per batting slot (pooled fallback for null slot)."""
    dists = {}
    pooled = np.bincount(np.clip(train["pa"].astype(int), 0, max_pa), minlength=max_pa + 1)
    dists[None] = pooled / pooled.sum()
    for slot, grp in train.groupby("batting_slot"):
        c = np.bincount(np.clip(grp["pa"].astype(int), 0, max_pa), minlength=max_pa + 1)
        if c.sum() >= 200:                                     # thin slot → pooled
            dists[int(slot)] = c / c.sum()
    return dists


# ═══════════════════════════════════════════════════════════════════════════════
# design matrix
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Design:
    medians: pd.Series
    mean: np.ndarray = None
    std: np.ndarray = None


def build_design(df: pd.DataFrame, design: Design | None = None) -> tuple[np.ndarray, Design]:
    """Standardized design matrix on the pre-registered contract. Train medians impute; an
    eb-missing indicator carries the 4.6% posterior-less rows honestly."""
    bad = FORBIDDEN_FEATURES & set(NUMERIC_FEATURES)
    if bad:  # market-blind guard — a contract edit that adds a price column must be LOUD
        raise RuntimeError(f"market-blind violation: {bad} in the feature contract")
    X = df[NUMERIC_FEATURES].astype(float).copy()
    eb_missing = X["eb_woba"].isna().astype(float)
    hand = df["batter_hand"].fillna("R")
    if design is None:
        design = Design(medians=X.median(numeric_only=True))
    X = X.fillna(design.medians).fillna(0.0)
    X["eb_missing"] = eb_missing
    X["is_lhb"] = (hand == "L").astype(float)
    X["is_switch"] = (hand == "S").astype(float)
    M = X.to_numpy(float)
    if design.mean is None:
        design.mean = M.mean(axis=0)
        design.std = np.where(M.std(axis=0) > 1e-9, M.std(axis=0), 1.0)
    return (M - design.mean) / design.std, design


# ═══════════════════════════════════════════════════════════════════════════════
# candidate arms — each returns an eval pmf matrix given (train, eval) frames
# ═══════════════════════════════════════════════════════════════════════════════

def _fit_poisson_mu(Xtr, ytr, Xev):
    from sklearn.linear_model import PoissonRegressor
    m = PoissonRegressor(alpha=1e-4, max_iter=500, tol=1e-7)
    m.fit(Xtr, ytr)
    return m.predict(Xtr), m.predict(Xev)


def arm_glm_poisson(tr: pd.DataFrame, ev: pd.DataFrame, market: str) -> np.ndarray:
    K = GRID_CAP[market]
    Xtr, design = build_design(tr)
    Xev, _ = build_design(ev, design)
    _, mu_ev = _fit_poisson_mu(Xtr, tr["y_actual"].to_numpy(), Xev)
    return poisson_pmf_grid(mu_ev, K)


def arm_glm_nb(tr: pd.DataFrame, ev: pd.DataFrame, market: str) -> np.ndarray:
    K = GRID_CAP[market]
    Xtr, design = build_design(tr)
    Xev, _ = build_design(ev, design)
    mu_tr, mu_ev = _fit_poisson_mu(Xtr, tr["y_actual"].to_numpy(), Xev)
    alpha = fit_nb_alpha(tr["y_actual"].to_numpy(), mu_tr)
    return nb_pmf_grid(mu_ev, alpha, K)


def arm_hurdle_nb(tr: pd.DataFrame, ev: pd.DataFrame, market: str) -> np.ndarray:
    from sklearn.linear_model import LogisticRegression
    K = GRID_CAP[market]
    Xtr, design = build_design(tr)
    Xev, _ = build_design(ev, design)
    ytr = tr["y_actual"].to_numpy()
    pos = ytr > 0
    logit = LogisticRegression(C=100.0, max_iter=1000)
    logit.fit(Xtr, pos.astype(int))
    p_pos_ev = logit.predict_proba(Xev)[:, 1]
    mu_tr_pos, mu_ev = _fit_poisson_mu(Xtr[pos], ytr[pos], Xev)
    alpha = fit_trunc_nb_alpha(ytr[pos], mu_tr_pos)
    return hurdle_pmf(p_pos_ev, mu_ev, alpha, K)


def arm_lgbm_nb(tr: pd.DataFrame, ev: pd.DataFrame, market: str) -> np.ndarray:
    import lightgbm as lgb
    K = GRID_CAP[market]
    Xtr, design = build_design(tr)
    Xev, _ = build_design(ev, design)
    ytr = tr["y_actual"].to_numpy()
    # fixed, pre-registered configuration — ONE arm, no tuning search (§6; keeps the declared
    # field at 5 real arms so the DSR bar is a statement about the design, not a grid)
    m = lgb.LGBMRegressor(objective="poisson", n_estimators=400, learning_rate=0.05,
                          num_leaves=63, min_child_samples=50, subsample=0.8,
                          subsample_freq=1, colsample_bytree=0.9,
                          random_state=SEED, verbose=-1)
    m.fit(Xtr, ytr)
    mu_tr = np.clip(m.predict(Xtr), 1e-4, None)
    mu_ev = np.clip(m.predict(Xev), 1e-4, None)
    alpha = fit_nb_alpha(ytr, mu_tr)
    return nb_pmf_grid(mu_ev, alpha, K)


def _fit_rate_glm(tr: pd.DataFrame, Xtr: np.ndarray, Xev: np.ndarray, count_col: str) -> np.ndarray:
    """Per-PA outcome rate via binomial GLM with (successes, failures) counts."""
    import statsmodels.api as sm
    succ = tr[count_col].to_numpy(float)
    pa = tr["pa"].to_numpy(float)
    fail = np.clip(pa - succ, 0, None)
    Xc_tr = sm.add_constant(Xtr, has_constant="add")
    Xc_ev = sm.add_constant(Xev, has_constant="add")
    res = sm.GLM(np.column_stack([succ, fail]), Xc_tr,
                 family=sm.families.Binomial()).fit(maxiter=100)
    if not np.all(np.isfinite(res.params)):     # NF1.7 (a)
        raise RuntimeError(f"binomial rate GLM for {count_col} produced non-finite params")
    return np.asarray(res.predict(Xc_ev), float)


def arm_pa_structural(tr: pd.DataFrame, ev: pd.DataFrame, market: str) -> np.ndarray:
    K = GRID_CAP[market]
    Xtr, design = build_design(tr)
    Xev, _ = build_design(ev, design)
    p1 = _fit_rate_glm(tr, Xtr, Xev, "singles")
    p2 = _fit_rate_glm(tr, Xtr, Xev, "doubles")
    p3 = _fit_rate_glm(tr, Xtr, Xev, "triples")
    ph = _fit_rate_glm(tr, Xtr, Xev, "home_runs")
    dists = pa_dist_by_slot(tr)
    pa_dist = np.stack([
        dists.get(int(s) if pd.notna(s) else None, dists[None])
        if (pd.isna(s) or int(s) in dists) else dists[None]
        for s in ev["batting_slot"]
    ])
    if market == "batter_hits":
        return binomial_mixture_pmf(pa_dist, p1 + p2 + p3 + ph, K)
    if market == "batter_home_runs":
        return binomial_mixture_pmf(pa_dist, ph, K)
    return compound_tb_pmf(pa_dist, p1, p2, p3, ph, K)


ARM_FNS = {
    "glm_poisson": arm_glm_poisson,
    "glm_nb": arm_glm_nb,
    "hurdle_nb": arm_hurdle_nb,
    "lgbm_nb": arm_lgbm_nb,
    "pa_structural": arm_pa_structural,
}


# ═══════════════════════════════════════════════════════════════════════════════
# HR pooled-benchmark guard (§9.1 — binding)
# ═══════════════════════════════════════════════════════════════════════════════

def guard_no_pooled_hr_benchmark(market: str, scope: str) -> None:
    """A pooled HR market-benchmark figure is FORBIDDEN — the two-sided share collapses
    60.9→8.7% across seasons (market structure), so pooling averages incomparable regimes.
    Every HR benchmark emission must pass scope='per_fold' through this guard."""
    if market == "batter_home_runs" and scope != "per_fold":
        raise RuntimeError("pooled HR market-benchmark figure requested — forbidden by the "
                           "pre-registration (§9.1); report per-fold beside de-vigged coverage")


# ═══════════════════════════════════════════════════════════════════════════════
# market benchmark (§5) — graded, never fit against
# ═══════════════════════════════════════════════════════════════════════════════

def market_rows_mask(df: pd.DataFrame) -> np.ndarray:
    """Benchmark-eligible rows: a two-sided de-vigged consensus AND a half-integer line
    (integer lines can push; the stored y_over grades a push as under, which biases the
    market side — so push-able rows are excluded from the comparison, ~1.5% of rows)."""
    line = df["line_consensus"].to_numpy(float)
    half = np.abs(line - np.floor(line) - 0.5) < 1e-9
    return df["p_over_consensus"].notna().to_numpy() & half


def model_p_over(pmf: np.ndarray, line: np.ndarray) -> np.ndarray:
    """P(y > line) for half-integer lines: 1 − F(floor(line))."""
    cdf = np.cumsum(pmf, axis=1)
    k = np.clip(np.floor(line).astype(int), 0, pmf.shape[1] - 1)
    return 1.0 - cdf[np.arange(len(line)), k]


def brier(p: np.ndarray, y: np.ndarray) -> float:
    """= the exact Bernoulli CRPS (NF-W4): the right closed form for a binary target."""
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


# ═══════════════════════════════════════════════════════════════════════════════
# per-market bake-off
# ═══════════════════════════════════════════════════════════════════════════════

def run_market(df_m: pd.DataFrame, market: str, rng: np.random.Generator,
               folds_limit: int | None = None) -> dict:
    K = GRID_CAP[market]
    folds = make_folds(df_m)
    if folds_limit:
        folds = folds[-folds_limit:]

    per_fold: dict[str, list[float]] = {a: [] for a in REAL_ARMS + DEGENERATE_ARMS}
    mae_fold: dict[str, list[float]] = {a: [] for a in REAL_ARMS + DEGENERATE_ARMS}
    pit_store: dict[str, list[np.ndarray]] = {a: [] for a in REAL_ARMS}
    cov_fold: dict[str, list[float]] = {a: [] for a in REAL_ARMS}
    eval_pmfs: dict[str, dict[str, np.ndarray]] = {}
    bench_rows = []
    fold_meta = []

    for fd in folds:
        tr = df_m[fd["train"]]
        ev = df_m[fd["eval"]]
        y_ev = ev["y_actual"].to_numpy()
        t0 = time.time()
        eval_pmfs[fd["fold"]] = {}
        for arm in REAL_ARMS:
            pmf = ARM_FNS[arm](tr, ev, market)
            eval_pmfs[fd["fold"]][arm] = pmf
            per_fold[arm].append(float(np.mean(crps_discrete(pmf, y_ev))))
            mae_fold[arm].append(float(np.mean(np.abs(point_median(pmf) - y_ev))))
            pit_store[arm].append(randomized_pit(pmf, y_ev, rng))
            cov_fold[arm].append(coverage_80(pmf, y_ev))
        # degenerate anchors — SCORED every run, never reasoned about (§3/NF-D14)
        z = zero_pmf(K, len(ev))
        m = marginal_pmf(tr["y_actual"].to_numpy(), K, len(ev))
        for name, pmf in (("degenerate_zero", z), ("degenerate_marginal", m)):
            per_fold[name].append(float(np.mean(crps_discrete(pmf, y_ev))))
            mae_fold[name].append(float(np.mean(np.abs(point_median(pmf) - y_ev))))

        # market benchmark rows (per fold; HR is ONLY ever reported at this grain)
        bm = market_rows_mask(ev)
        n_two_sided = int(ev["p_over_consensus"].notna().sum())
        bench_rows.append({
            "fold": fd["fold"], "n_eval": len(ev), "n_two_sided": n_two_sided,
            "coverage_share": round(n_two_sided / max(len(ev), 1), 4),
            "n_benchmark": int(bm.sum()),
            "_mask": bm,
        })
        fold_meta.append({"fold": fd["fold"], "n_train": len(tr), "n_eval": len(ev),
                          "secs": round(time.time() - t0, 1)})

    mean_crps = {a: float(np.mean(v)) for a, v in per_fold.items()}
    leader = min(REAL_ARMS, key=lambda a: mean_crps[a])

    # ── anchors: per-form peeking oracle + matched-n (diagnostic; not in the DSR field) ──
    oracle, matched_n = {}, {}
    last = folds[-1]
    ev = df_m[last["eval"]]
    y_ev = ev["y_actual"].to_numpy()
    tr_halves = half_label(df_m["game_date"], df_m["season"])
    for arm in REAL_ARMS:
        pmf_o = ARM_FNS[arm](ev, ev, market)          # peeking: fit ON the eval fold (NF1.9 f)
        oracle[arm] = float(np.mean(crps_discrete(pmf_o, y_ev)))
    prior_half = EVAL_FOLDS[EVAL_FOLDS.index(last["fold"]) - 1] if \
        EVAL_FOLDS.index(last["fold"]) > 0 else "2023H1"
    tr_one = df_m[(tr_halves == prior_half).to_numpy()]
    pmf_mn = ARM_FNS[leader](tr_one, ev, market)
    matched_n[leader] = float(np.mean(crps_discrete(pmf_mn, y_ev)))
    oracle_respected = {a: per_fold[a][-1] >= oracle[a] - 1e-9 for a in REAL_ARMS}
    oracle_beats_matched_n = oracle[leader] <= matched_n[leader] + 1e-9

    # ── deflation ──
    n_folds = len(folds)
    skill = np.array(per_fold[FOIL]) - np.array(per_fold[leader])   # + = leader better
    # NF1.8 / NF-W2e: a BEATS/LOSES read must be three-way — a nested form whose fitted
    # dispersion hits the floor COLLAPSES onto the foil, and its ~1e-6 "lead" is a TIE, not a
    # win. The tie threshold is relative to the metric scale and far below any effect this
    # design could certify (the smallest real per-fold delta observed anywhere is ~1e-2).
    tie_with_foil = bool(abs(float(skill.mean())) < 1e-4 * mean_crps[FOIL])
    beats_foil = (leader != FOIL) and (float(skill.mean()) > 0) and not tie_with_foil
    wins = int(np.sum(skill > 0))
    clause = fold_consistency_clause(n_folds)
    if tie_with_foil or leader == FOIL:
        p_one = 1.0        # a tie carries no one-sided evidence; nan would poison BH
    else:
        t = ttest_rel(per_fold[FOIL], per_fold[leader])
        p_one = float(t.pvalue / 2) if skill.mean() > 0 else 1.0 - float(t.pvalue / 2)

    perf = -np.array([per_fold[a] for a in REAL_ARMS]).T           # folds × arms, higher better
    pbo = pbo_cscv(perf, higher_is_better=True, n_splits=n_folds) if n_folds >= 4 else None
    # NF1.8 companions
    flip, degradation, contender_spread = _pbo_companions(perf, REAL_ARMS)

    dsr = dsr_gate({a: per_fold[a] for a in REAL_ARMS + DEGENERATE_ARMS},
                   incumbent_arm=FOIL, leader_arm=leader,
                   n_trials=len(REAL_ARMS) + len(DEGENERATE_ARMS),
                   degenerate_arms=DEGENERATE_ARMS)

    # NF-D10 paired mechanism deltas (+ = the mechanism helped)
    paired = {
        "dispersion (glm_nb − glm_poisson)": [
            float(p - n) for p, n in zip(per_fold["glm_poisson"], per_fold["glm_nb"])],
        "zero_mechanism (hurdle_nb − glm_nb)": [
            float(n - h) for n, h in zip(per_fold["glm_nb"], per_fold["hurdle_nb"])],
    }

    # ── market benchmark grading (per fold; pooled only for non-HR) ──
    bench_out = []
    for fd, br in zip(folds, bench_rows):
        ev = df_m[fd["eval"]]
        bm = br.pop("_mask")
        if bm.sum() < 50:
            br.update({"note": "too few benchmark rows"})
            bench_out.append(br)
            continue
        evb = ev[bm]
        line = evb["line_consensus"].to_numpy(float)
        y_over = evb["y_over"].to_numpy(bool).astype(float)
        p_mkt = evb["p_over_consensus"].to_numpy(float)
        # matched LEVEL-ONLY foil (NF-D15 g′): the market minus the TRAINING-period mean gap
        trb = df_m[fd["train"]]
        trm = market_rows_mask(trb)
        gap = float(np.mean(trb[trm]["p_over_consensus"].to_numpy(float)
                            - trb[trm]["y_over"].to_numpy(bool).astype(float)))
        p_mkt_lvl = np.clip(p_mkt - gap, 0.0, 1.0)
        pmf_l = eval_pmfs[fd["fold"]][leader][bm]
        p_model = model_p_over(pmf_l, line)
        br.update({
            "brier_market": round(brier(p_mkt, y_over), 5),
            "brier_market_level_adj": round(brier(p_mkt_lvl, y_over), 5),
            "brier_model": round(brier(p_model, y_over), 5),
            "bias_market": round(float(np.mean(p_mkt - y_over)), 4),
            "bias_model": round(float(np.mean(p_model - y_over)), 4),
            "train_gap_applied": round(gap, 4),
        })
        bench_out.append(br)

    pooled_bench = None
    if market != "batter_home_runs":
        guard_no_pooled_hr_benchmark(market, "pooled")
        rows = [b for b in bench_out if "brier_model" in b]
        w = np.array([b["n_benchmark"] for b in rows], float)
        pooled_bench = {
            "brier_market": round(float(np.average([b["brier_market"] for b in rows], weights=w)), 5),
            "brier_market_level_adj": round(float(np.average(
                [b["brier_market_level_adj"] for b in rows], weights=w)), 5),
            "brier_model": round(float(np.average([b["brier_model"] for b in rows], weights=w)), 5),
        }
    else:
        guard_no_pooled_hr_benchmark(market, "per_fold")

    # calibration reads (model vs realized — market-independent, poolable for all legs)
    pit_pooled = {a: pit_max_decile_dev(np.concatenate(pit_store[a])) for a in REAL_ARMS}
    model_beats_market_folds = sum(
        1 for b in bench_out if "brier_model" in b and b["brier_model"] < b["brier_market"])
    bench_evaluated = sum(1 for b in bench_out if "brier_model" in b)

    return {
        "market": market, "n_folds": n_folds, "fold_meta": fold_meta,
        "per_fold_crps": {a: [round(v, 5) for v in per_fold[a]] for a in per_fold},
        "mean_crps": {a: round(v, 5) for a, v in mean_crps.items()},
        "mean_mae": {a: round(float(np.mean(mae_fold[a])), 5) for a in mae_fold},
        "leader": leader, "foil": FOIL,
        "beats_foil": beats_foil, "tie_with_foil": tie_with_foil, "skill_per_fold": [round(s, 5) for s in skill],
        "fold_wins": wins, "fold_consistency": {
            "required": clause.wins_required,
            "attainable": clause.attainable, "passed":
                bool(wins >= clause.wins_required) if clause.attainable else None},
        "p_one_sided": round(p_one, 5),
        "pbo": (round(pbo.pbo, 4) if pbo else None),
        "pbo_companions": {"flip_distribution": flip,
                           "bailey_degradation": degradation,
                           "contender_spread": contender_spread},
        "dsr": {k: dsr.get(k) for k in ("dsr", "observed_sr", "sr0", "var_trials_sr", "binds",
                                        "dsr_with_degenerates_in_V", "n_obs", "n_trials",
                                        "declared_degenerate_arms", "degenerate_trial_arms",
                                        "available", "note")},
        "paired_mechanism_deltas": {k: [round(x, 5) for x in v] for k, v in paired.items()},
        "anchors": {
            "oracle_floor_per_form_last_fold": {a: round(v, 5) for a, v in oracle.items()},
            "oracle_respected_last_fold": oracle_respected,
            "matched_n_candidate": {a: round(v, 5) for a, v in matched_n.items()},
            "oracle_beats_matched_n": bool(oracle_beats_matched_n),
            "degenerate_zero_loses_crps": bool(
                mean_crps["degenerate_zero"] > min(mean_crps[a] for a in REAL_ARMS)),
            "degenerate_marginal_loses_crps": bool(
                mean_crps["degenerate_marginal"] > min(mean_crps[a] for a in REAL_ARMS)),
            "mae_inversion_observed": bool(
                np.mean(mae_fold["degenerate_zero"]) <= min(
                    np.mean(mae_fold[a]) for a in REAL_ARMS)),
        },
        "pit_max_decile_dev_pooled": {a: round(v, 4) for a, v in pit_pooled.items()},
        "coverage_80_per_fold": {a: [round(v, 4) for v in cov_fold[a]] for a in REAL_ARMS},
        "market_benchmark_per_fold": bench_out,
        "market_benchmark_pooled": pooled_bench,
        "model_beats_market_folds": f"{model_beats_market_folds}/{bench_evaluated}",
    }


def _pbo_companions(perf: np.ndarray, arms: list[str]) -> tuple[dict, float, float]:
    """NF1.8: flip distribution (who wins the IS halves), Bailey's performance degradation
    (median OOS gap IS-winner vs OOS-best), contender (top-half) spread."""
    from itertools import combinations
    T, N = perf.shape
    half = T // 2
    flips: dict[str, int] = {}
    gaps = []
    for c in combinations(range(T), half):
        is_idx = list(c)
        oos_idx = [i for i in range(T) if i not in c]
        is_mean = perf[is_idx].mean(axis=0)
        oos_mean = perf[oos_idx].mean(axis=0)
        w = int(np.argmax(is_mean))
        flips[arms[w]] = flips.get(arms[w], 0) + 1
        gaps.append(float(oos_mean.max() - oos_mean[w]))
    means = perf.mean(axis=0)
    order = np.sort(means)[::-1]
    top = order[: max(2, N // 2)]
    spread = float((top[0] - top[-1]) / abs(top[0])) if top[0] != 0 else float("nan")
    return flips, float(np.median(gaps)), round(spread, 5)


# ═══════════════════════════════════════════════════════════════════════════════
# verdicts + report
# ═══════════════════════════════════════════════════════════════════════════════

def market_verdict(res: dict, bh_pass: bool | None) -> dict:
    """Gate stack per the prereg §7/§8 (DoD): leader beats foil on OOS CRPS + PBO + DSR +
    fold consistency (+ BH across the 3 markets). A failure is CLASSIFIED, never collapsed."""
    gates = {
        "beats_foil": res["beats_foil"],
        "pbo_lt_0.2": (res["pbo"] is not None and res["pbo"] < PBO_BAR),
        "dsr_ge_0.95": bool(res["dsr"]["available"] and res["dsr"]["dsr"] >= DSR_BAR),
        "fold_consistency": bool(res["fold_consistency"]["passed"]),
        "bh_fdr": bh_pass,
    }
    all_pass = all(bool(v) for v in gates.values())
    out = {"gates": gates, "verdict": "SHIP_CANDIDATE (research-only, deploy-held)" if all_pass
           else "NULL"}
    if not all_pass:
        avail = bool(res["dsr"].get("available"))
        nv = classify_null(
            metric=f"{res['market']}:crps", n_folds=res["n_folds"],
            n_arms=res["dsr"]["n_trials"], beats_foil=res["beats_foil"],
            observed_sr=res["dsr"].get("observed_sr") if avail else None,
            var_trials_sr=res["dsr"].get("var_trials_sr") if avail else None,
            fold_wins=res["fold_wins"], p_one_sided=res["p_one_sided"],
            bh_cutoff=None,
            degenerates_excluded_from_v=(res["dsr"].get("binds")
                                         == "degenerate_excluded_whole_field"),
        )
        out["null_state"] = nv.state
        out["null_reason"] = nv.reason
        out["retest_trigger"] = nv.retest_trigger
    return out


def bh_fdr(pvals: dict[str, float], q: float = 0.05) -> dict[str, bool]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    passed, cut = {}, 0.0
    for i, (k, p) in enumerate(items, start=1):
        if p <= q * i / m:
            cut = q * i / m
    for k, p in items:
        passed[k] = p <= cut and cut > 0
    return passed


def write_report(results: dict, out_dir: Path, smoke: bool) -> Path:
    ts = datetime.now(timezone.utc).isoformat()
    name = "mlb_batter_props_phase2_bakeoff" + ("_smoke" if smoke else "")
    (out_dir / f"{name}.json").write_text(json.dumps(results, indent=2, default=str))

    L = []
    L.append("# MLB Batter Props — Phase 2 §0.5 pricing bake-off (hits / HR / TB)\n")
    L.append(f"*Generated {ts}*  ·  `best_alpha = 0` — no edge/ROI/win-rate claim; "
             "market-blind (book prices are never features); deploy-held, research-only.\n")
    L.append("Pre-registration: `quant_sports_intel_models/baseball/edge_program/"
             "MLB_batter_props_phase2_preregistration.md` — executed as registered "
             "(6 half-season folds = a HARD data ceiling; regular-season only).\n")
    for mkt, res in results["markets"].items():
        v = results["verdicts"][mkt]
        L.append(f"\n## {mkt} — **{v['verdict']}**")
        if "null_state" in v:
            L.append(f"\n**Null state: `{v['null_state']}`** — {v['null_reason']}")
            if v.get("retest_trigger"):
                L.append(f"\nRe-test trigger: {v['retest_trigger']}")
        L.append(f"\nGates: {v['gates']}")
        def _f(x):
            return f"{x:.4f}" if isinstance(x, (int, float)) and np.isfinite(x) else "UNDEFINED"
        L.append(f"\nLeader **{res['leader']}** vs foil `{res['foil']}` — mean OOS CRPS "
                 f"{res['mean_crps'][res['leader']]} vs {res['mean_crps'][res['foil']]}; "
                 f"fold wins {res['fold_wins']}/{res['n_folds']} "
                 f"(required {res['fold_consistency']['required']}); "
                 f"p(one-sided) {res['p_one_sided']}; PBO {res['pbo']}; "
                 f"DSR {_f(res['dsr']['dsr'])} (binds: {res['dsr'].get('binds')}; "
                 f"with-degenerates-in-V {_f(res['dsr'].get('dsr_with_degenerates_in_V'))})")
        if res["dsr"].get("note"):
            L.append(f"\nDSR note: {res['dsr']['note']}")
        L.append("\n| arm | mean CRPS | mean MAE | PIT max-dec dev |")
        L.append("|---|---|---|---|")
        for a in REAL_ARMS:
            L.append(f"| {a}{' (foil)' if a == FOIL else ''} | {res['mean_crps'][a]} | "
                     f"{res['mean_mae'][a]} | {res['pit_max_decile_dev_pooled'][a]} |")
        for a in DEGENERATE_ARMS:
            L.append(f"| {a} (degenerate anchor) | {res['mean_crps'][a]} | "
                     f"{res['mean_mae'][a]} | — |")
        anc = res["anchors"]
        L.append(f"\nAnchors: degenerate_zero loses CRPS = {anc['degenerate_zero_loses_crps']}; "
                 f"degenerate_marginal loses CRPS = {anc['degenerate_marginal_loses_crps']}; "
                 f"**MAE inversion observed = {anc['mae_inversion_observed']}** "
                 f"(the NF-D11 read — measured, not predicted); "
                 f"oracle beats matched-n = {anc['oracle_beats_matched_n']}")
        L.append(f"\nPaired mechanism deltas (NF-D10; + = mechanism helped, per fold): "
                 f"{res['paired_mechanism_deltas']}")
        L.append("\nPer-fold CRPS:")
        L.append("\n| fold | " + " | ".join(REAL_ARMS + DEGENERATE_ARMS) + " |")
        L.append("|---|" + "---|" * (len(REAL_ARMS) + len(DEGENERATE_ARMS)))
        for i, fm in enumerate(res["fold_meta"]):
            row = [str(res["per_fold_crps"][a][i]) for a in REAL_ARMS + DEGENERATE_ARMS]
            L.append(f"| {fm['fold']} (n={fm['n_eval']}) | " + " | ".join(row) + " |")

        # market benchmark — HR strictly per fold
        guard_no_pooled_hr_benchmark(mkt, "per_fold")
        L.append("\nDe-vigged market benchmark (graded, never fit against; leader's P(over) "
                 "vs consensus; level-adj = NF-D15 matched level-only foil):")
        L.append("\n| fold | two-sided coverage | n bench | Brier market | Brier lvl-adj | "
                 "Brier model | bias mkt | bias model |")
        L.append("|---|---|---|---|---|---|---|---|")
        for b in res["market_benchmark_per_fold"]:
            if "brier_model" in b:
                L.append(f"| {b['fold']} | {b['coverage_share']:.1%} | {b['n_benchmark']} | "
                         f"{b['brier_market']} | {b['brier_market_level_adj']} | "
                         f"{b['brier_model']} | {b['bias_market']} | {b['bias_model']} |")
            else:
                L.append(f"| {b['fold']} | {b['coverage_share']:.1%} | {b['n_benchmark']} | "
                         f"— | — | — | — | — |")
        if mkt == "batter_home_runs":
            L.append("\n⚠️ HR benchmark figures are PER-FOLD ONLY by registration (§9.1): the "
                     "two-sided share collapses 60.9→8.7% by season (books moved to one-way "
                     "anytime-HR; 2026H1 is Pinnacle-dominated = a DIFFERENT estimand). A pooled "
                     "HR figure would average incomparable regimes and is forbidden.")
        elif res["market_benchmark_pooled"]:
            L.append(f"\nPooled (row-weighted): {res['market_benchmark_pooled']}  ·  "
                     f"model beats market in {res['model_beats_market_folds']} folds")
        L.append(f"\nCoverage-80 FLOOR per fold (never a target — E2.1-r): "
                 f"{res['coverage_80_per_fold'][res['leader']]} (leader)")
    L.append(f"\n## Cross-market multiplicity (NF-D15 g″)\n")
    L.append(f"BH-FDR (q=0.05, 3 hypotheses): {results['bh_fdr']}  ·  "
             f"one-sided p per market: {results['p_values']}")
    L.append("\n---\n*Folds are the registered 2023H2..2026H1 blocks — a HARD ceiling (the "
             "2023-05-03 archive floor was verified on the correct endpoint; no spend widens "
             "the window). Regular-season only; postseason application is extrapolation. "
             "Population is market-selected (books quote better hitters).*\n")
    p = out_dir / f"{name}.md"
    p.write_text("\n".join(L))
    return p


# ═══════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════

def load_substrate(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df[df["y_actual"].notna()].copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--substrate", default=(
        "s3://baseball-betting-ml-artifacts/baseball/research/batter_prop_substrate/"
        "batter_prop_substrate_v1.parquet"))
    ap.add_argument("--markets", nargs="+", default=MARKETS, choices=MARKETS)
    ap.add_argument("--smoke", action="store_true",
                    help="HR market only, last 2 folds, 30%% row subsample")
    ap.add_argument("--out-dir", default="ablation_results")
    args = ap.parse_args()

    np.random.seed(SEED)                       # the NGBoost-class global-RNG lesson (§6.3)
    rng = np.random.default_rng(SEED)

    df = load_substrate(args.substrate)
    markets = ["batter_home_runs"] if args.smoke else args.markets
    folds_limit = 2 if args.smoke else None

    results: dict = {"generated": datetime.now(timezone.utc).isoformat(),
                     "smoke": args.smoke, "seed": SEED,
                     "substrate": args.substrate, "markets": {}, "verdicts": {}}
    t0 = time.time()
    for mkt in markets:
        d = df[df["market_key"] == mkt]
        if args.smoke:
            d = d.sample(frac=0.3, random_state=SEED).sort_values("game_date")
        print(f"── {mkt}: {len(d)} rows")
        results["markets"][mkt] = run_market(d, mkt, rng, folds_limit)
        print(f"   leader={results['markets'][mkt]['leader']} "
              f"mean_crps={results['markets'][mkt]['mean_crps']}")

    results["p_values"] = {m: results["markets"][m]["p_one_sided"] for m in results["markets"]}
    bh = bh_fdr(results["p_values"]) if len(results["p_values"]) == 3 else \
        {m: None for m in results["p_values"]}
    results["bh_fdr"] = bh
    for mkt in results["markets"]:
        results["verdicts"][mkt] = market_verdict(results["markets"][mkt], bh[mkt])

    out = write_report(results, Path(args.out_dir), args.smoke)
    print(f"\n✅ report → {out}   ({time.time() - t0:.0f}s total)")
    for mkt, v in results["verdicts"].items():
        print(f"   {mkt}: {v['verdict']}" + (f"  [{v.get('null_state')}]"
                                             if "null_state" in v else ""))


if __name__ == "__main__":
    main()
