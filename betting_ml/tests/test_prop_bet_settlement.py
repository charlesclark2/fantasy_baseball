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
    # E9.49: over/under now REQUIRES total_line — a totals bet without a line can never be
    # graded (settlement compares the final total against the line), so it showed "Pending"
    # forever. h2h needs no line. See test_prop_settlement_coverage.py for the rejection side.
    for m in ("h2h home", "h2h away"):
        assert BetCreate(game_pk=1, score_date="2026-07-08", market=m,
                         american_odds=-110, stake=1.0).market == m
    for m in ("over", "under"):
        assert BetCreate(game_pk=1, score_date="2026-07-08", market=m, total_line=8.5,
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
    monkeypatch.setattr(bets, "lakehouse_query_reason", lambda sql, params: (fake, None))
    out = bets.prop_starters(date="2026-07-01", _="uid")
    assert out["date"] == "2026-07-01"
    assert len(out["starters"]) == 1
    s = out["starters"][0]
    assert s["game_pk"] == 778899 and s["pitcher_id"] == 543037
    assert s["pitcher_name"] == "Gerrit Cole" and s["opponent"] == "BOS"
    assert s["game_date"] == "2026-07-01"  # date object sliced to ISO day


def test_prop_starters_empty_on_miss(monkeypatch):
    from app.backend.routers import bets
    monkeypatch.setattr(bets, "lakehouse_query_reason", lambda sql, params: ([], None))
    out = bets.prop_starters(date="2026-07-01", _="uid")
    assert out == {"date": "2026-07-01", "source": "probable_pitchers", "degraded": False,
                   "degraded_reason": None, "starters": []}


# ── E5.10: batter TOTAL-BASES props ──────────────────────────────────────────
#
# /props shipped a Total Bases tab (E5.9) while the log dialog and settlement were both
# strikeout-only, so a TB prop could not be recorded at all. These cover the three places
# that had to learn the market: the write model, the grader, and the batter picker.

def test_betcreate_accepts_a_total_bases_prop():
    from app.backend.models.bets import BetCreate
    b = BetCreate(game_pk=1, score_date="2026-08-15", market="total bases over",
                  american_odds=-115, stake=25, prop_line=1.5,
                  player_id=650490, player_name="Yandy Diaz")
    assert b.market == "total bases over" and b.prop_line == 1.5


def test_betcreate_rejects_a_total_bases_prop_with_no_line():
    """E9.49: a prop stored without its grading input sits Pending forever and looks
    identical to 'not finished yet' — so the line is required at WRITE time."""
    import pytest as _pytest
    from app.backend.models.bets import BetCreate
    with _pytest.raises(ValueError):
        BetCreate(game_pk=1, score_date="2026-08-15", market="total bases under",
                  american_odds=-115, stake=25, player_id=650490)


@pytest.mark.parametrize("market,actual,line,expected", [
    ("total bases over", 3, 1.5, "win"),
    ("total bases over", 1, 1.5, "loss"),
    ("total bases under", 1, 1.5, "win"),
    ("total bases under", 4, 1.5, "loss"),
    ("total bases over", 2, 2, "push"),      # integer line, exact
    ("total bases under", 2, 2, "push"),
    ("total bases over", 0, 0.5, "loss"),    # an 0-for-4 is a real settleable result
])
def test_total_bases_prop_outcome(market, actual, line, expected):
    from scripts.settle_user_bets import _prop_outcome
    assert _prop_outcome(market, actual, line) == expected


def test_the_two_prop_families_grade_independently():
    """A K market must never be graded off a TB total or vice versa — they share the
    grader, so the market string is the only thing keeping them apart."""
    from scripts.settle_user_bets import _K_PROP_MARKETS, _TB_PROP_MARKETS
    assert not (_K_PROP_MARKETS & _TB_PROP_MARKETS)


def test_settlement_and_the_api_agree_on_the_market_vocabulary():
    """The two _PROP_MARKETS sets are declared separately (the box script takes no
    app.backend import). A market the API accepts but settlement cannot grade is an
    unsettleable bet — the E9.49 class — so they must match exactly."""
    from app.backend.models.bets import _PROP_MARKETS as api_markets
    from scripts.settle_user_bets import _PROP_MARKETS as settle_markets
    assert api_markets == settle_markets


# ── total bases from a boxscore batting line ─────────────────────────────────

@pytest.mark.parametrize("batting,expected", [
    ({"hits": 0, "doubles": 0, "triples": 0, "homeRuns": 0}, 0),      # 0-for-4
    ({"hits": 1, "doubles": 0, "triples": 0, "homeRuns": 0}, 1),      # single
    ({"hits": 1, "doubles": 1, "triples": 0, "homeRuns": 0}, 2),      # double
    ({"hits": 1, "doubles": 0, "triples": 1, "homeRuns": 0}, 3),      # triple
    ({"hits": 1, "doubles": 0, "triples": 0, "homeRuns": 1}, 4),      # homer
    ({"hits": 3, "doubles": 1, "triples": 0, "homeRuns": 1}, 7),      # 1B + 2B + HR
])
def test_total_bases_from_batting_line(batting, expected):
    from scripts.settle_user_bets import total_bases_from_batting_line
    assert total_bases_from_batting_line(batting) == expected


@pytest.mark.parametrize("batting", [
    {},                                                          # player never batted
    {"hits": 2, "doubles": 1, "triples": 0},                      # homeRuns absent
    {"hits": 1, "doubles": None, "triples": 0, "homeRuns": 0},    # null component
    {"hits": 1, "doubles": 2, "triples": 0, "homeRuns": 0},       # XBH exceed hits
])
def test_an_uncomputable_batting_line_returns_none_never_zero(batting):
    """A missing stat and a genuine 0-for-4 are DIFFERENT facts: returning 0 here would
    silently settle an 'under' as a win off data we never had (NF1.7 (a))."""
    from scripts.settle_user_bets import total_bases_from_batting_line
    assert total_bases_from_batting_line(batting) is None


# ── /props/batters endpoint (the TB picker source) ───────────────────────────

def test_prop_batters_shapes_rows(monkeypatch):
    from datetime import date as _date

    from app.backend.routers import bets

    fake = [{
        "GAME_PK": 822941, "PLAYER_ID": 650490, "PLAYER_NAME": "Yandy Diaz",
        "TEAM": "Tampa Bay Rays", "OPPONENT": "Baltimore Orioles",
        "BATTING_SLOT": 1, "GAME_DATE": _date(2026, 8, 15),
    }]
    monkeypatch.setattr(bets, "lakehouse_query_reason", lambda sql, params: (fake, None))
    out = bets.prop_batters(date="2026-08-15", _="uid")
    assert out["date"] == "2026-08-15" and out["source"] == "lineups_wide"
    b = out["batters"][0]
    assert b["game_pk"] == 822941 and b["player_id"] == 650490
    assert b["player_name"] == "Yandy Diaz" and b["opponent"] == "Baltimore Orioles"
    assert b["game_date"] == "2026-08-15"


def test_prop_batters_empty_on_miss(monkeypatch):
    from app.backend.routers import bets
    monkeypatch.setattr(bets, "lakehouse_query_reason", lambda sql, params: ([], None))
    out = bets.prop_batters(date="2026-08-15", _="uid")
    assert out == {"date": "2026-08-15", "source": "lineups_wide", "degraded": False,
                   "degraded_reason": None, "batters": []}


def test_prop_batters_drops_a_row_with_no_usable_identity(monkeypatch):
    """A nameless/id-less row cannot be logged against — settlement keys on player_id —
    so it must not reach the picker as a blank option."""
    from app.backend.routers import bets
    fake = [
        {"GAME_PK": 1, "PLAYER_ID": None, "PLAYER_NAME": "Ghost", "TEAM": None,
         "OPPONENT": None, "BATTING_SLOT": 1, "GAME_DATE": None},
        {"GAME_PK": 1, "PLAYER_ID": 5, "PLAYER_NAME": "", "TEAM": None,
         "OPPONENT": None, "BATTING_SLOT": 2, "GAME_DATE": None},
    ]
    monkeypatch.setattr(bets, "lakehouse_query_reason", lambda sql, params: (fake, None))
    assert bets.prop_batters(date="2026-08-15", _="uid")["batters"] == []


# ── the silent-empty guard (E9.26b) ──────────────────────────────────────────
#
# `lakehouse_query` swallows every failure and returns [], so a read that BLEW UP inside the
# Lambda is byte-identical to a date that genuinely has nobody. That is exactly how the live
# picker read as "No posted lineups for this date yet" while the endpoint worked fine locally.
# Both pickers now report WHICH it was.

@pytest.mark.parametrize("fn_name,collection", [
    ("prop_starters", "starters"),
    ("prop_batters", "batters"),
])
def test_a_failed_lakehouse_read_is_reported_as_degraded(monkeypatch, fn_name, collection):
    from app.backend.routers import bets
    monkeypatch.setattr(bets, "lakehouse_query_reason", lambda sql, params: ([], "IOException: boom"))
    out = getattr(bets, fn_name)(date="2026-08-15", _="uid")
    assert out[collection] == []
    assert out["degraded"] is True, (
        "a FAILED read must be distinguishable from a genuinely empty date — otherwise the "
        "picker shows 'nothing for this date' over a broken backend (E9.26b)"
    )


@pytest.mark.parametrize("fn_name,collection", [
    ("prop_starters", "starters"),
    ("prop_batters", "batters"),
])
def test_a_genuinely_empty_date_is_not_reported_as_degraded(monkeypatch, fn_name, collection):
    """The other side of the same coin: an off-day must NOT claim the backend is broken."""
    from app.backend.routers import bets
    monkeypatch.setattr(bets, "lakehouse_query_reason", lambda sql, params: ([], None))
    out = getattr(bets, fn_name)(date="2026-12-25", _="uid")
    assert out[collection] == []
    assert out["degraded"] is False


def test_lakehouse_query_reason_reports_failure_without_raising():
    """The helper itself: a read that raises must return ([], False), never propagate — the
    router is a serving path and must not 500 on a cold lakehouse."""
    from app.backend.services import lakehouse_read

    def boom():
        raise RuntimeError("S3 is having a day")

    orig = lakehouse_read._get_conn
    try:
        lakehouse_read._get_conn = boom
        rows, reason = lakehouse_read.lakehouse_query_reason("SELECT 1")
        assert rows == [] and reason is not None
        assert "RuntimeError" in reason, "the reason must name the failure, not just flag it"
        # the swallowing wrapper keeps its old contract for existing callers
        assert lakehouse_read.lakehouse_query("SELECT 1") == []
    finally:
        lakehouse_read._get_conn = orig


def test_the_batters_query_scans_the_wide_lineup_table_only_once():
    """E9.26b: a heavy read can fail inside the Lambda AND poison the shared DuckDB
    singleton for later queries. The per-slot UNION ALL scanned the wide lineup table nine
    times; the unnest form does it once. Guard the shape, since the failure it prevents is
    invisible to CI (which mocks all IO)."""
    import ast
    import inspect
    import textwrap

    from app.backend.routers import bets

    # Scan the CODE only — not the comments, not the docstring. Both explain WHY the per-slot
    # union is gone and both name the table, so a raw text scan fails on correct source
    # (INC-38: prose must neither satisfy nor trip a source guard). ast.unparse drops
    # comments; the docstring is dropped explicitly.
    fn = ast.parse(textwrap.dedent(inspect.getsource(bets.prop_batters))).body[0]
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(getattr(fn.body[0], "value", None), ast.Constant)
            and isinstance(fn.body[0].value.value, str)):
        fn.body = fn.body[1:]
    src = ast.unparse(fn)

    assert "UNION ALL" not in src, (
        "the batters picker must not re-scan the wide lineup table per slot"
    )
    assert src.count("stg_statsapi_lineups_wide") == 1, (
        f"expected exactly one scan of the wide lineup table, found "
        f"{src.count('stg_statsapi_lineups_wide')}"
    )
    assert "unnest(" in src
