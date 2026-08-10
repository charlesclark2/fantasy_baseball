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

PICKS = REPO / "app/backend/routers/picks.py"
WSS = REPO / "scripts/write_serving_store.py"

SUITE = "betting_ml/tests/test_e9_46_home_copy.py"
NF_TR1_SUITE = "betting_ml/tests/test_nf_tr1_claim_copy.py"
SEL_SUITE = "betting_ml/tests/test_e9_46_featured_selection.py"

# The two ORDER BY clauses the featured-selection cases swap between: the shared constant the code
# uses now, and the pre-2026-08-08 rule that sorted on the clock.
_START_TIME_RULE = "ORDER BY game_datetime ASC NULLS LAST, game_pk ASC"

# Unique anchor for the ROUTER's today query specifically — `{_FEATURED_ORDER_BY}` appears four
# times in picks.py, so a bare anchor would patch whichever came first regardless of intent.
_ROUTER_TODAY_TAIL = """       total_line, market_pref, pick_side
FROM totals
{_FEATURED_ORDER_BY}
LIMIT 1
\"\"\"

# ⭐⭐ THE CARRY-OVER QUERY"""

# …and for the stale-fallback query, which is the one that was dead in production.
_ROUTER_STALE_TAIL = """       total_line, market_pref, actual_outcome, pick_side
FROM totals
{_FEATURED_ORDER_BY}"""

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
     '    "A demonstration, not a recommendation. We look at',
     '    "We look at',
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

    # ══ E9.46 REVISION 2 — THE FEATURED-PICK SELECTION RULE (operator, 2026-08-08) ═════════════
    #
    # ⭐ The pair below is the whole argument for `TestTheQueriesActuallyRun`, and they are the
    # same break aimed at two different guards. Restoring `ABS(edge)` re-introduces the exact
    # production defect: valid Snowflake, reads correctly, and DuckDB cannot bind it — so
    # `lakehouse_query` swallows a BinderException into `[]` and the home page silently shows the
    # empty state. A TEXT guard catches the token; only the EXECUTION guard catches the class, and
    # the class is what shipped. Neither implies the other.
    ("wrap the gap in ABS again — the ORDER BY token", PICKS,
     _ROUTER_STALE_TAIL,
     _ROUTER_STALE_TAIL.replace(
         "{_FEATURED_ORDER_BY}",
         "ORDER BY ABS(edge) DESC NULLS LAST, game_datetime ASC NULLS LAST, game_pk ASC, market_type ASC"),
     "test_the_gap_is_never_wrapped_in_a_function_in_an_order_by", SEL_SUITE),

    ("wrap the gap in ABS again — the query stops binding", PICKS,
     _ROUTER_STALE_TAIL,
     _ROUTER_STALE_TAIL.replace(
         "{_FEATURED_ORDER_BY}",
         "ORDER BY ABS(edge) DESC NULLS LAST, game_datetime ASC NULLS LAST, game_pk ASC, market_type ASC"),
     "TestTheQueriesActuallyRun::test_the_query_binds_and_returns_a_row_on_duckdb", SEL_SUITE),

    # ⚠️ ISOLATED FROM THE PAIR ABOVE ON PURPOSE (NF-D17 §7). This break BINDS fine — every key is
    # a selected column — so it can only be caught by the cherry-pick guard. A break that tripped
    # both clauses at once would prove neither.
    ("carry forward yesterday's WINNER instead of yesterday's pick", PICKS,
     _ROUTER_STALE_TAIL,
     _ROUTER_STALE_TAIL.replace(
         "{_FEATURED_ORDER_BY}",
         "ORDER BY actual_outcome DESC NULLS LAST, edge DESC NULLS LAST, game_datetime ASC NULLS LAST"),
     "test_no_featured_query_selects_on_the_outcome", SEL_SUITE),

    ("go back to featuring the earliest game of the day", PICKS,
     _ROUTER_TODAY_TAIL,
     _ROUTER_TODAY_TAIL.replace("{_FEATURED_ORDER_BY}", _START_TIME_RULE),
     "test_the_widest_gap_beats_an_earlier_start", SEL_SUITE),

    # ⭐ THE DRIFT CASE. The rule is duplicated across six constants in two files; the recap is only
    # a recap while all six agree. Move the WRITER's copy alone and require it to be caught — the
    # router-side breaks above cannot detect a writer-side drift.
    ("let the serving writer drift away from the router", WSS,
     "       prediction_type, total_line, market_pref, pick_side\nFROM totals\n{_FEATURED_ORDER_BY}",
     "       prediction_type, total_line, market_pref, pick_side\nFROM totals\n" + _START_TIME_RULE,
     "test_every_featured_query_shares_the_rule", SEL_SUITE),

    # ⛔ ELIGIBILITY IS WHAT KEEPS THE SORT HONEST — without it, "the widest gap on the board" is a
    # maximum order statistic that selects our own worst row.
    ("sort on the gap with no agreement filter at all", PICKS,
     "    WHERE b.layer4_h2h_conviction_flag = TRUE\n      AND b.layer4_h2h_decision IN ('home', 'away')",
     "    WHERE b.layer4_h2h_decision IN ('home', 'away')",
     "test_a_game_our_models_disagree_on_is_never_featured_however_wide_the_gap", SEL_SUITE),

    ("draw the recap from qualified_bet instead of the featured set", PICKS,
     "      AND prediction_type IN ('post_lineup', 'morning')\n),\nbase AS (SELECT * FROM ranked WHERE _rn = 1),\nh2h AS (\n    SELECT b.game_pk, b.home_team, b.away_team, 'h2h' AS market_type,\n           b.game_datetime,",
     "      AND qualified_bet = TRUE\n),\nbase AS (SELECT * FROM ranked WHERE _rn = 1),\nh2h AS (\n    SELECT b.game_pk, b.home_team, b.away_team, 'h2h' AS market_type,\n           b.game_datetime,",
     "test_the_recap_uses_the_same_eligible_population_as_the_writer", SEL_SUITE),

    # ── the copy is only true while the ORDER BY holds ────────────────────────────────────────
    ("leave the retired start-time description in the copy", COPY,
     "and feature the one where our number sits furthest from the market's",
     "of those, the first to start",
     "test_the_retired_start_time_rule_is_gone_from_the_copy", SEL_SUITE),

    ("drop the maximum-order-statistic caveat from the gap explanation", COPY,
     " — and because we feature the largest one on the board, it is also the read most likely to be ours getting something wrong rather than the market's.",
     ".",
     "test_the_gap_caveat_survives_the_sort_key", SEL_SUITE),

    ("stop telling a visitor the carried-over card is not today's slate", COPY,
     "for the date shown above, not today's slate",
     "and it is current",
     "test_a_carried_over_card_says_which_day_it_is_for", SUITE),

    # ══ E9.46 REVISION 3 — THE MARKET ALTERNATES (operator, 2026-08-08) ════════════════════════
    #
    # ⭐ THE SUBTLEST BREAK IN THE WHOLE HARNESS, and the reason its guard exists. Making both
    # branches prefer the SAME market on the same parity pins the card to one market forever — and
    # every other assertion still passes, because the ORDER BY is intact, the query binds, and the
    # gap still decides within the market. Only a direct comparison of the two fragments sees it.
    ("make both market branches prefer the same market", PICKS,
     '_MARKET_PREF_TOTALS = "CASE WHEN DAYOFYEAR(b.game_date) % 2 = 0 THEN 1 ELSE 0 END AS market_pref"',
     '_MARKET_PREF_TOTALS = "CASE WHEN DAYOFYEAR(b.game_date) % 2 = 0 THEN 0 ELSE 1 END AS market_pref"',
     "test_the_two_market_branches_are_exact_complements", SEL_SUITE),

    # …and the same break, aimed at the BEHAVIOUR rather than the fragments — the card stops
    # alternating. Two guards, two mechanisms, neither implying the other.
    ("pin the card to one market — the flip stops happening", PICKS,
     '_MARKET_PREF_TOTALS = "CASE WHEN DAYOFYEAR(b.game_date) % 2 = 0 THEN 1 ELSE 0 END AS market_pref"',
     '_MARKET_PREF_TOTALS = "CASE WHEN DAYOFYEAR(b.game_date) % 2 = 0 THEN 0 ELSE 1 END AS market_pref"',
     "test_the_market_flips_with_the_date", SEL_SUITE),

    # ⚠️ Keying the parity off the PARAMETER instead of the row. This binds and runs fine; it goes
    # wrong only on the three constants that resolve YESTERDAY, where it would silently recap the
    # wrong market. A behavioural test on today's card cannot see it — hence a structural guard.
    ("key the alternation off the query parameter instead of the row", PICKS,
     '_MARKET_PREF_H2H = "CASE WHEN DAYOFYEAR(b.game_date) % 2 = 0 THEN 0 ELSE 1 END AS market_pref"',
     '_MARKET_PREF_H2H = "CASE WHEN DAYOFYEAR(%(today)s::DATE) % 2 = 0 THEN 0 ELSE 1 END AS market_pref"',
     "test_the_alternation_keys_off_the_rows_own_date", SEL_SUITE),

    ("drop the market from the sort so the widest gap wins outright", PICKS,
     '    "ORDER BY market_pref ASC, edge DESC NULLS LAST, "\n    "game_datetime ASC NULLS LAST, game_pk ASC, market_type ASC"',
     '    "ORDER BY edge DESC NULLS LAST, "\n    "game_datetime ASC NULLS LAST, game_pk ASC, market_type ASC"',
     "test_the_days_market_beats_a_much_wider_gap_in_the_other", SEL_SUITE),

    # ⛔ The fallback: turning the preference into a FILTER makes the card go empty on a day when
    # its market has nothing, which is strictly worse than showing the other market with a label.
    ("turn the market preference into a hard filter", PICKS,
     "    WHERE b.layer4_h2h_conviction_flag = TRUE\n      AND b.layer4_totals_decision IN ('over', 'under')",
     "    WHERE b.layer4_h2h_conviction_flag = TRUE\n      AND DAYOFYEAR(b.game_date) % 2 = 1\n      AND b.layer4_totals_decision IN ('over', 'under')",
     "test_the_other_market_is_featured_when_the_days_market_has_nothing", SEL_SUITE),

    ("promise strict alternation the SQL does not guarantee", COPY,
     "on the moneyline or on the total, usually alternating between them so you see both",
     "alternating strictly between the moneyline and the total, one each day",
     "test_the_frame_does_not_promise_strict_alternation", SUITE),

    ("stop naming which market the card is making", CARD_MLB,
     "                {market.label}",
     "                {\"Today's read\"}",
     "test_the_card_renders_the_market_label", SUITE),

    # ══ THE CARRY-OVER IS A POINT READ ════════════════════════════════════════════════════════
    #
    # ⭐ Send it back through the lakehouse — the path that CANNOT deliver it in production (a
    # `SELECT p.*` over 94 columns, swallowed into `[]` inside the Lambda). The guard wires
    # `lakehouse_query` to raise, so a carry-over that depends on it cannot pass.
    ("make the carry-over depend on the lakehouse again", PICKS,
     "    _carried = _carry_over_recent_featured(today)\n    if _carried is not None:\n        return _carried",
     "    _carried = None\n    if _carried is not None:\n        return _carried",
     "test_the_previous_days_published_read_is_served_without_touching_the_lakehouse", SEL_SUITE),

    ("serve a carried-over card without saying it is one", PICKS,
     '        patched = {**blob, "is_stale": True, "is_preliminary": False}',
     '        patched = {**blob, "is_preliminary": False}',
     "test_a_carried_over_card_announces_itself_but_keeps_its_recap", SEL_SUITE),

    # ⭐ The regression this replaces an earlier case with: throwing the recap away was the FIRST
    # cut's behaviour, and it cost the card its only published result.
    ("throw away the recap on a carried-over card", PICKS,
     '        patched = {**blob, "is_stale": True, "is_preliminary": False}',
     '        patched = {**blob, "is_stale": True, "is_preliminary": False, "yesterday": None}',
     "test_a_carried_over_card_announces_itself_but_keeps_its_recap", SEL_SUITE),

    # ⚠️ The off-by-one I shipped in the first draft of the date label: rendering `pick_date`
    # directly labels the day BEFORE's result with the CARD's date.
    ("label the recap with the card's own date instead of the day before", CARD_MLB,
     "    d.setDate(d.getDate() - 1)",
     "    d.setDate(d.getDate())",
     "test_the_carried_recap_is_labelled_with_the_day_it_is_for", SUITE),

    ("let the carry-over shadow a published slate", PICKS,
     "    _carried = _carry_over_recent_featured(today)\n    if _carried is not None:\n        return _carried\n\n    # G100-D1",
     "    # moved above the today lookups\n\n    # G100-D1",
     "test_todays_own_read_is_preferred_over_the_carry_over", SEL_SUITE),

    ("carry a card forward from arbitrarily far back", PICKS,
     "_CARRY_OVER_MAX_DAYS = 3",
     "_CARRY_OVER_MAX_DAYS = 30",
     "test_it_reaches_back_past_a_missing_day_but_not_indefinitely", SEL_SUITE),

    ("carry forward a day on which nothing qualified", PICKS,
     '        if not blob or blob.get("game_pk") is None:',
     "        if not blob:",
     "test_an_empty_shell_blob_is_not_carried_over", SEL_SUITE),

    ("render an over/under lean without the line it is about", CARD_MLB,
     "        ? `${side} ${data.total_line}`",
     "        ? `${side}`",
     "test_a_totals_lean_carries_the_line_it_is_about", SUITE),
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
