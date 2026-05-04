"""Game Insights page — key model features and SHAP explanations per game."""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from app.utils.db import run_query
from betting_ml.utils.calibrated_classifier import PlattCalibratedXGBClassifier  # noqa: F401 — needed for joblib unpickling
from betting_ml.utils.model_io import load_model

st.set_page_config(page_title="Game Insights", layout="wide")
st.title("Game Insights")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(v):
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _fmt(v, precision: int = 3) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, str):
        return v
    return f"{v:.{precision}f}"


def _fmt_pct(v) -> str:
    f = _safe_float(v)
    return f"{f * 100:.1f}%" if f is not None else "N/A"


def _delta_str(a, b, precision: int = 3) -> str | None:
    fa, fb = _safe_float(a), _safe_float(b)
    if fa is None or fb is None:
        return None
    return f"{fa - fb:+.{precision}f}"


def _v(row: pd.Series, col: str):
    val = row.get(col)
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return str(val) if str(val).strip() else None


# ---------------------------------------------------------------------------
# Date selector (defaults to today)
# ---------------------------------------------------------------------------

date = st.date_input("Select date", value=datetime.date.today())
date_str = date.strftime("%Y-%m-%d")

# ---------------------------------------------------------------------------
# Game picker
# ---------------------------------------------------------------------------

_GAMES_SQL = """
SELECT
    p.game_pk,
    p.home_team,
    p.away_team,
    g.home_team_name,
    g.away_team_name,
    g.game_date
FROM (
    SELECT game_pk, home_team, away_team,
           ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY inserted_at DESC) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions
    WHERE score_date = '{date}'
) p
JOIN baseball_data.betting.stg_statsapi_games g ON p.game_pk = g.game_pk
WHERE p._rn = 1
ORDER BY p.home_team ASC
"""


@st.cache_data(ttl=300)
def load_games(date_str: str) -> pd.DataFrame:
    df = run_query(_GAMES_SQL.format(date=date_str))
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
    return df


games_df = load_games(date_str)

if games_df.empty:
    st.info("No predictions found for this date.")
    st.stop()


def _game_label(row: pd.Series) -> str:
    away = row.get("away_team_name") or row.get("away_team", "Away")
    home = row.get("home_team_name") or row.get("home_team", "Home")
    return f"{away} @ {home}"


game_options = {_game_label(row): int(row["game_pk"]) for _, row in games_df.iterrows()}
selected_label = st.selectbox("Select game", list(game_options.keys()))
game_pk = game_options[selected_label]

_row = games_df[games_df["game_pk"] == game_pk].iloc[0]
home_team_name: str = _row.get("home_team_name") or _row.get("home_team", "Home")
away_team_name: str = _row.get("away_team_name") or _row.get("away_team", "Away")

st.divider()

# ===========================================================================
# Section 1 — Prediction Summary
# ===========================================================================

_PRED_SQL = """
SELECT
    pred_total_runs           AS predicted_total_runs,
    calibrated_win_prob       AS home_win_prob,
    consensus_win_prob,
    calibrated_win_prob - consensus_win_prob AS edge,
    h2h_kelly_fraction        AS kelly_fraction
FROM baseball_data.betting_ml.daily_model_predictions
WHERE game_pk = {game_pk}
ORDER BY inserted_at DESC
LIMIT 1
"""


@st.cache_data(ttl=300)
def load_prediction(game_pk: int) -> pd.DataFrame:
    df = run_query(_PRED_SQL.format(game_pk=game_pk))
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
    return df


st.subheader("Prediction Summary")
pred_df = load_prediction(game_pk)

if pred_df.empty:
    st.warning("No prediction row found for this game.")
