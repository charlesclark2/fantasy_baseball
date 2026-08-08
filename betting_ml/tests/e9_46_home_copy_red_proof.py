#!/usr/bin/env python3
"""E9.46 RED PROOF — break the source one defect at a time, require the NAMED test to go RED.

    uv run python betting_ml/tests/e9_46_home_copy_red_proof.py
    uv run python betting_ml/tests/e9_46_home_copy_red_proof.py blog     # one case, by substring

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix, and `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run by hand whenever `test_e9_46_home_copy.py` is refactored.

WHY IT EXISTS. E9.46's suite is COPY GOVERNANCE — it asserts that a sentence contains a disclaimer
and that a link points somewhere. That is precisely the shape which reads as coverage while proving
nothing: this repo has shipped a source-inspection guard a COMMENT could satisfy (INC-38), and a
guard on an `and`-composed rule whose fixture was already refused by a different clause, so
deleting the clause it NAMED changed nothing observable (NF-D17 §7). Both were found only by
breaking the source and noticing the guard stayed green.

⭐ IT EARNED ITS KEEP IMMEDIATELY, in the same shape NF-TR1's did. `test_unshipped_roadmap_rows_
are_marked_not_live` extracted the roadmap by splitting on the identifier and then on the first
`]` — which lands inside the TYPE ANNOTATION `readonly {...}[]`, so it read an empty string. It was
caught by its own vacuity assertion rather than by a break, but the lesson is the same one: an
extractor that returns nothing makes every clause built on it vacuously true.

Restores every file from an IN-MEMORY backup in a `finally` block. ⛔ Deliberately does NOT use
`git checkout --` the way `frontend/e2e/red-proof.mjs` does — that harness destroys uncommitted work
in the files it patches (it ate an in-progress `subscribe/page.tsx` at E9.59).
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COPY = REPO / "frontend/lib/home-copy.ts"
PAGE = REPO / "frontend/app/page.tsx"
PICK = REPO / "frontend/components/home/pick-of-the-day.tsx"
NAV = REPO / "frontend/components/nav.tsx"
CARD = REPO / "frontend/components/home/featured-fantasy-player.tsx"
CARD_MLB = REPO / "frontend/components/home/pick-of-the-day.tsx"
FOOTER = REPO / "frontend/components/site-footer.tsx"
LAYOUT = REPO / "frontend/app/layout.tsx"
NF_TR1 = REPO / "betting_ml/tests/test_nf_tr1_claim_copy.py"

SUITE = "betting_ml/tests/test_e9_46_home_copy.py"
NF_TR1_SUITE = "betting_ml/tests/test_nf_tr1_claim_copy.py"

#: (label, file, old, new, test-name-substring, suite)
CASES = [
    # ── the denylist actually applies to the betting-side copy ────────────────────────────────
    ("put an edge claim back in the hero", COPY,
     'headline: "The number is only half the answer.",',
     'headline: "Daily edge over the market, quantified.",',
     "test_the_home_copy_passes_the_denylist", SUITE),

    # ⚠️ THE BREAK MUST USE A TERM THE *GATE* KNOWS, and the first attempt did not — which is a
    # finding worth keeping rather than a mistake to erase. `gates._DEFAULT_CLAIM_DENYLIST` is a
    # deliberate SUBSET of the export's (NF-TR1: "a term may be ADDED to the gate's list; it may
    # never be dropped from the export's"), so "more accurate" trips the denylist clause above and
    # is invisible to the gate. Breaking a gate clause with a non-gate term proves nothing about
    # the gate; "profitable" is on both lists.
    ("make a principle a profit claim", COPY,
     '    title: "We grade ourselves in public",',
     '    title: "We are profitable in public",',
     "test_the_governance_gate_passes_the_home_copy", SUITE),

    # ── the pick of the day is a demonstration, not a tout ────────────────────────────────────
    ("drop the not-a-recommendation disclaimer", COPY,
     '    "A demonstration, not a recommendation. Each day',
     '    "Each day',
     "test_the_pick_is_framed_as_a_demonstration", SUITE),

    ("call the gap an edge again", COPY,
     '    gap: "Gap",',
     '    gap: "Edge",',
     "test_the_gap_is_named_as_a_difference_not_as_an_edge", SUITE),

    ("render the served model narrative on the marketing page", PICK,
     "  conviction_label: string | null",
     "  conviction_label: string | null\n  model_narrative?: string | null",
     "test_the_home_page_does_not_render_served_model_prose", SUITE),

    ("collapse a failed read into the empty-slate message", PICK,
     "          <p className=\"text-sm leading-relaxed text-gray-400\">{COPY.unavailable}</p>",
     "          <p className=\"text-sm leading-relaxed text-gray-400\">{COPY.empty}</p>",
     "test_an_empty_read_and_a_failed_read_are_different_messages", SUITE),

    ("assert a verdict instead of a difference", COPY,
     '    "The distance between our probability and the market\'s de-vigged consensus probability.',
     '    "Where the market is mispriced relative to our probability.',
     "test_the_pick_block_never_claims_an_advantage", SUITE),

    # ── both verticals keep a door and a trust link ───────────────────────────────────────────
    ("send the fantasy door somewhere other than the free rankings", COPY,
     'cta: { label: "See the free rankings", href: "/fantasy/rankings" },',
     'cta: { label: "See the free rankings", href: "/subscribe" },',
     "test_both_verticals_are_declared_with_a_cta_and_a_trust_link", SUITE),

    ("hide that the MLB scorecard needs an account", COPY,
     'trust: { label: "How we grade out", href: "/performance", needsAccount: true },',
     'trust: { label: "How we grade out", href: "/performance", needsAccount: false },',
     "test_a_gated_trust_link_declares_that_it_is_gated", SUITE),

    ("paraphrase the canonical fantasy hook instead of reusing it", COPY,
     "    headline: PRODUCT_HOOK[0].title,\n    detail: PRODUCT_HOOK[0].detail,",
     '    headline: "Rankings for your league",\n    detail: "Every projection recomputed for your settings.",',
     "test_the_home_page_reuses_the_fantasy_canonical_copy_verbatim", SUITE),

    # E9.46 revision — the new clauses.
    # ⚠️ BROKEN BY DELETING THE RENDER, not by gating it behind `false`. The first attempt did the
    # latter and stayed GREEN — correctly: a SOURCE scan cannot see a render that is still present
    # but unreachable. That variant is covered at the render level instead, by
    # `home-positioning.spec.ts`'s "the rank gap never ships without its market-lean caveat", which
    # reads the actual DOM. Neither check implies the other and both are required.
    ("drop the market-lean caveat from the fantasy card", CARD,
     "                {data.leanNote}",
     "                {null}",
     "test_the_fantasy_card_always_renders_the_market_lean_caveat", SUITE),

    ("render the hardcoded conviction label instead of the measured one", CARD_MLB,
     "                  {COPY.agreementBadge}",
     "                  {data.conviction_label}",
     "test_the_mlb_badge_describes_what_was_measured", SUITE),

    ("let the MLB record be described as public", COPY,
     "the full daily record is on the members' scorecard",
     "the full daily record is public",
     "test_the_mlb_record_is_described_as_members_only", SUITE),

    ("drop the honest limit from the record sentence", COPY,
     " What that record has not shown is a durable advantage over the closing market, and we would rather say so here than let the card imply otherwise.",
     "",
     "test_the_record_sentence_states_both_halves", SUITE),

    ("lift the retired tagline back into the hero", COPY,
     '  headline: "The number is only half the answer.",',
     '  headline: "Daily edge, quantified.",',
     "test_the_retired_tagline_is_scoped_to_the_mlb_product", SUITE),

    ("drop the home page from the marketing-surface registry", NF_TR1,
     "_MARKETING_SURFACES = (_UPGRADE_BANNER_TSX, _SUBSCRIBE_TSX, _HOME_PAGE_TSX)",
     "_MARKETING_SURFACES = (_UPGRADE_BANNER_TSX, _SUBSCRIBE_TSX)",
     "test_the_home_page_is_registered_as_a_marketing_surface", SUITE),

    # ⚠️ BROKEN ON THE REGISTRY'S OWN SUITE, and it is the case that proves the registry does
    # something rather than merely existing: strand the home page's only route to the evidence and
    # require NF-TR1's link clause — not E9.46's — to catch it.
    ("strand the evidence — remove the home page's link to the track record", PAGE,
     "          href={TRACK_RECORD_TRUST_LINK.href}",
     '          href="/fantasy/projections"',
     "test_the_marketing_surfaces_link_to_the_track_record", NF_TR1_SUITE),

    # ── the roadmap is honest ─────────────────────────────────────────────────────────────────
    ("claim NCAAF is already live", COPY,
     '{ sport: "NCAAF", what: "Betting intelligence", when: "Coming this season", live: false },',
     '{ sport: "NCAAF", what: "Betting intelligence", when: "Coming this season", live: true },',
     "test_unshipped_roadmap_rows_are_marked_not_live", SUITE),

    # ⭐ THE OPERATOR'S OWN CORRECTION, pinned: a dated launch promise is a commitment a visitor can
    # check and find false on the day, which "coming this season" is not.
    ("put a dated launch promise back on the roadmap", COPY,
     '{ sport: "NCAAF", what: "Betting intelligence", when: "Coming this season", live: false },',
     '{ sport: "NCAAF", what: "Betting intelligence", when: "Around Aug 29", live: false },',
     "test_unshipped_roadmap_rows_are_marked_not_live", SUITE),

    ("let the roadmap promise results", COPY,
     "They are analysis rather than an assurance of results",
     "They are the picks you have been waiting for",
     "test_the_roadmap_note_refuses_to_promise_picks", SUITE),

    ("turn a coming-soon teaser into a link", PAGE,
     "              <span\n                className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-medium ${",
     "              <Link href=\"/ncaaf\" />\n              <span\n                className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-medium ${",
     "test_a_coming_soon_row_is_never_rendered_as_a_link", SUITE),

    # ── the blog demotion, both halves ────────────────────────────────────────────────────────
    ("put the blog back in the primary nav", NAV,
     '            href="/about"\n            className="hidden text-xs text-gray-500 hover:text-gray-300 transition-colors sm:block"\n          >\n            About\n          </Link>',
     '            href="/blog"\n            className="hidden text-xs text-gray-500 hover:text-gray-300 transition-colors sm:block"\n          >\n            About\n          </Link>',
     "test_the_blog_is_out_of_the_primary_nav", SUITE),

    # ⭐ THE OTHER DIRECTION, and the one that makes the clause above safe rather than merely
    # quieter: passing "no blog in the nav" by DELETING the blog is the dishonest way out.
    ("delete the blog from the footer instead of demoting it", FOOTER,
     '{ label: "Blog", href: "/blog" },\n',
     "",
     "test_the_blog_is_still_reachable", SUITE),

    ("feature a blog post on the home page again", PAGE,
     '          href="/blog"',
     '          href={`/blog/${post.title}`}',
     "test_the_home_page_no_longer_features_a_blog_post", SUITE),

    # ── the site-wide metadata ────────────────────────────────────────────────────────────────
    ("restore the edge claim in the site metadata", LAYOUT,
     "const SITE_DESCRIPTION =\n  'Transparent, model-driven sports analysis",
     "const SITE_DESCRIPTION =\n  'Bayesian sports analytics. Daily edge, quantified. Transparent, model-driven sports analysis",
     "test_the_site_description_makes_no_edge_claim", SUITE),

    # ── the guards on the guards ──────────────────────────────────────────────────────────────
    ("write inline prose on the page instead of in the copy module", PAGE,
     "        <p className=\"mt-6 text-xs leading-relaxed text-gray-600\">{FOOTER_CTA.disclaimer}</p>",
     "        <p className=\"mt-6 text-xs leading-relaxed text-gray-600\">{\"Everything here is analysis published for information only, it is not financial advice, and you alone are responsible for any wager you choose to place anywhere.\"}</p>",
     "test_the_page_and_component_carry_no_unscreened_prose", SUITE),
]


def run(test: str, suite: str) -> tuple[int, str]:
    p = subprocess.run(
        ["uv", "run", "pytest", f"{suite}::{test}", "-q", "--no-header"],
        cwd=REPO, capture_output=True, text=True,
    )
    return p.returncode, (p.stdout + p.stderr)[-1200:]


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    cases = [c for c in CASES if not only or only in c[0]] or CASES
    backups = {p: p.read_text() for p in {c[1] for c in cases}}
    failures: list[str] = []

    try:
        for name, path, old, new, test, suite in cases:
            src = backups[path]
            if old not in src:
                # ⚠️ A STALE ANCHOR IS A FAILURE, NOT A SKIP. NF-TR1's harness recorded a case that
                # silently reported "anchor not found" for a while — an UNPROVEN clause reading as
                # a quiet one. Count it.
                failures.append(f"{name}: PATCH ANCHOR NOT FOUND")
                print(f"⚠️  {name}: anchor not found")
                continue
            path.write_text(src.replace(old, new, 1))
            code, out = run(test, suite)
            path.write_text(src)
            print(f"{'RED ✅' if code else 'GREEN ❌ (vacuous!)'}  {name}  ->  {test}")
            if code == 0:
                failures.append(f"{name} -> {test} stayed GREEN")
                print("   " + out.replace("\n", "\n   "))
    finally:
        for p, src in backups.items():
            p.write_text(src)
        print("\nrestored all files")

    if failures:
        print("\n❌ VACUOUS CLAUSES:\n  " + "\n  ".join(failures))
        return 1
    print(f"\n✅ all {len(cases)} clauses RED-proven")
    return 0


if __name__ == "__main__":
    sys.exit(main())
