"""EV Tracker & Kelly Sizer page — all markets, all games, for the selected date."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from app.utils.db import run_query

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

_PICKS_SQL = """
SELECT
    p.*,
    COALESCE(l.both_confirmed, FALSE) AS both_confirmed
FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY inserted_at DESC) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions
    WHERE score_date = '{date}'
) p
LEFT JOIN (
    SELECT
        game_pk,
        COUNT(DISTINCT home_away) = 2 AS both_confirmed
    FROM baseball_data.betting.stg_statsapi_lineups_wide
    WHERE official_date = '{date}'
    GROUP BY game_pk
) l ON p.game_pk = l.game_pk
WHERE p._rn = 1
ORDER BY p.home_team ASC
"""

# ---------------------------------------------------------------------------
# Data loading and market expansion
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading EV data...")
def load_ev_data(date_str: str) -> pd.DataFrame:
    df = run_query(_PICKS_SQL.format(date=date_str))
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]

    rows = []
    for _, r in df.iterrows():
        game_pk = r.get("game_pk")
        home = r.get("home_team", "")
        away = r.get("away_team", "")
        matchup = f"{away} @ {home}"
        both_confirmed = bool(r.get("both_confirmed", False))

        consensus_win_prob = _safe_float(r.get("consensus_win_prob"))
        home_mkt_prob = _safe_float(r.get("h2h_market_implied_prob"))
        over_mkt_prob = _safe_float(r.get("over_prob_consensus"))
        p_over = _safe_float(r.get("p_over_ngboost"))

        market_defs = [
            ("h2h home", consensus_win_prob, home_mkt_prob),
            ("h2h away",
             (1.0 - consensus_win_prob) if consensus_win_prob is not None else None,
             (1.0 - home_mkt_prob) if home_mkt_prob is not None else None),
            ("over", p_over, over_mkt_prob),
            ("under",
             (1.0 - p_over) if p_over is not None else None,
             (1.0 - over_mkt_prob) if over_mkt_prob is not None else None),
        ]

        for market_name, model_prob, market_prob in market_defs:
            if model_prob is None or market_prob is None:
                continue
            if market_prob <= 0 or market_prob >= 1:
                continue

            decimal_odds = 1.0 / market_prob
            edge = model_prob - market_prob
            ev = (model_prob * (decimal_odds - 1)) - (1 - model_prob)
            if decimal_odds > 1:
                kelly_raw = ev / (decimal_odds - 1)
            else:
                kelly_raw = 0.0
            kelly_capped = min(max(kelly_raw, 0.0), 0.10)
            kelly_exceeded_cap = kelly_raw > 0.10

            actionable = (
                ev > 0
                and abs(edge) > 0.03
                and both_confirmed
                and model_prob is not None
            )

            rows.append({
                "game_pk": game_pk,
                "matchup": matchup,
                "market": market_name,
                "model_prob": model_prob,
                "market_prob": market_prob,
                "decimal_odds": decimal_odds,
                "edge": edge,
                "ev": ev,
                "kelly_raw": kelly_raw,
                "kelly_capped": kelly_capped,
                "kelly_exceeded_cap": kelly_exceeded_cap,
                "both_confirmed": both_confirmed,
                "actionable": actionable,
            })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="EV Tracker & Kelly Sizer — Baseball Betting Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

st.title("EV Tracker & Kelly Sizer")
st.caption(
    "Expected value and bet sizing for all markets on the selected date. "
    "Kelly fractions capped at 10% of bankroll."
)

if "selected_date" not in st.session_state:
    st.session_state["selected_date"] = datetime.date.today()
selected_date = st.date_input("Select date", value=st.session_state["selected_date"])
st.session_state["selected_date"] = selected_date
date_str = selected_date.isoformat()

with st.sidebar:
    bankroll_input = st.number_input(
        "Bankroll ($)", min_value=0.0, value=100.0, step=50.0, format="%.2f"
    )

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

df_ev = load_ev_data(date_str)

if df_ev.empty:
    st.info(
        f"No prediction data found for {selected_date}. "
        "Ensure predict_today.py has been run for this date and odds data is available."
    )
    with st.sidebar:
        st.subheader("Context")
        st.write(f"**Date:** {selected_date}")
        st.write("**Games loaded:** 0")
        st.write("**Actionable bets:** 0")
    st.stop()

# ---------------------------------------------------------------------------
# Doubleheader detection — build a display label per game_pk
# When the same matchup string appears under multiple game_pks, append
# "(G1)" / "(G2)" in game_pk sort order so rows are distinguishable.
# ---------------------------------------------------------------------------

def _build_game_labels(df: pd.DataFrame) -> dict:
    """Return {game_pk: display_matchup} with G1/G2 suffixes for doubleheaders."""
    # One row per game_pk → matchup mapping (game_pk is consistent within group)
    pk_to_matchup = df.drop_duplicates("game_pk")[["game_pk", "matchup"]].copy()
    # Count how many game_pks share each matchup string
    counts = pk_to_matchup.groupby("matchup")["game_pk"].transform("count")
    pk_to_matchup["is_double"] = counts > 1
    pk_to_matchup = pk_to_matchup.sort_values("game_pk")

    labels: dict = {}
    game_num: dict[str, int] = {}
    for _, row in pk_to_matchup.iterrows():
        pk = row["game_pk"]
        m = row["matchup"]
        if row["is_double"]:
            n = game_num.get(m, 0) + 1
            game_num[m] = n
            labels[pk] = f"{m} (G{n}, PK:{pk})"
        else:
            labels[pk] = m
    return labels

_game_labels = _build_game_labels(df_ev)
df_ev = df_ev.copy()
df_ev["matchup_label"] = df_ev["game_pk"].map(_game_labels)

# ---------------------------------------------------------------------------
# Warning banner — positive EV but lineup unconfirmed
# ---------------------------------------------------------------------------

pending_mask = (
    (df_ev["ev"] > 0)
    & (df_ev["edge"].abs() > 0.03)
    & (~df_ev["both_confirmed"])
    & df_ev["model_prob"].notna()
)
pending_rows = df_ev[pending_mask]

if not pending_rows.empty:
    pending_games = pending_rows["matchup_label"].unique().tolist()
    st.warning(
        "⚠ Lineup pending — the following games have positive EV "
        "but lineups are not yet confirmed. Do not act until lineups "
        "are confirmed:\n" + ", ".join(pending_games)
    )

# ---------------------------------------------------------------------------
# All Markets EV table
# ---------------------------------------------------------------------------

st.subheader("All Markets")

_ALL_MARKETS_HELP = {
    "Matchup": "Away team @ Home team. Doubleheaders show G1/G2 with the game_pk to distinguish games.",
    "Market": "h2h home = bet home to win | h2h away = bet away to win | over/under = totals market",
    "Model Prob": "Model-estimated probability for this side (blended NGBoost + XGBoost for h2h; NGBoost for totals)",
    "Mkt Impl Prob": "Probability implied by the consensus market odds (1 / decimal odds)",
    "Decimal Odds": "Decimal format odds: payout per $1 wagered including stake (e.g. 2.000 = even money)",
    "EV": "Expected value per $1 wagered. Formula: (model_prob × (decimal_odds − 1)) − (1 − model_prob). Positive = favorable long-run return.",
    "Raw Kelly%": (
        "Full Kelly criterion fraction before capping: EV / (decimal_odds − 1). "
        "This is the theoretically optimal bet size given the model edge, but can be very large — use Capped Kelly% for actual sizing."
    ),
    "Capped Kelly%": (
        "Kelly fraction hard-capped at 10% of bankroll. "
        "This is the column to use for sizing bets. "
        "If Raw Kelly% > 10% the cap is binding — the model sees a large edge but we limit exposure."
    ),
    "Actionable": (
        "True when ALL four conditions hold: "
        "(1) EV > 0, "
        "(2) |edge| > 3%, "
        "(3) both starting lineups confirmed, "
        "(4) model_prob is not null. "
        "False if any condition fails — do not bet rows marked False."
    ),
}

df_display = pd.DataFrame({
    "Matchup": df_ev["matchup_label"],
    "Market": df_ev["market"],
    "Model Prob": df_ev["model_prob"].map(lambda v: f"{v:.1%}" if v is not None else "—"),
    "Mkt Impl Prob": df_ev["market_prob"].map(lambda v: f"{v:.1%}" if v is not None else "—"),
    "Decimal Odds": df_ev["decimal_odds"].map(lambda v: f"{v:.3f}" if v is not None else "—"),
    "EV": df_ev["ev"].map(lambda v: f"{v:+.4f}" if v is not None else "—"),
    "Raw Kelly%": df_ev["kelly_raw"].map(lambda v: f"{v:.2%}" if v is not None else "—"),
    "Capped Kelly%": df_ev["kelly_capped"].map(lambda v: f"{v:.2%}" if v is not None else "—"),
    "Actionable": df_ev["actionable"],
})

st.dataframe(
    df_display,
    use_container_width=True,
    column_config={col: st.column_config.TextColumn(col, help=h) for col, h in _ALL_MARKETS_HELP.items()},
)

# ---------------------------------------------------------------------------
# Suggested Slate
# ---------------------------------------------------------------------------

st.subheader("Suggested Slate")

df_actionable = df_ev[df_ev["actionable"]].copy()

if df_actionable.empty:
    st.info(
        "No actionable bets for this date based on current odds, "
        "edge threshold (>3%), and lineup confirmation status."
    )
else:
    # Correlated-bet deduplication: when multiple markets for the same game_pk
    # are actionable, keep only the single highest-EV bet rather than flagging.
    df_actionable = df_actionable.copy()
    df_actionable["_ev_rank"] = (
        df_actionable.groupby("game_pk")["ev"]
        .rank(method="first", ascending=False)
    )
    # Capture what gets dropped before filtering, for the disclosure note
    df_dropped = df_actionable[df_actionable["_ev_rank"] > 1].copy()
    df_actionable = df_actionable[df_actionable["_ev_rank"] == 1].copy()

    stake = df_actionable["kelly_capped"] * bankroll_input
    to_win = stake * (df_actionable["decimal_odds"] - 1)
    ev_dollar = df_actionable["ev"] * stake

    def _decimal_to_american(dec: float) -> str:
        if dec >= 2.0:
            return f"+{round((dec - 1) * 100)}"
        else:
            return str(round(-100 / (dec - 1)))

    american_odds = df_actionable["decimal_odds"].map(_decimal_to_american)

    # Keep raw numeric columns alongside the formatted ones so we can
    # recompute metrics from whichever rows the user checks.
    df_slate = pd.DataFrame({
        "Include": True,
        "Bet": df_actionable["matchup_label"] + " — " + df_actionable["market"],
        "Odds": american_odds,
        "Stake ($)": stake.map(lambda v: f"{v:.2f}"),
        "To Win ($)": to_win.map(lambda v: f"{v:.2f}"),
        "EV ($)": ev_dollar.map(lambda v: f"{v:+.2f}"),
        "_stake_raw": stake.values,
        "_ev_raw": ev_dollar.values,
    })

    _slate_col_config = {
        "Include": st.column_config.CheckboxColumn(
            "Include",
            help="Check/uncheck to include or exclude this bet from the summary metrics below.",
            default=True,
        ),
        "Bet": st.column_config.TextColumn("Bet", help="Matchup and market side to wager on. One bet per game — the highest-EV market is kept when multiple markets qualify."),
        "Odds": st.column_config.TextColumn("Odds", help="Consensus market odds in American format (+150 = bet $100 to win $150; −150 = bet $150 to win $100). To Win is derived from these odds."),
        "Stake ($)": st.column_config.TextColumn("Stake ($)", help="Capped Kelly% × your bankroll. This is the suggested dollar amount to wager."),
        "To Win ($)": st.column_config.TextColumn("To Win ($)", help="Profit if the bet wins: Stake × (decimal_odds − 1)"),
        "EV ($)": st.column_config.TextColumn("EV ($)", help="Expected dollar profit per bet: EV × Stake. Positive = favorable in the long run."),
        "_stake_raw": st.column_config.Column("_stake_raw", disabled=True),
        "_ev_raw": st.column_config.Column("_ev_raw", disabled=True),
    }

    edited = st.data_editor(
        df_slate,
        use_container_width=True,
        column_config=_slate_col_config,
        column_order=["Include", "Bet", "Odds", "Stake ($)", "To Win ($)", "EV ($)"],
        hide_index=True,
        key="slate_editor",
    )

    # Disclosure: show which bets were dropped due to same-game deduplication
    if not df_dropped.empty:
        dropped_lines = [
            f"- {row['matchup_label']} — {row['market']} (EV {row['ev']:+.4f})"
            for _, row in df_dropped.iterrows()
        ]
        with st.expander(f"ℹ {len(df_dropped)} same-game bet(s) omitted — click to see"):
            st.markdown(
                "The following actionable bets were excluded because a higher-EV bet "
                "from the same game is already on the slate:\n\n" + "\n".join(dropped_lines)
            )

    # Metrics derive from whichever rows are checked
    selected = edited[edited["Include"]]
    total_stake = selected["_stake_raw"].sum()
    total_ev = selected["_ev_raw"].sum()
    n_bets = len(selected)
    expected_roi = total_ev / total_stake if total_stake > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Stake ($)", f"{total_stake:.2f}", help="Sum of bet sizes for all checked rows.")
    m2.metric(
        "Expected Profit ($)",
        f"{total_ev:+.2f}",
        help="Expected dollar profit across all checked bets, accounting for win probability. This is Total Stake × Expected ROI%.",
    )
    m3.metric(
        "Expected ROI%",
        f"{expected_roi:+.1%}",
        help="Expected profit as a percentage of total money staked across checked bets. For every $1 bet, you expect to gain/lose this fraction.",
    )
    m4.metric("Bets Selected", str(n_bets), help="Number of checked bets contributing to the metrics.")

# ---------------------------------------------------------------------------
# Sidebar context
# ---------------------------------------------------------------------------

n_games = df_ev["game_pk"].nunique() if not df_ev.empty else 0
n_actionable = int(df_ev["actionable"].sum()) if not df_ev.empty else 0

with st.sidebar:
    st.subheader("Context")
    st.write(f"**Date:** {selected_date}")
    st.write(f"**Bankroll:** ${bankroll_input:,.2f}")
    st.write(f"**Games loaded:** {n_games}")
    st.write(f"**Actionable bets:** {n_actionable}")
