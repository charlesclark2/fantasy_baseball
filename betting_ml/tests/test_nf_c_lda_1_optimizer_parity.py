"""NF-C-LDA-1 — THE PARITY GUARD between the two draft optimizers.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⭐ WHY THIS FILE IS LOAD-BEARING
═══════════════════════════════════════════════════════════════════════════════════════════════════
There are two draft optimizers, and both headers claim to be in lock-step with the other:

    frontend/lib/draft-optimizer.ts                  the SHIPPING engine (the web app draft tool)
    quant_sports_intel_models/fantasy_engine/draft.py the one the API Lambda runs for the extension

They had SILENTLY DRIFTED. Measured 2026-08-19 on a real 2026 full_ppr/12 board, the Python engine
was two shipped fixes behind — NF-D19's tier SIZING and NF-C2.1's flex-seat re-basing — and in a
mid-draft state that changed WHICH PLAYER was recommended (5 of 8 slots agreed; the Python engine
surfaced a TE the TS engine did not rank at all). A third difference was subtler and would have
survived any eyeball review: the TS engine rounds its outputs with `Math.round(x * 10) / 10` (half
AWAY FROM ZERO) while Python's `round(x, 1)` is half-to-EVEN, so `score` sat 0.05 apart on 10 of 41
sampled draft states — and the sort reads that rounded value.

Nothing would have surfaced any of it. Both engines run, both return plausible recommendations, no
error is raised anywhere — the E9.61 "two renderers of one field are two rule sets" class, aimed at
the number the product advises with. NF-C-LDA-1 put a live-draft overlay on the Python side, so the
drift became "the extension recommends a different player from the website", which is exactly the
failure the epic's ONE-RANKER rule exists to prevent.

═══════════════════════════════════════════════════════════════════════════════════════════════════
HOW IT WORKS, AND WHY IT IS SHAPED THIS WAY
═══════════════════════════════════════════════════════════════════════════════════════════════════
`frontend/scripts/gen-optimizer-parity-fixture.mjs` runs the TS engine over a committed board and a
committed set of draft states and records what it returned. This test replays the SAME states
through the Python engine and demands the SAME bytes.

⭐ THE FIXTURE IS REAL ENGINE OUTPUT, NEVER HAND-WRITTEN (NF-C0e). A hand-written expectation would
encode what its author BELIEVED the TS engine does, and the drift above is precisely a case where
that belief was wrong.

⭐ THE TS SIDE IS THE AUTHORITY. It is the engine users already draft with and its two extra fixes
were each measured on live boards. Parity is restored by moving Python to it — never the reverse.

⚠️ NODE IS NOT ON THE CI PATH. The committed fixture is; the generator is a developer tool. A test
that shelled out to node would go green-by-skip on any runner without it, which is the
NF1.7(a) vacuous-guard class — a check that could not run is not a check that passed.

⚠️ THE ADAPTER UNDER TEST IS THE SHIPPED ONE. The board publishes camelCase and the Python engine
reads snake_case, so something must translate. This test imports
`draft_assistant.engine_row` — the function the API endpoint itself calls — rather than
re-implementing the mapping locally, which would measure a translation we do not ship.

⛔ ANCHORED IN ITS OWN CLAUSE (E9.60): everything here fails only for NF-C-LDA-1's property.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.backend.services.draft_assistant import engine_row

_FIXTURES = Path(__file__).parent / "fixtures"
_INPUT = _FIXTURES / "nf_c_lda_1_optimizer_parity_input.json"
_EXPECTED = _FIXTURES / "nf_c_lda_1_optimizer_parity.json"


@pytest.fixture(scope="module")
def parity() -> tuple[dict, dict]:
    return json.loads(_INPUT.read_text()), json.loads(_EXPECTED.read_text())


def _python_recommendations(source: dict, scenario: dict) -> list[dict]:
    """Run the Python engine over one draft state, projected onto the TS engine's output shape."""
    from quant_sports_intel_models.fantasy_engine.draft import recommend
    from quant_sports_intel_models.fantasy_engine.league_config import LeagueConfig

    replacement = source["replacement"]
    rows = [engine_row(r, replacement) for r in source["board"]]
    recs = recommend(
        rows,
        config=LeagueConfig.from_dict(source["config"]),
        drafted_ids=scenario["drafted"],
        my_player_ids=scenario["mine"],
        # NF-C7 — `None` on every pre-NF-C7 scenario, which is the shape a caller that has never
        # heard of depth targets sends, so those scenarios keep pinning the INERT path too.
        depth_targets=scenario.get("depthTargets"),
        top_n=scenario.get("topN", 8),
    )
    return [
        {
            "id": r.player_id,
            "pos": r.position,
            "score": r.score,
            "needLevel": r.need_level,
            "needBonus": r.need_bonus,
            "seatValue": r.seat_value,
            "orderValue": r.order_value,
            "depthShort": r.depth_short,
            "expectedStarts": r.expected_starts,
            "positionalDropoff": r.positional_dropoff,
            "tier": r.tier,
            "isLastInTier": r.is_last_in_tier,
            "byeConflict": r.bye_conflict,
            "mustFill": r.must_fill,
            "deferred": r.deferred,
            "rationale": r.rationale,
        }
        for r in recs
    ]


