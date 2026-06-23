"""
fit_pitcher_archetypes.py
-------------------------
Epic 7.2 — Pitcher Archetype Clustering (revalidation).

Fits ONE cluster model across all seasons (2015–current) pooled simultaneously,
then assigns labels per (pitcher_id, season). Cross-season pooling is the same
strategy proven in 7.1: prevents per-season local optima and archetype dropout.

Era discontinuity (stratum-B features, excluded):
  - FanGraphs Stuff+ (overall_stuff_plus): only available 2020+; excluded from features.
  - MLB arm_angle tracking (fb_arm_angle): only available 2020+; excluded from features.
  - Both columns are present in the mart but NULL for 2015-2019.

Stratum-A feature set (13 features, available 2015+):
    fastball_pct, breaking_pct, offspeed_pct    — pitch mix composition
    fb_avg_velocity                              — raw velocity
    fb_avg_hmov, fb_avg_vmov                     — fastball movement
    brk_avg_hmov, brk_avg_vmov                   — breaking ball movement
    k_pct, bb_pct                                — outcome metrics
    whiff_pct                                    — swing-and-miss per swing
    gb_pct                                       — groundball rate
    age_at_season_start                          — career stage context

Target: 6 archetypes (matching current statsapi.pitcher_clusters):
    power_swing_and_miss, elite_breaking_ball, changeup_deceptive,
    contact_sinker_ball, multi_pitch_mix, soft_command

k evaluated over --k-range (default 5–8). Best model selected by silhouette score.
Heuristic labels suggested from centroids; inspect and override with --label-map.

Persistence:
    CREATE OR REPLACE TABLE baseball_data.statsapi.pitcher_clusters → INSERT assignments.
    Writes model artifacts to betting_ml/models/pitcher_archetypes/.
    Schema change from prototype (SNAPSHOT_DATE PK) → fit_date column, (pitcher_id, season) PK.

Usage:
    # Dry-run: print centroids and suggested labels, no Snowflake write
    uv run betting_ml/scripts/clustering/fit_pitcher_archetypes.py --dry-run

    # Full run with defaults (k=5–8, all three algorithms, min-bf=100)
    uv run betting_ml/scripts/clustering/fit_pitcher_archetypes.py

    # Override label assignments from centroid inspection
    uv run betting_ml/scripts/clustering/fit_pitcher_archetypes.py \\
        --label-map '{"0":"power_swing_and_miss","1":"elite_breaking_ball","2":"changeup_deceptive","3":"contact_sinker_ball","4":"multi_pitch_mix","5":"soft_command"}'

    # Restrict to kmeans only, evaluate k=6 only
    uv run betting_ml/scripts/clustering/fit_pitcher_archetypes.py \\
        --algorithms kmeans --k-range 6 6
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import silhouette_score
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

_MODELS_DIR = PROJECT_ROOT / "betting_ml" / "models" / "pitcher_archetypes"
# S3 is the prod source of truth (.pkl files are gitignored / not baked into the image).
# compute_archetype_posteriors.py loads the latest centroids/scaler from here.
_S3_PREFIX = "s3://baseball-betting-ml-artifacts/pitcher_archetypes"
_SILHOUETTE_WARN = 0.15  # Realistic ceiling for pitcher continuum data; warn if below

FEATURE_COLS = [
    # Stratum-A: available 2015+
    "fastball_pct",
    "breaking_pct",
    "offspeed_pct",
    "fb_avg_velocity",
    "fb_avg_hmov",
    "fb_avg_vmov",
    "brk_avg_hmov",
    "brk_avg_vmov",
    "k_pct",
    "bb_pct",
    "whiff_pct",
    "gb_pct",
    "age_at_season_start",
    # Stratum-B (2020+ only): fb_arm_angle, overall_stuff_plus — excluded from k-means
]

_DDL = """
CREATE OR REPLACE TABLE baseball_data.statsapi.pitcher_clusters (
    pitcher_id       INTEGER      NOT NULL,
    season           INTEGER      NOT NULL,
    cluster_id       INTEGER      NOT NULL,
    cluster_label    VARCHAR(50)  NOT NULL,
    silhouette_score FLOAT,
    fit_date         DATE,
    run_timestamp    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (pitcher_id, season)
)
"""

_PITCHER_PROFILE_QUERY = """
SELECT
    p.pitcher_id,
    p.game_year                AS season,
    p.bf_count,
    p.fastball_pct,
    p.breaking_pct,
    p.offspeed_pct,
    p.fb_avg_velocity,
    p.fb_arm_angle,
    p.fb_avg_hmov,
    p.fb_avg_vmov,
    p.brk_avg_hmov,
    p.brk_avg_vmov,
    p.overall_stuff_plus,
    p.k_pct,
    p.bb_pct,
    p.whiff_pct,
    p.gb_pct,
    p.birth_date
