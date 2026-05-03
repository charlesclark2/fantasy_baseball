"""Card 7.K supplementary — Pitcher cluster stability analysis.

Measures how many pitches per pitcher are needed before k-means cluster
assignments stabilize relative to the full-season baseline.

For each pitch-count threshold the script:
  1. Draws N_BOOTSTRAP random game-order replicates per pitcher, keeping
     games until the cumulative pitch count hits the threshold.
  2. Re-aggregates those games into pitcher-season arsenal features.
  3. Fits k-means with the same k chosen for the full-season baseline.
  4. Computes Adjusted Rand Index (ARI) between the subsample assignments
     and the full-season baseline assignments.

ARI is invariant to label permutation (random cluster IDs), so it
correctly measures agreement even when cluster numbering differs between
runs.

Output:
  - Console table: threshold → mean ARI ± std, pitcher coverage %
  - PNG plot saved to betting_ml/evaluation/cluster_stability_{season}.png

Usage:
    uv run python betting_ml/scripts/pitcher_clustering/cluster_stability_analysis.py --season 2024
    uv run python betting_ml/scripts/pitcher_clustering/cluster_stability_analysis.py --season 2024 --n-bootstrap 30
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.scripts.pitcher_clustering.cluster_pitchers import (
    FEATURE_COLS,
    _fit_clusters,
    _prepare_features,
)

_EVAL_DIR = PROJECT_ROOT / "betting_ml" / "evaluation"

THRESHOLDS = [50, 75, 100, 150, 200, 300, 500, 750, 1000]

_GAME_QUERY = """
SELECT
    pitcher_id,
    game_pk,
    game_date::date   AS game_date,
    game_year,
    pitch_category,
    COUNT(*)          AS pitch_count,
    AVG(release_speed_mph)          AS avg_velocity,
    AVG(pitch_movement_x_ft)        AS avg_hmov,
    AVG(pitch_movement_z_ft)        AS avg_vmov,
    AVG(release_spin_rate_rpm)      AS avg_spin,
    AVG(release_pos_z_ft)           AS avg_release_height,
    AVG(release_pos_x_ft)           AS avg_release_side,
    AVG(release_extension_ft)       AS avg_extension,
    AVG(pitcher_arm_angle_degrees)  AS avg_arm_angle
FROM baseball_data.betting.mart_pitch_characteristics
WHERE game_year = {season}
  AND pitch_category IN ('fastball', 'breaking', 'offspeed')
GROUP BY pitcher_id, game_pk, game_date, game_year, pitch_category
"""

_STUFF_QUERY = """
SELECT pitcher_id, overall_stuff_plus
FROM baseball_data.betting.mart_pitcher_arsenal_summary
WHERE game_year = {season}
"""


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_game_data(season: int) -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_GAME_QUERY.format(season=season))
        rows = cur.fetchall()
        columns = [d[0].lower() for d in cur.description]
        return pd.DataFrame(rows, columns=columns)
    finally:
        conn.close()


def _load_stuff_plus(season: int) -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_STUFF_QUERY.format(season=season))
        rows = cur.fetchall()
        columns = [d[0].lower() for d in cur.description]
        return pd.DataFrame(rows, columns=columns)
    finally:
        conn.close()


# ── Feature aggregation ───────────────────────────────────────────────────────

def _weighted_cat_agg(game_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-game-per-category rows to pitcher × category level using
    pitch-count-weighted averages."""
    metric_cols = [
        "avg_velocity", "avg_hmov", "avg_vmov", "avg_spin",
        "avg_release_height", "avg_release_side", "avg_extension", "avg_arm_angle",
    ]

    def _wagg(g: pd.DataFrame) -> pd.Series:
        w = g["pitch_count"].values
        out: dict = {"pitch_count": w.sum()}
        for col in metric_cols:
            valid = g[col].notna()
            if valid.any():
                out[col] = float(np.average(g.loc[valid, col], weights=w[valid.values]))
            else:
                out[col] = np.nan
        return pd.Series(out)

    return (
        game_df
        .groupby(["pitcher_id", "pitch_category"], sort=False)
        .apply(_wagg)
        .reset_index()
    )


