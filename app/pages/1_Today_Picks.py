"""Today's Picks page — reads pre-scored predictions from daily_model_predictions."""

from __future__ import annotations

import datetime
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from app.utils.db import run_query
from app.utils.prediction_status import basis_message, is_confirmed, lineup_status_emoji
from app.utils.scorer_env import scorer_env

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

_PICKS_SQL = """
SELECT
    p.*,
    COALESCE(l.both_confirmed, FALSE) AS both_confirmed,
    g.game_date AS stg_game_date
FROM (
    SELECT *,
           CASE
               WHEN prediction_type = 'post_lineup'                 THEN 'lineup_confirmed'
               WHEN COALESCE(data_source, '') = 'intraday_fallback' THEN 'provisional_fallback'
               ELSE 'provisional_pre_lineup'
           END AS prediction_basis,
           -- Priority: post_lineup (4) > morning-with-odds (3) > fallback-with-odds (2)
           -- > morning-no-odds (1) > fallback-no-odds (0). Recency breaks ties.
           -- Rows with odds beat same-tier rows without so a morning run that missed
           -- Bovada lines (e.g. team-name mismatch at ingest) loses to a fallback
           -- refresh that did pick up the odds.
           ROW_NUMBER() OVER (
               PARTITION BY game_pk
               ORDER BY
                   CASE
                       WHEN prediction_type = 'post_lineup'                                          THEN 4
                       WHEN COALESCE(data_source, '') != 'intraday_fallback' AND has_odds = TRUE     THEN 3
                       WHEN has_odds = TRUE                                                          THEN 2
                       WHEN COALESCE(data_source, '') != 'intraday_fallback'                        THEN 1
                       ELSE 0
                   END DESC,
                   inserted_at DESC
           ) AS _rn
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
LEFT JOIN (
    SELECT game_pk, game_date
    FROM baseball_data.betting.stg_statsapi_games
    WHERE official_date = '{date}'
) g ON p.game_pk = g.game_pk
WHERE p._rn = 1
ORDER BY p.home_team ASC
"""

_PIPELINE_STATUS_SQL = """
SELECT
    pipeline_status,
    predict_today_complete_ts,
    lineup_confirmed_complete_ts,
    signal_completeness_score,
    n_games_scored,
    n_qualified_bets,
    is_fresh
FROM baseball_data.betting.mart_pipeline_status
WHERE run_date = '{date}'
"""

_OUTCOMES_SQL = """
SELECT
    game_pk,
    home_score,
    away_score,
    home_is_winner,
    abstract_game_state
FROM baseball_data.betting.stg_statsapi_games
WHERE official_date = '{date}'
  AND abstract_game_state = 'Final'
"""

_MOVEMENT_SQL = """
WITH snap_consensus AS (
    SELECT
        o.event_id,
        o.home_team,
        o.away_team,
        o.ingestion_ts,
        AVG(CASE WHEN o.is_home_outcome AND o.market_key = 'h2h' THEN o.outcome_price_american END) AS home_ml_avg,
        AVG(CASE WHEN o.is_away_outcome AND o.market_key = 'h2h' THEN o.outcome_price_american END) AS away_ml_avg,
        AVG(CASE WHEN o.market_key = 'totals' AND o.outcome_name = 'Over' THEN o.outcome_point END) AS total_line_avg
    FROM baseball_data.betting.mart_odds_outcomes o
    WHERE o.commence_date = '{date}'
      AND o.ingestion_ts < o.commence_time
    GROUP BY o.event_id, o.home_team, o.away_team, o.ingestion_ts
),
ranked AS (
    SELECT
        sc.*,
        ROW_NUMBER() OVER (PARTITION BY sc.event_id ORDER BY sc.ingestion_ts ASC)  AS rn_first,
        ROW_NUMBER() OVER (PARTITION BY sc.event_id ORDER BY sc.ingestion_ts DESC) AS rn_last,
        COUNT(*) OVER (PARTITION BY sc.event_id) AS snapshot_count
    FROM snap_consensus sc
)
SELECT
    f.home_team,
    f.away_team,
    f.snapshot_count,
    f.ingestion_ts  AS first_ts,
    l.ingestion_ts  AS last_ts,
    f.home_ml_avg   AS home_ml_open,
    l.home_ml_avg   AS home_ml_current,
    f.away_ml_avg   AS away_ml_open,
    l.away_ml_avg   AS away_ml_current,
    f.total_line_avg AS total_line_open,
    l.total_line_avg AS total_line_current
FROM ranked f
JOIN ranked l ON f.event_id = l.event_id
WHERE f.rn_first = 1 AND l.rn_last = 1
ORDER BY f.home_team
"""

# ---------------------------------------------------------------------------
# Cached data loading
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading picks...")
def load_picks(date_str: str) -> pd.DataFrame:
    df = run_query(_PICKS_SQL.format(date=date_str))
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]

    kelly_raw = df["h2h_kelly_fraction"]
    df["kelly_capped"] = kelly_raw.clip(upper=0.10)
    df["kelly_exceeded_cap"] = kelly_raw > 0.10

    df["totals_kelly_capped"] = df["totals_kelly_fraction"].clip(upper=0.10)
    df["totals_kelly_exceeded_cap"] = df["totals_kelly_fraction"] > 0.10

    market = df["h2h_market_implied_prob"].replace(0, np.nan)
    # calibrated_win_prob = production model prob (Platt-recalibrated). The
    # pre-calibration audit column consensus_win_prob must NOT be used for
    # edge/EV/Kelly math (that's how predict_today.py computes live edge too).
    model = df["calibrated_win_prob"]
    decimal_odds = 1.0 / market
    df["ev"] = (model * (decimal_odds - 1)) - (1 - model)

    return df


