"""Card 7.K2 — Batter hitting-profile k-means clustering.

Loads mart_batter_profile_summary from Snowflake, clusters batters by hitting
profile vector, and persists assignments to baseball_data.statsapi.batter_clusters.

Upsert strategy: DELETE rows for the season, then INSERT fresh assignments.
MERGE is not used (Snowflake MERGE connectivity issues; project standard).

Silhouette threshold: 0.10 (batter profiles are more continuous than pitcher
arsenals, so the ceiling is lower — warn but do not abort below this).

Retraining cadence:
  - Run once per season after ZiPS projections are available (pre-season).
  - Optional mid-season rerun after ~750 PA accumulate in the target season.

CLI usage:
    uv run python betting_ml/scripts/batter_clustering/cluster_batters.py --season 2025
    uv run python betting_ml/scripts/batter_clustering/cluster_batters.py --season 2025 --dry-run
    uv run python betting_ml/scripts/batter_clustering/cluster_batters.py --season 2025 --min-k 4 --max-k 8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

_MODELS_DIR = PROJECT_ROOT / "betting_ml" / "models" / "batter_clustering"

# Clustering feature columns — all come from mart_batter_profile_summary.
# bb_k_ratio and contact_power are derived before scaling.
BATTER_FEATURE_COLS = [
    "k_pct",
    "bb_pct",
    "iso",
    "gb_pct",
    "fb_pct",
    "pull_pct",
    "hard_hit_pct",
    "barrel_pct",
    "avg_exit_velocity",
    "sprint_speed",       # NULL-imputed to median (FanGraphs; not in current mart)
    "avg_xwoba",
    "bb_k_ratio",         # derived: bb_pct / (k_pct + 0.001)
    "contact_power",      # derived: (1 - k_pct) * iso
]

_SILHOUETTE_THRESHOLD = 0.10

_DDL = """
CREATE TABLE IF NOT EXISTS baseball_data.statsapi.batter_clusters (
    batter_id        INTEGER      NOT NULL,
    season           INTEGER      NOT NULL,
    cluster_id       INTEGER      NOT NULL,
    cluster_label    VARCHAR(50)  NOT NULL,
    silhouette_score FLOAT,
    run_timestamp    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (batter_id, season)
)
"""

_LOAD_QUERY = """
SELECT
    batter_id,
    game_year         AS season,
    pa_count,
    avg_exit_velocity,
    gb_pct,
    fb_pct,
    ld_pct,
    pull_pct,
    hard_hit_pct,
    barrel_pct,
    avg_xwoba,
    k_pct,
    bb_pct,
    iso,
    proj_k_pct,
    proj_bb_pct
