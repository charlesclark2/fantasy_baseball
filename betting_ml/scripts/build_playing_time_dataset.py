"""build_playing_time_dataset.py — Story 33.1 Task 1b: the playing-time CANDIDATE PANEL.

Builds the leakage-safe training panel for the player playing-time probability model
(33.1) from the `mart_player_game_starts` fact (Task 1a). For each historical team-game,
the CANDIDATE set = players who started at least one of the team's recent games (strictly
PRIOR, so no leakage), and for each candidate we attach:
  - did_start ∈ {0,1}            (the LABEL — did this candidate start THIS game)
  - start_rate_{10,25,50}        (fraction of the team's last K PRIOR games the player started)
  - starts_{10,25,50}            (raw prior-start counts in window; the sample-size signal)
  - team_games_in_window_50      (denominator: team games available in the 50-game window)
  - days_since_last_start        (rest / recency)
  - is_injured                   (point-in-time from feature_pregame_injury_status; 2021+)
  - batting_order_if_started     (the slot, NULL when did_start=0 — diagnostics only)

Grain: one row per (game_pk, side, player_id) candidate. Panel = training data for Task 2.

LEAKAGE GUARD: every rolling window uses M.shift(1) — the current game's own start is
EXCLUDED, so a candidate's features depend only on strictly-prior team games. The candidate
set itself is prior-derived (started a prior game in the 50-game window), so a player never
appears for a game before their first start, and a traded/benched player decays out over K
games. did_start (the label) is the only column that reads the current game.

SCOPE (v1): OVERALL start-rates only. The vs-LHP/RHP platoon split is a documented fast-follow
— it needs the opposing-starter handedness, which mart_starting_pitcher_game_log does NOT carry
(it must be derived from pitch p_throws); wired in a follow-up. Overall start-rate is the
dominant P(start) signal (regulars ~95%+, bench/platoon lower), so the panel is useful now.

Runtime: loads ~465k start rows + builds a per-team rolling panel → minutes. HAND OFF.

Usage:
    uv run python betting_ml/scripts/build_playing_time_dataset.py
    uv run python betting_ml/scripts/build_playing_time_dataset.py --smoke   # synthetic self-test, no Snowflake
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

_OUT = PROJECT_ROOT / "betting_ml" / "data" / "playing_time_panel_33_1.parquet"
_WINDOWS = (10, 25, 50)
_CAND_WINDOW = 50  # a player is a candidate for game G if they started ≥1 of the team's last 50 prior games

_STARTS_SQL = """
SELECT game_pk, official_date, game_year, team, opp_team, side, player_id, batting_order
FROM baseball_data.betting.mart_player_game_starts
"""

_INJURY_SQL = """
SELECT player_id, is_injured, valid_from, valid_to
FROM baseball_data.betting_features.feature_pregame_injury_status
"""


def _team_panel(team_starts: pd.DataFrame) -> pd.DataFrame:
    """Candidate panel for ONE team. `team_starts` = actual-start rows for the team."""
    # team-games in date order (the team plays each game_pk exactly once, one side)
    tg = (team_starts[["game_pk", "side", "official_date", "game_year"]]
          .drop_duplicates("game_pk")
          .sort_values(["official_date", "game_pk"])
          .reset_index(drop=True))
    tg["gidx"] = np.arange(len(tg))
    gidx = dict(zip(tg["game_pk"], tg["gidx"]))

    g = team_starts.assign(gidx=team_starts["game_pk"].map(gidx))
    # M[gidx, player] = 1 if the player started that game
    M = (g.assign(_v=1)
           .pivot_table(index="gidx", columns="player_id", values="_v", aggfunc="max", fill_value=0)
           .reindex(range(len(tg)), fill_value=0)
           .sort_index())
    Mprior = M.shift(1)                                   # exclude the current game (leakage guard)
    ones_prior = pd.Series(1.0, index=M.index).shift(1)   # prior-game indicator

    feats = {}
    for K in _WINDOWS:
        sK = Mprior.rolling(K, min_periods=1).sum()
        gK = ones_prior.rolling(K, min_periods=1).sum()
        feats[f"starts_{K}"] = sK
        feats[f"start_rate_{K}"] = sK.div(gK, axis=0)
    team_games_in_window = ones_prior.rolling(_CAND_WINDOW, min_periods=1).sum()

    # days since last prior start, per player (ffill the start date, then shift to prior)
    date_arr = tg["official_date"].to_numpy(dtype="datetime64[ns]")
    start_dates = np.where(M.to_numpy() == 1, date_arr[:, None], np.datetime64("NaT"))
    start_dates = pd.DataFrame(start_dates, index=M.index, columns=M.columns).ffill().shift(1)
    days_since = pd.DataFrame((date_arr[:, None] - start_dates.to_numpy()) / np.timedelta64(1, "D"),
                              index=M.index, columns=M.columns)

    cand = feats[f"starts_{_CAND_WINDOW}"] > 0            # candidate = ≥1 prior start in window
    # melt each matrix to long on the candidate cells
    rows = cand.stack()
    rows = rows[rows].index                                # MultiIndex (gidx, player_id) of candidates
    if len(rows) == 0:
        return pd.DataFrame()
    gi = rows.get_level_values(0).to_numpy()
    pid = rows.get_level_values(1).to_numpy()

    def _pull(df):
        return df.to_numpy()[gi, [df.columns.get_loc(p) for p in pid]]

    panel = pd.DataFrame({
        "gidx": gi, "player_id": pid,
        "did_start": _pull(M).astype(int),
        "days_since_last_start": _pull(days_since),
        "team_games_in_window_50": team_games_in_window.to_numpy()[gi],
    })
    for K in _WINDOWS:
        panel[f"starts_{K}"] = _pull(feats[f"starts_{K}"])
        panel[f"start_rate_{K}"] = _pull(feats[f"start_rate_{K}"])

    panel = panel.merge(tg[["gidx", "game_pk", "side", "official_date", "game_year"]], on="gidx", how="left")
    panel = panel.merge(
        g[["game_pk", "player_id", "batting_order"]].rename(columns={"batting_order": "batting_order_if_started"}),
        on=["game_pk", "player_id"], how="left")
    panel["team"] = team_starts["team"].iloc[0]
    return panel.drop(columns=["gidx"])


def _attach_injury(panel: pd.DataFrame, inj: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time is_injured per (player_id, official_date). No record → not injured."""
    if inj.empty:
        panel["is_injured"] = False
        return panel
    inj = inj.copy()
    inj["valid_from"] = pd.to_datetime(inj["valid_from"])
    inj["valid_to"] = pd.to_datetime(inj["valid_to"])
    inj = inj.sort_values("valid_from")
    p = panel.sort_values("official_date").copy()
    p["official_date"] = pd.to_datetime(p["official_date"])
    merged = pd.merge_asof(p, inj, left_on="official_date", right_on="valid_from",
                           by="player_id", direction="backward")
    # the most-recent IL record at/before the game applies only while still open at game time.
    # `== True` maps NaN (no IL record) → False cleanly, avoiding the object-dtype fillna downcast.
    still_open = merged["valid_to"].isna() | (merged["valid_to"] > merged["official_date"])
    merged["is_injured"] = ((merged["is_injured"] == True) & still_open).astype(bool)  # noqa: E712
    return merged.drop(columns=["valid_from", "valid_to"])


