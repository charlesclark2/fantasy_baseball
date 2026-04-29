"""Phase 5, Task 6 — Daily scoring entry point.

Given a date (default today), score all confirmed regular-season games, print
a picks table to stdout, and write the canonical probability_outputs parquet.

Run from project root:
    uv run python betting_ml/scripts/predict_today.py
    uv run python betting_ml/scripts/predict_today.py --date 2025-04-15
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import load_features, load_todays_features, get_snowflake_connection
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.model_io import load_model
from betting_ml.utils.probability_layer import (
    compute_posterior,
    compute_edge,
    compute_kelly,
)
from betting_ml.models.total_runs_trainer import p_over_line


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_VERSION = "v0"

_CREATE_PREDICTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.daily_model_predictions (
    -- Run metadata
    model_version           VARCHAR(20)    NOT NULL,
    inserted_at             TIMESTAMP_NTZ  NOT NULL,
    score_date              DATE           NOT NULL,

    -- Game identifiers
    game_pk                 INTEGER,
    game_date               DATE,
    game_datetime           TIMESTAMP_NTZ,

    -- Matchup
    home_team               VARCHAR(100),
    away_team               VARCHAR(100),
    home_team_abbrev        VARCHAR(10),
    away_team_abbrev        VARCHAR(10),

    -- Whether bookmaker odds were available for this game
    has_odds                BOOLEAN,

    -- Core model outputs (populated for every game)
    p_home_win_ngboost      FLOAT,   -- NGBoost run-diff: P(home run diff > 0)
    p_home_win_classifier   FLOAT,   -- XGBoost + Platt calibration: P(home wins)
    consensus_win_prob      FLOAT,   -- 0.5 * ngboost + 0.5 * classifier
    pick                    VARCHAR(60),
    pred_total_runs         FLOAT,   -- NGBoost total-runs point estimate (loc)
    pred_total_runs_scale   FLOAT,   -- NGBoost total-runs uncertainty (scale / std dev)
    pred_run_diff_loc       FLOAT,   -- NGBoost run-diff point estimate (loc)
    pred_run_diff_scale     FLOAT,   -- NGBoost run-diff uncertainty (scale / std dev)
    p_over_ngboost          FLOAT,   -- NGBoost P(total runs > total_line_consensus)

    -- Probability layer (alpha tuned on historical data)
    alpha                   FLOAT,

    -- H2H (moneyline) market — NULL when has_odds = FALSE
    h2h_market_implied_prob FLOAT,   -- consensus vig-adjusted P(home wins)
    h2h_posterior_prob      FLOAT,   -- Bayesian blend of model and market
    h2h_edge                FLOAT,   -- p_home_win_ngboost - h2h_market_implied_prob
    h2h_kelly_fraction      FLOAT,   -- full Kelly fraction (positive = bet home)

    -- Totals market — NULL when has_odds = FALSE
    total_line_consensus    FLOAT,   -- consensus over/under line
    over_prob_consensus     FLOAT,   -- consensus vig-adjusted P(over)
    totals_model_prob       FLOAT,   -- NGBoost P(total > total_line_consensus)
    totals_posterior_prob   FLOAT,
    totals_edge             FLOAT,
    totals_kelly_fraction   FLOAT
)
"""

