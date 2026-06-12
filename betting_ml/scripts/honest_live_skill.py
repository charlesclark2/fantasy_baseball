"""Story 30.3 — honest live-skill tracker (point-in-time-correct evaluation).

WHY THIS EXISTS. The offline home_win benchmark (corr 0.42) is measured by
re-reading `feature_pregame_game_features` for SETTLED games — i.e. the
POST-game-backfilled (dense) row. The live serve only ever saw the PRE-game
(sparse) row for the same game_pk, because the feature store is not
AS-OF-snapshotted (refined_architecture_proposal §"Point-in-Time Feature
Engineering"). So **0.42 is an upper-bound CEILING, not the live target** — using
it as the live KPI silently overstates skill.

The point-in-time-honest live number is whatever the model ACTUALLY SERVED, which
is persisted in `daily_model_predictions` (p_home_win_classifier, pred_total_runs,
…). This harness scores those stored predictions against the true outcome
(`mart_game_results`) — no re-read, no backfill leakage. It is the canonical
"is the live model good at predicting baseball" tracker.

METRICS (Epic 30 PRIMARY = accuracy-to-truth; market-edge is secondary):
  - H2H / home_win: accuracy, Brier, NLL (log-loss), corr, ECE (10-bin calibration)
    vs the 0/1 winner.
  - Totals: RMSE / MAE / MedAE of pred_total_runs vs ACTUAL runs, plus calib_80
    (coverage of the model's 80% Normal interval loc ± 1.2816·scale).

SCOPE. The honest live surface is the DENSE serve: prediction_type='post_lineup'
AND data_source='feature_store' (lineups confirmed, full feature store). Morning /
intraday / unstamped rows are reported for contrast but are NOT the benchmark —
they are pre-lineup or carried-forward and expected to be weaker. The dense
post_lineup sample is still accumulating (n≈15 as of 2026-06-11); the goal is to
WATCH this number climb toward the 0.42 ceiling as the serving fixes (Story 30.3
serving-guard, Story 30.5 umpire feed) take effect — NOT to declare a verdict on a
tiny sample.

Read-only (one Snowflake aggregation pull). Hand off to run with credentials:

    uv run python betting_ml/scripts/honest_live_skill.py
    uv run python betting_ml/scripts/honest_live_skill.py --since 2026-06-11   # post-fix window
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "serving_parity"
_OFFLINE_CEILING = 0.42  # home_win corr on the dense (non-point-in-time) offline surface — a CEILING.

_QUERY = """
SELECT
    dmp.game_pk, dmp.game_date, dmp.prediction_type,
    COALESCE(dmp.data_source, '(unstamped)')      AS data_source,
    dmp.p_home_win_classifier                     AS phw,
    dmp.pred_total_runs                           AS ptot,
    dmp.pred_total_runs_scale                     AS ptot_scale,
    r.home_final_score + r.away_final_score        AS actual_total,
    CASE WHEN r.home_final_score > r.away_final_score THEN 1 ELSE 0 END AS y_home
FROM baseball_data.betting_ml.daily_model_predictions dmp
JOIN baseball_data.betting.mart_game_results r USING (game_pk)
WHERE dmp.game_date >= '{since}'
  AND r.home_final_score IS NOT NULL
  -- Story 30.7: live-skill must exclude rows backfilled after a promotion. Explicit
  -- flag (not prediction_type<>'backfill'), so post_lineup backfills can't sneak in.
  AND COALESCE(dmp.is_backfill, FALSE) = FALSE
"""


def _ece(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error — |confidence − accuracy| weighted by bin size."""
    if len(p) == 0:
        return float("nan")
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, bins) - 1, 0, n_bins - 1)
    ece = 0.0
    for b in range(n_bins):
        m = idx == b
        if not m.any():
            continue
        ece += (m.mean()) * abs(p[m].mean() - y[m].mean())
    return float(ece)


def _h2h_metrics(df: pd.DataFrame) -> dict:
    p = df["phw"].to_numpy(dtype=float)
    y = df["y_home"].to_numpy(dtype=float)
    ok = ~np.isnan(p)
    p, y = p[ok], y[ok]
    n = len(p)
    if n == 0:
        return {"n": 0}
    eps = 1e-9
    pc = np.clip(p, eps, 1 - eps)
    return {
        "n": n,
        "base_rate": round(float(y.mean()), 3),
        "accuracy": round(float(((p >= 0.5) == (y == 1)).mean()), 3),
        "brier": round(float(np.mean((p - y) ** 2)), 4),
        "nll": round(float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc))), 4),
        "corr": round(float(np.corrcoef(p, y)[0, 1]), 3) if n > 1 and p.std() > 0 else None,
        "ece": round(_ece(p, y), 4),
    }


