"""Story 29.1 — Totals point-accuracy benchmark (RMSE/MAE-to-actual).

The DECISION GATE for the reframed totals track (Epic 29). Nine prior confirmations
measured P_over/Brier (classification) or the Jensen mean-bias. NONE ran the
regression-loss test: is our predicted total a better POINT estimate of actual
runs than the Bovada line? A -110/-110 main line IS the market's point estimate,
so RMSE/MAE-to-actual is the honest "how close are we" yardstick.

Predictors compared on the leakage-free 2026 OOS surface (Bovada-source line only):
  - model_q50    : 10.10 quantile median   (oos_predictions_totals_quantile_10_10.parquet)
  - model_v4_mu  : NGBoost v4 champion mean (oos_predictions_totals_v1.parquet, oos_mu)
  - bovada_line  : the market's posted total (already joined in the parquets)
  - naive        : expanding season-to-date 2026 league mean total (leakage-safe;
                   games with game_date < T; seeded by the 2025 league mean)

No Snowflake read: the Bovada line was joined when the parquets were built
(load_total_line_bovada, which already unions the 2026 source-specific path).

EVAL ONLY — no training. Outputs an .md report + prints the table and verdict.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
L3 = REPO / "betting_ml" / "models" / "layer3"
QUANT_PARQUET = L3 / "oos_predictions_totals_quantile_10_10.parquet"
V4_PARQUET = L3 / "oos_predictions_totals_v1.parquet"
OUT_MD = REPO / "quant_sports_intel_models" / "baseball" / "ablation_results" / "totals_point_accuracy_29_1.md"

MONTHS = {4: "Apr", 5: "May", 6: "Jun"}


def _metrics(pred: np.ndarray, actual: np.ndarray) -> dict:
    """RMSE / MAE / median-abs-error / bias for a point predictor vs actual."""
    err = pred - actual
    return {
        "n": int(len(actual)),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mae": float(np.mean(np.abs(err))),
        "medae": float(np.median(np.abs(err))),
        "bias": float(np.mean(err)),  # mean(pred - actual); + = over-predicts
    }


def _naive_expanding(df: pd.DataFrame, seed_mean: float) -> pd.Series:
    """Leakage-safe expanding league mean: for a game on date T, the mean of all
    2026 actual totals on dates strictly < T; seeded by the 2025 league mean until
    the first prior date exists. Same-day games are NOT used (unknown pre-game)."""
    daily = df.groupby("game_date")["actual_total_runs"].agg(["sum", "count"]).sort_index()
    cum_sum = daily["sum"].cumsum().shift(1)   # strictly-before-T totals
    cum_cnt = daily["count"].cumsum().shift(1)
    prior_mean_by_date = (cum_sum / cum_cnt)
    prior_mean_by_date = prior_mean_by_date.fillna(seed_mean)  # earliest dates -> 2025 mean
    return df["game_date"].map(prior_mean_by_date)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="prod", help="kept for prompt parity; no Snowflake read needed")
    args = ap.parse_args()

    q = pd.read_parquet(QUANT_PARQUET)
    v = pd.read_parquet(V4_PARQUET)

    # 2025 league mean (naive seed) from the eval pool itself.
    seed_2025 = float(q.loc[q.season == 2025, "actual_total_runs"].mean())

    # Bring the v4 champion mean onto the quantile frame (game_date lives only on q).
    v4 = v[["game_pk", "season", "oos_mu"]].rename(columns={"oos_mu": "model_v4_mu"})
    df = q.merge(v4, on=["game_pk", "season"], how="left")

    d26 = df[df.season == 2026].copy()
    d26["month"] = d26["game_date"].dt.month
    d26["naive"] = _naive_expanding(d26, seed_2025)
    d26 = d26.rename(columns={"q50": "model_q50"})

    # Honest surface: Bovada-source line only (per the 29.1 surface guard).
    honest = d26[(d26["total_line_source"] == "bovada") & d26["bovada_line"].notna()].copy()
    # Secondary surface: any available line (bovada + consensus_fallback).
    broad = d26[d26["bovada_line"].notna()].copy()

    predictors = ["model_q50", "model_v4_mu", "bovada_line", "naive"]

    def panel(data: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for scope_name, sub in [("2026 (all)", data)] + [
            (f"2026 {MONTHS[m]}", data[data.month == m]) for m in sorted(data.month.unique())
        ]:
            actual = sub["actual_total_runs"].to_numpy()
            for p in predictors:
                m = _metrics(sub[p].to_numpy(), actual)
                rows.append({"scope": scope_name, "predictor": p, **m})
        return pd.DataFrame(rows)

    honest_panel = panel(honest)
    broad_panel = panel(broad)

    # ── Verdict logic: model (best of q50/v4) RMSE & MAE vs Bovada line on honest 2026 (all) ──
    h_all = honest_panel[honest_panel.scope == "2026 (all)"].set_index("predictor")
    line_rmse, line_mae = h_all.loc["bovada_line", "rmse"], h_all.loc["bovada_line", "mae"]
    best_model = min(["model_q50", "model_v4_mu"], key=lambda p: h_all.loc[p, "rmse"])
    m_rmse, m_mae = h_all.loc[best_model, "rmse"], h_all.loc[best_model, "mae"]
    rmse_gap = m_rmse - line_rmse  # negative => model beats the line
    mae_gap = m_mae - line_mae

    if rmse_gap <= 0:
        verdict = (f"PROCEED — best model ({best_model}) RMSE {m_rmse:.4f} <= Bovada line {line_rmse:.4f} "
                   f"(gap {rmse_gap:+.4f}). Central-estimate edge exists; advance to 29.2/29.3.")
    elif rmse_gap <= 0.10:
        verdict = (f"MARGINAL — best model ({best_model}) RMSE {m_rmse:.4f} vs line {line_rmse:.4f} "
                   f"(gap {rmse_gap:+.4f}, within ~0.10). Near parity; 29.2 calibration could close it. "
                   f"Proceed to 29.2 but treat 29.3 as conditional.")
    else:
        verdict = (f"DOWNGRADE — best model ({best_model}) RMSE {m_rmse:.4f} >> Bovada line {line_rmse:.4f} "
                   f"(gap {rmse_gap:+.4f}). No central-estimate edge; 29.3 downgraded, totals stay product-only.")

    def fmt(p: pd.DataFrame) -> str:
        out = []
        for scope in p.scope.unique():
            out.append(f"\n**{scope}**\n")
            out.append("| predictor | n | RMSE | MAE | MedAE | bias |")
            out.append("|---|--:|--:|--:|--:|--:|")
            for _, r in p[p.scope == scope].iterrows():
                out.append(f"| {r.predictor} | {r.n} | {r.rmse:.4f} | {r.mae:.4f} | {r.medae:.4f} | {r.bias:+.4f} |")
        return "\n".join(out)

    report = f"""# Story 29.1 — Totals Point-Accuracy Benchmark (RMSE/MAE-to-actual)