@st.cache_data(show_spinner="Loading market movement...")
def load_movement(date_str: str) -> pd.DataFrame:
    df = run_query(_MOVEMENT_SQL.format(date=date_str))
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    return df


@st.cache_data(show_spinner="Loading outcomes...")
def load_outcomes(date_str: str) -> pd.DataFrame:
    df = run_query(_OUTCOMES_SQL.format(date=date_str))
    if df.empty:
        return pd.DataFrame()
    df.columns = [c.lower() for c in df.columns]
    return df


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_TZ_OPTIONS: dict[str, str] = {
    "Eastern (ET)":  "America/New_York",
    "Central (CT)":  "America/Chicago",
    "Mountain (MT)": "America/Denver",
    "Pacific (PT)":  "America/Los_Angeles",
    "Arizona (AZ)":  "America/Phoenix",
    "Alaska (AKT)":  "America/Anchorage",
    "Hawaii (HST)":  "Pacific/Honolulu",
}
_TZ_ABBREVS: dict[str, str] = {
    "America/New_York":    "ET",
    "America/Chicago":     "CT",
    "America/Denver":      "MT",
    "America/Los_Angeles": "PT",
    "America/Phoenix":     "AZ",
    "America/Anchorage":   "AKT",
    "Pacific/Honolulu":    "HST",
}


def _fmt_game_time(val, tz: str = "America/New_York") -> str:
    if val is None:
        return "—"
    try:
        ts = pd.Timestamp(val)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        local = ts.tz_convert(tz)
        abbrev = _TZ_ABBREVS.get(tz, tz)
        return local.strftime("%-I:%M %p") + f" {abbrev}"
    except Exception:
        return "—"


def _fmt_pct(val) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"{float(val):.1%}"


def _fmt_signed(val) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"{float(val):+.3f}"


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _fmt_ml(val) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    v = round(float(val))
    return f"+{v}" if v > 0 else str(v)


def _fmt_movement_cell(open_val, current_val) -> tuple[str, float]:
    """Return (display_string, raw_delta) where delta = current - open in American odds points."""
    open_f = _safe_float(open_val)
    curr_f = _safe_float(current_val)
    if open_f is None or curr_f is None:
        return "—", 0.0
    delta = curr_f - open_f
    if abs(delta) < 1.0:
        return _fmt_ml(curr_f), 0.0
    sign = "+" if delta > 0 else "−"
    return f"{_fmt_ml(open_f)} → {_fmt_ml(curr_f)} ({sign}{abs(delta):.0f})", delta


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

_STYLE_VISIBLE_COLS = [
    "Signal", "Matchup", "Game Time", "Lineups", "P(Over)", "Model Win%",
    "Market Win%", "Posterior%", "Edge", "EV", "Kelly%",
]

_COL_HELP = {
    "Signal": "🟢 positive edge (moneyline or totals) on a lineup-confirmed prediction  |  🟡 positive edge but prediction is provisional (pre-lineup/fallback — may be blind to the confirmed starter)  |  ⚪ no edge in either market  |  ⛔ no odds data (Odds API gap)",
    "Matchup": "Away team @ Home team",
    "Game Time": "Scheduled first pitch — timezone set in sidebar",
    "Lineups": "✅ prediction is lineup-confirmed (post-lineup re-score, accounts for confirmed starters)  |  ⏳ lineups not yet posted (provisional prediction)  |  ⚠️ lineups posted but prediction still provisional — re-score pending; do not trust the edge yet",
    "P(Over)": "Model probability of total runs exceeding the consensus over/under line",
    "Model Win%": "Blended home-win probability (50% NGBoost run-differential + 50% XGBoost classifier)",
    "Market Win%": "Market-implied home-win probability derived from consensus moneyline odds",
    "Posterior%": "Bayesian posterior blending model and market signals using tuned alpha weight",
    "Edge": (
        "Model Win% minus Market Win%. "
        "Positive = model likes home team more than market. "
        "Negative = model likes away team more."
    ),
    "EV": "Expected value per unit wagered. Positive EV = favorable long-run return at current odds",
    "Kelly%": "Kelly-criterion bet sizing as % of bankroll, capped at 10%.  ⚠ = raw Kelly exceeded cap",
}


def _signal(has_odds: bool, edge: float | None, lineup_confirmed_pred: bool, threshold: float) -> str:
    # 🟢 (actionable) requires the displayed prediction to be lineup-confirmed
    # (post_lineup). A positive edge on a provisional/pre-lineup/fallback prediction
    # is 🟡 — it may be a feature gap (e.g. scored blind to the confirmed starter).
    if not has_odds:
        return "⛔"
    if edge is None:
        return "⚪"
    if abs(edge) >= threshold:
        return "🟢" if lineup_confirmed_pred else "🟡"
    return "⚪"


def _lineup_status(prediction_basis: str, both_confirmed: bool) -> str:
    # Shared with Game Insights et al. via app.utils.prediction_status so the
    # status semantics stay identical across pages.
    return lineup_status_emoji(prediction_basis, both_confirmed)


def _row_bg(row: pd.Series) -> list[str]:
    sig = row.get("Signal", "⚪")
    if sig == "🟢":
        bg = "background-color: #c6efce; color: #1e4620"
    elif sig == "🟡":
        bg = "background-color: #ffeb9c; color: #3d2b00"
    elif sig == "⛔":
        bg = "background-color: #f0f0f0; color: #999999"
    else:
        bg = ""
    return [bg] * len(row)


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Today's Picks — Baseball Betting Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

if "selected_date" not in st.session_state:
    st.session_state["selected_date"] = datetime.date.today()
