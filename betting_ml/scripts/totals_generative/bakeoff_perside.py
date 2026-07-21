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
import os
import sys
import time
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

# ⚠️ MUST precede `import numpy` — BLAS/OpenMP read their thread count at import time, and a
# later env change is ignored. Default 0 = leave the libraries alone; set E2_1R_THREADS=N to
# cap. Uncapped BLAS + an uncapped learner OVERSUBSCRIBE the CPU (N_blas × N_learner threads),
# which is how a 60s fit becomes a 210s one that LOOKS hung. See --n-jobs for the learner side.
_THREAD_CAP = os.environ.get("E2_1R_THREADS", "").strip()
if _THREAD_CAP:
    for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[_v] = _THREAD_CAP

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


# ---------------------------------------------------------------------------
# Progress logging
#
# WHY THIS IS NOT DECORATION: every heavy step here is a NATIVE call (LightGBM/XGBoost/CatBoost
# OpenMP kernels, BLAS in the GLM). While one is running, the Python interpreter is not
# executing — so there is no output AND Ctrl-C does not land until the native call returns.
# A silent multi-minute native fit is indistinguishable from a hang. Logging every step with a
# timestamp + elapsed is what makes "slow" distinguishable from "stuck".
# ---------------------------------------------------------------------------

_T0 = time.time()


def _log(msg: str, *, indent: int = 0) -> None:
    """Timestamped, FLUSHED progress line on stderr.

    stderr because stdout is where the machine-readable leaderboard goes, and flushing because a
    block-buffered pipe (`| tail`, `| tee`) is the other way a live run looks dead.
    """
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp} +{time.time() - _T0:6.0f}s] {'  ' * indent}{msg}", file=sys.stderr, flush=True)


class _Step:
    """Context manager that logs a step's start and its elapsed time on exit.

    Logging the START is the load-bearing half: it names the step you are currently blocked
    inside, which is exactly the information missing when a native fit appears to hang.
    """

    def __init__(self, msg: str, *, indent: int = 0):
        self.msg = msg
        self.indent = indent

    def __enter__(self):
        self.t0 = time.time()
        _log(f"{self.msg} …", indent=self.indent)
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            _log(f"{self.msg} ✓ ({time.time() - self.t0:.1f}s)", indent=self.indent)
        else:
            _log(f"{self.msg} ✗ FAILED after {time.time() - self.t0:.1f}s: {exc}", indent=self.indent)
        return False
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


#: Learner-level thread cap, set from --n-jobs. None = library default (all cores). Capping the
#: learner AND the BLAS (E2_1R_THREADS) is what prevents the oversubscription that makes an
#: otherwise-fine fit crawl. Applied at build time via the class's own thread parameter name.
_N_JOBS: int | None = None

_THREAD_PARAM: dict[str, str] = {
    "lgbm_poisson": "n_jobs",
    "xgb_poisson": "n_jobs",
    "catboost_poisson": "thread_count",
    # ngboost/sklearn GLM take their parallelism from the BLAS layer, not a constructor arg.
}


def set_n_jobs(n: int | None) -> None:
    global _N_JOBS
    _N_JOBS = n


def build_candidate(model_class: str, params: dict | None = None) -> Candidate:
    if model_class not in _BUILDERS:
        raise KeyError(f"unknown model class {model_class!r}; known: {sorted(_BUILDERS)}")
    merged = dict(params or {})
    if _N_JOBS is not None and model_class in _THREAD_PARAM:
        merged.setdefault(_THREAD_PARAM[model_class], _N_JOBS)
    return _BUILDERS[model_class](merged)


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

