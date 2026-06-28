"""Card 7.K — Pitcher arsenal k-means clustering.

Loads mart_pitcher_arsenal_summary from Snowflake, clusters pitchers by
arsenal vector, and persists assignments to baseball_data.statsapi.pitcher_clusters.

Each run is tagged with a snapshot_date (defaults to today).  The table PK is
(pitcher_id, season, snapshot_date), so monthly in-season reruns accumulate as
distinct snapshots rather than overwriting each other.  The downstream dbt model
feature_pitcher_cluster_matchups joins on MAX(snapshot_date) < game_date so each
game automatically picks up the most recent available snapshot without leakage.

Retraining cadence:
  - April / early May  : use prior-season snapshot (no current-season run needed)
  - ~June 1            : first in-season snapshot once starters have ~750 pitches
  - July–September     : monthly snapshots (around the 1st of each month)
  - Off-season         : run once after World Series ends to produce the
                         end-of-season baseline for the following year

Upsert strategy: DELETE rows matching (season, snapshot_date), then INSERT fresh
assignments.  MERGE is not used (Snowflake MERGE connectivity issues).

Usage:
    uv run python betting_ml/scripts/pitcher_clustering/cluster_pitchers.py --season 2025
    uv run python betting_ml/scripts/pitcher_clustering/cluster_pitchers.py --season 2025 --dry-run
    uv run python betting_ml/scripts/pitcher_clustering/cluster_pitchers.py --season 2025 --min-k 4 --max-k 10
    uv run python betting_ml/scripts/pitcher_clustering/cluster_pitchers.py --season 2026 --snapshot-date 2026-06-01
"""

from __future__ import annotations

import argparse
import datetime as _dt
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

_MODELS_DIR = PROJECT_ROOT / "betting_ml" / "models" / "pitcher_clustering"

# ── E11.1-W4 lakehouse: build-on-DuckDB I/O ───────────────────────────────────
# `--s3` reads mart_pitcher_arsenal_summary + ref_players from S3 parquet and writes
# pitcher_clusters to S3 parquet, so the BUILD runs on DuckDB (the sklearn k-means is
# unchanged → value-identical assignments). `--seed` is the one-time history migration:
# it copies the EXISTING Snowflake pitcher_clusters (all accumulated snapshots) into the
# S3 parquet so mart_batter_woba_vs_cluster — which joins on (pitcher_id, season) across
# ALL snapshots — has parity at cutover. Ongoing `--s3` runs DELETE+INSERT the run's
# (season, snapshot_date) into the consolidated parquet, mirroring _persist's semantics.
_S3_BUCKET   = "baseball-betting-ml-artifacts"
_LAKEHOUSE   = f"s3://{_S3_BUCKET}/baseball/lakehouse"
_S3_CLUSTERS = f"{_LAKEHOUSE}/pitcher_clusters/data.parquet"
_S3_ARSENAL  = f"{_LAKEHOUSE}/mart_pitcher_arsenal_summary/data.parquet"
_S3_REFPLAYERS = f"{_LAKEHOUSE}/stg_ref_players/part-0.parquet"

# Column order for the pitcher_clusters parquet — matches the LIVE Snowflake table
# baseball_data.statsapi.pitcher_clusters (pitcher_id, season, cluster_id,
# cluster_label, silhouette_score, fit_date, run_timestamp). The table is unique on
# (pitcher_id, season) — the `snapshot_date`-accumulation design in _DDL/_persist never
# materialised (1 fit_date), and the mart joins on (pitcher_id, season), so we key the
# S3 build on (pitcher_id, season) too.
_CLUSTER_COLS = [
    "pitcher_id", "season", "cluster_id", "cluster_label",
    "silhouette_score", "fit_date", "run_timestamp",
]


def _get_duckdb():
    """DuckDB connection with S3 credential-chain auth (mirrors run_w1_lakehouse.py)."""
    import duckdb
    duck = duckdb.connect()
    duck.execute("INSTALL httpfs; LOAD httpfs")
    duck.execute(
        "CREATE OR REPLACE SECRET baseball_s3 "
        "(TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')"
    )
    return duck


