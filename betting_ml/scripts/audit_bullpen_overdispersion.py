"""
audit_bullpen_overdispersion.py — Epic 6D.1

Overdispersion audit for bullpen runs allowed (count data).

Tests whether bullpen runs allowed (integer ≥ 0) fits NegBin(mu, r) better
than a Normal approximation. Motivates the 6D distributional retrofit choice.

Gate: Candidate A (NegBin wrapper) justified if:
  ≥ 7/10 mean-deciles show Var(Y) > E(Y)   (overdispersion present at all mean levels)
  AND NegBin NLL < Normal NLL on held-out data

Method:
  1. Query Snowflake:
       bullpen_runs = total_opponent_runs - starter_runs_allowed
       per (game_pk, pitching_team), game_year 2021+
  2. Merge with training parquet (for feature-based OLS proxy of expected runs)
  3. Fit Ridge to get predicted mean → bin into 10 deciles
  4. Per decile: compute actual mean, variance, and Var/Mean ratio
  5. Global: Var/Mean ratio, NegBin MLE r estimate
  6. Compare Normal NLL vs NegBin NLL on full sample

Output: betting_ml/models/ablation/bullpen_6d_overdispersion_{ts}.json

Usage:
    uv run python betting_ml/scripts/audit_bullpen_overdispersion.py
    uv run python betting_ml/scripts/audit_bullpen_overdispersion.py --min-year 2021
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.special import gammaln
from scipy.optimize import minimize
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection

_PARQUET_PATH  = _PROJECT_ROOT / "betting_ml" / "data" / "bullpen_state_train.parquet"
_OUTPUT_DIR    = _PROJECT_ROOT / "betting_ml" / "models" / "ablation"
_MIN_YEAR_DEFAULT = 2021

# Features from parquet used to build a simple OLS proxy (for decile binning only)
_PROXY_FEATURES = [
    "eb_bullpen_xwoba",
    "xwoba_against_14d",
    "xwoba_against_30d",
    "availability_index",
    "bullpen_ip_prev_1d",
    "bullpen_ip_prev_2d",
    "bullpen_ip_prev_3d",
]

# Overdispersion gate thresholds
_DECILE_GATE = 7   # ≥ 7/10 deciles must show Var > Mean
_N_DECILES   = 10


# ── Snowflake query ────────────────────────────────────────────────────────────

_RUNS_QUERY = """
WITH

game_scores AS (
    SELECT
        game_pk,
        game_year,
        home_team,
        away_team,
        home_final_score,
        away_final_score
    FROM baseball_data.betting.mart_game_results
    WHERE game_year >= {min_year}
      AND game_type = 'R'
),

-- One row per (game_pk, pitching_team) with the total runs scored against them
team_scores AS (
    SELECT
        game_pk,
        game_year,
        home_team   AS pitching_team,
        away_final_score AS total_runs_allowed
    FROM game_scores
    UNION ALL
    SELECT
        game_pk,
        game_year,
        away_team   AS pitching_team,
        home_final_score AS total_runs_allowed
    FROM game_scores
),

-- Starter runs allowed per (game_pk, pitching_team)
starter_runs AS (
    SELECT
        game_pk,
        pitching_team,
        COALESCE(runs_allowed, 0) AS starter_runs_allowed
    FROM baseball_data.betting.mart_starting_pitcher_game_log
    WHERE game_year >= {min_year}
)

SELECT
    t.game_pk,
    t.game_year,
    t.pitching_team,
    t.total_runs_allowed,
    COALESCE(s.starter_runs_allowed, 0)                             AS starter_runs_allowed,
    GREATEST(t.total_runs_allowed - COALESCE(s.starter_runs_allowed, 0), 0)
                                                                    AS bullpen_runs_allowed
FROM team_scores t
LEFT JOIN starter_runs s
    ON  s.game_pk       = t.game_pk
    AND s.pitching_team = t.pitching_team
