"""
train_run_env.py — Run Environment Sub-Model (Epic 3, Story 3.1 / 3.2)

Builds run_env_v1: a Ridge regression model that predicts total runs scored
from pre-game park, weather, and umpire features. Opponent offensive and
starter quality are included as controls only — not the primary signal.

Training window: 2021-01-01 onward (Story 2.5 weather coverage decision).
Pre-2021 has 0% weather coverage; no backfill is feasible.

Dome handling: dome games have NULL weather columns by design (correct per
Story 2.5). weather columns are coalesced to neutral indoor defaults:
  temp_f → 70, wind_component_mph → 0, humidity_pct → 50.
is_dome is kept as a binary feature so the model can learn the dome baseline.

Output signals written to mart_sub_model_signals:
  run_env_signal         — predicted total runs (z-scored vs. training mean/std)
  environment_volatility — park-level historical run variance proxy

park_run_factor_3yr null handling: ~2% of games are at non-standard venues
(A's at Sutter Health Park/Steinbrenner Field in 2025, Tokyo Dome, special
events). No prior-season MLB park factor exists for these. Imputed with
league-mean park factor at training time — do not drop these rows.

NO market features. This model must be strictly market-blind.

Usage:
    # Story 3.1: dataset audit only
    uv run python betting_ml/scripts/train_run_env.py --audit

    # Story 3.2: full training + artifact write
    uv run python betting_ml/scripts/train_run_env.py

    # Skip Snowflake CV result write
    uv run python betting_ml/scripts/train_run_env.py --no-snowflake
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

_REGISTRY_NAME = "run_env_v1"
_ARTIFACT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "run_env_v1.pkl"
_FEATURE_COLS_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "run_env_v1_features.json"

# Training window defined in sub_model_registry.yaml Story 2.5 weather audit.
_TRAINING_START = "2021-01-01"

# Market features that must never appear in the training matrix.
# Validated in validate_no_leakage() — any intersection raises an error.
_MARKET_FEATURES = frozenset({
    "total_line_consensus", "home_win_prob_consensus", "over_prob_consensus",
    "ml_consensus_std", "home_ml_money_pct", "away_ml_money_pct",
    "over_money_pct", "under_money_pct", "line_open_home", "line_close_home",
    "bookmaker_disagreement", "has_odds",
})

# ---------------------------------------------------------------------------
# Feature specification
# ---------------------------------------------------------------------------

# Park features: prior-season values — no leakage risk.
_PARK_FEATURES = [
    "park_run_factor_3yr",   # primary run environment signal
    "elevation_ft",          # air resistance on fly balls
    "center_ft",             # outfield depth (home run suppression proxy)
    "is_dome",               # 0/1 — also acts as weather validity mask
]

# Weather features: forecast_pregame observation type (canonical pre-game).
# Dome-coalesced in SQL: NULL → indoor neutral defaults.
_WEATHER_FEATURES = [
    "temp_f",                # air density (cold air → suppresses HR)
    "wind_component_mph",    # tailwind > 0 → ball carries; headwind < 0 → suppresses
    "humidity_pct",          # mild effect on ball carry
]

# Umpire features: trailing z-scores — no leakage (pre-game assignment known).
_UMPIRE_FEATURES = [
    "ump_runs_per_game_zscore",   # primary: run expectancy tendency
    "ump_run_impact_zscore",      # overall run impact
    "ump_k_pct_zscore",           # strikeout tendency (inversely corr. with runs)
    "ump_bb_pct_zscore",          # walk tendency (positively corr. with runs)
]

# Opponent quality controls: allow model to partial-out team/starter strength
# so the environment signal is not confounded by matchup quality.
# These are controls only — not the primary signal of interest.
_CONTROL_FEATURES = [
    "home_off_woba_30d",          # home team rolling offensive quality
    "away_off_woba_30d",          # away team rolling offensive quality
    "home_starter_proj_fip",      # home starter ZiPS projected FIP
    "away_starter_proj_fip",      # away starter ZiPS projected FIP
    "home_starter_xwoba_30d",     # home starter rolling performance
    "away_starter_xwoba_30d",     # away starter rolling performance
]

FEATURE_COLS = _PARK_FEATURES + _WEATHER_FEATURES + _UMPIRE_FEATURES + _CONTROL_FEATURES

# Metadata columns carried alongside features but excluded from the model matrix.
_META_COLS = ["game_pk", "game_date", "game_year", "total_runs", "venue_id", "venue_name"]

# Actual elevations for non-standard venues that have no entry in the park features table.
# Keyed by MLB Stats API venue_id. Source: verified from known venue locations.
# Mexico City (7,350 ft) is the most impactful outlier — mean imputation would be wrong by ~7,200 ft.
_VENUE_ELEVATION_FT: dict[int, float] = {
    5340: 7350.0,   # Estadio Alfredo Harp Helu — Mexico City (2,240 m)
    2735:  527.0,   # Journey Bank Ballpark — Williamsport, PA (Little League Classic)
    5381:   20.0,   # London Stadium — London, UK
    5150:   59.0,   # Gocheok Sky Dome — Seoul, South Korea
    5445: 1000.0,   # Field of Dreams — Dyersville, IA
    2397:   40.0,   # Tokyo Dome — Tokyo, Japan
    6130: 1519.0,   # Bristol Motor Speedway — Bristol, TN
    3949:  605.0,   # Rickwood Field — Birmingham, AL
}

# ---------------------------------------------------------------------------
# Training query
# ---------------------------------------------------------------------------

_TRAINING_QUERY = f"""
select
    -- metadata
    g.game_pk,
    g.game_date,
    extract(year from g.game_date)::int          as game_year,
    p.venue_id,
    p.venue_name,

    -- target (computed inline — no total_runs column in mart_game_results)
    g.home_final_score + g.away_final_score      as total_runs,

    -- park features (prior-season, no leakage risk)
    p.park_run_factor_3yr,
    p.elevation_ft,
    p.center_ft,
    -- is_dome derived from park roof_type, NOT w.is_dome: dome games have no
    -- weather row so w.is_dome is NULL, and iff(NULL,1,0) incorrectly returns 0.
    iff(p.roof_type = 'Dome', 1, 0)              as is_dome,

    -- weather features (dome-coalesced to neutral indoor defaults)
    coalesce(w.temp_f,            70)            as temp_f,
    coalesce(w.wind_component_mph, 0)            as wind_component_mph,
    coalesce(w.humidity_pct,      50)            as humidity_pct,

    -- umpire features (trailing z-scores, pre-game assignment)
    u.ump_runs_per_game_zscore,
    u.ump_run_impact_zscore,
    u.ump_k_pct_zscore,
    u.ump_bb_pct_zscore,

    -- opponent quality controls — team offense (rolling 30d)
    th.off_woba_30d                              as home_off_woba_30d,
    ta.off_woba_30d                              as away_off_woba_30d,

    -- opponent quality controls — starter quality
    sh.starter_proj_fip                          as home_starter_proj_fip,
    sh.xwoba_against_30d                         as home_starter_xwoba_30d,
    sa.starter_proj_fip                          as away_starter_proj_fip,
    sa.xwoba_against_30d                         as away_starter_xwoba_30d

