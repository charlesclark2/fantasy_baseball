"""feature_matrix.py — NCAAF-P1.3 pure logic for the pregame feature matrix.

The JOIN that assembles the matrix lives in dbt (`feature_ncaaf_pregame_matrix`), where it is
leakage-safe by construction and audited by a DATE-based singular test. This module holds the
IMPORT-SAFE pure functions the CLI driver + the fast-gate tests share:

  * FAMILIES / family_coverage  — the per-family, per-season NON-NULL coverage report (banner A:
    a silently-dead family, the F2/INC-31 class, must surface at build time, not in P1.4).
  * leakage_violations          — the DATE-based per-matchup leakage predicate, in pandas, IDENTICAL
    to the dbt gate `assert_pregame_matrix_is_point_in_time`. The fast-gate test uses it to PROVE
    the gate FAILS on a tampered/future-dated row (banner B — a green gate must mean something).
  * verify_join_grain           — the fan-out / drop guard: a season-level broadcast join that
    fanned out would DUPLICATE game_id; a week-level join that dropped would shrink the row count.

No `pipeline` import (fast-gate rule): pure pandas over frames the driver pulls from DuckDB.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── the feature families + a representative (home, away) column each. Coverage of the
#    representative column tracks whether that family's JOIN actually landed for the row. ──
FAMILIES: dict[str, tuple[str, str]] = {
    "strength (P1.2)":            ("home_strength_margin", "away_strength_margin"),
    "efficiency_raw (P1.1)":      ("home_off_ppa", "away_off_ppa"),
    "efficiency_opp_adj (P1.1)":  ("home_adj_net_ppa", "away_adj_net_ppa"),
    "pace_style":                 ("home_seconds_per_play", "away_seconds_per_play"),
    "line_trench":                ("home_off_line_yards", "away_off_line_yards"),
    "drive_quality":              ("home_points_per_drive", "away_points_per_drive"),
    "roster_continuity (P0.4)":   ("home_returning_ppa_pct", "away_returning_ppa_pct"),
    "portal_flux (P0.4)":         ("home_portal_net_count", "away_portal_net_count"),
    "talent (P0.4)":              ("home_team_talent", "away_team_talent"),
    "freshman_prior (P1.2b)":     ("home_freshman_proj_production", "away_freshman_proj_production"),
    "coaching (P0.5)":            ("home_hc_tenure_years", "away_hc_tenure_years"),
    "qb_continuity":              ("home_qb_trailing_ypa", "away_qb_trailing_ypa"),
    "rest":                       ("home_rest_days", "away_rest_days"),
    "travel/altitude":            ("away_travel_km", "away_altitude_change_m"),
}


def family_coverage(df: pd.DataFrame, season_col: str = "season") -> pd.DataFrame:
    """Per (season, family) pooled NON-NULL coverage across both sides.

    Returns long: season, family, coverage_pct (0–100), n_present, n_sides. A family that reads
    ~0% for a season it should cover is a dead-join alarm (banner A). A LEGITIMATELY-empty family
    (2014 strength; pre-2021 portal) reads low on purpose — the report is read, not just checked.
    """
    rows = []
    for family, (h, a) in FAMILIES.items():
        for col in (h, a):
            if col not in df.columns:
                raise KeyError(f"family {family!r} references missing column {col!r}")
        for season, g in df.groupby(season_col):
            vals = pd.concat([g[h], g[a]], ignore_index=True)
            n_sides = len(vals)
            n_present = int(vals.notna().sum())
            rows.append({
                "season": int(season),
                "family": family,
                "coverage_pct": round(100.0 * n_present / n_sides, 1) if n_sides else 0.0,
                "n_present": n_present,
                "n_sides": n_sides,
            })
    return pd.DataFrame(rows).sort_values(["season", "family"]).reset_index(drop=True)


def verify_join_grain(df: pd.DataFrame) -> dict:
    """The fan-out / drop guard. game_id must be UNIQUE — a broadcast join that fanned out (the
    season-level (season, team) key matching >1 row) would duplicate it; a mis-keyed week join
    likewise. Raises on a violation (HALT-tier). Returns the shape summary for the report."""
    n_rows = len(df)
    n_unique = int(df["game_id"].nunique())
    if n_rows != n_unique:
        dup = df["game_id"].value_counts()
        offenders = dup[dup > 1].head(10).to_dict()
        raise AssertionError(
            f"feature matrix is NOT 1-row-per-game: {n_rows} rows vs {n_unique} distinct game_id — "
            f"a join fanned out. Offending game_ids (count): {offenders}"
        )
    return {"n_rows": n_rows, "n_games": n_unique}


def leakage_violations(matrix: pd.DataFrame, team_games: pd.DataFrame) -> pd.DataFrame:
    """The DATE-based per-matchup leakage predicate — IDENTICAL logic to the dbt gate.

    For BOTH sides of every matchup, the team's feature snapshot (window = its completed games
    with season_order_week < the game's own season_order_week) must satisfy:
      (A) COUNT PARITY  — the matrix's {home,away}_games_played equals |window| (a snapshot joined
          at the WRONG week fails this). NULL claimed (week-1/no-coverage) is exempt from (A).
      (B) CLOCK SANITY  — max(window.game_date) < THIS game's kickoff date (an ordering bug that
          (A) is blind to fails this — the P1.1 postseason-week=1 collision).

    `matrix` needs: game_id, season, home_team_id, away_team_id, season_order_week, game_date,
    home_games_played, away_games_played. `team_games` needs: season, team_id, game_id,
    is_completed, season_order_week, game_date. Returns violating (game_id, team_id, side,
    violation) rows — EMPTY means the matrix is point-in-time.
    """
    sides = pd.concat([
        matrix[["game_id", "season", "home_team_id", "season_order_week", "game_date",
                "home_games_played"]].rename(
            columns={"home_team_id": "team_id", "home_games_played": "claimed_games"}).assign(side="home"),
        matrix[["game_id", "season", "away_team_id", "season_order_week", "game_date",
                "away_games_played"]].rename(
            columns={"away_team_id": "team_id", "away_games_played": "claimed_games"}).assign(side="away"),
    ], ignore_index=True)
    sides["game_date"] = pd.to_datetime(sides["game_date"])

    tg = team_games[team_games["is_completed"].astype(bool)][
        ["season", "team_id", "game_id", "season_order_week", "game_date"]
    ].rename(columns={"game_id": "w_game_id", "season_order_week": "w_order_week",
                      "game_date": "w_game_date"}).copy()
    tg["w_game_date"] = pd.to_datetime(tg["w_game_date"])

    # window = the team's completed games strictly before the matchup's own order-week
    joined = sides.merge(tg, on=["season", "team_id"], how="left")
    in_window = joined[joined["w_order_week"] < joined["season_order_week"]]
    agg = in_window.groupby(["game_id", "team_id", "side"], as_index=False).agg(
        recounted_games=("w_game_id", "count"),
        latest_game_in_window=("w_game_date", "max"),
    )
    out = sides.merge(agg, on=["game_id", "team_id", "side"], how="left")
    out["recounted_games"] = out["recounted_games"].fillna(0).astype(int)

    parity_bad = out["claimed_games"].notna() & (out["claimed_games"] != out["recounted_games"])
    clock_bad = out["latest_game_in_window"].notna() & (out["latest_game_in_window"] >= out["game_date"])
    viol = out[parity_bad | clock_bad].copy()
    viol["violation"] = np.where(parity_bad[parity_bad | clock_bad], "count parity", "clock sanity")
    return viol[["game_id", "team_id", "side", "season_order_week", "game_date",
                 "claimed_games", "recounted_games", "latest_game_in_window", "violation"]]
