"""Game Insights page — key model features and SHAP explanations per game."""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shap
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from app.utils.db import run_query
from app.utils.prediction_status import basis_message, is_confirmed
from app.utils.safe_conversions import safe_int
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
           -- post_lineup (4) > morning+odds (3) > fallback+odds (2) > morning-no-odds (1) > fallback-no-odds (0)
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
# Game Status (score if Final or Live)
# ===========================================================================

_GAME_STATE_SQL = """
SELECT
    abstract_game_state,
    detailed_state,
    home_score,
    away_score,
    game_date
FROM baseball_data.betting.stg_statsapi_games
WHERE game_pk = {game_pk}
LIMIT 1
"""


@st.cache_data(ttl=60)
def load_game_state(game_pk: int) -> pd.DataFrame:
    df = run_query(_GAME_STATE_SQL.format(game_pk=game_pk))
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
    return df


_gs_df = load_game_state(game_pk)
if not _gs_df.empty:
    _gs = _gs_df.iloc[0]
    _state = str(_gs.get("abstract_game_state") or "")
    if _state in ("Final", "Live"):
        _hs = _gs.get("home_score")
        _as = _gs.get("away_score")
        _detail = str(_gs.get("detailed_state") or _state)
        _score_str = f"{home_team_name} **{_hs}** — {away_team_name} **{_as}**"
        if _state == "Final":
            st.success(f"🏁 Final: {_score_str}")
        else:
            st.info(f"🔴 Live ({_detail}): {_score_str}")

# ===========================================================================
# Section 1 — Prediction Summary
# ===========================================================================

