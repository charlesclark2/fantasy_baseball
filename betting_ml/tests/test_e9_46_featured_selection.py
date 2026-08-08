"""E9.46 — the featured-pick SELECTION RULE, and the silent failure that hid a broken one.

Two operator changes on 2026-08-08 are pinned here:

  1. the featured MLB read is now the day's LARGEST model-vs-market gap among games where our two
     independent estimators agree, rather than the earliest-starting such game; and
  2. when today's run has not published yet, the previous read is CARRIED OVER rather than the
     card going empty.

⭐⭐ THE TEST THAT MATTERS MOST IS `TestTheQueriesActuallyRun`, AND IT IS WORTH SAYING WHY IN FULL.

(2) was not a missing feature. The carry-over query existed, was reachable, and was DEAD IN
PRODUCTION — it ended `ORDER BY actual_outcome DESC NULLS LAST, ABS(edge) DESC NULLS LAST, …`, and
DuckDB (the only engine that runs this path now) cannot ORDER a UNION by an EXPRESSION over a
selected column:

    Binder Error: Could not ORDER BY column "abs(h2h.edge)": add the expression/function to
    every SELECT, or move the UNION into a FROM clause.

`lakehouse_query` catches every exception and returns `[]` BY DESIGN — a last-resort read must
never 500 a router — so a query that cannot even BIND is indistinguishable from a slate with no
qualifying game. On 2026-08-08 the live endpoint served `game_pk: null` while the previous day
held 45 prediction rows, and nothing anywhere logged an error a human would see. That is the
E9.26b silent-`[]` class, and no amount of asserting on SQL TEXT catches it: the old ORDER BY is
valid Snowflake, reads correctly, and a source-inspection test would have called it fine.

⇒ these tests EXECUTE every featured query against a real DuckDB, through the SAME translation
layer the Lambda uses (`lakehouse_read.query_upper` — FQN stripping, dialect fixes, paramstyle),
over in-memory tables. Any query that cannot bind fails here instead of silently serving an empty
home page. ⛔ Do not "simplify" these into text assertions.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pytest

from app.backend.routers import picks
from app.backend.services import lakehouse_read
from betting_ml.tests._serving_store_loader import load_write_serving_store

_REPO = Path(__file__).resolve().parents[2]

_wss = load_write_serving_store("_wss_e9_46_featured")

# Every constant that resolves "the featured pick". The writer's two are the PRIMARY serving path;
# the router's four are the cold last-resort. They must agree, or "yesterday's featured pick"
# names a different game than the one that was featured.
WRITER_QUERIES = {
    "writer.today": _wss._FEATURED_TODAY_SERVING_SQL,
    "writer.yesterday": _wss._FEATURED_YESTERDAY_SERVING_SQL,
}
ROUTER_QUERIES = {
    "router.today": picks._FEATURED_TODAY_QUERY,
    "router.stale_fallback": picks._FEATURED_STALE_FALLBACK_QUERY,
    "router.yesterday": picks._FEATURED_YESTERDAY_QUERY,
    "router.yesterday_heal": picks._FEATURED_YESTERDAY_HEAL_QUERY,
}
ALL_QUERIES = {**WRITER_QUERIES, **ROUTER_QUERIES}

EXPECTED_ORDER_BY = (
    "ORDER BY edge DESC NULLS LAST, game_datetime ASC NULLS LAST, game_pk ASC, market_type ASC"
)


# ══ THE SHARED RULE ════════════════════════════════════════════════════════════════════════════


class TestTheSelectionRuleIsShared:
    def test_every_featured_query_shares_the_rule(self):
        """All six sort identically. A recap that resolves a different pick than the card above it
        is not a recap — it is a second, unannounced pick."""
        for name, sql in ALL_QUERIES.items():
            assert EXPECTED_ORDER_BY in sql, f"{name} does not carry the shared ORDER BY"

    def test_the_gap_is_the_lead_sort_key(self):
        """The operator's change, stated as the thing a reader can check: `edge` leads, and
        `game_datetime` is demoted to a tie-break. Asserting only that both appear would pass on
        the PREVIOUS rule too."""
        for name, sql in ALL_QUERIES.items():
            clause = _final_order_by(sql)
            keys = [k.strip() for k in clause.split(",")]
            assert keys[0].lower().startswith("edge desc"), f"{name} does not lead on the gap: {clause}"
            assert any(k.lower().startswith("game_datetime") for k in keys[1:]), (
                f"{name} dropped the deterministic tie-break: {clause}"
            )

    def test_no_featured_query_selects_on_the_outcome(self):
        """⛔ THE CHERRY-PICK GUARD. Two router constants used to lead with `actual_outcome DESC
        NULLS LAST`, which means "of the available picks, show the one that WON". On the one
        surface whose argument is that we grade ourselves honestly, carrying a winner forward by
        construction is precisely the claim `best_alpha = 0` forbids. `actual_outcome` may still be
        SELECTED (the recap displays it) — it may never be ORDERED BY."""
        for name, sql in ALL_QUERIES.items():
            clause = _final_order_by(sql)
            assert "actual_outcome" not in clause.lower(), (
                f"{name} orders on the outcome — it would show yesterday's winner by construction: {clause}"
            )
            assert "home_team_won" not in clause.lower(), f"{name} orders on the result: {clause}"

    def test_the_gap_is_never_wrapped_in_a_function_in_an_order_by(self):
        """The exact regression that killed the carry-over in production. `edge` is ALREADY
        `ABS(model − market)` in every branch, so `ABS(edge)` bought nothing and cost the feature.
        DuckDB cannot order a UNION by an expression over a selected column."""
        for name, sql in ALL_QUERIES.items():
            clause = _final_order_by(sql)
            assert not re.search(r"\b(abs|round|coalesce)\s*\(", clause, re.I), (
                f"{name} orders a UNION by an EXPRESSION — DuckDB cannot bind that, and "
                f"lakehouse_query swallows the failure into an empty page: {clause}"
            )


def _final_order_by(sql: str) -> str:
    """The last ORDER BY in the statement — the one that sorts the UNION and picks the row.
    (Window-function ORDER BYs inside `ROW_NUMBER() OVER (…)` are a different question and are not
    what any assertion here is about.)"""
    m = list(re.finditer(r"\nORDER BY (.+)", sql))
    assert m, "no top-level ORDER BY found"
    return m[-1].group(1)


# ══ THE QUERIES ACTUALLY BIND AND RUN ══════════════════════════════════════════════════════════


def _duck_with_fixtures(rows, clv=(), results=()):
    """A DuckDB connection carrying the three lakehouse tables the featured queries read, under the
    BARE names `strip_fqn` rewrites the Snowflake FQNs to."""
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE daily_model_predictions (
            game_pk BIGINT, game_date DATE, prediction_type VARCHAR, inserted_at TIMESTAMP,
            home_team VARCHAR, away_team VARCHAR, game_datetime TIMESTAMP,
            calibrated_win_prob DOUBLE, h2h_market_implied_prob DOUBLE,
            totals_model_prob DOUBLE, over_prob_consensus DOUBLE,
            win_prob_ci_low DOUBLE, win_prob_ci_high DOUBLE,
            layer4_h2h_decision VARCHAR, layer4_totals_decision VARCHAR,
            layer4_h2h_conviction_flag BOOLEAN, total_line_consensus DOUBLE,
            qualified_bet BOOLEAN, lineup_confirmed BOOLEAN
        )
        """
    )
    conn.execute("CREATE TABLE mart_clv_labeled_games (game_pk BIGINT, market_type VARCHAR, actual_outcome INTEGER)")
    conn.execute(
        "CREATE TABLE mart_game_results (game_pk BIGINT, home_team_won BOOLEAN, "
        "home_final_score INTEGER, away_final_score INTEGER)"
    )
    for r in rows:
        conn.execute("INSERT INTO daily_model_predictions VALUES (" + ",".join(["?"] * 19) + ")", r)
    for r in clv:
        conn.execute("INSERT INTO mart_clv_labeled_games VALUES (?,?,?)", r)
    for r in results:
        conn.execute("INSERT INTO mart_game_results VALUES (?,?,?,?)", r)
    return conn


