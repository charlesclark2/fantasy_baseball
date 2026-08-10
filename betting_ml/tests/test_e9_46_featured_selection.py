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
    "ORDER BY market_pref ASC, edge DESC NULLS LAST, "
    "game_datetime ASC NULLS LAST, game_pk ASC, market_type ASC"
)


# ══ THE SHARED RULE ════════════════════════════════════════════════════════════════════════════


class TestTheSelectionRuleIsShared:
    def test_every_featured_query_shares_the_rule(self):
        """All six sort identically. A recap that resolves a different pick than the card above it
        is not a recap — it is a second, unannounced pick."""
        for name, sql in ALL_QUERIES.items():
            assert EXPECTED_ORDER_BY in sql, f"{name} does not carry the shared ORDER BY"

    def test_the_market_leads_and_the_gap_breaks_it(self):
        """The two operator changes are BOTH sort keys and their ORDER matters, so assert the
        order rather than the presence. `market_pref` first (alternate the market), `edge` second
        (best gap within it), `game_datetime` demoted to a tie-break. Asserting only that all
        three appear would pass on either previous rule."""
        for name, sql in ALL_QUERIES.items():
            clause = _final_order_by(sql)
            keys = [k.strip().lower() for k in clause.split(",")]
            assert keys[0].startswith("market_pref"), (
                f"{name} does not lead on the market — the card will not alternate: {clause}"
            )
            assert keys[1].startswith("edge desc"), (
                f"{name} does not break the market on the gap: {clause}"
            )
            assert any(k.startswith("game_datetime") for k in keys[2:]), (
                f"{name} dropped the deterministic tie-break: {clause}"
            )

    def test_the_two_market_branches_are_exact_complements(self):
        """⚠️ The alternation is only an alternation while the two `market_pref` expressions are
        each other's inverse. A copy-paste that left both branches preferring the same market on
        the same parity would silently pin the card to one market forever — and every other
        assertion here would still pass, because the ORDER BY would be intact and the query would
        bind. So the two fragments are compared directly."""
        import re as _re

        for mod, label in ((_wss, "writer"), (picks, "router")):
            h2h = _re.sub(r"\s+", " ", mod._MARKET_PREF_H2H)
            tot = _re.sub(r"\s+", " ", mod._MARKET_PREF_TOTALS)
            assert h2h != tot, f"{label}: both market branches carry the SAME preference"
            # Same condition, opposite outcomes: swapping THEN/ELSE turns one into the other.
            assert h2h.replace("THEN 0 ELSE 1", "THEN 1 ELSE 0") == tot, (
                f"{label}: the branches are not complements —\n  h2h: {h2h}\n  tot: {tot}"
            )

    def test_the_alternation_keys_off_the_rows_own_date(self):
        """⛔ NEVER off `%(today)s`. Three of the six constants resolve YESTERDAY's pick; keying
        the parity off the parameter would make each of them need a `-1`, and one omission makes
        the recap name a different MARKET than the card it recaps. Off the row it is correct by
        construction."""
        for mod, label in ((_wss, "writer"), (picks, "router")):
            for frag in (mod._MARKET_PREF_H2H, mod._MARKET_PREF_TOTALS):
                assert "b.game_date" in frag, f"{label}: parity is not read from the row: {frag}"
                assert "today" not in frag, f"{label}: parity is keyed off the parameter: {frag}"

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