FROM baseball_data.betting.mart_batter_profile_summary
WHERE game_year = {season}
"""

_SPOT_CHECK_NAMES = {
    "Judge, Aaron",
    "Arraez, Luis",
    "Soto, Juan",
    "Alvarez, Yordan",
    "Kwan, Steven",
    "Freeman, Freddie",
    "Alonso, Pete",
    "Abreu, Jose",
    "Bichette, Bo",
    "Ramirez, Jose",
}


def _load_data(season: int) -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_LOAD_QUERY.format(season=season))
        rows = cur.fetchall()
        columns = [desc[0].lower() for desc in cur.description]
        return pd.DataFrame(rows, columns=columns)
    finally:
        conn.close()


def _load_names(batter_ids: list[int]) -> dict[int, str]:
    """Return batter_id → player_name from savant.ref_players."""
    if not batter_ids:
        return {}
    id_list = ", ".join(str(i) for i in batter_ids)
    query = f"""
        SELECT mlb_bam_id, player_name
        FROM baseball_data.savant.ref_players
        WHERE mlb_bam_id IN ({id_list})
    """
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        columns = [desc[0].lower() for desc in cur.description]
        df = pd.DataFrame(rows, columns=columns)
        return dict(zip(df["mlb_bam_id"], df["player_name"]))
    finally:
        conn.close()


def _assign_cluster_labels(centroid_df: pd.DataFrame) -> dict[int, str]:
    """Assign human-readable labels by inspecting centroid feature rankings.

    Labels are assigned in priority order so the most distinctive archetypes
    claim their slot first. Any clusters beyond 5 archetypes get 'balanced'.
    All comparisons are on standardized (z-score) centroid values.
    """
    c = centroid_df.copy()
    labels: dict[int, str] = {}
    used: set[int] = set()

    def _pick_max(score: pd.Series) -> int:
        remaining = score[~score.index.isin(used)]
        return int(remaining.idxmax())

    def _pick_min(score: pd.Series) -> int:
        remaining = score[~score.index.isin(used)]
        return int(remaining.idxmin())

    # 1. power_pull: highest (iso + barrel_pct + pull_pct)
    idx = _pick_max(c["iso"] + c["barrel_pct"] + c["pull_pct"])
    labels[idx] = "power_pull"
    used.add(idx)

    if len(used) >= len(c):
        return labels

    # 2. patient_obp: highest (bb_pct + bb_k_ratio)
    idx = _pick_max(c["bb_pct"] + c["bb_k_ratio"])
    labels[idx] = "patient_obp"
    used.add(idx)

    if len(used) >= len(c):
        return labels

    # 3. groundball_speed: highest gb_pct with lowest fb_pct
    idx = _pick_max(c["gb_pct"] - c["fb_pct"])
    labels[idx] = "groundball_speed"
    used.add(idx)

    if len(used) >= len(c):
        return labels

    # 4. high_whiff: highest k_pct
    idx = _pick_max(c["k_pct"])
    labels[idx] = "high_whiff"
    used.add(idx)

    if len(used) >= len(c):
        return labels

    # 5. contact_spray: lowest k_pct + lowest pull_pct (finesse contact hitter)
    idx = _pick_min(c["k_pct"] + c["pull_pct"])
    labels[idx] = "contact_spray"
    used.add(idx)

    # Remaining → balanced
    for i in c.index:
        if i not in used:
            labels[i] = "balanced"

    return labels


def _prepare_features(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, StandardScaler]:
    """Return (df_clean, X_scaled, scaler) after deriving features, imputing, normalizing."""
    df = df.copy()

    # Use FanGraphs projected k_pct/bb_pct when Statcast-derived values are null
    df["k_pct"] = df["k_pct"].combine_first(df.get("proj_k_pct", pd.Series(dtype=float)))
    df["bb_pct"] = df["bb_pct"].combine_first(df.get("proj_bb_pct", pd.Series(dtype=float)))

    # avg_xwoba imputed to league average when missing
    df["avg_xwoba"] = df["avg_xwoba"].fillna(0.315)

    # sprint_speed not yet in mart; impute to median (column kept for forward compatibility)
    if "sprint_speed" not in df.columns:
        df["sprint_speed"] = np.nan

    # Derived features computed before scaling
    df["bb_k_ratio"] = df["bb_pct"] / (df["k_pct"] + 0.001)
    df["contact_power"] = (1 - df["k_pct"]) * df["iso"]

    # Only include feature columns that actually exist and are not fully null
    available_cols = [c for c in BATTER_FEATURE_COLS if c in df.columns]
    X = df[available_cols].copy()

    # Drop columns where the entire column is null (e.g. sprint_speed not yet in mart)
    all_null_cols = [c for c in X.columns if X[c].isnull().all()]
    if all_null_cols:
        print(f"Dropping fully-null columns (not yet in mart): {all_null_cols}")
        X = X.drop(columns=all_null_cols)

    # Drop rows with >30% nulls across clustering features
    null_frac = X.isnull().mean(axis=1)
    mask = null_frac <= 0.30
    df_clean = df[mask].copy()
    X = X[mask]

    # Impute remaining nulls with column median (median cannot be NaN here since
    # all-null columns were already dropped above)
    for col in X.columns:
        median = X[col].median()
        if not np.isnan(median):
            X[col] = X[col].fillna(median)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    return df_clean, X_scaled, scaler


def _fit_clusters(
    X_scaled: np.ndarray,
    min_k: int,
    max_k: int,
    random_state: int = 42,
) -> tuple[KMeans, int, float]:
    """Fit k-means for k in [min_k, max_k]; return best model by silhouette score."""
    best_k = min_k
    best_score = -1.0
    best_model = None

    for k in range(min_k, max_k + 1):
        km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        labels = km.fit_predict(X_scaled)
        score = silhouette_score(X_scaled, labels)
        print(f"  k={k}: silhouette={score:.4f}")
        if score > best_score:
            best_score = score
            best_k = k
            best_model = km

    return best_model, best_k, best_score


def _print_centroids(
    centroid_df: pd.DataFrame,
    best_k: int,
    best_score: float,
    cluster_label_map: dict[int, str],
) -> None:
    centroid_df = centroid_df.copy()
    centroid_df.index.name = "cluster_id"
    centroid_df["cluster_label"] = [
        cluster_label_map.get(i, "balanced") for i in centroid_df.index
    ]
    print(f"\nBest k={best_k}, silhouette={best_score:.4f}")
    print("\nCluster centroids (standardized feature values):")
    print(centroid_df.to_string())
    print()


def _spot_check(df_result: pd.DataFrame, id_name_map: dict[int, str]) -> None:
    df_result = df_result.copy()
    df_result["player_name"] = df_result["batter_id"].map(id_name_map)
    check = df_result[df_result["player_name"].isin(_SPOT_CHECK_NAMES)][
        ["player_name", "cluster_id", "cluster_label"]
    ]
    if check.empty:
        print("No spot-check batters found in this season's data.")
    else:
        print("\nSpot-check — well-known batters and assigned clusters:")
        print(check.to_string(index=False))
    print()


def _ensure_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(_DDL)
    conn.commit()


def _persist(
    df_result: pd.DataFrame,
    season: int,
    best_score: float,
    dry_run: bool,
    conn,
) -> None:
    if dry_run:
        print(
            f"[dry-run] Would write {len(df_result)} rows for season={season}, "
            f"silhouette={best_score:.4f}"
        )
        return

    _ensure_table(conn)
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM baseball_data.statsapi.batter_clusters WHERE season = %s",
        (season,),
    )
    deleted = cur.rowcount

    rows = [
        (
            int(row["batter_id"]),
            int(row["season"]),
            int(row["cluster_id"]),
            str(row["cluster_label"]),
            float(best_score),
        )
        for _, row in df_result.iterrows()
    ]
    cur.executemany(
        """
        INSERT INTO baseball_data.statsapi.batter_clusters
            (batter_id, season, cluster_id, cluster_label, silhouette_score)
        VALUES (%s, %s, %s, %s, %s)
        """,
        rows,
    )
    conn.commit()
    print(
        f"Deleted {deleted} existing rows; inserted {len(rows)} rows "
        f"into baseball_data.statsapi.batter_clusters for season={season}."
    )


def _save_model_artifacts(model: KMeans, scaler: StandardScaler, season: int) -> None:
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, _MODELS_DIR / f"kmeans_{season}.pkl")
    joblib.dump(scaler, _MODELS_DIR / f"scaler_{season}.pkl")
    print(f"Model artifacts saved to {_MODELS_DIR}/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cluster batters by hitting profile vector.")
    parser.add_argument("--season", type=int, required=True, help="Season year to cluster")
    parser.add_argument("--dry-run", action="store_true", help="Skip Snowflake writes")
    parser.add_argument("--min-k", type=int, default=4, help="Minimum k for grid search")
    parser.add_argument("--max-k", type=int, default=8, help="Maximum k for grid search")
    args = parser.parse_args()

    print(f"Loading mart_batter_profile_summary for season={args.season}...")
    df = _load_data(args.season)
    print(f"Loaded {len(df)} batter-season rows.")

    if len(df) == 0:
        print("ERROR: No data found for this season. Has dbtf build been run?")
        sys.exit(1)

    df_clean, X_scaled, scaler = _prepare_features(df)
    print(f"{len(df_clean)} batters retained after null filtering.")

    print(f"\nFitting k-means for k={args.min_k}..{args.max_k}:")
    model, best_k, best_score = _fit_clusters(X_scaled, args.min_k, args.max_k)

    actual_cols = list(scaler.feature_names_in_) if hasattr(scaler, "feature_names_in_") else [
        c for c in BATTER_FEATURE_COLS if c in df_clean.columns and df_clean[c].notnull().any()
    ]
    centroid_df = pd.DataFrame(model.cluster_centers_, columns=actual_cols)
    centroid_df.index.name = "cluster_id"
    cluster_label_map = _assign_cluster_labels(centroid_df)

    _print_centroids(centroid_df, best_k, best_score, cluster_label_map)

    if best_score < _SILHOUETTE_THRESHOLD:
        print(
            f"WARNING: Best silhouette score {best_score:.4f} < threshold {_SILHOUETTE_THRESHOLD}. "
            "Batter profiles are continuous; clusters may have low separation but still carry "
            "predictive signal."
        )

    labels = model.labels_
    df_result = df_clean[["batter_id", "season"]].copy()
    df_result["cluster_id"] = labels
    df_result["cluster_label"] = df_result["cluster_id"].map(
        lambda i: cluster_label_map.get(i, "balanced")
    )

    print(f"\nCluster distribution (n={len(df_result)}):")
    print(df_result["cluster_label"].value_counts().to_string())
    print()

    id_name_map = _load_names(df_result["batter_id"].tolist())
    _spot_check(df_result, id_name_map)

    if not args.dry_run:
        conn = get_snowflake_connection()
        try:
            _persist(df_result, args.season, best_score, dry_run=False, conn=conn)
        finally:
            conn.close()
        _save_model_artifacts(model, scaler, args.season)
    else:
        print(
            f"[dry-run] season={args.season}, silhouette={best_score:.4f}, "
            f"batters={len(df_result)}, best_k={best_k}"
        )

    print("Done.")


if __name__ == "__main__":
    main()