def build(starts: pd.DataFrame, inj: pd.DataFrame) -> pd.DataFrame:
    parts = [_team_panel(g) for _, g in starts.groupby("team", sort=False)]
    panel = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    panel = _attach_injury(panel, inj)
    return panel


def _smoke() -> None:
    """Synthetic self-test of the leakage-safe panel logic (no Snowflake)."""
    rng = np.random.RandomState(0)
    rows = []
    base = pd.Timestamp("2024-04-01")
    # 2 teams, 60 games each; a regular (always starts) + a platoon (50%) + a callup (from game 40)
    for team in ("AAA", "BBB"):
        for gi in range(60):
            gpk = hash((team, gi)) % 10_000_000
            d = base + pd.Timedelta(days=gi)
            starters = [101]  # regular
            if rng.rand() < 0.5:
                starters.append(102)  # platoon
            if gi >= 40:
                starters.append(103)  # callup
            for slot, p in enumerate(starters, 1):
                rows.append(dict(game_pk=gpk, official_date=d, game_year=2024, team=team,
                                 opp_team="ZZZ", side="home", player_id=p, batting_order=slot))
    starts = pd.DataFrame(rows)
    panel = build(starts, pd.DataFrame(columns=["player_id", "is_injured", "valid_from", "valid_to"]))

    reg = panel[panel.player_id == 101]
    callup = panel[panel.player_id == 103]
    assert (reg["start_rate_25"].dropna() > 0.9).mean() > 0.8, "regular should have high start-rate"
    # leakage check: the callup must NOT be a candidate before its first start (game 40)
    early_callup = callup[callup["official_date"] < base + pd.Timedelta(days=40)]
    assert len(early_callup) == 0, "callup leaked as candidate before first start"
    # did_start is 0/1 and present
    assert set(panel["did_start"].unique()) <= {0, 1}
    print(f"  smoke: panel rows={len(panel)}, players={panel.player_id.nunique()}, "
          f"mean did_start={panel.did_start.mean():.3f}")
    print(f"  regular start_rate_25 mean={reg['start_rate_25'].mean():.3f}  "
          f"callup first candidate date={callup['official_date'].min().date()}  (expect ~game 40)")
    print("  SMOKE PASSED")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="synthetic self-test, no Snowflake")
    args = ap.parse_args()
    if args.smoke:
        _smoke()
        return

    from betting_ml.utils.data_loader import get_snowflake_connection
    conn = get_snowflake_connection()
    try:
        print("Loading start fact (mart_player_game_starts)...")
        starts = conn.cursor().execute(_STARTS_SQL).fetch_pandas_all()
        starts.columns = [c.lower() for c in starts.columns]
        starts["official_date"] = pd.to_datetime(starts["official_date"])
        print(f"  {len(starts):,} start rows, {starts['team'].nunique()} teams, "
              f"{starts['game_year'].min()}-{starts['game_year'].max()}")
        print("Loading injury status (feature_pregame_injury_status)...")
        inj = conn.cursor().execute(_INJURY_SQL).fetch_pandas_all()
        inj.columns = [c.lower() for c in inj.columns]
        print(f"  {len(inj):,} IL records, {inj['player_id'].nunique()} players")
    finally:
        conn.close()

    print("Building candidate panel...")
    panel = build(starts, inj)

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(_OUT, index=False)
    print(f"\nWrote {_OUT}")
    print(f"  panel rows={len(panel):,}  games={panel['game_pk'].nunique():,}  "
          f"players={panel['player_id'].nunique():,}")
    print(f"  base rate did_start={panel['did_start'].mean():.3f}  "
          f"injured rows={int(panel['is_injured'].sum()):,} ({panel['is_injured'].mean():.1%})")
    print(f"  candidates per team-game (mean)={len(panel)/panel.groupby(['game_pk','side']).ngroups:.1f}")
    # leakage sanity: a candidate with start_rate_50=1.0 should start often
    hi = panel[panel["start_rate_50"] >= 0.9]
    print(f"  sanity: start_rate_50≥0.9 cohort actual did_start rate={hi['did_start'].mean():.3f} (expect high)")


if __name__ == "__main__":
    main()