**Surface:** leakage-free 2026 OOS. **Honest panel = Bovada-source line only** (n={len(honest)});
secondary panel = any available line incl. consensus_fallback (n={len(broad)}).
**Eval only — no training.** Predictors: `model_q50` (10.10 quantile median), `model_v4_mu`
(NGBoost v4 champion mean), `bovada_line` (market posted total), `naive` (expanding season-to-date
2026 league mean, leakage-safe, seeded by 2025 mean = {seed_2025:.4f}).

`bias` = mean(pred − actual): positive over-predicts. RMSE penalizes large misses (mean-optimal);
MAE/MedAE are median-optimal, so `model_q50` (a median) is most fairly read on MAE/MedAE.

## VERDICT
{verdict}

(RMSE gap {rmse_gap:+.4f}, MAE gap {mae_gap:+.4f}; best model = {best_model}.)

## Honest panel — Bovada-source line only
{fmt(honest_panel)}

## Secondary panel — any available line (bovada + consensus_fallback)
{fmt(broad_panel)}

## Notes
- A sharp -110/-110 line is the market's own point estimate, so `bovada_line` is the benchmark to beat
  on RMSE/MAE; `naive` is the floor any model must clear to claim *any* point-prediction signal.
- The line's own `bias` row quantifies how well-centered the 2026 market was (vs the model's bias).
- Monthly split exposes regime shifts (the Apr→May→Jun scoring-environment move).
"""
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(report)

    print(report)
    print(f"\nWrote {OUT_MD.relative_to(REPO)}")


if __name__ == "__main__":
    main()
