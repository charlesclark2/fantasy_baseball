"""
analyze_totals_2026_failure.py — Epic 10 follow-up (post-10.6 investigation)

10.6 found BOTH totals models worse than the market AND worse than naive on the
2026 OOS gate (challenger Brier 0.3091 / champion 0.3129 vs Bovada de-vig 0.2281),
despite the challenger beating the market by +0.024 on 2023–2025. That ~0.10 Brier
sign-change in one season is structural, not variance. This script diagnoses WHY,
to decide whether it is fixable within the current architecture (early-season
cold-start, signal coverage, or feature freshness / distribution shift) or needs an
architecture change.

Outputs ablation_results/totals_2026_failure_analysis.md with:
  1. Brier by month (Apr/May/Jun 2026), challenger + champion, vs the 2023–25 baseline
  2. Brier by signal_completeness_score (>=0.8 vs <0.8), 2026 vs 2023–25
  3. Feature distribution shift: standardized (mean_2026 - mean_train)/std_train per signal
  4. High-confidence bin [0.80,1.00] breakdown by home_team (park proxy) + actual over-rate
  5. Go/No-Go recommendation

Reads the local OOS parquet (challenger) + load_layer3_features (matrix/dates/coverage/
features) + reuses score_champion_v4 (v4 on 2026). Snowflake-heavy → hand-off run.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.load_layer3_features import load_layer3_features, _load_feature_contract  # noqa: E402
from betting_ml.scripts.compare_totals_champion_challenger import score_champion_v4  # noqa: E402
from betting_ml.models.total_runs_trainer import p_over_line  # noqa: E402
from betting_ml.scripts.calibrate_totals_v1 import brier_score  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_OOS_PARQUET = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_predictions_totals_v1.parquet"
_REPORT = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results" / "totals_2026_failure_analysis.md"

_NAIVE = 0.25
_MARKET_2026 = 0.2281   # Bovada de-vig Brier on the 2026 gate set (from 10.6)


def _brier(df: pd.DataFrame, pcol: str) -> float:
    d = df[df[pcol].notna() & df["over_hit"].notna()]
    return brier_score(d[pcol].to_numpy(float), d["over_hit"].to_numpy(float)) if len(d) else np.nan


def build_frame(env: str) -> tuple[pd.DataFrame, list[str]]:
    """OOS challenger preds ⋈ Layer 3 matrix (dates/coverage/features/teams) + champion 2026 p_over."""
    P = pd.read_parquet(_OOS_PARQUET)
    P["game_pk"] = P["game_pk"].astype(int)

    M = load_layer3_features(min_games_played=15, start_date="2021-01-01", env=env)
    M["game_pk"] = M["game_pk"].astype(int)
    feat_cols = [c for c in _load_feature_contract() if c in M.columns
                 and pd.api.types.is_numeric_dtype(M[c])]
    ctx = ["game_pk", "game_date", "signal_completeness_score"]
    ctx += [c for c in ("home_team", "away_team") if c in M.columns]
    keep = list(dict.fromkeys(ctx + feat_cols))
    M = M[[c for c in keep if c in M.columns]].copy()
    M["game_date"] = pd.to_datetime(M["game_date"], errors="coerce")

    df = P.merge(M, on="game_pk", how="left")
    df["month"] = df["game_date"].dt.to_period("M").astype(str)

    # Champion v4 p_over on 2026 (genuine OOS for v4; in-sample on 2023-25 so we skip those).
    g26 = df[(df["season"] == 2026) & df["bovada_line"].notna()]["game_pk"].tolist()
    champ = score_champion_v4(g26)
    champ = champ.merge(df[["game_pk", "bovada_line"]], on="game_pk", how="left")
    champ["champ_p_over"] = p_over_line("Normal",
                                        {"loc": champ["champ_mu"].to_numpy(float),
                                         "scale": champ["champ_sigma"].to_numpy(float)},
                                        champ["bovada_line"].to_numpy(float))
    df = df.merge(champ[["game_pk", "champ_p_over"]], on="game_pk", how="left")
    log.info("Frame: %d OOS rows (%d in 2026); champion scored on %d",
             len(df), int((df["season"] == 2026).sum()), len(champ))
    return df, feat_cols


# --- 1. Brier by month -----------------------------------------------------
def brier_by_month(df: pd.DataFrame) -> pd.DataFrame:
    d = df[(df["season"] == 2026) & df["oos_p_over"].notna() & df["over_hit"].notna()]
    rows = []
    for mth, g in d.groupby("month"):
        rows.append({"month": mth, "n": len(g),
                     "challenger_brier": _brier(g, "oos_p_over"),
                     "champion_brier": _brier(g, "champ_p_over"),
                     "actual_over_rate": float(g["over_hit"].mean())})
    base = df[(df["season"].isin([2023, 2024, 2025])) & df["oos_p_over"].notna() & df["over_hit"].notna()]
    rows.append({"month": "2023-25 baseline", "n": len(base),
                 "challenger_brier": _brier(base, "oos_p_over"),
                 "champion_brier": np.nan, "actual_over_rate": float(base["over_hit"].mean())})
    return pd.DataFrame(rows)


# --- 2. Brier by signal coverage ------------------------------------------
def brier_by_coverage(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, yrs in (("2026", [2026]), ("2023-25", [2023, 2024, 2025])):
        d = df[df["season"].isin(yrs) & df["oos_p_over"].notna() & df["over_hit"].notna()
               & df["signal_completeness_score"].notna()]
        for cov_label, mask in (("coverage>=0.8", d["signal_completeness_score"] >= 0.8),
                                ("coverage<0.8", d["signal_completeness_score"] < 0.8)):
            g = d[mask]
            rows.append({"window": label, "coverage": cov_label, "n": len(g),
                         "challenger_brier": _brier(g, "oos_p_over")})
    return pd.DataFrame(rows)


# --- 3. Feature distribution shift ----------------------------------------
def feature_shift(df: pd.DataFrame, feat_cols: list[str], top: int = 15) -> pd.DataFrame:
    train = df[df["season"].isin([2021, 2022, 2023, 2024, 2025])]
    test = df[df["season"] == 2026]
    rows = []
    for c in feat_cols:
        tr = pd.to_numeric(train[c], errors="coerce").dropna()
        te = pd.to_numeric(test[c], errors="coerce").dropna()
        if len(tr) < 50 or len(te) < 20 or tr.std(ddof=1) == 0:
            continue
        std_shift = (te.mean() - tr.mean()) / tr.std(ddof=1)
        rows.append({"feature": c, "train_mean": tr.mean(), "train_std": tr.std(ddof=1),
                     "y2026_mean": te.mean(), "y2026_std": te.std(ddof=1),
                     "std_shift": std_shift, "abs_shift": abs(std_shift)})
    out = pd.DataFrame(rows).sort_values("abs_shift", ascending=False)
    return out.head(top)


# --- 4. High-confidence bin breakdown -------------------------------------
def highconf_breakdown(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    d = df[(df["season"] == 2026) & (df["oos_p_over"] >= 0.80) & df["over_hit"].notna()].copy()
    summary = {"n_highconf": len(d),
               "mean_pred": float(d["oos_p_over"].mean()) if len(d) else np.nan,
               "actual_over_rate": float(d["over_hit"].mean()) if len(d) else np.nan}
    if "home_team" in d.columns and len(d):
        by = (d.groupby("home_team")
              .agg(n=("over_hit", "size"), actual_over_rate=("over_hit", "mean"),
                   mean_pred=("oos_p_over", "mean"))
              .sort_values("n", ascending=False).reset_index())
    else:
        by = pd.DataFrame()
    return by, summary


# --- 5. Recommendation -----------------------------------------------------
def recommend(month: pd.DataFrame, cov: pd.DataFrame, shift: pd.DataFrame, hc: dict) -> list[str]:
    notes = []
    m26 = month[month["month"].str.startswith("2026")]
    if len(m26) >= 2:
        first, last = m26.iloc[0], m26.iloc[-1]
        improving = last["challenger_brier"] < first["challenger_brier"] - 0.02
        notes.append(f"- **Cold-start signal:** challenger Brier {first['month']} {first['challenger_brier']:.4f} "
                     f"→ {last['month']} {last['challenger_brier']:.4f} — "
                     + ("**improves over the season** (consistent with early-season EB cold-start; FIXABLE)."
                        if improving else "**does not materially improve** (not a simple cold-start)."))
    c26 = cov[cov["window"] == "2026"].set_index("coverage")["challenger_brier"]
    if {"coverage>=0.8", "coverage<0.8"} <= set(c26.index):
        gap = c26["coverage<0.8"] - c26["coverage>=0.8"]
        notes.append(f"- **Coverage:** Brier(<0.8) − Brier(>=0.8) = {gap:+.4f} — "
                     + ("low-coverage games drive the damage (FIXABLE via coverage gating)."
                        if gap > 0.03 else "coverage is NOT the main driver."))
    big = shift[shift["abs_shift"] >= 0.5]
    notes.append(f"- **Feature shift:** {len(big)} signal(s) shifted ≥0.5σ from training in 2026"
                 + (f" (top: {big.iloc[0]['feature']} {big.iloc[0]['std_shift']:+.2f}σ) — distribution shift / "
                    "freshness is a plausible root cause (FIXABLE)." if len(big) else
                    " — features are within the training distribution (shift is NOT the cause)."))
    if not np.isnan(hc.get("actual_over_rate", np.nan)):
        notes.append(f"- **High-confidence failure:** {hc['n_highconf']} games with p_over≥0.80 predicted "
                     f"{hc['mean_pred']:.3f} but hit {hc['actual_over_rate']:.3f} — the calibration break is "
                     "concentrated in over-confident OVER bets.")
    return notes


def run(env: str = "prod") -> None:
    df, feat_cols = build_frame(env)
    month = brier_by_month(df)
    cov = brier_by_coverage(df)
    shift = feature_shift(df, feat_cols)
    hc_by, hc = highconf_breakdown(df)
    rec = recommend(month, cov, shift, hc)

    lines = [
        "# Totals — 2026 OOS Failure Analysis (post-10.6 investigation)",
        "",
        f"Context: 10.6 found challenger Brier 0.3091 / champion 0.3129 vs **market {_MARKET_2026}** and "
        f"naive {_NAIVE} on 2026 — yet the challenger beat the market by +0.024 on 2023–25. "
        "A ~0.10 sign-change in one season ⇒ structural. This diagnoses fixable-vs-architectural.",
        "",
        "## 1. Brier by month (2026) vs 2023–25 baseline",
        month.to_markdown(index=False, floatfmt=".4f"),
        f"- Reference: market {_MARKET_2026}, naive {_NAIVE}. Lower is better; >0.25 = worse than a coin flip.",
        "",
        "## 2. Brier by signal coverage",
        cov.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## 3. Layer 3 feature distribution shift (2026 vs 2021–25 training)",
        f"Standardized shift = (mean_2026 − mean_train)/std_train. |shift|≥0.5σ flagged. Top {len(shift)}:",
        shift[["feature", "train_mean", "y2026_mean", "std_shift"]].to_markdown(index=False, floatfmt=".3f"),
        "",
        "## 4. High-confidence bin [0.80,1.00] breakdown (2026)",
        f"- {hc['n_highconf']} games; mean predicted P(over) {hc['mean_pred']:.3f}, actual over-rate "
        f"{hc['actual_over_rate']:.3f}.",
        (hc_by.head(12).to_markdown(index=False, floatfmt=".3f") if not hc_by.empty else "_no home_team data_"),
        "",
        "## 5. Go / No-Go recommendation",
        *rec,
        "",
        "**Decision:** if the drivers above are early-season cold-start, low coverage, or feature freshness, "
        "the 2026 failure is FIXABLE within the current architecture → proceed to 10.7 shadow once addressed. "
        "If features are in-distribution, coverage is balanced, and the damage does not concentrate/recover, "
        "the failure is more fundamental → revisit architecture (Phase 9) before building pipeline.",
    ]
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text("\n".join(lines) + "\n")
    log.info("Wrote %s", _REPORT)
    for n in rec:
        log.info(n)


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Diagnose the 2026 totals OOS failure (post-10.6)")
    p.add_argument("--env", choices=["prod", "dev"], default="prod")
    p.parse_args()
    run(env="prod")


if __name__ == "__main__":
    main()
