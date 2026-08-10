#!/usr/bin/env python3
"""E9.60 RED PROOF — break the source one defect at a time, require the NAMED test to go RED.

    uv run python betting_ml/tests/e9_60_positioning_copy_red_proof.py
    uv run python betting_ml/tests/e9_60_positioning_copy_red_proof.py kelly   # one case, by substring

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix, and `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run by hand whenever `test_e9_60_positioning_copy.py` is refactored.

WHY IT EXISTS. E9.60's suite is COPY GOVERNANCE — it asserts that a sentence contains a hedge, that
a capability sits in the right list, and that a link points somewhere. That is precisely the shape
which reads as coverage while proving nothing: this repo has shipped a source-inspection guard a
COMMENT could satisfy (INC-38), and a guard on an `and`-composed rule whose fixture a different
clause already refused, so deleting the clause it NAMED changed nothing observable (NF-D17 §7).

⭐ IT EARNED ITS KEEP BEFORE IT WAS EVEN WRITTEN. Four clauses in the first cut of the suite picked
the WRONG STRING — About and the FAQ deliberately make the same points in different words, so
`"featured MLB read"` matched an About bullet rather than the FAQ answer — and a fifth matched
`"bot"` inside the word `"both"`. All five failed loudly rather than silently, which is the only
reason they were fixed rather than shipped; the `faq_answers` fixture exists because of them.

⭐ EVERY CASE IS ISOLATING. Per NF-D17 §7, a fixture that trips more than one clause proves none of
them: each break below leaves every OTHER clause satisfiable, so only the named one can flip.

⚠️ THE HARNESS ASSERTS ITS OWN MUTATION LANDED. A red-proof whose patch silently no-ops reports
"the guard caught it" when nothing was ever broken — the scarier false finding, and one this repo
has hit (E11.24 #682). A missing anchor is counted as a FAILURE here, never skipped.

Restores every file from an IN-MEMORY backup in a `finally` block. ⛔ Deliberately does NOT use
`git checkout --` the way `frontend/e2e/red-proof.mjs` does — that harness destroys uncommitted work
in the files it patches (it ate an in-progress `subscribe/page.tsx` at E9.59).
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COPY = REPO / "frontend/lib/positioning-copy.ts"
ABOUT = REPO / "frontend/app/about/page.tsx"
FAQ = REPO / "frontend/app/faq/page.tsx"
NAV = REPO / "frontend/components/nav.tsx"
FOOTER = REPO / "frontend/components/site-footer.tsx"
NF_TR1 = REPO / "betting_ml/tests/test_nf_tr1_claim_copy.py"
NAV_MODEL = REPO / "frontend/lib/nav-model.ts"
LAYOUT = REPO / "frontend/app/layout.tsx"

SUITE = "betting_ml/tests/test_e9_60_positioning_copy.py"

#: (label, file, old, new, test-name-substring, suite)
CASES = [
    # ── the claim discipline reaches these surfaces ───────────────────────────────────────────
    ("put an edge claim in the About hero", COPY,
     'headline: "Better sports decisions start with knowing what you don\'t know.",',
     'headline: "The fantasy rankings that beat the market, guaranteed.",',
     "test_the_positioning_copy_passes_the_denylist", SUITE),

    # ⚠️ THE BREAK MUST USE A TERM THE *GATE* KNOWS. `gates._DEFAULT_CLAIM_DENYLIST` is a deliberate
    # SUBSET of the export's, so a term like "more accurate" trips the denylist clause and is
    # INVISIBLE to the gate — breaking a gate clause with a non-gate term proves nothing about the
    # gate. "beats the market" is in both. (The same note is on E9.46's harness, for the same trap.)
    ("make the copy fail the governance gate", COPY,
     'lede: "Credence compares model-implied probabilities with the betting market',
     'lede: "Credence beats the market on MLB pricing and compares probabilities',
     "test_the_governance_gate_passes_the_positioning_copy", SUITE),

    ("write a paragraph inline in the About JSX", ABOUT,
     "<h2 className=\"text-xl font-bold text-white mb-4\">{heading}</h2>",
     "<h2 className=\"text-xl font-bold text-white mb-4\">{heading}</h2>\n      <p>{\"Credence Sports is an analytics platform that publishes model projections and a market comparison for every game on the slate, every single day.\"}</p>",
     "test_the_pages_carry_no_unscreened_prose", SUITE),

    ("drop About from the NF-TR1 marketing registry", NF_TR1,
     "_MARKETING_SURFACES = (_UPGRADE_BANNER_TSX, _SUBSCRIBE_TSX, _HOME_PAGE_TSX, _ABOUT_TSX, _FAQ_TSX)",
     "_MARKETING_SURFACES = (_UPGRADE_BANNER_TSX, _SUBSCRIBE_TSX, _HOME_PAGE_TSX, _FAQ_TSX)",
     "test_the_marketing_surfaces_are_registered_with_nf_tr1", SUITE),

    # ── one story: two products, fantasy first ────────────────────────────────────────────────
    ("put betting before fantasy on About", COPY,
     '    key: "fantasy",\n    label: "Fantasy decision tools",',
     '    key: "betting_PLACEHOLDER",\n    label: "Fantasy decision tools",',
     "test_about_declares_both_products_fantasy_first", SUITE),

    ("restore the baseball-only About subhead", COPY,
     'subhead:\n    "Credence Sports builds fantasy decision tools and betting intelligence',
     'subhead:\n    "We forecast baseball the way the evidence supports. Credence builds tools',
     "test_about_no_longer_describes_a_baseball_only_company", SUITE),

    ("put the betting FAQ section before the fantasy one", COPY,
     'category: "Fantasy football",',
     'category: "Zebra football",',
     "test_the_faq_covers_both_products_in_the_site_order", SUITE),

    ("restore the MLB-only FAQ answer", COPY,
     'a: "NFL fantasy football and MLB betting intelligence are live today.',
     'a: "MLB baseball only, for the 2026 season. We are focused on doing one sport well.',
     "test_the_faq_no_longer_says_the_company_is_mlb_only", SUITE),

    # ── only what is live reads as live ───────────────────────────────────────────────────────
    ("advertise start/sit as available now", COPY,
     '      items: ["Draft rankings", "Player projections", "Projection ranges"],',
     '      items: ["Draft rankings", "Start/sit decision support"],',
     "test_no_unshipped_fantasy_capability_sits_in_a_live_list", SUITE),

    # ⭐ THE OTHER SIDE OF THE SAME RULE. Deleting the roadmap satisfies "nothing un-shipped is in a
    # live list" completely, and hides the roadmap from a visitor deciding whether to subscribe.
    ("delete the weekly tools from the roadmap instead of labelling them", COPY,
     '        "Weekly projections",\n        "Start/sit decision support",',
     '        "A thing",\n        "Another thing",',
     "test_the_unshipped_capabilities_are_still_named_as_coming", SUITE),

    ("link a coming-soon capability", ABOUT,
     '            {product.coming.items.map((i) => (\n              <li key={i} className="text-sm text-gray-500 leading-relaxed">\n                {i}\n              </li>',
     '            {product.coming.items.map((i) => (\n              <li key={i} className="text-sm text-gray-500 leading-relaxed">\n                <Link href="/fantasy/draft">{i}</Link>\n              </li>',
     "test_the_coming_lists_are_never_rendered_as_links", SUITE),

    ("advertise SIM-V1 in the evaluation section", COPY,
     'body: "Sports outcomes are noisy, so a projection should carry more than a single point estimate.',
     'body: "Our SIM-V1 known-truth gate simulation stress-tests every range. Sports outcomes are noisy.',
     "test_about_does_not_advertise_unbuilt_simulation", SUITE),

    # ── the record is described the way it is served ──────────────────────────────────────────
    ("advertise the MLB record as public", COPY,
     "lands on the members' scorecard; every past fantasy season",
     "lands on our public track record; every past fantasy season",
     "test_the_mlb_record_is_not_advertised_as_public", SUITE),

    # ⭐ THE INVERSE BREAK. Collapsing BOTH records into "members only" passes the clause above and
    # throws away the site's one freely-inspectable proof asset — the wrong correction.
    ("hide that the fantasy record is open to anyone", COPY,
     'a: "The fantasy track record is open to anyone with no account:',
     'a: "The fantasy track record sits behind the same membership as everything else:',
     "test_the_public_fantasy_record_is_still_described_as_open", SUITE),

    ("drop the honest limit from the accountability section", COPY,
     "    \"What that record has not shown is a durable advantage over the closing market, and we would",
     "    \"What that record shows is a real and repeatable signal, and we would",
     "test_the_record_copy_states_both_halves", SUITE),

    # ── the free/paid line matches the shipped tier ───────────────────────────────────────────
    ("stop naming the free preset in the free/paid answer", COPY,
     'a: "Free, including without an account: the full rankings board at full-PPR twelve teams',
     'a: "Free, including without an account: a generous rankings board',
     "test_the_free_tier_is_described_as_the_freemium_build_shipped_it", SUITE),

    ("sell the paid line as anti-scraping", COPY,
     'STAT_LINE_PLACEHOLDER_UNUSED',
     'STAT_LINE_PLACEHOLDER_UNUSED',
     "test_the_paid_line_is_never_sold_as_anti_scraping", SUITE),

    # ── the FAQ stopped telling visitors how much to bet ──────────────────────────────────────
    ("put Kelly sizing guidance back in the FAQ", COPY,
     'q: "What does Expected Value mean on the EV tracker?",',
     'q: "What is Kelly % and how much should I bet?",',
     "test_the_faq_carries_no_stake_sizing_guidance", SUITE),

    ("drop the conditional from the EV answer", COPY,
     "Expected Value is the arithmetic value a price would carry if the probability estimate behind it were correct.",
     "Expected Value is the arithmetic value a price carries over time.",
     "test_the_ev_answer_is_conditional_rather_than_a_promise", SUITE),

    ("describe the consensus as a single book again", COPY,
     'a: "A de-vigged market consensus, not one designated sportsbook.',
     'a: "A de-vigged market consensus taken from Bovada, our benchmark book.',
     "test_the_market_consensus_is_described_as_the_code_computes_it", SUITE),

    ("let models-agree read as market confidence", COPY,
     "It is computed without looking at the odds at all.",
     "It is computed from the odds and our own estimates together.",
     "test_the_models_agree_answer_describes_what_is_measured", SUITE),

    ("sell the featured read as the best bet", COPY,
     "It is a demonstration, not a recommendation, and it is not labelled the day's best bet.",
     "It is the strongest read on the board and the one we would look at first.",
     "test_the_featured_read_is_not_sold_as_the_best_bet", SUITE),

    # ── every signed-out nav entry opens for the visitor it is drawn for ───────────────────────
    # ⚠️ THIS CASE CHANGED THE GUARD, NOT JUST THE BREAK. The first cut asserted only
    # `product: "fantasy"` — which FOUR entries carry, so no single edit can falsify it, and the
    # break (flipping one entry) correctly stayed GREEN. That is an unfalsifiable clause, i.e. the
    # NF1.7(a) vacuous-anchor class hiding inside a passing suite. The guard now asserts the free
    # board's own href, which is both the sharper claim and single-edit breakable. Found by this
    # harness's vacuity check, which is exactly what it exists for.
    ("remove the free board's door from the signed-out nav", COPY,
     '    href: "/fantasy/rankings",',
     '    href: "/fantasy/projections",',
     "test_the_signed_out_nav_carries_the_fantasy_product", SUITE),

    # ⭐ OPERATOR, 2026-08-09 — the label must NAME the sport. The break restores the exact string
    # that shipped before this change, so it proves the guard catches the real prior state rather
    # than an invented one.
    ("go back to the ambiguous bare 'Fantasy' label", COPY,
     '    short: "Fantasy Football",',
     '    short: "Fantasy",',
     "test_the_fantasy_door_names_its_sport", SUITE),

    # ⚠️ The break has to move the COMPANY entries above the product ones, since there is no longer
    # a betting entry to reorder against.
    ("put the company pages before the product ones", COPY,
     '  { label: "About", href: "/about", product: null, desktop: true },\n  { label: "FAQ", href: "/faq", product: null, desktop: false },\n]',
     ']',
     "test_the_signed_out_nav_is_fantasy_first", SUITE),

    ("point a signed-out nav entry at a paid route", COPY,
     '{ label: "Projections", href: "/fantasy/projections", product: "fantasy", desktop: false },',
     '{ label: "Projections", href: "/performance", product: "fantasy", desktop: false },',
     "test_no_signed_out_nav_entry_points_at_a_route_that_refuses_an_anonymous_caller", SUITE),

    # ⭐⭐ THE OPERATOR'S REVERSAL OF THIS STORY'S OWN FIRST CUT, proven catchable. The break is
    # verbatim the row E9.60 originally shipped — so this case fails the moment someone re-adds it.
    ("re-add the MLB anchor door to the signed-out nav", COPY,
     '  { label: "About", href: "/about", product: null, desktop: true },',
     '  { label: "MLB betting intelligence", short: "MLB", href: "/#today", product: "betting", desktop: true },\n  { label: "About", href: "/about", product: null, desktop: true },',
     "test_the_signed_out_nav_has_no_mlb_door", SUITE),

    ("drop the FAQ from the signed-out nav", COPY,
     '  { label: "FAQ", href: "/faq", product: null, desktop: false },',
     '  { label: "Contact", href: "/contact", product: null, desktop: false },',
     "test_the_faq_is_reachable_from_the_signed_out_nav", SUITE),

    # ⭐ THE COVERAGE THIS STORY RELOCATED. `test_e9_56c_cta_routes.py` cannot see these hrefs (they
    # live in a `.ts` module, and it scans `.tsx` for literals), so a dead nav link is invisible to
    # it. This proves the replacement guard actually catches one.
    ("point a signed-out nav link at a route that does not exist", COPY,
     '{ label: "About", href: "/about", product: null, desktop: true },',
     '{ label: "About", href: "/pricing", product: null, desktop: true },',
     "test_every_signed_out_nav_href_resolves_to_a_real_route", SUITE),

    ("leave the nav rendering the fantasy-only public items", NAV,
     "SIGNED_OUT_NAV.filter((item) => item.desktop).map((item) => (",
     "publicNavItems().filter((item) => item.desktop).map((item) => (",
     "test_the_nav_renders_the_signed_out_set_rather_than_the_fantasy_only_one", SUITE),

    # ⭐ THE REGRESSION THIS STORY COULD EASILY HAVE SHIPPED, proven catchable.
    ("drop About for signed-in visitors", NAV,
     '          {showSubNav && (\n            <Link\n              href="/about"',
     '          {false && (\n            <Link\n              href="/about-removed"',
     "test_about_remains_reachable_for_a_signed_in_visitor", SUITE),

    ("drop About from the site footer", FOOTER,
     '  { label: "About", href: "/about" },\n',
     '',
     "test_the_footer_reaches_both_pages_this_story_rewrote", SUITE),
]

# ⚠️ The anti-scraping case needs a real sentence rather than a token swap, so it is built here
# instead of as a two-string replace above (the placeholder rows keep the table shape uniform).
CASES += [
    # ── the verify-flag: an in-flight capability must not read as shipped ──────────────────────
    ("promise the in-flight free personalized league", COPY,
     'export const FAQ_HEADER = {',
     'export const FREE_LEAGUE_CLAIM = "A free account can keep one personalized league."\n\nexport const FAQ_HEADER = {',
     "test_the_in_flight_free_league_grant_is_not_promised_as_live", SUITE),

    ("put personalization back in the Available-now list", COPY,
     '      items: ["Draft rankings", "Player projections", "Projection ranges"],',
     '      items: ["Draft rankings", "Player projections", "Per-league personalization"],',
     "test_the_available_now_list_holds_only_what_was_verified_serving", SUITE),

    # ── ⭐ the LIVE mobile-nav bug ─────────────────────────────────────────────────────────────
    ("remove the mobile menu height cap", NAV,
     '  "max-h-[calc(100dvh-4.25rem)] overflow-y-auto overscroll-contain"',
     '  "overflow-y-auto overscroll-contain"',
     "test_the_mobile_menu_is_capped_to_the_viewport", SUITE),

    # ⚠️ ANCHORED ON THE CODE LINE, NOT THE BARE TOKEN. `max-h-[calc(100dvh-4.25rem)]` appears in
    # the panel's DOC COMMENT first, so a first-occurrence patch broke the COMMENT — which the
    # guard strips before scanning — and the clause reported GREEN on an unbroken class string.
    # The same first-occurrence collision `docs/freemium_tier.md` records for `allows_board`.
    ("cap the mobile menu on a static viewport unit", NAV,
     '  "max-h-[calc(100dvh-4.25rem)] overflow-y-auto overscroll-contain"',
     '  "max-h-[calc(100vh-4.25rem)] overflow-y-auto overscroll-contain"',
     "test_the_mobile_menu_cap_uses_the_dynamic_viewport_unit", SUITE),

    ("let the mobile menu chain its scroll to the page", NAV,
     " overscroll-contain\"", "\"",
     "test_the_mobile_menu_does_not_chain_its_scroll_to_the_page", SUITE),

    ("fix only ONE of the two mobile panels", NAV,
     "{!showSubNav && mobileOpen && (\n        <div className={MOBILE_MENU_PANEL}>",
     "{!showSubNav && mobileOpen && (\n        <div className=\"border-t px-4 py-3 sm:hidden\">",
     "test_both_mobile_panels_use_the_shared_capped_class", SUITE),

    # ── nav IA ────────────────────────────────────────────────────────────────────────────────
    ("put MLB before fantasy in the signed-in nav", NAV_MODEL,
     '    sport: "nfl",\n    label: "NFL",', '    sport: "zzz",\n    label: "NFL",',
     "test_the_signed_in_nav_is_fantasy_first", SUITE),

    ("drop the top-level Track Record link", NAV,
     '            href="/fantasy/track-record"', '            href="/changelog"',
     "test_track_record_is_a_top_level_nav_entry_in_both_auth_states", SUITE),

    ("put MLB before fantasy in the footer", FOOTER,
     '  { label: "Fantasy Football", href: "/fantasy/rankings" },\n  { label: "MLB Betting Intelligence", href: "/#today" },',
     '  { label: "MLB Betting Intelligence", href: "/#today" },\n  { label: "Fantasy Football", href: "/fantasy/rankings" },',
     "test_the_footer_leads_with_the_fantasy_product", SUITE),

    ("make an unshipped footer product clickable", FOOTER,
     '  { label: "NFL Betting Intelligence" },',
     '  { label: "NFL Betting Intelligence", href: "/nfl" },',
     "test_an_unshipped_product_is_listed_in_the_footer_but_carries_no_link", SUITE),

    ("put MLB before fantasy in the SEO description", LAYOUT,
     "NFL fantasy rankings and MLB betting intelligence",
     "MLB betting intelligence and NFL fantasy rankings",
     "test_the_site_description_is_fantasy_first", SUITE),
]

CASES = [c for c in CASES if c[2] != "STAT_LINE_PLACEHOLDER_UNUSED"] + [
    ("sell the paid line as anti-scraping", COPY,
     'export const FAQ_HEADER = {',
     'export const SCRAPE_CLAIM = "Member numbers are held back to stop scrapers and bots lifting our board."\n\nexport const FAQ_HEADER = {',
     "test_the_paid_line_is_never_sold_as_anti_scraping", SUITE),
]


def run(test: str, suite: str) -> tuple[int, str]:
    p = subprocess.run(
        ["uv", "run", "pytest", suite, "-k", test, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    cases = [c for c in CASES if not only or only in c[0]] or CASES
    backups = {p: p.read_text() for p in {c[1] for c in cases}}
    failures: list[str] = []

    try:
        for name, path, old, new, test, suite in cases:
            src = backups[path]
            if old not in src:
                # ⚠️ A STALE ANCHOR IS A FAILURE, NOT A SKIP — an UNPROVEN clause reading as a quiet
                # one. And it is how a red-proof reports a phantom pass (E11.24 #682).
                failures.append(f"{name}: PATCH ANCHOR NOT FOUND")
                print(f"⚠️  {name}: anchor not found")
                continue
            patched = src.replace(old, new, 1)
            # ⚠️ PROVE THE MUTATION LANDED before trusting the verdict. A no-op patch makes "the
            # guard went red" and "nothing was broken" indistinguishable.
            if patched == src:
                failures.append(f"{name}: PATCH WAS A NO-OP")
                print(f"⚠️  {name}: patch did not change the file")
                continue
            path.write_text(patched)
            code, out = run(test, suite)
            path.write_text(src)
            print(f"{'RED ✅' if code else 'GREEN ❌ (vacuous!)'}  {name}  ->  {test}")
            if code == 0:
                failures.append(f"{name} -> {test} stayed GREEN")
                print("   " + out.replace("\n", "\n   ")[:1500])
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
