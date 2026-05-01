"""Performance Tracker page — historical prediction quality."""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from app.utils.db import run_query

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

_PREDICTION_LOG_SQL = """
SELECT
    prediction_date,
    game_pk,
    market,
    model_prob,
    market_prob_at_prediction,
    closing_market_prob,
    actual_outcome,
    decimal_odds,
    ev,
    kelly_fraction
FROM baseball_data.config.prediction_log
ORDER BY prediction_date ASC
"""

_PREDICTION_LOG_STATS_SQL = """
SELECT
    COUNT(*) AS total_rows,
    COUNT(actual_outcome) AS rows_with_outcome,
    COUNT(closing_market_prob) AS rows_with_clv,
    MIN(prediction_date) AS earliest_date,
    MAX(prediction_date) AS latest_date
FROM baseball_data.config.prediction_log
"""

# ---------------------------------------------------------------------------
# Cached data loading
# ---------------------------------------------------------------------------


def _table_missing(exc: Exception) -> bool:
    return "002003" in str(exc) or "does not exist" in str(exc).lower()


@st.cache_data(ttl=3600)
def load_prediction_log() -> pd.DataFrame:
    try:
        df = run_query(_PREDICTION_LOG_SQL)
    except Exception as exc:
        if _table_missing(exc):
            return pd.DataFrame()
        raise
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    for col in ["model_prob", "market_prob_at_prediction", "closing_market_prob",
                "decimal_odds", "ev", "kelly_fraction"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "actual_outcome" in df.columns:
        df["actual_outcome"] = pd.to_numeric(df["actual_outcome"], errors="coerce")
    if "prediction_date" in df.columns:
        df["prediction_date"] = pd.to_datetime(df["prediction_date"])
    return df


@st.cache_data(ttl=3600)
def load_prediction_log_stats() -> dict:
    try:
        df = run_query(_PREDICTION_LOG_STATS_SQL)
        if df.empty:
            return {}
        df.columns = [c.lower() for c in df.columns]
        row = df.iloc[0]
        return {
            "total_rows": int(row.get("total_rows") or 0),
            "rows_with_outcome": int(row.get("rows_with_outcome") or 0),
            "rows_with_clv": int(row.get("rows_with_clv") or 0),
            "earliest_date": row.get("earliest_date"),
            "latest_date": row.get("latest_date"),
        }
    except Exception as exc:
        if _table_missing(exc):
            return {}
        return {}


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Performance Tracker — Baseball Betting Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Performance Tracker")
st.caption(
    "Historical prediction quality — Brier score trend, "
    "Closing Line Value, and cumulative P&L simulation."
)

# ---------------------------------------------------------------------------
# Sidebar context
# ---------------------------------------------------------------------------

stats = load_prediction_log_stats()

with st.sidebar:
    st.subheader("Prediction Log Stats")
    st.write(f"**Total rows:** {stats.get('total_rows', '—')}")
    st.write(f"**Rows with outcome:** {stats.get('rows_with_outcome', '—')}")
    st.write(f"**Rows with CLV:** {stats.get('rows_with_clv', '—')}")
    earliest = stats.get("earliest_date")
    latest = stats.get("latest_date")
    if earliest:
        st.write(f"**Earliest prediction:** {pd.Timestamp(earliest).date()}")
    if latest:
        st.write(f"**Latest prediction:** {pd.Timestamp(latest).date()}")

# ---------------------------------------------------------------------------
# Load filtered data (actual_outcome IS NOT NULL)
# ---------------------------------------------------------------------------

df = load_prediction_log()

n_rows = len(df)

# ---------------------------------------------------------------------------
# Empty state guard
# ---------------------------------------------------------------------------

n_total_logged = stats.get("total_rows", n_rows)
if n_total_logged < 5:
    st.info(
        "Not enough history yet — check back after a few days of predictions. "
        "Predictions are logged each time predict_today.py runs; outcomes are "
        "backfilled automatically on the next prediction run."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Compute P&L for actionable rows (ev > 0)
# ---------------------------------------------------------------------------

actionable = (
    df[(df["ev"] > 0) & df["actual_outcome"].notna()].copy()
    if "ev" in df.columns else pd.DataFrame()
)

if not actionable.empty:
    actionable = actionable.sort_values("prediction_date")
    actionable["kelly_pnl"] = actionable["kelly_fraction"] * (
        actionable["actual_outcome"] * (actionable["decimal_odds"] - 1)
        - (1 - actionable["actual_outcome"])
    )
    actionable["flat_pnl"] = 1.0 * (
        actionable["actual_outcome"] * (actionable["decimal_odds"] - 1)
        - (1 - actionable["actual_outcome"])
    )
    actionable["kelly_cumulative"] = actionable["kelly_pnl"].cumsum()
    actionable["flat_cumulative"] = actionable["flat_pnl"].cumsum()

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------

st.header("Summary")

n_rows_total = stats.get("total_rows", n_rows)

if not actionable.empty:
    win_rate = (actionable["actual_outcome"] == 1).mean()
    win_rate_str = f"{win_rate:.1%}"
else:
    win_rate_str = "—"

clv_rows = df[df["closing_market_prob"].notna()] if "closing_market_prob" in df.columns else pd.DataFrame()
if not clv_rows.empty:
    mean_clv = (clv_rows["model_prob"] - clv_rows["closing_market_prob"]).mean()
    mean_clv_str = f"{mean_clv:+.4f}"
else:
    mean_clv_str = "—"

if not actionable.empty and "kelly_cumulative" in actionable.columns:
    cumul_kelly = actionable["kelly_pnl"].sum()
    cumul_flat = actionable["flat_pnl"].sum()
    kelly_pnl_str = f"{cumul_kelly:+.2f} units"
    flat_pnl_str = f"{cumul_flat:+.2f} units"
else:
    kelly_pnl_str = "—"
    flat_pnl_str = "—"

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Predictions Logged", n_rows_total)
col2.metric("Win Rate (Actionable)", win_rate_str)
col3.metric("Mean CLV", mean_clv_str)
col4.metric("Cumulative P&L (Kelly)", kelly_pnl_str)
col5.metric("Cumulative P&L (Flat)", flat_pnl_str)

# ---------------------------------------------------------------------------
# Brier Score Trend
# ---------------------------------------------------------------------------

st.header("Brier Score Trend")

df_brier_src = df[["prediction_date", "model_prob", "market_prob_at_prediction", "actual_outcome"]].dropna(
    subset=["model_prob", "actual_outcome"]
)

if not df_brier_src.empty:
    df_brier_src = df_brier_src.copy()
    df_brier_src["brier_model"] = (df_brier_src["model_prob"] - df_brier_src["actual_outcome"]) ** 2
    df_brier_src["brier_market"] = (
        df_brier_src["market_prob_at_prediction"] - df_brier_src["actual_outcome"]
    ) ** 2

    df_brier_grouped = (
        df_brier_src.groupby("prediction_date")
        .agg(brier_model=("brier_model", "mean"), brier_market=("brier_market", "mean"))
        .reset_index()
        .sort_values("prediction_date")
    )

    few_days = len(df_brier_grouped) < 14

    if not few_days:
        df_brier_grouped["brier_model_14d"] = df_brier_grouped["brier_model"].rolling(14).mean()
        df_brier_grouped["brier_market_14d"] = df_brier_grouped["brier_market"].rolling(14).mean()
    else:
        df_brier_grouped["brier_model_14d"] = df_brier_grouped["brier_model"]
        df_brier_grouped["brier_market_14d"] = df_brier_grouped["brier_market"]

    df_brier_plot = df_brier_grouped.set_index("prediction_date")[["brier_model_14d", "brier_market_14d"]]
    df_brier_plot.columns = ["Model (Brier)", "Market (Brier)"]
    st.line_chart(df_brier_plot, use_container_width=True)

    if few_days:
        st.caption("Fewer than 14 days of data — rolling average not yet meaningful.")
    else:
        st.caption(
            "Lower Brier score = better calibration. "
            "Market benchmark ≈ 0.2395 (Card 3.11 baseline)."
        )
else:
    st.info("No Brier score data available yet.")

# ---------------------------------------------------------------------------
# CLV Tracker
# ---------------------------------------------------------------------------

st.header("Closing Line Value (CLV)")

clv_df = (
    df[df["closing_market_prob"].notna()].copy()
    if "closing_market_prob" in df.columns
    else pd.DataFrame()
)

if clv_df.empty:
    st.info(
        "CLV data not yet available. The nightly Snowflake Task DAG "
        "backfills closing_market_prob from mart_odds_outcomes. Check back "
        "after the DAG has run."
    )
else:
    clv_df["clv"] = clv_df["model_prob"] - clv_df["closing_market_prob"]

    iso_cal = clv_df["prediction_date"].dt.isocalendar()
    clv_df["week_label"] = (
        iso_cal["year"].astype(str) + "-W" + iso_cal["week"].astype(str).str.zfill(2)
    )

    df_clv = clv_df.groupby("week_label", sort=True)["clv"].mean().reset_index()
    df_clv.columns = ["week_label", "mean_clv"]

    chart = (
        alt.Chart(df_clv)
        .mark_bar()
        .encode(
            x=alt.X("week_label:N", sort=None, title="Week"),
            y=alt.Y("mean_clv:Q", title="Mean CLV"),
            color=alt.condition(
                alt.datum.mean_clv > 0,
                alt.value("#28a745"),
                alt.value("#dc3545"),
            ),
            tooltip=["week_label", alt.Tooltip("mean_clv:Q", format="+.4f")],
        )
        .properties(title="Mean CLV by Week")
    )
    st.altair_chart(chart, use_container_width=True)

# ---------------------------------------------------------------------------
# P&L Simulation
# ---------------------------------------------------------------------------

st.header("Cumulative P&L Simulation")

if actionable.empty:
    st.info("No actionable predictions (ev > 0) found in the log yet.")
else:
    df_pnl = actionable.set_index("prediction_date")[["kelly_cumulative", "flat_cumulative"]]
    df_pnl.columns = ["Kelly (cumul. units)", "Flat (cumul. units)"]
    st.line_chart(df_pnl, use_container_width=True)
    st.caption(
        "Kelly staking uses the capped kelly_fraction logged at prediction time. "
        "Flat staking uses 1 unit per actionable bet."
    )
