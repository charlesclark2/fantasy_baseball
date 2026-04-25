"""Card 4.13 — Bayesian probability layer pipeline.

CV α tuning on has_odds historical games, final 2026 predictions, parquet output,
and Snowflake persistence.

Run from project root:
    uv run python betting_ml/scripts/run_probability_layer.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import load_features, get_snowflake_connection
from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.probability_layer import (
    compute_posterior,
    compute_edge,
    compute_kelly,
    tune_alpha,
)
from betting_ml.models.total_runs_trainer import train_ngboost, p_over_line


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_ngb_cfg(path: str, target_label: str) -> tuple[int, str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"NGBoost tuning results not found: {path}. "
            f"Run Card 4.12d/4.12e hyperparameter search first."
        )
    with open(p) as f:
        cfg = json.load(f)
    for key in ("best_n_estimators", "best_dist"):
        if key not in cfg:
            raise KeyError(
                f"Required key '{key}' missing from {path} ({target_label} config)."
            )
    return int(cfg["best_n_estimators"]), str(cfg["best_dist"])


def _align(X_train_imp: pd.DataFrame, X_eval_imp: pd.DataFrame) -> pd.DataFrame:
    return X_eval_imp.reindex(columns=X_train_imp.columns, fill_value=0.0)


def _impute(
    X_train_raw: pd.DataFrame, X_eval_raw: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pipeline = build_imputation_pipeline()
    X_train_imp = pipeline.fit_transform(X_train_raw)
    X_eval_imp = pipeline.transform(X_eval_raw)
    X_train_imp = X_train_imp.select_dtypes(include=[np.number])
    X_eval_imp = X_eval_imp[[c for c in X_train_imp.columns if c in X_eval_imp.columns]]
    X_eval_imp = _align(X_train_imp, X_eval_imp)
    return X_train_imp, X_eval_imp, pipeline


def _create_snowflake_tables(cur) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.probability_outputs (
            game_key        VARCHAR,
            market          VARCHAR,
            model_prob      FLOAT,
            market_implied_prob FLOAT,
            alpha           FLOAT,
            posterior_prob  FLOAT,
            edge            FLOAT,
            implied_kelly_fraction FLOAT,
            loaded_at       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.alpha_tuning_results (
            alpha       FLOAT,
            log_loss    FLOAT,
            loaded_at   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.probability_layer_summary (
            n_tuning_games          INTEGER,
            best_alpha              FLOAT,
            small_sample_warning    BOOLEAN,
            h2h_mean_edge           FLOAT,
            totals_mean_edge        FLOAT,
            h2h_positive_edge_pct   FLOAT,
            totals_positive_edge_pct FLOAT,
            n_games_2026_with_odds  INTEGER,
            n_output_rows           INTEGER,
            loaded_at               TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
        )
    """)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # --- Load data ---
    print("Loading features from Snowflake...")
    df = load_features()
    print(f"  Loaded {len(df):,} rows, {len(df.columns)} columns")

    for required_col in ("has_odds", "home_win_prob_consensus", "over_prob_consensus"):
        if required_col not in df.columns:
            raise ValueError(
                f"Required column '{required_col}' not found in feature DataFrame. "
                f"Ensure the mart_odds_consensus features are loaded (Card 4.7)."
            )

    feature_cols = load_retained_features()
    missing_features = [c for c in feature_cols if c not in df.columns]
    if missing_features:
        print(f"  Warning: {len(missing_features)} retained features not in df, will be ignored: {missing_features[:5]}")
        feature_cols = [c for c in feature_cols if c in df.columns]

    X = df[feature_cols]
    y_runs = df["total_runs"]
    y_diff = df["run_differential"]

    # --- Load NGBoost hyperparameters ---
    ngb_tot_n_est, ngb_tot_dist = _load_ngb_cfg(
        "betting_ml/evaluation/tuning_results_ngboost_total_runs.json",
        "total_runs",
    )
    ngb_diff_n_est, ngb_diff_dist = _load_ngb_cfg(
        "betting_ml/evaluation/tuning_results_ngboost_run_diff.json",
        "run_differential",
    )
    print(f"  NGBoost total_runs: n_estimators={ngb_tot_n_est}, dist={ngb_tot_dist}")
    print(f"  NGBoost run_diff:   n_estimators={ngb_diff_n_est}, dist={ngb_diff_dist}")

    # --- CV α tuning loop ---
    print("\nRunning CV α tuning loop...")
    h2h_model_probs_all: list[float] = []
    h2h_market_probs_all: list[float] = []
    h2h_outcomes_all: list[int] = []

    totals_model_probs_all: list[float] = []
    totals_market_probs_all: list[float] = []
    totals_outcomes_all: list[int] = []

    folds = list(all_season_splits(df, min_train_seasons=3))
    print(f"  {len(folds)} CV folds")

    for fold_num, (train_idx, eval_idx) in enumerate(folds):
        eval_year = int(df.loc[eval_idx, "game_year"].iloc[0])
        print(f"  Fold {fold_num + 1}/{len(folds)} (eval_year={eval_year})...", end=" ", flush=True)

        X_train_raw = X.loc[train_idx]
        X_eval_raw = X.loc[eval_idx]
        X_train_imp, X_eval_imp, _ = _impute(X_train_raw, X_eval_raw)

        y_runs_train = y_runs.loc[train_idx]
        y_diff_train = y_diff.loc[train_idx]

        # --- Total runs NGBoost ---
        ngb_tot_result = train_ngboost(
            X_train_imp, y_runs_train, X_eval_imp,
            dist=ngb_tot_dist, n_estimators=ngb_tot_n_est,
        )
        total_line_vals = df.loc[eval_idx, "total_line_consensus"].values
        p_over_total = p_over_line(ngb_tot_dist, ngb_tot_result["dist_params"], total_line=total_line_vals)

        # --- Run diff NGBoost ---
        ngb_diff_result = train_ngboost(
            X_train_imp, y_diff_train, X_eval_imp,
            dist=ngb_diff_dist, n_estimators=ngb_diff_n_est,
        )
        p_home_win = p_over_line(ngb_diff_dist, ngb_diff_result["dist_params"], total_line=0)

        # --- Filter to has_odds=True rows ---
        eval_has_odds = df.loc[eval_idx, "has_odds"].fillna(False).astype(bool)
        eval_h2h_mask = eval_has_odds & df.loc[eval_idx, "home_win_prob_consensus"].notna()

        qualifying_idx = eval_idx[eval_h2h_mask.values]
        qualifying_local_mask = eval_h2h_mask.values

        if qualifying_local_mask.sum() == 0:
            print(f"no qualifying h2h rows, skipping")
            continue

        # h2h tuning accumulation
        market_home_prob = df.loc[qualifying_idx, "home_win_prob_consensus"].values.astype(float)
        model_home_win = p_home_win[qualifying_local_mask]
        outcomes_h2h = df.loc[qualifying_idx, "home_win"].astype(int).values

        h2h_model_probs_all.extend(model_home_win.tolist())
        h2h_market_probs_all.extend(market_home_prob.tolist())
        h2h_outcomes_all.extend(outcomes_h2h.tolist())

        # totals tuning accumulation
        totals_mask_local = (
            eval_has_odds & df.loc[eval_idx, "over_prob_consensus"].notna()
        ).values
        totals_local_idx = eval_idx[totals_mask_local]

        if totals_mask_local.sum() > 0:
            market_over_prob = df.loc[totals_local_idx, "over_prob_consensus"].values.astype(float)
            model_over = p_over_total[totals_mask_local]
            actual_over = (
                df.loc[totals_local_idx, "total_runs"] > df.loc[totals_local_idx, "total_line_consensus"]
            ).astype(int).values

            totals_model_probs_all.extend(model_over.tolist())
            totals_market_probs_all.extend(market_over_prob.tolist())
            totals_outcomes_all.extend(actual_over.tolist())

        print(f"h2h={qualifying_local_mask.sum()}, totals={totals_mask_local.sum()}")

    # --- Tune α using combined h2h + totals data ---
    combined_model = np.array(h2h_model_probs_all + totals_model_probs_all)
    combined_market = np.array(h2h_market_probs_all + totals_market_probs_all)
    combined_outcomes = np.array(h2h_outcomes_all + totals_outcomes_all)
    n_tuning_games = len(combined_model)

    print(f"\nα tuning on {n_tuning_games:,} total has_odds eval records...")
    small_sample_warning = n_tuning_games < 100
    best_alpha, alpha_scores = tune_alpha(combined_model, combined_market, combined_outcomes)

    print(f"\n{'α':>6} | {'Log-Loss':>10} | {'Δ vs best':>10}")
    print("-" * 32)
    best_ll = min(r["log_loss"] for r in alpha_scores)
    for r in alpha_scores:
        delta = r["log_loss"] - best_ll
        marker = " ← best" if abs(delta) < 1e-10 else ""
        print(f"{r['alpha']:>6.1f} | {r['log_loss']:>10.6f} | {delta:>10.6f}{marker}")
    print(f"\nSelected best_alpha = {best_alpha}")

    # --- Final predictions on 2026 has_odds games ---
    print("\nBuilding final 2026 predictions...")
    mask_pre2026 = df["game_year"] < 2026
    mask_2026 = df["game_year"] == 2026

    X_train_final_raw = X[mask_pre2026]
    X_2026_raw = X[mask_2026]

    if len(X_2026_raw) == 0:
        print("Warning: no 2026 rows found. Writing empty parquet.")
        _write_empty_parquet()
        _write_snowflake_results(
            output_rows=[], alpha_scores=alpha_scores,
            n_tuning_games=n_tuning_games, best_alpha=best_alpha,
            small_sample_warning=small_sample_warning,
        )
        return

    X_train_final_imp, X_2026_imp, final_pipeline = _impute(X_train_final_raw, X_2026_raw)

    y_runs_pretrain = y_runs[mask_pre2026]
    y_diff_pretrain = y_diff[mask_pre2026]

    ngb_tot_final = train_ngboost(
        X_train_final_imp, y_runs_pretrain, X_2026_imp,
        dist=ngb_tot_dist, n_estimators=ngb_tot_n_est,
    )
    ngb_diff_final = train_ngboost(
        X_train_final_imp, y_diff_pretrain, X_2026_imp,
        dist=ngb_diff_dist, n_estimators=ngb_diff_n_est,
    )

    idx_2026 = df.index[mask_2026]
    total_line_2026 = df.loc[idx_2026, "total_line_consensus"].values
    p_over_total_2026 = p_over_line(ngb_tot_dist, ngb_tot_final["dist_params"], total_line=total_line_2026)
    p_home_win_2026 = p_over_line(ngb_diff_dist, ngb_diff_final["dist_params"], total_line=0)

    # --- Build output rows ---
    output_rows: list[dict] = []

    has_odds_2026 = df.loc[idx_2026, "has_odds"].fillna(False).astype(bool).values
    h2h_mkt_2026 = df.loc[idx_2026, "home_win_prob_consensus"].values
    over_mkt_2026 = df.loc[idx_2026, "over_prob_consensus"].values

    for i, gidx in enumerate(idx_2026):
        if not has_odds_2026[i]:
            continue

        game_key = str(gidx)
        if "game_pk" in df.columns:
            game_key = str(df.loc[gidx, "game_pk"])

        # h2h market
        if pd.notna(h2h_mkt_2026[i]):
            mp = float(p_home_win_2026[i])
            mkt = float(h2h_mkt_2026[i])
            edge = compute_edge(mp, mkt)
            output_rows.append({
                "game_key": game_key,
                "market": "h2h",
                "model_prob": mp,
                "market_implied_prob": mkt,
                "alpha": best_alpha,
                "posterior_prob": compute_posterior(mp, mkt, best_alpha),
                "edge": edge,
                "implied_kelly_fraction": compute_kelly(edge, mkt),
            })

        # totals market
        if pd.notna(over_mkt_2026[i]):
            mp = float(p_over_total_2026[i])
            mkt = float(over_mkt_2026[i])
            edge = compute_edge(mp, mkt)
            output_rows.append({
                "game_key": game_key,
                "market": "totals",
                "model_prob": mp,
                "market_implied_prob": mkt,
                "alpha": best_alpha,
                "posterior_prob": compute_posterior(mp, mkt, best_alpha),
                "edge": edge,
                "implied_kelly_fraction": compute_kelly(edge, mkt),
            })

    n_games_2026_with_odds = int(has_odds_2026.sum())
    n_output_rows = len(output_rows)
    print(f"  2026 has_odds games: {n_games_2026_with_odds}, output rows: {n_output_rows}")

    if n_output_rows == 0:
        print("Warning: no qualifying 2026 rows (has_odds=True and market prob not null). Writing empty parquet.")
        _write_empty_parquet()
    else:
        output_df = pd.DataFrame(output_rows)
        out_dir = PROJECT_ROOT / "betting_ml" / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "probability_outputs.parquet"
        output_df.to_parquet(out_path, index=False)
        print(f"  Wrote {out_path}")

    # --- Summary stats ---
    h2h_rows = [r for r in output_rows if r["market"] == "h2h"]
    tot_rows = [r for r in output_rows if r["market"] == "totals"]

    def _mean_edge(rows): return float(np.mean([r["edge"] for r in rows])) if rows else 0.0
    def _pct_pos(rows): return float(np.mean([r["edge"] > 0 for r in rows])) * 100 if rows else 0.0
    def _mean_kelly(rows): return float(np.mean([r["implied_kelly_fraction"] for r in rows])) if rows else 0.0

    h2h_mean_edge = _mean_edge(h2h_rows)
    totals_mean_edge = _mean_edge(tot_rows)
    h2h_pos_pct = _pct_pos(h2h_rows)
    totals_pos_pct = _pct_pos(tot_rows)

    print(f"\n{'Market':<10} | {'N Games':>8} | {'Mean Edge':>10} | {'% Pos Edge':>11} | {'Mean Kelly':>10}")
    print("-" * 60)
    print(f"{'h2h':<10} | {len(h2h_rows):>8} | {h2h_mean_edge:>10.4f} | {h2h_pos_pct:>10.1f}% | {_mean_kelly(h2h_rows):>10.4f}")
    print(f"{'totals':<10} | {len(tot_rows):>8} | {totals_mean_edge:>10.4f} | {totals_pos_pct:>10.1f}% | {_mean_kelly(tot_rows):>10.4f}")

    _write_snowflake_results(
        output_rows=output_rows,
        alpha_scores=alpha_scores,
        n_tuning_games=n_tuning_games,
        best_alpha=best_alpha,
        small_sample_warning=small_sample_warning,
        h2h_mean_edge=h2h_mean_edge,
        totals_mean_edge=totals_mean_edge,
        h2h_positive_edge_pct=h2h_pos_pct,
        totals_positive_edge_pct=totals_pos_pct,
        n_games_2026_with_odds=n_games_2026_with_odds,
        n_output_rows=n_output_rows,
    )

    print("\nDone.")


