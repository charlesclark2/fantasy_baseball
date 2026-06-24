"""incremental_lift_eval.py — Edge Program Story E13.4 (the incremental-lift harness).

The reusable evaluator the E13.4 coverage dossier's §5/§6 lift-tests need, and which did
NOT previously exist (the dossier's handoff command `rebaseline_purged_cv.py --add-features …`
was aspirational — that script only re-scores the FIXED champion recipe across CV regimes).

WHAT IT ANSWERS
---------------
"Does adding candidate feature column(s) to the CURRENT champion contract buy a *trustworthy*
incremental lift?" — for a SINGLE target, holding the model recipe fixed and changing ONLY the
feature set (base vs base+candidate). That isolation is the whole point: a recipe swap would
confound the feature's value with hyperparameter changes.

TWO TARGET FAMILIES (the §6 run-order: per-side run-MEANS first, H2H/champions second)
--------------------------------------------------------------------------------------
  * perside_runs  — the E2.1 per-side NegBin runs marginal (LightGBM-Poisson mean + NegBin r).
    The PRIORITY integration target (E2.2 §4.5: a recency/derived signal is most likely to move
    a number here). Candidate columns are `off_*` (batting side) / `opp_*` (faced pitching side)
    bases present in the wide mart — e.g. B1 TTO = `opp_starter_tto3_xwoba_penalty`.
  * home_win / run_diff / total_runs — the champions (reuses the promotion_gate_eval adapters;
    same spec on BOTH arms, only the columns differ).

WHAT IT REPORTS (per candidate config)
--------------------------------------
  * INCREMENTAL LIFT — base_metric − candidate_metric, per game, pooled AND stratified by
    `is_cold_start` (E13.7). The lift is read on the NON-cold-start subset too, so an E13.7
    baseline-FILLED row (rookie/call-up with archetype/Stuff+/platoon imputed) can neither
    manufacture nor dilute the signal. Metric is a LOSS (lower=better) so lift>0 ⇒ candidate helps.
  * PBO (AFML §11.4, betting_ml/utils/overfitting) over {base, candidates...} on a time-sliced
    performance matrix. PBO<0.2 = the in-sample-best config persists OOS (not selection noise).
  * DSR (AFML §14) on the per-game improvement series (base−candidate, oriented so >0=better),
    deflated by the number of candidate configs tried. DSR≥0.95 ("DSR>0 at 95%") = the mean
    per-game gain is significantly positive after multiple-testing deflation.
  * ORTHOGONALITY — max |corr| of each candidate column vs the base contract columns. A high
    corr means the candidate is redundant with what the model already has (the E13.4 finding for
    the FanGraphs windows); pre-registered cut for Candidate A is corr ≥ 0.7 ⇒ RULE OUT.

SHRINKAGE DISCIPLINE (E13.4 §5): a short-window value is mostly variance. `--shrink-raw-col`
empirical-Bayes shrinks a raw candidate toward the train league mean by its sample-size column
(`value' = (n·raw + k·prior)/(n+k)`) BEFORE it enters the model. Production features (e.g. the
TTO mart) bake their own shrinkage in dbt; this knob is for ad-hoc / validation candidates.

GATE (ship a winner only if ALL hold; else record the null — a clean null IS the deliverable):
  incremental lift > 0 (pooled AND on the non-cold-start subset)  AND  PBO < 0.2  AND  DSR ≥ 0.95
  AND (for the orthogonality pre-check candidates) max|corr| < the pre-registered cut.

VALIDATE THE HARNESS BEFORE TRUSTING IT (`--sanity`): injects a pure-noise candidate (expect
~0 lift, PBO high) and an in-contract-duplicate candidate (expect ~0 incremental lift). If those
don't read ~null, the harness — not the feature — is the finding. Needs no new dbt / no Snowflake
schema change (columns injected in pandas).

RUNTIME: retrains the recipe × folds × configs — minutes (NGBoost/LightGBM dominate). HAND TO
THE OPERATOR; writes nothing to prod. Pure-logic functions (PBO matrix, lift+strat, DSR mapping,
shrink, NegBin CRPS/NLL) are unit-tested in betting_ml/tests/test_incremental_lift_eval.py.

Usage (operator):
    # validate the harness first (sanity configs; per-side is the fastest backend)
    uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs --sanity
    # then the real candidate — per-side FIRST, then home_win
    uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs \
        --add-features opp_starter_tto3_xwoba_penalty --run-name e13_4_b1_tto
    uv run python betting_ml/scripts/incremental_lift_eval.py --target home_win \
        --add-features home_starter_tto3_xwoba_penalty,away_starter_tto3_xwoba_penalty \
        --run-name e13_4_b1_tto
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.overfitting import (
    DSR_CONFIDENCE, PBO_SHADOW_TO_LIVE, deflated_sharpe, pbo_cscv,
)

_RESULTS_DIR = (
    PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"
)

# ── Sanity-config column names (injected by --sanity; never real features) ────
_NOISE_COL = "__sanity_noise__"
_DUP_PREFIX = "__sanity_dup__"


def merge_feature_parquet(df: pd.DataFrame, path: str | None) -> pd.DataFrame:
    """Left-join a game_pk-keyed candidate-feature parquet onto the loaded feature frame (opt-in;
    no-op when path is None, so the default Snowflake-only behaviour is untouched).

    This is the bridge for features the heavy LAKEHOUSE build produces OUTSIDE Snowflake (E13.10's
    zone-overlap is built from S3 pitch parquet via duckdb, NOT a dbt mart) — it lets a lakehouse
    feature be lift-tested without a Snowflake write + dbt full-refresh just to probe a likely-null
    candidate. The parquet must carry `game_pk` plus the candidate column(s); rows are matched on
    game_pk (coerced to int). Columns already present in df are NOT overwritten (fail-safe)."""
    if not path:
        return df
    feat = pd.read_parquet(path)
    if "game_pk" not in feat.columns:
        raise SystemExit(f"--feature-parquet {path}: missing required 'game_pk' column "
                         f"(has {list(feat.columns)})")
    if "game_pk" not in df.columns:
        raise SystemExit("feature frame has no 'game_pk' to join the --feature-parquet on.")
    new_cols = [c for c in feat.columns if c != "game_pk" and c not in df.columns]
    if not new_cols:
        print(f"  [feature-parquet] no new columns to add from {path} (all already present?)")
        return df
    feat = feat[["game_pk"] + new_cols].copy()
    feat["game_pk"] = pd.to_numeric(feat["game_pk"], errors="coerce").astype("Int64")
    out = df.copy()
    out["game_pk"] = pd.to_numeric(out["game_pk"], errors="coerce").astype("Int64")
    merged = out.merge(feat, on="game_pk", how="left")
    cov = float(merged[new_cols[0]].notna().mean())
    print(f"  [feature-parquet] merged {new_cols} from {path}  (coverage {cov:.1%} of rows)")
    return merged


# ════════════════════════════════════════════════════════════════════════════
#  PURE-LOGIC primitives (unit-tested; no Snowflake / no model dependency)
# ════════════════════════════════════════════════════════════════════════════

def eb_shrink_toward_mean(raw: np.ndarray, n: np.ndarray, prior: float, k: float) -> np.ndarray:
    """Empirical-Bayes shrink a raw per-unit estimate toward `prior` by sample size `n`:
    `(n·raw + k·prior)/(n+k)`. k = the pseudo-count strength (larger ⇒ shrink harder). Rows
    with n=0 (or NaN raw) collapse to the prior. Isolates persistent change from small-sample
    variance — the E13.4 §5 discipline ('a 7d spike is mostly variance')."""
    raw = np.asarray(raw, float)
    n = np.asarray(n, float)
    n = np.where(np.isnan(n), 0.0, np.clip(n, 0.0, None))
    out = (n * np.where(np.isnan(raw), 0.0, raw) + k * prior) / (n + k)
    return out


def negbin_crps(y: np.ndarray, mu: np.ndarray, r: float, *, max_k: int = 60) -> np.ndarray:
    """Per-observation CRPS of a NegBin(mu, r) count distribution, computed exactly over the
    discrete support 0..max_k as Σ_k (F(k) − 1{y≤k})². The proper score E13.4 §6 names for the
    per-side marginal — sensitive to the WHOLE distribution, not just the point (NLL/MAE)."""
    from scipy.stats import nbinom
    mu = np.clip(np.asarray(mu, float), 1e-6, None)
    y = np.asarray(y, float)
    p = r / (r + mu)                                   # nbinom param (n=r, p)
    ks = np.arange(0, max_k + 1)
    cdf = nbinom.cdf(ks[None, :], n=r, p=p[:, None])   # (N, K+1)
    step = (y[:, None] <= ks[None, :]).astype(float)   # 1{y ≤ k}
    return np.sum((cdf - step) ** 2, axis=1)


def negbin_nll(y: np.ndarray, mu: np.ndarray, r: float) -> np.ndarray:
    """Per-observation NegBin(mu, r) NLL (the E2.1 native proper score). Vectorized twin of
    train_perside_negbin.negbin_nll (which returns the mean)."""
    from scipy.special import gammaln
    mu = np.clip(np.asarray(mu, float), 1e-6, None)
    y = np.asarray(y, float)
    pp = r / (r + mu)
    ll = (gammaln(y + r) - gammaln(r) - gammaln(y + 1.0)
          + r * np.log(pp) + y * np.log(1.0 - pp + 1e-12))
    return -ll


def time_sliced_perf(dates: np.ndarray, scores_by_config: dict[str, np.ndarray],
                     *, n_slices: int) -> tuple[np.ndarray, list[str]]:
    """Build the (T, N) per-config performance matrix PBO consumes: sort games by date, split
    into T contiguous time slices, and take each config's MEAN score per slice. Returns
    (matrix, config_names). Scores are LOSSES (lower=better) — pass higher_is_better=False to
    pbo_cscv. Slices are time-ordered so CSCV's contiguous partitions respect chronology."""
    names = list(scores_by_config)
    order = np.argsort(np.asarray(dates))
    n = len(order)
    n_slices = max(2, min(int(n_slices), n))
    buckets = np.array_split(order, n_slices)
    M = np.empty((len(buckets), len(names)), float)
    for t, idx in enumerate(buckets):
        for j, name in enumerate(names):
            M[t, j] = float(np.mean(scores_by_config[name][idx]))
    return M, names


