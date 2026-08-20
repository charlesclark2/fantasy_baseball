"""NF-C7b — depth targets are a SAVED setting, and the extension can read them.

NF-C7 shipped per-position depth targets in `localStorage`, keyed by season + scoring-format name.
Three consequences nobody chose:

  · two different leagues on the same format silently shared one setting;
  · nothing followed the user to another device;
  · ⭐ the Chrome extension could not read them AT ALL — `recommend()` accepted `depth_targets` and
    nothing on the extension path ever passed one. The parameter existed, every test passed, and
    the feature was absent on that surface: the NF-C0e "wired ≠ invoked" class. NF-C7's own guards
    could not see it because all of them exercised the web path.

The first test class below is the one that would have caught it, and it is written so that it FAILS
if the wiring is removed — not merely so that it passes today.
"""

from __future__ import annotations

import contextlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.backend.models.fantasy import (
    DEPTH_TARGET_POSITIONS,
    MAX_DEPTH_TARGET,
    League,
    LeagueSave,
    sanitize_depth_targets,
)
from app.backend.services import depth_targets as dt
from app.backend.services import draft_assistant

_FIXTURES = Path(__file__).parent / "fixtures"
_PRECEDENCE = _FIXTURES / "nf_c7b_depth_target_precedence.json"
_PRECEDENCE_TS = _FIXTURES / "nf_c7b_depth_target_precedence_ts.json"
_BOARD_INPUT = _FIXTURES / "nf_c_lda_1_optimizer_parity_input.json"


@contextlib.contextmanager
def _app_env(monkeypatch):
    """The `app_env` fixture from the endpoint suite, as a context manager.

    Same three things it does: reset the process-global per-IP limiter (a depleted bucket surfaces
    as a payload-shape failure, not as throttling), stub the projections load, and stub JWKS.
    """
    from app.backend.routers import fantasy
    from app.backend.services import cost_guardrails, jwt_verify
    from betting_ml.tests import test_nf_c_lda_1_endpoint as ep

    cost_guardrails.get_limiter().reset()
    monkeypatch.setattr(
        fantasy, "_load_json",
        lambda rel_key, sport="nfl": ep._PROJECTIONS if rel_key.endswith("projections.json") else None,
    )
    fantasy._full_projections_memo.clear()
    monkeypatch.setattr(jwt_verify, "_fetch_jwks", lambda: None)
    jwt_verify.reset_jwks_cache()
    yield


@pytest.fixture(scope="module")
def precedence_cases() -> list[dict]:
    return json.loads(_PRECEDENCE.read_text())["cases"]


@pytest.fixture(scope="module")
def board() -> dict:
    source = json.loads(_BOARD_INPUT.read_text())
    return {"players": source["board"], "replacement": source["replacement"]}


@pytest.fixture(scope="module")
def config():
    from quant_sports_intel_models.fantasy_engine.league_config import LeagueConfig

    return LeagueConfig.from_dict(json.loads(_BOARD_INPUT.read_text())["config"])