def _write_empty_parquet() -> None:
    empty = pd.DataFrame(columns=[
        "game_key", "market", "model_prob", "market_implied_prob",
        "alpha", "posterior_prob", "edge", "implied_kelly_fraction",
    ])
    out_dir = PROJECT_ROOT / "betting_ml" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    empty.to_parquet(out_dir / "probability_outputs.parquet", index=False)
    print("  Wrote empty probability_outputs.parquet")


def _write_snowflake_results(
    output_rows: list[dict],
    alpha_scores: list[dict],
    n_tuning_games: int,
    best_alpha: float,
    small_sample_warning: bool,
    h2h_mean_edge: float = 0.0,
    totals_mean_edge: float = 0.0,
    h2h_positive_edge_pct: float = 0.0,
    totals_positive_edge_pct: float = 0.0,
    n_games_2026_with_odds: int = 0,
    n_output_rows: int = 0,
) -> None:
    print("\nWriting results to Snowflake...")
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        _create_snowflake_tables(cur)

        # probability_outputs
        cur.execute("TRUNCATE TABLE baseball_data.betting_ml.probability_outputs")
        if output_rows:
            rows_sql = ", ".join(
                f"('{r['game_key']}', '{r['market']}', {r['model_prob']}, "
                f"{r['market_implied_prob']}, {r['alpha']}, {r['posterior_prob']}, "
                f"{r['edge']}, {r['implied_kelly_fraction']})"
                for r in output_rows
            )
            cur.execute(
                f"INSERT INTO baseball_data.betting_ml.probability_outputs "
                f"(game_key, market, model_prob, market_implied_prob, alpha, "
                f"posterior_prob, edge, implied_kelly_fraction) VALUES {rows_sql}"
            )
        print(f"  probability_outputs: {len(output_rows)} rows")

        # alpha_tuning_results
        cur.execute("TRUNCATE TABLE baseball_data.betting_ml.alpha_tuning_results")
        alpha_rows_sql = ", ".join(
            f"({r['alpha']}, {r['log_loss']})" for r in alpha_scores
        )
        cur.execute(
            f"INSERT INTO baseball_data.betting_ml.alpha_tuning_results "
            f"(alpha, log_loss) VALUES {alpha_rows_sql}"
        )
        print(f"  alpha_tuning_results: {len(alpha_scores)} rows")

        # probability_layer_summary
        cur.execute("TRUNCATE TABLE baseball_data.betting_ml.probability_layer_summary")
        cur.execute(
            "INSERT INTO baseball_data.betting_ml.probability_layer_summary "
            "(n_tuning_games, best_alpha, small_sample_warning, "
            "h2h_mean_edge, totals_mean_edge, "
            "h2h_positive_edge_pct, totals_positive_edge_pct, "
            "n_games_2026_with_odds, n_output_rows) "
            f"VALUES ({n_tuning_games}, {best_alpha}, {str(small_sample_warning).upper()}, "
            f"{h2h_mean_edge}, {totals_mean_edge}, "
            f"{h2h_positive_edge_pct}, {totals_positive_edge_pct}, "
            f"{n_games_2026_with_odds}, {n_output_rows})"
        )
        print("  probability_layer_summary: 1 row")

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