def _aggregate_to_pitcher_season(game_df: pd.DataFrame) -> pd.DataFrame:
    """Convert per-game-per-category rows into the pitcher-season wide feature
    format expected by _prepare_features / FEATURE_COLS."""
    season = int(game_df["game_year"].iloc[0])
    cat_agg = _weighted_cat_agg(game_df)

    totals = (
        cat_agg.groupby("pitcher_id")["pitch_count"]
        .sum()
        .rename("total_pitches")
        .reset_index()
    )

    # Column rename map: (pitch_category, raw_col) → final_col
    rename_map: dict[tuple[str, str], str] = {
        ("fastball", "avg_velocity"):      "fb_avg_velocity",
        ("fastball", "avg_hmov"):          "fb_avg_hmov",
        ("fastball", "avg_vmov"):          "fb_avg_vmov",
        ("fastball", "avg_spin"):          "fb_avg_spin",
        ("fastball", "avg_release_height"):"fb_release_height",
        ("fastball", "avg_release_side"):  "fb_release_side",
        ("fastball", "avg_extension"):     "fb_extension",
        ("fastball", "avg_arm_angle"):     "fb_arm_angle",
        ("breaking", "avg_velocity"):      "brk_avg_velocity",
        ("breaking", "avg_hmov"):          "brk_avg_hmov",
        ("breaking", "avg_vmov"):          "brk_avg_vmov",
        ("breaking", "avg_spin"):          "brk_avg_spin",
        ("offspeed", "avg_velocity"):      "os_avg_velocity",
    }

    result = totals.copy()
    for cat in ("fastball", "breaking", "offspeed"):
        sub = cat_agg[cat_agg["pitch_category"] == cat].copy()
        if sub.empty:
            continue
        keep_cols = {col for (c, col) in rename_map if c == cat}
        sub = sub[["pitcher_id", "pitch_count"] + list(keep_cols)].copy()
        sub = sub.rename(columns={col: rename_map[(cat, col)] for col in keep_cols})
        sub = sub.rename(columns={"pitch_count": f"{cat}_pitch_count"})
        result = result.merge(sub, on="pitcher_id", how="left")

    for cat in ("fastball", "breaking", "offspeed"):
        count_col = f"{cat}_pitch_count"
        pct_col = f"{cat}_pct"
        if count_col in result.columns:
            result[pct_col] = result[count_col] / result["total_pitches"]
            result = result.drop(columns=[count_col])
        else:
            result[pct_col] = 0.0

    # Align to the column names _prepare_features expects
    result = result.rename(columns={
        "fastball_pct": "fastball_pct",
        "breaking_pct": "breaking_pct",
        "offspeed_pct": "offspeed_pct",
    })
    result["season"] = season
    return result


def _attach_derived(pitcher_df: pd.DataFrame, stuff_df: pd.DataFrame) -> pd.DataFrame:
    """Join Stuff+, derive spin_diff and pitch_entropy."""
    df = pitcher_df.merge(
        stuff_df[["pitcher_id", "overall_stuff_plus"]], on="pitcher_id", how="left"
    )
    df["overall_stuff_plus"] = df["overall_stuff_plus"].fillna(100.0)
    df["spin_diff"] = df["brk_avg_spin"] - df["fb_avg_spin"]

    def _entropy(row: pd.Series) -> float:
        probs = [
            p for col in ("fastball_pct", "breaking_pct", "offspeed_pct")
            if pd.notna(p := row.get(col, np.nan)) and p > 0
        ]
        return -sum(p * np.log(p) for p in probs) if probs else 0.0

    df["pitch_entropy"] = df.apply(_entropy, axis=1)
    return df


# ── Subsampling ───────────────────────────────────────────────────────────────