def _load_data_s3(duck, season: int) -> pd.DataFrame:
    """S3/DuckDB analogue of _load_data — same projection + filter."""
    cols = (
        "pitcher_id, game_year AS season, total_pitches, "
        "fb_avg_velocity, brk_avg_velocity, os_avg_velocity, "
        "fb_avg_hmov, brk_avg_hmov, fb_avg_vmov, brk_avg_vmov, "
        "fastball_pct, breaking_pct, offspeed_pct, overall_stuff_plus, "
        "fb_avg_spin, brk_avg_spin, fb_release_height, fb_release_side, "
        "fb_extension, fb_arm_angle"
    )
    return duck.execute(
        f"SELECT {cols} FROM read_parquet('{_S3_ARSENAL}', union_by_name=true) "
        f"WHERE game_year = {int(season)}"
    ).fetch_df()


def _load_names_s3(duck, pitcher_ids: list[int]) -> dict[int, str]:
    if not pitcher_ids:
        return {}
    id_list = ", ".join(str(int(i)) for i in pitcher_ids)
    df = duck.execute(
        f"SELECT mlb_bam_id, player_name "
        f"FROM read_parquet('{_S3_REFPLAYERS}', union_by_name=true) "
        f"WHERE mlb_bam_id IN ({id_list})"
    ).fetch_df()
    return dict(zip(df["mlb_bam_id"], df["player_name"]))


def _persist_s3(duck, df_result: pd.DataFrame, season: int, snapshot_date: str,
                best_score: float) -> None:
    """Rebuild this run's `season` in the consolidated S3 parquet, preserving every
    OTHER season. The live table is unique on (pitcher_id, season), so we drop ALL of
    this season's prior rows (any fit_date) and write the fresh assignments — keeping
    (pitcher_id, season) unique for the mart join. `snapshot_date` (the --snapshot-date
    arg) is stored in the `fit_date` column to match the Snowflake schema."""
    new = df_result[["pitcher_id", "season", "cluster_id", "cluster_label"]].copy()
    new["silhouette_score"] = float(best_score)
    new["fit_date"] = snapshot_date
    # naive (tz-less) UTC wall time → TIMESTAMP_NTZ-compatible parquet column
    new["run_timestamp"] = pd.Timestamp(_dt.datetime.utcnow())
    new = new[_CLUSTER_COLS]

    # Carry forward all OTHER seasons (drop this season entirely → no (pitcher_id, season) dupes).
    try:
        existing = duck.execute(
            f"SELECT {', '.join(_CLUSTER_COLS)} "
            f"FROM read_parquet('{_S3_CLUSTERS}', union_by_name=true) "
            f"WHERE season <> {int(season)}"
        ).fetch_df()
        print(f"  carried forward {len(existing):,} existing rows (other seasons)")
    except Exception as e:
        existing = new.iloc[0:0].copy()
        print(f"  no existing pitcher_clusters parquet ({e}); writing fresh")

    out = pd.concat([existing, new], ignore_index=True)
    duck.register("_pc_out", out)
    duck.execute(f"COPY _pc_out TO '{_S3_CLUSTERS}' (FORMAT PARQUET)")
    print(f"  wrote {len(out):,} rows ({len(new):,} new for "
          f"season={season} fit_date={snapshot_date}) → {_S3_CLUSTERS}")


def _seed_s3_from_snowflake(duck) -> None:
    """One-time history migration: copy the existing Snowflake pitcher_clusters (all
    snapshots) into the S3 parquet so the mart has parity at cutover."""
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT pitcher_id, season, cluster_id, cluster_label, "
            "silhouette_score, fit_date, run_timestamp FROM baseball_data.statsapi.pitcher_clusters"
        )
        rows = cur.fetchall()
        cols = [d[0].lower() for d in cur.description]
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)[_CLUSTER_COLS]
    duck.register("_pc_seed", df)
    duck.execute(f"COPY _pc_seed TO '{_S3_CLUSTERS}' (FORMAT PARQUET)")
    print(f"Seeded {len(df):,} existing Snowflake rows → {_S3_CLUSTERS}")