FROM baseball_data.betting.mart_pitcher_profile_summary p
WHERE p.game_year >= {min_season}
  AND p.bf_count  >= {min_bf}
ORDER BY p.game_year, p.pitcher_id
"""

_NAMES_QUERY = """
SELECT mlb_bam_id, player_name
FROM baseball_data.savant.ref_players
WHERE mlb_bam_id IN ({id_list})
"""

_SPOT_CHECK_NAMES = {
    "Cole, Gerrit",
    "Webb, Logan",
    "Scherzer, Max",
    "deGrom, Jacob",
    "Bieber, Shane",
    "Glasnow, Tyler",
    "Cease, Dylan",
    "Hendricks, Kyle",
    "Fried, Max",
    "Gausman, Kevin",
    "Verlander, Justin",
    "Ohtani, Shohei",
    "Musgrove, Joe",
    "Alcántara, Sandy",
    "Strider, Spencer",
}


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_data(min_season: int, min_bf: int) -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_PITCHER_PROFILE_QUERY.format(min_season=min_season, min_bf=min_bf))
        rows = cur.fetchall()
        cols = [d[0].lower() for d in cur.description]
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()


def _load_names(pitcher_ids: list[int]) -> dict[int, str]:
    if not pitcher_ids:
        return {}
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_NAMES_QUERY.format(id_list=", ".join(str(i) for i in pitcher_ids)))
        rows = cur.fetchall()
        cols = [d[0].lower() for d in cur.description]
        df = pd.DataFrame(rows, columns=cols)
        return dict(zip(df["mlb_bam_id"], df["player_name"]))
    finally:
        conn.close()


# ── Feature preparation ───────────────────────────────────────────────────────

def _compute_age(birth_date, season: int) -> float | None:
    if birth_date is None or (isinstance(birth_date, float) and np.isnan(birth_date)):
        return None
    if isinstance(birth_date, str):
        try:
            bd = date.fromisoformat(birth_date)
        except ValueError:
            return None
    else:
        bd = birth_date
    season_start = date(int(season), 4, 1)
    return (season_start - bd).days / 365.25


def _prepare_features(
    df_profile: pd.DataFrame,
) -> tuple[pd.DataFrame, np.ndarray, StandardScaler, list[str]]:
    df = df_profile.copy()

    df["age_at_season_start"] = df.apply(
        lambda r: _compute_age(r["birth_date"], r["season"]), axis=1
    )

    # Drop rows where >30% of features are null
    null_frac = df[FEATURE_COLS].isnull().mean(axis=1)
    mask = null_frac <= 0.30
    n_dropped = (~mask).sum()
    if n_dropped:
        print(f"  Dropped {n_dropped} rows with >30% null features.")
    df_clean = df[mask].reset_index(drop=True)
    X = df_clean[FEATURE_COLS].copy()

    # Null counts before imputation
    null_counts = X.isnull().sum()
    notable = null_counts[null_counts > 0]
    if not notable.empty:
        for col, n in notable.items():
            print(f"  NOTE: {n} nulls in {col} — median-imputed")

    # Column-median imputation for remaining nulls
    for col in X.columns:
        if X[col].isnull().any():
            X[col] = X[col].fillna(X[col].median())

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    return df_clean, X_scaled, scaler, FEATURE_COLS


# ── Model comparison ──────────────────────────────────────────────────────────

def _compare_algorithms(
    X_scaled: np.ndarray,
    k_range: range,
    algorithms: list[str],
    random_state: int = 42,
) -> tuple[str, int, float, np.ndarray]:
    """Try each (algorithm, k) combination; return the combo with highest silhouette."""
    best_algo, best_k, best_score, best_labels = None, k_range.start, -1.0, None

    print(f"\nComparing algorithms {algorithms} for k={k_range.start}–{k_range.stop - 1}:")
    for k in k_range:
        for algo in algorithms:
            labels = _fit_one(X_scaled, algo, k, random_state)
            if labels is None:
                continue
            score = silhouette_score(X_scaled, labels)
            marker = " ◀ best so far" if score > best_score else ""
            print(f"  algo={algo:12s}  k={k}  silhouette={score:.4f}{marker}")
            if score > best_score:
                best_score, best_k, best_algo, best_labels = score, k, algo, labels

    return best_algo, best_k, best_score, best_labels


def _fit_one(
    X_scaled: np.ndarray,
    algo: str,
    k: int,
    random_state: int,
) -> np.ndarray | None:
    try:
        if algo == "kmeans":
            model = KMeans(n_clusters=k, n_init=20, random_state=random_state)
            return model.fit_predict(X_scaled)
        elif algo == "gmm":
            model = GaussianMixture(n_components=k, n_init=5, random_state=random_state)
            return model.fit_predict(X_scaled)
        elif algo == "hierarchical":
            model = AgglomerativeClustering(n_clusters=k, linkage="ward")
            return model.fit_predict(X_scaled)
    except Exception as exc:
        print(f"  WARNING: {algo} k={k} failed: {exc}")
    return None


def _refit_best_kmeans(
    X_scaled: np.ndarray,
    best_algo: str,
    best_k: int,
    random_state: int = 42,
) -> KMeans | None:
    if best_algo == "kmeans":
        model = KMeans(n_clusters=best_k, n_init=20, random_state=random_state)
        model.fit(X_scaled)
        return model
    return None


# ── Centroid inspection & label suggestions ───────────────────────────────────

def _print_centroid_summary(
    X_scaled: np.ndarray,
    labels: np.ndarray,
    feature_cols: list[str],
) -> pd.DataFrame:
    df_tmp = pd.DataFrame(X_scaled, columns=feature_cols)
    df_tmp["cluster_id"] = labels
    centroids = df_tmp.groupby("cluster_id")[feature_cols].mean()
    print("\nCluster centroids (standardized z-scores; positive = above league average):")
    print(centroids.round(3).to_string())
    return centroids


def _suggest_labels(centroids: pd.DataFrame) -> dict[int, str]:
    """
    Heuristic label suggestions based on centroid feature rankings.
    Assignment order is deliberate: most distinctive archetypes first,
    so ambiguous clusters fall through to multi_pitch_mix last.

    Inspect the centroid table above and override via --label-map if needed.
    """
    c = centroids.copy()
    labels: dict[int, str] = {}
    used: set[int] = set()

    def _pick_max(s: pd.Series) -> int:
        return int(s.drop(index=list(used), errors="ignore").idxmax())

    def _pick_min(s: pd.Series) -> int:
        return int(s.drop(index=list(used), errors="ignore").idxmin())

    def _assign(idx: int, label: str) -> None:
        labels[idx] = label
        used.add(idx)

    n = len(c)

    # 1. power_swing_and_miss: highest K% + whiff + velocity + stuff_plus
    if n >= 1:
        score = (
            c.get("k_pct", pd.Series(0, index=c.index))
            + c.get("whiff_pct", pd.Series(0, index=c.index))
            + c.get("fb_avg_velocity", pd.Series(0, index=c.index))
            + c.get("overall_stuff_plus", pd.Series(0, index=c.index))
        )
        _assign(_pick_max(score), "power_swing_and_miss")

    # 2. contact_sinker_ball: highest GB% − K% (ground-ball-inducing, low whiff)
    if n >= 2:
        score = (
            c.get("gb_pct", pd.Series(0, index=c.index))
            - c.get("k_pct", pd.Series(0, index=c.index))
        )
        _assign(_pick_max(score), "contact_sinker_ball")

    # 3. soft_command: lowest velocity + lowest stuff_plus (finesse/command pitcher)
    if n >= 3:
        score = (
            c.get("fb_avg_velocity", pd.Series(0, index=c.index))
            + c.get("overall_stuff_plus", pd.Series(0, index=c.index))
        )
        _assign(_pick_min(score), "soft_command")

    # 4. elite_breaking_ball: highest breaking% among remaining
    if n >= 4:
        col = c.get("breaking_pct", pd.Series(0, index=c.index))
        _assign(_pick_max(col.drop(index=list(used), errors="ignore")), "elite_breaking_ball")

    # 5. changeup_deceptive: highest offspeed% among remaining
    if n >= 5:
        col = c.get("offspeed_pct", pd.Series(0, index=c.index))
        _assign(_pick_max(col.drop(index=list(used), errors="ignore")), "changeup_deceptive")

    # 6. multi_pitch_mix: whatever remains (balanced/undefined pitch mix)
    for idx in c.index:
        if idx not in used:
            labels[idx] = "multi_pitch_mix"

    return labels


# ── Stability report ──────────────────────────────────────────────────────────

def _stability_report(df_result: pd.DataFrame) -> None:
    pivot = (
        df_result.groupby(["season", "cluster_label"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )
    print("\nCluster member counts by season (≥50 required per AC):")
    print(pivot.to_string())

    below = {
        (s, lbl): n
        for (s, lbl), n in pivot.stack().items()
        if n < 50 and n > 0
    }
    missing = {
        (s, lbl)
        for s in df_result["season"].unique()
        for lbl in df_result["cluster_label"].unique()
        if lbl not in pivot.columns or pivot.loc[s, lbl] == 0
    }

    if below:
        print(f"\nWARNING: {len(below)} (season, archetype) pairs below 50-member threshold:")
        for (s, lbl), n in sorted(below.items()):
            print(f"  {s} {lbl}: {n}")
    if missing:
        print(f"\nWARNING: {len(missing)} (season, archetype) pairs absent entirely:")
        for s, lbl in sorted(missing):
            print(f"  {s} {lbl}")
    if not below and not missing:
        print("All archetypes present with ≥ 50 members in every season. ✓")


def _spot_check(df_result: pd.DataFrame, id_name_map: dict[int, str]) -> None:
    df_result = df_result.copy()
    df_result["player_name"] = df_result["pitcher_id"].map(id_name_map)
    check = df_result[df_result["player_name"].isin(_SPOT_CHECK_NAMES)][
        ["player_name", "season", "cluster_id", "cluster_label"]
    ].sort_values(["player_name", "season"])
    if check.empty:
        print("No spot-check pitchers found in data.")
    else:
        print("\nSpot-check — well-known pitchers:")
        print(check.to_string(index=False))
    print()


# ── Persistence ───────────────────────────────────────────────────────────────

def _persist(df_result: pd.DataFrame, best_score: float, fit_date: str) -> None:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_DDL)

        rows = [
            (
                int(r["pitcher_id"]),
                int(r["season"]),
                int(r["cluster_id"]),
                str(r["cluster_label"]),
                float(best_score),
                fit_date,
            )
            for _, r in df_result.iterrows()
        ]
        cur.executemany(
            """
            INSERT INTO baseball_data.statsapi.pitcher_clusters
                (pitcher_id, season, cluster_id, cluster_label, silhouette_score, fit_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        conn.commit()
        print(f"Inserted {len(rows)} rows (silhouette={best_score:.4f}, fit_date={fit_date}).")
    finally:
        conn.close()


def _save_artifacts(
    best_algo: str,
    best_k: int,
    scaler: StandardScaler,
    feature_cols: list[str],
    labels: np.ndarray,
    fit_date: str,
    model: KMeans | None,
) -> None:
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "best_algo": best_algo,
        "best_k": best_k,
        "feature_cols": feature_cols,
        "fit_date": fit_date,
    }
    joblib.dump(artifact, _MODELS_DIR / f"meta_{fit_date}.pkl")
    joblib.dump(scaler, _MODELS_DIR / f"scaler_{fit_date}.pkl")
    if model is not None:
        joblib.dump(model, _MODELS_DIR / f"kmeans_{fit_date}.pkl")
    print(f"Artifacts saved to {_MODELS_DIR}/")

    # Mirror to S3 so the Dagster image / compute_archetype_posteriors.py can load them
    # (skips silently if AWS creds are absent — see upload_artifact).
    from betting_ml.utils.artifact_store import upload_artifact
    upload_artifact(_MODELS_DIR / f"meta_{fit_date}.pkl",   f"{_S3_PREFIX}/meta_{fit_date}.pkl")
    upload_artifact(_MODELS_DIR / f"scaler_{fit_date}.pkl", f"{_S3_PREFIX}/scaler_{fit_date}.pkl")
    if model is not None:
        upload_artifact(_MODELS_DIR / f"kmeans_{fit_date}.pkl", f"{_S3_PREFIX}/kmeans_{fit_date}.pkl")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fit pitcher archetype clusters across all seasons pooled (Epic 7.2).",
    )
    p.add_argument("--min-season", type=int, default=2015, help="Earliest season to include (min 2015)")
    p.add_argument("--min-bf", type=int, default=100, help="Minimum batters-faced threshold per season")
    p.add_argument(
        "--k-range", type=int, nargs=2, default=[5, 8], metavar=("K_MIN", "K_MAX"),
        help="Range of k values to evaluate (inclusive)",
    )
    p.add_argument(
        "--algorithms", nargs="+",
        default=["kmeans", "gmm", "hierarchical"],
        choices=["kmeans", "gmm", "hierarchical"],
        help="Algorithms to compare",
    )
    p.add_argument(
        "--label-map", type=str, default=None,
        help='JSON mapping cluster_id → label. If omitted, heuristic suggestions are used.',
    )
    p.add_argument("--dry-run", action="store_true", help="Skip Snowflake writes")
    p.add_argument("--random-state", type=int, default=42)
    return p


