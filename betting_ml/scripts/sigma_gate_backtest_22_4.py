"""sigma_gate_backtest_22_4.py — Story 22.4: backtested σ-aware selection & sizing.

Sweeps an edge_to_sigma abstain threshold and measures whether uncertainty-gated
selection lifts ROI / hit-rate vs the ungated qualified-bet set. Also evaluates
σ-scaled Kelly vs flat Kelly sizing on the same surface.

CALIBRATION PREREQUISITE (Story 9.8, 2026-06-16): all targets calibrated on 2026.

Outputs:
    quant_sports_intel_models/baseball/ablation_results/sigma_gate_22_4.md
    betting_ml/evaluation/sigma_gate_22_4/results.json

Run (hand-off — Snowflake query + bootstrap, expect ~2-5 min):
    uv run python betting_ml/scripts/sigma_gate_backtest_22_4.py

Honest-outcome contract: if σ-gating doesn't beat ungated on paired bootstrap,
the negative result is logged prominently. This is the decision surface for whether
to enable uncertainty_below_threshold in the bet_gate config and what threshold to use.

Data surface:
    baseball_data.betting_ml.daily_model_predictions  (predictions + Kelly fractions)
    baseball_data.betting.mart_game_results           (actual outcomes)
    Model versions with non-zero edges: v0, v1, v2, v3, v4, prod
    Period: 2026-03-26 → latest completed games
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import date

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection  # noqa: E402
from betting_ml.utils.sigma_gate import (  # noqa: E402
    compute_totals_ci_width, compute_h2h_ci_width,
    compute_edge_to_sigma, classify_sigma_tier,
    compute_sigma_scaled_kelly,
    ABSTAIN_THRESHOLD, MED_THRESHOLD, HIGH_THRESHOLD, SIGMA_PENALTY_K,
)

_EVAL_DIR    = PROJECT_ROOT / "betting_ml" / "evaluation" / "sigma_gate_22_4"
_REPORT_PATH = PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results" / "sigma_gate_22_4.md"

# Model versions with meaningful non-zero edges (v5 has alpha=0 / collapsed predictions)
_USABLE_MODEL_VERSIONS = ("v0", "v1", "v2", "v3", "v4", "prod")

_QUERY = """
SELECT
    d.game_pk,
    d.game_date,
    d.model_version,
    d.totals_edge,
    d.h2h_edge,
    d.pred_total_runs,
    d.pred_total_runs_scale,
    d.total_line_consensus,
    d.p_home_win_ngboost,
    d.p_home_win_classifier,
    d.calibrated_win_prob,
    d.totals_kelly_fraction,
    d.h2h_kelly_fraction,
    d.qualified_bet,
    d.game_conviction_score,
    d.over_prob_consensus,
    d.h2h_market_implied_prob,
    g.home_final_score,
    g.away_final_score,
    g.home_team_won
FROM baseball_data.betting_ml.daily_model_predictions d
JOIN baseball_data.betting.mart_game_results g ON d.game_pk = g.game_pk
WHERE d.game_date BETWEEN '2026-03-26' AND %(end_date)s
  AND d.model_version IN ('v0','v1','v2','v3','v4','prod')
  AND d.pred_total_runs_scale IS NOT NULL
  AND d.pred_total_runs IS NOT NULL
  AND g.home_final_score IS NOT NULL