_INSERT_PREDICTION = """
INSERT INTO baseball_data.betting_ml.daily_model_predictions (
    model_version, inserted_at, score_date,
    game_pk, game_date, game_datetime,
    home_team, away_team, home_team_abbrev, away_team_abbrev,
    has_odds,
    p_home_win_ngboost, p_home_win_classifier, consensus_win_prob, pick,
    pred_total_runs, pred_total_runs_scale,
    pred_run_diff_loc, pred_run_diff_scale,
    p_over_ngboost,
    alpha,
    h2h_market_implied_prob, h2h_posterior_prob, h2h_edge, h2h_kelly_fraction,
    total_line_consensus, over_prob_consensus,
    totals_model_prob, totals_posterior_prob, totals_edge, totals_kelly_fraction
) VALUES (
    %(model_version)s, %(inserted_at)s, %(score_date)s,
    %(game_pk)s, %(game_date)s, %(game_datetime)s,
    %(home_team)s, %(away_team)s, %(home_team_abbrev)s, %(away_team_abbrev)s,
    %(has_odds)s,
    %(p_home_win_ngboost)s, %(p_home_win_classifier)s, %(consensus_win_prob)s, %(pick)s,
    %(pred_total_runs)s, %(pred_total_runs_scale)s,
    %(pred_run_diff_loc)s, %(pred_run_diff_scale)s,
    %(p_over_ngboost)s,
    %(alpha)s,
    %(h2h_market_implied_prob)s, %(h2h_posterior_prob)s, %(h2h_edge)s, %(h2h_kelly_fraction)s,
    %(total_line_consensus)s, %(over_prob_consensus)s,
    %(totals_model_prob)s, %(totals_posterior_prob)s, %(totals_edge)s, %(totals_kelly_fraction)s
)
"""


