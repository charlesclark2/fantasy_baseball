"""E9.46 — COPY GOVERNANCE for the home page, the company's positioning surface.

NF-TR1 put the fantasy product's claims behind a screened copy module and a denylist. The home page
then became the one surface where BOTH verticals pitch at once — and the betting half had no such
module: its copy lived inline in `app/page.tsx` and led with "Daily edge, quantified", which is
precisely the claim `best_alpha = 0` forbids.

So this suite is the betting-side and platform-side twin of `test_nf_tr1_claim_copy.py`. It screens
`frontend/lib/home-copy.ts` the way that file screens `fantasy-claim-copy.ts`, and adds the clauses
that are specific to a home page: the featured pick must be framed as a demonstration rather than a
tout, the two verticals must both have a door, the coming-soon rows must not promise picks, and the
blog must be out of the primary nav without being deleted from the product.

⭐ EACH CLAUSE IS INDEPENDENTLY RED-PROVABLE, and that is a rule with a scar behind it (NF-D17 §7):
a guard on an `and`-composed condition passes with the clause it NAMES deleted whenever a different
clause already refuses the fixture. Every assertion below names exactly one thing and is written so
that removing that one thing turns it red; verified with
`uv run python betting_ml/tests/e9_46_home_copy_red_proof.py`.

⚠️ SOURCE-INSPECTION, SO COMMENTS ARE STRIPPED FIRST (INC-38). Both files under test DISCUSS these
rules at length in prose — `home-copy.ts` explains why "edge" is not used, by using the word — and
a raw substring search would be satisfied by the very comment explaining the rule.

Pure/offline (fast gate): reads source files only, no DuckDB/S3/network.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from betting_ml.governance import gates
from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as ex

_REPO = Path(__file__).resolve().parents[2]
_HOME_COPY_TS = _REPO / "frontend/lib/home-copy.ts"
_HOME_PAGE_TSX = _REPO / "frontend/app/page.tsx"
_PICK_COMPONENT_TSX = _REPO / "frontend/components/home/pick-of-the-day.tsx"
_NAV_TSX = _REPO / "frontend/components/nav.tsx"
_FOOTER_TSX = _REPO / "frontend/components/site-footer.tsx"
_CLAIM_COPY_TS = _REPO / "frontend/lib/fantasy-claim-copy.ts"
_NF_TR1_SUITE = _REPO / "betting_ml/tests/test_nf_tr1_claim_copy.py"


def _strip_ts_comments(src: str) -> str:
    """⚠️ LINE COMMENTS FIRST, then block comments — the opposite of the obvious order, and the
    order matters. A `//` comment containing a path glob or a URL fragment can open what the block
    regex reads as a comment and swallow everything up to the next close, silently deleting real
    source from the scan (measured elsewhere in this repo at 55 lines). Stripping `//` lines first
    removes that whole class."""
    src = "\n".join(line for line in src.split("\n") if not line.lstrip().startswith("//"))
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def _ts_string_literals(src: str) -> list[str]:
    """Every double-quoted string literal, comments stripped. Crude on purpose — a screening pass
    over prose constants, not a parser. Its own vacuity is asserted below."""
    return re.findall(r'"((?:[^"\\]|\\.)*)"', _strip_ts_comments(src))


@pytest.fixture(scope="module")
def home_literals() -> list[str]:
    return _ts_string_literals(_HOME_COPY_TS.read_text())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The guard on the guard
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_copy_module_scan_actually_finds_strings(home_literals):
    """⚠️ NF1.7 (a): an extractor that silently returned nothing would make every screening clause
    in this file vacuously true, and the file would read as coverage the whole time."""
    assert len(home_literals) >= 25, (
        f"only {len(home_literals)} string literal(s) extracted from the home copy module — the "
        f"screening below would be passing on nothing"
    )
    assert any("demonstration" in s for s in home_literals), (
        "the pick-of-the-day framing was not extracted — the scan is not reading the block that "
        "most needs screening"
    )


def test_the_comment_stripper_does_not_eat_real_source():
    """The other half of the vacuity guard, and a bug this repo has actually shipped: a stripper
    that swallowed the file would make every source-inspection clause below pass on an empty
    string."""
    stripped = _strip_ts_comments(_HOME_COPY_TS.read_text())
    assert "export const HERO" in stripped
    assert "export const SEASON_ROADMAP" in stripped
    assert len(stripped) > 0.25 * len(_HOME_COPY_TS.read_text()), (
        "comment stripping removed most of the file — a `//` line containing a block-comment "
        "opener is the usual cause"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC — the denylist applies to the BETTING-side copy too, not only the fantasy copy
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_home_copy_passes_the_denylist(home_literals):
    """The operator's rule is that the claim discipline spans BOTH verticals. Until E9.46 the
    denylist had only ever been run over fantasy copy."""
    for text in home_literals:
        hits = [t for t in ex._CLAIM_DENYLIST if t in text.lower()]
        assert not hits, f"home copy makes a forbidden claim {hits}: {text!r}"


def test_the_governance_gate_passes_the_home_copy(home_literals):
    """Run the ACTUAL promotion gate over the ACTUAL copy, not a re-implementation of its rule
    with the same word list."""
    result = gates.track_record_copy_compatible(home_literals)
    assert result.status == gates.PASS, result.detail


def test_that_gate_can_still_refuse_home_copy():
    """⚠️ A GATE THAT CANNOT FAIL IS NOT A GATE. The clause above is only evidence if the same call
    goes red on copy that should be refused."""
    bad = gates.track_record_copy_compatible(
        ["Credence beats the market on every position — profitable, guaranteed."]
    )
    assert bad.status == gates.FAIL


def test_the_page_and_component_carry_no_unscreened_prose():
    """⭐ THE HOLE THIS FILE EXISTS TO CLOSE. Screening a copy MODULE proves nothing if the page
    can write its own sentences inline — which is exactly what the pre-E9.46 page did.

    So: the long-form prose must live in a screened module. Enforced as a LENGTH rule on string
    literals in the JSX, because a heading ("Common questions") is fine and a paragraph is not, and
    the difference between them is length rather than kind. The threshold is set well above every
    label, badge and CTA the page renders and well below any real sentence."""
    for path in (_HOME_PAGE_TSX, _PICK_COMPONENT_TSX):
        long_literals = [
            s
            for s in _ts_string_literals(path.read_text())
            # Tailwind class strings are long, quoted, and not prose. They are identifiable by
            # having no sentence structure — no spaces around a lowercase word run with vowels is
            # too clever; keying on the absence of a sentence-ending or a comma is enough.
            if len(s) > 120 and not re.search(r"[a-z]-\[|text-|bg-|border-|grid-|flex", s)
        ]
        assert not long_literals, (
            f"{path.name} contains inline prose that no denylist screens: {long_literals[:2]}"
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC — the pick of the day is a TRANSPARENCY feature, not a tout
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_pick_is_framed_as_a_demonstration(home_literals):
    """⛔ The single most damaging thing this page could ship is a home page that tells a stranger
    to place this bet — it would contradict `best_alpha = 0` on the company's own front door. The
    disclaimer is therefore a required string, not a stylistic choice."""
    frame = next((s for s in home_literals if "demonstration" in s), None)
    assert frame, "the pick-of-the-day framing sentence is gone from the copy module"
    assert "not a recommendation" in frame.lower(), (
        f"the framing no longer disclaims a recommendation: {frame!r}"
    )


def test_the_pick_block_never_claims_an_advantage(home_literals):
    """The denylist catches the crude forms. This catches the comparative VERDICT words that would
    turn a transparency block back into a tout without tripping any banned phrase — the same shape
    NF-TR1 guards on the consensus hook, applied to the betting half."""
    pick_copy = " ".join(
        s for s in home_literals if "model" in s.lower() or "market" in s.lower()
    ).lower()
    assert pick_copy, "no pick copy extracted — this clause would be vacuous"
    for verdict in ("smarter than", "sharper than", "better than the market", "mispriced", "value bet"):
        assert verdict not in pick_copy, (
            f"the model-vs-market copy asserts a verdict ({verdict!r}) rather than a difference"
        )


def test_the_gap_is_named_as_a_difference_not_as_an_edge(home_literals):
    """⭐ The served field is literally called `edge` and the signed-in surfaces render it that way.
    On a marketing page "edge" reads as a claim to have one, and we do not have one to claim — six
    recorded no-edge results. The quantity is a difference between two probabilities, so it is
    labelled one."""
    labels = _strip_ts_comments(_HOME_COPY_TS.read_text()).split("labels:", 1)[1].split("}", 1)[0]
    assert '"Gap"' in labels, f"the model-vs-market quantity is no longer labelled 'Gap': {labels!r}"
    assert "edge" not in labels.lower(), f"the marketing label reintroduces 'edge': {labels!r}"


def test_the_home_page_does_not_render_served_model_prose():
    """⛔ `ai_summary` and `model_narrative` are model-generated, unversioned prose written for the
    signed-in analysis surfaces, and they use "edge" freely — the live payload on capture day read
    "a +3.2pp edge over the Bovada closing line".

    Rendering either here would put copy this repo does not control on the one page where the claim
    discipline is strictest, and every denylist scan downstream would be asserting against a string
    the API can change underneath it."""
    src = _strip_ts_comments(_PICK_COMPONENT_TSX.read_text())
    for field in ("ai_summary", "model_narrative", "top_drivers"):
        assert field not in src, (
            f"the home page renders the served `{field}` — unscreenable prose on the strictest "
            f"claim surface in the product"
        )


def test_an_empty_read_and_a_failed_read_are_different_messages(home_literals):
    """Two different facts. "The model published nothing today" is a routine, honest answer;
    "this page could not reach the model" is our failure and says nothing about the slate.
    A page that shows the first message on the second event states a falsehood about the model."""
    empty = next((s for s in home_literals if "Nothing to show yet" in s), None)
    unavailable = next((s for s in home_literals if "could not be loaded" in s), None)
    assert empty, "the honest empty state is gone"
    assert unavailable, "the failed-read state is gone — a failure would be reported as an empty slate"
    assert empty != unavailable

    src = _strip_ts_comments(_PICK_COMPONENT_TSX.read_text())
    assert "COPY.empty" in src and "COPY.unavailable" in src, (
        "the component no longer renders both states separately"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC — a first-class door to each vertical, and the trust link for each
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_both_verticals_are_declared_with_a_cta_and_a_trust_link():
    """The positioning AC as a data assertion. A vertical missing either half is the pre-E9.46
    state for that product: named on the page with no way in, or a way in with no evidence."""
    src = _strip_ts_comments(_HOME_COPY_TS.read_text())
    verticals = src.split("VERTICALS", 1)[1]
    for key in ('"betting"', '"fantasy"'):
        assert key in verticals, f"the {key} vertical is not declared in VERTICALS"
    assert '"/fantasy/rankings"' in verticals, "the fantasy door does not point at the free rankings"
    assert '"/performance"' in verticals, "the betting trust link does not point at the scorecard"
    assert "TRACK_RECORD_TRUST_LINK" in verticals, (
        "the fantasy trust link is not the NF-TR1 canonical one — a paraphrase is how a hedge gets "
        "dropped on one surface while a boast appears on another"
    )


def test_a_gated_trust_link_declares_that_it_is_gated():
    """⭐ `/fantasy/track-record` is genuinely public; `/performance` is behind the auth guard.
    Sending a stranger from a TRUST link into a login wall unannounced is the one surprise a trust
    link cannot afford, so the asymmetry is carried in the data rather than left to the reader."""
    src = _strip_ts_comments(_HOME_COPY_TS.read_text())
    betting = src.split('key: "betting"', 1)[1].split("},\n  {", 1)[0]
    fantasy = src.split('key: "fantasy"', 1)[1]
    assert "needsAccount: true" in betting, (
        "the MLB scorecard link no longer declares that it needs an account, but /performance is "
        "still behind AuthGuard"
    )
    assert "needsAccount: false" in fantasy, (
        "the fantasy track record is public and must not be labelled as gated"
    )


def test_the_home_page_reuses_the_fantasy_canonical_copy_verbatim():
    """NF-TR1's whole premise: three surfaces making the same pitch must use the same words.
    Paraphrase is how one surface loses a hedge while another gains a boast."""
    src = _strip_ts_comments(_HOME_COPY_TS.read_text())
    assert "PRODUCT_HOOK[0].title" in src and "PRODUCT_HOOK[0].detail" in src, (
        "the fantasy door paraphrases the canonical product hook instead of reusing it"
    )
    page = _strip_ts_comments(_HOME_PAGE_TSX.read_text())
    assert "DISAGREEMENT_HOOK" in page, (
        "the home page no longer renders the canonical consensus hook — the click-driver to the "
        "rankings is the one place a boast would be most tempting"
    )


def test_the_home_page_is_registered_as_a_marketing_surface():
    """⭐ THE REGISTRY IS THE POINT. `test_nf_tr1_claim_copy.py` keeps `_MARKETING_SURFACES` so that
    a new marketing page which forgets to appear there is a red build rather than a silent hole —
    and its own docstring says exactly that. The home page is now the largest such surface, so its
    membership is asserted here rather than assumed."""
    suite = _NF_TR1_SUITE.read_text()
    registry = suite.split("_MARKETING_SURFACES = (", 1)[1].split(")", 1)[0]
    assert "_HOME_PAGE_TSX" in registry, (
        "frontend/app/page.tsx is not in the NF-TR1 marketing-surface registry, so nothing checks "
        "that it links to the track record instead of quoting its measurement"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC — the season roadmap is honest
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_unshipped_roadmap_rows_are_marked_not_live():
    """NCAAF analytics and the NFL game model have not shipped. A row that claimed otherwise would
    be a promise a visitor can check and find false on the day."""
    src = _strip_ts_comments(_HOME_COPY_TS.read_text())
    # ⚠️ ANCHOR ON `= [`, NOT ON THE IDENTIFIER. The declaration is
    # `SEASON_ROADMAP: readonly {...}[] = [`, so splitting on the name and then on the first `]`
    # stops inside the TYPE ANNOTATION and extracts nothing — the identical trap NF-TR1's browser
    # denylist clause records. The vacuity assertion below is what caught it here, which is why it
    # is written down rather than implied.
    roadmap = src.split("SEASON_ROADMAP", 1)[1].split("= [", 1)[1].split("\n]", 1)[0]
    assert "sport:" in roadmap, "no roadmap rows extracted — this clause would be vacuous"
    for sport, marker in (("NCAAF", "Aug 29"), ("Game model", "Sep 9")):
        row = next((ln for ln in roadmap.split("\n") if marker in ln), None)
        assert row, f"the {sport} teaser row is gone from the roadmap"
        assert "live: false" in row, f"the {sport} row claims to be live: {row.strip()!r}"


def test_the_roadmap_note_refuses_to_promise_picks():
    """⛔ Both un-shipped rows are ANALYTICS. Neither has cleared a live betting gate — the NCAAF
    closing-line result is a recorded null — so a teaser implying picks would be selling a result
    the program does not have."""
    src = _strip_ts_comments(_HOME_COPY_TS.read_text())
    note = src.split("ROADMAP_NOTE", 1)[1].split(";", 1)[0]
    assert "does not mean picks we say will win" in note, (
        f"the roadmap note no longer refuses to promise picks: {note!r}"
    )


def test_a_coming_soon_row_is_never_rendered_as_a_link():
    """E9.56c's dead `/pricing` CTA wearing a friendlier label. The page renders the `when` value
    as TEXT for a non-live row; a future edit that wraps it in a Link would ship a route that does
    not exist."""
    page = _strip_ts_comments(_HOME_PAGE_TSX.read_text())
    roadmap_jsx = page.split("SEASON_ROADMAP.map", 1)[1].split("</ul>", 1)[0]
    assert "<Link" not in roadmap_jsx, (
        "a roadmap row renders a Link — an un-shipped teaser must carry no anchor at all"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC — the blog is demoted, and demoted is not deleted
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_blog_is_out_of_the_primary_nav():
    """Operator decision 3. The nav is the primary surface; the blog no longer competes with the
    two products for it."""
    nav = _strip_ts_comments(_NAV_TSX.read_text())
    assert 'href="/blog"' not in nav, "the blog is still a primary-nav link"


def test_the_blog_is_still_reachable():
    """⭐ THE HALF THAT MAKES THE RULE ABOVE SAFE RATHER THAN MERELY QUIETER. The decision is a
    DEMOTION — the GROWTH-100 content engine still publishes there — so deleting the route would
    be the dishonest way to pass the clause above. The footer renders on every page
    (`app/layout.tsx`), and the home page carries its own secondary link."""
    footer = _strip_ts_comments(_FOOTER_TSX.read_text())
    assert 'href: "/blog"' in footer, "the blog is gone from the site footer — that is a deletion"
    page = _strip_ts_comments(_HOME_PAGE_TSX.read_text())
    assert 'href="/blog"' in page, "the home page has no secondary link to the blog"


def test_the_home_page_no_longer_features_a_blog_post():
    """The pre-E9.46 page fetched the latest post and rendered its TITLE as a section heading above
    the pick card. A generic link is a demotion; a live headline is not, and the difference is
    invisible to any link-count check."""
    page = _strip_ts_comments(_HOME_PAGE_TSX.read_text())
    assert "/blog/posts" not in page, "the home page still fetches blog posts to feature one"
    assert "post.title" not in page, "the home page still renders a blog post's title"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC — the site-wide metadata stopped making the claim too
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_site_description_makes_no_edge_claim():
    """`app/layout.tsx`'s description was "Bayesian sports analytics. Daily edge, quantified." — the
    DEFAULT for every route that does not export its own, i.e. the sentence a link preview showed
    whenever any of them was pasted into a chat. It is the most widely-distributed copy in the
    product and had never been screened."""
    layout = _strip_ts_comments((_REPO / "frontend/app/layout.tsx").read_text())
    for literal in _ts_string_literals(layout) + re.findall(r"'([^']*)'", layout):
        assert "daily edge" not in literal.lower(), f"the site metadata still claims an edge: {literal!r}"
        hits = [t for t in ex._CLAIM_DENYLIST if t in literal.lower()]
        assert not hits, f"the site metadata makes a forbidden claim {hits}: {literal!r}"