@pytest.fixture(scope="module")
def pool(board) -> list[dict]:
    """The board itself, shaped as the extension forwards an ESPN pool.

    Using the board rows means every entry resolves, so a test about depth targets is never
    silently measuring a resolution failure instead.
    """
    slot = {"QB": 0, "RB": 2, "WR": 4, "TE": 6, "K": 17, "DST": 16}
    return [
        {
            "id": f"e{p['id']}",
            "fullName": p["name"],
            "proTeamId": None,
            "defaultPositionId": None,
            "eligibleSlots": [slot.get(p["pos"], 4)],
        }
        for p in board["players"]
    ]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE GAP NF-C7 SHIPPED: the extension path must actually apply a target
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheExtensionPathAppliesDepthTargets:
    def test_a_depth_target_changes_what_the_extension_recommends(self, board, config, pool):
        """The anti-vacuity test for the whole story.

        ⚠️ It is not enough that `recommend_for_state` ACCEPTS `depth_targets` — NF-C7's engine
        accepted the parameter for a week while no caller passed one. This asserts the ANSWER
        differs, so deleting the wiring inside `recommend_for_state` turns it red.
        """
        drafted = [r["id"] for r in pool[:120]]
        mine = drafted[:9]
        common = dict(board=board, config=config, pool=pool,
                      drafted_espn_ids=drafted, my_espn_ids=mine, top_n=12)

        without = draft_assistant.recommend_for_state(**common)
        with_te = draft_assistant.recommend_for_state(**common, depth_targets={"TE": 4})

        ids_without = [r["player_id"] for r in without["recommendations"]]
        ids_with = [r["player_id"] for r in with_te["recommendations"]]
        assert ids_without, "fixture produced no recommendations — every assertion here would be vacuous"
        assert ids_without != ids_with, (
            "a depth target did not change the extension's recommendation — the wiring in "
            "recommend_for_state is not reaching recommend()"
        )

    def test_the_response_names_where_the_targets_came_from(self, board, config, pool):
        """A league target of {QB: 2} and an account default of {QB: 2} rank identically.

        Without the source the user cannot tell WHICH screen to change, so the two are
        indistinguishable — the same reason the response echoes `state.overall_pick`.
        """
        out = draft_assistant.recommend_for_state(
            board=board, config=config, pool=pool, drafted_espn_ids=[], my_espn_ids=[], top_n=5,
            depth_targets={"QB": 2}, depth_targets_source=dt.SOURCE_ACCOUNT,
        )
        assert out["depth_targets"] == {"applied": {"QB": 2}, "source": "account"}

    def test_no_targets_is_reported_as_none_rather_than_omitted(self, board, config, pool):
        """An absent key and "no targets" must not be the same thing on the wire.

        A surface that has to distinguish "we applied nothing" from "this response predates the
        feature" cannot do it if the block simply disappears.
        """
        out = draft_assistant.recommend_for_state(
            board=board, config=config, pool=pool, drafted_espn_ids=[], my_espn_ids=[], top_n=5,
        )
        assert out["depth_targets"] == {"applied": {}, "source": "none"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE ROUTER, not just the service — where the NF-C7 gap actually lived
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheEndpointResolvesTargetsBeforeRanking:
    """⚠️ THE SERVICE TESTS ABOVE ARE NOT ENOUGH, and that is the whole lesson of NF-C7's gap.

    NF-C7's engine ACCEPTED `depth_targets`; the defect was that the layer above never passed one.
    A suite that stops at `recommend_for_state` reproduces exactly that blind spot one level up:
    delete the `resolve_for_record(...)` call in `routers/fantasy.py` and every other test in this
    file still passes. These two go through the REAL ASGI app.

    The harness is imported from `test_nf_c_lda_1_endpoint` rather than copied — a second copy of an
    80-line ASGI scope builder is a second thing to drift (E9.61).
    """

    @pytest.fixture()
    def endpoint(self, monkeypatch):
        from betting_ml.tests import test_nf_c_lda_1_endpoint as ep
        return ep

    def test_an_account_default_reaches_the_extension(self, endpoint, monkeypatch):
        from app.backend.services import dynamo

        monkeypatch.setattr(dynamo, "get_fantasy_prefs", lambda uid: {"depth_targets": {"TE": 4}})
        with _app_env(monkeypatch):
            status, body = endpoint._post(
                "/fantasy/nfl/draft-assistant", endpoint._body(), aws_event=endpoint._entitled()
            )
        assert status == 200, body[:400]
        assert json.loads(body)["depth_targets"] == {"applied": {"TE": 4}, "source": "account"}

    def test_no_account_default_reports_none_rather_than_guessing(self, endpoint, monkeypatch):
        """The two-sided half: without it, a hardcoded `{"TE": 4}` would pass the clause above."""
        from app.backend.services import dynamo

        monkeypatch.setattr(dynamo, "get_fantasy_prefs", lambda uid: {})
        with _app_env(monkeypatch):
            status, body = endpoint._post(
                "/fantasy/nfl/draft-assistant", endpoint._body(), aws_event=endpoint._entitled()
            )
        assert status == 200, body[:400]
        assert json.loads(body)["depth_targets"] == {"applied": {}, "source": "none"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Precedence — read from the SHARED fixture, never restated here
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestPrecedence:
    def test_the_shared_fixture_is_populated(self, precedence_cases):
        """Anti-vacuity: a parametrized suite over an empty fixture passes on nothing."""
        assert len(precedence_cases) >= 8, "the shared precedence fixture has been emptied"

    def test_every_case_resolves_as_the_shared_fixture_says(self, precedence_cases):
        """⭐ The rule is stated ONCE, in the fixture the TypeScript side also reads.

        E9.61: two renderers of one field become two rule sets, and a grep of the file that is
        wrong clears the file that is right. Neither side restates the precedence in prose.
        """
        failures = []
        for case in precedence_cases:
            targets, source = dt.resolve(case["league"], case["account"])
            if targets != case["targets"] or source != case["source"]:
                failures.append(
                    f"{case['name']}: got ({targets}, {source!r}), "
                    f"fixture says ({case['targets']}, {case['source']!r})"
                )
        assert not failures, "\n".join(failures)

    def test_the_fixture_exercises_every_source(self, precedence_cases):
        """A precedence fixture that never reaches one branch cannot defend it."""
        seen = {c["source"] for c in precedence_cases}
        assert seen == {"league", "account", "none"}, f"unreached branches: {seen}"

    def test_the_typescript_resolver_answers_identically(self, precedence_cases):
        """⭐ THE ANTI-DRIFT GUARANTEE, and the reason the fixture exists at all.

        Precedence has to hold in TWO places: the browser (the web draft surfaces) and the API
        Lambda (the extension's live draft). This repo has already paid for one rule with two
        implementations twice — E9.61's player name, upper-cased by two different passes, and this
        story's own sibling, where the two draft ENGINES had silently drifted two fixes apart and
        recommended different players on a real board.

        TypeScript cannot be imported from pytest, so `frontend/scripts/
        gen-depth-target-precedence-fixture.mjs` runs the SHIPPED resolver over these same cases and
        records its answers. Both sides are then held to one statement of the rule.

        ⚠️ The generator is NOT on the CI path — the committed output is — so an unavailable node
        cannot silently turn this green (NF-INFRA1: a check that cannot run is not a check).
        """
        ts = json.loads(_PRECEDENCE_TS.read_text())["answers"]
        assert len(ts) == len(precedence_cases), (
            "the TypeScript answers are stale — regenerate with "
            "`node --experimental-strip-types frontend/scripts/gen-depth-target-precedence-fixture.mjs`"
        )
        failures = []
        for case, answer in zip(precedence_cases, ts):
            assert answer["name"] == case["name"], "fixture and TS answers are out of order"
            if answer["targets"] != case["targets"] or answer["source"] != case["source"]:
                failures.append(
                    f"{case['name']}: TypeScript said ({answer['targets']}, {answer['source']!r}), "
                    f"the shared rule says ({case['targets']}, {case['source']!r})"
                )
        assert not failures, "\n".join(failures)

    def test_both_sides_were_actually_exercised(self, precedence_cases):
        """Anti-vacuity for the clause above: zipping two empty lists agrees about nothing."""
        ts = json.loads(_PRECEDENCE_TS.read_text())["answers"]
        assert len(ts) >= 8 and len(precedence_cases) >= 8

    def test_a_league_that_never_set_targets_inherits_rather_than_opting_out(self):
        """The distinction the whole resolver exists for.

        A record saved before this field existed has no key at all. If that read as "cleared", every
        pre-existing league would silently ignore the account default the user just set — and would
        present as "my default doesn't work", with nothing to point at.
        """
        legacy = {"name": "saved last season", "n_teams": 12}
        assert dt.resolve_for_record(legacy, {"TE": 3}) == ({"TE": 3}, dt.SOURCE_ACCOUNT)

    def test_clearing_one_league_does_not_re_inherit_the_account_default(self):
        """`league or account` — the obvious spelling — gets this wrong, because `{}` is falsy."""
        cleared = {"name": "L", "depth_targets": {}}
        assert dt.resolve_for_record(cleared, {"TE": 3}) == ({}, dt.SOURCE_NONE)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Storage contract
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestStorage:
    def test_a_save_normalises_and_the_response_carries_the_field(self):
        roster = [
            {"name": "QB", "count": 1, "eligible": ["QB"]},
            {"name": "RB", "count": 2, "eligible": ["RB"]},
            {"name": "WR", "count": 2, "eligible": ["WR"]},
            {"name": "TE", "count": 1, "eligible": ["TE"]},
            {"name": "FLEX", "count": 1, "eligible": ["RB", "WR", "TE"]},
            {"name": "BN", "count": 6, "eligible": [], "bench": True},
        ]
        saved = LeagueSave(
            name="L", n_teams=12, scoring={"per_stat": {"rec": 1.0}}, roster=roster,
            depth_targets={"QB": 2, "TE": 4, "PUNTER": 9, "RB": 0, "WR": 999},
        )
        assert saved.depth_targets == {"QB": 2, "TE": 4}
        # ⭐ The RESPONSE model must carry it too. A field the store holds but the response model
        # does not declare is STRIPPED on serialize with no error — E9.41, where a settled pick's
        # colour was broken for every user while DynamoDB had it right the whole time.
        out = League(league_id="x", **saved.model_dump()).model_dump()
        assert out["depth_targets"] == {"QB": 2, "TE": 4}

    def test_reading_a_stored_record_never_rewrites_what_is_stored(self):
        """E9.49 — a WRITE rule must never run on a READ of already-stored data.

        The validator lives on `LeagueSave`, not on the shared base. ⚠️ The hazard here is narrower
        than E9.49's original and is stated precisely rather than borrowed: this validator
        NORMALISES rather than rejecting, so putting it on the base would not 500 a read the way
        E9.49's `total_line` rule did. What it WOULD do is silently rewrite the caller's stored
        value on the way out — the response would report `{}` for a league whose record says
        something else, and no screen would show the difference.

        So the property asserted is the observable one: what the store holds is what the read
        reports, junk included. Normalisation happens where the value is USED (`resolve`), which the
        third assertion pins — defence at the point of use rather than a write rule leaking onto the
        read path.
        """
        stored = {"PUNTER": 999, "QB": -4}
        out = League(
            league_id="x", name="L", n_teams=12,
            scoring={"per_stat": {"rec": 1.0}}, roster=[],
            depth_targets=dict(stored),
        ).model_dump()
        assert out["depth_targets"] == stored, (
            "reading a stored league rewrote its depth targets — a write-time rule has leaked onto "
            "the read path (E9.49)"
        )
        # ...and nothing downstream ever sees the junk, because the resolver sanitises at use.
        assert dt.resolve(stored, {"TE": 3}) == ({}, dt.SOURCE_NONE)

    def test_the_stored_shape_is_small_enough_to_share_the_item(self):
        """NF-C6P3 — every league, the portfolio, platform tokens and the MLB leagues share ONE
        400 KB DynamoDB item, and an overflow refuses the WHOLE write: no new league, no new bet,
        no preference save. Measured rather than assumed, because that ceiling is real."""
        biggest = {p: MAX_DEPTH_TARGET for p in DEPTH_TARGET_POSITIONS}
        per_league = len(json.dumps(biggest))
        assert per_league * 25 < 5_000, f"25 leagues of targets is {per_league * 25} bytes"

    def test_an_unknown_position_can_never_be_stored(self):
        assert sanitize_depth_targets({"PUNTER": 3, "LB": 2}) == {}

    def test_a_count_above_the_ceiling_is_dropped_not_clamped(self):
        """Must match the TypeScript sanitizer, which originally CLAMPED.

        Once targets became a saved setting read by both the browser and the server, clamping on one
        side and dropping on the other would mean the same stored map resolved to two different
        rosters depending on which surface read it.
        """
        assert sanitize_depth_targets({"QB": MAX_DEPTH_TARGET + 1}) == {}
        assert sanitize_depth_targets({"QB": MAX_DEPTH_TARGET}) == {"QB": MAX_DEPTH_TARGET}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE STORE, not the model — a shipped bug these tests originally could not see
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheValuesSurviveARealDynamoRoundTrip:
    """⚠️ WRITTEN AFTER SHIPPING, BECAUSE EVERY TEST ABOVE PASSED WHILE THE FEATURE WAS BROKEN.

    Saving an account default worked and then vanished — within ~60 seconds (the react-query
    `staleTime`) or on any sign-out. The WRITE was landing; the READ was dropping it.

    DynamoDB returns every number as `Decimal`. `get_fantasy_prefs` used `_from_dynamo`, which
    converts Decimal only at the TOP level of the map it is handed — but these counts live TWO
    levels down (`fantasy_prefs.depth_targets.RB`), so they came back as `Decimal`, and
    `sanitize_depth_targets` tests `isinstance(v, (int, float))`, which `Decimal` is NEITHER. Every
    count was silently dropped.

    ⭐ THE REASON THE SUITE MISSED IT: every storage test above constructs a Python dict and feeds
    it to a Pydantic model. Pydantic COERCES Decimal to int, so it would have passed either way —
    the tests exercised the MODEL and the defect lived in the STORE. `list_fantasy_leagues` already
    used the deep converter, which is why the per-league path worked and only the account default
    broke; a test that had gone through the store would have found that asymmetry immediately.
    """

    @staticmethod
    def _table_holding(item: dict):
        class _FakeTable:
            def get_item(self, Key):  # noqa: N803 — boto3's own kwarg name
                return {"Item": item}
        return _FakeTable()

    def test_counts_come_back_as_ints_not_decimals(self, monkeypatch):
        from app.backend.services import dynamo

        monkeypatch.setattr(
            dynamo, "_users_table",
            lambda: self._table_holding(
                {"fantasy_prefs": {"depth_targets": {"RB": Decimal("6"), "TE": Decimal("2")}}}
            ),
        )
        got = dynamo.get_fantasy_prefs("u1")
        assert got == {"depth_targets": {"RB": 6, "TE": 2}}
        assert not any(isinstance(v, Decimal) for v in got["depth_targets"].values()), (
            "a Decimal survived the read — sanitize_depth_targets will silently drop it"
        )

    def test_a_stored_default_survives_the_read_path_end_to_end(self, monkeypatch):
        """The user-visible property: what was saved is what comes back.

        Asserted through `sanitize_depth_targets` — the function the router actually applies —
        rather than on the raw dict, because the defect was that the sanitizer rejected the type
        the store returned. Checking the dict alone would pass on the broken code.
        """
        from app.backend.services import dynamo

        monkeypatch.setattr(
            dynamo, "_users_table",
            lambda: self._table_holding(
                {"fantasy_prefs": {"depth_targets": {"RB": Decimal("6")}}}
            ),
        )
        served = sanitize_depth_targets(dynamo.get_fantasy_prefs("u1").get("depth_targets"))
        assert served == {"RB": 6}, "a saved account default did not survive the round trip"

    def test_the_resolver_sees_a_stored_default_too(self, monkeypatch):
        """...and it reaches the thing that ranks picks, not just the response body."""
        from app.backend.services import dynamo

        monkeypatch.setattr(
            dynamo, "_users_table",
            lambda: self._table_holding(
                {"fantasy_prefs": {"depth_targets": {"TE": Decimal("3")}}}
            ),
        )
        account = dynamo.get_fantasy_prefs("u1").get("depth_targets")
        assert dt.resolve_for_record({"name": "L"}, account) == ({"TE": 3}, dt.SOURCE_ACCOUNT)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The load-bearing guarantee, re-asserted on the NEW path
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestAPreferenceCannotProduceAnIllegalRoster:
    def test_a_saved_depth_target_can_never_starve_the_reserve_constraint(self, board, config, pool):
        """NF-C7's guarantee, now that a target can arrive from STORAGE rather than a form.

        The mechanism is unchanged — a target reorders inside the level-0 cohort and `need_level`
        never sees it — but the guarantee is only worth what it is tested on, and it had never been
        tested against a target the user did not type on the screen they were looking at.
        """
        drafted = [r["id"] for r in pool[:150]]
        mine = drafted[:13]
        out = draft_assistant.recommend_for_state(
            board=board, config=config, pool=pool, drafted_espn_ids=drafted,
            my_espn_ids=mine, top_n=40, depth_targets={"QB": 6, "TE": 6},
        )
        recs = out["recommendations"]
        assert recs, "fixture produced nothing — the assertion below would be vacuous"
        must_fill = [r for r in recs if r["must_fill"]]
        if must_fill:
            top = recs[0]
            assert top["must_fill"], (
                "a depth target outranked a slot the lineup REQUIRES — a preference has walked the "
                "user toward an illegal roster"
            )