# ── Non-vacuity: every clause below iterates the fixture, so an empty one passes on nothing ──────
def test_the_parity_fixture_is_populated_and_exercises_the_engine(parity):
    """⚠️ THE ANTI-VACUITY CLAUSE. Every assertion in this file loops over the fixture's scenarios,
    and a loop over an empty collection is a test that passes on nothing (NF1.7(a) / DSR-CONV #690,
    where a guard's only `grep` hit was a dict key and its body ran zero times)."""
    source, expected = parity
    assert len(source["board"]) > 500, "the parity board is too small to exercise position pools"
    assert len(source["scenarios"]) >= 20, "too few draft states to catch a state-dependent drift"
    assert set(source["scenarios"]) == set(expected["expected"]), (
        "the input and expectation fixtures describe different scenario sets — regenerate with "
        "frontend/scripts/gen-optimizer-parity-fixture.mjs"
    )
    total = sum(len(v) for v in expected["expected"].values())
    assert total >= 200, f"only {total} recommendations recorded; the guard would prove little"
    # …and the states must actually reach the mechanisms, or the fixture could agree by never
    # exercising them.
    flat = [r for v in expected["expected"].values() for r in v]
    assert any(r["needLevel"] == 2 for r in flat), "no state reaches a DEDICATED starter need"
    assert any(r["needLevel"] == 1 for r in flat), "no state reaches a FLEX seat (NF-C2.1)"
    assert any(r["needLevel"] == 0 for r in flat), "no state reaches a surplus/bench pick"
    assert any(r["mustFill"] for r in flat), "no state reaches the reserve constraint"
    # ── NF-C7 ──────────────────────────────────────────────────────────────────────────────────
    # Both clauses are ANTI-VACUITY, not behaviour: they assert the fixture REACHES the two NF-C7
    # mechanisms, so the byte-equality test below is actually pinning them. Without these the two
    # engines could agree on depth targets by never once setting one (NF1.7(a)).
    assert any(r["depthShort"] > 0 for r in flat), (
        "no scenario sets a DEPTH TARGET that fires — regenerate the input fixture with "
        "betting_ml/tests/fixtures/_gen_nf_c_lda_1_parity_input.py"
    )
    assert any(r["needLevel"] == 0 and r["expectedStarts"] > 0 for r in flat), (
        "no bench candidate has a non-zero expected-start count, so the insurance rule is unpinned"
    )
    assert any(r["needLevel"] == 0 and abs(r["seatValue"] - r["score"]) < 1e-9 and r["score"] >= 0
               for r in flat), "no bench candidate is scored on its insurance value alone"
    # The NF-C7 sort key DIVERGES from `score` for a bench candidate — if the fixture never reaches a
    # state where it does, the byte-equality clause below is agreeing about an untaken branch.
    assert any(r["needLevel"] == 0 and abs(r["orderValue"] - r["score"]) > 1e-9 for r in flat), (
        "no bench candidate's sort key differs from its score — the NF-C7 placement rule is unpinned"
    )
    assert len({r["tier"] for r in flat}) > 1, "every row is one tier — NF-D19 sizing untested"


