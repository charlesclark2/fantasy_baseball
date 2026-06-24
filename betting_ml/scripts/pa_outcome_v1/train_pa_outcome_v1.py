"""
train_pa_outcome_v1.py — E13.2 Phase 1: PA-outcome multiclass model.

Trains a LightGBM multiclass classifier on `mart_pa_outcome_substrate` (the
lakehouse PA-grain substrate, ~1.96M regular-season PAs 2015-2025) to predict
P(outcome) over the 10 classes {1B,2B,3B,HR,BB,IBB,HBP,K,out,other}. This is the
PA-outcome engine the Phase-2 Monte-Carlo game simulator chains through innings.

LEAKAGE: features are the substrate's entering-state (base_out_state, score-diff,
inning, platoon, times-thru-order, …) plus LEAK-SAFE point-in-time batter/pitcher
prior-rate profiles from features_pa_outcome.build_pit_features (as-of < game_date).
CV is PurgedWalkForwardSplit (season walk-forward + purge/embargo).

The model is judged against TWO no-skill baselines on held-out folds:
  1. marginal prior     — predict the train-set class frequencies for every PA
                          (the ~1.507-nat floor from Phase 0).
  2. log5 matchup prior — combine the batter & pitcher EB rate vectors by the
                          Bill-James/log5 odds rule p_c ∝ bat_c·pit_c/league_c.
                          This is the "did LEARNING beat naive odds-combination of
                          the priors the model already has as features" test.
A model that does not beat the log5 baseline by a meaningful margin has not earned
its complexity (champion-delta discipline; search-baseline-misleading memory).

Cost posture: reads the lakehouse via duckdb/S3 (credential_chain); no Snowflake.
Heavy fit → operator/runner (>1 min). Research phase — writes a CV dossier to
ablation_results and pushes the fitted model to S3 for Phase 2; NO serving-registry
promotion (that is a later, separate, careful step per the story).

Usage:
    uv run python betting_ml/scripts/pa_outcome_v1/train_pa_outcome_v1.py --smoke
    uv run python betting_ml/scripts/pa_outcome_v1/train_pa_outcome_v1.py
    uv run python betting_ml/scripts/pa_outcome_v1/train_pa_outcome_v1.py --no-promote
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="X does not have valid feature names", category=UserWarning)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.cv import make_purged_splitter  # noqa: E402
from betting_ml.utils.artifact_store import upload_artifact  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features_pa_outcome import CLASSES, STATIC_LEAGUE_PRIOR, build_pit_features  # noqa: E402

# Load run_w1_lakehouse.extract_duckdb_sql (the canonical duckdb-branch SQL parser)
# without requiring scripts/ to be a package.
_rwl_spec = importlib.util.spec_from_file_location(
    "run_w1_lakehouse", _PROJECT_ROOT / "scripts" / "run_w1_lakehouse.py"
)
_rwl = importlib.util.module_from_spec(_rwl_spec)
_rwl_spec.loader.exec_module(_rwl)

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"
_OUTPUT_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "pa_outcome_v1"

_EXCLUDE_EVAL_YEAR = 2026  # partial season — excluded from CV folds

# nll noise floor from betting_ml.utils.promotion_gate.NOISE_FLOOR["nll"]. The gate:
# the model must beat the log5 matchup baseline by AT LEAST this (mean) to count as a
# real, above-noise lift — a positive-but-sub-floor delta is "matches log5".
_NLL_NOISE_FLOOR = 0.01

# Entering-state features straight off the substrate.
_CAT_FEATURES = ["base_out_state", "platoon_matchup", "inning_half", "batter_hand", "pitcher_hand"]
_NUM_FEATURES = [
    "inning", "outs_at_entry", "entry_bat_score_diff",
    "runner_on_1b", "runner_on_2b", "runner_on_3b",
    "pitcher_times_thru_order_at_entry", "batter_prior_pas_this_game",
]

# num_class is inferred by the LGBMClassifier wrapper from the label set — passing
# it explicitly alongside the wrapper can conflict, so we omit it.
_LGBM_PARAMS = dict(
    objective="multiclass", metric="multi_logloss",
    n_estimators=600, learning_rate=0.05, num_leaves=63, min_child_samples=200,
    subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1, verbose=-1,
)


# ── Data load ───────────────────────────────────────────────────────────────

def load_substrate(smoke: bool) -> pd.DataFrame:
    """Build the substrate from the lakehouse: register stg_batter_pitches from S3,
    run the substrate model's duckdb-branch SQL, return regular-season PAs."""
    import duckdb

    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute(
        "CREATE OR REPLACE SECRET baseball_s3 (TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')"
    )
    stg_sql = _rwl.extract_duckdb_sql("stg_batter_pitches")
    conn.execute(f"CREATE OR REPLACE VIEW stg_batter_pitches AS {stg_sql}")
    substrate_sql = _rwl.extract_duckdb_sql("mart_pa_outcome_substrate")
    print("Building substrate from lakehouse stg_batter_pitches …")
    df = conn.execute(f"SELECT * FROM ({substrate_sql}) t WHERE game_type = 'R'").df()
    conn.close()

    df = df.sort_values(["game_date", "game_pk", "at_bat_number"]).reset_index(drop=True)
    if smoke:
        # Keep whole seasons so walk-forward CV still has ≥3 train seasons.
        keep = df["game_year"].isin([2015, 2016, 2017, 2018, 2019])
        df = df[keep].reset_index(drop=True)
    print(f"  substrate: {len(df):,} R-season PAs  "
          f"({int(df['game_year'].min())}–{int(df['game_year'].max())})")
    return df