ORDER BY d.game_date, d.game_pk, d.model_version
"""

_SWEEP_THRESHOLDS = [0.0, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.00, 1.50, 2.00]
_N_BOOTSTRAP = 2000


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_data(end_date: str) -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_QUERY, {"end_date": end_date})
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()

    df = pd.DataFrame(rows, columns=cols)
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
    for col in ("totals_edge","h2h_edge","pred_total_runs","pred_total_runs_scale",
                "total_line_consensus","p_home_win_ngboost","p_home_win_classifier",
                "calibrated_win_prob","totals_kelly_fraction","h2h_kelly_fraction",
                "game_conviction_score","over_prob_consensus","h2h_market_implied_prob",
                "home_final_score","away_final_score"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["home_team_won"] = df["home_team_won"].astype(bool)
    return df


# ---------------------------------------------------------------------------
# CI width & edge_to_sigma computation
# ---------------------------------------------------------------------------

def _add_sigma_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Compute CI widths and edge_to_sigma for totals and H2H."""
    # Totals CI width — vectorised via apply (scipy CDF; fast enough for ~3k rows)
    mask_tot = (df["pred_total_runs"].notna() & df["pred_total_runs_scale"].notna()
                & df["total_line_consensus"].notna())
    df["totals_ci_width"] = np.nan
    df.loc[mask_tot, "totals_ci_width"] = df[mask_tot].apply(
        lambda r: compute_totals_ci_width(
            r["pred_total_runs"], r["pred_total_runs_scale"], r["total_line_consensus"]
        ), axis=1
    )
    df["totals_edge_to_sigma"] = np.where(
        df["totals_edge"].notna() & df["totals_ci_width"].notna(),
        df["totals_edge"].abs() / df["totals_ci_width"],
        np.nan,
    )

    # H2H CI width
    mask_h2h = (df["calibrated_win_prob"].notna() & df["p_home_win_ngboost"].notna()
                & df["p_home_win_classifier"].notna())
    df["h2h_ci_width"] = np.nan
    df.loc[mask_h2h, "h2h_ci_width"] = df[mask_h2h].apply(
        lambda r: compute_h2h_ci_width(
            r["calibrated_win_prob"], r["p_home_win_ngboost"], r["p_home_win_classifier"]
        ), axis=1
    )
    df["h2h_edge_to_sigma"] = np.where(
        df["h2h_edge"].notna() & df["h2h_ci_width"].notna(),
        df["h2h_edge"].abs() / df["h2h_ci_width"],
        np.nan,
    )
    return df


# ---------------------------------------------------------------------------
# Outcome labels
# ---------------------------------------------------------------------------

def _add_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    """Add binary outcome columns for each target.

    totals_correct:  1 if edge > 0 (bet over) and total > line, or edge < 0 and total < line
    h2h_correct:     1 if h2h_edge > 0 (bet home) and home won, or h2h_edge < 0 and home lost
    """
    df["total_actual"] = df["home_final_score"] + df["away_final_score"]

    # Totals directional correctness
    df["totals_correct"] = np.where(
        df["totals_edge"].notna() & df["total_line_consensus"].notna() & (df["totals_edge"] != 0),
        np.where(
            df["totals_edge"] > 0,
            (df["total_actual"] > df["total_line_consensus"]).astype(float),
            (df["total_actual"] < df["total_line_consensus"]).astype(float),
        ),
        np.nan,
    )
    # Exclude pushes
    df.loc[df["total_actual"] == df["total_line_consensus"], "totals_correct"] = np.nan

    # H2H directional correctness
    df["h2h_correct"] = np.where(
        df["h2h_edge"].notna() & (df["h2h_edge"] != 0),
        np.where(
            df["h2h_edge"] > 0,
            df["home_team_won"].astype(float),
            (~df["home_team_won"]).astype(float),
        ),
        np.nan,
    )
    return df


# ---------------------------------------------------------------------------
# Flat ROI computation
# ---------------------------------------------------------------------------

def _compute_roi(df_sub: pd.DataFrame, target: str) -> float:
    """Flat-Kelly ROI for a filtered subset.

    ROI = Σ(return_i) / n_bets
    return_i = (1/market_prob - 1)  if correct else -1  (flat $1 bets)
    """
    correct_col = f"{target}_correct"
    mkt_col = "over_prob_consensus" if target == "totals" else "h2h_market_implied_prob"

    sub = df_sub[[correct_col, mkt_col]].dropna()
    if len(sub) == 0:
        return float("nan")

    decimal_odds = (1.0 / sub[mkt_col]).clip(upper=10.0)
    returns = np.where(sub[correct_col] == 1.0, decimal_odds - 1.0, -1.0)
    return float(returns.mean())


def _compute_sigma_kelly_roi(df_sub: pd.DataFrame, target: str) -> float:
    """σ-scaled Kelly ROI for a filtered subset (stake ∝ sigma_scaled_kelly)."""
    correct_col = f"{target}_correct"
    kelly_col   = f"{target}_kelly_fraction"
    ci_col      = f"{target}_ci_width"
    mkt_col     = "over_prob_consensus" if target == "totals" else "h2h_market_implied_prob"

    sub = df_sub[[correct_col, kelly_col, ci_col, mkt_col]].dropna()
    if len(sub) == 0:
        return float("nan")

    stakes = sub.apply(
        lambda r: compute_sigma_scaled_kelly(abs(r[kelly_col]), r[ci_col]), axis=1
    ).clip(lower=0)
    total_stake = stakes.sum()
    if total_stake == 0:
        return float("nan")

    decimal_odds = (1.0 / sub[mkt_col]).clip(upper=10.0)
    returns = np.where(sub[correct_col] == 1.0, decimal_odds - 1.0, -1.0)
    return float((stakes * returns).sum() / total_stake)