def main() -> None:
    args = _build_parser().parse_args()
    if args.min_season < 2015:
        print("WARNING: min-season < 2015 is not supported — clamping to 2015.")
        args.min_season = 2015
    k_range = range(args.k_range[0], args.k_range[1] + 1)
    fit_date = date.today().isoformat()

    print(f"Loading pitcher profiles (min_season={args.min_season}, min_bf={args.min_bf})...")
    df_profile = _load_data(args.min_season, args.min_bf)
    print(f"  {len(df_profile)} pitcher-season rows across {df_profile['season'].nunique()} seasons")

    if df_profile.empty:
        print("ERROR: No profile data found. Has dbtf build --select mart_pitcher_profile_summary been run?")
        sys.exit(1)

    print("\nPreparing cross-season feature matrix...")
    df_clean, X_scaled, scaler, feature_cols = _prepare_features(df_profile)
    print(f"  {len(df_clean)} pitcher-seasons in feature matrix")
    print(f"  {len(feature_cols)} features: {feature_cols}")

    best_algo, best_k, best_score, best_labels = _compare_algorithms(
        X_scaled, k_range, args.algorithms, args.random_state
    )

    print(f"\nWinner: algo={best_algo}, k={best_k}, silhouette={best_score:.4f}")
    if best_score < _SILHOUETTE_WARN:
        print(
            f"WARNING: silhouette {best_score:.4f} < AC target {_SILHOUETTE_WARN}. "
            "Consider adjusting k range or feature set."
        )

    centroids = _print_centroid_summary(X_scaled, best_labels, feature_cols)

    if args.label_map:
        raw_map = json.loads(args.label_map)
        cluster_label_map = {int(k): v for k, v in raw_map.items()}
        print("\nUsing --label-map overrides:")
    else:
        cluster_label_map = _suggest_labels(centroids)
        print("\nHeuristic label suggestions (pass --label-map to override):")
    for cid, lbl in sorted(cluster_label_map.items()):
        print(f"  cluster {cid} → {lbl}")

    df_result = df_clean[["pitcher_id", "season"]].copy()
    df_result["cluster_id"] = best_labels
    df_result["cluster_label"] = df_result["cluster_id"].map(
        lambda i: cluster_label_map.get(i, "multi_pitch_mix")
    )

    print(f"\nOverall cluster distribution (n={len(df_result)}):")
    print(df_result["cluster_label"].value_counts().to_string())

    _stability_report(df_result)

    id_name_map = _load_names(df_result["pitcher_id"].tolist())
    _spot_check(df_result, id_name_map)

    refit_model = _refit_best_kmeans(X_scaled, best_algo, best_k, args.random_state)

    if args.dry_run:
        print(
            f"[dry-run] Would write {len(df_result)} rows "
            f"(algo={best_algo}, k={best_k}, silhouette={best_score:.4f}). No changes made."
        )
    else:
        _persist(df_result, best_score, fit_date)
        _save_artifacts(best_algo, best_k, scaler, feature_cols, best_labels, fit_date, refit_model)

    print("\nDone.")


if __name__ == "__main__":
    main()