# ── Feature assembly ──────────────────────────────────────────────────────────

def assemble(df: pd.DataFrame, include_splits: bool) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Attach PIT features, coerce types, return (df, feature_cols, pit_cols)."""
    df, pit_cols = build_pit_features(df, include_splits=include_splits)
    for c in ("runner_on_1b", "runner_on_2b", "runner_on_3b"):
        df[c] = df[c].astype(float)
    for c in _CAT_FEATURES:
        df[c] = df[c].astype("category")
    df["y"] = pd.Categorical(df["pa_outcome_label"], categories=CLASSES).codes  # 0..9
    feature_cols = _CAT_FEATURES + _NUM_FEATURES + pit_cols
    return df, feature_cols, pit_cols


# ── Baselines ─────────────────────────────────────────────────────────────────

def _marginal_probs(y_train: np.ndarray, n_eval: int) -> np.ndarray:
    counts = np.bincount(y_train, minlength=len(CLASSES)).astype(float)
    p = counts / counts.sum()
    return np.tile(p, (n_eval, 1))


def _log5_probs(eval_df: pd.DataFrame) -> np.ndarray:
    """log5 / Bill-James odds combination of the batter & pitcher EB priors:
    p_c ∝ bat_c · pit_c / league_c, normalized per row."""
    lg = np.array([STATIC_LEAGUE_PRIOR[c] for c in CLASSES])
    bat = eval_df[[f"bat_eb_{c}" for c in CLASSES]].to_numpy(dtype=float)
    pit = eval_df[[f"pit_eb_{c}" for c in CLASSES]].to_numpy(dtype=float)
    raw = bat * pit / lg[None, :]
    return raw / raw.sum(axis=1, keepdims=True)


def _full_probs(model, X) -> np.ndarray:
    """Map LGBMClassifier.predict_proba (over model.classes_) into a fixed (n, 10)
    matrix in CLASSES order, floored + renormalized — robust if a train fold is
    missing a rare class (IBB/other)."""
    p = model.predict_proba(X)
    full = np.full((p.shape[0], len(CLASSES)), 1e-9)
    for j, cls in enumerate(model.classes_):
        full[:, int(cls)] = p[:, j]
    return full / full.sum(axis=1, keepdims=True)


def _logloss(y_true: np.ndarray, probs: np.ndarray) -> float:
    from sklearn.metrics import log_loss
    return float(log_loss(y_true, probs, labels=list(range(len(CLASSES)))))


# Pre-registered regime boundary: 2023 MLB rule changes (shift ban, bigger bases,
# pitch clock) — an EXTERNALLY-motivated breakpoint fixed before looking at results,
# so it cannot be tuned to maximize the delta.
_REGIME_BOUNDARY = 2023


def regime_split_eval(pa: pd.DataFrame, boundary: int = _REGIME_BOUNDARY,
                      n_boot: int = 2000, seed: int = 42) -> dict:
    """Game-clustered block bootstrap of the per-PA paired log-loss diff
    d = nll_log5 − nll_model (positive ⇒ model better), split at the 2023 rule
    boundary. Resampling whole GAMES (not PAs) respects within-game correlation.
    Returns per-regime {mean, ci_lo, ci_hi, n_pa, n_games} (95% CI)."""
    rng = np.random.default_rng(seed)
    out = {}
    for name, mask in (("pre_2023", pa["eval_year"] < boundary),
                       ("2023_plus", pa["eval_year"] >= boundary)):
        sub = pa[mask]
        if len(sub) == 0:
            out[name] = {"mean": None, "ci_lo": None, "ci_hi": None, "n_pa": 0, "n_games": 0}
            continue
        gb = sub.groupby("game_pk")["d"].agg(["sum", "count"])
        sums = gb["sum"].to_numpy(); cnts = gb["count"].to_numpy()
        idx = np.arange(len(gb))
        boots = np.empty(n_boot)
        for b in range(n_boot):
            s = rng.choice(idx, size=len(idx), replace=True)
            boots[b] = sums[s].sum() / cnts[s].sum()
        lo, hi = np.percentile(boots, [2.5, 97.5])
        out[name] = {"mean": round(float(sub["d"].mean()), 5),
                     "ci_lo": round(float(lo), 5), "ci_hi": round(float(hi), 5),
                     "n_pa": int(len(sub)), "n_games": int(len(gb))}
    return out


def per_class_reliability(y_true: np.ndarray, probs: np.ndarray, n_bins: int = 10) -> dict:
    """Per-class expected calibration error (ECE) on the pooled held-out predictions.
    The sim propagates the FULL distribution, so each class's probability must be
    calibrated — not just the argmax. ECE_c = Σ_bins |mean_pred − obs_freq|·(n_bin/N)."""
    out = {}
    for k, c in enumerate(CLASSES):
        p = probs[:, k]
        actual = (y_true == k).astype(float)
        b = np.clip((p * n_bins).astype(int), 0, n_bins - 1)
        ece = 0.0
        for bi in range(n_bins):
            m = b == bi
            if m.any():
                ece += abs(p[m].mean() - actual[m].mean()) * m.sum()
        out[c] = round(ece / len(p), 5)
    out["mean"] = round(float(np.mean([out[c] for c in CLASSES])), 5)
    return out


# ── CV ────────────────────────────────────────────────────────────────────────

def run_cv(df: pd.DataFrame, feature_cols: list[str]) -> list[dict]:
    import lightgbm as lgb

    cv_df = df[df["game_year"] != _EXCLUDE_EVAL_YEAR].reset_index(drop=True)
    _, splitter = make_purged_splitter(feature_cols=feature_cols, embargo_days=3)
    folds = list(splitter(cv_df))

    recs: list[dict] = []
    pooled_y: list[np.ndarray] = []
    pooled_p: list[np.ndarray] = []
    pa_gpk: list[np.ndarray] = []
    pa_year: list[np.ndarray] = []
    pa_d: list[np.ndarray] = []
    print(f"\n── PA-outcome walk-forward CV ({len(folds)} folds) ──")
    print(f"  {'eval':>6}  {'n_train':>9}  {'n_eval':>8}  {'model':>7}  {'log5':>7}  {'marg':>7}  {'Δ vs log5':>9}")
    for tr, ev in folds:
        eval_year = int(cv_df.loc[ev, "game_year"].mode().iloc[0])
        Xtr, ytr = cv_df.loc[tr, feature_cols], cv_df.loc[tr, "y"].to_numpy()
        Xev, yev = cv_df.loc[ev, feature_cols], cv_df.loc[ev, "y"].to_numpy()

        model = lgb.LGBMClassifier(**_LGBM_PARAMS)
        model.fit(Xtr, ytr, categorical_feature=_CAT_FEATURES)
        model_probs = _full_probs(model, Xev)
        pooled_y.append(yev)
        pooled_p.append(model_probs)

        log5_probs = _log5_probs(cv_df.loc[ev])
        ll_model = _logloss(yev, model_probs)
        ll_log5 = _logloss(yev, log5_probs)
        ll_marg = _logloss(yev, _marginal_probs(ytr, len(yev)))

        # Per-PA paired log-loss diff (nll_log5 − nll_model; + ⇒ model better) for the
        # pre-registered regime-split bootstrap.
        ar = np.arange(len(yev))
        nll_m = -np.log(np.clip(model_probs[ar, yev], 1e-12, 1.0))
        nll_5 = -np.log(np.clip(log5_probs[ar, yev], 1e-12, 1.0))
        pa_gpk.append(cv_df.loc[ev, "game_pk"].to_numpy())
        pa_year.append(np.full(len(yev), eval_year))
        pa_d.append(nll_5 - nll_m)

        recs.append({
            "eval_year": eval_year, "n_train": int(len(tr)), "n_eval": int(len(ev)),
            "logloss_model": round(ll_model, 5), "logloss_log5": round(ll_log5, 5),
            "logloss_marginal": round(ll_marg, 5),
            "delta_vs_log5": round(ll_log5 - ll_model, 5),
            "delta_vs_marginal": round(ll_marg - ll_model, 5),
        })
        print(f"  {eval_year:>6}  {len(tr):>9,}  {len(ev):>8,}  "
              f"{ll_model:>7.4f}  {ll_log5:>7.4f}  {ll_marg:>7.4f}  {ll_log5 - ll_model:>+9.4f}")
    reliability = per_class_reliability(np.concatenate(pooled_y), np.concatenate(pooled_p))
    pa = pd.DataFrame({"game_pk": np.concatenate(pa_gpk),
                       "eval_year": np.concatenate(pa_year),
                       "d": np.concatenate(pa_d)})
    regime = regime_split_eval(pa)
    return recs, reliability, regime


def summarize(recs: list[dict]) -> dict:
    mean = lambda k: float(np.mean([r[k] for r in recs]))  # noqa: E731
    out = {
        "mean_logloss_model": round(mean("logloss_model"), 5),
        "mean_logloss_log5": round(mean("logloss_log5"), 5),
        "mean_logloss_marginal": round(mean("logloss_marginal"), 5),
        "mean_delta_vs_log5": round(mean("delta_vs_log5"), 5),
        "mean_delta_vs_marginal": round(mean("delta_vs_marginal"), 5),
    }
    out["beats_log5_all_folds"] = all(r["delta_vs_log5"] > 0 for r in recs)
    out["beats_marginal_all_folds"] = all(r["delta_vs_marginal"] > 0 for r in recs)
    # THE GATE: mean lift over log5 must clear the nll noise floor to count as real.
    out["nll_noise_floor"] = _NLL_NOISE_FLOOR
    out["clears_noise_floor_vs_log5"] = out["mean_delta_vs_log5"] >= _NLL_NOISE_FLOOR
    return out


# ── Final fit + persistence ─────────────────────────────────────────────────

def fit_final(df: pd.DataFrame, feature_cols: list[str]):
    import lightgbm as lgb
    train = df[df["game_year"] != _EXCLUDE_EVAL_YEAR]
    model = lgb.LGBMClassifier(**_LGBM_PARAMS)
    model.fit(train[feature_cols], train["y"].to_numpy(), categorical_feature=_CAT_FEATURES)
    return model


def write_report(summary: dict, recs: list[dict], reliability: dict, regime: dict,
                 meta: dict, stem: str) -> None:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"story": "E13.2", "phase": 1, "model": meta["feature_set"],
               "classes": CLASSES, **meta, "summary": summary,
               "reliability_ece": reliability, "regime_split": regime, "folds": recs}
    (_REPORT_DIR / f"{stem}_cv.json").write_text(json.dumps(payload, indent=2, default=float))

    # THE GATE verdict (clears noise floor over log5 → proceed to Phase 2 sim).
    if summary["clears_noise_floor_vs_log5"]:
        gate = (f"GATE PASS — model beats log5 by {summary['mean_delta_vs_log5']:+.4f} nats "
                f"(≥ {summary['nll_noise_floor']} noise floor): the split signal lifts PA prediction "
                f"above naive odds-combination → proceed to Phase 2 sim.")
    else:
        gate = (f"GATE FAIL — model beats log5 by only {summary['mean_delta_vs_log5']:+.4f} nats "
                f"(< {summary['nll_noise_floor']} noise floor): the proven split signal does NOT lift "
                f"PA-outcome prediction over log5 on our data → log5 is near-optimal here. "
                f"Next decision is B (sim for product/distribution value only) vs C (pause).")
    md = [
        f"# E13.2 Phase 1 — PA-outcome multiclass CV — feature set {meta['feature_set']} ({date.today()})",
        "",
        f"- Substrate: {meta['n_pa']:,} R-season PAs, {meta['n_features']} features "
        f"({len(_CAT_FEATURES)} categorical + {len(_NUM_FEATURES)} entering-state + "
        f"{meta['n_pit']} point-in-time).",
        f"- No-skill marginal-prior floor (Phase 0): 1.5074 nats. nll noise floor: {summary['nll_noise_floor']}.",
        "",
        "## CV mean multiclass log-loss (lower = better)",
        f"- **model**:    {summary['mean_logloss_model']:.4f}",
        f"- log5 prior:   {summary['mean_logloss_log5']:.4f}  (Δ model {summary['mean_delta_vs_log5']:+.4f})",
        f"- marginal:     {summary['mean_logloss_marginal']:.4f}  (Δ model {summary['mean_delta_vs_marginal']:+.4f})",
        "",
        f"**{gate}**",
        f"(beats log5 all folds: {summary['beats_log5_all_folds']}; "
        f"beats marginal all folds: {summary['beats_marginal_all_folds']})",
        "",
        f"## Per-class calibration (ECE, pooled held-out — lower = better)",
        f"- mean ECE: {reliability['mean']:.4f}",
        "  " + " · ".join(f"{c} {reliability[c]:.4f}" for c in CLASSES),
        "",
        f"## Pre-registered regime split @ {meta['regime_boundary']} (2023 rule changes)",
        "Δ vs log5 (game-clustered block bootstrap, 95% CI). Decision rule fixed before "
        "the result: a real regime-specific edge requires the 2023+ lift to clear the noise "
        "floor with a CI excluding both 0 and the pre-2023 estimate.",
        f"- pre-2023 : {regime['pre_2023']['mean']:+.4f}  "
        f"[{regime['pre_2023']['ci_lo']:+.4f}, {regime['pre_2023']['ci_hi']:+.4f}]  "
        f"({regime['pre_2023']['n_pa']:,} PA, {regime['pre_2023']['n_games']:,} games)",
        f"- 2023+    : {regime['2023_plus']['mean']:+.4f}  "
        f"[{regime['2023_plus']['ci_lo']:+.4f}, {regime['2023_plus']['ci_hi']:+.4f}]  "
        f"({regime['2023_plus']['n_pa']:,} PA, {regime['2023_plus']['n_games']:,} games)",
        f"- **Regime verdict:** "
        f"{'REGIME-SPECIFIC EDGE — revisit Phase 2 on the post-2023 regime' if meta['regime_edge_2023plus'] else 'NULL — 2023+ lift does not clear the floor with a clean CI → log5 near-optimal; no rule-change edge → proceed to C (pause, preserve the calibrated PA asset)'}**",
        "",
        "## Per-fold",
        "| eval | n_train | n_eval | model | log5 | marginal | Δ vs log5 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in recs:
        md.append(f"| {r['eval_year']} | {r['n_train']:,} | {r['n_eval']:,} | "
                  f"{r['logloss_model']:.4f} | {r['logloss_log5']:.4f} | "
                  f"{r['logloss_marginal']:.4f} | {r['delta_vs_log5']:+.4f} |")
    (_REPORT_DIR / f"{stem}_cv.md").write_text("\n".join(md))
    print(f"\nWrote {_REPORT_DIR / f'{stem}_cv.md'}")


def save_artifact(model, feature_cols, pit_cols, summary, reliability, feature_set, promote) -> Path:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    import joblib
    local = _OUTPUT_DIR / f"pa_outcome_{feature_set}.pkl"
    joblib.dump({
        "model": model, "classes": CLASSES, "feature_cols": feature_cols,
        "cat_features": _CAT_FEATURES, "pit_cols": pit_cols, "feature_set": feature_set,
        "cv_summary": summary, "reliability_ece": reliability, "lgbm_params": _LGBM_PARAMS,
    }, local)
    print(f"  Saved → {local.relative_to(_PROJECT_ROOT)}")
    if promote:
        upload_artifact(local, f"s3://baseball-betting-ml-artifacts/sub_models/pa_outcome_{feature_set}.pkl")
    else:
        print("  [--no-promote] skipping S3 upload")
    return local


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smoke", action="store_true", help="2015-2019 only (fast sanity run)")
    ap.add_argument("--no-promote", action="store_true", help="skip S3 artifact upload")
    ap.add_argument("--no-splits", action="store_true",
                    help="overall EB rates only (reproduces the v1 feature set; default adds v2 splits)")
    args = ap.parse_args()

    include_splits = not args.no_splits
    feature_set = "v1" if args.no_splits else "v2"
    stem = f"e13_2_pa_outcome_{feature_set}"

    print(f"=== E13.2 Phase 1 — PA-outcome multiclass (feature set {feature_set}) ===")
    df = load_substrate(smoke=args.smoke)
    df, feature_cols, pit_cols = assemble(df, include_splits=include_splits)
    print(f"  features: {len(feature_cols)} "
          f"({len(_CAT_FEATURES)} cat + {len(_NUM_FEATURES)} num + {len(pit_cols)} PIT)")

    recs, reliability, regime = run_cv(df, feature_cols)
    summary = summarize(recs)
    print(f"\n  mean log-loss — model {summary['mean_logloss_model']:.4f} | "
          f"log5 {summary['mean_logloss_log5']:.4f} | marginal {summary['mean_logloss_marginal']:.4f}")
    print(f"  Δ vs log5: {summary['mean_delta_vs_log5']:+.4f} "
          f"({'CLEARS' if summary['clears_noise_floor_vs_log5'] else 'below'} the "
          f"{summary['nll_noise_floor']} noise floor)  |  mean per-class ECE: {reliability['mean']:.4f}")

    # Pre-registered regime split at the 2023 rule-change boundary.
    pre, post = regime["pre_2023"], regime["2023_plus"]
    floor = summary["nll_noise_floor"]
    regime_edge = (post["mean"] >= floor and post["ci_lo"] > 0 and post["ci_lo"] > pre["mean"])
    print(f"\n  ── regime split @ {_REGIME_BOUNDARY} (Δ vs log5, game-clustered 95% CI) ──")
    print(f"    pre-2023 : {pre['mean']:+.4f}  [{pre['ci_lo']:+.4f}, {pre['ci_hi']:+.4f}]  "
          f"({pre['n_pa']:,} PA)")
    print(f"    2023+    : {post['mean']:+.4f}  [{post['ci_lo']:+.4f}, {post['ci_hi']:+.4f}]  "
          f"({post['n_pa']:,} PA)")
    print(f"    pre-registered verdict: {'REGIME-SPECIFIC EDGE (revisit Phase 2 post-2023)' if regime_edge else 'NULL — proceed to C (log5 near-optimal, no rule-change edge)'}")

    meta = {"feature_set": feature_set, "n_pa": int(len(df)), "n_features": len(feature_cols),
            "n_pit": len(pit_cols), "kappa": 100.0, "kappa_split": 200.0,
            "regime_boundary": _REGIME_BOUNDARY, "regime_edge_2023plus": bool(regime_edge)}
    write_report(summary, recs, reliability, regime, meta, stem)

    print("\n── Fitting final model on completed seasons ──")
    model = fit_final(df, feature_cols)
    save_artifact(model, feature_cols, pit_cols, summary, reliability, feature_set,
                  promote=not args.no_promote)
    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