selected_date = st.date_input("Select date", value=st.session_state["selected_date"])
st.session_state["selected_date"] = selected_date
date_str = selected_date.isoformat()
is_today = selected_date == datetime.date.today()

title = "Today's Picks" if is_today else f"{selected_date.strftime('%B %d, %Y')} Picks"
st.title(title)

# Pipeline freshness banner — only shown for today's date.
if is_today:
    try:
        _ps_df = run_query(_PIPELINE_STATUS_SQL.format(date=date_str))
        if _ps_df.empty:
            st.warning(
                "Pipeline status unknown — no pipeline_status row for today. "
                "The daily pipeline may not have run yet or may have failed before completing predictions."
            )
        else:
            _ps = {c.lower(): v for c, v in zip(_ps_df.columns, _ps_df.iloc[0])}
            _status = _ps.get("pipeline_status", "")
            _is_fresh = bool(_ps.get("is_fresh", False))
            _complete_ts = _ps.get("predict_today_complete_ts")
            _sig_score = _ps.get("signal_completeness_score")
            if _status == "failed":
                st.error(
                    f"Pipeline failed — predictions could not be generated today. "
                    f"Check the Dagster daily_ingestion_job for errors."
                )
            elif not _is_fresh:
                _age_note = (
                    f" (last updated: {_complete_ts})" if _complete_ts else ""
                )
                st.warning(
                    f"Predictions updating{_age_note} — "
                    f"status: **{_status}**, "
                    f"games scored: {_ps.get('n_games_scored', '?')}, "
                    f"signal score: {f'{_sig_score:.0%}' if _sig_score is not None else '?'}. "
                    f"Picks shown may be incomplete or stale."
                )
    except Exception:
        pass  # Never let the banner crash the page.

_DBT_BIN = str(Path.home() / ".local" / "bin" / "dbt")
_DBT_DIR = str(_PROJECT_ROOT / "dbt")

col_r1, col_r2, col_r3 = st.columns([1, 1, 1])
with col_r1:
    if st.button("Refresh Predictions"):
        with st.spinner("Running predict_today.py…"):
            # Epic 1 market-blind models (2026-05-11): all three targets at v3.
            # model_version='prod' keeps these rows separate from versioned backfills.
            result = subprocess.run(
                [
                    "uv", "run", "python", "betting_ml/scripts/predict_today.py",
                    "--date", date_str,
                    "--model-tag", "prod",
                    "--home-win-tag", "v3",
                    "--total-runs-tag", "v3",
                    "--run-diff-tag", "v3",
                ],
                capture_output=True,
                text=True,
                cwd=str(_PROJECT_ROOT),
                env=scorer_env(),  # A1.12 — write prod (the schema this page reads)
            )
        st.cache_data.clear()
        if result.returncode == 0:
            _no_games = (
                "No games found" in result.stdout
                or "No games with confirmed lineups" in result.stdout
            )
            if _no_games:
                st.warning(
                    f"No games with confirmed lineups for {date_str} — predictions not updated. "
                    "Use 'Refresh Lineups & Odds Only' first if lineups are now available."
                )
            else:
                st.success("Predictions refreshed.")
        else:
            st.error(f"predict_today.py failed (exit {result.returncode})")
            st.code(result.stderr, language="text")