def _totals_metrics(df: pd.DataFrame) -> dict:
    m = df["ptot"].notna() & df["actual_total"].notna()
    pred = df.loc[m, "ptot"].to_numpy(dtype=float)
    act = df.loc[m, "actual_total"].to_numpy(dtype=float)
    n = len(pred)
    if n == 0:
        return {"n": 0}
    err = pred - act
    out = {
        "n": n,
        "rmse": round(float(np.sqrt(np.mean(err ** 2))), 3),
        "mae": round(float(np.mean(np.abs(err))), 3),
        "medae": round(float(np.median(np.abs(err))), 3),
        "mean_pred": round(float(pred.mean()), 2),
        "mean_actual": round(float(act.mean()), 2),
    }
    # calib_80: coverage of the model's 80% Normal interval (loc ± 1.2816·scale).
    sc = df.loc[m, "ptot_scale"].to_numpy(dtype=float)
    sok = ~np.isnan(sc) & (sc > 0)
    if sok.any():
        z = 1.2815515594
        lo = pred[sok] - z * sc[sok]
        hi = pred[sok] + z * sc[sok]
        cov = np.mean((act[sok] >= lo) & (act[sok] <= hi))
        out["calib_80"] = round(float(cov), 3)
        out["calib_80_n"] = int(sok.sum())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-01-01", help="earliest game_date (YYYY-MM-DD)")
    args = ap.parse_args()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_snowflake_connection()
    try:
        df = pd.read_sql(_QUERY.format(since=args.since), conn)
    finally:
        conn.close()
    df.columns = [c.lower() for c in df.columns]
    if df.empty:
        print(f"No settled predictions since {args.since}.")
        return

    # The honest live benchmark surface: dense, lineup-confirmed serve.
    honest = df[(df["prediction_type"] == "post_lineup") & (df["data_source"] == "feature_store")]

    report = {
        "since": args.since,
        "offline_home_win_corr_CEILING": _OFFLINE_CEILING,
        "honest_live_surface": "prediction_type='post_lineup' AND data_source='feature_store'",
        "honest_live": {"h2h": _h2h_metrics(honest), "totals": _totals_metrics(honest)},
        "by_path": [],
    }
    for (pt, ds), g in df.groupby(["prediction_type", "data_source"], dropna=False):
        report["by_path"].append({
            "prediction_type": pt, "data_source": ds,
            "h2h": _h2h_metrics(g), "totals": _totals_metrics(g),
        })

    # ---- console ----
    hl = report["honest_live"]
    print(f"\n=== HONEST LIVE SKILL (point-in-time; served predictions vs truth), since {args.since} ===")
    print(f"  surface: {report['honest_live_surface']}")
    print(f"  ⚠ offline home_win corr {_OFFLINE_CEILING} is a CEILING (non-point-in-time re-read), NOT the target.")
    print(f"  H2H : {hl['h2h']}")
    print(f"  TOT : {hl['totals']}")
    if hl["h2h"].get("n", 0) < 30:
        print(f"  NOTE: n={hl['h2h'].get('n', 0)} — sample too small for a verdict; accumulate settled slates.")
    print("\n--- all serve paths (contrast; only the dense post_lineup/feature_store row above is the benchmark) ---")
    print(f"{'prediction_type':<14} {'data_source':<18} {'n':>4}  {'hw_corr':>7} {'hw_brier':>8} {'hw_acc':>6}  "
          f"{'tot_mae':>7} {'tot_rmse':>8} {'calib80':>7}")
    for row in report["by_path"]:
        h, t = row["h2h"], row["totals"]
        print(f"{str(row['prediction_type']):<14} {str(row['data_source']):<18} {h.get('n', 0):>4}  "
              f"{str(h.get('corr')):>7} {str(h.get('brier')):>8} {str(h.get('accuracy')):>6}  "
              f"{str(t.get('mae')):>7} {str(t.get('rmse')):>8} {str(t.get('calib_80')):>7}")

    out = _OUT_DIR / "honest_live_skill.json"
    out.write_text(json.dumps(report, indent=2, default=float))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
