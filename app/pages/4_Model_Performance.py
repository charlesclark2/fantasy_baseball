"""Performance Tracker page — historical prediction quality."""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

import datetime

from app.utils.db import get_snowflake_session, run_query

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

_PLACED_BETS_SQL = """
SELECT
    b.score_date,
    b.matchup,
    b.market,
    b.american_odds,
    b.stake,
    b.total_line,
    b.outcome,
    g.home_score,
    g.away_score,
    g.status_code
FROM baseball_data.betting_ml.placed_bets b
LEFT JOIN baseball_data.betting.stg_statsapi_games g
    ON b.game_pk = g.game_pk
    AND g.status_code = 'F'
ORDER BY b.score_date ASC, b.placed_at ASC
"""

_PREDICTION_LOG_SQL = """
WITH game_versions AS (
    SELECT game_pk, MIN(model_version) AS model_version
    FROM baseball_data.betting_ml.daily_model_predictions
    GROUP BY game_pk
)
SELECT
    p.prediction_date,
    p.game_pk,
    p.market,
    COALESCE(gv.model_version, 'v0') AS model_version,
    p.model_prob,
    p.market_prob_at_prediction,
    p.closing_market_prob,
    p.actual_outcome,
    p.decimal_odds,
    p.ev,
    p.kelly_fraction
FROM baseball_data.config.prediction_log p
LEFT JOIN game_versions gv ON p.game_pk = gv.game_pk
ORDER BY p.prediction_date ASC
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

_MART_CLV_SQL = """
SELECT
    game_date,
    score_date,
    model_version,
    clv_home_ml,
    clv_total,
    has_clv,
    has_odds,
    open_vf_home,
    close_vf_home,
    n_books_with_clv
