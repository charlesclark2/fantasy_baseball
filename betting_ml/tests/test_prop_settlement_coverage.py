"""test_prop_settlement_coverage.py — E9.49 pitcher-K prop settlement coverage.

THE DEFECT THIS PINS. Pitcher-strikeout props (E9.42) settle against the starter's actual
K total from `mart_starting_pitcher_game_log` — a mart derived from Statcast
(stg_batter_pitches) and rebuilt only by the heavy DAILY lakehouse W2 step. So it
structurally LAGS a game's final by >= 1 day, while the SCORE source (stg_statsapi_games)
is intraday-fresh. Consequence, measured on prod 2026-07-29: h2h/totals settled same-night
on the evening passes while a K prop on a game that had been FINAL for hours stayed `open`,
and would stay open for another day or two. A bet that does not close is a trust failure,
and it was structurally invisible because nothing recorded WHEN a bet closed.

The cure has three parts, all pinned here:
  1. A FINAL-game prop the mart cannot answer falls back to the live MLB Stats API boxscore
     — but ONLY after an independent live-Final confirmation, and ONLY for a pitcher the
     boxscore itself marks a starter. A FINAL-game prop bet can no longer stay silently open.
  2. Settling stamps `settled_at` (+ `settle_source`), and the Bet response model DECLARES
     both — an undeclared field is dropped silently on serialize (the E9.41 class).
  3. A bet must carry its grading inputs at WRITE time (total_line / prop_line + player_id),
     so an unsettleable bet can't be created at all.

Fast-gate-safe: no network, no AWS, no Snowflake — the lakehouse reads and every HTTP call
are monkeypatched, and DynamoDB is a FakeTable.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import scripts.settle_user_bets as sub

REPO = Path(__file__).resolve().parents[2]
SETTLE = (REPO / "scripts" / "settle_user_bets.py").read_text()


# ── Fixtures: a fake DynamoDB table + a fake lakehouse ────────────────────────

class _FakeTable:
    """Records every update_item; serves a fixed pending set from the GSI scan."""

    def __init__(self, pending):
        self._pending = pending
        self.updates: list[dict] = []

    def scan(self, **kwargs):
        return {"Items": list(self._pending)}

    def update_item(self, **kwargs):
        self.updates.append(kwargs)
        return {}


def _prop_bet(**over):
    bet = {
        "user_id": "u1",
        "bet_id": "b-prop",
        "market": "strikeouts over",
        "pending_game_pk": 823596,
        "player_id": 700363,
        "prop_line": 4.5,
        "stake": 5,
        "american_odds": -110,
    }
    bet.update(over)
    return bet


def _install(monkeypatch, pending, *, scores, mart_ks, api_final=None, boxscore=None):
    """Wire settle_user_bets against fakes. Returns the FakeTable."""
    table = _FakeTable(pending)

    class _Res:
        def Table(self, _name):
            return table

    class _Sess:
        def resource(self, *a, **k):
            return _Res()

    monkeypatch.setattr(sub, "_aws_session", lambda: _Sess())
    monkeypatch.setattr(sub, "_connect_lakehouse", lambda: _FakeConn())
    monkeypatch.setattr(sub, "_final_scores", lambda conn, pks: scores)
    monkeypatch.setattr(sub, "_starter_strikeouts", lambda conn, pks: mart_ks)
    # The fallback's two HTTP hops, stubbed. Default = the API confirms nothing, which is
    # the fail-safe branch; a test opts in by passing api_final/boxscore.
    monkeypatch.setattr(sub, "_statsapi_final_games", lambda pks: set(api_final or ()))
    monkeypatch.setattr(sub, "_boxscore_starter_strikeouts", lambda gp: dict((boxscore or {}).get(gp, {})))
    return table


class _FakeConn:
    def close(self):
        pass


# ── 1. A FINAL-game prop bet cannot stay silently open ───────────────────────

class TestFinalGamePropCannotStayOpen:
    """The headline guard: game Final + mart empty ⇒ the bet still settles."""

    def test_mart_gap_is_closed_by_the_boxscore_fallback(self, monkeypatch):
        table = _install(
            monkeypatch,
            [_prop_bet()],
            scores={823596: (3, 2)},
            mart_ks={},                       # the daily-W2 lag: no row for this game yet
            api_final={823596},
            boxscore={823596: {700363: 4}},   # actual: 4 K vs a 4.5 line ⇒ over LOSES
        )
        assert sub.main([]) == 0
        assert len(table.updates) == 1, (
            "a prop bet on a FINAL game was left OPEN because the Statcast-derived mart had "
            "no row yet — this is exactly the E9.49 defect; the boxscore fallback must close it"
        )
        vals = table.updates[0]["ExpressionAttributeValues"]
        assert vals[":o"] == "loss"
        assert float(vals[":p"]) == -5.0
        assert vals[":s"] == "statsapi"

    def test_the_mart_stays_primary_when_it_has_the_row(self, monkeypatch):
        # The fallback must not displace the mart — every model reads the mart, so a settled
        # bet should agree with it whenever it can.
        table = _install(
            monkeypatch,
            [_prop_bet()],
            scores={823596: (3, 2)},
            mart_ks={(823596, 700363): 7},
            api_final={823596},
            boxscore={823596: {700363: 4}},   # would disagree — must never be consulted
        )
        assert sub.main([]) == 0
        vals = table.updates[0]["ExpressionAttributeValues"]
        assert vals[":s"] == "mart"
        assert vals[":o"] == "win", "7 K vs a 4.5 over line is a win off the MART row"

    def test_settling_removes_the_bet_from_the_pending_index(self, monkeypatch):
        table = _install(
            monkeypatch, [_prop_bet()], scores={823596: (3, 2)}, mart_ks={},
            api_final={823596}, boxscore={823596: {700363: 4}},
        )
        sub.main([])
        assert "REMOVE pending_game_pk" in table.updates[0]["UpdateExpression"]


# ── 2. …but never at the cost of a WRONG settlement ──────────────────────────

class TestFallbackRefusesToGuess:
    """Every branch where the fallback cannot be sure must leave the bet pending."""

    def test_unconfirmed_final_leaves_the_bet_pending(self, monkeypatch):
        # Our own table says Final; the live API does not confirm it. Settling here would
        # bank a PARTIAL mid-game K count as the final answer.
        table = _install(
            monkeypatch, [_prop_bet()], scores={823596: (3, 2)}, mart_ks={},
            api_final=set(), boxscore={823596: {700363: 4}},
        )
        assert sub.main([]) == 0
        assert table.updates == [], "an unconfirmed Final must never settle a prop"

    def test_a_scratched_starter_leaves_the_bet_pending(self, monkeypatch):
        # The pitcher never started: no boxscore starter line ⇒ no settlement, no guess.
        table = _install(
            monkeypatch, [_prop_bet()], scores={823596: (3, 2)}, mart_ks={},
            api_final={823596}, boxscore={823596: {640455: 6}},   # a different pitcher
        )
        assert sub.main([]) == 0
        assert table.updates == []

    def test_an_unfinished_game_is_never_touched(self, monkeypatch):
        table = _install(monkeypatch, [_prop_bet()], scores={}, mart_ks={},
                         api_final={823596}, boxscore={823596: {700363: 4}})
        assert sub.main([]) == 0
        assert table.updates == []

    def test_dry_run_writes_nothing(self, monkeypatch):
        table = _install(monkeypatch, [_prop_bet()], scores={823596: (3, 2)}, mart_ks={},
                         api_final={823596}, boxscore={823596: {700363: 4}})
        assert sub.main(["--dry-run"]) == 0
        assert table.updates == []

    def test_fallback_can_be_switched_off(self, monkeypatch):
        monkeypatch.setenv("PROP_STATSAPI_FALLBACK", "0")
        # _install stubs only the two HTTP hops, so the REAL _statsapi_strikeouts gate runs
        # and the kill switch is genuinely exercised. This is also the pre-fix behaviour —
        # the inverse of test_mart_gap_is_closed_by_the_boxscore_fallback above, which proves
        # the headline guard discriminates rather than passing vacuously.
        table = _install(monkeypatch, [_prop_bet()], scores={823596: (3, 2)}, mart_ks={},
                         api_final={823596}, boxscore={823596: {700363: 4}})
        assert sub.main([]) == 0
        assert table.updates == []

    def test_a_final_game_left_unsettled_still_alerts_loudly(self, monkeypatch, capsys):
        _install(monkeypatch, [_prop_bet()], scores={823596: (3, 2)}, mart_ks={},
                 api_final=set(), boxscore={})
        sub.main([])
        assert "[ALERT]" in capsys.readouterr().err, (
            "settlement is a WARN-tier op — a FINAL game it could not settle must reach "
            "stderr or the gap is invisible"
        )


# ── 3. Grading arithmetic (the push edge + both sides) ───────────────────────

class TestPropGrading:
    @pytest.mark.parametrize("market,line,ks,expected", [
        ("strikeouts over", 4.5, 4, "loss"),
        ("strikeouts over", 4.5, 5, "win"),
        ("strikeouts under", 4.5, 4, "win"),
        ("strikeouts under", 4.5, 5, "loss"),
        ("strikeouts over", 5.0, 5, "push"),    # integer line ⇒ push is reachable
        ("strikeouts under", 5.0, 5, "push"),
        ("strikeouts over", 3.5, 0, "loss"),    # a real logged bet: 0 K
    ])
    def test_outcome(self, market, line, ks, expected):
        assert sub._prop_outcome(market, ks, line) == expected

    def test_missing_line_never_grades(self):
        assert sub._prop_outcome("strikeouts over", 7, None) is None


# ── 4. An already-settled bet cannot linger in the pending index ─────────────

class TestOrphanedPendingIndexEntries:
    def test_settled_bet_is_de_indexed_not_regraded(self, monkeypatch):
        # Found in the prod audit: a bet settled 'push' in June still carried
        # pending_game_pk, so every settle pass re-scanned it forever.
        orphan = _prop_bet(bet_id="b-orphan", outcome="push", profit_loss=0)
        table = _install(monkeypatch, [orphan], scores={823596: (3, 2)},
                         mart_ks={(823596, 700363): 9}, api_final={823596})
        assert sub.main([]) == 0
        assert len(table.updates) == 1
        expr = table.updates[0]["UpdateExpression"]
        assert expr.strip() == "REMOVE pending_game_pk", (
            "an already-settled bet must be de-indexed, never re-graded (that would "
            "overwrite a user's recorded outcome)"
        )


# ── 5. settled_at / settle_source are recorded AND declared ──────────────────

class TestSettlementIsObservable:
    def test_settling_stamps_settled_at(self, monkeypatch):
        table = _install(monkeypatch, [_prop_bet()], scores={823596: (3, 2)}, mart_ks={},
                         api_final={823596}, boxscore={823596: {700363: 4}})
        sub.main([])
        upd = table.updates[0]
        assert "settled_at = if_not_exists(settled_at, :t)" in upd["UpdateExpression"], (
            "settled_at must be if_not_exists — a re-settle must never rewrite the "
            "canonical close time"
        )
        assert upd["ExpressionAttributeValues"][":t"].startswith("20")

    def test_bet_response_model_declares_the_new_fields(self):
        # E9.41 class: a field the STORE carries but the response model does not declare is
        # dropped SILENTLY on serialize — the writer alone is not enough.
        from app.backend.models.bets import Bet
        for field in ("settled_at", "settle_source"):
            assert field in Bet.model_fields, (
                f"{field} is written to DynamoDB but not declared on Bet — Pydantic will "
                f"strip it from every /bets response (the E9.41 failure mode)"
            )

    def test_read_side_update_also_stamps_settled_at(self, monkeypatch):
        # The auto-void path in routers/bets.py settles through dynamo.update_bet, which must
        # record settled_at too — otherwise voided bets have no close time.
        from app.backend.services import dynamo

        class _T:
            def __init__(self):
                self.last = None

            def get_item(self, Key):
                return {"Item": {"user_id": "u", "bet_id": "b", "pending_game_pk": 1, "stake": 5}}

            def update_item(self, **kwargs):
                self.last = kwargs
                return {"Attributes": {"user_id": "u", "bet_id": "b"}}

        t = _T()
        monkeypatch.setattr(dynamo, "_bets_table", lambda: t)
        dynamo.update_bet("u", "b", {"outcome": "void", "profit_loss": 0.0})
        assert "#sa = if_not_exists(#sa, :sa)" in t.last["UpdateExpression"]
        assert t.last["ExpressionAttributeNames"]["#sa"] == "settled_at"

    def test_non_settling_edit_does_not_stamp(self, monkeypatch):
        from app.backend.services import dynamo

        class _T:
            def __init__(self):
                self.last = None

            def get_item(self, Key):
                return {"Item": {"user_id": "u", "bet_id": "b", "pending_game_pk": 1, "stake": 5}}

            def update_item(self, **kwargs):
                self.last = kwargs
                return {"Attributes": {}}

        t = _T()
        monkeypatch.setattr(dynamo, "_bets_table", lambda: t)
        dynamo.update_bet("u", "b", {"stake": 20.0})
        assert "settled_at" not in str(t.last["ExpressionAttributeNames"].values())


# ── 6. An unsettleable bet cannot be CREATED ─────────────────────────────────

class TestGradingInputsRequiredAtWriteTime:
    def test_totals_bet_without_a_line_is_rejected(self):
        from app.backend.models.bets import BetCreate
        with pytest.raises(ValueError, match="total_line"):
            BetCreate(game_pk=1, score_date="2026-07-02", market="over",
                      american_odds=-125, stake=5)

    def test_prop_bet_without_a_line_is_rejected(self):
        from app.backend.models.bets import BetCreate
        with pytest.raises(ValueError, match="prop_line"):
            BetCreate(game_pk=1, score_date="2026-07-29", market="strikeouts over",
                      american_odds=-110, stake=5, player_id=700363)

    def test_prop_bet_without_a_player_is_rejected(self):
        from app.backend.models.bets import BetCreate
        with pytest.raises(ValueError, match="player_id"):
            BetCreate(game_pk=1, score_date="2026-07-29", market="strikeouts under",
                      american_odds=-110, stake=5, prop_line=4.5)

    def test_a_well_formed_prop_bet_is_accepted(self):
        from app.backend.models.bets import BetCreate
        bet = BetCreate(game_pk=823596, score_date="2026-07-29", market="strikeouts over",
                        american_odds=-110, stake=5, player_id=700363, prop_line=4.5)
        assert bet.prop_line == 4.5

    def test_h2h_needs_no_line(self):
        from app.backend.models.bets import BetCreate
        assert BetCreate(game_pk=1, score_date="2026-07-29", market="h2h home",
                         american_odds=-110, stake=5).total_line is None


# ── 8. A WRITE-time rule must never reject a STORED bet ──────────────────────

class TestReadModelIsNotBoundByCreateRules:
    """Shipped as a 500 on GET /bets, 2026-07-29. `Bet` subclassed `BetCreate`, so the
    new create-time rule above ran on every stored row during serialization — the one
    legacy over/under logged without a line (2026-07-02) raised, and because the router
    built the whole list at once, ONE un-representable row 500'd the user's ENTIRE bet log.
    A tightened input rule is retroactive over history unless the read model is separate.
    """

    def test_bet_does_not_inherit_the_create_validators(self):
        from app.backend.models.bets import Bet, BetCreate
        assert not issubclass(Bet, BetCreate), (
            "Bet must NOT subclass BetCreate — every validator added for CREATE would then "
            "run against stored rows on GET /bets and 500 the page for historical data"
        )

    def test_a_legacy_totals_bet_without_a_line_still_serializes(self):
        # The exact prod row (bet fc396f74…, LAA @ SEA, 2026-07-02).
        from app.backend.models.bets import Bet
        bet = Bet(bet_id="fc396f74", user_id="u1", placed_at="2026-07-02T23:43:47Z",
                  game_pk=823119, score_date="2026-07-02", market="over",
                  american_odds=-125, stake=5.0)   # no total_line — unsettleable but REAL
        assert bet.total_line is None and bet.market == "over"

    def test_the_write_rule_is_still_enforced(self):
        # The read fix must not have quietly disabled the create-time guard.
        from app.backend.models.bets import BetCreate
        with pytest.raises(ValueError, match="total_line"):
            BetCreate(game_pk=823119, score_date="2026-07-02", market="over",
                      american_odds=-125, stake=5.0)

    def test_one_bad_row_cannot_blank_the_whole_bet_log(self, monkeypatch):
        # Defence in depth: even an genuinely un-representable row must cost only itself.
        from app.backend.routers import bets as bets_router

        good = {"bet_id": "ok", "user_id": "u", "placed_at": "2026-07-02T00:00:00Z",
                "game_pk": 1, "score_date": "2026-07-02", "market": "h2h home",
                "american_odds": -110, "stake": 5.0, "outcome": "win"}
        broken = {"bet_id": "broken", "user_id": "u"}   # missing every required field

        monkeypatch.setattr(bets_router, "list_bets", lambda uid: [good, broken])
        resp = bets_router.get_bets(user_id="u")
        assert [b.bet_id for b in resp.bets] == ["ok"]
        assert resp.total == 1


# ── 7. Source invariants (cheap, catch a regression in review) ───────────────

class TestFallbackSourceInvariants:
    def test_every_http_call_has_a_finite_timeout(self):
        # INC-32: an un-timed-out network call on a scheduled-job path can wedge the worker.
        assert SETTLE.count("timeout=_HTTP_TIMEOUT") == 2, (
            "both Stats API calls (schedule confirm + boxscore) must pass a finite timeout"
        )
        assert "_HTTP_TIMEOUT = " in SETTLE

    def test_fallback_requires_a_starter_line(self):
        assert 'gamesStarted") != 1' in SETTLE, (
            "the boxscore fallback must accept only a STARTER's line — a reliever's K count "
            "must never settle a starter prop"
        )

    def test_fallback_failures_are_fail_safe_not_fatal(self):
        # Every fallback path returns empty on error so the bet stays pending; settlement is
        # WARN-tier and must never take down the op.
        body = SETTLE[SETTLE.find("def _statsapi_final_games"):SETTLE.find("# ── Settlement math")]
        assert body.count("except Exception") == 2
        # No `raise` STATEMENT (resp.raise_for_status() is fine — it is caught).
        assert not [ln for ln in body.splitlines() if ln.strip().startswith("raise ")], (
            "the fallback must degrade to 'leave the bet pending', never propagate"
        )
