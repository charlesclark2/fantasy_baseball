"""Story E1.8 — unit tests for the leakage-safe Stuff+/arsenal swap-in.

`_swap_stuff_plus_deleaked` repoints the LEAKY season-to-date Stuff+/arsenal columns to the
starter's PRIOR-SEASON arsenal (the leakage-safe reconstruction) for the clustered-MDA A/B.
These tests pin the swap semantics WITHOUT a live Snowflake connection by faking the cursor:
  - present prior-season values are repointed onto the matrix columns;
  - missing prior season (rookie / first MLB season) keeps the leaky value (minimal-change A/B);
  - the AS-OF-safe rolling `*_velo_30d` and unrelated columns are left untouched.
"""

from __future__ import annotations

import pandas as pd
import pytest

from betting_ml.scripts import clustered_feature_importance as cfi

_ARSENAL_DESC = [
    "game_pk", "side",
    "overall_stuff_plus", "fastball_stuff_plus", "slider_stuff_plus",
    "curveball_stuff_plus", "changeup_stuff_plus", "avg_fastball_velo_mph",
    "fastball_pct", "breaking_pct", "offspeed_pct",
]


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.description = [(c.upper(),) for c in _ARSENAL_DESC]

    def execute(self, *_a, **_k):
        return None

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)

    def close(self):
        return None


def _arsenal_row(game_pk, side, stuff):
    """A LEFT-JOIN result row; `stuff=None` models a starter with no prior-season arsenal."""
    if stuff is None:
        return (game_pk, side, None, None, None, None, None, None, None, None, None)
    return (game_pk, side, stuff, stuff - 5, stuff - 15, stuff - 10, stuff - 8,
            94.5, 0.5, 0.3, 0.2)


def _matrix():
    """Two games; every season-arsenal column carries a leaky sentinel (999 / 88.8)."""
    sentinels = {
        "starter_stuff_plus": 999.0, "starter_fastball_stuff_plus": 999.0,
        "starter_slider_stuff_plus": 999.0, "starter_curveball_stuff_plus": 999.0,
        "starter_changeup_stuff_plus": 999.0, "starter_avg_fastball_velo": 88.8,
        "starter_fastball_pct": 9.9, "starter_breaking_pct": 9.9, "starter_offspeed_pct": 9.9,
    }
    row = {"game_pk": None, "game_year": 2024}
    for side in ("home", "away"):
        for suffix, val in sentinels.items():
            row[f"{side}_{suffix}"] = val
    # AS-OF-safe rolling velo + an unrelated feature — must be untouched.
    row["home_starter_avg_fastball_velo_30d"] = 80.0
    row["home_off_xwoba_30d"] = 0.330
    r1, r2 = dict(row, game_pk="1"), dict(row, game_pk="2")
    return pd.DataFrame([r1, r2])


def test_swap_repoints_present_and_falls_back_on_rookie(monkeypatch):
    # game 1: both sides have prior-season arsenal; game 2: away has it, home is a rookie (None).
    rows = [
        _arsenal_row("1", "home", 110.0),
        _arsenal_row("1", "away", 90.0),
        _arsenal_row("2", "away", 100.0),
        _arsenal_row("2", "home", None),
    ]
    monkeypatch.setattr(cfi, "get_snowflake_connection", lambda: _FakeConn(rows))

    out = cfi._swap_stuff_plus_deleaked(_matrix())
    g1 = out.set_index("game_pk").loc["1"]
    g2 = out.set_index("game_pk").loc["2"]

    # present → repointed to prior-season values
    assert g1["home_starter_stuff_plus"] == 110.0
    assert g1["home_starter_slider_stuff_plus"] == 110.0 - 15
    assert g1["away_starter_stuff_plus"] == 90.0
    assert g1["home_starter_avg_fastball_velo"] == 94.5
    assert g2["away_starter_stuff_plus"] == 100.0

    # rookie / no prior season → keep the leaky value (minimal-change A/B)
    assert g2["home_starter_stuff_plus"] == 999.0
    assert g2["home_starter_avg_fastball_velo"] == 88.8

    # AS-OF-safe rolling velo + unrelated feature untouched
    assert g1["home_starter_avg_fastball_velo_30d"] == 80.0
    assert g1["home_off_xwoba_30d"] == 0.330


def test_swap_raises_on_empty_arsenal(monkeypatch):
    monkeypatch.setattr(cfi, "get_snowflake_connection", lambda: _FakeConn([]))
    with pytest.raises(RuntimeError, match="no rows"):
        cfi._swap_stuff_plus_deleaked(_matrix())