FROM baseball_data.betting.mart_prediction_clv
WHERE has_odds = TRUE
ORDER BY game_date ASC
"""

# ---------------------------------------------------------------------------
# Cached data loading
# ---------------------------------------------------------------------------


def _table_missing(exc: Exception) -> bool:
    return "002003" in str(exc) or "does not exist" in str(exc).lower()


@st.cache_data(ttl=300)
def load_placed_bets() -> pd.DataFrame:
    try:
        df = run_query(_PLACED_BETS_SQL)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    df["score_date"] = pd.to_datetime(df["score_date"]).dt.date
    for col in ("american_odds", "home_score", "away_score"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("stake", "total_line"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _settle_outcome(row: pd.Series) -> str | None:
    if pd.isna(row.get("status_code")) or row.get("status_code") != "F":
        return None
    hs, as_ = row.get("home_score"), row.get("away_score")
    if pd.isna(hs) or pd.isna(as_):
        return None
    total = hs + as_
    market = str(row.get("market", ""))
    tl = row.get("total_line")
    if market == "h2h home":
        return "win" if hs > as_ else "loss"
    if market == "h2h away":
        return "win" if as_ > hs else "loss"
    if market in ("over", "under") and not pd.isna(tl):
        if total > tl:
            return "win" if market == "over" else "loss"
        if total < tl:
            return "win" if market == "under" else "loss"
        return "push"
    return None


def _pl_from_outcome(stake: float, american_odds: int, outcome: str | None) -> float | None:
    if outcome is None:
        return None
    if outcome == "push":
        return 0.0
    dec = (american_odds / 100 + 1) if american_odds > 0 else (100 / abs(american_odds) + 1)
    return stake * (dec - 1) if outcome == "win" else -stake


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
def load_mart_clv_data() -> pd.DataFrame:
    try:
        df = run_query(_MART_CLV_SQL)
    except Exception as exc:
        if _table_missing(exc):
            return pd.DataFrame()
        raise
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    for col in ["clv_home_ml", "clv_total", "open_vf_home", "close_vf_home", "n_books_with_clv"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "game_date" in df.columns:
        df["game_date"] = pd.to_datetime(df["game_date"])
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
    load_mart_clv_data.clear()
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

    st.divider()
    st.subheader("Model Version")
    _all_versions: list[str] = []  # populated after data load below

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
# Global date range + model version filter
# ---------------------------------------------------------------------------

# Season selector (sidebar) — drives the default date range. Computed from
# the full unfiltered df so every season with data shows up.
if not df.empty and "prediction_date" in df.columns:
    _all_seasons = sorted(df["prediction_date"].dt.year.dropna().unique().astype(int).tolist())
else:
    _all_seasons = []

with st.sidebar:
    st.divider()
    st.subheader("Season")
    if _all_seasons:
        _season_options = ["All Seasons"] + [str(s) for s in _all_seasons]
        _current_year = datetime.date.today().year
        _default_idx = (
            _season_options.index(str(_current_year))
            if str(_current_year) in _season_options
            else 0
        )
        _selected_season = st.selectbox(
            "Show season",
            options=_season_options,
            index=_default_idx,
            key="season_filter",
        )
    else:
        _selected_season = "All Seasons"
        st.caption("Season data not available.")

# Resolve the season's [min, max] date bounds — these become the default for
# the date range and constrain its allowed values.
if not df.empty and "prediction_date" in df.columns:
    _all_min = df["prediction_date"].min().date()
    _all_max = df["prediction_date"].max().date()
    if _selected_season == "All Seasons":
        _season_min, _season_max = _all_min, _all_max
    else:
        _season_dates = df.loc[df["prediction_date"].dt.year == int(_selected_season), "prediction_date"]
        _season_min = _season_dates.min().date()
        _season_max = _season_dates.max().date()

    # Date inputs are keyed by season so switching season resets the range to
    # that season's bounds (rather than carrying over a stale prior selection).
    _date_key_suffix = _selected_season
    _fcol1, _fcol2 = st.columns(2)
    _filter_from = _fcol1.date_input(
        "Filter from",
        value=_season_min,
        min_value=_season_min,
        max_value=_season_max,
        key=f"global_from_{_date_key_suffix}",
    )
    _filter_to = _fcol2.date_input(
        "Filter to",
        value=_season_max,
        min_value=_season_min,
        max_value=_season_max,
        key=f"global_to_{_date_key_suffix}",
    )
    if _filter_from > _filter_to:
        st.warning("'Filter from' date must be on or before 'Filter to' date.")
        _filter_from, _filter_to = _season_min, _season_max

    df_view = df[
        (df["prediction_date"].dt.date >= _filter_from)
        & (df["prediction_date"].dt.date <= _filter_to)
    ]
else:
    df_view = df

# Model version sidebar filter (rendered here so we have data to inspect)
if "model_version" in df_view.columns:
    _all_versions = sorted(df_view["model_version"].dropna().unique().tolist())
else:
    _all_versions = []

with st.sidebar:
    if _all_versions:
        _selected_versions = st.multiselect(
            "Show versions",
            options=_all_versions,
            default=_all_versions,
            key="version_filter",
        )
        if _selected_versions and set(_selected_versions) != set(_all_versions):
            df_view = df_view[df_view["model_version"].isin(_selected_versions)]
    else:
        st.caption("Version data not available.")

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
    has_version = "model_version" in df_src.columns
    multi_version = has_version and df_src["model_version"].nunique() > 1

    cols_needed = ["prediction_date", "model_prob", "market_prob_at_prediction", "actual_outcome"]
    if has_version:
        cols_needed.append("model_version")

    brier_src = df_src[cols_needed].dropna(subset=["model_prob", "actual_outcome"])
    if brier_src.empty:
        st.info("No Brier score data available for this market.")
        return

    brier_src = brier_src.copy()
    brier_src["brier_model"] = (brier_src["model_prob"] - brier_src["actual_outcome"]) ** 2
    brier_src["brier_market"] = (brier_src["market_prob_at_prediction"] - brier_src["actual_outcome"]) ** 2

    group_cols = ["prediction_date"] + (["model_version"] if multi_version else [])
    grouped = (
        brier_src.groupby(group_cols)
        .agg(brier_model=("brier_model", "mean"), brier_market=("brier_market", "mean"))
        .reset_index()
        .sort_values("prediction_date")
    )

    few_days = grouped["prediction_date"].nunique() < 14

    if multi_version:
        for mv in grouped["model_version"].unique():
            mask = grouped["model_version"] == mv
            grouped.loc[mask, "brier_model_14d"] = grouped.loc[mask, "brier_model"].rolling(14, min_periods=1).mean()
            grouped.loc[mask, "brier_market_14d"] = grouped.loc[mask, "brier_market"].rolling(14, min_periods=1).mean()
        long = grouped[["prediction_date", "model_version", "brier_model_14d", "brier_market_14d"]].melt(
            id_vars=["prediction_date", "model_version"],
            value_vars=["brier_model_14d", "brier_market_14d"],
            var_name="source",
            value_name="brier",
        )
        long["source"] = long["source"].map({"brier_model_14d": "Model", "brier_market_14d": "Market"})
        long["series"] = long["model_version"] + " — " + long["source"]
    else:
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

    # Drop series with too few points to render meaningfully (avoids ghost
    # legend entries when one version has only a handful of games tagged).
    _MIN_POINTS_PER_SERIES = 5
    _viable = (
        long.groupby("series")["brier"]
        .apply(lambda s: s.notna().sum())
    )
    _viable = _viable[_viable >= _MIN_POINTS_PER_SERIES].index
    long = long[long["series"].isin(_viable)]
    if long.empty:
        st.info("Not enough data to draw the Brier trend for this filter.")
        return

    tooltip = [
        alt.Tooltip("prediction_date:T", title="Date", format="%b %d"),
        alt.Tooltip("series:N", title="Series"),
        alt.Tooltip("brier:Q", title="Brier Score", format=".4f"),
    ]
    if multi_version:
        tooltip.insert(1, alt.Tooltip("model_version:N", title="Version"))

    chart = (
        alt.Chart(long)
        .mark_line()
        .encode(
            x=alt.X("prediction_date:T", title="Date",
                    axis=alt.Axis(format="%b %d", labelAngle=-45, tickCount="day")),
            y=alt.Y("brier:Q", title="Brier Score", scale=alt.Scale(zero=False)),
            color=alt.Color("series:N", legend=alt.Legend(title=None)),
            tooltip=tooltip,
        )
        .properties(height=300)
    )
    st.altair_chart(chart, width='stretch')

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
# Closing Line Value — Market Movement (mart_prediction_clv)
# ---------------------------------------------------------------------------

st.header("Closing Line Value (Market Movement)")

with st.expander("What is CLV?", expanded=False):
    st.markdown(
        "**Closing Line Value (CLV)** measures whether the market moved *toward* our "
        "model's view between the opening line (morning prediction run, ~08:00 EDT) and "
        "the closing line (last snapshot before first pitch).\n\n"
        "- **clv_home_ml > 0** on a game: the closing market assigned *more* probability "
        "to the home team winning than the opening market did. If our model also predicted "
        "home team edge, that is CLV evidence of real edge.\n"
        "- **Positive mean CLV** across all predictions is the strongest long-run indicator "
        "of model edge, independent of short-term win/loss P&L.\n\n"
        "Source: `mart_prediction_clv` (dbt) — averages vig-free implied probabilities "
        "across up to 19 bookmakers per game."
    )

_mart_clv_raw = load_mart_clv_data()

if _mart_clv_raw.empty:
    st.info(
        "CLV data not yet available from mart_prediction_clv. "
        "Run `dbtf build --select mart_closing_line_value mart_prediction_clv` to populate."
    )
else:
    # Apply season filter using game_date (same logic as global sidebar filter)
    _mclv = _mart_clv_raw.copy()
    if not _mclv.empty and "game_date" in _mclv.columns:
        if "_filter_from" in dir() and _filter_from is not None:
            _mclv = _mclv[
                (_mclv["game_date"].dt.date >= _filter_from)
                & (_mclv["game_date"].dt.date <= _filter_to)
            ]
    # Apply model_version filter
    if "_selected_versions" in dir() and _selected_versions and "model_version" in _mclv.columns:
        _mclv = _mclv[_mclv["model_version"].isin(_selected_versions)]

    _mclv_has_clv = _mclv[_mclv["has_clv"] == True].copy() if not _mclv.empty else pd.DataFrame()

    # ── Summary metrics ───────────────────────────────────────────────────────
    if not _mclv_has_clv.empty:
        _mean_clv_ml  = _mclv_has_clv["clv_home_ml"].mean()
        _pct_positive = (_mclv_has_clv["clv_home_ml"] > 0).mean()
        _mean_clv_tot = _mclv_has_clv["clv_total"].dropna().mean() if "clv_total" in _mclv_has_clv.columns else float("nan")
        _n_with_clv   = int(_mclv_has_clv["has_clv"].sum())
        _coverage_pct = _n_with_clv / max(len(_mclv), 1) * 100

        _cm1, _cm2, _cm3, _cm4 = st.columns(4)
        _cm1.metric(
            "Mean CLV (moneyline)",
            f"{_mean_clv_ml:+.4f}",
            help="Average (close_vf_home − open_vf_home). Positive = market moved toward home team.",
        )
        _cm2.metric(
            "Pct Predictions with Positive CLV",
            f"{_pct_positive:.1%}",
            help="Fraction of games where clv_home_ml > 0 (market moved toward home by close).",
        )
        _cm3.metric(
            "Median CLV (moneyline)",
            f"{_mclv_has_clv['clv_home_ml'].median():+.4f}",
            help="Median CLV across all has_clv games.",
        )
        _cm4.metric(
            "Mean CLV (totals)",
            f"{_mean_clv_tot:+.3f} lines" if not pd.isna(_mean_clv_tot) else "—",
            help="Average (close_total_line − open_total_line). Negative = market moved toward under.",
        )
    else:
        st.info("No CLV data available for the selected filters.")

    # ── Rolling 14-day mean CLV chart ─────────────────────────────────────────
    if not _mclv_has_clv.empty and "game_date" in _mclv_has_clv.columns:
        _has_versions_clv = "model_version" in _mclv_has_clv.columns and _mclv_has_clv["model_version"].nunique() > 1

        if _has_versions_clv:
            _daily_clv = (
                _mclv_has_clv.groupby(["game_date", "model_version"])
                .agg(mean_clv_ml=("clv_home_ml", "mean"))
                .reset_index()
                .sort_values(["model_version", "game_date"])
            )
            for _mv in _daily_clv["model_version"].unique():
                _mask = _daily_clv["model_version"] == _mv
                _daily_clv.loc[_mask, "clv_14d"] = (
                    _daily_clv.loc[_mask, "mean_clv_ml"].rolling(14, min_periods=1).mean()
                )
            _clv_long = _daily_clv[["game_date", "model_version", "clv_14d"]].dropna()
            _clv_color = alt.Color("model_version:N", legend=alt.Legend(title="Version"))
        else:
            _daily_clv = (
                _mclv_has_clv.groupby("game_date")
                .agg(mean_clv_ml=("clv_home_ml", "mean"))
                .reset_index()
                .sort_values("game_date")
            )
            _daily_clv["clv_14d"] = _daily_clv["mean_clv_ml"].rolling(14, min_periods=1).mean()
            _daily_clv["model_version"] = "All"
            _clv_long = _daily_clv[["game_date", "model_version", "clv_14d"]].dropna()
            _clv_color = alt.value("#1f77b4")

        if not _clv_long.empty:
            _zero_line = (
                alt.Chart(pd.DataFrame({"y": [0]}))
                .mark_rule(color="grey", strokeDash=[4, 4])
                .encode(y="y:Q")
            )
            _clv_chart = (
                alt.Chart(_clv_long)
                .mark_line()
                .encode(
                    x=alt.X("game_date:T", title="Game Date",
                            axis=alt.Axis(format="%b %d", labelAngle=-45, tickCount="week")),
                    y=alt.Y("clv_14d:Q", title="14-Day Rolling Mean CLV"),
                    color=_clv_color,
                    tooltip=[
                        alt.Tooltip("game_date:T", title="Date", format="%b %d"),
                        alt.Tooltip("model_version:N", title="Version"),
                        alt.Tooltip("clv_14d:Q", title="14d Mean CLV", format="+.4f"),
                    ],
                )
                .properties(height=280, title="Rolling 14-Day Mean CLV (Moneyline)")
            )
            st.altair_chart((_clv_chart + _zero_line).properties(height=280), width="stretch")
            st.caption(
                "Rolling 14-day mean of (close_vf_home − open_vf_home) across all has_clv games. "
                "Dashed line = 0 reference. Consistently above zero confirms the model is "
                "identifying value before the market corrects."
            )

    # ── CLV distribution histogram ────────────────────────────────────────────
    if not _mclv_has_clv.empty:
        _has_multi_mv = "model_version" in _mclv_has_clv.columns and _mclv_has_clv["model_version"].nunique() > 1
        _95th = float(_mclv_has_clv["clv_home_ml"].quantile(0.95))

        _hist_base = alt.Chart(_mclv_has_clv)
        _hist_encode = dict(
            x=alt.X("clv_home_ml:Q", bin=alt.Bin(maxbins=40), title="CLV (Moneyline)"),
            y=alt.Y("count():Q", title="Game Count"),
            tooltip=[
                alt.Tooltip("clv_home_ml:Q", bin=True, title="CLV Bin"),
                alt.Tooltip("count():Q", title="Count"),
            ],
        )
        if _has_multi_mv:
            _hist_encode["color"] = alt.Color("model_version:N", legend=alt.Legend(title="Version"))

        _hist_chart = _hist_base.mark_bar(opacity=0.7).encode(**_hist_encode).properties(
            height=220, title="CLV Distribution (Moneyline)"
        )
        _zero_rule_hist = (
            alt.Chart(pd.DataFrame({"x": [0]}))
            .mark_rule(color="red", strokeDash=[4, 4])
            .encode(x="x:Q")
        )
        st.altair_chart((_hist_chart + _zero_rule_hist).properties(height=220), width="stretch")
        st.caption(
            f"CLV distribution across all has_clv games in the selected date range. "
            f"Red dashed line = 0. 95th percentile: {_95th:+.4f}."
        )

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
    st.altair_chart(chart, width='stretch')

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
    def _build_pnl_charts(df_subset: pd.DataFrame) -> tuple[alt.Chart | None, alt.Chart | None]:
        """Compute cumulative P&L for a subset of actionable rows.

        Returns (units_chart, roi_chart):
            - units_chart: cumulative dollar/unit P&L (per-strategy)
            - roi_chart:   cumulative ROI% (= cumulative_pnl / cumulative_stake)
        ROI% normalises away the stake-size difference between Kelly (tiny per-bet
        fractions of bankroll) and Flat (1 unit per bet), making the two strategies
        comparable on a common scale.
        """
        if df_subset.empty:
            return None, None
        df_subset = df_subset.sort_values("prediction_date").copy()
        df_subset["kelly_stake"] = df_subset["kelly_fraction"]
        df_subset["flat_stake"]  = 1.0
        df_subset["kelly_pnl"] = df_subset["kelly_stake"] * (
            df_subset["actual_outcome"] * (df_subset["decimal_odds"] - 1)
            - (1 - df_subset["actual_outcome"])
        )
        df_subset["flat_pnl"] = df_subset["flat_stake"] * (
            df_subset["actual_outcome"] * (df_subset["decimal_odds"] - 1)
            - (1 - df_subset["actual_outcome"])
        )
        df_subset["kelly_cumulative"]       = df_subset["kelly_pnl"].cumsum()
        df_subset["flat_cumulative"]        = df_subset["flat_pnl"].cumsum()
        df_subset["kelly_cumulative_stake"] = df_subset["kelly_stake"].cumsum()
        df_subset["flat_cumulative_stake"]  = df_subset["flat_stake"].cumsum()

        daily = (
            df_subset.groupby(df_subset["prediction_date"].dt.date)
            .agg(
                kelly_cumulative=("kelly_cumulative", "last"),
                flat_cumulative=("flat_cumulative", "last"),
                kelly_cumulative_stake=("kelly_cumulative_stake", "last"),
                flat_cumulative_stake=("flat_cumulative_stake", "last"),
            )
            .reset_index()
            .rename(columns={"prediction_date": "date"})
        )
        daily["date"] = pd.to_datetime(daily["date"])

        # ROI% = cumulative_pnl / cumulative_stake (avoid div-by-zero).
        # Suppress the warmup period — with only 1–2 bets settled, ROI% swings
        # between ±100% per outcome, which dominates the y-axis and hides the
        # actual long-run trend. Only render ROI once enough stake has accrued.
        _FLAT_STAKE_WARMUP = 10  # ~10 flat-unit bets before ROI% becomes informative
        daily["kelly_roi_pct"] = (
            daily["kelly_cumulative"] / daily["kelly_cumulative_stake"].replace(0, pd.NA) * 100.0
        )
        daily["flat_roi_pct"] = (
            daily["flat_cumulative"] / daily["flat_cumulative_stake"].replace(0, pd.NA) * 100.0
        )
        warmup_mask = daily["flat_cumulative_stake"] < _FLAT_STAKE_WARMUP
        daily.loc[warmup_mask, ["kelly_roi_pct", "flat_roi_pct"]] = pd.NA

        # ----- Cumulative units chart -----
        long_units = daily.melt(
            id_vars="date",
            value_vars=["kelly_cumulative", "flat_cumulative"],
            var_name="strategy",
            value_name="cumulative_units",
        )
        long_units["strategy"] = long_units["strategy"].map(
            {"kelly_cumulative": "Kelly", "flat_cumulative": "Flat (1 unit)"}
        )

        units_chart = (
            alt.Chart(long_units)
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
            .properties(height=350, title="Cumulative P&L (Units)")
        )

        # ----- Cumulative ROI% chart -----
        long_roi = daily.melt(
            id_vars="date",
            value_vars=["kelly_roi_pct", "flat_roi_pct"],
            var_name="strategy",
            value_name="roi_pct",
        )
        long_roi["strategy"] = long_roi["strategy"].map(
            {"kelly_roi_pct": "Kelly", "flat_roi_pct": "Flat (1 unit)"}
        )
        long_roi = long_roi.dropna(subset=["roi_pct"])

        roi_chart = (
            alt.Chart(long_roi)
            .mark_line(point=True)
            .encode(
                x=alt.X(
                    "date:T",
                    title="Date",
                    axis=alt.Axis(format="%b %d", labelAngle=-45, tickCount="day"),
                ),
                y=alt.Y("roi_pct:Q", title="Cumulative ROI %"),
                color=alt.Color("strategy:N", legend=alt.Legend(title="Strategy")),
                tooltip=[
                    alt.Tooltip("date:T", title="Date", format="%b %d"),
                    alt.Tooltip("strategy:N", title="Strategy"),
                    alt.Tooltip("roi_pct:Q", title="ROI %", format="+.2f"),
                ],
            )
            .properties(height=300, title="Cumulative ROI % (stake-normalised)")
        )

        return units_chart, roi_chart

    def _render_pnl_tab(df_subset: pd.DataFrame, empty_msg: str) -> None:
        units_chart, roi_chart = _build_pnl_charts(df_subset)
        if units_chart is None:
            st.info(empty_msg)
            return
        st.altair_chart(units_chart, width='stretch')
        st.caption(
            "**ROI %** divides cumulative P&L by cumulative stake, so Kelly and Flat "
            "are comparable on the same axis even though Kelly bets a much smaller "
            "fraction of bankroll per pick."
        )
        st.altair_chart(roi_chart, width='stretch')

    tab_combined, tab_h2h, tab_totals = st.tabs(["Combined", "Moneyline (h2h)", "Totals"])

    with tab_combined:
        _render_pnl_tab(actionable, "No actionable predictions in this date range.")

    with tab_h2h:
        subset = actionable[actionable["market"] == "h2h"] if "market" in actionable.columns else pd.DataFrame()
        _render_pnl_tab(subset, "No actionable h2h predictions in this date range.")

    with tab_totals:
        subset = actionable[actionable["market"] == "totals"] if "market" in actionable.columns else pd.DataFrame()
        _render_pnl_tab(subset, "No actionable totals predictions in this date range.")

# ---------------------------------------------------------------------------
# Actual Bet Performance
# ---------------------------------------------------------------------------

st.header("Actual Bet Performance")
st.caption(
    "Real dollars wagered via the Bet Tracker, settled against actual game scores. "
    "Only bets that have been logged and whose games have a final score are included "
    "in the chart and metrics. Pending bets are excluded from the cumulative line."
)

df_bets = load_placed_bets()

if df_bets.empty:
    st.info("No bets logged yet. Use 'Log a Bet' on the EV Tracker page to start tracking.")
else:
    df_bets["_outcome"] = df_bets.apply(_settle_outcome, axis=1)
    df_bets["_pl"] = df_bets.apply(
        lambda r: _pl_from_outcome(
            float(r["stake"]) if not pd.isna(r["stake"]) else 0.0,
            int(r["american_odds"]) if not pd.isna(r["american_odds"]) else 0,
            r["_outcome"],
        ),
        axis=1,
    )

    settled_bets = df_bets[df_bets["_outcome"].notna()].copy()
    wins_b = (settled_bets["_outcome"] == "win").sum()
    losses_b = (settled_bets["_outcome"] == "loss").sum()
    pushes_b = (settled_bets["_outcome"] == "push").sum()
    total_wagered_b = float(settled_bets["stake"].sum()) if not settled_bets.empty else 0.0
    total_pl_b = float(settled_bets["_pl"].sum()) if not settled_bets.empty else 0.0
    roi_b = total_pl_b / total_wagered_b if total_wagered_b > 0 else 0.0
    total_bets = len(df_bets)
    pending_count = int(df_bets["_outcome"].isna().sum())

    bm1, bm2, bm3, bm4, bm5 = st.columns(5)
    bm1.metric("Total Bets", total_bets, help=f"{pending_count} pending settlement.")
    bm2.metric("Total Wagered ($)", f"{total_wagered_b:.2f}", help="Sum of stakes for settled bets.")
    bm3.metric(
        "Total P&L ($)",
        f"{total_pl_b:+.2f}",
        delta=f"{total_pl_b:+.2f}",
        help="Actual realized profit/loss across all settled bets.",
    )
    bm4.metric("ROI%", f"{roi_b:+.1%}", help="Total P&L ÷ Total Wagered (settled bets).")
    bm5.metric("Record (W-L-P)", f"{wins_b}-{losses_b}-{pushes_b}")

    if not settled_bets.empty:
        settled_bets = settled_bets.sort_values("score_date").copy()
        settled_bets["cumulative_pl"] = settled_bets["_pl"].cumsum()

        # Collapse to one point per date (last cumulative value of that day)
        daily_pl = (
            settled_bets.groupby("score_date")
            .agg(cumulative_pl=("cumulative_pl", "last"), daily_pl=("_pl", "sum"))
            .reset_index()
        )
        daily_pl["date"] = pd.to_datetime(daily_pl["score_date"])

        # Add a zero-origin row so the chart starts at 0
        origin = pd.DataFrame([{
            "date": daily_pl["date"].min() - pd.Timedelta(days=1),
            "cumulative_pl": 0.0,
            "daily_pl": 0.0,
        }])
        daily_pl = pd.concat([origin, daily_pl], ignore_index=True).sort_values("date")

        line = (
            alt.Chart(daily_pl)
            .mark_line(point=True, color="#2196F3")
            .encode(
                x=alt.X("date:T", title="Date",
                        axis=alt.Axis(format="%b %d", labelAngle=-45, tickCount="day")),
                y=alt.Y("cumulative_pl:Q", title="Cumulative P&L ($)"),
                tooltip=[
                    alt.Tooltip("date:T", title="Date", format="%b %d"),
                    alt.Tooltip("cumulative_pl:Q", title="Cumulative P&L ($)", format="+.2f"),
                    alt.Tooltip("daily_pl:Q", title="Day P&L ($)", format="+.2f"),
                ],
            )
        )
        zero_rule = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
            color="grey", strokeDash=[4, 4]
        ).encode(y="y:Q")

        st.altair_chart((line + zero_rule).properties(height=300), width='stretch')
    else:
        st.info("No bets have settled yet — check back after today's games are final.")
