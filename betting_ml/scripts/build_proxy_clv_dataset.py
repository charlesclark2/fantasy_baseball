"""
build_proxy_clv_dataset.py — Epic 12 Story 12.3

Constructs proxy CLV labels for 2021–2025 regular-season games and runs the
proxy CLV analysis: logistic regression feature importances, calibration, AUC,
power analysis, and coverage bias check.

Outputs:
  - betting_ml/data/proxy_clv_dataset.parquet   (raw dataset for inspection)
  - ablation_results/proxy_clv_analysis.md      (findings report)

Proxy CLV label definition:
    proxy_clv_h2h      = close_devig_home - open_devig_home  (market movement)
    proxy_clv_positive = model and market agree on direction:
                         (proxy_clv_h2h > 0 AND h2h_edge > 0)
                      OR (proxy_clv_h2h < 0 AND h2h_edge < 0)

Known limitations (document in any downstream use):
  (a) CLV signal source: Pinnacle open→close where ≥2 snapshots exist (~48 games);
      consensus multi-book average (mart_closing_line_value) for all other games.
      This is a weaker "sharp-money" signal than a full Pinnacle time series.
  (b) Backfilled predictions, not intraday: daily_model_predictions for 2021–2025
      uses retrospective model scoring, not real-time prediction runs.
  (c) Public betting and CI-width features unavailable for 2021–2025; those feature
      groups are excluded from the proxy regression and treated as coverage-limited.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "betting_ml" / "data"
ABLATION_DIR = PROJECT_ROOT / "ablation_results"
REPORT_PATH = ABLATION_DIR / "proxy_clv_analysis.md"
DATASET_PATH = DATA_DIR / "proxy_clv_dataset.parquet"

_DB = "baseball_data"

# Features available in backfilled predictions — subset of meta-model features.
# Public betting (2024+ only, Action Network) and CI-width (live 2026+ only)
# are excluded; documented as coverage-limited in the report.
_FEATURE_COLS = [
    "h2h_edge",
    "totals_edge",
    "game_conviction_score",
    "gate_signals_met",
    "h2h_market_implied_prob",   # opening market price — available at prediction time
]

_BUILD_QUERY = f"""
with

-- ── Pinnacle open→close (games with ≥2 snapshots only) ────────────────────
pinnacle_snaps as (
    select
        game_pk,
        snapshot_ts,
        home_win_prob,
        row_number() over (partition by game_pk order by snapshot_ts asc)  as rn_open,
        row_number() over (partition by game_pk order by snapshot_ts desc) as rn_close
    from {_DB}.oddsapi.odds_snapshots_historical
    where bookmaker = 'pinnacle'
      and game_pk is not null
      and home_win_prob is not null
),
pinnacle_multi as (
    select game_pk
    from pinnacle_snaps
    group by game_pk
    having count(*) >= 2
),
pinnacle_open as (
    select p.game_pk, p.home_win_prob as pin_open_vf_home
    from pinnacle_snaps p
    inner join pinnacle_multi m on m.game_pk = p.game_pk
    where p.rn_open = 1
),
pinnacle_close as (
    select p.game_pk, p.home_win_prob as pin_close_vf_home
    from pinnacle_snaps p
    inner join pinnacle_multi m on m.game_pk = p.game_pk
    where p.rn_close = 1
),
pinnacle_clv as (
    select
        o.game_pk,
        o.pin_open_vf_home,
        c.pin_close_vf_home,
        c.pin_close_vf_home - o.pin_open_vf_home as pin_clv_h2h
    from pinnacle_open o
    join pinnacle_close c on c.game_pk = o.game_pk
),

-- ── Consensus CLV (mart) ───────────────────────────────────────────────────
consensus as (
    select
        game_pk,
        game_date,
        open_vf_home       as cons_open_vf_home,
        close_vf_home      as cons_close_vf_home,
        clv_home_ml        as cons_clv_h2h,
        n_books_with_clv
    from {_DB}.betting.mart_closing_line_value
    where data_source = 'historical'
),