_PRED_SQL = """
SELECT
    pred_total_runs                                                          AS predicted_total_runs,
    calibrated_win_prob                                                      AS home_win_prob,
    h2h_market_implied_prob                                                  AS market_win_prob,
    calibrated_win_prob - h2h_market_implied_prob                            AS edge,
    h2h_kelly_fraction                                                       AS kelly_fraction,
    discriminative_coverage,
    imputed_discriminative_count,
    is_degraded,
    imputed_features,
    CASE
        WHEN prediction_type = 'post_lineup'                 THEN 'lineup_confirmed'
        WHEN COALESCE(data_source, '') = 'intraday_fallback' THEN 'provisional_fallback'
        ELSE 'provisional_pre_lineup'
    END                                                                      AS prediction_basis
FROM baseball_data.betting_ml.daily_model_predictions
WHERE game_pk = {game_pk}
ORDER BY
    CASE
        WHEN prediction_type = 'post_lineup'                                          THEN 4
        WHEN COALESCE(data_source, '') != 'intraday_fallback' AND has_odds = TRUE     THEN 3
        WHEN has_odds = TRUE                                                          THEN 2
        WHEN COALESCE(data_source, '') != 'intraday_fallback'                        THEN 1
        ELSE 0
    END DESC,
    inserted_at DESC
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
    market_win_prob = _safe_float(r.get("market_win_prob"))
    edge = _safe_float(r.get("edge"))
    kelly = _safe_float(r.get("kelly_fraction"))

    c1.metric("Predicted Total Runs", f"{total_runs:.2f}" if total_runs is not None else "N/A")
    c2.metric("Home Win Prob", _fmt_pct(home_win_prob))
    c3.metric("Market Win Prob", _fmt_pct(market_win_prob))
    edge_label = (f"{'+' if edge >= 0 else ''}{edge * 100:.1f}%") if edge is not None else "N/A"
    c4.metric("Edge", edge_label,
              delta=f"{edge * 100:.1f}" if edge is not None else None,
              delta_color="normal")
    c5.metric("Kelly Fraction", _fmt_pct(kelly))

    # Prediction basis — flag provisional predictions that may be blind to the
    # confirmed starter/lineup (the case where the edge is not yet trustworthy).
    # Wording is shared with every other page via app.utils.prediction_status.
    _basis = str(r.get("prediction_basis") or "provisional_pre_lineup")
    if is_confirmed(_basis):
        st.caption(basis_message(_basis))
    else:
        st.warning(basis_message(_basis))

    # A2.5 — discriminative-feature coverage banner. Distinguishes a fully-served
    # prediction from one built on imputed (league-prior) signals, so a degraded
    # pick doesn't look as authoritative as a fully-served one.
    _cov = _safe_float(r.get("discriminative_coverage"))
    _n_imp = _safe_float(r.get("imputed_discriminative_count"))
    if _cov is not None:
        if bool(r.get("is_degraded")):
            st.error(
                f"⚠️ **Degraded prediction** — only {_cov:.0%} of discriminative features "
                f"(ELO, lineup-vs-starter archetype, empirical-Bayes quality, sequential, "
                f"matchup splits) were served; {int(_n_imp or 0)} were imputed to league "
                f"priors. The model falls back toward a flat base-rate here — treat the win "
                f"probability with low confidence. See 'What's Driving This Pick?' below for "
                f"which drivers are imputed."
            )
        elif _n_imp and _n_imp > 0:
            st.caption(
                f"◐ {int(_n_imp)} discriminative feature(s) imputed to league priors "
                f"({_cov:.0%} coverage) — the prediction is slightly blunted but reliable. "
                f"Imputed drivers are marked below."
            )
        else:
            st.caption("✅ Full discriminative-feature coverage — every matchup signal was served.")

st.divider()

# ===========================================================================
# Bovada Lines (latest pre-game snapshot only)
# ===========================================================================

_BOVADA_LINES_SQL = """
WITH pre_game AS (
    SELECT
        o.market_key,
        o.outcome_name,
        o.outcome_price_american,
        o.outcome_point,
        o.is_home_outcome,
        o.is_away_outcome,
        o.ingestion_ts
    FROM baseball_data.betting.mart_odds_outcomes o
    JOIN baseball_data.betting.stg_statsapi_games g
        ON g.official_date = o.commence_date
    -- A1.9: resolve both feeds to team_id via the canonical lookup and join on
    -- team_id, instead of matching display names. Kills the silent line-drop for
    -- relocated/renamed franchises (StatsAPI "Athletics" vs odds "Oakland
    -- Athletics", "Cleveland Indians", etc.). Consumer contract: lower + strip
    -- the Parlay doubleheader marker before joining on name_lower.
    JOIN baseball_data.betting.dim_team_name_lookup gh
        ON gh.name_lower = lower(regexp_replace(trim(g.home_team_name), '^G[12] ', ''))
    JOIN baseball_data.betting.dim_team_name_lookup ga
        ON ga.name_lower = lower(regexp_replace(trim(g.away_team_name), '^G[12] ', ''))
    JOIN baseball_data.betting.dim_team_name_lookup oh
        ON oh.name_lower = lower(regexp_replace(trim(o.home_team), '^G[12] ', ''))
       AND oh.team_id = gh.team_id
    JOIN baseball_data.betting.dim_team_name_lookup oa
        ON oa.name_lower = lower(regexp_replace(trim(o.away_team), '^G[12] ', ''))
       AND oa.team_id = ga.team_id
    WHERE g.game_pk = {game_pk}
      AND o.bookmaker_key = 'bovada'
      AND o.ingestion_ts::TIMESTAMP_NTZ < g.game_date::TIMESTAMP_NTZ
)
SELECT
    market_key,
    outcome_name,
    outcome_price_american,
    outcome_point,
    is_home_outcome,
    is_away_outcome,
    ingestion_ts
FROM pre_game
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY market_key, outcome_name
    ORDER BY ingestion_ts DESC
) = 1
ORDER BY market_key, is_home_outcome DESC
"""


@st.cache_data(ttl=300)
def load_bovada_lines(game_pk: int) -> pd.DataFrame:
    df = run_query(_BOVADA_LINES_SQL.format(game_pk=game_pk))
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
    return df


def _fmt_american(v) -> str:
    if v is None:
        return "N/A"
    try:
        n = int(v)
        return f"+{n}" if n > 0 else str(n)
    except (TypeError, ValueError):
        return "N/A"


st.subheader("Bovada Lines")
_bov_df = load_bovada_lines(game_pk)

if _bov_df.empty:
    st.caption("No pre-game Bovada lines found for this game.")
else:
    _h2h = _bov_df[_bov_df["market_key"] == "h2h"]
    _tot = _bov_df[_bov_df["market_key"] == "totals"]

    _bov_col1, _bov_col2 = st.columns(2)

    with _bov_col1:
        st.markdown("**Moneyline (H2H)**")
        if _h2h.empty:
            st.caption("Not available.")
        else:
            _home_row = _h2h[_h2h["is_home_outcome"] == True]
            _away_row = _h2h[_h2h["is_home_outcome"] == False]
            _home_ml = _fmt_american(_home_row.iloc[0]["outcome_price_american"]) if not _home_row.empty else "N/A"
            _away_ml = _fmt_american(_away_row.iloc[0]["outcome_price_american"]) if not _away_row.empty else "N/A"
            _snap_ts = _h2h["ingestion_ts"].max()
            mc1, mc2 = st.columns(2)
            mc1.metric(home_team_name, _home_ml)
            mc2.metric(away_team_name, _away_ml)
            if _snap_ts is not None:
                st.caption(f"Snapshot: {pd.Timestamp(_snap_ts).strftime('%Y-%m-%d %H:%M')} UTC")

    with _bov_col2:
        st.markdown("**Total Runs (O/U)**")
        # A2.7 — this panel shows the Bovada MARKET line only. It is independent of
        # the model's own total (see "Predicted Total Runs" above) and of the totals
        # model probability — a missing line here never means the model failed.
        # The Parlay API's totals feed is sparse/late for many books (Bovada
        # included) even when their moneyline is live, so distinguish a genuine
        # not-yet-posted total from no Bovada coverage at all rather than showing a
        # bare "Not available".
        if _tot.empty:
            if not _h2h.empty:
                st.caption(
                    "⏳ Bovada total not yet posted — Bovada has a moneyline for this game, "
                    "but its over/under feed is sparse/late (a known upstream gap in the odds "
                    "provider's totals market, **not** a model issue). Check back closer to "
                    "first pitch."
                )
            else:
                st.caption("Not available — no pre-game Bovada lines for this game.")
        else:
            _over_row  = _tot[_tot["outcome_name"].str.lower() == "over"]
            _under_row = _tot[_tot["outcome_name"].str.lower() == "under"]
            _line      = _over_row.iloc[0]["outcome_point"] if not _over_row.empty else None
            _over_ml   = _fmt_american(_over_row.iloc[0]["outcome_price_american"]) if not _over_row.empty else "N/A"
            _under_ml  = _fmt_american(_under_row.iloc[0]["outcome_price_american"]) if not _under_row.empty else "N/A"
            _snap_ts   = _tot["ingestion_ts"].max()
            tc1, tc2, tc3 = st.columns(3)
            tc1.metric("Line", f"{_line}" if _line is not None else "N/A")
            tc2.metric("Over", _over_ml)
            tc3.metric("Under", _under_ml)
            if _snap_ts is not None:
                st.caption(f"Snapshot: {pd.Timestamp(_snap_ts).strftime('%Y-%m-%d %H:%M')} UTC")
                # Flag a stale total: Bovada's moneyline refreshed materially later
                # than its total, so the displayed line may be outdated.
                _h2h_ts = _h2h["ingestion_ts"].max() if not _h2h.empty else None
                if _h2h_ts is not None and pd.notna(_snap_ts):
                    _lag_h = (pd.Timestamp(_h2h_ts) - pd.Timestamp(_snap_ts)).total_seconds() / 3600.0
                    if _lag_h >= 3.0:
                        st.caption(
                            f"⚠️ This total is ~{_lag_h:.0f}h older than Bovada's moneyline "
                            f"snapshot — Bovada stopped refreshing its O/U for this game, so the "
                            f"line may be stale."
                        )

st.divider()

# ===========================================================================
# Section 1B — Projected Starters & Lineup
# ===========================================================================

_STARTERS_SQL = """
SELECT side, probable_pitcher_id, probable_pitcher_name
FROM baseball_data.betting.stg_statsapi_probable_pitchers
WHERE game_pk = {game_pk}
"""

_STARTER_STATS_SQL = """
WITH last_30 AS (
    SELECT
        pitcher_id,
        runs_allowed,
        hits_allowed,
        walks,
        strikeouts,
        batters_faced,
        innings_pitched,
        ROW_NUMBER() OVER (PARTITION BY pitcher_id ORDER BY game_date DESC) AS rn
    FROM baseball_data.betting.mart_starting_pitcher_game_log
    WHERE pitcher_id IN ({pitcher_ids})
      AND game_date < '{date}'
)
SELECT
    pitcher_id,
    COUNT(*)                                                                           AS starts,
    ROUND(SUM(runs_allowed) * 9.0 / NULLIF(SUM(innings_pitched), 0), 2)               AS ra9,
    ROUND((SUM(walks) + SUM(hits_allowed)) / NULLIF(SUM(innings_pitched), 0), 2)      AS whip,
    ROUND(SUM(strikeouts)::FLOAT / NULLIF(SUM(batters_faced), 0) * 100, 1)            AS k_pct
