"""
compute_clv_monitoring.py — Epic 12 Story 12.2

Weekly descriptive CLV monitoring. Queries feature_pregame_meta_model_features,
produces seven analysis sections, appends a dated entry to clv_monitoring_log.md,
and logs summary metrics to MLflow under experiment 'clv_monitoring'.

Run manually:
    uv run betting_ml/scripts/compute_clv_monitoring.py

Returns (from run()):
    dict of summary metrics consumed by the Dagster asset for Dagster metadata.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection  # noqa: E402
from betting_ml.utils.mlflow_utils import get_or_create_experiment  # noqa: E402

_LOG_PATH = PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "clv_monitoring_log.md"

_DATABASE = "baseball_data"
_FEATURE_TABLE = f"{_DATABASE}.betting_features.feature_pregame_meta_model_features"

_QUERY = f"""
select
    game_pk,
    game_date,
    market_type,
    predicted_at,
    model_edge,
    clv,
    clv_positive,
    actual_outcome,
    h2h_edge_home,
    totals_edge,
    game_conviction_score,
    gate_signals_met,
    hours_to_first_pitch_at_prediction,
    home_ml_money_pct,
    bovada_vs_pinnacle_h2h,
    coverage_score,
    training_eligible
from {_FEATURE_TABLE}
order by game_date, game_pk, market_type
"""

# Gate thresholds for CLV meta-model stories (number of *distinct games*)
_GATES = [50, 100, 500, 1000]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_data() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()

    df = pd.DataFrame(rows, columns=cols)
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
    for col in ("clv", "model_edge", "h2h_edge_home", "totals_edge",
                "game_conviction_score", "home_ml_money_pct",
                "bovada_vs_pinnacle_h2h", "coverage_score",
                "hours_to_first_pitch_at_prediction"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["clv_positive"] = df["clv_positive"].astype(bool)
    df["training_eligible"] = df["training_eligible"].astype(bool)
    return df


# ---------------------------------------------------------------------------
# Analysis sections — each returns (markdown_str, metrics_dict)
# ---------------------------------------------------------------------------

def _pct_positive(series: pd.Series) -> float:
    return float(series.mean()) if len(series) > 0 else float("nan")


def _fmt_row(label: str, n: int, mean_clv: float, pct_pos: float) -> str:
    return (
        f"| {label} | {n} | {mean_clv:+.4f} | {pct_pos:.1%} |"
    )


def _section_gate_tracker(df: pd.DataFrame) -> tuple[str, dict]:
    """Gate threshold tracker: current counts and ETA for each gate."""
    n_games_h2h = int(df[df["market_type"] == "h2h"]["game_pk"].nunique())
    n_games_totals = int(df[df["market_type"] == "totals"]["game_pk"].nunique())
    n_games_total = int(df["game_pk"].nunique())

    # Estimate games/week using the last 28 days
    today = date.today()
    recent_cutoff = today - timedelta(days=28)
    recent = df[df["game_date"] >= recent_cutoff]["game_pk"].nunique()
    games_per_week = recent / 4.0 if recent > 0 else 0.0

    lines = [
        "### 1. Gate Threshold Tracker",
        "",
        f"| Market | Labeled games |",
        f"|--------|--------------|",
        f"| h2h | {n_games_h2h} |",
        f"| totals | {n_games_totals} |",
        f"| **total (distinct games)** | **{n_games_total}** |",
        "",
        f"Recent pace: **{games_per_week:.1f} games/week** (last 28 days)",
        "",
        "| Gate | Threshold | Games needed | Est. weeks | Est. date |",
        "|------|-----------|-------------|-----------|-----------|",
    ]
    for threshold in _GATES:
        needed = max(0, threshold - n_games_total)
        if games_per_week > 0 and needed > 0:
            weeks_needed = needed / games_per_week
            eta = today + timedelta(weeks=weeks_needed)
            eta_str = eta.strftime("%Y-%m-%d")
        elif needed == 0:
            weeks_needed = 0.0
            eta_str = "MET ✅"
        else:
            weeks_needed = float("inf")
            eta_str = "unknown"
        lines.append(
            f"| Epic 12.{_GATES.index(threshold) + 3} | ≥{threshold} games "
            f"| {needed} | {weeks_needed:.1f} | {eta_str} |"
        )

    metrics = {
        "n_games_h2h": n_games_h2h,
        "n_games_totals": n_games_totals,
        "n_games_total": n_games_total,
        "games_per_week_pace": round(games_per_week, 2),
    }
    return "\n".join(lines), metrics


def _section_clv_distribution(df: pd.DataFrame) -> tuple[str, dict]:
    """CLV distribution: mean, std, pct_positive by market type."""
    lines = [
        "### 2. CLV Distribution by Market Type",
        "",
        "| Market | n | Mean CLV | Std CLV | Pct CLV+ |",
        "|--------|---|----------|---------|----------|",
    ]
    metrics: dict = {}
    for mkt in ("h2h", "totals"):
        sub = df[df["market_type"] == mkt].dropna(subset=["clv"])
        n = len(sub)
        if n == 0:
            lines.append(f"| {mkt} | 0 | — | — | — |")
            continue
        mean_clv = float(sub["clv"].mean())
        std_clv = float(sub["clv"].std())
        pct_pos = _pct_positive(sub["clv_positive"])
        lines.append(
            f"| {mkt} | {n} | {mean_clv:+.4f} | {std_clv:.4f} | {pct_pos:.1%} |"
        )
        metrics[f"mean_clv_{mkt}"] = round(mean_clv, 6)
        metrics[f"std_clv_{mkt}"] = round(std_clv, 6)
        metrics[f"pct_positive_{mkt}"] = round(pct_pos, 4)

    return "\n".join(lines), metrics


def _section_edge_buckets(df: pd.DataFrame) -> tuple[str, dict]:
    """Mean CLV and pct_positive bucketed by absolute edge magnitude."""
    bins = [0.0, 0.02, 0.04, 0.06, float("inf")]
    labels = ["0–0.02", "0.02–0.04", "0.04–0.06", "0.06+"]

    lines = [
        "### 3. Edge Bucket Analysis",
        "",
        "Edge column: `|h2h_edge_home|` for h2h rows; `|totals_edge|` for totals rows.",
        "",
        "| Market | Edge bucket | n | Mean CLV | Pct CLV+ |",
        "|--------|------------|---|----------|----------|",
    ]
    metrics: dict = {}
    for mkt, edge_col in (("h2h", "h2h_edge_home"), ("totals", "totals_edge")):
        sub = df[(df["market_type"] == mkt)].dropna(subset=[edge_col, "clv"]).copy()
        sub["edge_abs"] = sub[edge_col].abs()
        sub["bucket"] = pd.cut(sub["edge_abs"], bins=bins, labels=labels, right=False)
        grp = sub.groupby("bucket", observed=True)
        for lbl in labels:
            g = grp.get_group(lbl) if lbl in grp.groups else pd.DataFrame()
            n = len(g)
            if n == 0:
                lines.append(f"| {mkt} | {lbl} | 0 | — | — |")
                continue
            mean_clv = float(g["clv"].mean())
            pct_pos = _pct_positive(g["clv_positive"])
            lines.append(
                f"| {mkt} | {lbl} | {n} | {mean_clv:+.4f} | {pct_pos:.1%} |"
            )
            key = f"edge_{mkt}_{lbl.replace('–', '_').replace('.', 'd').replace('+', 'plus')}"
            metrics[f"{key}_n"] = n
            metrics[f"{key}_mean_clv"] = round(mean_clv, 6)
            metrics[f"{key}_pct_pos"] = round(pct_pos, 4)

    return "\n".join(lines), metrics


def _section_conviction_tiers(df: pd.DataFrame) -> tuple[str, dict]:
    """Mean CLV and pct_positive by gate_signals_met tier."""
    lines = [
        "### 4. Conviction Tier Analysis",
        "",
        "| Gate signals met | n | Mean CLV | Pct CLV+ |",
        "|-----------------|---|----------|----------|",
    ]
    metrics: dict = {}
    sub = df.dropna(subset=["gate_signals_met", "clv"]).copy()
    sub["gate_signals_met"] = sub["gate_signals_met"].astype(int)
    grp = sub.groupby("gate_signals_met")
    for tier in sorted(sub["gate_signals_met"].unique()):
        g = grp.get_group(tier)
        n = len(g)
        mean_clv = float(g["clv"].mean())
        pct_pos = _pct_positive(g["clv_positive"])
        lines.append(f"| {tier} | {n} | {mean_clv:+.4f} | {pct_pos:.1%} |")
        metrics[f"conviction_{tier}_n"] = n
        metrics[f"conviction_{tier}_mean_clv"] = round(mean_clv, 6)
        metrics[f"conviction_{tier}_pct_pos"] = round(pct_pos, 4)

    if sub.empty:
        lines.append("| (no data) | — | — | — |")

    return "\n".join(lines), metrics


def _section_bookmaker_disagreement(df: pd.DataFrame) -> tuple[str, dict]:
    """Mean CLV by Bovada vs Pinnacle disagreement direction."""
    lines = [
        "### 5. Bookmaker Disagreement Analysis",
        "",
    ]
    metrics: dict = {}
    bov_pin = df.dropna(subset=["bovada_vs_pinnacle_h2h", "clv"])

    if bov_pin.empty:
        lines += [
            "No rows with `bovada_vs_pinnacle_h2h` populated yet "
            "(Pinnacle mart not yet built).",
            "",
            "This section will populate when the Pinnacle processed mart ships.",
        ]
        metrics["pinnacle_rows"] = 0
        return "\n".join(lines), metrics

    # bovada_vs_pinnacle_h2h = bovada_close_devig - pinnacle_close_devig
    # Positive = Bovada favors home more than Pinnacle
    favors_home = bov_pin[bov_pin["bovada_vs_pinnacle_h2h"] > 0]
    favors_away = bov_pin[bov_pin["bovada_vs_pinnacle_h2h"] <= 0]

    lines += [
        "| Direction | n | Mean CLV | Pct CLV+ |",
        "|-----------|---|----------|----------|",
    ]
    for label, g in (("Bovada favors home more", favors_home),
                     ("Bovada favors away more", favors_away)):
        n = len(g)
        if n == 0:
            lines.append(f"| {label} | 0 | — | — |")
            continue
        mean_clv = float(g["clv"].mean())
        pct_pos = _pct_positive(g["clv_positive"])
        lines.append(f"| {label} | {n} | {mean_clv:+.4f} | {pct_pos:.1%} |")
        safe = label.lower().replace(" ", "_")
        metrics[f"bk_dis_{safe}_n"] = n
        metrics[f"bk_dis_{safe}_mean_clv"] = round(mean_clv, 6)

    metrics["pinnacle_rows"] = len(bov_pin)
    return "\n".join(lines), metrics


def _section_public_betting(df: pd.DataFrame) -> tuple[str, dict]:
    """Mean CLV for public-heavy vs. contrarian home ML buckets."""
    lines = [
        "### 6. Public Betting Contrarian Signal",
        "",
    ]
    metrics: dict = {}
    sub = df[(df["market_type"] == "h2h")].dropna(subset=["home_ml_money_pct", "clv"])

    if sub.empty:
        lines += [
            "No h2h rows with `home_ml_money_pct` populated yet.",
            "",
            "Action Network data available from 2024-02-22; expect coverage once "
            "historical CLV labels are backfilled.",
        ]
        metrics["public_betting_rows"] = 0
        return "\n".join(lines), metrics

    public_heavy = sub[sub["home_ml_money_pct"] > 0.65]
    contrarian = sub[sub["home_ml_money_pct"] < 0.35]
    middle = sub[(sub["home_ml_money_pct"] >= 0.35) & (sub["home_ml_money_pct"] <= 0.65)]

    lines += [
        "| Bucket | Threshold | n | Mean CLV | Pct CLV+ |",
        "|--------|-----------|---|----------|----------|",
    ]
    for label, threshold, g in (
        ("Public heavy (home)", "> 65%", public_heavy),
        ("Neutral", "35–65%", middle),
        ("Contrarian (home fade)", "< 35%", contrarian),
    ):
        n = len(g)
        if n == 0:
            lines.append(f"| {label} | {threshold} | 0 | — | — |")
            continue
        mean_clv = float(g["clv"].mean())
        pct_pos = _pct_positive(g["clv_positive"])
        lines.append(f"| {label} | {threshold} | {n} | {mean_clv:+.4f} | {pct_pos:.1%} |")

    metrics["public_betting_rows"] = len(sub)
    metrics["public_heavy_n"] = len(public_heavy)
    metrics["contrarian_n"] = len(contrarian)
    return "\n".join(lines), metrics


def _section_timing(df: pd.DataFrame) -> tuple[str, dict]:
    """Mean CLV by hours-to-first-pitch bucket."""
    bins = [0, 2, 6, 12, float("inf")]
    labels = ["< 2h", "2–6h", "6–12h", "12h+"]

    lines = [
        "### 7. Timing Analysis",
        "",
        "| Hours to first pitch | n | Mean CLV | Pct CLV+ |",
        "|---------------------|---|----------|----------|",
    ]
    metrics: dict = {}
    sub = df.dropna(subset=["hours_to_first_pitch_at_prediction", "clv"]).copy()
    sub = sub[sub["hours_to_first_pitch_at_prediction"] >= 0]
    sub["bucket"] = pd.cut(
        sub["hours_to_first_pitch_at_prediction"],
        bins=bins,
        labels=labels,
        right=False,
    )
    grp = sub.groupby("bucket", observed=True)
    for lbl in labels:
        g = grp.get_group(lbl) if lbl in grp.groups else pd.DataFrame()
        n = len(g)
        if n == 0:
            lines.append(f"| {lbl} | 0 | — | — |")
            continue
        mean_clv = float(g["clv"].mean())
        pct_pos = _pct_positive(g["clv_positive"])
        lines.append(f"| {lbl} | {n} | {mean_clv:+.4f} | {pct_pos:.1%} |")
        safe = lbl.replace("<", "lt").replace(" ", "").replace("–", "_")
        metrics[f"timing_{safe}_n"] = n
        metrics[f"timing_{safe}_mean_clv"] = round(mean_clv, 6)

    return "\n".join(lines), metrics


# ---------------------------------------------------------------------------
# Section 8 — Pipeline health (A1.5)
# ---------------------------------------------------------------------------

_PIPELINE_HEALTH_QUERY = """
WITH games_per_day AS (
    SELECT official_date,
           MIN(CONVERT_TIMEZONE('UTC', game_date)) AS earliest_first_pitch_utc,
           COUNT(*)                                AS n_scheduled
    FROM baseball_data.betting.stg_statsapi_games
    WHERE game_type = 'R'
      -- Prior 7 complete days only. Without the upper bound this pulled the whole
      -- FUTURE schedule (every remaining game-day has official_date >= today-7),
      -- inflating n_days and diluting the SLA compliance %.
      AND official_date BETWEEN DATEADD('day', -7, CURRENT_DATE())
                            AND DATEADD('day', -1, CURRENT_DATE())
    GROUP BY official_date
),
ps AS (
    SELECT run_date,
           predict_today_complete_ts,
           lineup_confirmed_complete_ts,
           pipeline_status,
           n_games_scored,
           signal_completeness_score,
           avg_feature_coverage_score,
           job_start_ts
    FROM baseball_data.betting_ml.pipeline_status
    WHERE run_date >= DATEADD('day', -7, CURRENT_DATE())
)
SELECT
    g.official_date,
    g.n_scheduled,
    g.earliest_first_pitch_utc,
    ps.predict_today_complete_ts,
    ps.lineup_confirmed_complete_ts,
    ps.pipeline_status,
    ps.n_games_scored,
    ps.signal_completeness_score,
    ps.avg_feature_coverage_score,
    DATEDIFF('minute', ps.predict_today_complete_ts,
             g.earliest_first_pitch_utc)                    AS minutes_before_first_pitch
