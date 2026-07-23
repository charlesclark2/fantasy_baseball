"""bakeoff_f5_perside.py — Edge Program Story **E2.4** (First-5-innings per-side BAKE-OFF).

WHAT E2.4 IS
------------
E2.1/E2.2/E2.3 built the FULL-GAME per-side run distribution. E2.4 builds the same honest
distribution scoped to the **first five innings (F5)** — the sub-game the book sets lazily and
the "softer market" thesis of the E2 derivative chain rests on. The F5 distribution is
structurally different from the full game (CLAUDE.md / story E2.4):

  * LOWER mean (~2.4 per side vs ~4.5) → MORE discrete;
  * MORE zero-inflation (~22% scoreless-through-5 half-games in 2024) → the tails matter more;
  * STARTER-dominated — the bullpen barely pitches innings 1–5.

So E2.4 does NOT inherit the E2.1 NegBin form. It runs a §0.5 bake-off over ≥3 pre-registered
per-side distributional FORMS, each convolved with the SAME independent (ρ=0) machinery E2.3
uses, and picks on the E2.1-r downstream selection metric.

PRE-REGISTERED SEARCH  (learner × contract × form)
--------------------------------------------------
LEARNERS (the mean model — reused verbatim from the E2.1-r bake-off, `bakeoff_perside`):
  lgbm_poisson · xgb_poisson · catboost_poisson · ngboost_normal · glm_poisson

DISTRIBUTIONAL FORMS (the axis that matters for F5's zero-inflation — `betting_ml/utils/
f5_distribution.py`):
  * `poisson`    — var = mean; the low-mean baseline (F5 may not need NegBin's extra dispersion)
  * `heldout`    — NegBin, r MLE on INNER-HOLDOUT residuals (E2.3's leakage-safe fix); the
                   E2.1-r minimal-fix winner carried to F5 = THE REFERENCE/foil
  * `native`     — NGBoost (μ, σ) per game → per-game NegBin r (the heteroscedastic foil; ngboost
                   only)
  * `betabinom`  — Beta-Binomial(n, s): a BOUNDED overdispersed form whose mass can pile at 0 —
                   the one candidate that can represent F5's zero-heavy, bounded shape DIFFERENTLY
                   from the unbounded Poisson/NegBin (the story's named F5 candidate)

FEATURE CONTRACTS (pre-registered, selected IN-FOLD — `full`/`clustered`/`top_k` reused, plus):
  * `no_bullpen` — DROP the opposing-bullpen / pen-state channel. Hypothesis-driven (§0.5): the
                   bullpen barely pitches in F5, so its features are noise for this target. A
                   BOUNDED pre-registered drop, not an open subset search.

SELECTION METRIC — identical to E2.1-r (and its landmine fix): the per-side model FEEDS the
convolution, so it is judged on the CONVOLVED distribution's calibration —
    downstream_score = Σ_{j ∈ total, home_total, away_total} PIT_max_decile_dev_j   (lower better)
with `calib_80 ≥ 0.80` enforced as a FLOOR (never a target — inclusive-integer interval coverage
is inflated, WORSE at F5's low mean; an oracle covers ~0.82–0.86). `run_diff` excluded (E2.2/E2.3:
dropped home/away dependence). Guard: `test_f5_distribution.test_oracle_is_the_scoring_floor`.

DEFLATION: every (learner × contract × form × Optuna trial) config counts toward PBO < 0.2 /
DSR > 0 via the SAME `decide_verdict` the E2.1-r harness uses (reused verbatim).

DATA (§0.5 cost hygiene) — ONE PULL → PARQUET, then everything off the cache:
  `--assemble` does a SINGLE S3-lakehouse / DuckDB read (Snowflake-FREE — a SF pull is a RED FLAG
  post-E11.1 and would perturb the E11.20 metering window). It pulls the E2.1 pregame per-side
  feature matrix AND the F5 target (innings-1–5 cumulative scores from `stg_batter_pitches`), joins
  them, and writes one parquet. Every learner × contract × form × Optuna trial × CV fold reads it.

MARKET-BLIND: `assert_market_blind` runs on every contract's column list before any fit.
HONEST FRAME: a market-BLIND F5 distribution is PRODUCT value, not an edge claim — whether F5
beats its own close is E2.6/E13.9's question under deflation. `best_alpha = 0`.

USAGE (operator — stages 1/2/4 are the >1-min jobs)
---------------------------------------------------
    # 0) one pull → parquet cache (laptop or box; needs AWS_DEFAULT_REGION=us-east-2)
    uv run python betting_ml/scripts/totals_generative/bakeoff_f5_perside.py --assemble

    # 1) the bake-off: 5 learners × 4 contracts × their default form, purged CV
    uv run python betting_ml/scripts/totals_generative/bakeoff_f5_perside.py --stage bakeoff

    # 2) Optuna, ONE learner per invocation (retrain-per-target convention)
    uv run python betting_ml/scripts/totals_generative/bakeoff_f5_perside.py \
        --stage optuna --model-class lgbm_poisson --n-trials 40

    # 3) collect every stage-1/2 config → PBO/DSR + winner-vs-reference verdict
    uv run python betting_ml/scripts/totals_generative/bakeoff_f5_perside.py --stage decide

    # 4) fit the winning form on all complete seasons → leakage-safe served F5 distribution + gate
    uv run python betting_ml/scripts/totals_generative/bakeoff_f5_perside.py --stage finalize
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

# ⚠️ BLAS/OpenMP thread cap must precede numpy import (mirrors bakeoff_perside).
_THREAD_CAP = os.environ.get("E2_4_THREADS", os.environ.get("E2_1R_THREADS", "")).strip()
if _THREAD_CAP:
    for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[_v] = _THREAD_CAP

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

# ── Reuse the E2.1-r harness verbatim where the logic is form-agnostic ──
from betting_ml.scripts.totals_generative.bakeoff_perside import (  # noqa: E402
    FoldMatrices,
    _Step,
    _log,
    build_candidate,
    build_folds,
    clustered_contract,
    decide_verdict,
    downstream_score,
    infold_importance,
    passes_calibration_floor,
    resolve_contract,
    save_config_result as _save_config_result_base,
    score_predictive,
    set_n_jobs,
    MODEL_CLASSES,
    SCORED_DISTS,
    _pivot_games,
)
from betting_ml.scripts.totals_generative.train_perside_negbin import (  # noqa: E402
    _EXCLUDE_EVAL_YEAR,
    _TARGET,
    build_perside_frame,
    load_wide,
)
from betting_ml.utils.market_blind import assert_market_blind  # noqa: E402
from betting_ml.utils.f5_distribution import (  # noqa: E402
    BETABINOM_N_CAP,
    betabinom_nll,
    derive_distributions,
    draw_f5_independent,
    fit_betabinom_s,
    fit_negbin_r,
    negbin_nll,
    poisson_nll,
    sigma_to_negbin_r,
    F5DistributionParams,
)

# ---------------------------------------------------------------------------
# Constants / paths
# ---------------------------------------------------------------------------

_STORY = "E2.4"
# The reference/foil = the E2.1-r minimal-fix winner (LightGBM + held-out NegBin, full contract)
# carried to F5. Story E2.4: "note the E2.1-r result as a PRIOR (not a foregone pick)" — if
# nothing robustly beats it the F5 default IS the carried NegBin (a trustworthy null); else the
# bake-off promotes the winning F5 form.
_REFERENCE = ("lgbm_poisson", "full", "heldout")
_INCUMBENT, _INCUMBENT_CONTRACT, _INCUMBENT_FORM = _REFERENCE

_CALIB_TARGET = 0.80
_DEFAULT_DRAWS = 4_000
_DEFAULT_TOP_K = 120
_PBO_GATE = 0.2
_SEED = 42

_CACHE_DIR = _PROJECT_ROOT / "betting_ml" / "data" / "cache"
_CACHE_PATH = _CACHE_DIR / "e2_4_f5_perside_matrix.parquet"
_META_PATH = _CACHE_DIR / "e2_4_f5_perside_matrix.meta.json"

_RESULTS_DIR = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"
)
_TRIALS_DIR = _RESULTS_DIR / "e2_4_f5_configs"
_DECISION_JSON = _RESULTS_DIR / "e2_4_f5_bakeoff.json"
_DECISION_MD = _RESULTS_DIR / "e2_4_f5_bakeoff.md"
_CALIB_JSON = _RESULTS_DIR / "e2_4_f5_calibration.json"
_CALIB_MD = _RESULTS_DIR / "e2_4_f5_calibration.md"
_ARTIFACT_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "f5_generative_v1"

# The four pre-registered feature contracts (E2.1-r's three + the F5-specific no_bullpen drop).
CONTRACTS: tuple[str, ...] = ("full", "no_bullpen", "clustered", "top_k")
# The four pre-registered distributional forms.
FORM_MODES: tuple[str, ...] = ("poisson", "heldout", "native", "betabinom")

# Opposing-bullpen / pen-state feature prefixes (unpivoted as `opp_*` in build_perside_frame) —
# the `no_bullpen` contract drops exactly these (starters dominate F5).
_BULLPEN_PREFIXES: tuple[str, ...] = (
    "opp_bp_", "opp_bullpen_", "opp_reliever_", "opp_closer_",
    "opp_pitchers_used", "opp_high_leverage", "opp_high_lev",
)


def _is_bullpen_feature(col: str) -> bool:
    return any(col.startswith(p) for p in _BULLPEN_PREFIXES)


def default_form(model_class: str) -> str:
    """ngboost carries its own (μ, σ) → native per-game r; every other learner uses the E2.3
    held-out NegBin as its default form (the E2.1-r carried default)."""
    return "native" if build_candidate(model_class).native else "heldout"


# ---------------------------------------------------------------------------
# Stage 0 — the ONE data pull → parquet cache (pregame features + F5 target)
# ---------------------------------------------------------------------------

def _f5_target_sql(min_year: int) -> str:
    """Per-game F5 (innings 1–5) cumulative runs, per side, from stg_batter_pitches.

    Scores are game-cumulative and monotone, so MAX over inning ≤ 5 = each team's runs through
    the 5th (away bats the top, home the bottom of the 5th). The HAVING requires BOTH halves of
    the 5th to have been played (a valid F5 line = 5 complete innings) — dropping rain/walkoff-
    shortened games that never had an F5 close. Regular season only is enforced downstream by the
    inner JOIN to the pregame frame (which is game_type='R', has_full_data)."""
    return f"""
    SELECT
        game_pk,
        MAX(post_pitch_away_score) AS away_f5_runs,
        MAX(post_pitch_home_score) AS home_f5_runs
    FROM baseball_data.betting.stg_batter_pitches
    WHERE game_year >= {int(min_year)}
      AND inning <= 5
    GROUP BY game_pk
    HAVING COUNT(DISTINCT CASE WHEN inning = 5 THEN lower(inning_half) END) = 2
    """


def load_f5_target(min_year: int) -> pd.DataFrame:
    """F5 per-(game_pk, side) runs from the S3 lakehouse via DuckDB (Snowflake-FREE).

    Returns long form: columns game_pk, side ∈ {home, away}, f5_runs. This is the ONLY read of
    the pitch-grain mart — the aggregation collapses ~millions of pitch rows to one row per game
    in the single `--assemble` pull.
    """
    from scripts.utils.lakehouse_read import (
        duck_connect,
        referenced_tables,
        register_views,
        strip_fqn,
    )

    sql = _f5_target_sql(min_year)
    conn = duck_connect()
    register_views(conn, referenced_tables(sql))
    wide = conn.execute(strip_fqn(sql)).fetch_df()
    wide.columns = [c.lower() for c in wide.columns]
    home = wide[["game_pk", "home_f5_runs"]].rename(columns={"home_f5_runs": "f5_runs"})
    home["side"] = "home"
    away = wide[["game_pk", "away_f5_runs"]].rename(columns={"away_f5_runs": "f5_runs"})
    away["side"] = "away"
    long = pd.concat([home, away], ignore_index=True)
    long["f5_runs"] = pd.to_numeric(long["f5_runs"], errors="coerce")
    return long.dropna(subset=["f5_runs"])


def assemble_cache(min_year: int) -> Path:
    """Single lakehouse read → per-side pregame matrix with the F5 target → parquet.

    The pregame feature matrix is IDENTICAL to E2.1 (pregame features are known before first
    pitch — the F5 sub-game uses the same inputs); only the TARGET changes from full-game runs to
    F5 runs. So we reuse `build_perside_frame` and simply OVERWRITE its `runs_scored` target
    column with the F5 runs (dropping games without a valid F5 close), which makes the whole
    downstream harness (folds, matrix prep) work transparently on the F5 target.
    """
    print(f"=== {_STORY} stage 0 — assembling the F5 per-side matrix (lakehouse/DuckDB) ===")
    t0 = time.time()
    wide = load_wide(min_year, source="lakehouse")
    print(f"  wide pregame mart: {len(wide):,} games "
          f"({int(wide['game_year'].min())}–{int(wide['game_year'].max())})  ({time.time() - t0:.0f}s)")

    df, numeric_cols, cat_cols = build_perside_frame(wide)
    assert_market_blind(numeric_cols + cat_cols, context=f"{_STORY} F5 per-side matrix")
    print(f"  per-side rows (full-game target): {len(df):,}  |  {len(numeric_cols)} numeric + "
          f"{len(cat_cols)} categorical  |  market-blind ✅")

    t1 = time.time()
    f5 = load_f5_target(min_year)
    print(f"  F5 target: {f5['game_pk'].nunique():,} games with a valid F5 close  ({time.time() - t1:.0f}s)")

    # Swap the target: full-game runs → F5 runs (inner join drops games without a valid F5 close).
    n_before = len(df)
    df = df.merge(f5, on=["game_pk", "side"], how="inner")
    df[_TARGET] = df["f5_runs"].astype("float64")
    df = (
        df.drop(columns=["f5_runs"])
        .sort_values(["game_date", "game_pk", "side"])
        .reset_index(drop=True)
    )
    print(f"  F5 per-side rows after join: {len(df):,} (dropped {n_before - len(df):,} without an "
          f"F5 close)  |  mean F5 per-side runs {df[_TARGET].mean():.3f}  "
          f"frac-zero {float((df[_TARGET] == 0).mean()):.3f}")

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_CACHE_PATH, index=False)
    _META_PATH.write_text(json.dumps({
        "story": _STORY,
        "assembled_at": date.today().isoformat(),
        "min_year": min_year,
        "target": "f5_runs (innings 1-5 cumulative runs, per side)",
        "n_rows": int(len(df)),
        "n_games": int(df["game_pk"].nunique()),
        "mean_f5_perside": round(float(df[_TARGET].mean()), 4),
        "frac_zero_f5": round(float((df[_TARGET] == 0).mean()), 4),
        "numeric_cols": numeric_cols,
        "cat_cols": cat_cols,
        "seasons": sorted(int(y) for y in df["game_year"].unique()),
    }, indent=2))
    print(f"  cache → {_CACHE_PATH.relative_to(_PROJECT_ROOT)}  ({_CACHE_PATH.stat().st_size / 1e6:.1f} MB)")
    return _CACHE_PATH


def load_cache() -> tuple[pd.DataFrame, list[str], list[str], dict]:
    if not _CACHE_PATH.exists():
        raise SystemExit(
            f"[{_STORY}] no cached matrix at {_CACHE_PATH}. Run `--assemble` first "
            f"(one lakehouse pull; every later stage reads the cache)."
        )
    meta = json.loads(_META_PATH.read_text())
    df = pd.read_parquet(_CACHE_PATH)
    return df, list(meta["numeric_cols"]), list(meta["cat_cols"]), meta


# ---------------------------------------------------------------------------
# Feature contracts — reuse the E2.1-r resolver, add the F5-specific no_bullpen drop
# ---------------------------------------------------------------------------

def resolve_contract_f5(
    contract: str, X_tr: np.ndarray, feat_cols: list[str], ranking: list[str], *, top_k: int
) -> list[str]:
    if contract == "no_bullpen":
        return [c for c in feat_cols if not _is_bullpen_feature(c)]
    return resolve_contract(contract, X_tr, feat_cols, ranking, top_k=top_k)


# ---------------------------------------------------------------------------
# Form-aware dispersion + convolution (the F5-specific core)
# ---------------------------------------------------------------------------

def form_of(form_mode: str) -> str:
    """Map a bake-off form-mode to the f5_distribution sampler form."""
    return {"poisson": "poisson", "heldout": "negbin", "native": "negbin",
            "betabinom": "betabinom"}[form_mode]


def _fit_side_dispersion(form_mode: str, y: np.ndarray, mu: np.ndarray) -> float:
    if form_mode in ("heldout",):
        return fit_negbin_r(y, mu)
    if form_mode == "betabinom":
        return fit_betabinom_s(y, mu)
    raise KeyError(form_mode)


def _fit_dispersion(
    cand, fold: FoldMatrices, cols_idx: np.ndarray, form_mode: str,
    mu_ev: np.ndarray, sigma_ev: np.ndarray | None, sides_ev: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Per-row eval dispersion under the requested F5 form. Returns (disp_ev, info).

    `disp_ev` is the per-row parameter the sampler consumes (r for negbin, s for betabinom).
    Poisson has none → a finite dummy (the sampler ignores it, and a NaN would nuke the pivot's
    dropna). native → per-game r from ngboost's (μ, σ). heldout/betabinom → a per-SIDE parameter
    MLE'd on the INNER-HOLDOUT residuals (leakage-safe: the inner holdout is inside train).
    """
    if form_mode == "poisson":
        return np.ones_like(mu_ev), {"r_source": "poisson", "disp": None}

    if form_mode == "native":
        if sigma_ev is None:
            raise ValueError(f"{cand.name} is not native-distributional — no sigma for form 'native'")
        r_ev = sigma_to_negbin_r(mu_ev, sigma_ev)
        return r_ev, {"r_source": "native_joint", "disp_median": round(float(np.median(r_ev)), 4)}

    # heldout / betabinom: a per-side scalar fit on inner-holdout residuals (E2.3's fix).
    mu_ho, _ = cand.fit_predict(
        fold.X_inner_tr[:, cols_idx], fold.y_inner_tr, fold.X_inner_ho[:, cols_idx]
    )
    sides_ho = fold.inner_sides
    disp_by_side = {
        s: _fit_side_dispersion(form_mode, fold.y_inner_ho[sides_ho == s], mu_ho[sides_ho == s])
        for s in ("home", "away")
    }
    disp_ev = np.where(sides_ev == "home", disp_by_side["home"], disp_by_side["away"])
    key = "r" if form_mode == "heldout" else "s"
    return disp_ev, {
        "r_source": form_mode,
        f"{key}_home": round(float(disp_by_side["home"]), 4),
        f"{key}_away": round(float(disp_by_side["away"]), 4),
    }