FROM last_30
WHERE rn <= 30
GROUP BY pitcher_id
"""

_LINEUP_SQL = """
SELECT
    home_away,
    slot_1_player_id,  slot_1_full_name,  slot_1_position,
    slot_2_player_id,  slot_2_full_name,  slot_2_position,
    slot_3_player_id,  slot_3_full_name,  slot_3_position,
    slot_4_player_id,  slot_4_full_name,  slot_4_position,
    slot_5_player_id,  slot_5_full_name,  slot_5_position,
    slot_6_player_id,  slot_6_full_name,  slot_6_position,
    slot_7_player_id,  slot_7_full_name,  slot_7_position,
    slot_8_player_id,  slot_8_full_name,  slot_8_position,
    slot_9_player_id,  slot_9_full_name,  slot_9_position
FROM baseball_data.betting.stg_statsapi_lineups_wide
WHERE game_pk = {game_pk}
"""

_BATTER_STATS_SQL = """
SELECT
    batter_id,
    ops_std      AS ops,
    xwoba_std    AS xwoba,
    pa_count_std AS pa
FROM baseball_data.betting.mart_batter_rolling_stats
WHERE batter_id IN ({batter_ids})
  AND game_year  = {season}
  AND game_date  < '{date}'
QUALIFY ROW_NUMBER() OVER (PARTITION BY batter_id ORDER BY game_date DESC) = 1
"""

_MATCHUP_SQL = """
WITH pa_level AS (
    SELECT
        batter_id,
        game_pk,
        at_bat_number,
        MAX(COALESCE(woba_denom, 0))                                               AS woba_denom,
        SUM(CASE WHEN woba_denom = 1 THEN COALESCE(xwoba, woba_value) ELSE 0 END) AS xwoba_num
    FROM baseball_data.betting.stg_batter_pitches
    WHERE pitcher_id  = {pitcher_id}
      AND batter_id   IN ({batter_ids})
      AND game_date   < '{date}'
    GROUP BY batter_id, game_pk, at_bat_number
)
SELECT
    batter_id,
    COUNT(*)                                                    AS pa,
    ROUND(SUM(xwoba_num) / NULLIF(SUM(woba_denom), 0), 3)     AS xwoba