def _pred(
    game_pk, game_date, *, h2h_model=0.60, h2h_market=0.58, tot_model=0.55, tot_market=0.54,
    hour=13, conviction=True, h2h_decision="home", totals_decision="over",
):
    return [
        game_pk, game_date, "morning", datetime(2026, 8, 7, 9, 0),
        "HOU", "SEA", datetime(2026, 8, 7, hour, 0),
        h2h_model, h2h_market, tot_model, tot_market,
        0.50, 0.70, h2h_decision, totals_decision, conviction, 8.5, True, True,
    ]


TODAY = "2026-08-07"
YESTERDAY_OF = "2026-08-08"  # the param value whose DATEADD(-1) lands on TODAY


class TestTheQueriesActuallyRun:
    """⭐ Executes every constant through the Lambda's own translation layer. See the module
    docstring: the production defect this closes was a query that could not BIND, which no
    assertion over SQL TEXT can see."""

    @pytest.mark.parametrize("name", sorted(ALL_QUERIES))
    def test_the_query_binds_and_returns_a_row_on_duckdb(self, name):
        sql = ALL_QUERIES[name]
        # `game_date` is either today's or yesterday's depending on the constant, so seed both.
        rows = [_pred(1, date(2026, 8, 7)), _pred(2, date(2026, 8, 8))]
        conn = _duck_with_fixtures(
            rows,
            clv=[(1, "h2h", 1), (1, "totals", 0)],
            results=[(1, True, 6, 3), (2, True, 6, 3)],
        )
        param = TODAY if ".today" in name else YESTERDAY_OF
        out = lakehouse_read.query_upper(conn, sql, {"today": param})
        assert len(out) == 1, f"{name} bound but returned {len(out)} rows on a slate with a qualifying game"
        assert out[0]["GAME_PK"] is not None

    def test_the_carry_over_query_returns_the_previous_day_when_today_is_empty(self):
        """The operator's second change, end to end: nothing for today, so the card shows the most
        recent published read rather than the empty state."""
        conn = _duck_with_fixtures([_pred(11, date(2026, 8, 7))], results=[(11, True, 6, 3)])
        today = lakehouse_read.query_upper(conn, picks._FEATURED_TODAY_QUERY, {"today": YESTERDAY_OF})
        assert today == [], "precondition: today must have no qualifying game"
        carried = lakehouse_read.query_upper(
            conn, picks._FEATURED_STALE_FALLBACK_QUERY, {"today": YESTERDAY_OF}
        )
        assert [r["GAME_PK"] for r in carried] == [11]


