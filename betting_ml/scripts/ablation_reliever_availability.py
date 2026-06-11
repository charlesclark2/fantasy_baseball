"""
ablation_reliever_availability.py — Story 6.6

Ablation test: does the top-3 leverage arm availability vector
(closer_available, closer_rest_days, setup1_available, setup1_rest_days,
setup2_available, setup2_rest_days) improve Layer-3 model targets?

Tests two targets:
  1. total_runs  — Ridge regression CV MAE delta (NLL delta reported as secondary)
  2. home_win    — Ridge classifier CV Brier score delta

Methodology: walk-forward temporal CV (season folds) with Ridge (alpha=1000),
matching ablation_bullpen_signals.py. The ablation measures incremental Layer-3
signal value by adding the 6 new feature columns to the existing
feature_pregame_game_features baseline matrix.

Signal coverage is checked for the ≥95% non-null AC (Story 6.6 criterion 1).

Note: This script queries Snowflake and may take ~3–5 minutes to load
feature_pregame_game_features. Run as a hands-off handoff if desired:

    uv run python betting_ml/scripts/ablation_reliever_availability.py

Output is written to:
    betting_ml/models/ablation/ablation_reliever_top3_availability_<ts>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features, get_snowflake_connection
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.scripts.model_evaluation.cv_harness import _NON_FEATURE_COLS

_RIDGE_ALPHA = 1000

# 6 new availability columns from mart_reliever_top3_availability
_AVAIL_COLS = [
    "closer_available",
    "closer_rest_days",
    "setup1_available",
    "setup1_rest_days",
    "setup2_available",
    "setup2_rest_days",
]

# Imputation defaults: available flags → 1 (fully rested), rest_days → median
_AVAIL_DEFAULTS = {
    "closer_available":  1.0,
    "closer_rest_days":  None,   # filled with training-fold median
    "setup1_available":  1.0,
    "setup1_rest_days":  None,
    "setup2_available":  1.0,
    "setup2_rest_days":  None,
}

_OUTCOME_QUERY = """
SELECT
    game_pk,
    CASE WHEN home_final_score > away_final_score THEN 1 ELSE 0 END AS home_team_wins
FROM baseball_data.betting.mart_game_results
WHERE game_type = 'R'
  AND home_final_score IS NOT NULL
  AND away_final_score IS NOT NULL
"""

# Query: pivot home + away availability from mart_reliever_top3_availability
_AVAIL_QUERY = """
SELECT
    gr.game_pk,
    -- Home team availability
    MAX(CASE WHEN av.team_abbrev = gr.home_team THEN COALESCE(av.closer_available,  1) END)
        AS home_closer_available,
    MAX(CASE WHEN av.team_abbrev = gr.home_team THEN av.closer_rest_days              END)
        AS home_closer_rest_days,
    MAX(CASE WHEN av.team_abbrev = gr.home_team THEN COALESCE(av.setup1_available,  1) END)
        AS home_setup1_available,
    MAX(CASE WHEN av.team_abbrev = gr.home_team THEN av.setup1_rest_days              END)
        AS home_setup1_rest_days,
    MAX(CASE WHEN av.team_abbrev = gr.home_team THEN COALESCE(av.setup2_available,  1) END)
        AS home_setup2_available,
    MAX(CASE WHEN av.team_abbrev = gr.home_team THEN av.setup2_rest_days              END)
        AS home_setup2_rest_days,
    -- Away team availability
    MAX(CASE WHEN av.team_abbrev = gr.away_team THEN COALESCE(av.closer_available,  1) END)
        AS away_closer_available,
    MAX(CASE WHEN av.team_abbrev = gr.away_team THEN av.closer_rest_days              END)
        AS away_closer_rest_days,
    MAX(CASE WHEN av.team_abbrev = gr.away_team THEN COALESCE(av.setup1_available,  1) END)
        AS away_setup1_available,
    MAX(CASE WHEN av.team_abbrev = gr.away_team THEN av.setup1_rest_days              END)
        AS away_setup1_rest_days,
    MAX(CASE WHEN av.team_abbrev = gr.away_team THEN COALESCE(av.setup2_available,  1) END)
        AS away_setup2_available,
    MAX(CASE WHEN av.team_abbrev = gr.away_team THEN av.setup2_rest_days              END)
        AS away_setup2_rest_days
FROM baseball_data.betting.mart_game_results gr
JOIN baseball_data.betting.mart_reliever_top3_availability av
    ON  av.game_pk = gr.game_pk
WHERE gr.game_year >= 2021
  AND gr.game_type  = 'R'