def draw_predictive(
    game_frame: pd.DataFrame, form_mode: str, rng: np.random.Generator,
    *, n_draws: int = _DEFAULT_DRAWS, n_cap: int = BETABINOM_N_CAP,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Convolve per-side (μ, disp) → (sampled distributions, realised observations) for a form.

    `game_frame` has mu_home/mu_away, r_home/r_away (the dispersion slot, whatever the form uses),
    y_home/y_away (realised F5 runs). Reuses `_pivot_games`' column names — the `r_*` columns hold
    whichever dispersion parameter the form consumes.
    """
    y_home, y_away = draw_f5_independent(
        game_frame["mu_home"].to_numpy(float),
        game_frame["mu_away"].to_numpy(float),
        form_of(form_mode),
        game_frame["r_home"].to_numpy(float),
        game_frame["r_away"].to_numpy(float),
        rng, n_draws=n_draws, n_cap=n_cap,
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


def _perside_nll(form_mode: str, y: np.ndarray, mu: np.ndarray, disp: np.ndarray) -> float:
    """Secondary diagnostic: the form's own per-side NLL on the eval fold."""
    if form_mode == "poisson":
        return poisson_nll(y, mu)
    if form_mode == "betabinom":
        return betabinom_nll(y, mu, float(np.median(disp)))
    return negbin_nll(y, mu, float(np.median(disp)))


# ---------------------------------------------------------------------------
# Score ONE config across every fold (mirrors bakeoff_perside.evaluate_config, form-aware)
# ---------------------------------------------------------------------------

def evaluate_config(
    folds: list[FoldMatrices], model_class: str, contract: str, *,
    form_mode: str | None = None, params: dict | None = None, top_k: int = _DEFAULT_TOP_K,
    n_draws: int = _DEFAULT_DRAWS, n_slices: int = 4, seed: int = _SEED,
    n_cap: int = BETABINOM_N_CAP,
) -> dict[str, Any]:
    cand = build_candidate(model_class, params)
    fm = form_mode or default_form(model_class)
    rng = np.random.default_rng(seed)
    cfg_id = f"{model_class}__{contract}__{fm}"

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
            cols = resolve_contract_f5(contract, fold.X_tr, fold.feat_cols, fold.ranking, top_k=top_k)
            assert_market_blind(cols, context=f"{_STORY} {model_class}/{contract} fold {fold.eval_year}")
            cols_idx = np.array([fold.feat_cols.index(c) for c in cols])
            _log(f"{len(cols)} of {len(fold.feat_cols)} features; market-blind ✅", indent=3)

        with _Step(f"mean fit: {model_class} on {len(fold.y_tr):,}×{len(cols)}", indent=2):
            mu_ev, sigma_ev = cand.fit_predict(fold.X_tr[:, cols_idx], fold.y_tr, fold.X_ev[:, cols_idx])
        sides_ev = fold.ev_meta["side"].to_numpy()

        with _Step(f"dispersion '{fm}'" + ("" if fm in ("poisson", "native") else " (2nd fit)"), indent=2):
            disp_ev, disp_info = _fit_dispersion(cand, fold, cols_idx, fm, mu_ev, sigma_ev, sides_ev)
            _log(f"disp → {disp_info}", indent=3)

        nll = _perside_nll(fm, fold.y_ev, mu_ev, disp_ev)
        per_side_nll.append(nll)

        games = _pivot_games(fold.ev_meta, mu_ev, disp_ev, fold.y_ev)
        games_all.append(games)
        with _Step(f"convolution: {len(games):,} games × {n_draws:,} draws", indent=2):
            dists, obs = draw_predictive(games, fm, rng, n_draws=n_draws, n_cap=n_cap)
        with _Step("calibration diagnostics", indent=2):
            metrics = score_predictive(dists, obs, rng)
            score = downstream_score(metrics)

        with _Step(f"{n_slices} PBO buckets (slicing the fold's draws)", indent=2):
            for sl in np.array_split(np.arange(len(games)), n_slices):
                if len(sl) < 50:
                    continue
                bm = score_predictive(dists, obs, rng, rows=sl)
                bucket_scores.append(downstream_score(bm))
                bucket_metrics.append({j: dict(bm[j]) for j in bm})

        _log(f"fold {fold.eval_year} done: score {score:.5f}  "
             f"calib80(total) {metrics['total']['calib_80']:.3f}  NLL {nll:.4f}  "
             f"({time.time() - t_fold:.0f}s)", indent=2)
        fold_rows.append({
            "eval_year": fold.eval_year, "n_games": int(len(games)),
            "downstream_score": round(score, 5), "per_side_nll": round(nll, 4),
            "total_calib_80": metrics["total"]["calib_80"],
            "total_pit_maxdev": metrics["total"]["pit_max_decile_dev"],
            "run_diff_calib_80": metrics["run_diff"]["calib_80"],
            "run_diff_pit_maxdev": metrics["run_diff"]["pit_max_decile_dev"],
            "n_features": len(cols), **disp_info,
        })

    pooled = pd.concat(games_all, ignore_index=True)
    pooled_dists, pooled_obs = draw_predictive(pooled, fm, rng, n_draws=n_draws, n_cap=n_cap)
    pooled_metrics = score_predictive(pooled_dists, pooled_obs, rng)

    return {
        "story": _STORY,
        "config_id": cfg_id,
        "model_class": model_class,
        "contract": contract,
        "form": fm,
        "params": cand.params,
        "top_k": top_k if contract == "top_k" else None,
        "n_cap": n_cap if fm == "betabinom" else None,
        # The reference/foil is the E2.1-carried arch at DEFAULT params — NOT a tuned trial of
        # the same triple. Optuna passes explicit params, so `not params` excludes tuned
        # challengers on the reference axis (else every `--form heldout` lgbm trial would flag
        # itself the incumbent and pollute decide's reference selection).
        "is_incumbent": (model_class == _INCUMBENT and contract == _INCUMBENT_CONTRACT
                         and fm == _INCUMBENT_FORM and not params),
        "folds": fold_rows,
        "mean_downstream_score": round(float(np.mean([f["downstream_score"] for f in fold_rows])), 5),
        "pooled_downstream_score": round(downstream_score(pooled_metrics), 5),
        "pooled_metrics": pooled_metrics,
        "mean_per_side_nll": round(float(np.mean(per_side_nll)), 4),
        "bucket_scores": [round(float(b), 5) for b in bucket_scores],
        "bucket_metrics": bucket_metrics,
        "n_buckets": len(bucket_scores),
        "passes_calibration_floor": passes_calibration_floor(pooled_metrics),
    }


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
# Stage 1 — the bake-off (5 learners × 4 contracts × their default form)
# ---------------------------------------------------------------------------

def stage_bakeoff(args) -> None:
    df, numeric_cols, cat_cols, meta = load_cache()
    print(f"=== {_STORY} stage 1 — F5 BAKE-OFF ({len(df):,} per-side rows from cache) ===")
    folds = build_folds(df, numeric_cols, cat_cols, max_folds=args.max_folds)
    print(f"  purged folds: {[f.eval_year for f in folds]}")

    classes = [args.model_class] if args.model_class else list(MODEL_CLASSES)
    contracts = [args.contract] if args.contract else list(CONTRACTS)

    # The reference/foil first (E2.1-r carried arch), then each learner × contract at its default
    # form. Every non-ngboost learner also gets the poisson + betabinom forms on the FULL contract
    # (the F5-specific distributional question — is the low-mean zero-heavy F5 better served by a
    # bounded or a zero-dispersion form than by NegBin?).
    plan: list[tuple[str, str, str]] = [_REFERENCE]
    for mc in classes:
        for ct in contracts:
            entry = (mc, ct, default_form(mc))
            if entry not in plan:
                plan.append(entry)
    if not args.model_class and not args.contract:
        for mc in MODEL_CLASSES:
            if build_candidate(mc).native:
                continue
            for fm in ("poisson", "betabinom"):
                entry = (mc, "full", fm)
                if entry not in plan:
                    plan.append(entry)

    print(f"  {len(plan)} configs to evaluate\n")
    rows = []
    for mc, ct, fm in plan:
        t0 = time.time()
        res = evaluate_config(folds, mc, ct, form_mode=fm, top_k=args.top_k,
                              n_draws=args.n_draws, n_slices=args.n_slices, seed=args.seed)
        save_config_result(res, tag="bakeoff")
        rows.append(res)
        flag = "  ← REFERENCE" if res["is_incumbent"] else ""
        print(f"  {res['config_id']:<46} score {res['pooled_downstream_score']:.4f}  "
              f"calib80(total) {res['pooled_metrics']['total']['calib_80']:.3f}  "
              f"NLL {res['mean_per_side_nll']:.4f}  ({time.time() - t0:.0f}s){flag}")
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
    fm = args.form or default_form(mc)

    def objective(trial):
        params = _space(mc, trial)
        res = evaluate_config(folds, mc, contract, form_mode=fm, params=params, top_k=args.top_k,
                              n_draws=args.n_draws, n_slices=args.n_slices, seed=args.seed)
        save_config_result(res, tag=f"optuna_t{trial.number:03d}")
        trial.set_user_attr("pooled", res["pooled_downstream_score"])
        return res["pooled_downstream_score"]

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=args.seed))
    study.optimize(objective, n_trials=args.n_trials, show_progress_bar=False)
    print(f"\n  best pooled downstream score: {study.best_value:.5f}")
    print(f"  best params: {json.dumps(study.best_params)}")
    print("  every trial persisted → it counts toward PBO/DSR at `--stage decide`.")