@dataclass
class StratLift:
    stratum: str
    n: int
    base_metric: float
    cand_metric: float
    lift: float            # base − cand (LOSS units; >0 ⇒ candidate better)
    lift_pct: float        # lift / base_metric


def stratified_lift(base: np.ndarray, cand: np.ndarray, non_cold_mask: np.ndarray | None,
                    ) -> list[StratLift]:
    """Pooled + cold-start-stratified incremental lift. base/cand are per-game LOSS scores.
    `non_cold_mask` True = NON-cold-start row (E13.7 trustworthy). Reads lift on ALL, on the
    NON-cold subset (the trustworthy read), and on the COLD subset (diagnostic)."""
    base = np.asarray(base, float)
    cand = np.asarray(cand, float)
    out: list[StratLift] = []

    def _one(label: str, mask: np.ndarray) -> StratLift:
        b, c = float(base[mask].mean()), float(cand[mask].mean())
        lift = b - c
        return StratLift(label, int(mask.sum()), b, c, lift, lift / b if b else 0.0)

    out.append(_one("all", np.ones(len(base), bool)))
    if non_cold_mask is not None:
        nc = np.asarray(non_cold_mask, bool)
        if nc.any():
            out.append(_one("non_cold_start", nc))
        if (~nc).any():
            out.append(_one("cold_start", ~nc))
    return out


