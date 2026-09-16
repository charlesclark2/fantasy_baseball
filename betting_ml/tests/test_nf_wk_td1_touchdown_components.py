"""NF-WK-TD1 — the weekly component line carries TOUCHDOWNS, and cannot ship without them.

⭐ THE DEFECT, MEASURED ON THE PUBLISHED ARTIFACT. `WP.COMPONENTS` declares eleven components and
`WEEKLY_COMPONENT_FIELD` serves eleven keys, but only SEVEN label columns reached the matrix, so
`fit_component_head` skipped four in silence and `build_players` wrote them as `None`. On the
2026 wk 2 payload (`generated_at 2026-09-15T15:32:59+00:00`, committed under `ablation_results/`)
all 500 rows carried `passTd`/`passInt`/`rushTd`/`recTd` as null — a league scoring touchdowns
scored none of them, and touchdown terms are 22.1% of realized PPR (QB 33.3%).

⛔ KEYS-PRESENT-BUT-NULL IS HOW IT HID, and it is why every clause here counts NON-NULL VALUES.
A check asking WHICH FIELDS the payload carries reports full coverage of all eleven on the broken
artifact and passes. That artifact went through contract validation, an NF-G0 promotion review and
a live runtime gate. `available_fields` — the real classifier behind CAPTURED/APPLIED — is the
witness: it is keyed on a non-null number, so the pre-TD payload resolved four league terms to
CAPTURED while reporting the keys present.

⛔ THE REFUSAL IS IN THE BUILDER, NOT ON THE CONTRACT, and that is deliberate rather than weak.
Making the fields non-optional would break the ALREADY-PUBLISHED pre-TD artifact on read (NF-C0:
a response-shape change must be additive, and the deployed client reads a payload whose TD keys are
null). So both artifacts stay readable and the BUILD is what refuses to make another broken one —
which is exactly the pair of clauses in section 4.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.backend.models import nfl_weekly as C
from app.backend.services import league_scoring, weekly_league_board
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.fantasy import weekly_serving as WS

_REPO = Path(__file__).resolve().parents[2]
_FAN = _REPO / "quant_sports_intel_models/football/nfl/fantasy"
_AR = _FAN / "ablation_results"
_TD_FIELDS = ("passTd", "passInt", "rushTd", "recTd")


def _matrix(n: int = 24) -> pd.DataFrame:
    """A matrix in the SERVING shape: the seven labels `engineer_features` leaves on it, no TDs."""
    rng = np.random.default_rng(3)
    return pd.DataFrame({
        "season": 2025, "week": np.repeat([1, 2], n // 2),
        "gsis_id": [f"P{i:03d}" for i in range(n)],
        "position": np.resize(list(WP.POSITIONS), n),
        "attempts": rng.integers(0, 40, n).astype(float),
        "passing_yards": rng.integers(0, 350, n).astype(float),
        "carries": rng.integers(0, 20, n).astype(float),
        "rushing_yards": rng.integers(0, 120, n).astype(float),
        "targets": rng.integers(0, 12, n).astype(float),
        "receptions": rng.integers(0, 9, n).astype(float),
        "receiving_yards": rng.integers(0, 140, n).astype(float),
    })


def _feed(m: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    return pd.DataFrame({
        "season": m["season"].to_numpy(), "week": m["week"].to_numpy(),
        "player_id": m["gsis_id"].to_numpy(),
        "passing_tds": rng.integers(0, 4, len(m)).astype(float),
        "passing_interceptions": rng.integers(0, 3, len(m)).astype(float),
        "rushing_tds": rng.integers(0, 3, len(m)).astype(float),
        "receiving_tds": rng.integers(0, 3, len(m)).astype(float),
    })


def _row(**kw) -> dict:
    r = {"id": "P1", "name": "P", "pos": "WR", "team": "AAA", "opp": "BBB", "home": True,
         "status": "projected", "fpPpr": 9.0, "fpP10": 2.0, "fpP90": 17.0,
         "rosPpr": None, "rosP10": None, "rosP90": None, "rosWeeks": 0, "histWeeks": 4,
         "q": [1.0] * len(WP.Q_LEVELS)}
    r.update({f: 1.0 for f in C.WEEKLY_COMPONENT_FIELD.values()})
    r.update(kw)
    return r


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The attach: DERIVED, never a hand list
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_every_declared_component_reaches_the_matrix():
    m = _matrix()
    assert [c for c in WP.COMPONENTS if c not in m.columns] == [
        "passing_tds", "passing_interceptions", "rushing_tds", "receiving_tds"], (
        "the fixture no longer reproduces the serving shape this story fixes")
    out, audit = WS.attach_component_labels(m, _feed(m))
    assert not [c for c in WP.COMPONENTS if c not in out.columns]
    assert audit["attached"] == ["passing_tds", "passing_interceptions",
                                 "rushing_tds", "receiving_tds"]


def test_the_missing_set_is_derived_so_a_twelfth_component_cannot_land_null():
    """⭐ THE CLAUSE THAT KEEPS THIS FIX FROM BEING A ONE-OFF.

    A hand list of the four would re-arm the exact defect it fixes: a component added to
    `WP.COMPONENTS` later would be skipped by `fit_component_head` and written as `None`, silently,
    and the next reader would repeat this investigation. Driving the function with a component it
    has never seen is the only way to tell a derived set from a hard-coded one — asserting the four
    names would pass on either.
    """
    m = _matrix()
    feed = _feed(m)
    feed["sack_fumbles_lost"] = 1.0
    out, audit = WS.attach_component_labels(
        m, feed, components=(*WP.COMPONENTS, "sack_fumbles_lost"))
    assert "sack_fumbles_lost" in out.columns and "sack_fumbles_lost" in audit["attached"]


def test_a_column_already_on_the_matrix_is_left_alone_rather_than_merged_twice():
    """A double merge suffixes and orphans the label (`EM.attach_td_labels` raises on it). Deriving
    the missing set makes that impossible instead of detected — so re-running is a NO-OP, which is
    also what keeps a serving build alive if `engineer_features` ever starts carrying a column."""
    m = _matrix()
    once, _ = WS.attach_component_labels(m, _feed(m))
    twice, audit = WS.attach_component_labels(once, _feed(m))
    assert audit["attached"] == [] and len(audit["already_present"]) == len(WP.COMPONENTS)
    assert not [c for c in twice.columns if c.endswith(("_x", "_y"))]
    pd.testing.assert_frame_equal(once, twice)


def test_the_attach_refuses_a_duplicate_grain():
    m = _matrix()
    feed = pd.concat([_feed(m), _feed(m).head(1)], ignore_index=True)
    with pytest.raises(WS.WeeklyServingError, match="duplicate"):
        WS.attach_component_labels(m, feed)


def test_the_attach_refuses_a_conservation_failure():
    """A corrupt feed must not be able to change the label silently. Driven by making the join
    itself lossy — a key the matrix carries whose feed value cannot arrive intact."""
    m = _matrix()
    feed = _feed(m)
    feed.loc[:, "rushing_tds"] = np.nan
    feed.loc[0, "rushing_tds"] = 5.0
    # duplicate a MATRIX key so the merge fans out and the matrix-side sum double-counts
    m2 = pd.concat([m, m.head(1)], ignore_index=True)
    with pytest.raises(WS.WeeklyServingError, match="conservation FAILED|row count"):
        WS.attach_component_labels(m2, feed)


def test_the_attach_refuses_rather_than_degrades_when_the_feed_lacks_a_declared_column():
    """⛔ Serving a declared component as null is HOW IT WAS LOST. So a feed that cannot supply one
    is a refusal, not a quiet null — the alternative is this story's own defect, re-shipped."""
    m = _matrix()
    feed = _feed(m).drop(columns=["rushing_tds"])
    with pytest.raises(WS.WeeklyServingError, match="no column"):
        WS.attach_component_labels(m, feed)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The head and the payload — with NO change to either
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_component_head_fits_all_eleven_once_the_labels_are_there():
    m = _matrix(48)
    out, _ = WS.attach_component_labels(m, _feed(m))
    train, score = out[out["week"] == 1], out[out["week"] == 2].reset_index(drop=True)
    feats = [c for c in ("attempts", "passing_yards", "carries") if c in out.columns]
    comps = WP.fit_component_head(train, score, feats)
    assert sorted(c for c in comps.columns if c.startswith("proj_")) == sorted(
        f"proj_{c}" for c in WP.COMPONENTS)