with col_r2:
    if st.button("Refresh Lineups & Odds Only"):
        _scripts_dir = str(_PROJECT_ROOT / "scripts")
        # Pass --start-date for the prior month so retroactive lineup confirmations
        # (e.g. yesterday's games when today is the 1st) are picked up.
        _today = datetime.date.today()
        _first_of_month = _today.replace(day=1)
        _prior_month = (_first_of_month - datetime.timedelta(days=1)).replace(day=1)
        _prior_month_str = _prior_month.isoformat()
        _is_historical = not is_today

        if _is_historical:
            _ingest_steps = [
                ("Lineups", ["uv", "run", "python", "ingest_statsapi.py", "schedule",
                             "--start-date", _prior_month_str], _scripts_dir),
                ("Odds events (historical)", ["uv", "run", "python", "odds_api_ingestion.py",
                                              "historical-events",
                                              "--start-date", date_str,
                                              "--end-date", date_str], _scripts_dir),
                ("Odds lines (historical)", ["uv", "run", "python", "odds_api_ingestion.py",
                                             "historical-odds",
                                             "--start-date", date_str,
                                             "--end-date", date_str], _scripts_dir),
            ]
        else:
            _ingest_steps = [
                ("Lineups", ["uv", "run", "python", "ingest_statsapi.py", "schedule",
                             "--start-date", _prior_month_str], _scripts_dir),
                ("Odds events", ["uv", "run", "python", "parlay_api_ingestion.py", "events"], _scripts_dir),
                ("Odds lines", ["uv", "run", "python", "parlay_api_ingestion.py", "odds"], _scripts_dir),
                ("Odds line movement", ["uv", "run", "python", "parlay_api_ingestion.py", "line-movement"], _scripts_dir),
            ]

        _failed = False
        _new_hist_odds_rows: int | None = None
        for _label, _cmd, _cwd in _ingest_steps:
            with st.spinner(f"{_label}…"):
                _r = subprocess.run(_cmd, capture_output=True, text=True, cwd=_cwd)
            if _r.returncode != 0:
                st.error(f"{_label} failed (exit {_r.returncode})")
                st.code(_r.stderr, language="text")
                _failed = True
                break
            if _is_historical and "lines" in _label:
                for _line in _r.stdout.splitlines():
                    if _line.startswith("rows_inserted="):
                        try:
                            _new_hist_odds_rows = int(_line.split("=", 1)[1].strip())
                        except ValueError:
                            pass

        if not _failed:
            if _is_historical and (_new_hist_odds_rows is None or _new_hist_odds_rows == 0):
                st.info(
                    f"Historical odds for {selected_date.strftime('%B %d, %Y')} are already "
                    "up to date — no new data was found in The Odds API. "
                    "The dbt models and predictions were not rebuilt."
                )
            else:
                # Rebuild just the lineup + odds models synchronously so results are
                # immediately visible — no need to wait for a GHA workflow to finish.
                # Ordering: mart tables first (schema changes must be materialized before
                # feature tables that reference them), then feature tables in dependency
                # order. dbt resolves exact execution order from the DAG.
                _dbt_select = " ".join([
                    "stg_statsapi_lineups", "stg_statsapi_lineups_wide",
                    "stg_parlayapi_canonical_events", "stg_parlayapi_odds", "stg_parlayapi_line_movement",
                    "mart_odds_events", "mart_odds_outcomes",
                    "mart_team_season_record",
                    "mart_starting_pitcher_game_log",
                    "feature_pregame_lineup_features", "feature_pregame_odds_features",
                    "feature_pregame_team_features",
                    "feature_pregame_starter_features",
                    "feature_pregame_game_features",
                ])
                with st.spinner("Rebuilding dbt lineup + odds models…"):
                    _r = subprocess.run(
                        [_DBT_BIN, "build", "--select", _dbt_select,
                         "--project-dir", _DBT_DIR, "--profiles-dir", _DBT_DIR],
                        capture_output=True, text=True,
                    )
                if _r.returncode != 0:
                    st.error(f"dbt build failed (exit {_r.returncode})")
                    st.code(_r.stderr, language="text")
                else:
                    with st.spinner("Refreshing predictions with confirmed lineup data…"):
                        _r = subprocess.run(
                            ["uv", "run", "python", "betting_ml/scripts/predict_today.py",
                             "--date", date_str,
                             "--model-tag", "prod",
                             "--home-win-tag", "v3",
                             "--total-runs-tag", "v3",
                             "--run-diff-tag", "v3"],
                            capture_output=True, text=True,
                            cwd=str(_PROJECT_ROOT),
                            env=scorer_env(),  # A1.12 — write prod (the schema this page reads)
                        )
                    if _r.returncode != 0:
                        st.error(f"predict_today.py failed (exit {_r.returncode})")
                        st.code(_r.stderr, language="text")
                    else:
                        _no_games = (
                            "No games found" in _r.stdout
                            or "No games with confirmed lineups" in _r.stdout
                        )
                        st.cache_data.clear()
                        if _no_games:
                            st.warning(
                                "Ingestion and dbt rebuild complete, but no confirmed lineups yet — "
                                "predictions not updated. Try again once lineups post."
                            )
                        else:
                            _date_label = "Historical odds and predictions" if _is_historical else "Lineups, odds, and predictions"
                            st.success(f"{_date_label} refreshed.")

with col_r3:
    if st.button("Score Confirmed Lineups", help="Write post_lineup predictions for today's confirmed-lineup games (🟢 source). Equivalent to the Dagster lineup-sensor job."):
        with st.spinner("Running post-lineup score…"):
            # Mirrors the Dagster lineup-sensor job (pipeline/ops/sensor_ops.py::lineup_predict):
            # scripts/predict_today.py is the production scorer that supports --prediction-type /
            # --lineup-confirmed. (betting_ml/scripts/predict_today.py is the multi-version
            # backfill/eval tool and does NOT accept --prediction-type — calling it here was the bug.)
            # A1.12 — scorer_env() stamps TARGET_ENV=prod so the scorer writes the
            # same schema this page reads (betting_ml); read/write can't diverge.
            _r = subprocess.run(
                ["uv", "run", "python", "scripts/predict_today.py",
                 "--prediction-type", "post_lineup",
                 "--lineup-confirmed",
                 "--date", date_str],
                capture_output=True,
                text=True,
                cwd=str(_PROJECT_ROOT),
                env=scorer_env(),
            )
        st.cache_data.clear()
        if _r.returncode == 0:
            _no_games = (
                "No games found" in _r.stdout
                or "No games with confirmed lineups" in _r.stdout
            )
            if _no_games:
                st.warning("No confirmed lineups found — post_lineup predictions not written.")
            else:
                st.success("Post-lineup predictions written. Bets with confirmed lineups now show 🟢.")
        else:
            st.error(f"Post-lineup score failed (exit {_r.returncode})")
            st.code(_r.stderr, language="text")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

df = load_picks(date_str)

if df.empty:
    st.info(
        f"No predictions found for {selected_date}. "
        "Run 'Refresh Predictions' or check that predict_today.py has been run for this date."
    )
    with st.sidebar:
        st.subheader("Context")
        st.write(f"**Date:** {selected_date}")
        st.write("**Games loaded:** 0")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

best_alpha_val = _safe_float(df["alpha"].iloc[0]) if "alpha" in df.columns else None
model_version = str(df["model_version"].iloc[0]) if "model_version" in df.columns else "—"
inserted_at = str(df["inserted_at"].iloc[0]) if "inserted_at" in df.columns else "—"

with st.sidebar:
    st.subheader("Context")
    st.write(f"**Date:** {selected_date}")
    st.write(f"**Games loaded:** {len(df)}")
    if best_alpha_val is not None:
        st.write(f"**alpha:** {best_alpha_val:.2f}")
    st.write(f"**Model version:** {model_version}")
    st.write(f"**Scored at:** {inserted_at}")

    st.divider()
    st.subheader("Filters")
    edge_threshold = st.slider(
        "Min edge to highlight / recommend",
        min_value=0.01, max_value=0.15, value=0.05, step=0.01,
        format="%.2f",
    )
    selected_tz_label = st.selectbox(
        "Game time timezone",
        options=list(_TZ_OPTIONS.keys()),
        index=0,
    )
    selected_tz = _TZ_OPTIONS[selected_tz_label]