-- ── Merge: Pinnacle first, consensus fallback ──────────────────────────────
clv_merged as (
    select
        c.game_pk,
        c.game_date,
        coalesce(p.pin_open_vf_home,  c.cons_open_vf_home)  as open_vf_home,
        coalesce(p.pin_close_vf_home, c.cons_close_vf_home) as close_vf_home,
        coalesce(p.pin_clv_h2h,       c.cons_clv_h2h)       as proxy_clv_h2h,
        case when p.game_pk is not null then 'pinnacle' else 'consensus' end as proxy_source,
        c.n_books_with_clv
    from consensus c
    left join pinnacle_clv p on p.game_pk = c.game_pk
    where c.cons_open_vf_home  is not null
      and c.cons_close_vf_home is not null
),

-- ── Morning predictions — one per game (latest inserted_at) ───────────────
pred_ranked as (
    select
        game_pk,
        game_date,
        inserted_at,
        h2h_edge,
        totals_edge,
        game_conviction_score,
        gate_signals_met,
        h2h_market_implied_prob,
        row_number() over (
            partition by game_pk
            order by
                case when prediction_type = 'morning' then 1 else 2 end,
                inserted_at desc
        ) as rn
    from {_DB}.betting_ml.daily_model_predictions
    where game_date < '2026-01-01'
      and prediction_type in ('morning', 'backfill')
),
pred as (
    select
        game_pk,
        game_date,
        inserted_at,
        h2h_edge,
        totals_edge,
        game_conviction_score,
        gate_signals_met,
        h2h_market_implied_prob
    from pred_ranked
    where rn = 1
),

-- ── Final join ────────────────────────────────────────────────────────────
final as (
    select
        cl.game_pk,
        cl.game_date,
        cl.proxy_clv_h2h,
        cl.proxy_source,
        cl.open_vf_home,
        cl.close_vf_home,
        cl.n_books_with_clv,
        p.h2h_edge,
        p.totals_edge,
        p.game_conviction_score,
        p.gate_signals_met,
        p.h2h_market_implied_prob,
        -- Proxy label: model and market agree on direction
        case
            when cl.proxy_clv_h2h > 0 and p.h2h_edge > 0 then true
            when cl.proxy_clv_h2h < 0 and p.h2h_edge < 0 then true
            when cl.proxy_clv_h2h is not null and p.h2h_edge is not null then false
        end as proxy_clv_positive
    from clv_merged cl
    inner join pred p on p.game_pk = cl.game_pk
    where cl.proxy_clv_h2h is not null
      and p.h2h_edge is not null
)