FROM pa_level
GROUP BY batter_id
"""


@st.cache_data(ttl=300)
def load_starters(game_pk: int) -> pd.DataFrame:
    df = run_query(_STARTERS_SQL.format(game_pk=game_pk))
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
    return df


@st.cache_data(ttl=300)
def load_starter_stats(pitcher_ids: tuple[int, ...], date_str: str) -> pd.DataFrame:
    """Return trailing 30-start RA/9, WHIP, K% for each pitcher_id."""
    if not pitcher_ids:
        return pd.DataFrame()
    ids_str = ", ".join(str(p) for p in pitcher_ids)
    df = run_query(_STARTER_STATS_SQL.format(pitcher_ids=ids_str, date=date_str))
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
    return df


@st.cache_data(ttl=300)
def load_lineups(game_pk: int) -> pd.DataFrame:
    df = run_query(_LINEUP_SQL.format(game_pk=game_pk))
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
    return df


@st.cache_data(ttl=300)
def load_batter_stats(player_ids: tuple[int, ...], date_str: str) -> dict[int, dict]:
    """Season-to-date OPS + xwOBA for each player, latest row before date."""
    if not player_ids:
        return {}
    season = int(date_str[:4])
    ids_str = ", ".join(str(p) for p in player_ids)
    df = run_query(_BATTER_STATS_SQL.format(batter_ids=ids_str, season=season, date=date_str))
    if df.empty:
        return {}
    df.columns = [c.lower() for c in df.columns]
    return {
        int(r["batter_id"]): {
            "ops":   _safe_float(r.get("ops")),
            "xwoba": _safe_float(r.get("xwoba")),
            "pa":    safe_int(r.get("pa"), 0),
        }
        for _, r in df.iterrows()
    }


@st.cache_data(ttl=300)
def load_matchup_stats(batter_ids: tuple[int, ...], pitcher_id: int, date_str: str) -> dict[int, dict]:
    """Career PA + xwOBA per batter vs. a specific pitcher, through date_str."""
    if not batter_ids or pitcher_id is None:
        return {}
    ids_str = ", ".join(str(b) for b in batter_ids)
    df = run_query(_MATCHUP_SQL.format(pitcher_id=pitcher_id, batter_ids=ids_str, date=date_str))
    if df.empty:
        return {}
    df.columns = [c.lower() for c in df.columns]
    return {
        int(r["batter_id"]): {
            "pa":    safe_int(r.get("pa"), 0),
            "xwoba": _safe_float(r.get("xwoba")),
        }
        for _, r in df.iterrows()
    }


def _extract_player_ids(lineup_row: pd.Series | None) -> list[int]:
    """Return ordered list of player IDs (None → 0 skipped) from a wide lineup row."""
    if lineup_row is None:
        return []
    ids = []
    for slot in range(1, 10):
        pid = safe_int(lineup_row.get(f"slot_{slot}_player_id"))
        if pid is not None:
            ids.append(pid)
    return ids


def _lineup_table(
    lineup_row: pd.Series | None,
    batter_stats: dict[int, dict],
    matchup_stats: dict[int, dict],
    opp_sp_name: str | None = None,
) -> pd.DataFrame:
    """Build a 9-row DataFrame from a wide lineup row with batter stats."""
    show_matchup = opp_sp_name is not None
    rows = []
    for slot in range(1, 10):
        pid_raw = lineup_row.get(f"slot_{slot}_player_id") if lineup_row is not None else None
        pid = safe_int(pid_raw)
        name = lineup_row.get(f"slot_{slot}_full_name") if lineup_row is not None else None
        pos  = lineup_row.get(f"slot_{slot}_position")  if lineup_row is not None else None

        bs = batter_stats.get(pid, {}) if pid else {}
        ms = matchup_stats.get(pid, {}) if pid else {}

        ops_val   = bs.get("ops")
        xwoba_val = bs.get("xwoba")

        row: dict = {
            "#":     slot,
            "Player": name or "—",
            "Pos":   pos or "—",
            "OPS":   f"{ops_val:.3f}"   if ops_val   is not None else "—",
            "xwOBA": f"{xwoba_val:.3f}" if xwoba_val is not None else "—",
        }
        if show_matchup:
            pa = ms.get("pa", 0)
            mx = ms.get("xwoba")
            row["vs SP PA"]    = str(pa) if pa else "—"
            row["vs SP xwOBA"] = f"{mx:.3f}" if mx is not None and pa > 0 else "—"
        rows.append(row)
    return pd.DataFrame(rows)


st.subheader("Projected Starters & Lineup")

starters_df = load_starters(game_pk)
lineups_df = load_lineups(game_pk)

# Extract per-side data
def _get_side(df: pd.DataFrame, side_col: str, side_val: str) -> pd.Series | None:
    if df.empty:
        return None
    mask = df[side_col] == side_val
    return df[mask].iloc[0] if mask.any() else None

home_starter = _get_side(starters_df, "side", "home")
away_starter = _get_side(starters_df, "side", "away")
home_lineup_row = _get_side(lineups_df, "home_away", "home")
away_lineup_row = _get_side(lineups_df, "home_away", "away")

# Load trailing stats for both pitchers in one query
_pitcher_id_list = []
# safe_int guards the NaN case: a pandas NaN passes `is not None`, so int(NaN) would
# crash when a probable starter hasn't been announced yet for one side.
_home_pid = safe_int(home_starter.get("probable_pitcher_id")) if home_starter is not None else None
_away_pid = safe_int(away_starter.get("probable_pitcher_id")) if away_starter is not None else None
if _home_pid is not None:
    _pitcher_id_list.append(_home_pid)
if _away_pid is not None:
    _pitcher_id_list.append(_away_pid)

starter_stats_df = load_starter_stats(tuple(_pitcher_id_list), date_str)

def _get_pitcher_stats(pitcher_id: int | None) -> pd.Series | None:
    if pitcher_id is None or starter_stats_df.empty:
        return None
    mask = starter_stats_df["pitcher_id"] == pitcher_id
    return starter_stats_df[mask].iloc[0] if mask.any() else None

def _render_starter_stats(stats: pd.Series | None) -> None:
    """Render RA/9, WHIP, K% as metrics. Falls back to N/A gracefully."""
    ra9 = _safe_float(stats["ra9"]) if stats is not None else None
    whip = _safe_float(stats["whip"]) if stats is not None else None
    k_pct = _safe_float(stats["k_pct"]) if stats is not None else None
    starts = safe_int(stats.get("starts")) if stats is not None else None
    label_suffix = f" (last {starts} starts)" if starts else ""
    m1, m2, m3 = st.columns(3)
    m1.metric(f"RA/9{label_suffix}", f"{ra9:.2f}" if ra9 is not None else "N/A",
              help="Runs allowed per 9 innings over the last 30 starts. Proxy for ERA — no earned/unearned distinction.")
    m2.metric(f"WHIP{label_suffix}", f"{whip:.2f}" if whip is not None else "N/A",
              help="(Walks + Hits) / IP over the last 30 starts.")
    m3.metric(f"K%{label_suffix}", f"{k_pct:.1f}%" if k_pct is not None else "N/A",
              help="Strikeout rate (K / batters faced) over the last 30 starts.")

# Collect player IDs for stat lookups
_home_player_ids = _extract_player_ids(home_lineup_row)
_away_player_ids = _extract_player_ids(away_lineup_row)
_all_player_ids  = tuple(set(_home_player_ids + _away_player_ids))

batter_stats_map  = load_batter_stats(_all_player_ids, date_str)
home_matchup_map  = load_matchup_stats(tuple(_home_player_ids), _away_pid, date_str)
away_matchup_map  = load_matchup_stats(tuple(_away_player_ids), _home_pid, date_str)

_home_sp_name = home_starter["probable_pitcher_name"] if home_starter is not None else None
_away_sp_name = away_starter["probable_pitcher_name"] if away_starter is not None else None

lineup_col1, lineup_col2 = st.columns(2)

with lineup_col1:
    st.markdown(f"**{home_team_name}**")
    st.markdown(f"SP: **{_home_sp_name or 'TBD'}**")
    _render_starter_stats(_get_pitcher_stats(_home_pid))
    if home_lineup_row is not None:
        st.caption("OPS and xwOBA are season-to-date. 'vs SP' shows career PA and xwOBA against the opposing starter.")
        st.dataframe(
            _lineup_table(home_lineup_row, batter_stats_map, home_matchup_map, _away_sp_name),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("Lineup not yet confirmed.")

with lineup_col2:
    st.markdown(f"**{away_team_name}**")
    st.markdown(f"SP: **{_away_sp_name or 'TBD'}**")
    _render_starter_stats(_get_pitcher_stats(_away_pid))
    if away_lineup_row is not None:
        st.caption("OPS and xwOBA are season-to-date. 'vs SP' shows career PA and xwOBA against the opposing starter.")
        st.dataframe(
            _lineup_table(away_lineup_row, batter_stats_map, away_matchup_map, _home_sp_name),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("Lineup not yet confirmed.")

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
_REGISTRY_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml"


def _resolve_feature_cols_for(target: str) -> list[str]:
    """Return the feature column list for a given target's current production
    artifact, falling back to the global feature_columns.json if the registry
    has no per-target path."""
    import yaml
    if _REGISTRY_PATH.exists():
        registry = yaml.safe_load(_REGISTRY_PATH.read_text()) or {}
        entry = registry.get(target, {})
        feat_path_str = entry.get("feature_columns_path")
        if feat_path_str:
            p = Path(feat_path_str)
            if not p.is_absolute():
                p = _PROJECT_ROOT / p
            if p.exists():
                data = json.loads(p.read_text())
                return data["feature_cols"] if isinstance(data, dict) else data
    data = json.loads(_FEATURE_COLS_PATH.read_text())
    return data["feature_cols"] if isinstance(data, dict) else data


@st.cache_resource
def get_home_win_explainer() -> tuple[object, list[str]]:
    """Returns (shap_explainer, feature_columns) tuple for the home_win model.

    Branches on artifact type so v0 (PlattCalibratedXGBClassifier) and
    v1 (sklearn Pipeline / ElasticNet) both work.
    """
    model = load_model("home_win")
    feature_cols = _resolve_feature_cols_for("home_win")

    # v0: Platt-calibrated XGB → use TreeExplainer on the inner XGB classifier
    if hasattr(model, "xgb_classifier"):
        return shap.TreeExplainer(model.xgb_classifier), feature_cols

    # v1: sklearn Pipeline (elasticnet) → model-agnostic Explainer with
    # historical background. shap.LinearExplainer can't handle a full Pipeline
    # (preprocessor + estimator), so we wrap the prediction callable instead.
    if hasattr(model, "named_steps") or hasattr(model, "steps"):
        from betting_ml.utils.data_loader import load_features
        df_hist = load_features(min_games_played=15)
        X_bg = (
            df_hist.reindex(columns=feature_cols, fill_value=0.0)
            .fillna(0.0)
            .head(100)
        )
        if hasattr(model, "predict_proba"):
            predict_fn = lambda X: model.predict_proba(X)[:, 1]
        else:
            predict_fn = model.predict
        return shap.Explainer(predict_fn, X_bg), feature_cols

    # Fallback: assume tree-based
    return shap.TreeExplainer(model), feature_cols


@st.cache_resource
def get_total_runs_explainer() -> tuple[object, list[str]]:
    model = load_model("total_runs")
    feature_cols = _resolve_feature_cols_for("total_runs")
    return shap.TreeExplainer(model), feature_cols


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


def _imputed_feature_set(raw_df: pd.DataFrame, feature_cols: list[str]) -> set[str]:
    """A2.5 — which of `feature_cols` were NULL/absent in the raw feature vector.

    `_build_feature_df` silently fills these with 0.0, so a SHAP driver on an imputed
    feature would otherwise look like a genuine '0.000' contribution. This set lets the
    key-drivers panel mark such drivers as imputed instead of letting them appear to
    contribute normally (the elo_diff / archetype / R-per-game-at-park case for BOS/TB).
    """
    if raw_df is None or raw_df.empty:
        return set(feature_cols)
    imputed: set[str] = set()
    for col in feature_cols:
        if col not in raw_df.columns or pd.isna(raw_df.iloc[0][col]):
            imputed.add(col)
    return imputed


# ---------------------------------------------------------------------------
# Feature label + formatting helpers for the key-drivers panel
# ---------------------------------------------------------------------------

_FEATURE_LABELS: dict[str, str] = {
    # Home starter
    "home_starter_stuff_plus":             "Home SP: Stuff+",
    "home_starter_proj_fip":               "Home SP: Projected FIP",
    "home_starter_fastball_stuff_plus":    "Home SP: Fastball Stuff+",
    "home_starter_eb_k_pct":               "Home SP: K% (Bayes)",
    "home_starter_trailing_ra9_30g":       "Home SP: RA/9 (30g)",
    "home_starter_eb_xwoba_against":       "Home SP: xwOBA Against (Bayes)",
    "home_starter_trailing_fip_30g":       "Home SP: FIP (30g)",
    "home_starter_k_pct_30d":              "Home SP: K% (30d)",
    "home_starter_xwoba_against_30d":      "Home SP: xwOBA Against (30d)",
    "home_starter_whip_30d":               "Home SP: WHIP (30d)",
    "home_starter_csw_pct_season":         "Home SP: CSW% (Season)",
    "home_starter_bb_pct_30d":             "Home SP: BB% (30d)",
    "home_starter_hard_hit_pct_30d":       "Home SP: Hard Hit% (30d)",
    # Away starter
    "away_starter_stuff_plus":             "Away SP: Stuff+",
    "away_starter_proj_fip":               "Away SP: Projected FIP",
    "away_starter_fastball_stuff_plus":    "Away SP: Fastball Stuff+",
    "away_starter_eb_k_pct":               "Away SP: K% (Bayes)",
    "away_starter_trailing_ra9_30g":       "Away SP: RA/9 (30g)",
    "away_starter_eb_xwoba_against":       "Away SP: xwOBA Against (Bayes)",
    "away_starter_trailing_fip_30g":       "Away SP: FIP (30g)",
    "away_starter_k_pct_30d":              "Away SP: K% (30d)",
    "away_starter_xwoba_against_30d":      "Away SP: xwOBA Against (30d)",
    "away_starter_csw_pct_season":         "Away SP: CSW% (Season)",
    "away_starter_bb_pct_30d":             "Away SP: BB% (30d)",
    "away_starter_hard_hit_pct_30d":       "Away SP: Hard Hit% (30d)",
    # Home offense
    "home_off_xwoba_30d":                  "Home Off: xwOBA (30d)",
    "home_off_runs_per_game_30d":          "Home Off: R/G (30d)",
    "home_off_xwoba_std":                  "Home Off: xwOBA (season, z)",
    "home_off_runs_per_game_std":          "Home Off: R/G (season, z)",
    "home_off_xwoba_7d":                   "Home Off: xwOBA (7d)",
    "home_off_xwoba_14d":                  "Home Off: xwOBA (14d)",
    "home_off_hard_hit_pct_std":           "Home Off: Hard Hit% (season, z)",
    "home_off_bb_pct_std":                 "Home Off: BB% (season, z)",
    # Away offense
    "away_off_xwoba_30d":                  "Away Off: xwOBA (30d)",
    "away_off_runs_per_game_30d":          "Away Off: R/G (30d)",
    "away_off_xwoba_std":                  "Away Off: xwOBA (season, z)",
    "away_off_runs_per_game_std":          "Away Off: R/G (season, z)",
    "away_off_xwoba_7d":                   "Away Off: xwOBA (7d)",
    "away_off_xwoba_14d":                  "Away Off: xwOBA (14d)",
    "away_off_hard_hit_pct_std":           "Away Off: Hard Hit% (season, z)",
    "away_off_bb_pct_std":                 "Away Off: BB% (season, z)",
    # Bullpen
    "home_bp_eb_xwoba":                    "Home Bullpen: xwOBA (Bayes)",
    "home_bp_xwoba_against_30d":           "Home Bullpen: xwOBA Against (30d)",
    "home_bp_xwoba_against_14d":           "Home Bullpen: xwOBA Against (14d)",
    "home_bp_k_pct_30d":                   "Home Bullpen: K% (30d)",
    "home_bp_k_pct_14d":                   "Home Bullpen: K% (14d)",
    "home_bp_whiff_rate_30d":              "Home Bullpen: Whiff% (30d)",
    "home_bp_innings_pitched_14d":         "Home Bullpen: IP (14d)",
    "home_bp_bb_pct_30d":                  "Home Bullpen: BB% (30d)",
    "away_bp_eb_xwoba":                    "Away Bullpen: xwOBA (Bayes)",
    "away_bp_xwoba_against_30d":           "Away Bullpen: xwOBA Against (30d)",
    "away_bp_xwoba_against_14d":           "Away Bullpen: xwOBA Against (14d)",
    "away_bp_k_pct_30d":                   "Away Bullpen: K% (30d)",
    "away_bp_k_pct_14d":                   "Away Bullpen: K% (14d)",
    "away_bp_whiff_rate_30d":              "Away Bullpen: Whiff% (30d)",
    "away_bp_innings_pitched_14d":         "Away Bullpen: IP (14d)",
    "away_bp_bb_pct_30d":                  "Away Bullpen: BB% (30d)",
    # Lineup matchup
    "home_lineup_vs_away_starter_xwoba_adj":  "Home Lineup vs Away SP: xwOBA",
    "away_lineup_vs_home_starter_xwoba_adj":  "Away Lineup vs Home SP: xwOBA",
    "home_lineup_xwoba_vs_starter_archetype": "Home Lineup vs SP Archetype: xwOBA",
    "away_lineup_xwoba_vs_starter_archetype": "Away Lineup vs SP Archetype: xwOBA",
    "home_lineup_avg_xwoba_vs_cluster":       "Home Lineup vs SP Cluster: xwOBA",
    "away_lineup_avg_xwoba_vs_cluster":       "Away Lineup vs SP Cluster: xwOBA",
    "home_lineup_vs_away_starter_k_pct_adj":  "Home Lineup vs Away SP: K%",
    "away_lineup_vs_home_starter_k_pct_adj":  "Away Lineup vs Home SP: K%",
    # Sequential / team-level
    "home_team_sequential_win_prob":       "Home Team: Sequential Win Prob",
    "away_team_sequential_win_prob":       "Away Team: Sequential Win Prob",
    "home_team_sequential_woba":           "Home Team: Sequential wOBA",
    "away_team_sequential_woba":           "Away Team: Sequential wOBA",
    "home_team_sequential_bullpen_xwoba":  "Home Bullpen: Sequential xwOBA",
    "away_team_sequential_bullpen_xwoba":  "Away Bullpen: Sequential xwOBA",
    "home_team_oaa_blended":               "Home Defense: OAA",
    "away_team_oaa_prior_season":          "Away Defense: OAA",
    # Game-level
    "elo_diff":                            "ELO Differential (Home − Away)",
    "park_run_factor_3yr":                 "Park Run Factor (3yr)",
    "pythagorean_win_exp_diff":            "Pythagorean Win Exp Diff",
    "total_line_movement":                 "Total Line Movement",
    "total_line_std":                      "Total Line (Implied)",
    # Weather
    "humidity_pct":                        "Humidity",
    "wind_speed_mph":                      "Wind Speed",
    "temp_f":                              "Temperature",
}


@st.cache_resource
def _load_feature_descriptions() -> dict[str, str]:
    """Parse all dbt models/feature schema.yml files and return col→description."""
    import glob
    import yaml as _yaml
    desc: dict[str, str] = {}
    pattern = str(_PROJECT_ROOT / "dbt" / "models" / "**" / "*.yml")
    for path in glob.glob(pattern, recursive=True):
        if "dbt_packages" in path:
            continue
        try:
            schema = _yaml.safe_load(open(path))
            if not schema:
                continue
            for model in schema.get("models", []):
                for col in model.get("columns", []):
                    if col.get("description"):
                        desc[col["name"].lower()] = col["description"]
        except Exception:
            pass
    return desc


_ENTITY_TOKENS = {
    "bp":      "Bullpen",
    "off":     "Offense",
    "starter": "SP",
    "lineup":  "Lineup",
    "team":    "Team",
    "pit":     "Pitching",
    "avg":     "Lineup Avg",
    "vs":      "vs",
}
_STAT_TOKENS = {
    "xwoba":   "xwOBA",
    "woba":    "wOBA",
    "fip":     "FIP",
    "ra9":     "RA/9",
    "whip":    "WHIP",
    "era":     "ERA",
    "csw":     "CSW",
    "oaa":     "OAA",
    "elo":     "ELO",
    "iso":     "ISO",
    "ops":     "OPS",
    "eb":      "Bayes",
    "proj":    "Proj",
    "adj":     "Adj",
    "pct":     "%",
    "std":     "(z-score)",
}


def _prettify_feature_name(name: str) -> str:
    """Token-aware prettifier: home_bp_eb_uncertainty → 'Home Bullpen: Bayes Uncertainty'."""
    parts = name.split("_")
    if not parts:
        return name

    side = ""
    idx = 0
    if parts[0] in ("home", "away"):
        side = parts[0].title()
        idx = 1

    entity = ""
    if idx < len(parts) and parts[idx] in _ENTITY_TOKENS:
        entity = _ENTITY_TOKENS[parts[idx]]
        idx += 1

    tokens = parts[idx:]
    expanded: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        # Multi-token patterns
        if t == "k" and i + 1 < len(tokens) and tokens[i + 1] == "pct":
            expanded.append("K%"); i += 2; continue
        if t == "bb" and i + 1 < len(tokens) and tokens[i + 1] == "pct":
            expanded.append("BB%"); i += 2; continue
        if t == "hard" and i + 1 < len(tokens) and tokens[i + 1] == "hit":
            if i + 2 < len(tokens) and tokens[i + 2] == "pct":
                expanded.append("Hard Hit%"); i += 3
            else:
                expanded.append("Hard Hit"); i += 2
            continue
        if t == "stuff" and i + 1 < len(tokens) and tokens[i + 1] == "plus":
            expanded.append("Stuff+"); i += 2; continue
        if t == "runs" and i + 1 < len(tokens) and tokens[i + 1] == "per" and i + 2 < len(tokens) and tokens[i + 2] == "game":
            expanded.append("R/G"); i += 3; continue
        if t == "win" and i + 1 < len(tokens) and tokens[i + 1] in ("prob", "exp"):
            expanded.append(f"Win {tokens[i+1].title()}"); i += 2; continue
        # Time windows
        if t in ("30d", "14d", "7d", "30g", "3yr"):
            expanded.append(f"({t})"); i += 1; continue
        if t == "season":
            expanded.append("(Season)"); i += 1; continue
        # Stat tokens
        expanded.append(_STAT_TOKENS.get(t, t.title()))
        i += 1

    stat_str = " ".join(expanded)
    prefix = f"{side} {entity}".strip() if (side or entity) else ""
    return f"{prefix}: {stat_str}" if prefix and stat_str else (prefix or stat_str or name)


def _get_feature_label(name: str) -> str:
    return _FEATURE_LABELS.get(name, _prettify_feature_name(name))


def _format_feature_value(name: str, val: float) -> str:
    if val is None or (isinstance(val, float) and val != val):
        return "N/A"
    n = name.lower()
    if any(x in n for x in ("k_pct", "bb_pct", "whiff_rate", "csw_pct", "hard_hit_pct", "swing_pct", "contact_pct")):
        return f"{val * 100:.1f}%"
    if "humidity" in n:
        return f"{val:.0f}%"
    if "temp" in n:
        return f"{val:.0f}°F"
    if "wind" in n:
        return f"{val:.0f} mph"
    if any(x in n for x in ("xwoba", "woba", "iso")):
        return f"{val:.3f}"
    if "stuff_plus" in n:
        return f"{val:.0f}"
    if any(x in n for x in ("fip", "ra9", "whip")):
        return f"{val:.2f}"
    if "runs_per_game" in n or "run_factor" in n:
        return f"{val:.2f}"
    if "innings_pitched" in n or n.endswith("_ip"):
        return f"{val:.1f}"
    if "win_prob" in n or "win_exp" in n:
        return f"{val:.3f}"
    if "line" in n:
        return f"{val:.1f}"
    if "elo" in n:
        return f"{val:+.0f}" if "diff" in n else f"{val:.0f}"
    if n.endswith("_std") or n.endswith("_z"):
        return f"{val:+.2f}σ"
    return f"{val:.3f}"


def _compute_shap_drivers(
    explainer,
    X_df: pd.DataFrame,
    coverage: float = 0.75,
    min_drivers: int = 3,
    max_drivers: int = 10,
) -> "pd.DataFrame | None":
    """Compute SHAP values and return the top drivers as a DataFrame.

    Walks down the |SHAP|-sorted list until cumulative impact reaches
    `coverage` of the total, clamped to [min_drivers, max_drivers].
    """
    try:
        n_features = X_df.shape[1]
        try:
            sv = explainer(X_df, max_evals=2 * n_features + 64)
        except TypeError:
            sv = explainer(X_df)

        exp = sv[0]
        df = pd.DataFrame({
            "feature":       list(exp.feature_names),
            "shap_value":    exp.values,
            "feature_value": exp.data,
        })
        df["abs_shap"] = df["shap_value"].abs()
        df = df.sort_values("abs_shap", ascending=False).reset_index(drop=True)

        total_abs = df["abs_shap"].sum()
        cumulative = 0.0
        cutoff = min_drivers
        for i, row in df.iterrows():
            cumulative += row["abs_shap"]
            if i + 1 >= min_drivers and cumulative / total_abs >= coverage:
                cutoff = i + 1
                break
            if i + 1 >= max_drivers:
                cutoff = max_drivers
                break

        return df.head(cutoff)
    except Exception:
        return None


def _render_key_drivers(
    explainer,
    X_df: pd.DataFrame,
    model_label: str,
    pos_label: str,
    neg_label: str,
    imputed_set: set[str] | None = None,
) -> None:
    st.markdown(f"**{model_label}**")
    drivers = _compute_shap_drivers(explainer, X_df)
    if drivers is None or drivers.empty:
        st.caption("Driver analysis unavailable for this game.")
        return

    feat_descs = _load_feature_descriptions()
    imputed_set = imputed_set or set()
    _n_imputed_shown = 0

    for _, row in drivers.iterrows():
        feat = row["feature"]
        shap_val = float(row["shap_value"])
        feat_val = row["feature_value"]
        label = _get_feature_label(feat)
        is_imputed = feat in imputed_set
        direction = pos_label if shap_val > 0 else neg_label
        arrow = "↑" if shap_val > 0 else "↓"
        impact = f"{arrow} {abs(shap_val):.3f}"

        # A2.5 — an imputed driver was NULL in the source and filled with a league
        # prior; its value is not real, so show 'imputed' (not the 0.000 fill) and
        # grey it out so it doesn't read as a genuine contribution.
        if is_imputed:
            _n_imputed_shown += 1
            val_str = "imputed"
            color = "#888"
            label = f"{label} ⚠️"
        else:
            val_str = _format_feature_value(feat, float(feat_val))
            color = "#2ecc71" if shap_val > 0 else "#e74c3c"

        # Tooltip: first sentence of schema.yml description, or nothing
        raw_desc = feat_descs.get(feat, "")
        tooltip = raw_desc.split(".")[0].strip() if raw_desc else ""
        if is_imputed:
            tooltip = (
                "This feature was missing for this game and imputed to a league prior — "
                "its contribution is not based on real matchup data. "
            ) + tooltip
        # Escape quotes so they don't break the HTML title attribute
        tooltip_attr = f' title="{tooltip}"' if tooltip else ""

        label_html = (
            f'<span style="flex:2;font-size:0.84rem;cursor:default;'
            f'border-bottom:1px dotted #666;"{tooltip_attr}>{label}</span>'
            if tooltip else
            f'<span style="flex:2;font-size:0.84rem;">{label}</span>'
        )

        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:5px 10px;margin-bottom:3px;border-radius:5px;background:rgba(255,255,255,0.04);">'
            f'{label_html}'
            f'<span style="flex:1;text-align:center;font-size:0.84rem;color:#aaa;font-style:'
            f'{"italic" if is_imputed else "normal"};">{val_str}</span>'
            f'<span style="flex:1;text-align:right;font-size:0.84rem;font-weight:600;color:{color};">'
            f'{impact} {direction}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if _n_imputed_shown:
        st.caption(
            f"⚠️ {_n_imputed_shown} of the drivers above were imputed to a league prior "
            f"(missing for this game) — their contribution is not based on real matchup data."
        )


st.subheader("What's Driving This Pick?")
st.caption(
    "The features with the greatest influence on this game's prediction, ranked by SHAP impact. "
    "Only features accounting for the most significant share of the model's decision are shown — "
    "green (↑) pushes toward the listed outcome, red (↓) pushes against it. "
    "The impact score is in the model's output space (log-odds for home win; expected runs for total)."
)

raw_feat_df = load_full_feature_vector(game_pk, date_str)

if raw_feat_df.empty:
    st.warning("No feature data found for this game — driver analysis skipped.")
else:
    driver_col1, driver_col2 = st.columns(2)

    with driver_col1:
        try:
            hw_explainer, hw_feature_cols = get_home_win_explainer()
            X_hw = _build_feature_df(raw_feat_df, hw_feature_cols)
            hw_imputed = _imputed_feature_set(raw_feat_df, hw_feature_cols)
            _render_key_drivers(hw_explainer, X_hw, "Home Win Model", "→ Home Win", "→ Away Win", hw_imputed)
        except Exception as exc:
            st.warning(f"Home Win driver analysis failed: {exc}")

    with driver_col2:
        try:
            tr_explainer, tr_feature_cols = get_total_runs_explainer()
            X_tr = _build_feature_df(raw_feat_df, tr_feature_cols)
            tr_imputed = _imputed_feature_set(raw_feat_df, tr_feature_cols)
            _render_key_drivers(tr_explainer, X_tr, "Total Runs Model", "→ Over", "→ Under", tr_imputed)
        except Exception as exc:
            st.warning(f"Total Runs driver analysis failed: {exc}")

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
        safe_int(row.get("home_team_id")),
        safe_int(row.get("away_team_id")),
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
            st.dataframe(home_form, width='stretch', hide_index=True)

with form_col2:
    if away_team_id is None:
        st.warning("Could not resolve away team ID.")
    else:
        away_form = load_recent_form(away_team_id, game_date_str or date_str)
        st.markdown(f"**Away: {away_team_name} — Last 10{_form_record(away_form)}**")
        if away_form.empty:
            st.info("No prior games found for this team.")
        else:
            st.dataframe(away_form, width='stretch', hide_index=True)

st.divider()

# ===========================================================================
# Section 5 — Model Accuracy for These Teams (last 20 scored games)
# ===========================================================================

_TEAM_MODEL_ACCURACY_SQL = """
WITH best_pred AS (
    SELECT
        game_pk,
        pred_total_runs,
        calibrated_win_prob,
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
        ) AS rn
    FROM baseball_data.betting_ml.daily_model_predictions
),
team_games AS (
    SELECT
        g.home_score + g.away_score                                                     AS actual_total,
        p.pred_total_runs,
        CASE WHEN g.home_score > g.away_score THEN 1 ELSE 0 END                        AS home_won,
        CASE WHEN p.calibrated_win_prob > 0.5  THEN 1 ELSE 0 END                       AS model_picked_home
    FROM baseball_data.betting.stg_statsapi_games g
    JOIN best_pred p ON g.game_pk = p.game_pk AND p.rn = 1
    WHERE (g.home_team_id = {team_id} OR g.away_team_id = {team_id})
      AND g.abstract_game_state = 'Final'
      AND g.home_score IS NOT NULL
      AND g.away_score IS NOT NULL
      AND p.pred_total_runs IS NOT NULL
      AND p.calibrated_win_prob IS NOT NULL
    ORDER BY g.game_date DESC
    LIMIT 20
)
SELECT
    COUNT(*)                                                                            AS games,
    ROUND(AVG(CASE WHEN home_won = model_picked_home THEN 1.0 ELSE 0.0 END) * 100, 1) AS win_acc_pct,
    ROUND(AVG(ABS(pred_total_runs - actual_total)), 2)                                 AS total_runs_mae