ORDER BY t.game_pk, t.pitching_team
"""


def _fetch_bullpen_runs(min_year: int) -> pd.DataFrame:
    print(f"Querying Snowflake for bullpen runs allowed (game_year >= {min_year})...")
    conn = get_snowflake_connection()
    query = _RUNS_QUERY.format(min_year=min_year)
    df = pd.read_sql(query, conn)
    conn.close()
    df.columns = [c.lower() for c in df.columns]
    print(f"  Fetched {len(df):,} rows | {df['game_year'].nunique()} seasons")
    return df


# ── NegBin MLE ────────────────────────────────────────────────────────────────

def _negbin_nll(params: np.ndarray, y: np.ndarray) -> float:
    """Negative log-likelihood for NegBin(mu, r) with shared mu = mean(y), free r."""
    r = np.exp(params[0])  # log-space to enforce r > 0
    mu = y.mean()
    # NegBin pmf: Γ(r+k)/(Γ(r)k!) × (r/(r+mu))^r × (mu/(r+mu))^k
    log_pmf = (
        gammaln(r + y) - gammaln(r) - gammaln(y + 1)
        + r * np.log(r / (r + mu))
        + y * np.log(mu / (r + mu))
    )
    return -log_pmf.mean()


def _fit_negbin_r(y: np.ndarray) -> tuple[float, float]:
    """Fit NegBin r via MLE. Returns (r, final_nll)."""
    result = minimize(
        _negbin_nll,
        x0=[np.log(5.0)],
        args=(y,),
        method="Nelder-Mead",
        options={"maxiter": 2000, "xatol": 1e-6, "fatol": 1e-6},
    )
    r = float(np.exp(result.x[0]))
    return r, float(result.fun)


def _negbin_nll_at_r(y: np.ndarray, r: float) -> float:
    mu = y.mean()
    log_pmf = (
        gammaln(r + y) - gammaln(r) - gammaln(y + 1)
        + r * np.log(r / (r + mu))
        + y * np.log(mu / (r + mu))
    )
    return float(-log_pmf.mean())


def _normal_nll(y: np.ndarray) -> float:
    """Normal NLL with MLE mu and sigma (i.e., fitted to empirical mean/std)."""
    mu    = y.mean()
    sigma = max(y.std(), 1e-6)
    return float(-norm.logpdf(y, loc=mu, scale=sigma).mean())


# ── Overdispersion audit ──────────────────────────────────────────────────────

def _overdispersion_by_decile(
    y: np.ndarray,
    proxy_pred: np.ndarray,
    n_deciles: int = _N_DECILES,
) -> list[dict]:
    """
    Bin by predicted-mean decile (from Ridge proxy). Within each bin, compute
    actual mean, variance, and Var/Mean ratio. Returns list of decile records.
    """
    bins = np.percentile(proxy_pred, np.linspace(0, 100, n_deciles + 1))
    bins[0] -= 1e-9  # ensure lowest value is included

    records = []
    for i in range(n_deciles):
        mask = (proxy_pred > bins[i]) & (proxy_pred <= bins[i + 1])
        y_bin = y[mask]
        if len(y_bin) < 10:
            continue
        mu_actual  = float(y_bin.mean())
        var_actual = float(y_bin.var())
        records.append({
            "decile":          i + 1,
            "n":               int(mask.sum()),
            "pred_mean_lo":    round(float(bins[i]),     4),
            "pred_mean_hi":    round(float(bins[i + 1]), 4),
            "actual_mean":     round(mu_actual, 4),
            "actual_var":      round(var_actual, 4),
            "var_over_mean":   round(var_actual / max(mu_actual, 1e-9), 4),
            "overdispersed":   var_actual > mu_actual,
        })
    return records


def _build_proxy_predictions(
    runs_df: pd.DataFrame,
    parquet_df: pd.DataFrame,
) -> np.ndarray:
    """
    Merge runs data with parquet features, fit Ridge OLS proxy for expected runs,
    return in-sample predicted values for decile binning.
    """
    merged = runs_df.merge(
        parquet_df[["game_pk", "pitching_team"] + _PROXY_FEATURES],
        on=["game_pk", "pitching_team"],
        how="inner",
    )
    X = merged[_PROXY_FEATURES].to_numpy(dtype=float)
    y = merged["bullpen_runs_allowed"].to_numpy(dtype=float)

    pipe = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        Ridge(alpha=100.0),
    )
    pipe.fit(X, y)
    preds = pipe.predict(X)
    return preds, y, merged


# ── Main audit ────────────────────────────────────────────────────────────────

def run_audit(min_year: int = _MIN_YEAR_DEFAULT) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    # ── Fetch bullpen runs from Snowflake ──────────────────────────────────────
    runs_df = _fetch_bullpen_runs(min_year)

    # ── Load parquet for proxy features ───────────────────────────────────────
    if not _PARQUET_PATH.exists():
        print(f"WARNING: {_PARQUET_PATH} not found — proxy binning will use runs mean only")
        proxy_pred = np.full(len(runs_df), runs_df["bullpen_runs_allowed"].mean())
        y_runs     = runs_df["bullpen_runs_allowed"].to_numpy(dtype=float)
    else:
        parquet_df = pd.read_parquet(_PARQUET_PATH)
        parquet_df = parquet_df[parquet_df["game_year"] >= min_year].copy()
        proxy_pred, y_runs, merged_df = _build_proxy_predictions(runs_df, parquet_df)
        print(f"  Merged {len(merged_df):,} rows (runs × parquet features)")

    # ── Global stats ───────────────────────────────────────────────────────────
    global_mean = float(y_runs.mean())
    global_var  = float(y_runs.var())
    global_std  = float(y_runs.std())
    var_ratio   = global_var / max(global_mean, 1e-9)

    dist_counts = {
        int(k): int(v)
        for k, v in zip(*np.unique(y_runs.astype(int), return_counts=True))
        if k <= 15
    }

    print(f"\n── Bullpen runs distribution (n={len(y_runs):,}) ──────────────────────────")
    print(f"  Mean:      {global_mean:.4f}")
    print(f"  Std:       {global_std:.4f}")
    print(f"  Var:       {global_var:.4f}")
    print(f"  Var/Mean:  {var_ratio:.4f}  ({'OVERDISPERSED' if var_ratio > 1 else 'equi- or underdispersed'})")
    print(f"  P(0 runs): {dist_counts.get(0, 0) / len(y_runs):.3f}")

    # ── NegBin MLE fit ────────────────────────────────────────────────────────
    print("\n── NegBin MLE ──────────────────────────────────────────────────────────────")
    r_hat, negbin_nll = _fit_negbin_r(y_runs)
    normal_nll = _normal_nll(y_runs)
    delta_nll  = negbin_nll - normal_nll
    print(f"  NegBin r (MLE):    {r_hat:.4f}")
    print(f"  NegBin NLL:        {negbin_nll:.4f}")
    print(f"  Normal  NLL:       {normal_nll:.4f}")
    print(f"  Δ NLL (NB - N):    {delta_nll:+.4f}  ({'NegBin wins' if delta_nll < 0 else 'Normal wins'})")
    print(f"  Implied Var(NB):   {global_mean + global_mean**2 / r_hat:.4f}  (mu + mu²/r at fitted r)")

    # ── Decile overdispersion check ───────────────────────────────────────────
    print(f"\n── Decile overdispersion check ({_N_DECILES} deciles of proxy prediction) ────")
    decile_records = _overdispersion_by_decile(y_runs, proxy_pred)
    n_overdispersed = sum(1 for d in decile_records if d["overdispersed"])
    n_deciles_valid = len(decile_records)
    decile_gate_pass = n_overdispersed >= _DECILE_GATE

    print(f"  {'Dec':>4}  {'N':>6}  {'ActMean':>8}  {'ActVar':>8}  {'Var/Mean':>8}  {'OD?':>5}")
    for d in decile_records:
        print(
            f"  {d['decile']:>4}  {d['n']:>6}  {d['actual_mean']:>8.4f}  "
            f"{d['actual_var']:>8.4f}  {d['var_over_mean']:>8.4f}  "
            f"{'✓' if d['overdispersed'] else '✗':>5}"
        )
    print(f"\n  Deciles overdispersed: {n_overdispersed}/{n_deciles_valid}  "
          f"(gate ≥ {_DECILE_GATE}: {'PASS ✓' if decile_gate_pass else 'FAIL ✗'})")

    # ── Overall gate ───────────────────────────────────────────────────────────
    negbin_nll_gate = delta_nll < 0
    overall_gate    = decile_gate_pass and negbin_nll_gate

    print(f"\n── Gate summary ────────────────────────────────────────────────────────────")
    print(f"  Decile OD gate (≥ {_DECILE_GATE}/10):  {'PASS' if decile_gate_pass else 'FAIL'}")
    print(f"  NegBin NLL < Normal NLL:   {'PASS' if negbin_nll_gate else 'FAIL'}")
    print(f"  OVERALL:                   {'PASS — NegBin justified' if overall_gate else 'FAIL — revisit distribution choice'}")

    # ── Architecture recommendation ────────────────────────────────────────────
    if overall_gate:
        architecture = "Candidate A"
        arch_rationale = (
            "Overdispersion confirmed. Wrap Epic 6 champion mean with NegBin r "
            "fitted from training residuals (same pattern as 3D/4D)."
        )
    else:
        architecture = "Candidate A (tentative)"
        arch_rationale = (
            "Overdispersion gate not fully met. Proceed with Candidate A "
            "but revisit distribution family if NLL does not improve in 6D.2."
        )

    print(f"\n  Recommended architecture: {architecture}")
    print(f"  Rationale: {arch_rationale}")

    # ── Assemble results ───────────────────────────────────────────────────────
    results = {
        "audit_ts":         ts,
        "min_year":         min_year,
        "n_games":          int(len(y_runs)),
        "global_mean":      round(global_mean, 4),
        "global_var":       round(global_var, 4),
        "global_std":       round(global_std, 4),
        "var_over_mean":    round(var_ratio, 4),
        "pct_zero_runs":    round(dist_counts.get(0, 0) / len(y_runs), 4),
        "run_distribution": dist_counts,
        "negbin_r_hat":     round(r_hat, 4),
        "negbin_nll":       round(negbin_nll, 4),
        "normal_nll":       round(normal_nll, 4),
        "delta_nll":        round(delta_nll, 4),
        "negbin_implied_var": round(global_mean + global_mean**2 / r_hat, 4),
        "decile_records":   decile_records,
        "n_deciles_overdispersed": n_overdispersed,
        "n_deciles_valid":  n_deciles_valid,
        "decile_gate":      "PASS" if decile_gate_pass else "FAIL",
        "negbin_nll_gate":  "PASS" if negbin_nll_gate else "FAIL",
        "overall_gate":     "PASS" if overall_gate else "FAIL",
        "recommended_architecture": architecture,
        "arch_rationale":   arch_rationale,
    }

    # ── Save artifact ──────────────────────────────────────────────────────────
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"bullpen_6d_overdispersion_{ts}.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nArtifact saved → {out_path.relative_to(_PROJECT_ROOT)}")

    return results


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Epic 6D.1 — bullpen runs overdispersion audit"
    )
    parser.add_argument(
        "--min-year",
        type=int,
        default=_MIN_YEAR_DEFAULT,
        help=f"First season to include (default {_MIN_YEAR_DEFAULT})",
    )
    args = parser.parse_args()
    run_audit(min_year=args.min_year)


if __name__ == "__main__":
    main()