def candidate_dsr(base: np.ndarray, cand: np.ndarray, *, n_trials: int):
    """DSR on the per-game improvement series d = base − cand (LOSS units, so d>0 ⇒ candidate
    better). Treated as a 'return' series; deflated by n_trials (the candidate-config count =
    the multiple-testing burden). passes_live = DSR ≥ 0.95."""
    d = np.asarray(base, float) - np.asarray(cand, float)
    if len(d) < 3 or np.std(d) == 0:
        return None
    return deflated_sharpe(d, n_trials=max(int(n_trials), 1))


def max_abs_corr(df: pd.DataFrame, cand_cols: list[str], base_cols: list[str]) -> dict[str, dict]:
    """For each candidate column, the max |Pearson corr| against the base contract columns
    (pairwise-complete). The E13.4 orthogonality pre-check: high corr ⇒ redundant."""
    out: dict[str, dict] = {}
    base_present = [c for c in base_cols if c in df.columns and c not in cand_cols]
    for cc in cand_cols:
        if cc not in df.columns:
            out[cc] = {"max_abs_corr": None, "vs": None, "note": "candidate column absent"}
            continue
        x = pd.to_numeric(df[cc], errors="coerce")
        best, best_col = 0.0, None
        for bc in base_present:
            y = pd.to_numeric(df[bc], errors="coerce")
            ok = x.notna() & y.notna()
            if ok.sum() < 30 or x[ok].std() == 0 or y[ok].std() == 0:
                continue
            c = abs(float(np.corrcoef(x[ok], y[ok])[0, 1]))
            if c > best:
                best, best_col = c, bc
        out[cc] = {"max_abs_corr": round(best, 4), "vs": best_col}
    return out


