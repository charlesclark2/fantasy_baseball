"""NCAAF-P3.3b — the ratings-update stamp: the contract, the owner, and the premise it corrects.

WHAT P3.3 MEASURED. The rating, its band and both ranks move only when the P1.2 posterior is
re-fit, so between fits a team can win by 26 while all four sit unchanged beside that win in its
own schedule. Every number is right and the PAGE still misleads, because a reader reads a rating
printed today as a rating computed today — and the footer's "built <date>" (the HOURLY serving
write) actively encourages that reading.

⭐⭐ THE PREMISE THIS STORY WAS SPECIFIED ON IS FALSE, AND THAT IS WHAT MOST OF THIS FILE GUARDS.
P3.3b was to derive "next update" from `NCAAF_ROLL_FORWARD_CRON`, on a claim recorded in #1081's
own commit message: "the P1.2 strength fit rolls forward weekly". Measured 2026-09-04, three ways
that agree:

  1. STRUCTURALLY IMPOSSIBLE — `team_strength_week` is not in `ROLL_FORWARD_SOURCES` and cannot be
     (`ingest/sources.py` asserts at import that every entry is a free CFBD source; the ratings
     table is a derived model output written by `run_team_strength`).
  2. STATED IN THREE PLACES — the roll-forward job's docstring, the snapshot job's, and
     `BOX_OPERATIONS.md §10`, all naming the P1.2 re-fit an OPERATOR step. `grep run_team_strength
     pipeline/` returns docstrings and no call.
  3. MEASURED ON THE LAKE, TWO-SIDED — `ncaaf/derived/team_strength_week` last committed
     2026-08-18T06:16:36Z (v67); `ncaaf/raw/games` and `ncaaf/raw/talent` last committed
     2026-08-31T13:00:51Z / 13:01:13Z (Monday 06:00 PT). The roll-forward FIRED and the ratings did
     not move: the chain is alive AND it does not touch them.

So the guards below are not only "does the stamp render" — the load-bearing ones refuse the WRONG
derivation by name, because the false claim is still sitting in the git history where the next
reader will find it.

RED-proven by `betting_ml/tests/ncaaf_p3_3b_red_proof.py` (baseline-pass / NOT-SELECTED /
unique-anchor controls).
"""
from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from app.backend.models import ncaaf as contract
from betting_ml.monitoring import ncaaf_ratings_vintage as vintage
from quant_sports_intel_models.football.ncaaf.serving import team_payloads

REPO = Path(__file__).resolve().parents[2]
COPY_TS = REPO / "frontend/lib/ncaaf-copy.ts"
STAMP_TSX = REPO / "frontend/components/ncaaf/ratings-vintage.tsx"
TEAM_TS = REPO / "frontend/lib/ncaaf-team.ts"
WRITER = REPO / "scripts/write_ncaaf_serving_store.py"
SOURCES = REPO / "quant_sports_intel_models/football/ncaaf/ingest/sources.py"

STAMP_FIELDS = ("ratings_as_of", "ratings_next_update")


