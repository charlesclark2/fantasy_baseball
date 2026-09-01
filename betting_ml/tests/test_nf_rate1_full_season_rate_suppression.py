"""NF-RATE1 — the full-season rate is not printed when it is above any full season on record.

THE DEFECT (measured on the staged 2026 board, `board_full_ppr_12.json`, 868 rows). The rate column
is `pts × 17 ÷ g`, computed client-side from two fields that are both served and both stay served
(NF-INJ3b-SHIP ruling D3). On a heavily availability-capped row the quotient prints a number above
every real player on the board: GEORGE KITTLE 580, ALEC PIERCE 545, WILL LEVIS 633, against a #1
overall at 414. `MIN_GAMES_FOR_FULL_SEASON_RATE` does not catch them — all three sit at 3.3–3.7
expected games, well above the floor — because the floor guards the DENOMINATOR'S RESOLUTION and
this is a defect in the RATIO.

⭐ AND THE WORST ROW IS THE PRE-EXISTING ONE. Levis renders 633 on every scoring preset including
standard and predates NF-INJ3b's flip entirely; Kittle and Pierce were widened onto the list by it.
That is why the rule is anchored on realized football rather than written to cover the two rows an
incident named — a rule tuned to the new cases would have left the worst one on the board, and this
suite asserts the anchor catches Levis specifically for that reason.

WHAT THIS SUITE IS AND IS NOT. It is SOURCE INSPECTION over the frontend plus a behavioural read of
the published envelope. It cannot see a rendered cell — `frontend/e2e/specs/full-season-rate.spec.ts`
does that, per surface, both ways. The two are complementary and neither substitutes: a source guard
catches a second owner appearing, an E2E catches the owner being right and the render being wrong.

RED PROOF: `betting_ml/tests/nf_rate1_red_proof.py`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

#: The one owner of the rule, and the four sites that must reach it through that owner.
OWNER = "lib/fantasy.ts"
COPY = "lib/fantasy-claim-copy.ts"
SHARED = "components/fantasy/shared.tsx"
RENDER_SITES = (
    "components/fantasy/rankings-board.tsx",
    "components/fantasy/projections-table.tsx",
    "components/fantasy/player-page.tsx",
)


def _raw(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def _code(rel: str) -> str:
    """Frontend source with comments stripped.

    ⚠️ LOAD-BEARING, and the reason is recorded rather than assumed: this story's own explanatory
    comments NAME every symbol these clauses look for (`fullSeasonRateDisplay`, `fullSeasonRateCsv`,
    `<FullSeasonRateCell`), so a clause run over raw source would be satisfied by the prose while the
    call it names was deleted — the INC-38 "a comment cannot satisfy a guard" defect, which this
    story's comments make unusually easy to hit. Line comments are stripped first so a `//` inside a
    block comment cannot leave a dangling `*/`."""
    text = _raw(rel)
    text = "\n".join(re.sub(r"//.*$", "", ln) for ln in text.splitlines())
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _envelope() -> dict[str, float]:
    """`REALIZED_MAX_SEASON_PACE` as published, parsed out of the TypeScript.

    ⛔ NOT RE-DECLARED HERE. A Python copy of the ceilings would be a second owner of the very thing
    this story exists to keep single-owned, and it would go on agreeing with itself after the served
    numbers moved (`test_nf_inj1_c_stat_line_suppression.py` makes the same call for the same
    reason). Parsing keeps the assertion pointed at what actually ships."""
    code = _code(OWNER)
    m = re.search(
        r"export const REALIZED_MAX_SEASON_PACE:[^=]*=\s*\{(?P<body>.*?)\}", code, re.S
    )
    assert m, "REALIZED_MAX_SEASON_PACE is not exported from lib/fantasy.ts"
    pairs = re.findall(r"(\w+)\s*:\s*([0-9]+(?:\.[0-9]+)?)", m.group("body"))
    assert pairs, "the envelope parsed as empty — a guard over an empty map passes on nothing"
    return {k: float(v) for k, v in pairs}


def _full_season_games() -> int:
    m = re.search(r"export const FULL_SEASON_GAMES = (\d+)", _code(OWNER))
    assert m, "FULL_SEASON_GAMES is not exported"
    return int(m.group(1))


def _min_games() -> float:
    m = re.search(r"export const MIN_GAMES_FOR_FULL_SEASON_RATE = ([0-9.]+)", _code(OWNER))
    assert m, "MIN_GAMES_FOR_FULL_SEASON_RATE is not exported"
    return float(m.group(1))


def _suppressed(pts: float, games: float, pos: str) -> bool:
    """The published rule, applied: below the floor, or above the position's realized ceiling.

    This mirrors `fullSeasonRateDisplay`'s decision so the measured rows below can be scored against
    the envelope AS PUBLISHED. It reads both constants out of the TypeScript rather than restating
    them, so it cannot drift from the shipped rule without this file going red."""
    if games <= 0 or games < _min_games():
        return True
    ceiling = _envelope().get(pos.upper())
    return ceiling is not None and (pts * _full_season_games()) / games > ceiling


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The anchor — derived from realized history, and the DERIVATION is what is pinned
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_envelope_covers_exactly_the_positions_the_anchor_family_covers():
    """The same four positions as NF-INJ1's `REALIZED_MAX_PER_GAME`, and no more.

    ⛔ K and DST are OUT OF SCOPE, which is NOT the same as passing (NF1.7 (a) / `row_violations`'
    own convention). They carry no realized per-game counting analog here and are projected at a
    near-full slate, so the ratio defect cannot arise — but a future editor adding them must derive
    their ceiling, not guess it, and this clause makes the addition visible."""
    assert set(_envelope()) == {"QB", "RB", "WR", "TE"}


def test_the_envelope_pins_its_derivation_not_merely_its_values():
    """AC: "pin the DERIVATION, not the value".

    A bare map of four numbers is unfalsifiable — a later reader cannot tell a derived ceiling from
    a chosen one, and E2.1-r's failure mode is exactly a number quietly re-picked to accommodate a
    board that failed it. So the source must carry the query, the population, the statistic and the
    stability check, and this clause is what keeps them from being tidied away."""
    src = _raw(OWNER)
    block = src[src.index("NF-RATE1 — THE REALIZED-PACE CEILING"):src.index("export const REALIZED_MAX_SEASON_PACE")]
    for token, why in [
        ("main_nfl_marts.fct_player_week", "the source table the anchor family is derived from"),
        ("2006", "the seasons the population spans"),
        ("2025", "the seasons the population spans"),
        ("REALIZED_MAX_PER_GAME", "the anchor family this is the season-points analog of"),
        ("11,190", "the size of the population"),
        ("stability", "the check that the ceiling is not an artifact of one-game cameos"),
        ("E2.1-r", "the standing prohibition on re-deriving it from a board that failed it"),
    ]:
        assert token in block, f"the derivation does not record {why} ({token!r})"
    assert "select" in block.lower() and "group by" in block.lower(), (
        "the derivation records no query, so a reader cannot re-run it"
    )


def test_the_ceiling_is_a_max_over_the_most_generous_scoring_we_publish():
    """WHY THE TE CEILING IS THE HIGHEST OF THE FOUR SCORINGS. The served boards span standard,
    half, full PPR, superflex and TE-premium; TE-premium's `+0.5` per TE reception is the only
    preset that exceeds full PPR, so a ceiling derived on PPR alone would be too LOW for a
    TE-premium board and could suppress a rate that scoring genuinely permits.

    A false suppression is the expensive error here (a paying reader loses a real number and cannot
    tell why), so the rule errs toward printing — and this clause pins that the TE ceiling actually
    carries the premium headroom rather than merely claiming to."""
    env = _envelope()
    src = _raw(OWNER)
    assert "TE-premium" in src or "te_premium" in src, (
        "the derivation does not say which scoring the ceiling is taken over"
    )
    # The PPR-only TE ceiling measured 354.5; the TE-premium one 414.0. A ceiling at or below the
    # PPR figure would mean the premium term was dropped from the derivation.
    assert env["TE"] > 354.5, (
        f"the TE ceiling ({env['TE']}) is at or below the full-PPR maximum — the TE-premium "
        f"headroom the served boards need has been dropped from the derivation"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The rule, BOTH WAYS, on the rows that were actually measured
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: (name, pos, expected_pts, expected_games, rendered_rate) — read off the STAGED 2026 board on
#: 2026-08-30, the same artifact NF-INJ3b-SHIP's follow-up 9 measured. Carried as data rather than
#: re-derived so this clause is a statement about real served rows, not about a synthetic one.
_MEASURED_SUPPRESSED = [
    ("Will Levis", "QB", 137.7, 3.7, 633),      # PRE-EXISTING — predates NF-INJ3b's flip entirely
    ("George Kittle", "TE", 112.6, 3.3, 580),   # widened onto the list by the flip
    ("Alec Pierce", "WR", 118.6, 3.7, 545),     # widened onto the list by the flip
]

#: The other side, and the reason the rule is an ANCHOR rather than a list. Higgins was named beside
#: Kittle and Pierce in the same follow-up; Gibbs is the board's #1 overall. Both render rates a
#: real player-season has actually beaten, so both must still print.
_MEASURED_RENDERED = [
    ("Jayden Higgins", "WR", 121.5, 5.0, 413),
    ("Jahmyr Gibbs", "RB", 350.8, 14.4, 414),
]


@pytest.mark.parametrize("name,pos,pts,games,rate", _MEASURED_SUPPRESSED, ids=lambda v: str(v))
def test_the_rule_catches_every_measured_absurd_row(name, pos, pts, games, rate):
    """⭐ INCLUDING LEVIS, WHICH IS THE POINT. AC: "the rule must catch Levis (pre-existing) as well
    as the flip-widened rows — a fix that only catches the new cases is tuned to the incident."

    Also asserts the floor does NOT catch them: all three are above `MIN_GAMES_FOR_FULL_SEASON_RATE`,
    so a reading that "the existing floor was nearly enough" is false and the new predicate is doing
    all of the work."""
    assert games > _min_games(), (
        f"{name} sits below the existing floor — this row would not test the new rule at all"
    )
    assert _suppressed(pts, games, pos), (
        f"{name} renders {rate} at {pos} and the published envelope does not suppress it"
    )


@pytest.mark.parametrize("name,pos,pts,games,rate", _MEASURED_RENDERED, ids=lambda v: str(v))
def test_the_rule_leaves_a_high_but_real_rate_alone(name, pos, pts, games, rate):
    """THE OTHER HALF, and the one a rule written from the incident list would fail. Higgins was
    named in the same measurement as Kittle and Pierce, renders 413, and is NOT suppressed — a WR
    has posted a 435-point pace, so 413 is inside what football has done. The anchor says so; an
    incident list would have said otherwise."""
    assert not _suppressed(pts, games, pos), (
        f"{name} renders {rate} at {pos} — inside the realized envelope — and is being suppressed"
    )


def test_a_degenerate_ceiling_would_be_caught_here():
    """A two-sided sanity check on this suite itself. If the parsed envelope were empty, or every
    ceiling absurdly high, every clause above would pass vacuously — `_envelope()` already refuses
    an empty map, and this pins that the ceilings are in the neighbourhood a real season occupies."""
    env = _envelope()
    assert all(200 < v < 700 for v in env.values()), (
        f"a ceiling outside the range a real fantasy season occupies: {env}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. ONE OWNER, FOUR SITES
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_rule_is_declared_in_exactly_one_place():
    """The predicate — comparing an implied pace to the envelope — must exist once. Four inline
    copies of one rule is the "one logical thing, many owners" defect (INC-30 crontab, INC-36
    deploys, INC-38 month-boundary flags) on day one, and the CSV is precisely the owner a
    table-only fix forgets."""
    for rel in RENDER_SITES + (SHARED,):
        assert "REALIZED_MAX_SEASON_PACE" not in _code(rel), (
            f"{rel} reads the envelope directly — the rule now has two owners"
        )
    owners = [rel for rel in RENDER_SITES + (SHARED, OWNER)
              if "REALIZED_MAX_SEASON_PACE[" in _code(rel)]
    assert owners == [OWNER], f"the envelope is applied outside its owner: {owners}"


def test_no_render_site_recomputes_the_rate_inline():
    """⚠️ THE SHAPE THIS IS REALLY GUARDING. The defect was never the helper; it was that four
    surfaces each did their own arithmetic on two served fields. A site that goes back to
    `pts * 17 / g` (or to calling the raw `fullSeasonRate` helper) silently opts out of the rule
    while still rendering a number, which is indistinguishable from working."""
    for rel in RENDER_SITES:
        code = _code(rel)
        assert not re.search(r"\*\s*(17|FULL_SEASON_GAMES)\s*\)?\s*/", code), (
            f"{rel} appears to recompute the full-season rate inline"
        )
        assert not re.search(r"[^A-Za-z]fullSeasonRate\s*\(", code), (
            f"{rel} calls the raw helper directly, bypassing the suppression rule"
        )


@pytest.mark.parametrize(
    "rel,expected",
    [
        ("components/fantasy/rankings-board.tsx", "<FullSeasonRateCell"),
        ("components/fantasy/projections-table.tsx", "<FullSeasonRateCell"),
        ("components/fantasy/player-page.tsx", "FullSeasonRateSubLine("),
    ],
)
def test_every_on_page_site_renders_through_the_shared_component(rel, expected):
    """Three of the four sites. The fourth (the CSV) has its own clause below, because its correct
    rendering is an EMPTY CELL rather than a component and no component-shaped assertion can see
    it — which is exactly why a table-only fix misses it."""
    assert expected in _code(rel), f"{rel} does not render through the shared owner"


def test_the_player_page_renders_the_rate_on_both_of_its_tiles():
    """`player-page.tsx` is TWO call sites, not one — the reference Full-PPR tile and the
    league-scored tile beside it — and NF-INJ3b's follow-up enumerated them separately for that
    reason. A fix applied to one leaves the other printing 633."""
    assert _code("components/fantasy/player-page.tsx").count("FullSeasonRateSubLine(") == 2, (
        "the player page has two full-season-rate call sites; both must go through the owner"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The CSV column — the site a table-only fix silently misses
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_csv_column_is_fed_by_the_owner():
    """AC: "a Python guard covers the CSV column both ways". This is the first way: the exported
    `full_season_rate` column is produced by `fullSeasonRateCsv`, so it inherits the same rule the
    on-page column does rather than re-deriving one."""
    code = _code("components/fantasy/rankings-board.tsx")
    assert '"full_season_rate"' in code, "the export no longer carries the column at all"
    assert "fullSeasonRateCsv(" in code, "the exported column is not produced by the shared owner"


def test_the_csv_cell_is_empty_on_a_suppressed_row_and_a_number_otherwise():
    """The second way, and it takes two hops because the emptiness is produced by `downloadCsv`:

      1. `fullSeasonRateCsv` returns the value for `rate` and `null` for everything else, and
      2. `downloadCsv`'s escaper maps `null` to the empty string.

    ⭐ AN EMPTY CELL, NEVER A SENTINEL. A `withheld` string would break the column's type for every
    reader who sorts or averages it; `0` or `-1` would be a wrong number rather than an absent one.
    Both hops are asserted because breaking either one alone produces a well-formed file with a
    wrong column."""
    owner = _code(OWNER)
    body = owner[owner.index("export function fullSeasonRateCsv"):]
    body = body[: body.index("\n}")]
    # ⚠️ THE RETURN EXPRESSION, NOT "is `null` mentioned anywhere in this function". The first cut of
    # this clause spelled the latter and the red proof caught it GREEN against a body returning `0`
    # — because the signature's own `number | null` satisfied it. A sentinel is the exact defect
    # this guards, so the assertion has to read the branch that produces the cell.
    assert re.search(r'return\s+d\.kind === "rate" \? d\.value : null', body), (
        "fullSeasonRateCsv no longer returns null for the non-rate states — a sentinel (0, -1, a "
        "string) would be a wrong number in the column rather than an absent one"
    )
    esc = _code(SHARED)
    esc = esc[esc.index("export function downloadCsv"):]
    esc = esc[: esc.index("\n}")]
    assert 'if (v == null) return ""' in esc, (
        "downloadCsv no longer writes a null cell as empty — a suppressed row would export a "
        "sentinel or the literal 'null'"
    )


def test_the_empty_cell_semantics_are_written_down_where_the_export_is_built():
    """AC asks for the semantics in "the export's header note or data dictionary if one exists".
    Neither exists for this export — `downloadCsv` writes a bare header row and there is no data
    dictionary — so the semantics are recorded at the header list, which is where every other
    decision about this file's columns is already recorded. This clause keeps them there."""
    src = _raw("components/fantasy/rankings-board.tsx")
    block = src[src.index("const exportCsv"):src.index('"full_season_rate"')]
    assert "WITHHOLDING" in block.upper(), (
        "the export does not record what an empty full_season_rate cell means"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. What must NOT have changed
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_min_games_floor_is_untouched():
    """AC: "the existing MIN_GAMES floor behavior unchanged". The new state is ADDITIVE — every
    branch `fullSeasonRate` already refused still returns the same `unavailable` rendering it did
    before, so this story adds a state rather than restyling the one that was there."""
    owner = _code(OWNER)
    body = owner[owner.index("export function fullSeasonRate("):]
    body = body[: body.index("\n}")]
    assert "games < MIN_GAMES_FOR_FULL_SEASON_RATE" in body
    assert "games <= 0" in body
    assert body.count("return null") >= 3
    disp = owner[owner.index("export function fullSeasonRateDisplay"):]
    disp = disp[: disp.index("\n}")]
    assert 'kind: "unavailable"' in disp and "fullSeasonRate(" in disp, (
        "fullSeasonRateDisplay no longer delegates the pre-existing refusals to fullSeasonRate — "
        "the floor's behaviour is now restated rather than inherited, and the two can drift"
    )


def test_the_nf_inj1_c_stat_line_machinery_is_adjacent_not_shared():
    """AC: "NF-INJ1-C's withheld-stat-line machinery untouched (adjacent, not shared)".

    That mechanism suppresses SERVED COUNTING STATS the server marked on the row; this one suppresses
    a DERIVED DISPLAY LINE the client computes. Same Option-C pattern, different predicate, different
    inputs. Folding them together would make one component answer to two stories."""
    shared = _code(SHARED)
    assert "export function WithheldStat()" in shared, "NF-INJ1-C's component was removed"
    assert "export function WithheldFullSeasonRate()" in shared, "this story's component is missing"
    rate = shared[shared.index("export function WithheldFullSeasonRate"):]
    rate = rate[: rate.index("\n}")]
    assert "STAT_LINE_WITHHELD" not in rate, (
        "the rate's disclosure reuses NF-INJ1-C's copy — the two refusals would then say the same "
        "thing about different conditions"
    )
    assert "isStatWithheld" not in rate, "the rate's render reads NF-INJ1-C's server-side marker"


def test_the_withheld_copy_lives_in_claim_copy_and_makes_no_forecast():
    """⛔ NO FORECAST LANGUAGE AND NO INJURY CLAIM. The withheld state is a statement about OUR
    arithmetic, not about the player — and the column is not about availability at all, so any
    availability verb here would be both an unearned claim and a wrong one."""
    copy = _raw(COPY)
    for name in (
        "FULL_SEASON_RATE_WITHHELD_LABEL",
        "FULL_SEASON_RATE_WITHHELD_SR_LABEL",
        "FULL_SEASON_RATE_WITHHELD_DETAIL",
    ):
        assert f"export const {name}" in copy, f"{name} is not declared in fantasy-claim-copy.ts"
    strings = " ".join(
        re.findall(r"export const FULL_SEASON_RATE_WITHHELD_\w+\s*=\s*\n?\s*\"([^\"]*)\"", copy)
    ).lower()
    assert strings, "the withheld copy parsed as empty"
    for banned in (
        "expected to miss", "will miss", "is injured", "injury", "hurt", "expected to play",
        "guaranteed", "more accurate", "win your league",
    ):
        assert banned not in strings, f"the withheld copy makes a forecast/overclaim: {banned!r}"
    assert "record" in strings, (
        "the short label no longer names the condition a reader can check for themselves"
    )


def test_no_component_writes_the_withheld_prose_inline():
    """The copy screening only sees `fantasy-claim-copy.ts`, so a sentence typed into a component is
    a sentence nothing screens — the standing rule for every claim on these surfaces."""
    for rel in RENDER_SITES + (SHARED,):
        code = _code(rel)
        assert "higher than any full season" not in code.lower(), (
            f"{rel} writes the withheld wording inline instead of importing it"
        )


def test_the_rate_is_still_a_display_transform_only():
    """⛔⛔ INHERITED, NOT NEW. `test_freemium_tier.py` holds the boundary for `fullSeasonRate`; the
    two new exports are the same transform and inherit it. Ranking on a full-slate rate ranks players
    as if availability did not exist, and because it REORDERS the board it becomes a model decision
    subject to the whole-board placement gate rather than a UI change."""
    ordering = [
        "lib/league-scoring.ts", "lib/draft-optimizer.ts", "lib/mock-draft.ts",
        "lib/auction-optimizer.ts", "lib/big-board.ts",
        "components/fantasy/league-board.tsx", "components/fantasy/draft-optimizer.tsx",
        "components/fantasy/mock-draft.tsx", "components/fantasy/auction-optimizer.tsx",
        "components/fantasy/big-board.tsx",
    ]
    for rel in ordering:
        code = _code(rel)
        for sym in ("fullSeasonRateDisplay", "fullSeasonRateCsv", "REALIZED_MAX_SEASON_PACE"):
            assert sym not in code, f"{rel} uses {sym} — a display transform has leaked into ordering"


def test_the_e2e_spec_exists_and_covers_every_surface_both_ways():
    """A source guard cannot see a rendered cell. This clause pins that the spec which can exists,
    names all three on-page surfaces plus the CSV, and asserts BOTH sides on each — a spec that only
    checked the suppressed row would pass a build that suppressed the whole column."""
    spec = _FRONTEND / "e2e/specs/full-season-rate.spec.ts"
    assert spec.exists(), "NF-RATE1 has no E2E spec"
    text = spec.read_text()
    for surface in ("/fantasy/rankings", "/fantasy/projections", "/fantasy/player/"):
        assert surface in text, f"the E2E spec does not visit {surface}"
    assert "Export CSV" in text, "the E2E spec does not exercise the CSV export"
    # BOTH SIDES, PER SURFACE. One "the disclosure is visible" on the withheld row and one
    # "it is not there at all" on the control, for each of the three on-page surfaces. Presence
    # alone is satisfied by a treatment that fires on every row; absence alone by one that fires on
    # none — only the PAIR is the test, and only counting both sides can see that the pair is there.
    #
    # ⚠️ Read STRUCTURALLY (the assertion that FOLLOWS each locator) rather than as a fixed string:
    # every one of these carries a failure message, so the locator and its matcher are lines apart
    # and a literal-substring clause would silently count zero — passing on nothing.
    uses = text.split("WITHHELD_TRIGGER")[1:]
    shown = sum(1 for u in uses if "toBeVisible" in u[:400])
    absent = sum(1 for u in uses if "toHaveCount(0)" in u[:400])
    assert shown >= 3, (
        f"the E2E spec asserts the withheld disclosure VISIBLE on {shown} surfaces, not all three "
        f"(rankings board, projections table, player page)"
    )
    assert absent >= 3, (
        f"the E2E spec asserts an untouched control row on {absent} surfaces, not all three — a "
        f"spec that only checks the suppressed row passes a build that suppressed every row"
    )
    # ...and the CSV, whose two sides are an empty cell and a populated one.
    assert 'toBe("")' in text and 'not.toBe("")' in text, (
        "the E2E spec does not read the exported CSV column both ways"
    )