def candidate_is_degenerate(cand_eval_std, all_lift: float, dsr, cand_coverage=None,
                            min_coverage: float = 0.5) -> tuple[bool, str | None]:
    """Guard against a corrupt/constant/under-built feature being recorded as a 'no edge' null
    (E13.4 — the failures that nearly happened when a dbt build silently zeroed the TTO column,
    and when an incremental build left the B2 column NULL across all history).

    A candidate is DEGENERATE when it could not have produced a trustworthy lift:
      * its eval-set values are ~constant (zero variance) → it entered the matrix as a constant
        and the tree dropped it, OR the upstream feature is corrupt/missing; or
      * it produced byte-identical per-game scores to base (lift ≡ 0 AND a zero-variance
        improvement series → DSR n/a); or
      * it is non-null for only a small fraction of the eval games (`cand_coverage` < min_coverage)
        → the model trained/scored on a mostly-imputed-constant column, so any lift is on ~nothing.
        This is the incremental-not-full-refreshed signature (2026-06-23 B2): an `incremental` model
        only repopulated the 7-day lookback, so the new column was NULL across history. NOTE this
        fires even when std looks fine — std is computed on the few non-null rows, which can look
        healthy while >99% of the column is imputed (exactly what slipped past the std/byte-identical
        checks on the B2 home_win run).
    Any of these is a DATA/COVERAGE failure, NOT a trustworthy signal null — the lift study must NOT
    bank it as 'no edge'. Returns (is_degenerate, reason)."""
    if cand_eval_std is not None and cand_eval_std < 1e-9:
        return True, (f"candidate column is ~constant on the eval set (std={cand_eval_std:.2e}) "
                      f"— corrupt/missing/collapsed feature, NOT a signal null")
    if cand_coverage is not None and cand_coverage < min_coverage:
        return True, (f"candidate column is non-null on only {cand_coverage:.1%} of eval games "
                      f"(< {min_coverage:.0%}) — under-built / not full-refreshed across history "
                      f"(an incremental build only repopulated recent rows?), NOT a signal null")
    if abs(all_lift) < 1e-12 and dsr is None:
        return True, ("candidate produced byte-identical scores to base (lift≡0, zero-variance "
                      "improvement) — the feature had NO effect (constant/dropped); NOT a signal null")
    return False, None


def _candidate_eval_coverage(df: pd.DataFrame, extra_cols: list[str]) -> float | None:
    """Min non-null fraction across a candidate's present columns on the (eval) frame — the share
    of games for which the model actually saw a real (non-imputed) value. None if no column is
    present. Pairs with the dbt-side coverage check (output-null-while-parent-populated)."""
    fracs = []
    for c in extra_cols:
        if c in df.columns and len(df):
            v = pd.to_numeric(df[c], errors="coerce")
            fracs.append(float(v.notna().mean()))
    return min(fracs) if fracs else None


def _candidate_eval_std(df: pd.DataFrame, extra_cols: list[str]) -> float | None:
    """Min Pearson-usable std across a candidate's present columns on the (eval) frame — the
    variance the model actually saw. None if no column is present."""
    stds = []
    for c in extra_cols:
        if c in df.columns:
            v = pd.to_numeric(df[c], errors="coerce")
            stds.append(float(v.std(skipna=True)) if v.notna().any() else 0.0)
    return min(stds) if stds else None


# ════════════════════════════════════════════════════════════════════════════
#  CONFIG model: base + N candidate configs
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    """One feature set to score: the base contract + this config's extra columns
    (empty for the base config itself)."""
    name: str
    extra: list[str] = field(default_factory=list)


def _build_configs(add_features: list[str], sanity: bool) -> list[Config]:
    configs = [Config("base", [])]
    if add_features:
        configs.append(Config("candidate", list(add_features)))
    if sanity:
        configs.append(Config("sanity_noise", [_NOISE_COL]))
        configs.append(Config("sanity_dup", []))   # dup col is resolved per backend (a real base col copy)
    if len(configs) == 1:
        raise SystemExit("Nothing to evaluate: pass --add-features and/or --sanity.")
    return configs


# ════════════════════════════════════════════════════════════════════════════
#  BACKEND: champions (home_win / run_diff / total_runs) — reuse gate adapters
# ════════════════════════════════════════════════════════════════════════════

_CHAMP_METRIC = {"home_win": "nll", "run_diff": "mae", "total_runs": "mae"}  # nll(binary)=logloss