def _write_predictions_to_snowflake(
    df_today: pd.DataFrame,
    target_date: str,
    inserted_at: datetime,
    p_home_win_ngb: np.ndarray,
    p_home_win_clf: np.ndarray,
    loc_tot: np.ndarray,
    scale_tot: np.ndarray,
    loc_diff: np.ndarray,
    scale_diff: np.ndarray,
    p_over_total: np.ndarray,
    h2h_mkt: np.ndarray,
    over_mkt: np.ndarray,
    total_line_vals: np.ndarray,
    has_odds_col: pd.Series,
    best_alpha: float,
    picks: list[str],
) -> None:
    def _f(arr, i) -> float | None:
        v = arr[i]
        return None if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v)

    def _s(df, col, i):
        if col not in df.columns:
            return None
        v = df.iloc[i][col]
        if pd.isna(v):
            return None
        # Snowflake connector doesn't handle numpy scalars in %(name)s params;
        # .item() converts np.int64 / np.float64 / etc. to native Python types.
        return v.item() if hasattr(v, "item") else v

    def _sanitize(row: dict) -> dict:
        # Snowflake connector serializes Python float('nan') as the SQL literal NAN,
        # which Snowflake rejects. Convert any remaining NaN floats to None.
        return {
            k: (None if isinstance(v, float) and v != v else v)
            for k, v in row.items()
        }

    rows: list[dict] = []
    score_date = date.fromisoformat(target_date)

    for i in range(len(df_today)):
        has_odds = bool(has_odds_col.iloc[i])
        ngb_win  = float(p_home_win_ngb[i])
        clf_win  = float(p_home_win_clf[i])
        cons_win = ngb_win * 0.5 + clf_win * 0.5

        # H2H market values
        h2h_mkt_v  = _f(h2h_mkt, i)
        if has_odds and h2h_mkt_v is not None:
            h2h_edge  = compute_edge(ngb_win, h2h_mkt_v)
            h2h_post  = compute_posterior(ngb_win, h2h_mkt_v, best_alpha)
            h2h_kelly = compute_kelly(h2h_edge, h2h_mkt_v)
        else:
            h2h_edge = h2h_post = h2h_kelly = None

        # Totals market values
        over_mkt_v    = _f(over_mkt, i)
        total_line_v  = _f(total_line_vals, i)
        p_over_v      = float(p_over_total[i])
        if has_odds and over_mkt_v is not None:
            tot_edge  = compute_edge(p_over_v, over_mkt_v)
            tot_post  = compute_posterior(p_over_v, over_mkt_v, best_alpha)
            tot_kelly = compute_kelly(tot_edge, over_mkt_v)
        else:
            tot_edge = tot_post = tot_kelly = None

        # Parse game_datetime from df_today if present
        raw_dt = _s(df_today, "game_datetime", i)
        game_dt: datetime | None = None
        if raw_dt is not None:
            try:
                game_dt = pd.Timestamp(raw_dt).to_pydatetime().replace(tzinfo=None)
            except Exception:
                pass

        rows.append(_sanitize({
            "model_version":          MODEL_VERSION,
            "inserted_at":            inserted_at,
            "score_date":             score_date,
            "game_pk":                _s(df_today, "game_pk", i),
            "game_date":              score_date,
            "game_datetime":          game_dt,
            "home_team":              _s(df_today, "home_name", i) or _s(df_today, "home_team", i),
            "away_team":              _s(df_today, "away_name", i) or _s(df_today, "away_team", i),
            "home_team_abbrev":       _s(df_today, "home_team_abbrev", i) or _s(df_today, "home_abbr", i),
            "away_team_abbrev":       _s(df_today, "away_team_abbrev", i) or _s(df_today, "away_abbr", i),
            "has_odds":               has_odds,
            "p_home_win_ngboost":     ngb_win,
            "p_home_win_classifier":  clf_win,
            "consensus_win_prob":     cons_win,
            "pick":                   picks[i],
            "pred_total_runs":        float(loc_tot[i]),
            "pred_total_runs_scale":  float(scale_tot[i]),
            "pred_run_diff_loc":      float(loc_diff[i]),
            "pred_run_diff_scale":    float(scale_diff[i]),
            "p_over_ngboost":         p_over_v,
            "alpha":                  best_alpha,
            "h2h_market_implied_prob": h2h_mkt_v if has_odds else None,
            "h2h_posterior_prob":     h2h_post,
            "h2h_edge":               h2h_edge,
            "h2h_kelly_fraction":     h2h_kelly,
            "total_line_consensus":   total_line_v if has_odds else None,
            "over_prob_consensus":    over_mkt_v if has_odds else None,
            "totals_model_prob":      p_over_v if has_odds else None,
            "totals_posterior_prob":  tot_post,
            "totals_edge":            tot_edge,
            "totals_kelly_fraction":  tot_kelly,
        }))

    try:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(_CREATE_PREDICTIONS_TABLE)
            cur.executemany(_INSERT_PREDICTION, rows)
            conn.commit()
            print(f"\nWrote {len(rows)} prediction row(s) to "
                  f"baseball_data.betting_ml.daily_model_predictions "
                  f"(model_version={MODEL_VERSION}, inserted_at={inserted_at.isoformat()})")
        finally:
            conn.close()
    except Exception as exc:
        print(f"\nWarning: Could not write predictions to Snowflake ({exc}). "
              "Parquet output is still valid.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_ngb_cfg(path: str, target_label: str) -> tuple[int, str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"NGBoost tuning results not found: {path}. "
            f"Run Card 4.12 hyperparameter search first."
        )
    with open(p) as f:
        cfg = json.load(f)
    for key in ("best_n_estimators", "best_dist"):
        if key not in cfg:
            raise KeyError(f"Required key '{key}' missing from {path} ({target_label})")
    return int(cfg["best_n_estimators"]), str(cfg["best_dist"])


