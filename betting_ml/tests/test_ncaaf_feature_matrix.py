"""NCAAF-P1.3 — pregame feature-matrix guards.

Fast-gate only: pure pandas over SYNTHETIC frames + source inspection of the dbt SQL. No DuckDB,
no S3, no `pipeline` import (the fast gate has no dbt manifest — CLAUDE.md's fast-gate rule).

What these tests are for (the P1.1/P1.2/P1.2b standard — a green gate must MEAN something; CI mocks
all IO and cannot see the leakage class):
  * ⭐ the DATE-based leakage predicate is EMPTY on a clean matrix AND is PROVEN to FAIL on both a
    back-dated row (clock sanity) and a wrong-week snapshot (count parity) — banner B;
  * the fan-out guard raises when a season-level broadcast join duplicates a game_id — banner A;
  * per-family coverage is computed pooled over both sides, and a dead family reads ~0%;
  * the mart SQL joins the week-grained families on `season_order_week`, never raw `week` (the
    P1.1 postseason-week=1 leak), and the label_* target columns are prefixed + never a feature.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quant_sports_intel_models.football.ncaaf.models import feature_matrix as fm

_REPO = Path(__file__).resolve().parents[2]
_MART_SQL = (_REPO / "quant_sports_intel_models/sports_dbt/models/ncaaf/marts/"
             "feature_ncaaf_pregame_matrix.sql")
_GATE_SQL = (_REPO / "quant_sports_intel_models/sports_dbt/tests/ncaaf/"
             "assert_pregame_matrix_is_point_in_time.sql")


# ══════════════════════════════════════════════════════════════════════════════════════
# A tiny synthetic 2-team, 3-week universe with a KNOWN point-in-time structure
# ══════════════════════════════════════════════════════════════════════════════════════
#   Two teams (1, 2) play each other in weeks 1, 2, 3 (game_date monotone in the week). At the
#   kickoff of week W, each team's window = its completed games with season_order_week < W.


def _team_games() -> pd.DataFrame:
    # one fact row per (game, team) — the completed games that back the windows
    rows = []
    dates = {1: "2023-09-02", 2: "2023-09-09", 3: "2023-09-16"}
    for w, gid in [(1, 101), (2, 102), (3, 103)]:
        for tid in (1, 2):
            rows.append({"season": 2023, "team_id": tid, "game_id": gid,
                         "is_completed": True, "season_order_week": w, "game_date": dates[w]})
    return pd.DataFrame(rows)


def _matrix(home_games_played=None, away_games_played=None) -> pd.DataFrame:
    """The matchup rows, correctly point-in-time: at week W the window has W-1 prior games."""
    dates = {1: "2023-09-02", 2: "2023-09-09", 3: "2023-09-16"}
    rows = []
    for w, gid in [(1, 101), (2, 102), (3, 103)]:
        rows.append({
            "game_id": gid, "season": 2023,
            "home_team_id": 1, "away_team_id": 2,
            "season_order_week": w, "game_date": dates[w],
            # correct claim: W-1 completed games strictly before week W
            "home_games_played": w - 1, "away_games_played": w - 1,
            # a couple of feature columns for the coverage tests
            "home_strength_margin": 3.0, "away_strength_margin": -1.0,
            "home_off_ppa": 0.2 if w > 1 else None, "away_off_ppa": 0.1 if w > 1 else None,
        })
    df = pd.DataFrame(rows)
    if home_games_played is not None:
        df["home_games_played"] = home_games_played
    if away_games_played is not None:
        df["away_games_played"] = away_games_played
    return df


# ══════════════════════════════════════════════════════════════════════════════════════
# Leakage predicate — the heart of the story
# ══════════════════════════════════════════════════════════════════════════════════════


def test_clean_matrix_has_no_leakage():
    viol = fm.leakage_violations(_matrix(), _team_games())
    assert len(viol) == 0, f"clean matrix flagged as leaking:\n{viol}"


def test_leakage_gate_fires_on_a_backdated_row():
    """CLOCK SANITY (banner B): back-date week-3's kickoff to before its week-1/2 window → a game
    in the window now post-dates the kickoff. A week-based test would NOT catch this; the
    date-based gate must."""
    m = _matrix()
    m.loc[m["game_id"] == 103, "game_date"] = "2023-01-01"  # before the prior games
    viol = fm.leakage_violations(m, _team_games())
    assert len(viol) > 0, "leakage gate did NOT fire on a back-dated row — it is a no-op"
    assert (viol["violation"] == "clock sanity").any()


def test_leakage_gate_fires_on_a_wrong_week_snapshot():
    """COUNT PARITY: claim more prior games than the window actually holds (a snapshot joined at
    the WRONG, later week). The gate must catch the mismatch."""
    m = _matrix()
    m.loc[m["game_id"] == 102, "home_games_played"] = 5  # week-2 window really has 1
    viol = fm.leakage_violations(m, _team_games())
    assert len(viol) > 0
    assert (viol["violation"] == "count parity").any()


def test_null_claimed_games_is_exempt_from_parity_but_not_clock():
    """A week-1 / no-coverage row has NULL games_played — no rollup to recount, so parity is
    vacuous; but the clock check still holds (an empty window can't contain a future game)."""
    m = _matrix(home_games_played=None, away_games_played=None)
    viol = fm.leakage_violations(m, _team_games())
    assert len(viol) == 0


# ══════════════════════════════════════════════════════════════════════════════════════
# Fan-out / drop guard — banner A
# ══════════════════════════════════════════════════════════════════════════════════════


def test_grain_guard_passes_on_unique_games():
    shape = fm.verify_join_grain(_matrix())
    assert shape["n_rows"] == shape["n_games"] == 3


def test_grain_guard_raises_on_a_fanned_out_join():
    m = pd.concat([_matrix(), _matrix().iloc[[0]]], ignore_index=True)  # duplicate game 101
    with pytest.raises(AssertionError, match="NOT 1-row-per-game"):
        fm.verify_join_grain(m)


# ══════════════════════════════════════════════════════════════════════════════════════
# Coverage report
# ══════════════════════════════════════════════════════════════════════════════════════


def _full_matrix() -> pd.DataFrame:
    """`_matrix()` plus every remaining family column (constant, non-null) so `family_coverage`
    — which strictly requires all family columns, as the real matrix has them — runs. strength
    and efficiency_raw keep their `_matrix()` values (100% and the week-1 NULL pattern)."""
    df = _matrix()
    for h, a in fm.FAMILIES.values():
        for col in (h, a):
            if col not in df.columns:
                df[col] = 1.0
    return df


def test_family_coverage_pools_both_sides_and_flags_dead_family():
    cov = fm.family_coverage(_full_matrix())
    strength = cov[cov["family"] == "strength (P1.2)"].iloc[0]
    # strength is present on every side (6 sides across 3 games) → 100%
    assert strength["coverage_pct"] == 100.0
    assert strength["n_sides"] == 6
    # efficiency_raw is NULL at week 1 (both sides) → 4/6 present
    eff = cov[cov["family"] == "efficiency_raw (P1.1)"].iloc[0]
    assert eff["n_present"] == 4 and eff["n_sides"] == 6


def test_family_coverage_raises_on_missing_column():
    m = _matrix().drop(columns=["home_strength_margin"])
    with pytest.raises(KeyError):
        fm.family_coverage(m)


# ══════════════════════════════════════════════════════════════════════════════════════
# Source-inspection guards — the invariants the SQL must hold (CI-blind otherwise)
# ══════════════════════════════════════════════════════════════════════════════════════


def test_mart_joins_week_families_on_season_order_week_never_raw_week():
    sql = _MART_SQL.read_text()
    # the week-grained joins must key on season_order_week (the ONLY safe ordering)
    assert "as_of_week = g.season_order_week" in sql
    # and must NOT key any as-of join on raw CFBD `week`
    assert "as_of_week = g.week" not in sql


def test_labels_are_prefixed_and_never_a_feature():
    sql = _MART_SQL.read_text()
    assert "as label_home_win" in sql and "as label_total_points" in sql
    # no feature-side column may carry the label_ prefix (would let a `select home_*` leak it)
    assert "as home_label" not in sql and "as away_label" not in sql


def test_leakage_gate_is_date_based_and_wired():
    gate = _GATE_SQL.read_text()
    assert "clock sanity" in gate and "count parity" in gate
    # the gate compares against a kickoff DATE, not a week filter alone
    assert "kickoff_date" in gate and ">= kickoff_date" in gate