def _champion_backend(target: str, configs: list[Config], *, metric: str, embargo_days: int,
                      min_year: int, n_slices: int, seed: int,
                      feature_parquet: str | None = None) -> dict:
    from betting_ml.scripts.promotion_gate_eval import (
        _TARGETS, _build_specs, _contract_cols, _impute, _reconstruct_champion_cols,
        make_gate_splitter,
    )
    from betting_ml.utils.data_loader import load_features

    cfg = _TARGETS[target]
    print(f"Loading features from Snowflake (min_year={min_year}) ...")
    df = load_features(min_year=min_year).reset_index(drop=True)
    df = merge_feature_parquet(df, feature_parquet)
    print(f"  {len(df)} rows, seasons {sorted(df['game_year'].dropna().unique().tolist())}")

    base_cols = (_reconstruct_champion_cols(df) if cfg["champion_kind"] == "reconstruct"
                 else _contract_cols(cfg["champion_contract"], df))
    spec, _ = _build_specs(target, cfg, seed=seed)   # SAME spec on every config (champion arm)

    # Resolve sanity columns into df (noise + an in-contract duplicate).
    dup_col = None
    if any(c.name == "sanity_dup" for c in configs):
        dup_col = f"{_DUP_PREFIX}{base_cols[0]}"
        df[dup_col] = pd.to_numeric(df[base_cols[0]], errors="coerce")
        for c in configs:
            if c.name == "sanity_dup":
                c.extra = [dup_col]
    if any(_NOISE_COL in c.extra for c in configs):
        rng = np.random.default_rng(seed)
        df[_NOISE_COL] = rng.standard_normal(len(df))

    target_col, non_cold_col = cfg["target_col"], None
    if {"home_starter_is_cold_start", "away_starter_is_cold_start"} <= set(df.columns):
        non_cold = ((pd.to_numeric(df["home_starter_is_cold_start"], errors="coerce").fillna(0) == 0)
                    & (pd.to_numeric(df["away_starter_is_cold_start"], errors="coerce").fillna(0) == 0))
        df["__non_cold__"] = non_cold.values
        non_cold_col = "__non_cold__"

    # Fail loudly if a real candidate's columns are absent (e.g. the lift was run before the dbt
    # build materialized them) — otherwise the config would silently collapse to the base.
    for c in configs:
        missing = [x for x in c.extra if x not in df.columns]
        if missing:
            raise SystemExit(
                f"config '{c.name}': columns absent from feature_pregame_game_features: {missing}. "
                f"Build the dbt feature first (dbtf build --select state:modified+).")

    all_extra = sorted({c for cf in configs for c in cf.extra})
    splitter, _ = make_gate_splitter(True, feature_cols=set(base_cols) | set(all_extra),
                                     embargo_days=embargo_days)
    print(f"  base contract: {len(base_cols)} feats; metric={metric}; "
          f"PURGED CV (embargo={embargo_days}d); configs={[c.name for c in configs]}")

    # Per-game scores per config, accumulated across folds (aligned to a global eval index).
    per_game = {c.name: {} for c in configs}   # name -> {orig_idx: score}
    for train_idx, eval_idx in splitter(df):
        yr = int(df.loc[eval_idx, "game_year"].mode()[0])
        ytr = df.loc[train_idx, target_col].values
        yev = df.loc[eval_idx, target_col].values
        for c in configs:
            cols = base_cols + [x for x in c.extra if x in df.columns]
            Xtr, Xev = _impute(df.loc[train_idx, cols], df.loc[eval_idx, cols])
            out = spec.fit_predict(Xtr, ytr, Xev, yev)
            s = out.score_to_truth(yev, metric)
            for oi, sc in zip(eval_idx, s):
                per_game[c.name][int(oi)] = float(sc)
        print(f"    fold {yr}: scored {len(eval_idx)} games × {len(configs)} configs")

    common = sorted(set.intersection(*[set(per_game[c.name]) for c in configs]))
    dates = df.loc[common, "game_date"].values
    non_cold_mask = (df.loc[common, non_cold_col].values.astype(bool)
                     if non_cold_col else None)
    scores = {c.name: np.array([per_game[c.name][i] for i in common]) for c in configs}
    return _assemble(target, metric, df, common, dates, non_cold_mask, scores, configs,
                     base_cols, n_slices)


# ════════════════════════════════════════════════════════════════════════════
#  BACKEND: per-side NegBin (E2.1) — reuse train_perside_negbin assembly
# ════════════════════════════════════════════════════════════════════════════

