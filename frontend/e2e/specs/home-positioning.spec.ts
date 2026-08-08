import { expect, test, type Locator, type Page } from "@playwright/test"
import { collectPageErrors, FIXTURES, mockApi } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"

/**
 * E9.46 — the HOME PAGE as the company's positioning surface.
 *
 * ══ WHAT THIS FILE IS WRITTEN FROM ════════════════════════════════════════════════════════════
 *
 * The home page is the only surface in the product where both verticals pitch at once, and it is
 * the one a stranger meets first. Three failures live here and nothing else in the toolchain can
 * see any of them:
 *
 *   1. ⭐ A SINGLE-VERTICAL HOME PAGE. The pre-E9.46 page led with "Daily edge, quantified" and an
 *      MLB pick card; a visitor arriving for fantasy had to infer they were in the right place.
 *      `tsc` and `next build` are entirely blind to "this page reads as one product" — only a
 *      rendered check that BOTH doors are present and BOTH are reachable can hold it.
 *
 *   2. ⭐ A TOUT. `best_alpha = 0`: six recorded no-edge results, and the fantasy record's own 90%
 *      interval includes zero. A featured pick on a marketing page is one word from claiming an
 *      advantage neither vertical has. `test_e9_46_home_copy.py` screens the copy MODULE; only
 *      this file can scan the RENDERED document, which also carries every heading, badge, CTA
 *      label and empty state that no export-side denylist has ever read.
 *
 *   3. ⭐ A BLANK HERO ON AN EMPTY READ. The live element is a network call, and the E9.26b
 *      lesson is that a swallowed failure renders as nothing at all while every status code stays
 *      green. Three payload states are exercised below — populated, published-nothing, and
 *      read-failed — and all three must leave a page with its positioning intact.
 *
 * ⚠️ THE FIXTURE'S CONTENT CHANGES EVERY DAY. `picks-featured.json` is whichever game currently
 * has the widest model-vs-market gap, so every assertion here reads the payload's OWN values
 * rather than a literal. A spec pinned to "CIN @ WSH" would go red on a re-capture and teach
 * everyone to re-capture less often.
 */

const PICK = FIXTURES.featuredPick() as {
  game_pk: number | null
  matchup: string
  edge: number
  model_prob: number
  market_prob: number
  yesterday: { matchup: string; outcome: string } | null
}

/** Vertical position of an element's box — the honest form of "appears before" on a page. */
async function topOf(locator: Locator): Promise<number> {
  const box = await locator.first().boundingBox()
  expect(box, "element is not laid out, so its position cannot be compared").not.toBeNull()
  return box!.y
}

async function renderedText(page: Page): Promise<string> {
  return (await page.locator("body").innerText()).replace(/\s+/g, " ")
}

/**
 * Load the home page and wait for the live block to SETTLE.
 *
 * ⚠️ The NF-TR1 lesson, applied here before it can cost a CI run: `body.innerText` is a SNAPSHOT,
 * and the pick arrives over an async fetch. Scanning straight after `goto` can capture the loading
 * skeleton — in which the pick's numbers are legitimately absent — and report a product defect
 * when the fetch was merely late. Every state below renders one of four known terminal strings, so
 * waiting on "any of them is visible" is a wait on the block having resolved, not on the answer.
 */
async function gotoHome(page: Page) {
  await page.goto("/")
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  await expect(
    page
      .locator("#today")
      .getByText(/Our model leans|Nothing to show yet|could not be loaded|still processing/),
  ).toBeVisible()
}

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 1 — the page positions Credence across BOTH verticals, with a first-class door to each
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("both verticals get a first-class door, and both doors go somewhere", async ({ page }) => {
  const errors = collectPageErrors(page)
  const mock = await mockApi(page)
  await gotoHome(page)

  const text = await renderedText(page)
  // The identity claim: a visitor must be able to tell this covers both products without
  // scrolling into the detail. Both sport labels and both surface names render in the hero.
  expect(text).toContain("MLB")
  expect(text).toContain("NFL")
  expect(text).toMatch(/Betting intelligence/i)
  expect(text).toMatch(/Fantasy/i)

  // ⭐ THE LOAD-BEARING HALF. A page can NAME both products and still offer a door to only one —
  // which is the pre-E9.46 state almost exactly. Require a working entry point per vertical.
  //
  // ⚠️ SCOPED TO THE VERTICAL CARDS BY `data-vertical`, and that is a correction rather than a
  // style choice. The first cut located each door by its LINK TEXT, and the red-proof case that
  // deletes the fantasy vertical stayed GREEN — because `DISAGREEMENT_HOOK`'s block further down
  // the page links to the same route with a near-identical label, so it silently stood in for the
  // hero card. A locator that another element can satisfy is not testing the element it names.
  const fantasyCard = page.locator('[data-vertical="fantasy"]')
  await expect(fantasyCard, "the fantasy vertical has no card in the hero").toBeVisible()
  const fantasyDoor = fantasyCard.getByRole("link", { name: /free rankings/i })
  await expect(fantasyDoor, "no entry point into the fantasy product").toBeVisible()
  expect(await fantasyDoor.getAttribute("href")).toBe("/fantasy/rankings")

  const bettingCard = page.locator('[data-vertical="betting"]')
  await expect(bettingCard, "the betting vertical has no card in the hero").toBeVisible()
  const bettingDoor = bettingCard.getByRole("link", { name: /model-vs-market read/i })
  await expect(bettingDoor, "no entry point into the betting product").toBeVisible()

  // ⚠️ The betting CTA and the section it targets are two string literals in two files
  // (`home-copy.ts`'s `#today` and the component's `id="today"`), so nothing type-checks the
  // pairing. Prove it by navigating: click it and require the live section to be what we reach.
  await bettingDoor.click()
  await expect(page.locator("#today")).toBeInViewport()

  expectApiFullyMocked(mock)
  await expectNoNaN(page)
  expectNoPageErrors(errors)
})