select * from final
order by game_date
"""


def load_dataset() -> pd.DataFrame:
    from betting_ml.utils.data_loader import get_snowflake_connection

    conn = get_snowflake_connection()
    try:
        df = pd.read_sql(_BUILD_QUERY, conn)
    finally:
        conn.close()

    df.columns = [c.lower() for c in df.columns]
    return df


def _section_dataset_overview(df: pd.DataFrame) -> tuple[str, dict]:
    n_total = len(df)
    n_games = df["game_pk"].nunique()
    n_labeled = df["proxy_clv_positive"].notna().sum()
    pct_pos = df["proxy_clv_positive"].mean()
    n_pinnacle = (df["proxy_source"] == "pinnacle").sum()
    n_consensus = (df["proxy_source"] == "consensus").sum()
    by_year = df.groupby(pd.to_datetime(df["game_date"]).dt.year).size().to_dict()

    lines = [
        "## 1. Dataset Overview",
        "",
        f"- Total rows: {n_total:,}  |  Distinct games: {n_games:,}",
        f"- Rows with `proxy_clv_positive` defined: {n_labeled:,}",
        f"- Base rate `proxy_clv_positive`: {pct_pos:.1%}",
        f"- CLV source — Pinnacle: {n_pinnacle} games | Consensus: {n_consensus} games",
        "",
        "**By year:**",
        "",
        "| Year | Games |",
        "|------|-------|",
    ]
    for yr, cnt in sorted(by_year.items()):
        lines.append(f"| {yr} | {cnt:,} |")

    metrics = {
        "n_games": n_games,
        "n_labeled": int(n_labeled),
        "base_rate_proxy_positive": float(pct_pos),
        "n_pinnacle_source": int(n_pinnacle),
        "n_consensus_source": int(n_consensus),
    }
    return "\n".join(lines), metrics


def _section_logistic_regression(df: pd.DataFrame) -> tuple[str, dict]:
    from sklearn.calibration import calibration_curve
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import brier_score_loss, roc_auc_score
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    # Only use features with ≥50% non-null coverage in this dataset.
    # Conviction/gate features are 0% in historical backfill — exclude them.
    coverage = {f: df[f].notna().mean() for f in _FEATURE_COLS if f in df.columns}
    usable = [f for f, cov in coverage.items() if cov >= 0.50]
    sparse = [f for f, cov in coverage.items() if cov < 0.50]

    sub = df[usable + ["proxy_clv_positive"]].dropna()
    if len(sub) < 100 or not usable:
        msg = (
            "## 2. Logistic Regression\n\n"
            f"_Insufficient complete rows after coverage filtering "
            f"(usable features: {usable or 'none'}, n={len(sub)})._\n"
        )
        return msg, {}

    X = sub[usable].values
    y = sub["proxy_clv_positive"].astype(int).values

    pipe = Pipeline([("scaler", StandardScaler()), ("lr", LogisticRegression(max_iter=1000))])
    cv_auc = cross_val_score(pipe, X, y, cv=5, scoring="roc_auc").mean()

    pipe.fit(X, y)
    y_prob = pipe.predict_proba(X)[:, 1]
    auc = roc_auc_score(y, y_prob)
    brier = brier_score_loss(y, y_prob)

    coefs = pipe.named_steps["lr"].coef_[0]
    importances = sorted(zip(usable, coefs), key=lambda x: abs(x[1]), reverse=True)

    # Calibration: fraction positive vs mean predicted prob
    frac_pos, mean_pred = calibration_curve(y, y_prob, n_bins=5)
    cal_lines = ["| Predicted | Actual |", "|-----------|--------|"]
    for mp, fp in zip(mean_pred, frac_pos):
        cal_lines.append(f"| {mp:.3f} | {fp:.3f} |")

    cov_notes = ", ".join(f"{f} ({coverage[f]:.0%})" for f in usable)
    lines = [
        "## 2. Logistic Regression (proxy_clv_positive)",
        "",
        f"- n = {len(sub):,} complete rows",
        f"- Features used (≥50% coverage): {cov_notes}",
        f"- CV AUC (5-fold): **{cv_auc:.3f}**",
        f"- In-sample AUC: {auc:.3f}",
        f"- Brier score: {brier:.4f}",
        "",
        "**Feature coefficients (standardised):**",
        "",
        "| Feature | Coefficient | Classification |",
        "|---------|-------------|----------------|",
    ]
    metrics = {"cv_auc": float(cv_auc), "brier": float(brier)}
    for feat, coef in importances:
        if abs(coef) >= 0.10:
            classification = "informative"
        elif abs(coef) >= 0.03:
            classification = "weak"
        else:
            classification = "uninformative"
        lines.append(f"| {feat} | {coef:+.3f} | {classification} |")
        metrics[f"coef_{feat}"] = float(coef)

    lines += ["", "**Calibration (5 bins):**", ""] + cal_lines

    # Coverage-limited: features in _FEATURE_COLS excluded due to sparse coverage
    sparse_rows = [f"| `{f}` | {coverage.get(f, 0):.0%} non-null — below 50% threshold |" for f in sparse]
    always_limited = [
        "| `win_prob_ci_width` | Live 2026+ only |",
        "| `totals_p_over_ci_width` | Live 2026+ only |",
        "| `home_ml_money_pct` | Action Network 2024+ only |",
        "| `over_money_pct` | Action Network 2024+ only |",
        "| `bovada_vs_pinnacle_h2h` | Pinnacle processed mart not yet built |",
        "| `hours_to_first_pitch_at_prediction` | Backfill lacks precise insertion timestamps |",
    ]
    lines += [
        "",
        "**Coverage-limited features (excluded from regression):**",
        "",
        "| Feature | Reason |",
        "|---------|--------|",
    ] + sparse_rows + always_limited

    return "\n".join(lines), metrics


def _section_power_analysis(df: pd.DataFrame) -> tuple[str, dict]:
    """
    Estimate minimum live-game sample size for 80% CI width ≤ ±0.15
    on the h2h_edge coefficient using bootstrap subsampling.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    coverage = {f: df[f].notna().mean() for f in _FEATURE_COLS if f in df.columns}
    usable = [f for f, cov in coverage.items() if cov >= 0.50]

    if "h2h_edge" not in usable:
        return "## 3. Power Analysis\n\n_`h2h_edge` not available — cannot run power analysis._\n", {}

    sub = df[usable + ["proxy_clv_positive"]].dropna()
    if len(sub) < 200:
        return "## 3. Power Analysis\n\n_Insufficient data._\n", {}

    X_full = StandardScaler().fit_transform(sub[usable].values)
    y_full = sub["proxy_clv_positive"].astype(int).values

    edge_idx = usable.index("h2h_edge")
    sample_sizes = [50, 100, 150, 200, 300, 500, 750, 1000]
    n_boot = 200
    rng = np.random.default_rng(42)

    results = []
    for n in sample_sizes:
        if n > len(sub):
            break
        coefs = []
        for _ in range(n_boot):
            idx = rng.choice(len(sub), size=n, replace=False)
            Xi, yi = X_full[idx], y_full[idx]
            if yi.sum() < 3 or (1 - yi).sum() < 3:
                continue
            try:
                lr = LogisticRegression(max_iter=500).fit(Xi, yi)
                coefs.append(lr.coef_[0][edge_idx])
            except Exception:
                continue
        if len(coefs) < 50:
            continue
        ci_half = (np.percentile(coefs, 90) - np.percentile(coefs, 10)) / 2
        results.append((n, float(ci_half), len(coefs)))

    lines = [
        "## 3. Power Analysis",
        "",
        "Bootstrap-based estimate of 80% CI half-width on `h2h_edge` coefficient",
        "as a function of live-data sample size. Target: CI half-width ≤ 0.15.",
        "",
        "| n games | 80% CI half-width | Meets target? |",
        "|---------|-------------------|---------------|",
    ]
    min_n_meets = None
    for n, ci_half, _ in results:
        meets = ci_half <= 0.15
        if meets and min_n_meets is None:
            min_n_meets = n
        lines.append(f"| {n} | ±{ci_half:.3f} | {'✅' if meets else '❌'} |")

    if min_n_meets:
        lines += [
            "",
            f"**Conclusion:** ~{min_n_meets} live CLV-labeled games needed for "
            f"80% CI to narrow to ±0.15 on the `h2h_edge` coefficient.",
        ]
        if min_n_meets < 500:
            lines.append(
                f"This is below the current Story 12.6 frequentist gate (≥500 games). "
                f"Consider revising the gate threshold to ≥{min_n_meets}."
            )
    else:
        lines += ["", "_Target CI width not reached within the tested range._"]

    metrics = {"power_min_n_for_target_ci": min_n_meets or -1}
    for n, ci_half, _ in results:
        metrics[f"power_ci_half_n{n}"] = ci_half
    return "\n".join(lines), metrics