FROM games_per_day g
LEFT JOIN ps ON ps.run_date = g.official_date
ORDER BY g.official_date DESC
"""


def _load_pipeline_health() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_PIPELINE_HEALTH_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    df["official_date"] = pd.to_datetime(df["official_date"]).dt.date
    for col in ("n_scheduled", "n_games_scored"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["signal_completeness_score"] = pd.to_numeric(
        df["signal_completeness_score"], errors="coerce"
    )
    df["avg_feature_coverage_score"] = pd.to_numeric(
        df["avg_feature_coverage_score"], errors="coerce"
    )
    df["minutes_before_first_pitch"] = pd.to_numeric(
        df["minutes_before_first_pitch"], errors="coerce"
    )
    return df


def _section_pipeline_health() -> tuple[str, dict]:
    """7-day pipeline SLA health report."""
    try:
        df = _load_pipeline_health()
    except Exception as exc:
        return f"### 8. Pipeline Health (last 7 days)\n\n_Could not load: {exc}_\n", {}

    if df.empty:
        return "### 8. Pipeline Health (last 7 days)\n\n_No pipeline_status rows in last 7 days._\n", {}

    n_days = len(df)
    sla_threshold = 30  # minutes before first pitch

    sla_met = int(
        ((df["minutes_before_first_pitch"] >= sla_threshold) &
         (df["pipeline_status"] == "complete")).sum()
    )
    sla_pct = sla_met / n_days if n_days > 0 else 0.0

    complete_days = int((df["pipeline_status"] == "complete").sum())
    low_signal_days = int((df["signal_completeness_score"] < 0.80).sum())
    # A1.10/A1.11 — days the live feature pipeline served low-coverage predictions
    # (below the 0.70 feature-store gate). Surfaces a degraded feature source even
    # when the pipeline otherwise reports "complete".
    low_coverage_days = int((df["avg_feature_coverage_score"] < 0.70).sum())
    short_scored_days = int(
        (df["n_games_scored"] < df["n_scheduled"]).sum()
    )

    runtimes = df["minutes_before_first_pitch"].dropna()
    mean_lead = float(runtimes.mean()) if len(runtimes) > 0 else float("nan")
    cov_vals = df["avg_feature_coverage_score"].dropna()
    mean_cov = float(cov_vals.mean()) if len(cov_vals) > 0 else float("nan")

    lines = [
        "### 8. Pipeline Health (last 7 days)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Days audited | {n_days} |",
        f"| SLA compliance (≥30 min before first pitch) | **{sla_met}/{n_days} ({sla_pct:.0%})** |",
        f"| Days pipeline_status = complete | {complete_days}/{n_days} |",
        f"| Days signal_completeness < 0.80 | {low_signal_days} |",
        f"| Days feature_coverage < 0.70 | {low_coverage_days} |",
        f"| Mean feature_coverage_score | {mean_cov:.2f} |",
        f"| Days n_games_scored < scheduled | {short_scored_days} |",
        f"| Mean prediction lead (min before first pitch) | {mean_lead:.0f} min |",
        "",
        "| Date | Status | Scored/Sched | Signal | Coverage | Lead (min) | SLA |",
        "|------|--------|-------------|--------|----------|-----------|-----|",
    ]
    for _, row in df.iterrows():
        status = row["pipeline_status"] or "missing"
        scored = f"{row['n_games_scored']}/{row['n_scheduled']}"
        sig = f"{row['signal_completeness_score']:.2f}" if pd.notna(row["signal_completeness_score"]) else "—"
        cov = f"{row['avg_feature_coverage_score']:.2f}" if pd.notna(row["avg_feature_coverage_score"]) else "—"
        lead = f"{row['minutes_before_first_pitch']:.0f}" if pd.notna(row["minutes_before_first_pitch"]) else "—"
        sla_icon = "✅" if (pd.notna(row["minutes_before_first_pitch"]) and
                            row["minutes_before_first_pitch"] >= sla_threshold and
                            status == "complete") else "❌"
        lines.append(f"| {row['official_date']} | {status} | {scored} | {sig} | {cov} | {lead} | {sla_icon} |")

    metrics = {
        "pipeline_sla_pct_7d": round(sla_pct, 4),
        "pipeline_complete_days_7d": complete_days,
        "pipeline_low_signal_days_7d": low_signal_days,
        "pipeline_low_coverage_days_7d": low_coverage_days,
        "pipeline_mean_feature_coverage_7d": round(mean_cov, 3) if not np.isnan(mean_cov) else 0.0,
        "pipeline_short_scored_days_7d": short_scored_days,
        "pipeline_mean_lead_min_7d": round(mean_lead, 1) if not np.isnan(mean_lead) else 0.0,
    }
    return "\n".join(lines), metrics


# ---------------------------------------------------------------------------
# Log writing
# ---------------------------------------------------------------------------

def _build_entry(df: pd.DataFrame, run_date: date) -> tuple[str, dict]:
    """Build the full markdown entry and aggregate all metrics."""
    sections = [
        _section_gate_tracker(df),
        _section_clv_distribution(df),
        _section_edge_buckets(df),
        _section_conviction_tiers(df),
        _section_bookmaker_disagreement(df),
        _section_public_betting(df),
        _section_timing(df),
        _section_pipeline_health(),
    ]

    header = (
        f"## CLV Weekly Monitoring — {run_date.isoformat()}\n\n"
        f"Dataset: `{_FEATURE_TABLE}`  \n"
        f"Rows: {len(df)} | Distinct games: {df['game_pk'].nunique()} "
        f"| Date range: {df['game_date'].min()} → {df['game_date'].max()}\n"
    )

    all_metrics: dict = {}
    body_parts = []
    for md, metrics in sections:
        body_parts.append(md)
        all_metrics.update(metrics)

    entry = header + "\n\n" + "\n\n".join(body_parts) + "\n\n---\n"
    return entry, all_metrics


def _append_to_log(entry: str, log_path: Path = _LOG_PATH) -> None:
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n" + entry)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def run(log_path: Path = _LOG_PATH) -> dict:
    """Run the full monitoring suite. Returns summary metrics dict."""
    df = _load_data()

    if df.empty:
        print("No rows in feature_pregame_meta_model_features — skipping.")
        return {}

    run_date = date.today()
    entry, metrics = _build_entry(df, run_date)

    _append_to_log(entry, log_path)
    print(f"Appended monitoring entry to {log_path}")

    # Log to MLflow
    experiment_id = get_or_create_experiment("clv_monitoring")
    with mlflow.start_run(
        experiment_id=experiment_id,
        run_name=f"weekly_{run_date.isoformat()}",
    ):
        mlflow.log_metrics({k: v for k, v in metrics.items()
                            if isinstance(v, (int, float)) and np.isfinite(v)})
        mlflow.set_tag("run_date", run_date.isoformat())
        mlflow.set_tag("n_rows", str(len(df)))

    print(f"Logged {len(metrics)} metrics to MLflow experiment 'clv_monitoring'")
    return metrics


def main() -> None:
    metrics = run()
    if metrics:
        print("\n--- Summary metrics ---")
        for k, v in sorted(metrics.items()):
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