# Clustering feature columns. spin_diff and pitch_entropy are derived in
# _prepare_features before scaling; all others come directly from the mart.
FEATURE_COLS = [
    "fb_avg_velocity",
    "brk_avg_velocity",
    "os_avg_velocity",
    "fb_avg_hmov",
    "brk_avg_hmov",
    "fb_avg_vmov",
    "brk_avg_vmov",
    "fastball_pct",
    "breaking_pct",
    "offspeed_pct",
    "overall_stuff_plus",
    "fb_avg_spin",
    "brk_avg_spin",
    "spin_diff",        # derived: brk_avg_spin - fb_avg_spin
    "pitch_entropy",    # derived: Shannon entropy of pitch mix
    "fb_release_height",
    "fb_release_side",
    "fb_extension",
    "fb_arm_angle",
]

# Silhouette threshold — empirically, MLB pitcher data peaks ~0.14-0.16.
# Below this we warn but do not abort; the clusters still carry predictive signal.
_SILHOUETTE_THRESHOLD = 0.10

_DDL = """
CREATE TABLE IF NOT EXISTS baseball_data.statsapi.pitcher_clusters (
    pitcher_id       INTEGER      NOT NULL,
    season           INTEGER      NOT NULL,
    snapshot_date    DATE         NOT NULL,
    cluster_id       INTEGER      NOT NULL,
    cluster_label    VARCHAR(50)  NOT NULL,
    silhouette_score FLOAT,
    run_timestamp    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (pitcher_id, season, snapshot_date)
)
"""

_SPOT_CHECK_NAMES = [
    "Cole, Gerrit",
    "Kershaw, Clayton",
    "Hendricks, Kyle",
    "Scherzer, Max",
    "Wheeler, Zack",
    "Strider, Spencer",
    "Webb, Logan",
    "Alcántara, Sandy",
    "Cease, Dylan",
    "Burnes, Corbin",
]

_LOAD_QUERY = """
SELECT
    pitcher_id,
    game_year         AS season,
    total_pitches,
    fb_avg_velocity,
    brk_avg_velocity,
    os_avg_velocity,
    fb_avg_hmov,
    brk_avg_hmov,
    fb_avg_vmov,
    brk_avg_vmov,
    fastball_pct,
    breaking_pct,
    offspeed_pct,
    overall_stuff_plus,
    fb_avg_spin,
    brk_avg_spin,
    fb_release_height,
    fb_release_side,
    fb_extension,
    fb_arm_angle
FROM baseball_data.betting.mart_pitcher_arsenal_summary
WHERE game_year = {season}
"""


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


def _load_names(pitcher_ids: list[int]) -> dict[int, str]:
    """Return pitcher_id → player_name map from savant.ref_players."""
    if not pitcher_ids:
        return {}
    id_list = ", ".join(str(i) for i in pitcher_ids)
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
    claim their slot first. Any clusters beyond 5 archetypes get multi_pitch_mix.
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

    # 1. power_swing_and_miss: highest velocity + stuff+
    idx = _pick_max(c["fb_avg_velocity"] + c["overall_stuff_plus"])
    labels[idx] = "power_swing_and_miss"
    used.add(idx)

    if len(used) >= len(c):
        return labels

    # 2. elite_breaking_ball: highest breaking_pct
    idx = _pick_max(c["breaking_pct"])
    labels[idx] = "elite_breaking_ball"
    used.add(idx)

    if len(used) >= len(c):
        return labels

    # 3. contact_sinker_ball: lowest fb_avg_vmov (sinkers have least vertical carry)
    idx = _pick_min(c["fb_avg_vmov"])
    labels[idx] = "contact_sinker_ball"
    used.add(idx)

    if len(used) >= len(c):
        return labels

    # 4. changeup_deceptive: highest offspeed_pct
    idx = _pick_max(c["offspeed_pct"])
    labels[idx] = "changeup_deceptive"
    used.add(idx)

    if len(used) >= len(c):
        return labels

    # 5. soft_command: lowest velocity + lowest stuff+ (finesse / command pitchers)
    idx = _pick_min(c["fb_avg_velocity"] + c["overall_stuff_plus"])
    labels[idx] = "soft_command"
    used.add(idx)

    # All remaining get multi_pitch_mix
    for idx in c.index:
        if idx not in used:
            labels[idx] = "multi_pitch_mix"

    return labels