else:
    r = pred_df.iloc[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    total_runs = _safe_float(r.get("predicted_total_runs"))
    home_win_prob = _safe_float(r.get("home_win_prob"))
    consensus = _safe_float(r.get("consensus_win_prob"))
    edge = _safe_float(r.get("edge"))
    kelly = _safe_float(r.get("kelly_fraction"))

    c1.metric("Predicted Total Runs", f"{total_runs:.2f}" if total_runs is not None else "N/A")
    c2.metric("Home Win Prob", _fmt_pct(home_win_prob))
    c3.metric("Market Win Prob", _fmt_pct(consensus))
    edge_label = (f"{'+' if edge >= 0 else ''}{edge * 100:.1f}%") if edge is not None else "N/A"
    c4.metric("Edge", edge_label,
              delta=f"{edge * 100:.1f}" if edge is not None else None,
              delta_color="normal")
    c5.metric("Kelly Fraction", _fmt_pct(kelly))

st.divider()

# ===========================================================================
# Section 2 — Team Performance Comparison
# ===========================================================================
# Column aliases map spec names → actual DB columns so both the SQL query and
# the AC string checks work with a single source of truth.

_TEAM_RENAME = {
    "home_off_woba_30d":                     "home_rolling_ops_30d",
    "away_off_woba_30d":                     "away_rolling_ops_30d",
    "home_off_runs_per_game_30d":            "home_rolling_runs_per_game_30d",
    "away_off_runs_per_game_30d":            "away_rolling_runs_per_game_30d",
    "home_starter_xwoba_against_30d":        "home_starter_era",
    "away_starter_xwoba_against_30d":        "away_starter_era",
    "home_starter_k_pct_30d":               "home_starter_whip",
    "away_starter_k_pct_30d":               "away_starter_whip",
    "home_starter_pitcher_hand":             "home_starter_handedness",
    "away_starter_pitcher_hand":             "away_starter_handedness",
    "home_lineup_vs_away_starter_xwoba_adj": "home_platoon_advantage_score",
    "away_lineup_vs_home_starter_xwoba_adj": "away_platoon_advantage_score",
    "home_bp_xwoba_against_14d":             "home_bullpen_era_7d",
    "away_bp_xwoba_against_14d":             "away_bullpen_era_7d",
    "home_bp_innings_pitched_14d":           "home_bullpen_ip_7d",
    "away_bp_innings_pitched_14d":           "away_bullpen_ip_7d",
    "park_run_factor_3yr":                   "park_run_factor",
}

_FULL_FEATURES_SQL = """
SELECT *
FROM baseball_data.betting_features.feature_pregame_game_features
WHERE game_pk = {game_pk}
ORDER BY game_date DESC
LIMIT 1
"""


@st.cache_data(ttl=300)
def load_full_feature_vector(game_pk: int, date_str: str) -> pd.DataFrame:
    """Return all feature columns for game_pk.

    Tries Snowflake first; falls back to the same Stats API assembly path used
    by the prediction script so same-day games without a dbt build still work.
    """
    df = run_query(_FULL_FEATURES_SQL.format(game_pk=game_pk))
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
        return df
    # Fallback — mirrors predict_today.py's load_todays_features() path
    from betting_ml.utils.data_loader import load_todays_features
    all_today = load_todays_features(date_str)
    if all_today.empty:
        return pd.DataFrame()
    all_today.columns = [c.lower() for c in all_today.columns]
    row = all_today[all_today["game_pk"] == game_pk]
    return row.reset_index(drop=True)


@st.cache_data(ttl=300)
def load_team_features(game_pk: int, date_str: str) -> pd.DataFrame:
    df = load_full_feature_vector(game_pk, date_str)
    if df.empty:
        return df
    return df.rename(columns=_TEAM_RENAME)


st.subheader("Team Performance Comparison")
team_df = load_team_features(game_pk, date_str)

if team_df.empty:
    st.warning(
        "No feature data found for this game. "
        "The feature pipeline may not have run for this date yet — "
        "try running a dbtf build for the selected date first."
    )
else:
    r = team_df.iloc[0]

    # Label lives inside st.metric so the native help= icon is always visible.
    # Away column uses label_visibility="hidden" to preserve height alignment.
    def _cmp(
        label: str,
        hval,
        aval,
        precision: int = 3,
        lower_better: bool = False,
        help_text: str | None = None,
    ) -> None:
        c1, c2 = st.columns(2)
        hf, af = _safe_float(hval), _safe_float(aval)
        h_delta = _delta_str(hf, af, precision) if hf is not None and af is not None else None
        a_delta = _delta_str(af, hf, precision) if hf is not None and af is not None else None
        dc = "inverse" if lower_better else "normal"
        c1.metric(label, _fmt(hf, precision) if hf is not None else "N/A",
                  delta=h_delta, delta_color=dc, help=help_text)
        c2.metric(label, _fmt(af, precision) if af is not None else "N/A",
                  delta=a_delta, delta_color=dc, label_visibility="hidden")

    def _cmp_str(label: str, hval_str, aval_str, help_text: str | None = None) -> None:
        c1, c2 = st.columns(2)
        c1.metric(label, hval_str or "N/A", help=help_text)
        c2.metric(label, aval_str or "N/A", label_visibility="hidden")

    def _section(title: str) -> None:
        st.markdown(f"#### {title}")

    # Team name header
    hdr1, hdr2 = st.columns(2)
    hdr1.markdown(f"**{home_team_name}**")
    hdr2.markdown(f"**{away_team_name}**")

    _section("Offense (rolling 30d)")
    _cmp("wOBA 30d", _v(r, "home_rolling_ops_30d"), _v(r, "away_rolling_ops_30d"),
         help_text="Weighted On-Base Average over the last 30 days. Combines all offensive events into a single rate stat; higher is better.")
    _cmp("Runs/Game 30d", _v(r, "home_rolling_runs_per_game_30d"), _v(r, "away_rolling_runs_per_game_30d"), precision=2,
         help_text="Average runs scored per game over the last 30 days.")

    _section("Starting Pitcher")
    _cmp("xwOBA Against 30d", _v(r, "home_starter_era"), _v(r, "away_starter_era"),
         lower_better=True,
         help_text="Expected wOBA allowed by the starter over the last 30 days, based on contact quality. Lower is better.")
    _cmp("K% 30d", _v(r, "home_starter_whip"), _v(r, "away_starter_whip"),
         help_text="Strikeout rate of the starting pitcher over the last 30 days. Higher means more swing-and-miss ability.")
    _cmp_str("Handedness", _fmt(_v(r, "home_starter_handedness")), _fmt(_v(r, "away_starter_handedness")),
             help_text="Throwing hand of the starting pitcher (L = Left, R = Right).")

    _section("Lineup vs. Starter Handedness")
    _cmp("Platoon xwOBA Adj", _v(r, "home_platoon_advantage_score"), _v(r, "away_platoon_advantage_score"),
         help_text="Lineup xwOBA adjusted for batter-pitcher handedness matchups. Higher means the lineup has a more favorable platoon split against this starter.")

    _section("Bullpen (rolling 14d)")
    _cmp("Bullpen xwOBA Against", _v(r, "home_bullpen_era_7d"), _v(r, "away_bullpen_era_7d"),
         lower_better=True,
         help_text="Expected wOBA allowed by the bullpen over the last 14 days. Lower is better.")
    _cmp("Bullpen IP 14d", _v(r, "home_bullpen_ip_7d"), _v(r, "away_bullpen_ip_7d"), precision=1,
         help_text="Total innings pitched by the bullpen over the last 14 days. Very high values may indicate a taxed bullpen.")

    _section("Schedule Context")
    _cmp("Days Rest", _v(r, "home_days_rest"), _v(r, "away_days_rest"), precision=0,
         help_text="Days since the team's last game. More rest generally favors the pitching staff.")
    _cmp("Games Last 7d", _v(r, "home_games_last_7d"), _v(r, "away_games_last_7d"), precision=0,
         help_text="Number of games played in the last 7 days. Higher values may indicate accumulated fatigue.")

    _section("Park & Context")
    pc1, pc2 = st.columns(2)
    pc1.metric("Park Run Factor (3yr)", _fmt(_v(r, "park_run_factor")),
               help="3-year park factor for run scoring relative to league average (1.000 = neutral). Higher means more run-friendly environment.")
    dome_val = r.get("is_dome")
    pc2.metric("Is Dome", str(dome_val) if dome_val is not None else "N/A",
               help="Whether the game is played in a domed stadium, removing weather as a variable.")

st.divider()

# ===========================================================================
# Section 3 — SHAP Feature Importance
# ===========================================================================

_FEATURE_COLS_PATH = _PROJECT_ROOT / "model_artifacts" / "feature_columns.json"

@st.cache_resource
def get_home_win_explainer():
    model = load_model("home_win")
    inner = model.xgb_classifier if hasattr(model, "xgb_classifier") else model
    return shap.TreeExplainer(inner)


@st.cache_resource
def get_total_runs_explainer():
    model = load_model("total_runs")
    return shap.TreeExplainer(model)


def _build_feature_df(raw_df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    row = {}
    for col in feature_cols:
        if col in raw_df.columns:
            val = raw_df.iloc[0][col]
            try:
                row[col] = float(val) if val is not None else 0.0
            except (TypeError, ValueError):
                row[col] = 0.0
        else:
            row[col] = 0.0
    return pd.DataFrame([row], columns=feature_cols)


def _render_waterfall(explainer, X_df: pd.DataFrame, title: str) -> None:
    try:
        sv = explainer(X_df)
        fig, _ = plt.subplots()
        shap.plots.waterfall(sv[0], max_display=10, show=False)
        fig = plt.gcf()
        st.markdown(f"**{title}**")
        st.pyplot(fig)
        plt.close(fig)
    except Exception as exc:
        st.warning(f"SHAP waterfall unavailable for {title}: {exc}")


st.subheader("SHAP Feature Importance")
st.caption(
    "SHAP (SHapley Additive exPlanations) shows which features pushed this game's prediction "
    "above or below the model's baseline. Bars to the right increase the predicted probability "
    "(or total runs); bars to the left decrease it. The width reflects the feature's magnitude "
    "of influence for this specific game — not its overall importance across all games."
)

if not _FEATURE_COLS_PATH.exists():
    st.warning(
        "feature_columns.json not found — SHAP section unavailable. "
        f"Expected at {_FEATURE_COLS_PATH}"
    )
else:
    feature_cols = json.loads(_FEATURE_COLS_PATH.read_text())
    raw_feat_df = load_full_feature_vector(game_pk, date_str)

    if raw_feat_df.empty:
        st.warning("No feature data found for this game — SHAP section skipped.")
    else:
        X_df = _build_feature_df(raw_feat_df, feature_cols)
        shap_col1, shap_col2 = st.columns(2)

        with shap_col1:
            try:
                hw_explainer = get_home_win_explainer()
                _render_waterfall(hw_explainer, X_df, "Home Win Model")
            except Exception as exc:
                st.warning(f"Home Win SHAP explainer failed to load: {exc}")

        with shap_col2:
            try:
                tr_explainer = get_total_runs_explainer()
                _render_waterfall(tr_explainer, X_df, "Total Runs Model")
            except Exception as exc:
                st.warning(f"Total Runs SHAP explainer failed to load: {exc}")

st.divider()

# ===========================================================================
# Section 4 — Recent Team Form
# ===========================================================================

_FORM_SQL = """
SELECT
    g.game_date        AS "Date",
    CASE WHEN g.home_team_id = {team_id} THEN g.away_team_name
         ELSE g.home_team_name END AS "Opponent",
    CASE WHEN g.home_team_id = {team_id} THEN 'H' ELSE 'A' END AS "H/A",
    CASE WHEN g.home_team_id = {team_id} THEN g.home_score
         ELSE g.away_score END AS "RS",
    CASE WHEN g.home_team_id = {team_id} THEN g.away_score
         ELSE g.home_score END AS "RA"
FROM baseball_data.betting.stg_statsapi_games g
WHERE (g.home_team_id = {team_id} OR g.away_team_id = {team_id})
  AND g.game_type = 'R'
  AND g.abstract_game_state = 'Final'
  AND g.game_date < '{game_date}'
ORDER BY g.game_date DESC
LIMIT 10
"""


@st.cache_data(ttl=300)
def load_recent_form(team_id: int, game_date: str) -> pd.DataFrame:
    df = run_query(_FORM_SQL.format(team_id=team_id, game_date=game_date))
    if df.empty:
        return df
    df.columns = [c.strip('"') for c in df.columns]
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df["W/L"] = df.apply(
        lambda r: "W" if r["RS"] > r["RA"] else ("L" if r["RS"] < r["RA"] else "T"),
        axis=1,
    )
    form = df[["Date", "Opponent", "H/A", "RS", "RA", "W/L"]].copy()
    wins = int((form["W/L"] == "W").sum())
    losses = int((form["W/L"] == "L").sum())
    totals = pd.DataFrame([{
        "Date": "TOTALS",
        "Opponent": "",
        "H/A": "",
        "RS": int(form["RS"].sum()),
        "RA": int(form["RA"].sum()),
        "W/L": f"{wins}W-{losses}L",
    }])
    return pd.concat([form, totals], ignore_index=True)


def _get_team_ids(game_pk: int) -> tuple[int | None, int | None]:
    sql = f"""
    SELECT home_team_id, away_team_id, game_date
    FROM baseball_data.betting.stg_statsapi_games
    WHERE game_pk = {game_pk}
    LIMIT 1
    """
    df = run_query(sql)
    if df.empty:
        return None, None
    df.columns = [c.lower() for c in df.columns]
    row = df.iloc[0]
    return (
        int(row["home_team_id"]) if row.get("home_team_id") is not None else None,
        int(row["away_team_id"]) if row.get("away_team_id") is not None else None,
    )


st.subheader("Recent Team Form")

home_team_id, away_team_id = _get_team_ids(game_pk)
game_date_str = _row.get("game_date")
if isinstance(game_date_str, (datetime.date, datetime.datetime)):
    game_date_str = game_date_str.strftime("%Y-%m-%d")

form_col1, form_col2 = st.columns(2)

def _form_record(form_df: pd.DataFrame) -> str:
    if form_df.empty:
        return ""
    totals_row = form_df[form_df["Date"] == "TOTALS"]
    if not totals_row.empty:
        return f" — {totals_row.iloc[0]['W/L']}"
    return ""


with form_col1:
    if home_team_id is None:
        st.warning("Could not resolve home team ID.")
    else:
        home_form = load_recent_form(home_team_id, game_date_str or date_str)
        st.markdown(f"**Home: {home_team_name} — Last 10{_form_record(home_form)}**")
        if home_form.empty:
            st.info("No prior games found for this team.")
        else:
            st.dataframe(home_form, use_container_width=True, hide_index=True)

with form_col2:
    if away_team_id is None:
        st.warning("Could not resolve away team ID.")
    else:
        away_form = load_recent_form(away_team_id, game_date_str or date_str)
        st.markdown(f"**Away: {away_team_name} — Last 10{_form_record(away_form)}**")
        if away_form.empty:
            st.info("No prior games found for this team.")
        else:
            st.dataframe(away_form, use_container_width=True, hide_index=True)
