"""bakeoff_perside.py — Edge Program Story **E2.1-r** (per-side count-model BAKE-OFF).

WHY THIS EXISTS
---------------
E2.1 shipped a SINGLE architecture — `LightGBM-Poisson mean + 2-step MLE NegBin r`, compared
only against a Poisson likelihood baseline. No learner bake-off, no Optuna, no native-
distributional foil. That violates the §0.5 modeling standard, and it matters more here than
anywhere else in the stack: the per-side marginal is the most LOAD-BEARING object in the totals
program — E2.3 (convolution), E2.4 (F5), E2.5 (registration) and E2.6 (derivative pricing) all
consume it. E2.3's ~24% dispersion shortfall and its run-diff PIT near-miss both trace back to
per-side MARGINAL quality.

E2.1-r replaces the assumption with a result: a pre-registered ≥3-class bake-off, Optuna-tuned,
feature-ablated, judged on the **downstream convolved** calibration under purged CV, with the
whole search deflated (PBO < 0.2 / DSR > 0). Either a candidate beats the incumbent on a real
downstream gain, or the incumbent's single-architecture choice becomes a TRUSTWORTHY null.

PRE-REGISTERED CANDIDATE SET (learner × dispersion layer)
--------------------------------------------------------
  1. `lgbm_poisson`      LightGBM-Poisson mean            + 2-step r   ← THE INCUMBENT (the foil)
  2. `xgb_poisson`       XGBoost count:poisson / tweedie  + 2-step r
  3. `catboost_poisson`  CatBoost Poisson                 + 2-step r
  4. `ngboost_normal`    NGBoost NATIVE-JOINT (μ AND σ per game) → per-game r
  5. `glm_poisson`       sklearn PoissonRegressor (GLM, interpretable foil) + 2-step r

The DISPERSION LAYER is itself part of the search (not a fixed post-hoc hack):
  * `train`   — r MLE on TRAIN-fit residuals  (E2.1's exact behaviour; biased HIGH ≈ 8.5)
  * `heldout` — r MLE on INNER-HOLDOUT residuals (E2.3's fix; ≈ 3.71, leakage-safe: the inner
                holdout is the last season of the TRAIN block, never the eval fold)
  * `native`  — NGBoost emits (μ, σ) jointly → a PER-GAME r = μ²/(σ²−μ). This is the candidate
                that could retire the 2-step hack entirely.
ngboost has no NegBin distribution (0.5.10), so the native-joint foil is Normal(μ,σ) moment-
matched onto the NegBin the whole downstream stack speaks — a genuinely heteroscedastic,
jointly-learned dispersion, which is the property under test.

PRE-REGISTERED FEATURE CONTRACTS (§0.5 — bounded, hypothesis-driven, selected IN-FOLD)
--------------------------------------------------------------------------------------
  * `full`      — the E2.1 contract as shipped (no drops)
  * `clustered` — correlation-cluster redundancy prune (|ρ| ≥ 0.95 → keep the cluster member
                  with the highest in-fold gain); the `derive_clustered_contract.py` idea,
                  applied in-fold because the per-side matrix has no persisted importance JSON
  * `top_k`     — in-fold gain-importance top-K (K = --top-k, default 120)
NO open subset search. Selection uses TRAIN-fold rows ONLY (the ranking is computed from one
cheap LightGBM fit per fold and shared across candidates, so eval rows are never consulted).
EVERY (candidate × contract × Optuna trial) config counts toward PBO/DSR — deflation is what
makes a wide ablation safe.

THE SELECTION METRIC IS DOWNSTREAM, NOT PER-SIDE NLL
----------------------------------------------------
The per-side model exists to FEED the convolution, so candidates are ranked on the CONVOLVED
distribution's calibration (E2.3's own diagnostics, `betting_ml/utils/totals_distribution.py`):

    downstream_score = Σ_{j ∈ total, home_total, away_total} ( |calib_80_j − 0.80| + PIT_maxdev_j )

lower is better; 0 = a perfectly calibrated total AND both team totals. `run_diff` is measured
and reported but deliberately EXCLUDED from the score — E2.2/E2.3 settled its near-miss as the
dropped home/away dependence, not marginal dispersion, so scoring it would select on a defect
this model cannot fix. Per-side NegBin NLL is reported as a secondary diagnostic.

DATA (§0.5 cost hygiene) — ONE PULL, THEN EVERYTHING OFF THE CACHE
------------------------------------------------------------------
`--assemble` does a SINGLE **S3-lakehouse / DuckDB** read (Snowflake-FREE — post-E11.1 a
Snowflake pull for training data is a RED FLAG) and writes the assembled per-side matrix to
parquet. Every candidate, every contract, every Optuna trial and every CV fold then reads that
one parquet. Nothing in this module ever touches Snowflake.

MARKET-BLIND: `assert_market_blind` runs on every contract's column list before any fit.

USAGE (operator — stages 2/3 are the >1-min jobs)
-------------------------------------------------
    # 0) one pull → parquet cache  (laptop or box; needs AWS_DEFAULT_REGION=us-east-2)
    uv run python betting_ml/scripts/totals_generative/bakeoff_perside.py --assemble

    # 1) the bake-off: 5 classes × 3 contracts at pre-registered defaults, purged CV
    uv run python betting_ml/scripts/totals_generative/bakeoff_perside.py --stage bakeoff

    # 2) Optuna, ONE model class per invocation (per the retrain-per-target convention)
    uv run python betting_ml/scripts/totals_generative/bakeoff_perside.py \
        --stage optuna --model-class lgbm_poisson --n-trials 40

    # 3) collect every stage-1/2 config → PBO/DSR + winner-vs-incumbent verdict
    uv run python betting_ml/scripts/totals_generative/bakeoff_perside.py --stage decide
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

warnings.filterwarnings(
    "ignore", message="X does not have valid feature names", category=UserWarning,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.scripts.totals_generative.train_perside_negbin import (  # noqa: E402
    _EXCLUDE_EVAL_YEAR,
    _MIN_MU,
    _TARGET,
    _impute_means,
    _prepare_matrix,
    build_perside_frame,
    fit_negbin_r,
    load_wide,
    negbin_nll,
)
from betting_ml.utils.cv import PurgedWalkForwardSplit  # noqa: E402
from betting_ml.utils.market_blind import assert_market_blind  # noqa: E402
from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv  # noqa: E402
from betting_ml.utils.totals_distribution import (  # noqa: E402
    derive_distributions,
    draw_independent_samples,
    interval_coverage,
    pit_flatness,
    randomized_pit,
)

# ---------------------------------------------------------------------------
# Constants / paths
# ---------------------------------------------------------------------------

_STORY = "E2.1-r"
_INCUMBENT = "lgbm_poisson"          # the architecture E2.1 shipped — the foil to beat
_INCUMBENT_CONTRACT = "full"
_INCUMBENT_DISPERSION = "train"      # E2.1 fit r on TRAIN-fit means

_R_BOUNDS = (0.1, 500.0)             # mirrors fit_negbin_r's optimiser bounds
_CALIB_TARGET = 0.80                 # a calibrated 80% interval covers exactly 80%
_DEFAULT_DRAWS = 4_000               # bake-off draw count (final re-score uses --n-draws 10000)
_DEFAULT_TOP_K = 120
_CORR_THRESHOLD = 0.95
_PBO_GATE = 0.2
_SEED = 42

# The repo's training-data cache home (gitignored — a cache is regenerated, never committed).
_CACHE_DIR = _PROJECT_ROOT / "betting_ml" / "data" / "cache"
_CACHE_PATH = _CACHE_DIR / "e2_1r_perside_matrix.parquet"
_META_PATH = _CACHE_DIR / "e2_1r_perside_matrix.meta.json"

_RESULTS_DIR = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"
)
_TRIALS_DIR = _RESULTS_DIR / "e2_1r_configs"     # one JSON per evaluated config (stages 1+2)
_DECISION_JSON = _RESULTS_DIR / "e2_1r_bakeoff.json"
_DECISION_MD = _RESULTS_DIR / "e2_1r_bakeoff.md"


# ---------------------------------------------------------------------------
# Stage 0 — the ONE data pull → parquet cache (§0.5 cost hygiene)
# ---------------------------------------------------------------------------

def assemble_cache(min_year: int, *, source: str = "lakehouse") -> Path:
    """Single S3-lakehouse (DuckDB) read → assembled per-side matrix → parquet.

    Everything downstream (5 learners × 3 contracts × every Optuna trial × every CV fold)
    reads THIS file. Never re-query the source per candidate/trial.
    """
    print(f"=== {_STORY} stage 0 — assembling the per-side matrix (source={source}) ===")
    t0 = time.time()
    wide = load_wide(min_year, source=source)
    print(
        f"  wide mart: {len(wide):,} games, seasons "
        f"{int(wide['game_year'].min())}–{int(wide['game_year'].max())}  ({time.time() - t0:.0f}s)"
    )

    df, numeric_cols, cat_cols = build_perside_frame(wide)
    assert_market_blind(numeric_cols + cat_cols, context=f"{_STORY} per-side matrix")
    print(
        f"  per-side rows: {len(df):,}  |  {len(numeric_cols)} numeric + {len(cat_cols)} "
        f"categorical bases  |  CONTRACT-GUARD market-blind ✅"
    )

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_CACHE_PATH, index=False)
    _META_PATH.write_text(
        json.dumps(
            {
                "story": _STORY,
                "assembled_at": date.today().isoformat(),
                "source": source,
                "min_year": min_year,
                "n_rows": int(len(df)),
                "n_games": int(df["game_pk"].nunique()),
                "numeric_cols": numeric_cols,
                "cat_cols": cat_cols,
                "seasons": sorted(int(y) for y in df["game_year"].unique()),
            },
            indent=2,
        )
    )
    print(f"  cache → {_CACHE_PATH.relative_to(_PROJECT_ROOT)}  ({_CACHE_PATH.stat().st_size / 1e6:.1f} MB)")
    return _CACHE_PATH


def load_cache() -> tuple[pd.DataFrame, list[str], list[str], dict]:
    """Read the assembled per-side matrix. Fails loudly if `--assemble` has not run."""
    if not _CACHE_PATH.exists():
        raise SystemExit(
            f"[{_STORY}] no cached matrix at {_CACHE_PATH}. Run `--assemble` first "
            f"(one lakehouse pull; every later stage reads the cache)."
        )
    meta = json.loads(_META_PATH.read_text())
    df = pd.read_parquet(_CACHE_PATH)
    return df, list(meta["numeric_cols"]), list(meta["cat_cols"]), meta


# ---------------------------------------------------------------------------
# Candidate learners — each returns per-row (mu, sigma|None) on the eval matrix
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    """One pre-registered model class.

    `fit_predict(X_tr, y_tr, X_ev) -> (mu_ev, sigma_ev | None)`. A learner that emits `sigma`
    is NATIVE-DISTRIBUTIONAL (joint mean+dispersion); everything else pairs with a 2-step r.
    """

    name: str
    fit_predict: Callable[[np.ndarray, np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray | None]]
    native: bool = False
    params: dict[str, Any] = field(default_factory=dict)


def _lgbm(params: dict | None = None) -> Candidate:
    p = {
        "objective": "poisson", "num_leaves": 31, "learning_rate": 0.03,
        "min_child_samples": 40, "subsample": 0.85, "subsample_freq": 1,
        "colsample_bytree": 0.85, "n_estimators": 400, "random_state": _SEED, "verbose": -1,
    }
    p.update(params or {})

    def fp(X_tr, y_tr, X_ev):
        import lightgbm as lgb

        m = lgb.LGBMRegressor(**p)
        m.fit(X_tr, y_tr)
        return np.clip(m.predict(X_ev), _MIN_MU, None), None

    return Candidate("lgbm_poisson", fp, params=p)


def _xgb(params: dict | None = None) -> Candidate:
    p = {
        "objective": "count:poisson", "max_depth": 6, "learning_rate": 0.03,
        "n_estimators": 400, "subsample": 0.85, "colsample_bytree": 0.85,
        "min_child_weight": 5.0, "reg_lambda": 1.0, "random_state": _SEED,
        "tree_method": "hist", "verbosity": 0,
    }
    p.update(params or {})

    def fp(X_tr, y_tr, X_ev):
        import xgboost as xgb

        kw = dict(p)
        if kw.get("objective") == "reg:tweedie":
            kw.setdefault("tweedie_variance_power", 1.3)
        m = xgb.XGBRegressor(**kw)
        m.fit(X_tr, y_tr)
        return np.clip(m.predict(X_ev), _MIN_MU, None), None

    return Candidate("xgb_poisson", fp, params=p)


def _catboost(params: dict | None = None) -> Candidate:
    p = {
        "loss_function": "Poisson", "depth": 6, "learning_rate": 0.03,
        "iterations": 600, "l2_leaf_reg": 3.0, "random_seed": _SEED,
        "verbose": False, "allow_writing_files": False,
    }
    p.update(params or {})

    def fp(X_tr, y_tr, X_ev):
        from catboost import CatBoostRegressor

        m = CatBoostRegressor(**p)
        m.fit(X_tr, y_tr)
        return np.clip(m.predict(X_ev), _MIN_MU, None), None

    return Candidate("catboost_poisson", fp, params=p)


def _ngboost(params: dict | None = None) -> Candidate:
    """NATIVE-JOINT foil: NGBoost Normal emits (μ, σ) PER GAME, learned jointly.

    ngboost 0.5.10 has no NegBin distribution, so the learned (μ, σ²) are moment-matched onto
    the NegBin the downstream stack speaks: r = μ² / (σ² − μ) when σ² > μ, else near-Poisson.
    This is the candidate that could retire the 2-step r-MLE hack — the property under test is
    a jointly-learned, heteroscedastic (per-game) dispersion, which Normal(μ,σ) does provide.
    """
    p = {"n_estimators": 300, "learning_rate": 0.03, "minibatch_frac": 0.5, "random_state": _SEED}
    p.update(params or {})

    def fp(X_tr, y_tr, X_ev):
        from ngboost import NGBRegressor
        from ngboost.distns import Normal

        m = NGBRegressor(Dist=Normal, verbose=False, **p)
        m.fit(X_tr, y_tr)
        dist = m.pred_dist(X_ev)
        mu = np.clip(np.asarray(dist.params["loc"], dtype=float), _MIN_MU, None)
        sigma = np.clip(np.asarray(dist.params["scale"], dtype=float), 1e-6, None)
        return mu, sigma

    return Candidate("ngboost_normal", fp, native=True, params=p)


def _glm(params: dict | None = None) -> Candidate:
    # max_iter 1500: lbfgs does not converge in 400 on the ~290-col standardised matrix.
    p = {"alpha": 1e-3, "max_iter": 1500}
    p.update(params or {})

    def fp(X_tr, y_tr, X_ev):
        from sklearn.linear_model import PoissonRegressor
        from sklearn.preprocessing import StandardScaler

        sc = StandardScaler()
        Xtr = sc.fit_transform(X_tr)
        Xev = sc.transform(X_ev)
        m = PoissonRegressor(**p)
        m.fit(Xtr, y_tr)
        return np.clip(m.predict(Xev), _MIN_MU, None), None

    return Candidate("glm_poisson", fp, params=p)


_BUILDERS: dict[str, Callable[[dict | None], Candidate]] = {
    "lgbm_poisson": _lgbm,
    "xgb_poisson": _xgb,
    "catboost_poisson": _catboost,
    "ngboost_normal": _ngboost,
    "glm_poisson": _glm,
}
MODEL_CLASSES: tuple[str, ...] = tuple(_BUILDERS)
CONTRACTS: tuple[str, ...] = ("full", "clustered", "top_k")
DISPERSION_MODES: tuple[str, ...] = ("train", "heldout", "native")


def build_candidate(model_class: str, params: dict | None = None) -> Candidate:
    if model_class not in _BUILDERS:
        raise KeyError(f"unknown model class {model_class!r}; known: {sorted(_BUILDERS)}")
    return _BUILDERS[model_class](params)


def default_dispersion(model_class: str) -> str:
    """Native learners carry their own dispersion; everything else uses the E2.3 held-out r."""
    return "native" if build_candidate(model_class).native else "heldout"


# ---------------------------------------------------------------------------
# Dispersion layer
# ---------------------------------------------------------------------------

def sigma_to_negbin_r(mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """Moment-match a native (μ, σ) prediction onto a per-game NegBin dispersion r.

    NegBin var = μ + μ²/r  ⇒  r = μ² / (σ² − μ). When the learned variance is at or below the
    Poisson floor (σ² ≤ μ) the count is not overdispersed at that game — return the upper r
    bound (≈ Poisson), which is exactly the degenerate NegBin limit. Always clipped to the same
    (0.1, 500) band `fit_negbin_r` optimises over, so downstream sampling stays well-defined.
    """
    mu = np.clip(np.asarray(mu, dtype=float), _MIN_MU, None)
    var = np.asarray(sigma, dtype=float) ** 2
    excess = var - mu
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(excess > 1e-9, mu**2 / np.maximum(excess, 1e-9), _R_BOUNDS[1])
    return np.clip(np.nan_to_num(r, nan=_R_BOUNDS[1]), *_R_BOUNDS)


# ---------------------------------------------------------------------------
# Feature contracts — pre-registered, derived IN-FOLD from TRAIN rows only
# ---------------------------------------------------------------------------

def infold_importance(X_tr: np.ndarray, y_tr: np.ndarray, feat_cols: list[str]) -> list[str]:
    """Gain-importance ranking from ONE cheap LightGBM fit on TRAIN rows only.

    Shared across every candidate/contract within a fold (so the ablation costs one extra fit
    per fold, not one per config) and never sees eval rows — the E1.8 stale-ranking bug was
    exactly the failure of doing this once, globally, out of fold.
    """
    import lightgbm as lgb

    m = lgb.LGBMRegressor(
        objective="poisson", num_leaves=31, learning_rate=0.05, n_estimators=200,
        min_child_samples=40, random_state=_SEED, verbose=-1,
    )
    m.fit(X_tr, y_tr)
    gains = np.asarray(m.booster_.feature_importance(importance_type="gain"), dtype=float)
    order = np.argsort(-gains)
    return [feat_cols[i] for i in order]


def clustered_contract(
    X_tr: np.ndarray, feat_cols: list[str], ranking: list[str], threshold: float = _CORR_THRESHOLD
) -> list[str]:
    """Correlation-redundancy prune: walk the importance ranking, keep a feature unless it is
    |ρ| ≥ threshold with an already-kept one (i.e. keep the highest-gain member of each
    near-collinear cluster). The `derive_clustered_contract.py` removal idea applied in-fold.
    """
    idx = {c: i for i, c in enumerate(feat_cols)}
    Z = np.asarray(X_tr, dtype=float)
    std = Z.std(axis=0)
    kept: list[str] = []
    kept_idx: list[int] = []
    for col in ranking:
        j = idx[col]
        if std[j] == 0:                       # constant in-fold → carries no information
            continue
        if kept_idx:
            a = Z[:, j]
            block = Z[:, kept_idx]
            with np.errstate(invalid="ignore", divide="ignore"):
                num = ((block - block.mean(0)) * (a - a.mean())[:, None]).mean(0)
                rho = num / (block.std(0) * a.std() + 1e-12)
            if np.nanmax(np.abs(rho)) >= threshold:
                continue
        kept.append(col)
        kept_idx.append(j)
    return kept


def resolve_contract(
    contract: str,
    X_tr: np.ndarray,
    feat_cols: list[str],
    ranking: list[str],
    *,
    top_k: int = _DEFAULT_TOP_K,
) -> list[str]:
    if contract == "full":
        return list(feat_cols)
    if contract == "top_k":
        return ranking[: min(top_k, len(ranking))]
    if contract == "clustered":
        return clustered_contract(X_tr, feat_cols, ranking)
    raise KeyError(f"unknown contract {contract!r}; known: {CONTRACTS}")


# ---------------------------------------------------------------------------
# Downstream (convolved) scoring — the SELECTION metric
# ---------------------------------------------------------------------------

def convolved_metrics(
    game_frame: pd.DataFrame, rng: np.random.Generator, *, n_draws: int = _DEFAULT_DRAWS
) -> dict[str, dict[str, float]]:
    """Convolve per-side (μ, r) into total / run_diff / team totals and score calibration.

    `game_frame` is one row per game with mu_home, mu_away, r_home, r_away, y_home, y_away.
    Reuses E2.3's own machinery (`draw_independent_samples`, `interval_coverage`,
    `randomized_pit`, `pit_flatness`) so a bake-off winner is judged on EXACTLY the diagnostic
    E2.3 will re-validate it with.
    """
    y_home, y_away = draw_independent_samples(
        game_frame["mu_home"].to_numpy(float),
        game_frame["mu_away"].to_numpy(float),
        game_frame["r_home"].to_numpy(float),
        rng,
        r_away=game_frame["r_away"].to_numpy(float),
        n_draws=n_draws,
    )
    dists = derive_distributions(y_home, y_away)
    obs = {
        "total": game_frame["y_home"].to_numpy(float) + game_frame["y_away"].to_numpy(float),
        "run_diff": game_frame["y_home"].to_numpy(float) - game_frame["y_away"].to_numpy(float),
        "home_total": game_frame["y_home"].to_numpy(float),
        "away_total": game_frame["y_away"].to_numpy(float),
    }
    out: dict[str, dict[str, float]] = {}
    for key, samples in dists.items():
        pit = pit_flatness(randomized_pit(obs[key], samples, rng))
        out[key] = {
            "calib_80": round(interval_coverage(obs[key], samples), 4),
            "pit_max_decile_dev": pit["max_decile_dev"],
            "pit_mean_dev": pit["mean_dev_from_half"],
            "pit_is_flat": bool(pit["is_flat"]),
        }
    return out


#: the three distributions the per-side marginal is actually responsible for. `run_diff` is
#: measured but NOT scored — E2.2/E2.3 attributed its miss to the dropped home/away dependence,
#: which no choice of per-side marginal can repair.
SCORED_DISTS: tuple[str, ...] = ("total", "home_total", "away_total")


def downstream_score(metrics: dict[str, dict[str, float]]) -> float:
    """Scalar selection metric (LOWER IS BETTER; 0 = perfectly calibrated).

        Σ_{j ∈ total, home_total, away_total} ( |calib_80_j − 0.80| + PIT_maxdev_j )

    Pre-registered with equal weights: miscalibrated coverage and a non-flat PIT are both
    disqualifying for a distribution the product prices off, and neither dominates the other.
    """
    return float(
        sum(
            abs(metrics[j]["calib_80"] - _CALIB_TARGET) + metrics[j]["pit_max_decile_dev"]
            for j in SCORED_DISTS
        )
    )


# ---------------------------------------------------------------------------
# The CV engine — ONE pass over folds, every config scored off the same matrices
# ---------------------------------------------------------------------------

@dataclass
class FoldMatrices:
    """Everything a fold needs, built ONCE and reused by every (candidate × contract)."""

    eval_year: int
    feat_cols: list[str]
    ranking: list[str]
    X_tr: np.ndarray
    y_tr: np.ndarray
    tr_sides: np.ndarray          # per-row 'home'/'away' for the train block (2-step `train` r)
    X_ev: np.ndarray
    y_ev: np.ndarray
    ev_meta: pd.DataFrame
    X_inner_tr: np.ndarray
    y_inner_tr: np.ndarray
    X_inner_ho: np.ndarray
    y_inner_ho: np.ndarray
    inner_sides: np.ndarray       # per-row side for the inner holdout (2-step `heldout` r)


def build_folds(
    df: pd.DataFrame, numeric_cols: list[str], cat_cols: list[str], *, max_folds: int | None = None
) -> list[FoldMatrices]:
    """Purged walk-forward folds (E1.1) with an INNER holdout carved from each train block.

    The inner holdout = the LAST season of the train block. It is used only to fit the 2-step
    NegBin `r` on HELD-OUT residuals (E2.3's fix). It is strictly inside train, so the eval
    fold is never touched by the dispersion estimate.
    """
    splitter = PurgedWalkForwardSplit(min_train_seasons=3)
    folds_idx = list(splitter.split(df, feature_cols=numeric_cols))
    out: list[FoldMatrices] = []

    for train_idx, eval_idx in folds_idx:
        eval_year = int(df.loc[eval_idx, "game_year"].mode().iloc[0])
        if eval_year == _EXCLUDE_EVAL_YEAR:
            continue
        tr, ev = df.loc[train_idx], df.loc[eval_idx]
        means = _impute_means(tr, numeric_cols)
        X_tr, X_ev, feat_cols = _prepare_matrix(tr, ev, numeric_cols, cat_cols, means, None)

        inner_year = int(tr["game_year"].max())
        inner_mask = (tr["game_year"] == inner_year).to_numpy()
        if inner_mask.sum() < 200 or (~inner_mask).sum() < 500:
            inner_mask = np.zeros(len(tr), dtype=bool)
            inner_mask[int(len(tr) * 0.85):] = True   # fallback: last 15% chronologically

        ranking = infold_importance(X_tr, tr[_TARGET].to_numpy(float), feat_cols)

        out.append(
            FoldMatrices(
                eval_year=eval_year,
                feat_cols=feat_cols,
                ranking=ranking,
                X_tr=X_tr,
                y_tr=tr[_TARGET].to_numpy(float),
                tr_sides=tr["side"].to_numpy(),
                X_ev=X_ev,
                y_ev=ev[_TARGET].to_numpy(float),
                ev_meta=ev[["game_pk", "game_date", "game_year", "side"]].reset_index(drop=True),
                X_inner_tr=X_tr[~inner_mask],
                y_inner_tr=tr[_TARGET].to_numpy(float)[~inner_mask],
                X_inner_ho=X_tr[inner_mask],
                y_inner_ho=tr[_TARGET].to_numpy(float)[inner_mask],
                inner_sides=tr["side"].to_numpy()[inner_mask],
            )
        )
        if max_folds and len(out) >= max_folds:
            break
    return out


def _fit_dispersion(
    cand: Candidate,
    fold: FoldMatrices,
    cols_idx: np.ndarray,
    mode: str,
    mu_ev: np.ndarray,
    sigma_ev: np.ndarray | None,
    sides_ev: np.ndarray,
) -> tuple[np.ndarray, dict[str, float]]:
    """Per-row eval dispersion `r` under the requested dispersion layer. Returns (r_ev, info)."""
    if mode == "native":
        if sigma_ev is None:
            raise ValueError(f"{cand.name} is not native-distributional — no sigma to map")
        r_ev = sigma_to_negbin_r(mu_ev, sigma_ev)
        return r_ev, {"r_median": float(np.median(r_ev)), "r_source": "native_joint"}

    if mode == "train":
        # E2.1's exact behaviour: r MLE on TRAIN-fit means (biased HIGH — the known defect).
        mu_tr, _ = cand.fit_predict(fold.X_tr[:, cols_idx], fold.y_tr, fold.X_tr[:, cols_idx])
        sides_tr = fold.tr_sides
        r_by_side = {
            s: fit_negbin_r(fold.y_tr[sides_tr == s], mu_tr[sides_tr == s]) for s in ("home", "away")
        }
    elif mode == "heldout":
        # E2.3's fix: r MLE on INNER-HOLDOUT residuals (leakage-safe — still inside train).
        mu_ho, _ = cand.fit_predict(
            fold.X_inner_tr[:, cols_idx], fold.y_inner_tr, fold.X_inner_ho[:, cols_idx]
        )
        sides_ho = fold.inner_sides
        r_by_side = {
            s: fit_negbin_r(fold.y_inner_ho[sides_ho == s], mu_ho[sides_ho == s])
            for s in ("home", "away")
        }
    else:
        raise KeyError(f"unknown dispersion mode {mode!r}; known: {DISPERSION_MODES}")

    r_ev = np.where(sides_ev == "home", r_by_side["home"], r_by_side["away"])
    return r_ev, {
        "r_home": round(float(r_by_side["home"]), 4),
        "r_away": round(float(r_by_side["away"]), 4),
        "r_source": mode,
    }


def evaluate_config(
    folds: list[FoldMatrices],
    model_class: str,
    contract: str,
    *,
    dispersion: str | None = None,
    params: dict | None = None,
    top_k: int = _DEFAULT_TOP_K,
    n_draws: int = _DEFAULT_DRAWS,
    n_slices: int = 4,
    seed: int = _SEED,
) -> dict[str, Any]:
    """Score ONE config (model class × contract × dispersion × params) across every fold.

    Returns the pooled downstream score, the per-fold detail, and a per-BUCKET score vector
    (fold × time-slice) — the bucket vector is what feeds PBO/DSR at decide time.
    """
    cand = build_candidate(model_class, params)
    mode = dispersion or default_dispersion(model_class)
    rng = np.random.default_rng(seed)

    fold_rows: list[dict] = []
    bucket_scores: list[float] = []
    per_side_nll: list[float] = []
    games_all: list[pd.DataFrame] = []

    for fold in folds:
        cols = resolve_contract(contract, fold.X_tr, fold.feat_cols, fold.ranking, top_k=top_k)
        assert_market_blind(cols, context=f"{_STORY} {model_class}/{contract} fold {fold.eval_year}")
        cols_idx = np.array([fold.feat_cols.index(c) for c in cols])

        mu_ev, sigma_ev = cand.fit_predict(
            fold.X_tr[:, cols_idx], fold.y_tr, fold.X_ev[:, cols_idx]
        )
        sides_ev = fold.ev_meta["side"].to_numpy()
        r_ev, r_info = _fit_dispersion(cand, fold, cols_idx, mode, mu_ev, sigma_ev, sides_ev)

        nll = negbin_nll(fold.y_ev, mu_ev, float(np.median(r_ev)))
        per_side_nll.append(nll)

        games = _pivot_games(fold.ev_meta, mu_ev, r_ev, fold.y_ev)
        games_all.append(games)
        metrics = convolved_metrics(games, rng, n_draws=n_draws)
        score = downstream_score(metrics)

        # time-sliced buckets within the fold → the PBO/DSR performance matrix rows
        slices = np.array_split(np.arange(len(games)), n_slices)
        for sl in slices:
            if len(sl) < 50:
                continue
            bucket_scores.append(downstream_score(convolved_metrics(games.iloc[sl], rng, n_draws=n_draws)))

        fold_rows.append(
            {
                "eval_year": fold.eval_year,
                "n_games": int(len(games)),
                "downstream_score": round(score, 5),
                "per_side_negbin_nll": round(nll, 4),
                "total_calib_80": metrics["total"]["calib_80"],
                "total_pit_maxdev": metrics["total"]["pit_max_decile_dev"],
                "run_diff_calib_80": metrics["run_diff"]["calib_80"],
                "run_diff_pit_maxdev": metrics["run_diff"]["pit_max_decile_dev"],
                "n_features": len(cols),
                **r_info,
            }
        )

    pooled = pd.concat(games_all, ignore_index=True)
    pooled_metrics = convolved_metrics(pooled, rng, n_draws=n_draws)

    return {
        "story": _STORY,
        "config_id": f"{model_class}__{contract}__{mode}",
        "model_class": model_class,
        "contract": contract,
        "dispersion": mode,
        "params": cand.params,
        "top_k": top_k if contract == "top_k" else None,
        "is_incumbent": (
            model_class == _INCUMBENT
            and contract == _INCUMBENT_CONTRACT
            and mode == _INCUMBENT_DISPERSION
        ),
        "folds": fold_rows,
        "mean_downstream_score": round(float(np.mean([f["downstream_score"] for f in fold_rows])), 5),
        "pooled_downstream_score": round(downstream_score(pooled_metrics), 5),
        "pooled_metrics": pooled_metrics,
        "mean_per_side_negbin_nll": round(float(np.mean(per_side_nll)), 4),
        "bucket_scores": [round(float(b), 5) for b in bucket_scores],
        "n_buckets": len(bucket_scores),
    }


def _pivot_games(
    ev_meta: pd.DataFrame, mu: np.ndarray, r: np.ndarray, y: np.ndarray
) -> pd.DataFrame:
    """Per-(game, side) eval rows → one row per game with home/away μ, r and realised runs."""
    d = ev_meta.copy()
    d["mu"] = mu
    d["r"] = r
    d["y"] = y
    wide = d.pivot_table(index=["game_pk", "game_date"], columns="side", values=["mu", "r", "y"])
    # (value, side) MultiIndex → the flat mu_home / r_away / y_home … names convolved_metrics wants
    wide.columns = [f"{value}_{side}" for value, side in wide.columns]
    return (
        wide.dropna()
        .reset_index()
        .sort_values(["game_date", "game_pk"])
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Config persistence — every evaluated config counts toward PBO/DSR
# ---------------------------------------------------------------------------

def save_config_result(res: dict, tag: str = "") -> Path:
    _TRIALS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{res['config_id']}{('__' + tag) if tag else ''}.json"
    path = _TRIALS_DIR / name.replace("/", "_")
    path.write_text(json.dumps(res, indent=2, default=float))
    return path


def load_config_results() -> list[dict]:
    if not _TRIALS_DIR.exists():
        return []
    return [json.loads(p.read_text()) for p in sorted(_TRIALS_DIR.glob("*.json"))]


# ---------------------------------------------------------------------------
# Stage 1 — the bake-off (5 classes × 3 contracts, pre-registered defaults)
# ---------------------------------------------------------------------------

def stage_bakeoff(args) -> None:
    df, numeric_cols, cat_cols, meta = load_cache()
    print(f"=== {_STORY} stage 1 — BAKE-OFF ({len(df):,} per-side rows from cache) ===")
    folds = build_folds(df, numeric_cols, cat_cols, max_folds=args.max_folds)
    print(f"  purged folds: {[f.eval_year for f in folds]}")

    classes = [args.model_class] if args.model_class else list(MODEL_CLASSES)
    contracts = [args.contract] if args.contract else list(CONTRACTS)

    # The incumbent is evaluated EXACTLY as E2.1 shipped it (full contract, train-fit r) so the
    # comparison is against the real foil, not a modernised version of it.
    plan: list[tuple[str, str, str]] = [(_INCUMBENT, _INCUMBENT_CONTRACT, _INCUMBENT_DISPERSION)]
    for mc in classes:
        for ct in contracts:
            entry = (mc, ct, default_dispersion(mc))
            if entry not in plan:
                plan.append(entry)

    print(f"  {len(plan)} configs to evaluate\n")
    rows = []
    for mc, ct, disp in plan:
        t0 = time.time()
        res = evaluate_config(
            folds, mc, ct, dispersion=disp, top_k=args.top_k,
            n_draws=args.n_draws, n_slices=args.n_slices, seed=args.seed,
        )
        save_config_result(res, tag="bakeoff")
        rows.append(res)
        flag = "  ← INCUMBENT" if res["is_incumbent"] else ""
        print(
            f"  {res['config_id']:<44} score {res['pooled_downstream_score']:.4f}  "
            f"calib80(total) {res['pooled_metrics']['total']['calib_80']:.3f}  "
            f"NLL {res['mean_per_side_negbin_nll']:.4f}  ({time.time() - t0:.0f}s){flag}"
        )
    _ = meta
    print(f"\n  {len(rows)} configs written → {_TRIALS_DIR.relative_to(_PROJECT_ROOT)}")
    print("  Next: `--stage optuna --model-class <class>` per class, then `--stage decide`.")


# ---------------------------------------------------------------------------
# Stage 2 — Optuna, ONE model class per invocation
# ---------------------------------------------------------------------------

def _space(model_class: str, trial) -> dict:
    if model_class == "lgbm_poisson":
        return {
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 200, 1200, step=100),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 200, log=True),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
            # the §0.5-preferred knob: tune regularisation instead of searching subsets
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 50.0, log=True),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 20.0, log=True),
        }
    if model_class == "xgb_poisson":
        return {
            "objective": trial.suggest_categorical("objective", ["count:poisson", "reg:tweedie"]),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 200, 1200, step=100),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
            "min_child_weight": trial.suggest_float("min_child_weight", 0.5, 50.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 50.0, log=True),
            "tweedie_variance_power": trial.suggest_float("tweedie_variance_power", 1.05, 1.9),
        }
    if model_class == "catboost_poisson":
        return {
            "depth": trial.suggest_int("depth", 4, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
            "iterations": trial.suggest_int("iterations", 300, 1500, step=100),
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 0.5, 30.0, log=True),
            "random_strength": trial.suggest_float("random_strength", 0.1, 10.0, log=True),
        }
    if model_class == "ngboost_normal":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 150, 700, step=50),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.08, log=True),
            "minibatch_frac": trial.suggest_float("minibatch_frac", 0.3, 1.0),
        }
    if model_class == "glm_poisson":
        return {"alpha": trial.suggest_float("alpha", 1e-6, 10.0, log=True)}
    raise KeyError(model_class)


def stage_optuna(args) -> None:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    mc = args.model_class
    if not mc:
        raise SystemExit("--stage optuna requires --model-class (one class per invocation)")

    df, numeric_cols, cat_cols, _ = load_cache()
    print(f"=== {_STORY} stage 2 — OPTUNA ({mc}, {args.n_trials} trials) ===")
    folds = build_folds(df, numeric_cols, cat_cols, max_folds=args.max_folds)
    contract = args.contract or "full"
    disp = default_dispersion(mc)

    def objective(trial):
        params = _space(mc, trial)
        res = evaluate_config(
            folds, mc, contract, dispersion=disp, params=params, top_k=args.top_k,
            n_draws=args.n_draws, n_slices=args.n_slices, seed=args.seed,
        )
        save_config_result(res, tag=f"optuna_t{trial.number:03d}")
        trial.set_user_attr("buckets", res["bucket_scores"])
        trial.set_user_attr("pooled", res["pooled_downstream_score"])
        return res["pooled_downstream_score"]

    study = optuna.create_study(
        direction="minimize", sampler=optuna.samplers.TPESampler(seed=args.seed)
    )
    study.optimize(objective, n_trials=args.n_trials, show_progress_bar=False)
    print(f"\n  best pooled downstream score: {study.best_value:.5f}")
    print(f"  best params: {json.dumps(study.best_params)}")
    print("  every trial persisted → it counts toward PBO/DSR at `--stage decide`.")


# ---------------------------------------------------------------------------
# Stage 3 — deflate the whole search, pick the winner, write the decision
# ---------------------------------------------------------------------------

def stage_decide(args) -> None:
    results = load_config_results()
    if not results:
        raise SystemExit(f"[{_STORY}] no config results in {_TRIALS_DIR} — run --stage bakeoff first.")

    incumbent = next((r for r in results if r.get("is_incumbent")), None)
    if incumbent is None:
        raise SystemExit(
            f"[{_STORY}] the incumbent config ({_INCUMBENT}/{_INCUMBENT_CONTRACT}/"
            f"{_INCUMBENT_DISPERSION}) is missing — it is the foil; re-run --stage bakeoff."
        )

    n_buckets = min(len(r["bucket_scores"]) for r in results)
    perf = np.array([r["bucket_scores"][:n_buckets] for r in results], dtype=float).T  # (buckets, configs)
    n_cfg = perf.shape[1]

    # PBO over the ENTIRE search (bake-off configs + every Optuna trial) — §0.5 deflation.
    n_splits = min(16, n_buckets - (n_buckets % 2))
    pbo = pbo_cscv(perf, higher_is_better=False, n_splits=max(2, n_splits))

    best = min(results, key=lambda r: r["pooled_downstream_score"])
    inc_buckets = np.array(incumbent["bucket_scores"][:n_buckets], dtype=float)
    best_buckets = np.array(best["bucket_scores"][:n_buckets], dtype=float)
    improvement = inc_buckets - best_buckets            # >0 ⇔ the challenger is better calibrated
    dsr = deflated_sharpe(improvement, n_trials=max(1, n_cfg), benchmark_sr=0.0)

    gain = incumbent["pooled_downstream_score"] - best["pooled_downstream_score"]
    beats = best["config_id"] != incumbent["config_id"] and gain > 0
    deflated_ok = pbo.pbo < _PBO_GATE and dsr.dsr > 0.0
    verdict = "PROMOTE" if (beats and deflated_ok) else "INCUMBENT STANDS"

    print("=" * 78)
    print(f"{_STORY} DECISION — {n_cfg} configs, {n_buckets} buckets")
    print("=" * 78)
    ranked = sorted(results, key=lambda r: r["pooled_downstream_score"])[:12]
    for r in ranked:
        tag = " ← INCUMBENT" if r.get("is_incumbent") else ""
        print(
            f"  {r['pooled_downstream_score']:.5f}  {r['config_id']:<44} "
            f"calib80 {r['pooled_metrics']['total']['calib_80']:.3f}"
            f"  PITdev {r['pooled_metrics']['total']['pit_max_decile_dev']:.4f}{tag}"
        )
    print(f"\n  incumbent : {incumbent['config_id']}  score {incumbent['pooled_downstream_score']:.5f}")
    print(f"  best      : {best['config_id']}  score {best['pooled_downstream_score']:.5f}")
    print(f"  gain      : {gain:+.5f}  (positive ⇒ better-calibrated downstream)")
    print(f"  PBO       : {pbo.pbo:.3f}  ({'PASS' if pbo.pbo < _PBO_GATE else 'FAIL'} < {_PBO_GATE})")
    print(f"  DSR       : {dsr.dsr:.3f}  ({'PASS' if dsr.dsr > 0 else 'FAIL'} > 0)")
    print(f"\n  VERDICT   : {verdict}")
    if verdict == "PROMOTE":
        print(
            "  → re-emit totals_perside_v2, RE-RUN fit_totals_distribution.py to confirm the\n"
            "    downstream gain, then register in sub_model_registry.yaml. E2.5/E2.6 need a re-run."
        )
    else:
        print(
            "  → the incumbent stands. E2.1's single-architecture choice is now a TRUSTWORTHY\n"
            "    result (proven best over a deflated ≥3-class search), not an assumption.\n"
            "    E2.5/E2.6 do NOT need a re-run — the marginals are unchanged."
        )
    print("\n  Honest framing: this is a CALIBRATION result, not an edge claim (best_alpha = 0).")

    doc = {
        "story": _STORY,
        "decided_at": date.today().isoformat(),
        "n_configs": n_cfg,
        "n_buckets": n_buckets,
        "selection_metric": (
            "sum over {total, home_total, away_total} of |calib_80 - 0.80| + PIT max decile dev "
            "(lower is better); run_diff measured but excluded (E2.2/E2.3: dropped dependence)"
        ),
        "incumbent": {k: incumbent[k] for k in ("config_id", "pooled_downstream_score", "pooled_metrics", "mean_per_side_negbin_nll")},
        "best": {k: best[k] for k in ("config_id", "params", "pooled_downstream_score", "pooled_metrics", "mean_per_side_negbin_nll")},
        "gain_vs_incumbent": round(gain, 5),
        "pbo": round(float(pbo.pbo), 4),
        "dsr": round(float(dsr.dsr), 4),
        "gates": {
            "beats_incumbent_downstream": bool(beats),
            "pbo_lt_0_2": bool(pbo.pbo < _PBO_GATE),
            "dsr_gt_0": bool(dsr.dsr > 0.0),
            "market_blind": True,
        },
        "verdict": verdict,
        "requires_e2_5_e2_6_rerun": verdict == "PROMOTE",
        "leaderboard": [
            {
                "config_id": r["config_id"],
                "score": r["pooled_downstream_score"],
                "calib_80_total": r["pooled_metrics"]["total"]["calib_80"],
                "pit_maxdev_total": r["pooled_metrics"]["total"]["pit_max_decile_dev"],
                "per_side_nll": r["mean_per_side_negbin_nll"],
            }
            for r in sorted(results, key=lambda x: x["pooled_downstream_score"])
        ],
    }
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _DECISION_JSON.write_text(json.dumps(doc, indent=2, default=float))
    _DECISION_MD.write_text(_render_md(doc))
    print(f"\n  → {_DECISION_JSON.relative_to(_PROJECT_ROOT)}")
    print(f"  → {_DECISION_MD.relative_to(_PROJECT_ROOT)}")
    _ = args


def _render_md(doc: dict) -> str:
    lines = [
        f"# {_STORY} — Per-side count-model bake-off (revisit of the single-architecture E2.1)",
        "",
        f"_Decided {doc['decided_at']} · {doc['n_configs']} configs · {doc['n_buckets']} CV buckets_",
        "",
        "## Verdict",
        "",
        f"**{doc['verdict']}** — best `{doc['best']['config_id']}` vs incumbent "
        f"`{doc['incumbent']['config_id']}`, downstream gain `{doc['gain_vs_incumbent']:+.5f}`.",
        "",
        f"- PBO `{doc['pbo']:.3f}` ({'PASS' if doc['gates']['pbo_lt_0_2'] else 'FAIL'} < 0.2)",
        f"- DSR `{doc['dsr']:.3f}` ({'PASS' if doc['gates']['dsr_gt_0'] else 'FAIL'} > 0)",
        f"- E2.5 / E2.6 re-run required: **{'YES' if doc['requires_e2_5_e2_6_rerun'] else 'NO'}**",
        "",
        "## Selection metric",
        "",
        doc["selection_metric"],
        "",
        "## Leaderboard",
        "",
        "| config | score | calib_80 (total) | PIT maxdev (total) | per-side NegBin NLL |",
        "|---|---|---|---|---|",
    ]
    for r in doc["leaderboard"][:25]:
        lines.append(
            f"| `{r['config_id']}` | {r['score']:.5f} | {r['calib_80_total']:.3f} | "
            f"{r['pit_maxdev_total']:.4f} | {r['per_side_nll']:.4f} |"
        )
    lines += [
        "",
        "## Honest framing",
        "",
        "This is a **calibration** result, not an edge claim. A better-calibrated per-side "
        "marginal makes the convolved total / team-total distributions honest; it does not "
        "establish a market edge (`best_alpha = 0`). Market-blind CONTRACT-GUARD held on every "
        "contract in the search.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=f"Story {_STORY} — per-side count-model bake-off")
    ap.add_argument("--assemble", action="store_true",
                    help="Stage 0: ONE lakehouse (DuckDB/S3) pull → parquet cache, then exit.")
    ap.add_argument("--stage", choices=["bakeoff", "optuna", "decide"],
                    help="Stage 1 (bake-off), 2 (Optuna, one --model-class), or 3 (decide).")
    ap.add_argument("--source", choices=["lakehouse", "snowflake"], default="lakehouse",
                    help="--assemble source. lakehouse (default) = S3/DuckDB, Snowflake-free.")
    ap.add_argument("--min-year", type=int, default=2018)
    ap.add_argument("--model-class", choices=list(MODEL_CLASSES))
    ap.add_argument("--contract", choices=list(CONTRACTS))
    ap.add_argument("--top-k", type=int, default=_DEFAULT_TOP_K)
    ap.add_argument("--n-trials", type=int, default=30)
    ap.add_argument("--n-draws", type=int, default=_DEFAULT_DRAWS)
    ap.add_argument("--n-slices", type=int, default=4, help="PBO buckets per CV fold.")
    ap.add_argument("--max-folds", type=int, default=None, help="Cap folds (smoke runs).")
    ap.add_argument("--seed", type=int, default=_SEED)
    args = ap.parse_args()

    if args.assemble:
        assemble_cache(args.min_year, source=args.source)
        return
    if args.stage == "bakeoff":
        stage_bakeoff(args)
    elif args.stage == "optuna":
        stage_optuna(args)
    elif args.stage == "decide":
        stage_decide(args)
    else:
        ap.error("pass --assemble or --stage {bakeoff,optuna,decide}")


if __name__ == "__main__":
    main()