def _prepare_features(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, StandardScaler]:
    """Return (df_clean, X_scaled, scaler) after deriving features, imputing, and normalizing."""
    df = df.copy()

    # Impute overall_stuff_plus to league-average when FG crosswalk is missing
    df["overall_stuff_plus"] = df["overall_stuff_plus"].fillna(100.0)

    # Derived features computed before scaling
    df["spin_diff"] = df["brk_avg_spin"] - df["fb_avg_spin"]

    def _entropy(row: pd.Series) -> float:
        probs = [
            p for col in ("fastball_pct", "breaking_pct", "offspeed_pct")
            if pd.notna(p := row.get(col, np.nan)) and p > 0
        ]
        return -sum(p * np.log(p) for p in probs) if probs else 0.0

    df["pitch_entropy"] = df.apply(_entropy, axis=1)

    X = df[FEATURE_COLS].copy()

    # Drop rows with >30% nulls across clustering features
    null_frac = X.isnull().mean(axis=1)
    mask = null_frac <= 0.30
    df_clean = df[mask].copy()
    X = X[mask]

    # Impute remaining nulls with column median
    for col in X.columns:
        median = X[col].median()
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
    """Fit k-means for k in [min_k, max_k], return best model by silhouette score."""
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
    model: KMeans,
    best_k: int,
    best_score: float,
    cluster_label_map: dict[int, str],
) -> None:
    centroid_df = pd.DataFrame(model.cluster_centers_, columns=FEATURE_COLS)
    centroid_df.index.name = "cluster_id"
    centroid_df["cluster_label"] = [
        cluster_label_map.get(i, "multi_pitch_mix") for i in centroid_df.index
    ]
    print(f"\nBest k={best_k}, silhouette={best_score:.4f}")
    print("\nCluster centroids (standardized feature values):")
    print(centroid_df.to_string())
    print()


def _spot_check(df_result: pd.DataFrame, id_name_map: dict[int, str]) -> None:
    df_result["player_name"] = df_result["pitcher_id"].map(id_name_map)
    check = df_result[df_result["player_name"].isin(_SPOT_CHECK_NAMES)][
        ["player_name", "cluster_id", "cluster_label"]
    ]
    if check.empty:
        print("No spot-check pitchers found in this season's data.")
    else:
        print("\nSpot-check — well-known starters and assigned clusters:")
        print(check.to_string(index=False))
    print()


def _ensure_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(_DDL)
    conn.commit()


