"""
ablation_eb_bullpen_distributional.py — Epic 6D.5

Retrospective EB ablation within the NegBin distributional framework.

Question: does including EB bullpen posteriors (eb_bullpen_xwoba,
eb_bullpen_uncertainty, eb_bullpen_coverage_pct) improve distributional
quality vs. raw rolling stats alone?

Compares walk-forward CV (same fold structure as the bullpen_v2 champion) on:
    champion (24 features, EB included) — loaded from bullpen_v2.pkl
    no-eb    (21 features, EB excluded) — re-run here with default LightGBM params

Metrics compared:
    - Mean CV NLL (primary)
    - Mean CV calib_80
    - High-fatigue subset NLL (fatigue_score > 0.7 rows)
    - Mean NegBin r

No Optuna tuning in this script (retrospective ablation; default params suffice
to measure signal value, not architecture).  For a fair comparison, the
champion's pre-tuning NLL (cand_a_cv_nll) is used as the reference, not
tuned_cv_nll.

Outputs:
    betting_ml/models/sub_models/bullpen_v2/ablation_eb_bullpen_{ts}.json
    quant_sports_intel_models/baseball/clv_monitoring_log.md  (appended)

Usage:
    uv run python betting_ml/scripts/ablation_eb_bullpen_distributional.py
    uv run python betting_ml/scripts/ablation_eb_bullpen_distributional.py --min-year 2021
    uv run python betting_ml/scripts/ablation_eb_bullpen_distributional.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import gammaln
from scipy.stats import nbinom

warnings.filterwarnings("ignore", message="X does not have valid feature names",
                        category=UserWarning, module="sklearn")
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy connectable",
                        category=UserWarning)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection

_PARQUET_PATH  = _PROJECT_ROOT / "betting_ml" / "data" / "bullpen_state_train.parquet"
_ARTIFACT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "bullpen_v2.pkl"
_OUTPUT_DIR    = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "bullpen_v2"
_CLV_LOG_PATH  = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "clv_monitoring_log.md"

_TARGET_COL      = "bullpen_runs_allowed"
_YEAR_COL        = "game_year"
_MIN_YEAR_DEFAULT = 2021
_FATIGUE_THRESH  = 0.7
_MIN_R           = 1e-3

# Champion feature set (24 features — same as bullpen_v2)
_FEATURE_COLS_ALL = [
    "eb_bullpen_xwoba",
    "eb_bullpen_uncertainty",
    "eb_bullpen_coverage_pct",
    "xwoba_against_14d",
    "k_pct_14d",
    "bb_pct_14d",
    "hard_hit_pct_14d",
    "whiff_rate_14d",
    "innings_pitched_14d",
    "xwoba_against_30d",
    "k_pct_30d",
    "bb_pct_30d",
    "hard_hit_pct_30d",
    "whiff_rate_30d",
    "innings_pitched_30d",
    "availability_index",
    "bullpen_ip_prev_1d",
    "bullpen_ip_prev_2d",
    "bullpen_ip_prev_3d",
    "pitchers_used_prev_3d",
    "pitchers_used_prev_7d",
    "reliever_appearances_prev_3d",
    "high_leverage_used_prev_2d",
    "closer_used_prev_1d",
]

# EB features being ablated (3 features)
_EB_FEATURES = {"eb_bullpen_xwoba", "eb_bullpen_uncertainty", "eb_bullpen_coverage_pct"}

# Raw rolling only (21 features)
_FEATURE_COLS_NO_EB = [f for f in _FEATURE_COLS_ALL if f not in _EB_FEATURES]


# ── Snowflake target fetch ─────────────────────────────────────────────────────

_RUNS_QUERY = """
WITH game_scores AS (
    SELECT
        game_pk,
        game_year,
        home_team,
        away_team,
        home_final_score,
        away_final_score,
        ABS(home_final_score - away_final_score) AS score_delta
    FROM baseball_data.betting.mart_game_results
    WHERE game_year >= {min_year}
      AND game_type = 'R'
),
team_scores AS (
    SELECT game_pk, game_year, home_team AS pitching_team,
           away_final_score AS total_runs_allowed, score_delta FROM game_scores
    UNION ALL
    SELECT game_pk, game_year, away_team AS pitching_team,
           home_final_score AS total_runs_allowed, score_delta FROM game_scores
),
starter_runs AS (
    SELECT game_pk, pitching_team,
           COALESCE(runs_allowed, 0) AS starter_runs_allowed
    FROM baseball_data.betting.mart_starting_pitcher_game_log
    WHERE game_year >= {min_year}
)
SELECT
    t.game_pk,
    t.game_year,
    t.pitching_team,
    GREATEST(t.total_runs_allowed - COALESCE(s.starter_runs_allowed, 0), 0) AS bullpen_runs_allowed