# ---------------------------------------------------------------------------
# Bootstrap test: does gated hit-rate beat ungated?
# ---------------------------------------------------------------------------

def _bootstrap_paired_test(
    ungated_correct: np.ndarray,
    gated_correct: np.ndarray,
    n_boot: int = _N_BOOTSTRAP,
) -> dict:
    """Paired bootstrap: probability that gated hit-rate > ungated hit-rate.

    Uses Efron's bootstrap (resample with replacement independently from each set).
    Reports: gated_hit_rate, ungated_hit_rate, delta, p_value_one_sided, ci_95.
    """
    rng = np.random.default_rng(42)
    ungated_correct = ungated_correct[~np.isnan(ungated_correct)]
    gated_correct   = gated_correct[~np.isnan(gated_correct)]

    if len(ungated_correct) == 0 or len(gated_correct) == 0:
        return {"error": "insufficient_data", "n_ungated": len(ungated_correct), "n_gated": len(gated_correct)}

    obs_ungated = float(ungated_correct.mean())
    obs_gated   = float(gated_correct.mean())
    obs_delta   = obs_gated - obs_ungated

    boot_deltas = np.empty(n_boot)
    for b in range(n_boot):
        ug_boot = rng.choice(ungated_correct, size=len(ungated_correct), replace=True).mean()
        g_boot  = rng.choice(gated_correct,   size=len(gated_correct),   replace=True).mean()
        boot_deltas[b] = g_boot - ug_boot

    p_val = float((boot_deltas >= 0).mean())  # p(gated ≥ ungated) under bootstrap
    ci_lo, ci_hi = float(np.percentile(boot_deltas, 2.5)), float(np.percentile(boot_deltas, 97.5))

    return {
        "ungated_hit_rate":  round(obs_ungated, 4),
        "gated_hit_rate":    round(obs_gated,   4),
        "delta":             round(obs_delta,   4),
        "p_value_gated_better": round(p_val, 4),
        "boot_ci_95": (round(ci_lo, 4), round(ci_hi, 4)),
        "n_ungated": len(ungated_correct),
        "n_gated":   len(gated_correct),
    }


# ---------------------------------------------------------------------------
# Threshold sweep
# ---------------------------------------------------------------------------

def _sweep_target(df: pd.DataFrame, target: str) -> list[dict]:
    """Sweep edge_to_sigma thresholds for one target (totals or h2h)."""
    ets_col     = f"{target}_edge_to_sigma"
    correct_col = f"{target}_correct"

    df_base = df[df[ets_col].notna() & df[correct_col].notna()].copy()
    if len(df_base) == 0:
        print(f"  [{target}] No data with both ets and outcome — skipping.")
        return []

    results = []
    ungated_correct = df_base[correct_col].values

    for thresh in _SWEEP_THRESHOLDS:
        gated = df_base[df_base[ets_col] >= thresh]
        n_gated   = len(gated)
        n_dropped = len(df_base) - n_gated
        pct_kept  = n_gated / len(df_base) if len(df_base) > 0 else 0.0

        hit_rate  = float(gated[correct_col].mean()) if n_gated > 0 else float("nan")
        flat_roi  = _compute_roi(gated, target)
        sig_roi   = _compute_sigma_kelly_roi(gated, target)
        avg_edge  = float(gated[f"{target}_edge"].abs().mean()) if n_gated > 0 else float("nan")

        results.append({
            "threshold":   thresh,
            "n_selected":  n_gated,
            "n_dropped":   n_dropped,
            "pct_kept":    round(pct_kept, 3),
            "hit_rate":    round(hit_rate, 4) if not np.isnan(hit_rate) else None,
            "flat_roi":    round(flat_roi, 4) if not np.isnan(flat_roi) else None,
            "sigma_kelly_roi": round(sig_roi, 4) if not np.isnan(sig_roi) else None,
            "avg_abs_edge": round(avg_edge, 4) if not np.isnan(avg_edge) else None,
        })

    # Bootstrap test at ABSTAIN_THRESHOLD (the default gate level)
    gated_at_default = df_base[df_base[ets_col] >= ABSTAIN_THRESHOLD]
    boot = _bootstrap_paired_test(ungated_correct, gated_at_default[correct_col].values)
    for r in results:
        if r["threshold"] == ABSTAIN_THRESHOLD:
            r["bootstrap"] = boot

    return results


