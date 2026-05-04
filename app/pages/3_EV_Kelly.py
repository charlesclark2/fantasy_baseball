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

from app.utils.db import run_execute, run_query

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

            total_line = _safe_float(r.get("total_line_consensus")) if "over" in market_name or "under" in market_name else None

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
                "total_line": total_line,
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
        "Profit If Win ($)": to_win.map(lambda v: f"{v:.2f}"),
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
        "Odds": st.column_config.TextColumn("Odds", help="Consensus market odds in American format (+150 = bet $100 to win $150; −150 = bet $150 to win $100)."),
        "Stake ($)": st.column_config.TextColumn("Stake ($)", help="Capped Kelly% × your bankroll. This is the suggested dollar amount to wager."),
        "Profit If Win ($)": st.column_config.TextColumn("Profit If Win ($)", help="Net profit if the bet wins: Stake × (decimal_odds − 1). Does not account for win probability — see EV ($) for the probability-weighted figure."),
        "EV ($)": st.column_config.TextColumn("EV ($)", help="Probability-weighted expected dollar profit: (model_prob × Profit If Win) − (1 − model_prob) × Stake. This is less than Profit If Win because it accounts for the chance the bet loses."),
        "_stake_raw": st.column_config.Column("_stake_raw", disabled=True),
        "_ev_raw": st.column_config.Column("_ev_raw", disabled=True),
    }

    edited = st.data_editor(
        df_slate,
        use_container_width=True,
        column_config=_slate_col_config,
        column_order=["Include", "Bet", "Odds", "Stake ($)", "Profit If Win ($)", "EV ($)"],
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
# Log a Bet
# ---------------------------------------------------------------------------

_BET_HISTORY_SQL = """
SELECT
    b.bet_id,
    b.placed_at,
    b.score_date,
    b.game_pk,
    b.matchup,
    b.market,
    b.bookmaker,
    b.american_odds,
    b.stake,
    b.total_line,
    b.model_prob,
    b.market_prob,
    b.ev,
    b.kelly_capped,
    b.outcome,
    b.profit_loss,
    b.notes,
    g.home_score,
    g.away_score,
    g.status_code
FROM baseball_data.betting_ml.placed_bets b
LEFT JOIN baseball_data.betting.stg_statsapi_games g
    ON b.game_pk = g.game_pk
    AND g.status_code = 'F'
ORDER BY b.placed_at DESC
"""

_INSERT_BET_SQL = """
INSERT INTO baseball_data.betting_ml.placed_bets
    (score_date, game_pk, matchup, market, bookmaker, american_odds, stake,
     total_line, model_prob, market_prob, ev, kelly_capped, notes)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def _derive_outcome(row: pd.Series) -> str | None:
    """Return 'win', 'loss', 'push', or None (pending) for a placed_bets row."""
    if pd.isna(row.get("status_code")) or row.get("status_code") != "F":
        return None
    home_score = row.get("home_score")
    away_score = row.get("away_score")
    if pd.isna(home_score) or pd.isna(away_score):
        return None
    total_actual = home_score + away_score
    market = str(row.get("market", ""))
    total_line = row.get("total_line")

    if market == "h2h home":
        return "win" if home_score > away_score else "loss"
    if market == "h2h away":
        return "win" if away_score > home_score else "loss"
    if market in ("over", "under") and not pd.isna(total_line):
        if total_actual > total_line:
            return "win" if market == "over" else "loss"
        if total_actual < total_line:
            return "win" if market == "under" else "loss"
        return "push"
    return None


def _compute_pl(stake: float, american_odds: int, outcome: str | None) -> float | None:
    if outcome is None:
        return None
    if outcome == "push":
        return 0.0
    if american_odds > 0:
        decimal_odds = american_odds / 100 + 1
    else:
        decimal_odds = 100 / abs(american_odds) + 1
    if outcome == "win":
        return stake * (decimal_odds - 1)
    return -stake  # loss


def _american_from_decimal(dec: float) -> int:
    if dec >= 2.0:
        return round((dec - 1) * 100)
    else:
        return round(-100 / (dec - 1))


@st.cache_data(ttl=300, show_spinner="Loading bet history...")
def load_bet_history() -> pd.DataFrame:
    return run_query(_BET_HISTORY_SQL)


st.divider()
with st.expander("📝 Log a Bet", expanded=False):
    _bet_logged_msg = st.session_state.pop("_bet_success", None)
    if _bet_logged_msg:
        st.success(f"Bet logged: {_bet_logged_msg}")

    # Version counters: incrementing a counter changes widget keys, forcing
    # Streamlit to create fresh widgets with their value= defaults on the next render.
    _sel_v = st.session_state.get("_bet_sel_version", 0)
    _form_v = st.session_state.get("_bet_form_version", 0)

    # ---- game + market selectors (outside form so auto-populate reacts) ----
    if df_ev.empty:
        st.info("No EV data for this date. Select a date with games to log a bet.")
    else:
        matchup_options = ["— select —"] + sorted(df_ev["matchup_label"].unique().tolist())
        sel_game = st.selectbox(
            "Game",
            matchup_options,
            key=f"bet_log_game_{_sel_v}",
        )

        df_game_rows = df_ev[df_ev["matchup_label"] == sel_game] if sel_game != "— select —" else pd.DataFrame()

        market_options = df_game_rows["market"].tolist() if not df_game_rows.empty else []
        sel_market = st.selectbox(
            "Market",
            ["— select —"] + market_options,
            key=f"bet_log_market_{_sel_v}",
        )

        ev_row: pd.Series | None = None
        if sel_game != "— select —" and sel_market != "— select —" and not df_game_rows.empty:
            mask = df_game_rows["market"] == sel_market
            if mask.any():
                ev_row = df_game_rows[mask].iloc[0]

        if ev_row is not None:
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Model Prob", f"{ev_row['model_prob']:.1%}")
            c2.metric("Mkt Impl Prob", f"{ev_row['market_prob']:.1%}")
            c3.metric("Consensus Odds", f"{_american_from_decimal(ev_row['decimal_odds']):+d}")
            c4.metric("EV", f"{ev_row['ev']:+.4f}")
            c5.metric("Capped Kelly%", f"{ev_row['kelly_capped']:.2%}")

        with st.form(f"log_bet_form_{_form_v}"):
            col_a, col_b, col_c = st.columns(3)
            bookmaker = col_a.text_input("Bookmaker", value="bovada", key=f"bet_form_bookmaker_{_form_v}")
            default_odds = (
                _american_from_decimal(ev_row["decimal_odds"]) if ev_row is not None else -110
            )
            actual_odds = col_b.number_input(
                "Actual Odds (American)",
                min_value=-10000,
                max_value=10000,
                value=int(default_odds),
                step=1,
                key=f"bet_form_odds_{_form_v}",
            )
            stake_input = col_c.number_input(
                "Stake ($)", min_value=0.01, value=10.0, step=1.0, key=f"bet_form_stake_{_form_v}"
            )

            show_total_line = ev_row is not None and sel_market in ("over", "under")
            default_total = float(ev_row["total_line"]) if (show_total_line and ev_row["total_line"] is not None) else 0.0
            total_line_input = None
            if show_total_line:
                total_line_input = st.number_input(
                    "Total Line (O/U)", value=default_total, step=0.5, key=f"bet_form_total_line_{_form_v}"
                )

            notes_input = st.text_area("Notes (optional)", max_chars=500, key=f"bet_form_notes_{_form_v}")

            submitted = st.form_submit_button("Log Bet")
            if submitted:
                if sel_game == "— select —" or sel_market == "— select —":
                    st.error("Select a game and market before logging.")
                elif stake_input <= 0:
                    st.error("Stake must be greater than 0.")
                elif actual_odds == 0:
                    st.error("American odds cannot be 0.")
                else:
                    try:
                        game_pk_val = int(df_game_rows.iloc[0]["game_pk"]) if not df_game_rows.empty else None
                        run_execute(
                            _INSERT_BET_SQL,
                            params=(
                                date_str,
                                game_pk_val,
                                sel_game,
                                sel_market,
                                bookmaker or None,
                                int(actual_odds),
                                float(stake_input),
                                float(total_line_input) if total_line_input is not None else None,
                                float(ev_row["model_prob"]) if ev_row is not None else None,
                                float(ev_row["market_prob"]) if ev_row is not None else None,
                                float(ev_row["ev"]) if ev_row is not None else None,
                                float(ev_row["kelly_capped"]) if ev_row is not None else None,
                                notes_input or None,
                            ),
                        )
                        st.session_state["_bet_success"] = f"{sel_game} — {sel_market} @ {int(actual_odds):+d} (${float(stake_input):.2f})"
                        st.session_state["_bet_sel_version"] = _sel_v + 1
                        st.session_state["_bet_form_version"] = _form_v + 1
                        load_bet_history.clear()
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to log bet: {exc}")

# ---------------------------------------------------------------------------
# Bet History
# ---------------------------------------------------------------------------

st.subheader(f"Bet History — {selected_date.strftime('%b %-d, %Y')}")

df_hist_raw = load_bet_history()

if df_hist_raw.empty:
    st.info("No bets logged yet. Use 'Log a Bet' above to record your first bet.")
else:
    _df_all = df_hist_raw.copy()
    _df_all.columns = [c.lower() for c in _df_all.columns]
    if "score_date" in _df_all.columns:
        _df_all["score_date"] = pd.to_datetime(_df_all["score_date"]).dt.date
    df_hist = _df_all[_df_all["score_date"] == selected_date].copy() if "score_date" in _df_all.columns else _df_all.copy()

    if df_hist.empty:
        st.info(f"No bets logged for {selected_date}. Use 'Log a Bet' above to record a bet for this date.")
    else:
        # Auto-settle: derive outcome and P&L in Python (display-only, no DB writes)
        df_hist["_derived_outcome"] = df_hist.apply(_derive_outcome, axis=1)
        df_hist["_display_outcome"] = df_hist["_derived_outcome"].where(
            df_hist["outcome"].isna(), df_hist["outcome"]
        )
        df_hist["_pl"] = df_hist.apply(
            lambda r: _compute_pl(
                float(r["stake"]) if not pd.isna(r["stake"]) else 0.0,
                int(r["american_odds"]) if not pd.isna(r["american_odds"]) else 0,
                r["_display_outcome"],
            ),
            axis=1,
        )

        # Summary metrics (settled only)
        settled = df_hist[df_hist["_display_outcome"].notna()]
        wins = (settled["_display_outcome"] == "win").sum()
        losses = (settled["_display_outcome"] == "loss").sum()
        pushes = (settled["_display_outcome"] == "push").sum()
        total_wagered = float(settled["stake"].sum()) if not settled.empty else 0.0
        total_pl = float(settled["_pl"].sum()) if not settled.empty else 0.0
        roi = total_pl / total_wagered if total_wagered > 0 else 0.0

        sm1, sm2, sm3, sm4 = st.columns(4)
        sm1.metric("Total Wagered ($)", f"{total_wagered:.2f}", help="Sum of stakes for settled bets only.")
        sm2.metric(
            "Total P&L ($)",
            f"{total_pl:+.2f}",
            delta=f"{total_pl:+.2f}",
            help="Realized profit/loss across all settled bets.",
        )
        sm3.metric("ROI%", f"{roi:+.1%}", help="Total P&L ÷ Total Wagered (settled bets).")
        sm4.metric("Record (W-L-P)", f"{wins}-{losses}-{pushes}", help="Wins, losses, and pushes among settled bets.")

        def _fmt_outcome(o):
            if o is None or (isinstance(o, float) and pd.isna(o)):
                return "pending"
            return str(o)

        df_table = pd.DataFrame({
            "Matchup": df_hist["matchup"],
            "Market": df_hist["market"],
            "Bookmaker": df_hist["bookmaker"].fillna("—"),
            "Odds": df_hist["american_odds"].map(lambda v: f"{int(v):+d}" if not pd.isna(v) else "—"),
            "Stake ($)": df_hist["stake"].map(lambda v: f"{float(v):.2f}" if not pd.isna(v) else "—"),
            "Model Prob": df_hist["model_prob"].map(lambda v: f"{float(v):.1%}" if not pd.isna(v) else "—"),
            "EV": df_hist["ev"].map(lambda v: f"{float(v):+.4f}" if not pd.isna(v) else "—"),
            "Outcome": df_hist["_display_outcome"].map(_fmt_outcome),
            "P&L ($)": df_hist["_pl"].map(lambda v: f"{float(v):+.2f}" if v is not None and not pd.isna(v) else "—"),
        })

        def _outcome_color(val: str):
            colors = {"win": "color: green", "loss": "color: red", "push": "color: grey", "pending": "font-style: italic; color: grey"}
            return colors.get(val, "")

        styled = df_table.style.map(_outcome_color, subset=["Outcome"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

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