def _section_coverage_bias(df: pd.DataFrame) -> tuple[str, dict]:
    """
    Check whether Pinnacle-sourced games differ systematically from consensus-sourced
    games on key features — a bias that would skew proxy analysis results.
    """
    pin = df[df["proxy_source"] == "pinnacle"]
    cons = df[df["proxy_source"] == "consensus"]

    lines = [
        "## 4. Coverage Bias (Pinnacle vs Consensus source)",
        "",
        f"Pinnacle-sourced: {len(pin)} games | Consensus-sourced: {len(cons)} games",
        "",
        "| Feature | Pinnacle mean | Consensus mean | Δ |",
        "|---------|--------------|----------------|---|",
    ]
    metrics = {}
    for col in ["h2h_edge", "game_conviction_score", "proxy_clv_h2h"]:
        if col not in df.columns:
            continue
        pm = pin[col].mean() if len(pin) > 0 else float("nan")
        cm = cons[col].mean()
        delta = pm - cm if not np.isnan(pm) else float("nan")
        lines.append(f"| {col} | {pm:.4f} | {cm:.4f} | {delta:+.4f} |")
        metrics[f"bias_delta_{col}"] = float(delta) if not np.isnan(delta) else 0.0

    pct_pos_pin = pin["proxy_clv_positive"].mean() if len(pin) > 0 else float("nan")
    pct_pos_cons = cons["proxy_clv_positive"].mean()
    lines += [
        "",
        f"- `proxy_clv_positive` rate — Pinnacle: {pct_pos_pin:.1%} | Consensus: {pct_pos_cons:.1%}",
        "",
        "_If Pinnacle mean h2h_edge or proxy_clv_positive differs substantially from_",
        "_consensus, Pinnacle coverage is non-random and results should be treated with_",
        "_extra skepticism for those ~48 games._",
    ]
    return "\n".join(lines), metrics