# ---------------------------------------------------------------------------
# Main picks table
# ---------------------------------------------------------------------------

display_rows = []

for _, r in df.iterrows():
    matchup = f"{r['away_team']} @ {r['home_team']}"
    has_odds = bool(r.get("has_odds", False))
    both = bool(r.get("both_confirmed", False))

    basis = str(r.get("prediction_basis") or "provisional_pre_lineup")
    lineup_confirmed_pred = basis == "lineup_confirmed"

    h2h_edge = _safe_float(r.get("h2h_edge"))
    totals_edge_for_sig = _safe_float(r.get("totals_edge"))
    _all_edges = [e for e in [h2h_edge, totals_edge_for_sig] if e is not None]
    _max_abs_edge = max((abs(e) for e in _all_edges), default=None)
    sig = _signal(has_odds, _max_abs_edge, lineup_confirmed_pred, edge_threshold)

    p_over = _safe_float(r.get("p_over_ngboost"))
    kelly_capped = _safe_float(r.get("kelly_capped"))
    kelly_exceeded = bool(r.get("kelly_exceeded_cap", False))

    if has_odds and kelly_capped is not None:
        kelly_str = f"{kelly_capped:.1%}"
        if kelly_exceeded:
            kelly_str += " ⚠"
    else:
        kelly_str = "—"

    display_rows.append({
        "Signal": sig,
        "Matchup": matchup,
        "Game Time": _fmt_game_time(r.get("game_datetime") or r.get("stg_game_date"), selected_tz),
        "Lineups": _lineup_status(basis, both),
        "P(Over)": _fmt_pct(p_over) if has_odds and p_over is not None else "—",
        "Model Win%": _fmt_pct(_safe_float(r.get("calibrated_win_prob"))),
        "Market Win%": _fmt_pct(_safe_float(r.get("h2h_market_implied_prob"))) if has_odds else "—",
        "Posterior%": _fmt_pct(_safe_float(r.get("h2h_posterior_prob"))) if has_odds else "—",
        "Edge": _fmt_signed(h2h_edge) if has_odds else "—",
        "EV": _fmt_signed(_safe_float(r.get("ev"))) if has_odds else "—",
        "Kelly%": kelly_str,
    })

df_display = pd.DataFrame(display_rows)

st.dataframe(
    df_display.style.apply(_row_bg, axis=1),
    width='stretch',
    column_config={col: st.column_config.TextColumn(col, help=_COL_HELP[col]) for col in _COL_HELP},
    column_order=_STYLE_VISIBLE_COLS,
)

# ---------------------------------------------------------------------------
# IL injury warnings
# ---------------------------------------------------------------------------

if "home_injured_player_count" in df.columns or "away_injured_player_count" in df.columns:
    il_warnings = []
    for _, r in df.iterrows():
        home_il = int(r.get("home_injured_player_count") or 0)
        away_il = int(r.get("away_injured_player_count") or 0)
        if home_il > 0 or away_il > 0:
            parts = []
            if home_il > 0:
                parts.append(f"{r['home_team']}: {home_il} IL player(s)")
            if away_il > 0:
                parts.append(f"{r['away_team']}: {away_il} IL player(s)")
            il_warnings.append(f"{r['away_team']} @ {r['home_team']} — " + ", ".join(parts))
    if il_warnings:
        with st.expander("⚠ IL Players in Projected Lineups", expanded=True):
            for msg in il_warnings:
                st.warning(msg)

# ---------------------------------------------------------------------------
# Recommended Bets
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Recommended Bets")
st.caption(f"Games with |edge| ≥ {edge_threshold:.0%}. Moneyline edge is from the home team's perspective; negative edge = bet away.")

bet_rows = []
_provisional_bet_matchups: list[str] = []