test("neither door is buried — both render above the fold of the page's own hero", async ({
  page,
}) => {
  // A "first-class door to each" is a LAYOUT claim, and the failure mode is a page that carries
  // the fantasy card three screens below an MLB pick. Assert the two cards sit level with each
  // other, which a primary/secondary split cannot satisfy.
  await mockApi(page)
  await gotoHome(page)

  // Same scoping rule as above — the cards themselves, not a link label another block can supply.
  const bettingTop = await topOf(page.locator('[data-vertical="betting"]'))
  const fantasyTop = await topOf(page.locator('[data-vertical="fantasy"]'))
  const liveBlockTop = await topOf(page.locator("#today"))

  expect(
    Math.abs(bettingTop - fantasyTop),
    "the two vertical doors are not peers — one is stacked well below the other",
  ).toBeLessThan(400)
  expect(
    Math.max(bettingTop, fantasyTop),
    "a vertical door renders below the live pick block, i.e. below the fold of the positioning",
  ).toBeLessThan(liveBlockTop)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 2 — the pick of the day is a TRANSPARENCY feature, and it never leaves the page blank
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("the live block renders the served model-vs-market read, framed as a demonstration", async ({
  page,
}) => {
  const errors = collectPageErrors(page)
  const mock = await mockApi(page)
  await gotoHome(page)

  const block = page.locator("#today")

  // ⭐ FOLLOWS THE SERVER. The E9.59 lesson: "a number renders" and "THE number renders" are
  // different assertions, and only the second can tell a live read from a hardcoded mock-up.
  // `model_prob` is P(home) / P(over); below 0.5 the lean is the other side, so the page shows
  // the complement — assert whichever one the payload implies.
  const shown = PICK.model_prob < 0.5 ? 1 - PICK.model_prob : PICK.model_prob
  await expect(block.getByText(`${(shown * 100).toFixed(1)}%`).first()).toBeVisible()
  await expect(block.getByText(PICK.matchup)).toBeVisible()
  await expect(block.getByText(`+${Math.abs(PICK.edge).toFixed(1)} pts`)).toBeVisible()

  // ⛔ THE FRAMING IS NOT OPTIONAL, and it must arrive WITH the numbers rather than under them —
  // a visitor reads the big figure first. Without this the block is a tout, which is the single
  // most damaging thing this page could ship.
  await expect(block.getByText(/demonstration, not a recommendation/i)).toBeVisible()
  expect(
    await topOf(block.getByText(/demonstration, not a recommendation/i)),
    "the framing renders below the numbers it is supposed to frame",
  ).toBeLessThan(await topOf(block.getByText(PICK.matchup)))

  // ⛔ NO SERVED PROSE. `ai_summary` and `model_narrative` are model-generated, unversioned, and
  // use "edge" freely — the live payload on capture day says "a +3.2pp edge over the Bovada
  // closing line". If either ever reaches this page, the denylist scan below is asserting against
  // a string the API can change underneath it, so the absence is pinned explicitly.
  const text = await renderedText(page)
  expect(text, "the home page is rendering served model prose").not.toContain("The top factors")
  expect(text).not.toMatch(/pp edge/i)

  // The public half of the honest record: yesterday's graded result, win or loss, with no account.
  if (PICK.yesterday) {
    await expect(block.getByText(PICK.yesterday.matchup)).toBeVisible()
    await expect(block.getByText(PICK.yesterday.outcome, { exact: false }).first()).toBeVisible()
  }

  expectApiFullyMocked(mock)
  await expectNoNaN(page)
  expectNoPageErrors(errors)
})

test("a slate with nothing published says so, and the positioning survives it", async ({ page }) => {
  const errors = collectPageErrors(page)
  const mock = await mockApi(page, {
    // The real shape of "the model published nothing today" — `/picks/featured` answers 200 with
    // a null `game_pk`. It is a routine state, not an error.
    transform: (path, body) => (path === "/picks/featured" ? { ...body, game_pk: null } : body),
  })
  await gotoHome(page)

  await expect(page.locator("#today").getByText(/Nothing to show yet/i)).toBeVisible()
  // ⭐ AND THE HERO IS UNTOUCHED. The AC is that an empty read never blanks the page; a block that
  // merely vanished would pass any "the empty message is absent" check and fail the user.
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  await expect(page.getByRole("link", { name: /free rankings/i }).first()).toBeVisible()
  await expect(page.getByRole("link", { name: /model-vs-market read/i }).first()).toBeVisible()

  expectApiFullyMocked(mock)
  expectNoPageErrors(errors)
})

test("a FAILED read is reported as ours, not as an empty slate", async ({ page }) => {
  // ⭐ THE DISTINCTION IS THE POINT. "The model published nothing" and "this page could not reach
  // the model" are different facts, and a page that shows the first message on the second event is
  // stating a falsehood about the model. Nothing but a failing read can tell the two apart.
  const errors = collectPageErrors(page)
  const mock = await mockApi(page, { fail: ["/picks/featured"] })
  await gotoHome(page)

  const block = page.locator("#today")
  await expect(block.getByText(/could not be loaded/i)).toBeVisible()
  await expect(
    block.getByText(/Nothing to show yet/i),
    "a failed read is being reported as an empty slate",
  ).toHaveCount(0)

  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  await expect(page.getByRole("link", { name: /free rankings/i }).first()).toBeVisible()

  expectApiFullyMocked(mock)
  expectNoPageErrors(errors)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 3 — the trust links, for BOTH verticals
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("both verticals link to an honest record, and the gated one says it is gated", async ({
  page,
}) => {
  await mockApi(page)
  await gotoHome(page)

  const fantasyTrust = page.getByRole("link", { name: /See the track record/i }).first()
  await expect(fantasyTrust).toBeVisible()
  expect(await fantasyTrust.getAttribute("href")).toBe("/fantasy/track-record")

  const mlbTrust = page.getByRole("link", { name: /graded out/i }).first()
  await expect(mlbTrust).toBeVisible()
  expect(await mlbTrust.getAttribute("href")).toBe("/performance")

  // ⭐ THE ASYMMETRY MUST BE VISIBLE. `/fantasy/track-record` is genuinely public;
  // `/performance` is behind the auth guard. Sending a stranger from a TRUST link into a login
  // wall unannounced is the one surprise a trust link cannot afford, so the free one is labelled
  // free — and this assertion is what stops a later edit from quietly levelling the two.
  await expect(page.getByText(/free, no account/i).first()).toBeVisible()
})

test("the trust link reaches a Track Record page that actually renders", async ({ page }) => {
  // A SOURCE scan sees the binding, never the destination — the E9.56c dead-CTA class. Only
  // navigation can tell a bound link from a working one.
  await mockApi(page)
  await gotoHome(page)

  await page.getByRole("link", { name: /See the track record/i }).first().click()
  await expect(page).toHaveURL(/\/fantasy\/track-record/)
  await expect(page.getByText("The honest read")).toBeVisible()
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 4 — the claim discipline, over the WHOLE rendered document
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("the rendered home page makes no forbidden market or edge claim", async ({ page }) => {
  await mockApi(page)
  await gotoHome(page)

  // Open the FAQ accordions: a denied phrase inside a collapsed panel still ships. The landing
  // FAQ is seven paragraphs of claim-bearing prose and is exactly where one would hide.
  for (const trigger of await page.locator("button[data-slot='accordion-trigger']").all()) {
    await trigger.click()
  }

  const hits = forbiddenPhrasesIn(await renderedText(page))
  expect(hits, `the home page renders forbidden claim language: ${hits.join(", ")}`).toEqual([])
})

test("the page never presents the model's read as a bet to place", async ({ page }) => {
  // The denylist catches the crude forms. This catches the IMPERATIVE — the shape a featured pick
  // slides into without tripping any banned phrase, and the shape that would contradict
  // `best_alpha = 0` on the company's own front door.
  await mockApi(page)
  await gotoHome(page)

  const text = await renderedText(page)
  for (const imperative of [
    /\bbet (this|today|now)\b/i,
    /\bplay of the day\b/i,
    /\block of the\b/i,
    /\btoday'?s best bet\b/i,
    /\bpicks that win\b/i,
  ]) {
    expect(text, `the page tells a visitor to place a bet: ${imperative}`).not.toMatch(imperative)
  }

  // And the positive half: inside the live block the quantity is named as a DIFFERENCE, not as an
  // advantage we hold. ⚠️ Scoped to `#today` and asserted in both directions — a page-wide
  // `/\bgap\b/i` is satisfied by the framing prose ("we show both numbers, the gap"), so it would
  // pass with the stat label reverted to "Edge". The absence is the load-bearing half.
  const blockText = await page.locator("#today").innerText()
  expect(blockText).toMatch(/\bgap\b/i)
  expect(
    blockText,
    "the model-vs-market quantity is labelled 'edge' — on a marketing page that reads as a claim " +
      "to have one, and `best_alpha = 0` says we do not",
  ).not.toMatch(/\bedge\b/i)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 5 — the blog is demoted, and demoted is not deleted
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("the blog is out of the primary nav but still reachable", async ({ page }) => {
  await mockApi(page)
  await gotoHome(page)

  // ⭐ SCOPED TO THE PRIMARY <nav>, which is what "primary nav" means. A page-wide "no /blog
  // anywhere" assertion would be satisfied only by DELETING the blog, which is not the decision —
  // the GROWTH-100 content engine still publishes to it.
  //
  // ⚠️ `nav a[href^='/blog']` IS NOT THAT SCOPE, and the first cut of this clause failed on it:
  // `SiteFooter` wraps its own links in a `<nav>`, so the selector matched the FOOTER link that
  // this story deliberately keeps. Excluding anything inside `<footer>` is what makes the locator
  // mean what the sentence above says.
  const navBlogLinks = await page.evaluate(
    () =>
      [...document.querySelectorAll("nav a[href^='/blog']")].filter((a) => !a.closest("footer"))
        .length,
  )
  expect(navBlogLinks, "the blog is still in the primary nav").toBe(0)

  // The other half, and the half that makes the rule above safe rather than merely quieter: it has
  // to still be reachable, or this stopped being a demotion.
  const blogLinks = await page.locator("a[href^='/blog']").count()
  expect(blogLinks, "the blog is unreachable from the home page — demoted, not deleted").toBeGreaterThan(0)
  await expect(page.locator("footer a[href='/blog']")).toBeVisible()
})

test("no blog POST is promoted into the page", async ({ page }) => {
  // The pre-E9.46 page fetched the latest post and rendered its TITLE as a section heading above
  // the pick card — which is the promotion this decision reverses. A generic "Blog" link is a
  // demotion; a live headline is not, and the difference is invisible to a link-count check.
  const mock = await mockApi(page)
  await gotoHome(page)

  expect(
    mock.requested.filter((p) => p.startsWith("/blog")),
    "the home page is still fetching blog posts to feature one",
  ).toEqual([])

  // ⚠️ THE OBVIOUS FORM OF THIS ASSERTION IS DEFEATED BY OUR OWN COPY, which is worth recording:
  // the first cut asserted the old eyebrow `/From the Blog/i` was absent, and it FAILED — because
  // the secondary link this story adds reads "Notes from the blog", which contains that substring.
  // A text scan for a heading that a demoted link can accidentally satisfy is not the rule anyway.
  // The real distinction is STRUCTURAL: a link to `/blog` is a demotion; a link to a SPECIFIC post
  // is the promotion this decision reverses.
  const postLinks = await page.locator("a[href^='/blog/']").count()
  expect(
    postLinks,
    "the home page links to a specific blog post — that is featuring one, not demoting the blog",
  ).toBe(0)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 6 — the season roadmap is honest
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("the coming-soon rows are teasers, not links into routes that do not exist", async ({
  page,
}) => {
  await mockApi(page)
  await gotoHome(page)

  await expect(page.getByText(/NCAAF/).first()).toBeVisible()
  await expect(page.getByText(/Around Aug 29/i)).toBeVisible()
  await expect(page.getByText(/Around Sep 9/i)).toBeVisible()

  // ⛔ E9.56c's dead `/pricing` CTA wearing a friendlier label. `route-integrity.spec.ts` would
  // catch a 404 target; it would NOT catch a link to a real-but-empty surface teased as live, so
  // the rule enforced here is that an un-shipped row carries no anchor at all.
  const roadmapRow = page.locator("li", { hasText: "Around Aug 29" })
  expect(await roadmapRow.locator("a").count(), "a coming-soon row is a link").toBe(0)

  // The sentence that keeps the roadmap from promising picks it has no basis to promise.
  await expect(page.getByText(/It does not mean picks we say will win/i)).toBeVisible()
})