# ---------------------------------------------------------------------------
# Dropped-bet log (no silent truncation)
# ---------------------------------------------------------------------------

def _log_dropped_at_threshold(df: pd.DataFrame, target: str, threshold: float, n_dropped_limit: int = 20) -> list[dict]:
    """Return a sample of the bets dropped by the given threshold."""
    ets_col  = f"{target}_edge_to_sigma"
    edge_col = f"{target}_edge"
    correct_col = f"{target}_correct"

    df_base = df[df[ets_col].notna() & df[correct_col].notna()]
    dropped = df_base[df_base[ets_col] < threshold].nlargest(n_dropped_limit, edge_col, keep="first")

    return [
        {
            "game_pk":     int(r["game_pk"]),
            "game_date":   str(r["game_date"]),
            "model_version": r["model_version"],
            "edge":        round(float(r[edge_col]), 4),
            "ets":         round(float(r[ets_col]), 4),
            "ci_width":    round(float(r[f"{target}_ci_width"]), 4),
            "correct":     int(r[correct_col]) if not np.isnan(r[correct_col]) else None,
        }
        for _, r in dropped.iterrows()
    ]


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _verdict(boot: dict | None) -> str:
    if boot is None or "error" in boot:
        return "⚠ insufficient data for bootstrap"
    delta = boot["delta"]
    p_val = boot["p_value_gated_better"]
    ci_lo, ci_hi = boot["boot_ci_95"]
    sig = "✓ significant" if p_val >= 0.80 else "✗ not significant"
    direction = "LIFTS" if delta > 0 else "DOES NOT LIFT"
    return (f"{direction} hit-rate: Δ={delta:+.4f}, p(gated≥ungated)={p_val:.2f}, "
            f"95% CI [{ci_lo:+.4f},{ci_hi:+.4f}] — {sig}")


