#!/usr/bin/env python
"""Story A2.6 (audit helper) — Re-score completed games with the CURRENT feature
marts and measure whether skill improves when the model is served correct features.

The 2026-06-10 audit found the deployed home_win champion has ~zero live skill
(corr≈0.03). The hypothesis (A2.2–A2.4) is that this is feature-SERVING skew, not a
broken model: at live scoring time the discriminative features (ELO / archetype /
cluster / h2h / RISP) were null→constant-imputed, so the model saw noise. This script
tests that hypothesis directly and CHEAPLY, without waiting for fixes to deploy and
games to accumulate:

  1. Load completed games from the historical feature store (feature_pregame_game_features
     JOIN mart_game_results) — for COMPLETED games the marts hold the exact, populated,
     leakage-guarded pre-game feature snapshot (game_date < anchor). This is "the features
     the model SHOULD have been served."
  2. Score the SAME production models / calibrator / registry feature columns as the
     deployed scorer (predict_today's impute → reindex(fill 0) → score path).
  3. Compute the SAME honest metrics as model_health_metrics.py (reused verbatim) and
     compare the re-scored verdict to the deployed-live baseline.

Read the result like this:
  - Re-scored corr ≫ live corr (toward CV ~0.15–0.20) → the model HAS skill when properly
    served; the problem is serving (A2.3/A2.4 will help once deployed). Verdict leans
    "serving-fixed-healthy".
  - Re-scored corr still ≈ 0 with populated features → architecture-limited; escalate to
    Tracks B / Epics 27/28. The serving fixes alone won't save it.

This is an AUDIT ONLY — it never writes to Snowflake.

LEAKAGE NOTE: the deployed models were trained through 2025; only 2026 is honest OOS
(see project_layer3_signal_leakage). Re-scoring pre-2026 games is IN-SAMPLE and will
inflate corr — the script warns and defaults the window to 2026.

Hand-off (loads the full feature store; can exceed 1 min):

    python scripts/ops/rescore_audit.py --since 2026-05-20 --compare-live
    python scripts/ops/rescore_audit.py --days 30
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# scripts/ops on path so we can reuse the A2.1 metric/gate engine verbatim.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

import model_health_metrics as mh  # noqa: E402  (shared eval + gate, same dir)
from betting_ml.utils.data_loader import load_features, get_snowflake_connection  # noqa: E402
from betting_ml.utils.preprocessing import build_imputation_pipeline  # noqa: E402
from betting_ml.utils.model_io import load_model  # noqa: E402
from betting_ml.models.total_runs_trainer import p_over_line  # noqa: E402

_MODELS = _REPO_ROOT / "betting_ml" / "models"
_REGISTRY_PATH = _MODELS / "model_registry.yaml"
_CALIBRATOR_PATH = _MODELS / "home_win" / "calibrator.joblib"
_RESULTS_TABLE = "baseball_data.betting_ml.model_health_metrics"


def _load_calibrator():
    import joblib
    if _CALIBRATOR_PATH.exists():
        return joblib.load(_CALIBRATOR_PATH)
    return None


def _apply_calibrator(calibrator, consensus_win_prob: np.ndarray) -> np.ndarray:
    if calibrator is None:
        return consensus_win_prob
    raw = np.asarray(consensus_win_prob, dtype=float).reshape(-1, 1)
    return calibrator.predict_proba(raw)[:, 1]


def _load_best_alpha() -> float:
    cache = _MODELS / "best_alpha.json"
    if cache.exists():
        try:
            return float(json.loads(cache.read_text())["best_alpha"])
        except Exception:
            pass
    return 0.0


def _registry_feat_cols(registry: dict, target: str) -> list[str]:
    return json.loads((_REPO_ROOT / registry[target]["feature_columns_path"]).read_text())


def _score(df: pd.DataFrame, registry: dict) -> pd.DataFrame:
    """Replicate the deployed scorer (predict_today) on completed-game features.

    impute every numeric col → reindex to each model's training columns (fill 0.0) →
    score by column position. Identical mechanics to scripts/predict_today.py.
    """
    tot_dist = registry["total_runs"]["dist"]
    diff_dist = registry["run_differential"]["dist"]
    hw_cols = _registry_feat_cols(registry, "home_win")
    tot_cols = _registry_feat_cols(registry, "total_runs")
    diff_cols = _registry_feat_cols(registry, "run_differential")

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    pipe = build_imputation_pipeline()
    pipe.fit(df[numeric_cols])
    df_t = pd.DataFrame(pipe.transform(df[numeric_cols]), columns=numeric_cols, index=df.index)

    clf_hw = load_model("home_win", "prod")
    ngb_tot = load_model("total_runs", "prod")
    ngb_diff = load_model("run_differential", "prod")
    calibrator = _load_calibrator()
    print(f"  models: home_win={type(clf_hw).__name__}  total_runs={type(ngb_tot).__name__}  "
          f"run_diff={type(ngb_diff).__name__}  calibrator={'yes' if calibrator else 'NONE'}")

    X_tot = df_t.reindex(columns=tot_cols, fill_value=0.0).values
    dist_tot = ngb_tot.pred_dist(X_tot)
    loc_tot, scale_tot = dist_tot.params["loc"], dist_tot.params["scale"]

    X_diff = df_t.reindex(columns=diff_cols, fill_value=0.0).values
    dist_diff = ngb_diff.pred_dist(X_diff)
    loc_diff, scale_diff = dist_diff.params["loc"], dist_diff.params["scale"]
    p_hw_ngb = p_over_line(diff_dist, {"loc": loc_diff, "scale": scale_diff}, total_line=0)

    X_clf = df_t.reindex(columns=hw_cols, fill_value=0.0).values.astype(np.float32)
    p_hw_clf = clf_hw.predict_proba(X_clf)[:, 1]

    cons_win = p_hw_ngb * 0.5 + p_hw_clf * 0.5
    cal_win = _apply_calibrator(calibrator, cons_win)

    total_line = (df["total_line_consensus"].to_numpy(dtype=float)
                  if "total_line_consensus" in df.columns else np.full(len(df), np.nan))
    p_over = p_over_line(tot_dist, {"loc": loc_tot, "scale": scale_tot}, total_line=total_line)

    # Reconstruct exact final scores from the two actuals so we can reuse the A2.1 eval
    # functions unchanged: home = (total + diff)/2, away = (total − diff)/2.
    total_actual = df["total_runs"].to_numpy(dtype=float)
    diff_actual = df["run_differential"].to_numpy(dtype=float)
    home_final = (total_actual + diff_actual) / 2.0
    away_final = (total_actual - diff_actual) / 2.0

    return pd.DataFrame({
        "game_pk": df["game_pk"].to_numpy(),
        "home_final_score": home_final,
        "away_final_score": away_final,
        "run_differential": diff_actual,
        "consensus_win_prob": cons_win,
        "calibrated_win_prob": cal_win,
        "h2h_market_implied_prob": df.get("home_win_prob_consensus", pd.Series(np.nan, index=df.index)).to_numpy(dtype=float),
        "pred_total_runs": np.asarray(loc_tot, dtype=float),
        "totals_p_over": np.asarray(p_over, dtype=float),
        "over_prob_consensus": df.get("over_prob_consensus", pd.Series(np.nan, index=df.index)).to_numpy(dtype=float),
        "total_line_consensus": total_line,
        "pred_run_diff_loc": np.asarray(loc_diff, dtype=float),
    })


def _fetch_live_baseline(conn, start: date, end: date) -> dict:
    """Most-recent deployed-live metrics per target from model_health_metrics, for the
    closest matching window, so we can print a re-scored-vs-live delta."""
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            select target, n_games, verdict, corr, brier, no_skill_brier, spread, mae
            from {_RESULTS_TABLE}
            qualify row_number() over (partition by target order by run_at desc) = 1
            """
        )
        out = {}
        for r in cur.fetchall():
            out[r[0]] = {"n_games": r[1], "verdict": r[2], "corr": r[3],
                         "brier": r[4], "no_skill_brier": r[5], "spread": r[6], "mae": r[7]}
        cur.close()
        return out
    except Exception as exc:
        print(f"  [compare-live] could not read {_RESULTS_TABLE} ({exc})")
        return {}


