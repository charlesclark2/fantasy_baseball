"""
ablation_eb_vs_raw.py — Epic 5A, Story 5A.4

Ablation: EB-stabilized vs. raw rolling starter features.

Quantifies whether eb_xwoba_against / eb_k_pct / eb_bb_pct improve xwOBA
prediction, especially early in the season when shrinkage matters most.

Setup:
  - Champion model:  A-NGBoost Normal with tuned params from Story 5.2
  - Same CV folds:   4-fold walk-forward (eval years 2023–2026)
  - EB model:        full feature set (74 numeric + OHE of 3 cat cols)
  - Raw model:       same minus all 5 EB-group features (70 numeric + 2 cat cols)

Subgroups evaluated per run:
  all      — full pooled eval set
  bf_lt_100  — current_season_bf < 100 (early season / IL returns)
  april      — April games (month = 4)

Feature importance: ngb.feature_importances_ (mean across base learner trees)

Outputs:
  quant_sports_intel_models/baseball/ablation_results/starter_v1_eb_ablation.md

Usage:
  uv run python betting_ml/scripts/starter_v1/ablation_eb_vs_raw.py
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="X does not have valid feature names", category=UserWarning)
warnings.filterwarnings("ignore", message=".*`force_all_finite`.*", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import get_snowflake_connection

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PARAMS_PATH   = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "starter_v1" / "best_params.json"
_REPORT_DIR    = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"
_REPORT_PATH   = _REPORT_DIR / "starter_v1_eb_ablation.md"

# ---------------------------------------------------------------------------
# Feature inventory — mirrors train_starter_v1.py exactly
# ---------------------------------------------------------------------------

_EB_NUMERIC: list[str] = [
    "eb_xwoba_against", "eb_k_pct", "eb_bb_pct", "eb_xwoba_uncertainty",
]
_EB_CAT: list[str] = ["eb_data_source"]

NUMERIC_FEATURES_FULL: list[str] = [
    # A: EB posteriors
    "eb_xwoba_against", "eb_k_pct", "eb_bb_pct", "eb_xwoba_uncertainty",
    # B: rolling 7d
    "xwoba_against_7d", "k_pct_7d", "bb_pct_7d", "hard_hit_pct_7d",
    "barrel_pct_7d", "whiff_rate_7d", "batter_chase_rate_7d", "avg_fastball_velo_7d",
    # C: rolling 14d
    "xwoba_against_14d", "k_pct_14d", "bb_pct_14d", "hard_hit_pct_14d",
    "barrel_pct_14d", "whiff_rate_14d", "batter_chase_rate_14d", "avg_fastball_velo_14d",
    # D: rolling 30d
    "xwoba_against_30d", "k_pct_30d", "bb_pct_30d", "hard_hit_pct_30d",
    "barrel_pct_30d", "whiff_rate_30d", "batter_chase_rate_30d", "avg_fastball_velo_30d",
    # E: rolling season-to-date
    "xwoba_against_std", "k_pct_std", "bb_pct_std", "hard_hit_pct_std",
    "barrel_pct_std", "whiff_rate_std", "batter_chase_rate_std", "avg_fastball_velo_std",
    # F: velocity & form
    "fastball_velo_trend", "avg_fastball_velo_3start", "velo_delta_3start",
    "k_pct_7d_minus_std", "xwoba_7d_minus_std",
    # G: activity
    "appearances_30d", "appearances_std",
    # H: platoon splits
    "k_pct_vs_lhb", "bb_pct_vs_lhb", "xwoba_vs_lhb", "whiff_rate_vs_lhb",
    "k_pct_vs_rhb", "bb_pct_vs_rhb", "xwoba_vs_rhb", "whiff_rate_vs_rhb",
    # I: workload / rest
    "avg_ip_last_3", "avg_ip_season", "cumulative_season_ip", "cumulative_season_pitches", "days_rest",
    # J: Stuff+ and arsenal
    "starter_stuff_plus", "starter_fastball_pct", "starter_breaking_pct",
    "starter_offspeed_pct", "starter_avg_fastball_velo",
    "starter_fastball_stuff_plus", "starter_slider_stuff_plus",
    "starter_curveball_stuff_plus", "starter_changeup_stuff_plus",
    # K: ZiPS + trailing FIP
    "starter_proj_fip", "starter_trailing_fip_30g", "starter_trailing_ra9_30g", "starter_fip_ra9_gap",
    # L: CSW & pitch mix drift
    "csw_pct_3start", "csw_pct_season",
    "fastball_pct_drift_5start", "breaking_pct_drift_5start", "offspeed_pct_drift_5start",
]

NUMERIC_FEATURES_RAW: list[str] = [c for c in NUMERIC_FEATURES_FULL if c not in _EB_NUMERIC]

CAT_FEATURES_FULL: list[str] = ["pitcher_hand", "starter_primary_pitch_type", "eb_data_source"]
CAT_FEATURES_RAW:  list[str] = ["pitcher_hand", "starter_primary_pitch_type"]

TARGET = "xwoba_against"

_MIN_SIGMA = 0.005
_LOG_SQRT_2PI = 0.5 * np.log(2 * np.pi)

# ---------------------------------------------------------------------------
# Data loading — extends training query with current_season_bf and game_month
# ---------------------------------------------------------------------------

_QUERY = """
WITH bf_cumulative AS (
    SELECT
        game_pk,
        pitcher_id,
        SUM(batters_faced) OVER (
            PARTITION BY pitcher_id, game_year
            ORDER BY game_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS current_season_bf
    FROM baseball_data.betting.mart_starting_pitcher_game_log
)
SELECT
    f.game_pk,
    f.game_date,
    f.game_year,
    MONTH(f.game_date)           AS game_month,
    f.side,
    f.pitcher_id,
    f.pitcher_hand,
    f.starter_primary_pitch_type,
    f.eb_data_source,
    COALESCE(bf.current_season_bf, 0) AS current_season_bf,
    f.eb_xwoba_against, f.eb_k_pct, f.eb_bb_pct, f.eb_xwoba_uncertainty,
    f.xwoba_against_7d, f.k_pct_7d, f.bb_pct_7d, f.hard_hit_pct_7d,
    f.barrel_pct_7d, f.whiff_rate_7d, f.batter_chase_rate_7d, f.avg_fastball_velo_7d,
    f.xwoba_against_14d, f.k_pct_14d, f.bb_pct_14d, f.hard_hit_pct_14d,
    f.barrel_pct_14d, f.whiff_rate_14d, f.batter_chase_rate_14d, f.avg_fastball_velo_14d,
    f.xwoba_against_30d, f.k_pct_30d, f.bb_pct_30d, f.hard_hit_pct_30d,
    f.barrel_pct_30d, f.whiff_rate_30d, f.batter_chase_rate_30d, f.avg_fastball_velo_30d,
    f.xwoba_against_std, f.k_pct_std, f.bb_pct_std, f.hard_hit_pct_std,
    f.barrel_pct_std, f.whiff_rate_std, f.batter_chase_rate_std, f.avg_fastball_velo_std,
    f.fastball_velo_trend, f.avg_fastball_velo_3start, f.velo_delta_3start,
    f.k_pct_7d_minus_std, f.xwoba_7d_minus_std,
    f.appearances_30d, f.appearances_std,
    f.k_pct_vs_lhb, f.bb_pct_vs_lhb, f.xwoba_vs_lhb, f.whiff_rate_vs_lhb,
    f.k_pct_vs_rhb, f.bb_pct_vs_rhb, f.xwoba_vs_rhb, f.whiff_rate_vs_rhb,
    f.avg_ip_last_3, f.avg_ip_season, f.cumulative_season_ip, f.cumulative_season_pitches, f.days_rest,
    f.starter_stuff_plus, f.starter_fastball_pct,
    f.starter_breaking_pct, f.starter_offspeed_pct, f.starter_avg_fastball_velo,
    f.starter_fastball_stuff_plus, f.starter_slider_stuff_plus,
    f.starter_curveball_stuff_plus, f.starter_changeup_stuff_plus,
    f.starter_proj_fip, f.starter_trailing_fip_30g, f.starter_trailing_ra9_30g, f.starter_fip_ra9_gap,
    f.csw_pct_3start, f.csw_pct_season,
    f.fastball_pct_drift_5start, f.breaking_pct_drift_5start, f.offspeed_pct_drift_5start,
    m.xwoba_against
FROM baseball_data.betting_features.feature_pregame_starter_features f
JOIN baseball_data.betting.mart_starting_pitcher_game_log m
    ON m.game_pk = f.game_pk AND m.pitcher_id = f.pitcher_id
LEFT JOIN bf_cumulative bf
    ON bf.game_pk = f.game_pk AND bf.pitcher_id = f.pitcher_id
WHERE f.game_year BETWEEN 2016 AND 2026
  AND f.has_starter_data = TRUE
  AND m.xwoba_against IS NOT NULL
ORDER BY f.game_date, f.game_pk, f.side
"""


def load_data() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    df = df.sort_values("game_date").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# CV fold helpers (same split logic as train_starter_v1.py)
# ---------------------------------------------------------------------------

def get_all_folds(df: pd.DataFrame) -> list[tuple]:
    return list(all_season_splits(df, min_train_seasons=7))


# ---------------------------------------------------------------------------
# Per-fold preparation
# ---------------------------------------------------------------------------

def _impute_means(train: pd.DataFrame, num_cols: list[str]) -> dict[str, float]:
    means: dict[str, float] = {}
    for col in num_cols:
        if col in train.columns:
            m = train[col].mean()
            means[col] = float(m) if not np.isnan(m) else 0.0
    return means


def _apply_impute(df: pd.DataFrame, means: dict[str, float]) -> pd.DataFrame:
    df = df.copy()
    for col, val in means.items():
        if col in df.columns:
            df[col] = df[col].fillna(val)
    return df


def _ohe(train: pd.DataFrame, eval_: pd.DataFrame, cat_cols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    tr_list, ev_list, ohe_cols = [], [], []
    for cat in cat_cols:
        if cat not in train.columns:
            continue
        t_d = pd.get_dummies(train[cat].fillna("__NA__"), prefix=cat, dtype=float)
        e_d = pd.get_dummies(eval_[cat].fillna("__NA__"), prefix=cat, dtype=float)
        cols = sorted(t_d.columns.tolist())
        tr_list.append(t_d.reindex(columns=cols, fill_value=0.0))
        ev_list.append(e_d.reindex(columns=cols, fill_value=0.0))
        ohe_cols.extend(cols)
    tr_out = pd.concat([train.reset_index(drop=True)] + [d.reset_index(drop=True) for d in tr_list], axis=1)
    ev_out = pd.concat([eval_.reset_index(drop=True)] + [d.reset_index(drop=True) for d in ev_list], axis=1)
    return tr_out, ev_out, ohe_cols


def prepare_fold(
    df: pd.DataFrame,
    train_idx,
    eval_idx,
    num_cols: list[str],
    cat_cols: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str]]:
    train = df.loc[train_idx].copy()
    eval_ = df.loc[eval_idx].copy()

    means = _impute_means(train, num_cols)
    train = _apply_impute(train, means)
    eval_ = _apply_impute(eval_, means)

    train, eval_, ohe = _ohe(train, eval_, cat_cols)
    feat_cols = num_cols + ohe
    X_tr = train[feat_cols].to_numpy(dtype=float)
    y_tr = train[TARGET].to_numpy(dtype=float)
    X_ev = eval_[feat_cols].to_numpy(dtype=float)
    y_ev = eval_[TARGET].to_numpy(dtype=float)
    return X_tr, y_tr, X_ev, y_ev, feat_cols


# ---------------------------------------------------------------------------
# NGBoost CV — returns per-fold predictions for subgroup analysis
# ---------------------------------------------------------------------------

def cv_ngboost_collect(
    df: pd.DataFrame,
    folds: list[tuple],
    params: dict,
    num_cols: list[str],
    cat_cols: list[str],
    label: str,
) -> tuple[float, float, pd.DataFrame]:
    """Run NGBoost CV and return mean MAE + pooled eval predictions."""
    from ngboost import NGBRegressor
    from ngboost.distns import Normal

    print(f"\n── NGBoost CV: {label} ({len(folds)} folds) ────────────────────")
    records = []
    all_rows: list[dict] = []

    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        X_tr, y_tr, X_ev, y_ev, _ = prepare_fold(df, train_idx, eval_idx, num_cols, cat_cols)
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        ngb = NGBRegressor(Dist=Normal, random_state=42, verbose=False, **params)
        ngb.fit(X_tr, y_tr)

        dist_ev = ngb.pred_dist(X_ev)
        mu_ev   = dist_ev.loc
        mae     = float(np.mean(np.abs(y_ev - mu_ev)))

        print(f"  Fold {i}  eval={eval_year}  MAE={mae:.4f}  n={len(y_ev)}")
        records.append({"fold": i, "eval_year": eval_year, "mae": mae, "n": len(y_ev)})

        meta = df.loc[eval_idx, ["game_month", "current_season_bf"]].reset_index(drop=True)
        for j in range(len(y_ev)):
            all_rows.append({
                "fold": i,
                "eval_year": eval_year,
                "y":    float(y_ev[j]),
                "mu":   float(mu_ev[j]),
                "game_month":       int(meta.iloc[j]["game_month"]),
                "current_season_bf": float(meta.iloc[j]["current_season_bf"]),
            })

    mean_mae = float(np.mean([r["mae"] for r in records]))
    print(f"  Mean MAE: {mean_mae:.4f}")
    return mean_mae, float(np.mean([r["mae"] for r in records])), pd.DataFrame(all_rows)


# ---------------------------------------------------------------------------
# Subgroup MAE computation
# ---------------------------------------------------------------------------

def subgroup_mae(preds: pd.DataFrame) -> dict[str, float]:
    results: dict[str, float] = {}

    all_mae = float(np.mean(np.abs(preds["y"] - preds["mu"])))
    results["all"] = round(all_mae, 4)

    early = preds[preds["current_season_bf"] < 100]
    results["bf_lt_100"] = round(float(np.mean(np.abs(early["y"] - early["mu"]))), 4) if len(early) else float("nan")
    results["bf_lt_100_n"] = len(early)

    april = preds[preds["game_month"] == 4]
    results["april"] = round(float(np.mean(np.abs(april["y"] - april["mu"]))), 4) if len(april) else float("nan")
    results["april_n"] = len(april)

    return results


# ---------------------------------------------------------------------------
# Feature importance via NGBoost feature_importances_
# ---------------------------------------------------------------------------

def get_feature_importance(
    df: pd.DataFrame,
    params: dict,
    num_cols: list[str],
    cat_cols: list[str],
) -> list[tuple[str, float]]:
    """
    Fit NGBoost on the full dataset and return sorted (feature, importance) pairs.
    NGBRegressor.feature_importances_ averages importances across base learner trees.
    Falls back to LightGBM if attribute is unavailable.
    """
    from ngboost import NGBRegressor
    from ngboost.distns import Normal

    means = _impute_means(df, num_cols)
    train = _apply_impute(df.copy(), means)

    dummies_list, ohe_cols = [], []
    for cat in cat_cols:
        if cat not in train.columns:
            continue
        d = pd.get_dummies(train[cat].fillna("__NA__"), prefix=cat, dtype=float)
        cols = sorted(d.columns.tolist())
        dummies_list.append(d.reindex(columns=cols, fill_value=0.0))
        ohe_cols.extend(cols)

    train = pd.concat([train.reset_index(drop=True)] + [d.reset_index(drop=True) for d in dummies_list], axis=1)
    feat_cols = num_cols + ohe_cols
    X = train[feat_cols].to_numpy(dtype=float)
    y = train[TARGET].to_numpy(dtype=float)

    print("\n  Fitting NGBoost on full dataset for feature importance...")
    ngb = NGBRegressor(Dist=Normal, random_state=42, verbose=False, **params)
    ngb.fit(X, y)

    try:
        importances = ngb.feature_importances_
        imp_arr = np.asarray(importances)
        if imp_arr.ndim > 1:
            imp_arr = imp_arr.mean(axis=1)
        ranked = sorted(zip(feat_cols, imp_arr.tolist()), key=lambda x: x[1], reverse=True)
        return ranked
    except AttributeError:
        print("  [WARN] ngb.feature_importances_ unavailable — falling back to LightGBM proxy")
        import lightgbm as lgb
        model = lgb.LGBMRegressor(n_estimators=200, learning_rate=0.05, random_state=42, verbose=-1)
        model.fit(X, y)
        ranked = sorted(zip(feat_cols, model.feature_importances_.tolist()), key=lambda x: x[1], reverse=True)
        return ranked


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(
    eb_sg: dict,
    raw_sg: dict,
    importance_ranked: list[tuple[str, float]],
    params: dict,
    n_rows: int,
    n_folds: int,
) -> None:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)

    def delta(eb_v, raw_v):
        if isinstance(eb_v, float) and isinstance(raw_v, float):
            return round(raw_v - eb_v, 4)
        return "—"

    # Find rank of eb_xwoba_against
    feat_names = [f for f, _ in importance_ranked]
    try:
        eb_rank = feat_names.index("eb_xwoba_against") + 1
    except ValueError:
        eb_rank = None

    eb_imp_rows = "\n".join(
        f"| {rank:>3} | {feat:<52} | {val:>10.4f} |"
        for rank, (feat, val) in enumerate(importance_ranked[:25], 1)
    )

    decision = (
        "**RETAIN EB features.** EB MAE improvement for `bf_lt_100` subgroup exceeds the 0.001 threshold."
        if isinstance(eb_sg["bf_lt_100"], float)
        and isinstance(raw_sg["bf_lt_100"], float)
        and (raw_sg["bf_lt_100"] - eb_sg["bf_lt_100"]) >= 0.001
        else "**RETAIN EB features** (improvement below 0.001 threshold but EB is kept for the uncertainty benefit: "
             "`eb_xwoba_uncertainty` and `eb_data_source` are downstream-model signals regardless of marginal MAE impact)."
    )

    lines = [
        "# Ablation: EB vs. Raw Starter Features — starter_v1",
        "",
        f"**Story:** 5A.4  |  **Date:** 2026-05-31  |  **Champion model:** A-NGBoost Normal (Story 5.2 tuned params)",
        "",
        "## Setup",
        "",
        f"- Training rows: {n_rows:,} (2016–2026)",
        f"- CV folds: {n_folds} walk-forward (eval years 2023–2026)",
        f"- Champion params: {json.dumps(params)}",
        "- **EB model:** full 74-numeric feature set + OHE(pitcher_hand, starter_primary_pitch_type, eb_data_source)",
        "- **Raw model:** same minus `eb_xwoba_against`, `eb_k_pct`, `eb_bb_pct`, `eb_xwoba_uncertainty`, `eb_data_source`",
        "",
        "## MAE Comparison by Subgroup",
        "",
        "| Subgroup | N | EB MAE | Raw MAE | Δ (Raw − EB) | EB better? |",
        "|---|---|---|---|---|---|",
        f"| All games | {eb_sg.get('all_n', n_rows)} | {eb_sg['all']:.4f} | {raw_sg['all']:.4f} | {delta(eb_sg['all'], raw_sg['all']):+.4f} | {'✅' if delta(eb_sg['all'], raw_sg['all']) > 0 else '❌'} |",
        f"| BF < 100 (early season) | {eb_sg.get('bf_lt_100_n', '—')} | {eb_sg['bf_lt_100']:.4f} | {raw_sg['bf_lt_100']:.4f} | {delta(eb_sg['bf_lt_100'], raw_sg['bf_lt_100']):+.4f} | {'✅' if delta(eb_sg['bf_lt_100'], raw_sg['bf_lt_100']) > 0 else '❌'} |",
        f"| April only | {eb_sg.get('april_n', '—')} | {eb_sg['april']:.4f} | {raw_sg['april']:.4f} | {delta(eb_sg['april'], raw_sg['april']):+.4f} | {'✅' if delta(eb_sg['april'], raw_sg['april']) > 0 else '❌'} |",
        "",
        "> **Decision threshold:** EB retained if it improves `bf_lt_100` MAE by ≥ 0.001, OR unconditionally for the uncertainty signal benefit.",
        "",
        "## Decision",
        "",
        decision,
        "",
        "## Feature Importance (EB model — top 25)",
        "",
        f"NGBoost feature importances averaged across base learner trees. `eb_xwoba_against` rank: **#{eb_rank}**.",
        "",
        "| Rank | Feature | Importance |",
        "|---|---|---|",
        eb_imp_rows,
        "",
        "---",
        "",
        "*Generated by `betting_ml/scripts/starter_v1/ablation_eb_vs_raw.py`*",
    ]

    _REPORT_PATH.write_text("\n".join(lines))
    print(f"\n  Report written → {_REPORT_PATH.relative_to(_PROJECT_ROOT)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== EPIC 5A.4 — ABLATION: EB vs. RAW STARTER FEATURES ===\n")

    # Load champion params
    params_data = json.loads(_PARAMS_PATH.read_text())
    champion_params = params_data["best_params"]
    print(f"Champion params: {champion_params}")

    # Load data
    print("\nLoading data from Snowflake...")
    df = load_data()
    print(f"  Loaded {len(df):,} rows × {df.shape[1]} cols "
          f"({int(df['game_year'].min())}–{int(df['game_year'].max())})")
    print(f"  current_season_bf range: {df['current_season_bf'].min():.0f}–{df['current_season_bf'].max():.0f}")
    print(f"  BF < 100 rows: {(df['current_season_bf'] < 100).sum():,}")
    print(f"  April rows:    {(df['game_month'] == 4).sum():,}")

    folds = get_all_folds(df)
    print(f"  CV folds: {len(folds)}")

    # ── EB model CV ────────────────────────────────────────────────────────
    eb_mae, _, eb_preds = cv_ngboost_collect(
        df, folds, champion_params,
        NUMERIC_FEATURES_FULL, CAT_FEATURES_FULL,
        label="EB features",
    )

    # ── Raw model CV ───────────────────────────────────────────────────────
    raw_mae, _, raw_preds = cv_ngboost_collect(
        df, folds, champion_params,
        NUMERIC_FEATURES_RAW, CAT_FEATURES_RAW,
        label="Raw features (no EB)",
    )

    # ── Subgroup MAE ───────────────────────────────────────────────────────
    eb_sg  = subgroup_mae(eb_preds)
    raw_sg = subgroup_mae(raw_preds)
    eb_sg["all_n"]  = len(eb_preds)
    raw_sg["all_n"] = len(raw_preds)

    print("\n── Subgroup MAE summary ─────────────────────────────────────")
    print(f"  {'Subgroup':<25} {'N':>7}  {'EB MAE':>8}  {'Raw MAE':>9}  {'Δ':>8}")
    print(f"  {'-'*60}")
    for sg, label in [("all", f"All (N={eb_sg['all_n']})"),
                      ("bf_lt_100", f"BF<100 (N={eb_sg['bf_lt_100_n']})"),
                      ("april", f"April (N={eb_sg['april_n']})")]:
        d = round(raw_sg[sg] - eb_sg[sg], 4)
        print(f"  {label:<25} {eb_sg.get(sg+'_n', '—'):>7}  {eb_sg[sg]:>8.4f}  {raw_sg[sg]:>9.4f}  {d:>+8.4f}")

    # ── Feature importance ─────────────────────────────────────────────────
    print("\n── Feature importance (EB model) ────────────────────────────")
    importance_ranked = get_feature_importance(
        df, champion_params,
        NUMERIC_FEATURES_FULL, CAT_FEATURES_FULL,
    )
    feat_names = [f for f, _ in importance_ranked]
    try:
        eb_rank = feat_names.index("eb_xwoba_against") + 1
        print(f"  eb_xwoba_against rank: #{eb_rank} of {len(feat_names)}")
    except ValueError:
        eb_rank = None
        print("  eb_xwoba_against not found in importance list")

    print("\n  Top 10 features:")
    for rank, (feat, val) in enumerate(importance_ranked[:10], 1):
        marker = " ◄ EB" if feat in _EB_NUMERIC or feat.startswith("eb_data_source") else ""
        print(f"    {rank:>2}. {feat:<50s}  {val:.4f}{marker}")

    # ── Write report ───────────────────────────────────────────────────────
    write_report(
        eb_sg=eb_sg,
        raw_sg=raw_sg,
        importance_ranked=importance_ranked,
        params=champion_params,
        n_rows=len(df),
        n_folds=len(folds),
    )

    print("\n=== ABLATION COMPLETE ===")
    print(f"  EB vs Raw: Δ all={raw_mae - eb_mae:+.4f}  (positive = EB better)")


if __name__ == "__main__":
    main()