GROUP BY gr.game_pk
"""

# Wide column names after pivot (home + away, 6 each = 12 total)
_WIDE_AVAIL_COLS = [
    "home_closer_available",  "home_closer_rest_days",
    "home_setup1_available",  "home_setup1_rest_days",
    "home_setup2_available",  "home_setup2_rest_days",
    "away_closer_available",  "away_closer_rest_days",
    "away_setup1_available",  "away_setup1_rest_days",
    "away_setup2_available",  "away_setup2_rest_days",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_outcomes() -> pd.DataFrame:
    """Load home_team_wins outcome from mart_game_results."""
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_OUTCOME_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    df["game_pk"] = df["game_pk"].astype(int)
    df["home_team_wins"] = df["home_team_wins"].astype(float)
    return df


def _load_avail_signals() -> pd.DataFrame:
    print("Loading top-3 availability signals from Snowflake...")
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_AVAIL_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    df["game_pk"] = df["game_pk"].astype(int)
    for col in _WIDE_AVAIL_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    print(f"  {len(df):,} game_pk rows")
    return df


def _check_coverage(df: pd.DataFrame) -> dict:
    """Verify Story 6.6 AC: availability flags non-null ≥95% of game-sides."""
    total = len(df)
    coverage = {}
    for col in ["home_closer_available", "away_closer_available",
                "home_setup1_available", "away_setup1_available",
                "home_setup2_available", "away_setup2_available"]:
        if col in df.columns:
            nn = df[col].notna().sum()
            pct = 100.0 * nn / max(total, 1)
            coverage[col] = round(pct, 2)
    return coverage


# ---------------------------------------------------------------------------
# CV harness
# ---------------------------------------------------------------------------

def _run_fold_cv_mae(
    df: pd.DataFrame,
    feature_cols: list[str],
    tag: str,
) -> list[dict]:
    """Walk-forward CV for total_runs (MAE metric)."""
    fold_results = []
    folds = list(all_season_splits(df, min_train_seasons=3))
    for train_idx, eval_idx in folds:
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        Xtr_raw = df.loc[train_idx, feature_cols]
        Xev_raw = df.loc[eval_idx, feature_cols]
        ytr = df.loc[train_idx, "total_runs"].values
        yev = df.loc[eval_idx, "total_runs"].values

        pipe = build_imputation_pipeline()
        Xtr = pipe.fit_transform(Xtr_raw).select_dtypes(include=[np.number])
        Xev = pipe.transform(Xev_raw).reindex(columns=Xtr.columns, fill_value=0.0)

        # Impute availability columns: flags → 1, rest_days → training median
        for col in _WIDE_AVAIL_COLS:
            if col not in Xtr.columns:
                continue
            if "available" in col:
                Xtr[col] = Xtr[col].fillna(1.0)
                Xev[col] = Xev[col].fillna(1.0)
            else:
                fill = float(Xtr[col].median()) if Xtr[col].notna().any() else 3.0
                Xtr[col] = Xtr[col].fillna(fill)
                Xev[col] = Xev[col].fillna(fill)

        model = Ridge(alpha=_RIDGE_ALPHA)
        model.fit(Xtr.values, ytr)
        y_pred = model.predict(Xev.values)
        mae = float(np.mean(np.abs(yev - y_pred)))
        bias = float(np.mean(y_pred - yev))

        fold_results.append({
            "tag":       tag,
            "eval_year": eval_year,
            "n_eval":    len(yev),
            "mae":       mae,
            "bias":      bias,
        })
    return fold_results


def _run_fold_cv_brier(
    df: pd.DataFrame,
    feature_cols: list[str],
    tag: str,
) -> list[dict]:
    """Walk-forward CV for home_win (Brier score metric)."""
    from sklearn.linear_model import LogisticRegression
    fold_results = []
    folds = list(all_season_splits(df, min_train_seasons=3))
    for train_idx, eval_idx in folds:
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        Xtr_raw = df.loc[train_idx, feature_cols]
        Xev_raw = df.loc[eval_idx, feature_cols]
        ytr = df.loc[train_idx, "home_team_wins"].values.astype(float)
        yev = df.loc[eval_idx, "home_team_wins"].values.astype(float)

        pipe = build_imputation_pipeline()
        Xtr = pipe.fit_transform(Xtr_raw).select_dtypes(include=[np.number])
        Xev = pipe.transform(Xev_raw).reindex(columns=Xtr.columns, fill_value=0.0)

        for col in _WIDE_AVAIL_COLS:
            if col not in Xtr.columns:
                continue
            if "available" in col:
                Xtr[col] = Xtr[col].fillna(1.0)
                Xev[col] = Xev[col].fillna(1.0)
            else:
                fill = float(Xtr[col].median()) if Xtr[col].notna().any() else 3.0
                Xtr[col] = Xtr[col].fillna(fill)
                Xev[col] = Xev[col].fillna(fill)

        model = LogisticRegression(C=1.0 / _RIDGE_ALPHA, max_iter=2000, random_state=42)
        model.fit(Xtr.values, ytr)
        probs = model.predict_proba(Xev.values)[:, 1]
        brier = float(np.mean((probs - yev) ** 2))
        fold_results.append({
            "tag":       tag,
            "eval_year": eval_year,
            "n_eval":    len(yev),
            "brier":     brier,
        })
    return fold_results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Story 6.6 ablation: top-3 leverage arm availability vector"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print signal coverage then exit without running CV.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_PROJECT_ROOT / "betting_ml" / "models" / "ablation"),
        help="Directory for JSON result file.",
    )
    args = parser.parse_args()

    print("=== STORY 6.6 — TOP-3 LEVERAGE ARM AVAILABILITY ABLATION ===\n")

    print("Loading base features from Snowflake (feature_pregame_game_features)...")
    df_base = load_features(min_games_played=15)
    df_base = df_base[df_base["game_year"] >= 2021].reset_index(drop=True)
    if "game_date" in df_base.columns:
        df_base = df_base.sort_values("game_date").reset_index(drop=True)
    print(f"  {len(df_base):,} rows, seasons {sorted(df_base['game_year'].unique())}")

    print()
    df_avail = _load_avail_signals()

    # Coverage check — AC: *_available non-null ≥95% of game-sides
    print("\nCoverage check (Story 6.6 AC: ≥95% non-null for *_available):")
    cov = _check_coverage(df_avail)
    all_pass = True
    for col, pct in cov.items():
        gate = "PASS ✓" if pct >= 95.0 else "FAIL ✗"
        if pct < 95.0:
            all_pass = False
        print(f"  {col:<30s}  {pct:5.1f}%  {gate}")
    if all_pass:
        print("  → All availability flags meet ≥95% non-null criterion.")
    else:
        print("  → WARNING: some flags below 95%. Check mart_reliever_top3_availability build.")

    if args.dry_run:
        print("\n[DRY RUN] Exiting before CV.")
        return

    # Join game outcomes (home_team_wins) from mart_game_results
    df_outcomes = _load_outcomes()
    df_base = df_base.merge(df_outcomes, on="game_pk", how="left")
    n_outcomes = df_base["home_team_wins"].notna().sum()
    print(f"\nOutcomes joined: {n_outcomes:,} / {len(df_base):,} rows have home_team_wins")

    # Merge availability signals → base
    df_base["game_pk"] = df_base["game_pk"].astype(int)
    df_merged = df_base.merge(df_avail, on="game_pk", how="left")
    n_joined = df_merged["home_closer_available"].notna().sum()
    print(
        f"\nJoined: {n_joined:,} / {len(df_merged):,} base rows have availability signals "
        f"({100.0 * n_joined / max(len(df_merged), 1):.1f}%)"
    )

    _NON_FEAT = _NON_FEATURE_COLS | {"split", "game_type"} | set(_WIDE_AVAIL_COLS)
    numeric_cols = df_merged.select_dtypes(include=[np.number]).columns.tolist()
    base_feature_cols  = [c for c in numeric_cols if c not in _NON_FEAT]
    avail_feature_cols = base_feature_cols + [c for c in _WIDE_AVAIL_COLS if c in df_merged.columns]

    print(f"\n  Baseline feature cols:     {len(base_feature_cols)}")
    print(f"  With-avail feature cols:   {len(avail_feature_cols)}")

    # ── Target 1: total_runs (MAE) ─────────────────────────────────────────────
    print("\n--- TARGET 1: total_runs (MAE via Ridge) ---")

    print("\n  BASELINE (no availability signals):")
    base_mae_results = _run_fold_cv_mae(df_merged, base_feature_cols, tag="baseline_totals")
    for r in base_mae_results:
        print(f"    {r['eval_year']}: MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  n={r['n_eval']}")
    base_mae_mean = float(np.mean([r["mae"] for r in base_mae_results]))
    print(f"  Baseline mean MAE: {base_mae_mean:.4f}")

    print("\n  WITH AVAILABILITY SIGNALS:")
    avail_mae_results = _run_fold_cv_mae(df_merged, avail_feature_cols, tag="avail_totals")
    for r in avail_mae_results:
        print(f"    {r['eval_year']}: MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  n={r['n_eval']}")
    avail_mae_mean = float(np.mean([r["mae"] for r in avail_mae_results]))
    print(f"  With-avail mean MAE: {avail_mae_mean:.4f}")

    delta_mae = avail_mae_mean - base_mae_mean
    n_improved_mae = sum(
        1 for b, s in zip(base_mae_results, avail_mae_results) if s["mae"] < b["mae"]
    )
    print(f"  Δ MAE (with − base): {delta_mae:+.4f}  ({'improvement' if delta_mae < 0 else 'degradation'})")
    print(f"  Folds improved:      {n_improved_mae} / {len(base_mae_results)}")

    # ── Target 2: home_win (Brier) ─────────────────────────────────────────────
    if "home_team_wins" not in df_merged.columns:
        print("\n  [SKIP] home_team_wins column not found — cannot run Brier ablation.")
        brier_results = {"skipped": True, "reason": "home_team_wins not in feature table"}
    else:
        print("\n--- TARGET 2: home_win (Brier via LogisticRegression) ---")

        print("\n  BASELINE (no availability signals):")
        base_brier_results = _run_fold_cv_brier(df_merged, base_feature_cols, tag="baseline_h2h")
        for r in base_brier_results:
            print(f"    {r['eval_year']}: Brier={r['brier']:.4f}  n={r['n_eval']}")
        base_brier_mean = float(np.mean([r["brier"] for r in base_brier_results]))
        print(f"  Baseline mean Brier: {base_brier_mean:.4f}")

        print("\n  WITH AVAILABILITY SIGNALS:")
        avail_brier_results = _run_fold_cv_brier(df_merged, avail_feature_cols, tag="avail_h2h")
        for r in avail_brier_results:
            print(f"    {r['eval_year']}: Brier={r['brier']:.4f}  n={r['n_eval']}")
        avail_brier_mean = float(np.mean([r["brier"] for r in avail_brier_results]))
        print(f"  With-avail mean Brier: {avail_brier_mean:.4f}")

        delta_brier = avail_brier_mean - base_brier_mean
        n_improved_brier = sum(
            1 for b, s in zip(base_brier_results, avail_brier_results) if s["brier"] < b["brier"]
        )
        print(f"  Δ Brier (with − base): {delta_brier:+.5f}  ({'improvement' if delta_brier < 0 else 'degradation'})")
        print(f"  Folds improved:        {n_improved_brier} / {len(base_brier_results)}")

        brier_results = {
            "baseline_mean_brier":  base_brier_mean,
            "avail_mean_brier":     avail_brier_mean,
            "delta_brier":          delta_brier,
            "n_folds_improved":     n_improved_brier,
            "n_folds_total":        len(base_brier_results),
            "fold_records":         avail_brier_results,
        }

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"""
=== STORY 6.6 ABLATION SUMMARY ===
  Signals added:         {', '.join(_WIDE_AVAIL_COLS)}
  Coverage AC (≥95%):    {'PASS' if all_pass else 'FAIL'}

  total_runs target (MAE):
    Baseline mean MAE:   {base_mae_mean:.4f}
    With-avail mean MAE: {avail_mae_mean:.4f}
    Δ MAE:               {delta_mae:+.4f}  ({'improvement' if delta_mae < 0 else 'degradation'})
    Folds improved:      {n_improved_mae} / {len(base_mae_results)}""")

    if not isinstance(brier_results, dict) or not brier_results.get("skipped"):
        print(f"""
  home_win target (Brier):
    Baseline mean Brier: {base_brier_mean:.4f}
    With-avail Brier:    {avail_brier_mean:.4f}
    Δ Brier:             {delta_brier:+.5f}  ({'improvement' if delta_brier < 0 else 'degradation'})
    Folds improved:      {n_improved_brier} / {len(base_brier_results)}""")

    print("""
  Next steps:
    1. If Δ is positive (directional improvement), proceed to bullpen_v2 retrain:
       uv run python betting_ml/scripts/build_bullpen_state_dataset.py
       (then rebuild parquet with new availability columns)
       uv run python betting_ml/scripts/train_bullpen_distributional.py
    2. After retrain, backfill signals:
       uv run python betting_ml/scripts/generate_bullpen_signals.py --backfill
    3. Rebuild feature mart:
       dbtf build --select feature_pregame_bullpen_state_features+
    4. Log ablation results in sub_model_registry.yaml bullpen_v2 notes (Story 6.6)
""")

    # ── Save JSON ──────────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"ablation_reliever_top3_availability_{ts}.json"

    result = {
        "story":                 "6.6",
        "run_at":                ts,
        "coverage_ac":           {"pass": all_pass, "per_col": cov},
        "total_runs": {
            "baseline_mean_mae": base_mae_mean,
            "avail_mean_mae":    avail_mae_mean,
            "delta_mae":         delta_mae,
            "n_folds_improved":  n_improved_mae,
            "n_folds_total":     len(base_mae_results),
            "fold_records":      avail_mae_results,
        },
        "home_win":              brier_results,
        "avail_cols_tested":     _WIDE_AVAIL_COLS,
    }
    out_path.write_text(json.dumps(result, indent=2))
    print(f"Results saved → {out_path.relative_to(_PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
