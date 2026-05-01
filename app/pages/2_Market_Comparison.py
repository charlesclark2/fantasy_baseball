"""Market Comparison page — per-game deep-dive comparing model vs. bookmaker implied probabilities."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from app.utils.db import run_query

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Market Comparison — Baseball Betting Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _american_to_raw_prob(price: float) -> float:
    if price < 0:
        return abs(price) / (abs(price) + 100.0)
    return 100.0 / (price + 100.0)


def _vig_adjust(home_price: float, away_price: float) -> tuple[float, float, float]:
    """Return (home_imp_prob, away_imp_prob, vig) vig-adjusted from American odds."""
    hp = _american_to_raw_prob(home_price)
    ap = _american_to_raw_prob(away_price)
    total = hp + ap
    if total == 0:
        return np.nan, np.nan, np.nan
    return hp / total, ap / total, total - 1.0


def _fmt_pct(val) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"{float(val):.1%}"


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _fmt_american(val) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    v = round(float(val))
    return f"+{v}" if v > 0 else str(v)


def _fmt_game_time(val) -> str:
    if val is None:
        return "TBD"
    try:
        ts = pd.Timestamp(val)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.tz_convert("America/New_York").strftime("%-I:%M %p ET")
    except Exception:
        return str(val)


def _fmt_ts(val) -> str:
    """Format an ingestion_ts for human-readable display (e.g. 'Apr 28, 12:02 PM UTC')."""
    if val is None:
        return ""
    try:
        ts = pd.Timestamp(val)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.strftime("%b %-d, %-I:%M %p UTC")
    except Exception:
        return str(val)


# ---------------------------------------------------------------------------
# Data loading — all queries parameterized by date
# ---------------------------------------------------------------------------

def _games_sql(date_str: str) -> str:
    return f"""
    SELECT
        p.game_pk,
        p.game_datetime,
        p.home_team                    AS home_team_abbrev,
        p.away_team                    AS away_team_abbrev,
        g.home_team_name,
        g.away_team_name,
        g.double_header,
        g.game_number,
        e.event_id,
        p.consensus_win_prob,
        p.h2h_market_implied_prob,
        p.pred_total_runs,
        p.p_over_ngboost,
        p.over_prob_consensus,
        p.total_line_consensus,
        c.home_win_prob_sharp,
        c.home_win_prob_soft,
        c.sharp_soft_ml_delta,
        c.market_bookmaker_count
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY inserted_at DESC) AS _rn
        FROM baseball_data.betting_ml.daily_model_predictions
        WHERE score_date = '{date_str}'
          AND has_odds = TRUE
    ) p
    JOIN baseball_data.betting.stg_statsapi_games g
        ON g.game_pk = p.game_pk
    LEFT JOIN baseball_data.betting.mart_odds_events e
        ON e.home_team = g.home_team_name
        AND e.away_team = g.away_team_name
        AND e.commence_date = g.official_date
    LEFT JOIN baseball_data.betting.mart_odds_consensus c
        ON c.event_id = e.event_id
    WHERE p._rn = 1
    QUALIFY ROW_NUMBER() OVER (PARTITION BY p.game_pk ORDER BY e.event_id NULLS LAST) = 1
    ORDER BY p.game_datetime ASC
    """


@st.cache_data(ttl=300)
def load_games(date_str: str) -> pd.DataFrame:
    df = run_query(_games_sql(date_str))
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    return df


def _game_filter(event_id: str | None, home_team: str, away_team: str, date_str: str) -> str:
    """Return a SQL WHERE fragment that scopes to the specific game.

    Prefers event_id (unique per game, avoids cross-series collisions) and falls back
    to team names + commence_date when event_id is unavailable.
    """
    if event_id:
        return f"event_id = '{event_id}'"
    return f"home_team = '{home_team}' AND away_team = '{away_team}' AND commence_date = '{date_str}'"


@st.cache_data(ttl=300)
def load_line_movement(event_id: str | None, home_team: str, away_team: str, date_str: str) -> pd.DataFrame:
    """Load all h2h snapshots (pre- and post-game) for line movement chart."""
    gf = _game_filter(event_id, home_team, away_team, date_str)
    sql = f"""
    SELECT
        bookmaker_key,
        ingestion_ts,
        commence_time,
        MAX(CASE WHEN is_home_outcome THEN outcome_price_american END) AS home_price,
        MAX(CASE WHEN is_away_outcome THEN outcome_price_american END) AS away_price
    FROM baseball_data.betting.mart_odds_outcomes
    WHERE {gf}
      AND market_key = 'h2h'
    GROUP BY bookmaker_key, ingestion_ts, commence_time
    ORDER BY ingestion_ts ASC
    """
    df = run_query(sql)
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    df["home_imp_prob"] = df.apply(
        lambda r: _vig_adjust(r["home_price"], r["away_price"])[0]
        if _safe_float(r["home_price"]) and _safe_float(r["away_price"])
        else np.nan,
        axis=1,
    )
    return df


def _build_totals_df(df: pd.DataFrame) -> pd.DataFrame:
    """Add over_imp_prob column to a totals DataFrame."""
    if df.empty:
        return df
    df["over_imp_prob"] = df.apply(
        lambda r: _vig_adjust(r["over_price"], r["under_price"])[0]
        if _safe_float(r["over_price"]) and _safe_float(r["under_price"])
        else np.nan,
        axis=1,
    )
    return df


@st.cache_data(ttl=300)
def load_totals_latest(event_id: str | None, home_team: str, away_team: str, date_str: str, game_datetime_utc: str | None = None) -> pd.DataFrame:
    """Most recent pre-game totals snapshot per bookmaker."""
    gf = _game_filter(event_id, home_team, away_team, date_str)
    time_filter = f"AND ingestion_ts < '{game_datetime_utc}'" if game_datetime_utc else "AND ingestion_ts < commence_time"
    sql = f"""
    SELECT
        bookmaker_key,
        ingestion_ts,
        commence_time,
        MAX(CASE WHEN outcome_name = 'Over'  THEN outcome_price_american END) AS over_price,
        MAX(CASE WHEN outcome_name = 'Under' THEN outcome_price_american END) AS under_price,
        MAX(outcome_point) AS total_line
    FROM baseball_data.betting.mart_odds_outcomes
    WHERE {gf}
      AND market_key = 'totals'
      AND ingestion_ts = (
          SELECT MAX(ingestion_ts) FROM baseball_data.betting.mart_odds_outcomes
          WHERE {gf}
            AND market_key = 'totals'
            {time_filter}
      )
    GROUP BY bookmaker_key, ingestion_ts, commence_time
    """
    df = run_query(sql)
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    return _build_totals_df(df)


@st.cache_data(ttl=300)
def load_totals_current(event_id: str | None, home_team: str, away_team: str, date_str: str) -> pd.DataFrame:
    """Absolute latest totals snapshot per bookmaker (no time filter — may be in-game)."""
    gf = _game_filter(event_id, home_team, away_team, date_str)
    sql = f"""
    SELECT
        bookmaker_key,
        ingestion_ts,
        commence_time,
        MAX(CASE WHEN outcome_name = 'Over'  THEN outcome_price_american END) AS over_price,
        MAX(CASE WHEN outcome_name = 'Under' THEN outcome_price_american END) AS under_price,
        MAX(outcome_point) AS total_line
    FROM baseball_data.betting.mart_odds_outcomes
    WHERE {gf}
      AND market_key = 'totals'
      AND ingestion_ts = (
          SELECT MAX(ingestion_ts) FROM baseball_data.betting.mart_odds_outcomes
          WHERE {gf}
      )
    GROUP BY bookmaker_key, ingestion_ts, commence_time
    """
    df = run_query(sql)
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    return _build_totals_df(df)


def _build_books_df(df: pd.DataFrame) -> pd.DataFrame:
    """Add vig-adjusted probability columns and sort by home_imp_prob."""
    if df.empty:
        return df
    vig_cols = df.apply(
        lambda r: pd.Series(
            _vig_adjust(r["home_price_american"], r["away_price_american"]),
            index=["home_imp_prob", "away_imp_prob", "vig"],
        )
        if _safe_float(r["home_price_american"]) and _safe_float(r["away_price_american"])
        else pd.Series({"home_imp_prob": np.nan, "away_imp_prob": np.nan, "vig": np.nan}),
        axis=1,
    )
    return pd.concat([df, vig_cols], axis=1).sort_values("home_imp_prob", ascending=False)


@st.cache_data(ttl=300)
def load_books_latest(event_id: str | None, home_team: str, away_team: str, date_str: str, game_datetime_utc: str | None = None) -> pd.DataFrame:
    """Most recent pre-game h2h snapshot per bookmaker."""
    gf = _game_filter(event_id, home_team, away_team, date_str)
    time_filter = f"AND ingestion_ts < '{game_datetime_utc}'" if game_datetime_utc else "AND ingestion_ts < commence_time"
    sql = f"""
    SELECT
        bookmaker_key,
        ingestion_ts,
        commence_time,
        MAX(CASE WHEN is_home_outcome THEN outcome_price_american END) AS home_price_american,
        MAX(CASE WHEN is_away_outcome THEN outcome_price_american END) AS away_price_american
    FROM baseball_data.betting.mart_odds_outcomes
    WHERE {gf}
      AND market_key = 'h2h'
      AND ingestion_ts = (
          SELECT MAX(ingestion_ts) FROM baseball_data.betting.mart_odds_outcomes
          WHERE {gf}
            AND market_key = 'h2h'
            {time_filter}
      )
    GROUP BY bookmaker_key, ingestion_ts, commence_time
    """
    df = run_query(sql)
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    return _build_books_df(df)


@st.cache_data(ttl=300)
def load_books_current(event_id: str | None, home_team: str, away_team: str, date_str: str) -> pd.DataFrame:
    """Absolute latest h2h snapshot per bookmaker (no time filter — may be in-game)."""
    gf = _game_filter(event_id, home_team, away_team, date_str)
    sql = f"""
    SELECT
        bookmaker_key,
        ingestion_ts,
        commence_time,
        MAX(CASE WHEN is_home_outcome THEN outcome_price_american END) AS home_price_american,
        MAX(CASE WHEN is_away_outcome THEN outcome_price_american END) AS away_price_american
    FROM baseball_data.betting.mart_odds_outcomes
    WHERE {gf}
      AND market_key = 'h2h'
      AND ingestion_ts = (
          SELECT MAX(ingestion_ts) FROM baseball_data.betting.mart_odds_outcomes
          WHERE {gf}
      )
    GROUP BY bookmaker_key, ingestion_ts, commence_time
    """
    df = run_query(sql)
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    return _build_books_df(df)


# ---------------------------------------------------------------------------
# Header + date selector
# ---------------------------------------------------------------------------

st.title("Market Comparison")
st.caption("Model probability vs. bookmaker implied probability with line movement context.")

if "selected_date" not in st.session_state:
    st.session_state["selected_date"] = datetime.date.today()
selected_date = st.date_input("Date", value=st.session_state["selected_date"])
st.session_state["selected_date"] = selected_date
date_str = selected_date.isoformat()

# ---------------------------------------------------------------------------
# Game selector
# ---------------------------------------------------------------------------

df_games = load_games(date_str)

if df_games.empty:
    st.info(
        f"No games with model predictions and odds data found for **{selected_date.strftime('%B %d, %Y')}**. "
        "Try a different date or run predictions first."
    )
    st.stop()

st.caption(f"Showing {len(df_games)} game(s) for **{selected_date.strftime('%B %d, %Y')}**")

game_options: list[str] = []
game_rows: dict[str, pd.Series] = {}

for _, row in df_games.iterrows():
    dh = str(row.get("double_header", "N") or "N").upper()
    gn = row.get("game_number")
    dh_suffix = f" (Game {gn})" if dh != "N" and gn else ""
    label = f"{row['away_team_name']} @ {row['home_team_name']} — {_fmt_game_time(row['game_datetime'])}{dh_suffix}"
    # Deduplicate labels in the unlikely case two games share identical display text
    if label in game_rows:
        label = f"{label} [PK {row['game_pk']}]"
    game_options.append(label)
    game_rows[label] = row

selected_label = st.selectbox("Select game", options=game_options)
selected_row = game_rows[selected_label]
selected_game_pk = int(selected_row["game_pk"])
home_team = str(selected_row["home_team_name"])
away_team = str(selected_row["away_team_name"])

# Derive game start time from daily_model_predictions (more reliable than the
# commence_time column in mart_odds_outcomes, which may reflect local time).
_commence_ts = None
_game_datetime_utc: str | None = None
_gdt_raw = selected_row.get("game_datetime")
if _gdt_raw is not None:
    _commence_ts = pd.Timestamp(_gdt_raw)
    if pd.isna(_commence_ts):
        _commence_ts = None
    else:
        if _commence_ts.tzinfo is None:
            _commence_ts = _commence_ts.tz_localize("UTC")
        _game_datetime_utc = _commence_ts.strftime("%Y-%m-%d %H:%M:%S")

# Extract event_id — scopes all mart_odds_outcomes queries to this specific game,
# preventing cross-series collisions when the same teams play multiple series.
event_id: str | None = selected_row.get("event_id") or None

# ---------------------------------------------------------------------------
# Load bookmaker data and build bookmaker selector
# ---------------------------------------------------------------------------

df_books = load_books_latest(event_id, home_team, away_team, date_str, _game_datetime_utc)
df_books_current = load_books_current(event_id, home_team, away_team, date_str)
df_mv = load_line_movement(event_id, home_team, away_team, date_str)

# Count pre-game snapshots only (for the sidebar and threshold warnings)
if not df_mv.empty and _commence_ts is not None:
    _df_pre = df_mv[pd.to_datetime(df_mv["ingestion_ts"], utc=True) < _commence_ts]
    snap_count = _df_pre["ingestion_ts"].nunique()
else:
    snap_count = df_mv["ingestion_ts"].nunique() if not df_mv.empty else 0

available_books = sorted(df_books["bookmaker_key"].dropna().unique().tolist()) if not df_books.empty else []
book_options = ["— All bookmakers —"] + available_books
selected_book_label = st.selectbox(
    "Focus on a bookmaker (optional)",
    options=book_options,
    help="Select a specific bookmaker to compare its lines directly against model predictions.",
)
selected_book = None if selected_book_label == "— All bookmakers —" else selected_book_label

# ---------------------------------------------------------------------------
# Sidebar context
# ---------------------------------------------------------------------------

bk_count = _safe_float(selected_row.get("market_bookmaker_count"))

with st.sidebar:
    st.subheader("Selected Game")
    st.write(f"**Date:** {selected_date.strftime('%B %d, %Y')}")
    st.write(f"**{away_team} @ {home_team}**")
    st.write(f"**Game PK:** {selected_game_pk}")
    if bk_count is not None:
        st.write(f"**Bookmakers (h2h):** {int(bk_count)}")
    else:
        st.write(f"**Bookmakers (h2h):** {len(available_books) or '—'}")
    st.write(f"**Ingestion snapshots:** {snap_count}")
    st.caption(
        f"This game has {snap_count} pre-game snapshot(s). "
        "The line movement chart shows all snapshots with a marker at game start time."
    )

# ---------------------------------------------------------------------------
# Bookmaker vs. Model comparison card (when a book is selected)
# ---------------------------------------------------------------------------

if selected_book:
    # Resolve pre-game and current snapshots for the selected book
    _bk_pre_row = df_books[df_books["bookmaker_key"] == selected_book] if not df_books.empty else pd.DataFrame()
    _bk_cur_row = df_books_current[df_books_current["bookmaker_key"] == selected_book] if not df_books_current.empty else pd.DataFrame()

    # Determine whether the current snapshot is post-game
    _cur_ts = None
    _cur_is_postgame = False
    if not _bk_cur_row.empty and "ingestion_ts" in _bk_cur_row.columns:
        _cur_ts_raw = _bk_cur_row.iloc[0].get("ingestion_ts")
        if _cur_ts_raw is not None:
            _cur_ts = pd.Timestamp(_cur_ts_raw)
            if _cur_ts.tzinfo is None:
                _cur_ts = _cur_ts.tz_localize("UTC")
            if _commence_ts is not None and _cur_ts > _commence_ts:
                _cur_is_postgame = True

    # Determine whether pre-game and current are different snapshots
    _pre_ts = None
    if not _bk_pre_row.empty and "ingestion_ts" in _bk_pre_row.columns:
        _pre_ts_raw = _bk_pre_row.iloc[0].get("ingestion_ts")
        if _pre_ts_raw is not None:
            _pre_ts = pd.Timestamp(_pre_ts_raw)
            if _pre_ts.tzinfo is None:
                _pre_ts = _pre_ts.tz_localize("UTC")

    _has_both_snapshots = _cur_is_postgame and _pre_ts is not None and _pre_ts != _cur_ts

    # Use pre-game row for model comparison metrics; fall back to current if no pre-game
    _bk_display = _bk_pre_row if not _bk_pre_row.empty else _bk_cur_row

    if not _bk_display.empty:
        bk = _bk_display.iloc[0]
        bk_home_imp = _safe_float(bk.get("home_imp_prob"))
        bk_home_price = _safe_float(bk.get("home_price_american"))
        bk_away_price = _safe_float(bk.get("away_price_american"))
        model_prob = _safe_float(selected_row.get("consensus_win_prob"))
        consensus_mkt = _safe_float(selected_row.get("h2h_market_implied_prob"))

        st.subheader(f"📊 {selected_book} vs. Model — Moneyline")

        # Pre-game line
        pre_label = f"Pre-Game Line ({_fmt_ts(_pre_ts)})" if _pre_ts else f"{selected_book} Pre-Game Line"
        if not _bk_pre_row.empty:
            st.markdown(
                f"**{pre_label}:** &nbsp;"
                f"{home_team} `{_fmt_american(bk_home_price)}` &nbsp;|&nbsp; "
                f"{away_team} `{_fmt_american(bk_away_price)}`"
            )
        else:
            st.caption("No pre-game snapshot available for this bookmaker.")

        # Current (in-game) line when different from pre-game
        if _has_both_snapshots and not _bk_cur_row.empty:
            cur_bk = _bk_cur_row.iloc[0]
            cur_home_price = _safe_float(cur_bk.get("home_price_american"))
            cur_away_price = _safe_float(cur_bk.get("away_price_american"))
            st.warning(
                f"**Live line captured after game start ({_fmt_ts(_cur_ts)})** — "
                "these odds reflect in-game scoring, not pre-game betting consensus. "
                f"They are shown for reference only.  \n"
                f"{home_team} `{_fmt_american(cur_home_price)}` &nbsp;|&nbsp; "
                f"{away_team} `{_fmt_american(cur_away_price)}`",
                icon="⚠️",
            )

        col_bk1, col_bk2, col_bk3 = st.columns(3)
        with col_bk1:
            val = f"{bk_home_imp:.1%}" if bk_home_imp is not None else "—"
            delta = model_prob - bk_home_imp if (model_prob is not None and bk_home_imp is not None) else None
            st.metric(
                f"{selected_book} Pre-Game Implied (Home)",
                val,
                delta=f"{delta:+.3f} model edge" if delta is not None else None,
                delta_color="normal",
                help="Vig-adjusted implied probability from the last pre-game snapshot.",
            )
        with col_bk2:
            st.metric(
                "Model Win% (Home)",
                f"{model_prob:.1%}" if model_prob is not None else "—",
                help="50% NGBoost run-differential + 50% XGBoost classifier.",
            )
        with col_bk3:
            st.metric(
                "All-Book Consensus (Home)",
                f"{consensus_mkt:.1%}" if consensus_mkt is not None else "—",
                help="Vig-adjusted average across all available bookmakers.",
            )

        st.subheader(f"📊 {selected_book} vs. Model — Totals")

        # Totals comparison for selected book
        df_totals_pre = load_totals_latest(event_id, home_team, away_team, date_str, _game_datetime_utc)
        df_totals_cur = load_totals_current(event_id, home_team, away_team, date_str)

        _tot_pre = df_totals_pre[df_totals_pre["bookmaker_key"] == selected_book] if not df_totals_pre.empty else pd.DataFrame()
        _tot_cur = df_totals_cur[df_totals_cur["bookmaker_key"] == selected_book] if not df_totals_cur.empty else pd.DataFrame()

        # Check if totals current snapshot is post-game
        _tot_cur_is_postgame = False
        _tot_cur_ts = None
        if not _tot_cur.empty and "ingestion_ts" in _tot_cur.columns:
            _tot_cur_ts_raw = _tot_cur.iloc[0].get("ingestion_ts")
            if _tot_cur_ts_raw:
                _tot_cur_ts = pd.Timestamp(_tot_cur_ts_raw)
                if _tot_cur_ts.tzinfo is None:
                    _tot_cur_ts = _tot_cur_ts.tz_localize("UTC")
                if _commence_ts and _tot_cur_ts > _commence_ts:
                    _tot_cur_is_postgame = True

        _tot_pre_ts = None
        if not _tot_pre.empty and "ingestion_ts" in _tot_pre.columns:
            _tot_pre_ts_raw = _tot_pre.iloc[0].get("ingestion_ts")
            if _tot_pre_ts_raw:
                _tot_pre_ts = pd.Timestamp(_tot_pre_ts_raw)
                if _tot_pre_ts.tzinfo is None:
                    _tot_pre_ts = _tot_pre_ts.tz_localize("UTC")

        _tot_has_both = _tot_cur_is_postgame and _tot_pre_ts is not None and _tot_pre_ts != _tot_cur_ts

        _tot_display = _tot_pre if not _tot_pre.empty else _tot_cur
        if not _tot_display.empty:
            t = _tot_display.iloc[0]
            bk_over_imp = _safe_float(t.get("over_imp_prob"))
            bk_over_price = _safe_float(t.get("over_price"))
            bk_under_price = _safe_float(t.get("under_price"))
            bk_line = _safe_float(t.get("total_line"))
            model_over = _safe_float(selected_row.get("p_over_ngboost"))
            mkt_over = _safe_float(selected_row.get("over_prob_consensus"))

            tot_pre_label = f"Pre-Game Totals ({_fmt_ts(_tot_pre_ts)})" if _tot_pre_ts else f"{selected_book} Pre-Game Totals"
            if bk_line is not None:
                st.markdown(
                    f"**{tot_pre_label}:** &nbsp;"
                    f"O/U `{bk_line:.1f}` &nbsp;|&nbsp; "
                    f"Over `{_fmt_american(bk_over_price)}` &nbsp;|&nbsp; "
                    f"Under `{_fmt_american(bk_under_price)}`"
                )

            if _tot_has_both and not _tot_cur.empty:
                tc = _tot_cur.iloc[0]
                cur_line = _safe_float(tc.get("total_line"))
                cur_over = _safe_float(tc.get("over_price"))
                cur_under = _safe_float(tc.get("under_price"))
                if cur_line is not None:
                    st.warning(
                        f"**Live totals captured after game start ({_fmt_ts(_tot_cur_ts)})** — "
                        "this line reflects in-game scoring and is shown for reference only.  \n"
                        f"O/U `{cur_line:.1f}` &nbsp;|&nbsp; "
                        f"Over `{_fmt_american(cur_over)}` &nbsp;|&nbsp; "
                        f"Under `{_fmt_american(cur_under)}`",
                        icon="⚠️",
                    )

            col_ot1, col_ot2, col_ot3 = st.columns(3)
            with col_ot1:
                over_delta = (model_over - bk_over_imp) if (model_over and bk_over_imp) else None
                st.metric(
                    f"{selected_book} Over Implied (Pre-Game)",
                    f"{bk_over_imp:.1%}" if bk_over_imp is not None else "—",
                    delta=f"{over_delta:+.3f} model edge" if over_delta is not None else None,
                    delta_color="normal",
                    help="Vig-adjusted over probability from the last pre-game totals snapshot.",
                )
            with col_ot2:
                st.metric(
                    "Model Over%",
                    f"{model_over:.1%}" if model_over is not None else "—",
                    help="NGBoost P(total runs > consensus O/U line).",
                )
            with col_ot3:
                st.metric(
                    "All-Book Over Consensus",
                    f"{mkt_over:.1%}" if mkt_over is not None else "—",
                    help="Vig-adjusted over probability averaged across all bookmakers.",
                )

        st.divider()

# ---------------------------------------------------------------------------
# Moneyline panel
# ---------------------------------------------------------------------------

st.header("Moneyline")

model_prob = _safe_float(selected_row.get("consensus_win_prob"))
market_prob = _safe_float(selected_row.get("h2h_market_implied_prob"))

col_model, col_market = st.columns(2)

with col_model:
    st.metric(
        "Model Win% (Home)",
        f"{model_prob:.1%}" if model_prob is not None else "—",
        help="50% NGBoost run-differential + 50% XGBoost classifier.",
    )

with col_market:
    if market_prob is not None and model_prob is not None:
        delta_val = model_prob - market_prob
        st.metric(
            "Market Consensus Win% (Home)",
            f"{market_prob:.1%}",
            delta=f"{delta_val:+.3f}",
            delta_color="normal",
            help="Vig-adjusted average across all bookmakers. Positive delta = model favors home more than market.",
        )
    else:
        st.metric(
            "Market Consensus Win% (Home)",
            f"{market_prob:.1%}" if market_prob is not None else "—",
        )

# Line movement chart
st.subheader("Line Movement")

if df_mv.empty or df_mv["home_imp_prob"].isna().all():
    st.info("No odds snapshots found for this game. Snapshots are collected throughout the day — check back later.")
elif snap_count == 0:
    st.info(
        "No pre-game snapshots found — all available odds were ingested after the game started. "
        "These in-game lines reflect live scoring and are not meaningful for pre-game analysis."
    )
else:
    df_mv_clean = df_mv.dropna(subset=["home_imp_prob"])

    if selected_book:
        df_mv_plot = df_mv_clean[df_mv_clean["bookmaker_key"] == selected_book]
    else:
        df_mv_plot = df_mv_clean

    df_pivot = df_mv_plot.pivot_table(
        index="ingestion_ts", columns="bookmaker_key", values="home_imp_prob"
    )
    df_pivot.index = pd.to_datetime(df_pivot.index, utc=True)
    df_pivot.columns = [str(c) for c in df_pivot.columns]

    # Y-axis bounds: when a book is focused, show full range including post-game moves
    # (the dramatic swing IS the story). When all books shown, zoom to pre-game range
    # so small pre-game differences remain readable.
    if selected_book:
        all_vals = df_mv_plot["home_imp_prob"].dropna()
    else:
        _pre_rows = df_mv_clean[
            pd.to_datetime(df_mv_clean["ingestion_ts"], utc=True) < _commence_ts
        ] if _commence_ts is not None else df_mv_clean
        all_vals = _pre_rows["home_imp_prob"].dropna()
    y_min = max(0.0, all_vals.min() - 0.05) if not all_vals.empty else 0.3
    y_max = min(1.0, all_vals.max() + 0.05) if not all_vals.empty else 0.7

    consensus_val = _safe_float(selected_row.get("consensus_win_prob"))
    post_game_present = _commence_ts is not None and not df_pivot.empty and (
        df_pivot.index.max() > _commence_ts
    )

    fig = go.Figure()
    for col in df_pivot.columns:
        fig.add_trace(go.Scatter(
            x=df_pivot.index,
            y=df_pivot[col],
            mode="lines+markers",
            name=col,
            line=dict(width=1.5),
        ))
    if consensus_val is not None:
        fig.add_hline(
            y=consensus_val,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Model {consensus_val:.1%}",
            annotation_position="bottom right",
        )
    if _commence_ts is not None:
        # add_vline with annotation errors in this plotly version when the x-axis
        # contains timezone-aware datetimes. Use add_shape + add_annotation instead.
        _vline_x = _commence_ts.strftime("%Y-%m-%dT%H:%M:%S")
        fig.add_shape(
            type="line",
            x0=_vline_x, x1=_vline_x,
            y0=0, y1=1, yref="paper",
            line=dict(dash="dot", color="gray", width=2),
        )
        fig.add_annotation(
            x=_vline_x, y=1, yref="paper",
            text="Game Start",
            showarrow=False,
            font=dict(color="gray", size=11),
            xanchor="left", yanchor="top",
        )
    fig.update_layout(
        xaxis_title="Snapshot Time",
        yaxis_title="Home Win Implied Probability",
        yaxis=dict(tickformat=".0%", range=[y_min, y_max]),
        legend_title="Bookmaker",
        height=380,
        margin=dict(l=0, r=0, t=30, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)
    caption_parts = [f"{snap_count} pre-game ingestion snapshots. Dashed red line = model consensus."]
    if post_game_present:
        caption_parts.append("Dotted gray line = game start. Odds to the right of that line were captured after the game began and should be interpreted with caution.")
    else:
        caption_parts.append("Dotted gray line marks scheduled game start time.")
    st.caption(" ".join(caption_parts))

# ---------------------------------------------------------------------------
# Totals panel
# ---------------------------------------------------------------------------

st.header("Totals")

pred_total = _safe_float(selected_row.get("pred_total_runs"))
total_line = _safe_float(selected_row.get("total_line_consensus"))

# Pre-game and current totals snapshots (all bookmakers)
df_totals_pre = load_totals_latest(event_id, home_team, away_team, date_str, _game_datetime_utc)
df_totals_cur = load_totals_current(event_id, home_team, away_team, date_str)

# Detect whether the latest totals snapshot is post-game
_totals_cur_ts = None
_totals_cur_is_postgame = False
if not df_totals_cur.empty and "ingestion_ts" in df_totals_cur.columns:
    _tc_raw = df_totals_cur["ingestion_ts"].dropna()
    if not _tc_raw.empty:
        _totals_cur_ts = pd.Timestamp(_tc_raw.iloc[0])
        if _totals_cur_ts.tzinfo is None:
            _totals_cur_ts = _totals_cur_ts.tz_localize("UTC")
        if _commence_ts and _totals_cur_ts > _commence_ts:
            _totals_cur_is_postgame = True

_totals_pre_ts = None
if not df_totals_pre.empty and "ingestion_ts" in df_totals_pre.columns:
    _tp_raw = df_totals_pre["ingestion_ts"].dropna()
    if not _tp_raw.empty:
        _totals_pre_ts = pd.Timestamp(_tp_raw.iloc[0])
        if _totals_pre_ts.tzinfo is None:
            _totals_pre_ts = _totals_pre_ts.tz_localize("UTC")

_totals_has_both = _totals_cur_is_postgame and _totals_pre_ts is not None and _totals_pre_ts != _totals_cur_ts

# Use pre-game data for the consensus line comparison; fall back to current if no pre-game
df_totals_all = df_totals_pre if not df_totals_pre.empty else df_totals_cur

# Selected book's pre-game O/U line (for 3-column layout)
book_total_line: float | None = None
if selected_book and not df_totals_all.empty:
    _bk_tot = df_totals_all[df_totals_all["bookmaker_key"] == selected_book]
    if not _bk_tot.empty:
        book_total_line = _safe_float(_bk_tot.iloc[0].get("total_line"))

# Pre-game vs. current O/U totals info line (shown above the metrics)
if _totals_has_both:
    _pre_ou = df_totals_pre["total_line"].dropna().mode()
    _cur_ou = df_totals_cur["total_line"].dropna().mode()
    _pre_ou_str = f"{_pre_ou.iloc[0]:.1f}" if not _pre_ou.empty else "—"
    _cur_ou_str = f"{_cur_ou.iloc[0]:.1f}" if not _cur_ou.empty else "—"
    st.info(
        f"Pre-game consensus O/U: **{_pre_ou_str}** ({_fmt_ts(_totals_pre_ts)}) — "
        f"Current O/U: **{_cur_ou_str}** ({_fmt_ts(_totals_cur_ts)}, after game start). "
        "Metrics below use the pre-game snapshot."
    )

if selected_book and book_total_line is not None:
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        st.metric(
            "Market O/U Line (Pre-Game)",
            f"{total_line:.1f} runs" if total_line is not None else "—",
            help="Consensus over/under line averaged across all bookmakers (pre-game snapshot).",
        )
    with col_t2:
        book_line_delta = (book_total_line - total_line) if total_line is not None else None
        st.metric(
            f"{selected_book} O/U Line (Pre-Game)",
            f"{book_total_line:.1f} runs",
            delta=f"{book_line_delta:+.1f} vs. consensus" if book_line_delta is not None else None,
            delta_color="off",
            help="This bookmaker's pre-game over/under line. Delta shows deviation from market consensus.",
        )
    with col_t3:
        ref_line = book_total_line
        if pred_total is not None:
            run_delta = pred_total - ref_line
            st.metric(
                "Model Predicted Total",
                f"{pred_total:.1f} runs",
                delta=f"{run_delta:+.1f} vs. {selected_book} line",
                delta_color="normal",
                help="NGBoost predicted mean total runs.",
            )
        else:
            st.metric("Model Predicted Total", "—", help="NGBoost predicted mean total runs.")
else:
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.metric(
            "Market O/U Line (Pre-Game)",
            f"{total_line:.1f} runs" if total_line is not None else "—",
            help="Consensus over/under line averaged across all bookmakers (pre-game snapshot).",
        )
    with col_t2:
        if pred_total is not None and total_line is not None:
            run_delta = pred_total - total_line
            st.metric(
                "Model Predicted Total",
                f"{pred_total:.1f} runs",
                delta=f"{run_delta:+.1f} vs. line",
                delta_color="normal",
                help="NGBoost predicted mean total runs. Positive delta = model expects more runs than the market line.",
            )
        else:
            st.metric(
                "Model Predicted Total",
                f"{pred_total:.1f} runs" if pred_total is not None else "—",
                help="NGBoost predicted mean total runs.",
            )

# Over probability chart (separate from the run count metrics above)
if not df_totals_all.empty and not df_totals_all["over_imp_prob"].isna().all():
    p_over_model = _safe_float(selected_row.get("p_over_ngboost"))
    df_chart = df_totals_all[["bookmaker_key", "over_imp_prob"]].dropna().copy()

    if selected_book:
        df_chart = df_chart[df_chart["bookmaker_key"] == selected_book]

    # Put model first so it reads left-to-right: model → bookmakers
    if p_over_model is not None:
        model_row = pd.DataFrame([{"bookmaker_key": "model", "over_imp_prob": p_over_model}])
        df_chart = pd.concat([model_row, df_chart], ignore_index=True)

    if not df_chart.empty:
        st.caption("**Over probability** — model vs. bookmakers (vig-adjusted, most recent pre-game snapshot)")
        _bar_colors = [
            "#FF7F0E" if bk == "model" else "#1f77b4"
            for bk in df_chart["bookmaker_key"]
        ]
        _fig_totals = go.Figure(go.Bar(
            x=df_chart["bookmaker_key"],
            y=df_chart["over_imp_prob"],
            marker_color=_bar_colors,
            text=[f"{v:.1%}" for v in df_chart["over_imp_prob"]],
            textposition="outside",
        ))
        _fig_totals.update_layout(
            yaxis=dict(tickformat=".0%", range=[0, min(1.0, df_chart["over_imp_prob"].max() + 0.1)]),
            xaxis_title=None,
            yaxis_title="Over Probability",
            height=320,
            margin=dict(l=0, r=0, t=10, b=0),
            showlegend=False,
        )
        st.plotly_chart(_fig_totals, use_container_width=True)
        st.caption("Orange bar = model prediction. Blue bars = bookmakers.")
else:
    st.info("No totals odds data for this game.")

# ---------------------------------------------------------------------------
# Sharp vs. Soft panel (conditional)
# ---------------------------------------------------------------------------

sharp_prob = _safe_float(selected_row.get("home_win_prob_sharp"))
soft_prob = _safe_float(selected_row.get("home_win_prob_soft"))
sharp_soft_delta = _safe_float(selected_row.get("sharp_soft_ml_delta"))

if sharp_prob is not None and soft_prob is not None:
    st.header("Sharp vs. Soft Books")

    with st.expander("What are sharp and soft books?", expanded=False):
        st.markdown("""