def draw_predictive(
    game_frame: pd.DataFrame, rng: np.random.Generator, *, n_draws: int = _DEFAULT_DRAWS
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Convolve per-side (μ, r) → (sampled distributions, realised observations).

    Split out from the scoring so a fold's draws can be taken ONCE and then SLICED for the PBO
    buckets. Sampling dominates this harness's runtime (a fold's draw array is
    n_games × n_draws), and each game's draws are independent, so a row-subset of the fold's
    samples IS the sub-population's predictive — re-drawing per bucket was pure waste, and it
    made the buckets independent redraws rather than exact sub-populations of the scored fold.

    `game_frame` is one row per game with mu_home, mu_away, r_home, r_away, y_home, y_away.
    """
    y_home, y_away = draw_independent_samples(
        game_frame["mu_home"].to_numpy(float),
        game_frame["mu_away"].to_numpy(float),
        game_frame["r_home"].to_numpy(float),
        rng,
        r_away=game_frame["r_away"].to_numpy(float),
        n_draws=n_draws,
    )
    obs_home = game_frame["y_home"].to_numpy(float)
    obs_away = game_frame["y_away"].to_numpy(float)
    obs = {
        "total": obs_home + obs_away,
        "run_diff": obs_home - obs_away,
        "home_total": obs_home,
        "away_total": obs_away,
    }
    return derive_distributions(y_home, y_away), obs


def score_predictive(
    dists: dict[str, np.ndarray],
    obs: dict[str, np.ndarray],
    rng: np.random.Generator,
    *,
    rows: np.ndarray | None = None,
) -> dict[str, dict[str, float]]:
    """Calibration diagnostics for a drawn predictive, optionally on a ROW SUBSET (a PBO bucket).

    Uses E2.3's own machinery (`interval_coverage`, `randomized_pit`, `pit_flatness`) so a
    bake-off winner is judged on EXACTLY the diagnostic E2.3 will re-validate it with.
    """
    out: dict[str, dict[str, float]] = {}
    for key, samples in dists.items():
        s = samples if rows is None else samples[rows]
        o = obs[key] if rows is None else obs[key][rows]
        pit = pit_flatness(randomized_pit(o, s, rng))
        out[key] = {
            "calib_80": round(interval_coverage(o, s), 4),
            "pit_max_decile_dev": pit["max_decile_dev"],
            "pit_mean_dev": pit["mean_dev_from_half"],
            "pit_is_flat": bool(pit["is_flat"]),
        }
    return out


def convolved_metrics(
    game_frame: pd.DataFrame, rng: np.random.Generator, *, n_draws: int = _DEFAULT_DRAWS
) -> dict[str, dict[str, float]]:
    """Draw + score in one call (the whole-frame convenience form)."""
    dists, obs = draw_predictive(game_frame, rng, n_draws=n_draws)
    return score_predictive(dists, obs, rng)


#: the three distributions the per-side marginal is actually responsible for. `run_diff` is
#: measured but NOT scored — E2.2/E2.3 attributed its miss to the dropped home/away dependence,
#: which no choice of per-side marginal can repair.
SCORED_DISTS: tuple[str, ...] = ("total", "home_total", "away_total")


def downstream_score(metrics: dict[str, dict[str, float]]) -> float:
    """Scalar selection metric (LOWER IS BETTER; 0 = perfectly calibrated).

        Σ_{j ∈ total, home_total, away_total} PIT_max_decile_dev_j

    🩹 CORRECTED 2026-07-20 — the original metric added a `|calib_80_j − 0.80|` term and it
    INVERTED THE RANKING. `interval_coverage` tests `y ∈ [Q10, Q90]` with INCLUSIVE bounds on an
    INTEGER-valued predictive, so the boundary atoms are counted whole and coverage is
    systematically inflated above the nominal 0.80. An ORACLE (truth drawn from exactly the
    NegBin being scored, zero misspecification) measures:

        total 0.823 · home_total 0.862 · away_total 0.850   ← a PERFECT model, not 0.80

    So `|calib_80 − 0.80|` is minimised by a model that is genuinely TOO NARROW — it rewards
    under-dispersion for cancelling a discreteness artefact. In the E2.1-r stage-1 bake-off that
    handed the win to `ngboost_normal` at a score BETTER THAN THE ORACLE'S (0.1426 < 0.1624),
    which is impossible for an honestly-calibrated model and is the tell that the metric, not
    the model, was wrong. Its 3×-worse PIT deviation confirmed the under-dispersion
    independently. `test_oracle_is_the_scoring_floor` is the permanent guard.

    The randomised PIT (`randomized_pit`) spreads mass WITHIN each CDF step, so it is
    discreteness-correct by construction, and PIT flatness is the STRICTER check anyway:
    calib_80 interrogates one interval, PIT interrogates the whole distribution's shape. Hence
    the score is PIT-only. `calib_80` is still measured and reported, and enforced as a FLOOR
    (≥ 0.80, exactly as E2.3's shipped gate uses it) via `passes_calibration_floor` — a floor is
    what it was always fit for; treating it as a target is what broke.

    `run_diff` remains excluded — E2.2/E2.3 attributed its miss to the dropped home/away
    dependence, which no choice of per-side marginal can repair.
    """
    return float(sum(metrics[j]["pit_max_decile_dev"] for j in SCORED_DISTS))


def passes_calibration_floor(metrics: dict[str, dict[str, float]]) -> bool:
    """E2.3's own gate shape: every scored distribution must cover AT LEAST the nominal 80%.

    A floor, never a target (see `downstream_score`) — an interval that is too wide is
    conservative, one that is too narrow under-prices tail risk on a surface the product quotes.
    """
    return all(metrics[j]["calib_80"] >= _CALIB_TARGET for j in SCORED_DISTS)


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
    with _Step("fold prologue: purged walk-forward split"):
        splitter = PurgedWalkForwardSplit(min_train_seasons=3)
        folds_idx = list(splitter.split(df, feature_cols=numeric_cols))
    out: list[FoldMatrices] = []

    for train_idx, eval_idx in folds_idx:
        eval_year = int(df.loc[eval_idx, "game_year"].mode().iloc[0])
        if eval_year == _EXCLUDE_EVAL_YEAR:
            continue
        tr, ev = df.loc[train_idx], df.loc[eval_idx]
        _log(f"fold {eval_year}: {len(tr):,} train / {len(ev):,} eval rows", indent=1)

        with _Step(f"fold {eval_year}: impute + OHE matrix", indent=2):
            means = _impute_means(tr, numeric_cols)
            X_tr, X_ev, feat_cols = _prepare_matrix(tr, ev, numeric_cols, cat_cols, means, None)
            _log(f"matrix {X_tr.shape[0]:,} × {X_tr.shape[1]} features", indent=3)

        inner_year = int(tr["game_year"].max())
        inner_mask = (tr["game_year"] == inner_year).to_numpy()
        if inner_mask.sum() < 200 or (~inner_mask).sum() < 500:
            inner_mask = np.zeros(len(tr), dtype=bool)
            inner_mask[int(len(tr) * 0.85):] = True   # fallback: last 15% chronologically
            _log(f"inner holdout: season split too small → last 15% chronologically", indent=3)
        else:
            _log(f"inner holdout: season {inner_year} ({inner_mask.sum():,} rows)", indent=3)

        # One LightGBM fit — the single slowest step of the prologue, and the one that used to
        # run completely silently for minutes per fold.
        with _Step(f"fold {eval_year}: in-fold importance ranking (LightGBM fit)", indent=2):
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
    cfg_id = f"{model_class}__{contract}__{mode}"

    fold_rows: list[dict] = []
    bucket_scores: list[float] = []
    bucket_metrics: list[dict] = []
    per_side_nll: list[float] = []
    games_all: list[pd.DataFrame] = []

    _log(f"CONFIG {cfg_id}  ({len(folds)} folds, {n_draws:,} draws, {n_slices} buckets/fold)")
    for i, fold in enumerate(folds, start=1):
        t_fold = time.time()
        _log(f"[{i}/{len(folds)}] fold {fold.eval_year}", indent=1)

        with _Step(f"contract '{contract}'", indent=2):
            cols = resolve_contract(contract, fold.X_tr, fold.feat_cols, fold.ranking, top_k=top_k)
            assert_market_blind(
                cols, context=f"{_STORY} {model_class}/{contract} fold {fold.eval_year}"
            )
            cols_idx = np.array([fold.feat_cols.index(c) for c in cols])
            _log(f"{len(cols)} of {len(fold.feat_cols)} features; market-blind ✅", indent=3)

        # The mean fit is a NATIVE call — no Python runs inside it, so this is the step a run
        # is most likely to be sitting in when it looks hung.
        with _Step(f"mean fit: {model_class} on {len(fold.y_tr):,}×{len(cols)}", indent=2):
            mu_ev, sigma_ev = cand.fit_predict(
                fold.X_tr[:, cols_idx], fold.y_tr, fold.X_ev[:, cols_idx]
            )
        sides_ev = fold.ev_meta["side"].to_numpy()

        # dispersion mode 'train'/'heldout' each cost a SECOND full fit — the usual surprise
        # when a config takes ~2× the time the mean fit alone would suggest.
        with _Step(f"dispersion '{mode}'" + ("" if mode == "native" else " (2nd fit)"), indent=2):
            r_ev, r_info = _fit_dispersion(cand, fold, cols_idx, mode, mu_ev, sigma_ev, sides_ev)
            _log(f"r → {r_info}", indent=3)

        nll = negbin_nll(fold.y_ev, mu_ev, float(np.median(r_ev)))
        per_side_nll.append(nll)

        games = _pivot_games(fold.ev_meta, mu_ev, r_ev, fold.y_ev)
        games_all.append(games)
        with _Step(f"convolution: {len(games):,} games × {n_draws:,} draws", indent=2):
            dists, obs = draw_predictive(games, rng, n_draws=n_draws)
        with _Step("calibration diagnostics", indent=2):
            metrics = score_predictive(dists, obs, rng)
            score = downstream_score(metrics)

        # Time-sliced buckets → the PBO/DSR performance matrix rows. These SLICE the draws
        # taken above rather than re-drawing (see draw_predictive) — the buckets are exact
        # sub-populations of the scored fold, and cost ~nothing instead of n_slices× the
        # convolution.
        with _Step(f"{n_slices} PBO buckets (slicing the fold's draws)", indent=2):
            for sl in np.array_split(np.arange(len(games)), n_slices):
                if len(sl) < 50:
                    continue
                bm = score_predictive(dists, obs, rng, rows=sl)
                bucket_scores.append(downstream_score(bm))
                # Persist the FULL per-bucket metrics, not just the scalar. The 2026-07-20
                # metric correction could not be applied by re-scoring because only the scalar
                # had been stored — it forced a full re-fit of every config. Storing the raw
                # diagnostics makes any future metric change a pure offline re-score.
                bucket_metrics.append({j: dict(bm[j]) for j in bm})

        _log(
            f"fold {fold.eval_year} done: score {score:.5f}  "
            f"calib80(total) {metrics['total']['calib_80']:.3f}  NLL {nll:.4f}  "
            f"({time.time() - t_fold:.0f}s)",
            indent=2,
        )

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
        "bucket_metrics": bucket_metrics,
        "n_buckets": len(bucket_scores),
        "passes_calibration_floor": passes_calibration_floor(pooled_metrics),
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
# Verdict logic — a PURE function so it is unit-tested (the 2026-07-20 rewrite)
#
# The original binary PROMOTE / INCUMBENT-STANDS conflated TWO independent questions and, when
# the incumbent FAILED the calibration floor, still printed "incumbent stands → proven best,
# marginals unchanged" — self-contradictory (a floor-failing model cannot be the fallback). The
# E2.1-r result forced the correction: the per-side design has two separable axes —
#   (A) the LEARNER (mean model): the 5-way bake-off is a NULL — no learner robustly beats
#       LightGBM; the top ~12 configs tie within ~4% and PBO over that tied cluster is HIGH
#       (0.35) precisely because "which tied learner wins" is noise. That is the trustworthy
#       learner null, NOT evidence the improvement is overfit.
#   (B) the DISPERSION estimator: train-fit r (incumbent) → held-out r is a single pre-registered
#       structural switch (E2.3's fix) that improves EVERY CV bucket, DSR→1. Held on one axis it
#       carries no multiple-comparison exposure.
# So the honest decision is: keep the incumbent LEARNER (A is null), promote the minimal
# DISPERSION fix (B is robust). `decide_verdict` encodes exactly that precedence.
# ---------------------------------------------------------------------------

def _learner_of(config_id: str) -> str:
    return config_id.split("__")[0]


def _contract_of(config_id: str) -> str:
    return config_id.split("__")[1]


def decide_verdict(
    results: list[dict], *, pbo_gate: float = _PBO_GATE, n_splits_cap: int = 16
) -> dict[str, Any]:
    """Turn a set of evaluated configs into a verdict. PURE (no IO) → unit-tested.

    Verdict precedence:
      1. `PROMOTE`            — a challenger beats the incumbent AND the WHOLE search is
                                deflation-clean (PBO < gate, DSR > 0): the search cleanly
                                identifies a single winner.
      2. `PROMOTE_MINIMAL_FIX`— the full search is NOT clean (e.g. a tied learner cluster), but
                                the minimal change from the incumbent — SAME learner + contract,
                                dispersion switched to the best eligible layer — improves every
                                bucket with DSR > 0. Promote that; the learner is left alone.
      3. `FIX_REQUIRED`       — the incumbent FAILS the calibration floor (is broken) and no
                                robust fix was found. Never silently keep shipping it.
      4. `INCUMBENT_STANDS`   — the incumbent passes the floor and nothing robustly beats it
                                (the genuine trustworthy-null case).
    """
    incumbent = next((r for r in results if r.get("is_incumbent")), None)
    if incumbent is None:
        raise ValueError("no incumbent config present")

    def floor_ok(r: dict) -> bool:
        if "passes_calibration_floor" in r:
            return bool(r["passes_calibration_floor"])
        return passes_calibration_floor(r["pooled_metrics"])

    n_buckets = min(len(r["bucket_scores"]) for r in results)
    perf = np.array([r["bucket_scores"][:n_buckets] for r in results], dtype=float).T
    n_cfg = perf.shape[1]
    n_splits = min(n_splits_cap, n_buckets - (n_buckets % 2))
    full_pbo = float(pbo_cscv(perf, higher_is_better=False, n_splits=max(2, n_splits)).pbo)

    eligible = [r for r in results if floor_ok(r)]
    rejected = [r for r in results if not floor_ok(r)]
    incumbent_ok = floor_ok(incumbent)
    inc_buckets = np.array(incumbent["bucket_scores"][:n_buckets], dtype=float)

    def _dsr_vs(challenger: dict, n_trials: int) -> tuple[float, bool]:
        ch = np.array(challenger["bucket_scores"][:n_buckets], dtype=float)
        improvement = inc_buckets - ch                 # >0 ⇔ challenger better (lower score)
        d = float(deflated_sharpe(improvement, n_trials=max(1, n_trials), benchmark_sr=0.0).dsr)
        return d, bool((improvement > 0).all())

    # ── overall best eligible (the full-search winner) ──
    best = min(eligible, key=lambda r: r["pooled_downstream_score"]) if eligible else None
    full_clean = False
    best_dsr = 0.0
    if best is not None and best["config_id"] != incumbent["config_id"]:
        best_gain = incumbent["pooled_downstream_score"] - best["pooled_downstream_score"]
        best_dsr, _ = _dsr_vs(best, n_cfg)
        full_clean = best_gain > 0 and full_pbo < pbo_gate and best_dsr > 0.0

    # ── minimal change: same learner + contract, only the dispersion layer differs ──
    inc_l, inc_c = _learner_of(incumbent["config_id"]), _contract_of(incumbent["config_id"])
    minimal_pool = [
        r for r in eligible
        if _learner_of(r["config_id"]) == inc_l and _contract_of(r["config_id"]) == inc_c
        and r["config_id"] != incumbent["config_id"]
    ]
    minimal_best = min(minimal_pool, key=lambda r: r["pooled_downstream_score"]) if minimal_pool else None
    minimal_clean = False
    minimal_dsr = 0.0
    if minimal_best is not None:
        # n_trials = the dispersion alternatives tried for this (learner, contract) cell — the
        # honest deflation for a single-axis pre-registered switch, not the whole search.
        n_disp = sum(
            1 for r in results
            if _learner_of(r["config_id"]) == inc_l and _contract_of(r["config_id"]) == inc_c
        )
        minimal_dsr, all_pos = _dsr_vs(minimal_best, n_disp)
        minimal_gain = incumbent["pooled_downstream_score"] - minimal_best["pooled_downstream_score"]
        minimal_clean = minimal_gain > 0 and all_pos and minimal_dsr > 0.0

    if full_clean:
        verdict, winner = "PROMOTE", best
    elif minimal_clean:
        verdict, winner = "PROMOTE_MINIMAL_FIX", minimal_best
    elif not incumbent_ok:
        verdict, winner = "FIX_REQUIRED", None
    else:
        verdict, winner = "INCUMBENT_STANDS", None

    return {
        "verdict": verdict,
        "winner": winner,
        "incumbent": incumbent,
        "incumbent_passes_floor": incumbent_ok,
        "best": best,
        "minimal_best": minimal_best,
        "full_pbo": round(full_pbo, 4),
        "best_dsr": round(best_dsr, 4),
        "minimal_dsr": round(minimal_dsr, 4),
        "n_configs": n_cfg,
        "n_buckets": n_buckets,
        "eligible": eligible,
        "rejected": rejected,
        "requires_downstream_rerun": verdict in ("PROMOTE", "PROMOTE_MINIMAL_FIX"),
    }


# ---------------------------------------------------------------------------
# Stage 3 — deflate the whole search, pick the winner, write the decision
# ---------------------------------------------------------------------------

def stage_decide(args) -> None:
    results = load_config_results()
    if not results:
        raise SystemExit(f"[{_STORY}] no config results in {_TRIALS_DIR} — run --stage bakeoff first.")

    if not any(r.get("is_incumbent") for r in results):
        raise SystemExit(
            f"[{_STORY}] the incumbent config ({_INCUMBENT}/{_INCUMBENT_CONTRACT}/"
            f"{_INCUMBENT_DISPERSION}) is missing — it is the foil; re-run --stage bakeoff."
        )

    d = decide_verdict(results, pbo_gate=_PBO_GATE)
    incumbent, best, winner = d["incumbent"], d["best"], d["winner"]
    verdict = d["verdict"]

    if d["rejected"]:
        _log(f"{len(d['rejected'])} config(s) REJECTED by the calib_80 ≥ {_CALIB_TARGET} floor:")
        for r in sorted(d["rejected"], key=lambda x: x["pooled_downstream_score"]):
            worst = min(r["pooled_metrics"][j]["calib_80"] for j in SCORED_DISTS)
            inc = "  (THE INCUMBENT — it is BROKEN, not a fallback)" if r.get("is_incumbent") else ""
            _log(f"  {r['config_id']:<46} worst calib_80 {worst:.3f}{inc}", indent=1)
    if not d["eligible"]:
        raise SystemExit(
            f"[{_STORY}] every config failed the calib_80 ≥ {_CALIB_TARGET} floor — nothing to pick."
        )

    gain = (
        incumbent["pooled_downstream_score"] - winner["pooled_downstream_score"]
        if winner else 0.0
    )

    print("=" * 78)
    print(f"{_STORY} DECISION — {d['n_configs']} configs, {d['n_buckets']} buckets")
    print("=" * 78)
    for r in sorted(d["eligible"], key=lambda r: r["pooled_downstream_score"])[:12]:
        marks = "".join([
            " ← INCUMBENT" if r.get("is_incumbent") else "",
            "  ★ WINNER" if winner and r["config_id"] == winner["config_id"] else "",
        ])
        print(
            f"  {r['pooled_downstream_score']:.5f}  {r['config_id']:<44} "
            f"calib80 {r['pooled_metrics']['total']['calib_80']:.3f}"
            f"  PITdev {r['pooled_metrics']['total']['pit_max_decile_dev']:.4f}{marks}"
        )
    inc_floor = "PASS" if d["incumbent_passes_floor"] else "FAIL — DISQUALIFIED"
    print(f"\n  incumbent   : {incumbent['config_id']}  score {incumbent['pooled_downstream_score']:.5f}"
          f"  [calib floor {inc_floor}]")
    if winner:
        print(f"  winner      : {winner['config_id']}  score {winner['pooled_downstream_score']:.5f}"
              f"  (gain {gain:+.5f})")
    print(f"  full-search PBO : {d['full_pbo']:.3f}  "
          f"({'PASS' if d['full_pbo'] < _PBO_GATE else 'FAIL'} < {_PBO_GATE}) "
          f"— high ⇒ the LEARNER choice is not identifiable (tied cluster), a learner NULL")
    print(f"  minimal-fix DSR : {d['minimal_dsr']:.3f}  "
          f"(same learner, dispersion switched; {'PASS' if d['minimal_dsr'] > 0 else 'FAIL'} > 0)")
    print(f"\n  VERDICT   : {verdict}")
    _print_verdict_action(verdict, incumbent, winner)
    print("\n  Honest framing: this is a CALIBRATION result, not an edge claim (best_alpha = 0).")

    def _slim(r):
        return None if r is None else {
            k: r.get(k) for k in
            ("config_id", "params", "pooled_downstream_score", "pooled_metrics", "mean_per_side_negbin_nll")
        }

    doc = {
        "story": _STORY,
        "decided_at": date.today().isoformat(),
        "n_configs": d["n_configs"],
        "n_buckets": d["n_buckets"],
        "selection_metric": (
            "sum over {total, home_total, away_total} of PIT max decile dev (lower is better); "
            "calib_80 ≥ 0.80 enforced as a FLOOR not a target (discreteness inflates coverage — "
            "an oracle covers ~0.82-0.86, so |calib_80-0.80| would reward under-dispersion); "
            "run_diff measured but excluded (E2.2/E2.3: dropped dependence)"
        ),
        "verdict": verdict,
        "incumbent_passes_calibration_floor": d["incumbent_passes_floor"],
        "incumbent": _slim(incumbent),
        "best": _slim(best),
        "winner": _slim(winner),
        "gain_vs_incumbent": round(gain, 5),
        "full_search_pbo": d["full_pbo"],
        "best_dsr": d["best_dsr"],
        "minimal_fix_dsr": d["minimal_dsr"],
        "gates": {
            "full_search_deflated": bool(d["full_pbo"] < _PBO_GATE and d["best_dsr"] > 0.0),
            "minimal_fix_deflated": bool(d["minimal_dsr"] > 0.0),
            "market_blind": True,
        },
        "requires_e2_5_e2_6_rerun": d["requires_downstream_rerun"],
        "leaderboard": [
            {
                "config_id": r["config_id"],
                "score": r["pooled_downstream_score"],
                "calib_80_total": r["pooled_metrics"]["total"]["calib_80"],
                "pit_maxdev_total": r["pooled_metrics"]["total"]["pit_max_decile_dev"],
                "per_side_nll": r["mean_per_side_negbin_nll"],
                "passes_floor": (
                    r["passes_calibration_floor"] if "passes_calibration_floor" in r
                    else passes_calibration_floor(r["pooled_metrics"])
                ),
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


def _print_verdict_action(verdict: str, incumbent: dict, winner: dict | None) -> None:
    if verdict == "PROMOTE":
        print(
            f"  → the search cleanly identifies a winner: re-emit {winner['config_id']} as\n"
            "    totals_perside_v2, RE-RUN fit_totals_distribution.py, register in\n"
            "    sub_model_registry.yaml. E2.5/E2.6 re-run."
        )
    elif verdict == "PROMOTE_MINIMAL_FIX":
        print(
            "  → TWO-AXIS result. LEARNER: the 5-way bake-off is a NULL — no learner robustly\n"
            f"    beats the incumbent's ({_learner_of(incumbent['config_id'])}); the tied cluster's\n"
            "    high PBO is that null, not overfitting. DISPERSION: the minimal single-axis switch\n"
            f"    → {winner['config_id']} improves every CV bucket (DSR>0).\n"
            "  → PROMOTE the minimal fix: KEEP the learner, switch the dispersion layer only.\n"
            "    Re-emit totals_perside_v2 (same mean model, new dispersion), re-run\n"
            "    fit_totals_distribution.py, register. ⚠️ Verify whether E2.5/E2.6 read the STORED\n"
            "    dispersion or E2.3's re-calibrated r — if the latter, downstream may be unchanged."
        )
    elif verdict == "FIX_REQUIRED":
        print(
            "  → the incumbent FAILS the calibration floor (it under-covers — it is BROKEN), and\n"
            "    no deflation-clean fix was found among the evaluated configs. Do NOT keep shipping\n"
            "    it. Widen the search (more dispersion candidates / Optuna) before promoting."
        )
    else:  # INCUMBENT_STANDS
        print(
            "  → the incumbent passes the calibration floor and nothing robustly beats it. Its\n"
            "    single-architecture choice is a TRUSTWORTHY result (proven best over a deflated\n"
            "    ≥3-class search), not an assumption. E2.5/E2.6 do NOT re-run — marginals unchanged."
        )


def _render_md(doc: dict) -> str:
    lines = [
        f"# {_STORY} — Per-side count-model bake-off (revisit of the single-architecture E2.1)",
        "",
        f"_Decided {doc['decided_at']} · {doc['n_configs']} configs · {doc['n_buckets']} CV buckets_",
        "",
        "## Verdict",
        "",
        f"**{doc['verdict']}**"
        + (f" — winner `{doc['winner']['config_id']}` vs incumbent "
           f"`{doc['incumbent']['config_id']}`, downstream gain `{doc['gain_vs_incumbent']:+.5f}`."
           if doc.get("winner") else
           f" — incumbent `{doc['incumbent']['config_id']}`."),
        "",
        f"- incumbent passes calib_80 floor: **{'YES' if doc['incumbent_passes_calibration_floor'] else 'NO — DISQUALIFIED'}**",
        f"- full-search PBO `{doc['full_search_pbo']:.3f}` "
        f"({'PASS' if doc['gates']['full_search_deflated'] else 'FAIL'} < 0.2) — high ⇒ the "
        "learner choice is a tied cluster (a learner NULL), not overfitting",
        f"- minimal-fix DSR `{doc['minimal_fix_dsr']:.3f}` "
        f"({'PASS' if doc['gates']['minimal_fix_deflated'] else 'FAIL'} > 0) — same learner, "
        "dispersion switched only",
        f"- E2.5 / E2.6 re-run required: **{'YES' if doc['requires_e2_5_e2_6_rerun'] else 'NO'}**",
        "",
        "## Selection metric",
        "",
        doc["selection_metric"],
        "",
        "## Leaderboard",
        "",
        "| config | score | calib_80 (total) | PIT maxdev (total) | per-side NegBin NLL | floor |",
        "|---|---|---|---|---|---|",
    ]
    for r in doc["leaderboard"][:25]:
        lines.append(
            f"| `{r['config_id']}` | {r['score']:.5f} | {r['calib_80_total']:.3f} | "
            f"{r['pit_maxdev_total']:.4f} | {r['per_side_nll']:.4f} | "
            f"{'✅' if r.get('passes_floor', True) else '❌'} |"
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
    ap.add_argument("--n-jobs", type=int, default=None,
                    help="Learner thread cap (LightGBM/XGBoost/CatBoost). Pair with the "
                         "E2_1R_THREADS env var to also cap BLAS — uncapped, the two "
                         "oversubscribe the CPU and a fine fit crawls.")
    ap.add_argument("--seed", type=int, default=_SEED)
    args = ap.parse_args()

    set_n_jobs(args.n_jobs)
    _log(
        f"{_STORY} start · stage={args.stage or 'assemble'} "
        f"· n_jobs={args.n_jobs or 'default'} · BLAS cap={_THREAD_CAP or 'default'} · pid={os.getpid()}"
    )
    # A native OpenMP/BLAS fit does not run Python, so Ctrl-C is QUEUED until the call returns —
    # on a long fit that reads as "it won't die". `kill -9 <pid>` is the reliable stop; the pid
    # is logged above precisely so it is to hand.
    _log("Ctrl-C lands only between native fits — to stop immediately: kill -9 " + str(os.getpid()))

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
