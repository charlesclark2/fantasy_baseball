"""Performance Tracker page — historical prediction quality."""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from app.utils.db import get_snowflake_session, run_query

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

if st.button("Refresh Data", help="Clear cached results and reload from Snowflake."):
    get_snowflake_session.clear()
    load_prediction_log.clear()
    load_prediction_log_stats.clear()
    st.rerun()

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
# Global date range filter
# ---------------------------------------------------------------------------

if not df.empty and "prediction_date" in df.columns:
    _all_min = df["prediction_date"].min().date()
    _all_max = df["prediction_date"].max().date()
    _fcol1, _fcol2 = st.columns(2)
    _filter_from = _fcol1.date_input(
        "Filter from", value=_all_min, min_value=_all_min, max_value=_all_max, key="global_from"
    )
    _filter_to = _fcol2.date_input(
        "Filter to", value=_all_max, min_value=_all_min, max_value=_all_max, key="global_to"
    )
    if _filter_from > _filter_to:
        st.warning("'Filter from' date must be on or before 'Filter to' date.")
        _filter_from, _filter_to = _all_min, _all_max

    df_view = df[
        (df["prediction_date"].dt.date >= _filter_from)
        & (df["prediction_date"].dt.date <= _filter_to)
    ]
else:
    df_view = df

# ---------------------------------------------------------------------------
# Compute P&L for actionable rows (ev > 0)
# ---------------------------------------------------------------------------

