"""train_line_movement_head1.py — Epic E3.1: Closing-line Head-1 (line-movement regression).

Predicts Δ(open→close) of the book the user bets (Bovada), separately for:
  - h2h    : move of the de-vigged-ish implied home-win prob (prob units)
             target = mart_odds_line_movement.h2h_line_movement
  - totals : move of the total line (run units)
             target = mart_odds_line_movement.total_line_movement

WHY BOVADA, NOT PINNACLE (design decision, E3.1):
  Clean Pinnacle history is single-season (2026 dense) — too thin for the season-based
  E1.1 purged CV (needs >=3 train seasons). Bovada's open->close move is multi-season
  (2021-26) AND it is the CLV the binding Story-12.5 gate measures (the user bets Bovada).
  Pinnacle's sharp OPEN + the Layer-2 baseball fair-value anchor join as 2026-available
  ENRICHMENTS (NULL pre-2026), so they can only contribute to the 2026 eval fold for now —
  an honest limitation, reported per-season. (Denser intraday 2024/25 Pinnacle would make
  the sharp-gap feature multi-season; deferred per spec until v1 shows the signal exists.)

LEAKAGE DISCIPLINE: every feature is known at/near the OPEN; the CLOSE is the target,
  never an input. snapshot_count is intentionally excluded (it's a close-time quantity).

MODEL: NGBoost Normal (point move + uncertainty) per market, under PurgedWalkForwardSplit
  (E1.1). Reuses betting_ml.models.total_runs_trainer.train_ngboost — no new odds/model math.

GATES (E3.1 AC): beat on OOS MAE BOTH baselines — no-move (predict 0) and drift (predict the
  train-mean move) — and show directional accuracy with a bootstrap-CI lower bound > 0.5.
  Beating these is NECESSARY, not sufficient: go-live additionally needs E1.4 PBO<0.2 + DSR>0
  and >=100 forward live games positive CLV (Story 12.5). Honest-framing: transparency model,
  no +EV/win-rate claim. Writes nothing to prod.

Runtime: NGBoost over 3 folds × 2 markets — a few minutes. HAND OFF to run with Snowflake creds.

Usage:
    uv run python betting_ml/scripts/train_line_movement_head1.py --market all
    uv run python betting_ml/scripts/train_line_movement_head1.py --market h2h --refresh-cache
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

from betting_ml.models.total_runs_trainer import train_ngboost
from betting_ml.utils.cv import make_purged_splitter
from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.training_cache import get_cached_df

import joblib

_REPORT = PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results" / "line_movement_head1.md"
_JSON = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "line_movement_head1.json"
_MODEL_DIR = PROJECT_ROOT / "betting_ml" / "models" / "market"

# ── Per-market spec ──────────────────────────────────────────────────────────
# `multi_season` features exist 2021-26 (clean at open). `enrichment` features are
# 2026-only (NULL pre-2026 → imputed); they test the fair-value-anchor thesis on the
# 2026 fold. The derived gap columns are computed in _add_derived().
MARKETS = {
    "h2h": {
        "target": "h2h_line_movement",
        "open_col": "open_home_win_prob",
        "multi_season": [
            "open_home_win_prob", "ml_implied_prob_std", "ml_implied_prob_range",
            "sharp_soft_ml_spread", "n_books_available",
        ],
        "enrichment": ["consensus_win_prob", "pinnacle_open_prob",
                       "anchor_gap_h2h", "sharp_gap_h2h"],
    },
    "totals": {
        "target": "total_line_movement",
        "open_col": "open_total_line",
        "multi_season": [
            "open_total_line", "totals_line_std", "totals_line_range", "n_books_available",
        ],
        "enrichment": ["pred_total_runs", "pinnacle_open_line",
                       "anchor_gap_tot", "sharp_gap_tot"],
    },
}

_DATASET_SQL = """
with base as (
    select game_pk, game_date, h2h_line_movement, total_line_movement,
           open_home_win_prob, open_total_line
    from baseball_data.betting.mart_odds_line_movement
    where bookmaker = 'bovada'
),
disp as (
    select game_pk, ml_implied_prob_std, ml_implied_prob_range,
           totals_line_std, totals_line_range, sharp_soft_ml_spread, n_books_available
    from baseball_data.betting.mart_bookmaker_disagreement
),
game_times as (
    select game_pk, game_date as commence_time
    from baseball_data.betting.stg_statsapi_games
),
anchor as (
    -- LIVE baseball fair value, earliest pre-game row per game. POINT-IN-TIME guard
    -- (inserted_at < first pitch) is the robust filter: is_backfill was only added in
    -- Story 30.7 (2026-06-12), so older post-hoc rows carry is_backfill=NULL and would
    -- otherwise masquerade as live (a leak). The inserted_at guard collapses anchor to
    -- genuinely-live 2026 predictions — the intended 2026-only enrichment.
    select game_pk, consensus_win_prob, pred_total_runs from (
        select p.game_pk, p.consensus_win_prob, p.pred_total_runs,
               row_number() over (partition by p.game_pk order by p.inserted_at asc) as rn
        from baseball_data.betting_ml.daily_model_predictions p
        join game_times gt on gt.game_pk = p.game_pk
        where p.prediction_type in ('morning', 'post_lineup')
          and coalesce(p.is_backfill, false) = false
          and p.inserted_at < gt.commence_time
    ) where rn = 1
),
sharp_h2h as (
    select game_pk, pinnacle_open_prob
    from baseball_data.betting_features.feature_pregame_edge_market
    where market_type = 'h2h'
),
sharp_tot as (
    select game_pk, pinnacle_open_line
    from baseball_data.betting_features.feature_pregame_edge_market
    where market_type = 'totals'
)
select b.game_pk, b.game_date, b.h2h_line_movement, b.total_line_movement,
       b.open_home_win_prob, b.open_total_line,
       d.ml_implied_prob_std, d.ml_implied_prob_range, d.totals_line_std,
       d.totals_line_range, d.sharp_soft_ml_spread, d.n_books_available,
       a.consensus_win_prob, a.pred_total_runs,
       sh.pinnacle_open_prob, st.pinnacle_open_line