FROM team_scores t
LEFT JOIN starter_runs s
    ON s.game_pk = t.game_pk AND s.pitching_team = t.pitching_team
ORDER BY t.game_pk, t.pitching_team
"""


def _fetch_bullpen_runs(min_year: int) -> pd.DataFrame:
    conn = get_snowflake_connection()
    df = pd.read_sql(_RUNS_QUERY.format(min_year=min_year), conn)
    conn.close()
    df.columns = [c.lower() for c in df.columns]
    return df


def _load_data(min_year: int) -> pd.DataFrame:
    if not _PARQUET_PATH.exists():
        print(f"ERROR: {_PARQUET_PATH} not found. Run build_bullpen_state_dataset.py first.")
        sys.exit(1)

    parquet_df = pd.read_parquet(_PARQUET_PATH)
    parquet_df = parquet_df[parquet_df[_YEAR_COL] >= min_year].copy()
    for col in _FEATURE_COLS_ALL:
        if col in parquet_df.columns:
            parquet_df[col] = pd.to_numeric(parquet_df[col], errors="coerce")

    runs_df = _fetch_bullpen_runs(min_year)
    df = parquet_df.merge(
        runs_df[["game_pk", "pitching_team", "bullpen_runs_allowed"]],
        on=["game_pk", "pitching_team"], how="inner",
    )
    df = df.dropna(subset=[_TARGET_COL]).reset_index(drop=True)
    df[_TARGET_COL] = df[_TARGET_COL].astype(float)
    print(f"  Dataset: {len(df):,} rows | {df[_YEAR_COL].nunique()} seasons "
          f"[{int(df[_YEAR_COL].min())}–{int(df[_YEAR_COL].max())}]")
    return df


# ── NegBin utilities ───────────────────────────────────────────────────────────

def _negbin_logpmf(y: np.ndarray, mu: np.ndarray | float, r: float) -> np.ndarray:
    r = max(float(r), _MIN_R)
    mu = np.clip(mu, 1e-6, None)
    p = r / (r + mu)
    return (gammaln(r + y) - gammaln(r) - gammaln(y + 1)
            + r * np.log(p) + y * np.log(1.0 - p))


def _negbin_nll(y: np.ndarray, mu: np.ndarray | float, r: float) -> float:
    return float(-_negbin_logpmf(y, mu, r).mean())


def _negbin_calib_80(y: np.ndarray, mu: np.ndarray | float, r: float) -> float:
    r = max(float(r), _MIN_R)
    mu = np.clip(np.asarray(mu, dtype=float), 1e-6, None)
    p = r / (r + mu)
    lo = nbinom.ppf(0.10, n=r, p=p).astype(float)
    hi = nbinom.ppf(0.90, n=r, p=p).astype(float)
    return float(((y >= lo) & (y <= hi)).mean())


def _fit_negbin_r(y: np.ndarray, mu: np.ndarray) -> float:
    def neg_ll(log_r: float) -> float:
        return _negbin_nll(y, mu, np.exp(log_r))
    result = minimize_scalar(neg_ll, bounds=(-3.0, 6.0), method="bounded")
    return float(np.exp(result.x))


# ── Walk-forward CV ────────────────────────────────────────────────────────────

def _run_cv(
    df: pd.DataFrame,
    feature_cols: list[str],
    label: str,
    n_estimators: int = 500,
    learning_rate: float = 0.05,
    num_leaves: int = 31,
) -> tuple[float, float, float, float, list[dict]]:
    """Walk-forward season CV. Returns (mean_nll, mean_mae, mean_calib_80, mean_r, fold_records)."""
    from lightgbm import LGBMRegressor

    seasons = sorted(df[_YEAR_COL].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    print(f"\n  [{label}] {len(feature_cols)} features | {len(folds)} folds")

    fold_records: list[dict] = []
    for train_seasons, test_season in folds:
        tr = df[df[_YEAR_COL].isin(train_seasons)].copy()
        te = df[df[_YEAR_COL] == test_season].copy()

        impute_vals = {col: float(tr[col].median()) for col in feature_cols}
        for col in feature_cols:
            tr[col] = tr[col].fillna(impute_vals[col])
            te[col] = te[col].fillna(impute_vals[col])

        X_tr = tr[feature_cols].to_numpy(dtype=float)
        y_tr = tr[_TARGET_COL].to_numpy(dtype=float)
        X_te = te[feature_cols].to_numpy(dtype=float)
        y_te = te[_TARGET_COL].to_numpy(dtype=float)

        lgb = LGBMRegressor(
            n_estimators=n_estimators, learning_rate=learning_rate,
            num_leaves=num_leaves, random_state=42, verbose=-1,
        )
        lgb.fit(X_tr, y_tr)

        mu_tr = np.clip(lgb.predict(X_tr), 1e-6, None)
        mu_te = np.clip(lgb.predict(X_te), 1e-6, None)
        r = _fit_negbin_r(y_tr, mu_tr)

        nll   = _negbin_nll(y_te, mu_te, r)
        mae   = float(np.mean(np.abs(mu_te - y_te)))
        calib = _negbin_calib_80(y_te, mu_te, r)

        rec = {
            "fold":          len(fold_records) + 1,
            "train_seasons": list(map(int, train_seasons)),
            "test_season":   int(test_season),
            "n_train":       int(len(y_tr)),
            "n_test":        int(len(y_te)),
            "nll":           round(nll, 4),
            "mae":           round(mae, 4),
            "calib_80":      round(calib, 4),
            "r":             round(r, 4),
        }
        fold_records.append(rec)
        print(f"    fold {rec['fold']:>2} (test={test_season}): "
              f"NLL={nll:.4f}  MAE={mae:.4f}  calib80={calib:.4f}  r={r:.4f}")

    mean_nll   = float(np.mean([f["nll"]      for f in fold_records]))
    mean_mae   = float(np.mean([f["mae"]      for f in fold_records]))
    mean_calib = float(np.mean([f["calib_80"] for f in fold_records]))
    mean_r     = float(np.mean([f["r"]        for f in fold_records]))
    print(f"  [{label}] Mean → NLL={mean_nll:.4f}  MAE={mean_mae:.4f}  "
          f"calib80={mean_calib:.4f}  r={mean_r:.4f}")
    return mean_nll, mean_mae, mean_calib, mean_r, fold_records


# ── High-fatigue subset evaluation ────────────────────────────────────────────

def _high_fatigue_eval(
    df: pd.DataFrame,
    feature_cols: list[str],
) -> dict:
    """Fit final model on all data, evaluate high-fatigue vs rested subset NLL."""
    from lightgbm import LGBMRegressor

    df = df.copy()
    impute_vals = {col: float(df[col].median()) for col in feature_cols}
    for col in feature_cols:
        df[col] = df[col].fillna(impute_vals[col])

    X_all = df[feature_cols].to_numpy(dtype=float)
    y_all = df[_TARGET_COL].to_numpy(dtype=float)

    lgb = LGBMRegressor(n_estimators=500, learning_rate=0.05, num_leaves=31,
                        random_state=42, verbose=-1)
    lgb.fit(X_all, y_all)
    mu_all = np.clip(lgb.predict(X_all), 1e-6, None)
    r = _fit_negbin_r(y_all, mu_all)

    fatigue_col = "fatigue_score"
    if fatigue_col not in df.columns:
        return {"error": "fatigue_score column not found in parquet"}

    fatigue_mask = df[fatigue_col].fillna(0.0) > _FATIGUE_THRESH
    rest_mask    = ~fatigue_mask

    result: dict = {
        "fatigue_thresh": _FATIGUE_THRESH,
        "final_r": round(r, 4),
    }

    for label, mask in [("high_fatigue", fatigue_mask), ("rested", rest_mask)]:
        n = int(mask.sum())
        result[label] = {"n": n}
        if n >= 50:
            result[label]["nll"]      = round(_negbin_nll(y_all[mask], mu_all[mask], r), 4)
            result[label]["calib_80"] = round(_negbin_calib_80(y_all[mask], mu_all[mask], r), 4)

    return result


# ── Monitoring log append ──────────────────────────────────────────────────────

def _append_monitoring_log(summary_lines: list[str]) -> None:
    _CLV_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    header_needed = not _CLV_LOG_PATH.exists()

    with open(_CLV_LOG_PATH, "a") as fh:
        if header_needed:
            fh.write("# CLV Monitoring Log\n\n")
            fh.write("Append-only log of model ablation and CLV results.\n\n")
            fh.write("---\n\n")
        for line in summary_lines:
            fh.write(line + "\n")
        fh.write("\n")
    print(f"  Appended to {_CLV_LOG_PATH.relative_to(_PROJECT_ROOT)}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Epic 6D.5: EB ablation in distributional NegBin framework"
    )
    parser.add_argument("--min-year", type=int, default=_MIN_YEAR_DEFAULT,
                        help=f"Earliest season (default {_MIN_YEAR_DEFAULT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Load data and print shape, then exit without CV")
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    print("=" * 72)
    print("EPIC 6D.5 — EB Ablation: distributional NegBin framework")
    print(f"Champion features: {len(_FEATURE_COLS_ALL)}  |  No-EB features: {len(_FEATURE_COLS_NO_EB)}")
    print(f"EB features being ablated: {sorted(_EB_FEATURES)}")
    print("=" * 72)

    # ── Load champion baselines from pkl ──────────────────────────────────────
    if not _ARTIFACT_PATH.exists():
        print(f"ERROR: {_ARTIFACT_PATH} not found. Run train_bullpen_distributional.py first.")
        sys.exit(1)

    champion_artifact = joblib.load(_ARTIFACT_PATH)
    champ_nll     = champion_artifact.get("cand_a_cv_nll",   champion_artifact.get("cv_nll"))
    champ_calib   = champion_artifact.get("cv_calib_80",     None)
    champ_r       = champion_artifact.get("cv_mean_r",       None)
    champ_tuned   = champion_artifact.get("tuned_cv_nll",    None)
    champ_subset  = champion_artifact.get("subset_eval",     {})

    champ_hf_nll = champ_subset.get("high_fatigue", {}).get("nll") if champ_subset else None

    print(f"\nChampion (bullpen_v2, pre-tuning CV NLL): {champ_nll}")
    print(f"Champion tuned CV NLL:                     {champ_tuned}")
    print(f"Champion calib_80:                         {champ_calib}")
    print(f"Champion mean r:                           {champ_r}")
    print(f"Champion high-fatigue NLL:                 {champ_hf_nll}")

    # ── Load data ─────────────────────────────────────────────────────────────
    print(f"\nLoading data (min_year={args.min_year})...")
    df = _load_data(args.min_year)

    null_pct = df[_FEATURE_COLS_NO_EB].isna().mean() * 100
    high_null = null_pct[null_pct > 2]
    if not high_null.empty:
        print("  Null rates > 2% in no-EB feature set (median-imputed per fold):")
        for col, pct in high_null.items():
            print(f"    {col}: {pct:.1f}%")

    if args.dry_run:
        print(f"\n[DRY RUN] Data loaded: {len(df):,} rows. Exiting before CV.")
        return

    # ── Run no-EB CV ──────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("Walk-forward CV: no-EB feature set (21 raw rolling features)")
    print("=" * 72)

    no_eb_nll, no_eb_mae, no_eb_calib, no_eb_r, no_eb_folds = _run_cv(
        df, _FEATURE_COLS_NO_EB, label="no-eb"
    )

    # ── High-fatigue subset eval for no-EB model ──────────────────────────────
    print("\nFitting final no-EB model for high-fatigue subset evaluation...")
    no_eb_subset = _high_fatigue_eval(df, _FEATURE_COLS_NO_EB)
    no_eb_hf_nll = no_eb_subset.get("high_fatigue", {}).get("nll")

    # ── Comparison table ──────────────────────────────────────────────────────
    nll_delta   = round(no_eb_nll - champ_nll, 4) if champ_nll else None
    calib_delta = round(no_eb_calib - champ_calib, 4) if champ_calib else None
    hf_delta    = round(no_eb_hf_nll - champ_hf_nll, 4) if (no_eb_hf_nll and champ_hf_nll) else None

    eb_helps_nll   = nll_delta is not None and nll_delta > 0   # no-EB is worse → EB helps
    eb_helps_calib = calib_delta is not None and calib_delta < 0
    eb_helps_hf    = hf_delta is not None and hf_delta > 0

    print("\n" + "=" * 72)
    print("6D.5 EB Ablation Results")
    print("=" * 72)
    w = 38
    print(f"  {'Metric':<{w}}  {'Champion (EB)':>14}  {'No-EB':>10}  {'Delta (no_eb - champ)':>22}")
    print(f"  {'-'*w}  {'-'*14}  {'-'*10}  {'-'*22}")
    print(f"  {'CV NLL (pre-tuning)':<{w}}  {champ_nll or 'N/A':>14}  {no_eb_nll:>10.4f}  "
          f"{('+' if nll_delta >= 0 else '') + str(nll_delta) if nll_delta is not None else 'N/A':>22}")
    print(f"  {'CV calib_80':<{w}}  {champ_calib or 'N/A':>14}  {no_eb_calib:>10.4f}  "
          f"{('+' if calib_delta >= 0 else '') + str(calib_delta) if calib_delta is not None else 'N/A':>22}")
    print(f"  {'High-fatigue NLL (all-data model)':<{w}}  {champ_hf_nll or 'N/A':>14}  "
          f"{no_eb_hf_nll or 'N/A':>10}  "
          f"{('+' if hf_delta >= 0 else '') + str(hf_delta) if hf_delta is not None else 'N/A':>22}")
    print()

    eb_adds_nll_lift   = "YES" if eb_helps_nll   else "NO"
    eb_adds_calib_lift = "YES" if eb_helps_calib else "NO"
    eb_adds_hf_lift    = "YES" if eb_helps_hf    else "NO"

    print(f"  EB improves CV NLL:            {eb_adds_nll_lift}  (positive delta → no-EB worse → EB helps)")
    print(f"  EB improves calib_80:          {eb_adds_calib_lift}")
    print(f"  EB improves high-fatigue NLL:  {eb_adds_hf_lift}")

    # Decision rule: retain EB if it meaningfully reduces NLL (>0.005) or
    # shows high-fatigue improvement — the domain-motivated use case.
    nll_lift_material = nll_delta is not None and nll_delta >= 0.005
    retain_eb = nll_lift_material or eb_helps_hf

    decision = "RETAIN" if retain_eb else "DEFER_TO_V3"
    rationale = []
    if nll_lift_material:
        rationale.append(f"EB reduces CV NLL by {nll_delta:.4f} (>= 0.005 threshold)")
    if eb_helps_hf:
        rationale.append("EB improves high-fatigue subset NLL")
    if not retain_eb:
        rationale.append("NLL lift < 0.005 and no high-fatigue NLL improvement")

    print(f"\n  Decision: {decision}")
    print(f"  Rationale: {'; '.join(rationale)}")
    print("=" * 72)

    # ── Write JSON ────────────────────────────────────────────────────────────
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"ablation_eb_bullpen_{ts}.json"

    payload = {
        "run_ts":       ts,
        "story":        "6D.5",
        "min_year":     args.min_year,
        "champion": {
            "n_features":      len(_FEATURE_COLS_ALL),
            "cv_nll":          champ_nll,
            "tuned_cv_nll":    champ_tuned,
            "cv_calib_80":     champ_calib,
            "cv_mean_r":       champ_r,
            "high_fatigue_nll": champ_hf_nll,
        },
        "no_eb": {
            "n_features":       len(_FEATURE_COLS_NO_EB),
            "features_dropped": sorted(_EB_FEATURES),
            "cv_nll":           round(no_eb_nll, 4),
            "cv_mae":           round(no_eb_mae, 4),
            "cv_calib_80":      round(no_eb_calib, 4),
            "cv_mean_r":        round(no_eb_r, 4),
            "high_fatigue_nll": no_eb_hf_nll,
            "fold_records":     no_eb_folds,
            "subset_eval":      no_eb_subset,
        },
        "deltas": {
            "nll_delta":           nll_delta,
            "calib_80_delta":      calib_delta,
            "high_fatigue_nll_delta": hf_delta,
        },
        "eb_adds_nll_lift":    eb_helps_nll,
        "eb_adds_calib_lift":  eb_helps_calib,
        "eb_adds_hf_lift":     eb_helps_hf,
        "nll_lift_material":   nll_lift_material,
        "decision":            decision,
        "rationale":           rationale,
    }

    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nAblation JSON → {out_path.relative_to(_PROJECT_ROOT)}")

    # ── Append to CLV monitoring log ──────────────────────────────────────────
    nll_delta_str   = f"{nll_delta:+.4f}" if nll_delta is not None else "N/A"
    calib_delta_str = f"{calib_delta:+.4f}" if calib_delta is not None else "N/A"
    hf_delta_str    = f"{hf_delta:+.4f}" if hf_delta is not None else "N/A"

    log_lines = [
        f"## 6D.5 EB Ablation — distributional NegBin ({ts})",
        f"",
        f"| Metric | Champion (EB, 24 feat) | No-EB (21 feat) | Delta |",
        f"|--------|------------------------|-----------------|-------|",
        f"| CV NLL | {champ_nll} | {no_eb_nll:.4f} | {nll_delta_str} |",
        f"| calib_80 | {champ_calib} | {no_eb_calib:.4f} | {calib_delta_str} |",
        f"| High-fatigue NLL | {champ_hf_nll} | {no_eb_hf_nll} | {hf_delta_str} |",
        f"",
        f"**Decision:** {decision}  ",
        f"**Rationale:** {'; '.join(rationale)}  ",
        f"**File:** `{out_path.relative_to(_PROJECT_ROOT)}`  ",
        f"",
        f"---",
    ]
    _append_monitoring_log(log_lines)

    print("\n" + "=" * 72)
    print(f"6D.5 complete — decision: {decision}")
    print("=" * 72)


if __name__ == "__main__":
    main()