def _subsample_games(
    game_df: pd.DataFrame,
    threshold: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """For each pitcher, shuffle game order and retain games until cumulative
    pitch count first equals or exceeds *threshold*.  Always keeps at least
    one game so pitchers with fewer than threshold pitches still contribute."""
    parts: list[pd.DataFrame] = []
    for pid, grp in game_df.groupby("pitcher_id", sort=False):
        game_totals = (
            grp.groupby("game_pk")["pitch_count"]
            .sum()
            .reset_index()
            .sample(frac=1, random_state=int(rng.integers(0, 1_000_000)))
        )
        game_totals["cumsum"] = game_totals["pitch_count"].cumsum()
        # Keep all games up to and including the one that first meets threshold
        cutoff = game_totals["cumsum"].searchsorted(threshold, side="left")
        cutoff = min(cutoff, len(game_totals) - 1)
        included = game_totals.iloc[: cutoff + 1]["game_pk"]
        parts.append(grp[grp["game_pk"].isin(included)])
    return pd.concat(parts, ignore_index=True)


# ── Clustering with fixed k ───────────────────────────────────────────────────

def _cluster_fixed_k(
    df: pd.DataFrame,
    k: int,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Scale features, fit KMeans with fixed k.
    Returns (pitcher_ids, cluster_labels) for rows that survive null filtering."""
    X = df[FEATURE_COLS].copy()
    null_frac = X.isnull().mean(axis=1)
    mask = null_frac <= 0.30
    df_clean = df[mask].copy()
    X = X[mask].copy()
    for col in X.columns:
        X[col] = X[col].fillna(X[col].median())

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
    labels = km.fit_predict(X_scaled)
    return df_clean["pitcher_id"].values, labels


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pitcher cluster stability analysis — ARI vs. pitch-count threshold."
    )
    parser.add_argument("--season", type=int, required=True, help="Season to analyse (needs full data in mart)")
    parser.add_argument("--n-bootstrap", type=int, default=20, help="Bootstrap replicates per threshold")
    parser.add_argument("--min-k", type=int, default=4)
    parser.add_argument("--max-k", type=int, default=10)
    args = parser.parse_args()

    print(f"Loading per-game pitch data for {args.season}...")
    game_df = _load_game_data(args.season)
    print(f"  {len(game_df):,} pitcher-game-category rows loaded.")

    if game_df.empty:
        print("ERROR: no pitch data found. Has dbt build been run for this season?")
        sys.exit(1)

    print("Loading Stuff+ from mart...")
    stuff_df = _load_stuff_plus(args.season)

    # ── Full-season baseline ──────────────────────────────────────────────────
    print("\nBuilding full-season baseline clusters...")
    full_pitcher = _aggregate_to_pitcher_season(game_df)
    full_pitcher = _attach_derived(full_pitcher, stuff_df)
    _, X_full, _ = _prepare_features(full_pitcher)

    print(f"Searching k={args.min_k}..{args.max_k} for full-season baseline:")
    _, best_k, best_score = _fit_clusters(X_full, args.min_k, args.max_k)
    print(f"  → best_k={best_k}, silhouette={best_score:.4f}, pitchers={len(full_pitcher)}")

    full_ids, full_labels = _cluster_fixed_k(full_pitcher, k=best_k)
    full_label_map: dict[int, int] = dict(zip(full_ids.tolist(), full_labels.tolist()))

    # ── Bootstrap stability loop ──────────────────────────────────────────────
    print(f"\nRunning {args.n_bootstrap} bootstrap replicates per threshold...\n")
    rng = np.random.default_rng(42)
    rows: list[dict] = []

    for threshold in THRESHOLDS:
        aris: list[float] = []
        coverages: list[float] = []

        for rep in range(args.n_bootstrap):
            sub_game = _subsample_games(game_df, threshold, rng)
            sub_pitcher = _aggregate_to_pitcher_season(sub_game)
            sub_pitcher = _attach_derived(sub_pitcher, stuff_df)

            if len(sub_pitcher) < best_k + 1:
                continue

            try:
                sub_ids, sub_labels = _cluster_fixed_k(sub_pitcher, k=best_k, random_state=rep)
            except Exception:
                continue

            # ARI on the intersection of pitchers present in both runs
            common = sorted(set(full_label_map) & set(sub_ids.tolist()))
            if len(common) < 10:
                continue

            sub_map: dict[int, int] = dict(zip(sub_ids.tolist(), sub_labels.tolist()))
            y_full = np.array([full_label_map[p] for p in common])
            y_sub  = np.array([sub_map[p] for p in common])

            aris.append(adjusted_rand_score(y_full, y_sub))
            coverages.append(len(common) / len(full_label_map))

        if not aris:
            print(f"  threshold={threshold:5d}: insufficient data — skipped")
            continue

        mean_ari = float(np.mean(aris))
        std_ari  = float(np.std(aris))
        mean_cov = float(np.mean(coverages))

        rows.append({
            "threshold":     threshold,
            "mean_ari":      mean_ari,
            "std_ari":       std_ari,
            "min_ari":       float(np.min(aris)),
            "max_ari":       float(np.max(aris)),
            "mean_coverage": mean_cov,
        })
        print(
            f"  threshold={threshold:5d} pitches │ "
            f"ARI={mean_ari:.3f} ± {std_ari:.3f} "
            f"[{np.min(aris):.3f}–{np.max(aris):.3f}] │ "
            f"coverage={mean_cov*100:.1f}%"
        )

    if not rows:
        print("ERROR: no results produced.")
        sys.exit(1)

    results = pd.DataFrame(rows)

    print("\n── Stability summary (k={}) ──".format(best_k))
    print(results.to_string(index=False, float_format="{:.3f}".format))

    # Recommended threshold: first point where mean ARI ≥ 0.75
    stable = results[results["mean_ari"] >= 0.75]
    if not stable.empty:
        rec = int(stable.iloc[0]["threshold"])
        print(f"\nRecommended minimum pitch threshold: {rec} (first threshold with mean ARI ≥ 0.75)")
    else:
        best_row = results.loc[results["mean_ari"].idxmax()]
        print(
            f"\nNo threshold reached ARI ≥ 0.75. "
            f"Best was {best_row['mean_ari']:.3f} at threshold={int(best_row['threshold'])}."
        )

    # ── Plot ──────────────────────────────────────────────────────────────────
    _EVAL_DIR.mkdir(parents=True, exist_ok=True)

    fig, ax1 = plt.subplots(figsize=(11, 6))

    ax1.plot(results["threshold"], results["mean_ari"], "b-o", lw=2, label="Mean ARI")
    ax1.fill_between(
        results["threshold"],
        results["mean_ari"] - results["std_ari"],
        results["mean_ari"] + results["std_ari"],
        alpha=0.20, color="blue", label="±1 std",
    )
    ax1.fill_between(
        results["threshold"],
        results["min_ari"],
        results["max_ari"],
        alpha=0.08, color="blue", label="min–max range",
    )
    ax1.axhline(0.75, color="orange", linestyle="--", lw=1.5, alpha=0.8, label="ARI = 0.75")
    ax1.axhline(0.85, color="green",  linestyle="--", lw=1.5, alpha=0.8, label="ARI = 0.85")
    ax1.set_xlabel("Minimum pitches per pitcher (threshold)", fontsize=12)
    ax1.set_ylabel("Adjusted Rand Index (vs. full-season clusters)", color="blue", fontsize=12)
    ax1.set_ylim(-0.05, 1.05)
    ax1.set_title(
        f"Pitcher Cluster Stability — {args.season} season  "
        f"(best_k={best_k}, n_bootstrap={args.n_bootstrap})",
        fontsize=13,
    )

    ax2 = ax1.twinx()
    ax2.plot(
        results["threshold"], results["mean_coverage"] * 100,
        "r--s", alpha=0.55, lw=1.5, label="Pitcher coverage %",
    )
    ax2.set_ylabel("% of full-season pitchers included", color="red", fontsize=12)
    ax2.set_ylim(0, 108)

    lines1, lbls1 = ax1.get_legend_handles_labels()
    lines2, lbls2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, lbls1 + lbls2, loc="lower right", fontsize=10)

    out_path = _EVAL_DIR / f"cluster_stability_{args.season}.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"\nPlot saved → {out_path}")
    print("Done.")


if __name__ == "__main__":
    main()