def _perside_backend(configs: list[Config], *, metric: str, embargo_days: int, min_year: int,
                     n_slices: int, seed: int, feature_parquet: str | None = None) -> dict:
    from betting_ml.scripts.totals_generative.train_perside_negbin import (
        _MIN_MU, _TARGET, _fit_lgbm, _impute_means, _prepare_matrix, build_perside_frame,
        fit_negbin_r, load_wide,
    )
    from betting_ml.utils.cv import PurgedWalkForwardSplit

    print(f"Loading wide per-game mart from Snowflake (min_year={min_year}) ...")
    wide = load_wide(min_year)
    # Carry the faced-starter cold-start flag through the unpivot for stratification.
    wide.columns = [c.lower() for c in wide.columns]
    # Opt-in lakehouse feature bridge: land home_<base>/away_<base> in the wide mart so the
    # per-side unpivot can derive off_<base>/opp_<base> (e.g. opp_zone_overlap for E13.10).
    wide = merge_feature_parquet(wide, feature_parquet)
    df, numeric_cols, cat_cols = build_perside_frame(wide)
    df = _attach_perside_coldstart(df, wide)

    # Resolve any off_*/opp_* candidate that the production allow-list doesn't already unpivot,
    # by deriving it from the wide mart on the fly (eval-only — keeps the candidate OUT of the
    # production per-side feature list until it earns promotion).
    for c in configs:
        for col in c.extra:
            if col in df.columns or col in (_NOISE_COL,) or col.startswith(_DUP_PREFIX):
                continue
            df = _attach_perside_wide_base(df, wide, col)
    print(f"  per-side rows: {len(df)}; base = {len(numeric_cols)} num + {len(cat_cols)} cat")

    # Resolve sanity columns into the per-side frame.
    dup_col = None
    if any(c.name == "sanity_dup" for c in configs):
        dup_col = f"{_DUP_PREFIX}{numeric_cols[0]}"
        df[dup_col] = pd.to_numeric(df[numeric_cols[0]], errors="coerce")
        for c in configs:
            if c.name == "sanity_dup":
                c.extra = [dup_col]
    if any(_NOISE_COL in c.extra for c in configs):
        rng = np.random.default_rng(seed)
        df[_NOISE_COL] = rng.standard_normal(len(df))

    # Validate candidate columns exist in the per-side frame (off_*/opp_* bases).
    for c in configs:
        missing = [x for x in c.extra if x not in df.columns]
        if missing:
            raise SystemExit(
                f"config '{c.name}': columns absent from the per-side frame: {missing}. "
                f"Per-side candidate columns must be present as off_<base>/opp_<base> in "
                f"feature_pregame_game_features (build the dbt feature first).")

    splitter = PurgedWalkForwardSplit(min_train_seasons=3, embargo_days=embargo_days)
    folds = list(splitter.split(df, feature_cols=numeric_cols))
    print(f"  PURGED CV (embargo={embargo_days}d); metric={metric}; "
          f"configs={[c.name for c in configs]}")

    per_game = {c.name: {} for c in configs}
    for train_idx, eval_idx in folds:
        yr = int(df.loc[eval_idx, "game_year"].mode().iloc[0])
        tr, ev = df.loc[train_idx], df.loc[eval_idx]
        y_tr = tr[_TARGET].to_numpy(float)
        y_ev = ev[_TARGET].to_numpy(float)
        for c in configs:
            num = numeric_cols + [x for x in c.extra if x in df.columns]
            means = _impute_means(tr, num)
            X_tr, X_ev, _ = _prepare_matrix(tr, ev, num, cat_cols, means, None)
            model = _fit_lgbm(X_tr, y_tr)
            mu_tr = np.clip(model.predict(X_tr), _MIN_MU, None)
            mu_ev = np.clip(model.predict(X_ev), _MIN_MU, None)
            r = fit_negbin_r(y_tr, mu_tr)                   # dispersion on TRAIN only
            s = (negbin_crps(y_ev, mu_ev, r) if metric == "crps"
                 else negbin_nll(y_ev, mu_ev, r))
            for oi, sc in zip(eval_idx, s):
                per_game[c.name][int(oi)] = float(sc)
        print(f"    fold {yr}: scored {len(eval_idx)} per-side rows × {len(configs)} configs")

    common = sorted(set.intersection(*[set(per_game[c.name]) for c in configs]))
    dates = df.loc[common, "game_date"].values
    nc = df.loc[common, "opp_starter_is_cold_start"]
    non_cold_mask = (pd.to_numeric(nc, errors="coerce").fillna(0) == 0).values
    scores = {c.name: np.array([per_game[c.name][i] for i in common]) for c in configs}
    return _assemble("perside_runs", metric, df, common, dates, non_cold_mask, scores, configs,
                     numeric_cols, n_slices)


def _attach_perside_wide_base(df: pd.DataFrame, wide: pd.DataFrame, col: str) -> pd.DataFrame:
    """Derive an `off_<base>`/`opp_<base>` candidate column for the per-side frame from the wide
    mart, mirroring build_perside_frame's unpivot: `off_` = the batting side's own value,
    `opp_` = the faced (opposing) side's value. Eval-only — no edit to the production allow-list.
    Raises if the prefix/base is not resolvable from the wide mart."""
    if col.startswith("off_"):
        base, opp = col[len("off_"):], False
    elif col.startswith("opp_"):
        base, opp = col[len("opp_"):], True
    else:
        raise SystemExit(
            f"per-side candidate '{col}' must be prefixed off_/opp_ (batting/faced side) so the "
            f"harness can unpivot it from the wide mart, or already exist in the per-side frame.")
    if f"home_{base}" not in wide.columns or f"away_{base}" not in wide.columns:
        raise SystemExit(
            f"per-side candidate '{col}': wide mart lacks home_{base}/away_{base} — build the "
            f"dbt feature into feature_pregame_game_features first.")
    # For side=home: own=home_<base>, faced=away_<base>. opp_ takes the faced side.
    g = pd.DataFrame({
        "game_pk": wide["game_pk"],
        "home": pd.to_numeric(wide[f"home_{base}"], errors="coerce").values,
        "away": pd.to_numeric(wide[f"away_{base}"], errors="coerce").values,
    })
    m = df.merge(g, on="game_pk", how="left")
    is_home = df["side"].values == "home"
    own = np.where(is_home, m["home"].values, m["away"].values)
    faced = np.where(is_home, m["away"].values, m["home"].values)
    df = df.copy()
    df[col] = faced if opp else own
    return df


