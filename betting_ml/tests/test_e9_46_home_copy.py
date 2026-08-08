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
_FANTASY_CARD_TSX = _REPO / "frontend/components/home/featured-fantasy-player.tsx"
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
    # ⚠️ BOUNDED TO THE ARRAY, not "everything after the identifier". The unbounded slice ran to
    # end-of-file, so `FANTASY_PROOF.cta.href` — the SAME route, declared 60 lines later — satisfied
    # the rankings assertion and the red-proof break that repointed the actual door stayed GREEN.
    # A slice wide enough to contain a second copy of what it is looking for cannot fail.
    src = _strip_ts_comments(_HOME_COPY_TS.read_text())
    verticals = src.split("export const VERTICALS", 1)[1].split("\n]", 1)[0]
    assert verticals.count("cta:") == 2, (
        f"expected exactly two vertical doors in the slice, found {verticals.count('cta:')} — the "
        f"slice bounds are wrong and every assertion below is suspect"
    )
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
    # ⚠️ ANCHOR INSIDE `VERTICALS` FIRST, and this cost a debugging round worth writing down: the
    # `VerticalDoor` TYPE declares `key: "betting" | "fantasy"`, so splitting the whole file on
    # `key: "betting"` lands in the TYPE, not the data — and the slice then ran on to the end of the
    # FANTASY entry, so the clause read `needsAccount: false` and reported the MLB link as
    # un-flagged. Same family as NF-TR1's "anchor on `= [`, not on the identifier".
    #
    # Sliced FORWARD from each key to the end of its own object literal, because E9.46's revision
    # put fantasy FIRST (the acquisition priority) — an order-dependent slice would read the wrong
    # block and pass for the wrong reason.
    src = _strip_ts_comments(_HOME_COPY_TS.read_text())
    verticals = src.split("export const VERTICALS", 1)[1]
    betting = verticals.split('key: "betting"', 1)[1].split("\n  },", 1)[0]
    fantasy = verticals.split('key: "fantasy"', 1)[1].split("\n  },", 1)[0]
    assert "trust:" in betting and "trust:" in fantasy, (
        "the per-vertical slices did not capture a trust block — this clause would be vacuous"
    )
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
    # The hook now renders on the fantasy PROOF card rather than in `page.tsx` — that section IS
    # the hook instantiated (the player we rank furthest from where the crowd drafts him, with the
    # drivers behind it), so it is the right home for it. Asserted where it actually renders.
    card = _strip_ts_comments(_FANTASY_CARD_TSX.read_text())
    assert "{DISAGREEMENT_HOOK}" in card, (
        "the fantasy proof no longer renders the canonical consensus hook verbatim — the one place "
        "on this page a boast would be most tempting"
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
    for sport, marker in (("NCAAF", "NCAAF"), ("NFL betting intelligence", "Coming this season")):
        rows = [ln for ln in roadmap.split("\n") if marker in ln]
        assert rows, f"the {sport} teaser row is gone from the roadmap"
        for row in rows:
            if "Coming this season" in row:
                assert "live: false" in row, f"a coming-soon row claims to be live: {row.strip()!r}"

    # ⚠️ NO DATED PROMISES. "Around Aug 29" is a commitment a visitor can check and find false on
    # the day; "coming this season" is one we control. Asserted as an absence so a date cannot
    # creep back in unnoticed.
    assert not re.search(r"\b(Aug|Sep|August|September)\s*\d", roadmap), (
        f"a dated launch promise is back on the roadmap: {roadmap.strip()!r}"
    )
    # Both un-shipped rows are the SAME product as the live MLB one.
    assert roadmap.count("Betting intelligence") >= 3, (
        "the un-shipped rows no longer describe betting intelligence — 'Game analytics' and "
        "'Game model' both misdescribe what is being built"
    )


def test_the_roadmap_note_refuses_to_promise_picks():
    """⛔ Both un-shipped rows are ANALYTICS. Neither has cleared a live betting gate — the NCAAF
    closing-line result is a recorded null — so a teaser implying picks would be selling a result
    the program does not have."""
    src = _strip_ts_comments(_HOME_COPY_TS.read_text())
    note = src.split("ROADMAP_NOTE", 1)[1].split(";", 1)[0]
    # ⚠️ THE WORDING IS CONSTRAINED BY THE DENYLIST, and that is worth recording before someone
    # "improves" it back. The first draft read "not a promise of picks that win" — a NEGATION, and
    # still a red build, because a substring scan cannot see the "not" (the same reason "sure thing"
    # is unusable even inside a disclaimer). A rewrite must AVOID the denied phrasing, not disclaim it.
    assert "analysis rather than an assurance of results" in note, (
        f"the roadmap note no longer refuses to promise results: {note!r}"
    )
    assert "durable advantage" in note, f"the roadmap note dropped the honest limit: {note!r}"


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


# ══════════════════════════════════════════════════════════════════════════════════════════════
# E9.46 REVISION (2026-08-08) — the fantasy proof, the corrected MLB badge, and the record framing
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_fantasy_card_always_renders_the_market_lean_caveat():
    """⛔ Measured on the live 2026 artifact: ZERO of the 111 players eligible for this card carry
    `mktLean == "independent"`, because that value is precisely the thin-data rookie case with no
    driver decomposition — and drivers are required to be featured. So at every position we can
    feature, our ranking already blends market consensus, and the rank gap is a real disagreement
    but never an independent one.

    The caveat therefore qualifies the card's headline number and must render UNCONDITIONALLY and
    INLINE. Behind a disclosure it is a caveat most readers never open."""
    card = _strip_ts_comments(_FANTASY_CARD_TSX.read_text())
    assert "{data.leanNote}" in card, "the fantasy card no longer renders the market-lean caveat"
    assert "<details" not in card.lower(), (
        "the market-lean caveat appears to have been moved behind a disclosure — it qualifies the "
        "headline number and has to arrive with it"
    )


def test_the_mlb_badge_describes_what_was_measured():
    """⭐ The served `conviction_label` is a HARDCODED CONSTANT — the literal "HIGH CONVICTION",
    stamped on every featured pick in both the serving writer and the API fallback. It classifies
    nothing, and a bettor reads it as confidence in the result.

    What the row actually satisfies is `|calibrated_win_prob − P(run_diff > 0)| ≤ 0.02`: two
    INDEPENDENT Credence estimators agreeing with each other, computed without reference to the
    odds. So the badge must state that, and must not render the served string."""
    src = _strip_ts_comments(_PICK_COMPONENT_TSX.read_text())
    assert "{COPY.agreementBadge}" in src, "the MLB badge no longer renders the measured label"
    assert "{data.conviction_label}" not in src, (
        "the hardcoded 'HIGH CONVICTION' string is being rendered — it measures nothing and reads "
        "as a promise about the result"
    )
    literals = _ts_string_literals(_HOME_COPY_TS.read_text())
    badge = next(s for s in literals if "models agree" in s.lower())
    for inverted in ("disagreement", "high conviction", "market gap"):
        assert inverted not in badge.lower(), (
            f"the badge says {inverted!r}, which is not what the flag measures — the flag is our "
            f"two models AGREEING, and it never looks at the odds"
        )


def test_the_mlb_record_is_described_as_members_only():
    """⚠️ VERIFIED 2026-08-08: `/picks/scorecard`, `/performance`, `/picks/today` and
    `/picks/history` all return 401 to an anonymous request. The record is real and graded daily —
    but it is not reachable without an account, so calling it public would send a cold visitor from
    a trust link into a login wall."""
    literals = _ts_string_literals(_HOME_COPY_TS.read_text())
    joined = " ".join(literals).lower()
    assert "members' scorecard" in joined, (
        "the copy no longer says where the MLB record lives"
    )
    for overclaim in ("public daily record", "public track record", "publicly available record"):
        assert overclaim not in joined, (
            f"the MLB record is advertised as {overclaim!r}, but every record endpoint 401s for an "
            f"anonymous caller"
        )


def test_the_record_sentence_states_both_halves():
    """⭐ THE TWO HALVES PULL AGAINST EACH OTHER AND BOTH ARE REQUIRED.

    Copy implying we do not measure ourselves would be as false as copy claiming an edge — the
    daily model-vs-market record is computed every day, losses included. What it has not shown is a
    durable advantage over the closing market. Dropping the first half throws away the most credible
    thing the product has; dropping the second is the overclaim `best_alpha = 0` forbids."""
    literals = _ts_string_literals(_HOME_COPY_TS.read_text())
    record = next(s for s in literals if "graded against the market" in s)
    assert "durable advantage" in record, (
        f"the record sentence claims the grading without stating its limit: {record!r}"
    )
    assert "wins and losses" in record.lower(), (
        f"the record sentence no longer says the losses are included: {record!r}"
    )


def test_the_retired_tagline_is_scoped_to_the_mlb_product():
    """"Daily edge, quantified" was the company H1 until this release and is kept as the BETTING
    product's tagline (operator, 2026-08-08). The regression is it drifting back up into
    company-wide positioning, where it no longer describes a company that also ships fantasy."""
    src = _strip_ts_comments(_HOME_COPY_TS.read_text())
    hero = src.split("export const HERO", 1)[1].split("} as const", 1)[0]
    assert "edge" not in hero.lower(), f"the retired tagline is back in the hero: {hero!r}"

    layout = _strip_ts_comments((_REPO / "frontend/app/layout.tsx").read_text())
    assert "daily edge" not in layout.lower(), "the retired tagline is back in the site metadata"

    # And it must still exist for the MLB product, or this is a deletion rather than a scoping.
    assert 'MLB_PRODUCT_TAGLINE = "Daily edge, quantified."' in src
    pick = _strip_ts_comments(_PICK_COMPONENT_TSX.read_text())
    assert "MLB_PRODUCT_TAGLINE" in pick, "the MLB product tagline is not rendered on the MLB block"


def test_a_carried_over_card_says_which_day_it_is_for():
    """⭐ THE CARRY-OVER, WHICH IS A CLAIM SURFACE AND NOT JUST A LOADING STATE (operator,
    2026-08-08: keep the previous read up until today's projections land).

    A stale card that does not announce itself is the worst of the three states this block can be
    in. The empty state is honest and the failed state is honest; a yesterday card presented as
    today's read is a false statement about a live slate — a visitor could act on a number for a
    game that has already been played. So the note has to carry BOTH halves: that today's run
    hasn't published, and that what is on screen belongs to the date shown above it.

    ⚠️ The date itself is rendered from `pick_date` and is what makes "the date shown above"
    resolvable, so the component's rendering of both is asserted too — the sentence alone would be
    a dangling reference if the date chip were ever dropped."""
    src = _strip_ts_comments(_HOME_COPY_TS.read_text())
    m = re.search(r"\n  staleNote:\s*\n?\s*\"(.*?)\",\n", src, re.S)
    assert m, "MLB_PROOF.staleNote is gone — a carried-over card would be unlabelled"
    note = m.group(1).lower()

    assert "hasn't published" in note or "has not published" in note, (
        f"the note does not say today's run is still pending: {note!r}"
    )
    assert "not today's slate" in note, (
        f"the note does not tell a visitor this is a previous day's read: {note!r}"
    )

    pick = _strip_ts_comments(_PICK_COMPONENT_TSX.read_text())
    assert "COPY.staleNote" in pick, "the component never renders the carry-over note"
    assert "data.is_stale" in pick, "the component does not branch on the carried-over flag"
    assert "pick_date" in pick, (
        "the date chip is gone, so \"the date shown above\" in the note refers to nothing"
    )


def test_the_frame_does_not_promise_strict_alternation():
    """⭐ THE COPY IS BOUNDED BY WHAT THE SQL GUARANTEES, and here the SQL guarantees less than the
    obvious sentence would claim.

    `market_pref` is a SORT KEY, not a filter: on a day when the market whose turn it is has no
    qualifying game, the other market's best read is featured instead of the card going empty.
    That is the right behaviour — a labelled read beats no read — but it means "we alternate
    between the moneyline and the total" is a promise a visitor could catch us breaking, on a page
    whose entire argument is that we do not overstate. So the frame hedges, and it names both
    markets so nobody has to infer the alternation from watching for a week.

    ⚠️ The hedge is what makes the FALLBACK safe to keep. If this guard is ever "fixed" by
    tightening the copy, the fallback has to become a filter in the same change — and then some
    days show nothing."""
    src = _strip_ts_comments(_HOME_COPY_TS.read_text())
    m = re.search(r"\n  frame:\s*\n?\s*\"(.*?)\",\n", src, re.S)
    assert m, "MLB_PROOF.frame is gone"
    frame = m.group(1).lower()

    assert "moneyline" in frame and "total" in frame, (
        f"the frame does not name both markets, so the alternation is invisible: {frame!r}"
    )
    assert "usually alternating" in frame, (
        "the frame states the alternation without the hedge the SQL requires — `market_pref` is a "
        f"sort key with a fallback, not a guarantee: {frame!r}"
    )


def test_the_card_names_the_market_it_is_making():
    """The card alternates between two markets that quote DIFFERENT quantities — a win probability
    and an over probability — so the copy for both must exist, each with its own one-line
    explanation of what the number on screen actually measures."""
    src = _strip_ts_comments(_HOME_COPY_TS.read_text())
    m = re.search(r"\n  markets: \{(.*?)\n  \},", src, re.S)
    assert m, "MLB_PROOF.markets is gone — the card cannot name its market"
    markets = m.group(1)
    for key, label in (("h2h", "Moneyline"), ("totals", "Total runs")):
        assert f"{key}: {{" in markets, f"no copy for the {key} market"
        assert label in markets, f"the {key} market has no human label"
    assert markets.count("hint:") == 2, "a market ships without its one-line explanation"


def test_the_card_renders_the_market_label():
    """⚠️ SPLIT FROM THE COPY CHECK ABOVE, AND FROM THE TOTAL-LINE CHECK BELOW, because the first
    version asserted all three together against `"COPY.markets" in src` — and stayed GREEN when the
    rendered label was replaced with a literal, since `COPY.markets` was still referenced two lines
    up. A clause is only tested when the fixture satisfies every OTHER clause (NF-D17 §7), which
    for a source scan means each clause needs its own precise expression.

    Copy that exists but is never rendered is the "wired but never invoked" class (NF-C0e (b))."""
    pick = _strip_ts_comments(_PICK_COMPONENT_TSX.read_text())
    assert "COPY.markets" in pick, "the component does not read the market copy"
    # ⚠️ NEWLINE-ANCHORED, and that is not fussiness. A bare `"{market.label}" in pick` stayed GREEN
    # when the rendered badge was replaced with a literal, because the trigger's
    # `aria-label={`What ${market.label} means`}` CONTAINS that substring — an accessibility label
    # standing in for the visible one. The same collision class as the fantasy-door locator.
    assert "\n                {market.label}\n" in pick, (
        "the market label is never rendered as the card's own text"
    )
    assert "data-market" in pick, "the rendered market is not exposed for the E2E check"


def test_a_totals_lean_carries_the_line_it_is_about():
    """"Our model leans Over" is not a statement — over what? On roughly half the days this card is
    a total, and the side without the number is meaningless.

    The exact interpolation is asserted rather than a mention of `total_line`, for the reason in
    `test_the_card_renders_the_market_label`: the field is read in three places, so a looser check
    passes while the rendered string has lost the number."""
    pick = _strip_ts_comments(_PICK_COMPONENT_TSX.read_text())
    assert "${side} ${data.total_line}" in pick, (
        "an over/under lean renders without the line it is about"
    )


def test_the_carried_recap_is_labelled_with_the_day_it_is_for():
    """⭐ THE OFF-BY-ONE GUARD, and it pins a bug that was in the first draft of this label.

    On a live card the recap is the previous day's read and "Yesterday" is right. On a CARRIED-OVER
    card the card is already a previous day, so "Yesterday" would point at the card's own date while
    naming the day before it. The fix is to render the DATE — but the recap is the day BEFORE
    `pick_date`, not `pick_date` itself, and the first cut rendered `pick_date` directly. That would
    have labelled Aug 6's result "August 7" and re-created the exact confusion the label exists to
    remove, while looking entirely plausible on screen.

    So the subtraction is asserted, not merely the presence of a date."""
    pick = _strip_ts_comments(_PICK_COMPONENT_TSX.read_text())
    assert "recapLabel" in pick, "the recap label is no longer computed"
    assert "d.setDate(d.getDate() - 1)" in pick, (
        "the carried recap is labelled with the CARD's date rather than the day it actually "
        "reports — an off-by-one that reads as correct"
    )
    # And the live-card path must still say "Yesterday", or this fix has quietly changed the
    # normal state too.
    assert "COPY.yesterdayLabel" in pick