def _executable_source(src: str) -> str:
    """`src` with every comment AND every docstring removed.

    ⚠️ WRITTEN BECAUSE IT BIT, IN THIS FILE, ON THE FIRST RUN. The mtime clause below forbids the
    token `LastModified`, and the module it scans EXPLAINS in its docstring that it never reads an
    S3 `LastModified` — so a comment-only strip failed on prose that says the opposite of the
    defect. That is the INC-38 "prose satisfies the guard" class in its trip direction, which is
    the friendlier one: the other direction is a guard a COMMENT can satisfy, and a strip that
    misses docstrings is vulnerable to both.
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


def _strength_rows(as_of_week: int = 1, games: int = 0) -> pd.DataFrame:
    return pd.DataFrame([{
        "team_id": 68, "season": 2026, "as_of_week": as_of_week, "games_in_window": games,
        "strength_margin": 3.09, "strength_margin_sd": 7.29,
        "model_version": "ncaaf_team_strength_v1", "league_base_points": 1.0,
        "home_field_advantage": 2.0, "residual_sigma": 16.0, "hyper_n_prior_seasons": 1,
    }])


# ── the served contract ──────────────────────────────────────────────────────────────────────

def test_both_halves_are_declared_on_the_contract():
    """E9.41: a field the response model does not declare is STRIPPED on serialize.

    That defect is invisible from the store — the value is correct in DynamoDB the whole time and
    simply never reaches a reader — which is exactly how `FeaturedYesterday.status` broke the
    Won/Lost colour for every settled pick without an error anywhere.
    """
    declared = contract.declared_field_names(contract.NcaafTeamStrength)
    for field in STAMP_FIELDS:
        assert field in declared, (
            f"{field} is not declared on NcaafTeamStrength — FastAPI will drop it on the way out "
            f"and the page will render a stated absence over a store that had the value")


def test_the_stamp_fields_carry_no_claim_token():
    """The served-contract screen, run over the new fields specifically.

    `assert_no_edge_claim_in_schema` walks every model, so this is belt-and-braces — but it is the
    clause that would fail first if a future rename reached for a word like `edge_as_of`.
    """
    contract.assert_no_edge_claim_in_schema()
    for field in STAMP_FIELDS:
        assert not any(tok in field for tok in contract.FORBIDDEN_PAYLOAD_TOKENS)


@pytest.mark.parametrize("strength_available", [True, False])
def test_the_stamp_survives_the_builder_on_both_block_branches(strength_available):
    """A page whose posterior could not be read still has a lake behind it.

    ⚠️ THE UNAVAILABLE BRANCH IS THE ONE THAT ROTS. It is a separate `return` in `build_strength`,
    so a field added to the available dict alone type-checks, validates, and is simply missing on
    the branch a reader meets during an outage — the two-returns-one-contract shape.
    """
    payloads = team_payloads.build_team_payloads(
        season=2026,
        strength=_strength_rows() if strength_available else None,
        team_dim=pd.DataFrame([{"team_id": 68, "season": 2026}]),
        ratings_as_of="2026-08-18T06:16:36.806000+00:00",
        ratings_next_update=None,
    )
    block = payloads[68]["strength"]
    assert block["status"] == ("available" if strength_available else "unavailable")
    assert block["ratings_as_of"] == "2026-08-18T06:16:36.806000+00:00"
    assert block["ratings_next_update"] is None


def test_the_vintage_is_not_derived_from_the_week_index_or_the_write_clock():
    """⛔ THE TWO WRONG SOURCES, refused by measurement rather than by comment.

    `as_of_week` is a WEEK INDEX (the contract says so in as many words) and `generated_at` is when
    THIS write ran — hourly, so it is precisely the number that makes a five-week-old rating look
    fresh. Either would render a completely plausible stamp.
    """
    payloads = team_payloads.build_team_payloads(
        season=2026, strength=_strength_rows(as_of_week=9),
        ratings_as_of="2026-08-18T06:16:36.806000+00:00")
    blob = payloads[68]
    assert blob["strength"]["ratings_as_of"] == "2026-08-18T06:16:36.806000+00:00"
    assert blob["strength"]["ratings_as_of"][:10] != blob["generated_at"][:10], (
        "the vintage equals the serving-write date — it is being read off the write clock")
    assert "9" not in blob["strength"]["ratings_as_of"][:4], "the vintage was built from a week index"


# ── the owner, and the premise it corrects ───────────────────────────────────────────────────

def test_no_schedule_is_registered_as_refreshing_the_ratings():
    """The MEASUREMENT, pinned so a future edit has to argue with it.

    ⛔ An entry here is a claim that the named schedule's JOB REWRITES `team_strength_week`. Nothing
    does today: the P1.2 re-fit is an operator laptop step. An empty registry is therefore a
    measured fact, and `next_ratings_update` returning None from it is the honest answer the
    surface renders as a stated absence.
    """
    assert vintage.RATINGS_REFRESH_SCHEDULES == (), (
        "a schedule was registered as refreshing the NCAAF ratings — verify its JOB actually "
        "writes ncaaf/derived/team_strength_week before trusting this, and update this clause "
        "with the evidence rather than deleting it")
    assert vintage.next_ratings_update() is None


def test_the_roll_forward_schedule_is_refused_by_name():
    """⭐ THE CLAUSE THIS WHOLE FILE EXISTS FOR.

    #1081's commit message states the P1.2 fit "rolls forward weekly", and that sentence is in the
    git history for good. The next reader who wires a "next update" half will reach for exactly
    that schedule, and every surface signal encourages them: it is weekly, it is Monday 06:00, it
    is named `sports_ncaaf_roll_forward_schedule`, and it genuinely refreshes NCAAF data. It just
    does not refresh THIS artifact.
    """
    assert "sports_ncaaf_roll_forward_schedule" not in vintage.RATINGS_REFRESH_SCHEDULES, (
        "the roll-forward schedule was registered as refreshing the ratings. It does not: its job "
        "ingests ROLL_FORWARD_SOURCES and rebuilds the dbt marts, and `team_strength_week` is "
        "neither. Measured 2026-08-31 — it fired and the ratings' Delta commit did not move.")
    # The structural half, read off the source of truth rather than restated: a derived model
    # output cannot enter that list, because every member is asserted to be a free CFBD source.
    src = SOURCES.read_text()
    listed = re.search(r"ROLL_FORWARD_SOURCES = \[(.*?)\]", src, re.S)
    assert listed, "ROLL_FORWARD_SOURCES moved — re-anchor this clause"
    assert "team_strength_week" not in listed.group(1)
    assert 'SOURCES[n].tier == "cfbd"' in src, (
        "the registry-integrity assertion that makes a derived table structurally ineligible for "
        "the roll-forward has gone — the premise this story corrects could silently become true")


def test_the_cron_arithmetic_resolves_a_real_next_fire():
    """⛔ NON-VACUITY, and it must not need `pipeline` to be it.

    With the registry empty by measurement, every clause above is satisfied by a function that
    returns None unconditionally — so the resolution would be untested code the day someone fills
    the registry in. This drives the OTHER arm through the PURE half, which takes a cron string, so
    the fast gate can run it without `pipeline` package state (E11.23).

    ⚠️ The cron is the roll-forward's, used here ONLY as a well-known weekly Monday 06:00 PT
    expression to exercise the arithmetic. That is not a claim that it refreshes the ratings — the
    clause below refuses exactly that, and it is why this one asserts nothing about the registry.
    """
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    got = vintage.next_fire("0 6 * 2-12,1 1", "America/Los_Angeles", now)
    assert got > now, "the next fire is not in the future"
    assert got - now < timedelta(days=8), "a weekly cron resolved more than a week out"
    assert got.weekday() == 0, f"expected a Monday fire, got {got.isoformat()}"
    assert got.tzinfo is not None and got.utcoffset() == timedelta(0), "not returned as UTC"


def test_the_schedule_lookup_reads_the_live_definition_rather_than_a_copied_cron():
    """The cadence has ONE owner: the `ScheduleDefinition`. A cron re-declared here would be the
    INC-30/36/38 shape (one logical thing, two execution owners) — the very class this module is a
    correction for.

    Guarded rather than unconditional: this is the one clause that must import `pipeline`, whose
    package state a fast-gate run does not have (E11.23). A SKIP is loud about why.
    """
    pytest.importorskip("pipeline", reason="pipeline package state absent (fast gate / worktree)")
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    got = vintage.next_ratings_update(now, schedules=("sports_ncaaf_roll_forward_schedule",))
    assert got is not None and got.weekday() == 0
    # It agrees with the pure arm driven by the cron the schedule actually declares — which is what
    # proves the lookup read the definition rather than something that merely looks like it.
    assert got == vintage.next_fire("0 6 * 2-12,1 1", "America/Los_Angeles", now)


def test_an_unknown_schedule_name_raises_rather_than_silently_resolving_to_none():
    """A stale registry entry must be LOUD. Returning None would render a stated absence — i.e. the
    same output as the correct empty-registry answer — so a typo would look exactly like the
    measured truth (NF1.7(a): a check that could not run is not a check that passed).
    """
    pytest.importorskip("pipeline", reason="pipeline package state absent (fast gate / worktree)")
    with pytest.raises(KeyError, match="no Dagster schedule named"):
        vintage.next_ratings_update(schedules=("sports_ncaaf_no_such_schedule",))


def test_the_vintage_read_never_raises_and_reports_an_unreadable_lake_as_none():
    """ALERT tier: an unreadable lake must cost the page its STAMP, never its ratings."""
    assert vintage.read_ratings_vintage(local_root="/nonexistent/lake/root") is None


def test_the_vintage_is_read_from_the_delta_log_not_an_object_mtime():
    """INC-41, as a source invariant rather than a comment.

    An S3 `LastModified` is refreshed by any server-side rewrite that changes no data, and
    `aws s3 ls` prints SHELL-LOCAL time — both read GREEN straight through the 19-day NF-FRESH1
    outage. The read therefore delegates to `sports_delta_freshness`, which owns the commit read
    AND the epoch-milliseconds-or-datetime ambiguity delta-rs has shipped both ways.
    """
    src = (REPO / "betting_ml/monitoring/ncaaf_ratings_vintage.py").read_text()
    code = _executable_source(src)
    assert "sports_delta_freshness" in code, "the vintage read forked away from the shared owner"
    for banned in ("LastModified", "last_modified", "getmtime", "st_mtime"):
        assert banned not in code, f"the vintage is being read from an mtime ({banned}) — INC-41"


def test_the_writer_passes_both_halves_and_degrades_rather_than_failing():
    """The serving write is HALT-tier; the stamp is not. A vintage read that threw and was not
    caught would take the whole NCAAF publish down for a decoration.
    """
    src = WRITER.read_text()
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    for field in STAMP_FIELDS:
        assert re.search(rf"{field}=stamp\[", code), (
            f"the writer does not pass {field} into build_team_payloads")
    assert "ratings_vintage_fields" in code
    assert re.search(r"except Exception[^\n]*\n[^\n]*log\.warning", code), (
        "the vintage read is not wrapped — a lake blip would fail a HALT-tier serving write")


# ── the surface ──────────────────────────────────────────────────────────────────────────────

def test_the_stamp_copy_contains_no_date_and_no_cadence_sentence():
    """⛔ Rule 1 of `ncaaf-copy.ts`: no measured figure in the copy file.

    A cadence written as prose ("updated Monday mornings") is right on the day it is typed and
    wrong the first time the cadence, the season or the premise moves — which is what happened
    here BEFORE a line was written. Both halves are read off the payload; nothing in the copy may
    name a day, a month or a date.
    """
    src = COPY_TS.read_text()
    block = src[src.index("NCAAF-P3.3b"):]
    literals = re.findall(r'"([^"]*)"', block)
    assert literals, "the P3.3b copy block has no string literals — re-anchor this clause"
    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    for text in literals:
        low = text.lower()
        assert not re.search(r"\d{4}-\d{2}-\d{2}", text), f"a date literal in copy: {text!r}"
        for day in weekdays:
            assert day not in low, f"the copy names a weekday ({day!r}) instead of reading a date"
        for promise in ("will change", "will move", "guaranteed"):
            assert promise not in low, f"the copy promises movement: {text!r}"


def test_the_stamp_component_reads_the_payload_and_hardcodes_nothing():
    src = STAMP_TSX.read_text()
    assert not re.search(r"\d{4}-\d{2}-\d{2}", src), "a date literal in the stamp component"
    assert "new Date(" not in src, (
        "the stamp reaches for the client clock — an unread artifact must render a stated absence, "
        "never today's date")
    assert "ratingsStamp(strength)" in src, "the stamp is not derived from its own prop"


def test_the_two_absences_render_as_two_different_things():
    """NF-C6b: "we could not read when" and "there is no next one" are different facts, and a
    surface that renders them identically makes every recurrence re-investigate from scratch.
    """
    src = STAMP_TSX.read_text()
    for testid in ("ncaaf-ratings-as-of-absent", "ncaaf-ratings-next-update-absent"):
        assert f'data-testid="{testid}"' in src, f"{testid} is not rendered"
    assert "RATINGS_AS_OF_UNAVAILABLE" in src and "RATINGS_NEXT_UPDATE_UNSCHEDULED" in src


def test_the_stamp_has_exactly_one_owner_on_the_frontend():
    """⭐ ONE COMPONENT, however many surfaces print a rating.

    Only the team page renders `strength_margin` today (the game cards and futures board carry the
    field in their types and print neither), so this has one caller. The clause exists for the
    SECOND one: a surface that re-worded the fact rather than importing it would be two rule sets
    for one statement (E9.61), and the drift would be invisible until a reader saw both.
    """
    tsx = list((REPO / "frontend/components").rglob("*.tsx"))
    renderers = [p for p in tsx if "<NcaafRatingsVintage" in p.read_text()]
    assert [p.name for p in renderers] == ["team-strength.tsx"], (
        f"unexpected stamp renderers: {[p.name for p in renderers]}")
    # And nobody re-implements it: the copy constants may be imported ONLY by the component.
    for path in tsx:
        if path.name == "ratings-vintage.tsx":
            continue
        assert "RATINGS_AS_OF_PREFIX" not in path.read_text(), (
            f"{path.name} renders the stamp's wording itself instead of importing the component")


def test_the_derivation_has_one_owner_and_validates_before_slicing():
    """`isoDateOf` is the single place a served instant becomes a printed day.

    ⚠️ A SLICE, NOT A `Date`: `toLocaleDateString` renders in the runtime's zone, so server and
    browser can disagree and Next hydration mismatches — and a vintage shifted by a day either side
    of midnight buys nothing. The validation is what stops a malformed instant printing as a
    truncated fragment that still looks like a date.
    """
    src = TEAM_TS.read_text()
    tree = ast_like_functions = re.findall(r"export function (\w+)", src)
    assert "isoDateOf" in ast_like_functions and "ratingsStamp" in ast_like_functions
    body = src[src.index("export function isoDateOf"):src.index("export function ratingsStamp")]
    assert "toLocaleDateString" not in body, "the vintage is formatted in the runtime's timezone"
    assert re.search(r"\\d\{4\}-\\d\{2\}-\\d\{2\}", body) or r"\d{4}-\d{2}-\d{2}" in body, (
        "the date is sliced without validating its shape — a malformed instant would print as a "
        "fragment that still reads like a date")
    del tree


def test_the_fixtures_cover_both_arms_of_the_stamp():
    """⛔ NON-VACUITY OF THE E2E. The "renders a real vintage" clause and the "states the absence"
    clause are only worth anything if some fixture reaches each. Both captures predate the Phase-A
    deploy (so neither carries the fields), and the generated fixture carries the vintage.
    """
    import json
    api = REPO / "frontend/e2e/fixtures/api"
    captures = [json.loads((api / f"ncaaf-team-{t}.json").read_text()) for t in (68, 2449)]
    populated = json.loads((api / "ncaaf-team-populated.synthetic.json").read_text())

    for blob in captures:
        assert blob["strength"].get("ratings_as_of") is None, (
            "a capture has acquired a vintage — the ABSENCE arm now has no fixture. Re-anchor it "
            "onto a transform-stripped payload; do not weaken the clause.")
    assert populated["strength"]["ratings_as_of"], "the PRESENT arm has no fixture"
    assert populated["strength"]["ratings_next_update"] is None, (
        "the generated fixture invented a next update — production emits none")
    # The played/unplayed contrast the pair exists for, so the stamp is proven on both states.
    completed = sorted(b["schedule"]["n_completed"] for b in captures)
    assert completed[0] == 0 and completed[-1] > 0, (
        "the capture pair lost its played/unplayed contrast")
    # And the re-capture's own point: standings now exist on production bytes.
    for blob in captures:
        assert blob["strength"]["standing_fbs"], (
            "the re-captured payload carries no standing — re-capture, do not hand-edit")