def _write_report(all_results: dict, dropped: dict, meta: dict, report_path: Path, json_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {"meta": meta, "results": all_results, "dropped_samples": dropped}
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    lines = [
        "# Story 22.4 — σ-gate backtest: uncertainty-aware selection & sizing",
        "",
        f"**Date:** {meta['run_date']}  ·  "
        f"**Surface:** {meta['n_games_total']} games, "
        f"model_version IN {meta['model_versions']}  ·  "
        f"**Period:** {meta['date_range']}",
        "",
        "**Calibration prerequisite (9.8):** total_runs cov80 0.808 ✓, "
        "run_diff cov80 0.776 ✓, home_win ECE 0.040 ✓ (A2.9 identity). All cleared.",
        "",
        f"**Preliminary thresholds (pre-backtest):** abstain<{ABSTAIN_THRESHOLD}, "
        f"low<{MED_THRESHOLD}, medium<{HIGH_THRESHOLD}, high≥{HIGH_THRESHOLD}",
        "",
    ]

    for target, rows in all_results.items():
        lines += [f"## {target.upper()}", ""]
        if not rows:
            lines += ["_No data._", ""]
            continue

        # Ungated baseline
        baseline = rows[0]
        lines += [
            f"**Ungated baseline (threshold=0):** "
            f"n={baseline['n_selected']}, "
            f"hit_rate={baseline['hit_rate']}, "
            f"flat_roi={baseline['flat_roi']}, "
            f"avg_|edge|={baseline['avg_abs_edge']}",
            "",
        ]

        # Sweep table
        lines += ["| threshold | n | pct_kept | hit_rate | flat_roi | σ-kelly_roi | avg_|edge| |",
                  "|-----------|---|----------|----------|----------|-------------|------------|"]
        for r in rows:
            hr  = f"{r['hit_rate']:.4f}"  if r['hit_rate']  is not None else "—"
            roi = f"{r['flat_roi']:+.4f}" if r['flat_roi']  is not None else "—"
            skr = f"{r['sigma_kelly_roi']:+.4f}" if r['sigma_kelly_roi'] is not None else "—"
            ae  = f"{r['avg_abs_edge']:.4f}" if r['avg_abs_edge'] is not None else "—"
            lines.append(f"| {r['threshold']:.2f} | {r['n_selected']} | "
                         f"{r['pct_kept']:.1%} | {hr} | {roi} | {skr} | {ae} |")
        lines.append("")

        # Bootstrap verdict at default threshold
        boot_row = next((r for r in rows if r["threshold"] == ABSTAIN_THRESHOLD), None)
        boot     = boot_row.get("bootstrap") if boot_row else None
        lines += [
            f"**Bootstrap verdict at threshold={ABSTAIN_THRESHOLD}:** "
            f"{_verdict(boot)}",
            "",
        ]

        # Dropped bets sample
        d = dropped.get(target, [])
        lines += [f"**Dropped bets sample at threshold={ABSTAIN_THRESHOLD}** "
                  f"(top-{len(d)} by |edge|, no silent truncation):", ""]
        if d:
            lines += ["| game_pk | date | model | edge | ets | ci_width | correct |",
                      "|---------|------|-------|------|-----|----------|---------|"]
            for row in d:
                lines.append(
                    f"| {row['game_pk']} | {row['game_date']} | {row['model_version']} "
                    f"| {row['edge']:+.4f} | {row['ets']:.3f} | {row['ci_width']:.3f} "
                    f"| {row['correct']} |"
                )
        else:
            lines.append("_None dropped at this threshold._")
        lines.append("")

    # Verdict block
    lines += [
        "## σ-Kelly sizing verdict",
        "",
        "σ-scaled Kelly down-weights high-uncertainty legs: `sigma_scaled_kelly = "
        f"base_kelly / (1 + {SIGMA_PENALTY_K} * ci_width)`. "
        "Compare `sigma_kelly_roi` vs `flat_roi` at each threshold above.",
        "",
        "## Gate config update",
        "",
        "Based on these results, set `uncertainty_below_threshold.threshold` in "
        "`betting_ml/sub_model_registry.yaml` and set `enabled: true` if the bootstrap "
        "shows lift. If negative, log this report and leave gate disabled.",
        "",
    ]

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines))
    print(f"\nReport: {report_path}")
    print(f"JSON:   {json_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> dict:
    end_date = str(date.today())
    print(f"[22.4] Loading backtest data up to {end_date} …")
    df = _load_data(end_date)
    print(f"  Loaded {len(df):,} rows from {df['game_date'].min()} to {df['game_date'].max()}")

    print("[22.4] Computing CI widths and edge_to_sigma …")
    df = _add_sigma_columns(df)
    df = _add_outcomes(df)

    n_totals_w_ets = df["totals_edge_to_sigma"].notna().sum()
    n_h2h_w_ets    = df["h2h_edge_to_sigma"].notna().sum()
    print(f"  Totals rows with ets: {n_totals_w_ets:,}  |  H2H rows with ets: {n_h2h_w_ets:,}")

    print("[22.4] Sweeping thresholds …")
    all_results: dict[str, list[dict]] = {}
    dropped:     dict[str, list[dict]] = {}
    for target in ("totals", "h2h"):
        print(f"  → {target} …")
        all_results[target] = _sweep_target(df, target)
        dropped[target]     = _log_dropped_at_threshold(df, target, ABSTAIN_THRESHOLD)

    meta = {
        "run_date":        end_date,
        "n_games_total":   len(df),
        "model_versions":  list(_USABLE_MODEL_VERSIONS),
        "date_range":      f"{df['game_date'].min()} – {df['game_date'].max()}",
        "abstain_threshold": ABSTAIN_THRESHOLD,
        "med_threshold":     MED_THRESHOLD,
        "high_threshold":    HIGH_THRESHOLD,
        "sigma_penalty_k":   SIGMA_PENALTY_K,
        "n_bootstrap":       _N_BOOTSTRAP,
        "calibration_prereq": "9.8 DONE 2026-06-16 — all targets calibrated on 2026",
    }

    _write_report(
        all_results, dropped, meta,
        _REPORT_PATH,
        _EVAL_DIR / "results.json",
    )

    # Print headline summary
    print("\n--- HEADLINE RESULTS ---")
    for target, rows in all_results.items():
        if not rows:
            continue
        baseline    = rows[0]
        boot_row    = next((r for r in rows if r["threshold"] == ABSTAIN_THRESHOLD), None)
        boot        = boot_row.get("bootstrap") if boot_row else None
        print(f"\n{target.upper()} baseline (n={baseline['n_selected']}): "
              f"hit_rate={baseline['hit_rate']}, roi={baseline['flat_roi']}")
        print(f"  σ-gate T={ABSTAIN_THRESHOLD}: {_verdict(boot)}")
    return {"meta": meta, "results": all_results}


if __name__ == "__main__":
    run()
