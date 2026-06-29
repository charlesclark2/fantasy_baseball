"""
build_matchup_training_data.py — Story 8.1: Build matchup model training dataset

Produces a 125-row dataset (25 cells × 5 seasons, 2021–2025) merging:
  - Hard MAP cell statistics from mart_pitch_play_event + batter/pitcher_clusters
    (prior-season cluster labels per leakage rule: game_year - 1)
  - Soft-weighted end-of-season snapshots from mart_batter_archetype_vs_pitcher_cluster
  - EB prior features from betting_ml/models/eb_priors/matchup_cell_priors.json (8.0 output)

Output columns:
  Identifiers:  batter_cluster_label, pitcher_cluster_label, season
  Hard MAP:     hard_n_pa, hard_xwoba_mean, hard_xwoba_std, hard_woba_mean,
                k_pct, bb_pct, hard_hit_pct
  Soft-wtd:     soft_pa_weight, soft_xwoba_mean, soft_woba_mean
  EB priors:    eb_grand_mean, eb_batter_effect, eb_pitcher_effect, eb_additive_pred,
                eb_shrunk_interaction, eb_mu_cell, eb_cell_shrinkage_factor, eb_cell_n_pa
  Derived:      raw_interaction_residual (hard_xwoba_mean - eb_additive_pred),
                cell_sparsity_flag (hard_n_pa < 200)

Output: betting_ml/models/matchup_v1/matchup_training_data.csv

Usage:
    uv run python betting_ml/scripts/eb_priors/build_matchup_training_data.py
    uv run python betting_ml/scripts/eb_priors/build_matchup_training_data.py --min-season 2021 --max-season 2024
    uv run python betting_ml/scripts/eb_priors/build_matchup_training_data.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

_EB_PRIORS_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "eb_priors" / "matchup_cell_priors.json"
_OUTPUT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "matchup_v1" / "matchup_training_data.csv"

_SPARSE_THRESHOLD = 200

# Hard MAP: join each terminal PA to prior-season cluster labels (leakage rule: game_year - 1).
# hard_hit_pct denominator = in-play events; LEFT JOIN stg_batter_pitches for exit velocity.
_HARD_MAP_SQL = """
SELECT
    bc.cluster_label  AS batter_cluster_label,
    pc.cluster_label  AS pitcher_cluster_label,
    ppe.game_year     AS season,
    COUNT(*)          AS hard_n_pa,
    ROUND(AVG(ppe.xwoba), 6)
                                                                        AS hard_xwoba_mean,
    ROUND(STDDEV(ppe.xwoba), 6)
                                                                        AS hard_xwoba_std,
    ROUND(SUM(ppe.woba_value) / NULLIF(SUM(ppe.woba_denom), 0), 6)
                                                                        AS hard_woba_mean,
    ROUND(AVG(CASE WHEN ppe.is_strikeout THEN 1.0 ELSE 0.0 END), 4)    AS k_pct,
    ROUND(AVG(CASE WHEN ppe.is_walk     THEN 1.0 ELSE 0.0 END), 4)    AS bb_pct,
    ROUND(
        SUM(CASE WHEN sbp.exit_velocity_mph >= 95 THEN 1.0 ELSE 0.0 END)
        / NULLIF(SUM(CASE WHEN ppe.is_in_play THEN 1.0 ELSE 0.0 END), 0),
    4)                                                                  AS hard_hit_pct
FROM baseball_data.betting.mart_pitch_play_event ppe
JOIN baseball_data.statsapi.batter_clusters bc
    ON  bc.batter_id = ppe.batter_id
    AND bc.season    = ppe.game_year - 1
JOIN baseball_data.statsapi.pitcher_clusters pc
    ON  pc.pitcher_id = ppe.pitcher_id
    AND pc.season     = ppe.game_year - 1
LEFT JOIN baseball_data.betting.stg_batter_pitches sbp
    ON  sbp.game_pk       = ppe.game_pk
    AND sbp.at_bat_number = ppe.at_bat_number
    AND sbp.pitch_number  = ppe.pitch_number
WHERE ppe.plate_appearance_event IS NOT NULL
  AND ppe.game_year BETWEEN %(min_season)s AND %(max_season)s
GROUP BY 1, 2, 3
ORDER BY 3, 1, 2
"""

# Soft-weighted: end-of-season snapshots (last game_date per cell per season).
# Subquery avoids QUALIFY limitation with parameterised queries.
_SOFT_SQL = """
SELECT
    batter_cluster_label,
    pitcher_cluster_label,
    YEAR(game_date)   AS season,
    pa_weight         AS soft_pa_weight,
    raw_xwoba         AS soft_xwoba_mean,
    raw_woba          AS soft_woba_mean