FROM team_games
"""


@st.cache_data(ttl=600)
def load_team_model_accuracy(team_id: int) -> pd.DataFrame:
    df = run_query(_TEAM_MODEL_ACCURACY_SQL.format(team_id=team_id))
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
    return df


def _render_team_accuracy(team_name: str, team_id: int | None) -> None:
    st.markdown(f"**{team_name}**")
    if team_id is None:
        st.caption("Team ID unavailable.")
        return
    acc_df = load_team_model_accuracy(team_id)
    if acc_df.empty:
        st.caption("Not enough data.")
        return
    r = acc_df.iloc[0]
    games = safe_int(r.get("games"), 0)
    if games == 0:
        st.caption("No scored games found.")
        return
    win_acc   = _safe_float(r.get("win_acc_pct"))
    total_mae = _safe_float(r.get("total_runs_mae"))
    ma1, ma2, ma3 = st.columns(3)
    ma1.metric(
        "Win Pick Acc",
        f"{win_acc:.1f}%" if win_acc is not None else "N/A",
        help="% of games where the model picked the correct winner (home_win_prob > 0.5 vs actual), last 20 scored games.",
    )
    ma2.metric(
        "Total Runs MAE",
        f"{total_mae:.2f}" if total_mae is not None else "N/A",
        help="Mean absolute error of the model's total runs prediction vs actual, last 20 scored games.",
    )
    ma3.metric(
        "Sample (n)",
        str(games),
        help="Number of games with model predictions and final scores used in the calculation.",
    )


st.subheader("Model Accuracy — These Teams (Last 20 Games)")

acc_col1, acc_col2 = st.columns(2)

with acc_col1:
    _render_team_accuracy(home_team_name, home_team_id)

with acc_col2:
    _render_team_accuracy(away_team_name, away_team_id)