def test_build_players_emits_every_component_field_unchanged():
    m = _matrix(48)
    out, _ = WS.attach_component_labels(m, _feed(m))
    train, score = out[out["week"] == 1], out[out["week"] == 2].reset_index(drop=True)
    comps = WP.fit_component_head(train, score, ["attempts", "passing_yards", "carries"])
    universe = score[["gsis_id", "position"]].copy()
    universe["team"] = "AAA"; universe["is_bye"] = False
    universe["opponent"] = "BBB"; universe["is_home"] = 1.0
    qmap = {str(g): np.linspace(0.0, 20.0, len(WP.Q_LEVELS)) for g in score["gsis_id"]}
    ros = pd.DataFrame(columns=["ros_mean", "ros_q10", "ros_q90", "n_weeks"]).rename_axis("gsis_id")
    players = WS.build_players(universe, qmap, comps, ros, names={}, hist_weeks={})
    assert players
    for f in C.WEEKLY_COMPONENT_FIELD.values():
        assert all(r[f] is not None for r in players), f"{f} still null"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Wiring — the attach and the refusal are INVOKED, not merely defined (NF-C0e)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_build_serving_matrix_calls_the_attach_on_the_real_feed_not_the_stub():
    """⛔ THE FEED CHOICE IS THE CLAUSE. `build_serving_matrix` deliberately keeps two feeds: the
    opponent-grid stub supplies GROUP KEYS, and a stub's zero reaching a LABEL is a fabricated
    outcome — the same reason `attach_labels` is given the real feed. Asserting merely that the
    attach is called would pass on the wrong one."""
    src = _FAN.joinpath("weekly_serving.py").read_text()
    body = src.split("def build_serving_matrix", 1)[1].split("\ndef ", 1)[0]
    body = "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))
    assert "attach_component_labels(modeled, src[\"stats\"])" in body, (
        "build_serving_matrix must attach from the REAL stats feed, not `feat_stats` (which carries "
        "the opponent-grid stub — a stub zero reaching a label is a fabricated outcome)")
    assert "attach_component_labels(modeled, feat_stats" not in body