def _persist(
    df_result: pd.DataFrame,
    season: int,
    snapshot_date: str,
    best_score: float,
    dry_run: bool,
    conn,
) -> None:
    if dry_run:
        print(
            f"[dry-run] Would write {len(df_result)} rows for season={season}, "
            f"snapshot_date={snapshot_date}, silhouette={best_score:.4f}"
        )
        return

    cur = conn.cursor()
    _ensure_table(conn)

    # Delete existing (season, snapshot_date) rows, then insert fresh
    cur.execute(
        "DELETE FROM baseball_data.statsapi.pitcher_clusters "
        "WHERE season = %s AND snapshot_date = %s",
        (season, snapshot_date),
    )
    deleted = cur.rowcount

    rows = [
        (
            int(row["pitcher_id"]),
            int(row["season"]),
            snapshot_date,
            int(row["cluster_id"]),
            str(row["cluster_label"]),
            float(best_score),
        )
        for _, row in df_result.iterrows()
    ]
    cur.executemany(
        """
        INSERT INTO baseball_data.statsapi.pitcher_clusters
            (pitcher_id, season, snapshot_date, cluster_id, cluster_label, silhouette_score)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    conn.commit()
    print(
        f"Deleted {deleted} existing rows; inserted {len(rows)} rows "
        f"into baseball_data.statsapi.pitcher_clusters "
        f"for season={season}, snapshot_date={snapshot_date}."
    )


def _save_model_artifacts(
    model: KMeans, scaler: StandardScaler, season: int, snapshot_date: str
) -> None:
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, _MODELS_DIR / f"kmeans_{season}_{snapshot_date}.pkl")
    joblib.dump(scaler, _MODELS_DIR / f"scaler_{season}_{snapshot_date}.pkl")
    print(f"Model artifacts saved to {_MODELS_DIR}/")


def main() -> None:
    import datetime as _dt

    parser = argparse.ArgumentParser(description="Cluster pitchers by arsenal vector.")
    parser.add_argument("--season", type=int, required=True, help="Season year to cluster")
    parser.add_argument("--dry-run", action="store_true", help="Skip Snowflake writes")
    parser.add_argument("--min-k", type=int, default=4, help="Minimum k for grid search")
    parser.add_argument("--max-k", type=int, default=10, help="Maximum k for grid search")
    parser.add_argument(
        "--snapshot-date",
        type=str,
        default=_dt.date.today().isoformat(),
        help="Snapshot date tag for this run (YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--s3", action="store_true",
        help="E11.1-W4: build on DuckDB — read mart_pitcher_arsenal_summary + ref_players "
             "from S3 parquet and DELETE+INSERT this run's snapshot into the S3 "
             "pitcher_clusters parquet (no Snowflake).",
    )
    parser.add_argument(
        "--seed", action="store_true",
        help="E11.1-W4 one-time: copy the existing Snowflake pitcher_clusters (all "
             "snapshots) into the S3 parquet for cutover parity, then exit.",
    )
    args = parser.parse_args()
    snapshot_date: str = args.snapshot_date

    if args.seed:
        # One-time history migration; no clustering this run.
        duck = _get_duckdb()
        _seed_s3_from_snowflake(duck)
        duck.close()
        print("Done (seed).")
        return

    _duck = _get_duckdb() if args.s3 else None

    print(f"Loading mart_pitcher_arsenal_summary for season={args.season}...")
    df = _load_data_s3(_duck, args.season) if args.s3 else _load_data(args.season)
    print(f"Loaded {len(df)} pitcher-season rows.")

    if len(df) == 0:
        print("ERROR: No data found for this season. Has dbt build been run?")
        sys.exit(1)

    df_clean, X_scaled, scaler = _prepare_features(df)
    print(f"{len(df_clean)} pitchers retained after null filtering.")

    print(f"\nFitting k-means for k={args.min_k}..{args.max_k}:")
    model, best_k, best_score = _fit_clusters(X_scaled, args.min_k, args.max_k)

    # Build centroid df for label assignment and printing
    centroid_df = pd.DataFrame(model.cluster_centers_, columns=FEATURE_COLS)
    centroid_df.index.name = "cluster_id"
    cluster_label_map = _assign_cluster_labels(centroid_df)

    _print_centroids(model, best_k, best_score, cluster_label_map)

    if best_score < _SILHOUETTE_THRESHOLD:
        print(
            f"WARNING: Best silhouette score {best_score:.4f} < threshold {_SILHOUETTE_THRESHOLD}. "
            "Clusters may have low separation but can still carry predictive signal."
        )

    labels = model.labels_
    df_result = df_clean[["pitcher_id", "season"]].copy()
    df_result["cluster_id"] = labels
    df_result["cluster_label"] = df_result["cluster_id"].map(
        lambda i: cluster_label_map.get(i, "multi_pitch_mix")
    )

    print(f"\nCluster distribution (n={len(df_result)}):")
    print(df_result["cluster_label"].value_counts().to_string())
    print()

    # Spot-check against well-known starters
    id_name_map = (
        _load_names_s3(_duck, df_result["pitcher_id"].tolist())
        if args.s3 else _load_names(df_result["pitcher_id"].tolist())
    )
    _spot_check(df_result, id_name_map)

    print(f"Snapshot date: {snapshot_date}")

    if args.s3 and not args.dry_run:
        # E11.1-W4 build-on-DuckDB: write the snapshot to S3 parquet (no Snowflake).
        _persist_s3(_duck, df_result, args.season, snapshot_date, best_score)
        _duck.close()
        _save_model_artifacts(model, scaler, args.season, snapshot_date)
    elif not args.dry_run:
        conn = get_snowflake_connection()
        try:
            _persist(df_result, args.season, snapshot_date, best_score, dry_run=False, conn=conn)
        finally:
            conn.close()
        _save_model_artifacts(model, scaler, args.season, snapshot_date)
    else:
        print(
            f"[dry-run] season={args.season}, snapshot_date={snapshot_date}, "
            f"silhouette={best_score:.4f}, pitchers={len(df_result)}, best_k={best_k}"
        )

    print("Done.")


if __name__ == "__main__":
    main()