for _, r in df.iterrows():
    if not bool(r.get("has_odds", False)):
        continue

    matchup = f"{r['away_team']} @ {r['home_team']}"
    both = bool(r.get("both_confirmed", False))
    # Status reflects whether the PREDICTION is lineup-confirmed (consistent with
    # the picks table and Game Insights) — not merely whether lineups are posted.
    _bet_basis = str(r.get("prediction_basis") or "provisional_pre_lineup")
    lineup_icon = lineup_status_emoji(_bet_basis, both)
    _bet_is_provisional = not is_confirmed(_bet_basis)

    h2h_edge = _safe_float(r.get("h2h_edge"))
    if h2h_edge is not None and abs(h2h_edge) >= edge_threshold:
        if h2h_edge > 0:
            direction = f"HOME ({r['home_team']})"
            kelly_val = _safe_float(r.get("kelly_capped"))
            kelly_exceeded = bool(r.get("kelly_exceeded_cap", False))
        else:
            direction = f"AWAY ({r['away_team']})"
            away_mkt = _safe_float(r.get("h2h_market_implied_prob"))
            if away_mkt is not None and 0 < away_mkt < 1.0:
                away_mkt_prob = 1.0 - away_mkt
                away_model_prob = 1.0 - float(r.get("calibrated_win_prob", 0.5))
                away_dec_odds = 1.0 / away_mkt_prob
                raw_k = (away_model_prob * (away_dec_odds - 1) - (1 - away_model_prob)) / (away_dec_odds - 1)
                kelly_val = min(raw_k, 0.10)
                kelly_exceeded = raw_k > 0.10
            else:
                kelly_val, kelly_exceeded = None, False

        kelly_str = f"{kelly_val:.1%}" if kelly_val is not None else "—"
        if kelly_exceeded:
            kelly_str += " ⚠"

        bet_rows.append({
            "Type": "Moneyline",
            "Matchup": matchup,
            "Bet": direction,
            "Edge": _fmt_signed(h2h_edge),
            "EV": _fmt_signed(_safe_float(r.get("ev"))),
            "Kelly%": kelly_str,
            "Lineups": lineup_icon,
        })
        if _bet_is_provisional and matchup not in _provisional_bet_matchups:
            _provisional_bet_matchups.append(matchup)

    totals_edge = _safe_float(r.get("totals_edge"))
    if totals_edge is not None and abs(totals_edge) >= edge_threshold:
        line = _safe_float(r.get("total_line_consensus"))
        direction_str = "OVER" if totals_edge > 0 else "UNDER"
        line_str = f"{line:.1f}" if line is not None else "?"

        t_kelly = _safe_float(r.get("totals_kelly_capped"))
        t_exceeded = bool(r.get("totals_kelly_exceeded_cap", False))
        t_kelly_str = f"{t_kelly:.1%}" if t_kelly is not None else "—"
        if t_exceeded:
            t_kelly_str += " ⚠"

        totals_model_prob = _safe_float(r.get("totals_model_prob"))
        over_mkt = _safe_float(r.get("over_prob_consensus"))
        if totals_model_prob and over_mkt and over_mkt > 0:
            dec = 1.0 / over_mkt
            t_ev = (totals_model_prob * (dec - 1)) - (1 - totals_model_prob)
        else:
            t_ev = None

        bet_rows.append({
            "Type": "Total Runs",
            "Matchup": matchup,
            "Bet": f"{direction_str} {line_str}",
            "Edge": _fmt_signed(totals_edge),
            "EV": _fmt_signed(t_ev),
            "Kelly%": t_kelly_str,
            "Lineups": lineup_icon,
        })
        if _bet_is_provisional and matchup not in _provisional_bet_matchups:
            _provisional_bet_matchups.append(matchup)

if _provisional_bet_matchups:
    st.warning(
        "⚠️ "
        + str(len(_provisional_bet_matchups))
        + " recommended bet(s) are on **provisional (pre-lineup) predictions** — "
        "these may be blind to the confirmed starter/lineup, so the edge isn't yet "
        "trustworthy. Wait for the post-lineup re-score before betting. Affected: "
        + ", ".join(_provisional_bet_matchups)
        + ". (Open Game Insights for the per-game detail.)"
    )

if bet_rows:
    df_bets = pd.DataFrame(bet_rows)

    def _bet_row_style(row: pd.Series) -> list[str]:
        # Green only when the PREDICTION is lineup-confirmed (✅). Lineups posted
        # but prediction still provisional (⚠️) or not posted (⏳) stay amber —
        # the edge isn't trustworthy until the post-lineup re-score.
        confirmed = row.get("Lineups") == "✅"
        bg = "background-color: #c6efce; color: #1e4620" if confirmed else "background-color: #ffeb9c; color: #3d2b00"
        return [bg] * len(row)

    bet_col_help = {
        "Type": "Bet market: Moneyline (win/loss) or Total Runs (over/under)",
        "Matchup": "Away @ Home",
        "Bet": "Recommended side to wager on",
        "Edge": "Model probability minus market-implied probability for the recommended side",
        "EV": "Expected value per unit wagered at current odds",
        "Kelly%": "Suggested bet size as % of bankroll (capped at 10%)",
        "Lineups": "✅ prediction is lineup-confirmed (post-lineup re-score)  |  ⚠️ lineups posted but prediction still provisional — re-score pending, edge not yet trustworthy  |  ⏳ lineups not posted yet (provisional)",
    }

    st.dataframe(
        df_bets.style.apply(_bet_row_style, axis=1),
        width='stretch',
        column_config={col: st.column_config.TextColumn(col, help=h) for col, h in bet_col_help.items()},
    )
else:
    st.info(f"No bets meet the {edge_threshold:.0%} edge threshold for {selected_date}.")

# ---------------------------------------------------------------------------
# Market Movement
# ---------------------------------------------------------------------------