def test_the_runner_refuses_a_payload_whose_component_line_is_incomplete():
    src = _FAN.joinpath("run_weekly_serving.py").read_text()
    src = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
    assert "WS.assert_component_line_complete(players)" in src, (
        "the completeness refusal is defined but nothing calls it (wired ≠ invoked)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The refusal — VALUES, never keys
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_refusal_fires_on_the_published_pre_td_artifact_shape():
    """⭐ THE DECISIVE CLAUSE, driven by the REAL committed payload rather than a hand-made one.

    Every one of its 500 rows carries all eleven component KEYS and four of them are null. A
    fields-carried check passes on it; this must not."""
    payload = json.loads((_AR / "nf_wk_td1_before_week2_players.json").read_text())
    rows = payload["players"]
    assert all(all(f in r for f in _TD_FIELDS) for r in rows), "fixture is not the keys-present shape"
    assert all(r[f] is None for r in rows for f in _TD_FIELDS), "fixture is not the all-null shape"
    with pytest.raises(WS.WeeklyServingError, match="NULL on projected players"):
        WS.assert_component_line_complete(rows)


def test_a_fields_carried_check_PASSES_on_that_same_artifact():
    """The counterexample, pinned — so the next reader does not reintroduce the cheaper check.

    `component_fields_present` is the real classifier the league board uses. On the broken payload
    it reports ALL ELEVEN fields... as far as key presence goes it is complete. The reason it is
    not is that `available_fields` is keyed on a non-null NUMBER — which is the whole lesson."""
    rows = json.loads((_AR / "nf_wk_td1_before_week2_players.json").read_text())["players"]
    assert all(f in rows[0] for f in C.WEEKLY_COMPONENT_FIELD.values())
    present = weekly_league_board.component_fields_present(rows)
    assert _TD_FIELDS[0] not in present, "available_fields must be keyed on a VALUE, not a key"
    assert len(present) == len(C.WEEKLY_COMPONENT_FIELD) - len(_TD_FIELDS)


def test_the_refusal_fires_on_a_fabricated_row_for_a_player_the_model_did_not_project():
    bad = _row(status="unprojected")
    with pytest.raises(WS.WeeklyServingError, match="did not project"):
        WS.assert_component_line_complete([_row(), bad])


def test_a_bye_is_the_documented_exception_and_does_not_trip_either_direction():
    bye = _row(status="bye", **{f: 0.0 for f in C.WEEKLY_COMPONENT_FIELD.values()})
    assert WS.assert_component_line_complete([_row(), bye])["n_projected"] == 1


def test_the_refusal_refuses_to_pass_on_nothing():
    """NF1.7 (a): a check that examined no projected row has not passed."""
    with pytest.raises(WS.WeeklyServingError, match="ZERO projected rows"):
        WS.assert_component_line_complete([_row(status="bye")])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Both artifacts stay readable — the NF-C0 additive rule, both directions
# ══════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("td_value", [None, 1.25])
def test_the_contract_accepts_the_pre_TD_and_post_TD_artifacts_alike(td_value):
    """⛔ The contract must NOT be tightened to require the TD fields. The pre-TD payload is already
    PUBLISHED and the deployed client reads it; a required field would 500 on it (NF-C0)."""
    C.NflWeeklyPlayer.model_validate(_row(**{f: td_value for f in _TD_FIELDS}))


@pytest.mark.parametrize("td_value", [None, 1.25])
def test_the_league_board_scores_both_artifacts_without_raising(td_value):
    rows = [_row(id=f"P{i}", **{f: td_value for f in _TD_FIELDS}) for i in range(3)]
    fields = league_scoring.available_fields(rows)
    for f in _TD_FIELDS:
        assert (f in fields) is (td_value is not None), (
            "CAPTURED/APPLIED must follow the VALUE, not the key")


def test_emission_flips_the_touchdown_terms_from_captured_to_applied():
    """⭐ THE CONSUMER-VISIBLE POINT OF THE WHOLE STORY, measured through the real resolver."""
    stat_field = dict(C.STAT_FIELD)
    scoring = {"per_stat": {"pass_td": 4.0, "rush_td": 6.0, "rec_td": 6.0,
                            "pass_int": -2.0, "rec_yds": 0.1}}
    before = [_row(**{f: None for f in _TD_FIELDS})]
    after = [_row(**{f: 0.5 for f in _TD_FIELDS})]

    def applied(rows: list[dict]) -> set[str]:
        _, report = league_scoring.resolve_scoring(
            scoring, stat_field=stat_field, fields=league_scoring.available_fields(rows))
        return {t["key"] for t in report["terms"] if t["verdict"] == "applied"}

    before_applied, after_applied = applied(before), applied(after)
    td_terms = {"pass_td", "rush_td", "rec_td", "pass_int"}
    # ⛔ Both directions: the terms must be CAPTURED before and APPLIED after. Asserting only the
    # second would pass on a resolver that always applies them.
    assert not (td_terms & before_applied), f"pre-TD payload already applied {td_terms & before_applied}"
    assert td_terms <= after_applied, f"emission did not flip them (after applied {after_applied})"
    # …and a term that was ALREADY applied stays applied — the flip is additive, not a reshuffle.
    assert "rec_yds" in before_applied and "rec_yds" in after_applied


def test_the_weekly_page_filters_the_stat_line_on_a_VALUE_so_both_artifacts_render():
    """The FE1 page must keep rendering the pre-TD artifact AND pick the TD columns up for free.

    It filters per field on `!= null`, so a null TD column is simply not drawn and a populated one
    appears with no page change. Asserting the FILTER rather than a rendered column is deliberate:
    the rendered output is the E2E suite's business, and what this clause owns is that the page
    never assumes a component is present (the shape that would 500 on the already-published blob).
    """
    page = (_REPO / "frontend/components/fantasy/weekly-page.tsx").read_text()
    assert "paid![key] != null" in page, (
        "the weekly page no longer filters its stat line on a non-null VALUE — a pre-TD payload "
        "(already published, and what the deployed client reads) must still render")


def test_a_raw_recapture_cannot_retire_the_synthetic_bye_row():
    """⚠️ MT1 finding 7, pinned BEFORE the re-capture that will tempt the mistake.

    The published 2026 wk 2 payload carries `n_bye: 0`, so a raw capture of it cannot exercise the
    bye clause at all — swapping the fixtures wholesale would trade a real defect for a vacuous
    guard. The re-arm condition is `manifest.n_bye > 0` on a captured week, never a guessed week
    number. This clause holds the line by asserting the fixture set still contains a bye.
    """
    fx = json.loads((_REPO / "frontend/e2e/fixtures/api/"
                     "fantasy-nfl-weekly-players-entitled.synthetic.json").read_text())
    byes = [r for r in fx["players"] if r.get("status") == "bye"]
    assert byes, (
        "the entitled weekly fixture no longer contains a bye row. The published week this would "
        "have been captured from has n_bye=0, so the bye clause is now VACUOUS — keep a "
        "deliberately-synthetic bye and re-arm on manifest.n_bye > 0.")
    assert all(byes[0].get(f) == 0.0 for f in C.WEEKLY_COMPONENT_FIELD.values()), (
        "a bye's component line must be the DETERMINISTIC identity zero NF-W1 pre-registered, "
        "not null and not an estimate")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. A label on an unplayed week is INERT — proven, not asserted
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_a_target_week_label_can_never_reach_training():
    """The attach fills an unmatched (target-week) row with the frame's retained ZERO. That is only
    safe because `build` trains STRICTLY before the target week, so the fabricated zero is never
    read as a label. That is a property of the runner's code, which a future edit could remove —
    so it is read from the source rather than trusted."""
    src = _FAN.joinpath("run_weekly_serving.py").read_text()
    src = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
    assert 'train = modeled.loc[modeled["gw"] < int(target_rows["gw"].iloc[0])]' in src, (
        "training is no longer strictly before the target week — a target-week component label "
        "(a retained zero for an unplayed game) would become a training outcome")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The NF-INC-0914 pattern, extended to this entrypoint (card GyD9hoeD)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_no_name_in_the_weekly_serving_path_resolves_nowhere():
    """The NF-INC-0914 static scope check, pointed at the two modules this story edits.

    ⭐ WHY IT IS HERE. `run_weekly_serving.main()` DOES have executing callers — but both reach only
    the `--publish`-bucket refusal, which raises before `build()` runs (the caller patches `build`
    to explode and asserts it does not). So `main()`'s SUCCESS PATH has never been executed by
    anything, which is precisely the shape that stopped every board publish in NF-INC-0914. A real
    execution of it needs a whole synthetic lake; this static check costs milliseconds, has no
    fixture-coverage blind spot, and catches the exact break that incident was."""
    for rel in ("run_weekly_serving.py", "weekly_serving.py"):
        tree = ast.parse((_FAN / rel).read_text())

        def bound(node, into: set) -> set:
            for n in ast.walk(node):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                    into.add(n.id)
                elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    into.add(n.name)
                elif isinstance(n, ast.alias):
                    into.add((n.asname or n.name).split(".")[0])
                elif isinstance(n, ast.ExceptHandler) and n.name:
                    into.add(n.name)
                elif isinstance(n, ast.arg):
                    into.add(n.arg)
            return into

        import builtins
        module_scope = bound(tree, set())
        fns = [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        assert fns, f"{rel}: scope check found no functions — it would pass on nothing"
        unresolved = [
            f"{rel}:{fn.name}() line {n.lineno}: {n.id!r}"
            for fn in fns
            for n in ast.walk(fn)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
            and n.id not in (bound(fn, set()) | module_scope | set(dir(builtins)))
        ]
        assert not unresolved, (
            "name(s) in the weekly serving path resolve nowhere — the NF-INC-0914 class, which on "
            "the box is a NameError that publishes nothing:\n  " + "\n  ".join(sorted(set(unresolved))))


def test_the_weekly_entrypoints_success_path_is_recorded_as_unexecuted():
    """⚠️ AN HONEST MARKER, NOT A GUARD — and it is here because the card's premise is not quite
    right and a future reader should not inherit the wrong version.

    Card GyD9hoeD says `run_weekly_serving.main()` has "zero executing callers". Measured: it has
    TWO, and both stop at the `--publish` bucket refusal. The exposure is real but narrower —
    everything AFTER that refusal is unexecuted by CI. This clause pins the measurement so the
    successor story scopes itself to the right gap."""
    import warnings
    tests = Path(__file__).parent
    callers: list[str] = []
    for path in sorted(tests.glob("test_*.py")):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(path.read_text())
        except SyntaxError:  # pragma: no cover — a broken sibling is not ours
            continue
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "main" and isinstance(n.func.value, ast.Name)
                    and n.func.value.id in {"R", "RWS", "run_weekly_serving"}):
                callers.append(f"{path.name}:{n.lineno}")
    assert callers, (
        "run_weekly_serving.main() now has NO executing caller at all — that is strictly worse "
        "than the narrow gap this clause records; restore one (NF-INC-0914).")
