"""test_prop_bet_settlement.py — E9.42 "Log this prop".

Covers the two backend pieces of logging a pitcher-strikeout prop into the Bet Log:
  1. the bet pydantic model accepts the new prop market type + prop fields (and still
     rejects unknown markets), and
  2. settle_user_bets._prop_outcome settles a logged K prop against the starter's actual
     strikeouts (over / under / push vs the logged line).

Pure logic — no DynamoDB / Snowflake — so it runs in the fast gate.
"""

from __future__ import annotations

import pytest

from app.backend.models.bets import BetCreate
from scripts.settle_user_bets import _prop_outcome


# ── bet model: prop market type + prop fields ────────────────────────────────

def test_betcreate_accepts_strikeout_prop():
    b = BetCreate(
        game_pk=778899, score_date="2026-07-08", matchup="Gerrit Cole K vs BOS",
        market="strikeouts over", bookmaker="Bovada", american_odds=-115, stake=25.0,
        prop_line=6.5, player_id=543037, player_name="Gerrit Cole", projection=6.8,
    )
    assert b.market == "strikeouts over"
    assert b.prop_line == 6.5
    assert b.player_id == 543037
    assert b.player_name == "Gerrit Cole"
    assert b.projection == 6.8


def test_betcreate_accepts_strikeouts_under():
    b = BetCreate(
        game_pk=1, score_date="2026-07-08", market="strikeouts under",
        american_odds=100, stake=10.0, prop_line=5.5, player_id=99,
    )
    assert b.market == "strikeouts under"


def test_betcreate_still_accepts_game_markets():
    for m in ("h2h home", "h2h away", "over", "under"):
        assert BetCreate(game_pk=1, score_date="2026-07-08", market=m,
                         american_odds=-110, stake=1.0).market == m


def test_betcreate_rejects_unknown_market():
    with pytest.raises(ValueError):
        BetCreate(game_pk=1, score_date="2026-07-08", market="strikeouts middle",
                  american_odds=-110, stake=1.0)


def test_prop_fields_default_none_for_game_bets():
    b = BetCreate(game_pk=1, score_date="2026-07-08", market="over",
                  american_odds=-110, stake=1.0, total_line=8.5)
    assert b.player_id is None and b.prop_line is None and b.projection is None


# ── settlement: actual K vs the logged line ──────────────────────────────────

@pytest.mark.parametrize("market,actual,line,expected", [
    ("strikeouts over", 8, 6.5, "win"),
    ("strikeouts over", 5, 6.5, "loss"),
    ("strikeouts under", 5, 6.5, "win"),
    ("strikeouts under", 8, 6.5, "loss"),
    # integer line → push when actual K equals the line exactly
    ("strikeouts over", 6, 6.0, "push"),
    ("strikeouts under", 6, 6.0, "push"),
    # boundary either side of an integer line
    ("strikeouts over", 7, 6.0, "win"),
    ("strikeouts under", 5, 6.0, "win"),
])
def test_prop_outcome(market, actual, line, expected):
    assert _prop_outcome(market, actual, line) == expected


def test_prop_outcome_none_without_line():
    assert _prop_outcome("strikeouts over", 7, None) is None


def test_prop_outcome_unknown_market_is_none():
    assert _prop_outcome("over", 7, 6.5) is None


# ── /props/starters endpoint (manual back-log picker source) ─────────────────

def test_prop_starters_shapes_rows(monkeypatch):
    from datetime import date as _date

    from app.backend.routers import bets

    fake = [{
        "GAME_PK": 778899, "PITCHER_ID": 543037, "PITCHER_NAME": "Gerrit Cole",
        "TEAM": "NYY", "OPPONENT": "BOS", "GAME_DATE": _date(2026, 7, 1),
    }]
    monkeypatch.setattr(bets, "lakehouse_query", lambda sql, params: fake)
    out = bets.prop_starters(date="2026-07-01", _="uid")
    assert out["date"] == "2026-07-01"
    assert len(out["starters"]) == 1
    s = out["starters"][0]
    assert s["game_pk"] == 778899 and s["pitcher_id"] == 543037
    assert s["pitcher_name"] == "Gerrit Cole" and s["opponent"] == "BOS"
    assert s["game_date"] == "2026-07-01"  # date object sliced to ISO day


def test_prop_starters_empty_on_miss(monkeypatch):
    from app.backend.routers import bets
    monkeypatch.setattr(bets, "lakehouse_query", lambda sql, params: [])
    out = bets.prop_starters(date="2026-07-01", _="uid")
    assert out == {"date": "2026-07-01", "source": "probable_pitchers", "starters": []}
