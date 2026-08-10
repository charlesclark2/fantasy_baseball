"""E9.61 — the "vs our generic board" delta: WHO renders it, and what must stay off the edge.

══ WHY THIS IS ITS OWN FILE ══════════════════════════════════════════════════════════════════════

The nearest existing guard is `test_freemium_tier.py`, and bolting these clauses onto it would be
the E9.60 coupling trap: a requirement from THIS story failing under THAT story's name sends the
next reader to the wrong spec, and a fixture change made for one silently re-decides the other.
Each story's clauses live under its own name.

══ WHAT IS AT RISK ═══════════════════════════════════════════════════════════════════════════════

E9.61 put a PERSONALIZATION renderer onto `/fantasy/rankings`, which is a PUBLIC route. Two things
therefore have to stay true, and neither is enforced by a check anyone wrote in the component:

  1. THE RENDERER SET IS CLOSED. The freemium build's own lesson is that a tier is enforced by WHICH
     COMPONENT RENDERS — #681 gated one of three renderers and looked finished. So the three
     renderers are enumerated here; a fourth has to be added deliberately, with its gate.
  2. THE EDGE CANNOT ASK A PER-CALLER QUESTION. The delta reads one per-caller endpoint
     (`/fantasy/leagues`). If that ever became shared-cacheable or degrade-allowlisted, one caller's
     league could be served to another from a CDN entry — the breach `cache_control_for` exists to
     prevent, arriving through a config line rather than through code.

⚠️ EVERY CLAUSE BELOW IS RED-PROVEN by deliberately breaking the source it names (see
`e9_61_generic_delta_red_proof.py`). Two of them were written wrong first and only the red proof
said so, which is the whole argument for running it.
"""

import re
from pathlib import Path

import pytest

from app.backend.services import cost_guardrails

_REPO = Path(__file__).resolve().parents[2]
_FRONTEND = _REPO / "frontend"

pytestmark = pytest.mark.skipif(not _FRONTEND.is_dir(), reason="frontend/ not present")


def _code(rel: str) -> str:
    """Frontend source with comments stripped.

    ⚠️ COMMENTS ARE STRIPPED FOR THE REASON INC-38 RECORDS: a source-inspection guard that matches
    anywhere in the file can be satisfied by PROSE, so the explanatory comment written above a fix
    keeps the guard green after the fix itself is deleted. Line comments first, then block comments
    — the other order lets a `//`-commented `/*` swallow real code.
    """
    text = (_FRONTEND / rel).read_text()
    text = "\n".join(re.sub(r"//.*$", "", ln) for ln in text.splitlines())
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return text


#: The module that OWNS the delta's rendering — label, chip, cell, band.
_DELTA_UI = "components/fantasy/league-delta-ui.tsx"

#: Every component that may render the delta, and how each one is gated.
#:
#: ⭐ AXIS ONE OF TWO: what RENDERS personalization. (Axis two — what CREATES a personalized league —
#: is deliberately absent from this story: E9.61 adds no creation path, and `test_g100_c1_free_league`
#: owns the two that exist. Recorded here so "we only checked one axis" cannot be true by omission.)
_DELTA_RENDERERS = {
    # The activation screen. Its whole page is behind `FantasyLeagueGuard`, so the delta needs no
    # per-render condition of its own — the surface cannot be reached without a league.
    "components/fantasy/my-league.tsx": "page-gated",
    # PUBLIC route. The delta must be conditional on a custom league being selected.
    "components/fantasy/rankings-board.tsx": "isCustom",
    # `FantasyGuard`-gated, but conditional anyway: on a preset the comparison is a wall of zeroes.
    "components/fantasy/league-board.tsx": "isCustom",
}


def _renderers_found() -> set[str]:
    """Every frontend component that imports the delta UI. The greppable inverse of the list above —
    an omission-proof enumeration rather than a remembered one."""
    found = set()
    for path in (_FRONTEND / "components").rglob("*.tsx"):
        rel = str(path.relative_to(_FRONTEND)).replace("\\", "/")
        if rel == _DELTA_UI:
            continue
        if "components/fantasy/league-delta-ui" in _code(rel):
            found.add(rel)
    return found