**Sharp books** cater to professional and high-volume bettors. They accept large wagers, adjust their lines
quickly in response to bets, and are generally considered the most accurate market signal. In this model,
sharp books are: **lowvig**, **betonlineag**, and **bovada**.

**Soft books** target recreational bettors. They tend to offer slightly worse odds, move lines more slowly,
and are more influenced by public betting trends than sharp money. Soft books here are:
**DraftKings**, **FanDuel**, **BetMGM**, **WilliamHill (US)**, and **BetRivers**.

**Why this matters:** When sharp books disagree significantly with soft books on a team's win probability,
it can indicate that professional bettors have a different view than the general public — a signal sometimes
called "sharp money." A large positive delta (sharp − soft) means sharp books favor the home team more than
soft books do, which can be interpreted as a buy signal on the home side.
        """)

    st.metric(
        label="Sharp–Soft Home Win% Delta",
        value=f"{sharp_soft_delta:+.3f}" if sharp_soft_delta is not None else "—",
        help=(
            "Sharp book average minus soft book average for home win probability. "
            "Positive = sharps favor home more than softs."
        ),
    )

    col_sh, col_so = st.columns(2)
    with col_sh:
        st.metric(
            "Sharp Books — Home Win%",
            f"{sharp_prob:.1%}",
            help="lowvig, betonlineag, bovada (vig-adjusted average)",
        )
    with col_so:
        st.metric(
            "Soft Books — Home Win%",
            f"{soft_prob:.1%}",
            help="DraftKings, FanDuel, BetMGM, WilliamHill US, BetRivers (vig-adjusted average)",
        )

# ---------------------------------------------------------------------------
# Cross-bookmaker table
# ---------------------------------------------------------------------------

st.header("All Bookmakers")

if df_books.empty:
    st.info("No bookmaker data available for the most recent snapshot.")
else:
    # Drop duplicate bookmaker rows (can occur when commence_time varies across rows)
    df_display = (
        df_books
        .drop_duplicates(subset=["bookmaker_key"])
        .drop(columns=["ingestion_ts", "commence_time"], errors="ignore")
        .copy()
    )
    df_display["home_imp_prob"] = df_display["home_imp_prob"].apply(_fmt_pct)
    df_display["away_imp_prob"] = df_display["away_imp_prob"].apply(_fmt_pct)
    df_display["vig"] = df_display["vig"].apply(
        lambda v: f"{v:.3f}" if _safe_float(v) is not None else "—"
    )
    st.dataframe(
        df_display,
        use_container_width=True,
        column_config={
            "bookmaker_key": st.column_config.TextColumn("Bookmaker"),
            "home_price_american": st.column_config.NumberColumn("Home ML", format="%d"),
            "away_price_american": st.column_config.NumberColumn("Away ML", format="%d"),
            "home_imp_prob": st.column_config.TextColumn("Home Imp%"),
            "away_imp_prob": st.column_config.TextColumn("Away Imp%"),
            "vig": st.column_config.TextColumn(
                "Vig",
                help=(
                    "Vig (vigorish) is the bookmaker's built-in margin. "
                    "It's the amount by which home + away implied probabilities sum above 1.0. "
                    "A vig of 0.050 means the book keeps ~5% of each dollar wagered in the long run. "
                    "Lower vig = better value for the bettor. Sharp books typically run 0.01–0.03; "
                    "recreational books often run 0.04–0.07 or higher."
                ),
            ),
        },
        hide_index=True,
    )

