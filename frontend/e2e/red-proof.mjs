#!/usr/bin/env node
/**
 * E9.63 — RED PROOF: break the app on purpose, one defect at a time, and require the suite to FAIL.
 *
 *   npm run e2e:red-proof            # all cases
 *   npm run e2e:red-proof -- blank   # one case, by id substring
 *
 * ══ WHY THIS EXISTS AS A SCRIPT, NOT A ONE-OFF ══════════════════════════════════════════════════
 *
 * A green suite proves nothing on its own. A test that CANNOT fail is worse than no test: it reads
 * as coverage, so nobody looks again. This repo has been bitten by that specific shape more than
 * once (a source-inspection guard a COMMENT could satisfy; a guard on an `and`-composed rule whose
 * fixture was already refused by a different clause, so deleting the clause it named changed
 * nothing). Both were caught only by deliberately breaking the source and noticing the guard stayed
 * green.
 *
 * So each case below re-introduces a REAL, SHIPPED defect — every one of these was live in
 * production — and asserts the named spec goes red. Re-run it whenever the specs are refactored;
 * a case that stops failing means the assertion it names has quietly become decorative.
 *
 * The working tree is restored after every case, including on a crash (see `restoreAll`).
 */

import { execFileSync, spawnSync } from "node:child_process"
import { readFileSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..")

const CASES = [
  {
    id: "blank-locked-board",
    shipped: "E9.56b — Rankings rendered BLANK for every logged-out visitor",
    detail:
      "`p.pts != null` drops all 858 rows of a locked board, because a locked row carries no `pts`.",
    file: "components/fantasy/rankings-board.tsx",
    from: "(p) => (boardLocked || p.pts != null) &&",
    to: "(p) => p.pts != null &&",
    grep: "locked Rankings",
  },
  {
    id: "nan-in-columns",
    shipped: "E9.56b — the two NaN-class defects",
    // ⭐ DECLARED GREEN. This is a FINDING, not a gap, and pinning it here is what keeps it one.
    //
    // Both shipped NaN defects were COMPARATORS (`-Infinity - -Infinity`, `undefined - undefined`
    // when sorting a locked board). E9.56b's own commit message records why they were invisible:
    // "Array.sort treats a NaN comparator as 0, so it *happens* to leave the server's order
    // intact". Nothing wrong ever reaches the DOM, so no rendered-text scan can see them — they
    // are a unit-level concern and E9.56b already guards them there.
    //
    // The render-level form of the class is a missing null-guard in the shared `num()` formatter,
    // which is what is broken below. MEASURED with that guard removed, across all four
    // page × payload combinations (projections locked / rankings locked / projections entitled /
    // track record): ZERO rendered NaN. On a locked board `numOrLock` short-circuits to a lock
    // chip before `num` is ever reached with a null, and every real payload's numeric fields are
    // non-null (checked: all seven track-record seasons carry no nulls in the three columns they
    // format).
    //
    // ⇒ `expectNoNaN` is a live tripwire for a FUTURE render-level NaN and costs nothing, but it
    // has no reachable trigger today and is NOT presented as proven. If this case ever flips to
    // RED, the class has become observable — update this note and the README rather than deleting
    // the case.
    expect: "GREEN",
    detail: "the shipped form is comparator-only; the render form has no reachable trigger today",
    file: "components/fantasy/shared.tsx",
    from: "  v == null ? \"—\" : v.toLocaleString(undefined, { minimumFractionDigits: nd, maximumFractionDigits: nd })",
    to: "  Number(v).toLocaleString(undefined, { minimumFractionDigits: nd, maximumFractionDigits: nd })",
    grep: "renders NaN|no NaN",
  },
  {
    id: "withheld-renders-as-absent",
    shipped: "E9.56c — a withheld value fell through to an em-dash",
    detail:
      "A locked cell rendering '—' says 'we have nothing for this player' instead of 'subscribe to see it'.",
    file: "components/fantasy/shared.tsx",
    from: "): React.ReactNode => (v == null && locked ? <LockChip /> : num(v, nd))",
    to: "): React.ReactNode => num(v, nd)",
    grep: "carries a lock chip",
  },
  {
    id: "dead-cta-route",
    shipped: "E9.56c — the primary CTA pointed at `/pricing`, a route that never existed",
    detail:
      "Killed the entire buy path. Invisible to tsc (a URL is a string) and to next build (it was a plain <a href>).",
    file: "components/fantasy/shared.tsx",
    from: 'export const SUBSCRIBE_HREF = "/subscribe"',
    to: 'export const SUBSCRIBE_HREF = "/pricing-does-not-exist"',
    grep: "route integrity|CTA",
  },
  {
    id: "server-supplied-cta-trusted-verbatim",
    shipped: "E9.56c — the API's `upgrade.ctaHref` was rendered verbatim",
    detail:
      "A server-controlled link target is a server-controlled outage; the API Lambda ships on its own cadence.",
    file: "components/fantasy/shared.tsx",
    from: "  return href && KNOWN_CTA_ROUTES.has(href) ? href : SUBSCRIBE_HREF",
    to: "  return href ?? SUBSCRIBE_HREF",
    grep: "not trusted verbatim",
  },
  {
    id: "no-signup-affordance",
    shipped: "E9.58 — the logged-out nav offered no way to create an account",
    detail:
      "The pre-E9.58 state, and the mobile-only variant of it (`hidden sm:flex`) that a desktop-only suite cannot see.",
    file: "components/nav.tsx",
    from: "<Link href={SIGNUP_HREF}>Sign Up</Link>",
    to: "<span>Sign Up</span>",
    grep: "signup affordance",
  },
  {
    id: "hardcoded-price",
    shipped: "E9.59 — the defect the whole story exists to make impossible",
    // ⚠️ NOT a previously-shipped defect, and the only case here that is not. It is the
    // failure mode the decision was made to prevent: a price rendered from a constant is
    // indistinguishable from a correct one until the operator edits Stripe and the site
    // keeps charging one number while showing another. Every other instrument in the repo
    // is blind to it — `tsc` sees a valid string, `next build` renders nothing, and a spec
    // that merely asserts "a price is visible" passes. The transform test is the only thing
    // that can tell "shows A price" from "shows THE price", so it gets proved like one.
    detail:
      "Renders a constant instead of the server's `unit_amount`; passes any 'a price is shown' assertion.",
    file: "app/subscribe/page.tsx",
    from: "{fmtAmount(publicPricing.data.unit_amount, publicPricing.data.currency)}",
    to: '{"$10"}',
    grep: "FOLLOWS the server",
  },
  {
    id: "price-outage-breaks-the-funnel",
    shipped: "E9.59 — the deploy-skew window this story ships into",
    // The API-Gateway NONE route is an operator step landing AFTER the Lambda deploy, so a
    // logged-out pricing fetch 401s in between. Rendering the whole logged-out card only
    // when the price arrives is the natural way to write it and takes the sign-up path down
    // with the price — a display outage becoming a funnel outage.
    detail: "Gating the signup card on the price means a 401 from the pricing read hides the CTA.",
    file: "app/subscribe/page.tsx",
    from: "        {!loading && !signedIn && (",
    to: "        {!loading && !signedIn && publicPricing.data && (",
    grep: "absent, not fatal",
  },
  {
    id: "claim-leads-the-page",
    shipped: "NF-TR1 — pre-emptive: the page leading with the ADP comparison",
    // ⚠️ NOT a previously-shipped defect. It is the PRE-NF-TR1 state of the page, and the reason
    // the story is LAUNCH-GATING: leading with a +0.022 gap whose own 90% interval includes zero
    // (NF-D17) makes a result that might be nothing into the product's headline promise. Nothing
    // else can see it — `tsc` types a reordered JSX tree fine, the copy itself is unchanged and
    // still passes every denylist, and any "the claim is visible" assertion passes either way.
    // Only a geometric read of the rendered page can tell "shows the hook" from "leads with it".
    detail: "Removing the calibration block puts the benchmark comparison first, as it was before.",
    file: "components/fantasy/track-record-page.tsx",
    from: "      <CalibrationLead />\n",
    to: "",
    grep: "calibration leads",
  },
  {
    id: "unhedged-plain-lead",
    shipped: "NF-TR1 — pre-emptive: the punchier lead with the hedge removed",
    // The specific failure the operator's readability constraint creates. Rewriting an analyst
    // sentence for a casual reader is the right call AND is exactly the edit during which
    // "it could just be luck" gets dropped for sounding weak. The remaining copy is still
    // denylist-clean, so no word-list can catch it; only an assertion naming the hedge can.
    detail: "Drops the could-be-luck clause while the measured interval still includes zero.",
    file: "e2e/fixtures/api/fantasy-nfl-track-record-manifest.json",
    // ⚠️ ANCHORED THROUGH TO THE FOLLOWING KEY, and the first attempt without that was a false
    // GREEN worth recording: `headline` and `claim.lead` hold the IDENTICAL string (by design —
    // `headline` is the lead, so every surface quoting it inherits the plain wording), `headline`
    // comes first in the file, and `String.replace` with a string patches only the FIRST match. So
    // the break edited the field nothing renders and the page kept its hedge. Trailing `"precise"`
    // is what makes this anchor unique to the block the page actually reads.
    //
    // ⚠️ The anchor therefore has to span the CLOSING sentence too, which NF-TR1's own final
    // reframe appended after this hedge — that is what silently STALED this case (it reported
    // "anchor not found", i.e. an unproven clause, rather than failing loudly). Spanning it also
    // keeps the break ISOLATED: the close survives, so `test…no_generated_block_ends_on_a_caveat`
    // stays satisfied and only the hedge assertion can flip.
    from:
      " It is small enough that it could just be luck \\u2014 we are not promising it repeats." +
      " The season-by-season and position-by-position detail is below, along with the players we" +
      ' ranked furthest from where the crowd was drafting them.",\n    "precise"',
    to:
      " The season-by-season and position-by-position detail is below, along with the players we" +
      ' ranked furthest from where the crowd was drafting them.",\n    "precise"',
    grep: "keeps its hedges",
  },
  {
    id: "legacy-headline-promoted-to-lead",
    shipped: "NF-TR1 — pre-emptive: the deploy-skew fallback that looks defensive",
    // `frontend/` auto-deploys on merge; the artifact only grows its `claim` block at the
    // operator's post-merge `--publish`. A `claim?.lead ?? headline` fallback is the natural
    // defensive edit and would put the OLD un-hedged sentence back in the lead for the whole
    // window — with every test that uses the NEW fixture still green, because that fixture HAS a
    // claim block. Only the spec that strips it can see this.
    detail: "The pre-NF-TR1 `headline` renders as the lead instead of as fine print.",
    file: "components/fantasy/track-record-page.tsx",
    // ⚠️ THE BREAK MUST LIFT `ClaimLead` OUT OF THE `manifest.claim ?` BRANCH, and the first
    // attempt that only added the `?? headline` fallback in place was INERT — a false GREEN.
    // Inside the true branch `claim` is non-null by construction, so the fallback can never fire,
    // and on the no-claim render the component is not mounted at all. The defect only exists when
    // the lead is hoisted ABOVE the guard, which is exactly the shape this file shipped in its
    // first draft. A break that cannot change behaviour proves nothing about the test.
    from:
      "          {manifest.claim ? (\n            <>\n" +
      "              <ClaimLead lead={manifest.claim.lead} />",
    to:
      "          <ClaimLead lead={manifest.claim?.lead ?? manifest.headline} />\n" +
      "          {manifest.claim ? (\n            <>",
    grep: "still leads with calibration",
  },
  {
    id: "banner-recites-the-measurement",
    shipped: "NF-TR1 — the pre-reframe state: the locked board recited the track-record statistic",
    // ⚠️ THIS ONE ACTUALLY SHIPPED (E9.56c, "lead with the receipts"), which is why it is worth a
    // case rather than a comment. It is not dishonest — the sentence is generated from the
    // scorecard and passes every denylist — it is the WRONG INSTRUMENT for a conversion surface:
    // a +0.022 gap whose interval includes zero must arrive with four hedges and close on "it
    // could just be luck", and the caveats are unreadable without the table beside them.
    // Invisible to every other gate: it types, it builds, and it is denylist-clean.
    detail: "Puts the generated claim back in the upgrade banner, in place of the content hook.",
    file: "components/fantasy/shared.tsx",
    from: '        {DISAGREEMENT_HOOK}{" "}',
    to: '        {receipts?.claim?.precise}{" "}',
    grep: "does not recite the measurement",
  },
  {
    id: "trust-link-goes-nowhere",
    shipped: "NF-TR1 — pre-emptive: the E9.56c dead-CTA class, on the evidence link",
    // Dropping the quotation is only safe because the evidence stays one click away. A trust link
    // pointing at a route that does not render strands it — and a SOURCE scan cannot see this at
    // all, because the binding `href={TRACK_RECORD_TRUST_LINK.href}` is still right there in the
    // JSX. Only navigation can tell a bound link from a working one.
    detail: "Repoints the trust link at a route that is not the track record.",
    file: "lib/fantasy-claim-copy.ts",
    from: '  href: "/fantasy/track-record",',
    to: '  href: "/fantasy/track-record-does-not-exist",',
    grep: "trust link reaches",
  },
  {
    id: "lead-ends-on-its-own-disclaimer",
    shipped: "NF-TR1 — pre-emptive: the plain lead trailing off on a caveat",
    // AC 5. The hedges are non-negotiable and all four stay; what this case protects is the LAST
    // thing a reader is left holding. Broken at the artifact, because that is how it would really
    // happen — the copy is generated, so the observable defect arrives as a republished manifest.
    detail: "Removes the closing pointer so the lead stops on 'it could just be luck'.",
    file: "e2e/fixtures/api/fantasy-nfl-track-record-manifest.json",
    from:
      " The season-by-season and position-by-position detail is below, along with the players we" +
      ' ranked furthest from where the crowd was drafting them.",\n    "precise"',
    to: '",\n    "precise"',
    grep: "keeps its hedges",
  },
  {
    id: "disclosure-dropped",
    shipped: "NF-TR1 — pre-emptive: a required disclosure stops being published",
    // ⚠️ THIS CASE EXISTS BECAUSE OF A NEAR-MISS IN THE OPPOSITE DIRECTION. "all six required
    // disclosures render" first shipped with a bare `goto` and a whole-page text scan, so on a
    // slow runner it read the LOADING state and reported a missing disclosure that was merely
    // late. The fix was to wait for the claim to render (`gotoTrackRecord`) — and a wait added to
    // silence a red test is exactly how a test stops being able to fail. So: prove it still goes
    // red when a disclosure is genuinely ABSENT rather than slow.
    detail: "Removes the running-back wash — the disclosure that costs us something.",
    file: "e2e/fixtures/api/fantasy-nfl-track-record-manifest.json",
    from:
      '      "At running back it is a wash. Our order there was no better than the draft-day' +
      ' consensus, and we do not claim it was.",\n',
    to: "",
    grep: "all six required disclosures",
  },
  {
    id: "expected-points-label-reverted",
    shipped: "the defect this story fixed — a projected-points column headed as a bare projection",
    // The original state of the public track record: an availability-weighted EXPECTED total
    // sitting unlabelled beside a real finished season, so the only reading available to a visitor
    // was "the model is broken".
    detail: "Puts the retired 'Our pts' heading back on the season table.",
    file: "components/fantasy/track-record-page.tsx",
    from: "                <InfoTip label={EXPECTED_POINTS_LABEL}>{GLOSSARY.expectedPoints}</InfoTip>",
    to: "                Our pts",
    grep: "headed as expected points",
  },
  {
    id: "projected-games-invented",
    shipped: "pre-emptive: a fabricated games figure on a payload that carries none",
    // ⚠️ THE FAILURE MODE WITH THE WORST SHAPE, and the reason the deploy-skew test exists. The
    // frontend deploys on merge; `projGames` only lands at the operator's post-merge `--publish`.
    // A `?? 17`-style fallback would fill the gap with a confident, wrong number — making the
    // points discount look accounted for on precisely the rows where we have nothing to account
    // for it with, and reading as data rather than as a defect.
    detail: "Falls back to a full season when the payload carries no projGames.",
    file: "components/fantasy/track-record-page.tsx",
    from: "{num(r.projGames)}",
    to: "{num(r.projGames ?? 17)}",
    grep: "no invented games figure",
  },
  {
    id: "availability-overclaim",
    shipped: "pre-emptive: the label absorbing a residual miscalibration",
    // ⭐⭐ THE ONE THAT WOULD MAKE THIS STORY HARMFUL RATHER THAN MERELY INCOMPLETE. Availability
    // carries most of the measured level shift and NOT all of it; the remainder is a real
    // miscalibration with its own model story. Dropping the hedge turns an honest disclosure into
    // a cover — a visible anomaly made invisible — which is strictly worse than the unlabelled
    // number this story started from.
    detail: "Deletes the 'not the only reason' sentence from the page's framing copy.",
    file: "lib/fantasy-claim-copy.ts",
    from:
      " It is not the only reason a projection lands under a finished season, and we do not" +
      " present it as one.",
    to: "",
    grep: "WITHOUT claiming it explains everything",
  },
  {
    id: "definition-hover-only",
    shipped: "pre-emptive: the definition becoming unreachable on a phone",
    // Radix's Tooltip closes on pointerdown BY DESIGN, so a tap can never open one — a phone
    // reader would meet the identical unexplained number this story exists to explain. ⭐ Note
    // this case is only meaningful because the spec runs on the `mobile` (touch, hover-less)
    // project: on desktop Chromium the popover opens from hover before the click lands, and a
    // hover-only tooltip would pass.
    detail: "Downgrades the column definition to a hover-only title attribute.",
    file: "components/fantasy/track-record-page.tsx",
    from: "                <InfoTip label={EXPECTED_POINTS_LABEL}>{GLOSSARY.expectedPoints}</InfoTip>",
    to: "                <span title={GLOSSARY.expectedPoints}>{EXPECTED_POINTS_LABEL}</span>",
    grep: "opens on TAP",
  },
  {
    id: "google-entry-missing",
    shipped: "E9.58 — a signup entry point with no working Google button",
    detail: "The DNS-dead-host outage presented to the user as exactly this: no way through.",
    file: "app/subscribe/page.tsx",
    from: "  const googleEnabled = isHostedUiConfigured()",
    to: "  const googleEnabled = false",
    grep: "offers a working Google entry",
  },

  // ══ E9.46 — the home page as a positioning surface ═════════════════════════════════════════
  {
    id: "home-single-vertical",
    shipped: "E9.46 — the pre-story home page, which read as an MLB betting site",
    // ⚠️ THIS ONE ACTUALLY SHIPPED and was live until this story: "Daily edge, quantified" over an
    // MLB pick card, with nothing telling a visitor arriving for fantasy they were in the right
    // place. Invisible to every other gate — a single-product page types, builds and renders
    // perfectly. Only a rendered check that BOTH doors exist can see it.
    //
    // ⚠️ THE FIRST BREAK WAS INERT AND THE SUITE CORRECTLY STAYED GREEN — worth recording, because
    // it is the shape this whole harness exists to catch. Renaming the vertical's `key` changed
    // nothing a visitor could see: both cards still rendered. Rendering only the FIRST vertical is
    // a break that actually removes the door. It then exposed a REAL defect in the spec — the
    // fantasy door was located by link text, which the `DISAGREEMENT_HOOK` block further down the
    // page also matches, so it stood in for the deleted card. Both were fixed; a break that cannot
    // change behaviour proves nothing about the test.
    detail: "Renders only the first vertical, leaving a betting-only home page.",
    file: "app/page.tsx",
    from: "          {VERTICALS.map((v) => (",
    to: "          {VERTICALS.slice(0, 1).map((v) => (",
    grep: "both doors go somewhere",
  },
  {
    id: "home-pick-is-a-tout",
    shipped: "E9.46 — pre-emptive: the featured pick presented as a recommendation",
    // ⭐⭐ THE ONE THAT WOULD MAKE THIS PAGE HARMFUL RATHER THAN MERELY WEAK. `best_alpha = 0`:
    // six recorded no-edge results. A featured pick without its framing is the company claiming,
    // on its own front door, the exact advantage it has repeatedly measured and failed to find.
    // The remaining copy stays denylist-clean, so no word list can catch this — only an assertion
    // naming the disclaimer can.
    // ⚠️ THIS ANCHOR WENT STALE ONCE ALREADY (found 2026-08-08, unrelated story). E9.46's
    // alternate-the-market fix reworded the sentence after the frame — "Each day…" became "We look
    // at the games where…" — and the anchor kept naming the old wording, so the harness reported
    // ANCHOR-MISSING and this case proved nothing until someone read the summary. ⭐ Anchor a
    // red-proof case on the SHORTEST text that carries the thing being removed (here the frame
    // itself), never on the sentence that happens to follow it: the surrounding copy is the part
    // most likely to be rewritten, and it takes the guard with it.
    detail: "Removes the demonstration-not-recommendation frame from the live block.",
    file: "lib/home-copy.ts",
    from: '"A demonstration, not a recommendation. ',
    to: '"',
    grep: "framed as a demonstration",
  },
  {
    id: "home-blank-on-empty-read",
    shipped: "E9.26b — a swallowed empty read rendering as nothing at all",
    // The silent-`[]` class, on the marketing page. `lakehouse_query` catching and returning an
    // empty result left a whole panel blank for days with every status code green. Here the same
    // shape is a live block that simply vanishes when the model published nothing — which is
    // indistinguishable from a broken page, and is the AC this story states explicitly.
    detail: "Renders nothing instead of the honest empty state when the slate is empty.",
    file: "components/home/pick-of-the-day.tsx",
    from: "  if (data.game_pk == null) {\n    return (\n      <Shell>",
    to: "  if (data.game_pk == null) {\n    return null\n    return (\n      <Shell>",
    grep: "nothing published says so",
  },
  {
    id: "home-failed-read-reads-as-empty-slate",
    shipped: "E9.46 — pre-emptive: a page failure reported as a model result",
    // Two different facts. "The model published nothing today" is routine and honest; "this page
    // could not reach the model" is our failure and says nothing about the slate. Collapsing them
    // states a falsehood about the model on the one surface where its honesty is the product.
    detail: "Shows the empty-slate message when the read itself failed.",
    file: "components/home/pick-of-the-day.tsx",
    from: '<p className="text-sm leading-relaxed text-gray-400">{COPY.unavailable}</p>',
    to: '<p className="text-sm leading-relaxed text-gray-400">{COPY.empty}</p>',
    grep: "reported as ours",
  },
  {
    id: "home-gap-relabelled-as-edge",
    shipped: "E9.46 — the served field's own name leaking onto a marketing page",
    // ⚠️ THE MOST LIKELY REGRESSION IN THIS WHOLE STORY, because it looks like a consistency fix:
    // the API field IS called `edge` and every signed-in surface renders it that way, so aligning
    // the home page with them reads as tidying up. On a marketing page it is a claim to an
    // advantage we do not have.
    detail: "Renames the model-vs-market difference back to 'Edge'.",
    file: "lib/home-copy.ts",
    from: '    gap: "Gap",',
    to: '    gap: "Edge",',
    grep: "as a bet to place",
  },

  // ══ E9.46 revision (2026-08-08) — fantasy-first, and the three factual corrections ══════════
  {
    id: "home-fantasy-proof-missing",
    shipped: "E9.46 revision — pre-emptive: the fantasy product with no concrete demonstration",
    // Fantasy is the acquisition priority, and before this revision it had a text-only treatment
    // while MLB got the one real card. A page that DESCRIBES personalisation instead of showing it
    // is the defect; nothing in tsc or next build can see the difference.
    detail: "Removes the fantasy player card, leaving the fantasy pitch as prose only.",
    file: "app/page.tsx",
    from: "        <FeaturedFantasyPlayer />\n",
    to: "",
    grep: "renders a real player",
  },
  {
    id: "home-mlb-proof-first",
    shipped: "E9.46 revision — pre-emptive: the MLB card back above the fantasy card",
    // The ordering is a product decision (fantasy is the acquisition priority), and it is invisible
    // to every gate except a geometric read of the rendered page.
    detail: "Swaps the two product proofs so MLB leads again.",
    file: "app/page.tsx",
    from: "        <FeaturedFantasyPlayer />\n        {/* The MLB proof renders",
    to: "        {/* The MLB proof renders",
    grep: "FANTASY proof comes before",
  },
  {
    id: "home-conviction-label-restored",
    shipped: "E9.46 revision — the hardcoded 'HIGH CONVICTION' badge, which was live until this release",
    // ⚠️ THIS ONE ACTUALLY SHIPPED. `conviction_label` is a HARDCODED CONSTANT stamped on every
    // featured pick, so the badge classified nothing — and a bettor reads "high conviction" as
    // confidence that the team wins, which is the exact claim best_alpha=0 forbids. It is
    // denylist-clean, it types, it builds, and only an assertion naming it can catch it.
    detail: "Renders the served conviction_label instead of the measured model-agreement label.",
    file: "components/home/pick-of-the-day.tsx",
    from: "                  {COPY.agreementBadge}",
    to: "                  {data.conviction_label}",
    grep: "never says HIGH CONVICTION",
  },
  {
    id: "home-fantasy-lean-caveat-dropped",
    shipped: "E9.46 revision — pre-emptive: the rank gap presented as an independent read",
    // Measured on the live artifact: ZERO of the 111 eligible players have mktLean 'independent',
    // so our ranking always blends market consensus at the positions we can feature. Showing the
    // gap without the caveat overstates what it means — and the copy stays denylist-clean either
    // way, so only an assertion naming the caveat can see it.
    detail: "Stops rendering the market-lean caveat beside the rank gap.",
    file: "components/home/featured-fantasy-player.tsx",
    from: "                {data.leanNote}",
    to: "                {null}",
    grep: "market-lean caveat",
  },
  {
    id: "home-blog-back-in-primary-nav",
    shipped: "E9.46 — the pre-story nav, where the blog sat beside the products",
    // 🔧 E9.64 — RE-ANCHORED, and the reason is the more interesting half of the repair.
    //
    // This used to rewrite the hardcoded About `<Link>` in `nav.tsx` to point at /blog. It went
    // STALE on the indentation when E9.60 wrapped that link in `{showSubNav && (` — but re-pointing
    // the whitespace would have produced a case that ran and proved NOTHING, which is strictly
    // worse: `showSubNav` is `authenticated || isSignedIn`, and the spec this names drives an
    // ANONYMOUS visitor, so that link does not render for them however its href is written.
    //
    // ⭐ The list that actually renders the primary nav for a stranger is `SIGNED_OUT_NAV`, so that
    // is where a blog link would have to come back. Same lesson as E9.64's item-5 fix one file over:
    // an assertion about what an anonymous visitor is offered has to be anchored on the AUTHORED
    // LIST they are served, not on markup that is gated away from them.
    detail: "Restores the blog as a primary-nav link (operator decision 3 reverses this).",
    file: "lib/positioning-copy.ts",
    from: '  { label: "About", href: "/about", product: null, desktop: true },',
    to:
      '  { label: "Blog", href: "/blog", product: null, desktop: true },\n' +
      '  { label: "About", href: "/about", product: null, desktop: true },',
    grep: "out of the primary nav",
  },
  {
    id: "home-coming-soon-is-a-link",
    shipped: "E9.56c — the dead `/pricing` CTA, wearing a friendlier label",
    // A "coming soon" anchor into a route that does not exist is the same defect that killed the
    // buy path, and `route-integrity.spec.ts` only catches it once the target 404s — a link to a
    // real-but-unfinished surface teased as live would sail past it.
    detail: "Wraps an un-shipped roadmap row's date in a link.",
    file: "app/page.tsx",
    from: "              <span\n                className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-medium ${",
    to: "              <Link href=\"/about\">soon</Link>\n              <span\n                className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-medium ${",
    grep: "teasers, not links",
  },

  // ══ THE FREEMIUM BUILD — the free board, the boundary, the full-season rate ════════════════
  {
    id: "free-board-re-gated",
    shipped: "the pre-freemium state: a logged-out visitor bounced off the rankings",
    // ⭐ THE FUNNEL-KILLING FAILURE, and the one no Python assertion in the repo can see. The API
    // is perfectly happy — it serves the full board to anyone — so every server-side test stays
    // green; the visitor simply never arrives. A redirect leaves no error, no log and nothing in
    // the payload. Only a browser that follows the navigation can tell "the board is free" from
    // "the board is free and unreachable".
    //
    // ⚠️ BROKEN AT THE IMPORT, NOT AT THE JSX TAG. The harness applies ONE first-occurrence
    // replacement, so swapping `<FantasyPublicGuard>` leaves `</FantasyPublicGuard>` behind and the
    // build fails on unbalanced JSX — which reports as BUILD-CAUGHT and proves nothing about the
    // spec. Aliasing the import produces the real defect (the page is gated) in one contiguous edit.
    detail: "Puts the paid guard back on Rankings, so a stranger is redirected before it renders.",
    file: "app/fantasy/rankings/page.tsx",
    from: 'import { FantasyPublicGuard } from "@/components/auth-guard"',
    to: 'import { FantasyGuard as FantasyPublicGuard } from "@/components/auth-guard"',
    grep: "renders the full board for a logged-out visitor",
  },
  {
    id: "paid-half-un-gated",
    shipped: "pre-emptive: the whole product becoming free",
    // ⚠️ THE CASE THAT PROVES THE SUITE IS NOT SELF-SATISFYING. Every other freemium assertion is
    // "the free thing is visible" — a change that un-gated EVERYTHING would pass all of them and
    // the suite would be green with the business given away. This is the only case whose failure
    // means the opposite of the others'.
    detail: "Makes the Draft Optimizer public, so a logged-out visitor reaches the paid half.",
    file: "app/fantasy/draft/page.tsx",
    from: 'import { FantasyGuard } from "@/components/auth-guard"',
    to: 'import { FantasyPublicGuard as FantasyGuard } from "@/components/auth-guard"',
    grep: "still bounces a logged-out visitor",
  },
  {
    id: "player-page-content-re-split",
    shipped: "NF3.2's state: a public player ROUTE whose CONTENT was still split by entitlement",
    // ⚠️ THE FAILURE MODE THAT LOOKS LEAST LIKE ONE. The route stays public, the page renders, the
    // header and bio are right, nothing errors and no test that asserts "the player page loads"
    // notices — a visitor simply never sees the projection they came for. `route-integrity` passes,
    // `tsc` passes, and the API is serving the full payload the whole time.
    detail: "Sends every visitor back to the track-record-only view, as NF3.2 did.",
    file: "components/fantasy/player-page.tsx",
    from: "  return <PlayerView playerId={playerId} />",
    to: "  return <TrackRecordOnlyView playerId={playerId} />",
    grep: "player page renders the real projection",
  },
  {
    id: "boundary-not-stated",
    shipped: "pre-emptive: a complete free board with nothing to buy",
    // Not a rendering fault — the page looks perfect. It is a POSITIONING fault: a complete-looking
    // free board with no boundary stated reads as the whole product, so the paid aha ("what changed
    // because it is MY league") never gets posed and nobody converts. Invisible to every gate that
    // asks whether the page works, because it does.
    detail: "Removes the free/paid boundary block from below the rankings board.",
    file: "components/fantasy/rankings-board.tsx",
    from: "          <FreemiumBoundary entitled={entitled} />",
    to: "",
    grep: "states what a membership adds",
  },
  {
    id: "full-season-rate-divides-by-zero",
    shipped: "pre-emptive: `Infinity` rendered as a projection",
    // ⭐ THE DEFECT THE FIXTURE'S THREE DEGENERATE ROWS EXIST TO CATCH. `pts * 17 / 0` is
    // `Infinity`, which is a `number` in JS — so it survives every `!= null` guard a caller might
    // write and prints "∞" in a points column. `tsc` cannot see it (the arithmetic is valid), and
    // a fixture where every row has a healthy games figure cannot see it either — which is exactly
    // the fixture anyone would write by hand.
    detail: "Drops the zero-games guard, so a player projected to miss the season renders ∞.",
    file: "lib/fantasy.ts",
    from: "  if (games <= 0) return null",
    to: "  if (games < 0) return null",
    grep: "renders an em-dash",
  },
  {
    id: "boundary-recites-the-measurement",
    shipped: "NF-TR1's rule, on the surface that replaced the one it was written for",
    // The banner NF-TR1 wrote this rule against renders only on a LOCKED payload, which no live
    // caller now receives. So the rule's original guard would go on passing forever while the
    // surface a visitor ACTUALLY meets quietly grew a quotation of the statistic. This is that
    // rule re-proved on the live surface.
    detail: "Puts the generated claim into the freemium boundary in place of the trust link.",
    file: "components/fantasy/shared.tsx",
    from: "        {FREE_TIER_SUMMARY.detail}",
    to: "        {\"Our 2025 rankings modestly outperformed ADP (+0.022 rank correlation).\"}",
    grep: "does not quote its number",
  },

  // ══ ONE PRESET IS FREE (2026-08-08) ════════════════════════════════════════════════════════
  {
    id: "unentitled-defaulted-onto-a-paid-preset",
    shipped: "pre-emptive: a first visit that opens on a board the API refuses",
    // ⭐ A FIRST IMPRESSION, and nothing server-side can see it. The API behaves perfectly — it
    // refuses a paid preset, which is its job — and every Python assertion stays green. What breaks
    // is that the CLIENT asked for the wrong one, so the visitor's opening screen is a refusal they
    // did nothing to earn. `tsc` cannot see it (both branches type-check) and it is invisible to
    // anyone testing while logged in as a subscriber, i.e. to us.
    detail: "Restores the entitled default (half-PPR) for everyone, including the logged out.",
    file: "lib/fantasy-queries.ts",
    from: "    if (!entitled && free) {",
    to: "    if (false && free) {",
    grep: "lands on the free preset",
  },
  {
    id: "paid-presets-left-selectable",
    shipped: "pre-emptive: a picker that offers boards the API will not serve",
    // The dropdown is the one place the boundary has to be legible BEFORE a click. Leaving the paid
    // options enabled turns every one of them into a dead end discovered only after selecting it —
    // and a dead end is indistinguishable from a bug to the person who hit it.
    detail: "Stops disabling the paid options in the format picker.",
    file: "components/fantasy/shared.tsx",
    from: "                  disabled: locked,\n                }\n              }),",
    to: "                  disabled: false,\n                }\n              }),",
    grep: "not selectable",
  },
  {
    id: "paid-presets-hidden-instead-of-locked",
    shipped: "pre-emptive: the tempting fix that removes the upsell along with the problem",
    // ⚠️ THIS SATISFIES THE CASE ABOVE COMPLETELY — a removed option cannot be selected. It also
    // makes the free board look like the only board we publish, which is untrue and is the reverse
    // of what an upgrade prompt is for. The two cases have to coexist or one of them can be
    // "fixed" into the other.
    detail: "Filters the paid presets out of the picker rather than disabling them.",
    file: "components/fantasy/shared.tsx",
    from: "              options: manifest.configs.map((c) => {",
    to: "              options: manifest.configs.filter((c) => isFreeConfig(c)).map((c) => {",
    grep: "not selectable",
  },
  {
    id: "paid-league-size-left-selectable",
    shipped: "pre-emptive: locking the FORMAT and forgetting the SIZE",
    // `full_ppr` at ten teams is a different board — league size sets the replacement level — and
    // the API refuses it. A format-only lock leaves the two controls able to compose a request that
    // cannot load, which is the same dead end as above reached by a different route.
    detail: "Stops locking the paid league size.",
    file: "components/fantasy/shared.tsx",
    from: "              const locked = lockFormats && n !== free!.size",
    to: "              const locked = false && n !== free!.size",
    grep: "league SIZE is locked",
  },
  {
    id: "refusal-reads-as-an-empty-search",
    shipped: "pre-emptive: a paywall described as a typo",
    // The 403 arrives as zero rows, and the pre-existing empty branch says "No players match — try
    // clearing the search box". Every gate that asks whether the page WORKS is satisfied: it
    // renders, nothing errors, the copy is grammatical. It is simply an answer to a question the
    // visitor did not ask, on the one visit where being wrong costs most.
    detail: "Removes the refused-board branch so a 403 falls through to the empty-search state.",
    file: "components/fantasy/rankings-board.tsx",
    from: "          {!boardLoading && boardError && (",
    to: "          {false && boardError && (",
    grep: "not as an empty search",
  },
  // ══ THE PAID SCORINGS ON THE OTHER TWO SURFACES ═══════════════════════════════════════════
  {
    id: "projections-offers-every-scoring",
    shipped: "the state PR #681 left behind on Season Projections",
    // #681 locked the BOARD's format picker and left this one open, because they are different
    // controls in different files that happen to mean the same thing. The page kept offering
    // half-PPR and standard to a logged-out visitor for the whole of that PR's life.
    detail: "Unlocks every reference scoring in the projections picker.",
    file: "components/fantasy/projections-table.tsx",
    from: "                  const lockedOption = !entitled && s !== FREE_SCORING",
    to: "                  const lockedOption = false",
    grep: "only the free reference scoring",
  },
  {
    id: "player-page-prints-the-paid-totals",
    shipped: "the same gap on the player page — the surface that shows all three side by side",
    detail: "Prints the standard total to a free visitor.",
    file: "components/fantasy/player-page.tsx",
    from: "value={entitled ? num(proj.fpStd) : <LockChip title={STAT_LINE_LOCK_TITLE} />}",
    to: "value={num(proj.fpStd)}",
    grep: "locks the two paid totals",
  },
  {
    id: "everything-locked-including-the-free-total",
    shipped: "pre-emptive: the nervous fix that locks the free number too",
    // ⚠️ THE OPPOSITE FAILURE. Every "the paid total is locked" assertion stays green while the
    // free board loses the one number it exists to show — and it would look, to whoever made the
    // change, exactly like being careful.
    detail: "Locks the free full-PPR total along with the paid ones.",
    file: "components/fantasy/player-page.tsx",
    from: "                value={num(proj.fpPpr)}",
    to: "                value={<LockChip />}",
    grep: "keeps the free one",
  },
  {
    id: "stat-line-printed-beside-locked-totals",
    shipped: "pre-emptive: a paywall the reader can do in their head",
    // \u2b50\u2b50 The reference totals differ ONLY in how a reception scores, so with the stat line back
    // the two locked figures are one subtraction away on the same screen —
    // `half = full - 0.5 x rec`. Every "the total is locked" case above stays green.
    detail: "Restores the raw stat line under the locked totals.",
    file: "components/fantasy/player-page.tsx",
    from: '              {entitled ? (\n                <div className="grid grid-cols-3',
    to: '              {true ? (\n                <div className="grid grid-cols-3',
    grep: "raw stat line is withheld",
  },
  {
    id: "preset-called-the-readers-league",
    shipped: "pre-emptive: telling a free visitor a preset is their own league",
    // Not a leak — a false statement about the reader, on the tile whose label is the exact phrase
    // the paid tier is sold on. Spending it over a preset costs the boundary its vocabulary.
    detail: "Labels the free board's tile as the visitor's own league.",
    file: "components/fantasy/player-page.tsx",
    from: '                    : config?.label ?? "Board scoring"',
    to: '                    : config ? `${config.label} (your league)` : "Your league"',
    grep: "own league",
  },
  {
    id: "stored-paid-selection-survives-a-lapse",
    shipped: "pre-emptive: a lapsed member greeted by a refusal on the page they were reading",
    // The format selection outlives the membership in localStorage. Re-checking it against the free
    // board is one line, and skipping it strands exactly the person most likely to come back.
    detail: "Honours the stored selection for an unentitled caller.",
    file: "lib/fantasy-queries.ts",
    from: "      setConfigName(names.includes(free.config) ? free.config : names[0] ?? null)",
    to: "      setConfigName(stored.configName ?? free.config)",
    grep: "does not strand a lapsed member",
  },

  // ══ G100-C1 — one free personalized league ═════════════════════════════════════════════════
  {
    id: "delta-sign-inverted",
    shipped: "pre-emptive: the rank delta subtracted the wrong way round",
    // ⭐ THE DEFECT THIS SURFACE IS MOST LIKELY TO SHIP. Rank is an INVERTED scale — smaller is
    // better — so `league - generic` is the spelling that reads naturally and is wrong. Every
    // riser then renders a down arrow and vice versa, on a page that is otherwise completely
    // normal: no error, no blank, no NaN, and the numbers are all real.
    //
    // 🔧 E9.64 — RE-POINTED AT A NEW ASSERTION, because the one it named had stopped being able to
    // see it and that is a finding rather than a chore. This case used to grep the movers test,
    // which was exact while the highlights were SELECTED on rank movement. E9.61 correctly
    // re-anchored that test onto VOR when the ranking moved — and in doing so left the OVERALL move
    // unread by anything, even though the board's "vs our generic board" COLUMN still renders it
    // (`GenericDeltaCell scale="overall"`). So the break went in, every arrow in that column
    // flipped, and the suite stayed green. `vor-delta-subtraction-inverted` covers the VOR side;
    // this now covers the rank side, against a test written for it.
    //
    // ⚠️ THE SHAPE TO REMEMBER: re-anchoring a test onto a new quantity can silently ORPHAN the old
    // one. When a spec's anchor moves, check what the previous anchor was the only reader of.
    detail: "Inverts `ovrDelta`, so every arrow in the board's move column points the wrong way.",
    file: "lib/league-delta.ts",
    from: "      ovrDelta: g ? g.ovrRank - p.ovrRank : null,",
    to: "      ovrDelta: g ? p.ovrRank - g.ovrRank : null,",
    grep: "agrees with the two boards' own ranks",
  },
  {
    id: "activation-fires-on-mount",
    shipped: "pre-emptive: counting a visitor who saw an empty state as ACTIVATED",
    // The activation event is the funnel's DENOMINATOR, so a false positive here is worse than a
    // miss: it inflates activation, which reads as a CONVERSION problem and sends the next story
    // at the wrong thing entirely. Firing on mount rather than on the board rendering is the
    // natural way to write it.
    detail: "Fires `custom_board_viewed` even with no league configured.",
    // 🔧 E9.64 — re-anchored: the guard grew a `loading` clause (the telemetry fix that stopped it
    // firing before the generic board landed, shipping a null `players_moved`). The break is
    // unchanged in intent — strip the guard down to the ref and it fires on mount.
    file: "components/fantasy/my-league.tsx",
    from: "    if (fired.current || loading || !league || ranked.length === 0) return",
    to: "    if (fired.current) return",
    grep: "does NOT fire on an empty state",
  },
  {
    id: "activation-fires-per-render",
    shipped: "pre-emptive: one activation counted many times",
    // Same denominator, the other way: without the once-per-mount ref the capture re-fires on
    // every re-render (a position-tab click, a query settling), so a single user inflates the
    // metric by however much they browsed.
    detail: "Drops the once-per-mount guard on the activation capture.",
    file: "components/fantasy/my-league.tsx",
    from: "    if (fired.current || loading || !league || ranked.length === 0) return\n    fired.current = true",
    to: "    if (loading || !league || ranked.length === 0) return",
    grep: "under the name the funnel reads",
    // ⭐ DECLARED GREEN, and it is a FINDING rather than a gap — defence in depth, measured.
    //
    // Once-per-mount is delivered TWICE over here, independently: by the `fired` ref, and by the
    // effect's dependency list (`[league, ranked.length, delta, loading]`), none of which changes
    // when the user browses — a position-tab click re-renders the component but re-runs no effect. So
    // removing the ref alone changes no observable behaviour, and no SINGLE-line break can falsify
    // the clause. The spec exercises the property anyway (it clicks a tab and re-counts), so a
    // future edit that makes those deps unstable is caught by the test even though this case
    // cannot express it.
    //
    // ⚠️ If this ever flips to RED, one of the two layers has gone and the note above is stale.
    expect: "GREEN",
  },
  {
    id: "activation-event-renamed",
    shipped: "pre-emptive: renaming an event G100-D0's dashboard reads",
    // The event NAME is a contract with the funnel dashboard, not an implementation detail. A
    // rename breaks measurement silently — the app keeps working perfectly and the chart goes flat.
    detail: "Renames the activation event.",
    file: "components/fantasy/my-league.tsx",
    from: 'posthog.capture("custom_board_viewed", {',
    to: 'posthog.capture("my_league_viewed", {',
    grep: "under the name the funnel reads",
  },
  {
    id: "free-league-nav-hidden",
    shipped: "pre-emptive: the free tier ships with no way to reach it",
    // The fantasy surface is LOCKED for a free account, so without `freeSignedIn` the whole menu
    // collapses to an upsell and the one league a free user is entitled to becomes unreachable.
    // The feature would exist, work, and be invisible.
    detail: "Drops the locked-surface exemption for the free league items.",
    file: "components/nav.tsx",
    from: "surfaceItems(g).filter((i) => i.public || (i.freeSignedIn && isSignedIn))",
    to: "surfaceItems(g).filter((i) => i.public)",
    grep: "can reach the league surfaces from the nav",
  },
  {
    id: "free-league-nav-shown-logged-out",
    shipped: "pre-emptive: a nav item whose only behaviour is a redirect",
    // The mirror image. A league is stored against a Cognito `sub`, so these pages bounce an
    // anonymous visitor to /login — offering them is a menu that lies about what it opens.
    detail: "Shows the signed-in-only league items to a logged-out visitor.",
    file: "components/nav.tsx",
    from: "surfaceItems(g).filter((i) => i.public || (i.freeSignedIn && isSignedIn))",
    to: "surfaceItems(g).filter((i) => i.public || i.freeSignedIn)",
    grep: "is not offered the league surfaces",
    // ⭐ DECLARED GREEN — a FINDING, and the same defence-in-depth shape as
    // `activation-fires-per-render`. A logged-out visitor never reaches this filter at all: the
    // whole surface sub-nav is behind `showSubNav` (`authenticated || isSignedIn`), so the fantasy
    // dropdown is not rendered and its items cannot appear however this line is written.
    //
    // The `isSignedIn` half is therefore belt-and-braces — and worth keeping, because the ONE path
    // that does render nav items to a logged-out visitor is `publicNavItems()` (E9.58 lifted the
    // public surfaces into the top bar for exactly that reason). A future change that widened that
    // path would meet this clause. The spec's assertion is a real user-facing property either way.
    //
    // ⚠️ If this flips to RED, the sub-nav has become reachable logged-out and the note is stale.
    expect: "GREEN",
  },
  {
    id: "withheld-leagues-vanish-silently",
    shipped: "pre-emptive: a lapsed member's leagues disappear with no account of why",
    // Two of their leagues stop being personalized. Rendering that as SILENCE — on a surface they
    // typed their own settings into — reads as data loss, which is a support ticket and a churn
    // event rather than an upgrade prompt.
    detail: "Suppresses the 'nothing has been deleted' notice.",
    file: "components/fantasy/my-league.tsx",
    from: "          {withheld > 0 && (",
    to: "          {false && (",
    grep: "told nothing was deleted",
  },
  {
    id: "delta-claims-the-market",
    shipped: "pre-emptive: a movement column read as a claim about the market",
    // ⛔ `best_alpha = 0`. The delta is between two of OUR boards and says nothing about ADP or
    // consensus — but "movement" means "versus the market" everywhere else in this category, so a
    // reader imports that meaning unless the page refuses it explicitly.
    detail: "Removes the sentence saying the comparison is between our own boards.",
    file: "lib/fantasy-claim-copy.ts",
    from: "  \"Movement is between two of our own boards",
    to: "  \"Movement shows where your league values a player differently",
    grep: "sees its own board and the delta that explains it",
  },
  {
    id: "free-board-guessed-locally",
    shipped: "pre-emptive: guessing the free preset client-side during the deploy-skew window",
    // NF-C0. `frontend/` ships on merge, the API only on a manual `deploy.sh`, so the manifest
    // spends a window without `freeBoard`. Defaulting to "full_ppr" locally states the paywall in
    // TWO places — and during that window it renders a confident comparison against a board the
    // server never said was free.
    detail: "Falls back to a hardcoded free preset instead of withholding the comparison.",
    file: "components/fantasy/my-league.tsx",
    from: "  const free = freeSelection(manifest)",
    to: '  const free = freeSelection(manifest) ?? { config: "full_ppr", size: 12 }',
    grep: "manifest has not named a free board yet",
  },
  {
    id: "configured-league-reads-as-no-league",
    shipped: "pre-emptive: telling a user with a saved league to go and set one up",
    // The page cannot show a scored board until the board read lands, so "my league is here but
    // unscored" is a state of its own. Keying the empty state on it is the natural way to write it,
    // and it fires whenever that read is slow, 404s before the first export, or fails.
    //
    // 🔧 E9.64 — THE BREAK WAS REPLACED BECAUSE IT HAD GONE INERT, and this is the durable half.
    // It used to swap `!hasSavedLeague` for `!league`, which was a real defect while scoring
    // happened in the BROWSER: `useMyTeams` could not build a board without the projections blob,
    // so `teams` — and therefore `league` — stayed null exactly when the read failed. NF-EPIC 1
    // moved scoring server-side, `league` now comes off `/fantasy/nfl/my-teams` (which this spec
    // does not fail), and the substitution stopped changing anything at all: the case ran, the
    // suite stayed green, and it read as a decorative assertion when the assertion was fine.
    //
    // ⚠️ The lesson is that a red-proof case is only as durable as the DATA-FLOW it assumes. When a
    // read moves, re-check every case whose break depends on that read failing. The break now names
    // the scored board directly, which is what "keyed on the scored board" means today.
    detail: "Keys the empty state on the scored board rather than on the saved-league payload.",
    file: "components/fantasy/my-league.tsx",
    from: "      {!teamsLoading && !hasSavedLeague && (",
    to: "      {!teamsLoading && !leagueBoard && (",
    grep: "never described as 'no league' when scoring fails",
  },

  // ── G100-C1 FOLLOW-UP (operator, 2026-08-08) ────────────────────────────────────────────────
  // Three defects the first REAL league surfaced in under a minute, none of which the original
  // suite could see. The pattern is worth naming: every one of them is about whether the screen is
  // USABLE, and the original spec only ever asked whether it was CORRECT.
  {
    id: "pool-ignored-highlights-the-waiver-wire",
    shipped:
      "G100-C1 — every riser and faller was a player nobody would draft, on the first real league",
    // Rank density grows down the board: a few points separates adjacent players at pick 30 and
    // dozens of them at rank 400. So the largest RANK moves live in the deep tail BY CONSTRUCTION,
    // and a highlight list sorted by rank movement is a list of waiver-wire churn. Passing a null
    // pool restores exactly that (the parameter's own "unknown must not filter" fallback), which
    // makes this the honest re-introduction rather than a synthetic break.
    detail: "Drops the draft pool, so highlights are drawn from the whole board again.",
    file: "components/fantasy/my-league.tsx",
    from: "    () => computeLeagueDelta(genericBoard, leagueBoard, pool, LOW_PREDICTABILITY_POSITIONS),",
    to: "    () => computeLeagueDelta(genericBoard, leagueBoard, null, LOW_PREDICTABILITY_POSITIONS),",
    grep: "shrinking the pool shrinks the highlights",
  },
  {
    id: "kickers-and-defenses-lead-the-movers",
    shipped:
      "G100-C1 — four D/STs in the top five movers on the first real league (CLE, KC, NE, GB)",
    // The pool filter did NOT fix this and could not: K and D/ST sit comfortably inside any real
    // draft pool. ~32 of each project within a narrow band, so any difference in a league's K/DST
    // scoring reorders the whole position at once, and the band sits deep enough in the overall list
    // that a one-tier shuffle is worth dozens of places. Every one of them is noise.
    detail: "Drops the low-predictability exclusion, so K/DST compete for the headlines again.",
    file: "components/fantasy/my-league.tsx",
    from: "    () => computeLeagueDelta(genericBoard, leagueBoard, pool, LOW_PREDICTABILITY_POSITIONS),",
    to: "    () => computeLeagueDelta(genericBoard, leagueBoard, pool, []),",
    grep: "no kicker or defense can lead the list",
  },
  {
    id: "ir-slots-counted-as-draft-picks",
    shipped: "pre-emptive: an IR spot is not a draft pick",
    // ⚠️ THE ISOLATING CASE. The default fixture has NO reserve slots, so this defect is invisible
    // to every other test in the suite — which is precisely how it would have shipped. A 3-IR
    // league would draft 160 players and be told its pool is 190.
    detail: "Counts IR/taxi spots toward the pool, inflating it by the whole reserve bench.",
    file: "lib/league-delta.ts",
    from: 'const NON_DRAFT_SLOTS = new Set(["IR", "TAXI"])',
    to: "const NON_DRAFT_SLOTS = new Set([])",
    grep: "IR and taxi spots are not draft picks",
  },
  {
    id: "page-numbering-restarts-each-page",
    shipped: "pre-emptive: the row number silently stops meaning rank",
    // `i + 1` over a paged slice renders "1" at the top of every page. Nothing looks broken — the
    // rows are right, the order is right, and only the leftmost column is quietly lying about what
    // it measures.
    detail: "Numbers rows by their position on screen rather than their position in the board.",
    file: "components/fantasy/my-league.tsx",
    from: "                      {(pageSize === ALL_ROWS ? 0 : safePage * pageSize) + i + 1}",
    to: "                      {i + 1}",
    grep: "numbering continues across pages",
  },
  {
    id: "late-page-survives-a-filter-change",
    shipped: "pre-emptive: an empty table that reads as 'you have no TEs'",
    // ⭐ DECLARED GREEN, and MEASURED both ways round rather than reasoned about — which is the only
    // reason it is here. Two independent mechanisms deliver "a filter change never empties the
    // table": the tab handler resets the page to 0, and the render clamps `page` to the new last
    // page. Breaking EITHER alone leaves the other holding, so no single-line defect is observable
    // and the case is a statement about defence in depth, not about the assertion being decorative.
    //
    // ⚠️ THIS IS THE `and`-COMPOSED-CLAUSE TRAP FACING THE OTHER WAY (NF-D17): there, a guard stayed
    // green because a DIFFERENT clause already refused the fixture. Here the redundancy is
    // deliberate and wanted — but it has the same consequence for provability, so it gets said out
    // loud instead of being left as a case that quietly always passes. The break below removes the
    // PRIMARY mechanism (the reset); the clamp catches it and the table stays populated.
    //
    // If this ever flips to RED, the two mechanisms are no longer independent and this note is
    // stale — fix the note, do not delete the case.
    expect: "GREEN",
    detail: "Removes the page reset on a position change; the render-time clamp still holds.",
    file: "components/fantasy/my-league.tsx",
    from: "                setPos(v)\n                setPage(0)",
    to: "                setPos(v)",
    grep: "never shows an empty table",
  },
  {
    id: "importer-ignores-the-quota",
    shipped: "G100-C1 — a free account at its quota could still import a SECOND league",
    // ⭐ THE ONE THE OPERATOR HIT. The manual editor refused it and the importer did not, so the
    // limit was met as a 409 after choosing a platform, typing a username and waiting on a preview.
    // The tier is enforced by WHICH COMPONENT RENDERS — #681's lesson, on the two create paths.
    detail: "Restores the ungated league list: every league is importable regardless of quota.",
    file: "components/fantasy/league-import.tsx",
    from: "                const locked = atQuota && !saved",
    to: "                const locked = false",
    grep: "a SECOND league cannot be chosen",
  },
  {
    id: "the-quota-locks-the-league-you-already-have",
    shipped: "pre-emptive: the fix, applied one clause too widely",
    // ⚠️ THE OTHER SIDE OF THE SAME CLAUSE, and the reason the fixture carries both a saved and an
    // unsaved league. Re-importing the league you already have is an UPDATE — it creates nothing,
    // the server's cap does not apply, and it is how a returning user refreshes a roster mid-season.
    // "Lock everything once at quota" passes the case above and breaks that.
    detail: "Locks every league at quota, including the one already saved (an update, not a create).",
    file: "components/fantasy/league-import.tsx",
    from: "                const locked = atQuota && !saved",
    to: "                const locked = atQuota",
    grep: "a SECOND league cannot be chosen",
  },
  {
    id: "refusal-leads-to-a-dead-route",
    shipped: "E9.56c — every locked CTA pointed at `/pricing`, a route that does not exist",
    // The real defect, re-introduced on the new surface. A dead CTA is invisible to `next build`
    // (these are `<Link href>` to a literal, resolved at runtime) and to any test that does not
    // assert the target — so the entire conversion path off a refusal 404s and looks perfect.
    detail: "Points the upgrade CTA at the route E9.56c shipped and had to fix.",
    file: "components/fantasy/shared.tsx",
    from: "          href={SUBSCRIBE_HREF}\n          className=\"inline-flex items-center gap-1.5 rounded border border-[#10b981]/40",
    to: "          href=\"/pricing\"\n          className=\"inline-flex items-center gap-1.5 rounded border border-[#10b981]/40",
    grep: "carries a way to lift it",
  },
  {
    id: "landing-view-loses-its-surface",
    shipped: "G100-D0 — the first cut, caught on the wire before merge",
    // ⭐ A DEFECT THIS SUITE ACTUALLY FOUND, and the reason `funnel-telemetry.ts` carries no
    // `"use client"`. A constant imported from a client-boundary module into a SERVER component
    // resolves to a client REFERENCE, not to its value — so `<LandingView surface={…HOME}/>` on the
    // (server-rendered) home page received `undefined` and every `landing_view` from the
    // highest-traffic page in the product shipped with no `surface`.
    //
    // Nothing else in the toolchain can see it: the types are real so `tsc` passes, `next build`
    // passes, the component renders, and the event still fires. Only reading the property off the
    // ingest request body distinguishes "the event fired" from "the event fired with its
    // dimensions", which is the whole difference between a funnel you can segment and one you
    // cannot.
    detail: "Re-marks the contract module as a client boundary; the server component's prop becomes undefined.",
    file: "lib/funnel-telemetry.ts",
    from: "/**\n * G100-D0 — THE FUNNEL EVENT CONTRACT.",
    to: '"use client"\n\n/**\n * G100-D0 — THE FUNNEL EVENT CONTRACT.',
    grep: "landing_view under the name the dashboard reads",
  },
  {
    id: "landing-view-races-the-session",
    shipped: "G100-D0 — the second cut, also caught on the wire before merge",
    // The other half of the same discovery. `landing_view` is the ONLY funnel event that can fire
    // before the auth provider has restored a session, and `free_paid_status` cannot be registered
    // until that resolves. Firing on bare mount raced it, and the top of the funnel — the one step
    // with the most traffic — became the one step that could not be split by tier.
    //
    // It is the quietest possible failure: the event arrives, the funnel counts the visitor, the
    // rate is correct, and a single breakdown dimension is silently absent. Same shape as G100-C1's
    // `players_moved: null` race, one step up the funnel.
    detail: "Drops the wait for the session, so the event outruns the property that describes the caller.",
    file: "components/analytics/landing-view.tsx",
    from: "    if (fired.current || loading) return",
    to: "    if (fired.current) return",
    grep: "reports `comped`, never `paid`",
  },

  // ══ E9.61 — the "vs our generic board" delta on the browse boards ═════════════════════════════
  {
    id: "personalization-leaks-onto-the-public-board",
    shipped: "pre-emptive: the gate this story is most likely to lose",
    // ⭐ THE ONE THAT MATTERS. `/fantasy/rankings` is PUBLIC, and this column renders
    // PERSONALIZATION. The gate is not a check anyone wrote — it is that `isCustom` is unreachable
    // without a token — so the way it breaks is not "someone deletes the guard" but "someone
    // computes the delta unconditionally and hides it in the render", which is what the freemium
    // build already shipped once in a different costume (#681 gated one of three renderers).
    detail: "Computes the delta for every caller, so the band renders on the anonymous free board.",
    file: "components/fantasy/rankings-board.tsx",
    from: "      isCustom\n        ? computeLeagueDelta(genericBoard, board, pool, LOW_PREDICTABILITY_POSITIONS)\n        : null,",
    to: "      computeLeagueDelta(genericBoard ?? board, board, pool, LOW_PREDICTABILITY_POSITIONS),",
    grep: "an ANONYMOUS visitor",
  },
  {
    id: "delta-column-ignores-the-rank-scale",
    shipped: "pre-emptive: the two-scales trap `adpPositionRanks` already exists for",
    // A position tab ranks 1..n WITHIN the position; an OVERALL move printed beside it compares two
    // different scales. Arithmetically wrong, and it looks entirely normal — which is why the spec
    // compares two RENDERINGS of the same player rather than reading a value back.
    detail: "Pins the column to the overall scale on every tab.",
    file: "components/fantasy/rankings-board.tsx",
    from: 'const deltaScale = pos === "Overall" ? ("overall" as const) : ("position" as const)',
    to: 'const deltaScale = "overall" as const',
    grep: "changes with the tab",
  },
  {
    id: "delta-column-loses-its-label",
    shipped: "pre-emptive: an unlabelled delta inherits the market reading",
    // Every other delta column in this product means "versus ADP". A bare one on a fantasy board is
    // read as a claim about where the room is drafting — i.e. as an edge claim, on a surface whose
    // whole honesty argument is that it makes none. `best_alpha = 0`.
    detail: "Replaces the explicit label with the ambiguous one the category defaults to.",
    file: "lib/fantasy-claim-copy.ts",
    from: 'export const GENERIC_DELTA_LABEL = "vs our generic board"',
    to: 'export const GENERIC_DELTA_LABEL = "Move"',
    grep: "under the label that says what they compare",
  },
  {
    id: "custom-selection-lost-to-the-load-race",
    shipped: "E9.61 — MEASURED LIVE on the real build, and silent",
    // ⭐ NOT PRE-EMPTIVE. Before the `savedLeaguesLoading` deferral, a free account picked its
    // league on Rankings, saw the personalized board and the delta, reloaded — and was put back on
    // the generic preset with the column gone. `useFormatSelection` commits on the first manifest
    // and locks itself out, so the stored `custom:<id>` lost the race against the (uncached)
    // saved-league request and matched nothing. No error, no log; the feature just was not there
    // the second time.
    detail: "Removes the deferral, restoring the race the stored custom selection usually loses.",
    file: "lib/fantasy-queries.ts",
    from: "    if (savedLeaguesLoading) return",
    to: "    if (false) return",
    grep: "survive a reload",
  },
  {
    id: "vor-delta-subtraction-inverted",
    shipped: "pre-emptive: the sign error the highlights' new ranking can have",
    // ⭐ THE ANCHOR THIS STORY HAD TO REPLACE. The previous check — "every riser's overall rank
    // improved" — was exact while the list was SELECTED on rank movement, and became false when the
    // ranking moved to VOR (value and board position can legitimately disagree). The replacement
    // re-derives the chip from the league board's own rendered VOR and the generic board FIXTURE,
    // neither of which passes through `computeLeagueDelta` — so an inverted subtraction flips the
    // chip while both inputs stay put. A "risers all show a positive number" check would NOT catch
    // this: membership and the number flip together, which is the tautology E9.63 caught once
    // already.
    detail: "Inverts `vorDelta`, so every riser is really a faller and the chip agrees with itself.",
    file: "lib/league-delta.ts",
    from: "vorDelta: g && g.vor != null && p.vor != null ? p.vor - g.vor : null,",
    to: "vorDelta: g && g.vor != null && p.vor != null ? g.vor - p.vor : null,",
    grep: "the movement is real",
  },
  {
    id: "low-predictability-positions-lead-again",
    shipped: "G100-C1 (live) — four defenses in the top five movers",
    // ⭐ RE-PROVEN UNDER THE NEW METRIC, which is the point of keeping it. The exclusion was
    // originally argued from rank DENSITY, and E9.61 replaced rank movement with VOR delta — so the
    // density argument no longer applies and the clause could look redundant. It is not: the reason
    // that survives is that "why those players moved" is computed over skill positions only, so a
    // headlined D/ST is a mover the page structurally cannot explain. On this fixture the league
    // board's entire top is D/ST, so it is the hardest available case.
    detail: "Drops the low-predictability exclusion from the highlight population.",
    file: "lib/league-delta.ts",
    from: "  const comparable = allComparable.filter((d) => d.draftable && !d.lowPred)",
    to: "  const comparable = allComparable.filter((d) => d.draftable)",
    grep: "no kicker or defense can lead the list",
  },
  // ── the free tier's nav gate, both directions + the anchor that keeps the negative honest ────
  {
    id: "logged-out-nav-does-not-mount",
    shipped: "not a shipped defect — this proves the negative spec's ANCHOR can actually fail",
    // ⭐ THE CASE THAT TESTS THE TEST, and the only break that reaches this anchor. Removing the
    // logged-out nav's Sign Up affordance stands in for "the nav did not render": the three
    // `toHaveCount(0)`s below it are still trivially satisfied, so a RED here can only have come
    // from the anchor. Without this case the anchor would be an unfalsifiable line of ceremony —
    // which is the exact shape it was added to remove.
    detail: "Drops the Sign Up affordance from the logged-out nav, so the anchor has nothing.",
    file: "components/nav.tsx",
    from: "<Link href={SIGNUP_HREF}>Sign Up</Link>",
    to: "<span>Sign Up</span>",
    grep: "logged-out visitor is not offered",
  },
  {
    id: "league-nav-offered-to-a-logged-out-visitor",
    shipped: "the shape `public: true` would have had — a menu that lies about what it opens",
    // ⭐ DECLARED GREEN, AND THAT IS THE FINDING. Pinning it here is what keeps it one.
    //
    // "a logged-out visitor is not offered the league surfaces" reads like a guard on
    // `freeSignedIn && isSignedIn`. It is not. MEASURED while de-flaking its sibling: the anonymous
    // nav renders ONE unlabelled button and six links, with no `NFL`/`MLB` dropdown at all, because
    // `showSubNav = authenticated || isSignedIn` (nav.tsx:93) withholds the entire sport sub-nav
    // one level ABOVE the item filter. So promoting `freeSignedIn` to public puts the items in a
    // menu that is not in the DOM, and the spec cannot see it.
    //
    // The requirement still holds — anonymous visitors genuinely are not offered these — it is just
    // over-determined, and the spec's own comment now says so rather than implying a guard it does
    // not provide. If this ever flips to RED the nav's structure moved and both notes are stale.
    expect: "GREEN",
    detail: "Treats `freeSignedIn` as public; invisible here because the whole sub-nav is withheld.",
    file: "components/nav.tsx",
    from: "surfaceItems(g).filter((i) => i.public || (i.freeSignedIn && isSignedIn))",
    to: "surfaceItems(g).filter((i) => i.public || i.freeSignedIn)",
    grep: "logged-out visitor is not offered",
  },
  {
    id: "logged-out-nav-renders-nothing-at-all",
    shipped: "not a shipped defect — this measures the REACH of the negative spec's anchor",
    // ⭐ ALSO DECLARED GREEN, for the same structural reason, and it bounds what the anchor claims.
    //
    // The intent was: empty the locked menu, leaving the three `toHaveCount(0)`s trivially
    // satisfied so ONLY the render anchor can fail. It stays green because the anchor is
    // `nav a[href="/signup"]` — logged-out nav CHROME, which this filter never touches.
    //
    // That is deliberate rather than a weaker choice: for an anonymous visitor no anchor inside the
    // sport menu exists to reach for. The anchor therefore proves the nav MOUNTED (the blank-page
    // vacuity this spec really was exposed to) and nothing more, which is exactly what the spec now
    // claims. Over-claiming it would repeat the mistake one level up.
    expect: "GREEN",
    detail: "Empties the locked menu; the anchor is nav chrome, so it is untouched by design.",
    file: "components/nav.tsx",
    from: "surfaceItems(g).filter((i) => i.public || (i.freeSignedIn && isSignedIn))",
    to: "surfaceItems(g).filter(() => false)",
    grep: "logged-out visitor is not offered",
  },
  // ══ E9.64 — FANTASY INTERACTIVITY ═════════════════════════════════════════════════════════
  //
  // The gate cases come FIRST because one of them is the whole reason this story touched the nav:
  // G100-D0-R1 item 5 found that "a logged-out visitor is not offered the league surfaces" could not
  // fail, and registered TWO declared-GREEN cases above saying so. The case below is the falsifiable
  // replacement — it breaks the list that actually renders for an anonymous visitor.
  {
    id: "nav-offers-a-gated-league-surface",
    shipped: "G100-D0-R1 item 5 — pre-emptive: the future in which the protection silently vanishes",
    // ⭐⭐ THE CASE THE OLD ANCHOR COULD NOT EXPRESS. R1's two cases break `surfaceItems(...)` inside
    // `nav.tsx` and are DECLARED GREEN, correctly: an anonymous visitor never reaches that filter,
    // because `showSubNav` withholds the entire sport sub-nav. The protection was real and
    // incidental, so a future story that rendered the sport menu logged-out would remove it with no
    // test anywhere going red.
    //
    // Since E9.60 the list that ACTUALLY renders for a stranger is `SIGNED_OUT_NAV` — authored, and
    // therefore falsifiable. Putting a gated league surface in it is exactly the defect: a link
    // whose only behaviour is a bounce to /login, offered to someone with no account.
    detail: "Adds My League to the authored signed-out nav, so a stranger is offered a wall.",
    file: "lib/positioning-copy.ts",
    from: '  { label: "About", href: "/about", product: null, desktop: true },',
    to:
      '  { label: "My League", href: "/fantasy/my-league", product: "fantasy", desktop: true },\n' +
      '  { label: "About", href: "/about", product: null, desktop: true },',
    grep: "no entitlement-gated fantasy surface is offered",
  },
  {
    id: "league-surface-open-to-strangers",
    shipped: "pre-emptive: a per-caller surface losing its guard",
    // The other half of the same property — not OFFERED is not the same as not REACHABLE, and a
    // bookmark or a shared link never sees the nav. Everything on My League is computed from the
    // caller's own saved league, so an un-guarded render is a page that cannot work rather than a
    // page that leaks: `/fantasy/leagues` answers 401 and the screen renders its empty state
    // forever. Aliasing the import produces the real defect in one contiguous edit (the same shape
    // `free-board-re-gated` uses, and for the same reason — swapping the JSX tag leaves the closing
    // tag behind and the build fails instead of the spec).
    detail: "Drops FantasyLeagueGuard from My League, so a stranger is not bounced to sign in.",
    file: "app/fantasy/my-league/page.tsx",
    from: 'import { FantasyLeagueGuard } from "@/components/auth-guard"',
    to: 'import { FantasyPublicGuard as FantasyLeagueGuard } from "@/components/auth-guard"',
    grep: "refuses a stranger who follows a direct link",
  },
  {
    id: "free-account-bounced-to-login-not-upsell",
    shipped: "pre-emptive: sending a signed-in account to sign in again",
    // ⭐ THE REFUSAL THAT COSTS MONEY IF IT INVERTS. This account HAS an account; what it lacks is a
    // membership. /login is a dead end that asks them to do something they have already done, and
    // it is one line away from correct — the guard has both destinations right there. Mirrors the
    // server's 401-vs-403 split, and nothing anywhere asserted it before E9.64.
    detail: "Sends an unentitled signed-in caller to /login instead of to the upsell.",
    file: "components/auth-guard.tsx",
    from: 'if (!canAccess("fantasy", groups)) { router.push("/subscribe"); return }',
    to: 'if (!canAccess("fantasy", groups)) { router.push(loginHref(pathname)); return }',
    grep: "upsells a free account",
  },
  {
    id: "sign-in-bounce-drops-the-destination",
    shipped: "E9.58 — every guard bounce used to be a bare `/login`",
    // ⚠️ THIS ONE ACTUALLY SHIPPED. A stranger who followed a link to a walled surface, created an
    // account and came back was deposited on /dashboard with no trace of where they had been
    // heading — the signup completes and the journey does not.
    detail: "Drops `?next=` from the guard bounce.",
    file: "components/auth-guard.tsx",
    from:
      'return pathname && pathname !== "/login" ? `/login?next=${encodeURIComponent(pathname)}` : "/login"',
    to: 'return "/login"',
    grep: "refuses a stranger who follows a direct link",
  },

  // ── the free board, actually used ───────────────────────────────────────────────────────────
  {
    id: "position-filter-does-not-filter",
    shipped: "pre-emptive: a filter that repaints and narrows nothing",
    detail: "Stops scoping the board to the selected position.",
    file: "components/fantasy/rankings-board.tsx",
    from: 'const scoped = projected.filter((p) => (pos === "Overall" ? true : p.pos === pos))',
    to: "const scoped = projected",
    grep: "leaves only that position",
  },
  {
    id: "empty-search-renders-a-blank-table",
    shipped: "the silent-empty class — E9.56b's shape, reached through a control",
    // A zero-row table with no message is indistinguishable from a broken board, and it is the
    // state a visitor reaches by typing a name we do not carry. ⚠️ Its mirror — a REFUSED paid
    // board falling through to this same message — is `refusal-reads-as-an-empty-search` above;
    // the two share a zero-row table and are different facts, so both are pinned or one can be
    // "fixed" into the other.
    detail: "Removes the no-results message, leaving an empty table and no explanation.",
    file: "components/fantasy/rankings-board.tsx",
    from: "          {!boardLoading && !boardError && rows.length === 0 && (",
    to: "          {false && !boardError && rows.length === 0 && (",
    grep: "a search that matches nothing says so",
  },
  {
    id: "paging-does-not-advance",
    shipped: "pre-emptive: a Next button that repaints page one",
    detail: "Ignores the page offset, so every page renders the first slice.",
    file: "components/fantasy/rankings-board.tsx",
    from: "    () => (pageSize === ALL_ROWS ? rows : rows.slice(page * pageSize, page * pageSize + pageSize)),",
    to: "    () => (pageSize === ALL_ROWS ? rows : rows.slice(0, pageSize)),",
    grep: "paging advances through the board",
  },
  {
    id: "player-cell-links-to-one-shared-player",
    shipped: "pre-emptive: every row opening the same player's page",
    // ⭐ THE DEFECT EVERY "THE PLAYER PAGE RENDERS" ASSERTION PASSES. The click lands on a real,
    // perfectly-rendering page; it is simply about somebody else. Only following the link and
    // comparing the destination against the row that was clicked can see it — which is why the
    // spec clicks the THIRD row rather than the first (a break that binds the first row's id would
    // be invisible to a first-row click).
    detail: "Binds every row's link to the first row on the page.",
    file: "components/fantasy/rankings-board.tsx",
    from: "                              href={`/fantasy/player/${p.id}`}",
    to: "                              href={`/fantasy/player/${paged[0]?.id ?? p.id}`}",
    grep: "links to the page for THAT player",
  },

  // ── the draft optimizer ─────────────────────────────────────────────────────────────────────
  {
    id: "drafted-player-stays-on-the-board",
    shipped: "pre-emptive: a player who can be drafted twice",
    // ⭐ In a live draft this is discovered by the room, not by us. Nothing errors, nothing blanks
    // and the board looks perfect — the tool just quietly stops tracking what is gone.
    detail: "Stops removing drafted players from the available board.",
    file: "components/fantasy/draft-optimizer.tsx",
    from: "    const rows = (board ?? []).filter((p) => !draftedIds.has(p.id))",
    to: "    const rows = board ?? []",
    grep: "takes him off the board",
  },
  {
    id: "sort-direction-never-reverses",
    shipped: "pre-emptive: a column header that sorts once and then does nothing",
    // Deliberately the DIRECTION half only. The first click still works, so any "clicking Pts sorts
    // by points" assertion stays green — the control looks live and is half dead, which is the
    // failure a single-click test cannot see.
    detail: "Pins the sort direction to descending, so a second click is inert.",
    file: "components/fantasy/draft-optimizer.tsx",
    from: 'if (sortCol === col) setSortDir((d) => (d === "asc" ? "desc" : "asc"))',
    to: 'if (sortCol === col) setSortDir("desc")',
    grep: "clicking again reverses it",
  },
  {
    id: "draft-does-not-survive-a-reload",
    shipped: "pre-emptive: two hours of tracked picks lost to a refresh",
    // The reason the state is persisted at all. A draft runs in a tab that gets reloaded,
    // backgrounded and killed; this is the only test in the suite that reloads anything.
    detail: "Ignores the stored draft on restore, so every reload starts an empty draft.",
    file: "components/fantasy/draft-optimizer.tsx",
    from: "      if (raw) {\n        const s = JSON.parse(raw) as DraftState",
    to: "      if (raw && false) {\n        const s = JSON.parse(raw) as DraftState",
    grep: "mid-draft reload keeps the picks",
  },

  // ── My Teams: each roster under its OWN format ──────────────────────────────────────────────
  {
    id: "every-roster-scored-on-one-board",
    shipped: "pre-emptive: the cards relabelled, the scoring shared",
    // ⭐⭐ THE FAILURE MY TEAMS EXISTS TO NOT HAVE, and the one with no visible symptom: every card
    // renders, no NaN, nothing throws, and every number on the second league is wrong. A user
    // cannot detect it without doing the arithmetic themselves — which is exactly what the spec
    // does, from the projections payload's own reception count.
    detail: "Serves the first league's roster to every card, so both are scored on one board.",
    file: "lib/fantasy-queries.ts",
    from: "      roster: rosters[league.league_id] ?? [],",
    to: "      roster: rosters[Object.keys(rosters)[0]] ?? [],",
    grep: "different points in two leagues",
  },
  {
    id: "unresolvable-roster-row-dropped",
    shipped: "pre-emptive: data loss on the user's own roster",
    // A rostered player we cannot match to a projection is the tempting thing to filter away — the
    // table gets tidier and the user silently sees 14 of their 15 players, with no statement that
    // anything is missing.
    detail: "Hides rostered players that did not match a projection.",
    file: "components/fantasy/my-teams.tsx",
    from: "  const bench = roster.filter((r) => !r.roster.starter)",
    to: "  const bench = roster.filter((r) => !r.roster.starter && r.board)",
    grep: "unresolvable name is counted rather than hidden",
  },

  // ── NF-C6b: the cross-league portfolio rollup ────────────────────────────────────────────────
  //
  // Every one of these renders a plausible number. That is the point: a portfolio total is a single
  // figure with no visible derivation, so the reader has no way to check it and the defect ships.
  {
    id: "portfolio-total-includes-bench",
    shipped: "pre-emptive: the total that quietly counts the whole roster",
    // ⭐ THE LIKELIEST WAY THIS GOES WRONG, and it is invisible on inspection: a bench-inclusive
    // total is bigger, still plausible, still ranks the teams in a sensible-looking order, and
    // disagrees with the Starters table directly beneath it only if someone adds the rows up.
    detail: "Totals every rostered player instead of the platform's reported starters.",
    file: "lib/portfolio-rollup.ts",
    from: "roster.filter((r) => r.roster.starter)",
    to: "roster",
    grep: "sum of the starters",
  },
  {
    id: "portfolio-ranked-backwards",
    shipped: "pre-emptive: the ranking that sorts the wrong way",
    // A reversed sort is a one-character defect that produces a perfectly ordered table naming the
    // WEAKEST team first — and with two leagues there is no shape to the table that betrays it.
    detail: "Ranks by ascending total, so the lowest-projecting team is presented as #1.",
    file: "lib/portfolio-rollup.ts",
    from: ".sort((a, b) => b.bestPossible - a.bestPossible || a.leagueName.localeCompare(b.leagueName))",
    to: ".sort((a, b) => a.bestPossible - b.bestPossible || a.leagueName.localeCompare(b.leagueName))",
    grep: "ranks the teams",
  },
  {
    id: "portfolio-ranked-by-as-set",
    shipped: "pre-emptive: ranking on the lineup instead of the roster",
    // ⭐⭐ THE CASE THE WHOLE `lineupGap` FIXTURE EXISTS FOR, and the one that proves that fixture is
    // not decorative. Ranking on as-set is a DEFENSIBLE-looking mistake — it is the figure the user
    // can check — but pre-kickoff it ranks lineup-setting diligence rather than roster strength,
    // which is the distinction the PM's Option-C decision turned on.
    //
    // ⚠️ Against the `linked` pair this break is INVISIBLE: the half-PPR team leads on both readings
    // there, so the table is identical either way. Only the reversed `lineupGap` fixture separates
    // them — if this case ever goes GREEN, that fixture has stopped discriminating and the
    // "ordered by BEST-POSSIBLE" gate has quietly become vacuous.
    detail: "Sorts the summary on the platform's lineup (as-set) rather than on best-possible.",
    file: "lib/portfolio-rollup.ts",
    from: ".sort((a, b) => b.bestPossible - a.bestPossible || a.leagueName.localeCompare(b.leagueName))",
    to: ".sort((a, b) => b.asSet - a.asSet || a.leagueName.localeCompare(b.leagueName))",
    grep: "ordered by BEST-POSSIBLE",
  },
  {
    id: "portfolio-best-ignores-bench",
    shipped: "pre-emptive: a 'best possible lineup' that never looks at the bench",
    // The subtlest of the set. Feeding the optimizer only the players already starting makes
    // best-possible collapse onto as-set, so the gap is always 0.0 and the surface silently reports
    // that every lineup is already optimal — the exact opposite of the signal it exists to give,
    // with two totals that agree and therefore look consistent rather than broken.
    detail: "Runs the optimizer over the starters only, so it can never field a benched player.",
    file: "lib/portfolio-rollup.ts",
    from: "const { players } = toReportPlayers(roster)",
    to: "const { players } = toReportPlayers(startersOf(roster))",
    grep: "best-possible fields the bench",
  },
  {
    id: "portfolio-formats-caveat-hidden",
    shipped: "NF-C6P3's own finding — a caveat behind a hover is a caveat that did not render",
    // ⭐⭐ THE MOST CONSEQUENTIAL OF THE FOUR. Without this line the table is read as "which of my
    // rosters is best", which the numbers cannot support: a half-PPR total is larger than a
    // standard one for the very same players. Moving it into a `title` is exactly how it would be
    // lost in a tidy-up — the string is still there, still imported, still "on the page".
    detail: "Moves the different-scoring-systems caveat into a tooltip instead of rendering it.",
    file: "components/fantasy/my-teams.tsx",
    from: "{rollup.mixedFormats && <li>{PORTFOLIO_CAVEAT_FORMATS}</li>}",
    to: "{rollup.mixedFormats && <li title={PORTFOLIO_CAVEAT_FORMATS} />}",
    grep: "caveats render with the table",
  },
  {
    id: "portfolio-ranking-of-one",
    shipped: "pre-emptive: a one-row 'ranking'",
    // A single team ranked #1 of 1 dresses one number up as a comparison and invites the reader to
    // think a field was considered. The per-league total is the honest half and stays either way.
    detail: "Renders the cross-league ranking for an account with a single league.",
    file: "lib/portfolio-rollup.ts",
    from: "if (rollups.length < 2) return null",
    to: "if (rollups.length < 1) return null",
    grep: "no ranking",
  },

  {
    id: "portfolio-mobile-fixed-width-summary",
    shipped: "NF-C6b — the rollup shipped unreadable on a phone",
    // ⭐ THE OPERATOR'S OWN BUG, restored. `min-w-[520px]` on the summary makes the table wider than
    // a phone, so the reader has to drag it sideways to reach the ranked figure and the bench gap —
    // the two numbers the surface exists for. Desktop-only assertions cannot see this: at 1280px
    // every column fits and the page verifies as correct.
    detail: "Puts a fixed 520px minimum back on the summary table.",
    file: "components/fantasy/my-teams.tsx",
    from: '      <div className="mt-3 overflow-x-auto">\n        <table className="w-full text-left text-[11px]">',
    to: '      <div className="mt-3 overflow-x-auto">\n        <table className="w-full min-w-[520px] text-left text-[11px]">',
    // ⚠️ NOT the page-level "never scrolls sideways" test — that one CANNOT catch this, because
    // `overflow-x-auto` keeps the DOCUMENT tidy while the table scrolls inside its own container.
    // Pointing this case at it produced a MISMATCH (green on broken source) on the first cut, which
    // is precisely the vacuous-guard shape the red proof exists to surface.
    grep: "numbers that matter",
  },
  {
    id: "portfolio-mobile-fixed-width-roster",
    shipped: "NF-C6b — the roster tables the operator actually screenshotted",
    // The pre-existing half of the same defect: the Starters/Bench tables carried `min-w-[480px]`
    // from NF-C6 Phase 1, which is what cut "Expected pts" off the right edge of the screenshot.
    detail: "Puts a fixed 480px minimum back on the roster tables.",
    file: "components/fantasy/my-teams.tsx",
    from: '      <div className="mt-2 overflow-x-auto">\n        <table className="w-full text-left text-[11px]">',
    to: '      <div className="mt-2 overflow-x-auto">\n        <table className="w-full min-w-[480px] text-left text-[11px]">',
    grep: "numbers that matter",
  },

  // ── league import: the review queue ─────────────────────────────────────────────────────────
  {
    id: "import-warnings-suppressed",
    shipped: "pre-emptive: an import that quietly loses a rule",
    // ⭐⭐ The component's own comment names this as the failure the whole surface guards. A league
    // whose scoring we silently dropped produces a board that is confidently wrong all season, on
    // the user's own settings, and this screen is the only place it is ever mentioned.
    detail: "Stops rendering the platform rules we could not represent.",
    file: "components/fantasy/league-import.tsx",
    from: "          {preview.warnings.length > 0 && (",
    to: "          {false && (",
    grep: "word for word, before saving",
  },
  {
    id: "coverage-claims-everything-applies",
    shipped: "pre-emptive: an unchecked coverage report presented as a clean one",
    // ⚠️ THE OPTIMISTIC RENDER IS THE NATURAL ONE TO WRITE. The resolver reads an absent column set
    // as "we have everything", so a panel that simply renders whatever it has states a FALSE fact
    // about the user's league on any upstream outage — and "the panel is absent" reads to a user as
    // "this league has no unsupported settings". Both non-answers have to be named out loud.
    detail: "Removes the could-not-check panel when the projections read fails.",
    file: "components/fantasy/league-import.tsx",
    from: "          {!coverage && !projectionsPending && (",
    to: "          {false && !projectionsPending && (",
    grep: "coverage check that could not run says so",
  },

  // ── G100-D0-R1: the signup event counts ACCOUNTS, not buttons ────────────────────────────────
  {
    id: "signup-keyed-on-the-button-again",
    shipped: "G100-D0 (live) — R1 under-counted every signup that entered through /login",
    // ⭐ THE DEFECT THIS STORY EXISTS TO FIX, and it was live in production: every self-serve door
    // auto-provisions, so a first-timer clicking SIGN IN got a real new account and emitted no
    // signup event at all. Because R1's funnel is ORDERED, those people were then discarded from
    // it entirely — neither signups nor drop-offs. Measured: all 16 auth events in production's
    // first 48h used the /login door.
    detail: "Restores the pre-R1 rule — emit on the stashed intent instead of the server's answer.",
    file: "lib/post-signin.ts",
    from: "  if (acceptance.known) {\n    if (acceptance.created) {",
    to: '  if (acceptance.known) {\n    if (intent === "signup") {',
    grep: "SIGN IN door is counted as a signup",
  },
  {
    id: "intent-overrides-the-server",
    shipped: "G100-D0 (live) — the other half: a returning user who clicked Sign Up was counted",
    // Fixing one direction and not the other leaves the funnel wrong. This is the shape a
    // "helpful" fallback naturally has — honour the intent whenever it says signup — and it
    // silently restores a false positive on top of an authoritative `created: false`.
    detail: "Lets the intent fallback run even when the server DID answer.",
    file: "lib/post-signin.ts",
    from: "  if (acceptance.known) {",
    to: "  if (false) {",
    grep: "RETURNING user who clicks Sign Up",
  },
  {
    id: "absent-created-read-as-false",
    shipped: "the NF-C0 / E8.6 deploy-skew class (the API Lambda has no CD)",
    // ⭐ ABSENT ≠ FALSE, the same distinction `lib/terms.ts` already draws for `tos_accepted_at`.
    // Collapsing them takes step 2 of the funnel to a flat ZERO for the whole skew window, and a
    // zero on a conversion chart reads as a conversion collapse rather than as a missing deploy.
    detail: "Coerces an absent `created` to false, so an un-deployed Lambda zeroes the funnel.",
    file: "lib/terms.ts",
    from:
      'if (!res || typeof res.created !== "boolean") return { known: false }\n' +
      "  return { known: true, created: res.created }",
    to: "return { known: true, created: Boolean(res && res.created) }",
    grep: "un-deployed backend degrades",
  },

  // ── E9.64b: the two REAL import paths — ESPN paste, and Yahoo OAuth ─────────────────────────
  {
    id: "espn-league-named-as-sleeper",
    shipped: "LIVE UNTIL E9.64b — every ESPN import read back as a Sleeper league",
    // ⭐⭐ A REAL DEFECT, FOUND BY WRITING THIS STORY'S SPEC. The review screen named the platform
    // with a TWO-WAY test on a THREE-WAY field, so the paste flow — on the platform with the
    // largest share of leagues — told the user their ESPN league came from Sleeper, on the one
    // screen whose entire job is to let them check what we understood. Both branches are strings,
    // so `tsc` was happy; nothing had ever opened this screen on a non-Sleeper preview.
    detail: "Restores the two-way platform test on a three-way field.",
    file: "components/fantasy/league-import.tsx",
    from: "                  {platformLabel(preview.platform)}\n                  {preview.season",
    to: '                  {preview.platform === "yahoo" ? "Yahoo" : "Sleeper"}\n                  {preview.season',
    grep: "read back correctly from its own real payload",
  },
  {
    id: "espn-yardage-scored-as-captured",
    shipped: "NF-C0e — every ESPN league scored ZERO passing/rushing/receiving yardage",
    // ⭐⭐ THE OUTAGE, RENDERED. `espn.py` wrote Sleeper's `pass_yd` where the engine reads the
    // canonical `pass_yds`; an unrecognised key passes through verbatim and reports CAPTURED, which
    // is a legitimate verdict for a rule we genuinely do not project — so nothing errored and the
    // panel truthfully said so while nobody read it. Broken here from the CONSUMER side (the
    // canonical map itself), which produces the identical rendered state: the term moves out of
    // APPLIED and into "Saved with your league, but NOT applied".
    detail: "Drops the canonical `pass_yds` key from STAT_FIELD, exactly as the outage did.",
    file: "lib/league-config.ts",
    from: 'pass_yds: "passYds"',
    to: 'pass_yd: "passYds"',
    grep: "scoring is APPLIED, not silently captured",
  },
  {
    id: "espn-read-url-built-locally",
    shipped: "pre-emptive: the settings link assembled client-side instead of by the server",
    // `POST /espn/read-url` exists so the SERVER owns this string — it format-checks the league id
    // and builds ESPN's path. A locally-built link renders perfectly, works today, and breaks
    // silently the day ESPN's path moves. The E9.58 shape: internally consistent everywhere, and
    // pointing somewhere that does not answer.
    detail: "Ignores the server's URL and constructs one in the browser.",
    file: "components/fantasy/league-import.tsx",
    from: "    if (res?.url) setEspnLink(res.url)",
    to: '    setEspnLink(`https://fantasy.espn.com/football/league?leagueId=${espnLeagueId.trim()}`)',
    grep: "the SERVER's, not one the page assembled",
  },
  {
    id: "espn-prune-walk-stops-walking",
    shipped: "pre-emptive: pruneEspnPayload silently stops removing the bulk",
    // ⭐⭐ THE DEFECT WITH NO SYMPTOM. `pruneEspnPayload` is the only reason a real ESPN league fits
    // under the server's 4 MB paste cap — un-pruned a real drafted response is ~3.3 MB for TEN
    // teams, a 12-team league lands at ~99% of the cap and a 14-team league is REFUSED. And it is
    // wrapped in `catch { return text }`, so on any shape it does not expect it hands the ORIGINAL
    // back. Nothing errors, nothing renders differently, and the import simply starts failing for
    // size on the two commonest league sizes.
    //
    // Renaming the key it walks is the NF-C0e class exactly: a plausible identifier, a walk that
    // finds nothing, and a function that reports success. ⚠️ Note what this case CANNOT reach: the
    // spec it fails is the SYNTHETIC size probe, which is built from the same belief about ESPN's
    // shape the pruner encodes — so it catches the walk BREAKING, never the belief being WRONG.
    // That half needs the operator-supplied un-pruned captures (see `espn-raw-captures.ts`); until
    // they land, the ten tests guarding it skip and say so in the run output.
    detail: "The player walk iterates a key that does not exist, so no bulk is ever removed.",
    file: "lib/fantasy-import.ts",
    from: "    for (const t of doc.teams ?? []) {",
    to: "    for (const t of doc.teamsById ?? []) {",
    grep: "pruner survives a real-size",
  },
  {
    id: "import-error-replaced-with-a-generic-string",
    shipped: "pre-emptive: the server's actionable message swapped for 'something went wrong'",
    // `errorText`'s own docstring names this: the API's `detail` is written to be READ by a user
    // ("that doesn't look like the JSON from ESPN — open the link we generated…"), and substituting
    // a generic string throws away the only sentence that says what to DO. On the paste flow that
    // is the difference between a recoverable typo and a dead end.
    detail: "Discards the server's detail on every error.",
    file: "components/fantasy/league-import.tsx",
    from: 'if (!/^API error \\d+$/.test(message)) return message || "Something went wrong."',
    to: 'if (!/^API error \\d+$/.test(message)) return "Something went wrong."',
    grep: "says WHY, at the control",
  },
  {
    id: "could-not-read-box-always-rendered",
    shipped: "pre-emptive: telling every user we failed to read their league",
    // ⭐ THE OTHER SIDE OF `import-warnings-suppressed`, and it needed a second real payload to be
    // reachable at all: one committed ESPN capture parses with ZERO warnings. A component that
    // rendered the header unconditionally passes the suppression case while alarming most users
    // about a league we read perfectly.
    detail: "Renders the 'what we could not read' header even with nothing to report.",
    file: "components/fantasy/league-import.tsx",
    from: "          {preview.warnings.length > 0 && (",
    to: "          {true && (",
    grep: "read CLEANLY shows no",
  },
  {
    id: "captured-rule-shown-as-its-espn-number",
    shipped: "pre-emptive: a disclosure the reader cannot act on",
    // ESPN NUMBERS its scoring rules, so a captured term renders as "15" or "129@dst" without the
    // server's label. Technically honest and completely useless: the user cannot tell WHICH of
    // their settings we dropped, which is the entire point of the disclosure.
    detail: "Stops reading the server's `unmapped_labels`.",
    file: "components/fantasy/league-import.tsx",
    from: "                                {preview.unmapped_labels?.[t.key] ?? t.key}",
    to: "                                {t.key}",
    grep: "ESPN number is made readable",
  },
  {
    id: "yahoo-connect-offered-before-approval",
    shipped: "pre-emptive: a button that 503s, on a platform Yahoo has not approved",
    // `list_platforms`' docstring names this exact trade: `available` and `configured` are reported
    // separately so the UI can say "coming, pending registration" instead of hiding the option or
    // offering a control the server refuses. Production is in this state TODAY.
    detail: "Offers the connect button regardless of the runtime `configured` flag.",
    file: "components/fantasy/league-import.tsx",
    from: "            {!platform?.configured ? (",
    to: "            {false ? (",
    grep: "offers NO button to press",
  },
  {
    id: "yahoo-authorize-url-rebuilt-locally",
    shipped: "pre-emptive: the OAuth URL assembled client-side, dropping the signed `state`",
    // ⭐ The signed `state` is the ONLY thing binding a returning Yahoo grant to the account that
    // started the flow — the callback is unauthenticated by necessity, since it is entered by a
    // browser redirect carrying no bearer token. A client that rebuilds this URL either fails the
    // round trip or grafts a Yahoo account onto the wrong Credence one.
    detail: "Navigates to a locally-assembled authorize URL instead of the server's.",
    file: "components/fantasy/league-import.tsx",
    from: "    if (res?.authorize_url) window.location.href = res.authorize_url",
    to: '    window.location.href = "https://api.login.yahoo.com/oauth2/request_auth?client_id=local"',
    grep: "authorize URL the SERVER supplied",
  },
  {
    id: "yahoo-return-states-collapsed",
    shipped: "pre-emptive: one banner for connected, cancelled and failed",
    // Three distinct facts. A single "you're connected" for all of them is wrong twice over: a user
    // who CANCELLED is told they granted access, and a user whose sign-in FAILED never learns that
    // nothing was saved before they walk away believing we hold a grant.
    detail: "Shows the connected banner for every return flag.",
    file: "components/fantasy/league-import.tsx",
    from: '      {yahooFlag === "connected" && (',
    to: "      {yahooFlag && (",
    grep: "says what actually happened",
  },
  {
    id: "yahoo-owner-team-not-preselected",
    shipped: "pre-emptive: throwing away the one thing OAuth tells us that a paste cannot",
    // Yahoo's response carries `is_current_login`, so the preview knows which team is the caller's —
    // which is what lets My Teams score a roster without the user picking one. Discarding it is not
    // a crash: the screen renders perfectly and quietly saves a league with no team linked.
    detail: "Ignores `is_owner` when adopting a preview.",
    file: "components/fantasy/league-import.tsx",
    from: "    setSelectedTeamKey(res.teams.find((t) => t.is_owner)?.team_key ?? null)",
    to: "    setSelectedTeamKey(null)",
    grep: "pre-selects the user's team",
  },
  {
    id: "yahoo-attribution-dropped",
    shipped: "pre-emptive: a CONTRACTUAL requirement, invisible to every other instrument",
    // 🚩 Yahoo's API terms require attribution wherever their data is shown. It renders in one
    // branch nothing had ever entered, and losing it is a compliance failure that looks — to `tsc`,
    // to `next build`, and to every other spec here — like a perfectly clean page.
    detail: "Removes the Yahoo attribution from a screen showing Yahoo data.",
    file: "components/fantasy/league-import.tsx",
    from: '          {preview.platform === "yahoo" && (',
    to: "          {false && (",
    grep: "required attribution is rendered",
  },

  // ══ NF-C6P2 — THE POST-DRAFT ROSTER REPORT ══════════════════════════════════════════════════
  //
  // The report is an AGGREGATOR over already-served values, so its defects are not crashes. Every
  // case below renders a complete, clean, plausible page and is wrong — which is exactly the class
  // this file exists for, and the class `tsc`/`next build`/eslint are all blind to.
  {
    id: "total-is-not-the-lineup",
    shipped: "pre-emptive: a headline total that is not the sum of the lineup beneath it",
    // The E9.46 rank defect in a new costume: a plausible-looking number that is not the one the
    // label claims. Totalling the whole ROSTER instead of the STARTERS is the natural way to write
    // it, is off by the entire bench, and reads as a perfectly normal page — a user would have to
    // add up ten rows by hand to notice.
    detail: "Totals every rostered player instead of the ones actually in the lineup.",
    file: "lib/roster-report.ts",
    from: '  const total = slots.reduce((n, s) => n + (s.player?.pts ?? 0), 0)',
    to: '  const total = players.reduce((n, p) => n + p.pts, 0)',
    grep: "sum of the starting lineup",
  },
  {
    id: "unmatched-roster-row-vanishes",
    shipped: "pre-emptive: a rostered player we could not resolve, dropped without a word",
    // ⛔ AN ABSENCE MUST BE REPORTED, NEVER IMPUTED (NF1.7 (a)). Silently dropping the row makes the
    // report describe a smaller team than the user has, while presenting as complete. The opposite
    // error — scoring it as zero — is equally invisible and understates the total instead.
    detail: "Stops counting roster rows that did not match the board.",
    file: "lib/roster-report.ts",
    from: "      unmatched.push(name || String(row.roster?.player_key ?? \"unknown\"))",
    to: "      // dropped",
    grep: "could not resolve is named",
  },
  {
    id: "empty-states-collapsed",
    shipped: "NF-C6's own shipped bug, one surface over",
    // "You never picked a team" and "your league has not drafted" are different facts with
    // different next actions. NF-C6 shipped them sharing a message and told a real user to go and
    // pick a team they had already picked. Collapsing them here reproduces that exactly.
    detail: "Reports a pre-draft league as though no team were linked.",
    file: "lib/roster-report.ts",
    from: '      reason: league.source_team_key ? "not-drafted" : "no-team-linked",',
    to: '      reason: "no-team-linked",',
    // ⚠️ THE WHOLE DESCRIBE BLOCK, not the one test whose title contains "NOT the same message" —
    // which is what this case first pointed at, and it came back GREEN twice. That test drives the
    // captured league (`source_team_key: null`), so it renders "no team linked" both before and
    // after the break and structurally cannot see it. The clause that CAN is the positive one on a
    // LINKED, undrafted league, so the grep has to reach it.
    grep: "four different messages",
  },
  {
    id: "upgrade-prompt-sold-to-subscribers",
    shipped: "pre-emptive: selling a member what they already pay for",
    // Reads to a paying subscriber as a bug in our billing, and it passes every positive assertion
    // about the prompt — only the negative half can see it.
    detail: "Renders the season-upgrade prompt regardless of entitlement.",
    file: "components/fantasy/roster-report.tsx",
    from: "  if (entitled) return null",
    to: "  if (false) return null",
    grep: "NOT sold what they already pay for",
  },
  {
    id: "team-band-swapped-for-the-correlated-one",
    shipped: "pre-emptive: the pessimistic band presented as the honest one",
    // ⭐ THE HONESTY DEFECT WITH NO VISIBLE SYMPTOM. Independence under-disperses a correlated sum
    // (NF-W7b measured it), which is why BOTH ends are published and the wider one is labelled as
    // the outer bound. Swapping them puts the comonotone band in the headline and the narrow one in
    // the "if every season moved in step" line — every number is real, both are still rendered, and
    // the page now says the widest reading is the tight one.
    detail: "Swaps the independent band with the fully-correlated bound.",
    file: "lib/roster-report.ts",
    from: "    p10: Math.max(0, total - Z80 * Math.sqrt(varLo)),\n    p90: total + Z80 * Math.sqrt(varHi),\n    correlatedP10: Math.max(0, sumLo),\n    correlatedP90: sumHi,",
    to: "    p10: Math.max(0, sumLo),\n    p90: sumHi,\n    correlatedP10: Math.max(0, total - Z80 * Math.sqrt(varLo)),\n    correlatedP90: total + Z80 * Math.sqrt(varHi),",
    grep: "correlated bound is at least as wide",
  },
  {
    id: "our-rank-falls-back-to-the-matched-set",
    shipped: "E9.46 — the open follow-up this story closed",
    // ⭐ THE DEFECT THE LIVE CARD COULD NOT SHOW. `ourRank` was the ADP-MATCHED rank while
    // /fantasy/rankings ranks the full board; George Kittle sat at TE21 under both readings, so the
    // site displayed no contradiction and the divergence stayed invisible. Measured on the served
    // board the populations are nowhere near each other (TE 23 of 169).
    //
    // The break here is the natural client-side spelling of the regression — preferring the matched
    // rank when it is present — and the spec catches it because the harness serves a rank the
    // fixture cannot contain and demands the DOM follow it (the E9.59 hardcoded-price shape).
    //
    // ⚠️ The POPULATION itself is proven server-side, against the shipping selector, in
    // `test_e9_46_featured_player.py` with a deliberately DEEP position — a browser cannot see it,
    // because the featured fixture and the board fixture are generated from different sources.
    detail: "Renders the ADP-matched rank in the tile labelled with the full-board one.",
    file: "components/home/featured-fantasy-player.tsx",
    from: "<PositionRank label={COPY.ourRankLabel} pos={player.pos} rank={market.ourRank} />",
    to: "<PositionRank label={COPY.ourRankLabel} pos={player.pos} rank={market.ourRankAmongDrafted ?? market.ourRank} />",
    grep: "rank is the SERVER",
  },
  {
    id: "tabs-that-do-not-tab",
    shipped: "pre-emptive: tabs that render every panel and hide the inactive ones",
    // ⭐ THE FIX THAT LOOKS LIKE THE FIX. The operator's report was "too much scrolling" (2026-08-15,
    // eight stacked sections ≈ four screens). A tab strip whose panels all render — hidden with CSS,
    // or simply not gated at all — satisfies every "is this section visible" assertion, looks
    // correct in a screenshot, and changes NOTHING about the problem: the page is still four screens
    // long and a screen reader still reads all eight sections in order.
    //
    // The break makes `Panel` unconditional, which is exactly how it would really be written wrong.
    detail: "Renders every panel regardless of which tab is selected.",
    file: "components/fantasy/roster-report.tsx",
    from: "  if (id !== active) return null",
    to: "  if (false) return null",
    grep: "tabbed, not a single scroll",
  },
  {
    id: "dst-join-reverted",
    shipped: "NF-C6P3 — the D/ST starting slot was EMPTY for every imported league",
    // ⭐ THIS IS THE DEFECT AS IT ACTUALLY SHIPPED, and it is the most instructive case on the board.
    // Our own board publishes a team defence as "SEA D/ST"; every platform publishes a NICKNAME
    // ("Seahawks D/ST", "Detroit Lions", "Seattle"). Folded through the name normalizer those are
    // `sea dst` and `seahawks dst`, so the join matched NO defence on ANY platform — and because a
    // miss is a legitimate `board: null`, nothing errored: the slot rendered "nobody eligible" and
    // its points were silently missing from the headline total.
    //
    // ⚠️ The case only bites because the fixture's D/ST row is taken from the REAL captured ESPN
    // league (`platformDstRow`). A roster row built from our own board's naming matches trivially
    // even with this branch removed, and the whole clause would pass on nothing (NF-C0e).
    detail: "Removes the team-defence branch, restoring the name-only join.",
    file: "lib/league-scoring.ts",
    from: '  if (position === "DST") {',
    to: "  if (false) {",
    grep: "D/ST slot is filled",
  },
  {
    id: "free-agent-pool-ignores-the-rosters",
    shipped: "NF-C6P3 — pre-emptive: the pool stops reading the league's stored rosters",
    // The section still renders, still calls itself a free-agent pool, and still carries the
    // sentence saying it is one — it just offers players who are on somebody's roster. Nothing
    // about the page looks wrong; the list is simply a claim we can no longer support.
    detail: "Every unowned-by-me player is treated as available again.",
    file: "lib/roster-report.ts",
    from: "if (rosteredIds) return !rosteredIds.has(p.id)",
    to: "if (rosteredIds) return true",
    grep: "excludes players on another manager",
  },
  {
    id: "partial-league-read-as-complete",
    shipped: "NF-C6P3 — pre-emptive: partial roster coverage promoted to a free-agent claim",
    // ⭐ THE DANGEROUS DIRECTION. With 8 of 12 rosters held, this break lists four teams' worth of
    // ROSTERED players as free agents — a confidently wrong list that reads exactly like a right
    // one, under copy that has just told the reader we hold every roster.
    detail: "Treats any held roster as complete coverage of the league.",
    file: "lib/roster-report.ts",
    from: "const complete = held.length > 0 && nTeams > 0 && held.length >= nTeams",
    to: "const complete = held.length > 0",
    grep: "reports the absence instead of guessing",
  },
  {
    id: "comparison-rank-is-not-the-table",
    shipped: "NF-C6P3 (b) — pre-emptive: the comparison ranks by something it does not render",
    // ⭐ THE PLAUSIBLE-LOOKING WRONG NUMBER, on the most quotable figure the page produces. Sorting
    // by team NAME still renders a complete, tidy, ordered-looking table with a rank column and a
    // summary sentence — and the reader's position in their league is simply wrong. Nothing about
    // the page looks broken (E9.46's rank, one surface over).
    detail: "Orders the table alphabetically instead of by the totals it renders.",
    file: "lib/roster-report.ts",
    from: "    .sort((a, b) => b.total - a.total || a.teamName.localeCompare(b.teamName))",
    to: "    .sort((a, b) => a.teamName.localeCompare(b.teamName))",
    grep: "rank follows the totals",
  },
  {
    id: "comparison-caveats-behind-a-click",
    shipped: "NF-C6P3 (b) — pre-emptive: the standings caveats move behind a disclosure",
    // ⛔ THE FAILURE THIS WHOLE SECTION IS SHAPED AGAINST. A ranked table answers "did I win my
    // draft?" whether or not it was asked; the three caveats are what keep it a statement about
    // projected starter points. Behind a <details> they render for nobody, the table reads as
    // standings, and not one number on the page has changed.
    detail: "Wraps the caveat list in a collapsed disclosure.",
    file: "components/fantasy/roster-report.tsx",
    from: '      <ul className="mt-3 space-y-1.5 text-[11px] leading-relaxed text-gray-500" data-testid="league-comparison-caveats">',
    to: '      <ul hidden className="mt-3 space-y-1.5 text-[11px] leading-relaxed text-gray-500" data-testid="league-comparison-caveats">',
    grep: "caveats render with the table",
  },
  {
    id: "comparison-promises-a-finish",
    shipped: "NF-C6P3 (b) — pre-emptive: the ranking is restated as a projected finish",
    // The one sentence that turns arithmetic into a forecast. It needs a weekly-variance schedule
    // simulation that does not exist, and `best_alpha = 0`.
    detail: "Rewrites the comparison note as an outcome claim.",
    file: "lib/fantasy-claim-copy.ts",
    from: '  "Every team\'s roster filled by our optimizer and totalled on your league\'s own board',
    to: '  "Your projected finish this season, from every team\'s roster filled by our optimizer',
    grep: "no finish, no odds",
  },
  {
    id: "props-default-sort-is-not-slate-order",
    shipped: "E5.10 — pre-emptive: the honest-framing ruling that Slate order is ALWAYS the default",
    // ⭐ THE PM RULING, MADE RED-PROVABLE. "Difference vs books" is a legitimate sort, but the ruling
    // was that it must NEVER be the default — this is what makes that a checked property rather than
    // a comment nobody re-verifies. Nothing about the page looks broken: every sort option still
    // works, the labels are still honest, the slate still renders. Only the FIRST thing a visitor
    // sees has quietly become the delta ranking.
    // ⚠️ NOT the `useState` initializer — the slate-key-reset effect runs unconditionally on mount
    // (`initializedSlateKey` starts null) and OVERWRITES it, so the effect's own default is what a
    // visitor actually sees. That effect call is the one this case has to break.
    detail: "The reset effect opens the sort control on Difference vs books instead of Slate order.",
    file: "app/props/page.tsx",
    from: '    setSearch("")\n    setSortKey("slate")',
    to: '    setSearch("")\n    setSortKey("diff")',
    grep: "Slate order stays the default|reads Slate order on first load",
  },
  {
    id: "props-team-chip-does-not-filter",
    shipped: "E5.10 — pre-emptive: the team/matchup filter chip becomes a no-op",
    // The chip still renders, still shows as pressed/active, and the page does not error — it just
    // stops actually narrowing the slate, so a 15-game slate goes back to being a scroll problem
    // one click at a time.
    detail: "groupMatchesTeams always reports a match, so no team chip can ever narrow the slate.",
    file: "lib/props-slate.ts",
    from: "export function groupMatchesTeams(teams: string[], selected: Set<string>): boolean {\n  if (selected.size === 0) return true\n  return teams.some((t) => selected.has(t))\n}",
    to: "export function groupMatchesTeams(teams: string[], selected: Set<string>): boolean {\n  return true\n}",
    grep: "team filter chip jumps straight to that game",
  },
  {
    id: "props-search-does-not-filter",
    shipped: "E5.10 — pre-emptive: the name search box stops narrowing the slate",
    // The input still accepts text and nothing errors — every row just keeps rendering underneath
    // it, which is indistinguishable from a search that works right up until you look for the one
    // batter you typed.
    detail: "matchesSearch always returns true, so no query narrows the rendered rows.",
    file: "lib/props-slate.ts",
    from: 'export function matchesSearch(row: SlateRow, search: string): boolean {\n  const q = search.trim().toLowerCase()\n  if (!q) return true\n  return (row.fullName ?? "").toLowerCase().includes(q)\n}',
    to: "export function matchesSearch(row: SlateRow, search: string): boolean {\n  return true\n}",
    grep: "a partial name narrows to that one player's game",
  },
  {
    id: "props-sort-does-not-reorder",
    shipped: "E5.10 — pre-emptive: a non-Slate sort flattens the slate without actually sorting it",
    // The mode switch (grouped → flat list) still fires, so the page LOOKS like it changed — the
    // cards are just left in whatever order they arrived in, not ordered by the metric the Sort
    // control now claims to be showing.
    detail: "sortRowsByMetric drops the comparator, so the flat list keeps its original order.",
    file: "lib/props-slate.ts",
    from: "  return [...rows].sort((a, b) => metric(b) - metric(a))",
    to: "  return [...rows]",
    grep: "Proj TB sorts the flattened slate by projection, descending",
  },
  {
    id: "props-sportsbook-chip-does-not-filter",
    shipped: "E5.10 — pre-emptive: the sportsbook filter chip becomes a no-op",
    // The operator's own follow-up request: "if my betting platform is Bovada, a user should be
    // able to filter down to those books". The chip still renders and still shows as pressed —
    // it just stops actually narrowing the slate to that book's own props.
    detail: "matchesBooks always reports a match, so no sportsbook chip can ever narrow the slate.",
    file: "lib/props-slate.ts",
    from: "export function matchesBooks(row: SlateRow, selected: Set<string>): boolean {\n  if (selected.size === 0) return true\n  return row.books.some((b) => selected.has(b))\n}",
    to: "export function matchesBooks(row: SlateRow, selected: Set<string>): boolean {\n  return true\n}",
    grep: "a sportsbook chip leaves only rows that book actually quoted",
  },
  {
    id: "league-picker-reverts-to-teams-0",
    shipped: "G100-C2 — pre-emptive: the multi-league picker stops actually switching leagues",
    // The pre-story shape, restated: `entry` ignores the URL/picker selection entirely and always
    // reads `teams[0]`. The control still renders, still lists both leagues, and still LOOKS like
    // it worked — the heading and board simply never move, because nothing downstream of `entry`
    // was ever reading the selection to begin with.
    detail: "`entry` always resolves to teams[0], so picking the second league changes nothing.",
    file: "components/fantasy/my-league.tsx",
    from: "    return requested ?? teams[0]",
    to: "    return teams[0]",
    grep: "switching leagues re-scores the whole page for the selected league",
  },
  {
    id: "mock-value-lists-inverted",
    shipped: "NF-C2.1 — the defect this SHIPPED with, reported off a real mock draft",
    // ⚠️ NOT pre-emptive. This one went out. `vsMarket` was `marketRank - overallPick`, which is
    // POSITIVE for a REACH, and the screen filed the positive list under "fell furthest past ADP" —
    // so both lists were exactly backwards. Live example from the report: Jordyn Tyson, taken at
    // #44 with an ADP of 94, presented as the draft's biggest value when he was a fifty-pick reach.
    //
    // It survived because the only assertion on that panel was that it RENDERS. An inverted list
    // renders perfectly, with plausible names and plausible numbers, and reads as a feature — which
    // is why the guard that replaced it plants one unambiguous steal and one unambiguous reach and
    // demands each land in its own list.
    detail: "Flips the sign of vsMarket, so steals and reaches swap places exactly as they shipped.",
    file: "lib/mock-draft.ts",
    from: "      vsMarket: adp == null ? null : Math.round(overallPick - adp),",
    to: "      vsMarket: adp == null ? null : Math.round(adp - overallPick),",
    grep: "point the right way",
  },
  {
    id: "mock-cpu-ignores-the-market",
    shipped: "NF-C2.1 — pre-emptive: the CPU room quietly stops reading ADP",
    // ⚠️ THE DEFECT WITH NO SYMPTOM. Every visible thing still works — the room picks, the log
    // fills, names disappear off the board, the draft grades — it is just no longer a DRAFT ROOM.
    // Opponents would take our board's order, so the user could sit on a consensus first-rounder
    // until round 5 and the whole practice value is gone. Nothing renders differently; only an
    // assertion about the DISTRIBUTION of the picks can see it, which is why the engine half of
    // this spec exists at all.
    detail: "The persona blend collapses to our own board rank, so the market half of it is dead.",
    file: "lib/mock-draft.ts",
    from: "    let key = persona.marketWeight * mr + (1 - persona.marketWeight) * br",
    to: "    let key = br",
    grep: "roughly when the market drafts them",
  },
  {
    id: "mock-sim-is-not-replayable",
    shipped: "NF-C2.1 — pre-emptive: 'Skip to my pick' becomes a DIFFERENT draft",
    // ⭐ THE CASE THAT PROVES THE REPLAY TEST IS NOT DECORATIVE. Carrying one generator across the
    // batch is the obvious way to write a seeded sim, and it is wrong here for a reason that never
    // surfaces as an error: the result then depends on how many picks were drawn in one call. The
    // timer path draws one at a time, the skip button draws many, and a mid-draft reload replays
    // from stored picks — three paths, three different drafts, no symptom except that the room
    // changes under you when you press fast-forward.
    detail: "One generator shared across every pick, so the draft depends on the batching.",
    file: "lib/mock-draft.ts",
    from: "  const rng = makeRng(hashSeed(seed, overallPick, slot))",
    to: "  const rng = ((globalThis as unknown as { __rp?: () => number }).__rp ??= makeRng(seed))",
    grep: "IDENTICAL draft",
  },
  {
    id: "mock-grade-drops-its-circularity-note",
    shipped: "NF-C2.1 — pre-emptive: the grade presented as a verdict on the team",
    // ⚠️ THE OVERCLAIM THIS FEATURE IS ONE COPY EDIT AWAY FROM AT ALL TIMES, and no word-list can
    // catch it: the remaining copy is entirely denylist-clean. The room is ranked on OUR
    // projections — the same numbers the recommendation panel maximises — while the CPU seats draft
    // partly off market ADP, so a user who follows the recommendations tends to finish top BY
    // CONSTRUCTION. Without the note, "1st of 12" reads as evidence the tool works. Deleting the
    // paragraph is exactly the edit someone makes to tighten a results screen.
    detail: "Removes the note saying the grade scores the room on the same projections it advised from.",
    file: "components/fantasy/mock-draft.tsx",
    from: "        {GRADE_CIRCULARITY_NOTE}\n",
    to: "",
    grep: "roster grades",
  },
  {
    id: "flex-seat-scored-on-position-replacement",
    shipped: "NF-C2.1 follow-up — the TE-for-FLEX push, reported off a real mock draft",
    // ⚠️ NOT pre-emptive. This shipped, in the live Draft Optimizer as well as the mock: a flex-only
    // candidate was scored on his own position's VOR, and TE replacement sits ~19 points below RB/WR
    // replacement on the served board, so every TE carried that head start into a seat that only
    // collects points. Measured over 200 drafts on the served board, the pick it displaced was a
    // TE-at-FLEX in 181 of 181 cases.
    //
    // It survived because it is not a bug in any single number — every VOR was correct, the panel
    // rendered, the reason read sensibly ("Fills an open FLEX (TE-eligible)"). It was a UNITS error,
    // and the only thing that can catch a units error is a fixture that states the right answer
    // independently: whichever player projects more POINTS.
    detail: "Scores a flex-only candidate on his own position's VOR, exactly as it shipped.",
    file: "lib/draft-optimizer.ts",
    from: "    const base = seatValue(p)",
    to: "    const base = vor",
    grep: "does not win the FLEX seat",
  },
  {
    id: "flex-seat-fix-became-a-te-penalty",
    shipped: "NF-C2.1 follow-up — pre-emptive: the OVER-correction, and the likelier future edit",
    // ⭐ THE OTHER DIRECTION, and the one a future session is more likely to reach for. "Stop
    // recommending TEs at flex" is one line away from a blanket TE demotion, which would break the
    // DEDICATED TE slot — where VOR is exactly the right unit, because TE-vs-TE is the whole
    // question. This break re-bases every TE regardless of which seat is open; the flex assertions
    // stay green, so only the dedicated-slot clause can catch it.
    detail: "Re-bases a TE onto the flex seat even when it is his own dedicated starter slot.",
    file: "lib/draft-optimizer.ts",
    from: "    if (needLevel(open, pos) !== 1) continue\n    let best = Infinity",
    to: "    if (needLevel(open, pos) === 0) continue\n    let best = Infinity",
    grep: "DEDICATED TE starter is untouched",
  },
  {
    id: "flex-urgency-uses-the-within-position-gap",
    shipped: "NF-C2.1 follow-up — pre-emptive, and DECLARED INERT ON THE PICK",
    // ⚠️ THIS IS THE HALF THAT MEASURED INERT, and recording that is the point. Reverting it changes
    // the top recommendation on 0 of 3,000 decision points on the served board — the flex bonus is
    // capped at a few VOR by `NEED_W_FLEX` and the gaps it competes with are far wider. A guard
    // written against a flipped PICK would therefore be a clause that cannot fail, so the assertion
    // is on the QUANTITY: the bonus must be paid on the gap over the flex pool (0.8 on the fixture),
    // not the gap to the next man at the position (1.6).
    detail: "Pays the flex need bonus on the within-position cliff, as it did before the change.",
    file: "lib/draft-optimizer.ts",
    from: "    const urgency = level === 1 ? flexPoolDropoff[p.pos] ?? dropoff : dropoff",
    to: "    const urgency = dropoff",
    grep: "gap over the FLEX POOL",
  },
  {
    id: "draft-grid-item-cannot-shrink",
    shipped: "NF-C2.1 follow-up — the horizontal scrollbar, reported on desktop",
    // ⚠️ NOT pre-emptive. This went out: a longer recommendation reason widened the whole draft
    // screen past `max-w-6xl`, gave the page a horizontal scrollbar and pushed the roster panel off
    // the right edge. Measured at 1512px before the fix: scrollWidth 2129.
    //
    // ⭐ THE TRAP IS THAT THE CODE LOOKED RIGHT. The rationale row already carried `min-w-0 flex-1`
    // and `truncate`, which is the usual answer — but a GRID item's automatic minimum is its
    // MIN-CONTENT width, `truncate` sets `white-space: nowrap`, and the min-content of nowrap text
    // is the entire sentence. `min-w-0` on the flex child removes the automatic minimum for FLEX
    // layout and does nothing to the grid track. Deleting one utility class from the grid ITEM is a
    // completely invisible edit that reproduces the whole bug.
    detail: "Removes min-w-0 from the grid item holding the recommendation panel.",
    file: "components/fantasy/mock-draft.tsx",
    from: '          <div className="flex min-w-0 flex-col gap-4">',
    to: '          <div className="flex flex-col gap-4">',
    grep: "never widens the page",
  },
  {
    id: "roster-panel-drops-the-bye-week",
    shipped: "NF-C2.1 follow-up — pre-emptive: the roster panel stops showing bye weeks",
    // The bye is the one roster fact a drafter cannot reconstruct from the board in front of them,
    // and it is a single optional chip in a row that renders perfectly well without it — which is
    // exactly the shape that gets dropped by a layout tidy-up and noticed by nobody.
    detail: "Renders the bye chip empty, exactly as a conditional render that stopped firing would.",
    file: "components/fantasy/mock-draft.tsx",
    from: "      {bye == null ? \"—\" : `BYE ${bye}`}",
    to: "      {null}",
    grep: "carries his bye week",
  },
  {
    id: "nfl-menu-groups-lose-their-labels",
    shipped: "NF-C2.1 follow-up — pre-emptive: the NFL menu falls back to one flat list",
    // Twelve items in one undifferentiated column is where it started, and a section whose label
    // goes null renders as an unheaded run of links that reads as a continuation of the group above
    // it — visually plausible, and wrong.
    detail: "Drops the Draft group's label, merging it into the group above.",
    file: "lib/nav-model.ts",
    from: '            label: "Draft",',
    to: "            label: null,",
    grep: "grouped by job",
  },
  {
    id: "nav-surface-suppression-eats-a-real-header",
    shipped: "NF-C2.1 follow-up — pre-emptive: the surface-header suppression widens by one word",
    // ⭐ THE OVER-CORRECTION. Suppressing the surface label when the surface has ANY labelled
    // section — instead of when it OPENS with one — reads as the same rule and deletes MLB's
    // "Betting" header, which is the only heading its first six items have. The NFL assertions stay
    // green throughout, so only the MLB control can catch it.
    detail: "Suppresses the surface label whenever any section is labelled, not just the first.",
    file: "components/nav.tsx",
    from: "!locked && visibleSurfaces(sport).length === 1 && !!firstVisibleSection?.label",
    to: "!locked && visibleSurfaces(sport).length === 1 && g.sections.some((s) => !!s.label)",
    grep: "grouped by job",
  },
  {
    id: "auction-strands-a-roster-spot",
    shipped: "NF-C5 — pre-emptive: the max bid lets a user spend down to an unfillable roster",
    // ⭐ THE ONE CORRECTNESS PROPERTY OF THE WHOLE TOOL. An empty starter slot scores zero, so a
    // bid that consumes the money the remaining spots need is not a trade-off — it is a wrong
    // answer, and it is invisible until the end of the auction when there is nothing to be done
    // about it. Dropping the reserve leaves every other number on screen looking entirely normal.
    detail: "Removes the reserve, so a single bid may consume every remaining dollar.",
    file: "lib/auction-optimizer.ts",
    from: "  const affordable = budget - minBid * (slots - 1)",
    to: "  const affordable = budget",
    grep: "strand a roster spot",
  },
  {
    id: "auction-opens-off-par",
    shipped: "NF-C5 — pre-emptive: the surplus is divided by the whole board, not the draftable set",
    // ⭐ THE DEFECT THIS STORY ACTUALLY SHIPPED AND CAUGHT. Money allocated to players nobody will
    // roster leaves the draftable set worth a fraction of the room, and the auction opens telling
    // every user that prices are ~2x value before a dollar is spent. Measured on the real board
    // fixture (722 above-replacement rows against 180 roster spots): 2.06x.
    //
    // ⚠️ NO UNIT OF ARITHMETIC ON A NORMALLY-SHAPED BOARD CAN SEE THIS — the eligible set and the
    // whole board coincide there. Only the face-validity check against a real payload can.
    detail: "Divides the surplus by every above-replacement row rather than the draftable set.",
    file: "lib/auction-optimizer.ts",
    from: "  const totalVor = draftable.reduce((a, i) => a + vals[i], 0)",
    to: "  const totalVor = vals.reduce((a, b) => a + b, 0)",
    grep: "prices at par",
  },
  {
    id: "auction-inflation-reads-backwards",
    shipped: "NF-C5 — pre-emptive: the inflation multiplier is inverted",
    // The direction is the entire signal, and inverting it is the single most plausible mistake in
    // the module: it turns "the room has overspent, what is left is cheap" into "prices are high",
    // and every max bid moves the wrong way with it. Every number on screen stays finite and
    // plausible, which is why a rendered-output scan cannot catch it and a directional test must.
    detail: "Inverts the multiplier, so an overpaying room reads as an expensive one.",
    file: "lib/auction-optimizer.ts",
    from: "    multiplier: valueRemaining > 0 ? dollars / valueRemaining : 1,",
    to: "    multiplier: valueRemaining > 0 ? valueRemaining / dollars : 1,",
    grep: "overpaying deflates",
  },
  {
    id: "auction-money-renders-as-zero",
    shipped: "NF-C5 — pre-emptive: a missing dollar value renders as $0 instead of an em-dash",
    // "We have no value for him" and "he is worth nothing" are different facts, and on an auction
    // board the second one is an instruction. A `$0` beside a player is a plausible-looking number
    // that nothing else on the page contradicts.
    detail: "Makes the shared money formatter coerce a null to $0.",
    file: "lib/auction-optimizer.ts",
    from: '  v == null || !Number.isFinite(v) ? "—" : `$${Math.round(v)}`',
    to: "  `$${Math.round(Number(v))}`",
    grep: "em-dash",
  },
  {
    id: "auction-sold-ignores-the-chosen-team",
    shipped: "NF-C5 — REAL, reported live 2026-08-17: every rival win was charged to one team",
    // ⭐ THE ACTUAL SHIPPED DEFECT, restored exactly: `Sold` hardcoded `myTeam === 1 ? 2 : 1`, so
    // the room panel was wrong AND — past that team's roster size — its extra buys became invisible
    // to `openSlots`, which is the denominator `inflation` divides by.
    //
    // ⚠️ The regression test uses TWO different rival teams on purpose. A single rival sale would
    // pass just as well against the hardcoded version, which is the fixture-cannot-fail shape.
    detail: "Ignores the team picked in the menu and charges the hardcoded one.",
    file: "components/fantasy/auction-optimizer.tsx",
    from: "            onSelect={() => onSell(b.team)}",
    to: "            onSelect={() => onSell(myTeam === 1 ? 2 : 1)}",
    grep: "charged to the team that actually won it",
  },
  {
    id: "auction-board-sold-ignores-the-typed-price",
    shipped: "NF-C5 — REAL, reported live 2026-08-17: the board could record WHO but not FOR HOW MUCH",
    // ⭐ THE ACTUAL SHIPPED DEFECT, restored exactly. The board table's "Sold" wrote a default and
    // there was no box to type in, so a nomination that is not on the shortlist — which is most of
    // a real auction — went into the ledger at the tool's own valuation rather than at its price.
    // Everything downstream of the money then drifts from the room: inflation, every max bid, and
    // every team's remaining. Nothing on screen looks wrong, which is why it survived a live run.
    detail: "Ignores the typed price and records the default.",
    file: "components/fantasy/auction-optimizer.tsx",
    from: "                                  sell(p.id, team, priceFor(p.id, defaultSalePrice(bid)))",
    to: "                                  sell(p.id, team, defaultSalePrice(bid))",
    grep: "recorded at what he actually sold for",
  },
  {
    id: "auction-board-win-ignores-the-typed-price",
    shipped: "NF-C5 — REAL, reported live 2026-08-17: the same gap on my own purchases",
    // The other button, and a SEPARATE code path — worth its own case because the two were fixed
    // together and could drift apart. Under-recording my own spend is the dangerous direction: it
    // leaves the tool believing I have money I do not, which is exactly how a roster spot ends up
    // unfundable at the end of an auction.
    detail: "Ignores the typed price on my own win and records the default.",
    file: "components/fantasy/auction-optimizer.tsx",
    from: "                                  sell(p.id, myTeam, priceFor(p.id, defaultSalePrice(bid)))",
    to: "                                  sell(p.id, myTeam, defaultSalePrice(bid))",
    grep: "charges my budget exactly what I typed",
  },
  {
    id: "auction-price-box-shows-what-it-does-not-write",
    shipped: "NF-C5 — pre-emptive: the price box's placeholder is not what a blank record writes",
    // ONE box sits between "I won" and "Sold", so the moment the two buttons default differently
    // the greyed-out figure is right for at most one of them — an input that displays one number
    // and writes another, with no error and nothing on screen to contradict it. `maxBid` is the
    // plausible wrong choice (it is what the column beside it shows).
    //
    // ⚠️ Only visible once money has been spent: with a full budget the affordability cap is inert
    // and the two numbers coincide, which is why the test drains the budget first.
    detail: "Shows the max bid in the box while a blank record writes his value at today's prices.",
    file: "components/fantasy/auction-optimizer.tsx",
    from: "                                placeholder={String(defaultSalePrice(bid))}",
    to: "                                placeholder={String(bid.maxBid)}",
    grep: "records the number the box was showing",
  },
  {
    id: "auction-board-keeps-its-own-price-ledger",
    shipped: "NF-C5 — pre-emptive: the board and the shortlist keep two prices for one player",
    // The E9.61 two-renderers rule on the number a user TYPES. A price is a fact about a player,
    // so a second ledger keyed per-surface means typing $3 in one place and clicking the button in
    // the other records something never entered — and the player appears on both surfaces at once.
    detail: "Keys the board's price box per-surface, so the shortlist never sees what was typed.",
    file: "components/fantasy/auction-optimizer.tsx",
    from: "                                  setPrices((prev) => ({ ...prev, [p.id]: e.target.value }))",
    to: '                                  setPrices((prev) => ({ ...prev, ["board:" + p.id]: e.target.value }))',
    grep: "share ONE price box",
  },
  {
    id: "auction-quotes-the-interval-in-dollars",
    shipped: "NF-C5 — REAL, reported live 2026-08-17: every player's value band bottomed at $1",
    // ⭐ THE SECOND SHIPPED DEFECT, restored at the point it becomes visible. The board published a
    // dollar band priced off the projection's points interval; on the served 2026 board the low
    // edge was $1 for ALL 870 rows and the high edges summed to 412% of the money in the room — a
    // figure nobody can spend is not a price. The cause is structural: a dollar is a SHARE of a
    // fixed pool, so a quantile priced through a rate belonging to another world is not on the
    // dollar scale, and neither a narrower quantile nor a common-quantile world repairs it (the
    // latter is not even ordered — measured). Putting a `$` back in front of the two numbers is
    // exactly the claim that was withdrawn.
    detail: "Re-quotes the projection's points interval as a dollar range.",
    file: "lib/auction-optimizer.ts",
    from: "  return lo === hi ? `${lo} pts` : `${lo}–${hi} pts`",
    to: "  return lo === hi ? `$${lo}` : `$${lo}–$${hi}`",
    grep: "quoted in points",
  },

  // ══ NF-C4 — the custom big board ══════════════════════════════════════════════════════════════
  //
  // Every case here is a defect that ships past `tsc` and `next build`: the page renders, the
  // numbers are right, and the feature quietly does not work.
  {
    id: "drag-never-commits",
    shipped: "NF-C4 — pre-emptive: the reorder that looks like it worked and did not",
    // ⭐ THE MOST LIKELY WAY THIS FEATURE BREAKS, and the least visible. A pointer drag that never
    // reaches its commit leaves the row exactly where it was — no error, no console warning, and a
    // cursor that moved. The E2E harness produced this exact symptom once for an unrelated reason
    // (`boundingBox()` is viewport-relative and does not scroll, so every event landed outside the
    // 720px viewport), which is precisely why the assertion has to be the ORDER and not "a pointer
    // event was dispatched".
    detail: "The drag's move handler bails before it can reorder, so the board never changes.",
    file: "components/fantasy/big-board.tsx",
    from: "      if (!el) return",
    to: "      if (el) return",
    grep: "vs-us column",
  },
  {
    id: "save-reports-success-before-the-server-answers",
    shipped: "NF-C4 — pre-emptive: E8.6's silent-save class, on a draft-day board",
    // ⭐ THE ONE THAT COSTS A USER THEIR DRAFT. An optimistic "✓ Saved" is the natural way to write
    // this and it makes a REFUSED save indistinguishable from a stored one — the user closes the
    // tab believing their board is safe. The refusal a real user meets is the shared 400 KB item
    // budget, which answers 413; nothing else in the product would contradict a wrong "Saved".
    detail: "Reports success without awaiting the write, so a refusal still renders as saved.",
    file: "components/fantasy/big-board.tsx",
    from: "      const saved = await saveBoard.mutateAsync({ ...doc, config: configName, size })",
    to: "      void saveBoard.mutateAsync({ ...doc, config: configName, size }).catch(() => {})",
    grep: "SERVER's explanation",
  },
  {
    id: "save-error-loses-the-servers-sentence",
    shipped: "NF-C4 — pre-emptive: a precise explanation replaced by a generic one",
    // The refusal's whole value is that it says NOTHING WAS CHANGED — that is what turns "saving is
    // broken" into "delete a board you no longer need". `apiFetch` goes to the trouble of preserving
    // FastAPI's `detail` for exactly this; discarding it at the last step is the `lib/api.ts` lesson
    // repeated one layer out.
    detail: "Swallows the API's `detail` behind a fixed string.",
    file: "components/fantasy/big-board.tsx",
    from: 'message: e instanceof Error && e.message ? e.message : "Could not save this board.",',
    to: 'message: "Could not save this board.",',
    grep: "SERVER's explanation",
  },
  {
    id: "failed-read-reads-as-an-empty-account",
    shipped: "E9.46's class — pre-emptive, and pointed at the user's OWN data",
    // "You have nothing saved for this board" is a confident statement about someone's work that a
    // 503 gives us no standing to make, and it is the message most likely to make them rebuild a
    // board that is sitting there intact. Falling through on a failed read is the natural way to
    // write the loader, and nothing else in the product would contradict the result.
    detail: "Loads an empty document on a failed read, so an outage renders as 'nothing saved'.",
    file: "components/fantasy/big-board.tsx",
    from: '    if (savedError) {\n      setSaveState({ kind: "unreadable" })\n      return\n    }',
    to: '    if (false) {\n      setSaveState({ kind: "unreadable" })\n      return\n    }',
    grep: "never says 'nothing saved'",
  },
  {
    id: "saved-board-loads-order-only",
    shipped: "NF-C4 — pre-emptive: two thirds of a saved board silently not restored",
    // ⚠️ THE SHAPE THAT PASSES THE OBVIOUS TEST. "Reorder, save, reload, the order is right" stays
    // green while the user's tier breaks and their target/avoid flags are gone — and a tag they set
    // in August is exactly the thing they will not re-check on draft night.
    detail: "Restores `order` and drops the tiers and tags.",
    file: "components/fantasy/big-board.tsx",
    from:
      "          order: stored.order ?? [],\n          tier_breaks: stored.tier_breaks ?? [],\n" +
      "          tags: stored.tags ?? {},",
    to: "          order: stored.order ?? [],\n          tier_breaks: [],\n          tags: {},",
    grep: "tiers and tags",
  },
  {
    id: "board-overflows-the-page-on-a-phone",
    shipped: "NF-C2.1 — the 2129px page, on the surface most likely to be read on a phone",
    // ⭐ THE HALF THAT IS ACTUALLY LOAD-BEARING. The row grid declares a 720px minimum, so without
    // its own scroll container that width reaches the document and the save bar leaves the screen.
    // ⚠️ Its sibling token `min-w-0` is NOT load-bearing today and the source guard says so
    // (`test_nf_c4_custom_big_board.py`): this container's parent is a block, so removing `min-w-0`
    // alone is measurably inert. Breaking the token that can be SEEN is what makes this a proof
    // rather than a restatement of the CSS.
    detail: "Removes the board's own horizontal scroll container.",
    file: "components/fantasy/big-board.tsx",
    from: 'className="min-w-0 overflow-x-auto rounded-lg border border-[#262626] bg-[#0f0f0f]"',
    to: 'className="min-w-0 rounded-lg border border-[#262626] bg-[#0f0f0f]"',
    grep: "inside its own container",
  },
  {
    id: "cheat-sheet-prints-our-numbers",
    shipped: "NF-C4 — pre-emptive: second-guessing the user at the pick",
    // The editing view exists to show our read beside theirs. The PRINTED sheet is read at 4.11,
    // away from any caveat, and a projection beside a ranking they deliberately overrode invites
    // them to re-litigate a decision they already made. The tier and the tag are the decisions.
    detail: "Puts our projection back on the printed sheet.",
    file: "components/fantasy/big-board.tsx",
    from: '                      <span className="truncate">{r.player.name}</span>',
    to: '                    <span className="truncate">{r.player.name} Proj {r.player.pts}</span>',
    grep: "none of our numbers",
  },

  // ── NF-C4 follow-up: the six defects the LIVE surface had that CI did not ────────────────────
  {
    id: "board-intro-loses-a-space",
    shipped: "NF-C4 — reported live: the page read \"our 2026board\"",
    // 🐛 A REAL, REPRODUCED COMPILER BEHAVIOUR, not a typo: the leading space of a JSX text node
    // that begins immediately after an expression is trimmed, so `{SEASON} board` renders as
    // "2026board". Measured in this harness — the JSX form fails this spec.
    detail: "Puts the season back beside JSX text instead of inside the string.",
    file: "components/fantasy/big-board.tsx",
    // ⚠️ THE WHOLE LINE, not its opening: a partial swap leaves the template literal's closing
    // backtick behind, the build fails to parse, and the case reports BUILD-CAUGHT — which
    // proves the compiler noticed, not that the SUITE would have.
    from:
      "            {`Start with our ${SEASON} board for your league, then make it your own. Drag players up or down, draw your own tier breaks, flag who you are chasing and who you are passing on, and write yourself a note on anyone. Our rank, our projection and the market's ADP stay next to every row, so you can always see where you have moved away from us.`}",
    to:
      "            Start with our {SEASON} board for your league, then make it your own. Drag players up or down, draw your own tier breaks, flag who you are chasing and who you are passing on, and write yourself a note on anyone. Our rank, our projection and the market&apos;s ADP stay next to every row, so you can always see where you have moved away from us.",
    grep: "spaces intact",
  },
  {
    id: "row-icons-explained-only-by-hover",
    shipped: "NF-C4 — reported live: nobody can read the scissors",
    // A star and a no-entry sign can be inferred. "Scissors = start a new tier here" cannot, and a
    // `title` is invisible on the phone where a draft board is actually read.
    detail: "Defines the icon legend and never mounts it.",
    file: "components/fantasy/big-board.tsx",
    from: "          <IconLegend />",
    to: "          {/* legend */}",
    grep: "in words, not only as a glyph",
  },
  {
    id: "sheet-invents-a-tier-1",
    shipped: "NF-C4 — reported live: every player printed under TIER 1",
    // With no breaks drawn, every player IS in tier 1 — so the heading was true and read as a
    // broken tiering. The fix is to stop claiming a tier the user never drew.
    detail: "Prints a TIER heading over a board with no tiers drawn.",
    file: "components/fantasy/big-board.tsx",
    from: "              {hasTiers && (",
    to: "              {true && (",
    grep: "never drew",
  },
  {
    id: "note-never-reaches-the-server",
    shipped: "NF-C4 — pre-emptive: a note that survives the session and nothing else",
    // The note renders, the save reports success, and the reload is empty — the silent-save shape
    // E8.6 exists for, one field over.
    detail: "Drops the notes from the save payload.",
    file: "components/fantasy/big-board.tsx",
    from: "      const saved = await saveBoard.mutateAsync({ ...doc, config: configName, size })",
    to: "      const saved = await saveBoard.mutateAsync({ ...doc, notes: {}, config: configName, size })",
    grep: "printed on the cheat sheet",
  },
  {
    id: "dropped-notes-reported-as-saved",
    shipped: "NF-C4 — pre-emptive: NF-C0 deploy skew on a field the backend ignores",
    // `frontend/` auto-deploys on merge; the API Lambda ships only via `deploy.sh`. The older
    // backend ACCEPTS `notes`, ignores them, returns 200 — and the user reads "✓ Saved".
    detail: "Trusts the 200 instead of comparing it with what was sent.",
    file: "components/fantasy/big-board.tsx",
    from: "      const keptNotes = Object.keys(saved?.notes ?? {}).length",
    to: "      const keptNotes = sentNotes",
    grep: "quietly dropped the notes",
  },
  {
    id: "player-link-navigates-away-from-unsaved-work",
    shipped: "NF-C4 — pre-emptive: a click that discards a curated board",
    // This surface holds unsaved work in component state, and a player card is exactly the thing
    // you glance at mid-edit.
    detail: "Opens the player page in the same tab.",
    file: "components/fantasy/big-board.tsx",
    from: '                            target="_blank"\n                            rel="noopener noreferrer"',
    to: "",
    grep: "opens in a new tab",
  },
  {
    id: "note-loses-every-space-typed",
    shipped: "NF-C4 — reported live: notes came out as one unreadable string",
    // 🐛 `setNote` runs on EVERY KEYSTROKE. Trimming there removes the space the user just typed
    // before the next character can follow it. ⚠️ The spec only reaches this with
    // `pressSequentially` — `fill()` sets the whole value in one event and is blind to it, which
    // is precisely why it shipped.
    detail: "Normalises the note on every keystroke.",
    file: "lib/big-board.ts",
    from: '  const raw = String(text ?? "").slice(0, MAX_NOTE_LEN)',
    to: '  const raw = String(text ?? "").trim().slice(0, MAX_NOTE_LEN)',
    grep: "KEEPS the spaces",
  },
  {
    id: "site-footer-prints-under-the-cheat-sheet",
    shipped: "NF-C4 — reported off a real printout: a page of dead nav links",
    // `SiteFooter` is mounted in the ROOT LAYOUT — a sibling of the page — so no class on the big
    // board can reach it. Asserted under a REAL print medium (`emulateMedia`), not by reading
    // class names.
    detail: "Breaks the selector that reaches the root-layout footer.",
    file: "app/globals.css",
    from: "  body:has([data-printable-surface]) footer {",
    to: "  body:has([data-printable-surface]) footer.never-matches {",
    grep: "cheat sheet and nothing else",
  },

  // ══ NF-C8 — the availability flag ═════════════════════════════════════════════════════════════
  //
  // ⭐ THESE TWO ARE HERE BECAUSE THE PYTHON SUITE STRUCTURALLY CANNOT SEE THEM.
  // `test_nf_c8_availability_flag_copy.py` proves the copy is honest and that all three surfaces
  // BIND the component — and every clause in it stays green for a classifier that flags EVERY row
  // or NONE of them. A flag on every row is decoration, not disclosure; a flag on no row is
  // indistinguishable from the defect the story exists to fix. Only a render can tell.
  {
    id: "availability-flags-everything",
    shipped: "NF-C8 — pre-emptive: a classifier that stops discriminating",
    detail:
      "Flags every row. The badge renders, the copy is honest, the Python suite is green — and the " +
      "colour now means nothing, because it is on all 858 rows.",
    file: "lib/fantasy.ts",
    from: '  if (games < LIMITED_AVAILABILITY_GAMES) return "limited"\n  return null',
    to: '  return "limited"',
    grep: "a materially-low games row is flagged and a full-season row is not",
  },
  {
    id: "availability-threshold-off-by-one",
    shipped: "NF-C8 — pre-emptive: the inclusive comparison",
    // The threshold is a design quantity and `<` vs `<=` is the classic silent slip. It is not
    // catchable by any source clause that pins the CONSTANT (14 is still 14), and on the captured
    // fixture — whose minimum `g` is 14 — it would flag a large slice of the board.
    detail: "`<=` instead of `<`, so a row AT a full-slate-minus-three flags when it should not.",
    file: "lib/fantasy.ts",
    from: "  if (games < LIMITED_AVAILABILITY_GAMES) return \"limited\"",
    to: "  if (games <= LIMITED_AVAILABILITY_GAMES) return \"limited\"",
    grep: "a materially-low games row is flagged and a full-season row is not",
  },
  {
    id: "availability-leaks-a-locked-row",
    shipped: "NF-C8 — pre-emptive: NF-LEAK1 on the games column",
    // E9.56's redaction strips `g` and renders a subscribe chip. A classifier that ignores `locked`
    // would flag whatever value reached it — disclosing the withheld figure's neighbourhood on
    // exactly the rows the server withheld it from, beside a chip saying it is withheld.
    detail: "Drops the `locked` guard, so a redacted row can still be flagged.",
    file: "lib/fantasy.ts",
    from: "  if (opts?.locked) return null",
    to: "  if (false) return null",
    grep: "a locked row is never flagged",
  },
  {
    id: "availability-chip-shows-a-fixed-number",
    shipped: "NF-C8 — pre-emptive: the badge that is not the player's own figure",
    // The badge IS the games number, so a chip carrying a constant renders perfectly and is wrong
    // on every row but one. `tsc` sees a string; the Python suite sees a component that renders.
    detail: "Renders a fixed games figure in the chip instead of the served per-player value.",
    file: "components/fantasy/shared.tsx",
    from: "  const value = num(games)",
    to: '  const value = "9.9"',
    grep: "a materially-low games row is flagged and a full-season row is not",
  },

  // ── NF-C9 — the weekly game-status designation ────────────────────────────────────────────────
  //
  // ⭐ SAME REASON AS THE FOUR ABOVE: `test_nf_c9_designation_disclosure.py` proves the copy is
  // honest and that all three surfaces BIND the component, and every clause in it stays green for a
  // component that renders on EVERY row, on NO row, or with the wrong value in the chip. This field
  // is a factual claim about a named person's game status, so "renders on every row" is not merely
  // decoration here — it asserts a designation for ~93% of players who carry none.
  {
    id: "designation-renders-on-every-row",
    shipped: "NF-C9 — pre-emptive: the disclosure that stops discriminating",
    detail:
      "Renders the chip whatever the payload says, so every undesignated player is shown as " +
      "carrying a game-status designation he does not have.",
    file: "components/fantasy/shared.tsx",
    from: "  if (status === undefined) return null",
    to: "  if (false) return null",
    grep: "each of the three states renders as itself",
  },
  {
    id: "designation-collapses-absent-into-unknown",
    shipped: "NF-C9 — pre-emptive: the NF-FRESH2 collapse, in the direction that shouts",
    // ABSENT means "nothing to disclose" — the normal state for ~93% of players. NULL means "the
    // feed said something we could not read". Treating them as one thing renders "unknown" under
    // almost every player on every board, which is the scary-word-everywhere failure the NF-C8
    // freshness note names, at board scale. `tsc` cannot see it: both are `undefined | null`.
    detail: "`status == null` instead of `status === undefined`, so an absent key says 'unknown'.",
    file: "components/fantasy/shared.tsx",
    from: "  if (status === undefined) return null",
    to: "  if (status === undefined || status === null) return null",
    grep: "each of the three states renders as itself",
  },
  {
    id: "designation-chip-shows-a-fixed-value",
    shipped: "NF-C9 — pre-emptive: the chip that is not this player's own designation",
    // The chip IS the designation, so a constant renders perfectly and is a false statement about
    // a named person on every row but one. The Python suite sees a component that renders.
    detail: "Renders a fixed designation instead of the served per-player value.",
    file: "components/fantasy/shared.tsx",
    from: "  const glyph = known == null ? WEEKLY_DESIGNATION_UNKNOWN : (WEEKLY_DESIGNATION_CODE[known] ?? known)",
    to: '  const glyph = "Q"',
    grep: "each of the three states renders as itself",
  },
  {
    id: "designation-unknown-loses-the-disclaimer",
    shipped: "NF-C9 — pre-emptive: the branch a reader has least to go on",
    // "unknown" with no statement about whether we priced it reads MORE like a model input than a
    // designation does. A component that hangs the disclaimer off the recognised branch looks
    // complete, and the Python clause that pins it had to be rewritten twice before it could see
    // this (see that suite's note on the preceding-character assertion).
    detail: "Hides the un-modelled disclaimer on the unreadable-value branch.",
    file: "components/fantasy/shared.tsx",
    from: '      <p className="mt-2">{WEEKLY_DESIGNATION_NOT_MODELLED}</p>',
    to: '      {known != null && <p className="mt-2">{WEEKLY_DESIGNATION_NOT_MODELLED}</p>}',
    grep: "still carries the disclaimer",
  },
  {
    id: "designation-nested-in-the-availability-branch",
    shipped: "NF-C9 — pre-emptive: the defect that would have skipped the motivating player",
    // ⭐⭐ THE ONE THAT MATTERS MOST. The designation and the availability flag are INDEPENDENT:
    // Jordyn Tyson, the row that produced NF-C8's finding, sat at 13.6 projected games — ABOVE the
    // flag threshold — so he carries a designation and NO flag. Nested inside the player page's
    // availability-tier branch, the disclosure renders only where the projection is ALREADY
    // discounted: i.e. never for the player it was written for. Every source clause about binding
    // and copy stays green.
    detail: "Moves the player page's designation inside its availability-tier branch.",
    file: "components/fantasy/player-page.tsx",
    from: "                    <span className=\"ml-1.5 normal-case\">\n" +
      "                      <WeeklyDesignation\n" +
      "                        status={proj.gameStatus}\n" +
      "                        freshness={projPayload?.freshness}\n" +
      "                      />\n" +
      "                    </span>",
    to: "                    {availabilityTier(proj.g) != null && (\n" +
      "                      <span className=\"ml-1.5 normal-case\">\n" +
      "                        <WeeklyDesignation\n" +
      "                          status={proj.gameStatus}\n" +
      "                          freshness={projPayload?.freshness}\n" +
      "                        />\n" +
      "                      </span>\n" +
      "                    )}",
    grep: "the player page discloses the same designation",
  },

  // ── NF-INJ1-C: the impossible stat line is withheld ─────────────────────────────────────────
  {
    id: "withheld-stat-renders-a-bare-em-dash",
    shipped: "NF-INJ1-C — pre-emptive: THE defect this whole spec exists to be able to see",
    // ⭐⭐ THE HIGHEST-VALUE CASE IN THIS GROUP, because the broken build looks IDENTICAL.
    // The server sends an ABSENT key, and the shipped table already renders an absent number as a
    // bare em-dash — so a build that ignores `statLineWithheld` prints "—" too. Same pixels, and
    // "we are deliberately not showing you this" silently becomes "we have nothing for this
    // player" (E9.56c, exactly). `tsc`, `next build`, every source scan and every Python clause in
    // this story stay green: the marker is still SENT, it is just not READ.
    detail: "Ignores the row's withheld marker, so the cells fall through to the plain em-dash.",
    file: "components/fantasy/projections-table.tsx",
    from:
      "                        {isStatWithheld(p.statLineWithheld, String(c.key)) ? (\n" +
      "                          <WithheldStat />\n" +
      "                        ) : (\n" +
      "                          numOrLock(p[c.key] as number | null, p.locked, c.nd ?? 1)\n" +
      "                        )}",
    to: "                        {numOrLock(p[c.key] as number | null, p.locked, c.nd ?? 1)}",
    grep: "the violating row is withheld and the clean row is untouched",
  },
  {
    id: "withheld-treatment-applied-to-every-row",
    shipped: "NF-INJ1-C — pre-emptive: the failure that costs a MEMBER the data they paid for",
    // The opposite miss, and the one with the larger blast radius. A treatment keyed on anything
    // broader than the row's own marker (a null check, a position check, a truthiness slip) blanks
    // the stat line across the paid surface — and it reads as a working feature, because the
    // disclosure it renders is perfectly correct copy. Only a NAMED clean row can see it.
    detail: "Applies the withheld treatment to every stat cell, not only the marked rows.",
    file: "components/fantasy/projections-table.tsx",
    from: "                        {isStatWithheld(p.statLineWithheld, String(c.key)) ? (",
    to: "                        {true ? (",
    grep: "the violating row is withheld and the clean row is untouched",
  },
  {
    id: "player-page-prints-the-impossible-line",
    shipped: "NF-INJ1-C — pre-emptive: a table-only fix, on the surface where it matters most",
    // The player page renders the stat line as TILES, a different code path from the table's
    // cells. It is also where the defect is most legible — the point total and the projected-games
    // figure sit side by side, so an impossible line here is one a reader can check at a glance.
    // A fix applied only to the table leaves exactly that page printing 82.7 attempts per game.
    detail: "Reverts the player page's tiles to printing the raw value.",
    file: "components/fantasy/player-page.tsx",
    from:
      "                        isStatWithheld(proj.statLineWithheld, String(c.key)) ? (\n" +
      "                          <WithheldStat />\n" +
      "                        ) : (\n" +
      "                          num(proj[c.key] as number | null, c.nd ?? 1)\n" +
      "                        )",
    to: "                        num(proj[c.key] as number | null, c.nd ?? 1)",
    grep: "the player page withholds the same line the table does",
  },
  {
    id: "withheld-disclosure-unreachable-on-touch",
    shipped: "NF-INJ1-C — pre-emptive: the disclosure a phone reader can never open",
    // ⚠️ THE CLAUSE THAT IS VACUOUS ON DESKTOP, so this case is only meaningful on the `mobile`
    // project — which is why the spec is registered there. A `title=` tooltip is the natural,
    // tidier-looking edit and it is unreachable on a phone: no hover, no long-press affordance. It
    // leaves an unexplained em-dash on a surface the reader has PAID for, which is worse than the
    // impossible number it replaced. Chromium cannot tell the two apart (`click()` fires
    // `pointerenter` first, so a hover-only disclosure opens before the click lands).
    detail: "Swaps the tap-reachable popover for a hover-only title attribute.",
    file: "components/fantasy/shared.tsx",
    // ⚠️ THE WHOLE COMPONENT BODY IS REPLACED, not wrapped. A partial edit here produces
    // unbalanced JSX and the case then fails at BUILD time — which reads as RED for a reason that
    // has nothing to do with the assertion, i.e. a case that "passes" while proving nothing about
    // the spec (the "a check whose two outcomes look identical is not a check" class).
    from:
      "    <InfoTip\n" +
      "      bare\n" +
      "      srLabel={STAT_LINE_WITHHELD_SR_LABEL}\n" +
      "      label={\n" +
      "        <span data-testid=\"withheld-stat\" className=\"cursor-help text-gray-500 underline decoration-dotted decoration-gray-700 underline-offset-4\">\n" +
      "          —\n" +
      "        </span>\n" +
      "      }\n" +
      "    >\n" +
      "      <p className=\"font-medium text-gray-300\">{STAT_LINE_WITHHELD_LABEL}</p>\n" +
      "      <p className=\"mt-1.5\">{STAT_LINE_WITHHELD_DETAIL}</p>\n" +
      "    </InfoTip>",
    to:
      "    <span\n" +
      "      data-testid=\"withheld-stat\"\n" +
      "      title={`${STAT_LINE_WITHHELD_LABEL} ${STAT_LINE_WITHHELD_DETAIL}`}\n" +
      "      aria-label={STAT_LINE_WITHHELD_SR_LABEL}\n" +
      "      className=\"cursor-help text-gray-500\"\n" +
      "    >\n" +
      "      —\n" +
      "    </span>",
    grep: "refuses every forecast reading",
  },
  {
    id: "withheld-label-claims-an-adjustment-we-did-not-make",
    shipped: "NF-INJ1-C — the label as it SHIPPED, before the PM reworded it",
    // ⭐⭐ NOT PRE-EMPTIVE — this string was live on the paid surface. It is not merely vague, it
    // is INVERTED: "availability-adjusted" says we adjusted this line for availability, when the
    // line is withheld PRECISELY BECAUSE it was not rescaled with the games. The decoupling is the
    // NF1.5 defect itself, so the label described the one thing that did not happen.
    //
    // ⚠️ THE REASON THIS CASE EARNS ITS PLACE: the reword was invisible to every pin that predated
    // it. The trigger's accessible name comes from a DIFFERENT constant, and "the disclosure says
    // it is withheld" is true of both strings — so this swap turns the suite green-to-green unless
    // the clause added with the reword is doing real work. This is the case that proves it is.
    detail: "Restores the retired 'availability-adjusted' label on the withheld-stat disclosure.",
    file: "lib/fantasy-claim-copy.ts",
    from: 'export const STAT_LINE_WITHHELD_LABEL = "stat detail withheld — inconsistent with projected games"',
    to: 'export const STAT_LINE_WITHHELD_LABEL = "stat detail withheld — availability-adjusted"',
    grep: "refuses every forecast reading",
  },
  {
    id: "quota-409-collapsed-at-the-fetch-boundary",
    shipped: "NF-DTB-1 — the free-league cap reported as a generic save failure",
    // ⭐⭐ THE ACTUAL SHIPPED DEFECT, restored at its actual location. `apiFetch` threw a BARE
    // `Error` and discarded `res.status`, so a 409 (the free-league cap, with a precise server
    // detail) was indistinguishable from a 400 at every call site — and both rendered through the
    // generic "Could not save. …" line. The user met a LIMIT and was told their save was broken,
    // with nothing naming the cap and no way past it (E8.6's shape, on a paywall).
    //
    // ⚠️ THIS IS THE ROOT BREAK, NOT A SURFACE ONE. With the status gone, `isLeagueQuotaRefusal`
    // returns false everywhere at once, so BOTH create paths regress from a single edit — which is
    // the point: it proves the specs are keyed on the boundary and not on a component-local flag.
    detail: "Reverts `apiFetch` to throwing a bare Error, discarding the HTTP status.",
    file: "lib/api.ts",
    from:
      "    throw new AuthError('Unauthorized')\n" +
      "  }\n" +
      "  if (!res.ok) throw new ApiError(res.status, await errorMessage(res))",
    to:
      "    throw new AuthError('Unauthorized')\n" +
      "  }\n" +
      "  if (!res.ok) throw new Error(await errorMessage(res))",
    grep: "reads as a LIMIT, not as a failure",
  },
  {
    id: "quota-notice-shown-for-every-save-failure",
    shipped: "NF-DTB-1 — the one-sided fix, i.e. the defect the FIX itself invites",
    // ⭐ THE OTHER HALF. The tempting cure for the case above is "show the quota notice whenever a
    // save errors", which passes every at-cap assertion and reports a genuine FAULT to the user as
    // a billing limit — worse than the bug, because it sends them to checkout for a server error.
    // The non-quota twin specs are what refuse it, and this case is what proves they can.
    detail: "Treats EVERY failed save as the quota refusal, not just a 409.",
    file: "lib/entitlements.ts",
    from: "export function isLeagueQuotaRefusal(e: unknown): boolean {\n  return apiErrorStatus(e) === 409\n}",
    to: "export function isLeagueQuotaRefusal(e: unknown): boolean {\n  return e instanceof Error\n}",
    grep: "reads as a LIMIT, not as a failure",
  },

]

/**
 * ⭐ E9.64b — THE RECORDED BOARD, and the reason this script is now SCHEDULED.
 *
 * ══ THE FAILURE THIS EXISTS TO CATCH ══════════════════════════════════════════════════════════
 *
 * E9.64's first full run found SIX pre-existing cases whose verdict no longer matched their
 * declaration — anchors that had drifted, and breaks whose data-flow had been retired underneath
 * them. None was introduced by that story; they had simply gone dead at some point and nobody was
 * looking, because **nothing ran this script**. It was a manual command, so its only trigger was a
 * session remembering to type it, and a red-proof harness nobody runs is decorative — which is the
 * exact defect it exists to prevent, one level up.
 *
 * So the board's shape is RECORDED here and the run FAILS when the shape moves. That turns
 * "somebody should re-run the red proof" into a scheduled job with a verdict.
 *
 * ⚠️ WHAT A DRIFT MEANS, AND WHAT IT DOES NOT. This number changing is not automatically a bug —
 * adding a guard SHOULD add a case. The rule is that the two move TOGETHER, in the same commit: a
 * new case comes with an updated total, so the only way this fires unexpectedly is a case that
 * stopped behaving as declared. ⛔ Do not "fix" a drift by editing these numbers to match the
 * output; read the summary first — a case that flipped from RED to MISMATCH is a guard that has
 * quietly become decorative, and it is the finding.
 *
 * Last FULL measurement 2026-08-14 (ESPN-PRUNER): 107 cases, 101 RED, 6 NOT-OBSERVABLE, exit 0.
 * Previously (E9.64b): 106 / 100 / 6. (E9.64): 95 / 89 / 6.
 *
 * ⚠️ THE CURRENT NUMBERS ARE DERIVED, NOT MEASURED, and saying so is the point. NF-C6P2 added SIX
 * cases and RED-proved each ONE AT A TIME (`--` by id), which is a real verdict per case; it did not
 * re-run the whole board, because 113 cases × a production build each is an hour-plus job and does
 * not belong in a session. So 113/107/6 is 107/101/6 plus six individually-proven REDs — and the
 * next full run is what CONFIRMS it. ⛔ A projection is not a measurement: if that run disagrees,
 * the finding is whatever drifted, never this line (see the ⛔ note above).
 *
 * Additionally verified without a full run: all 114 anchors resolve against the current tree, so no
 * case is STALE.
 *
 * 🪤 AND A WARNING PAID FOR IN THIS SESSION: a full run KILLED mid-flight (a timeout, ^C, anything
 * that does not let the exit trap finish) leaves the case file it was on MUTATED in the working
 * tree. It surfaced here as `app/fantasy/draft/page.tsx` sitting in the `paid-half-un-gated` broken
 * state — i.e. the Draft Optimizer publicly guarded — which reads exactly like a live entitlement
 * hole rather than like test residue. `git status` before believing it, and `git checkout --` the
 * file. (Nothing reached a commit: staging by explicit path rather than `git add -A` is what kept
 * it out.)
 */
// NF-C6P3 adds SIX cases in total (three in (a), three in (b)), each RED-proven individually (`-- <id>`) rather than by a full board
// run, for the same reason NF-C6P2 recorded: 120 cases × a production build each does not belong in
// a session. So 120/114/6 is 114/108/6 plus six individually-proven REDs, and the next full run is
// what CONFIRMS it. ⛔ A projection is not a measurement — if that run disagrees, the finding is
// whatever drifted, never this line.
// E5.10 adds FIVE cases (default sort, team-chip filter, name search, non-slate-sort ordering,
// sportsbook filter — the last a follow-up request in the same story), each RED-proven
// individually (`-- props-`) for the same reason — a production build per case does not belong
// in a session. So 120/114/6 → 125/119/6, and the next full run CONFIRMS it.
// G100-C2 adds ONE case (the multi-league picker reverting to `teams[0]`), RED-proven individually
// (`-- league-picker`) for the same reason. So 125/119/6 → 126/120/6, and the next full run CONFIRMS
// it.
// NF-C5's follow-ups add FIVE cases in total — four for the board price box, one for the retired
// dollar band — each RED-proven individually (`-- auction-board`, `-- auction-price-box`,
// `-- auction-quotes`) for the same reason every entry above records: a production build per case
// does not belong in a session. So 137/131/6 → 142/136/6, and the next full run CONFIRMS it.
// ⛔ A projection is not a measurement.
const RECORDED_BOARD = { total: 169, red: 163, notObservable: 6 }

// argv[2] is the case-id filter; flags (`--force`) must not be mistaken for one.
const filter = process.argv.slice(2).find((a) => !a.startsWith("-"))
const selected = filter ? CASES.filter((c) => c.id.includes(filter)) : CASES
if (!selected.length) {
  console.error(`no case matching "${filter}". ids: ${CASES.map((c) => c.id).join(", ")}`)
  process.exit(2)
}

/**
 * ⚠️⚠️ COMMIT FIRST. `restoreAll` below is a `git checkout --`, i.e. it restores every case
 * file from HEAD — so any UNCOMMITTED edit to one of them is destroyed, silently, on exit.
 * That is not hypothetical: it ate a session's in-progress `app/subscribe/page.tsx` while
 * red-proving E9.59's own new case (2026-08-07). The per-case `writeFileSync(path, original)`
 * restore is correct; the exit trap is the belt-and-braces path for a crash, and it can only
 * reach for HEAD.
 *
 * So refuse to start on a dirty case file rather than eating it. `--force` is available for
 * the deliberate "I know, my work is stashed" case.
 */
function assertCaseFilesAreCommitted() {
  if (process.argv.includes("--force")) return
  const dirty = execFileSync("git", ["status", "--porcelain", "--", ...new Set(CASES.map((c) => c.file))], {
    cwd: FRONTEND,
    encoding: "utf8",
  }).trim()
  if (!dirty) return
  console.error(
    "⛔ red-proof rewrites these files and restores them from HEAD on exit, which would DESTROY " +
      "your uncommitted work in:\n" +
      dirty +
      "\n\nCommit (or stash) first, then re-run. `--force` overrides.",
  )
  process.exit(2)
}

function restoreAll() {
  for (const c of CASES) {
    try {
      execFileSync("git", ["checkout", "--", c.file], { cwd: FRONTEND })
    } catch {
      /* nothing to restore */
    }
  }
}
assertCaseFilesAreCommitted()
process.on("exit", restoreAll)
process.on("SIGINT", () => process.exit(130))

const run = (cmd, args) =>
  spawnSync(cmd, args, { cwd: FRONTEND, stdio: "pipe", encoding: "utf8", shell: false })

const results = []

for (const c of selected) {
  const path = join(FRONTEND, c.file)
  const original = readFileSync(path, "utf8")
  if (!original.includes(c.from)) {
    console.log(`SKIP  ${c.id} — anchor not found in ${c.file} (the source moved; update the case)`)
    results.push({ id: c.id, verdict: "STALE" })
    continue
  }

  process.stdout.write(`\n▶ ${c.id}\n  breaking: ${c.shipped}\n  building… `)
  writeFileSync(path, original.replace(c.from, c.to))

  const build = run("npm", ["run", "e2e:build"])
  if (build.status !== 0) {
    // A break that does not compile proves nothing about the E2E suite — `tsc`/the build caught it,
    // which is a different (and welcome) gate. Say so rather than counting it as a pass, and PRINT
    // the tail: a transient build failure and a genuinely-uncompilable break look identical from
    // the exit code alone, and mislabelling one as the other is how a missed case hides.
    console.log("BUILD FAILED — either the build caught this defect, or the build itself flaked:")
    console.log(
      [build.stdout, build.stderr].join("\n").trim().split("\n").slice(-15).join("\n"),
    )
    writeFileSync(path, original)
    results.push({ id: c.id, verdict: "BUILD-CAUGHT" })
    continue
  }

  process.stdout.write("running… ")
  const test = run("npx", ["playwright", "test", "--reporter=line", "--grep", c.grep])
  writeFileSync(path, original)

  const red = test.status !== 0
  const wanted = c.expect ?? "RED"
  const observed = red ? "RED" : "GREEN"
  const ok = observed === wanted

  if (wanted === "GREEN") {
    // A case DECLARED green asserts the opposite property: this defect is genuinely not
    // DOM-observable, and saying so is a finding. If it ever goes red, the boundary moved and the
    // note on the case is now wrong — which is a failure worth surfacing, not a quiet upgrade.
    console.log(
      ok
        ? "GREEN ✅ (declared not-observable — see the case note)"
        : "RED ❌ (declared not-observable, but the suite caught it — the note is now stale)",
    )
  } else {
    console.log(ok ? "RED ✅ (the suite caught it)" : "GREEN ❌ (THE SUITE MISSED IT)")
    if (!ok) console.log(test.stdout.split("\n").slice(-12).join("\n"))
  }
  results.push({ id: c.id, verdict: ok ? (wanted === "GREEN" ? "NOT-OBSERVABLE" : "RED") : "MISMATCH" })
}

// Rebuild clean so the tree is left in a runnable state.
process.stdout.write("\nrestoring clean build… ")
console.log(run("npm", ["run", "e2e:build"]).status === 0 ? "ok" : "FAILED")

console.log("\n── red-proof summary ─────────────────────────────")
for (const r of results) console.log(`  ${r.verdict.padEnd(12)} ${r.id}`)
const bad = results.filter((r) => r.verdict !== "RED" && r.verdict !== "NOT-OBSERVABLE")
if (bad.length) {
  console.log(
    `\n${bad.length} case(s) did not match their declared expectation. The suite is not proving what it claims.`,
  )
  process.exitCode = 1
}

// ── the recorded board ──────────────────────────────────────────────────────────────────────────
//
// Only meaningful for a FULL run: a filtered invocation is a debugging tool and its counts describe
// whatever the operator asked for, not the board. Reporting drift there would train everyone to
// ignore this line, which is how a monitor gets muted.
if (!filter) {
  const observed = {
    total: results.length,
    red: results.filter((r) => r.verdict === "RED").length,
    notObservable: results.filter((r) => r.verdict === "NOT-OBSERVABLE").length,
  }
  const drifted = Object.keys(RECORDED_BOARD).filter((k) => observed[k] !== RECORDED_BOARD[k])
  const shape = (b) => `${b.total} cases, ${b.red} RED, ${b.notObservable} NOT-OBSERVABLE`
  if (drifted.length) {
    console.log(
      `\n⚠️  BOARD DRIFT — recorded: ${shape(RECORDED_BOARD)}\n` +
        `                observed: ${shape(observed)}\n` +
        `                moved:    ${drifted.join(", ")}\n\n` +
        "If you ADDED or REMOVED a case, update RECORDED_BOARD in the same commit — the two are\n" +
        "meant to move together. If you did not, a case has stopped behaving as declared: read the\n" +
        "summary above and repair the case. ⛔ Never edit RECORDED_BOARD to match a drift you did\n" +
        "not cause — that is how a guard becomes decorative.",
    )
    process.exitCode = 1
  } else {
    console.log(`\nboard matches the record — ${shape(observed)}`)
  }
}
