"""win_total_source.py — NF-D4: preseason SEASON WIN-TOTAL env (the forward-Vegas team environment).

NF-D2 slice 4 shipped a QB team-environment tilt off the projection-season team's WEEK-1 implied
points (leakage-safe, but a single noisy game → held-out QB within-pos ρ only +~0.012, ~1/5 of the
leaky season-long ceiling +~0.06). NF-D4 replaces that Week-1 proxy with a genuinely-forward
SEASON-level market read: the preseason regular-season WIN TOTAL (the Vegas over/under win line),
set BEFORE any of the season's games ⇒ **leakage-safe**, and a season-long implied team-quality
measure (not a single game). Fed as `team_env` to the SAME shipped `environment_tilt_scale` (which
z-scores `team_env` within the QB field, so the underlying UNITS are irrelevant — win-total vs
implied-points is purely a question of which ordering better predicts QB fantasy output).

⚠️ PROBE-FIRST FINDING (2026-07-26, recorded so it isn't rediscovered):
  • The **Odds API does NOT expose an NFL regular-season win-total (futures) market.** The only NFL
    futures key is `americanfootball_nfl_super_bowl_winner` (has_outrights=true — champion odds), and
    the main `americanfootball_nfl` key is game lines only (has_outrights=false). So NF-D4 source #2
    (Odds-API win-total futures) is UNAVAILABLE — no paid /historical pull was fired for it, no credits
    spent. The forward win-total signal therefore comes from a STATIC public backfill (source #3), which
    is exactly what the story pre-registered as the validation instrument.
  • The Odds-API `/historical` GAME-LINE endpoint returns the CLOSING snapshot (last state ≤ kickoff),
    floor 2020; a true OPENING snapshot would need the earliest snapshot per game (credit-heavy, per-game
    not season-level). Season-level win totals dominate that idea for the QB-environment purpose, so the
    opening-line capture (source #1) is left as a FUTURE serving-only extension, not built here.

DATA (source #3 — a ONE-TIME STATIC backfill, committed + auditable):
  Preseason regular-season win totals for 2020–2025, transcribed from covers.com Sports Odds History
  (https://www.covers.com/sportsoddshistory/nfl-win/?y=YYYY&sa=nfl&t=win) — ONE consistent source
  across all six seasons so the season-to-season ordering is comparable. These are the widely-quoted
  preseason lines (a de-facto consensus; a ~0.5-win book-to-book spread doesn't move a z-scored,
  rank-based tilt). Cross-checked against mrcaseb/nfl-data `historical_win_totals.csv` (1989–2020) and
  greerreNFL/nfl-win-total-data `sos.csv` (2003–2022) where they overlap. 2020 is the earliest season
  the shipped Week-1 baseline (`dim_nfl_game`) also covers, so 2020–2025 is the fair comparison window.

  A win total is a season-level TEAM-QUALITY read (offense + defense), so it is a slightly NOISIER
  proxy for the OFFENSIVE environment than the (leaky) season-long implied points — but it is a
  genuinely-forward, season-long signal, which is the NF-D4 hypothesis under test. `run_team_context_
  ablation.py` decides whether it beats the Week-1 line on held-out within-position ρ.

Team codes = nflverse abbreviations (match `dim_nfl_game` / `fct_player_week`). Rams keyed `LAR`;
the harness normalises the stray `LA` code (see `run_team_context_ablation`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# The 32 nflverse team codes (Washington = WAS across the FT→Commanders rename; Rams = LAR).
TEAM_CODES: tuple[str, ...] = (
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB",
    "HOU", "IND", "JAX", "KC", "LV", "LAC", "LAR", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WAS",
)

# season → {team_code: preseason regular-season win total (over/under line)}.
# Source: covers.com Sports Odds History (one consistent source, all seasons).
WIN_TOTALS: dict[int, dict[str, float]] = {
    2020: {"ARI": 7.5, "ATL": 7.5, "BAL": 11.5, "BUF": 9.0, "CAR": 5.5, "CHI": 8.0,
           "CIN": 5.5, "CLE": 8.5, "DAL": 10.0, "DEN": 7.5, "DET": 7.0, "GB": 8.5,
           "HOU": 7.5, "IND": 9.5, "JAX": 4.5, "KC": 11.5, "LV": 7.5, "LAC": 8.0,
           "LAR": 8.5, "MIA": 6.0, "MIN": 9.0, "NE": 9.0, "NO": 10.5, "NYG": 6.5,
           "NYJ": 6.5, "PHI": 9.5, "PIT": 9.5, "SF": 10.5, "SEA": 9.5, "TB": 9.5,
           "TEN": 8.5, "WAS": 5.0},
    2021: {"ARI": 8.5, "ATL": 7.5, "BAL": 10.5, "BUF": 11.5, "CAR": 7.5, "CHI": 7.5,
           "CIN": 6.5, "CLE": 10.5, "DAL": 9.0, "DEN": 9.0, "DET": 4.5, "GB": 10.5,
           "HOU": 4.0, "IND": 9.0, "JAX": 6.5, "KC": 12.5, "LV": 7.5, "LAC": 9.5,
           "LAR": 10.5, "MIA": 9.0, "MIN": 9.0, "NE": 9.5, "NO": 9.0, "NYG": 7.0,
           "NYJ": 6.0, "PHI": 6.5, "PIT": 8.5, "SF": 10.5, "SEA": 9.5, "TB": 12.0,
           "TEN": 9.5, "WAS": 8.5},
    2022: {"ARI": 8.5, "ATL": 4.5, "BAL": 10.5, "BUF": 12.0, "CAR": 6.5, "CHI": 5.5,
           "CIN": 9.5, "CLE": 8.0, "DAL": 10.0, "DEN": 10.0, "DET": 6.5, "GB": 11.0,
           "HOU": 4.5, "IND": 10.0, "JAX": 6.5, "KC": 10.5, "LV": 8.5, "LAC": 10.5,
           "LAR": 10.5, "MIA": 9.0, "MIN": 9.5, "NE": 8.5, "NO": 9.0, "NYG": 7.0,
           "NYJ": 5.5, "PHI": 10.0, "PIT": 7.5, "SF": 10.0, "SEA": 5.5, "TB": 11.0,
           "TEN": 9.0, "WAS": 7.5},
    2023: {"ARI": 4.5, "ATL": 8.5, "BAL": 10.0, "BUF": 10.5, "CAR": 7.5, "CHI": 7.5,
           "CIN": 11.0, "CLE": 9.0, "DAL": 10.0, "DEN": 8.5, "DET": 9.5, "GB": 7.5,
           "HOU": 6.5, "IND": 6.5, "JAX": 9.5, "KC": 11.5, "LV": 6.5, "LAC": 9.5,
           "LAR": 6.5, "MIA": 9.5, "MIN": 8.5, "NE": 7.5, "NO": 9.5, "NYG": 7.5,
           "NYJ": 9.5, "PHI": 11.5, "PIT": 9.0, "SF": 11.0, "SEA": 9.0, "TB": 6.0,
           "TEN": 7.5, "WAS": 6.5},
    2024: {"ARI": 7.0, "ATL": 9.5, "BAL": 10.5, "BUF": 10.0, "CAR": 5.5, "CHI": 8.5,
           "CIN": 10.5, "CLE": 8.5, "DAL": 10.0, "DEN": 5.5, "DET": 10.5, "GB": 10.0,
           "HOU": 9.5, "IND": 8.5, "JAX": 8.5, "KC": 11.5, "LV": 6.5, "LAC": 9.0,
           "LAR": 8.5, "MIA": 10.0, "MIN": 6.5, "NE": 4.5, "NO": 7.5, "NYG": 6.5,
           "NYJ": 9.5, "PHI": 10.5, "PIT": 8.0, "SF": 11.5, "SEA": 7.5, "TB": 7.5,
           "TEN": 6.5, "WAS": 6.5},
    2025: {"ARI": 8.5, "ATL": 8.5, "BAL": 11.5, "BUF": 12.5, "CAR": 6.5, "CHI": 8.5,
           "CIN": 9.5, "CLE": 4.5, "DAL": 7.5, "DEN": 9.5, "DET": 10.5, "GB": 10.5,
           "HOU": 9.5, "IND": 7.5, "JAX": 7.5, "KC": 11.5, "LV": 6.5, "LAC": 9.5,
           "LAR": 9.5, "MIA": 7.5, "MIN": 9.5, "NE": 8.5, "NO": 4.5, "NYG": 5.5,
           "NYJ": 6.5, "PHI": 11.5, "PIT": 8.5, "SF": 10.5, "SEA": 8.5, "TB": 9.5,
           "TEN": 6.5, "WAS": 9.5},
    # 2026 = the SERVING season (the upcoming board). DraftKings first-look lines, ~July 2026 (FOX
    # Sports 32-team recap of the DK market). Preseason ⇒ leakage-safe; refresh if the operator wants
    # a later, tighter snapshot before the board's final publish.
    2026: {"ARI": 3.5, "ATL": 6.5, "BAL": 11.5, "BUF": 10.5, "CAR": 7.5, "CHI": 9.5,
           "CIN": 10.5, "CLE": 5.5, "DAL": 9.5, "DEN": 9.5, "DET": 10.5, "GB": 9.5,
           "HOU": 9.5, "IND": 7.5, "JAX": 8.5, "KC": 10.5, "LV": 5.5, "LAC": 9.5,
           "LAR": 11.5, "MIA": 4.5, "MIN": 8.5, "NE": 10.5, "NO": 7.5, "NYG": 7.5,
           "NYJ": 5.5, "PHI": 10.5, "PIT": 8.5, "SF": 9.5, "SEA": 10.5, "TB": 8.5,
           "TEN": 6.5, "WAS": 7.5},
}

# Integrity: every season carries all 32 codes exactly once (a transcription guard).
for _yr, _wt in WIN_TOTALS.items():
    assert set(_wt) == set(TEAM_CODES), f"{_yr} win totals miss/extra teams: {set(_wt) ^ set(TEAM_CODES)}"

WIN_TOTAL_SEASONS: tuple[int, ...] = tuple(sorted(WIN_TOTALS))


def win_total_env(season: int) -> pd.DataFrame:
    """The preseason win-total env for one season → DataFrame[proj_team, env_wt]. `env_wt` is the raw
    win-total line (the tilt z-scores it, so no scaling here). Empty when the season isn't backfilled."""
    wt = WIN_TOTALS.get(int(season))
    if not wt:
        return pd.DataFrame(columns=["proj_team", "env_wt"])
    return pd.DataFrame({"proj_team": list(wt), "env_wt": list(wt.values())})


