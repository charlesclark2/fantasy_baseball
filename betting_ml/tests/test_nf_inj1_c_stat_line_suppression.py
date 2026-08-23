"""NF-INJ1-C — the impossible counting-stat line is WITHHELD on `/fantasy/nfl/projections-full`.

THE DEFECT (NF-INJ1, measured on the live board — not hypothetical). NF1.5's ordering step hands a
player a different player's point level and rescales the twelve stat columns to reach it while
leaving `proj_games` behind, so ~10 served rows (all QB) carry a per-game workload no NFL player has
ever recorded: Easton Stick at 153.4 pass attempts over 1.86 projected games = **82.7 per game**
against an all-time realized maximum of 45.4. `fpPpr` is SCORED from that line, so the points agree
with the line and disagree with the games — nothing is self-inconsistent in a way a schema or the
scorer can see, and every test in the repo was green.

The MODEL fix (NF-INJ2) ran and was REFUSED by its own pre-registered ordering gate, which fired the
Option-C trigger the PM had already recorded in `nf_inj1_diagnosis.md` §8.1(b). This suite is that
fallback's acceptance criteria as executable clauses. ⛔ Nothing here re-reads or relaxes NF-INJ2's
refusal (E2.1-r) — it implements the consequence the refusal itself triggered.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⭐ IT RUNS AGAINST A REAL CAPTURED `/projections-full` PAYLOAD
═══════════════════════════════════════════════════════════════════════════════════════════════════

`fixtures/nf_epic1_projection_rows.json` is real exporter output pulled from the live gated endpoint
(its generator is committed beside it), and it carries **7 genuinely violating QBs by name** — Case
Keenum, Easton Stick, Sam Howell among them — beside 233 in-scope rows that are fine. That matters
for two opposite reasons, and neither is satisfiable by a hand-written fixture:

  * a suite whose "violating" row is one the author typed proves the code matches the author's
    idea of the defect, not the defect (NF-C0e);
  * a suite with no CLEAN rows cannot catch the failure that actually hurts — suppression firing
    too widely on a paid surface. 233 of them here have to come through byte-identical.

⚠️ THE E2E FIXTURE IS NOT USABLE FOR THIS and the difference is worth knowing: the browser suite's
`…entitled.synthetic.json` is SCRAMBLED (`passAtt == passYds == rushAtt` on every row), which makes
**246 of its 784 in-scope rows violate** — 31%, entirely an artifact of the scrambling. Asserted
against it, "the suppression is narrow" would be measuring the fixture. The browser spec therefore
PLANTS its two rows explicitly (the NF-C9 pattern) and this suite carries the population claim.

RED-PROVEN: `uv run python betting_ml/tests/nf_inj1_c_red_proof.py`. Pure/offline (fast gate) —
reads committed fixtures and source, no DuckDB/S3/network.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from app.backend.services import projection_fields, stat_line_suppression as sup
from quant_sports_intel_models.football.nfl.fantasy import projection_coherence

_REPO = Path(__file__).resolve().parents[2]
_ROWS_JSON = Path(__file__).parent / "fixtures" / "nf_epic1_projection_rows.json"
_DIAGNOSIS_MD = (
    _REPO / "quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_inj1_diagnosis.md"
)
_SERVICE_PY = _REPO / "app/backend/services/stat_line_suppression.py"
_ROUTER_PY = _REPO / "app/backend/routers/fantasy.py"


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return json.loads(_ROWS_JSON.read_text())


@pytest.fixture(scope="module")
def payload(rows) -> dict:
    return {"season": 2026, "generated_at": "2026-08-21T05:23:33Z", "players": rows}


@pytest.fixture(scope="module")
def suppressed(payload) -> dict:
    return sup.suppress_projections_payload(payload)


def _violating_ids(rows) -> set[str]:
    """The recorded predicate, applied independently of the code under test."""
    return {v["id"] for r in rows for v in projection_coherence.row_violations(r)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The predicate is NF-INJ1's, and is not re-derived here
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_predicate_is_imported_from_nf_inj1_never_restated_in_the_backend():
    """⛔ THE ENVELOPE MAY HAVE EXACTLY ONE OWNER.

    A copy of `REALIZED_MAX_PER_GAME` under `app/backend/` would put the guard that PAGES about a
    violating row and the code that WITHHOLDS it under two owners — the repo's most-repeated defect
    class (INC-30's crontab, INC-36's deploy lock, INC-38's four callers, E9.61's two renderers of
    one name) — and the drift would be silent in both directions: a widened backend copy withholds
    nothing while the publish guard still pages, a narrowed one blanks stat lines nothing pages
    about.

    Checked as a numeric-literal scan over the module's AST rather than a grep for the constant's
    NAME, because the header DISCUSSES the envelope at length and a name-grep would match the prose
    that explains why the numbers are not here (the NF-C0e trap, where a docstring naming a
    forbidden thing false-matched the guard written to forbid it).
    """
    tree = ast.parse(_SERVICE_PY.read_text())
    banned = {
        round(float(v), 2)
        for env in projection_coherence.REALIZED_MAX_PER_GAME.values()
        for v in env.values()
    }
    assert banned, "the envelope is empty — this clause would pass on nothing"
    found = [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, float)
        and round(n.value, 2) in banned
    ]
    assert not found, (
        f"{_SERVICE_PY.name} contains envelope threshold(s) {found} as literals — the predicate "
        "must be IMPORTED from projection_coherence, never copied. See the module header."
    )


def test_the_recorded_predicate_is_cited_where_a_reader_will_look():
    """The spec's own acceptance criterion: cite the recorded source, do not invent a threshold.

    A reader meeting `row_is_impossible` has to be able to get from here to the measurement without
    guessing, and the diagnosis file is the thing that would go stale first.
    """
    src = _SERVICE_PY.read_text()
    assert "nf_inj1_diagnosis.md" in src, (
        "the service no longer cites NF-INJ1's recorded diagnosis — the threshold then reads as "
        "one this story chose"
    )
    assert _DIAGNOSIS_MD.is_file(), "the cited diagnosis file does not exist"
    assert "REALIZED_MAX_PER_GAME" in projection_coherence.__dict__ or hasattr(
        projection_coherence, "REALIZED_MAX_PER_GAME"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# What is withheld, and — the harder half — what is NOT
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_a_violating_row_loses_its_counting_stats_and_keeps_its_points_and_games(rows, suppressed):
    """⭐ THE PM's RULING, BOTH HALVES. "suppress the counting-stat line; points + expected games
    still render" — and the second half is not decoration: a drafter meeting a blank row learns
    nothing, while a drafter meeting a point total and a 1.9-game availability figure learns the
    thing that actually matters about Easton Stick."""
    violating = _violating_ids(rows)
    assert violating, "the fixture carries no violating row — every clause below would be vacuous"
    stat_fields = sup.counting_stat_fields()
    by_id = {r["id"]: r for r in rows if isinstance(r, dict)}
    seen = 0
    for row in suppressed["players"]:
        if row["id"] not in violating:
            continue
        seen += 1
        original = by_id[row["id"]]
        expected = sorted(k for k in stat_fields if k in original)
        assert row.get(sup.WITHHELD_KEY) == expected, (
            f"{row['name']}: the withheld marker does not name exactly the counting stats removed"
        )
        for key in expected:
            assert key not in row, f"{row['name']}: {key} survived suppression"
        # …and the three things that must SURVIVE.
        assert row.get("g") == original.get("g"), f"{row['name']}: expected games moved"
        for pts in ("fpPpr", "fpStd", "fpHalf"):
            assert row.get(pts) == original.get(pts), f"{row['name']}: {pts} moved"
    assert seen == len(violating), "not every violating row was reached"


def test_a_clean_row_is_byte_identical(rows, payload, suppressed):
    """⭐ THE FAILURE THAT WOULD ACTUALLY HURT. This is the PAID substrate; a predicate that fires
    one row too wide costs a member the data they bought, and it would look exactly like a working
    feature. 233 of the 240 in-scope rows here must come through untouched — asserted as JSON
    equality AND as object IDENTITY, because `suppress_row` returns the original object for a clean
    row precisely so this is true by construction rather than by careful key ordering."""
    violating = _violating_ids(rows)
    originals = {id(r): r for r in payload["players"]}
    clean = 0
    for before, after in zip(payload["players"], suppressed["players"]):
        if before["id"] in violating:
            continue
        clean += 1
        assert after is before, (
            f"{before['name']} is coherent and was rebuilt anyway — a clean row must be the SAME "
            "object, or 'byte-identical' is a claim about key ordering rather than a property"
        )
        assert sup.WITHHELD_KEY not in after
    assert clean > 200, f"only {clean} clean rows — the narrowness claim rests on too few"
    assert originals  # the payload was not emptied


def test_the_suppression_is_narrow_on_a_real_payload(rows, suppressed):
    """The population claim, on real exporter output: a handful of rows, all QB, and the count on
    the payload agrees with the independent read of the predicate."""
    violating = _violating_ids(rows)
    assert suppressed[sup.WITHHELD_COUNT_KEY] == len(violating)
    assert len(violating) / len(rows) < 0.05, (
        "more than 5% of a real payload lost its stat line — that is not the NF-INJ1 defect, it is "
        "a predicate misfiring on the paid surface"
    )
    positions = {r["pos"] for r in rows if r["id"] in violating}
    assert positions == {"QB"}, (
        f"violations reached {positions}. NF-INJ1 measured the defect as QB-only (structural: QB "
        "has a narrow per-game anchor AND the widest availability spread on a roster). A breach "
        "elsewhere is a finding, not a pass"
    )


def test_points_and_games_are_never_in_the_withheld_set():
    """Derived from the scorer's map, and the two DERIVED totals must not ride along.

    `PAID_PLAYER_FIELDS` is `STAT_FIELD.values() | {fpStd, fpHalf}` — reaching for the paid set
    instead of the stat set is the natural mistake, and it withholds exactly the numbers the PM
    ruled must still render."""
    fields = sup.counting_stat_fields()
    assert fields == frozenset(projection_fields.STAT_FIELD.values())
    for keep in ("fpPpr", "fpStd", "fpHalf", "g", "adp", "name", "pos"):
        assert keep not in fields, f"{keep} would be withheld — the PM's ruling keeps it"
    assert projection_fields.PAID_SCORING_FIELDS & fields == frozenset()


def test_a_new_scorable_stat_is_withheld_automatically(monkeypatch, rows):
    """⭐ THE SAFETY DIRECTION, INHERITED FROM NF-EPIC 1. A hand-written list would leave the NEXT
    stat the exporter adds VISIBLE on a violating row, with no code change and no failing test.
    Deriving from `STAT_FIELD` means teaching the scorer about a stat is what makes it withheld."""
    monkeypatch.setitem(projection_fields.STAT_FIELD, "brand_new_stat", "brandNewStat")
    victim = next(r for r in rows if projection_coherence.row_violations(r))
    patched = sup.suppress_row({**victim, "brandNewStat": 999.0})
    assert "brandNewStat" not in patched
    assert "brandNewStat" in patched[sup.WITHHELD_KEY]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ABSENT ≠ WITHHELD, and the marker must not leak the number
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_marker_carries_no_magnitude(rows, suppressed):
    """🚨 THE ONE THAT UNDOES THE WHOLE STORY IF IT IS WRONG.

    `row_violations` hands back `season_total`, `implied_per_game` and `times_over`, and every one
    of them reconstructs the withheld value: `implied_per_game × g` IS the season total, and so is
    `times_over × max_ever_per_game × g`. Publishing any of them out of helpfulness would leave the
    suppressed number one multiplication away on the payload whose purpose is to not carry it.
    Field NAMES only — asserted structurally (every element a string) so a future dict-shaped
    marker cannot smuggle a float back in.
    """
    violating = _violating_ids(rows)
    marked = [r for r in suppressed["players"] if r["id"] in violating]
    assert marked, "no marked row — this clause would pass on nothing"
    for row in marked:
        marker = row[sup.WITHHELD_KEY]
        assert isinstance(marker, list) and marker
        for element in marker:
            assert isinstance(element, str), (
                f"the withheld marker on {row['name']} carries a non-string {element!r} — a "
                "magnitude here reconstructs the value we just withheld"
            )
        blob = json.dumps(row)
        assert "implied_per_game" not in blob and "times_over" not in blob


def test_a_never_served_stat_is_distinguishable_from_a_withheld_one(rows, suppressed):
    """NF-FRESH2's discipline, at the FIELD level: the marker names what was REMOVED, never the
    whole vocabulary.

    ⚠️ MEASURED FIRST, AND THE MEASUREMENT CHANGES WHAT THIS CAN CLAIM. The exporter is fully
    DENSE — all 314 rows of the real captured payload carry all 53 scorable fields, so a QB row
    carries `fgAtt` and the nine points-allowed buckets at 0.0 rather than omitting them. Today,
    therefore, NOTHING on a served row is "never served", and the absent-vs-withheld distinction
    lives entirely at the ROW level — which is exactly why the marker exists and why reading a
    missing key as a refusal would be wrong the moment that density changes.

    So the clause is made in two parts: on the REAL row, the marker must equal what was present
    (below), and on a deliberately SPARSE row, a field the payload never carried must not be
    claimed as withheld. The second half would be vacuous against the fixture — writing it as if
    the fixture supplied it is how a guard ends up passing on nothing (NF1.7 (a)).
    """
    violating = _violating_ids(rows)
    row = next(r for r in suppressed["players"] if r["id"] in violating)
    marker = set(row[sup.WITHHELD_KEY])
    assert "passAtt" in marker, "the breaching stat itself is not named as withheld"
    assert marker == sup.counting_stat_fields(), (
        "on today's dense payload the marker should name every scorable field, since every one was "
        "present. If this fails, the exporter has become sparse — good, and the sparse half below "
        "is now the live half"
    )

    sparse = {"id": "s", "name": "Sparse Quarterback", "pos": "QB", "g": 1.5,
              "passAtt": 300.0, "passYds": 2000.0, "fpPpr": 40.0}
    patched = sup.suppress_row(sparse)
    assert patched is not sparse, "the sparse row does not violate — pick harsher numbers"
    named = set(patched[sup.WITHHELD_KEY])
    assert named == {"passAtt", "passYds"}, (
        f"the marker names {sorted(named - {'passAtt', 'passYds'})}, which this row never carried — "
        "claiming to withhold a stat that was never served is the same inversion as rendering a "
        "withheld stat as an honest absence, facing the other way"
    )
    assert "rec" not in patched and "rec" not in named


def test_the_count_is_emitted_even_when_nothing_was_withheld():
    """⭐ ZERO IS A MEASUREMENT; A MISSING KEY IS NOT.

    "0 rows were withheld" and "this build does not run the check" are different facts, and a key
    that appears only when something fired cannot tell them apart — the vacuous-pass shape
    (NF1.7 (a)) this whole story is an instance of. A reader comparing two payloads must be able to
    see that the check RAN."""
    clean = {"players": [{"id": "x", "name": "Coherent Quarterback", "pos": "QB", "g": 17.0,
                          "passAtt": 500.0, "passYds": 4000.0, "fpPpr": 300.0}]}
    out = sup.suppress_projections_payload(clean)
    assert out[sup.WITHHELD_COUNT_KEY] == 0
    assert out["players"][0] is clean["players"][0]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# It must not be able to damage the surfaces it does not own
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_it_never_mutates_its_input(payload, rows):
    """⛔ THE BLOB IS `_full_projections`'s MEMO, which `/nfl/my-teams` scores a saved league from.
    An in-place edit would turn a display patch into a change to a served board's numbers — the one
    thing the story promises not to do, and it would surface as a user's league quietly re-ranking
    some minutes after a page load (the TTL), which is close to undebuggable."""
    before = json.dumps(payload, sort_keys=True)
    sup.suppress_projections_payload(payload)
    sup.suppress_projections_payload(payload)
    assert json.dumps(payload, sort_keys=True) == before, (
        "suppress_projections_payload mutated the memoized projections blob"
    )
    assert any(projection_coherence.row_violations(r) for r in rows), (
        "the fixture stopped violating, so the mutation check above ran on a no-op"
    )


def test_only_the_paid_route_suppresses():
    """SCOPE, pinned on the router source. The public payload carries no stat line at all
    (NF-EPIC 1 strips it), so suppressing there would be inert; `/nfl/my-teams` consumes the SCORED
    output and must not see a suppressed line at all."""
    src = _ROUTER_PY.read_text()
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Attribute) and n.attr == "suppress_projections_payload"]
    assert len(calls) == 1, (
        f"suppress_projections_payload is called {len(calls)} times in the router — it belongs on "
        "`/nfl/projections-full` and nowhere else"
    )
    full = src.index("def nfl_projections_full")
    board = src.index("def nfl_board")
    at = src.index("suppress_projections_payload(")
    assert full < at < board, "the suppression call is not inside nfl_projections_full"


def test_a_malformed_row_costs_only_itself():
    """E9.49 — one bad row must never blank the collection on a serving read."""
    out = sup.suppress_projections_payload(
        {"players": [None, "junk", {"id": "ok", "pos": "QB", "g": 16.0, "passAtt": 500.0}]}
    )
    assert len(out["players"]) == 3
    assert out["players"][0] is None and out["players"][1] == "junk"
    assert out["players"][2]["passAtt"] == 500.0


def test_an_unevaluable_row_is_left_alone_not_blanked():
    """A row with no usable `g` cannot be judged. `row_violations` returns [] for it BY DESIGN
    (NF-INJ1 counts those separately rather than calling them clean) — and the serving choice here
    is to leave the line alone, because failing closed on an unevaluable row means a bug in a
    symptom patch for ten backup QBs can blank the paid substrate for 868 players. Recorded as a
    deliberate direction, not an oversight."""
    for g in (None, 0, 0.0):
        row = {"id": "u", "pos": "QB", "g": g, "passAtt": 500.0}
        assert sup.suppress_row(row) is row


def test_the_engine_import_is_lazy():
    """A module-scope import would put NF-INJ1's module on EVERY route's cold-start path for one
    endpoint's benefit — the exact defect the PERF audit measured in this Lambda (−21.8% once the
    transitive `snowflake.connector` → pandas import was lazied)."""
    for node in ast.parse(_SERVICE_PY.read_text()).body:   # module scope only
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "quant_sports_intel_models"
        ):
            pytest.fail("stat_line_suppression imports the model tree at MODULE scope")
        if isinstance(node, ast.Import):
            assert not any(a.name.startswith("quant_sports_intel_models") for a in node.names)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The copy — honest framing (the spec's third acceptance criterion)
# ══════════════════════════════════════════════════════════════════════════════════════════════

_CLAIM_COPY_TS = _REPO / "frontend/lib/fantasy-claim-copy.ts"

#: The three constants this story adds. Named explicitly rather than scanned for, so MOVING one out
#: of `fantasy-claim-copy.ts` (where the shared NF-TR1 governance screens every literal) fails here
#: instead of silently leaving it unscreened — the copy-drifts-to-an-ungoverned-file hole.
_WITHHELD_CONSTANTS = (
    "STAT_LINE_WITHHELD_LABEL",
    "STAT_LINE_WITHHELD_SR_LABEL",
    "STAT_LINE_WITHHELD_DETAIL",
)


def _withheld_copy() -> dict[str, str]:
    import re

    src = _CLAIM_COPY_TS.read_text()
    out: dict[str, str] = {}
    for name in _WITHHELD_CONSTANTS:
        m = re.search(rf"export const {name} =\s*\n?\s*\"((?:[^\"\\\\]|\\\\.)*)\"", src)
        assert m, f"{name} is not an exported string constant in fantasy-claim-copy.ts"
        out[name] = m.group(1)
    return out


def test_the_withheld_copy_lives_where_the_shared_governance_screens_it():
    """⭐ NON-VACUITY FOR EVERY CLAUSE BELOW, and a real anti-drift property in its own right.

    `test_nf_tr1_claim_copy.py` runs the export's `_CLAIM_DENYLIST` and the governance gate over
    every string literal in THIS FILE. A constant that drifts into a component (or into a new
    module) is silently unscreened, and the surface still renders. Binding the location is what
    makes "the copy passes the denylist" a standing property rather than a fact about today."""
    copy = _withheld_copy()
    assert len(copy) == len(_WITHHELD_CONSTANTS)
    for name, text in copy.items():
        assert text.strip(), f"{name} is empty — every clause below would pass on nothing"


def test_the_withheld_copy_passes_the_shared_claim_denylist():
    from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as ex

    for name, text in _withheld_copy().items():
        hits = [t for t in ex._CLAIM_DENYLIST if t in text.lower()]
        assert not hits, f"{name} contains overclaim(s) {hits}"


def test_the_withheld_copy_forecasts_nothing_about_the_player():
    """⛔ THE HAZARD SPECIFIC TO THIS REFUSAL. The suppression fires on rows whose expected-games
    figure is low, so a reader meets the em-dash next to "1.9 proj. games" — and copy that reached
    for ANY availability verb would read as a medical or usage forecast we have not made and do not
    make (`best_alpha = 0`). This copy is a statement about OUR line, never about him.

    The same phrase list NF-C9's browser spec holds over its own disclaimer, plus the durations a
    coherence refusal has even less business implying."""
    forecast = ("will miss", "injury risk", "is hurt", "sidelined", "out for", "expected back",
                "we expect him", "likely to", "should return", "at risk")
    duration = ("weeks", "rest of the season", "multi-week", "games out")
    for name, text in _withheld_copy().items():
        low = text.lower()
        for term in forecast:
            assert term not in low, f"{name} forecasts ({term!r}) — it must describe our line only"
        for term in duration:
            assert term not in low, f"{name} implies a duration ({term!r})"


def test_the_short_label_names_the_condition_not_an_adjustment_we_did_not_make():
    """⭐ PM RULING, 2026-08-23 (nf-inj1-c.yaml closeout, RULINGS Decision 2).

    NF-INJ1-C shipped the PM's default label verbatim: "stat detail withheld —
    availability-adjusted". That is not merely vague, it is INVERTED — it says we adjusted this
    line for availability, when the line is withheld PRECISELY BECAUSE it was not rescaled with the
    games (`_RAW_SCALE_COLS` moves the twelve stat columns and not `proj_games`; that decoupling is
    the NF1.5 defect). The retired label described the one thing that did not happen.

    ⚠️ ITS OWN REASON TO EXIST: every clause that predates it is satisfied word-for-word by the
    RETIRED string — the trigger's accessible name comes from `STAT_LINE_WITHHELD_SR_LABEL`, and
    "says it is withheld" is true of both — so the reword could have landed with a fully green suite
    and nothing measuring it. Kept as its OWN clause rather than folded into the one below, so the
    fixture that flips it cannot be refused by a different assertion first (NF-D17).
    """
    label = _withheld_copy()["STAT_LINE_WITHHELD_LABEL"].lower()
    assert "inconsistent with projected games" in label, (
        "the short label no longer names the CONDITION. A reader is then told a stat is withheld "
        "and not that our own line and our own projected games disagree, which is the entire reason"
    )
    assert "availability-adjusted" not in label, (
        "the retired wording is back. It is the one phrasing that makes a positive claim about a "
        "stat we are refusing to show, and it claims the opposite of what happened"
    )


def test_the_withheld_copy_says_what_it_is_and_what_survives():
    """The two things a reader has to be able to learn from the disclosure: that this is a
    WITHHOLDING (not a missing number, not a lock), and that the point total and games figure beside
    it are unaffected. ⚠️ Each asserted against copy in which the OTHER is satisfied — every clause
    reads the same string, so neither can hide the other's absence (NF-D17)."""
    copy = _withheld_copy()
    label, detail = copy["STAT_LINE_WITHHELD_LABEL"], copy["STAT_LINE_WITHHELD_DETAIL"]
    assert "withheld" in label.lower(), (
        "the short label no longer says the stat is WITHHELD — an em-dash with a neutral tooltip "
        "that does not use the word reads as a missing number, which is the whole inversion"
    )
    assert "withhold" in detail.lower() or "withheld" in detail.lower()
    for survives in ("points", "games"):
        assert survives in detail.lower(), (
            f"the detail no longer says his projected {survives} are unaffected — the reader then "
            "cannot tell how much of the row to distrust"
        )
    # 🔴 FOUND BY THE RED PROOF, and it was a real hole. The first cut screened only "membership"
    # and "subscri", so the deliberate break "Members see the full line for every other player."
    # — a textbook drift into the paywall's register — sailed straight through and the clause came
    # back GREEN. ⇒ screen the STEM, and anchor it at a word boundary so an innocent "remember"
    # cannot false-fire the way a bare substring scan would (the negation/substring-blindness class
    # that has fired on this repo's copy guards twice).
    import re as _re

    for stem in ("member", "subscri", "unlock", "upgrade", "paid plan"):
        assert not _re.search(rf"\b{stem}", detail.lower()), (
            f"the withheld copy has drifted into the LOCK's wording ({stem!r}) — this refusal is "
            "served to a member who has ALREADY paid for the stat line, and selling it to them "
            "again is the wrong story entirely"
        )
