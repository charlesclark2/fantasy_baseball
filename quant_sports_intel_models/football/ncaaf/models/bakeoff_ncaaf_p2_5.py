"""bakeoff_ncaaf_p2_5.py — NCAAF-P2.5: the total / joint-distribution SHAPE bake-off.

WHAT THIS STORY IS
------------------
P1.4 built the joint (margin, total) predictive and P2.1-S1 repointed its MEAN. What remains is the
conditional predictive SHAPE. This harness scores the ten pre-registered shape families
(`p2_5_shapes.SHAPES`, doc §4.1) against the SERVED config on the SAME season-forward purged folds
P1.4 and P2.1 use, and decides under the pre-registered deflation gates.

⭐ THE MEAN IS FROZEN (pre-registration §1). Every arm consumes the same per-game (μ_margin, μ_total)
from the served `ridge / strength_pace` config, refit walk-forward per fold. Arms differ ONLY in the
shape around it, which (a) is the story's scope, (b) makes ΔCRPS attributable to shape alone, and
(c) keeps the field COHERENT — the thing `SR0` is actually taxed by (MH2.5 / NF-W6b-C).

⭐ THE FOIL IS THE **SERVED** CONFIG, NOT THE STORY CARD'S NUMBER. The card cites total PITdev
0.0218; that is `ncaaf_p1_4_calibration.json` (contract `strength_only`, superseded). What SERVES is
`ncaaf_s1_serve_calibration.json` (contract `strength_pace`) at **0.0173, PIT-flat**. Measuring
against the card would hand every candidate a 0.0045 head start it did not earn, so the foil is
refit here and REPRODUCTION-CHECKED against the served artifact (`--stage battery` gate R).

TWO RETURN SERIES, DECLARED SEPARATELY (the NCAAF-P2.1-S1 lesson): PBO runs CSCV over the per-BUCKET
matrix; the BINDING DSR runs on the per-FOLD matched-pair series. Sharing one silently taxes DSR.

ANCHORS ARE DIAGNOSTIC, NEVER TRIALS (MH2.1 a): `n_trials` = the declared field of 10; `V` is
measured over the real arms only. An anchor that polices the metric must not set the gate's own bar.

USAGE (LAPTOP; SF-free, DuckDB/parquet only, off the MLB serving lane)
---------------------------------------------------------------------
    uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_5 \
        --stage battery [--max-folds 2 --smoke]
    uv run python -m quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_5 --stage decide

HONEST FRAME: `best_alpha = 0`. A better-shaped predictive is calibration/product value, never an
edge claim. Market-blind. NCAAF is not served, so any survivor is a research-artifact re-point.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from betting_ml.utils.cv import PurgedWalkForwardSplit  # noqa: E402
from betting_ml.utils.market_blind import assert_market_blind  # noqa: E402
from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv  # noqa: E402
from quant_sports_intel_models.football.ncaaf.models import p2_5_shapes as shp  # noqa: E402
from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (  # noqa: E402
    JointDispersion,
    derive_markets,
    draw_joint,
    fit_gaussian_dispersion,
    fit_strength_posterior_scale,
    interval_coverage,
    sample_joint_normal,
    score_calibration,
    strength_posterior_sigma,
)
from quant_sports_intel_models.football.ncaaf.models.p2_1_blocks import (  # noqa: E402
    PACE_COMPOSITE_COLS,
    derive_pace_composites,
)

_STORY = "NCAAF-P2.5"
_MODELS_DIR = Path(__file__).resolve().parent
_RESULTS_DIR = _MODELS_DIR.parent / "ablation_results"
_CACHE_PATH = _PROJECT_ROOT / "betting_ml" / "data" / "cache" / "ncaaf_p1_4_game_matrix.parquet"

_SCORES_JSON = _RESULTS_DIR / "ncaaf_p2_5_shape_scores.json"
_DECISION_JSON = _RESULTS_DIR / "ncaaf_p2_5_distribution_shape.json"
_DECISION_MD = _RESULTS_DIR / "ncaaf_p2_5_distribution_shape.md"
#: the SERVED calibration record this story's foil must reproduce (gate R).
_SERVED_CALIB = _RESULTS_DIR / "ncaaf_s1_serve_calibration.json"

#: ⛔ DECIDED-STORY PATHS THIS STORY MUST NEVER WRITE. A run that overwrites a decided story's
#: audit trail destroys evidence, and it has happened here before (the P2.1-S1-serve defect-3
#: class — caught by `git status`, not by a test). Named so a guard can assert it mechanically.
_DECIDED_STORY_PATHS_NEVER_WRITTEN: tuple[str, ...] = (
    "ncaaf_p1_4_calibration.json", "ncaaf_p1_4_calibration.md",
    "ncaaf_p1_4_game_bakeoff.json", "ncaaf_p1_4_game_bakeoff.md", "ncaaf_p1_4_game_model.md",
    "ncaaf_s1_serve_calibration.json", "ncaaf_s1_serve_calibration.md",
    "ncaaf_p2_1_s1_pace.json", "ncaaf_p2_1_s1_pace.md", "ncaaf_p2_1_s1_pace_scores.json",
    "ncaaf_p2_1_s1b_composite.json", "ncaaf_p2_1_s1b_composite.md",
    "ncaaf_p2_1_structural_battery.json", "ncaaf_p2_1_structural_battery.md",
    "ncaaf_p2_5_preregistration.md",
)

# ── pre-registered constants (⛔ none re-chosen after the run) ──────────────────────────────────
_MARGIN, _TOTAL, _YEAR, _DATE = "label_home_margin", "label_total_points", "season", "game_date"
_HOME_PTS, _AWAY_PTS = "label_home_points", "label_away_points"
_STRENGTH_PREFIXES = ("home_strength", "away_strength", "strength_margin_diff")
_SEED = 42
_RIDGE_ALPHA = 10.0            # the served P1.4/S1 reference learner
_SERVED_FORM = "strength_posterior"
_N_DRAWS = 4_000               # inherited from P2.1
_N_SLICES = 4                  # PBO buckets per fold
_PBO_GATE, _DSR_GATE, _FDR_ALPHA = 0.20, 0.95, 0.05
_TIE_BAND = 1e-3               # inherited from P2.1 — ⛔ not re-chosen here
_CALIB_TARGET, _CALIB_TOL = 0.80, 0.02
_PIT_DEV_GATE, _PIT_MEAN_GATE = 0.025, 0.020    # `totals_distribution`'s own flatness band
_C2_MARGIN = 0.0010            # C2: how much better than the foil's total PITdev counts as repair
#: gate R — the foil's refit σ must reproduce the SERVED artifact this closely (points).
_REPRO_TOL_SIGMA = 0.25

_T0 = time.time()


def _log(msg: str, indent: int = 0) -> None:
    print(f"[+{time.time() - _T0:6.0f}s] {'  ' * indent}{msg}", file=sys.stderr, flush=True)


# ===========================================================================
# Cache + folds — the EXACT P1.4/P2.1 structure
# ===========================================================================

def load_cache() -> tuple[pd.DataFrame, dict]:
    """The one-pull P1.4 cache + the S1b-certified pace composites derived by the SHARED function.

    ⭐ `derive_pace_composites` is the same call the serving assemble makes, so the contract resolved
    here is byte-identical to the certified one — two renderers of one field would be two rule sets
    (E9.61). The chosen path and its mtime are LOGGED, because a story that reads an on-disk artifact
    cannot be validated in a fresh worktree unless the artifact it picked is visible (the board-regen
    artifact-precedence lesson).
    """
    if not _CACHE_PATH.exists():
        raise SystemExit(
            f"[{_STORY}] no cache at {_CACHE_PATH}. It is gitignored, so a fresh worktree does not "
            "have it (NF-INFRA1). Copy it from the main checkout, or re-run P1.4 `--assemble`.")
    import datetime as _dt
    mtime = _dt.datetime.fromtimestamp(_CACHE_PATH.stat().st_mtime).isoformat(timespec="seconds")
    _log(f"cache {_CACHE_PATH} (mtime {mtime}, {_CACHE_PATH.stat().st_size / 1e6:.1f} MB)")
    df = pd.read_parquet(_CACHE_PATH)
    df[_DATE] = pd.to_datetime(df[_DATE], errors="coerce")
    df = df[df["label_is_completed"] == True].reset_index(drop=True)  # noqa: E712
    df["game_year"] = df[_YEAR].astype(int)
    df = derive_pace_composites(df)
    return df, {"cache": str(_CACHE_PATH), "cache_mtime": mtime, "n_games": int(len(df))}


def served_columns(df: pd.DataFrame) -> list[str]:
    """The SERVED `strength_pace` contract resolved on this frame (S1-serve's shipped contract)."""
    strength = [c for c in df.columns
                if any(c.startswith(p) for p in _STRENGTH_PREFIXES)
                and str(df[c].dtype) not in ("object", "category")]
    pace = [c for c in PACE_COMPOSITE_COLS if c in df.columns]
    if len(pace) != len(PACE_COMPOSITE_COLS):
        raise SystemExit(
            f"[{_STORY}] the served contract needs {list(PACE_COMPOSITE_COLS)}; found {pace}. A "
            "missing pace column must RAISE — scoring a pace-free foil under a pace contract would "
            "measure every candidate against the WRONG incumbent (NF1.7 a).")
    return strength + pace


@dataclass
class Fold:
    eval_year: int
    tr: pd.DataFrame
    ev: pd.DataFrame
    inner_tr: pd.DataFrame
    inner_ho: pd.DataFrame


def build_folds(df: pd.DataFrame, max_folds: int | None = None) -> list[Fold]:
    """Season-forward PURGED walk-forward, purge band by calendar DATE.

    ⛔ Ordered by `season_order_week` / `game_date`, NEVER raw `week` — the postseason `week`=1
    collision is the P1.1 leak this whole vertical is built to avoid.
    """
    df = df.sort_values([_YEAR, "season_order_week", _DATE]).reset_index(drop=True)
    splitter = PurgedWalkForwardSplit(min_train_seasons=3, year_col="game_year", date_col=_DATE)
    folds: list[Fold] = []
    for tr_idx, ev_idx in splitter.split(df, feature_cols=None):
        tr, ev = df.loc[tr_idx].reset_index(drop=True), df.loc[ev_idx].reset_index(drop=True)
        yr = int(ev["game_year"].mode().iloc[0])
        inner_year = int(tr["game_year"].max())
        mask = (tr["game_year"] == inner_year).to_numpy()
        if mask.sum() < 150 or (~mask).sum() < 300:
            mask = np.zeros(len(tr), bool)
            mask[int(len(tr) * 0.85):] = True
        folds.append(Fold(yr, tr, ev, tr[~mask].reset_index(drop=True), tr[mask].reset_index(drop=True)))
        if max_folds and len(folds) >= max_folds:
            break
    return folds


def _matrices(a: pd.DataFrame, b: pd.DataFrame, cols: list[str]) -> tuple[np.ndarray, np.ndarray]:
    def num(f: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({c: pd.to_numeric(f[c], errors="coerce").astype("float64") for c in cols},
                            index=f.index)
    A, B = num(a), num(b)
    m = A.mean(numeric_only=True)
    return A.fillna(m).fillna(0.0).to_numpy(float), B.fillna(m).fillna(0.0).to_numpy(float)


def _strength_var(frame: pd.DataFrame, impute: float | None = None) -> np.ndarray:
    sv = np.zeros(len(frame))
    for c in ("home_strength_margin_sd", "away_strength_margin_sd"):
        s = pd.to_numeric(frame[c], errors="coerce") if c in frame.columns \
            else pd.Series(np.nan, index=frame.index)
        if impute is not None:
            s = s.fillna(np.sqrt(max(impute, 0.0) / 2.0))
        sv = sv + np.nan_to_num(s.to_numpy(float)) ** 2
    return sv


def _ridge(X_tr, y_m, y_t, X_ev, alpha: float = _RIDGE_ALPHA):
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler()
    A, B = sc.fit_transform(X_tr), sc.transform(X_ev)
    return (Ridge(alpha=alpha).fit(A, y_m).predict(B),
            Ridge(alpha=alpha).fit(A, y_t).predict(B))


# ===========================================================================
# The FROZEN-MEAN fold context — computed ONCE per fold, shared by every arm
# ===========================================================================

@dataclass
class FoldContext:
    """Everything every arm shares: the frozen μ, the leakage-safe residuals, and the drivers.

    Computing this once is not only a cost saving — it is what MAKES the mean frozen. If each arm
    refit its own mean, a "shape" comparison would silently carry a mean difference.
    """
    eval_year: int
    mu_m_ev: np.ndarray
    mu_t_ev: np.ndarray
    y_m_ev: np.ndarray
    y_t_ev: np.ndarray
    # inner-holdout (the leakage-safe fit set for every shape parameter)
    mu_m_ho: np.ndarray
    mu_t_ho: np.ndarray
    y_m_ho: np.ndarray
    y_t_ho: np.ndarray
    resid_m: np.ndarray
    resid_t: np.ndarray
    sv_ho: np.ndarray
    sv_ev: np.ndarray
    Z_ho: np.ndarray
    Z_ev: np.ndarray
    driver_names: list[str]
    # the incumbent's fitted dispersion (the base scale every arm is allowed)
    disp: JointDispersion
    sig_m_ev: np.ndarray
    sig_t_ev: np.ndarray
    sig_m_ho: np.ndarray
    sig_t_ho: np.ndarray
    train_home_pts: np.ndarray
    train_away_pts: np.ndarray


def build_context(fold: Fold, cols: list[str]) -> FoldContext:
    assert_market_blind(cols, context=f"{_STORY} served contract fold {fold.eval_year}")
    X_tr, X_ev = _matrices(fold.tr, fold.ev, cols)
    X_itr, X_iho = _matrices(fold.inner_tr, fold.inner_ho, cols)
    y_m_tr, y_t_tr = fold.tr[_MARGIN].to_numpy(float), fold.tr[_TOTAL].to_numpy(float)
    y_m_ev, y_t_ev = fold.ev[_MARGIN].to_numpy(float), fold.ev[_TOTAL].to_numpy(float)
    y_m_ho, y_t_ho = fold.inner_ho[_MARGIN].to_numpy(float), fold.inner_ho[_TOTAL].to_numpy(float)

    mu_m_ev, mu_t_ev = _ridge(X_tr, y_m_tr, y_t_tr, X_ev)
    mu_m_ho, mu_t_ho = _ridge(X_itr, fold.inner_tr[_MARGIN].to_numpy(float),
                              fold.inner_tr[_TOTAL].to_numpy(float), X_iho)
    rm, rt = y_m_ho - mu_m_ho, y_t_ho - mu_t_ho

    sv_imp = float(np.nanmedian(_strength_var(fold.tr)))
    sv_ho = _strength_var(fold.inner_ho, impute=sv_imp)
    sv_ev = _strength_var(fold.ev, impute=sv_imp)

    # the incumbent's held-out dispersion — the SHIPPED estimators, so the foil is what serves
    g = fit_gaussian_dispersion(rm, rt)
    disp = JointDispersion(sigma_margin=g.sigma_margin, sigma_total=g.sigma_total, rho=g.rho)
    disp.sigma0_margin, disp.k_margin = fit_strength_posterior_scale(rm, sv_ho)
    disp.sigma0_total, disp.k_total = fit_strength_posterior_scale(rt, sv_ho)
    sig_m_ev = strength_posterior_sigma(disp.sigma0_margin, disp.k_margin, sv_ev)
    sig_t_ev = strength_posterior_sigma(disp.sigma0_total, disp.k_total, sv_ev)
    sig_m_ho = strength_posterior_sigma(disp.sigma0_margin, disp.k_margin, sv_ho)
    sig_t_ho = strength_posterior_sigma(disp.sigma0_total, disp.k_total, sv_ho)

    Z_ho, Z_ev, names = shp.build_driver_matrix(
        fold.inner_ho, fold.ev, mu_m_ho, mu_m_ev, sv_ho, sv_ev)
    assert_market_blind(names, context=f"{_STORY} variance drivers fold {fold.eval_year}")

    return FoldContext(
        eval_year=fold.eval_year, mu_m_ev=mu_m_ev, mu_t_ev=mu_t_ev, y_m_ev=y_m_ev, y_t_ev=y_t_ev,
        mu_m_ho=mu_m_ho, mu_t_ho=mu_t_ho, y_m_ho=y_m_ho, y_t_ho=y_t_ho, resid_m=rm, resid_t=rt,
        sv_ho=sv_ho, sv_ev=sv_ev, Z_ho=Z_ho, Z_ev=Z_ev, driver_names=names, disp=disp,
        sig_m_ev=sig_m_ev, sig_t_ev=sig_t_ev, sig_m_ho=sig_m_ho, sig_t_ho=sig_t_ho,
        train_home_pts=fold.tr[_HOME_PTS].to_numpy(float),
        train_away_pts=fold.tr[_AWAY_PTS].to_numpy(float))


# ===========================================================================
# The samplers — one per registered arm + the four generic anchors
# ===========================================================================

def draw_arm(arm: str, c: FoldContext, rng: np.random.Generator, n_draws: int
             ) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Draw `arm`'s (margin, total) predictive on the fold's EVAL rows. Returns (m, t, info)."""
    info: dict[str, Any] = {}

    # ── the FOIL: the shipped serving path, called verbatim ────────────────────────────────────
    if arm == "incumbent":
        m, t = draw_joint(_SERVED_FORM, c.mu_m_ev, c.mu_t_ev, c.disp, rng, n_draws=n_draws,
                          sigma_margin_native=c.sig_m_ev, sigma_total_native=c.sig_t_ev)
        info = {"sigma0_margin": round(c.disp.sigma0_margin, 3), "k_margin": round(c.disp.k_margin, 3),
                "sigma0_total": round(c.disp.sigma0_total, 3), "k_total": round(c.disp.k_total, 3),
                "rho": round(c.disp.rho, 4)}
        return m, t, info

    # ── the four generic ANCHORS: the incumbent with a deliberately-degenerate scale ───────────
    if arm in ("zero_width", "max_width", "coverage_target"):
        if arm == "zero_width":
            sm = np.full_like(c.sig_m_ev, shp.MIN_SIGMA)
            st = np.full_like(c.sig_t_ev, shp.MIN_SIGMA)
        elif arm == "max_width":
            sm, st = c.sig_m_ev * 3.0, c.sig_t_ev * 3.0
        else:
            # ⭐ the COVERAGE-TARGET degenerate: scale σ so calib_80 hits EXACTLY 0.80 on the inner
            # holdout, with NO shape change. Under a Normal an 80% interval is ±1.2816σ, so the
            # scale that makes the empirical hit-rate 0.80 is q₀.₈₀(|z|)/1.2816. It must SATISFY the
            # coverage constraint and LOSE the metric — that is the E2.1-r proof that calib_80 is a
            # FLOOR and can never be the criterion.
            z1 = 1.2815515655446004
            cm = float(np.quantile(np.abs(c.resid_m / np.maximum(c.sig_m_ho, 1e-6)), 0.80) / z1)
            ct = float(np.quantile(np.abs(c.resid_t / np.maximum(c.sig_t_ho, 1e-6)), 0.80) / z1)
            sm, st = c.sig_m_ev * cm, c.sig_t_ev * ct
            info = {"coverage_scale_margin": round(cm, 4), "coverage_scale_total": round(ct, 4)}
        m, t = sample_joint_normal(c.mu_m_ev, c.mu_t_ev, sm, st, c.disp.rho, rng, n_draws=n_draws)
        return m, t, info

    # ── conditional heteroskedasticity (and its permutation anchor) ────────────────────────────
    if arm in ("cond_het", "permute"):
        Z_fit = c.Z_ho
        if arm == "permute":
            # PERMUTATION anchor (NF1.7 b): shuffle the DRIVER rows against the residuals. This
            # destroys the conditional structure while leaving the marginal untouched, so it is the
            # anchor that can actually act on this mechanism (a marginal-shape permutation would be
            # vacuous — NF-D16). It must LOSE to `cond_het`.
            Z_fit = c.Z_ho[rng.permutation(len(c.Z_ho))]
        th_m = shp.fit_log_variance(c.resid_m, Z_fit)
        th_t = shp.fit_log_variance(c.resid_t, Z_fit)
        sm = shp.apply_log_variance(th_m, c.Z_ev)
        st = shp.apply_log_variance(th_t, c.Z_ev)
        zm = c.resid_m / np.maximum(shp.apply_log_variance(th_m, Z_fit), 1e-6)
        zt = c.resid_t / np.maximum(shp.apply_log_variance(th_t, Z_fit), 1e-6)
        rho = float(np.clip(np.corrcoef(zm, zt)[0, 1], -0.95, 0.95))
        m, t = sample_joint_normal(c.mu_m_ev, c.mu_t_ev, sm, st, rho, rng, n_draws=n_draws)
        info = {"rho": round(rho, 4), "n_drivers": int(c.Z_ev.shape[1]),
                "sigma_total_p10_p90": [round(float(np.percentile(st, 10)), 2),
                                        round(float(np.percentile(st, 90)), 2)],
                "gamma_l2": round(float(np.sum(th_t[1:] ** 2)), 5)}
        return m, t, info

    # ── the true bivariate t (tail DEPENDENCE — deliberately not a Gaussian copula) ────────────
    if arm == "student_t":
        zm = c.resid_m / np.maximum(c.sig_m_ho, 1e-6)
        zt = c.resid_t / np.maximum(c.sig_t_ho, 1e-6)
        _, pm = shp.fit_standardized_marginal("student_t", zm, rng)
        _, pt = shp.fit_standardized_marginal("student_t", zt, rng)
        dof = float(np.sqrt(pm["dof"] * pt["dof"]))     # ONE ν: a bivariate t has a single dof
        rho = float(np.clip(np.corrcoef(zm, zt)[0, 1], -0.95, 0.95))
        m, t = shp.draw_bivariate_t(c.mu_m_ev, c.mu_t_ev, c.sig_m_ev, c.sig_t_ev, rho, dof,
                                    rng, n_draws)
        info = {"dof": round(dof, 3), "dof_margin": pm["dof"], "dof_total": pt["dof"],
                "rho": round(rho, 4), "collapse_at": "dof→∞"}
        return m, t, info

    # ── the Gaussian-copula ⊗ standardized-marginal family ─────────────────────────────────────
    if arm in ("skew_normal", "skew_t", "mixture", "copula"):
        family = "empirical" if arm == "copula" else arm
        zm = c.resid_m / np.maximum(c.sig_m_ho, 1e-6)
        zt = c.resid_t / np.maximum(c.sig_t_ho, 1e-6)
        gm, pm = shp.fit_standardized_marginal(family, zm, rng)
        gt, pt = shp.fit_standardized_marginal(family, zt, rng)
        rho = shp.normal_scores_rho(c.resid_m, c.resid_t)
        m, t = shp.draw_copula(c.mu_m_ev, c.mu_t_ev, c.sig_m_ev, c.sig_t_ev, gm, gt, rho,
                               rng, n_draws)
        info = {"rho_normal_scores": round(rho, 4), "margin_params": pm, "total_params": pt}
        return m, t, info

    # ── separate home/away score distributions → transform ─────────────────────────────────────
    if arm == "home_away":
        yh_ho = (c.y_t_ho + c.y_m_ho) / 2.0
        ya_ho = (c.y_t_ho - c.y_m_ho) / 2.0
        mh_ho = np.clip((c.mu_t_ho + c.mu_m_ho) / 2.0, shp.MIN_MU_POINTS, None)
        ma_ho = np.clip((c.mu_t_ho - c.mu_m_ho) / 2.0, shp.MIN_MU_POINTS, None)
        r_h = shp.fit_negbin_r(np.clip(yh_ho, 0, None), mh_ho)
        r_a = shp.fit_negbin_r(np.clip(ya_ho, 0, None), ma_ho)
        rho_sides = shp.normal_scores_rho(yh_ho - mh_ho, ya_ho - ma_ho)
        mh = np.clip((c.mu_t_ev + c.mu_m_ev) / 2.0, shp.MIN_MU_POINTS, None)
        ma = np.clip((c.mu_t_ev - c.mu_m_ev) / 2.0, shp.MIN_MU_POINTS, None)
        yh, ya = shp.draw_correlated_negbin(mh, ma, r_h, r_a, rho_sides, rng, n_draws)
        info = {"r_home": round(r_h, 1), "r_away": round(r_a, 1),
                "rho_sides": round(rho_sides, 4),
                "note": "P1.4's `count` form FORCED rho_sides=0; this arm fits it"}
        return yh - ya, yh + ya, info

    # ── discrete-score simulation on the empirical key-number lattice ──────────────────────────
    if arm == "key_number":
        pmf_h = shp.score_lattice_pmf(c.train_home_pts)
        pmf_a = shp.score_lattice_pmf(c.train_away_pts)
        mh = (c.mu_t_ev + c.mu_m_ev) / 2.0
        ma = (c.mu_t_ev - c.mu_m_ev) / 2.0
        # per-side σ from the incumbent's joint scale: Var(h) = (σ_t² + σ_m² + 2ρσ_tσ_m)/4
        v_h = (c.sig_t_ev ** 2 + c.sig_m_ev ** 2 + 2 * c.disp.rho * c.sig_t_ev * c.sig_m_ev) / 4.0
        v_a = (c.sig_t_ev ** 2 + c.sig_m_ev ** 2 - 2 * c.disp.rho * c.sig_t_ev * c.sig_m_ev) / 4.0
        rho_sides = shp.normal_scores_rho(c.y_m_ho - c.mu_m_ho, c.y_t_ho - c.mu_t_ho)
        # correlate the two sides through a Gaussian copula on the lattice uniforms
        from scipy.stats import norm
        n = len(mh)
        z1 = rng.standard_normal((n, n_draws))
        z2 = rho_sides * z1 + math.sqrt(max(1.0 - rho_sides ** 2, 0.0)) * rng.standard_normal((n, n_draws))
        # ⚠️ the target VARIANCE, never a bandwidth — composing a Gaussian kernel of width b with an
        # empirical pmf gives 1/var = 1/s_e² + 1/b², so passing σ as the bandwidth under-disperses
        # the arm systematically (see `tilted_lattice_pmf`).
        yh = shp.tilted_lattice_draw(pmf_h, mh, np.clip(v_h, 1.0, None), norm.cdf(z1))
        ya = shp.tilted_lattice_draw(pmf_a, ma, np.clip(v_a, 1.0, None), norm.cdf(z2))
        key = [3, 7, 10, 14, 17, 21, 24, 28]
        info = {"rho_sides": round(rho_sides, 4),
                "lattice_key_mass_home": round(float(pmf_h[key].sum()), 4),
                "lattice_nonkey_mass_home": round(float(pmf_h[[1, 2, 4, 5, 8, 11]].sum()), 4)}
        return yh - ya, yh + ya, info

    # ── the distributional-boosting foil ───────────────────────────────────────────────────────
    if arm == "quantile_boost":
        Qm = shp.fit_quantile_boost(c.resid_m, c.Z_ho, c.Z_ev)
        Qt = shp.fit_quantile_boost(c.resid_t, c.Z_ho, c.Z_ev)
        rho = shp.normal_scores_rho(c.resid_m, c.resid_t)
        m, t = shp.draw_pergame_quantiles(c.mu_m_ev, c.mu_t_ev, Qm, Qt, rho, rng, n_draws)
        info = {"rho_normal_scores": round(rho, 4), "n_levels": int(len(shp.QB_LEVELS)),
                "n_fit_rows": int(len(c.resid_m)),
                "median_iqr_total": round(float(np.median(
                    Qt[:, list(shp.QB_LEVELS).index(0.75)] - Qt[:, list(shp.QB_LEVELS).index(0.25)]
                    if 0.75 in list(shp.QB_LEVELS) else Qt[:, -1] - Qt[:, 0])), 3)}
        return m, t, info

    raise KeyError(f"{_STORY}: unknown arm {arm!r}")


def oracle_context(c: FoldContext) -> FoldContext:
    """A PEEKING copy of the fold context: every FIT-side field replaced by its EVAL-side twin.

    ⭐ THE PER-FORM CEILING, and it is deliberately built HERE rather than inside `draw_arm` — so
    `draw_arm` never constructs an eval residual and the leakage guard on it stays structural.
    Passing this context to an arm makes that arm fit its shape parameters on the answers it is
    about to be scored against: **same form, same estimator, same n** (~750 eval rows against ~736
    inner-holdout rows), which is what makes it a legitimate floor (NF1.7 (b) / NF1.9 (f) — a peeking
    oracle is a floor only at matched family AND matched sample) and PER-FORM, because the families
    NEST and a single field-wide ceiling would falsely veto a legitimately better nested form
    (NF-D16 g‴).

    ⚠️ WHAT THIS REPLACED, AND WHY (amendment A8.6). The first construction was a SELF-CONSISTENCY
    oracle — truth drawn from the arm's own predictive, whose expected CRPS is the closed form
    `½·E|X−X'|`. That IS a valid floor for a PIT-type metric (P1.4's `downstream_score`, where a
    perfectly-specified predictive achieves ~0 deviation and nothing can beat it). It is **NOT** a
    floor for CRPS: `E_G[CRPS(F,·)] = E|X−Y_G| − ½E|X−X'|`, so an OVER-DISPERSED `F` scores BETTER
    against a tighter reality `G` than against synthetic truth drawn from itself. Measured on the
    smoke: the incumbent came in 0.285 BELOW its own self-consistency figure and read as "the oracle
    was beaten" when nothing was wrong. The quantity is still computed and reported — as a
    DISPERSION diagnostic (`self_consistency_crps`), which is exactly what it is — but it no longer
    gates anything.
    """
    from dataclasses import replace
    rm_ev = c.y_m_ev - c.mu_m_ev
    rt_ev = c.y_t_ev - c.mu_t_ev
    # the SCALE is a fitted quantity too, so the peek refits it on the eval residuals — otherwise an
    # arm that consumes σ rather than a standardized shape (key_number, home_away, the degenerates)
    # gets a peek that cannot act, and an inactive anchor is uninformative, never a pass (NF-D20).
    g = fit_gaussian_dispersion(rm_ev, rt_ev)
    d2 = JointDispersion(sigma_margin=g.sigma_margin, sigma_total=g.sigma_total, rho=g.rho)
    d2.sigma0_margin, d2.k_margin = fit_strength_posterior_scale(rm_ev, c.sv_ev)
    d2.sigma0_total, d2.k_total = fit_strength_posterior_scale(rt_ev, c.sv_ev)
    sm = strength_posterior_sigma(d2.sigma0_margin, d2.k_margin, c.sv_ev)
    st = strength_posterior_sigma(d2.sigma0_total, d2.k_total, c.sv_ev)
    # ⚠️ `train_home_pts` / `train_away_pts` are deliberately NOT swapped. They are `key_number`'s
    # empirical SUBSTRATE (~5,000 train games), not a fitted parameter — replacing them with the
    # ~750 eval games would hand the "peeking" oracle a 6× SMALLER lattice and it would lose on
    # sample size while appearing to lose on peeking. Measured before this correction: key_number's
    # peek came in 0.010 WORSE than the honest arm and read as BEATEN. A peeking oracle is a floor
    # only at matched family AND matched SAMPLE (NF1.7 (b) / NF1.9 (f)); the peek swaps what is
    # FITTED and holds what is DATA.
    return replace(
        c,
        mu_m_ho=c.mu_m_ev, mu_t_ho=c.mu_t_ev, y_m_ho=c.y_m_ev, y_t_ho=c.y_t_ev,
        resid_m=rm_ev, resid_t=rt_ev, sv_ho=c.sv_ev, Z_ho=c.Z_ev,
        disp=d2, sig_m_ev=sm, sig_t_ev=st, sig_m_ho=sm, sig_t_ho=st,
    )


# ===========================================================================
# Scoring ONE arm on ONE fold
# ===========================================================================

def score_arm_fold(arm: str, c: FoldContext, rng: np.random.Generator,
                   *, n_draws: int = _N_DRAWS, peek: FoldContext | None = None) -> dict[str, Any]:
    m_s, t_s, info = draw_arm(arm, c, rng, n_draws)

    obs = {"margin": c.y_m_ev, "total": c.y_t_ev, "home_win": (c.y_m_ev > 0).astype(float)}
    metrics = score_calibration(derive_markets(m_s, t_s), obs, rng)

    crps_t = shp.crps_ensemble(c.y_t_ev, t_s)
    crps_m = shp.crps_ensemble(c.y_m_ev, m_s)

    # ⭐ THE PER-FORM PEEKING ORACLE (NF-D16 g‴ + NF1.7 (b)): the SAME shape family, same estimator
    # and same n, but fitted on the EVAL fold's own residuals — i.e. it has seen the answers. An
    # honest arm may not beat it. Per-form because the families NEST, so one field-wide ceiling would
    # falsely veto a legitimately better nested form; and a TIE is INACTIVE, never a refusal
    # (NF-W6d — the anchor pair simply had nothing to act on).
    orng = np.random.default_rng(_SEED + 7919)
    _, t_peek, _ = draw_arm(arm, peek if peek is not None else oracle_context(c), orng, n_draws)
    oracle_crps_t = float(shp.crps_ensemble(c.y_t_ev, t_peek).mean())
    # ⚠️ A DISPERSION DIAGNOSTIC, NOT A FLOOR (A8.6): E_{Y~F}[CRPS(F,Y)] = ½·E|X−X'| is the score F
    # would get if reality WERE F. Because E_G[CRPS(F,·)] = E|X−Y_G| − ½E|X−X'|, an OVER-dispersed F
    # scores BETTER against a tighter reality than against itself — so a real CRPS below this figure
    # means the predictive is WIDER than the realised outcomes, which is information, not a failure.
    _sub = t_s[:, : min(400, n_draws)]
    self_consistency_t = float(0.5 * np.mean(np.abs(_sub - _sub[:, ::-1])))

    tail_t = shp.tail_crps(c.y_t_ev, t_s)
    joint = shp.joint_pit_dev(m_s, t_s, c.y_m_ev, c.y_t_ev, rng)
    mean_ok = shp.mean_preservation(m_s, t_s, c.mu_m_ev, c.mu_t_ev)

    buckets = [float(crps_t[sl].mean())
               for sl in np.array_split(np.arange(len(c.y_t_ev)), _N_SLICES) if len(sl) >= 40]

    return {
        "arm": arm, "eval_year": c.eval_year, "n_games": int(len(c.y_t_ev)),
        "crps_total": round(float(crps_t.mean()), 5),
        "crps_margin": round(float(crps_m.mean()), 5),
        "crps_joint": round(float(crps_t.mean() + crps_m.mean()), 5),
        "oracle_crps_total": round(oracle_crps_t, 5),
        "self_consistency_crps_total": round(self_consistency_t, 5),
        "tail_crps_total": round(float(tail_t), 5),
        "total_calib_80": metrics["total"]["calib_80"],
        "margin_calib_80": metrics["margin"]["calib_80"],
        "total_pit_dev": metrics["total"]["pit_max_decile_dev"],
        "total_pit_mean_dev": metrics["total"]["pit_mean_dev"],
        "total_pit_flat": bool(metrics["total"]["pit_is_flat"]),
        "margin_pit_dev": metrics["margin"]["pit_max_decile_dev"],
        "margin_pit_flat": bool(metrics["margin"]["pit_is_flat"]),
        "h2h_brier": metrics["home_win"]["brier"],
        **{f"joint_{k}": v for k, v in joint.items()},
        "mean_preserved": bool(mean_ok["ok"]),
        "mean_shift_margin": mean_ok["mean_shift_margin"],
        "mean_shift_total": mean_ok["mean_shift_total"],
        "buckets": [round(b, 5) for b in buckets],
        "info": info,
        # carried for the pooled re-score (the pooled PIT is what the ship clauses read)
        "_pooled": {"margin": m_s, "total": t_s},
    }


# ===========================================================================
# Gate R — the foil must reproduce the SERVED artifact
# ===========================================================================

def reproduction_check(rows: list[dict], ctxs: list[FoldContext]) -> dict[str, Any]:
    """Does this harness's FOIL reproduce the config that actually serves?

    ⭐ Load-bearing, and it is the check a stale cache would fail. Every candidate is measured
    against this foil, so a foil that is not the served model makes the whole leaderboard a
    comparison against a stranger. The served record is `ncaaf_s1_serve_calibration.json`; its σ is
    fitted on POOLED OOS residuals, so the pooled refit here is the like-for-like comparison.
    """
    out: dict[str, Any] = {"served_record": _SERVED_CALIB.name}
    if not _SERVED_CALIB.exists():
        out["status"] = "UNVERIFIED"
        out["why"] = ("the served calibration record is absent — the foil cannot be proven to be the "
                      "served config. An unverifiable check is never scored as a pass (NF1.7 a).")
        return out
    served = json.loads(_SERVED_CALIB.read_text())["served_params"]
    rm = np.concatenate([c.y_m_ev - c.mu_m_ev for c in ctxs])
    rt = np.concatenate([c.y_t_ev - c.mu_t_ev for c in ctxs])
    g = fit_gaussian_dispersion(rm, rt)
    d = {"sigma_margin": g.sigma_margin, "sigma_total": g.sigma_total, "rho": g.rho}
    deltas = {k: round(float(d[k] - served[k]), 4) for k in ("sigma_margin", "sigma_total")}
    ok = all(abs(v) <= _REPRO_TOL_SIGMA for v in deltas.values())
    out.update({
        "status": "PASS" if ok else "FAIL",
        "n_oos_pooled": int(len(rm)), "n_oos_served": int(json.loads(_SERVED_CALIB.read_text())
                                                          .get("n_oos_games", 0)),
        "refit": {k: round(float(v), 4) for k, v in d.items()},
        "served": {k: round(float(served[k]), 4) for k in ("sigma_margin", "sigma_total", "rho")},
        "delta": deltas, "tol_points": _REPRO_TOL_SIGMA,
        "note": ("a FAIL means the foil is not the served config — most likely a stale feature "
                 "cache — and the whole leaderboard would be a comparison against a stranger."),
    })
    return out


# ===========================================================================
# Stage 1 — the battery
# ===========================================================================

def _pooled_rescore(rows: list[dict], ctxs: list[FoldContext], rng: np.random.Generator
                    ) -> dict[str, Any]:
    """Pooled-OOS calibration for one arm — what every ship clause reads.

    The ship clauses are stated on the POOLED distribution because that is what the served artifact
    reports and therefore the only like-for-like comparison to the incumbent's recorded 0.0173.
    """
    m = np.concatenate([r["_pooled"]["margin"] for r in rows], axis=0)
    t = np.concatenate([r["_pooled"]["total"] for r in rows], axis=0)
    ym = np.concatenate([c.y_m_ev for c in ctxs])
    yt = np.concatenate([c.y_t_ev for c in ctxs])
    metrics = score_calibration(derive_markets(m, t), {"margin": ym, "total": yt,
                                                       "home_win": (ym > 0).astype(float)}, rng)
    joint = shp.joint_pit_dev(m, t, ym, yt, rng)
    return {
        "n": int(len(ym)),
        "total_pit_dev": metrics["total"]["pit_max_decile_dev"],
        "total_pit_mean_dev": metrics["total"]["pit_mean_dev"],
        "total_pit_flat": bool(metrics["total"]["pit_is_flat"]),
        "total_calib_80": metrics["total"]["calib_80"],
        "margin_pit_dev": metrics["margin"]["pit_max_decile_dev"],
        "margin_pit_flat": bool(metrics["margin"]["pit_is_flat"]),
        "margin_calib_80": metrics["margin"]["calib_80"],
        "h2h_brier": metrics["home_win"]["brier"],
        **{f"joint_{k}": v for k, v in joint.items()},
    }


def stage_battery(args) -> None:
    df, meta = load_cache()
    cols = served_columns(df)
    print(f"=== {_STORY} stage 1 — SHAPE BATTERY ===")
    print(f"  {len(df):,} completed games {int(df[_YEAR].min())}–{int(df[_YEAR].max())} · served "
          f"contract `strength_pace` ({len(cols)} cols) · form frozen mean = ridge(α={_RIDGE_ALPHA})")
    print(f"  weather drivers: ABSENT — {shp.WEATHER_ABSENCE_NOTE}")

    folds = build_folds(df, max_folds=args.max_folds)
    print(f"  purged season-forward folds: {[f.eval_year for f in folds]}")
    ctxs: list[FoldContext] = []
    for f in folds:
        t0 = time.time()
        ctxs.append(build_context(f, cols))
        _log(f"fold {f.eval_year}: ctx built ({len(f.ev):,} eval / {len(f.inner_ho):,} inner-ho) "
             f"[{time.time() - t0:.1f}s]", indent=1)

    peeks = [oracle_context(c) for c in ctxs]     # the per-form ceiling's context, once per fold
    arms = list(shp.SHAPES and [s.arm for s in shp.SHAPES]) + list(shp.GENERIC_ANCHORS)
    if args.arms:
        arms = [a for a in arms if a in set(args.arms.split(","))]
    n_draws = 800 if args.smoke else args.n_draws

    scored: dict[str, Any] = {}
    for arm in arms:
        t0 = time.time()
        rng = np.random.default_rng(_SEED)
        rows = [score_arm_fold(arm, c, rng, n_draws=n_draws, peek=pk)
                for c, pk in zip(ctxs, peeks)]
        pooled = _pooled_rescore(rows, ctxs, np.random.default_rng(_SEED + 11))
        for r in rows:
            r.pop("_pooled", None)
        scored[arm] = {
            "arm": arm,
            "fold_crps_total": [r["crps_total"] for r in rows],
            "fold_crps_joint": [r["crps_joint"] for r in rows],
            "fold_oracle_crps_total": [r["oracle_crps_total"] for r in rows],
            "fold_tail_crps_total": [r["tail_crps_total"] for r in rows],
            "buckets": [b for r in rows for b in r["buckets"]],
            "pooled_crps_total": round(float(np.mean([r["crps_total"] for r in rows])), 5),
            "pooled_crps_joint": round(float(np.mean([r["crps_joint"] for r in rows])), 5),
            "pooled_tail_crps_total": round(float(np.mean([r["tail_crps_total"] for r in rows])), 5),
            "oracle_crps_total": round(float(np.mean([r["oracle_crps_total"] for r in rows])), 5),
            "self_consistency_crps_total": round(
                float(np.mean([r["self_consistency_crps_total"] for r in rows])), 5),
            "mean_preserved_all_folds": bool(all(r["mean_preserved"] for r in rows)),
            "max_abs_mean_shift": round(float(max(
                max(abs(r["mean_shift_margin"]), abs(r["mean_shift_total"])) for r in rows)), 4),
            "margin_pit_flat_folds": int(sum(r["margin_pit_flat"] for r in rows)),
            "total_pit_flat_folds": int(sum(r["total_pit_flat"] for r in rows)),
            "pooled": pooled,
            "folds": rows,
        }
        print(f"  {arm:<16} crps_total {scored[arm]['pooled_crps_total']:.5f}  "
              f"pooled totalPIT {pooled['total_pit_dev']:.4f} (mean {pooled['total_pit_mean_dev']:.4f}"
              f", flat {pooled['total_pit_flat']})  calib80 {pooled['total_calib_80']:.3f}  "
              f"jointPIT {pooled['joint_joint_pit_dev']:.4f}  ({time.time() - t0:.0f}s)")

    repro = reproduction_check(scored.get("incumbent", {}).get("folds", []), ctxs)
    print(f"\n  gate R (foil reproduces the SERVED artifact): {repro.get('status')}  "
          f"{repro.get('delta', repro.get('why', ''))}")

    doc = {
        "story": _STORY, "scored_at": date.today().isoformat(), "smoke": bool(args.smoke),
        "n_folds": len(folds), "fold_years": [f.eval_year for f in folds], "n_draws": n_draws,
        "seed": _SEED, "served_contract": "strength_pace", "served_form": _SERVED_FORM,
        "served_columns": cols, "driver_names": ctxs[0].driver_names,
        "weather_drivers_absent": shp.WEATHER_ABSENCE_NOTE,
        "declared_field_size": shp.DECLARED_FIELD_SIZE,
        "reproduction_check": repro, "cache_meta": meta,
        "arms": {k: {kk: vv for kk, vv in v.items() if kk != "folds"} for k, v in scored.items()},
        "arm_folds": {k: v["folds"] for k, v in scored.items()},
    }
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _SCORES_JSON.write_text(json.dumps(doc, indent=2, default=float))
    print(f"\n  → {_SCORES_JSON.relative_to(_PROJECT_ROOT)}")


# ===========================================================================
# Stage 2 — decide
# ===========================================================================

def fold_series(foil: dict, arm: dict) -> np.ndarray:
    """The BINDING DSR series: per-FOLD matched pair `crps_total(foil) − crps_total(arm)`.

    > 0 ⇔ the arm beats the served incumbent. One observation per season-forward fold — the
    independent unit of this design, declared separately from the PBO bucket series because PBO wants
    MANY buckets and DSR wants LOW-NOISE INDEPENDENT observations (NCAAF-P2.1-S1).
    """
    f = np.asarray(foil["fold_crps_total"], float)
    a = np.asarray(arm["fold_crps_total"], float)
    n = min(len(f), len(a))
    return f[:n] - a[:n]


def sharpe(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    s = x.std(ddof=1) if len(x) > 1 else 0.0
    return float(x.mean() / s) if s > 0 else 0.0


def series_moments(x: np.ndarray) -> tuple[float, float]:
    """(skew, kurtosis) in `deflated_sharpe`'s convention.

    ⭐ LOAD-BEARING: `deflated_sharpe` estimates the moments FROM the series while `cv_power`'s
    reachability arithmetic DEFAULTS to Gaussian. Leaving that default in place publishes a
    "come back with more seasons" re-test trigger for a gate that may already have passed — the
    actively-misleading trigger MH2/NF-D18 forbid (NCAAF-P2.1-S1b defect 1). The measured moments are
    therefore passed explicitly wherever the instrument accepts them.
    """
    from scipy import stats
    x = np.asarray(x, float)
    if len(x) < 3:
        return 0.0, 3.0
    return float(stats.skew(x, bias=False)), float(stats.kurtosis(x, fisher=False, bias=False))


def paired_p(delta: np.ndarray) -> float:
    d = np.asarray(delta, float)
    if len(d) < 2 or d.std(ddof=1) == 0:
        return 1.0 if d.mean() <= 0 else 0.0
    from scipy import stats
    return float(stats.t.sf(d.mean() / (d.std(ddof=1) / math.sqrt(len(d))), df=len(d) - 1))


def bh(pvals: dict[str, float], alpha: float = _FDR_ALPHA) -> tuple[dict[str, bool], float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    passed, cutoff, kmax = {k: False for k in pvals}, 0.0, 0
    for i, (_k, p) in enumerate(items, start=1):
        if p <= alpha * i / m:
            kmax, cutoff = i, alpha * i / m
    for i, (k, _p) in enumerate(items, start=1):
        passed[k] = i <= kmax
    return passed, cutoff


def anchor_report(arms: dict) -> dict[str, Any]:
    """Run VALIDITY. A misbehaving anchor invalidates the run — checked BEFORE any verdict.

    Every expectation is the one written in `p2_5_shapes.ANCHOR_EXPECTATION` before the run, so a
    surprise here cannot be re-read as a finding (E2.1-r).
    """
    out: dict[str, Any] = {"expectations": dict(shp.ANCHOR_EXPECTATION)}
    floor = _CALIB_TARGET - _CALIB_TOL
    foil = arms.get(shp.FOIL_ARM)

    # ⭐ PER-FORM oracle floor: each arm against the peeking version of its OWN form (NF-D16 g‴).
    # A single field-wide ceiling would falsely veto a legitimately better nested form.
    oracles: dict[str, Any] = {}
    for a, v in arms.items():
        gap = float(v["pooled_crps_total"] - v["oracle_crps_total"])
        # a TIE is INACTIVE, never a refusal (NF-W6d): the anchor pair had nothing to act on.
        state = "BEATEN" if gap < -_TIE_BAND else ("INACTIVE_TIE" if abs(gap) <= _TIE_BAND else "OK")
        oracles[a] = {"pooled_crps_total": v["pooled_crps_total"],
                      "own_form_peeking_oracle": v["oracle_crps_total"],
                      "self_consistency_crps": v["self_consistency_crps_total"],
                      "gap": round(gap, 5), "state": state}
    out["per_form_oracle"] = oracles
    # ⭐ PER-ARM, NOT FIELD-WIDE. The pre-registration makes this ceiling per-form *precisely so* that
    # one arm's ceiling cannot veto the others; letting a single BEATEN arm invalidate the whole run
    # would reinstate the field-wide behaviour §3 forbids (NF-D16 g‴), and it is the NF-D20
    # bundled-flag liability at the level of the run. A beaten arm is INELIGIBLE (clause C8); every
    # other arm's reading is untouched.
    out["oracle_beaten_arms"] = sorted(a for a, o in oracles.items() if o["state"] == "BEATEN")
    out["oracle_floor_ok"] = not out["oracle_beaten_arms"]
    out["oracle_floor_ok_field_sanity"] = all(
        oracles[a]["state"] != "BEATEN" for a in oracles if a in shp.GENERIC_ANCHORS
        or a == shp.FOIL_ARM)

    def _pooled(a: str, key: str, default=None):
        return arms[a]["pooled"].get(key, default) if a in arms else default

    if "permute" in arms and "cond_het" in arms:
        d = float(arms["permute"]["pooled_crps_total"] - arms["cond_het"]["pooled_crps_total"])
        out["permute"] = {
            "permute_crps": arms["permute"]["pooled_crps_total"],
            "cond_het_crps": arms["cond_het"]["pooled_crps_total"],
            "permute_minus_cond_het": round(d, 5),
            "loses_to_cond_het": bool(d > _TIE_BAND),
            "tie": bool(abs(d) <= _TIE_BAND),
            "reading": ("a TIE means the conditional-variance channel carries no information beyond "
                        "the marginal — which is a finding about the DRIVERS, not a broken anchor"),
        }
    for a in ("zero_width", "max_width", "coverage_target"):
        if a not in arms:
            continue
        cal_t, cal_m = _pooled(a, "total_calib_80", 0.0), _pooled(a, "margin_calib_80", 0.0)
        loses = bool(foil is None or arms[a]["pooled_crps_total"] > foil["pooled_crps_total"] + _TIE_BAND)
        entry = {"pooled_crps_total": arms[a]["pooled_crps_total"],
                 "total_calib_80": cal_t, "margin_calib_80": cal_m,
                 "satisfies_coverage_floor": bool(cal_t >= floor and cal_m >= floor),
                 "loses_the_metric": loses}
        if a == "coverage_target" and foil is not None:
            # would this degenerate SHIP under the full pre-registered rule? A pure σ-rescale makes
            # no shape change, so it cannot repair the total PIT (C2) — that is the E2.1-r proof.
            cl = ship_clauses(arms[a], foil)
            entry["clauses"] = cl
            entry["ships_under_the_full_rule"] = bool(
                cl["all_ok"] and arms[a]["pooled_crps_total"] < foil["pooled_crps_total"] - _TIE_BAND)
        out[a] = entry
    # ⭐ TWO FLAGS, NOT ONE. Bundling a MEASUREMENT-validity check with a SELECTION-hygiene check is
    # the NF-D20 liability: a reader sees one `False` and concludes the measurement is untrustworthy
    # when the sanity half is fine. They answer different questions and are reported separately.
    #
    #   measurement_valid  — is the SCORE trustworthy? (own-form oracle floor; the two sharpness
    #                        degenerates behaving; the permutation anchor losing). A failure here
    #                        means no finding can be read in either direction.
    #   selection_hygiene  — is `calib_80` being used as a TARGET? The coverage-target degenerate
    #                        must satisfy the coverage CONSTRAINT and must not WIN THE SELECTION
    #                        (the full ship rule, of which CRPS is only the primary). E2.1-r's
    #                        concern is a coverage-distance criterion a degenerate wins — see the
    #                        pre-registration amendment for why the CRPS-only reading is ALSO
    #                        reported rather than replaced.
    # ⛔ `permute` is NOT in this flag. Whether a shuffled-driver variance model beats the real one
    # is a statement about the MECHANISM (does the conditional-variance channel carry information?),
    # not about whether the SCORE is trustworthy — and the pre-registration §3 already words it that
    # way. Gating run validity on it would report "the measurement is untrustworthy" for what is
    # actually a clean negative result about the drivers (NF-D20: a bundled flag mixing a
    # metric-sanity check with a mechanism hypothesis is a liability).
    mv = out["oracle_floor_ok_field_sanity"]
    mv = mv and out.get("zero_width", {}).get("loses_the_metric", True)
    mv = mv and not out.get("zero_width", {}).get("satisfies_coverage_floor", False)
    mv = mv and out.get("max_width", {}).get("loses_the_metric", True)
    mv = mv and out.get("max_width", {}).get("satisfies_coverage_floor", True)
    out["measurement_valid"] = bool(mv)

    ct = out.get("coverage_target", {})
    ct_ships = bool(ct.get("ships_under_the_full_rule", False))
    out["selection_hygiene"] = {
        "coverage_target_satisfies_floor": bool(ct.get("satisfies_coverage_floor", True)),
        "coverage_target_loses_crps": bool(ct.get("loses_the_metric", True)),
        "coverage_target_wins_the_selection": ct_ships,
        "ok": bool(ct.get("satisfies_coverage_floor", True) and not ct_ships),
        "note": ("the pre-registered wording was 'must LOSE the metric'. Reported verbatim above as "
                 "`coverage_target_loses_crps`; the BINDING reading is "
                 "`coverage_target_wins_the_selection`, because the selection is the full ship rule "
                 "(CRPS primary + C1..C7), not the CRPS number alone. A pure σ-rescale carries NO "
                 "shape change and therefore cannot satisfy C2 — which is exactly the proof that "
                 "coverage is a floor and never a target."),
    }
    pm = out.get("permute", {})
    out["mechanism_findings"] = {
        "conditional_variance_channel_is_real": bool(pm.get("loses_to_cond_het", False)),
        "permute_minus_cond_het": pm.get("permute_minus_cond_het"),
        "reading": ("REPORTED, never a validity gate. `permute` is `cond_het` with the driver rows "
                    "SHUFFLED against the residuals: it destroys the conditional structure and "
                    "leaves the marginal untouched. If the shuffled fit BEATS the real one, the "
                    "registered variance drivers carry no information beyond the marginal and the "
                    "real fit is paying an overfitting cost for them — a clean NEGATIVE result "
                    "about the drivers, not a broken measurement."),
    }
    out["all_anchors_behaved"] = bool(mv and out["selection_hygiene"]["ok"])
    return out


def ship_clauses(arm: dict, foil: dict) -> dict[str, Any]:
    """The pre-registered §5.2 ship clauses, EACH reported separately.

    ⛔ Deliberately not bundled into one boolean: a bundled gate flag mixing distinct clauses is a
    liability — a reader cannot tell which half failed, and a metric-sanity clause reads as a
    mechanism verdict (NF-D20).
    """
    p, fp = arm["pooled"], foil["pooled"]
    floor = _CALIB_TARGET - _CALIB_TOL
    c: dict[str, Any] = {}
    c["C1_total_pit_flat"] = {
        "ok": bool(p["total_pit_dev"] <= _PIT_DEV_GATE and p["total_pit_mean_dev"] <= _PIT_MEAN_GATE),
        "pit_dev": p["total_pit_dev"], "pit_mean_dev": p["total_pit_mean_dev"]}
    c["C2_total_pit_repaired"] = {
        "ok": bool(fp["total_pit_dev"] - p["total_pit_dev"] > _C2_MARGIN),
        "foil": fp["total_pit_dev"], "arm": p["total_pit_dev"],
        "improvement": round(float(fp["total_pit_dev"] - p["total_pit_dev"]), 5),
        "required": _C2_MARGIN}
    c["C3_margin_pit_flat"] = {"ok": bool(p["margin_pit_flat"]), "pit_dev": p["margin_pit_dev"]}
    c["C4_coverage_floor"] = {
        "ok": bool(p["total_calib_80"] >= floor and p["margin_calib_80"] >= floor),
        "total": p["total_calib_80"], "margin": p["margin_calib_80"], "floor": floor}
    c["C5_tail_crps"] = {
        "ok": bool(arm["pooled_tail_crps_total"] <= foil["pooled_tail_crps_total"] + _TIE_BAND),
        "arm": arm["pooled_tail_crps_total"], "foil": foil["pooled_tail_crps_total"]}
    c["C6_joint_calibration"] = {
        "ok": bool(p["joint_joint_pit_dev"] <= fp["joint_joint_pit_dev"] + _TIE_BAND),
        "arm": p["joint_joint_pit_dev"], "foil": fp["joint_joint_pit_dev"]}
    c["C7_mean_preserved"] = {"ok": bool(arm["mean_preserved_all_folds"]),
                              "max_abs_shift": arm["max_abs_mean_shift"],
                              "tol": shp.MEAN_PRESERVATION_TOL}
    c["all_ok"] = bool(all(v["ok"] for k, v in c.items() if k.startswith("C")))
    return c


def _c8(arm_name: str, anchors: dict) -> dict[str, Any]:
    """C8 — this arm's OWN-form peeking ceiling was not beaten.

    ⚠️ A `BEATEN` state does not mean the arm is wrong; it means its ceiling is not a valid ceiling
    FOR IT, so the arm is not floor-verified and cannot be promoted on this run. The peek is a
    peeking **MLE** (the shape parameters are refit by their own estimators on the eval residuals)
    while the metric is **CRPS** — for an arm whose scale reaches the predictive through a
    non-Gaussian transform, those two optima need not coincide, so the MLE peek is not guaranteed
    to bound the CRPS. Left FAILING and decomposed rather than re-specified after the fact (E2.1-r).
    """
    o = anchors.get("per_form_oracle", {}).get(arm_name, {})
    return {"ok": o.get("state") != "BEATEN", "state": o.get("state"), "gap": o.get("gap")}


def stage_decide(args) -> None:
    if not _SCORES_JSON.exists():
        raise SystemExit(f"[{_STORY}] no scores — run `--stage battery` first.")
    doc = json.loads(_SCORES_JSON.read_text())
    arms = doc["arms"]
    foil = arms[shp.FOIL_ARM]
    real = [a for a in shp.CANDIDATE_ARMS if a in arms]
    n_folds = int(doc["n_folds"])

    # ── A: run validity first ──────────────────────────────────────────────────────────────────
    anchors = anchor_report(arms)
    repro = doc.get("reproduction_check", {})

    # ── B: the two declared series ─────────────────────────────────────────────────────────────
    #  V is measured over the REAL arms only — a diagnostic anchor must never set the gate's own bar
    #  (MH2.1 a: an oracle's Sharpe drove V and made DSR unclearable for a purely arithmetic reason).
    series = {a: fold_series(foil, arms[a]) for a in real}
    sr_real = np.array([sharpe(s) for s in series.values()], float)
    V = float(np.var(sr_real, ddof=1)) if len(sr_real) > 1 else None
    n_trials = shp.DECLARED_FIELD_SIZE

    # ── C: PBO over the per-BUCKET matrix of the real field + the foil ─────────────────────────
    bucket_arms = [shp.FOIL_ARM] + real
    n_b = min(len(arms[a]["buckets"]) for a in bucket_arms)
    perf = np.array([arms[a]["buckets"][:n_b] for a in bucket_arms], float).T
    n_splits = max(2, min(16, n_b - (n_b % 2)))
    pbo_res = pbo_cscv(perf, higher_is_better=False, n_splits=n_splits)
    pbo = float(pbo_res.pbo)

    # ── D: per-arm gates ───────────────────────────────────────────────────────────────────────
    pvals = {a: paired_p(series[a]) for a in real}
    bh_pass, bh_cut = bh(pvals)
    rows: dict[str, Any] = {}
    for a in real:
        s = series[a]
        gain = float(foil["pooled_crps_total"] - arms[a]["pooled_crps_total"])
        sk, ku = series_moments(s)
        dsr = deflated_sharpe(s, n_trials=n_trials, var_trials_sr=V) if len(s) >= 3 else None
        spec = next(x for x in shp.SHAPES if x.arm == a)
        tie = bool(abs(gain) <= _TIE_BAND)
        rows[a] = {
            "arm": a, "doc_item": spec.doc_item,
            "pooled_crps_total": arms[a]["pooled_crps_total"],
            "gain_vs_foil": round(gain, 5),
            "tie_with_foil": tie, "nests_foil": spec.nests_incumbent, "collapse_at": spec.collapse,
            "fold_wins": int(np.sum(s > 0)), "n_folds": int(len(s)),
            "sharpe": round(sharpe(s), 4), "series_skew": round(sk, 4), "series_kurt": round(ku, 4),
            "dsr": None if dsr is None else round(float(dsr.dsr), 4),
            "sr0": None if dsr is None else round(float(dsr.sr0), 4),
            "p_one_sided": round(pvals[a], 6), "bh_pass": bool(bh_pass[a]),
            "clauses": {**ship_clauses(arms[a], foil), "C8_own_form_floor": _c8(a, anchors)},
            # the fitted shape parameters of the FIRST fold — carried so §5.3's nested-tie rule can
            # be read off the record (is the extra parameter sitting at its collapse value?) rather
            # than inferred from the margin alone.
            "fitted_params_fold1": (doc.get("arm_folds", {}).get(a, [{}])[0] or {}).get("info"),
        }

    # ── E: the verdict ─────────────────────────────────────────────────────────────────────────
    for a in real:
        rows[a]["clauses"]["all_ok"] = bool(
            rows[a]["clauses"]["all_ok"] and rows[a]["clauses"]["C8_own_form_floor"]["ok"])

    def _ships(r: dict) -> bool:
        return bool(r["clauses"]["all_ok"] and not r["tie_with_foil"] and r["gain_vs_foil"] > 0
                    and r["dsr"] is not None and r["dsr"] >= _DSR_GATE and r["bh_pass"]
                    and pbo < _PBO_GATE)

    survivors = [a for a in real if _ships(rows[a])]
    best = min(real, key=lambda a: arms[a]["pooled_crps_total"]) if real else None
    # run validity is now a FIELD-level property (the metric-sanity degenerates + the foil's own
    # ceiling + the reproduction gate). A per-ARM ceiling failure makes THAT ARM ineligible via C8;
    # it does not invalidate the other nine readings.
    run_valid = bool(anchors["measurement_valid"] and anchors["selection_hygiene"]["ok"]
                     and repro.get("status") == "PASS")

    if not run_valid:
        verdict = "RUN_INVALID"
    elif survivors:
        verdict = "PROMOTE"
    else:
        verdict = "REFERENCE_STANDS"

    # ── F: classify the null (⭐ measured moments + declared_field_size — never the defaults) ───
    null: dict[str, Any] = {}
    if verdict == "REFERENCE_STANDS" and best is not None:
        r = rows[best]
        s = series[best]
        # ⛔ a refusal caused by a hard CONSTRAINT is CONSTRAINT_REFUSED, never POWER_LIMITED — the
        # latter publishes a "more seasons" trigger for a shortfall no fold count can move (NF-D18).
        constraint_failed = [k for k, v in r["clauses"].items()
                             if k.startswith("C") and not v["ok"]]
        beats = bool(r["gain_vs_foil"] > _TIE_BAND)
        v = cv_power.classify_null(
            metric="crps_total", n_folds=n_folds, n_arms=len(real), beats_foil=beats,
            observed_sr=r["sharpe"], var_trials_sr=V, fold_wins=r["fold_wins"],
            p_one_sided=r["p_one_sided"], bh_cutoff=bh_cut,
            skew=r["series_skew"], kurt=r["series_kurt"],
            declared_field_size=shp.DECLARED_FIELD_SIZE,
            degenerates_excluded_from_v=True)
        null = {
            "best_arm": best,
            "instrument_state": v.state, "instrument_reason": v.reason,
            "instrument_retest_trigger": v.retest_trigger, "instrument_detail": v.detail,
            "constraint_clauses_failed": constraint_failed,
            "binding_half": ("constraint" if constraint_failed else "statistical"),
            "recorded_state": ("CONSTRAINT_REFUSED" if constraint_failed else v.state),
            "why_recorded_state": (
                "the refusal is caused by a pre-registered SHIP CLAUSE, not by the statistic — no "
                "fold count moves a clause, so a `POWER_LIMITED`-style 'more seasons' trigger would "
                "be actively misleading (NF-D18). The instrument's own state is preserved above."
                if constraint_failed else
                "no ship clause bound; the statistic is what refused, so the instrument's state "
                "stands as recorded."),
            "declared_field_size": shp.DECLARED_FIELD_SIZE,
            "field_remedy_admissible": v.detail.get("field_remedy_admissible"),
        }

    # ── G: PBO companions (NF1.8: a rank statistic alone cannot tell UNSTABLE from TIED) ───────
    pooled = {a: arms[a]["pooled_crps_total"] for a in real}
    lo, hi = min(pooled.values()), max(pooled.values())
    nf = min(len(arms[a]["fold_crps_total"]) for a in bucket_arms)
    flips: dict[str, int] = {a: 0 for a in bucket_arms}
    for i in range(nf):
        flips[min(bucket_arms, key=lambda a: arms[a]["fold_crps_total"][i])] += 1

    out = {
        "story": _STORY, "decided_at": date.today().isoformat(),
        "smoke": doc.get("smoke", False),
        "verdict": verdict, "survivors": survivors, "best_arm": best,
        "n_folds": n_folds, "fold_years": doc["fold_years"],
        "declared_field_size": shp.DECLARED_FIELD_SIZE, "n_trials": n_trials,
        "var_trials_sr_real_arms_only": None if V is None else round(V, 6),
        "run_validity": {"reproduction_check": repro, "anchors": anchors, "valid": run_valid},
        "deflation": {"pbo": round(pbo, 4), "pbo_gate": _PBO_GATE, "pbo_pass": bool(pbo < _PBO_GATE),
                      "n_buckets": int(n_b), "n_cscv_combos": int(pbo_res.n_combos),
                      "dsr_gate": _DSR_GATE, "bh_alpha": _FDR_ALPHA, "bh_cutoff": round(bh_cut, 6)},
        "pbo_companions": {
            "contender_spread_crps": round(float(hi - lo), 5),
            "contender_spread_pct_of_foil": round(float((hi - lo) / foil["pooled_crps_total"] * 100), 4),
            "fold_flip_distribution": flips,
            "reading": ("E2.1-r: a HIGH PBO over a field whose candidates genuinely TIE is the NULL "
                        "— 'which tied candidate wins is noise' — not evidence of overfitting; a "
                        "high PBO with a WIDE spread IS overfitting. The SPREAD is the "
                        "discriminator, so it is reported beside the flip distribution."),
        },
        "foil": {"arm": shp.FOIL_ARM, "pooled_crps_total": foil["pooled_crps_total"],
                 "pooled": foil["pooled"], "pooled_tail_crps_total": foil["pooled_tail_crps_total"]},
        "arms": rows, "null_classification": null,
        "weather_drivers_absent": doc.get("weather_drivers_absent"),
        "driver_names": doc.get("driver_names"),
        "honest_frame": ("best_alpha = 0 — this story can only improve the SHAPE/honesty of a "
                         "probability, never claim an edge. Market-blind. NCAAF is not served, so a "
                         "survivor is a research-artifact re-point, never a deploy."),
    }
    _DECISION_JSON.write_text(json.dumps(out, indent=2, default=float))
    _DECISION_MD.write_text(render_dossier(out))
    _print_decision(out)
    print(f"\n  → {_DECISION_JSON.relative_to(_PROJECT_ROOT)}\n  → {_DECISION_MD.relative_to(_PROJECT_ROOT)}")


def _print_decision(d: dict) -> None:
    print("=" * 92)
    print(f"{_STORY} DECISION — {d['verdict']}   ({d['n_folds']} folds, field {d['declared_field_size']})")
    print("=" * 92)
    f = d["foil"]
    print(f"  FOIL {f['arm']:<14} crps_total {f['pooled_crps_total']:.5f}  totalPIT "
          f"{f['pooled']['total_pit_dev']:.4f}  calib80 {f['pooled']['total_calib_80']:.3f}")
    print(f"  {'arm':<16}{'crps_total':>11}{'gain':>10}{'wins':>6}{'DSR':>8}{'p':>9}  "
          f"{'totalPIT':>9}  clauses")
    for a, r in sorted(d["arms"].items(), key=lambda kv: kv[1]["pooled_crps_total"]):
        bad = [k.split("_")[0] for k, v in r["clauses"].items() if k.startswith("C") and not v["ok"]]
        print(f"  {a:<16}{r['pooled_crps_total']:>11.5f}{r['gain_vs_foil']:>+10.5f}"
              f"{r['fold_wins']:>4}/{r['n_folds']}{(r['dsr'] if r['dsr'] is not None else float('nan')):>8.3f}"
              f"{r['p_one_sided']:>9.4f}  {r['clauses']['C1_total_pit_flat']['pit_dev']:>9.4f}  "
              f"{'✅ all' if not bad else '❌ ' + ','.join(bad)}"
              f"{'  ⟵ TIE' if r['tie_with_foil'] else ''}")
    dd = d["deflation"]
    print(f"\n  PBO {dd['pbo']:.3f} ({'PASS' if dd['pbo_pass'] else 'FAIL'} < {dd['pbo_gate']})  "
          f"contender spread {d['pbo_companions']['contender_spread_pct_of_foil']:.3f}% of foil  "
          f"BH cutoff {dd['bh_cutoff']:.4g}")
    rv = d["run_validity"]
    print(f"  run validity: reproduction {rv['reproduction_check'].get('status')} · measurement "
          f"{'OK' if rv['anchors']['measurement_valid'] else 'MISBEHAVED'} · selection-hygiene "
          f"{'OK' if rv['anchors']['selection_hygiene']['ok'] else 'MISBEHAVED'} → "
          f"{'VALID' if rv['valid'] else 'INVALID'}")
    if d["null_classification"]:
        n = d["null_classification"]
        print(f"  null: {n['recorded_state']} (instrument {n['instrument_state']}; binding half "
              f"{n['binding_half']})")


def render_dossier(d: dict) -> str:
    L: list[str] = []
    A = L.append
    A(f"# {_STORY} — total / joint-distribution SHAPE repair")
    A("")
    A(f"_Decided {d['decided_at']} · {d['n_folds']} season-forward purged folds "
      f"({d['fold_years'][0]}–{d['fold_years'][-1]}) · declared field {d['declared_field_size']} · "
      f"`best_alpha = 0` · market-blind · deploy-held_")
    A("")
    A(f"## Verdict — **{d['verdict']}**")
    A("")
    if d["verdict"] == "PROMOTE":
        A(f"Survivor(s): {', '.join('`' + s + '`' for s in d['survivors'])}.")
    elif d["verdict"] == "RUN_INVALID":
        A("An anchor misbehaved or the foil failed to reproduce the served config — **no verdict is "
          "reached**. A run whose validity anchors fail cannot produce a finding in either direction.")
    else:
        A("No candidate cleared every pre-registered clause under deflation ⇒ **the served P1.4/S1 "
          "shape stands.** A null here is a valid, recorded outcome, not a failed story.")
    A("")
    A("## The premise, re-measured")
    A("")
    A("The story card cites the incumbent's total PITdev as **0.0218** — that is "
      "`ncaaf_p1_4_calibration.json` (contract `strength_only`), a **superseded** contract. The "
      "config that actually SERVES (`ncaaf_s1_serve_calibration.json`, contract `strength_pace`) is "
      "at **0.0173 and PIT-flat**; P1.4's failure was `pit_mean_dev` 0.0263, a LOCATION defect the "
      "S1 pace term largely repaired. The foil here is therefore the SERVED config, not the card's "
      "— measuring against 0.0218 would hand every candidate a 0.0045 head start it did not earn.")
    A("")
    r = d["run_validity"]["reproduction_check"]
    A(f"Reproduction gate R: **{r.get('status')}** — refit σ {r.get('refit')} vs served "
      f"{r.get('served')} (δ {r.get('delta')}, tol {r.get('tol_points')} pts).")
    A("")
    A("## Data prerequisite — weather")
    A("")
    A(f"**ABSENT.** {d.get('weather_drivers_absent')}")
    A("")
    A("## Leaderboard (primary = pooled total-CRPS, lower better)")
    A("")
    A("| arm | doc §4.1 item | crps_total | gain vs foil | folds won | DSR | p | total PITdev | clauses |")
    A("|---|---|---|---|---|---|---|---|---|")
    f = d["foil"]
    A(f"| **`{f['arm']}` (FOIL)** | the served form | {f['pooled_crps_total']:.5f} | — | — | — | — | "
      f"{f['pooled']['total_pit_dev']:.4f} | — |")
    for a, row in sorted(d["arms"].items(), key=lambda kv: kv[1]["pooled_crps_total"]):
        bad = [k.split("_")[0] for k, v in row["clauses"].items() if k.startswith("C") and not v["ok"]]
        A(f"| `{a}` | {row['doc_item']} | {row['pooled_crps_total']:.5f} | "
          f"{row['gain_vs_foil']:+.5f}{' *(TIE)*' if row['tie_with_foil'] else ''} | "
          f"{row['fold_wins']}/{row['n_folds']} | "
          f"{('%.3f' % row['dsr']) if row['dsr'] is not None else '—'} | {row['p_one_sided']:.4f} | "
          f"{row['clauses']['C1_total_pit_flat']['pit_dev']:.4f} | "
          f"{'✅ all' if not bad else '❌ ' + ', '.join(bad)} |")
    A("")
    dd = d["deflation"]
    pc = d["pbo_companions"]
    A("## Deflation")
    A("")
    A(f"- **PBO {dd['pbo']:.3f}** ({'PASS' if dd['pbo_pass'] else 'FAIL'} < {dd['pbo_gate']}) over "
      f"{dd['n_buckets']} buckets / {dd['n_cscv_combos']} CSCV combos.")
    A(f"- **DSR** on the per-FOLD matched-pair series, `n_trials = {d['n_trials']}` (the declared "
      f"field), `V = {d['var_trials_sr_real_arms_only']}` measured over the REAL arms only — "
      "⛔ anchors are excluded from both, because an anchor that polices the metric must not set the "
      "gate's own bar (MH2.1 a).")
    A(f"- **BH-FDR** α={dd['bh_alpha']} across the {len(d['arms'])} candidate contrasts; cutoff "
      f"{dd['bh_cutoff']:.4g}.")
    A(f"- Contender spread **{pc['contender_spread_pct_of_foil']:.3f}%** of the foil's CRPS; "
      f"per-fold flip distribution `{pc['fold_flip_distribution']}`.")
    A("")
    A(f"  {pc['reading']}")
    A("")
    A("## Run-validity anchors (⛔ diagnostic, never trials)")
    A("")
    an = d["run_validity"]["anchors"]
    A("| anchor | pre-registered expectation | observed |")
    A("|---|---|---|")
    for k, exp in an["expectations"].items():
        obs = an.get(k, {})
        A(f"| `{k}` | {exp} | `{json.dumps({kk: vv for kk, vv in obs.items() if kk != 'reading'})}` |")
    A("")
    mf = an.get("mechanism_findings", {})
    if mf:
        A(f"**Conditional-variance channel** (the `permute` read — REPORTED, never a validity gate): "
          f"the shuffled-driver fit came in `{mf.get('permute_minus_cond_het')}` against the real "
          f"one ⇒ the channel is "
          f"**{'REAL' if mf.get('conditional_variance_channel_is_real') else 'NOT REAL'}**. "
          f"{mf.get('reading')}")
        A("")
    A("**Per-form oracle floor** (NF-D16 g‴ — one ceiling per form, because the families NEST and a "
      "single field-wide ceiling would falsely veto a legitimately better nested form; a TIE is "
      "INACTIVE, never a refusal — NF-W6d):")
    A("")
    A("| arm | pooled CRPS | own-form PEEKING oracle | gap | state | self-consistency (diagnostic) |")
    A("|---|---|---|---|---|---|")
    for a, o in sorted(an["per_form_oracle"].items(),
                       key=lambda kv: kv[1]["own_form_peeking_oracle"]):
        A(f"| `{a}` | {o['pooled_crps_total']:.5f} | {o['own_form_peeking_oracle']:.5f} | "
          f"{o['gap']:+.5f} | {o['state']} | {o['self_consistency_crps']:.5f} |")
    A("")
    if d["null_classification"]:
        n = d["null_classification"]
        A("## Null classification")
        A("")
        A(f"- best arm `{n['best_arm']}` → recorded state **{n['recorded_state']}** "
          f"(binding half: **{n['binding_half']}**).")
        A(f"- `cv_power.classify_null` state `{n['instrument_state']}` — passed the series' OWN "
          "measured skew/kurtosis and `declared_field_size="
          f"{n['declared_field_size']}` (⛔ never the Gaussian default: that disagreement publishes a "
          "misleading 'come back with more seasons' trigger — NCAAF-P2.1-S1b defect 1).")
        if n["constraint_clauses_failed"]:
            A(f"- ship clauses that BOUND: `{', '.join(n['constraint_clauses_failed'])}`.")
        A(f"- {n['why_recorded_state']}")
        A(f"- instrument reason: {n['instrument_reason']}")
        if n.get("instrument_retest_trigger"):
            A(f"- instrument re-test trigger: {n['instrument_retest_trigger']}")
        A("")
    A("## Honest framing")
    A("")
    A(d["honest_frame"])
    A("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"Story {_STORY} — distribution-shape bake-off")
    ap.add_argument("--stage", choices=["battery", "decide"], required=True)
    ap.add_argument("--max-folds", type=int, default=None)
    ap.add_argument("--n-draws", type=int, default=_N_DRAWS)
    ap.add_argument("--arms", type=str, default=None, help="comma-separated subset (smoke only)")
    ap.add_argument("--smoke", action="store_true", help="800 draws — plumbing only, never a verdict")
    args = ap.parse_args()
    if args.stage == "battery":
        stage_battery(args)
    else:
        stage_decide(args)


if __name__ == "__main__":
    main()
