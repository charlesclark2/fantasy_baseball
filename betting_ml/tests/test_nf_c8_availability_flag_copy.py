"""NF-C8 — the AVAILABILITY FLAG: copy governance + surface coverage, as executable clauses.

WHAT THE FLAG IS. The projection already multiplies the chance a player misses games through his
point total, and the expected-games figure `g` is served beside it — so on every board the discount
is PRESENT and INVISIBLE. A drafter meets a player ranked two rounds lower than he expected and a
points number he cannot account for; the column that explains it sits four columns right in the same
grey as everything else. NF-C8 colours the games figure on the rows where the discount is material
and puts the sentence one tap behind it.

⛔⛔ THE FAILURE THIS SUITE EXISTS TO PREVENT, AND IT IS NOT A COSMETIC ONE: THE FLAG MUST NEVER
FORECAST AN INJURY. What we hold is a property of OUR PROJECTION — we project this player for fewer
than a full slate of games. What we do NOT hold, have never modelled and could not defend is that a
particular player is hurt, will get hurt, or will miss particular weeks. Those are medical
predictions about a named person, published under our name, on the highest-traffic surface in the
fantasy product.

Two things make that failure LIKELY rather than hypothetical, which is why it gets a suite:

  1. AN AMBER CHIP READS AS "INJURY RISK" ALL BY ITSELF. The colour is doing the same work the words
     are, and only the words can be screened — so the words have to carry the disclaimer explicitly
     rather than merely avoid the claim.
  2. IT IS ONE VERB WIDE. "will miss", "expected to miss", "injury risk", "out for", "questionable"
     — each is a natural thing to write, each is shorter than the honest phrasing, and none of them
     would fail a build without `_INJURY_FORECAST_VERBS` below.

⭐ ONE FIXTURE PER CLAUSE (NF-D17 §7). Several rules here are conjunctions, and a fixture that trips
two clauses at once tests NEITHER — the first refusal hides the second. Each clause is written so
that deleting the ONE thing it names turns it, and only it, red. `nf_c8_red_proof.py` proves that.

⭐ COMMENTS ARE STRIPPED BEFORE EVERY SOURCE MATCH (INC-38). The modules touched here explain
themselves by quoting the forbidden wordings while forbidding them — `fantasy.ts`'s NF-C8 block
literally contains "will miss" inside the paragraph that bans it — so a raw substring scan would be
satisfied by that prose, and would ALSO fire on it. Both directions are real.

Pure/offline (fast gate): reads source files, no DuckDB/S3/network.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as ex

_REPO = Path(__file__).resolve().parents[2]
_CLAIM_COPY_TS = _REPO / "frontend/lib/fantasy-claim-copy.ts"
_FANTASY_LIB_TS = _REPO / "frontend/lib/fantasy.ts"
_SHARED_TSX = _REPO / "frontend/components/fantasy/shared.tsx"
_FANTASY_COMPONENTS = _REPO / "frontend/components/fantasy"

#: The copy constants this story added. Named so a red run points at the offending one rather than
#: at "some string in a 900-line module".
_NF_C8_CONSTANTS = (
    "AVAILABILITY_FLAG_LABEL",
    "AVAILABILITY_FLAG_SUMMARY",
    "AVAILABILITY_FLAG_DEFINITION",
    "AVAILABILITY_DATA_AS_OF_PREFIX",
)

#: ⛔⛔ THE INJURY-FORECAST BOUNDARY, as a list. Every phrase here asserts something about a PERSON'S
#: HEALTH or about SPECIFIC WEEKS — neither of which our model produces. `g` is an expectation over
#: everything that could happen to a player; it is not a diagnosis and not a schedule.
#:
#: ⚠️ "injury" ALONE IS NOT ON THIS LIST, and that omission is deliberate rather than an oversight.
#: The freshness line has to be able to say WHICH FEED it is stamping ("Injury and roster status as
#: of …"), and a blanket ban on the word would make the honest provenance line unwriteable — the
#: NF-C6P3 lesson, where a negation-blind denylist made the honest hedge the cheapest thing to
#: delete. What is banned is the CLAIM, not the noun.
#:
#: ⚠️⚠️ THE SCAN IS DELIBERATELY **NEGATION-BLIND**, AND THAT IS A CONSIDERED CHOICE RATHER THAN THE
#: NF-C6P3 DEFECT REPEATED. It fired during this story's own build, on an honest hedge that read
#: "it is not a forecast that he IS HURT" — i.e. on the sentence refusing the claim. Two repairs
#: were available and the tempting one is wrong:
#:
#:   ⛔ make the scan negation-aware — a negation WINDOW is a real hole, because a forecast survives
#:      negation intact: "we do not think he WILL MISS more than three games" is still a medical
#:      prediction and would be waved through by any "preceded by a negator" rule.
#:   ✅ keep the scan absolute and express the refusal WITHOUT the banned tokens ("not a forecast
#:      about his health"). The meaning is identical and nothing honest is lost.
#:
#: What stops that strictness from doing what NF-C6P3 warns about — making the HEDGE the cheapest
#: thing to delete — is that the hedge is independently REQUIRED by
#: `test_the_definition_says_out_loud_that_it_is_not_a_diagnosis` below. Deleting it fails a clause;
#: rewording it around the token does not. The two clauses only work as a pair.
_INJURY_FORECAST_VERBS = (
    "will miss",
    "will be out",
    "expected to miss",
    "projected to miss",
    "likely to miss",
    "injury risk",
    "injury-prone",
    "is injured",
    "is hurt",
    "out for",
    "sidelined",
    "questionable for",
    "day-to-day",
    "return from injury",
)

#: Wordings that would let the flag absorb the residual — the `EXPECTED_POINTS_NOTE` rule, one
#: surface over and on far more traffic. Availability carries most of the measured level shift and
#: not all of it, and a flag saying otherwise would use an honest mechanism to bury a dishonest
#: amount.
_ABSORPTION_CLAIMS = (
    "accounts for the difference",
    "explains the difference",
    "explains the gap",
    "accounts for the gap",
    "fully explains",
    "entirely explained",
    "this is why his number",
    "that is why his number",
)

#: Every fantasy surface that RENDERS a projected-games value, and therefore owes the reader a flag
#: when that value is materially low. Pinned by its own exhaustiveness clause below (INC-38: a
#: per-surface fix fails exactly where the registry is incomplete).
_GAMES_SURFACES: tuple[str, ...] = (
    "rankings-board.tsx",
    "projections-table.tsx",
    "player-page.tsx",
)

#: ⚠️ THE ACKNOWLEDGED NON-CARRIERS, with the reason each is out of scope. An exemption list is a
#: liability unless every entry states WHY, so the exhaustiveness clause below reads this rather
#: than a bare filename set.
_GAMES_SURFACE_EXEMPTIONS: dict[str, str] = {
    # A finished-season retrospective. `projGames` there describes a season that has already been
    # played, so "we project limited availability" is not a statement it can make — the flag would
    # be a forward-looking chip on a backward-looking row.
    "track-record-page.tsx": "renders a REALIZED season's games, not a projection",
}


def _strip_ts_comments(src: str) -> str:
    """⚠️ INC-38: a source-inspection guard a COMMENT can satisfy cannot fail — and here a comment
    can also make one fire FALSELY, because the modules under test quote the banned wordings inside
    the paragraphs that ban them.

    ⚠️⚠️ LINE COMMENTS COME OFF **FIRST**, AND THAT ORDER IS THE WHOLE FUNCTION — carried verbatim
    from `test_expected_points_label_copy._strip_ts_comments`, including the reason: a `//` comment
    containing a path glob opens a `/*` that a block-first stripper closes at the next genuine `*/`,
    silently deleting every line between (measured: 55 lines of live code in `draft-optimizer.tsx`).
    A registry clause would then scan a source with the very lines it polices removed — green
    against a defect physically present on disk.

    `(?<!:)` keeps `https://` from being read as a comment."""
    src = re.sub(r"(?<!:)//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def _ts_string_literals(src: str) -> list[str]:
    return re.findall(r'"((?:[^"\\]|\\.)*)"', _strip_ts_comments(src))


@pytest.fixture(scope="module")
def copy_src() -> str:
    return _CLAIM_COPY_TS.read_text()


def _const(src: str, name: str) -> str:
    """The prose of one exported constant — the string literal(s) in its declaration.

    Anchored on the assignment and terminated at the next top-level `export`, so a clause about one
    constant can never be satisfied by a neighbouring one's wording."""
    body = src.split(f"export const {name}", 1)
    assert len(body) == 2, f"{name} is not exported from the canonical copy module"
    tail = body[1].split("\nexport const ", 1)[0]
    literals = _ts_string_literals(tail)
    assert literals, f"no prose extracted for {name} — every clause about it would be vacuous"
    return " ".join(literals).lower()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 0. The instruments themselves. An extractor that silently returns nothing, or a stripper that