# ══ WHAT THE RULE PICKS ════════════════════════════════════════════════════════════════════════


class TestTheWidestGapWins:
    def test_the_widest_gap_beats_an_earlier_start(self):
        """The operator's change, as behaviour rather than as text. ⚠️ The fixture is built so the
        two rules DISAGREE — the early game has the small gap — because on a fixture where the
        widest gap happens also to start first, this test would pass under the OLD rule too."""
        conn = _duck_with_fixtures([
            _pred(1, date(2026, 8, 7), hour=12, h2h_model=0.60, h2h_market=0.58,
                  tot_model=0.50, tot_market=0.50),                                    # early, gap .02
            _pred(2, date(2026, 8, 7), hour=22, h2h_model=0.75, h2h_market=0.55,
                  tot_model=0.50, tot_market=0.50),                                    # late,  gap .20
        ])
        out = lakehouse_read.query_upper(conn, picks._FEATURED_TODAY_QUERY, {"today": TODAY})
        assert out[0]["GAME_PK"] == 2, "the earliest game won — the ORDER BY is still on the clock"
        assert out[0]["EDGE"] == pytest.approx(0.20)

    def test_a_game_our_models_disagree_on_is_never_featured_however_wide_the_gap(self):
        """⛔ ELIGIBILITY IS NOT ORDERING, and this clause is what keeps the sort honest. Featuring
        the day's maximum gap is a maximum order statistic: with no eligibility rule it reliably
        selects the game where OUR number is most likely to be wrong. Requiring the two independent
        estimators to agree first is what makes the widest remaining gap a disagreement with the
        market rather than an artefact of our own noise.

        The fixture gives the INELIGIBLE game the far bigger gap, so the conviction filter is the
        only thing that can decide the result (NF-D17 §7: a clause is only tested when the fixture
        satisfies every other clause)."""
        conn = _duck_with_fixtures([
            _pred(1, date(2026, 8, 7), h2h_model=0.62, h2h_market=0.58,
                  tot_model=0.50, tot_market=0.50, conviction=True),                   # gap .04
            _pred(2, date(2026, 8, 7), h2h_model=0.95, h2h_market=0.45,
                  tot_model=0.50, tot_market=0.50, conviction=False),                  # gap .50
        ])
        out = lakehouse_read.query_upper(conn, picks._FEATURED_TODAY_QUERY, {"today": TODAY})
        assert out[0]["GAME_PK"] == 1, "an ineligible game was featured because its gap was widest"

    def test_the_carry_over_shows_the_featured_pick_and_not_the_winner(self):
        """The cherry-pick guard, as behaviour. The LOSING pick has the wider gap, so it is the one
        that was featured, so it is the one carried over — even though a winner is available."""
        conn = _duck_with_fixtures(
            [
                _pred(1, date(2026, 8, 7), h2h_model=0.80, h2h_market=0.55,
                      tot_model=0.50, tot_market=0.50),                                # gap .25 — LOST
                _pred(2, date(2026, 8, 7), h2h_model=0.60, h2h_market=0.58,
                      tot_model=0.50, tot_market=0.50),                                # gap .02 — WON
            ],
            clv=[(1, "h2h", 0), (2, "h2h", 1)],
        )
        out = lakehouse_read.query_upper(
            conn, picks._FEATURED_STALE_FALLBACK_QUERY, {"today": YESTERDAY_OF}
        )
        assert out[0]["GAME_PK"] == 1, "the winning pick was carried forward — outcome selection"
        assert out[0]["ACTUAL_OUTCOME"] == 0

    def test_the_recap_resolves_the_same_pick_as_the_card(self):
        """The recap and the carry-over read the same day through different constants. They named
        different games before this story: the recap ranked over `qualified_bet` with no conviction
        filter and led on `actual_outcome DESC`."""
        conn = _duck_with_fixtures(
            [
                _pred(1, date(2026, 8, 7), h2h_model=0.80, h2h_market=0.55,
                      tot_model=0.50, tot_market=0.50),
                _pred(2, date(2026, 8, 7), h2h_model=0.60, h2h_market=0.58,
                      tot_model=0.50, tot_market=0.50),
            ],
            clv=[(1, "h2h", 0), (2, "h2h", 1)],
        )
        card = lakehouse_read.query_upper(conn, picks._FEATURED_STALE_FALLBACK_QUERY, {"today": YESTERDAY_OF})
        recap = lakehouse_read.query_upper(conn, picks._FEATURED_YESTERDAY_QUERY, {"today": YESTERDAY_OF})
        assert card[0]["GAME_PK"] == recap[0]["GAME_PK"]
        assert card[0]["MARKET_TYPE"] == recap[0]["MARKET_TYPE"]

    def test_the_recap_uses_the_same_eligible_population_as_the_writer(self):
        """`qualified_bet` is a DIFFERENT set from the featured one. A recap drawn from it can name
        a game that was never featured at all."""
        src = picks._FEATURED_YESTERDAY_QUERY
        assert "layer4_h2h_conviction_flag = TRUE" in src
        assert "qualified_bet" not in src