def _print_compare(hw: dict, tot: dict, rd: dict, live: dict) -> None:
    print("\n" + "-" * 78)
    print("  RE-SCORED (corrected features)  vs  DEPLOYED-LIVE (model_health_metrics)")
    print("-" * 78)
    print(f"  {'target':<18}{'corr (live→rescored)':<26}{'verdict (live→rescored)':<28}")
    rescored = {"home_win": hw, "total_runs": tot, "run_differential": rd}
    for tgt in ("home_win", "total_runs", "run_differential"):
        rs = rescored[tgt]
        rs_corr = rs.get("calibrated_corr", rs.get("corr"))
        lv = live.get(tgt, {})
        lv_corr = lv.get("corr")
        corr_str = f"{mh._fmt(lv_corr)} → {mh._fmt(rs_corr)}"
        verdict_str = f"{lv.get('verdict', '—')} → {rs['verdict']}"
        print(f"  {tgt:<18}{corr_str:<26}{verdict_str:<28}")
    print("-" * 78)
    print("  Interpretation: a large corr jump (live≈0 → rescored toward CV) ⇒ the model")
    print("  has skill when served correct features ⇒ SERVING was the problem (A2.3/A2.4).")
    print("  No jump (rescored still ≈0) ⇒ architecture-limited ⇒ escalate to Epics 27/28.\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-score completed games with current features (A2.6 audit).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, default=30, help="rolling window ending --end (default 30)")
    g.add_argument("--since", type=str, help="window start YYYY-MM-DD (overrides --days)")
    ap.add_argument("--end", type=str, help="window end YYYY-MM-DD (default today)")
    ap.add_argument("--min-games", type=int, default=mh.MIN_GAMES, help=f"gate min sample (default {mh.MIN_GAMES})")
    ap.add_argument("--compare-live", action="store_true",
                    help="print a re-scored-vs-deployed-live delta from model_health_metrics")
    ap.add_argument("--allow-pre-2026", action="store_true",
                    help="permit pre-2026 games (IN-SAMPLE for models trained ≤2025; corr inflated)")
    args = ap.parse_args()

    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    start = datetime.strptime(args.since, "%Y-%m-%d").date() if args.since else end - timedelta(days=args.days)
    window = f"{start.isoformat()} → {end.isoformat()}"

    if start < date(2026, 1, 1) and not args.allow_pre_2026:
        print(f"[REFUSING] window {window} includes pre-2026 games, which are IN-SAMPLE for the "
              f"deployed models (trained ≤2025) and would inflate corr. Use --allow-pre-2026 to "
              f"override, or set --since 2026-01-01 or later for an honest OOS audit.")
        return 1

    registry = yaml.safe_load(_REGISTRY_PATH.read_text())

    print("Loading historical feature store (completed games)...")
    df = load_features(min_games_played=15)
    if "game_date" in df.columns:
        df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
        df = df[(df["game_date"] >= start) & (df["game_date"] <= end)].reset_index(drop=True)
    print(f"  {len(df):,} completed game(s) in {window}")
    if df.empty:
        print("Nothing to re-score.")
        return 0

    print("Scoring with production models...")
    scored = _score(df, registry)

    hw = mh._eval_home_win(scored, args.min_games)
    tot = mh._eval_regression(scored, "total_runs", args.min_games)
    rd = mh._eval_regression(scored, "run_differential", args.min_games)

    print()
    mh._print_report(f"RE-SCORE AUDIT (corrected features) — {window}", None, registry["home_win"]["model_version"], hw, tot, rd)

    if args.compare_live:
        conn = get_snowflake_connection()
        try:
            live = _fetch_live_baseline(conn, start, end)
        finally:
            conn.close()
        if live:
            _print_compare(hw, tot, rd, live)

    print(f"GATE (re-scored): {{'home_win': '{hw['verdict']}', "
          f"'total_runs': '{tot['verdict']}', 'run_differential': '{rd['verdict']}'}}")
    print("(audit only — nothing written to Snowflake)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