from base b
left join disp d       on d.game_pk = b.game_pk
left join anchor a     on a.game_pk = b.game_pk
left join sharp_h2h sh on sh.game_pk = b.game_pk
left join sharp_tot st on st.game_pk = b.game_pk
"""


def load_line_movement_dataset() -> pd.DataFrame:
    """Pull the multi-season Head-1 training frame from Snowflake (one row per game)."""
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_DATASET_SQL)
        df = cur.fetch_pandas_all()
    finally:
        conn.close()
    df.columns = [c.lower() for c in df.columns]
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["game_year"] = df["game_date"].dt.year
    return _add_derived(df)


def _add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Fair-value-anchor gap features (2026-only; NULL where an input is NULL)."""
    df = df.copy()
    df["anchor_gap_h2h"] = df["consensus_win_prob"] - df["open_home_win_prob"]
    df["sharp_gap_h2h"] = df["pinnacle_open_prob"] - df["open_home_win_prob"]
    df["anchor_gap_tot"] = df["pred_total_runs"] - df["open_total_line"]
    df["sharp_gap_tot"] = df["pinnacle_open_line"] - df["open_total_line"]
    return df


def _impute(train_raw: pd.DataFrame, eval_raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Median impute on train statistics; all-NaN-in-train columns (e.g. a 2026 enrichment
    in a pre-2026 training fold) fall back to 0.0 so NGBoost never sees a NaN."""
    med = train_raw.median(numeric_only=True)
    med = med.fillna(0.0)
    Xtr = train_raw.fillna(med).fillna(0.0)
    Xev = eval_raw.reindex(columns=train_raw.columns).fillna(med).fillna(0.0)
    return Xtr, Xev


def _directional_ci(y_true: np.ndarray, y_pred: np.ndarray, *, n_boot: int = 2000,
                    seed: int = 42) -> dict:
    """Directional accuracy (sign(pred)==sign(true)) over moved games (true!=0), with a
    bootstrap 90% CI. AC: lower bound > 0.5."""
    mask = y_true != 0
    yt, yp = y_true[mask], y_pred[mask]
    if len(yt) < 20:
        return {"n": int(len(yt)), "acc": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan")}
    hit = (np.sign(yt) == np.sign(yp)).astype(float)
    rng = np.random.default_rng(seed)
    boots = [hit[rng.integers(0, len(hit), len(hit))].mean() for _ in range(n_boot)]
    return {"n": int(len(yt)), "acc": float(hit.mean()),
            "ci_lo": float(np.percentile(boots, 5)), "ci_hi": float(np.percentile(boots, 95))}


def run_market(market: str, df: pd.DataFrame) -> dict:
    spec = MARKETS[market]
    target = spec["target"]
    feat_cols = spec["multi_season"] + spec["enrichment"]

    # Keep games with a realized move and a present opening line.
    d = df[df[target].notna() & df[spec["open_col"]].notna()].reset_index(drop=True)
    print(f"\n=== {market} Head-1 ({target}; {len(d)} games, "
          f"seasons {sorted(d['game_year'].unique().tolist())}) ===")

    _, splitter = make_purged_splitter(feature_cols=feat_cols)
    per_season, oos_true, oos_pred, oos_year = [], [], [], []
    for train_idx, eval_idx in splitter(d):
        yr = int(d.loc[eval_idx, "game_year"].mode().iloc[0])
        ytr = d.loc[train_idx, target].to_numpy()
        yev = d.loc[eval_idx, target].to_numpy()
        Xtr, Xev = _impute(d.loc[train_idx, feat_cols], d.loc[eval_idx, feat_cols])
        out = train_ngboost(Xtr, pd.Series(ytr), Xev, dist="Normal")
        pred = np.asarray(out["y_pred"])

        mae_model = float(np.mean(np.abs(yev - pred)))
        mae_nomove = float(np.mean(np.abs(yev)))                 # predict 0
        mae_drift = float(np.mean(np.abs(yev - ytr.mean())))     # predict train-mean
        di = _directional_ci(yev, pred)
        per_season.append({
            "season": yr, "n_eval": int(len(yev)), "n_train": int(len(ytr)),
            "mae_model": mae_model, "mae_nomove": mae_nomove, "mae_drift": mae_drift,
            "beats_nomove": mae_model < mae_nomove, "beats_drift": mae_model < mae_drift,
            "dir_acc": di["acc"], "dir_ci_lo": di["ci_lo"], "dir_ci_hi": di["ci_hi"],
        })
        oos_true.append(yev); oos_pred.append(pred); oos_year.append(np.full(len(yev), yr))
        print(f"  {yr}: MAE model={mae_model:.4f}  no-move={mae_nomove:.4f}  drift={mae_drift:.4f}"
              f"  | dir-acc={di['acc']:.3f} [{di['ci_lo']:.3f},{di['ci_hi']:.3f}]")

    yt = np.concatenate(oos_true); yp = np.concatenate(oos_pred)
    pooled_mae = float(np.mean(np.abs(yt - yp)))
    pooled_nomove = float(np.mean(np.abs(yt)))
    pooled_drift = float(np.mean(np.abs(yt - yt.mean())))
    pooled_dir = _directional_ci(yt, yp)
    passes = (pooled_mae < pooled_nomove and pooled_mae < pooled_drift
              and pooled_dir["ci_lo"] > 0.5)
    print(f"  POOLED: MAE model={pooled_mae:.4f}  no-move={pooled_nomove:.4f}  drift={pooled_drift:.4f}"
          f"  | dir-acc CI lo={pooled_dir['ci_lo']:.3f}  → {'PASS' if passes else 'NO EDGE'}")

    # Persist a full-data model artifact for later serving (NOT promoted — go-live gated by E1.4).
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    Xall, _ = _impute(d[feat_cols], d[feat_cols].head(1))
    full = train_ngboost(Xall, d[target], Xall.head(1), dist="Normal")
    joblib.dump({"model": full["model"], "feature_cols": feat_cols, "market": market,
                 "target": target, "trained_rows": int(len(d))},
                _MODEL_DIR / f"head1_{market}.joblib")

    return {
        "market": market, "target": target, "n_games": int(len(d)),
        "feature_cols": feat_cols,
        "pooled": {"mae_model": pooled_mae, "mae_nomove": pooled_nomove,
                   "mae_drift": pooled_drift, "dir_acc": pooled_dir["acc"],
                   "dir_ci_lo": pooled_dir["ci_lo"], "dir_ci_hi": pooled_dir["ci_hi"],
                   "n_moved": pooled_dir["n"]},
        "passes_e31_gate": bool(passes),
        "per_season": per_season,
    }


def _write_report(results: dict) -> None:
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _JSON.parent.mkdir(parents=True, exist_ok=True)
    _JSON.write_text(json.dumps(results, indent=2, default=float))
    lines = [
        "# Closing-Line Head-1 — Line-Movement Regression (Epic E3.1)",
        "",
        "NGBoost-Normal predicting Bovada's Δ(open→close), under the E1.1 purged walk-forward CV. "
        "Target is the book the user bets (the CLV Story-12.5 measures). Pinnacle sharp-open + "
        "Layer-2 baseball anchor are 2026-only enrichments (NULL pre-2026 ⇒ they help only the "
        "2026 fold for now). **E3.1 gate: beat BOTH no-move and drift on pooled OOS MAE AND "
        "directional-accuracy CI lower bound > 0.5.** Passing is necessary, not sufficient — "
        "go-live still needs E1.4 PBO<0.2 + DSR>0 + ≥100 forward live games positive CLV.",
        "",
        "| market | n games | MAE model | MAE no-move | MAE drift | dir-acc | dir CI lo | E3.1 gate |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m, r in results.items():
        p = r["pooled"]
        lines.append(
            f"| {m} | {r['n_games']} | {p['mae_model']:.4f} | {p['mae_nomove']:.4f} | "
            f"{p['mae_drift']:.4f} | {p['dir_acc']:.3f} | {p['dir_ci_lo']:.3f} | "
            f"{'✅ pass' if r['passes_e31_gate'] else '❌ no edge'} |")
    lines += ["", "_Pooled across the 2024/2025/2026 eval folds. `dir-acc` over moved games only._", ""]
    for m, r in results.items():
        lines += [f"## {m} — target `{r['target']}`", "",
                  f"- features ({len(r['feature_cols'])}): `{', '.join(r['feature_cols'])}`",
                  "", "| season | n eval | MAE model | no-move | drift | beats? | dir-acc [90% CI] |",
                  "|---|---|---|---|---|---|---|"]
        for s in r["per_season"]:
            beats = ("nm✓" if s["beats_nomove"] else "nm✗") + " " + ("dr✓" if s["beats_drift"] else "dr✗")
            lines.append(
                f"| {s['season']} | {s['n_eval']} | {s['mae_model']:.4f} | {s['mae_nomove']:.4f} | "
                f"{s['mae_drift']:.4f} | {beats} | {s['dir_acc']:.3f} "
                f"[{s['dir_ci_lo']:.3f},{s['dir_ci_hi']:.3f}] |")
        lines.append("")
    _REPORT.write_text("\n".join(lines))
    print(f"\nWrote {_REPORT}\nWrote {_JSON}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["h2h", "totals", "all"], default="all")
    ap.add_argument("--refresh-cache", action="store_true")
    args = ap.parse_args()

    df = get_cached_df("edge_e31_line_movement", load_line_movement_dataset,
                       refresh=args.refresh_cache)
    print(f"Loaded {len(df)} games; seasons {sorted(df['game_year'].dropna().unique().tolist())}")
    markets = ["h2h", "totals"] if args.market == "all" else [args.market]
    results = {m: run_market(m, df) for m in markets}
    _write_report(results)
    print("\n=== E3.1 HEAD-1 SUMMARY ===")
    for m, r in results.items():
        p = r["pooled"]
        print(f"  {m:7s}: MAE {p['mae_model']:.4f} vs no-move {p['mae_nomove']:.4f}/drift "
              f"{p['mae_drift']:.4f}; dir-CI-lo {p['dir_ci_lo']:.3f}  "
              f"{'✅ PASS' if r['passes_e31_gate'] else '❌ NO EDGE'}")


if __name__ == "__main__":
    main()
