"""E9.60 — COPY GOVERNANCE for the About and FAQ pages, and the signed-out navigation.

E9.46 screened the home page; NF-TR1 screened the fantasy product copy. About and FAQ were the last
two public marketing surfaces whose prose lived INLINE in JSX, read by no denylist — and both had
gone false in the same way the landing FAQ had before E9.46 fixed it: the FAQ answered "What
sport(s) does Credence cover?" with "MLB baseball only, for the 2026 season" and About's subhead
read "We forecast baseball the way the evidence supports", on a site whose home page leads with an
NFL fantasy product.

So this suite is the About/FAQ twin of `test_e9_46_home_copy.py`. It screens
`frontend/lib/positioning-copy.ts` the same way, and adds the clauses specific to these surfaces:
only shipped capabilities may read as shipped, the MLB record may not be advertised as public, the
free/paid line must match `docs/freemium_tier.md`, the paid line must not be sold as anti-scraping,
and a signed-out visitor must find a door to BOTH products.

⭐ EACH CLAUSE IS INDEPENDENTLY RED-PROVABLE (NF-D17 §7): a guard on an `and`-composed condition
passes with the clause it NAMES deleted whenever a different clause already refuses the fixture.
Every assertion below names one thing and is written so removing that one thing turns it red;
verified with `uv run python betting_ml/tests/e9_60_positioning_copy_red_proof.py`.

⚠️ SOURCE-INSPECTION, SO COMMENTS ARE STRIPPED FIRST (INC-38). The module under test DISCUSSES these
rules at length — it explains why "public track record" is forbidden, by writing the phrase — and a
raw substring search would be satisfied by the comment explaining the rule.

Pure/offline (fast gate): reads source files only, no DuckDB/S3/network.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from betting_ml.governance import gates
from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as ex

_REPO = Path(__file__).resolve().parents[2]
_FRONTEND = _REPO / "frontend"
_APP = _FRONTEND / "app"
_COPY_TS = _FRONTEND / "lib/positioning-copy.ts"
_ABOUT_TSX = _APP / "about/page.tsx"
_FAQ_TSX = _APP / "faq/page.tsx"
_NAV_TSX = _FRONTEND / "components/nav.tsx"
_FOOTER_TSX = _FRONTEND / "components/site-footer.tsx"
_NF_TR1_SUITE = _REPO / "betting_ml/tests/test_nf_tr1_claim_copy.py"

pytestmark = pytest.mark.skipif(not _APP.is_dir(), reason="frontend/ not present")


def _strip_ts_comments(src: str) -> str:
    """⚠️ LINE COMMENTS FIRST, then block comments — the opposite of the obvious order, and the
    order matters. A `//` comment containing a URL fragment or a path glob can open what the block
    regex reads as a comment and swallow real source up to the next close. Stripping `//` lines
    first removes that whole class (`test_e9_46_home_copy.py` records the same lesson)."""
    src = "\n".join(line for line in src.split("\n") if not line.lstrip().startswith("//"))
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def _ts_string_literals(src: str) -> list[str]:
    """Every double-quoted string literal, comments stripped. Crude on purpose — a screening pass
    over prose constants, not a parser. Its own vacuity is asserted below."""
    return re.findall(r'"((?:[^"\\]|\\.)*)"', _strip_ts_comments(src))


@pytest.fixture(scope="module")
def copy_literals() -> list[str]:
    return _ts_string_literals(_COPY_TS.read_text())


@pytest.fixture(scope="module")
def copy_src() -> str:
    return _strip_ts_comments(_COPY_TS.read_text())


@pytest.fixture(scope="module")
def faq_answers(copy_src) -> list[str]:
    """⚠️ THE FAQ ANSWERS ALONE, and the fixture exists because the first cut of this suite did not
    have it and four clauses picked the WRONG STRING.

    About and the FAQ deliberately make the same points in different words, so a scan over every
    literal in the module finds an About sentence that merely CONTAINS the anchor phrase and asserts
    against it: `"featured MLB read"` matched `ABOUT_NOT`'s bullet rather than the FAQ answer, and
    `"de-vigged market consensus"` matched the betting product's `live.note`. Both then failed for
    the right-looking reason on the wrong text.

    Anchoring inside `FAQ_SECTIONS` makes each clause name exactly one string."""
    block = copy_src.split("export const FAQ_SECTIONS", 1)[1].split("\nexport const FAQ_HEADER", 1)[0]
    answers = re.findall(r'\n        a:\s*"((?:[^"\\]|\\.)*)"', block)
    assert len(answers) >= 25, (
        f"only {len(answers)} FAQ answer(s) extracted — every FAQ clause below would be vacuous"
    )
    return answers


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The guard on the guard
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_copy_module_scan_actually_finds_strings(copy_literals):
    """⚠️ NF1.7 (a): an extractor that silently returned nothing would make every screening clause
    in this file vacuously true, and the file would read as coverage the whole time."""
    assert len(copy_literals) >= 80, (
        f"only {len(copy_literals)} string literal(s) extracted from the positioning copy module — "
        f"the screening below would be passing on nothing"
    )
    assert any("knowing what you don" in s for s in copy_literals), (
        "the About H1 was not extracted — the scan is not reading the block that most needs "
        "screening"
    )
    assert any("de-vigged market consensus" in s for s in copy_literals), (
        "the FAQ answers were not extracted — the scan is reading only the About half"
    )


def test_the_comment_stripper_does_not_eat_real_source(copy_src):
    """The other half of the vacuity guard, and a bug this repo has actually shipped: a stripper
    that swallowed the file would make every source-inspection clause below pass on an empty
    string."""
    assert "export const ABOUT_HERO" in copy_src
    assert "export const FAQ_SECTIONS" in copy_src
    assert "export const SIGNED_OUT_NAV" in copy_src
    assert len(copy_src) > 0.25 * len(_COPY_TS.read_text()), (
        "comment stripping removed most of the file — a `//` line containing a block-comment "
        "opener is the usual cause"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC — the claim discipline reaches these surfaces too
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_positioning_copy_passes_the_denylist(copy_literals):
    """`best_alpha = 0`. The same denylist E9.46 runs over the home copy and NF-TR1 runs over the
    fantasy copy, now over the last two unscreened public marketing surfaces."""
    for text in copy_literals:
        hits = [t for t in ex._CLAIM_DENYLIST if t in text.lower()]
        assert not hits, f"About/FAQ copy makes a forbidden claim {hits}: {text!r}"


def test_the_governance_gate_passes_the_positioning_copy(copy_literals):
    """Run the ACTUAL promotion gate over the ACTUAL copy, not a re-implementation of its rule with
    the same word list."""
    result = gates.track_record_copy_compatible(copy_literals)
    assert result.status == gates.PASS, result.detail


def test_that_gate_can_still_refuse_positioning_copy():
    """⚠️ A GATE THAT CANNOT FAIL IS NOT A GATE. The clause above is only evidence if the same call
    goes red on copy that should be refused."""
    bad = gates.track_record_copy_compatible(
        ["Credence beats the market on MLB and fantasy alike — profitable, guaranteed."]
    )
    assert bad.status == gates.FAIL


def test_the_pages_carry_no_unscreened_prose():
    """⭐ THE HOLE THIS FILE EXISTS TO CLOSE. Screening a copy MODULE proves nothing if the page can
    write its own sentences inline — which is exactly what both pre-E9.60 pages did.

    Enforced as a LENGTH rule on string literals in the JSX, because a heading ("What we believe")
    is fine and a paragraph is not, and the difference between them is length rather than kind. The
    threshold sits well above every label and CTA these pages render and well below any real
    sentence. Same instrument as `test_e9_46_home_copy.py`'s equivalent clause."""
    for path in (_ABOUT_TSX, _FAQ_TSX):
        long_literals = [
            s
            for s in _ts_string_literals(path.read_text())
            # Tailwind class strings are long, quoted, and not prose.
            if len(s) > 120 and not re.search(r"[a-z]-\[|text-|bg-|border-|grid-|flex", s)
        ]
        assert not long_literals, (
            f"{path.name} contains inline prose that no denylist screens: {long_literals[:2]}"
        )