#    eats live code, makes every clause below vacuously true (NF1.7 (a)). Checked first, on purpose.
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_copy_extractor_actually_finds_every_nf_c8_constant(copy_src):
    for name in _NF_C8_CONSTANTS:
        assert len(_const(copy_src, name)) > 15, f"{name} extracted as near-empty prose"
    # The definition is the one that carries the boundary; a one-liner there would pass the
    # screens and explain nothing.
    assert len(_const(copy_src, "AVAILABILITY_FLAG_DEFINITION")) > 200


def test_the_comment_stripper_removes_prose_that_would_satisfy_or_falsely_trip_a_scan():
    """Both directions, because both occur in this story's own sources: the NF-C8 blocks in
    `fantasy.ts` and `fantasy-claim-copy.ts` contain the banned phrase "will miss" inside the
    paragraph forbidding it, so an unstripped scan would FAIL on the very comment that documents the
    rule — and a comment saying "we never say will miss" must not be able to satisfy a clause
    demanding the disclaimer either."""
    src = (
        '// the flag must never say he will miss weeks\n'
        '/* nor "injury risk" */\n'
        'const real = "We project this player for fewer games"\n'
    )
    out = _strip_ts_comments(src)
    assert "will miss" not in out
    assert "injury risk" not in out
    assert "We project this player" in out