# ---------------------------------------------------------------------------
# Stage 3 — decide (reuses the E2.1-r deflated verdict logic verbatim)
# ---------------------------------------------------------------------------

def stage_decide(args) -> None:
    results = load_config_results()
    if not results:
        raise SystemExit(f"[{_STORY}] no config results in {_TRIALS_DIR} — run --stage bakeoff first.")
    if not any(r.get("is_incumbent") for r in results):
        raise SystemExit(f"[{_STORY}] the reference config ({'/'.join(_REFERENCE)}) is missing — "
                         "it is the foil; re-run --stage bakeoff.")

    d = decide_verdict(results, pbo_gate=_PBO_GATE)
    incumbent, best, winner, verdict = d["incumbent"], d["best"], d["winner"], d["verdict"]

    if d["rejected"]:
        _log(f"{len(d['rejected'])} config(s) REJECTED by the calib_80 ≥ {_CALIB_TARGET} floor:")
        for r in sorted(d["rejected"], key=lambda x: x["pooled_downstream_score"]):
            worst = min(r["pooled_metrics"][j]["calib_80"] for j in SCORED_DISTS)
            ref = "  (THE REFERENCE — carried NegBin under-covers at F5)" if r.get("is_incumbent") else ""
            _log(f"  {r['config_id']:<48} worst calib_80 {worst:.3f}{ref}", indent=1)
    if not d["eligible"]:
        raise SystemExit(f"[{_STORY}] every config failed the calib_80 ≥ {_CALIB_TARGET} floor.")

    gain = (incumbent["pooled_downstream_score"] - winner["pooled_downstream_score"]) if winner else 0.0
    print("=" * 80)
    print(f"{_STORY} F5 DECISION — {d['n_configs']} configs, {d['n_buckets']} buckets")
    print("=" * 80)
    for r in sorted(d["eligible"], key=lambda r: r["pooled_downstream_score"])[:15]:
        marks = "".join([" ← REFERENCE" if r.get("is_incumbent") else "",
                         "  ★ WINNER" if winner and r["config_id"] == winner["config_id"] else ""])
        print(f"  {r['pooled_downstream_score']:.5f}  {r['config_id']:<46} "
              f"calib80 {r['pooled_metrics']['total']['calib_80']:.3f}"
              f"  PITdev {r['pooled_metrics']['total']['pit_max_decile_dev']:.4f}{marks}")
    print(f"\n  reference : {incumbent['config_id']}  score {incumbent['pooled_downstream_score']:.5f}"
          f"  [calib floor {'PASS' if d['incumbent_passes_floor'] else 'FAIL — DISQUALIFIED'}]")
    if winner:
        print(f"  winner    : {winner['config_id']}  score {winner['pooled_downstream_score']:.5f}"
              f"  (gain {gain:+.5f})")
    print(f"  full-search PBO : {d['full_pbo']:.3f} ({'PASS' if d['full_pbo'] < _PBO_GATE else 'FAIL'} "
          f"< {_PBO_GATE}) — high ⇒ the FORM/learner choice is a tied cluster (a null)")
    print(f"  minimal-fix DSR : {d['minimal_dsr']:.3f} ({'PASS' if d['minimal_dsr'] > 0 else 'FAIL'} > 0)")
    print(f"\n  VERDICT   : {verdict}")
    _print_action(verdict, incumbent, winner)
    print("\n  Honest framing: a market-BLIND F5 distribution is PRODUCT value, not an edge claim "
          "(best_alpha = 0). Whether F5 beats its own close is E2.6/E13.9's question.")

    def _slim(r):
        return None if r is None else {k: r.get(k) for k in
            ("config_id", "form", "params", "pooled_downstream_score", "pooled_metrics", "mean_per_side_nll")}

    doc = {
        "story": _STORY, "decided_at": date.today().isoformat(),
        "n_configs": d["n_configs"], "n_buckets": d["n_buckets"],
        "selection_metric": (
            "sum over {total, home_total, away_total} of PIT max decile dev (lower better); "
            "calib_80 ≥ 0.80 enforced as a FLOOR not a target (F5's low mean makes the inclusive-"
            "integer coverage inflation WORSE than full-game — an oracle covers ~0.82-0.86); "
            "run_diff measured but excluded (E2.2/E2.3 dropped dependence)"),
        "reference_config": "/".join(_REFERENCE),
        "verdict": verdict,
        "reference_passes_calibration_floor": d["incumbent_passes_floor"],
        "reference": _slim(incumbent), "best": _slim(best), "winner": _slim(winner),
        "gain_vs_reference": round(gain, 5),
        "full_search_pbo": d["full_pbo"], "best_dsr": d["best_dsr"], "minimal_fix_dsr": d["minimal_dsr"],
        "gates": {
            "full_search_deflated": bool(d["full_pbo"] < _PBO_GATE and d["best_dsr"] > 0.0),
            "minimal_fix_deflated": bool(d["minimal_dsr"] > 0.0), "market_blind": True,
        },
        "leaderboard": [{
            "config_id": r["config_id"], "form": r.get("form"),
            "score": r["pooled_downstream_score"],
            "calib_80_total": r["pooled_metrics"]["total"]["calib_80"],
            "pit_maxdev_total": r["pooled_metrics"]["total"]["pit_max_decile_dev"],
            "per_side_nll": r["mean_per_side_nll"],
            "passes_floor": r.get("passes_calibration_floor", passes_calibration_floor(r["pooled_metrics"])),
        } for r in sorted(results, key=lambda x: x["pooled_downstream_score"])],
    }
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _DECISION_JSON.write_text(json.dumps(doc, indent=2, default=float))
    _DECISION_MD.write_text(_render_md(doc))
    print(f"\n  → {_DECISION_JSON.relative_to(_PROJECT_ROOT)}")
    print(f"  → {_DECISION_MD.relative_to(_PROJECT_ROOT)}")
    print(f"  Next: `--stage finalize` fits the winning form → the served, leakage-safe F5 distribution.")
    _ = args