FROM (
    SELECT
        batter_cluster_label,
        pitcher_cluster_label,
        game_date,
        pa_weight,
        raw_xwoba,
        raw_woba,
        ROW_NUMBER() OVER (
            PARTITION BY batter_cluster_label, pitcher_cluster_label, YEAR(game_date)
            ORDER BY game_date DESC
        ) AS rn
    FROM baseball_data.betting.mart_batter_archetype_vs_pitcher_cluster
    WHERE YEAR(game_date) BETWEEN %(min_season)s AND %(max_season)s
      AND raw_xwoba IS NOT NULL
) t
WHERE rn = 1
ORDER BY season, batter_cluster_label, pitcher_cluster_label
"""


# ── E11.1-W7a lakehouse: read-on-DuckDB ───────────────────────────────────────
# `--s3` repoints the hard-MAP + soft-weighted source reads at S3 parquet via DuckDB so the
# training-data build runs off-Snowflake. There is no Snowflake write here (the only output is
# the local CSV), so --s3 is purely a read-side swap.
_S3_BUCKET = "baseball-betting-ml-artifacts"
_LAKEHOUSE = f"s3://{_S3_BUCKET}/baseball/lakehouse"

_S3_SOURCE_TABLES = [
    "mart_pitch_play_event",
    "batter_clusters",
    "pitcher_clusters",
    "stg_batter_pitches",
    "mart_batter_archetype_vs_pitcher_cluster",
]


def _get_duckdb():
    import duckdb
    duck = duckdb.connect()
    duck.execute("INSTALL httpfs; LOAD httpfs")
    duck.execute(
        "CREATE OR REPLACE SECRET baseball_s3 "
        "(TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')"
    )
    for _p in ("SET http_timeout=600000", "SET http_retries=8",
               "SET preserve_insertion_order=false"):
        try:
            duck.execute(_p)
        except Exception:
            pass
    return duck


def _register_s3_views(duck) -> None:
    for name in _S3_SOURCE_TABLES:
        glob = f"{_LAKEHOUSE}/{name}/**/*.parquet"
        duck.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{glob}', union_by_name=true)"
        )


def _duck_sql_for(sql: str) -> str:
    """Rewrite the hard/soft Snowflake source queries for DuckDB: bare-name views,
    YEAR(game_date)→year(game_date::date) (parquet game_date is VARCHAR), and the named
    %(min_season)s/%(max_season)s params are substituted as literals by the caller."""
    import re
    s = sql
    s = s.replace("baseball_data.betting.mart_pitch_play_event", "mart_pitch_play_event")
    s = s.replace("baseball_data.statsapi.batter_clusters", "batter_clusters")
    s = s.replace("baseball_data.statsapi.pitcher_clusters", "pitcher_clusters")
    s = s.replace("baseball_data.betting.stg_batter_pitches", "stg_batter_pitches")
    s = s.replace("baseball_data.betting.mart_batter_archetype_vs_pitcher_cluster",
                  "mart_batter_archetype_vs_pitcher_cluster")
    s = re.sub(r"YEAR\(\s*game_date\s*\)", "year(game_date::date)", s)
    return s


def _run_query(conn, sql: str, params: dict, duck=None) -> list[dict]:
    # E11.1-W7a: --s3 reads from S3 parquet via DuckDB (named params substituted as literal
    # ints — DuckDB execute here uses string substitution, not paramstyle).
    if duck is not None:
        s = _duck_sql_for(sql)
        s = s.replace("%(min_season)s", str(int(params["min_season"])))
        s = s.replace("%(max_season)s", str(int(params["max_season"])))
        cur = duck.execute(s)
        cols = [d[0].lower() for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def _load_eb_priors() -> dict:
    if not _EB_PRIORS_PATH.exists():
        print(f"ERROR: {_EB_PRIORS_PATH} not found. Run fit_matchup_cell_priors.py first (Story 8.0).")
        sys.exit(1)
    return json.loads(_EB_PRIORS_PATH.read_text())


def _build_dataset(
    hard_rows: list[dict],
    soft_rows: list[dict],
    eb: dict,
) -> list[dict]:
    soft_index = {
        (r["batter_cluster_label"], r["pitcher_cluster_label"], int(r["season"])): r
        for r in soft_rows
    }

    grand_mean = eb["global"]["grand_mean_xwoba"]
    batter_effects = eb["batter_effects"]
    pitcher_effects = eb["pitcher_effects"]
    cell_eb = eb["cells"]

    dataset: list[dict] = []
    for r in hard_rows:
        b = r["batter_cluster_label"]
        p = r["pitcher_cluster_label"]
        s = int(r["season"])
        n_pa = int(r["hard_n_pa"])

        b_eff = batter_effects.get(b, 0.0)
        p_eff = pitcher_effects.get(p, 0.0)
        additive_pred = round(grand_mean + b_eff + p_eff, 6)

        eb_cell = cell_eb.get(f"{b}__{p}", {})

        hard_xwoba = float(r["hard_xwoba_mean"]) if r["hard_xwoba_mean"] is not None else None
        raw_interaction = (
            round(hard_xwoba - additive_pred, 6) if hard_xwoba is not None else None
        )

        soft = soft_index.get((b, p, s), {})

        dataset.append({
            "batter_cluster_label": b,
            "pitcher_cluster_label": p,
            "season": s,
            # Hard MAP stats (prior-season cluster labels)
            "hard_n_pa": n_pa,
            "hard_xwoba_mean": hard_xwoba,
            "hard_xwoba_std": float(r["hard_xwoba_std"]) if r["hard_xwoba_std"] is not None else None,
            "hard_woba_mean": float(r["hard_woba_mean"]) if r["hard_woba_mean"] is not None else None,
            "k_pct": float(r["k_pct"]) if r["k_pct"] is not None else None,
            "bb_pct": float(r["bb_pct"]) if r["bb_pct"] is not None else None,
            "hard_hit_pct": float(r["hard_hit_pct"]) if r["hard_hit_pct"] is not None else None,
            # Soft-weighted stats (end-of-season snapshot)
            "soft_pa_weight": float(soft["soft_pa_weight"]) if soft else None,
            "soft_xwoba_mean": float(soft["soft_xwoba_mean"]) if soft else None,
            "soft_woba_mean": float(soft["soft_woba_mean"]) if soft else None,
            # EB prior features (2016–2020 calibration window)
            "eb_grand_mean": grand_mean,
            "eb_batter_effect": round(b_eff, 6),
            "eb_pitcher_effect": round(p_eff, 6),
            "eb_additive_pred": additive_pred,
            "eb_shrunk_interaction": eb_cell.get("shrunk_interaction"),
            "eb_mu_cell": eb_cell.get("mu_cell"),
            "eb_cell_shrinkage_factor": eb_cell.get("cell_shrinkage_factor"),
            "eb_cell_n_pa": eb_cell.get("cell_n_pa"),
            # Derived
            "raw_interaction_residual": raw_interaction,
            "cell_sparsity_flag": n_pa < _SPARSE_THRESHOLD,
        })

    return dataset


def _print_sparsity_report(dataset: list[dict]) -> None:
    print("\n── Cell sparsity matrix (hard MAP n_pa, totalled across all seasons) ───────")
    b_archs = sorted({r["batter_cluster_label"] for r in dataset})
    p_archs = sorted({r["pitcher_cluster_label"] for r in dataset})

    total_pa: dict[tuple, int] = {}
    for r in dataset:
        key = (r["batter_cluster_label"], r["pitcher_cluster_label"])
        total_pa[key] = total_pa.get(key, 0) + r["hard_n_pa"]

    header = f"{'':22s}" + "".join(f"{p[:14]:>16s}" for p in p_archs)
    print(header)
    sparse_cells = []
    for b in b_archs:
        row = f"{b:<22s}"
        for p in p_archs:
            n = total_pa.get((b, p), 0)
            row += f"{n:>16,}"
            if n < _SPARSE_THRESHOLD:
                sparse_cells.append((b, p, n))
        print(row)

    if sparse_cells:
        print(f"\nWARNING: {len(sparse_cells)} cell(s) below {_SPARSE_THRESHOLD} PA sparse threshold:")
        for b, p, n in sparse_cells:
            print(f"  {b}__{p}: {n:,} PA")
    else:
        print(f"\nAll 25 cells dense (> {_SPARSE_THRESHOLD} PA). cell_sparsity_flag = False for all rows.")

    seasons = sorted({r["season"] for r in dataset})
    print("\n── Per-season cell coverage ───────────────────────────────────────────────")
    for s in seasons:
        s_rows = [r for r in dataset if r["season"] == s]
        min_pa = min(r["hard_n_pa"] for r in s_rows)
        max_pa = max(r["hard_n_pa"] for r in s_rows)
        n_sparse = sum(1 for r in s_rows if r["cell_sparsity_flag"])
        print(f"  {s}: n_cells={len(s_rows):2d}  min_pa={min_pa:6,}  max_pa={max_pa:6,}  sparse={n_sparse}")


def _print_summary(dataset: list[dict]) -> None:
    seasons = sorted({r["season"] for r in dataset})
    n_cells = len(dataset) // len(seasons)
    print(f"\n── Dataset summary ─────────────────────────────────────────────────────────")
    print(f"  Rows: {len(dataset)}  ({n_cells} cells × {len(seasons)} seasons: {seasons})")

    xw = [r["hard_xwoba_mean"] for r in dataset if r["hard_xwoba_mean"] is not None]
    if xw:
        print(f"  hard_xwoba_mean: min={min(xw):.4f}  mean={sum(xw)/len(xw):.4f}  max={max(xw):.4f}")

    ri = [r["raw_interaction_residual"] for r in dataset if r["raw_interaction_residual"] is not None]
    if ri:
        print(
            f"  raw_interaction_residual: "
            f"min={min(ri):.4f}  mean={sum(ri)/len(ri):.4f}  "
            f"max={max(ri):.4f}  std={float(np.std(ri)):.4f}"
        )

    # Quick check: do EB prior predictions track observed? Show power_pull row from earliest season
    print("\n── EB prior vs. 2021 observed (power_pull cells) ───────────────────────────")
    pp = sorted(
        [r for r in dataset if r["batter_cluster_label"] == "power_pull" and r["season"] == min(seasons)],
        key=lambda x: x["pitcher_cluster_label"],
    )
    for r in pp:
        print(
            f"  power_pull__{r['pitcher_cluster_label']:<22s} "
            f"eb_mu={r['eb_mu_cell']:.4f}  "
            f"obs={r['hard_xwoba_mean']:.4f}  "
            f"Δ={r['raw_interaction_residual']:+.4f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build matchup model training dataset (Story 8.1)")
    parser.add_argument("--min-season", type=int, default=2021)
    parser.add_argument("--max-season", type=int, default=2025)
    parser.add_argument("--dry-run", action="store_true", help="Print report but do not write CSV")
    parser.add_argument("--s3", action="store_true",
                        help="E11.1-W7a: read source tables from S3 parquet via DuckDB "
                             "(no Snowflake). Output CSV path is unchanged.")
    args = parser.parse_args()

    print(f"Loading EB priors from {_EB_PRIORS_PATH.name}...")
    eb = _load_eb_priors()
    g = eb["global"]
    print(f"  grand_mean={g['grand_mean_xwoba']:.4f}  σ_interaction={g['sigma_interaction']:.4f}  k_ratio={g['k_ratio']:.0f}")

    params = {"min_season": args.min_season, "max_season": args.max_season}
    conn = None
    duck = None
    if args.s3:
        print(f"\n[--s3] Reading sources from S3 lakehouse via DuckDB ({args.min_season}–{args.max_season})...")
        duck = _get_duckdb()
        _register_s3_views(duck)
    else:
        print(f"\nQuerying Snowflake ({args.min_season}–{args.max_season})...")
        conn = get_snowflake_connection()
    try:
        print("  Running hard MAP query (mart_pitch_play_event + batter/pitcher_clusters)...")
        hard_rows = _run_query(conn, _HARD_MAP_SQL, params, duck=duck)
        print(f"  {len(hard_rows)} rows")

        print("  Running soft-weighted query (mart_batter_archetype_vs_pitcher_cluster)...")
        soft_rows = _run_query(conn, _SOFT_SQL, params, duck=duck)
        print(f"  {len(soft_rows)} rows")
    finally:
        if conn is not None:
            conn.close()
        if duck is not None:
            duck.close()

    if not hard_rows:
        print("ERROR: no hard MAP rows. Check batter_clusters/pitcher_clusters have prior-season coverage (game_year - 1).")
        sys.exit(1)
    if not soft_rows:
        print("WARNING: no soft-weighted rows. Has mart_batter_archetype_vs_pitcher_cluster been rebuilt from 2016?")

    print("\nBuilding training dataset...")
    dataset = _build_dataset(hard_rows, soft_rows, eb)
    print(f"  {len(dataset)} rows built")

    _print_sparsity_report(dataset)
    _print_summary(dataset)

    if args.dry_run:
        print(f"\n[dry-run] Would write to {_OUTPUT_PATH}. No file written.")
    else:
        _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(dataset[0].keys())
        with _OUTPUT_PATH.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(dataset)
        print(f"\nWrote {_OUTPUT_PATH}")
        print(f"  Columns ({len(fieldnames)}): {', '.join(fieldnames)}")


if __name__ == "__main__":
    main()