def test_the_python_engine_reproduces_the_shipping_engine_exactly(parity):
    """Field-for-field equality, zero tolerance.

    ⛔ NOT "close enough". A tolerance here could only be defended by someone who already knew how
    big the drift was — which is the thing under test. The two engines were made to agree exactly,
    including the JS rounding rule (`_js_round1`), so the guard demands exactly that.
    """
    source, expected = parity
    mismatches: list[str] = []
    for name, want in expected["expected"].items():
        got = _python_recommendations(source, source["scenarios"][name])
        if len(got) != len(want):
            mismatches.append(f"{name}: returned {len(got)} recommendations, expected {len(want)}")
            continue
        for i, (w, g) in enumerate(zip(want, got)):
            for field in w:
                if w[field] != g[field]:
                    mismatches.append(f"{name}[{i}].{field}: TS={w[field]!r} PY={g[field]!r}")
    assert not mismatches, (
        "the Python optimizer has drifted from the shipping TS engine — the live-draft extension "
        "would advise a different pick from the web app, silently:\n  "
        + "\n  ".join(mismatches[:25])
    )


def test_the_recommended_pick_itself_agrees_state_for_state(parity):
    """The ORDER, stated separately from the field values.

    The clause above would also fail on a cosmetic difference; this one fails only when the tool's
    actual ADVICE differs, so a reader can tell "the sentence changed" from "we now recommend a
    different player" without reading a 25-line diff.
    """
    source, expected = parity
    differing = []
    for name, want in expected["expected"].items():
        got = _python_recommendations(source, source["scenarios"][name])
        if [r["id"] for r in want] != [r["id"] for r in got]:
            differing.append(f"{name}: TS={[r['id'] for r in want][:4]} PY={[r['id'] for r in got][:4]}")
    assert not differing, "the two engines recommend different players:\n  " + "\n  ".join(differing[:10])


def test_the_engine_row_adapter_supplies_every_field_the_engine_reads(parity):
    """The adapter is the join between the two vocabularies, so a field it forgets is a silent zero.

    `fantasy_engine.draft` reads its inputs with `.get()` and `_fnum(..., default=0.0)`, so a
    missing key does not raise — it scores as 0 and the recommendation is quietly wrong. This pins
    the mapping to the keys the engine actually reads.
    """
    source, _ = parity
    row = engine_row(source["board"][0], source["replacement"])
    for field in (
        "player_id", "player_name", "position", "team_id", "vor", "league_points",
        "replacement_points", "positional_rank", "overall_rank", "bye", "is_rookie",
        "vor_p10", "vor_p90", "low_pred",
        # NF-C7 — expected games played, the input to the bench seat's insurance value. A missing
        # key here is a SILENT ZERO: every bench candidate would price as worthless cover and the
        # panel would look plausible while ranking depth by nothing at all.
        "games",
    ):
        assert field in row, f"engine_row drops {field!r}, which the optimizer reads"
    assert row["player_id"] is not None and row["league_points"] is not None
    # `replacement_points` has no same-named board column — the adapter derives it, and a 0 here
    # would silently flatten the last-player VONA fallback and the whole flex-seat re-basing.
    assert row["replacement_points"], "replacement_points resolved to a falsy value"


def test_the_lockstep_claim_is_stated_in_both_engines(parity):
    """Both files must SAY they are pinned, and name this guard.

    A future editor of either engine has to learn that the other exists. The comment is not the
    enforcement — the clauses above are — but a silent pin is one a reader can violate in good
    faith, then be surprised by a red build they cannot explain.
    """
    repo = Path(__file__).resolve().parents[2]
    ts = (repo / "frontend/lib/draft-optimizer.ts").read_text()
    py = (repo / "quant_sports_intel_models/fantasy_engine/draft.py").read_text()
    assert "fantasy_engine/draft.py" in ts, "the TS engine does not name its Python counterpart"
    assert "draft-optimizer.ts" in py, "the Python engine does not name its TS counterpart"
    assert "test_nf_c_lda_1_optimizer_parity" in py, (
        "the Python engine does not name the guard that pins it — an editor who changes it has no "
        "pointer to why the build went red"
    )