def _attach_perside_coldstart(df: pd.DataFrame, wide: pd.DataFrame) -> pd.DataFrame:
    """Map each per-side row's FACED starter cold-start flag (opponent's starter) onto the
    per-side frame: side=home faces away's starter, and vice-versa. Absent flag ⇒ 0 (treated
    as non-cold, the conservative default)."""
    h = pd.to_numeric(wide.get("away_starter_is_cold_start", 0), errors="coerce").fillna(0)
    a = pd.to_numeric(wide.get("home_starter_is_cold_start", 0), errors="coerce").fillna(0)
    flag = pd.DataFrame({"game_pk": wide["game_pk"], "home": h.values, "away": a.values})
    m = df.merge(flag, on="game_pk", how="left")
    df = df.copy()
    df["opp_starter_is_cold_start"] = np.where(df["side"].values == "home",
                                               m["home"].values, m["away"].values)
    return df


# ════════════════════════════════════════════════════════════════════════════
#  Assembly: lift + PBO + DSR + orthogonality → verdict
# ════════════════════════════════════════════════════════════════════════════

def _assemble(target, metric, df, common, dates, non_cold_mask, scores, configs, base_cols,
              n_slices) -> dict:
    base = scores["base"]
    cand_names = [c.name for c in configs if c.name != "base"]
    n_trials = len(cand_names)

    # PBO over ALL configs (base + candidates) on the time-sliced loss matrix.
    M, names = time_sliced_perf(dates, scores, n_slices=n_slices)
    pbo = pbo_cscv(M, higher_is_better=False, n_splits=min(n_slices, M.shape[0]))

    extra_by_name = {c.name: c.extra for c in configs}
    results = {"target": target, "metric": metric, "n_eval": len(common),
               "n_configs": len(configs),
               "pbo": {"pbo": pbo.pbo, "n_combos": pbo.n_combos, "n_configs": pbo.n_configs,
                       "n_slices": pbo.n_splits, "clears_live": pbo.clears_live_pbo,
                       "threshold": PBO_SHADOW_TO_LIVE},
               "candidates": {}}
    for name in cand_names:
        cand = scores[name]
        lift = stratified_lift(base, cand, non_cold_mask)
        dsr = candidate_dsr(base, cand, n_trials=n_trials)
        orth = max_abs_corr(df.loc[common], extra_by_name[name], base_cols)
        by = {s.stratum: asdict(s) for s in lift}
        nc = by.get("non_cold_start", by["all"])
        lift_pos = by["all"]["lift"] > 0 and nc["lift"] > 0
        dsr_ok = bool(dsr and dsr.passes_live)
        # Degenerate-candidate guard: a constant/dropped/corrupt feature must NOT be banked as a
        # null. A degenerate candidate is neither SHIP nor a trustworthy null — it's INVALID.
        cand_std = _candidate_eval_std(df.loc[common], extra_by_name[name])
        cand_cov = _candidate_eval_coverage(df.loc[common], extra_by_name[name])
        degenerate, degen_reason = candidate_is_degenerate(
            cand_std, by["all"]["lift"], dsr, cand_coverage=cand_cov)
        ship = bool(lift_pos and pbo.clears_live_pbo and dsr_ok and not degenerate)
        results["candidates"][name] = {
            "extra_cols": extra_by_name[name],
            "candidate_eval_std": cand_std,
            "candidate_eval_coverage": cand_cov,
            "lift": by,
            "dsr": (None if dsr is None else
                    {"dsr": dsr.dsr, "observed_sr": dsr.observed_sr, "sr0": dsr.sr0,
                     "n_trials": dsr.n_trials, "n_obs": dsr.n_obs,
                     "passes_live": dsr.passes_live, "threshold": DSR_CONFIDENCE}),
            "orthogonality": orth,
            "degenerate": degenerate,
            "degenerate_reason": degen_reason,
            "gate": {"lift_positive_all_and_noncold": lift_pos,
                     "pbo_clears_live": pbo.clears_live_pbo, "dsr_passes_live": dsr_ok,
                     "not_degenerate": not degenerate,
                     "SHIP": ship},
            "verdict": ("INVALID (degenerate — re-check the feature build, NOT a null)" if degenerate
                        else "SHIP" if ship else "NO-SHIP (record null)"),
        }
    return results


# ════════════════════════════════════════════════════════════════════════════
#  Reporting
# ════════════════════════════════════════════════════════════════════════════