def test_the_comment_stripper_does_not_eat_code_after_a_path_glob_in_a_line_comment():
    """The `draft-optimizer.tsx` defect, pinned here too so this suite's copy of the stripper cannot
    regress independently of the one in `test_expected_points_label_copy.py`.

    ⚠️⚠️ THE TRAILING BLOCK COMMENT IS LOAD-BEARING AND THIS CLAUSE SHIPPED WITHOUT IT — caught by
    the red proof, not by review. `/\*.*?\*/` needs a CLOSING `*/` to match anything at all, so a
    fixture whose only `/*` is the one hiding inside the path glob gives a block-first stripper
    NOTHING to consume: it deletes nothing, both assertions hold, and the clause passes whichever
    order the stripper uses. The genuine block comment below supplies the `*/` that a block-first
    stripper closes on — swallowing the two code lines between — which is the only reason reordering
    the two `re.sub` calls turns this red."""
    src = (
        "// boards load through the gated backend (/fantasy/nfl/*, require_fantasy_access)\n"
        'const heading = "will miss"\n'
        'const doc = "https://example.com/docs"\n'
        "/* a real block comment mentioning injury risk */\n"
    )
    out = _strip_ts_comments(src)
    assert "will miss" in out, "code after a path glob in a line comment was swallowed"
    assert "https://example.com/docs" in out, "a URL was mistaken for a line comment"
    assert "injury risk" not in out, "a genuine block comment survived"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. ⛔⛔ The injury-forecast boundary — the clause this whole story answers to
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("name", _NF_C8_CONSTANTS)
def test_the_flag_copy_never_forecasts_an_injury(name, copy_src):
    """⛔⛔ THE LOAD-BEARING CLAUSE. `g` is an expectation across everything that could happen to a
    player — it is not a diagnosis, and it names no weeks. Any wording asserting a player IS hurt,
    WILL be hurt, or will miss SPECIFIC time is a medical prediction we have never made, published
    under our name beside his photo."""
    prose = _const(copy_src, name)
    hits = [v for v in _INJURY_FORECAST_VERBS if v in prose]
    assert not hits, (
        f"{name} forecasts an injury {hits} — the flag describes OUR PROJECTION ('we project N "
        f"games'), never a player's health"
    )