def _load_best_alpha() -> float:
    # Primary source: alpha_tuning_results (Card 4.13 output)
    try:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT alpha FROM baseball_data.betting_ml.alpha_tuning_results "
                "ORDER BY loaded_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row is not None:
                return float(row[0])
            print("Warning: alpha_tuning_results is empty; trying local cache")
        finally:
            conn.close()
    except Exception as exc:
        print(f"Warning: Could not load alpha from Snowflake ({exc}); trying local cache")

    # Fallback: best_alpha.json written by Card 4.13
    cache_path = PROJECT_ROOT / "betting_ml" / "models" / "best_alpha.json"
    if cache_path.exists():
        with open(cache_path) as f:
            return float(json.load(f)["best_alpha"])

    print("Warning: best_alpha.json not found; using 0.5")
    return 0.5


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score today's MLB games using the Phase 5 production models."
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        default=date.today().isoformat(),
        help="Target game date (default: today)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    args = _parse_args()
    target_date = args.date
    print(f"Scoring games for {target_date}")

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    df_today = load_todays_features(target_date)

    if df_today.empty:
        print(f"No games found for {target_date}.")
        sys.exit(0)

    print(f"  Found {len(df_today)} game(s) for {target_date}")

    # Filter to confirmed lineups when lineup data is available (home_lineup_slot_1 /
    # away_lineup_slot_1 are populated by the nightly dbt pipeline; the statsapi
    # fallback path does not have them, so the filter is skipped gracefully).
    lineup_cols = ("home_lineup_slot_1", "away_lineup_slot_1")
    if all(c in df_today.columns for c in lineup_cols):
        before = len(df_today)
        df_today = df_today[
            df_today["home_lineup_slot_1"].notna() & df_today["away_lineup_slot_1"].notna()
        ]
        print(f"  Lineup filter: {before} → {len(df_today)} game(s) with confirmed lineups")
        if df_today.empty:
            print("No games with confirmed lineups found.")
            sys.exit(0)

    for col in ("has_odds", "home_win_prob_consensus"):
        if col not in df_today.columns:
            raise ValueError(
                f"Required column '{col}' not found in today's feature data. "
                f"Available columns: {sorted(df_today.columns.tolist())}"
            )

    print("Loading historical features for imputation pipeline fitting...")
    df_hist = load_features(min_games_played=15)
    print(f"  Loaded {len(df_hist):,} historical rows")

    # ------------------------------------------------------------------
    # Feature matrix preparation
    # ------------------------------------------------------------------
    feature_cols = load_retained_features()
    feature_cols_hist = [c for c in feature_cols if c in df_hist.columns]
    feature_cols_today = [c for c in feature_cols if c in df_today.columns]
    missing = set(feature_cols) - set(feature_cols_today)
    if missing:
        warnings.warn(
            f"{len(missing)} retained features missing from today's data (will fill NaN): "
            f"{sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}"
        )

    X_hist = df_hist[[c for c in feature_cols_hist if c in df_hist.columns]]
    X_today_raw = df_today[[c for c in feature_cols_today if c in df_today.columns]]
    X_today_raw = X_today_raw.reindex(columns=X_hist.columns, fill_value=np.nan)

    pipeline = build_imputation_pipeline()
    X_hist_imp = pipeline.fit_transform(X_hist)
    X_hist_imp = X_hist_imp.select_dtypes(include=[np.number])

    X_today_imp = pipeline.transform(X_today_raw)
    X_today_imp = X_today_imp.reindex(columns=X_hist_imp.columns, fill_value=0.0)

    # ------------------------------------------------------------------
    # Load production models
    # ------------------------------------------------------------------
    print("Loading production models from registry...")
    ngb_total = load_model("total_runs", "prod")
    ngb_diff  = load_model("run_differential", "prod")
    clf_hw    = load_model("home_win", "prod")
    print(f"  total_runs: {type(ngb_total).__name__}")
    print(f"  run_differential: {type(ngb_diff).__name__}")
    print(f"  home_win: {type(clf_hw).__name__}")

    # ------------------------------------------------------------------
    # Load NGBoost distribution config
    # ------------------------------------------------------------------
    _, ngb_tot_dist = _load_ngb_cfg(
        "betting_ml/evaluation/tuning_results_ngboost_total_runs.json", "total_runs"
    )
    _, ngb_diff_dist = _load_ngb_cfg(
        "betting_ml/evaluation/tuning_results_ngboost_run_diff.json", "run_differential"
    )

    # ------------------------------------------------------------------
    # Load best_alpha from Snowflake
    # ------------------------------------------------------------------
    best_alpha = _load_best_alpha()
    print(f"  best_alpha={best_alpha}")

    # ------------------------------------------------------------------
    # Score today's games
    # ------------------------------------------------------------------
    X_vals = X_today_imp.values

    # NGBoost .dist() returns the predictive distribution (scipy-compatible, .params + .cdf()).
    # In ngboost >=0.3 the method is named pred_dist(); the plan spec refers to this as .dist().
    pred_dist_tot = ngb_total.pred_dist(X_vals)
    loc_tot   = pred_dist_tot.params["loc"]
    scale_tot = pred_dist_tot.params["scale"]

    total_line_vals = (
        df_today["total_line_consensus"].values
        if "total_line_consensus" in df_today.columns
        else np.full(len(df_today), np.nan)
    )
    p_over_total = p_over_line(
        ngb_tot_dist, {"loc": loc_tot, "scale": scale_tot}, total_line=total_line_vals
    )

    pred_dist_diff = ngb_diff.pred_dist(X_vals)
    loc_diff   = pred_dist_diff.params["loc"]
    scale_diff = pred_dist_diff.params["scale"]
    p_home_win_ngb = p_over_line(
        ngb_diff_dist, {"loc": loc_diff, "scale": scale_diff}, total_line=0
    )

    p_home_win_clf = clf_hw.predict_proba(X_vals)[:, 1]

    # ------------------------------------------------------------------
    # Build output rows (has_odds=True games only, Card 4.13 schema)
    # ------------------------------------------------------------------
    has_odds_col = df_today["has_odds"].fillna(False).astype(bool)
    h2h_mkt  = (
        df_today["home_win_prob_consensus"].values
        if "home_win_prob_consensus" in df_today.columns
        else np.full(len(df_today), np.nan)
    )
    over_mkt = (
        df_today["over_prob_consensus"].values
        if "over_prob_consensus" in df_today.columns
        else np.full(len(df_today), np.nan)
    )

    output_rows: list[dict] = []
    for i, row_idx in enumerate(df_today.index):
        game_key = str(row_idx)
        if "game_pk" in df_today.columns:
            game_key = str(df_today.loc[row_idx, "game_pk"])

        if not has_odds_col.iloc[i]:
            continue

        if pd.notna(h2h_mkt[i]):
            mp  = float(p_home_win_ngb[i])
            mkt = float(h2h_mkt[i])
            edge = compute_edge(mp, mkt)
            output_rows.append({
                "game_key":             game_key,
                "market":               "h2h",
                "model_prob":           mp,
                "market_implied_prob":  mkt,
                "alpha":                best_alpha,
                "posterior_prob":       compute_posterior(mp, mkt, best_alpha),
                "edge":                 edge,
                "implied_kelly_fraction": compute_kelly(edge, mkt),
            })

        if pd.notna(over_mkt[i]):
            mp  = float(p_over_total[i])
            mkt = float(over_mkt[i])
            edge = compute_edge(mp, mkt)
            output_rows.append({
                "game_key":             game_key,
                "market":               "totals",
                "model_prob":           mp,
                "market_implied_prob":  mkt,
                "alpha":                best_alpha,
                "posterior_prob":       compute_posterior(mp, mkt, best_alpha),
                "edge":                 edge,
                "implied_kelly_fraction": compute_kelly(edge, mkt),
            })

    # Rank has_odds games by abs(edge) descending (highest-conviction bets first).
    output_rows.sort(key=lambda r: abs(r.get("edge") or 0.0), reverse=True)

    # ------------------------------------------------------------------
    # Write parquet
    # ------------------------------------------------------------------
    out_dir = PROJECT_ROOT / "betting_ml" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"probability_outputs_{target_date}.parquet"

    if output_rows:
        pd.DataFrame(output_rows).to_parquet(out_path, index=False, engine="pyarrow")
    else:
        pd.DataFrame(columns=[
            "game_key", "market", "model_prob", "market_implied_prob",
            "alpha", "posterior_prob", "edge", "implied_kelly_fraction",
        ]).to_parquet(out_path, index=False, engine="pyarrow")

    # ------------------------------------------------------------------
    # Print picks table (all games, not just has_odds)
    # ------------------------------------------------------------------
    def _matchup(idx: int) -> str:
        row = df_today.iloc[idx]
        for home_col, away_col in [
            ("home_team_abbrev", "away_team_abbrev"),
            ("home_team", "away_team"),
        ]:
            if home_col in df_today.columns and away_col in df_today.columns:
                return f"{row[away_col]} @ {row[home_col]}"
        return str(df_today.index[idx])

    def _game_time(idx: int) -> str:
        row = df_today.iloc[idx]
        if "game_datetime" in df_today.columns and pd.notna(row.get("game_datetime")):
            return str(row["game_datetime"])
        if "game_date" in df_today.columns:
            return str(row["game_date"])
        return "—"

    def _pct(val) -> str:
        if pd.isna(val):
            return "—"
        return f"{float(val)*100:.1f}%"

    pred_total = loc_tot
    picks_list: list[str] = []

    rows_table = []
    csv_rows: list[dict] = []
    for i in range(len(df_today)):
        has_odds = has_odds_col.iloc[i]
        ngb_win = float(p_home_win_ngb[i])
        clf_win = float(p_home_win_clf[i])
        consensus_win = ngb_win * 0.5 + clf_win * 0.5

        if consensus_win >= 0.55:
            pick = f"HOME ({consensus_win*100:.0f}%)"
        elif consensus_win <= 0.45:
            pick = f"AWAY ({(1-consensus_win)*100:.0f}%)"
        elif consensus_win > 0.50:
            pick = f"TOSS-UP (lean HOME {consensus_win*100:.0f}%)"
        elif consensus_win < 0.50:
            pick = f"TOSS-UP (lean AWAY {(1-consensus_win)*100:.0f}%)"
        else:
            pick = "EVEN"

        picks_list.append(pick)

        _h2h_v = float(h2h_mkt[i]) if pd.notna(h2h_mkt[i]) else None
        _edge_v = compute_edge(float(p_home_win_ngb[i]), _h2h_v) if (has_odds and _h2h_v is not None) else None
        _post_v = compute_posterior(float(p_home_win_ngb[i]), _h2h_v, best_alpha) if (has_odds and _h2h_v is not None) else None
        _kelly_v = compute_kelly(_edge_v, _h2h_v) if (_edge_v is not None and _h2h_v is not None) else None

        rows_table.append({
            "Matchup":            _matchup(i),
            "Pick":               pick,
            "Game Time":          _game_time(i),
            "Pred Total":         f"{pred_total[i]:.1f}",
            "Model Win% (NGBoost)": _pct(p_home_win_ngb[i]),
            "Classifier Win%":    _pct(p_home_win_clf[i]),
            "Market Win%":        _pct(_h2h_v) if has_odds else "—",
            "Posterior%":         _pct(_post_v),
            "Edge":               f"{_edge_v*100:.1f}%" if _edge_v is not None else "—",
            "Kelly%":             f"{_kelly_v*100:.2f}%" if _kelly_v is not None else "—",
        })

        _row = df_today.iloc[i]
        _home = _row.get("home_name") or _row.get("home_team") or ""
        _away = _row.get("away_name") or _row.get("away_team") or ""
        csv_rows.append({
            "game_pk":               _row.get("game_pk"),
            "matchup":               _matchup(i),
            "game_time":             _game_time(i),
            "predicted_total_runs":  float(pred_total[i]),
            "model_home_win_prob":   float(p_home_win_ngb[i]),
            "market_home_win_prob":  _h2h_v,
            "posterior_prob":        _post_v,
            "edge":                  _edge_v,
            "kelly_fraction":        _kelly_v,
            "home_team":             _home,
            "away_team":             _away,
        })

    df_table = pd.DataFrame(rows_table)
    print("\n" + df_table.to_string(index=False))

    print("""
Column Definitions
------------------
  Matchup              Away team @ Home team. All win probabilities below are for the HOME team.

  Pick                 Model recommendation based on the consensus of Model Win% (NGBoost) and
                       Classifier Win%.
                         HOME (X%)  — model strongly favors home (consensus >55%); X% = home win prob.
                         AWAY (X%)  — model strongly favors away (consensus <45%); X% = away win prob.
                         TOSS-UP (lean HOME/AWAY X%) — consensus in 45–55% range; lean direction shown.
                         EVEN — consensus is exactly 50/50.

  Game Time            Scheduled start time (UTC).

  Pred Total           NGBoost point estimate for the total combined runs scored in the game.

  Model Win% (NGBoost) Probability the HOME team wins, from the NGBoost distributional model trained
                       on run differential. NGBoost outputs a full probability distribution over
                       outcomes, and this is the probability that home run differential > 0.

  Classifier Win%      Probability the HOME team wins, from a separately trained XGBoost classifier
                       with Platt (sigmoid) calibration. Uses the same features but is trained
                       directly on win/loss outcomes rather than run differential.

  Market Win%          Consensus vig-adjusted implied probability the HOME team wins, averaged across
                       all bookmakers. Vig-adjustment removes the bookmaker's built-in margin so the
                       home and away probabilities sum to 100%.

  Posterior%           Bayesian blend of Model Win% (NGBoost) and Market Win%, controlled by
                       best_alpha (tuned on historical data). Values near Market Win% mean the market
                       is weighted heavily; values near Model Win% mean the model is trusted more.
                       This is the final probability used for Kelly sizing.

  Edge                 Model Win% (NGBoost) minus Market Win% — how much the model disagrees with
                       the market, expressed in percentage points.
                         Positive (+) = model thinks the home team is more likely to win than the
                           market implies → potential value on a HOME bet.
                         Negative (−) = model thinks the home team is less likely to win than the
                           market implies → potential value on an AWAY bet.

  Kelly%               Implied Kelly criterion bet size as a fraction of bankroll, derived from
                       Edge and Market Win%.
                         Positive (+) = Kelly recommends betting on the HOME team.
                         Negative (−) = Kelly recommends betting on the AWAY team.
                       These are full-Kelly values — in practice apply a fractional multiplier
                       (e.g. 0.25×) to reduce variance before sizing real bets.""")

    n_h2h = sum(1 for r in output_rows if r["market"] == "h2h")
    n_tot = sum(1 for r in output_rows if r["market"] == "totals")
    if output_rows:
        print(f"\nWrote {len(output_rows)} output rows ({n_h2h} h2h, {n_tot} totals) to {out_path}")
    else:
        print(f"\nWrote 0 output rows (no odds available — picks table above uses model probabilities only) to {out_path}")

    # ------------------------------------------------------------------
    # Write predictions CSV (all games — canonical Phase 6 daily snapshot)
    # ------------------------------------------------------------------
    csv_path = out_dir / f"predictions_{target_date}.csv"
    pd.DataFrame(csv_rows).to_csv(csv_path, index=False)
    print(f"Wrote {len(csv_rows)} game(s) to {csv_path}")

    # ------------------------------------------------------------------
    # Write predictions to Snowflake
    # ------------------------------------------------------------------
    run_ts = datetime.now(timezone.utc).replace(tzinfo=None)
    _write_predictions_to_snowflake(
        df_today=df_today,
        target_date=target_date,
        inserted_at=run_ts,
        p_home_win_ngb=p_home_win_ngb,
        p_home_win_clf=p_home_win_clf,
        loc_tot=loc_tot,
        scale_tot=scale_tot,
        loc_diff=loc_diff,
        scale_diff=scale_diff,
        p_over_total=p_over_total,
        h2h_mkt=h2h_mkt,
        over_mkt=over_mkt,
        total_line_vals=total_line_vals,
        has_odds_col=has_odds_col,
        best_alpha=best_alpha,
        picks=picks_list,
    )


if __name__ == "__main__":
    main()