st.divider()
with st.expander("📈 Market Movement", expanded=False):
    df_mv = load_movement(date_str)

    if df_mv.empty:
        st.info("No odds data found for this date.")
    else:
        max_snaps = int(df_mv["snapshot_count"].max()) if not df_mv.empty else 0
        if max_snaps <= 1:
            st.info(
                "Only one odds capture so far for this date — "
                "line movement will appear here as more snapshots are collected throughout the day."
            )

        _MV_VISIBLE = ["Matchup", "Home ML", "Away ML", "Total Line", "Captures", "Time Window"]
        _MV_COL_HELP = {
            "Matchup": "Away @ Home",
            "Home ML": "Consensus home-team moneyline: open → close (Δ pts). Pre-game snapshots only.  Blue = significant move (≥15 pts).",
            "Away ML": "Consensus away-team moneyline: open → close (Δ pts). Pre-game snapshots only.",
            "Total Line": "Consensus over/under line: open → close. Pre-game snapshots only.",
            "Captures": "Number of pre-game odds snapshots collected for this date",
            "Time Window": "Time range of first and last pre-game capture (UTC)",
        }
        _MV_SIG_THRESHOLD = 15

        mv_rows = []
        for _, r in df_mv.iterrows():
            matchup = f"{r['away_team']} @ {r['home_team']}"
            snaps = int(r["snapshot_count"])

            first_ts = r["first_ts"]
            last_ts = r["last_ts"]
            try:
                time_range = f"{pd.Timestamp(first_ts).strftime('%H:%M')} – {pd.Timestamp(last_ts).strftime('%H:%M')} UTC"
            except Exception:
                time_range = "—"

            home_cell, home_delta = _fmt_movement_cell(r.get("home_ml_open"), r.get("home_ml_current"))
            away_cell, away_delta = _fmt_movement_cell(r.get("away_ml_open"), r.get("away_ml_current"))

            total_open = _safe_float(r.get("total_line_open"))
            total_curr = _safe_float(r.get("total_line_current"))
            if total_open is not None and total_curr is not None:
                total_delta = total_curr - total_open
                if abs(total_delta) < 0.05:
                    total_cell = f"{total_curr:.1f}"
                    total_delta = 0.0
                else:
                    sign = "+" if total_delta > 0 else "−"
                    total_cell = f"{total_open:.1f} → {total_curr:.1f} ({sign}{abs(total_delta):.1f})"
            else:
                total_cell, total_delta = "—", 0.0

            mv_rows.append({
                "Matchup": matchup,
                "Home ML": home_cell,
                "Away ML": away_cell,
                "Total Line": total_cell,
                "Captures": snaps,
                "Time Window": time_range,
                "_home_delta": home_delta,
                "_away_delta": away_delta,
                "_total_delta": total_delta,
            })

        if mv_rows:
            df_mv_display = pd.DataFrame(mv_rows)

            def _mv_row_bg(row: pd.Series) -> list[str]:
                deltas = [
                    abs(float(row.get("_home_delta") or 0)),
                    abs(float(row.get("_away_delta") or 0)),
                    abs(float(row.get("_total_delta") or 0)),
                ]
                if max(deltas) >= _MV_SIG_THRESHOLD:
                    return ["background-color: #dce6f5; color: #1a3b6e"] * len(row)
                return [""] * len(row)

            st.dataframe(
                df_mv_display.style.apply(_mv_row_bg, axis=1),
                width='stretch',
                column_config={col: st.column_config.TextColumn(col, help=h) for col, h in _MV_COL_HELP.items()},
                column_order=_MV_VISIBLE,
            )

# ---------------------------------------------------------------------------
# Game Outcomes  (past dates only)
# ---------------------------------------------------------------------------

if not is_today:
    st.divider()
    st.subheader("Game Outcomes")

    df_outcomes = load_outcomes(date_str)

    if df_outcomes.empty:
        st.info("No final scores found for this date. Results may not be ingested yet.")
    else:
        outcome_map = {int(row["game_pk"]): row for _, row in df_outcomes.iterrows()}

        outcome_rows = []
        for _, r in df.iterrows():
            gk = int(r.get("game_pk", 0))
            outcome = outcome_map.get(gk)
            if outcome is None:
                continue

            matchup = f"{r['away_team']} @ {r['home_team']}"
            home_score = int(outcome["home_score"])
            away_score = int(outcome["away_score"])
            home_won = bool(outcome["home_is_winner"])
            total_runs = home_score + away_score
            score_str = f"{r['away_team']} {away_score} – {home_score} {r['home_team']}"

            # Moneyline correctness
            model_prob = _safe_float(r.get("calibrated_win_prob"))
            mkt_prob = _safe_float(r.get("h2h_market_implied_prob"))
            model_pick_home = model_prob is not None and model_prob > 0.5
            mkt_pick_home = mkt_prob is not None and mkt_prob > 0.5
            model_ml_correct = model_pick_home == home_won
            mkt_ml_correct = mkt_pick_home == home_won
            model_ml_pick = r["home_team"] if model_pick_home else r["away_team"]
            mkt_ml_pick = r["home_team"] if mkt_pick_home else r["away_team"]

            # Totals correctness
            line = _safe_float(r.get("total_line_consensus"))
            model_over_prob = _safe_float(r.get("p_over_ngboost"))
            mkt_over_prob = _safe_float(r.get("over_prob_consensus"))

            if line is not None and model_over_prob is not None:
                went_over = total_runs > line
                push = total_runs == line
                result_str = f"{total_runs} runs ({'push' if push else 'OVER' if went_over else 'UNDER'} {line:.1f})"
                model_over_pick = model_over_prob > 0.5
                mkt_over_pick = mkt_over_prob > 0.5 if mkt_over_prob is not None else None
                if push:
                    model_tot_cell = f"{'OVER' if model_over_pick else 'UNDER'} — Push"
                    mkt_tot_cell = f"{'OVER' if mkt_over_pick else 'UNDER'} — Push" if mkt_over_pick is not None else "—"
                else:
                    model_tot_correct = model_over_pick == went_over
                    mkt_tot_correct = (mkt_over_pick == went_over) if mkt_over_pick is not None else None
                    model_tot_cell = f"{'✅' if model_tot_correct else '❌'} {'OVER' if model_over_pick else 'UNDER'}"
                    mkt_tot_cell = (
                        f"{'✅' if mkt_tot_correct else '❌'} {'OVER' if mkt_over_pick else 'UNDER'}"
                        if mkt_tot_correct is not None else "—"
                    )
            else:
                result_str = f"{total_runs} runs"
                model_tot_cell = "—"
                mkt_tot_cell = "—"

            outcome_rows.append({
                "Matchup": matchup,
                "Score": score_str,
                "Totals Result": result_str,
                "Model ML": f"{'✅' if model_ml_correct else '❌'} {model_ml_pick}",
                "Market ML": f"{'✅' if mkt_ml_correct else '❌'} {mkt_ml_pick}",
                "Model Total": model_tot_cell,
                "Market Total": mkt_tot_cell,
            })

        if outcome_rows:
            df_out = pd.DataFrame(outcome_rows)

            def _outcome_bg(row: pd.Series) -> list[str]:
                styles = []
                for col, val in row.items():
                    if col in ("Model ML", "Market ML", "Model Total", "Market Total"):
                        if isinstance(val, str) and val.startswith("✅"):
                            styles.append("background-color: #c6efce; color: #1e4620")
                        elif isinstance(val, str) and val.startswith("❌"):
                            styles.append("background-color: #ffc7ce; color: #9c0006")
                        else:
                            styles.append("")
                    else:
                        styles.append("")
                return styles

            outcome_col_help = {
                "Matchup": "Away @ Home",
                "Score": "Final score: Away runs – Home runs",
                "Totals Result": "Actual total runs vs the consensus line",
                "Model ML": "✅/❌ — whether the model's moneyline pick was correct",
                "Market ML": "✅/❌ — whether the market's moneyline favorite was correct",
                "Model Total": "✅/❌ — whether the model's over/under pick was correct",
                "Market Total": "✅/❌ — whether the market's over/under lean was correct",
            }

            n_final = len(df_out)
            model_ml_wins = sum(1 for v in df_out["Model ML"] if v.startswith("✅"))
            mkt_ml_wins = sum(1 for v in df_out["Market ML"] if v.startswith("✅"))
            model_tot_wins = sum(1 for v in df_out["Model Total"] if v.startswith("✅"))
            mkt_tot_wins = sum(1 for v in df_out["Market Total"] if v.startswith("✅"))

            def _accuracy_delta(wins: int, total: int) -> tuple[str, str]:
                """Return (delta_str, delta_color) relative to 50% baseline."""
                pct = wins / total
                diff = pct - 0.50
                return f"{diff:+.0%} vs 50%", "normal" if diff >= 0 else "inverse"

            summary_cols = st.columns(4)
            d, dc = _accuracy_delta(model_ml_wins, n_final)
            summary_cols[0].metric("Model ML", f"{model_ml_wins}/{n_final} ({model_ml_wins/n_final:.0%})", d, delta_color=dc)
            d, dc = _accuracy_delta(mkt_ml_wins, n_final)
            summary_cols[1].metric("Market ML", f"{mkt_ml_wins}/{n_final} ({mkt_ml_wins/n_final:.0%})", d, delta_color=dc)
            n_tot = sum(1 for v in df_out["Model Total"] if v.startswith(("✅", "❌")))
            if n_tot:
                d, dc = _accuracy_delta(model_tot_wins, n_tot)
                summary_cols[2].metric("Model Totals", f"{model_tot_wins}/{n_tot} ({model_tot_wins/n_tot:.0%})", d, delta_color=dc)
                d, dc = _accuracy_delta(mkt_tot_wins, n_tot)
                summary_cols[3].metric("Market Totals", f"{mkt_tot_wins}/{n_tot} ({mkt_tot_wins/n_tot:.0%})", d, delta_color=dc)

            st.dataframe(
                df_out.style.apply(_outcome_bg, axis=1),
                width='stretch',
                column_config={col: st.column_config.TextColumn(col, help=h) for col, h in outcome_col_help.items()},
            )
        else:
            st.info("Predictions exist for this date but no final scores were found.")