def test_the_definition_says_out_loud_that_it_is_not_a_diagnosis(copy_src):
    """The other direction of the same rule, and it is a SEPARATE failure: avoiding the forbidden
    verbs is not the same as telling the reader what the flag is not. A coloured chip reads as
    "injury risk" on its own — the colour makes the claim whether the words do or not — so the words
    have to refuse it explicitly rather than merely decline to make it."""
    d = _const(copy_src, "AVAILABILITY_FLAG_DEFINITION")
    assert "not a diagnosis" in d, (
        "the flag's definition no longer states it is not a diagnosis — without that sentence an "
        "amber chip beside a player's name IS an injury claim, regardless of what it avoids saying"
    )
    assert "average across everything that could happen" in d, (
        "the definition no longer explains that the games figure is an expectation, which is the "
        "whole reason it is not a forecast about this player"
    )


def test_the_definition_names_our_projection_as_the_subject(copy_src):
    """"We project this player for fewer games" is defensible; "he will play fewer games" is a
    forecast about a person. The grammatical subject is the entire distinction, so it is asserted
    rather than left to the author's ear."""
    d = _const(copy_src, "AVAILABILITY_FLAG_DEFINITION")
    assert "we project" in d, (
        "the definition's subject is no longer OUR PROJECTION — a sentence whose subject is the "
        "player is a claim about the player"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The flag may not absorb the residual, and may not publish its own thresholds
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("name", _NF_C8_CONSTANTS)
def test_the_flag_copy_does_not_claim_availability_explains_the_whole_gap(name, copy_src):
    """`EXPECTED_POINTS_NOTE`'s rule, on a much higher-traffic surface. Availability carries most of
    the measured level shift and not all of it; the residual is a real miscalibration with its own
    model story, and a chip that said "this is why his number is low" would convert a visible
    anomaly into an invisible one."""
    prose = _const(copy_src, name)
    hits = [c for c in _ABSORPTION_CLAIMS if c in prose]
    assert not hits, f"{name} claims availability {hits}"


def test_the_definition_carries_the_residual_hedge(copy_src):
    """…and states it positively, so the absence of an absorption claim is not merely luck."""
    d = _const(copy_src, "AVAILABILITY_FLAG_DEFINITION")
    assert "not the only reason" in d, (
        "the flag's definition dropped the hedge — it now reads as though availability accounts "
        "for where a projection lands, which it does not"
    )


def test_the_flag_copy_publishes_no_threshold_and_no_measured_figure(copy_src):
    """⛔ Two rules at once, and they share a mechanism. The thresholds live in `lib/fantasy.ts` as
    DISPLAY constants; typing one into a sentence would duplicate it where no test pins it AND
    dress a rendering choice as a published finding. The `{games}` placeholder is what keeps the
    per-player value read from the served artifact (E9.56b/NF-D3) rather than typed."""
    for name in _NF_C8_CONSTANTS:
        prose = _const(copy_src, name)
        assert not re.search(r"\d", prose), (
            f"{name} contains a digit — the flag's thresholds are display constants in "
            f"lib/fantasy.ts and the per-player games value is interpolated from the payload; "
            f"neither belongs in copy"
        )


def test_the_summary_interpolates_the_served_games_value(copy_src):
    """The one number the flag shows is the PLAYER'S OWN, read from the payload. The placeholder is
    what proves it is not typed — and its absence would be invisible, because a summary reading
    "limited availability priced in" with no figure still renders perfectly well."""
    raw = _CLAIM_COPY_TS.read_text().split("export const AVAILABILITY_FLAG_SUMMARY", 1)[1]
    summary = _ts_string_literals(raw.split("\nexport const ", 1)[0])[0]
    assert "{games}" in summary, (
        "AVAILABILITY_FLAG_SUMMARY no longer carries the {games} placeholder — the flag would show "
        "no per-player figure, or worse, a typed one"
    )


def test_the_flag_copy_passes_the_track_record_denylist(copy_src):
    """These strings ship on the free, public, unauthenticated boards — the most-read surfaces in
    the product — so they answer to the same screen as the track record's generated claim.

    (`test_nf_tr1_claim_copy.py` scans the whole module; this names the NF-C8 constants so a red run
    points at them rather than at "some literal in a 900-line file".)"""
    for name in _NF_C8_CONSTANTS:
        prose = _const(copy_src, name)
        hits = [t for t in ex._CLAIM_DENYLIST if t in prose]
        assert not hits, f"{name} makes a forbidden claim {hits}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The thresholds — ONE shared constant, pinned, and never a model input
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_thresholds_are_one_shared_constant_at_the_declared_values():
    """⭐ THE STORY'S OWN AC. Three surfaces flag rows; if each carried its own `< 12.5` the boards
    would drift apart silently — the same row flagged on Rankings and not on Projections, with
    nothing failing. Pinned at the values so a change is a deliberate edit to a test rather than a
    quiet re-tuning (the E2.1-r discipline: a display threshold reverse-engineered to make a
    particular player flag is the same inversion as a gate reverse-engineered to pass).

    ⚠️ 12.5, NOT 14 — see the constant's own doc. 14 was derived against `FULL_SEASON_GAMES`, which
    no skill player is projected near; measured on the served board it sat just below the MEDIAN
    draftable skill player (14.4) and flagged 37.6% of them."""
    src = _strip_ts_comments(_FANTASY_LIB_TS.read_text())
    assert re.search(r"export const LIMITED_AVAILABILITY_GAMES\s*=\s*12\.5\b", src), (
        "LIMITED_AVAILABILITY_GAMES is not declared as 12.5 in lib/fantasy.ts"
    )
    assert re.search(r"export const HEAVILY_LIMITED_AVAILABILITY_GAMES\s*=\s*10\b", src), (
        "HEAVILY_LIMITED_AVAILABILITY_GAMES is not declared as 10 in lib/fantasy.ts"
    )


def test_the_threshold_is_not_anchored_on_the_schedule_length():
    """⚠️ THE MISTAKE THIS STORY SHIPPED AND HAD TO CORRECT, pinned so it cannot come back.

    `FULL_SEASON_GAMES` is 17 — the SCHEDULE. The only rows projected anywhere near it are team
    defences; the median draftable skill player is 14.4. A threshold expressed as "N games below a
    full slate" therefore measures every skill player against a level none of them occupy, and the
    first version of this constant flagged 37.6% of the draftable skill board as a result.

    The clause is deliberately about the DERIVATION rather than the value: a future edit that
    re-anchors on the schedule would very likely re-introduce a threshold near 14 and re-create the
    defect, and the value pin above would not catch it if the number happened to differ."""
    src = _strip_ts_comments(_FANTASY_LIB_TS.read_text())
    decl = src.split("export const LIMITED_AVAILABILITY_GAMES", 1)[1].split("\n", 1)[0]
    assert "FULL_SEASON_GAMES" not in decl, (
        "the availability threshold is expressed in terms of FULL_SEASON_GAMES — that is the "
        "schedule length, not a level any skill player is projected at, and anchoring on it is "
        "exactly how this constant came to flag 37.6% of the draftable skill board"
    )


def test_no_surface_hardcodes_its_own_availability_threshold():
    """The other half of "one shared constant": the constants existing does not stop a component
    writing `p.g < 14` inline. Scanned across the whole fantasy component tree, because the hazard
    is a FUTURE surface, not the three this story wired."""
    offenders = {}
    for path in sorted(_FANTASY_COMPONENTS.glob("*.tsx")):
        src = _strip_ts_comments(path.read_text())
        hits = re.findall(r"\.g\s*[<>]=?\s*\d+(?:\.\d+)?", src)
        if hits:
            offenders[path.name] = hits
    assert not offenders, (
        f"these surfaces compare a games value against a literal threshold: {offenders}. Use "
        f"`availabilityTier` so the three boards cannot disagree about which rows are flagged."
    )


def test_the_classifier_is_display_only_and_never_reaches_ordering():
    """⛔⛔ The same hard boundary `fullSeasonRate` carries, for the same reason and enforced the
    same way (`test_freemium_tier.py` does this for that helper). A threshold that moved a player's
    RANK would be a model decision subject to the whole-board placement gate (NF-D18/NF-D20), not a
    UI change — and it would be a change nobody pre-registered."""
    ordering_modules = [
        _REPO / "frontend/lib/draft-optimizer.ts",
        _REPO / "frontend/lib/big-board.ts",
        _REPO / "frontend/lib/auction-optimizer.ts",
        _REPO / "frontend/lib/league-scoring.ts",
        _REPO / "frontend/lib/roster-report.ts",
    ]
    present = [m for m in ordering_modules if m.exists()]
    assert len(present) >= 4, (
        f"only {len(present)} ordering module(s) found — this clause would be scanning almost "
        f"nothing; the module list has drifted from the repo"
    )
    for path in present:
        src = _strip_ts_comments(path.read_text())
        assert "availabilityTier" not in src, (
            f"{path.name} imports the availability classifier — it is DISPLAY ONLY and must never "
            f"reach VOR, the ordering, tiering or the optimizer"
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Coverage — the registry, and the exhaustiveness check that keeps it honest
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("filename", _GAMES_SURFACES)
def test_every_games_surface_renders_the_shared_flag(filename):
    """⚠️ THE BINDING, NOT THE IMPORT — the weaker form is what `test_expected_points_label_copy`
    shipped and the red proof caught. A bare `"AvailabilityFlag" in src` is satisfied by the import
    statement alone, so a surface that imports it and then renders a bare `numOrLock(p.g, …)` would
    pass. Matching the JSX element requires it to reach the render."""
    src = _strip_ts_comments((_FANTASY_COMPONENTS / filename).read_text())
    assert re.search(r"<AvailabilityFlag\b", src), (
        f"{filename} renders a projected-games value without the availability flag — the "
        f"discount is invisible on that surface (importing the component is not rendering it)"
    )


@pytest.mark.parametrize("filename", _GAMES_SURFACES)
def test_no_games_surface_still_renders_the_bare_unflagged_figure(filename):
    """The retired form. A surface carrying BOTH the flag and a leftover `numOrLock(p.g, …)` would
    satisfy the clause above while leaving a second, unflagged games cell on the page — which is
    exactly how a partially-migrated surface ships looking finished."""
    src = _strip_ts_comments((_FANTASY_COMPONENTS / filename).read_text())
    assert not re.search(r"numOrLock\(\s*(?:p|proj|row)\.g\b", src), (
        f"{filename} still renders a projected-games figure through the bare `numOrLock` the flag "
        f"replaced"
    )


def test_the_games_surface_registry_is_still_exhaustive():
    """⭐ THE CLAUSE THAT MAKES THE REGISTRY WORTH HAVING (INC-38): a per-surface fix fails exactly
    where the registry is incomplete, so the registry needs a guard rather than the author's memory.
    Any fantasy component reading a games value in REAL CODE is either a registered carrier or an
    exemption with a written reason — never an unnoticed third thing."""
    known = set(_GAMES_SURFACES) | set(_GAMES_SURFACE_EXEMPTIONS)
    unregistered = {}
    for path in sorted(_FANTASY_COMPONENTS.glob("*.tsx")):
        if path.name in known:
            continue
        src = _strip_ts_comments(path.read_text())
        # The two shapes a games VALUE is rendered in today: the board/projection row field and the
        # track-record export's own key.
        hits = re.findall(r"(?:numOrLock|num|int)\(\s*\w+\.(?:g|projGames)\b", src)
        if hits:
            unregistered[path.name] = hits
    assert not unregistered, (
        f"these fantasy surfaces render a projected-games value and are in neither the flag "
        f"registry nor the exemption list: {unregistered}. Either wire `AvailabilityFlag` and add "
        f"them to _GAMES_SURFACES, or record why the flag does not apply in "
        f"_GAMES_SURFACE_EXEMPTIONS."
    )


def test_every_exemption_states_a_reason():
    """An exemption list whose entries are bare filenames is a list of surfaces nobody has to
    justify. Each one records WHY the flag does not apply, and the clause is what stops the next
    entry being added without one."""
    for name, reason in _GAMES_SURFACE_EXEMPTIONS.items():
        assert (_FANTASY_COMPONENTS / name).exists(), (
            f"{name} is exempted from the availability flag but no longer exists — a stale "
            f"exemption silently widens the hole it names"
        )
        assert len(reason) > 25, f"the exemption for {name} does not state a reason"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The definition is TAPPABLE, and its prose is the canonical constant
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_flag_definition_travels_through_infotip_and_not_a_hover_only_tooltip():
    """E9.63/NF3's touch lesson, and it is the difference between a fix and a decoration: Radix's
    Tooltip closes on pointerdown by design, so a tap can never open one, and a `title=` attribute
    is hover-only too. A phone reader — who cannot hover — would meet a coloured number with no way
    to find out what the colour means, which is strictly worse than the grey number it replaced."""
    src = _strip_ts_comments(_SHARED_TSX.read_text())
    flag = src.split("export function AvailabilityFlag", 1)
    assert len(flag) == 2, "AvailabilityFlag is not exported from shared.tsx"
    body = flag[1].split("\nexport ", 1)[0]
    assert "<InfoTip" in body, (
        "the availability flag no longer renders its definition through InfoTip — a hover-only "
        "tooltip is unreachable on the phone this flag is mostly read on"
    )
    assert "title=" not in body, "the flag's definition is on a hover-only `title` attribute"


def test_the_flag_prose_is_the_canonical_constants_and_not_retyped():
    """Pasting the wording into the component would put the single most dangerous sentence in the
    fantasy product — the one that must not become an injury forecast — outside every clause in this
    file and outside `test_nf_tr1_claim_copy.py`'s whole-module screen."""
    src = _strip_ts_comments(_SHARED_TSX.read_text())
    body = src.split("export function AvailabilityFlag", 1)[1].split("\nexport ", 1)[0]
    for name in ("AVAILABILITY_FLAG_SUMMARY", "AVAILABILITY_FLAG_DEFINITION"):
        assert name in body, f"the flag does not render {name}; its prose has been re-typed"


def test_the_flag_falls_through_to_the_plain_figure_rather_than_rendering_nothing():
    """⚠️ THE QUIET REGRESSION THIS STORY COULD SHIP. `AvailabilityFlag` REPLACED the games cell on
    three surfaces; if it returned `null` for an unflagged row, ~95% of every board would lose its
    games column outright — and it would look deliberate, because an empty cell always does. It
    renders the ordinary `numOrLock` output instead, which is also what keeps a LOCKED row's
    subscribe chip and an absent `g`'s em-dash working unchanged."""
    src = _strip_ts_comments(_SHARED_TSX.read_text())
    body = src.split("export function AvailabilityFlag", 1)[1].split("\nexport ", 1)[0]
    assert re.search(r"if\s*\(\s*tier\s*==\s*null\s*\)\s*return\s*<>\{numOrLock\(", body), (
        "AvailabilityFlag no longer falls through to the plain `numOrLock` figure on an unflagged "
        "row — an unflagged board would render an empty games column"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The freshness line — visible staleness, and the absent/null distinction
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_flag_reads_back_the_injury_vintage_the_exporter_already_stamps():
    """NF-FRESH2 stamped `sleeper_status_as_of` into the payload and NOTHING ever read it back — a
    stamp nothing reads is not a freshness guarantee (NF-INJ1). The flag rests on that feed more
    directly than any other surface does, so it is where the vintage belongs."""
    src = _strip_ts_comments(_SHARED_TSX.read_text())
    assert "sleeper_status_as_of" in src, (
        "the availability flag does not read the injury-status vintage — staleness in the one feed "
        "this flag rests on would again be invisible"
    )


def test_an_absent_vintage_key_renders_nothing_and_a_null_one_renders_unknown():
    """⚠️ NF-FRESH2's absent-vs-null rule, and both directions are load-bearing:
      • KEY ABSENT (an older payload, or an NF-C0 deploy-skew window) → emit nothing. Inventing
        "unknown" would put a scary word under every flag during a routine deploy.
      • VALUE NULL (the exporter looked and could not tell) → emit "unknown". Dropping it silently
        would let a missing stamp read as covered — an unevaluable check is never scored healthy
        (NF1.7 (a))."""
    src = _strip_ts_comments(_SHARED_TSX.read_text())
    body = src.split("export function availabilityAsOfLine", 1)
    assert len(body) == 2, "availabilityAsOfLine is not exported from shared.tsx"
    fn = body[1].split("\nexport ", 1)[0]
    assert '"sleeper_status_as_of" in vintage' in fn, (
        "availabilityAsOfLine does not distinguish an ABSENT key from a NULL value — a payload "
        "that never carried the stamp would be described as unknown"
    )
    assert "AVAILABILITY_DATA_AS_OF_UNKNOWN" in fn, (
        "a null/unparseable vintage no longer renders as unknown — it is being silently dropped, "
        "which lets a missing stamp read as covered"
    )
