"""The EXPECTED-POINTS labelling — copy governance + surface coverage, as executable clauses.

NF-TR1's public track record surfaced the problem this suite defends: our published point total is
an EXPECTED season total (the chance a player misses games is multiplied through it), so it sits
structurally below both an "if he plays every week" projection and a healthy player's finished
season. Unlabelled, a reader meets a projection far under a real outcome and concludes the model is
broken. It is not — but the number was shipped with nothing beside it saying so.

The remedy is a LABEL, and a label has exactly two ways to fail, both silent:

  1. IT OVERCLAIMS. Availability carries most of the measured level shift and NOT all of it — a
     residual remains at the worst position, and that residual is a genuine miscalibration with its
     own carded model story. Copy implying "the games column accounts for the difference" would use
     an honest mechanism to bury a dishonest amount. That is worse than the unlabelled number,
     because it converts a visible anomaly into an invisible one.
  2. IT MISSES A SURFACE. The label is worth what its coverage is worth: one board still reading
     "Proj pts" is one board on which the whole misread survives. Coverage is therefore a REGISTRY
     with an exhaustiveness check, not a set of one-off greps (INC-38's per-caller-flag lesson: a
     per-surface fix fails exactly where the registry is incomplete).

⭐ ONE FIXTURE PER CLAUSE (NF-D17 §7). Several rules here are conjunctions, and a fixture that trips
two clauses at once tests NEITHER — the first refusal hides the second. Each clause below is
written so that deleting the ONE thing it names turns it, and only it, red.

⭐ COMMENTS ARE STRIPPED BEFORE EVERY SOURCE MATCH (INC-38). The components' own comments quote the
old labels verbatim while explaining why they were replaced; a raw substring scan would be
satisfied by that prose and stay green with the labelling reverted.

Pure/offline (fast gate): reads source files, no DuckDB/S3/network.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as ex

_REPO = Path(__file__).resolve().parents[2]
_CLAIM_COPY_TS = _REPO / "frontend/lib/fantasy-claim-copy.ts"
_SHARED_TSX = _REPO / "frontend/components/fantasy/shared.tsx"
_FANTASY_COMPONENTS = _REPO / "frontend/components/fantasy"

#: Every fantasy surface that renders a projected-points figure, and how it must label it.
#:
#: ⭐ A REGISTRY, NOT A LIST OF GREPS — and it is pinned by its own exhaustiveness clause below, so
#: a surface added later cannot quietly ship with the old wording. `label_constant` names the
#: surfaces that render the number in a COLUMN/heading (which get the canonical constant and the
#: tappable definition); `label_literal` names the one that cannot.
_POINTS_SURFACES: tuple[tuple[str, str], ...] = (
    ("track-record-page.tsx", "label_constant"),
    ("projections-table.tsx", "label_constant"),
    ("rankings-board.tsx", "label_constant"),
    ("league-board.tsx", "label_constant"),
    ("player-page.tsx", "label_constant"),
    ("my-teams.tsx", "label_constant"),
    # ⚠️ THE ONE EXCEPTION, and it is a structural one rather than an oversight: the search
    # result's points chip lives INSIDE the result's `<Link>`, and `InfoTip` renders a real
    # `<button>` — nesting one in an anchor is invalid HTML and a tap on the definition would
    # navigate instead of open. It carries the WORD, and the definition is one tap away on the
    # player page it links to.
    ("player-search.tsx", "label_literal"),
)

#: The wordings this story retired. A surviving occurrence (in real code, not in a comment) is a
#: surface the labelling missed.
_RETIRED_LABELS = ("Our pts", "Proj pts", "Proj. pts", "Proj (PPR)")


def _strip_ts_comments(src: str) -> str:
    """⚠️ INC-38: a source-inspection guard a COMMENT can satisfy cannot fail. Every component
    touched here explains itself by quoting the label it replaced, so the retired wordings appear
    all over the prose — the scans below must never see it.

    ⚠️⚠️ LINE COMMENTS COME OFF **FIRST**, AND THAT ORDER IS THE WHOLE FUNCTION. Stripping block
    comments first is the obvious implementation and it is BLIND IN THE DANGEROUS DIRECTION: a `//`
    comment containing a path glob — `draft-optimizer.tsx` line 69 has a real one, "(/fantasy/nfl/*,
    require_fantasy_access)" — opens a `/*` that `/\\*.*?\\*/` happily closes at the next genuine
    `*/`, DELETING every line between. Measured on that file: 55 lines of live code vanished,
    including the one a red-proof case had just broken, so the registry clause reported GREEN
    against a defect physically present on disk. Found by the red proof, not by review.

    `(?<!:)` keeps `https://` (and any other scheme) from being read as a comment."""
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
# The extractor itself — an extractor that silently returns nothing makes every clause below
# vacuously true (NF1.7 (a)). Checked first, on purpose.
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_copy_extractor_actually_finds_the_new_constants(copy_src):
    for name in ("EXPECTED_POINTS_DEFINITION", "PROJECTED_GAMES_DEFINITION", "EXPECTED_POINTS_NOTE"):
        assert len(_const(copy_src, name)) > 100, f"{name} extracted as near-empty prose"


def test_the_comment_stripper_removes_prose_that_would_satisfy_a_scan():
    """The stripper is what separates "this file labels its column" from "this file has a comment
    about labelling". Proven on a synthetic in both forms, so a regression in the stripper shows up
    here rather than as a silently-passing coverage clause."""
    src = '// <th>Proj pts</th>\n/* Proj pts */\nconst real = "Expected pts"\n'
    assert "Proj pts" not in _strip_ts_comments(src)
    assert "Expected pts" in _strip_ts_comments(src)


def test_the_comment_stripper_does_not_eat_code_after_a_path_glob_in_a_line_comment():
    """⚠️ A REAL DEFECT THIS SUITE SHIPPED AND THE RED PROOF CAUGHT — pinned so it cannot return.

    `// … (/fantasy/nfl/*, require_fantasy_access)` is ordinary prose in this codebase, and it
    contains `/*`. A stripper that removes BLOCK comments first reads that as an opening delimiter
    and deletes everything up to the next genuine `*/` — 55 lines of live code in
    `draft-optimizer.tsx`. The coverage clauses would then be scanning a source with the very lines
    they police silently removed: green against a defect physically present on disk, the worst
    failure shape a guard has.

    Also pins the `https://` case the ordering fix has to preserve."""
    src = (
        "// boards load through the gated backend (/fantasy/nfl/*, require_fantasy_access)\n"
        'const heading = "Proj pts"\n'
        'const doc = "https://example.com/docs"\n'
        "/* a real block comment mentioning Our pts */\n"
    )
    out = _strip_ts_comments(src)
    assert "Proj pts" in out, "code after a path glob in a line comment was swallowed"
    assert "https://example.com/docs" in out, "a URL was mistaken for a line comment"
    assert "Our pts" not in out, "a genuine block comment survived"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The copy may not overclaim — the failure that would make this story harmful
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_note_states_that_availability_is_not_the_whole_story(copy_src):
    """⛔⛔ THE LOAD-BEARING CLAUSE OF THIS ENTIRE STORY.

    Availability carries most of the measured level shift; a residual remains at the worst position
    and it is a real miscalibration, carded as its own model story. A page that let a reader infer
    the games column accounts for the whole difference would have used an honest mechanism to bury
    a dishonest amount — strictly worse than shipping the number unexplained, because the anomaly
    stops being visible.

    Held on the NOTE specifically (the page-level block a track-record reader meets beside a
    finished season's real total), not on the definitions, because that is the only place the two
    numbers sit side by side."""
    note = _const(copy_src, "EXPECTED_POINTS_NOTE")
    assert "not the only reason" in note, (
        "the expected-points note no longer says availability is not the only reason a projection "
        "lands under a finished season — without that sentence the label overclaims"
    )


def test_the_note_does_not_promise_the_games_column_explains_the_gap(copy_src):
    """The other direction of the same rule: not merely "a hedge is present" but "no sentence
    contradicts it". A note carrying the hedge AND a phrase like "which is why our number is lower
    than the final total" would satisfy the clause above and still mislead."""
    note = _const(copy_src, "EXPECTED_POINTS_NOTE")
    for forbidden in ("accounts for the difference", "explains the difference", "explains the gap",
                      "accounts for the gap", "fully explains", "entirely explained"):
        assert forbidden not in note, (
            f"the note claims availability {forbidden!r} — it does not, and a residual "
            f"miscalibration is not something a label may absorb"
        )


def test_the_framing_is_a_disclosure_and_not_an_apology(copy_src):
    """⭐ THE STORY'S OWN FRAMING RULE. Pricing missed games in is a choice we would defend, and the
    copy states why we prefer it. Apologising for the number gives away exactly the trust the
    disclosure is meant to earn — and is the most natural way for a later edit to soften it."""
    for name in ("EXPECTED_POINTS_NOTE", "EXPECTED_POINTS_DEFINITION"):
        prose = _const(copy_src, name)
        for apology in ("sorry", "apolog", "unfortunately", "we know this looks", "our fault"):
            assert apology not in prose, f"{name} apologises for the projection ({apology!r})"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The copy must actually SAY the thing — a label that explains nothing is decoration
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_definition_names_missed_games_as_the_reason_the_number_is_lower(copy_src):
    """Both halves, and they are separate failures: a definition that says "expected points"
    without naming missed games explains nothing, and one that names missed games without saying it
    makes our number LOWER leaves the reader's actual question — "why is this under what everyone
    else publishes?" — unanswered."""
    d = _const(copy_src, "EXPECTED_POINTS_DEFINITION")
    assert "misses games" in d or "missed games" in d, (
        "the definition does not name missed games as what is priced in"
    )
    assert "lower" in d, "the definition does not tell the reader our number is deliberately lower"


def test_the_projected_games_definition_explains_the_fractional_value(copy_src):
    """The games figure renders as e.g. 13.9, and "you cannot play nine tenths of a game" is the
    first thing a reader thinks. It is an expectation across outcomes, and the definition says so —
    otherwise the column that exists to make the points number legible needs explaining itself."""
    g = _const(copy_src, "PROJECTED_GAMES_DEFINITION")
    assert "average" in g or "expectation" in g, (
        "the projected-games definition does not explain that it is an expectation, so a "
        "fractional games value reads as an error"
    )


def test_the_new_copy_carries_no_measured_figure(copy_src):
    """⛔ E9.56b/NF-D3, applied to this story's strings: no per-position ratio, no games average, no
    bias number. The SIZE of the discount is shown by rendering the served per-player `projGames`
    beside the points — a figure read from the artifact, which cannot drift the way a typed one
    would. (`test_nf_tr1_claim_copy.py` scans the whole module; this names the new constants so a
    red run points at them.)"""
    for name in ("EXPECTED_POINTS_DEFINITION", "PROJECTED_GAMES_DEFINITION", "EXPECTED_POINTS_NOTE",
                 "EXPECTED_POINTS_LABEL", "PROJECTED_GAMES_LABEL"):
        prose = _const(copy_src, name)
        assert not re.search(r"\d\.\d{2,}", prose), f"{name} hardcodes a measured figure"


def test_the_new_copy_passes_the_track_record_denylist(copy_src):
    """These strings ship on the PUBLIC track record beside a claim whose own interval includes
    zero, so they answer to the same screen as the claim itself."""
    for name in ("EXPECTED_POINTS_DEFINITION", "PROJECTED_GAMES_DEFINITION", "EXPECTED_POINTS_NOTE",
                 "EXPECTED_POINTS_LABEL", "PROJECTED_GAMES_LABEL"):
        prose = _const(copy_src, name)
        hits = [t for t in ex._CLAIM_DENYLIST if t in prose]
        assert not hits, f"{name} makes a forbidden claim {hits}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. ⛔ The methodology caution: the outcome-bucketed decile comparison is NOT citable
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_no_surface_cites_the_outcome_bucketed_decile_comparison():
    """⛔ Sorting players by their REALIZED outcome and comparing per-decile means shows a
    compression pattern even for a PERFECTLY calibrated projection — the top realized decile is
    selected for positive noise. It cannot distinguish bias from correct shrinkage, so it is not
    evidence of anything and must never appear on a user-facing surface. The honest per-position
    statistic is the unconditional mean, which the track-record page already uses.

    Scanned across the whole fantasy component tree rather than the files this story touched: the
    hazard is a FUTURE surface reaching for the most dramatic-looking table in the memo."""
    for path in sorted(_FANTASY_COMPONENTS.glob("*.tsx")) + [_CLAIM_COPY_TS]:
        text = _strip_ts_comments(path.read_text()).lower()
        for phrase in ("decile", "top 10% of finishers", "bucketed by outcome"):
            assert phrase not in text, (
                f"{path.name} cites the outcome-bucketed decile comparison ({phrase!r}) — that "
                f"pattern appears for a perfect projection too and cannot show bias"
            )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Coverage — the registry, and the exhaustiveness check that keeps it honest
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("filename,kind", _POINTS_SURFACES)
def test_every_points_surface_labels_its_number_as_expected(filename, kind):
    src = _strip_ts_comments((_FANTASY_COMPONENTS / filename).read_text())
    if kind == "label_constant":
        # ⚠️ THE BINDING, NOT THE IMPORT — and this clause shipped the weaker form and was caught by
        # the red proof, exactly as NF-TR1's trust-link guard was. A bare
        # `"EXPECTED_POINTS_LABEL" in src` is satisfied by the IMPORT STATEMENT alone, so a surface
        # that imports the constant and then renders a hand-typed literal passes it. Matching
        # `label={…EXPECTED_POINTS_LABEL…}` requires the constant to reach the rendered attribute
        # (directly or inside a template literal, which is how the player page and My Teams use it).
        assert re.search(r"label=\{[^}]*EXPECTED_POINTS_LABEL", src), (
            f"{filename} does not BIND the canonical label constant into its rendered label — a "
            f"surface that re-types its own wording is a surface where the term can drift "
            f"(importing it is not using it)"
        )
    else:
        assert "Expected (PPR)" in src, f"{filename} does not label its points figure as expected"


def test_the_points_surface_registry_is_still_exhaustive():
    """⭐ THE CLAUSE THAT MAKES THE REGISTRY ABOVE WORTH HAVING (INC-38): a per-surface fix fails
    exactly where the registry is incomplete, so the registry needs its own guard rather than the
    author's memory. Any fantasy component still rendering one of the retired wordings in REAL CODE
    is a surface the labelling missed."""
    missed = {}
    for path in sorted(_FANTASY_COMPONENTS.glob("*.tsx")):
        src = _strip_ts_comments(path.read_text())
        hits = [lbl for lbl in _RETIRED_LABELS if lbl in src]
        if hits:
            missed[path.name] = hits
    assert not missed, (
        f"these fantasy surfaces still render a retired projected-points label: {missed}. Either "
        f"label them (and add them to _POINTS_SURFACES) or retire the wording."
    )


def test_the_definitions_are_the_canonical_constants_rather_than_retyped_prose():
    """The boards read their definitions from `GLOSSARY`, whose entries for these two terms must be
    the constants themselves. Pasting the prose into `shared.tsx` instead would put the single most
    load-bearing disclosure in the product outside every copy-governance check there is — including
    every clause in this file."""
    src = _strip_ts_comments(_SHARED_TSX.read_text())
    for glossary_key, constant in (("expectedPoints", "EXPECTED_POINTS_DEFINITION"),
                                   ("projectedGames", "PROJECTED_GAMES_DEFINITION")):
        assert re.search(rf"{glossary_key}:\s*{constant}\b", src), (
            f"GLOSSARY.{glossary_key} is not bound to {constant} — if it has been re-typed as a "
            f"string literal, the denylist and no-measured-figure screens no longer see it"
        )


def test_the_definition_is_tappable_and_not_a_hover_only_tooltip():
    """E9.63/NF3's touch lesson, and it is the difference between a fix and a decoration: Radix's
    Tooltip closes on pointerdown by design, so a tap can never open one. A phone reader — who
    cannot hover — would meet the identical unexplained number this story exists to explain.

    `InfoTip` is built on Popover for exactly this reason; the clause is that the definitions
    travel through IT, and never through a bare `title=` attribute (which is also hover-only)."""
    for filename, kind in _POINTS_SURFACES:
        if kind != "label_constant":
            continue
        src = _strip_ts_comments((_FANTASY_COMPONENTS / filename).read_text())
        assert re.search(r"<InfoTip[^>]*>\s*\{?GLOSSARY\.(expectedPoints|projectedGames)", src, re.S), (
            f"{filename} does not render the expected-points definition through InfoTip — a "
            f"hover-only tooltip leaves every phone reader with the original shock"
        )
        assert not re.search(r'title=\{?["\']?\{?GLOSSARY\.(expectedPoints|projectedGames)', src), (
            f"{filename} passes the definition as a `title` attribute, which is hover-only"
        )
