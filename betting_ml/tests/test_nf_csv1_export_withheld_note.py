"""NF-CSV1 — the exported board CSV STATES what it withholds, in the file.

THE GAP (NF-RATE1 closeout ruling ①). NF-RATE1 gave the full-season rate three render states and
carried the suppression into the CSV export, where a withheld rate is correctly written as an EMPTY
CELL. On the page that emptiness is a tappable em-dash with a disclosure behind it. In the exported
file it is a blank, and nothing anywhere in the file says why — so the one surface a paying reader
actually works from was the one that explained nothing. A blank in a spreadsheet reads as "we have
nothing for this player", which is the E9.56c inversion this family exists to prevent, arriving
through the surface that leaves the popover behind.

THE SHAPE (ruled by the PM, not chosen here): a NOTE ROW appended to the file — not a README in a
zip, not a `title=` on the Export button, both of which leave the file itself silent. The header
stays row 1, the data columns are untouched, and the note trails the data so header-first parsers
and index-based row readers keep working.

WHAT THIS SUITE IS AND IS NOT. Source inspection over the frontend, plus a behavioural read of the
assembled note. It cannot see a downloaded file — `frontend/e2e/specs/fantasy-board-flows.spec.ts`
(the row-count contract, both directions) and `frontend/e2e/specs/full-season-rate.spec.ts` (the
note's rendered bytes) do that, by actually downloading one. Neither substitutes for the other.

RED PROOF: `betting_ml/tests/nf_csv1_red_proof.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

COPY = "lib/fantasy-claim-copy.ts"
OWNER = "lib/fantasy.ts"
SHARED = "components/fantasy/shared.tsx"
EXPORTER = "components/fantasy/rankings-board.tsx"
CSV_READER = "e2e/support/exported-csv.ts"
CONTRACT_SPEC = "e2e/specs/fantasy-board-flows.spec.ts"
COPY_SPEC = "e2e/specs/full-season-rate.spec.ts"


def _raw(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def _code(rel: str) -> str:
    """Frontend source with comments stripped.

    ⚠️ LOAD-BEARING HERE IN PARTICULAR (the INC-38 rule). This story's own explanatory comments name
    every symbol these clauses look for — `csvWithheldNote`, `CSV_WITHHELD_NOTE`,
    `fullSeasonRateDisplay`, even the phrase "cannot tell the two apart" — so a clause run over raw
    source would be satisfied by the prose describing the code while the code itself was deleted.
    Line comments go first so a `//` inside a block comment cannot leave a dangling `*/`."""
    text = _raw(rel)
    text = "\n".join(re.sub(r"//.*$", "", ln) for ln in text.splitlines())
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _note_parts() -> dict[str, str]:
    """`CSV_WITHHELD_NOTE`'s three parts, parsed out of the TypeScript.

    ⛔ NOT RE-DECLARED HERE. A Python copy of the wording would be a second owner of the very copy
    this story routes through one module, and it would go on agreeing with itself after the shipped
    string moved (`test_nf_rate1_full_season_rate_suppression.py` parses the envelope for the same
    reason). Parsing keeps every assertion pointed at what actually ships."""
    code = _code(COPY)
    m = re.search(r"export const CSV_WITHHELD_NOTE = \{(?P<body>.*?)\n\} as const", code, re.S)
    assert m, "CSV_WITHHELD_NOTE is not exported from the governed copy module"
    body = m.group("body")
    parts = {
        "lead": re.search(r'lead:\s*\n?\s*"((?:[^"\\]|\\.)*)"', body),
        "trailer": re.search(r'trailer:\s*\n?\s*"((?:[^"\\]|\\.)*)"', body),
    }
    assert all(parts.values()), f"CSV_WITHHELD_NOTE is missing a part: {parts}"
    out = {k: v.group(1) for k, v in parts.items() if v}
    out.update(_clauses())
    return out


def _clauses() -> dict[str, str]:
    """The per-class clauses, keyed by class id, parsed out of `CSV_WITHHELD_NOTE.clause`."""
    code = _code(COPY)
    m = re.search(r"export const CSV_WITHHELD_NOTE = \{.*?clause:\s*\{(?P<body>.*?)\n  \},", code, re.S)
    assert m, "CSV_WITHHELD_NOTE has no clause map"
    pairs = re.findall(r'"([a-z0-9-]+)":\s*\n?\s*"((?:[^"\\]|\\.)*)"', m.group("body"))
    assert pairs, "the clause map parsed as EMPTY — a guard over an empty map passes on nothing"
    return {f"clause:{k}": v for k, v in pairs}


def _registered_classes() -> list[str]:
    m = re.search(
        r"export const CSV_WITHHELD_CLASSES: readonly CsvWithheldClass\[\] = \[(?P<body>[^\]]*)\]",
        _code(COPY),
    )
    assert m, "CSV_WITHHELD_CLASSES is not exported"
    found = re.findall(r'"([a-z0-9-]+)"', m.group("body"))
    assert found, "the class registry parsed as EMPTY — every clause below would pass on nothing"
    return found


def _assembled_note() -> str:
    """The note as `csvWithheldNote` assembles it for every registered class, in registry order."""
    parts = _note_parts()
    return " ".join(
        [parts["lead"], *(parts[f"clause:{c}"] for c in _registered_classes()), parts["trailer"]]
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The copy — governed, screened, single-line, and honest about what a blank means
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_note_copy_lives_in_the_governed_module_and_nowhere_else():
    """Every claim-bearing string on these surfaces goes through `fantasy-claim-copy.ts`, which is
    what the denylist and every copy clause screen. A sentence typed into a component is a sentence
    nothing screens — and the note is a published claim that happens to travel in a file."""
    copy_src = _code(COPY)
    for const in ("CSV_WITHHELD_NOTE", "CSV_WITHHELD_CLASSES", "csvWithheldNote"):
        assert re.search(rf"export (const|function|type) {const}\b", copy_src), (
            f"{const} is not exported from the governed copy module"
        )
    # ⚠️ ABSENCE OF THE PROSE, not merely presence of the constant. A component that imports the
    # constant AND types its own sentence beside it satisfies a presence-only clause (the NF-C0e /
    # freemium lesson), and the typed sentence is the one nothing screens.
    #
    # ⚠️ THE PROBE IS A SHORT PREFIX, and the length was MEASURED rather than picked. The first cut
    # used 60 characters, which runs one character PAST the lead's opening sentence — so an inline
    # copy of exactly that sentence (the most likely way this defect actually arrives) did not
    # contain the probe and the clause stayed GREEN on it. The red proof caught it. A prefix short
    # enough to sit inside one sentence is what makes the clause bite; longer is not stricter.
    parts = _note_parts()
    for rel in (EXPORTER, SHARED, OWNER):
        code = _code(rel)
        for name, text in parts.items():
            probe = text[:40]
            assert len(probe) == 40, f"CSV_WITHHELD_NOTE.{name} is too short to probe for"
            assert probe.lower() not in code.lower(), (
                f"{rel} writes the note's {name} wording inline instead of importing it"
            )


def test_every_part_of_the_note_is_a_single_line():
    """⚠️ A NEWLINE ANYWHERE IN THIS COPY BREAKS THE FILE'S ROW COUNT. `downloadCsv`'s escaper wraps
    any cell containing `\\n` in quotes, which is legal CSV and produces a MULTI-LINE FIELD — so the
    note would occupy two physical lines, the row-count contract in the E2E would count one of them
    as a data row, and every line-counting reader of this file would be off by one. It is the kind
    of thing a copy edit does without noticing, so it is pinned rather than trusted."""
    for name, text in _note_parts().items():
        assert "\n" not in text and "\\n" not in text, (
            f"CSV_WITHHELD_NOTE.{name} contains a newline — it would export as a multi-line field"
        )
        assert text.strip() == text and text, f"CSV_WITHHELD_NOTE.{name} is blank or padded"


def test_the_note_makes_no_forecast_and_names_the_condition_a_reader_can_check():
    """⛔ THE SAME BAR THE ON-PAGE DISCLOSURE IS HELD TO. This says nothing about a player, his
    health, his role or his season — it is a statement about OUR OWN arithmetic. `best_alpha = 0`.

    ⚠️ AND IT MUST KEEP NAMING WHY. "a value is withheld" alone tells a reader nothing they could
    check; the checkable part is that the implied pace is above what football has actually done,
    which is verifiable against the very file it rides in (`expected_pts` and `expected_games` are
    both in it). A future trim to a bare "withheld" loses exactly that."""
    note = _assembled_note().lower()
    for banned in ("expected to miss", "will miss", "is injured", "injury", "injured"):
        assert banned not in note, f"the exported note makes a forecast: {banned!r}"
    # The overclaim denylist, mirrored from the browser's copy of it.
    denylist = re.findall(r'^\s*"([^"]+)",', _raw("e2e/support/claim-denylist.ts"), re.M)
    assert len(denylist) > 10, "the denylist parsed as near-empty — this clause would pass on nothing"
    assert [t for t in denylist if t in note] == [], "the exported note carries an overclaim"
    assert "above any season a real player has posted" in note, (
        "the note no longer names the condition a reader can check for themselves"
    )


def test_the_note_does_not_claim_that_every_blank_cell_is_a_withholding():
    """⚠️⚠️ THE HONESTY CLAUSE, AND THE ONE THIS STORY IS MOST EXPOSED TO. `fullSeasonRateCsv`
    returns `null` for the `unavailable` state as well as for `withheld`, so the SAME empty cell has
    two entirely different meanings and the file cannot tell them apart — a fact the owner's own
    docstring records. A note reading "a blank in this column is a number we are withholding" would
    therefore be FALSE about the three rows in the served board that simply have no expected-games
    figure, and would make the file dishonest in the other direction from the gap this closes.

    Measured on `fantasy-nfl-board-full_ppr-12-2026-free.json` (858 rows): 0 withheld, 3
    unavailable — i.e. the misleading reading is not hypothetical, it is what the served board would
    produce today."""
    note = _assembled_note().lower()
    assert "cannot tell the two apart" in note, (
        "the note does not say the file cannot separate a withheld cell from an absent one"
    )
    assert "absence rather than a withholding" in note, (
        "the note does not name the OTHER reason a cell in this column is blank"
    )


def test_the_note_points_at_the_surface_that_carries_the_per_row_disclosure():
    """The file cannot say WHICH rows; the page can, and does (a withheld cell is a tappable dotted
    em-dash, an unavailable one is a plain one). A note that stated a refusal without saying where
    the per-row answer lives leaves the reader with a fact and no way to act on it."""
    trailer = _note_parts()["trailer"].lower()
    label = re.search(
        r'export const FULL_SEASON_RATE_LABEL = "([^"]+)"', _code(COPY)
    )
    assert label, "FULL_SEASON_RATE_LABEL is not exported"
    assert label.group(1).lower() in trailer, (
        "the note does not name the on-page column that carries the full disclosure"
    )
    assert "site" in trailer, "the note does not tell the reader the disclosure is on the site"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The registry — one clause per class, and only classes that reach THIS export
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_every_registered_class_has_a_clause_and_every_clause_a_class():
    """AC: the note "enumerates EACH withheld class present". That is only true if the registry and
    the clause map are the same set — a registered class with no clause would silently contribute
    nothing (a file withholding two things saying it withholds one), and a clause with no registered
    class is dead copy nothing screens against a real file."""
    registered = set(_registered_classes())
    clauses = {k.split(":", 1)[1] for k in _clauses()}
    assert registered == clauses, (
        f"the class registry and the clause map disagree: registered-only={registered - clauses}, "
        f"clause-only={clauses - registered}"
    )
    union = re.search(r"export type CsvWithheldClass = (?P<u>[^\n]+)", _code(COPY))
    assert union, "CsvWithheldClass is not exported"
    declared = set(re.findall(r'"([a-z0-9-]+)"', union.group("u")))
    assert declared == registered, (
        f"the CsvWithheldClass union and the registry disagree: {declared} vs {registered}"
    )


def test_the_registry_holds_only_classes_that_can_reach_this_export():
    """🔎 THE CHECK THE ACCEPTANCE CRITERION ASKS FOR BY NAME, MECHANISED RATHER THAN ASSERTED IN
    PROSE: does NF-INJ1-C's stat-line withholding reach any column of this file?

    It does not, and the three facts that make that true are each pinned here, because any one of
    them changing is what would make the note incomplete:

      1. the rankings board is the ONLY `downloadCsv` caller in the app, so this is the only
         exported file that could carry a stat-line column;
      2. it does not read `statLineWithheld` — the per-row marker NF-INJ1-C renders from;
      3. its header list carries no stat-line column for that marker to apply to.

    ⚠️ If a stat column is ever added to this export, (3) fails here and the registry gains a
    member — which is the point: the incompleteness surfaces as a red test rather than as a note
    that quietly stopped enumerating everything."""
    callers = sorted(
        str(p.relative_to(_FRONTEND))
        for p in _FRONTEND.rglob("*.tsx")
        if "downloadCsv(" in _code(str(p.relative_to(_FRONTEND)))
    ) + sorted(
        str(p.relative_to(_FRONTEND))
        for p in _FRONTEND.rglob("*.ts")
        if not str(p).endswith(".d.ts") and "downloadCsv(" in _code(str(p.relative_to(_FRONTEND)))
    )
    assert callers, "no downloadCsv call site found — this clause would pass on nothing"
    assert set(callers) <= {EXPORTER, SHARED}, (
        f"a second CSV export exists ({callers}) and this story's note reaches only {EXPORTER} — "
        f"the new file's withheld classes have not been enumerated"
    )

    exporter = _code(EXPORTER)
    assert "statLineWithheld" not in exporter, (
        "the export now reads the NF-INJ1-C stat-line marker — that withheld class reaches this "
        "file and the note must name it"
    )
    headers = re.search(r'\["rank", "tier", "player".*?\]', exporter, re.S)
    assert headers, "the export's header list could not be located"
    # The NF-INJ1-C markers are per-STAT keys; none of them is an exported column today.
    for stat in ("pass_", "rush_", "rec_", "targets", "carries", "attempts", "completions"):
        assert stat not in headers.group(0), (
            f"the export now carries a stat-line column ({stat!r}); re-run the NF-INJ1-C reach "
            f"check and register that class"
        )
    assert _registered_classes() == ["full-season-rate"], (
        "the registry no longer matches the measured reach — re-derive it rather than editing it"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Conditional on a WITHHELD ROW, never on an empty cell
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_export_keys_the_note_on_the_owner_not_on_an_empty_cell():
    """⛔⛔ THE DEFECT THIS CLAUSE EXISTS FOR, and it is the natural way to write the feature. The
    obvious trigger is "did any cell come out empty?" — `fullSeasonRateCsv(...) == null` — and it is
    WRONG, because that helper returns `null` for the `unavailable` state too. Keyed that way, the
    served board (3 rows with no games figure, 0 withheld) exports a note claiming a withholding it
    does not contain: a false statement about the file, produced by a feature added for honesty.

    The correct predicate reads the owner's `kind`, which separates the two — and reading it through
    `fullSeasonRateDisplay` also keeps the rule single-owned (NF-RATE1)."""
    exporter = _code(EXPORTER)
    body = exporter[exporter.index("const exportCsv"):]
    body = body[: body.index("\n  }")]
    assert 'fullSeasonRateDisplay(' in body and '=== "withheld"' in body, (
        "the export does not decide the note by asking the owner whether a row is WITHHELD"
    )
    assert not re.search(r"fullSeasonRateCsv\([^)]*\)\s*==?=?\s*null", body), (
        "the note is keyed on an EMPTY CELL — which is also what an unavailable row produces, so "
        "the note would fire on a file that withholds nothing"
    )
    assert "csvWithheldNote(" in body, "the export does not build its note through the copy module"
    # ...and the argument is the computed set, not a literal — a hard-coded list would emit the note
    # on every export, which is the same false claim by a shorter route.
    assert re.search(r"csvWithheldNote\(\s*withheldClasses\s*\)", body), (
        "the note's class list is not the set computed from this file's rows"
    )


def test_the_note_is_absent_rather_than_empty_when_nothing_is_withheld():
    """"No withheld cells ⇒ the file is byte-identical to today's" is the acceptance criterion, and
    it fails on an empty-string note as surely as on a wrong one: an empty note appended as a row
    still adds a line to EVERY export. So the builder returns `null`, and `downloadCsv` treats a
    falsy note as no row at all rather than as a row of blanks."""
    copy_src = _code(COPY)
    fn = copy_src[copy_src.index("export function csvWithheldNote"):]
    fn = fn[: fn.index("\n}")]
    assert re.search(r"if \(listed\.length === 0\) return null", fn), (
        "csvWithheldNote does not return null for a file with nothing withheld"
    )
    shared = _code(SHARED)
    dl = shared[shared.index("export function downloadCsv"):]
    dl = dl[: dl.index("\n}")]
    assert re.search(r"if \(note\) \{", dl), (
        "downloadCsv appends the note row unconditionally — an export with nothing to disclose "
        "would gain a line"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Where the row lands: header row 1, note last, data columns untouched
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_note_row_is_appended_after_the_data_and_keeps_the_header_arity():
    """The three machine-readability properties, all owned by `downloadCsv` rather than by the call
    site, because each is a property of the FILE:

      · the header is still built first, so it is still row 1;
      · the note is PUSHED onto the line list after the data rows are spread into it;
      · the row is `[note, ...nulls]` sized to the header, so a column reader sees a row of blanks
        rather than a short row.
    """
    shared = _code(SHARED)
    dl = shared[shared.index("export function downloadCsv"):]
    dl = dl[: dl.index("\n}")]
    assert re.search(r"const lines = \[\s*headers\.map\(esc\)", dl), (
        "the header is no longer the first line of the file"
    )
    # The note is appended AFTER the data — `push`, onto a list the rows are already in.
    assert dl.index("...rows.map") < dl.index("lines.push("), (
        "the note row is written before the data rows — a reader slicing rows by index would take "
        "it as data, and a header-first parser could take it as the header"
    )
    assert re.search(
        r"lines\.push\(\s*\[note, \.\.\.Array\(Math\.max\(headers\.length - 1, 0\)\)\.fill\(null\)\]",
        dl,
    ), (
        "the note row does not carry the header's arity with only its first cell populated"
    )
    assert "note?: string | null" in dl, "downloadCsv's note parameter is not optional/nullable"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The contract, and the E2E that reads the actual bytes
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_row_count_contract_is_exact_and_two_sided():
    """AC: the row-count assertion is "UPDATED, not weakened … never a >= or a tolerance", and it
    must fail BOTH ways — a note on a file with nothing withheld, and a withheld cell with no note.

    ⚠️ READ STRUCTURALLY. Both directions live in the same describe block over the same
    `readExportedCsv` split; a clause that merely looked for the string "noteLines" would be
    satisfied by one of them."""
    spec = _raw(CONTRACT_SPEC)
    assert "readExportedCsv(" in spec, "the contract no longer reads the file through one splitter"
    assert re.search(r"expect\(\s*dataLines\.length,", spec), (
        "the contract no longer counts DATA rows separately from the note"
    )
    # Direction 1: nothing withheld ⇒ no note.
    assert re.search(r"expect\(\s*noteLines,[^)]*\)[\s\S]{0,400}?\.toEqual\(\[\]\)", spec), (
        "the contract does not assert that a board withholding nothing exports NO note row"
    )
    # Direction 2: something withheld ⇒ exactly one.
    assert re.search(r"expect\(\s*noteLines\.length,[\s\S]{0,300}?\.toBe\(1\)", spec), (
        "the contract does not assert that a withheld cell exports EXACTLY ONE note row"
    )
    # ⛔ AND NEITHER SIDE IS A TOLERANCE. A `>=` on a row count is how "the export dropped rows"
    # stops being catchable, which is the defect the original clause existed for.
    # ⚠️ SCOPED TO THE EXPORT DESCRIBE, not to the rest of the file. Other blocks in this spec use
    # `toBeGreaterThan` legitimately (a filter must leave SOME rows), and a whole-file scan would
    # fail on them — a guard that fires on unrelated code is one that gets loosened.
    start = spec.index('test.describe("exporting the board"')
    end = spec.index("test.describe(", start + 1)
    window = spec[start:end]
    assert "noteLines" in window, "the export describe was sliced wrong — this clause reads nothing"
    for loose in ("toBeGreaterThanOrEqual", "toBeLessThanOrEqual", "toBeGreaterThan("):
        assert loose not in window, (
            f"the row-count contract uses {loose} — an exact count is the only form that catches a "
            f"paginated export or a stray note row"
        )


def test_the_e2e_reads_the_downloaded_bytes_both_ways():
    """A source guard cannot see a downloaded file. These are the specs that can, and this clause
    pins that they exist and that each asserts the side it is there for."""
    contract = _raw(CONTRACT_SPEC)
    copy_spec = _raw(COPY_SPEC)
    for spec, name in ((contract, CONTRACT_SPEC), (copy_spec, COPY_SPEC)):
        assert 'waitForEvent("download")' in spec, f"{name} does not download the export"
    # The planted case, in the contract spec: the committed board has NO breaching row, so a clause
    # asserted against it as served would assert nothing (the NF-INJ2b vacuous-fixture shape).
    # ⚠️ WORD-BOUNDARIED. A bare `"transform:" in contract` is satisfied by `_transform:` — i.e. by
    # a plant that has been renamed out of the mock's option shape and therefore does nothing at
    # all, which is precisely the "assert against the board as served" defect. Found by the red
    # proof, not by reading this clause.
    assert re.search(r"(?<![\w$])transform:", contract) and '"/fantasy/nfl/board"' in contract, (
        "the contract's withheld-side case does not plant a breaching row — the committed board "
        "contains none, so the clause would pass on nothing"
    )
    # The copy spec pins the RENDERED bytes against the copy module, not a substring of them.
    assert re.search(r"\.toBe\(\s*csvWithheldNote\(\[\"full-season-rate\"\]\)\s*\)", copy_spec), (
        "the E2E does not pin the note row's rendered bytes against the governed copy"
    )
    assert "forbiddenPhrasesIn(note)" in copy_spec, (
        "the E2E does not screen the note a reader actually receives against the denylist"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. What must NOT have changed
# ══════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "symbol",
    ["REALIZED_MAX_SEASON_PACE", "MIN_GAMES_FOR_FULL_SEASON_RATE", "fullSeasonRateDisplay"],
)
def test_the_suppression_owner_is_untouched_by_the_note_machinery(symbol):
    """Scope discipline, asserted rather than promised: the note is a DISCLOSURE of a decision that
    was already being made. It must not participate in making it. A note builder that could reach
    the envelope or the floor would be a second owner of the rule (NF-RATE1's whole point), and one
    that could reach the display decision could change which rows are withheld."""
    copy_src = _code(COPY)
    block = copy_src[copy_src.index("export type CsvWithheldClass"):]
    block = block[: block.index("\n}") + 2] if "\n}" in block else block
    assert symbol not in block, (
        f"the note machinery references {symbol} — a disclosure must not touch the rule it discloses"
    )


def test_the_note_never_reaches_an_ordering_module():
    """⛔⛔ INHERITED FROM NF-RATE1, and it applies with more force here: the note is assembled from
    the withheld SET, so a module that imported it would be one import away from branching the board
    on which rows are withheld. Ranking on a display suppression is a model decision subject to the
    whole-board placement gate (NF-D18/NF-D20), not a UI change."""
    ordering = [
        "lib/league-scoring.ts", "lib/draft-optimizer.ts", "lib/mock-draft.ts",
        "lib/auction-optimizer.ts", "lib/big-board.ts",
        "components/fantasy/league-board.tsx", "components/fantasy/draft-optimizer.tsx",
        "components/fantasy/mock-draft.tsx", "components/fantasy/auction-optimizer.tsx",
        "components/fantasy/big-board.tsx",
    ]
    for rel in ordering:
        code = _code(rel)
        for sym in ("csvWithheldNote", "CSV_WITHHELD_NOTE", "CSV_WITHHELD_CLASSES"):
            assert sym not in code, f"{rel} uses {sym} — the export's note has leaked into ordering"