def test_exactly_the_declared_components_render_the_delta():
    """A NEW renderer of a personalization surface has to be a deliberate act.

    This is the clause #681 needed and did not have: the tier is enforced by which component draws
    the thing, so the set has to be enumerable in one command and asserted, not remembered.
    """
    assert _renderers_found() == set(_DELTA_RENDERERS), (
        "the set of components rendering the generic-vs-your-league delta has changed — add it to "
        "_DELTA_RENDERERS with its gate, or remove it"
    )


@pytest.mark.parametrize(
    "component", [c for c, gate in _DELTA_RENDERERS.items() if gate == "isCustom"]
)
def test_a_browse_board_only_computes_the_delta_for_a_custom_league(component):
    """The gate on the two BROWSE boards, which are not (Rankings) or not only (League Board)
    protected by their page guard.

    ⚠️ ASSERTED ON `computeLeagueDelta`'S CALL, NOT ON THE RENDER. Hiding a computed delta in JSX
    would satisfy a "the band is conditional" check while still doing the per-caller work — and, on
    Rankings, still issuing the extra board fetch on the highest-traffic anonymous surface in the
    product. The condition has to sit on the COMPUTATION.
    """
    code = _code(component)
    call = re.search(r"isCustom[^\n]*\n?[^\n]*computeLeagueDelta", code)
    assert call, (
        f"{component} calls computeLeagueDelta without an isCustom condition — a public/preset "
        "caller would get a personalized comparison computed for them"
    )


@pytest.mark.parametrize("component", list(_DELTA_RENDERERS))
def test_no_renderer_spells_the_label_itself(component):
    """One quantity, one name.

    My League shipped this column as "vs free board" and the two boards would have arrived with
    whatever their author typed. The same number under three names on adjacent pages is how a reader
    concludes they are three different numbers, so the label is a shared constant and a literal in a
    renderer is a drift that has already begun.
    """
    code = _code(component)
    assert "GENERIC_DELTA_LABEL" in code, f"{component} does not use the shared delta label"
    for literal in ('"vs free board"', '"vs generic board"', '"vs ADP"', '"Move"', '"Δ"'):
        assert literal not in code, f"{component} hardcodes a delta label ({literal})"


def test_the_label_names_the_comparison_rather_than_inheriting_the_market_reading():
    """⛔ `best_alpha = 0`. Every other delta column in this product — and in the category — means
    "versus ADP". This one is the distance between two of OUR boards, so an ambiguous header would
    turn it into an implied claim about where the market is wrong."""
    copy = _code("lib/fantasy-claim-copy.ts")
    m = re.search(r'GENERIC_DELTA_LABEL\s*=\s*"([^"]+)"', copy)
    assert m, "GENERIC_DELTA_LABEL is gone"
    label = m.group(1).lower()
    assert "generic" in label, f"the delta label ({m.group(1)!r}) does not name what it compares"
    assert "adp" not in label, "the delta label claims an ADP comparison, which it is not"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The delta has to still be there on the SECOND visit
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# A column that renders once and is gone after a reload is worse than no column: it reads as the
# product being unreliable rather than as a feature that is missing. Both clauses below were
# MEASURED broken on the real build while this story was being written.


def _selection_hook() -> str:
    code = _code("lib/fantasy-queries.ts")
    return code[code.index("export function useFormatSelection") : code.index("const persist =")]


def test_the_initial_selection_waits_for_the_caller_s_own_leagues():
    """⭐ THE RACE. The hook commits a selection the first time it sees a manifest and then locks
    itself out (`configName !== null`). Saved leagues are a SECOND request, and the slower one — the
    manifest is CDN-cached and this is not — so without a deferral a stored `custom:<id>` is matched
    against an empty list, the caller is put on a preset, and the effect re-runs only to return
    immediately. The delta simply is not there the second time, with no error.

    ⚠️ ASSERTED ON THE `isLoading` SPELLING TOO, because `isPending` is the plausible wrong one and
    it fails the other way: a DISABLED query (an anonymous visitor — `enabled: !!accessToken`) is
    pending forever, so gating on it would hang the format picker on every logged-out page load.
    """
    body = _selection_hook()
    assert re.search(r"if\s*\(savedLeaguesLoading\)\s*return", body), (
        "the selection commits before the caller's leagues have arrived — a stored custom league "
        "loses the race and the personalized board silently reverts to a preset"
    )
    for component in (c for c, gate in _DELTA_RENDERERS.items() if gate == "isCustom"):
        code = _code(component)
        assert re.search(r"isLoading:\s*savedLeaguesLoading", code), (
            f"{component} does not pass the saved-league loading flag (or uses isPending, which is "
            "true forever for an anonymous caller's disabled query)"
        )