# ---------------------------------------------------------------------------
# Kelly Criterion explainer
# ---------------------------------------------------------------------------

st.divider()
with st.expander("📖 How to use the Kelly Criterion (Kelly%)"):
    st.markdown("""
**What is a bankroll?**
Your **bankroll** is the total pool of money you have set aside specifically for betting — think of it as your betting budget,
kept separate from everyday spending. Kelly% tells you what fraction of that pool to wager on a single game.

For example, if you decide your daily betting budget is **$100**, that $100 is your bankroll for the day.
A Kelly% of **5%** means bet **$5** on that game. A Kelly% of **10%** means bet **$10**.

---

**What is the Kelly Criterion?**
It is a formula for deciding how much of your bankroll to bet on a given wager to maximize long-run growth.

**The formula**
$$
f = \\frac{b \\cdot p - q}{b}
$$
where:
- **f** = fraction of bankroll to bet (the Kelly%)
- **p** = your estimated probability of winning (Model Win% or Posterior%)
- **q** = probability of losing = 1 − p
- **b** = net odds received per unit wagered = (1 / Market Win%) − 1

---

**A worked example using a $100 daily budget**

Say the model gives a team a **55% win probability**, but the market implies only **50%** (even odds, +100 American):
- b = (1 / 0.50) − 1 = 1.0
- p = 0.55, q = 0.45
- f = (1.0 × 0.55 − 0.45) / 1.0 = **10%**

With a $100 bankroll: **bet $10 on this game.**
If you win, you collect $10 profit. If you lose, you're down $10 and have $90 left.

---

**Why the cap?**
Full Kelly can recommend very large bets, but model probability estimates are uncertain — real edges are often smaller than they appear.
This page **caps Kelly at 10% ($10 on a $100 budget)** as a hard safety limit.
Many experienced bettors use **half-Kelly** (divide by 2) to reduce day-to-day variance further.

**When Kelly% is negative**
A negative Kelly means the edge is against you on that side — do not bet it.

---

**Practical guidance ($100 daily budget)**

| Kelly% shown | Bet size | Suggested action |
|---|---|---|
| Negative | $0 | Skip — no edge |
| 0% – 2% | $0 – $2 | Very marginal; consider skipping |
| 2% – 5% | $2 – $5 | Small bet — edge exists but is thin |
| 5% – 10% | $5 – $10 | Solid edge; bet with confidence |
| 10% ⚠ | $10 | Cap hit; raw edge was even larger — bet the cap |

> **Important:** Kelly% is a *maximum* — it assumes your probability estimate is correct.
> Always wait for ✓ lineup confirmation before placing any bet; lineup changes can significantly shift true win probability.
""")