from baseball_data.betting.mart_game_results g
left join baseball_data.betting_features.feature_pregame_park_features p
    on p.game_pk = g.game_pk
left join baseball_data.betting_features.feature_pregame_weather_features w
    on w.game_pk = g.game_pk
left join baseball_data.betting_features.feature_pregame_umpire_features u
    on u.game_pk = g.game_pk
left join baseball_data.betting_features.feature_pregame_team_features th
    on th.game_pk = g.game_pk and th.side = 'home'
left join baseball_data.betting_features.feature_pregame_team_features ta
    on ta.game_pk = g.game_pk and ta.side = 'away'
left join baseball_data.betting_features.feature_pregame_starter_features sh
    on sh.game_pk = g.game_pk and sh.side = 'home'
left join baseball_data.betting_features.feature_pregame_starter_features sa
    on sa.game_pk = g.game_pk and sa.side = 'away'

where g.game_date >= '{_TRAINING_START}'
  and g.game_type = 'R'
  and g.home_final_score is not null
  and g.away_final_score is not null

order by g.game_date, g.game_pk
"""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_training_data() -> pd.DataFrame:
    """Pull the run_env training matrix from Snowflake.

    Returns one row per completed regular-season game from 2021-01-01 onward.
    All LEFT JOINs — dome games have coalesced weather values, not dropped rows.
    """
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_TRAINING_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()

    df = pd.DataFrame(rows, columns=cols)
    for col in df.columns:
        if df[col].dtype == object:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() >= df[col].notna().sum() * 0.9:
                df[col] = converted
    return df


# ---------------------------------------------------------------------------
# Leakage validation
# ---------------------------------------------------------------------------

def validate_no_leakage(df: pd.DataFrame) -> None:
    """Assert no market features appear in the training DataFrame.

    Raises ValueError listing any market columns found.
    """
    found = _MARKET_FEATURES & set(df.columns)
    if found:
        raise ValueError(
            f"LEAKAGE DETECTED — market features in training data: {sorted(found)}\n"
            "Remove these columns before training."
        )

    future_patterns = ["_postgame_", "_observed_at_", "final_score", "result_"]
    flagged = [c for c in df.columns if any(p in c for p in future_patterns)
               and c not in ("home_final_score", "away_final_score")]
    if flagged:
        raise ValueError(
            f"POTENTIAL LEAKAGE — columns with post-game keywords: {flagged}"
        )

    print("Leakage validation passed — no market or post-game features found.")


# ---------------------------------------------------------------------------
# Dataset audit (Story 3.1 deliverable)
# ---------------------------------------------------------------------------

def audit_dataset(df: pd.DataFrame) -> None:
    """Print a structured audit of the training dataset.

    Checks:
    - Per-season row counts and target distribution
    - Feature null rates
    - Dome game handling
    - Feature column confirmation
    """
    print("\n" + "=" * 65)
    print("RUN ENVIRONMENT TRAINING DATASET AUDIT")
    print(f"Training window: {_TRAINING_START} → latest")
    print(f"Total rows: {len(df):,}")
    print("=" * 65)

    # Per-season breakdown
    print("\n── Per-season summary ──────────────────────────────────────")
    season_stats = (
        df.groupby("game_year")
        .agg(
            games=("game_pk", "count"),
            avg_runs=("total_runs", "mean"),
            std_runs=("total_runs", "std"),
            dome_games=("is_dome", "sum"),
            null_weather=(
                "wind_component_mph",
                lambda x: (x == 0).sum(),  # dome-coalesced to 0
            ),
            null_umpire=("ump_runs_per_game_zscore", lambda x: x.isna().sum()),
            null_park=("park_run_factor_3yr", lambda x: x.isna().sum()),
            null_home_fip=("home_starter_proj_fip", lambda x: x.isna().sum()),
        )
        .reset_index()
    )
    print(season_stats.to_string(index=False))

    # Overall target distribution
    print("\n── Target (total_runs) distribution ────────────────────────")
    desc = df["total_runs"].describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95])
    for stat, val in desc.items():
        print(f"  {stat:8s}: {val:.3f}")

    # Null rates per feature
    print("\n── Feature null rates ──────────────────────────────────────")
    null_df = pd.DataFrame({
        "feature": FEATURE_COLS,
        "null_count": [df[c].isna().sum() if c in df.columns else len(df) for c in FEATURE_COLS],
        "null_pct": [
            round(df[c].isna().mean() * 100, 1) if c in df.columns else 100.0
            for c in FEATURE_COLS
        ],
        "missing_from_df": [c not in df.columns for c in FEATURE_COLS],
    })
    print(null_df.to_string(index=False))

    # Dome handling check
    dome_count = int(df["is_dome"].sum())
    print(f"\n── Dome game handling ──────────────────────────────────────")
    print(f"  Dome games: {dome_count} ({dome_count/len(df)*100:.1f}% of total)")
    print(f"  Dome avg_runs: {df.loc[df['is_dome']==1,'total_runs'].mean():.2f}")
    print(f"  Outdoor avg_runs: {df.loc[df['is_dome']==0,'total_runs'].mean():.2f}")

    # Missing feature columns
    missing_cols = [c for c in FEATURE_COLS if c not in df.columns]
    if missing_cols:
        print(f"\n[WARN] Feature columns missing from query result: {missing_cols}")
    else:
        print(f"\nAll {len(FEATURE_COLS)} feature columns present in dataset.")

    print("\n── Feature column list ─────────────────────────────────────")
    for group, cols in [
        ("Park", _PARK_FEATURES),
        ("Weather (dome-coalesced)", _WEATHER_FEATURES),
        ("Umpire", _UMPIRE_FEATURES),
        ("Controls", _CONTROL_FEATURES),
    ]:
        print(f"  {group}: {cols}")

    print("\nAudit complete.")


# ---------------------------------------------------------------------------
# Training helpers (Story 3.2)
# ---------------------------------------------------------------------------

_ALPHA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

# Imputation targets — keys match exactly one training-time statistic each.
# Umpire z-scores: 0.0 = neutral (no adjustment needed; no key required).
_IMPUTE_COLS = {
    "park": ["park_run_factor_3yr"],
    "fip": ["home_starter_proj_fip", "away_starter_proj_fip"],
    "woba": ["home_off_woba_30d", "away_off_woba_30d"],
    "xwoba": ["home_starter_xwoba_30d", "away_starter_xwoba_30d"],
}


def _compute_impute_values(train_df: pd.DataFrame) -> dict:
    """Compute training-set means for all feature columns.

    Called on each CV train split so no test leakage occurs.
    Stores a catch-all mean for every feature col under key '_col_<name>',
    plus named means for semantic groupings.
    """
    vals: dict = {}

    # Catch-all: mean for every feature column (covers elevation_ft, center_ft, etc.)
    for col in FEATURE_COLS:
        if col in train_df.columns:
            col_mean = train_df[col].mean()
            vals[f"_col_{col}"] = float(col_mean) if not np.isnan(col_mean) else 0.0

    # Named means for semantic clarity
    for col in _IMPUTE_COLS["park"]:
        vals[col] = vals.get(f"_col_{col}", 1.0)

    fip_vals = []
    for col in _IMPUTE_COLS["fip"]:
        if col in train_df:
            fip_vals.extend(train_df[col].dropna().tolist())
    vals["_fip_mean"] = float(np.mean(fip_vals)) if fip_vals else 4.30

    woba_vals = []
    for col in _IMPUTE_COLS["woba"]:
        if col in train_df:
            woba_vals.extend(train_df[col].dropna().tolist())
    vals["_woba_mean"] = float(np.mean(woba_vals)) if woba_vals else 0.315

    xwoba_vals = []
    for col in _IMPUTE_COLS["xwoba"]:
        if col in train_df:
            xwoba_vals.extend(train_df[col].dropna().tolist())
    vals["_xwoba_mean"] = float(np.mean(xwoba_vals)) if xwoba_vals else 0.315

    return vals


def _apply_imputation(df: pd.DataFrame, impute_vals: dict) -> pd.DataFrame:
    """Fill nulls in the feature matrix using training-time imputation values.

    Applies targeted imputation first (domain-appropriate defaults), then a
    catch-all pass fills any remaining NaN with the training-set column mean.
    """
    df = df.copy()

    # Targeted imputation
    for col in _IMPUTE_COLS["park"]:
        if col in df.columns:
            df[col] = df[col].fillna(impute_vals.get(col, 1.0))
    for col in _UMPIRE_FEATURES:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)
    for col in _IMPUTE_COLS["fip"]:
        if col in df.columns:
            df[col] = df[col].fillna(impute_vals["_fip_mean"])
    for col in _IMPUTE_COLS["woba"]:
        if col in df.columns:
            df[col] = df[col].fillna(impute_vals["_woba_mean"])
    for col in _IMPUTE_COLS["xwoba"]:
        if col in df.columns:
            df[col] = df[col].fillna(impute_vals["_xwoba_mean"])

    # Venue-specific elevation lookup — applied before the catch-all mean fill.
    # Covers non-standard venues (Mexico City, London, Tokyo, etc.) where the
    # park features table has no elevation_ft row. Mean imputation would be wrong
    # by thousands of feet for Mexico City (7,350 ft vs. ~500 ft MLB average).
    if "elevation_ft" in df.columns and "venue_id" in df.columns:
        null_elev = df["elevation_ft"].isna()
        if null_elev.any():
            df.loc[null_elev, "elevation_ft"] = df.loc[null_elev, "venue_id"].map(
                _VENUE_ELEVATION_FT
            )

    # Catch-all: fill any remaining NaN with training-set column mean
    for col in FEATURE_COLS:
        if col in df.columns and df[col].isna().any():
            fallback = impute_vals.get(f"_col_{col}", 0.0)
            df[col] = df[col].fillna(fallback)

    return df


def _build_Xy(df: pd.DataFrame, impute_vals: dict) -> tuple[np.ndarray, np.ndarray]:
    """Return (X, y) arrays from a (possibly already-imputed) DataFrame."""
    df_imp = _apply_imputation(df, impute_vals)
    X = df_imp[FEATURE_COLS].to_numpy(dtype=float)
    y = df_imp["total_runs"].to_numpy(dtype=float)
    return X, y


def _walk_forward_cv(df: pd.DataFrame) -> tuple[float, float, list[dict]]:
    """Walk-forward season CV across all seasons in df.

    For each season s (starting from the second available season):
      - Train on all prior seasons
      - Test on season s

    Tries all alphas in _ALPHA_GRID; returns (best_alpha, best_mean_mae, fold_records).
    """
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    seasons = sorted(df["game_year"].unique())
    if len(seasons) < 2:
        raise ValueError(f"Need at least 2 seasons for walk-forward CV; got {seasons}")

    folds = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    best_alpha = 1.0
    best_mean_mae = float("inf")

    for alpha in _ALPHA_GRID:
        fold_maes = []
        for train_seasons, test_season in folds:
            train_mask = df["game_year"].isin(train_seasons)
            test_mask = df["game_year"] == test_season
            train_df = df[train_mask]
            test_df = df[test_mask]

            impute_vals = _compute_impute_values(train_df)
            X_train, y_train = _build_Xy(train_df, impute_vals)
            X_test, y_test = _build_Xy(test_df, impute_vals)

            pipe = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
            pipe.fit(X_train, y_train)
            y_pred = pipe.predict(X_test)
            mae = float(np.mean(np.abs(y_pred - y_test)))
            fold_maes.append(mae)

        mean_mae = float(np.mean(fold_maes))
        if mean_mae < best_mean_mae:
            best_mean_mae = mean_mae
            best_alpha = alpha

    # Collect fold records with best alpha
    fold_records = []
    for train_seasons, test_season in folds:
        train_mask = df["game_year"].isin(train_seasons)
        test_mask = df["game_year"] == test_season
        train_df = df[train_mask]
        test_df = df[test_mask]

        impute_vals = _compute_impute_values(train_df)
        X_train, y_train = _build_Xy(train_df, impute_vals)
        X_test, y_test = _build_Xy(test_df, impute_vals)

        pipe = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=best_alpha))])
        pipe.fit(X_train, y_train)
        y_pred = pipe.predict(X_test)
        mae = float(np.mean(np.abs(y_pred - y_test)))
        bias = float(np.mean(y_pred - y_test))
        fold_records.append({
            "fold": len(fold_records) + 1,
            "train_seasons": list(map(int, train_seasons)),
            "test_season": int(test_season),
            "n_train": int(len(y_train)),
            "n_test": int(len(y_test)),
            "mae": round(mae, 4),
            "bias": round(bias, 4),
        })

    return best_alpha, round(best_mean_mae, 4), fold_records


def _print_cv_results(best_alpha: float, fold_records: list[dict]) -> None:
    mean_mae = float(np.mean([r["mae"] for r in fold_records]))
    mean_bias = float(np.mean([r["bias"] for r in fold_records]))
    print("\n── Walk-forward CV results ─────────────────────────────────")
    print(f"  Best alpha: {best_alpha}")
    print(f"  {'Fold':>4}  {'Train':>16}  {'Test':>6}  {'N_train':>7}  {'N_test':>6}  {'MAE':>6}  {'Bias':>7}")
    for r in fold_records:
        train_str = f"{r['train_seasons'][0]}–{r['train_seasons'][-1]}"
        print(
            f"  {r['fold']:>4}  {train_str:>16}  {r['test_season']:>6}  "
            f"{r['n_train']:>7}  {r['n_test']:>6}  {r['mae']:>6.3f}  {r['bias']:>+7.3f}"
        )
    print(f"  {'Mean':>4}  {'':>16}  {'':>6}  {'':>7}  {'':>6}  {mean_mae:>6.3f}  {mean_bias:>+7.3f}")


def _print_calibration(df: pd.DataFrame, y_pred: np.ndarray) -> None:
    """Print calibration breakdowns on the full training set (in-sample proxy)."""
    df = df.copy()
    df["_pred"] = y_pred
    df["_err"] = np.abs(df["_pred"] - df["total_runs"])
    df["_bias"] = df["_pred"] - df["total_runs"]

    print("\n── Calibration: by season ──────────────────────────────────")
    for yr, grp in df.groupby("game_year"):
        print(
            f"  {yr}  n={len(grp):>4}  MAE={grp['_err'].mean():.3f}  "
            f"bias={grp['_bias'].mean():+.3f}"
        )

    print("\n── Calibration: dome vs outdoor ────────────────────────────")
    for label, mask in [("dome", df["is_dome"] == 1), ("outdoor", df["is_dome"] == 0)]:
        g = df[mask]
        if len(g):
            print(f"  {label:>7}  n={len(g):>5}  MAE={g['_err'].mean():.3f}  bias={g['_bias'].mean():+.3f}")

    print("\n── Calibration: by temperature band ───────────────────────")
    bins = [(-999, 55, "cold (<55°F)"), (55, 75, "mild (55–75°F)"), (75, 999, "warm (>75°F)")]
    for lo, hi, label in bins:
        mask = (df["temp_f"] >= lo) & (df["temp_f"] < hi)
        g = df[mask]
        if len(g):
            print(f"  {label:>14}  n={len(g):>5}  MAE={g['_err'].mean():.3f}  bias={g['_bias'].mean():+.3f}")

    print("\n── Calibration: by park run factor quartile ────────────────")
    qcuts = pd.qcut(df["park_run_factor_3yr"], q=4, labels=["Q1 (low)", "Q2", "Q3", "Q4 (high)"])
    for q_label, grp in df.groupby(qcuts, observed=True):
        print(
            f"  {str(q_label):>10}  n={len(grp):>5}  MAE={grp['_err'].mean():.3f}  "
            f"bias={grp['_bias'].mean():+.3f}"
        )


def _update_registry(cv_score: float) -> None:
    """Write cv_score and promotion_status=challenger to sub_model_registry.yaml."""
    import re

    registry_path = _PROJECT_ROOT / "betting_ml" / "sub_model_registry.yaml"
    text = registry_path.read_text()

    # Update cv_score under run_env_v1 block only
    text = re.sub(
        r"(run_env_v1:.*?cv_score:)\s*null",
        rf"\1 {cv_score}",
        text,
        count=1,
        flags=re.DOTALL,
    )
    # Update promotion_status
    text = re.sub(
        r"(run_env_v1:.*?promotion_status:)\s*pending",
        r"\1 challenger",
        text,
        count=1,
        flags=re.DOTALL,
    )
    registry_path.write_text(text)
    print(f"\nRegistry updated: cv_score={cv_score}, promotion_status=challenger")


# ---------------------------------------------------------------------------
# Training (Story 3.2)
# ---------------------------------------------------------------------------

def train(df: pd.DataFrame, *, no_snowflake: bool = False) -> None:
    """Train run_env_v1 Ridge regression with walk-forward season CV.

    Walk-forward folds: train on all seasons before year T, test on year T.
    Alpha selected by grid search across folds. Final model trained on full data.
    Artifact and feature-column JSON written to betting_ml/models/sub_models/.
    Registry updated with cv_score and promotion_status=challenger.
    """
    import pickle
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    print("\n" + "=" * 65)
    print("TRAINING run_env_v1 — Ridge regression")
    print("=" * 65)

    # ------------------------------------------------------------------
    # 1. Walk-forward CV to select alpha and measure held-out MAE
    # ------------------------------------------------------------------
    print("\nRunning walk-forward CV (alpha grid: {})...".format(_ALPHA_GRID))
    best_alpha, mean_mae, fold_records = _walk_forward_cv(df)
    _print_cv_results(best_alpha, fold_records)

    # ------------------------------------------------------------------
    # 2. Train final model on all data with best alpha
    # ------------------------------------------------------------------
    print(f"\nTraining final model (alpha={best_alpha}) on all {len(df):,} rows...")
    impute_vals = _compute_impute_values(df)
    X_all, y_all = _build_Xy(df, impute_vals)

    pipeline = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=best_alpha))])
    pipeline.fit(X_all, y_all)

    y_pred_all = pipeline.predict(X_all)
    train_mae = float(np.mean(np.abs(y_pred_all - y_all)))
    print(f"  Training MAE (in-sample, expected lower than CV): {train_mae:.4f}")
    print(f"  Walk-forward CV MAE (reported metric):            {mean_mae:.4f}")

    # ------------------------------------------------------------------
    # 3. Calibration report (in-sample, diagnostic only)
    # ------------------------------------------------------------------
    df_imp = _apply_imputation(df, impute_vals)
    _print_calibration(df_imp, y_pred_all)

    # ------------------------------------------------------------------
    # 4. Feature coefficients
    # ------------------------------------------------------------------
    coef = pipeline.named_steps["ridge"].coef_
    print("\n── Feature coefficients (unstandardized direction only) ────")
    for feat, c in sorted(zip(FEATURE_COLS, coef), key=lambda x: abs(x[1]), reverse=True):
        print(f"  {feat:<35s}  {c:+.4f}")

    # ------------------------------------------------------------------
    # 5. Save artifact
    # ------------------------------------------------------------------
    artifact = {
        "model": pipeline,
        "feature_cols": FEATURE_COLS,
        "impute_values": impute_vals,
        "target_mean": float(y_all.mean()),
        "target_std": float(y_all.std()),
        "cv_mae": mean_mae,
        "best_alpha": best_alpha,
        "cv_fold_records": fold_records,
    }
    _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_ARTIFACT_PATH, "wb") as fh:
        pickle.dump(artifact, fh)
    print(f"\nArtifact saved → {_ARTIFACT_PATH}")

    with open(_FEATURE_COLS_PATH, "w") as fh:
        json.dump(FEATURE_COLS, fh, indent=2)
    print(f"Feature columns saved → {_FEATURE_COLS_PATH}")

    # ------------------------------------------------------------------
    # 6. Update registry
    # ------------------------------------------------------------------
    _update_registry(mean_mae)

    print("\n" + "=" * 65)
    print(f"run_env_v1 training complete. CV MAE = {mean_mae:.4f} runs.")
    print("Next: Story 3.3 — generate and store run environment signals.")
    print("=" * 65)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Train run_env_v1 sub-model (Epic 3)")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Story 3.1: load and audit the training dataset only; do not train.",
    )
    parser.add_argument(
        "--no-snowflake",
        action="store_true",
        help="Skip writing CV results back to Snowflake (local dev).",
    )
    args = parser.parse_args()

    print(f"Loading training data from Snowflake ({_TRAINING_START} → latest)...")
    df = load_training_data()
    print(f"Loaded {len(df):,} rows across {df['game_year'].nunique()} seasons.")

    validate_no_leakage(df)

    if args.audit:
        audit_dataset(df)
        return

    train(df, no_snowflake=args.no_snowflake)


if __name__ == "__main__":
    main()