def _print_report(res: dict) -> None:
    print("\n" + "=" * 78)
    print(f"E13.4 INCREMENTAL-LIFT — {res['target']} (metric={res['metric']}, "
          f"n_eval={res['n_eval']})")
    print("=" * 78)
    p = res["pbo"]
    print(f"  PBO (over {p['n_configs']} configs, {p['n_slices']} slices, {p['n_combos']} combos) "
          f"= {p['pbo']:.3f}  → clears_live(<{p['threshold']}) = {p['clears_live']}")
    for name, c in res["candidates"].items():
        _cov = c.get("candidate_eval_coverage")
        print(f"\n  ── candidate '{name}'  (+{c['extra_cols']})  "
              f"[eval std={c.get('candidate_eval_std')}, "
              f"eval coverage={'n/a' if _cov is None else f'{_cov:.1%}'}]")
        if c.get("degenerate"):
            print(f"    🛑 DEGENERATE — {c['degenerate_reason']}")
            print(f"       This is INVALID, not a null. Re-check the feature build/coverage "
                  f"before reading any verdict.")
        print(f"    {'stratum':<16}{'n':>7}{'base':>11}{'cand':>11}{'lift':>11}{'lift%':>9}")
        for st, d in c["lift"].items():
            print(f"    {st:<16}{d['n']:>7}{d['base_metric']:>11.4f}{d['cand_metric']:>11.4f}"
                  f"{d['lift']:>+11.4f}{d['lift_pct']:>+8.2%}")
        if c["dsr"]:
            d = c["dsr"]
            print(f"    DSR = {d['dsr']:.3f} (SR={d['observed_sr']:+.3f} vs SR0={d['sr0']:+.3f}, "
                  f"trials={d['n_trials']}) → passes_live(≥{d['threshold']}) = {d['passes_live']}")
        else:
            print("    DSR = n/a (zero-variance or too-few improvement obs)")
        for cc, o in c["orthogonality"].items():
            if o.get("max_abs_corr") is not None:
                print(f"    orthogonality {cc}: max|corr|={o['max_abs_corr']:.3f} vs {o['vs']}")
            else:
                print(f"    orthogonality {cc}: {o.get('note','n/a')}")
        g = c["gate"]
        print(f"    GATE → lift>0(all&non-cold)={g['lift_positive_all_and_noncold']}  "
              f"PBO<{PBO_SHADOW_TO_LIVE}={g['pbo_clears_live']}  DSR≥{DSR_CONFIDENCE}="
              f"{g['dsr_passes_live']}  not_degenerate={g['not_degenerate']}  ⇒  "
              f"{'🛑 ' + c['verdict'] if c.get('degenerate') else ('SHIP ✅' if g['SHIP'] else 'NO-SHIP (record null)')}")


def main() -> None:
    ap = argparse.ArgumentParser(description="E13.4 incremental-lift harness")
    ap.add_argument("--target", required=True,
                    choices=["perside_runs", "home_win", "run_diff", "total_runs"])
    ap.add_argument("--add-features", default="",
                    help="Comma-separated candidate column(s) to add to the champion/E2.1 base "
                         "contract. For perside_runs these must be off_*/opp_* bases present in "
                         "the wide mart.")
    ap.add_argument("--sanity", action="store_true",
                    help="Inject a pure-noise candidate (expect ~0 lift, high PBO) and an "
                         "in-contract-duplicate candidate (expect ~0 incremental lift) to "
                         "VALIDATE the harness before trusting a real verdict.")
    ap.add_argument("--metric", default=None,
                    help="Per-game LOSS metric. perside_runs: crps (default) or nll. champions: "
                         "nll (=logloss, home_win default) / mae (run_diff,total_runs default) / crps.")
    ap.add_argument("--embargo-days", type=int, default=3)
    ap.add_argument("--min-year", type=int, default=2021)
    ap.add_argument("--n-slices", type=int, default=16,
                    help="Time slices for the PBO performance matrix (AFML CSCV partitions).")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--run-name", default=None,
                    help="Output basename → ablation_results/<run-name>_<target>_lift.json")
    ap.add_argument("--feature-parquet", default=None,
                    help="Opt-in: a game_pk-keyed parquet of candidate column(s) built OUTSIDE "
                         "Snowflake (e.g. the E13.10 lakehouse zone-overlap feature) to left-join "
                         "before evaluation. Default None ⇒ Snowflake-only (unchanged).")
    args = ap.parse_args()

    add = [c.strip() for c in args.add_features.split(",") if c.strip()]
    configs = _build_configs(add, args.sanity)

    if args.target == "perside_runs":
        metric = args.metric or "crps"
        res = _perside_backend(configs, metric=metric, embargo_days=args.embargo_days,
                               min_year=args.min_year, n_slices=args.n_slices, seed=args.seed,
                               feature_parquet=args.feature_parquet)
    else:
        metric = args.metric or _CHAMP_METRIC[args.target]
        res = _champion_backend(args.target, configs, metric=metric,
                                embargo_days=args.embargo_days, min_year=args.min_year,
                                n_slices=args.n_slices, seed=args.seed,
                                feature_parquet=args.feature_parquet)

    _print_report(res)

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    base = args.run_name or ("sanity" if args.sanity and not add else "lift")
    out = _RESULTS_DIR / f"{base}_{args.target}_lift.json"
    out.write_text(json.dumps(res, indent=2, default=float))
    print(f"\nWrote {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