def _section_feature_classification(df: pd.DataFrame, lr_metrics: dict) -> tuple[str, dict]:
    col_coverage = {f: df[f].notna().mean() for f in _FEATURE_COLS if f in df.columns}

    classifications = {}
    for feat in _FEATURE_COLS:
        key = f"coef_{feat}"
        if key not in lr_metrics or col_coverage.get(feat, 0) < 0.50:
            classifications[feat] = "coverage_limited"
            continue
        coef = abs(lr_metrics[key])
        if coef >= 0.10:
            classifications[feat] = "informative"
        elif coef >= 0.03:
            classifications[feat] = "weak"
        else:
            classifications[feat] = "uninformative"

    coverage_limited = [
        "win_prob_ci_width",
        "totals_p_over_ci_width",
        "home_ml_money_pct",
        "over_money_pct",
        "bovada_vs_pinnacle_h2h",
        "hours_to_first_pitch_at_prediction",
    ]

    lines = [
        "## 5. Feature Classification Summary",
        "",
        "Classifications inform prior means for Story 12.4 Bayesian model.",
        "Uninformative → tighten prior toward 0. Informative → use proxy coefficient.",
        "",
        "| Feature | Classification | Note |",
        "|---------|---------------|------|",
    ]
    for feat, cls in classifications.items():
        coef_str = (
            f"coef={lr_metrics.get(f'coef_{feat}', 0):+.3f}"
            if f"coef_{feat}" in lr_metrics
            else "—"
        )
        lines.append(f"| {feat} | **{cls}** | {coef_str} |")
    for feat in coverage_limited:
        lines.append(f"| {feat} | **coverage_limited** | Not in historical backfill |")

    return "\n".join(lines), {}


def run() -> None:
    print("Loading proxy CLV dataset from Snowflake...")
    df = load_dataset()
    print(f"  {len(df):,} rows loaded, {df['game_pk'].nunique():,} distinct games")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DATASET_PATH, index=False)
    print(f"  Dataset saved to {DATASET_PATH}")

    print("Running analysis sections...")
    s1, m1 = _section_dataset_overview(df)
    s2, m2 = _section_logistic_regression(df)
    s3, m3 = _section_power_analysis(df)
    s4, m4 = _section_coverage_bias(df)
    s5, m5 = _section_feature_classification(df, m2)

    run_date = date.today().isoformat()
    header = "\n".join([
        "# Proxy CLV Analysis — Epic 12 Story 12.3",
        "",
        f"**Run date:** {run_date}",
        "",
        "**Known limitations of this analysis:**",
        "- (a) CLV signal: Pinnacle open→close where ≥2 snapshots (~48 games); "
        "consensus multi-book average otherwise. Not a pure sharp-money signal.",
        "- (b) Backfilled predictions (2021–2025), not real-time intraday runs.",
        "- (c) Public betting, CI-width, and bookmaker-disagreement features unavailable "
        "for historical backfill; excluded from regression and classified as coverage-limited.",
        "",
        "---",
        "",
    ])

    all_metrics = {**m1, **m2, **m3, **m4}

    report = header + "\n\n".join([s1, s2, s3, s4, s5])
    ABLATION_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report)
    print(f"  Report written to {REPORT_PATH}")

    try:
        import mlflow
        from betting_ml.utils.mlflow_utils import get_or_create_experiment

        mlflow.set_experiment(get_or_create_experiment("clv_monitoring"))
        with mlflow.start_run(run_name=f"proxy_clv_analysis_{run_date}"):
            mlflow.log_metrics({k: v for k, v in all_metrics.items() if isinstance(v, (int, float))})
            mlflow.log_artifact(str(REPORT_PATH))
        print("  Metrics logged to MLflow experiment 'clv_monitoring'")
    except Exception as e:
        print(f"  MLflow logging skipped: {e}")


if __name__ == "__main__":
    run()
