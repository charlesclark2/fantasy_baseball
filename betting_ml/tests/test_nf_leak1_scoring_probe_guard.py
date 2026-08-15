"""NF-LEAK1 — the paid-stat reconstruction vector is priced out, and real leagues still save.

WHAT THIS DEFENDS. `/fantasy/nfl/league-board` scores an arbitrary caller-supplied config against
the full projection and returns `pts` per player. That is what keeps G100-C1's free personalized
league alive after NF-EPIC 1 withheld the stat line — and, by construction, it is also a channel
into that stat line. Measured on the pre-fix code by `scripts/nf_leak1_reconstruction_cost.py`:
the whole paid per-stat line for all 858 players in **44 round trips / 22 seconds**.

⭐ THE STANDARD IS COST, NOT CLOSURE. No server that scores a user's own scoring rules can be
proven leak-free. Every assertion below is about PRICE and ATTRIBUTION; none of them claims zero,
and `test_no_guard_here_claims_the_leak_is_closed` makes that a mechanical property of the source
rather than an intention.

TWO-SIDED BY CONSTRUCTION. Half these tests try to break the paywall; the other half assert a real
user is untouched — because a refusal rule is only as good as the population it does NOT refuse, and
the cheapest way to "fix" this leak is to ship something that also refuses real leagues.

RED-proven by `betting_ml/tests/nf_leak1_red_proof.py`.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: The per-registered gate this story is judged on: one free account must need at least this long of
#: sustained, uninterrupted probing to reconstruct the paid stat line.
VIABLE_PATH_DAYS = 14.0

#: The attacker's measured best surviving plan (`admissible_attack_plan`, real scorer + real
#: artifact): 38 scorable stats covered in 32 admissible scoring changes.
MEASURED_ATTACK_CHANGES = 32

SECONDS_PER_DAY = 86400.0


def _guard():
    return pytest.importorskip("app.backend.services.scoring_probe_guard")


def _cfg(per_stat: dict, position_bonuses: dict | None = None) -> dict:
    return {"scoring": {"per_stat": per_stat, "position_bonuses": position_bonuses or {}}}


def _scorable_stats(exclude: dict) -> list[str]:
    """Real keys from the scorer's own map, minus the ones the baseline already scores.

    ⚠️ REAL KEYS, NOT INVENTED ONES, AND IT IS LOAD-BEARING. `scoring_fingerprint` drops any key the
    scorer cannot apply, so a probe built from `stat_0`, `stat_1`… produces an IDENTICAL fingerprint
    every time: zero deltas, nothing flagged, and a walk test that passes on no walk at all. The
    first cut of this file did exactly that.
    """
    from app.backend.services.projection_fields import STAT_FIELD

    return [s for s in sorted(STAT_FIELD) if s not in exclude]


#: A realistic league — the shape the editor and every importer produce.
REAL = {
    "pass_yds": 0.04, "pass_td": 4.0, "pass_int": -2.0,
    "rush_yds": 0.1, "rush_td": 6.0,
    "rec": 0.5, "rec_yds": 0.1, "rec_td": 6.0,
    "fumbles_lost": -2.0,
}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. THE ATTACK — priced past the pre-registered gate
# ══════════════════════════════════════════════════════════════════════════════════════════════


class TestTheReconstructionAttackIsPricedOut:
    def test_the_isolation_probe_is_refused_at_write_time(self):
        """Model A — every weight zero but one, so `pts` IS the stat, recovered EXACTLY (measured:
        100.00% of cells). The cheapest and most precise form, and it must never be storable."""
        guard = _guard()
        assert guard.shape_violations(_cfg({"rec": 1.0}))
        assert guard.shape_violations(_cfg({"pass_yds": 1.0}))  # a CORE stat isolated, too

    def test_no_single_term_config_is_admissible_whichever_stat_it_names(self):
        """The property `MIN_CORE_STATS = 2` exists for, asserted over the WHOLE stat map rather
        than the one or two keys a fixture happens to pick — a threshold of 1 passes an isolated
        core stat, and that hole is invisible if you only probe with `rec`."""
        guard = _guard()
        from app.backend.services.projection_fields import STAT_FIELD

        admitted = [s for s in STAT_FIELD if not guard.shape_violations(_cfg({s: 1.0}))]
        assert admitted == [], f"these stats can still be isolated in one term: {admitted}"

    def test_a_probe_cannot_pad_a_degenerate_config_with_dataless_keys(self):
        """⭐ THE BYPASS THAT KILLED THE FIRST DESIGN. A term-COUNT floor is free to satisfy: 15 of
        the 53 keys in `STAT_FIELD` have no column in the published artifact, so padding with them
        contributes exactly 0.0 to `pts` while making a one-real-term probe look like a league.
        The rule counts CORE families precisely because those columns always carry data."""
        guard = _guard()
        padded = _cfg({
            "rec": 1.0,
            "dst_ya_g_550p": 1.0, "dst_ya_g_500_549": 1.0, "dst_ya_g_450_499": 1.0,
        })
        assert guard.shape_violations(padded)

    def test_the_dynamic_range_cap_is_tighter_than_what_the_system_already_enforced(self):
        """⭐ THE DEFECT THIS STORY SHIPPED AND THE HARNESS CAUGHT. `LeagueSave` already bounds
        `|w| ≤ 1000`, which for any config whose smallest weight is ~1 already implies a ratio
        ceiling of ~10³. The first cut of `MAX_WEIGHT_RATIO` was 10⁴ — a LOOSENING wearing a
        guardrail's clothes, measured to make packing BETTER (2.11 stats/config, up from 1.73).

        A range rule is only a guardrail below the range the system already allowed.
        """
        guard = _guard()
        models = pytest.importorskip("app.backend.models.fantasy")
        implied_status_quo = 1000.0
        assert guard.MAX_WEIGHT_RATIO < implied_status_quo
        # and it must still be reachable at all — a cap below the widest REAL league is a refusal
        # rule pointed at customers (measured: presets 150, widest imported league 300).
        assert guard.MAX_WEIGHT_RATIO >= 300.0
        assert models.LeagueSave is not None

    def test_a_magnitude_packed_probe_is_refused(self):
        """Model C — several stats at separated magnitudes decoded out of one `pts`. It was the
        CHEAPEST path before this story (22 round trips, 99.80% exact); the two shape rules compose
        to refuse it: too few core families, and the spread the encoding needs."""
        guard = _guard()
        # ⭐ THE FIXTURE SATISFIES EVERY OTHER CLAUSE ON PURPOSE (NF-D17). It scores four core
        # families at realistic weights, so the core-stat rule CANNOT be what refuses it — only the
        # dynamic range can. A packed fixture that also happened to be degenerate would prove
        # nothing about the ratio cap, and deleting that cap would leave this test green.
        packed = _cfg({
            "pass_yds": 1.0, "pass_td": 1.0, "rush_yds": 1.0, "rec_yds": 1.0,
            "def_safety": 1.0, "st_td": 100.0, "def_blocked_kick": 10000.0,
        })
        assert guard.shape_violations(_cfg({
            "pass_yds": 1.0, "pass_td": 1.0, "rush_yds": 1.0, "rec_yds": 1.0,
        })) == [], "the fixture's non-packed half must be admissible, or this proves nothing"
        problems = guard.shape_violations(packed)
        assert problems, "a magnitude-packed config was accepted"
        assert any("range" in p for p in problems), problems

    def test_the_measured_attack_plan_costs_more_than_the_pre_registered_gate(self):
        """⭐⭐ THE ATTACK SIMULATION. Replays the attacker's measured best surviving plan — 32
        admissible scoring changes — through the REAL budget, one charge at a time, and asserts the
        elapsed wall-clock clears the pre-registered viable-path threshold.

        Drives the real `charge` on a real ledger rather than asserting on the constants, so a
        change to burst, refill, the surcharge OR the refill maths all move this number.
        """
        guard = _guard()
        now = 0.0
        ledger = None
        stats = _scorable_stats(REAL)[:MEASURED_ATTACK_CHANGES]
        assert len(stats) == MEASURED_ATTACK_CHANGES, "not enough scorable stats to replay the plan"

        for i, stat in enumerate(stats):
            probe = _cfg({**REAL, stat: 1.0 + i})
            verdict = guard.charge(ledger, probe, now)
            while not verdict.allowed:
                now += verdict.retry_after_seconds
                verdict = guard.charge(verdict.ledger, probe, now)
            ledger = verdict.ledger

        days = now / SECONDS_PER_DAY
        assert days >= VIABLE_PATH_DAYS, (
            f"the measured attack plan completes in {days:.1f} days, inside the "
            f"{VIABLE_PATH_DAYS:.0f}-day viable-path gate"
        )

    def test_delete_then_recreate_does_not_hand_back_a_fresh_budget(self):
        """⭐ THE BYPASS A PER-LEAGUE COUNTER WOULD HAVE. A free account may hold only ONE league but
        may delete and recreate it without limit, so state parked on the league record resets on
        every recreate. The ledger is keyed on the ACCOUNT; a recreate is just another change."""
        guard = _guard()
        ledger, now, spent = None, 0.0, 0
        while spent < 200:  # drain the bucket, however many changes that takes
            verdict = guard.charge(ledger, _cfg({**REAL, "rec": 0.5 + spent}), now)
            ledger = verdict.ledger
            spent += 1
            if not verdict.allowed:
                break
        else:  # pragma: no cover — a bucket that never empties is the defect this asserts against
            pytest.fail("the budget never ran out")

        # The league is deleted and recreated: a brand-new league_id, a config the account has never
        # saved before, no per-league state anywhere. The bucket is still theirs, and still empty.
        assert not guard.charge(ledger, _cfg({**REAL, "pass_td": 7.0}), now).allowed

    def test_position_bonuses_are_metered_like_per_stat_weights(self):
        """`score_row` adds a position bonus to `pts` exactly like a per-stat weight, so it is a
        second door into the same room. A rule that policed `per_stat` alone would leave the whole
        attack available one key over."""
        guard = _guard()
        before = _cfg(REAL)
        after = _cfg(REAL, {"TE": {"rec": 1.0}})
        assert guard.scoring_changed(before, after)
        assert not guard.charge(None, after, 0.0).ledger["last_scoring"].keys().isdisjoint(
            {"TE:rec"}
        )

    def test_a_probe_walk_pays_the_surcharge_and_is_logged_against_the_account(self):
        """The detector: a single-stat delta from an account that has already walked many distinct
        stats. Charged double, and — the part that matters — recorded, so the activity is
        attributable to a Cognito `sub` rather than to an anonymous `curl`."""
        guard = _guard()
        ledger, now = None, 0.0
        costs = []
        # A true walk: one stat at a time, each step differing from the last in exactly one weight.
        # Time advances a day per step so the BUDGET never interferes — this test is about the
        # detector, and a charge refused for lack of tokens would prove nothing about it.
        # ⚠️ AN ACCUMULATING WALK, so each step really is a ONE-weight delta from the last. Building
        # each probe as `{**REAL, stat_i: 1.0}` instead looks like a walk and is not: dropping
        # `stat_{i-1}` while adding `stat_i` is a TWO-key delta, which is precisely the evasion the
        # detector is documented not to catch. The first cut of this test was that evasion, and it
        # would have reported the detector as broken.
        walk = _scorable_stats(REAL)[: guard.PROBE_TOUCH_THRESHOLD + 4]
        probe = dict(REAL)
        for stat in walk:
            probe[stat] = 1.0
            verdict = guard.charge(ledger, _cfg(dict(probe)), now)
            ledger = verdict.ledger
            costs.append(verdict.cost)
            now += SECONDS_PER_DAY

        assert ledger["probe_hits"] > 0, "a single-stat walk was never flagged"
        assert costs[-1] == guard.PROBE_SURCHARGE
        assert costs[0] == 1.0, "the walk was flagged before it had walked anywhere"

    def test_the_first_few_single_stat_tweaks_are_not_treated_as_probing(self):
        """The other side of the detector, and the reason it arms late: tuning one knob at a time is
        how everybody edits scoring. A user who changes PPR, then a TE bonus, then a fumble weight
        must never be surcharged.

        ⭐ THE BASELINE IS A SHIPPED PRESET, NOT A MINIMAL STUB, AND THAT IS WHAT MAKES THIS TEST
        ABLE TO FAIL. The false positive being guarded against is caused by a league's FIRST save
        seeding the walk counter with every term it contains — so it only reproduces at a real
        league's size. Against a 9-term stub the counter never reaches the threshold and the test
        passes with the bug present; against `full_ppr`'s 28 terms it fires on the second tweak,
        which is exactly what a real user would have hit.
        """
        guard = _guard()
        lp = pytest.importorskip(
            "quant_sports_intel_models.football.nfl.fantasy.league_presets"
        )
        base = dict(lp.get_preset("full_ppr").to_dict()["scoring"]["per_stat"])
        assert len(base) >= 20, "the fixture must be a real-sized league to reproduce the defect"

        ledger, now = None, 0.0
        # An ACCUMULATING one-knob-at-a-time walk — the same single-key-delta shape a probe uses,
        # just short. If it were built by replacing the last stat each time, every delta would be
        # two keys, the detector could never fire whatever the threshold, and this test would pass
        # with the threshold set to zero.
        cfg = dict(base)
        for stat, weight in (
            ("rec", 1.0), ("rec_td", 4.0), ("fumbles_lost", -1.0), ("two_pt", 2.0),
        ):
            cfg[stat] = weight
            verdict = guard.charge(ledger, _cfg(dict(cfg)), now)
            assert verdict.allowed
            assert not verdict.probe_shaped, f"a real user's tweak of {stat} was flagged"
            assert verdict.cost == 1.0
            ledger = verdict.ledger
        assert ledger["probe_hits"] == 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. THE LEGITIMATE FREE EXPERIENCE — unaffected
# ══════════════════════════════════════════════════════════════════════════════════════════════


class TestLegitimateFreeUseIsUnaffected:
    def test_every_shipped_preset_still_saves(self):
        """The 8 boards we publish are configs a user can start from. If the guard refuses one of
        them, the guard is wrong — not the league."""
        guard = _guard()
        lp = pytest.importorskip(
            "quant_sports_intel_models.football.nfl.fantasy.league_presets"
        )
        for name in lp.PRESETS:
            assert guard.shape_violations(lp.get_preset(name).to_dict()) == [], name

    def test_every_captured_real_imported_league_still_saves(self):
        """⭐ AGAINST REAL PAYLOADS, NOT A FIXTURE WE WROTE. Two real ESPN leagues and a real Yahoo
        league, captured from the live platforms — the NF-C0 lesson that a fixture derived from your
        own assumptions cannot disconfirm them. Measured spread: 21–44 scoring terms, weight ratios
        150–300, all six core families present in all of them."""
        guard = _guard()
        fixtures = sorted((REPO / "frontend/e2e/fixtures/api").glob("fantasy-import-*.json"))
        assert fixtures, "no captured import fixtures — this guard would pass on nothing"

        checked = 0
        for path in fixtures:
            for cfg in _configs_in(json.loads(path.read_text())):
                assert guard.shape_violations(cfg) == [], f"{path.name}: {cfg.get('name')}"
                checked += 1
        assert checked >= 4, f"only {checked} real configs checked"

    def test_a_setup_session_of_a_handful_of_tweaks_is_never_throttled(self):
        """The separation this story turns on: a real user importing a league and then tuning the
        scoring several times in one sitting must not meet a limiter at all."""
        guard = _guard()
        ledger, now = None, 0.0
        for i in range(6):
            verdict = guard.charge(ledger, _cfg({**REAL, "rec": 0.5 + i * 0.1}), now)
            assert verdict.allowed, f"a real user was throttled on tweak {i + 1}"
            ledger = verdict.ledger
            now += 45.0  # a considered edit, not a script

    def test_a_week_later_the_budget_has_refilled(self):
        """A free account is a season-long relationship, not a session. Someone who spent their
        burst in August must be able to edit again in September."""
        guard = _guard()
        ledger, now = None, 0.0
        for i in range(int(guard.BUDGET_BURST)):
            ledger = guard.charge(ledger, _cfg({**REAL, "rec": float(i)}), now).ledger
        assert not guard.charge(ledger, _cfg({**REAL, "rec": 99.0}), now).allowed
        later = now + 7 * SECONDS_PER_DAY
        assert guard.charge(ledger, _cfg({**REAL, "rec": 99.0}), later).allowed

    @pytest.mark.parametrize(
        "label,after",
        [
            ("renamed", {"name": "New name", "scoring": {"per_stat": REAL}}),
            ("roster edited", {"scoring": {"per_stat": REAL}, "roster": [{"name": "FLEX"}]}),
            ("team linked", {"scoring": {"per_stat": REAL}, "source_team_key": "t7"}),
            ("roster re-imported", {"scoring": {"per_stat": REAL}, "imported_roster": [{"n": 1}]}),
        ],
    )
    def test_an_edit_that_does_not_touch_the_scoring_is_never_charged(self, label, after):
        """⭐ THE METER IS ON THE SCORING, NOT ON THE SAVE. Everything else a user does to a league
        leaves `pts` alone and therefore leaks nothing — including the re-import that refreshes a
        roster snapshot, which would otherwise burn a token every time somebody pressed sync."""
        guard = _guard()
        assert not guard.scoring_changed({"scoring": {"per_stat": REAL}}, after), label

    def test_a_captured_only_term_is_not_a_scoring_change(self):
        """A platform term the scorer keeps for fidelity but never applies cannot move `pts`, so
        changing it must be free — otherwise we bill a user for the completeness we asked them to
        preserve."""
        guard = _guard()
        before = {"scoring": {"per_stat": {**REAL, "espn_special_rule": 1.0}}}
        after = {"scoring": {"per_stat": {**REAL, "espn_special_rule": 99.0}}}
        assert not guard.scoring_changed(before, after)

    def test_an_entitled_caller_is_not_metered_at_all(self):
        """A subscriber can `GET /fantasy/nfl/projections/full` and receive the entire stat line in
        ONE request. Metering their league edits protects nothing and degrades what they paid for,
        so the exemption is a correctness property, not a courtesy."""
        router = pytest.importorskip("app.backend.routers.fantasy")

        class Entitled:
            fantasy = True

        # No ledger, no storage, no throttle — it returns before touching any of them.
        router._enforce_scoring_probe_guard(
            "sub-1", Entitled(), before=None, after=_cfg(REAL)
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. FAILURE MODES — the ways a limiter hurts the wrong person
# ══════════════════════════════════════════════════════════════════════════════════════════════


class TestFailureModes:
    def test_a_refused_change_does_not_spend_a_token(self):
        """A limiter that charges for its own refusals pushes the unlock time further away on every
        retry — so a real user who hits it once can never get back in."""
        guard = _guard()
        # ⭐ A PARTIAL BALANCE, and that is what makes this test able to fail. Draining to exactly
        # zero first would hide a decrementing bug behind the `max(0.0, …)` floor: 0 − 1 clamps to
        # 0, so "unchanged" and "decremented" are the same number. Starting at 0.5 separates them.
        partial = {"tokens": 0.5, "checked_at": 0.0, "changes": 3, "probe_hits": 0,
                   "last_scoring": {}, "touched": []}
        now = 0.0

        first = guard.charge(partial, _cfg({**REAL, "rec": 99.0}), now)
        assert not first.allowed
        assert first.ledger["tokens"] == pytest.approx(0.5), "a refusal spent budget"

        for _ in range(5):
            again = guard.charge(first.ledger, _cfg({**REAL, "rec": 99.0}), now)
            assert not again.allowed
            assert again.ledger["tokens"] == pytest.approx(0.5)
            assert again.retry_after_seconds <= first.retry_after_seconds

    def test_an_unreadable_ledger_fails_open_rather_than_locking_the_user_out(self):
        """The failure being guarded against here is OUR storage. Treating unreadable state as "no
        budget" would present to a real user as their league becoming permanently unsavable — much
        worse than one attacker getting one extra bucket."""
        guard = _guard()
        for junk in (None, "nonsense", {"tokens": "abc"}, {"touched": "not-a-list"}, {}):
            verdict = guard.charge(junk, _cfg(REAL), 0.0)
            assert verdict.allowed, junk

    def test_a_stored_ledger_cannot_grant_more_than_the_burst(self):
        """The other direction: a tampered or corrupted `tokens` value must not mint budget.

        ⚠️ ASSERTED ON `_coerce` DIRECTLY, not through `charge`. Two independent clamps hold this
        property (one on read, one on refill), so a test that only drove `charge` stayed GREEN with
        the read-side clamp deleted — the NF-D17 shape, where a second clause quietly covers for the
        one under test. Both are wanted; each needs its own fixture.
        """
        guard = _guard()
        coerced = guard._coerce({"tokens": 10_000.0, "checked_at": 0.0}, 0.0)
        assert coerced["tokens"] <= guard.BUDGET_BURST
        verdict = guard.charge({"tokens": 10_000.0, "checked_at": 0.0}, _cfg(REAL), 0.0)
        assert verdict.ledger["tokens"] <= guard.BUDGET_BURST

    def test_the_ledger_cannot_grow_without_bound_on_the_user_item(self):
        """It rides the users table item (400 KB, shared with the league configs themselves), so an
        unbounded list here is an item-size failure for the whole account, not just this feature."""
        guard = _guard()
        ledger, now = None, 0.0
        # Position bonuses give far more distinct scorable term keys than `per_stat` alone (53), so
        # this can actually reach the bound rather than passing because nothing could exceed it.
        stats = _scorable_stats(REAL)
        keys = [(pos, s) for pos in ("QB", "RB", "WR", "TE", "K", "DST") for s in stats]
        assert len(keys) > 128, "the fixture cannot exceed the bound it asserts"
        # ⚠️ ACCUMULATING, so every step is a ONE-key delta and actually feeds `touched`. Replacing
        # the bonus each time is a two-key delta, which the counter deliberately ignores — a
        # non-accumulating fixture leaves `touched` empty and the bound untested.
        bonuses: dict = {}
        for pos, stat in keys[:300]:
            bonuses.setdefault(pos, {})[stat] = 1.0
            ledger = guard.charge(
                ledger, _cfg(REAL, {p: dict(t) for p, t in bonuses.items()}), now
            ).ledger
            # 3 days per step, not 1: past `PROBE_TOUCH_THRESHOLD` every step here is a single-stat
            # delta and therefore SURCHARGED, so a one-token-a-day drip leaves every later charge
            # refused — and a refused charge never touches the counter, so the bound under test is
            # never approached and the test passes on a stalled fixture.
            now += 3 * SECONDS_PER_DAY
        assert len(ledger["touched"]) > 20, (
            f"the fixture only fed {len(ledger['touched'])} keys — it cannot exercise the bound"
        )
        assert len(ledger["touched"]) <= 128

    def test_a_failed_ledger_write_is_reported_rather_than_swallowed(self, caplog):
        """⭐ AN UNEVALUABLE GUARD IS NOT A PASSING ONE (NF1.7 (a)). If the ledger write is dropped,
        that change went UNCOUNTED — the budget silently stopped being enforced for that account.

        The save itself is deliberately NOT refused: turning a DynamoDB blip into "saving is broken"
        for a real user is the worse failure (E8.6). So the contract is (a) the writer reports the
        miss instead of raising, and (b) the caller emits a `[METRIC]` line an operator can see a
        run of. A silent `except: pass` here would make the budget's absence invisible.
        """
        import logging

        from app.backend.services import dynamo

        router = pytest.importorskip("app.backend.routers.fantasy")

        class Boom:
            def get_item(self, **_):
                return {}

            def update_item(self, **_):
                raise RuntimeError("dynamo is down")

        class Free:
            fantasy = False

        original = dynamo._users_table
        dynamo._users_table = lambda: Boom()
        try:
            assert dynamo.put_fantasy_scoring_ledger("u1", {"tokens": 1.0}) is False
            with caplog.at_level(logging.WARNING):
                router._enforce_scoring_probe_guard("u1", Free(), before=None, after=_cfg(REAL))
        finally:
            dynamo._users_table = original

        assert any("ledger_write_failed" in r.getMessage() for r in caplog.records), [
            r.getMessage() for r in caplog.records
        ]

    def test_the_ledger_survives_a_real_dynamodb_round_trip(self):
        """⭐ THE RUNTIME-CLASS BUG CI CANNOT SEE. DynamoDB refuses Python floats, and this ledger is
        almost entirely floats (`tokens`, `checked_at`, every stored weight). Every test above holds
        the ledger as a plain dict, so a serialization failure would be invisible here and would
        surface only on the box — as a `[METRIC] …ledger_write_failed` on EVERY change, i.e. as the
        budget silently never being enforced.

        Driven through the REAL `put_fantasy_scoring_ledger` / `get_fantasy_scoring_ledger` pair
        against a table that REJECTS floats exactly as DynamoDB does — not through `_to_ddb`
        directly, which would test the conversion helper while leaving the writer free to stop
        calling it (the wired-≠-invoked shape, NF-C0e). Then charged again off the round-tripped
        value, because "it serialized" is not "it still works as a ledger".
        """
        from decimal import Decimal

        from app.backend.services import dynamo

        guard = _guard()

        class FloatRejectingTable:
            """DynamoDB refuses `float`; boto3 raises `TypeError: Float types are not supported`."""

            def __init__(self):
                self.stored = None

            @staticmethod
            def _check(value):
                if isinstance(value, float):
                    raise TypeError("Float types are not supported. Use Decimal types instead.")
                if isinstance(value, dict):
                    for v in value.values():
                        FloatRejectingTable._check(v)
                elif isinstance(value, (list, tuple)):
                    for v in value:
                        FloatRejectingTable._check(v)

            def update_item(self, Key, UpdateExpression, ExpressionAttributeNames=None,  # noqa: N803
                            ExpressionAttributeValues=None, ConditionExpression=None):
                self._check(ExpressionAttributeValues)
                self.stored = (ExpressionAttributeValues or {})[":led"]
                return {}

            def get_item(self, Key):  # noqa: N803
                return {"Item": {"fantasy_scoring_ledger": self.stored}}

        table = FloatRejectingTable()
        original = dynamo._users_table
        dynamo._users_table = lambda: table
        try:
            verdict = guard.charge(None, _cfg({**REAL, "rec": 0.75}), 1_760_000_000.5)
            assert dynamo.put_fantasy_scoring_ledger("u1", verdict.ledger) is True, (
                "the ledger could not be written to a DynamoDB-faithful table"
            )
            assert isinstance(table.stored["tokens"], Decimal)
            restored = dynamo.get_fantasy_scoring_ledger("u1")
        finally:
            dynamo._users_table = original

        assert isinstance(restored, dict)
        again = guard.charge(restored, _cfg({**REAL, "rec": 0.9}), 1_760_000_050.0)
        assert again.allowed
        assert again.ledger["changes"] == verdict.ledger["changes"] + 1
        assert again.ledger["tokens"] == pytest.approx(guard.BUDGET_BURST - 2.0, abs=0.01)

    def test_the_throttle_message_names_what_still_works(self):
        """A paywall message that only says "no" reads as a broken form. It has to tell a real user
        what to do and what they can still edit."""
        guard = _guard()
        message = guard.throttle_message(7200)
        assert "scoring" in message.lower()
        assert "roster" in message.lower()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. THE HONEST FRAMING — a mechanical property of the source, not an intention
# ══════════════════════════════════════════════════════════════════════════════════════════════


class TestTheRecordDoesNotOverclaim:
    def test_no_guard_here_claims_the_leak_is_closed(self):
        """⛔ This vector cannot be made provably zero, and the operator's standing discipline is
        that the code must not drift into saying otherwise (the same guard `test_freemium_tier.py`
        keeps over the stat-line lock's copy). A future edit that upgrades "impractical" to
        "impossible" goes red here."""
        guard = _guard()
        lines = Path(guard.__file__).read_text().lower().splitlines()

        # 🪤 A NAIVE SUBSTRING SCAN FAILS ON THIS MODULE'S OWN PROHIBITION — its header contains the
        # sentence "nothing here may claim the leak is closed", which is the OPPOSITE of an
        # overclaim and which the first cut of this test flagged. Scanning a source file for a
        # FORBIDDEN PHRASE has to exclude the lines that forbid it, or the test fires hardest on the
        # code that got the discipline right (INC-38's prose-satisfies-a-source-scan, inverted).
        negations = ("not ", "never", "cannot", "n't", "⛔", "may claim", "must not", "nothing ")
        for i, line in enumerate(lines, start=1):
            if any(marker in line for marker in negations):
                continue
            for claim in (
                "leak is closed", "no longer possible", "cannot be reconstructed",
                "impossible to reconstruct", "zero leak", "fully prevents",
            ):
                assert claim not in line, f"line {i} claims {claim!r}: {line.strip()!r}"

        source = "\n".join(lines)
        assert "attributable" in source, "the module never says the activity is attributable"
        assert "residual" in source, "the module never names what it does NOT close"

    def test_the_residual_multi_account_path_is_recorded(self):
        """Signup is free, instant and self-serve, so fresh accounts buy the same reconstruction in
        one pass. Recording it is what keeps the next audit trusting this one (NF-EPIC 1 §9's own
        reasoning, which this story inherits rather than replaces)."""
        guard = _guard()
        source = Path(guard.__file__).read_text().lower()
        assert "residual" in source
        assert "account" in source and "signup" in source


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. END TO END through the real ASGI app — the gate is SERVER-SIDE (NF3.2)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# Raw ASGI rather than starlette's TestClient, for the reason E9.56's suite documents: TestClient
# cannot set the `aws.event` scope key Mangum uses to carry the API Gateway authorizer context,
# which is the one thing separating a real account from a forged token. A browser test could not
# vouch for any of this — hiding the editor stops nobody from PUTting a config at the API.


class _LedgerTable:
    """A users-table stub that understands BOTH map writes the league path performs."""

    def __init__(self):
        self.leagues: dict = {}
        self.ledger: dict | None = None

    def get_item(self, Key):  # noqa: N803
        item = {"fantasy_leagues": self.leagues}
        if self.ledger is not None:
            item["fantasy_scoring_ledger"] = self.ledger
        return {"Item": item}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeNames=None,  # noqa: N803
                    ExpressionAttributeValues=None, ConditionExpression=None):
        names, values = ExpressionAttributeNames or {}, ExpressionAttributeValues or {}
        expr = " ".join(UpdateExpression.split())
        if expr == "SET #fl = :empty":
            if ConditionExpression:
                raise RuntimeError("ConditionalCheckFailedException")  # the map already exists
        elif expr == "SET #fl.#id = :cfg":
            self.leagues[names["#id"]] = values[":cfg"]
        elif expr == "SET #sl = :led":
            self.ledger = values[":led"]
        else:  # a new expression shape must not pass silently
            raise AssertionError(f"unhandled UpdateExpression: {expr}")
        return {}


def _call(path: str, *, method: str = "GET", body: dict | None = None, aws_event: dict | None = None):
    import anyio

    from app.backend.main import app

    out: dict = {}
    parts: list[bytes] = []
    raw = json.dumps(body).encode() if body is not None else b""

    async def run():
        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.1"},
            "http_version": "1.1", "method": method, "scheme": "https",
            "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
            "headers": [(b"host", b"testserver"), (b"content-type", b"application/json")],
            "client": ("test", 1), "server": ("testserver", 443),
        }
        if aws_event is not None:
            scope["aws.event"] = aws_event

        async def receive():
            return {"type": "http.request", "body": raw, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                out["status"] = message["status"]
            elif message["type"] == "http.response.body":
                parts.append(message.get("body", b""))

        await app(scope, receive, send)

    anyio.run(run)
    payload = b"".join(parts)
    try:
        return out["status"], json.loads(payload)
    except Exception:  # noqa: BLE001 — a 204 has no body, and that is a valid outcome
        return out["status"], payload


def _event(groups: str = "[]", sub: str = "free-user-1"):
    """The authorizer context as Mangum delivers it. `groups="[]"` is a real, gateway-validated
    account with NO entitlement — the free tier, which is exactly who this story is about.

    ⚠️ BRACKETED AND SPACE-SEPARATED, not comma-separated: that is the shape Cognito actually
    emits, including for a single group (G100-C0-MFA).
    """
    return {
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"sub": sub, "cognito:groups": groups}}}
        }
    }


def _body(per_stat: dict) -> dict:
    return {
        "name": "Sunday Money",
        "n_teams": 10,
        "scoring": {"per_stat": per_stat},
        "roster": [
            {"name": "QB", "count": 1, "eligible": ["QB"]},
            {"name": "RB", "count": 2, "eligible": ["RB"]},
            {"name": "WR", "count": 3, "eligible": ["WR"]},
            {"name": "TE", "count": 1, "eligible": ["TE"]},
            {"name": "BENCH", "count": 6, "eligible": [], "bench": True},
        ],
    }


@pytest.fixture()
def api(monkeypatch):
    """Stub ONLY the storage boundary. Routing, both router dependencies, the entitlement resolver
    and every Pydantic model are the real thing."""
    from app.backend.services import cost_guardrails, dynamo, jwt_verify

    # The per-IP limiter is process-global and stateful, so it carries token depletion ACROSS test
    # FILES and surfaces as unrelated payload-shape failures. Reset it; its own behaviour has its
    # own suite and must not be a hidden dependency here.
    cost_guardrails.get_limiter().reset()

    table = _LedgerTable()
    monkeypatch.setattr(dynamo, "_users_table", lambda: table)
    monkeypatch.setattr(jwt_verify, "_fetch_jwks", lambda: None)
    jwt_verify.reset_jwks_cache()
    return table


class TestTheGateIsEnforcedServerSide:
    def test_a_free_account_saves_a_real_league_through_the_api(self, api):
        """The control. Everything below is only meaningful if this passes."""
        status, payload = _call(
            "/fantasy/leagues", method="POST", body=_body(REAL), aws_event=_event()
        )
        assert status == 201, payload
        assert payload["name"] == "Sunday Money"

    def test_an_isolating_probe_is_refused_by_the_api_not_by_the_editor(self, api):
        """A hand-rolled POST, no browser involved. 400 rather than 429: this config would never be
        stored at any budget, and charging a token for our own refusal would let a scripted caller
        drain a real user's bucket with configs that were never going to be saved."""
        status, payload = _call(
            "/fantasy/leagues", method="POST", body=_body({"rec": 1.0, "pass_yds": 0.0}),
            aws_event=_event(),
        )
        assert status == 400, payload
        assert "core" in str(payload.get("detail", "")).lower()
        assert api.ledger is None, "a refused config spent budget"

    def test_a_free_account_that_burns_its_budget_is_throttled_with_a_retry_after(self, api):
        """The primary lever, end to end. A real user never reaches this; a reconstruction walk
        reaches it on its 13th change and then waits a day per change for the next 20."""
        guard = _guard()
        stats = _scorable_stats(REAL)
        last = None
        for i in range(int(guard.BUDGET_BURST) + 1):
            probe = dict(REAL)
            probe[stats[i]] = 1.0 + i
            last = _call(
                "/fantasy/leagues", method="POST", body=_body(probe), aws_event=_event()
            )
        status, payload = last
        assert status == 429, payload
        assert "scoring" in str(payload.get("detail", "")).lower()

    def test_the_real_attack_path_is_the_PUT_and_it_is_throttled_too(self, api):
        """⭐ THE PATH THAT MATTERS. A free account holds ONE league (`FREE_PERSONALIZED_LEAGUE_
        QUOTA`), so a reconstruction walk cannot use `POST` — it edits the one league it has, over
        and over. `PUT` deliberately carries NO quota check (a user at their quota must still be
        able to edit), which is exactly why the meter has to be here rather than on the count.
        """
        guard = _guard()
        status, created = _call(
            "/fantasy/leagues", method="POST", body=_body(REAL), aws_event=_event()
        )
        assert status == 201, created
        league_id = created["league_id"]

        stats = _scorable_stats(REAL)
        probe = dict(REAL)
        statuses = []
        for i in range(int(guard.BUDGET_BURST) + 2):
            probe[stats[i]] = 1.0 + i
            code, payload = _call(
                f"/fantasy/leagues/{league_id}", method="PUT", body=_body(dict(probe)),
                aws_event=_event(),
            )
            statuses.append(code)
        assert 429 in statuses, statuses
        assert statuses[0] == 200, "a real user's first edit was throttled"

    def test_editing_everything_EXCEPT_the_scoring_is_never_throttled(self, api):
        """The separation, end to end: renaming a league or re-linking a team leaves `pts` alone,
        leaks nothing, and must stay free however many times a user does it."""
        status, created = _call(
            "/fantasy/leagues", method="POST", body=_body(REAL), aws_event=_event()
        )
        assert status == 201, created
        league_id = created["league_id"]

        # 15, not 40: `_call` sends no `Authorization` HEADER (the authorizer context rides the
        # `aws.event` scope key instead), so `cost_guardrails` classifies these as PUBLIC and its
        # own 30-request burst — nothing to do with this story — fires first at ~31 calls. 15 still
        # proves the point, being comfortably more than the 12-token scoring budget would allow if
        # a rename were charged.
        for i in range(15):
            body = {**_body(REAL), "name": f"Rename {i}", "source_team_key": f"team-{i}"}
            code, payload = _call(
                f"/fantasy/leagues/{league_id}", method="PUT", body=body, aws_event=_event()
            )
            assert code == 200, (i, code, payload)

    def test_a_subscriber_is_never_throttled_on_the_same_traffic(self, api):
        """⭐ THE TWO-SIDED HALF. The identical request pattern that throttles a free account must
        not touch a subscriber — they can already fetch the whole stat line from
        `/fantasy/nfl/projections/full` in ONE request, so metering them protects nothing."""
        guard = _guard()
        stats = _scorable_stats(REAL)
        for i in range(int(guard.BUDGET_BURST) + 4):
            probe = dict(REAL)
            probe[stats[i]] = 1.0 + i
            status, payload = _call(
                "/fantasy/leagues", method="POST", body=_body(probe),
                aws_event=_event(groups="[subscriber]", sub="paid-1"),
            )
            assert status in (201, 409), (i, status, payload)

    def test_reading_a_league_is_never_gated_by_the_write_rules(self, api):
        """E9.49: a rule tightened for SAVES must never run on the READ path. A league stored before
        these rules existed — or one an operator seeded — has to stay readable and deletable."""
        api.leagues["legacy"] = {
            "name": "Legacy", "n_teams": 12, "sport": "nfl",
            "scoring": {"per_stat": {"rec": 1.0}},  # would be REFUSED as a save today
            "roster": [{"name": "QB", "count": 1, "eligible": ["QB"], "bench": False}],
        }
        status, payload = _call("/fantasy/leagues", aws_event=_event())
        assert status == 200, payload
        assert [league["name"] for league in payload] == ["Legacy"]


def _configs_in(obj, out=None) -> list[dict]:
    """Every `{scoring: {per_stat: …}}` config nested anywhere in a captured fixture."""
    out = [] if out is None else out
    if isinstance(obj, dict):
        scoring = obj.get("scoring")
        if isinstance(scoring, dict) and isinstance(scoring.get("per_stat"), dict):
            out.append(obj)
        for value in obj.values():
            _configs_in(value, out)
    elif isinstance(obj, list):
        for value in obj:
            _configs_in(value, out)
    return out