def zteam(s: pd.Series) -> pd.Series:
    """z-score a team-level Series across the season's ~32 teams (NaN-safe; flat ⇒ zeros)."""
    x = pd.to_numeric(s, errors="coerce")
    sd = x.std()
    return (x - x.mean()) / sd if sd and np.isfinite(sd) else x * 0.0


def blend_env_with_win_total(team_env_df: pd.DataFrame, season: int,
                             env_col: str = "team_env", team_col: str = "proj_team") -> pd.DataFrame:
    """NF-D4 SHIPPED env — the team-level 0.5/0.5 z-BLEND of a Week-1 implied-points env frame with the
    preseason WIN TOTAL, the source that beat the Week-1-only baseline on held-out QB within-position ρ
    (a season-level team-quality read that STABILISES the noisy single-game Week-1 line; win-total-ALONE
    was WORSE than Week-1 and is not shipped). Returns the frame with `env_col` REPLACED by the blend
    (the tilt re-z-scores within the QB field, so a team-level z here is order-correct). GRACEFUL
    FALLBACK: unchanged `env_col` when the season has no backfilled win totals (⇒ the exact slice-4
    Week-1-only behavior — a future season just needs its 32 totals added to `WIN_TOTALS`); a team
    missing a win total keeps its Week-1 z alone (no NaN contamination)."""
    wt = win_total_env(season)
    if wt.empty or team_env_df.empty or env_col not in team_env_df.columns:
        return team_env_df
    df = team_env_df.merge(wt, on=team_col, how="left")
    zwk1, zwt = zteam(df[env_col]).to_numpy(), zteam(df["env_wt"]).to_numpy()
    df[env_col] = np.where(np.isfinite(zwt), (zwk1 + zwt) / 2.0, zwk1)
    return df.drop(columns=["env_wt"])