def test_the_marketing_surfaces_are_registered_with_nf_tr1():
    """⭐ THE REGISTRY IS THE POINT. `test_nf_tr1_claim_copy.py` keeps `_MARKETING_SURFACES` so a new
    marketing page that forgets to appear there is a red build rather than a silent hole. About and
    FAQ are marketing surfaces and were never in it — which is part of how they drifted."""
    suite = _NF_TR1_SUITE.read_text()
    registry = suite.split("_MARKETING_SURFACES = (", 1)[1].split(")", 1)[0]
    for name in ("_ABOUT_TSX", "_FAQ_TSX"):
        assert name in registry, (
            f"{name} is not in the NF-TR1 marketing-surface registry, so nothing checks that it "
            f"links to the track record instead of quoting its measurement"
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC — the site tells ONE story: two products, fantasy first
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_about_declares_both_products_fantasy_first(copy_src):
    """Spec §2: one product order everywhere. The home page's `VERTICALS` leads with fantasy
    because that is the acquisition priority; About and the nav must not make a visitor infer a
    different priority from a different page."""
    block = copy_src.split("export const ABOUT_PRODUCTS", 1)[1].split("\n]", 1)[0]
    assert block.count("key:") == 2, (
        f"expected exactly two product blocks in the slice, found {block.count('key:')} — the "
        f"slice bounds are wrong and every assertion below is suspect"
    )
    assert block.index('"fantasy"') < block.index('"betting"'), (
        "About leads with betting; the home page leads with fantasy. One order, everywhere."
    )


def test_about_no_longer_describes_a_baseball_only_company(copy_literals):
    """The literal defect this story was opened for. The page's subhead read "We forecast baseball
    the way the evidence supports" and its audience paragraph addressed a Fangraphs reader — a
    one-sport identity on a two-product site."""
    joined = " ".join(copy_literals).lower()
    assert "forecast baseball" not in joined, (
        "the retired baseball-only positioning line is back in the About copy"
    )
    for vertical in ("fantasy", "mlb"):
        assert vertical in joined, f"the About/FAQ copy never mentions {vertical}"


def test_the_faq_covers_both_products_in_the_site_order(copy_src):
    """Spec §17: the FAQ gained a dedicated fantasy section, and the sections run in the same
    product order as About and the nav."""
    block = copy_src.split("export const FAQ_SECTIONS", 1)[1]
    cats = re.findall(r'category:\s*"([^"]+)"', block)
    assert len(cats) >= 4, f"only {len(cats)} FAQ section(s) found — the slice is wrong: {cats}"
    lowered = [c.lower() for c in cats]
    fantasy_i = next(i for i, c in enumerate(lowered) if "fantasy" in c)
    betting_i = next(i for i, c in enumerate(lowered) if "betting" in c)
    assert fantasy_i < betting_i, (
        f"the FAQ puts betting before fantasy, contradicting the site's product order: {cats}"
    )


def test_the_faq_no_longer_says_the_company_is_mlb_only(copy_literals):
    """⛔ THE EXACT SENTENCE E9.46 ALREADY HAD TO DELETE FROM THE LANDING FAQ, which was still live
    one route over on this page: "MLB baseball only, for the 2026 season"."""
    joined = " ".join(copy_literals).lower()
    for stale in ("mlb baseball only", "baseball analytics tool", "one sport well before expanding"):
        assert stale not in joined, f"the FAQ still carries the retired MLB-only framing: {stale!r}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC — only what is LIVE reads as live
# ══════════════════════════════════════════════════════════════════════════════════════════════
# Spec §3.1/§3.2: these are NOT shipped. A `live` list containing one of them is the defect this
# whole story exists to prevent — advertising roadmap work as a capability.
_UNSHIPPED = ("weekly projection", "start/sit", "waiver", "matchup-aware", "lineup win probability")


def test_no_unshipped_fantasy_capability_sits_in_a_live_list(copy_src):
    """⭐ THE STRUCTURAL GUARD, and the reason `ABOUT_PRODUCTS` is data rather than prose. Both
    lists render the same words in different places, so a text scan cannot tell "weekly projections
    are coming" from "weekly projections are available" — but the `live` / `coming` keys can."""
    block = copy_src.split("export const ABOUT_PRODUCTS", 1)[1].split("\n]", 1)[0]
    live_blocks = re.findall(r"live:\s*\{(.*?)\n    \},", block, re.S)
    assert len(live_blocks) == 2, (
        f"extracted {len(live_blocks)} live block(s), expected 2 — this clause would be vacuous"
    )
    for lb in live_blocks:
        low = lb.lower()
        for cap in _UNSHIPPED:
            assert cap not in low, (
                f"an un-shipped capability ({cap!r}) is listed as AVAILABLE NOW: {lb.strip()[:120]!r}"
            )


def test_the_unshipped_capabilities_are_still_named_as_coming(copy_src):
    """⭐ THE HALF THAT MAKES THE RULE ABOVE SAFE RATHER THAN MERELY QUIETER. Deleting the weekly
    tools entirely would satisfy the clause above completely — and would hide the roadmap from a
    visitor deciding whether to subscribe. They must be present, and present as NOT YET."""
    block = copy_src.split("export const ABOUT_PRODUCTS", 1)[1].split("\n]", 1)[0]
    coming_blocks = re.findall(r"coming:\s*\{(.*?)\n    \},", block, re.S)
    assert len(coming_blocks) == 2, (
        f"extracted {len(coming_blocks)} coming block(s), expected 2 — this clause would be vacuous"
    )
    joined = " ".join(coming_blocks).lower()
    for cap in ("weekly projection", "start/sit", "waiver", "matchup-aware"):
        assert cap in joined, f"{cap!r} vanished from the roadmap rather than being labelled coming"
    assert "nfl betting intelligence" in joined and "ncaaf betting intelligence" in joined, (
        "the un-shipped betting verticals are no longer labelled as coming"
    )


def test_the_coming_lists_are_never_rendered_as_links():
    """E9.56c's dead `/pricing` CTA wearing a friendlier label — the same rule the home page's
    roadmap carries. An un-shipped capability must carry no anchor at all."""
    page = _strip_ts_comments(_ABOUT_TSX.read_text())
    coming_jsx = page.split('data-capability="coming"', 1)[1].split("</div>", 1)[0]
    assert "<Link" not in coming_jsx and "<a " not in coming_jsx, (
        "a coming-soon capability renders a link — that is a route that does not exist behind a "
        "button"
    )


def test_about_does_not_advertise_unbuilt_simulation(copy_literals):
    """Spec §10/§11. Lineup win-probability simulation, weekly matchup simulation and the known-truth
    gate simulator (SIM-V1) are NOT operational. Advertising roadmap work as shipped, on the two
    sections whose subject is our standard of evidence, would be self-refuting."""
    ranges_and_eval = " ".join(
        s for s in copy_literals if "predictive distribution" in s or "held-out" in s or "range" in s.lower()
    ).lower()
    assert ranges_and_eval, "no ranges/evaluation copy extracted — this clause would be vacuous"
    for unbuilt in ("sim-v1", "matchup simulation", "lineup win probability", "known-truth"):
        assert unbuilt not in ranges_and_eval, (
            f"the copy advertises {unbuilt!r}, which is not operational"
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC — the record is described the way it is actually served
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_mlb_record_is_not_advertised_as_public(copy_literals):
    """⚠️ THE ONE PLACE THIS STORY DEPARTS FROM ITS OWN SPEC, and it is a live-product fact rather
    than a preference. The spec calls the MLB track record PUBLIC in §3.3, §4.4 and §12. It is not:
    `app/backend/main.py` mounts `picks.router` and `performance.router` with `dependencies=_paid`,
    so `/picks/scorecard`, `/picks/today`, `/picks/history` and `/performance` all refuse an
    anonymous caller.

    The spec's own §25 subordinates its wording to the live product, so following the live truth IS
    following the spec. `home-copy.ts` already carries the identical correction."""
    joined = " ".join(copy_literals).lower()
    for overclaim in ("public daily record", "public track record", "publicly available record"):
        assert overclaim not in joined, (
            f"the MLB record is advertised as {overclaim!r}, but every MLB record endpoint refuses "
            f"an anonymous caller"
        )
    assert "members' scorecard" in joined, "the copy no longer says where the MLB record lives"


def test_the_public_fantasy_record_is_still_described_as_open(faq_answers):
    """⭐ THE ASYMMETRY IS REAL AND BOTH HALVES MATTER. `fantasy_public.router` carries no gate, so
    the fantasy track record genuinely IS open to anyone. Collapsing both records into "members
    only" to satisfy the clause above would throw away the site's one freely-inspectable proof
    asset — which is exactly the wrong correction.

    ⚠️ ANCHORED ON THE ONE ANSWER WHOSE JOB THIS IS, and the first cut was not: a module-wide
    `"no account" in joined or "open to anyone" in joined` stayed GREEN when the record answer was
    rewritten to say the fantasy record is members-only, because four OTHER strings still carried
    the phrase. Caught by the red-proof; a clause that a different sentence can satisfy is testing
    that sentence, not this one."""
    ans = next((s for s in faq_answers if "The fantasy track record is" in s), None)
    assert ans, "the 'where can I see the record' answer is gone"
    low = ans.lower()
    assert "no account" in low, (
        f"the fantasy track record is no longer described as freely readable: {ans!r}"
    )
    assert "members' scorecard" in low, (
        f"the answer no longer distinguishes the gated MLB record from the open fantasy one, which "
        f"is the whole reason it names them separately: {ans!r}"
    )


def test_the_record_copy_states_both_halves(copy_src):
    """⭐ THE TWO HALVES PULL AGAINST EACH OTHER AND BOTH ARE REQUIRED (the E9.46 rule, restated on
    this surface). Copy implying we do not measure ourselves would be as false as copy claiming an
    edge; copy claiming the edge is the overclaim `best_alpha = 0` forbids.

    ⚠️ ANCHORED ON `ABOUT_ACCOUNTABILITY`, the section whose entire subject this is. The first cut
    scanned the whole module and stayed GREEN when that section's limit was rewritten into a claim,
    because the phrase survived in three FAQ answers — the identical vacuity as the clause above."""
    block = copy_src.split("export const ABOUT_ACCOUNTABILITY", 1)[1].split("} as const", 1)[0]
    assert "paragraphs:" in block, "the accountability slice is empty — this clause would be vacuous"
    low = block.lower()
    assert "durable advantage over the closing market" in low, (
        "the accountability section states the grading without its honest limit"
    )
    assert "wins and losses" in low or "losing observations" in low, (
        "the accountability section no longer says the losing observations stay on the page"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC — the free/paid line matches `docs/freemium_tier.md`
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_free_tier_is_described_as_the_freemium_build_shipped_it(faq_answers):
    """Verified against `app/backend/services/entitlement.py`: `FREE_BOARD_CONFIG = "full_ppr"`,
    `FREE_BOARD_SIZE = 12`, and `FREE_PERSONALIZED_LEAGUE_QUOTA` defaults to 1 (G100-C1). Copy that
    describes an entitlement goes stale SILENTLY — nothing renders differently when a sentence stops
    being true — which is precisely why it is pinned.

    ⚠️ ANCHORED ON THE "what is free" ANSWER. A module-wide scan stayed GREEN when the scoring-format
    answer stopped naming the free preset, because a second answer still mentioned it — the third
    instance of the same vacuity the red-proof caught in this file."""
    ans = next((s for s in faq_answers if s.startswith("Free, including without an account")), None)
    assert ans, "the free/paid answer is gone"
    low = ans.lower()
    assert "full-ppr twelve teams" in low or "full-ppr at twelve teams" in low, (
        f"the free/paid answer no longer names the free preset, so a visitor cannot tell which "
        f"board is open: {ans!r}"
    )
    assert "one personalized league" in low, (
        f"the free tier's one personalized league (G100-C1, quota 1) is not described: {ans!r}"
    )
    assert "draft optimizer" in low, (
        f"the answer no longer names the decision-support half of the paid tier: {ans!r}"
    )


def test_the_paid_line_is_never_sold_as_anti_scraping(copy_literals):
    """⛔ `docs/freemium_tier.md` §1: the free board is scrapeable BY DESIGN and that was accepted
    when the tier was drawn. An anti-scraping framing would be false, and the claim-copy module
    already carries the same guard for the fantasy surfaces."""
    joined = " ".join(copy_literals).lower()
    # ⚠️ WORD BOUNDARIES, NOT SUBSTRINGS. The first cut used `"bot" in joined` and went RED on the
    # phrase "BOTH are the same product" — a false positive that would have been "fixed" by
    # weakening the guard rather than by noticing the bug in it.
    for false_claim in (r"scrap", r"bots?\b", r"crawler", r"steal our numbers"):
        assert not re.search(rf"\b{false_claim}", joined), (
            f"the copy defends the paid line as protection against {false_claim!r} — the free board "
            f"is scrapeable by design and that framing is false"
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC — the FAQ stopped telling visitors how much to bet
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_faq_carries_no_stake_sizing_guidance(copy_literals):
    """Spec §18.9. Stake sizing presumes something to size against, and `best_alpha = 0` says we do
    not have it. ⚠️ The FEATURE is still live behind the paywall (`/ev-tracker` renders raw and
    capped Kelly columns; `/settings` carries a Kelly cap) — removing it is a product decision
    outside E9.60's scope and is flagged in the handoff. This guard covers the PUBLIC copy only."""
    joined = " ".join(copy_literals).lower()
    for sizing in ("kelly", "how much should i bet", "fraction of bankroll", "bankroll management"):
        assert sizing not in joined, (
            f"the public FAQ carries stake-sizing guidance ({sizing!r}); with no demonstrated edge "
            f"there is nothing to size against"
        )


def test_the_ev_answer_is_conditional_rather_than_a_promise(copy_literals):
    """Spec §18.8 keeps the EV question only because EV IS live (`/ev-tracker` renders it). Kept, but
    the conditional is the whole answer: a positive number is a statement about our estimate, not
    evidence the estimate is right."""
    ev = next((s for s in copy_literals if "Expected Value is" in s), None)
    assert ev, "the EV answer is gone while `/ev-tracker` still renders EV to members"
    low = ev.lower()
    assert "if the probability estimate behind it were correct" in low, (
        f"the EV answer states the value without its conditional: {ev!r}"
    )
    assert "durable advantage" in low, (
        f"the EV answer omits the record's honest limit, which is what stops it reading as a "
        f"promise: {ev!r}"
    )


def test_the_market_consensus_is_described_as_the_code_computes_it(faq_answers):
    """Spec §4.2, verified against `dbt/models/mart/mart_odds_consensus.sql`: each book's two-way
    prices are de-vigged, then consensus is a PLAIN UNWEIGHTED average across every book pricing
    both sides. ⛔ The pre-E9.60 FAQ said Bovada was "the benchmark we use for edge detection",
    conflating the comparison probability with the book a price is graded at."""
    ans = next((s for s in faq_answers if "de-vigged market consensus" in s), None)
    assert ans, "the market-consensus answer is gone"
    low = ans.lower()
    assert "not one designated sportsbook" in low, (
        f"the answer no longer rules out a single-book benchmark: {ans!r}"
    )
    assert "none weighted above another" in low, (
        f"the answer no longer states the average is unweighted — there IS a sharp/soft split in "
        f"that model and the column we score against does not use it: {ans!r}"
    )


def test_the_models_agree_answer_describes_what_is_measured(faq_answers):
    """Spec §4.1. The flag is `|calibrated_win_prob − P(run_diff > 0)| ≤ 0.02` — two INDEPENDENT
    Credence estimators agreeing with each other, computed with no reference to the odds. A visitor
    reads "models agree" as confidence in the RESULT unless told otherwise."""
    ans = next((s for s in faq_answers if "two independent Credence models" in s), None)
    assert ans, "the models-agree answer is gone"
    low = ans.lower()
    assert "without looking at the odds" in low, (
        f"the answer no longer says the indicator is computed market-blind: {ans!r}"
    )
    assert "not a confidence rating" in low, (
        f"the answer no longer refuses the reading a visitor actually arrives with: {ans!r}"
    )


def test_the_featured_read_is_not_sold_as_the_best_bet(faq_answers):
    """Spec §4.3. ⚠️ The spec's own phrasing is "not a guaranteed recommendation" and "guaranteed"
    is a DENIED substring — a screening pass cannot see the "not" in front of it, the same reason
    `home-copy.ts`'s roadmap note had to be rewritten rather than negated. So the refusal is worded
    around the denylist rather than disclaiming it."""
    ans = next((s for s in faq_answers if "worked example" in s), None)
    assert ans, "the featured-read answer is gone"
    low = ans.lower()
    assert "demonstration, not a recommendation" in low, (
        f"the featured read is no longer framed as a demonstration: {ans!r}"
    )
    assert "not labelled the day's best bet" in low, (
        f"the answer no longer refuses the best-bet reading: {ans!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC — a signed-out visitor finds a door to BOTH products
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_signed_out_nav_carries_both_products(copy_src):
    """⭐⭐ THE NAVIGATION DEFECT E9.60 FIXES, as a data assertion.

    The nav rendered `publicNavItems()` — every `public: true` item in `nav-model.ts` — and all four
    of them are FANTASY. So the nav of a two-product company listed exactly one product, and the
    live MLB betting product had no signed-out door anywhere."""
    block = copy_src.split("export const SIGNED_OUT_NAV", 1)[1].split("\n]", 1)[0]
    assert block.count("href:") >= 5, (
        f"only {block.count('href:')} nav entries extracted — the slice is wrong and every clause "
        f"below is suspect"
    )
    for product in ('"fantasy"', '"betting"'):
        assert f"product: {product}" in block, (
            f"the signed-out nav has no door to the {product} product"
        )


def test_the_signed_out_nav_is_fantasy_first(copy_src):
    """Spec §2/§20: the same product order as the home page's `VERTICALS` and About."""
    block = copy_src.split("export const SIGNED_OUT_NAV", 1)[1].split("\n]", 1)[0]
    assert block.index('product: "fantasy"') < block.index('product: "betting"'), (
        "the signed-out nav leads with betting; the home page and About lead with fantasy"
    )


def test_the_betting_door_is_a_route_an_anonymous_visitor_can_actually_open(copy_src):
    """⛔ THE TEMPTING WRONG FIX. `/performance`, `/dashboard`, `/picks/*`, `/props` and
    `/ev-tracker` are all mounted `dependencies=_paid`, so pointing the nav's MLB door at any of
    them puts a login wall behind a product label — the one surprise a first-touch nav link cannot
    afford. The public MLB surface is the home page's featured read."""
    block = copy_src.split("export const SIGNED_OUT_NAV", 1)[1].split("\n]", 1)[0]
    betting_rows = [ln for ln in block.split("\n") if 'product: "betting"' in ln]
    assert betting_rows, "no betting row found — this clause would be vacuous"
    for row in betting_rows:
        for gated in ("/performance", "/dashboard", "/picks", "/props", "/ev-tracker"):
            assert gated not in row, (
                f"the signed-out MLB door points at {gated}, which refuses an anonymous caller: "
                f"{row.strip()!r}"
            )


def test_the_faq_is_reachable_from_the_signed_out_nav(copy_src):
    """Spec §22. The FAQ had NO nav entry at any viewport before this story — it was reachable only
    from the footer and from an About CTA."""
    block = copy_src.split("export const SIGNED_OUT_NAV", 1)[1].split("\n]", 1)[0]
    assert '"/faq"' in block, "the FAQ is still absent from the signed-out navigation"


def test_every_signed_out_nav_href_resolves_to_a_real_route(copy_src):
    """⭐ THE COVERAGE THIS STORY RELOCATED, RE-CLOSED HERE.

    `test_e9_56c_cta_routes.py` catches a link pointing at a route with no `page.tsx` — but it scans
    `.tsx` files for LITERAL `href="/…"`, and these entries now live in a `.ts` data module, so they
    fell out of its scope. That is exactly the comment the pre-E9.60 nav carried as its reason for
    writing the links as inline JSX. The coverage is not lost, it is re-derived here against the
    same filesystem route table."""
    block = copy_src.split("export const SIGNED_OUT_NAV", 1)[1].split("\n]", 1)[0]
    hrefs = re.findall(r'href:\s*"(/[^"]*)"', block)
    # `TRACK_RECORD_TRUST_LINK.href` is a symbol rather than a literal, so it is resolved from its
    # own module — otherwise this clause would silently skip the one entry it does not spell out.
    claim_copy = _strip_ts_comments((_FRONTEND / "lib/fantasy-claim-copy.ts").read_text())
    trust = re.search(
        r"TRACK_RECORD_TRUST_LINK[^{]*\{(?:[^}]*?)href:\s*\"(/[^\"]*)\"", claim_copy, re.S
    )
    assert trust, "could not resolve TRACK_RECORD_TRUST_LINK.href — this clause would under-cover"
    hrefs.append(trust.group(1))
    assert len(hrefs) >= 5, f"only {len(hrefs)} href(s) resolved — this clause would be vacuous"

    static = set()
    for page in _APP.rglob("page.tsx"):
        parts = [
            p
            for p in page.relative_to(_APP).parent.parts
            if not (p.startswith("(") and p.endswith(")"))
        ]
        if any(p.startswith("[") for p in parts):
            continue
        static.add("/" + "/".join(parts) if parts else "/")

    broken = [h for h in hrefs if (h.split("#")[0].rstrip("/") or "/") not in static]
    assert not broken, (
        f"signed-out nav link(s) point at a route with no page.tsx — a 404 behind a nav item: "
        f"{broken}"
    )


def test_the_nav_renders_the_signed_out_set_rather_than_the_fantasy_only_one():
    """Copy that exists but is never rendered is the "wired but never invoked" class (NF-C0e (b)).
    The module is only the fix if the component actually reads it — and the old fantasy-only source
    must be gone from the signed-out path, or both render and the nav simply doubles up."""
    nav = _strip_ts_comments(_NAV_TSX.read_text())
    assert "SIGNED_OUT_NAV" in nav, "the nav does not read the signed-out navigation model"
    assert "publicNavItems" not in nav, (
        "the nav still renders `publicNavItems()`, which is fantasy-only — the MLB door would be a "
        "duplicate rather than a fix"
    )


def test_about_remains_reachable_for_a_signed_in_visitor():
    """⚠️ A REGRESSION THIS STORY COULD EASILY HAVE SHIPPED. The About link used to render
    unconditionally; folding it into `SIGNED_OUT_NAV` (which renders only when `!showSubNav`) would
    have quietly removed it for every visitor with an account. Both halves are asserted because the
    signed-out one alone would pass with the signed-in link deleted."""
    nav = _strip_ts_comments(_NAV_TSX.read_text())
    assert "showSubNav && (" in nav and 'href="/about"' in nav, (
        "there is no About link on the signed-in path — the rewrite dropped it"
    )


def test_the_footer_reaches_both_pages_this_story_rewrote():
    """The footer renders on EVERY page (`app/layout.tsx`) and carried FAQ but not About, so the two
    rewritten pages linked to each other in one direction only. The track record — the site's
    central trust asset — was absent from it entirely."""
    footer = _strip_ts_comments(_FOOTER_TSX.read_text())
    for href in ('href: "/about"', 'href: "/faq"', 'href: "/fantasy/track-record"'):
        assert href in footer, f"the site footer no longer reaches {href}"
