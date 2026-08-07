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
    detail: "Drops the fantasy vertical, leaving a betting-only home page.",
    file: "lib/home-copy.ts",
    from: '    key: "fantasy",',
    to: '    key: "fantasy-disabled",',
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
    detail: "Removes the demonstration-not-recommendation frame from the live block.",
    file: "lib/home-copy.ts",
    from: '    "This is a demonstration, not a recommendation. Of today',
    to: '    "Of today',
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
  {
    id: "home-blog-back-in-primary-nav",
    shipped: "E9.46 — the pre-story nav, where the blog sat beside the products",
    detail: "Restores the blog as a primary-nav link (operator decision 3 reverses this).",
    file: "components/nav.tsx",
    from: '            href="/about"\n            className="hidden text-xs text-gray-500 hover:text-gray-300 transition-colors sm:block"',
    to: '            href="/blog"\n            className="hidden text-xs text-gray-500 hover:text-gray-300 transition-colors sm:block"',
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
]

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