# ── The dates are load-bearing now that the market alternates on day-of-year parity ──────────
#   2026-08-07 → DAYOFYEAR 219 (odd)  → TOTALS is the preferred market
#   2026-08-08 → DAYOFYEAR 220 (even) → MONEYLINE is the preferred market
# A test about the GAP must hold the market constant, or `market_pref` decides the result before
# `edge` is ever consulted and the test measures the wrong key.
TODAY = "2026-08-07"          # totals day
H2H_DAY = "2026-08-08"        # moneyline day
YESTERDAY_OF = "2026-08-08"   # DATEADD(-1) → 2026-08-07, a totals day
H2H_DAY_NEXT = "2026-08-09"   # DATEADD(-1) → 2026-08-08, a moneyline day


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
            _pred(1, date(2026, 8, 8), hour=12, h2h_model=0.60, h2h_market=0.58,
                  totals_decision=None),                                               # early, gap .02
            _pred(2, date(2026, 8, 8), hour=22, h2h_model=0.75, h2h_market=0.55,
                  totals_decision=None),                                               # late,  gap .20
        ])
        out = lakehouse_read.query_upper(conn, picks._FEATURED_TODAY_QUERY, {"today": H2H_DAY})
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
            _pred(1, date(2026, 8, 8), h2h_model=0.62, h2h_market=0.58,
                  totals_decision=None, conviction=True),                              # gap .04
            _pred(2, date(2026, 8, 8), h2h_model=0.95, h2h_market=0.45,
                  totals_decision=None, conviction=False),                             # gap .50
        ])
        out = lakehouse_read.query_upper(conn, picks._FEATURED_TODAY_QUERY, {"today": H2H_DAY})
        assert out[0]["GAME_PK"] == 1, "an ineligible game was featured because its gap was widest"

    def test_the_carry_over_shows_the_featured_pick_and_not_the_winner(self):
        """The cherry-pick guard, as behaviour. The LOSING pick has the wider gap, so it is the one
        that was featured, so it is the one carried over — even though a winner is available."""
        conn = _duck_with_fixtures(
            [
                _pred(1, date(2026, 8, 8), h2h_model=0.80, h2h_market=0.55,
                      totals_decision=None),                                           # gap .25 — LOST
                _pred(2, date(2026, 8, 8), h2h_model=0.60, h2h_market=0.58,
                      totals_decision=None),                                           # gap .02 — WON
            ],
            clv=[(1, "h2h", 0), (2, "h2h", 1)],
        )
        out = lakehouse_read.query_upper(
            conn, picks._FEATURED_STALE_FALLBACK_QUERY, {"today": H2H_DAY_NEXT}
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


# ══ THE MARKET ALTERNATES ══════════════════════════════════════════════════════════════════════


class TestTheMarketAlternates:
    """Sorting on the raw gap alone does not pick the most interesting disagreement — it picks the
    market whose probabilities move more. Measured over 34 slates, totals won 31 of them, because
    the totals model's eligible gaps are ~3× wider (median 0.116 vs 0.036) purely as a matter of
    scale. `market_pref` is the fix."""

    def _both_markets(self, game_date):
        """One game carrying BOTH an eligible moneyline and an eligible total, with the TOTAL given
        the far wider gap (0.30 vs 0.04). ⭐ That asymmetry is the whole point: it reproduces the
        real-world skew, so on a moneyline day the market key has to beat a much bigger number to
        win. A symmetric fixture would pass whether or not `market_pref` did anything."""
        return [_pred(1, game_date, h2h_model=0.62, h2h_market=0.58,
                      tot_model=0.80, tot_market=0.50)]

    def test_the_market_flips_with_the_date(self):
        """The alternation itself: the SAME game, the SAME two gaps, one day apart — and a
        different market is featured. Asserting one day alone could not distinguish alternation
        from a fixed preference."""
        totals_day = lakehouse_read.query_upper(
            conn := _duck_with_fixtures(self._both_markets(date(2026, 8, 7))),
            picks._FEATURED_TODAY_QUERY, {"today": TODAY},
        )
        h2h_day = lakehouse_read.query_upper(
            _duck_with_fixtures(self._both_markets(date(2026, 8, 8))),
            picks._FEATURED_TODAY_QUERY, {"today": H2H_DAY},
        )
        assert conn is not None
        assert totals_day[0]["MARKET_TYPE"] == "totals"
        assert h2h_day[0]["MARKET_TYPE"] == "h2h", (
            "the moneyline never gets a turn — the card is pinned to totals by the wider gaps"
        )

    def test_the_days_market_beats_a_much_wider_gap_in_the_other(self):
        """⭐ THE KEY ORDER, as behaviour. On a moneyline day the featured read is the moneyline
        even though the total on the same game disagrees by 30 points against the moneyline's 4 —
        i.e. `market_pref` genuinely outranks `edge`, rather than the two happening to agree."""
        out = lakehouse_read.query_upper(
            _duck_with_fixtures(self._both_markets(date(2026, 8, 8))),
            picks._FEATURED_TODAY_QUERY, {"today": H2H_DAY},
        )
        assert out[0]["MARKET_TYPE"] == "h2h"
        assert out[0]["EDGE"] == pytest.approx(0.04)

    def test_the_best_gap_still_wins_inside_the_days_market(self):
        """Alternation chooses the MARKET; the gap still chooses the GAME. Two moneyline-only
        games on a moneyline day: the wider gap is featured."""
        conn = _duck_with_fixtures([
            _pred(1, date(2026, 8, 8), h2h_model=0.60, h2h_market=0.58, totals_decision=None),
            _pred(2, date(2026, 8, 8), h2h_model=0.78, h2h_market=0.55, totals_decision=None),
        ])
        out = lakehouse_read.query_upper(conn, picks._FEATURED_TODAY_QUERY, {"today": H2H_DAY})
        assert out[0]["GAME_PK"] == 2

    def test_the_other_market_is_featured_when_the_days_market_has_nothing(self):
        """⛔ A PREFERENCE, NOT A FILTER, and this is why. Some days no game qualifies in the
        market whose turn it is; featuring nothing would be a worse answer than featuring the other
        market, because the card LABELS which market it is showing either way. Written as a
        `market_pref ASC` sort key rather than a `WHERE`, so the fallback is automatic.

        ⇒ alternation is the normal rhythm, not a guarantee — copy must not promise strict
        alternation, which `TestTheCopyMatchesTheQuery` pins."""
        conn = _duck_with_fixtures([
            # A moneyline day, but the only eligible read on the board is a total.
            _pred(1, date(2026, 8, 8), h2h_decision=None, tot_model=0.70, tot_market=0.52),
        ])
        out = lakehouse_read.query_upper(conn, picks._FEATURED_TODAY_QUERY, {"today": H2H_DAY})
        assert len(out) == 1, "the card went empty rather than falling back to the other market"
        assert out[0]["MARKET_TYPE"] == "totals"

    def test_a_totals_read_carries_the_line_it_is_about(self):
        """"Our model leans Over" is not a statement until the number is beside it. The line is
        served for a total and NULL for a moneyline, where it would be meaningless."""
        conn = _duck_with_fixtures([
            _pred(1, date(2026, 8, 7), h2h_decision=None, tot_model=0.70, tot_market=0.52),
        ])
        out = lakehouse_read.query_upper(conn, picks._FEATURED_TODAY_QUERY, {"today": TODAY})
        assert out[0]["MARKET_TYPE"] == "totals"
        assert out[0]["TOTAL_LINE"] == pytest.approx(8.5)

        conn2 = _duck_with_fixtures([
            _pred(2, date(2026, 8, 8), totals_decision=None),
        ])
        out2 = lakehouse_read.query_upper(conn2, picks._FEATURED_TODAY_QUERY, {"today": H2H_DAY})
        assert out2[0]["MARKET_TYPE"] == "h2h"
        assert out2[0]["TOTAL_LINE"] is None, "a moneyline read is carrying a total line"


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


# ══ THE CARRY-OVER IS A POINT READ, NOT A QUERY ════════════════════════════════════════════════


class TestTheCarryOverServesThePublishedBlob:
    """🩹 THE SECOND, INDEPENDENT REASON THE CARRY-OVER DID NOT WORK IN PRODUCTION.

    Fixing the ORDER BY made `_FEATURED_STALE_FALLBACK_QUERY` bind — and it still could not deliver
    a card, because it is a `SELECT p.*` over the 94-column `daily_model_predictions`, the read
    E9.26b documents as reliably failing INSIDE the API Lambda while working perfectly outside it.
    `lakehouse_query` swallows that into `[]` by design, so the two failures are indistinguishable
    from "no game qualified" and from each other. Measured 2026-08-08 09:17Z against the deployed
    Lambda: `/picks/featured` served `game_pk: null` while yesterday's blob sat complete in
    DynamoDB and the same query returned the right row from a laptop.

    ⇒ the home page now carries over the PUBLISHED blob via a DynamoDB point read. These tests pin
    that it does not depend on the lakehouse at all — which is the property that makes it work.
    """

    @staticmethod
    def _wire(monkeypatch, cache: dict, *, lakehouse_raises=True):
        monkeypatch.setattr(picks.serving_cache, "get_cache",
                            lambda ns, day: cache.get(day), raising=True)
        monkeypatch.setattr(picks, "get_cache", lambda key: None, raising=True)
        monkeypatch.setattr(picks.cost_guardrails, "degrade_mode_enabled", lambda: False, raising=True)

        def _boom(*a, **kw):
            if lakehouse_raises:
                raise AssertionError("the carry-over reached for the lakehouse")
            return []

        monkeypatch.setattr(picks, "lakehouse_query", _boom, raising=True)
        monkeypatch.setattr(picks, "current_game_date_iso", lambda: "2026-08-08", raising=True)

    _BLOB = {
        "game_pk": 823103, "matchup": "TB @ SEA", "market_type": "h2h", "pick_side": "away",
        "edge": 3.04, "model_prob": 0.47, "market_prob": 0.44, "pick_date": "2026-08-07",
        "home_team": "SEA", "away_team": "TB", "is_stale": False, "is_preliminary": True,
        "yesterday": {"matchup": "DET @ SEA", "market_type": "totals",
                      "outcome": "Won", "status": "win"},
    }

    def test_the_previous_days_published_read_is_served_without_touching_the_lakehouse(
        self, monkeypatch
    ):
        """⭐ THE LOAD-BEARING ONE. `lakehouse_query` is wired to RAISE, so the card can only be
        produced by the point read. A test that merely asserted the right payload would pass even
        if the answer had come from the query that cannot run in prod."""
        self._wire(monkeypatch, {"2026-08-07": dict(self._BLOB)})
        out = picks.get_featured_pick()
        assert out.game_pk == 823103
        assert out.matchup == "TB @ SEA"
        assert out.pick_date == "2026-08-07"

    def test_a_carried_over_card_announces_itself_but_keeps_its_recap(self, monkeypatch):
        """Two fields are rewritten and one is deliberately KEPT.

        `is_stale` is what makes the card announce itself — serving yesterday's numbers unlabelled
        is the one genuinely dangerous state this block can be in. `is_preliminary` describes
        whether lineups were confirmed for a slate that has since finished, so it is meaningless
        here.

        ⭐ THE RECAP STAYS, and an earlier cut of this test asserted the opposite. Dropping it
        identified a real ambiguity — a recap labelled "Yesterday" beside a card that is ITSELF
        yesterday names the wrong day — and then solved it by deleting the only self-grading on a
        card that is purely retrospective. The label is the thing that was wrong, not the content;
        the component names the DATE on a stale card.

        ⚠️ It is also the ONLY result that can be shown here: grading the carried pick's own game
        needs `mart_game_results` (statcast-derived, rebuilt by the daily job) or
        `stg_statsapi_games` (schedule capture is frozen 04:00–14:00 UTC by design), and both
        refresh at roughly the moment the carry-over ends."""
        self._wire(monkeypatch, {"2026-08-07": dict(self._BLOB)})
        out = picks.get_featured_pick()
        assert out.is_stale is True
        assert out.is_preliminary is False
        assert out.yesterday is not None, (
            "the carried card lost its recap — the only self-grading a logged-out visitor sees"
        )
        assert out.yesterday.matchup == "DET @ SEA"
        assert out.yesterday.outcome == "Won"

    def test_todays_own_read_is_preferred_over_the_carry_over(self, monkeypatch):
        """The carry-over must never shadow a published slate — it is a fallback, not a cache."""
        today = {**self._BLOB, "game_pk": 999, "pick_date": "2026-08-08"}
        self._wire(monkeypatch, {"2026-08-08": today, "2026-08-07": dict(self._BLOB)})
        out = picks.get_featured_pick()
        assert out.game_pk == 999
        assert out.is_stale is False

    def test_it_reaches_back_past_a_missing_day_but_not_indefinitely(self, monkeypatch):
        """A late or failed run should not blank the page; a week-old card should not be presented
        as 'the most recent read' either. The bound is a product judgement, so it is pinned."""
        self._wire(monkeypatch, {"2026-08-05": {**self._BLOB, "pick_date": "2026-08-05"}})
        assert picks.get_featured_pick().pick_date == "2026-08-05"

        # One day further back than the bound allows: fall through to the honest empty state.
        self._wire(monkeypatch, {"2026-08-04": {**self._BLOB, "pick_date": "2026-08-04"}},
                   lakehouse_raises=False)
        assert picks.get_featured_pick().game_pk is None

    def test_an_empty_shell_blob_is_not_carried_over(self, monkeypatch):
        """A stored `game_pk: null` is the record of a day on which nothing qualified. Carrying it
        forward would render the empty state while claiming to be a previous read."""
        self._wire(monkeypatch, {"2026-08-07": {"game_pk": None}}, lakehouse_raises=False)
        assert picks.get_featured_pick().game_pk is None

    def test_the_carry_over_helper_never_raises_on_a_bad_read(self, monkeypatch):
        """Defence in depth, tested at the level where it is real.

        ⚠️ The first draft asserted this through the ENDPOINT, with a raising `get_cache` — and it
        failed, correctly. `serving_cache.get_cache` already swallows every exception and returns
        None, so a raising point read cannot happen in production, and the endpoint's own first
        cache lookup is unguarded precisely because it does not need a guard. Asserting the
        endpoint's behaviour under an impossible input would have been testing the monkeypatch.

        What IS worth pinning is the helper's own contract: whatever it is handed, it answers with
        a payload or with None, never by raising — because a missing carry-over is a cosmetic gap
        on the landing page and a 500 is an outage."""
        def _explode(ns, day):
            raise RuntimeError("dynamo is unhappy")

        monkeypatch.setattr(picks.serving_cache, "get_cache", _explode, raising=True)
        assert picks._carry_over_recent_featured("2026-08-08") is None

    def test_an_unparseable_blob_is_skipped_rather_than_served(self):
        """A blob written by a build whose schema this one cannot read must not 500 the page."""
        import unittest.mock as mock

        with mock.patch.object(picks.serving_cache, "get_cache",
                               return_value={"game_pk": 1, "edge": "not-a-number"}):
            assert picks._carry_over_recent_featured("2026-08-08") is None