actionable = (
    df_view[(df_view["ev"] > 0) & df_view["actual_outcome"].notna()].copy()
    if "ev" in df_view.columns else pd.DataFrame()
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

def _render_summary(df_all: pd.DataFrame, act: pd.DataFrame) -> None:
    n_rows_total = len(df_all)

    if not act.empty:
        win_rate_str = f"{(act['actual_outcome'] == 1).mean():.1%}"
    else:
        win_rate_str = "—"

    clv_src = df_all[df_all["closing_market_prob"].notna()] if "closing_market_prob" in df_all.columns else pd.DataFrame()
    if not clv_src.empty:
        mean_clv_str = f"{(clv_src['model_prob'] - clv_src['closing_market_prob']).mean():+.4f}"
    else:
        mean_clv_str = "—"

    if not act.empty:
        act = act.sort_values("prediction_date").copy()
        act["_kelly_pnl"] = act["kelly_fraction"] * (
            act["actual_outcome"] * (act["decimal_odds"] - 1) - (1 - act["actual_outcome"])
        )
        act["_flat_pnl"] = 1.0 * (
            act["actual_outcome"] * (act["decimal_odds"] - 1) - (1 - act["actual_outcome"])
        )
        kelly_pnl_str = f"{act['_kelly_pnl'].sum():+.2f} units"
        flat_pnl_str = f"{act['_flat_pnl'].sum():+.2f} units"
    else:
        kelly_pnl_str = flat_pnl_str = "—"

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Predictions Logged", n_rows_total)
    col2.metric(
        "Win Rate (Actionable)", win_rate_str,
        help=(
            "Percentage of bets won among actionable predictions (EV > 0). "
            "An EV > 0 bet means the model estimated a higher win probability than "
            "the market implied — above 50% is expected but does not guarantee profit."
        ),
    )
    col3.metric(
        "Mean CLV", mean_clv_str,
        help=(
            "Closing Line Value: the average difference between the model's predicted "
            "probability and the market's closing (pre-game) probability. "
            "Positive CLV means predictions consistently found better prices than where "
            "the market settled — the strongest long-run indicator of a real edge."
        ),
    )
    col4.metric(
        "Cumulative P&L (Kelly)", kelly_pnl_str,
        help=(
            "Simulated profit/loss using Kelly-fractional bet sizing. "
            "The kelly_fraction logged at prediction time determines stake size as a "
            "fraction of bankroll. 1 unit = your chosen base bet size."
        ),
    )
    col5.metric(
        "Cumulative P&L (Flat)", flat_pnl_str,
        help=(
            "Simulated profit/loss using a flat 1-unit stake on every actionable bet "
            "(EV > 0). Higher variance than Kelly staking but easier to benchmark "
            "against a simple buy-and-hold baseline."
        ),
    )


st.header("Summary")

_s_tab_combined, _s_tab_h2h, _s_tab_totals = st.tabs(["Combined", "Moneyline (h2h)", "Totals"])

with _s_tab_combined:
    _render_summary(df_view, actionable)

with _s_tab_h2h:
    _df_h2h = df_view[df_view["market"] == "h2h"] if "market" in df_view.columns else df_view
    _act_h2h = actionable[actionable["market"] == "h2h"] if "market" in actionable.columns else pd.DataFrame()
    _render_summary(_df_h2h, _act_h2h)

with _s_tab_totals:
    _df_tot = df_view[df_view["market"] == "totals"] if "market" in df_view.columns else df_view
    _act_tot = actionable[actionable["market"] == "totals"] if "market" in actionable.columns else pd.DataFrame()
    _render_summary(_df_tot, _act_tot)

# ---------------------------------------------------------------------------
# Brier Score Trend
# ---------------------------------------------------------------------------

def _render_brier(df_src: pd.DataFrame) -> None:
    brier_src = df_src[["prediction_date", "model_prob", "market_prob_at_prediction", "actual_outcome"]].dropna(
        subset=["model_prob", "actual_outcome"]
    )
    if brier_src.empty:
        st.info("No Brier score data available for this market.")
        return

    brier_src = brier_src.copy()
    brier_src["brier_model"] = (brier_src["model_prob"] - brier_src["actual_outcome"]) ** 2
    brier_src["brier_market"] = (brier_src["market_prob_at_prediction"] - brier_src["actual_outcome"]) ** 2

    grouped = (
        brier_src.groupby("prediction_date")
        .agg(brier_model=("brier_model", "mean"), brier_market=("brier_market", "mean"))
        .reset_index()
        .sort_values("prediction_date")
    )

    few_days = len(grouped) < 14
    grouped["brier_model_14d"] = grouped["brier_model"].rolling(14, min_periods=1).mean()
    grouped["brier_market_14d"] = grouped["brier_market"].rolling(14, min_periods=1).mean()

    long = grouped[["prediction_date", "brier_model_14d", "brier_market_14d"]].melt(
        id_vars="prediction_date",
        value_vars=["brier_model_14d", "brier_market_14d"],
        var_name="series",
        value_name="brier",
    )
    long["series"] = long["series"].map(
        {"brier_model_14d": "Model (Brier)", "brier_market_14d": "Market (Brier)"}
    )

    chart = (
        alt.Chart(long)
        .mark_line()
        .encode(
            x=alt.X("prediction_date:T", title="Date",
                    axis=alt.Axis(format="%b %d", labelAngle=-45, tickCount="day")),
            y=alt.Y("brier:Q", title="Brier Score", scale=alt.Scale(zero=False)),
            color=alt.Color("series:N", legend=alt.Legend(title=None)),
            tooltip=[
                alt.Tooltip("prediction_date:T", title="Date", format="%b %d"),
                alt.Tooltip("series:N", title="Series"),
                alt.Tooltip("brier:Q", title="Brier Score", format=".4f"),
            ],
        )
        .properties(height=300)
    )
    st.altair_chart(chart, use_container_width=True)

    if few_days:
        st.caption("Fewer than 14 days of data — rolling average not yet meaningful.")
    else:
        st.caption("Lower Brier score = better calibration. Market benchmark ≈ 0.2395 (Card 3.11 baseline).")


st.header("Brier Score Trend")
st.caption(
    "The **Brier score** measures how well-calibrated probability predictions are: "
    "lower is better, with 0.25 being the random-guessing (50/50) baseline. "
    "The **Model** line tracks our predictions; the **Market** line tracks the "
    "market's implied probabilities at prediction time. "
    "When the model line sits below the market line, the model is better calibrated."
)

_b_tab_combined, _b_tab_h2h, _b_tab_totals = st.tabs(["Combined", "Moneyline (h2h)", "Totals"])

with _b_tab_combined:
    _render_brier(df_view)

with _b_tab_h2h:
    _render_brier(df_view[df_view["market"] == "h2h"] if "market" in df_view.columns else df_view)

with _b_tab_totals:
    _render_brier(df_view[df_view["market"] == "totals"] if "market" in df_view.columns else df_view)

# ---------------------------------------------------------------------------
# CLV Tracker
# ---------------------------------------------------------------------------

st.header("Closing Line Value (CLV)")
st.caption(
    "Each bar shows the average CLV for one week of predictions. "
    "**CLV = model probability − market closing probability.** "
    "A positive bar means the model consistently predicted higher win chances than "
    "where the market settled before game time — a sign of genuine edge. "
    "A negative bar means the market closed at a higher probability than the model "
    "estimated, which suggests the model may be undervaluing those outcomes. "
    "Hover over a bar to see the exact week dates and CLV value."
)

clv_df = (
    df_view[df_view["closing_market_prob"].notna()].copy()
    if "closing_market_prob" in df_view.columns
    else pd.DataFrame()
)

if clv_df.empty:
    st.info(
        "CLV data not yet available. The nightly backfill job populates "
        "closing_market_prob from mart_odds_outcomes. Check back after "
        "the daily_ingestion workflow has run."
    )
else:
    clv_df["clv"] = clv_df["model_prob"] - clv_df["closing_market_prob"]

    # Compute week start (Monday) for each row, then build a readable date-range label.
    clv_df["week_start"] = clv_df["prediction_date"] - pd.to_timedelta(
        clv_df["prediction_date"].dt.dayofweek, unit="D"
    )
    clv_df["week_start"] = clv_df["week_start"].dt.normalize()

    df_clv = (
        clv_df.groupby(["week_start", "market"], sort=True)
        .agg(mean_clv=("clv", "mean"))
        .reset_index()
    )
    df_clv["week_end"] = df_clv["week_start"] + pd.Timedelta(days=6)
    df_clv["week_label"] = (
        df_clv["week_start"].dt.strftime("%b %-d")
        + " – "
        + df_clv["week_end"].dt.strftime("%b %-d")
    )
    df_clv["market_label"] = df_clv["market"].map({"h2h": "Moneyline (h2h)", "totals": "Totals"})

    chart = (
        alt.Chart(df_clv)
        .mark_bar()
        .encode(
            x=alt.X("week_label:N", sort=None, title="Week"),
            y=alt.Y("mean_clv:Q", title="Mean CLV"),
            color=alt.Color(
                "market_label:N",
                scale=alt.Scale(
                    domain=["Moneyline (h2h)", "Totals"],
                    range=["#1f77b4", "#ff7f0e"],
                ),
                legend=alt.Legend(title="Market"),
            ),
            xOffset=alt.XOffset("market_label:N"),
            tooltip=[
                alt.Tooltip("week_label:N", title="Week"),
                alt.Tooltip("market_label:N", title="Market"),
                alt.Tooltip("mean_clv:Q", title="Mean CLV", format="+.4f"),
            ],
        )
        .properties(title="Mean CLV by Week and Market")
    )
    st.altair_chart(chart, use_container_width=True)

# ---------------------------------------------------------------------------
# P&L Simulation
# ---------------------------------------------------------------------------

st.header("Cumulative P&L Simulation")
st.caption(
    "This chart shows simulated profit and loss over time for every prediction where the model "
    "estimated positive expected value (EV > 0). "
    "**Flat staking** bets exactly 1 unit on every qualifying prediction regardless of edge size — "
    "easy to benchmark but ignores the model's confidence. "
    "**Kelly staking** sizes each bet as a fraction of bankroll proportional to the estimated edge "
    "(kelly_fraction logged at prediction time), so a small edge = a small stake. "
    "Kelly fractions are intentionally conservative, which is why the Kelly line stays much lower "
    "than the Flat line — it is not underperforming, it is simply risking far less per bet. "
    "A rising line means the strategy is profitable over the selected date range; "
    "the slope tells you how quickly edge is being captured."
)

if actionable.empty:
    st.info("No actionable predictions (ev > 0) found in the log yet.")
else:
    def _build_pnl_chart(df_subset: pd.DataFrame) -> alt.Chart:
        """Compute cumulative P&L for a subset of actionable rows and return an Altair chart."""
        if df_subset.empty:
            return None
        df_subset = df_subset.sort_values("prediction_date").copy()
        df_subset["kelly_pnl"] = df_subset["kelly_fraction"] * (
            df_subset["actual_outcome"] * (df_subset["decimal_odds"] - 1)
            - (1 - df_subset["actual_outcome"])
        )
        df_subset["flat_pnl"] = 1.0 * (
            df_subset["actual_outcome"] * (df_subset["decimal_odds"] - 1)
            - (1 - df_subset["actual_outcome"])
        )
        df_subset["kelly_cumulative"] = df_subset["kelly_pnl"].cumsum()
        df_subset["flat_cumulative"] = df_subset["flat_pnl"].cumsum()

        daily = (
            df_subset.groupby(df_subset["prediction_date"].dt.date)
            .agg(kelly_cumulative=("kelly_cumulative", "last"), flat_cumulative=("flat_cumulative", "last"))
            .reset_index()
            .rename(columns={"prediction_date": "date"})
        )
        daily["date"] = pd.to_datetime(daily["date"])

        long = daily.melt(
            id_vars="date",
            value_vars=["kelly_cumulative", "flat_cumulative"],
            var_name="strategy",
            value_name="cumulative_units",
        )
        long["strategy"] = long["strategy"].map(
            {"kelly_cumulative": "Kelly", "flat_cumulative": "Flat (1 unit)"}
        )

        return (
            alt.Chart(long)
            .mark_line(point=True)
            .encode(
                x=alt.X(
                    "date:T",
                    title="Date",
                    axis=alt.Axis(format="%b %d", labelAngle=-45, tickCount="day"),
                ),
                y=alt.Y("cumulative_units:Q", title="Cumulative Units"),
                color=alt.Color("strategy:N", legend=alt.Legend(title="Strategy")),
                tooltip=[
                    alt.Tooltip("date:T", title="Date", format="%b %d"),
                    alt.Tooltip("strategy:N", title="Strategy"),
                    alt.Tooltip("cumulative_units:Q", title="Cumulative Units", format="+.2f"),
                ],
            )
            .properties(height=350)
        )

    tab_combined, tab_h2h, tab_totals = st.tabs(["Combined", "Moneyline (h2h)", "Totals"])

    with tab_combined:
        chart = _build_pnl_chart(actionable)
        if chart:
            st.altair_chart(chart, use_container_width=True)

    with tab_h2h:
        subset = actionable[actionable["market"] == "h2h"] if "market" in actionable.columns else pd.DataFrame()
        chart = _build_pnl_chart(subset)
        if chart:
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No actionable h2h predictions in this date range.")

    with tab_totals:
        subset = actionable[actionable["market"] == "totals"] if "market" in actionable.columns else pd.DataFrame()
        chart = _build_pnl_chart(subset)
        if chart:
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No actionable totals predictions in this date range.")