def test_an_unentitled_caller_s_own_league_is_restored_from_storage():
    """The positive half of the clause `test_freemium_tier` narrowed at E9.61.

    That guard forbids the unentitled branch honouring a stored PAID PRESET, and used to enforce it
    by requiring the branch not to read `stored` at all. G100-C1 made one restore legitimate — a free
    account owns ONE personalized league — so the prohibition is now scoped to presets and THIS is
    what keeps the permitted case from being 'simplified' away again. Deliberately in E9.61's own
    file: the requirement is this story's, and a clause failing under another story's name sends the
    next reader to the wrong spec.
    """
    body = _selection_hook()
    branch = body[body.index("if (!entitled && free)") :]
    branch = branch[: branch.index("names.includes(free.config)")]
    assert re.search(r"customIds\.has\(\s*stored\.configName\s*\)", branch), (
        "an unentitled caller's own saved league is no longer restored — they are returned to the "
        "generic preset on every reload, and the personalized board they are entitled to is gone"
    )
    assert "setConfigName(stored.configName)" in branch, (
        "the branch tests the stored league but never selects it"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The edge must not be able to ask a per-caller question
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: The read that makes a `custom:` selection possible at all. Per-caller, therefore never shared.
_PERSONALIZATION_PATHS = ("/fantasy/leagues", "/fantasy/nfl/my-teams")


@pytest.mark.parametrize("path", _PERSONALIZATION_PATHS)
def test_a_personalization_read_is_never_shared_cacheable(path):
    """A CDN entry for one caller's league, served to the next visitor, is a data breach caused
    entirely by a caching header. `public_cache_control` must decline these outright — belt as well
    as the braces of `cache_control_for`'s `Authorization` check below."""
    assert cost_guardrails.public_cache_control(path) is None, (
        f"{path} became shared-cacheable — one caller's league can be served to another"
    )


@pytest.mark.parametrize("path", _PERSONALIZATION_PATHS)
def test_an_authenticated_read_of_one_is_private_no_store(path):
    """The braces. Even if a prefix were added above, a request carrying `Authorization` must still
    resolve to `private, no-store` — the two halves are independent and both are required."""
    assert (
        cost_guardrails.cache_control_for(path, has_authorization=True, status_code=200)
        == cost_guardrails.PRIVATE_CACHE_CONTROL
    )


def test_the_delta_added_no_new_endpoint_to_the_degrade_floor():
    """Degrade mode is the spend kill switch, and its allowlist is "cheap AND the floor we promise".

    The delta is deliberately built from reads that were ALREADY classified: the free preset board
    (allowlisted, a single S3 GetObject of the same bytes for everyone) and the caller's saved
    leagues (not allowlisted — personalization is not the floor). Adding the latter would keep a
    per-caller DynamoDB read alive during a cost event AND put a personalization surface inside the
    promise the floor makes.
    """
    for path in _PERSONALIZATION_PATHS:
        assert not cost_guardrails.is_allowed_in_degrade(path), (
            f"{path} joined the degrade floor — personalization is not the floor we promise"
        )
    # The other side of the clause: a gate that refused EVERYTHING would satisfy the loop above.
    assert cost_guardrails.is_allowed_in_degrade("/fantasy/nfl/board"), (
        "the free board left the degrade floor — the delta's generic side must stay up"
    )


# ── item 2: the VOR-delta highlights, and the noise floor a REAL-DATA run forced ─────────────────
#
# The highlights rank on VOR delta rather than rank movement (see `HIGHLIGHTS_RANK_BY_VOR`). Running
# the SHIPPED `buildBoard` + `computeLeagueDelta` over the LIVE 2026 payloads — which the e2e
# fixtures structurally cannot do, their two boards being on incompatible point scales — surfaced a
# defect the fixture suite could never see, so these clauses live here rather than in e2e.
#
# MEASURED (858 players, five league shapes, plus a control league identical to the free preset):
#   * the control's true delta is 0 for every player, yet it RECONSTRUCTS at p50 0.30 / max 1.70,
#     because the generic side arrives rounded to 1dp from the API while the league side is
#     re-scored in the browser from the raw stat line;
#   * so a superflex league (quarterbacks rise, nobody's value falls) filled its "Worth less in your
#     league" column with five players at 0.6–0.7, and a 3-WR league filled it with tight ends
#     at 0.5 — a heading, five names and an explanation, over rounding;
#   * at a floor of 2.0 none of the 858 control players survive and nothing real is lost: the
#     smallest GENUINE highlight across the five leagues measured 4.1.

_LEAGUE_DELTA = "lib/league-delta.ts"
_MY_LEAGUE = "components/fantasy/my-league.tsx"


def test_the_highlights_rank_on_value_not_on_rank_movement():
    """Item 2 itself. Rank movement is a density-dependent proxy — both prior highlight defects
    (deep-tail churn, then K/DST) were that proxy misbehaving and each needed its own exclusion."""
    src = (_FRONTEND / _LEAGUE_DELTA).read_text()
    body = _code(_LEAGUE_DELTA)
    assert "HIGHLIGHTS_RANK_BY_VOR" in src, "the rationale constant is gone"
    for side in ("risers", "fallers"):
        block = body[body.index(f"const {side} = valued"):]
        block = block[: block.index(".slice(")]
        assert "vorDelta" in block, f"{side} no longer sorts on VOR"
        assert "ovrDelta" not in block, f"{side} went back to sorting on rank movement"


def test_a_highlight_must_clear_the_measured_reconstruction_noise():
    """⭐ The floor exists because the two sides of the delta are BUILT DIFFERENTLY, so "no change"
    does not reconstruct as exactly zero. Without it a league that genuinely moves value in one
    direction still prints a fabricated list in the other."""
    body = _code(_LEAGUE_DELTA)
    assert re.search(r"MIN_HIGHLIGHT_VOR_DELTA\s*=\s*2\b", body), \
        "the noise floor is gone or is no longer the measured value"
    gate = body[body.index("const valued = comparable.filter"):]
    gate = gate[: gate.index(")\n")]
    assert "MIN_HIGHLIGHT_VOR_DELTA" in gate and "Math.abs" in gate, (
        "highlight eligibility no longer applies the floor — a two-sided |delta| test is required, "
        "since a one-sided one would filter only risers or only fallers"
    )


def test_the_floor_is_documented_as_measured_rather_than_chosen():
    """A magic threshold nobody can re-derive is un-maintainable: the right value is a function of
    how many decimals the board export publishes, so the measurement and that dependency have to
    travel with the constant."""
    src = (_FRONTEND / _LEAGUE_DELTA).read_text()
    doc = src[: src.index("export const MIN_HIGHLIGHT_VOR_DELTA")]
    doc = doc[doc.rindex("/**"):]
    assert "1.70" in doc, "the measured noise maximum is no longer recorded beside the floor"
    assert "858" in doc, "the population the floor was measured over is no longer recorded"
    assert "4.1" in doc, "the smallest GENUINE highlight is no longer recorded — without it the "\
                         "floor cannot be shown to cost nothing"


@pytest.mark.parametrize("side", ["risers", "fallers"])
def test_each_highlight_column_has_its_own_empty_state(side):
    """The floor makes a ONE-SIDED result common (measured: superflex and 3-WR both lift a position
    and lower nothing), so a column can be legitimately empty while its neighbour is full. Rendering
    a bare heading over nothing reads as a bug; each side says so in words instead."""
    src = (_FRONTEND / _MY_LEAGUE).read_text()
    marker = f'data-testid="{side}-none"'
    assert marker in src, f"the {side} column has no empty state"

    # ⚠️ PRESENCE OF THE MARKUP IS NOT THE CLAUSE — this guard's first cut asserted only that, and
    # the red proof caught it: rewriting the condition to `{false ? (` leaves the empty-state <p>
    # sitting in the file, unreachable, and the guard scored it healthy. (Reading back a substring
    # the source still contains is the "assert the render, not the import" trap.) So walk BACK from
    # the marker to the condition that actually guards it — and note the naive
    # `src.index(f"delta.{side}.length === 0")` finds the EARLIER both-columns-empty check first,
    # because `delta.risers.length + delta.fallers.length === 0` contains that exact substring.
    guard = src[max(0, src.index(marker) - 240) : src.index(marker)]
    assert f"delta.{side}.length === 0 ? (" in guard, (
        f"the {side} empty state is no longer conditioned on that column being empty — the markup "
        f"is present but unreachable"
    )
    body = src[src.index(marker) : src.index(marker) + 240]
    assert "Nothing is worth meaningfully" in body, (
        f"the {side} empty state no longer says plainly that nothing cleared the floor"
    )