def _print_action(verdict: str, incumbent: dict, winner: dict | None) -> None:
    if verdict in ("PROMOTE", "PROMOTE_MINIMAL_FIX") and winner:
        print(f"  → the bake-off selects `{winner['config_id']}` (form={winner.get('form')}) as the F5\n"
              "    per-side distribution. Run `--stage finalize --model-class <winner learner> "
              "--contract <winner contract>\n    --form <winner form>` to emit the served, "
              "leakage-safe F5 distribution + PIT gate.")
    elif verdict == "FIX_REQUIRED":
        print("  → the carried NegBin reference FAILS the F5 calib floor (F5 is more dispersed/zero-\n"
              "    heavy than the full game) and no clean fix was found — widen the form/Optuna search\n"
              "    (the betabinom + poisson forms exist precisely for this) before finalizing.")
    else:  # INCUMBENT_STANDS
        print(f"  → nothing robustly beats the carried NegBin reference (`{incumbent['config_id']}`) at\n"
              "    F5 — so the E2.1 NegBin form carries to F5 as a TRUSTWORTHY null (proven over a\n"
              "    deflated ≥3-form search). Finalize with the reference form.")


def _render_md(doc: dict) -> str:
    lines = [
        f"# {_STORY} — First-5-innings (F5) per-side distribution bake-off",
        "", f"_Decided {doc['decided_at']} · {doc['n_configs']} configs · {doc['n_buckets']} CV buckets_", "",
        "## Verdict", "",
        f"**{doc['verdict']}**" + (
            f" — winner `{doc['winner']['config_id']}` (form `{doc['winner']['form']}`) vs reference "
            f"`{doc['reference']['config_id']}`, downstream gain `{doc['gain_vs_reference']:+.5f}`."
            if doc.get("winner") else f" — reference `{doc['reference']['config_id']}` carries."),
        "",
        f"- reference passes calib_80 floor: **{'YES' if doc['reference_passes_calibration_floor'] else 'NO — DISQUALIFIED'}**",
        f"- full-search PBO `{doc['full_search_pbo']:.3f}` "
        f"({'PASS' if doc['gates']['full_search_deflated'] else 'FAIL'} < 0.2)",
        f"- minimal-fix DSR `{doc['minimal_fix_dsr']:.3f}` "
        f"({'PASS' if doc['gates']['minimal_fix_deflated'] else 'FAIL'} > 0)",
        "", "## Selection metric", "", doc["selection_metric"], "",
        "## Leaderboard", "",
        "| config | form | score | calib_80 (total) | PIT maxdev (total) | per-side NLL | floor |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in doc["leaderboard"][:30]:
        lines.append(
            f"| `{r['config_id']}` | {r['form']} | {r['score']:.5f} | {r['calib_80_total']:.3f} | "
            f"{r['pit_maxdev_total']:.4f} | {r['per_side_nll']:.4f} | "
            f"{'✅' if r.get('passes_floor', True) else '❌'} |")
    lines += ["", "## Honest framing", "",
        "A market-BLIND F5 distribution is **product value** (an honest first-5-innings "
        "distribution), NOT an edge claim (`best_alpha = 0`). Whether F5 beats its own close is "
        "E2.6/E13.9's question under deflation. Market-blind CONTRACT-GUARD held on every "
        "contract in the search.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stage 4 — finalize: fit the winning form on all complete seasons → served F5 distribution
# ---------------------------------------------------------------------------

def _collect_oos(folds, model_class, contract, form_mode, *, top_k, seed) -> pd.DataFrame:
    """Walk-forward OOS per-(game, side) means for the chosen learner/contract, for calibration.

    Returns one row per (game_pk, side, season) with the eval-fold mean `mu` and realised `y` —
    the honest OOS marginals E2.3-style dispersion calibration needs (no in-sample optimism)."""
    cand = build_candidate(model_class)
    rows: list[pd.DataFrame] = []
    for fold in folds:
        cols = resolve_contract_f5(contract, fold.X_tr, fold.feat_cols, fold.ranking, top_k=top_k)
        cols_idx = np.array([fold.feat_cols.index(c) for c in cols])
        assert_market_blind(cols, context=f"{_STORY} finalize {model_class}/{contract}")
        mu_ev, sigma_ev = cand.fit_predict(fold.X_tr[:, cols_idx], fold.y_tr, fold.X_ev[:, cols_idx])
        d = fold.ev_meta.copy()
        d["mu"] = np.clip(mu_ev, 0.05, None)
        d["y"] = fold.y_ev
        d["season"] = fold.eval_year
        if sigma_ev is not None:
            d["sigma"] = sigma_ev
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


def _calibrate_dispersion_expanding(oos: pd.DataFrame, form_mode: str, side: str) -> dict[int, float]:
    """Leakage-safe per-season dispersion: season T fit on strictly-prior OOS residuals only.

    Mirrors totals_distribution.calibrate_dispersion_expanding but form-aware. poisson → {} (no
    dispersion). native → {} (per-game, not calibrated). Demonstrates the served value's stability
    across seasons (the E2.3 finding) without ever peeking at the scored season."""
    if form_mode in ("poisson", "native"):
        return {}
    sub = oos[oos["side"] == side]
    seasons = sorted(int(s) for s in sub["season"].unique())
    out: dict[int, float] = {}
    for t in seasons:
        prior = sub[sub["season"] < t]
        if len(prior) < 200:
            continue
        y, mu = prior["y"].to_numpy(float), prior["mu"].to_numpy(float)
        out[t] = round(_fit_side_dispersion(form_mode, y, mu), 4)
    return out


def _served_dispersion(oos: pd.DataFrame, form_mode: str, side: str) -> float | None:
    """Single served per-side dispersion = MLE over ALL pooled OOS residuals (E2.3 serves one
    stable value; the expanding map above shows it's leakage-safe-stable)."""
    if form_mode in ("poisson",):
        return None
    sub = oos[oos["side"] == side]
    y, mu = sub["y"].to_numpy(float), sub["mu"].to_numpy(float)
    if form_mode == "native":
        # per-game r from (μ, σ) — serve the median as a single fallback (native serves per game).
        return round(float(np.median(sigma_to_negbin_r(sub["mu"].to_numpy(float), sub["sigma"].to_numpy(float)))), 4)
    return round(_fit_side_dispersion(form_mode, y, mu), 4)


def _pivot_oos_games(oos: pd.DataFrame, disp_home: float, disp_away: float, form_mode: str) -> pd.DataFrame:
    """OOS per-(game, side) rows → one row per game with home/away μ, served disp, realised y."""
    d = oos.copy()
    if form_mode == "native":
        d["disp"] = sigma_to_negbin_r(d["mu"].to_numpy(float), d["sigma"].to_numpy(float))
    else:
        d["disp"] = np.where(d["side"] == "home", disp_home if disp_home else 1.0,
                             disp_away if disp_away else 1.0)
    wide = d.pivot_table(index=["game_pk", "game_date"], columns="side", values=["mu", "disp", "y"])
    wide.columns = [f"{v}_{s}" for v, s in wide.columns]
    wide = wide.rename(columns={"disp_home": "r_home", "disp_away": "r_away"})
    return wide.dropna().reset_index().sort_values(["game_date", "game_pk"]).reset_index(drop=True)


def stage_finalize(args) -> None:
    from betting_ml.utils.f5_distribution import pit_flatness, randomized_pit, interval_coverage

    df, numeric_cols, cat_cols, meta = load_cache()
    mc = args.model_class or _INCUMBENT
    contract = args.contract or _INCUMBENT_CONTRACT
    fm = args.form or _INCUMBENT_FORM
    print(f"=== {_STORY} stage 4 — FINALIZE ({mc} / {contract} / form={fm}) ===")

    folds = build_folds(df, numeric_cols, cat_cols, max_folds=args.max_folds)
    oos = _collect_oos(folds, mc, contract, fm, top_k=args.top_k, seed=args.seed)
    print(f"  OOS marginals: {len(oos):,} (game,side) rows, seasons "
          f"{sorted(int(s) for s in oos['season'].unique())}")

    expanding = {s: _calibrate_dispersion_expanding(oos, fm, s) for s in ("home", "away")}
    disp_home = _served_dispersion(oos, fm, "home")
    disp_away = _served_dispersion(oos, fm, "away")
    print(f"  served dispersion: home={disp_home}  away={disp_away}  (form {fm})")
    if expanding["home"]:
        print(f"  expanding-window home (leakage-safe, per season): {expanding['home']}")

    games = _pivot_oos_games(oos, disp_home or 1.0, disp_away or 1.0, fm)
    rng = np.random.default_rng(args.seed)
    dists, obs = draw_predictive(
        games.assign(),  # already has mu_home/mu_away/r_home/r_away/y_home/y_away
        fm, rng, n_draws=args.n_draws, n_cap=BETABINOM_N_CAP,
    )

    gate: dict[str, Any] = {}
    for key in ("total", "run_diff", "home_total", "away_total"):
        pit = pit_flatness(randomized_pit(obs[key], dists[key], rng))
        gate[key] = {
            "calib_80": round(interval_coverage(obs[key], dists[key]), 4),
            "pit_max_decile_dev": pit["max_decile_dev"],
            "pit_mean_dev": pit["mean_dev_from_half"],
            "pit_is_flat": pit["is_flat"],
        }
    floor_ok = all(gate[j]["calib_80"] >= _CALIB_TARGET for j in SCORED_DISTS)
    pit_ok = all(gate[j]["pit_is_flat"] for j in SCORED_DISTS)
    print("\n  ── F5 distribution gate (pooled OOS) ──")
    for j in ("total", "home_total", "away_total", "run_diff"):
        note = "" if j in SCORED_DISTS else "  (measured, not gated — dropped dependence)"
        print(f"    {j:<12} calib_80 {gate[j]['calib_80']:.3f}  PITdev {gate[j]['pit_max_decile_dev']:.4f}  "
              f"flat {gate[j]['pit_is_flat']}{note}")
    print(f"  calib floor (≥{_CALIB_TARGET} on total+team totals): {'PASS ✅' if floor_ok else 'FAIL ❌'}")
    print(f"  PIT-flat (total+team totals): {'PASS ✅' if pit_ok else 'FAIL ❌'}")

    params = F5DistributionParams(
        form=fm, dispersion_home=disp_home, dispersion_away=disp_away, rho=0.0,
        n_cap=BETABINOM_N_CAP, n_draws=10_000,
        notes=(f"E2.4 F5 per-side distribution. learner={mc}, contract={contract}. Served "
               f"dispersion MLE'd on pooled OOS held-out residuals (leakage-safe; per-season "
               f"expanding values confirm stability). Market-blind; best_alpha=0."),
    )
    calib_doc = {
        "story": _STORY, "fit_at": date.today().isoformat(),
        "model_class": mc, "contract": contract, "form": fm,
        "n_oos_rows": int(len(oos)), "n_games": int(len(games)),
        "served_params": params.to_dict(),
        "expanding_window_dispersion": expanding,
        "gate": gate,
        "gate_pass": {"calib_floor": floor_ok, "pit_flat": pit_ok},
        "market_blind": True,
    }
    if args.no_save:
        print("\n[--no-save] skipping artifact + calibration write.")
        return
    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (_ARTIFACT_DIR / "f5_distribution_v1.json").write_text(json.dumps(params.to_dict(), indent=2))
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _CALIB_JSON.write_text(json.dumps(calib_doc, indent=2, default=float))
    _CALIB_MD.write_text(_render_calib_md(calib_doc))
    print(f"\n  served params → {(_ARTIFACT_DIR / 'f5_distribution_v1.json').relative_to(_PROJECT_ROOT)}")
    print(f"  calibration   → {_CALIB_JSON.relative_to(_PROJECT_ROOT)}")
    print("  Artifact NOT promoted to S3 (gated at E2.6). Next: E2.5 registration + leakage-safe backfill; "
          "E2.6 measures F5 efficiency vs its own closes (do NOT assume it).")
    _ = (cat_cols, meta)


def _render_calib_md(doc: dict) -> str:
    g = doc["gate"]
    lines = [
        f"# {_STORY} — F5 per-side distribution calibration (served)", "",
        f"_Fit {doc['fit_at']} · learner `{doc['model_class']}` · contract `{doc['contract']}` · "
        f"form `{doc['form']}` · {doc['n_games']:,} OOS games_", "",
        "## Served contract", "",
        f"- form: **{doc['form']}**  ·  served dispersion home `{doc['served_params']['dispersion_home']}` / "
        f"away `{doc['served_params']['dispersion_away']}`  ·  ρ = 0 (independent, E2.2)", "",
        "## Gate (pooled OOS)", "",
        "| distribution | calib_80 | PIT max-decile-dev | PIT-flat | gated |",
        "|---|---|---|---|---|",
    ]
    for j in ("total", "home_total", "away_total", "run_diff"):
        gated = "yes" if j in SCORED_DISTS else "no (dropped dependence)"
        lines.append(f"| {j} | {g[j]['calib_80']:.3f} | {g[j]['pit_max_decile_dev']:.4f} | "
                     f"{'✅' if g[j]['pit_is_flat'] else '❌'} | {gated} |")
    lines += ["",
        f"**calib floor (≥0.80 on total + team totals):** {'PASS ✅' if doc['gate_pass']['calib_floor'] else 'FAIL ❌'}  ·  "
        f"**PIT-flat:** {'PASS ✅' if doc['gate_pass']['pit_flat'] else 'FAIL ❌'}", "",
        "## Honest framing", "",
        "A market-BLIND F5 distribution is product value, not an edge claim (`best_alpha = 0`). "
        "F5 efficiency vs its own close is measured at E2.6 — not assumed here.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=f"Story {_STORY} — F5 per-side distribution bake-off")
    ap.add_argument("--assemble", action="store_true",
                    help="Stage 0: ONE lakehouse (DuckDB/S3) pull (pregame features + F5 target) → cache.")
    ap.add_argument("--stage", choices=["bakeoff", "optuna", "decide", "finalize"])
    ap.add_argument("--min-year", type=int, default=2018)
    ap.add_argument("--model-class", choices=list(MODEL_CLASSES))
    ap.add_argument("--contract", choices=list(CONTRACTS))
    ap.add_argument("--form", choices=list(FORM_MODES))
    ap.add_argument("--top-k", type=int, default=_DEFAULT_TOP_K)
    ap.add_argument("--n-trials", type=int, default=30)
    ap.add_argument("--n-draws", type=int, default=_DEFAULT_DRAWS)
    ap.add_argument("--n-slices", type=int, default=4, help="PBO buckets per CV fold.")
    ap.add_argument("--max-folds", type=int, default=None, help="Cap folds (smoke runs).")
    ap.add_argument("--n-jobs", type=int, default=None, help="Learner thread cap.")
    ap.add_argument("--no-save", action="store_true", help="finalize: skip artifact write.")
    ap.add_argument("--seed", type=int, default=_SEED)
    args = ap.parse_args()

    set_n_jobs(args.n_jobs)
    _log(f"{_STORY} start · stage={args.stage or 'assemble'} · pid={os.getpid()} "
         f"· BLAS cap={_THREAD_CAP or 'default'}")
    _log("Ctrl-C lands only between native fits — to stop immediately: kill -9 " + str(os.getpid()))

    if args.assemble:
        assemble_cache(args.min_year)
        return
    if args.stage == "bakeoff":
        stage_bakeoff(args)
    elif args.stage == "optuna":
        stage_optuna(args)
    elif args.stage == "decide":
        stage_decide(args)
    elif args.stage == "finalize":
        stage_finalize(args)
    else:
        ap.error("pass --assemble or --stage {bakeoff,optuna,decide,finalize}")


if __name__ == "__main__":
    main()