# ══ THE COPY IS DOWNSTREAM OF THE SQL ══════════════════════════════════════════════════════════


class TestTheCopyMatchesTheQuery:
    """The home page describes this selection in words. The first E9.46 cut shipped a description
    of a rule the SQL did not implement; the copy is only true while the ORDER BY holds, so it is
    pinned to it here rather than left to a reader to re-check."""

    def _frame(self) -> str:
        src = (_REPO / "frontend/lib/home-copy.ts").read_text()
        m = re.search(r"export const MLB_PROOF = \{(.*?)\n\} as const", src, re.S)
        assert m, "MLB_PROOF not found"
        body = m.group(1)
        fm = re.search(r"\n  frame:\s*\n?\s*\"(.*?)\",\n", body, re.S)
        assert fm, "MLB_PROOF.frame not found"
        return fm.group(1)

    def test_the_home_copy_describes_the_actual_order_by(self):
        frame = self._frame()
        assert "furthest from the market" in frame, (
            "the copy no longer describes the gap-based selection the SQL implements"
        )

    def test_the_retired_start_time_rule_is_gone_from_the_copy(self):
        frame = self._frame()
        for stale in ("first to start", "earliest", "first game"):
            assert stale not in frame.lower(), f"copy still describes the retired rule: {stale!r}"

    def test_the_gap_caveat_survives_the_sort_key(self):
        """Sorting on the gap turns it into a maximum order statistic. The card says so — a big
        green number with no caveat reads as an opportunity, which is the claim six recorded
        no-edge results do not support."""
        src = (_REPO / "frontend/lib/home-copy.ts").read_text()
        m = re.search(r"\n  gapHint:\s*\n?\s*\"(.*?)\",\n", src, re.S)
        assert m, "MLB_PROOF.gapHint not found"
        hint = m.group(1).lower()
        assert "disagreement, not advantage" in hint
        assert "most likely to be ours getting something wrong" in hint, (
            "the maximum-order-statistic caveat was dropped from the gap explanation"
        )
